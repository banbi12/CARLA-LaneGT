"""V4.5 target organization; frozen V4.2 world geometry is never modified."""
import copy,hashlib,json,math
import numpy as np
from scipy.spatial import cKDTree

RULE='divider_target_duplicate_containment_and_touching_chain_v2'
DEFAULT=dict(duplicate_tolerance_m=1e-5,endpoint_tolerance_m=1e-5,max_tangent_bend_deg=15.)


def checked(policy=None):
    p=dict(DEFAULT)
    if policy:
        if set(policy)-set(p):raise ValueError('Unknown divider target policy')
        p.update(policy)
    if not 0<p['duplicate_tolerance_m']<=1e-4 or not 0<p['endpoint_tolerance_m']<=1e-4:
        raise ValueError('Target normalization only accepts coincident geometry')
    if not 0<p['max_tangent_bend_deg']<=20:raise ValueError('Invalid target tangent bound')
    return p


def canonical(points,tolerance=1e-7):
    """Compare identical polylines despite redundant straight-line vertices."""
    out=[]
    for point in np.asarray(points,float):
        if out and np.linalg.norm(point-out[-1])<=1e-10:continue
        out.append(point)
        while len(out)>=3:
            a,b,c=out[-3:];d=c-a;n=float(d@d)
            if n<1e-20:break
            t=float((b-a)@d/n)
            if not 0<=t<=1 or np.linalg.norm(b-(a+t*d))>tolerance:break
            out.pop(-2)
    return np.asarray(out)


def equivalent(a,b,tolerance,directed=False):
    if a.shape!=b.shape:return False
    if np.max(abs(a-b))<=tolerance or (not directed and np.max(abs(a-b[::-1]))<=tolerance):return True
    if len(a)>3 and np.linalg.norm(a[0]-a[-1])<=tolerance and np.linalg.norm(b[0]-b[-1])<=tolerance:
        for sequence in ([b[:-1]] if directed else [b[:-1],b[-2::-1]]):
            for k in np.flatnonzero(np.max(abs(sequence-a[0]),axis=1)<=tolerance):
                if np.max(abs(a[:-1]-np.roll(sequence,-int(k),axis=0)))<=tolerance:return True
    return False


def outward(points,end):
    p=np.asarray(points,float)
    if end:p=p[::-1]
    for q in p[1:]:
        v=q-p[0];n=np.linalg.norm(v)
        if n>1e-9:return v/n
    raise ValueError('Divider target has no valid endpoint tangent')


def projected(points,curve):
    """Nearest positions on a piecewise-linear XYZ curve, including its height."""
    vectors=np.diff(curve,axis=0);lengths=np.linalg.norm(vectors,axis=1)
    fractions=np.clip(np.sum((points[:,None,:]-curve[None,:-1,:])*vectors[None,:,:],axis=2)
        /np.maximum(lengths[None,:]**2,1e-30),0,1)
    distances=np.linalg.norm(points[:,None,:]-(curve[None,:-1,:]+fractions[:,:,None]*vectors[None,:,:]),axis=2)
    indices=np.argmin(distances,axis=1);rows=np.arange(len(points))
    positions=np.r_[0.,np.cumsum(lengths)][indices]+fractions[rows,indices]*lengths[indices]
    return distances[rows,indices],positions


def contained(a,b,tolerance,directed=False):
    """A follows one unchanged subcurve of B; proximity or crossing is insufficient.

    Compare both directions over the covered interval, with monotone arc
    positions. Never synthesize an extension or apply a planar road union.
    Closed and self-intersecting curves need explicit topology and stay apart.
    """
    if len(a)<2 or len(b)<2:return False
    if np.linalg.norm(a[0]-a[-1])<=tolerance or np.linalg.norm(b[0]-b[-1])<=tolerance:return False
    from shapely.geometry import LineString
    if not LineString(a[:,:2]).is_simple or not LineString(b[:,:2]).is_simple:return False
    distances,positions=projected(a,b)
    if distances.max()>tolerance:return False
    if positions[-1]<positions[0]:
        if directed:return False
        a=a[::-1];positions=positions[::-1]
    if np.any(np.diff(positions)<-tolerance):return False
    length=float(np.linalg.norm(np.diff(a,axis=0),axis=1).sum())
    if abs(positions[-1]-positions[0]-length)>2*tolerance*len(a):return False
    bs=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(b,axis=0),axis=1))]
    interior=b[(bs>positions[0])&(bs<positions[-1])]
    # Every B vertex in the interval must also lie on A. Together with monotone
    # projection, this rejects a shortcut through a bend and an unrelated fork.
    if len(interior) and projected(interior,a)[0].max()>tolerance:return False
    return True


