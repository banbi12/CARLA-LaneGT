"""Pinned V4.2 boundary structure; semantic evidence may only join endpoints.

No observed contour can become an independent annotation. All original XODR
vertices are preserved; missing unanchored curbs remain for manual review.
"""
import copy
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.spatial import cKDTree
from shapely.geometry import Point, LineString
from mapgt.common import digest
from .io import load, sha
from .geometry import project
from .surface import depth_world, layer_mask
from .town05_geometry import runs, resample
from .boundary_occlusion import tangent

GENERATOR = 'pinned_xodr_v42_boundary_structure_v1'
GROUND_NONROAD = (2, 10)  # CARLA 0.9.16: Sidewalks, Terrain (verified local API).


def boundary_context(xodr, features):
    """Describe known non-road apron width; never move the pinned boundary.

    A one-way road's reference-line boundary can be outside a 2m sidewalk.
    The old 0.8m semantic probe then sees Sidewalk on both sides everywhere.
    Only an explicitly represented lane prefix can authorize wider probes.
    """
    from .legacy_xodr import XodrMap
    xmap=XodrMap.from_file(xodr);result={}
    for feature in features:
        src=feature['source'];ends=[];road=xmap.by_id[src['road_id']]
        for s in [src['s_start'],src['s_end']]:
            sec=next(sec for sec in road.sections if sec.s==src['section_s'])
            width=0.;prefix=[]
            if src.get('selection')=='centerline_oneway_edge' and src['lane_id']==0:
                sides=[[l for l in sec.lanes if l.id*sign>0] for sign in (1,-1)]
                active=[side for side in sides if any(l.width_at(float(s))>.01 for l in side)]
                if len(active)==1:
                    for lane in sorted(active[0],key=lambda l:abs(l.id)):
                        if lane.type not in ('sidewalk','shoulder','border','curb'):break
                        width+=lane.width_at(float(s));prefix.append(dict(lane_id=lane.id,lane_type=lane.type))
            ends.append(dict(max_offset_m=max(.8,width+.35) if prefix else .8,
                xodr_nonroad_prefix_m=width,lane_prefix=prefix))
        result[feature['id']]=ends
    return result


def road_relations(path,include_outgoing=False):
    root = ET.parse(path).getroot()
    road_nodes={int(r.get('id')):r for r in root.findall('road')}
    relations = set()
    for r in root.findall('road'):
        rid = int(r.get('id'))
        for node in r.findall('link/*'):
            if node.get('elementType') == 'road':
                relations.add(tuple(sorted((rid, int(node.get('elementId'))))))
    for j in root.findall('junction'):
        roads = set()
        for c in j.findall('connection'):
            roads.update([int(c.get('incomingRoad')), int(c.get('connectingRoad'))])
            if include_outgoing:
                connecting=road_nodes.get(int(c.get('connectingRoad')))
                if connecting is not None:
                    for link in connecting.findall('link/*'):
                        if link.get('elementType')=='road':roads.add(int(link.get('elementId')))
        for a in roads:
            for b in roads:
                relations.add(tuple(sorted((a, b))))
    return sorted(relations)


def load_world(project, map_profile):
    from .map_profile import read
    profile = read(project, map_profile)
    repository = Path(project).resolve().parents[1]
    pin = load(repository/profile['baseline_pin'])
    native = repository/'assets'/pin['source_world_asset']
    xodr = repository/'assets'/profile['xodr_asset']
    if sha(native) != pin['source_world_sha256'] or sha(xodr) != pin['xodr_sha256']:
        raise ValueError('Structural boundary source identity mismatch')
    world = load(native)
    if world['xodr_sha256'] != profile['xodr_sha256'] or world['map_name'] != profile['map_id']:
        raise ValueError('Structural boundary map identity mismatch')
    features = [f for f in world['features'] if f['class_name']=='boundary']
    if not features:raise ValueError('Pinned XODR structural boundary is empty')
    return dict(schema='lanegt_structural_boundary_world_v1',generator=GENERATOR,
        map_name=profile['map_id'],xodr_sha256=world['xodr_sha256'],features=copy.deepcopy(features),
        source_world_sha256=pin['source_world_sha256'],road_relations=road_relations(xodr),
        road_relations_expanded=road_relations(xodr,include_outgoing=True),
        boundary_context=boundary_context(xodr,features),
        audit=dict(features=len(features),exact_pinned_V42_boundary=True,base_geometry_unchanged=True,
            global_XY_union=False,semantic_images_used=False,
            limitations='V42 road-local candidates can miss unmarked curb sections; semantic adds connections only'))


