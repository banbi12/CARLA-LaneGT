"""Infer short curb continuations behind labelled poles, lights and signs only.

The connector's height comes from observed endpoints. Object depth is never
treated as road depth; visible samples and curb-side context must agree.
"""
import numpy as np
from .geometry import project
from .surface import depth_world, layer_mask

OCCLUDER_IDS = (6, 7, 8)  # CARLA 0.9.16 CityObjectLabel: Poles, TrafficLight, TrafficSigns.


def tangent(points, start=False, window=.6):
    p = np.asarray(points, float)
    if start:
        return -tangent(p[::-1], False, window)
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
    before = np.array([np.interp(max(0.,s[-1]-window),s,p[:,j]) for j in range(3)])
    v = p[-1]-before
    return v/max(np.linalg.norm(v[:2]),1e-12)


def tail_samples(points,policy,start=False):
    p = np.asarray(points,float)
    if start:p=p[::-1]
    s = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
    if s[-1]<.15:return np.empty((0,3)),np.empty((0,3))
    at=np.linspace(max(0.,s[-1]-policy['boundary_occlusion_context_m']),max(0.,s[-1]-.02),9)
    xyz=np.column_stack([np.interp(at,s,p[:,j]) for j in range(3)])
    before=np.column_stack([np.interp(np.maximum(0,at-.12),s,p[:,j]) for j in range(3)])
    after=np.column_stack([np.interp(np.minimum(s[-1],at+.12),s,p[:,j]) for j in range(3)])
    v=after-before;v/=np.maximum(np.linalg.norm(v[:,:2],axis=1)[:,None],1e-12)
    return xyz,-v if start else v


def road_side(xyz,v,meta,labels,policy):
    if not len(xyz):return np.zeros(0,int)
    normal=np.c_[-v[:,1],v[:,0],np.zeros(len(v))]
    votes=np.zeros(len(xyz),int)
    h,w=labels.shape
    for offset in np.array([.6,1.2,1.8,2.5])*policy['boundary_occlusion_side_offset_m']:
        probe=np.vstack([xyz+normal*offset,xyz-normal*offset])
        uv=np.rint(project(probe,meta)).astype(int)
        safe=(uv[:,0]>=48)&(uv[:,0]<w-48)&(uv[:,1]>=48)&(uv[:,1]<h-48)
        x=np.clip(uv[:,0],0,w-1);y=np.clip(uv[:,1],0,h-1)
        values=labels[y,x];d=meta['_depth_m'][y,x]
        good=safe&np.isin(values,[1,2,24])&np.isfinite(d)&(d>0)&(d<999.)
        if good.any():
            actual=depth_world(uv[good],meta)
            good[good]=layer_mask(actual,meta)&(np.abs(actual[:,2]-probe[good,2])<=policy['boundary_occlusion_height_tolerance_m']+.08)
        plus,minus=values.reshape(2,-1);valid=good.reshape(2,-1).all(axis=0)&(votes==0)
        votes[valid&np.isin(plus,[1,24])&(minus==2)]=1
        votes[valid&(plus==2)&np.isin(minus,[1,24])]=-1
    return votes


def side_context(points,meta,labels,policy,start=False):
    xyz,v=tail_samples(points,policy,start)
    if not len(xyz):return 0
    votes=road_side(xyz,v,meta,labels,policy)
    positive=np.mean(votes==1);negative=np.mean(votes==-1)
    threshold=policy['boundary_occlusion_side_fraction']
    return 1 if positive>=threshold else -1 if negative>=threshold else 0


def visible_tail(points, meta, labels, policy, start=False):
    xyz,_=tail_samples(points,policy,start)
    if not len(xyz):return False
    uv=np.rint(project(xyz,meta)).astype(int);h,w=labels.shape
    if np.any(uv<[48,48]) or np.any(uv>=[w-48,h-48]):return False
    x,y=uv[:,0],uv[:,1];d=meta['_depth_m'][y,x]
    good=np.isin(labels[y,x],[1,2,24])&np.isfinite(d)&(d>0)&(d<999.)
    if good.mean()<.6:return False
    actual=depth_world(uv[good],meta)
    return bool(layer_mask(actual,meta).all() and
        np.max(np.abs(actual[:,2]-xyz[good,2]))<=policy['boundary_occlusion_height_tolerance_m'])


def visible_endpoints(p,q,meta,labels,policy):
    xyz=np.asarray([p[-1],q[0]]);uv=np.rint(project(xyz,meta)).astype(int);h,w=labels.shape
    if np.any(uv<[48,48]) or np.any(uv>=[w-48,h-48]):return False
    d=meta['_depth_m'][uv[:,1],uv[:,0]]
    if not (np.isin(labels[uv[:,1],uv[:,0]],[1,2,24])&np.isfinite(d)&(d>0)&(d<999.)).all():return False
    actual=depth_world(uv,meta)
    return bool(layer_mask(actual,meta).all() and np.max(np.abs(actual[:,2]-xyz[:,2]))<=policy['boundary_occlusion_height_tolerance_m'])


