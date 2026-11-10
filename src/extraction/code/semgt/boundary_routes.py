"""Endpoint-anchored semantic curb fitting; never emit a free observed contour.

The normal-offset dynamic program follows measured road/non-road interfaces.
Its search is bounded by the calibrated image and topology, not an arbitrary
8m turn/30m straight cutoff. Every proposed path still passes depth/side tests.
"""
import copy
import itertools
import numpy as np
import cv2
from scipy.interpolate import CubicHermiteSpline
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree
from shapely.geometry import LineString
from .geometry import project
from .surface import layer_mask, depth_world
from .boundary_occlusion import tangent
from .town05_geometry import resample

REVISION='endpoint_anchored_semantic_route_v1'


def reference_field(meta, labels):
    cache=meta.get('_boundary_route_field')
    if cache is not None:
        return cache
    depth=meta['_depth_m']
    world=meta['_world_xyz']
    valid=np.isfinite(depth)&(depth>0)&(depth<999.)&layer_mask(world,meta)
    road=np.isin(labels,[1,24])&valid
    nonroad=np.isin(labels,[2,10])&valid
    kernel=np.ones((3,3),np.uint8)
    contact=(road&(cv2.dilate(nonroad.astype(np.uint8),kernel)>0)) | (nonroad&(cv2.dilate(road.astype(np.uint8),kernel)>0))
    scale=float(meta['metric_scale_m_per_pixel'])
    distance=cv2.distanceTransform((~contact).astype(np.uint8),cv2.DIST_L2,5)*scale
    cache=dict(distance=distance,valid=valid,contact=contact,scale=scale)
    meta['_boundary_route_field']=cache
    return cache


def in_reference(xyz,meta,labels,border=48):
    uv=project(xyz,meta)
    h,w=labels.shape
    return np.isfinite(uv).all(axis=1)&(uv[:,0]>=border)&(uv[:,0]<w-border)&(uv[:,1]>=border)&(uv[:,1]<h-border)


def route_distance(curve,meta,labels):
    field=reference_field(meta,labels)
    uv=np.rint(project(curve,meta)).astype(int)
    h,w=labels.shape
    if np.any(uv<0) or np.any(uv>=[w,h]):
        return dict(mean_m=1e6,p95_m=1e6)
    d=field['distance'][uv[:,1],uv[:,0]]
    return dict(mean_m=float(np.mean(d)),p95_m=float(np.percentile(d,95)))


def small_static_mask(meta,labels,policy):
    """Only compact Static/Other props may supplement named thin occluders."""
    cache=meta.get('_boundary_route_static_mask')
    if cache is not None:return cache
    count,components,stats,_=cv2.connectedComponentsWithStats(np.isin(labels,[20,22]).astype(np.uint8),8)
    limit=policy['boundary_route_static_occluder_max_diagonal_m']
    scale=meta['metric_scale_m_per_pixel']
    allowed=np.zeros(count,bool)
    if count>1:
        allowed[1:]=np.hypot(stats[1:,cv2.CC_STAT_WIDTH],stats[1:,cv2.CC_STAT_HEIGHT])*scale<=limit
    cache=allowed[components]
    meta['_boundary_route_static_mask']=cache
    return cache


def route_evidence(curve,p,q,meta,labels,policy,context,straight):
    from .structural_boundary import evidence
    uv=np.rint(project(curve,meta)).astype(int)
    h,w=labels.shape
    if np.any(uv<0) or np.any(uv>=[w,h]):
        return False,dict(reason='outside_safe_reference')
    x,y=uv[:,0],uv[:,1]
    raised=meta['_world_xyz'][y,x,2]>curve[:,2]+.35
    extra=np.isin(labels[y,x],[20,22])&small_static_mask(meta,labels,policy)[y,x]&raised
    amended=labels
    if extra.any() and policy['boundary_occlusion_enabled']:
        amended=labels.copy()
        amended[y[extra],x[extra]]=6
    accepted,proof=evidence(curve,p,q,meta,amended,policy,context,straight)
    if extra.any():
        proof.update(compact_elevated_static_occluders=np.unique(labels[y[extra],x[extra]]).tolist(),
                     static_object_depth_used_as_ground=False)
    return accepted,proof