def side_votes(xyz, vectors, meta, labels, policy, max_offsets=None):
    normal = np.c_[-vectors[:, 1], vectors[:, 0], np.zeros(len(vectors))]
    normal /= np.maximum(np.linalg.norm(normal[:, :2], axis=1)[:, None], 1e-12)
    votes = np.zeros(len(xyz), int)
    h, w = labels.shape
    limit=np.broadcast_to(.8 if max_offsets is None else max_offsets,(len(xyz),))
    limit=np.minimum(limit,policy['structural_boundary_context_max_offset_m'])
    for offset in (.15, .3, .5, .8, 1., 1.25, 1.5, 2., 2.5, 3., 3.5, 4.):
        if not np.any(limit>=offset):continue
        probe = np.vstack([xyz+normal*offset, xyz-normal*offset])
        uv = np.rint(project(probe, meta)).astype(int)
        safe = (uv[:, 0]>=48)&(uv[:, 0]<w-48)&(uv[:, 1]>=48)&(uv[:, 1]<h-48)
        x, y = np.clip(uv[:, 0], 0, w-1), np.clip(uv[:, 1], 0, h-1)
        values, d = labels[y, x], meta['_depth_m'][y, x]
        valid = safe & np.isin(values, [1, 24]+list(GROUND_NONROAD)) & np.isfinite(d)&(d>0)&(d<999.)
        if valid.any():
            actual = depth_world(uv[valid], meta)
            valid[valid] = layer_mask(actual, meta)&(abs(actual[:, 2]-probe[valid, 2])<=policy['structural_boundary_height_tolerance_m'])
        plus, minus = values.reshape(2, -1)
        good = valid.reshape(2, -1).all(axis=0)&(votes==0)&(limit>=offset)
        votes[good&np.isin(plus, [1, 24])&np.isin(minus, GROUND_NONROAD)] = 1
        votes[good&np.isin(minus, [1, 24])&np.isin(plus, GROUND_NONROAD)] = -1
    return votes