def support(curve, p, q, meta, labels, masks, policy):
    def reject(reason, **info):
        return False, dict(reason=reason,**info)
    if not policy['boundary_occlusion_enabled']:
        return reject('occlusion_connection_disabled')
    if meta.get('_depth_m') is None:raise ValueError('Boundary occlusion inference requires measured depth')
    length=float(np.linalg.norm(np.diff(curve[:,:2],axis=0),axis=1).sum())
    if length>policy['boundary_occlusion_max_gap_m']:
        return reject('occlusion_gap_too_long')
    chord=curve[-1,:2]-curve[0,:2];chord/=max(np.linalg.norm(chord),1e-12)
    if min(tangent(p)[:2]@chord,tangent(q,True)[:2]@chord)<policy['boundary_occlusion_tangent_dot']:
        return reject('occlusion_endpoint_direction')
    uv=np.rint(project(curve,meta)).astype(int);h,w=labels.shape
    if np.any(uv<[48,48]) or np.any(uv>=[w-48,h-48]):
        return reject('occlusion_outside_safe_reference')
    x,y=uv[:,0],uv[:,1];values=labels[y,x];blocked=np.isin(values,OCCLUDER_IDS)
    if not blocked.any():
        return reject('no_labelled_thin_occluder')
    if not visible_endpoints(p,q,meta,labels,policy):return reject('endpoints_not_observed_on_road_layer')
    visible=~blocked
    if not np.isin(values[visible],[1,2,24]).all():
        return reject('unexplained_occlusion_class')
    fraction=float(blocked.mean())
    if fraction>policy['boundary_occlusion_max_fraction']:
        return reject('too_much_occlusion',fraction=fraction)
    s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(curve[:,:2],axis=0),axis=1))]
    edges=np.r_[s[0],(s[:-1]+s[1:])/2,s[-1]]
    cuts=np.flatnonzero(np.diff(np.r_[False,blocked,False].astype(int)))
    max_run=max(float(edges[b]-edges[a]) for a,b in zip(cuts[::2],cuts[1::2]))
    if max_run>policy['boundary_occlusion_max_run_m']:
        return reject('occluder_span_too_wide',max_run_m=max_run)
    from .occlusion_context import component_map
    component_ids=np.unique(component_map(meta,labels)[y[blocked],x[blocked]])
    if (fraction>.7 or max_run>.8 or length>1.5) and (len(component_ids)!=1 or component_ids[0]==0):
        return reject('wide_gap_requires_single_occluder_component')
    first,last=np.flatnonzero(blocked)[[0,-1]]
    tail=policy['boundary_occlusion_min_visible_m']
    gap_shoulders=bool(edges[first]>=tail and length-edges[last+1]>=tail)
    if not (visible_tail(p,meta,labels,policy) and visible_tail(q,meta,labels,policy,True)):
        return reject('insufficient_observed_endpoint_context')
    measured=meta.get('_depth_m')
    if measured is None:
        raise ValueError('Boundary occlusion inference requires measured depth')
    d=measured[y[visible],x[visible]]
    if not np.isfinite(d).all() or np.any(d<=0) or np.any(d>=999.):
        return reject('visible_depth_invalid')
    actual=depth_world(uv[visible],meta)
    error=float(np.max(np.abs(actual[:,2]-curve[visible,2])))
    if not layer_mask(actual,meta).all() or error>policy['boundary_occlusion_height_tolerance_m']:
        return reject('visible_layer_or_height_mismatch',height_error_m=error)
    side_a=side_context(p,meta,labels,policy)
    side_b=side_context(q,meta,labels,policy,True)
    if not side_a or side_a!=side_b:
        return reject('curb_side_context_disagrees',side_a=side_a,side_b=side_b)
    v=np.gradient(curve,axis=0);v/=np.maximum(np.linalg.norm(v[:,:2],axis=1)[:,None],1e-12)
    votes=road_side(curve[visible],v[visible],meta,labels,policy)
    if not len(votes) or np.mean(votes==side_a)<.6:return reject('visible_curb_support_missing')
    return True, dict(method='labelled_pole_occlusion_with_adaptive_curb_context_v2',inferred_not_measured=True,
        occluder_ids=sorted(set(values[blocked].tolist())),occluded_fraction=fraction,
        max_occluded_run_m=max_run,visible_height_error_m=error,
        road_side_consistent=True,endpoint_context_verified=True,visible_gap_shoulders=gap_shoulders,
        occluder_component_ids=component_ids.tolist(),
        connector_height_source='observed_endpoints_Hermite')