def fit(seed,meta,labels,policy):
    """Smooth normal offsets selected by semantic/depth data, with fixed ends."""
    field=reference_field(meta,labels)
    if not field['contact'].any():
        return None,dict(reason='no_measured_road_nonroad_interface')
    step=policy['boundary_route_sample_step_m']
    points=resample(seed,step)
    if len(points)<3:
        return None,dict(reason='insufficient_route_samples')
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,:2],axis=0),axis=1))]
    vectors=np.gradient(points,axis=0)
    normal=np.c_[-vectors[:,1],vectors[:,0],np.zeros(len(points))]
    normal/=np.maximum(np.linalg.norm(normal[:,:2],axis=1)[:,None],1e-12)
    width=policy['boundary_route_fit_width_m']
    offsets=np.linspace(-width,width,2*int(np.ceil(width/.05))+1)
    xyz=points[:,None,:]+normal[:,None,:]*offsets[None,:,None]
    uv=np.rint(project(xyz.reshape(-1,3),meta)).astype(int).reshape(len(points),len(offsets),2)
    h,w=labels.shape
    safe=(uv[:,:,0]>=48)&(uv[:,:,0]<w-48)&(uv[:,:,1]>=48)&(uv[:,:,1]<h-48)
    x,y=np.clip(uv[:,:,0],0,w-1),np.clip(uv[:,:,1],0,h-1)
    values=labels[y,x]
    ground=np.isin(values,[1,2,10,24])&field['valid'][y,x]
    z=meta['_world_xyz'][y,x,2]
    ground&=abs(z-xyz[:,:,2])<=policy['structural_boundary_height_tolerance_m']
    static=np.isin(values,[20,22])&small_static_mask(meta,labels,policy)[y,x]&(z>xyz[:,:,2]+.35)
    occluded=(np.isin(values,[6,7,8])|static)&policy['boundary_occlusion_enabled']
    distance=field['distance'][y,x]
    allowed=safe&(ground|occluded)&(distance<=policy['boundary_route_max_interface_distance_m'])
    cost=1.+(distance/.12)**2+.1*offsets[None,:]**2
    cost+=occluded*2.
    cost[~allowed]=np.inf
    # The route must leave and arrive along the native endpoint tangents.
    reach=np.minimum(lengths,lengths[-1]-lengths)
    limit=width*np.minimum(1.,(reach/.8)**2)
    cost[np.abs(offsets)[None,:]>limit[:,None]+1e-8]=np.inf
    centre=int(np.argmin(abs(offsets)))
    cost[0,:]=np.inf;cost[-1,:]=np.inf
    cost[0,centre]=0.;cost[-1,centre]=0.
    delta=offsets[:,None]-offsets[None,:]
    transition=.7*(delta/max(step,.05))**2
    transition[abs(delta)>.25]=np.inf
    best=cost[0].copy();parent=np.empty(cost.shape,np.int16)
    for i in range(1,len(points)):
        scores=best[:,None]+transition
        parent[i]=np.argmin(scores,axis=0)
        best=cost[i]+np.min(scores,axis=0)
        if not np.isfinite(best).any():
            return None,dict(reason='no_continuous_supported_interface',failed_at_m=float(lengths[i]))
    k=centre;chosen=np.empty(len(points))
    if not np.isfinite(best[k]):
        return None,dict(reason='no_supported_endpoint_arrival')
    for i in range(len(points)-1,-1,-1):
        chosen[i]=offsets[k]
        if i:k=int(parent[i,k])
    fitted=gaussian_filter1d(chosen,max(1.,.20/max(step,.05)),mode='nearest')
    taper=np.minimum(1.,(reach/.8)**2)
    fitted*=taper
    curve=points+normal*fitted[:,None]
    # Correct substantial height differences only from visible measured ground;
    # thin-object depths are never used as a road surface.
    pixel=np.rint(project(curve,meta)).astype(int)
    if not in_reference(curve,meta,labels).all():
        return None,dict(reason='fitted_route_outside_reference')
    px,py=pixel[:,0],pixel[:,1]
    observed=np.isin(labels[py,px],[1,2,10,24])&field['valid'][py,px]
    observed&=abs(meta['_world_xyz'][py,px,2]-curve[:,2])<=policy['structural_boundary_height_tolerance_m']
    if observed.sum()>=3:
        correction=meta['_world_xyz'][py[observed],px[observed],2]-curve[observed,2]
        if np.percentile(abs(correction),80)>.03:
            dz=np.interp(lengths,lengths[observed],correction)
            curve[:,2]+=gaussian_filter1d(dz,max(1.,.25/max(step,.05)))*taper
    curve[0]=seed[0];curve[-1]=seed[-1]
    return curve,dict(method=REVISION,max_normal_offset_m=float(np.max(abs(fitted))),
        interface_distance=route_distance(curve,meta,labels),sample_step_m=step,
        measured_ground_samples=int(observed.sum()),fixed_native_endpoints=True)