def evidence(curve, p, q, meta, labels, policy, context=None, straight=False):
    """Visible ground on opposite sides; only labelled thin objects may obscure it."""
    def reject(reason, **extra):
        return False, dict(reason=reason, **extra)
    context=context or dict(p_max_offset_m=.8,q_max_offset_m=.8)
    offsets=[context['p_max_offset_m'],context['q_max_offset_m']]
    tails = [resample(p), resample(q)]
    votes = []
    contexts=[]
    for index,points in enumerate(tails):
        if len(points)<3:
            return reject('insufficient_structural_endpoint_context')
        side=0
        for n in [7,13,21]:
            tail=points[-n:] if index==0 else points[:n]
            v=np.gradient(tail,axis=0)
            vote=side_votes(tail,v,meta,labels,policy,offsets[index])
            side=1 if np.mean(vote==1)>=.6 else (-1 if np.mean(vote==-1)>=.6 else 0)
            if side:
                contexts.append(dict(samples=len(tail),max_offset_m=min(offsets[index],policy['structural_boundary_context_max_offset_m']),supported_fraction=float(np.mean(vote==side))))
                break
        votes.append(side)
    if not votes[0] or votes[0]!=votes[1]:
        return reject('endpoint_road_nonroad_roles_disagree', sides=votes)
    uv = np.rint(project(curve, meta)).astype(int)
    h, w = labels.shape
    if np.any(uv<[48,48]) or np.any(uv>=[w-48,h-48]):
        return reject('outside_safe_reference')
    x,y = uv[:, 0],uv[:, 1]
    values = labels[y,x]
    blocked = np.isin(values, [6,7,8])
    if blocked.any() and not policy['boundary_occlusion_enabled']:
        return reject('occlusion_connection_disabled')
    known = np.isin(values,[1,2,10,24])
    if not (known|blocked).all():
        return reject('unexplained_semantic_class')
    d = meta['_depth_m'][y,x]
    visible = ~blocked
    if not visible.any() or np.mean(visible)<.2:
        return reject('insufficient_visible_ground')
    if not (np.isfinite(d[visible])&(d[visible]>0)&(d[visible]<999.)).all():
        return reject('invalid_visible_depth')
    actual = depth_world(uv[visible],meta)
    error = float(np.max(abs(actual[:,2]-curve[visible,2])))
    if not layer_mask(actual,meta).all() or error>policy['structural_boundary_height_tolerance_m']:
        return reject('visible_height_or_layer_mismatch', max_height_error_m=error)
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(curve[:,:2],axis=0),axis=1))]
    edges=np.r_[0.,(lengths[:-1]+lengths[1:])/2,lengths[-1]]
    blocked_run=max([float(edges[b]-edges[a]) for a,b in runs(blocked)]+[0.])
    if blocked_run>policy['boundary_occlusion_max_run_m']:
        return reject('thin_occluder_span_too_long', blocked_run_m=blocked_run)
    vote = side_votes(curve,np.gradient(curve,axis=0),meta,labels,policy,
        np.linspace(offsets[0],offsets[1],len(curve)))
    fraction = float(np.mean(vote==votes[0]))
    threshold=policy['structural_boundary_straight_semantic_fraction'] if straight else policy['structural_boundary_semantic_fraction']
    if fraction<threshold:
        return reject('insufficient_road_nonroad_connection_support', fraction=fraction)
    return True, dict(method='XODR_endpoint_connection_with_depth_and_road_nonroad_evidence',
        road_nonroad_fraction=fraction, max_height_error_m=error,
        blocked_run_m=blocked_run, inferred_not_measured=bool(blocked.any()),
        ground_nonroad_labels=list(GROUND_NONROAD), standalone_semantic_geometry=False,
        endpoint_context=contexts,context=context,straight_connection=straight)


def merge_chains(base, selected):
    """Merge only linked endpoints; every native vertex is retained verbatim."""
    links={}
    for record in selected:
        a,b=map(tuple,record['endpoint_indices'])
        curve=np.asarray(record['points_xyz'])
        links[a]=(b,curve,record);links[b]=(a,curve[::-1],record)
    remaining=set(range(len(base)));out=[]
    while remaining:
        seed=min(remaining)
        component={seed};todo=[seed]
        while todo:
            i=todo.pop()
            for e in (0,1):
                if (i,e) in links:
                    j=links[(i,e)][0][0]
                    if j not in component:component.add(j);todo.append(j)
        starts=[(i,e) for i in sorted(component) for e in (0,1) if (i,e) not in links]
        current=min(starts) if starts else (seed,0)
        arrays=[];sources=[];records=[];seen=set()
        while current[0] not in seen:
            i,e=current;seen.add(i);remaining.remove(i)
            p=np.asarray(base[i]['points_xyz']);arrays.append(p if e==0 else p[::-1]);sources.append(base[i]['id'])
            exit=(i,1-e)
            if exit not in links:break
            current,curve,record=links[exit];records.append(record)
            arrays.append(curve[1:] if current[0] in seen else curve[1:-1])
        if not records:
            out.append(copy.deepcopy(base[seed]));continue
        points=np.vstack([a for a in arrays if len(a)]).tolist()
        out.append(dict(id='boundary:'+digest(dict(base_ids=sources,points=points))[:24],
            class_name='boundary',points_xyz=points,
            source=dict(kind='XODR_structural_boundary_with_semantic_connections',base_ids=sources,
                base_geometry_unchanged=True,standalone_semantic_geometry=False),connections=records))
    return out