def normalize(targets,bev_range=None,policy=None):
    return normalize_class(targets,bev_range,policy)


def parent_ids(target):
    return set(target['source'].get('input_parent_ids',[target['parent_id']]))


def normalize_class(targets,bev_range=None,policy=None,class_name='divider',directed=False,
                    preserve_parent_cuts=False,rule=RULE):
    policy=checked(policy);raw=[t for t in targets if t['class_name']==class_name]
    audit=dict(rule=rule,policy=policy,class_name=class_name,directed=directed,
        preserve_parent_cuts=preserve_parent_cuts,input_targets=len(raw),output_targets=len(raw),
        input_dividers=len(raw),output_dividers=len(raw),
        duplicate_groups=[],joins=[],rejected_endpoints=[],raw_world_modified=False,
        semantic_divider_geometry_added=False,duplicate_instances_removed=0,joins_count=0,
        exact_duplicate_instances_removed=0,contained_instances_removed=0,contained_groups=[])
    if not raw:return copy.deepcopy(targets),audit
    kept=[];groups=[];curves=[];mins=[];maxs=[]
    for i,target in enumerate(raw):
        p=np.asarray(target['full_xyz'],float)
        if p.ndim!=2 or p.shape[1]!=3 or len(p)<2 or not np.isfinite(p).all():raise ValueError('Invalid divider target XYZ')
        if not np.array_equal(p[:,:2],np.asarray(target['full'])):raise ValueError('Divider XY/XYZ differ')
        c=canonical(p);low=p.min(axis=0);high=p.max(axis=0);found=None
        if len(c)<2:raise ValueError('Degenerate divider target')
        for j,q in enumerate(curves):
            if np.max(abs(low-mins[j]))>policy['duplicate_tolerance_m'] or np.max(abs(high-maxs[j]))>policy['duplicate_tolerance_m']:continue
            if equivalent(c,q,policy['duplicate_tolerance_m'],directed):found=j;break
        if found is None:
            kept.append(target);groups.append([i]);curves.append(c);mins.append(low);maxs.append(high)
        else:groups[found].append(i)
    for group in groups:
        if len(group)>1:audit['duplicate_groups'].append([raw[i]['id'] for i in group])
    audit['exact_duplicate_instances_removed']=sum(len(g)-1 for g in groups)
    # Nearly equal endpoints and differently clipped road records can describe
    # nested subcurves. Retain the longest existing geometry before constructing
    # the endpoint graph, so redundant pieces do not create false branches.
    representatives=[]
    for i in sorted(range(len(kept)),key=lambda j:(-float(np.linalg.norm(np.diff(curves[j],axis=0),axis=1).sum()),j)):
        owner=None
        for j in representatives:
            tol=policy['duplicate_tolerance_m']
            if np.any(mins[i]<mins[j]-tol) or np.any(maxs[i]>maxs[j]+tol):continue
            if contained(curves[i],curves[j],tol,directed):owner=j;break
        if owner is None:representatives.append(i)
        else:
            audit['contained_groups'].append(dict(retained_target_id=kept[owner]['id'],
                contained_target_ids=[raw[k]['id'] for k in groups[i]]))
            audit['contained_instances_removed']+=1;groups[owner]+=groups[i]
    representatives.sort(key=lambda i:min(groups[i]))
    kept=[kept[i] for i in representatives];groups=[groups[i] for i in representatives]
    ends=np.asarray([p for t in kept for p in [t['full_xyz'][0],t['full_xyz'][-1]]])
    neighbors={i:[] for i in range(len(ends))};closed={i for i,t in enumerate(kept) if np.linalg.norm(ends[2*i]-ends[2*i+1])<1e-9}
    for a,b in sorted(cKDTree(ends).query_pairs(policy['endpoint_tolerance_m'])):
        if a//2==b//2 or a//2 in closed or b//2 in closed:continue
        if directed and a%2==b%2:continue
        if bev_range is not None:
            p=ends[a];lo=np.asarray(bev_range[:2]);hi=np.asarray(bev_range[2:])
            if min(np.min(abs(p[:2]-lo)),np.min(abs(p[:2]-hi)))<=policy['endpoint_tolerance_m']:continue
        neighbors[a].append(b);neighbors[b].append(a)
    links={}
    for a,bs in neighbors.items():
        if not bs:continue
        if len(bs)!=1 or len(neighbors[bs[0]])!=1:
            audit['rejected_endpoints'].append(dict(target_id=kept[a//2]['id'],end=a%2,reason='branch_or_ambiguous_continuation'));continue
        b=bs[0]
        if a>b:continue
        if preserve_parent_cuts:
            pa=set().union(*(parent_ids(raw[k]) for k in groups[a//2]))
            pb=set().union(*(parent_ids(raw[k]) for k in groups[b//2]))
            if pa&pb:
                audit['rejected_endpoints'].append(dict(target_id=kept[a//2]['id'],end=a%2,reason='intentional_boundary_partition'));continue
        dot=float(-outward(kept[a//2]['full_xyz'],a%2)@outward(kept[b//2]['full_xyz'],b%2))
        bend=math.degrees(math.acos(float(np.clip(dot,-1,1))))
        if bend>policy['max_tangent_bend_deg']:
            audit['rejected_endpoints'].append(dict(target_id=kept[a//2]['id'],end=a%2,reason='tangent_discontinuity',bend_deg=bend));continue
        links[a]=b;links[b]=a
        audit['joins'].append(dict(target_ids=[kept[a//2]['id'],kept[b//2]['id']],ends=[a%2,b%2],
            endpoint_gap_m=float(np.linalg.norm(ends[a]-ends[b])),bend_deg=bend))
    remaining=set(range(len(kept)));normalized=[];owned=[]
    while remaining:
        seed=min(remaining);component={seed};todo=[seed]
        while todo:
            i=todo.pop()
            for e in (2*i,2*i+1):
                if e in links and links[e]//2 not in component:component.add(links[e]//2);todo.append(links[e]//2)
        start=min([e for i in component for e in ([2*i] if directed else [2*i,2*i+1]) if e not in links] or [2*seed])
        current=start;visited=set();points=[];members=[]
        while current//2 not in visited:
            i,end=divmod(current,2);visited.add(i);remaining.remove(i);members+=groups[i]
            if directed and end:raise ValueError('Directed centerline order was reversed')
            p=copy.deepcopy(kept[i]['full_xyz']);p=p[::-1] if end else p
            if points and points[-1]==p[0]:points+=p[1:]
            else:points+=p
            exit=2*i+1-end
            if exit not in links:break
            current=links[exit]
            if current//2 in visited and points[-1]!=points[0]:points.append(copy.deepcopy(points[0]))
        members=sorted(members);owned+=members
        if len(members)==1:
            normalized.append((members[0],copy.deepcopy(raw[members[0]])));continue
        identities=[raw[i]['id'] for i in members]
        identity=class_name+'_target:'+hashlib.sha256(json.dumps(dict(ids=identities,points=points),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
        normalized.append((members[0],dict(id=identity,parent_id=identity,class_name=class_name,full=[p[:2] for p in points],full_xyz=points,
            source=dict(kind='V45_'+class_name+'_target_normalized',rule=rule,input_target_ids=identities,
                input_parent_ids=sorted(set().union(*(parent_ids(raw[i]) for i in members))),
                original_sources=[dict(target_id=raw[i]['id'],source=copy.deepcopy(raw[i]['source'])) for i in members],
                geometry_source=('frozen XODR-only V4.2; duplicate/contained subcurve cleanup and coincident endpoint chains only' if class_name=='divider' else 'existing accepted '+class_name+' XYZ; target organization only'),
                **(dict(direction_preserved=True) if directed else {})))))
    new=[t for _,t in sorted(normalized,key=lambda v:v[0])];out=[];inserted=False
    for target in targets:
        if target['class_name']==class_name:
            if not inserted:out+=new;inserted=True
        else:out.append(copy.deepcopy(target))
    if sorted(owned)!=list(range(len(raw))):raise ValueError('Divider target source coverage lost')
    audit.update(output_dividers=len(new),output_targets=len(new),duplicate_instances_removed=sum(len(g)-1 for g in groups),
        joins_count=len(audit['joins']),all_input_instances_represented=True)
    return out,audit