def crosses_base(curve,base,i,j):
    line=LineString(curve[:,:2])
    for k,f in enumerate(base):
        if k in (i,j):continue
        p=np.asarray(f['points_xyz'])
        if p[:,2].min()>curve[:,2].max()+.4 or p[:,2].max()<curve[:,2].min()-.4:continue
        if line.crosses(LineString(p[:,:2])):return True
    return False


def connect(base,world,meta,labels,policy):
    from .structural_boundary import merge_chains,assert_preserved
    from .boundary_alignment import pair_bias,aligned_shapes,REVISION as ALIGNED_REVISION
    aligned=policy.get('boundary_route_align_to_xodr',False)
    revision=ALIGNED_REVISION if aligned else REVISION
    audit=dict(base_features=len(base),base_geometry_unchanged=True,standalone_semantic_boundaries=0,
        connections=[],rejected_connections=[],candidate_diagnostics=[],boundary_revision=revision,
        metric_search_limit_m=policy['boundary_route_search_max_gap_m'])
    if not base or not policy['boundary_smooth_enabled']:
        return copy.deepcopy(base),audit
    ends=np.asarray([p for f in base for p in (f['points_xyz'][0],f['points_xyz'][-1])])
    visible=in_reference(ends,meta,labels)
    available=np.flatnonzero(visible)
    pairs=list(itertools.combinations(available.tolist(),2))
    occupied=set()
    for a,b in cKDTree(ends).query_pairs(.04):
        if a//2!=b//2:occupied.update([a,b])
    relations={tuple(r) for r in world.get('road_relations_expanded',world['road_relations'])}
    candidates=[]
    fit_policy=dict(policy,boundary_occlusion_max_run_m=policy['boundary_route_occlusion_max_run_m'])
    for a,b in pairs:
        i,ea=divmod(a,2);j,eb=divmod(b,2)
        if i==j:continue
        sa,sb=base[i]['source'],base[j]['source']
        rid_a,rid_b=sa['road_id'],sb['road_id']
        diagnostic=dict(source_ids=[base[i]['id'],base[j]['id']],endpoint_indices=[[i,ea],[j,eb]])
        audit['candidate_diagnostics'].append(diagnostic)
        if rid_a!=rid_b and tuple(sorted((rid_a,rid_b))) not in relations:
            diagnostic['reason']='no_XODR_topological_relation';continue
        if a in occupied or b in occupied:
            diagnostic['reason']='native_endpoint_already_touching';continue
        p=np.asarray(base[i]['points_xyz']);q=np.asarray(base[j]['points_xyz'])
        p=p[::-1] if ea==0 else p;q=q[::-1] if eb==1 else q
        gap=float(np.linalg.norm(q[0,:2]-p[-1,:2]));diagnostic['gap_m']=gap
        if gap<=.015:
            diagnostic['reason']='already_touching';continue
        cap=policy['boundary_route_search_max_gap_m']
        if cap is not None and gap>cap:
            diagnostic['reason']='configured_search_limit';continue
        if abs(p[-1,2]-q[0,2])>max(.25,.2*gap):
            diagnostic['reason']='endpoint_height_difference';continue
        chord=(q[0]-p[-1])/gap
        ta,tb=tangent(p),tangent(q,True)
        dots=[float(ta[:2]@chord[:2]),float(tb[:2]@chord[:2])]
        diagnostic['tangent_chord_dots']=dots
        if min(dots)<.05 or float(ta[:2]@tb[:2])<np.cos(np.deg2rad(150)):
            diagnostic['reason']='endpoint_direction';continue
        straight=min(dots)>np.cos(np.deg2rad(12)) and float(ta[:2]@tb[:2])>np.cos(np.deg2rad(12))
        diagnostic['mode']='straight' if straight else 'turn'
        ctx=world.get('boundary_context',{})
        context=dict(p_max_offset_m=ctx.get(base[i]['id'],[{},{}])[ea].get('max_offset_m',.8),
                     q_max_offset_m=ctx.get(base[j]['id'],[{},{}])[eb].get('max_offset_m',.8))
        attempts=[];accepted=[]
        bias,bias_error=pair_bias(p,q,meta,labels,policy) if aligned else (None,None)
        if aligned:diagnostic.update(local_bias=bias,alignment_failure=bias_error)
        for factor in ([1.] if straight else [.8,1.,1.171572875,1.35,1.5,1.8]):
            seed=CubicHermiteSpline([0,gap],[p[-1],q[0]],[ta*factor,tb*factor])(np.linspace(0,gap,max(5,int(gap/.1)+1)))
            seed[0]=p[-1];seed[-1]=q[0]
            if not in_reference(seed,meta,labels).all():
                attempts.append(dict(tangent_scale=factor,reason='outside_safe_reference'));continue
            if aligned and bias is not None:
                shapes=aligned_shapes(seed,p,q,bias,meta,labels,policy)
            elif aligned:
                shapes=[(seed,dict(method='native_hermite_alignment_unavailable',alignment_failure=bias_error,
                    native_height_profile=True,measured_surface_height_used_as_output=False),seed,p,q)]
            else:
                fitted,info=fit(seed,meta,labels,policy)
                shapes=[(fitted,info,fitted,p,q)] if fitted is not None else []
                shapes.append((seed,dict(method='endpoint_hermite_evidence_fallback',fitting_failure=info if fitted is None else None),seed,p,q))
            for curve,fit_info,guide,evidence_p,evidence_q in shapes:
                attempt=dict(tangent_scale=factor,fitting=fit_info)
                attempts.append(attempt)
                if LineString(curve).length>policy['boundary_route_max_curve_ratio']*gap or not LineString(np.vstack([p,curve[1:-1],q])).is_simple:
                    attempt['reason']='curve_shape_or_self_intersection';continue
                ok,proof=route_evidence(guide,evidence_p,evidence_q,meta,labels,fit_policy,context,straight)
                if aligned:proof.update(validation_geometry='semantic_guide' if bias is not None else 'native_hermite',
                    output_geometry_definition='XODR_surface_outer_edge')
                attempt.update(accepted=ok,**proof)
                if not ok:continue
                if crosses_base(curve,base,i,j):
                    attempt.update(accepted=False,reason='crosses_existing_structural_boundary');continue
                distances=route_distance(guide,meta,labels)
                score=distances['mean_m']+.1*distances['p95_m']+.15*(1-proof['road_nonroad_fraction'])
                record=dict(kind='XODR_structural_endpoint_semantic_connection',class_name='boundary',
                    boundary_smooth_connection=True,gap_m=gap,source_ids=[base[i]['id'],base[j]['id']],
                    endpoint_indices=[[i,ea],[j,eb]],points_xyz=curve.tolist(),evidence=proof,
                    tangent_scale=factor,straight_connection=straight,semantic_fitting=fit_info,
                    interface_distance=route_distance(curve,meta,labels),route_score=score,boundary_revision=revision)
                if aligned:record.update(semantic_guide_xyz=guide.tolist(),guide_interface_distance=distances)
                accepted.append((score,record))
        diagnostic['curve_attempts']=attempts
        if not accepted:
            diagnostic['reason']=attempts[-1].get('reason','no_supported_route') if attempts else 'no_supported_route'
            audit['rejected_connections'].append(dict(source_ids=diagnostic['source_ids'],gap_m=gap,
                endpoint_indices=diagnostic['endpoint_indices'],evidence=dict(reason=diagnostic['reason']),curve_attempts=attempts));continue
        score,record=min(accepted,key=lambda x:x[0])
        diagnostic.update(reason='supported_candidate',route_score=score,fit_method=record['semantic_fitting']['method'])
        candidates.append((score,gap,a,b,record))
    used=set();selected=[]
    for score,gap,a,b,record in sorted(candidates,key=lambda x:x[:4]):
        if a in used or b in used:continue
        rivals=[v for v in candidates if not ({v[2],v[3]}&used) and (v[2],v[3])!=(a,b)
                and {a,b}&{v[2],v[3]} and abs(v[0]-score)<.025 and abs(v[1]-gap)<.25]
        if rivals:
            audit['rejected_connections'].append(dict(record,evidence=dict(reason='ambiguous_endpoint_pair')));continue
        curve=np.asarray(record['points_xyz'])
        if any(LineString(curve[:,:2]).crosses(LineString(np.asarray(v['points_xyz'])[:,:2])) and
               np.asarray(v['points_xyz'])[:,2].min()<=curve[:,2].max()+.4 and
               np.asarray(v['points_xyz'])[:,2].max()>=curve[:,2].min()-.4 for v in selected):continue
        selected.append(record);used.update([a,b])
    audit['connections']=selected
    chosen={tuple(tuple(e) for e in c['endpoint_indices']) for c in selected}
    for d in audit['candidate_diagnostics']:
        if d['reason']=='supported_candidate':
            d['selection_status']='selected' if tuple(tuple(e) for e in d['endpoint_indices']) in chosen else 'endpoint_or_route_conflict'
    result=merge_chains(base,selected)
    assert_preserved(base,result)
    return result,audit