def connect(base, world, meta, labels, policy):
    if policy.get('boundary_route_enabled',False):
        from .boundary_routes import connect as route_connect
        return route_connect(base,world,meta,labels,policy)
    return connect_legacy(base,world,meta,labels,policy)


def connect_legacy(base, world, meta, labels, policy):
    audit=dict(base_features=len(base), base_geometry_unchanged=True,
        standalone_semantic_boundaries=0, connections=[], rejected_connections=[])
    if not base or not policy['boundary_smooth_enabled']:
        return copy.deepcopy(base),audit
    relations={tuple(r) for r in world['road_relations']}
    ends=np.asarray([p for f in base for p in (f['points_xyz'][0],f['points_xyz'][-1])])
    pairs=sorted(cKDTree(ends[:,:2]).query_pairs(policy['structural_boundary_straight_max_gap_m']))
    # Native endpoints that already touch another endpoint do not need a branch.
    occupied=set()
    for a,b in cKDTree(ends).query_pairs(.04):
        if a//2!=b//2:occupied.update([a,b])
    candidates=[];diagnostics=[]
    audit['candidate_diagnostics']=diagnostics
    for a,b in pairs:
        i,ea=divmod(a,2);j,eb=divmod(b,2)
        if i==j:continue
        sa,sb=base[i]['source'],base[j]['source']
        rid_a,rid_b=sa['road_id'],sb['road_id']
        if rid_a!=rid_b and tuple(sorted((rid_a,rid_b))) not in relations:continue
        p=np.asarray(base[i]['points_xyz']);q=np.asarray(base[j]['points_xyz'])
        p=p[::-1] if ea==0 else p;q=q[::-1] if eb==1 else q
        gap=float(np.linalg.norm(q[0,:2]-p[-1,:2]))
        diagnostic=dict(source_ids=[base[i]['id'],base[j]['id']],endpoint_indices=[[i,ea],[j,eb]],gap_m=gap)
        diagnostics.append(diagnostic)
        if a in occupied or b in occupied:
            diagnostic.update(reason='native_endpoint_already_touching');continue
        if gap<=.015:
            diagnostic.update(reason='already_touching');continue
        if abs(p[-1,2]-q[0,2])>max(.25,.2*gap):
            diagnostic.update(reason='endpoint_height_difference');continue
        chord=(q[0]-p[-1])/gap
        ta,tb=tangent(p),tangent(q,True)
        dots=[float(ta[:2]@chord[:2]),float(tb[:2]@chord[:2])]
        diagnostic['tangent_chord_dots']=dots
        straight=gap>policy['structural_boundary_max_gap_m']
        if straight:
            parallel=float(ta[:2]@tb[:2])
            lateral=max(abs(float(np.cross(ta[:2],q[0,:2]-p[-1,:2]))),abs(float(np.cross(tb[:2],q[0,:2]-p[-1,:2]))))
            if min(dots)<np.cos(np.deg2rad(3)) or parallel<np.cos(np.deg2rad(3)) or lateral>.2:
                diagnostic.update(reason='long_gap_requires_collinear_straight_edges',lateral_m=lateral);continue
        elif min(dots)<.1:
            diagnostic.update(reason='endpoint_direction');continue
        ctx=world.get('boundary_context',{})
        context=dict(p_max_offset_m=ctx.get(base[i]['id'],[{},{}])[ea].get('max_offset_m',.8),
            q_max_offset_m=ctx.get(base[j]['id'],[{},{}])[eb].get('max_offset_m',.8))
        attempts=[];record=None
        # Try the frozen shape first, then quarter-circle-compatible curvature.
        # Only a supported endpoint connector may be emitted; no contour is added.
        for factor in ([1.] if straight else [1.,1.171572875,1.35,1.5]):
            curve=CubicHermiteSpline([0,gap],[p[-1],q[0]],[ta*factor,tb*factor])(np.linspace(0,gap,max(5,int(gap/.06)+1)))
            curve[0]=p[-1];curve[-1]=q[0]
            if LineString(curve).length>1.6*gap or not LineString(np.vstack([p,curve[1:-1],q])).is_simple:
                attempts.append(dict(tangent_scale=factor,reason='curve_shape_or_self_intersection'));continue
            accepted,proof=evidence(curve,p,q,meta,labels,policy,context,straight)
            attempts.append(dict(tangent_scale=factor,accepted=accepted,**proof))
            if accepted:
                # A candidate must not cross unrelated existing boundary geometry.
                line=LineString(curve[:,:2]);blocked=False
                for k,f in enumerate(base):
                    if k in (i,j):continue
                    near=resample(f['points_xyz'],.2)
                    if np.min(np.linalg.norm(near[:,:2]-curve[len(curve)//2,:2],axis=1))>gap+1:continue
                    if near[:,2].min()>curve[:,2].max()+.4 or near[:,2].max()<curve[:,2].min()-.4:continue
                    if line.crosses(LineString(near[:,:2])):blocked=True;break
                if blocked:
                    attempts[-1].update(accepted=False,reason='crosses_existing_structural_boundary');continue
            record=dict(kind='XODR_structural_endpoint_semantic_connection',class_name='boundary',
                boundary_smooth_connection=True,gap_m=gap,source_ids=[base[i]['id'],base[j]['id']],
                endpoint_indices=[[i,ea],[j,eb]],points_xyz=curve.tolist(),evidence=proof,
                tangent_scale=factor,straight_connection=straight)
            if accepted:break
        diagnostic['curve_attempts']=attempts
        if record is None or not attempts[-1].get('accepted'):
            diagnostic.update(reason=attempts[-1].get('reason','no_supported_curve') if attempts else 'no_supported_curve')
            if record is not None:audit['rejected_connections'].append(dict(record,curve_attempts=attempts))
            continue
        diagnostic.update(reason='supported_candidate',tangent_scale=record['tangent_scale'])
        candidates.append((gap,a,b,record))
    used=set();selected=[]
    for gap,a,b,record in sorted(candidates,key=lambda c:c[:3]):
        if a in used or b in used:continue
        rivals=[v for v in candidates if not ({v[1],v[2]} & used) and (v[1],v[2])!=(a,b) and {a,b}&{v[1],v[2]} and v[0]<gap+.25]
        if rivals:
            audit['rejected_connections'].append(dict(record,evidence=dict(reason='ambiguous_endpoint_pair')));continue
        curve=np.asarray(record['points_xyz'])
        if any(LineString(curve[:,:2]).crosses(LineString(np.asarray(v['points_xyz'])[:,:2])) and
               np.asarray(v['points_xyz'])[:,2].min()<=curve[:,2].max()+.4 and
               np.asarray(v['points_xyz'])[:,2].max()>=curve[:,2].min()-.4 for v in selected):continue
        selected.append(record);used.update([a,b])
    audit['connections']=selected
    chosen={tuple(tuple(e) for e in c['endpoint_indices']) for c in selected}
    rejected={tuple(tuple(e) for e in c['endpoint_indices']):c['evidence'].get('reason','rejected') for c in audit['rejected_connections']}
    for row in diagnostics:
        if row['reason']=='supported_candidate':
            pair=tuple(tuple(e) for e in row['endpoint_indices'])
            row['selection_status']='selected' if pair in chosen else rejected.get(pair,'endpoint_or_crossing_conflict')
    result=merge_chains(base,selected)
    assert_preserved(base,result)
    return result,audit


def assert_preserved(base, result):
    """Fail closed if any structural curve was removed, shifted or reclassified."""
    for original in base:
        owners=[f for f in result if f['id']==original['id'] or original['id'] in f.get('source',{}).get('base_ids',[])]
        if len(owners)!=1 or owners[0]['class_name']!='boundary':
            raise ValueError('Structural boundary lost or duplicated: '+original['id'])
        a=original['points_xyz'];b=owners[0]['points_xyz']
        if not any(b[i:i+len(a)] in (a,a[::-1]) for i in range(len(b)-len(a)+1)):
            raise ValueError('Original structural vertices were moved: '+original['id'])
