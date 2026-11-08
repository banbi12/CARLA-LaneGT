"""Crosswalk roles and lamp components constrain semantic additions only.

V4.2 divider geometry is never passed through this exclusion filter.
"""
import copy
import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.vectorized import contains
from .geometry import project,transform,uid


def kernel(radius):
    radius=max(1,int(round(radius)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,2*radius+1))


def build(meta,labels,policy,crosswalks=(),footprints=()):
    scale=float(meta['metric_scale_m_per_pixel']);h,w=labels.shape
    role=np.zeros((h,w),np.uint8);observed=np.zeros_like(role);polygons=[]
    margin=policy['divider_crosswalk_role_margin_m']
    for f in crosswalks or ():
        xyz=np.asarray(f['points_xyz'],float)
        local=transform(xyz,meta['GT_model_from_world'])
        lo,hi=meta.get('model_z_range_m',[-2,2])
        if local[:,2].max()<lo-.4 or local[:,2].min()>hi+.4:continue
        uv=project(xyz,meta)
        if not np.isfinite(uv).all() or np.any(uv.max(axis=0)<0) or np.any(uv.min(axis=0)>[w,h]):continue
        poly=Polygon(xyz[:,:2]).buffer(margin)
        if poly.is_empty:continue
        plane=np.linalg.lstsq(np.c_[xyz[:,:2],np.ones(len(xyz))],xyz[:,2],rcond=None)[0]
        polygons.append((poly,plane))
        cv2.fillPoly(role,[np.rint(uv).astype(np.int32)],1)
    if role.any():role=cv2.dilate(role,kernel(margin/scale))
    for uv in footprints or ():
        if len(uv)>=3:cv2.fillPoly(observed,[np.rint(uv).astype(np.int32)],1)
    if observed.any():observed=cv2.dilate(observed,kernel(margin/scale))
    raw=np.isin(labels,[6,7,8]).astype(np.uint8)
    closed=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    _,components=cv2.connectedComponents(closed,8)
    touched=np.unique(components[((role|observed)>0)&(raw>0)])
    touched=touched[touched>0]
    linked=np.isin(components,touched)&(closed>0)
    halo=cv2.dilate(linked.astype(np.uint8),kernel(policy['divider_linked_pole_halo_m']/scale))>0
    # Reconnect role context through the occluding object, never paint geometry.
    # Thin remnants of a crosswalk rail can extend far beyond a local halo.
    paint=(labels==24)&meta['_layer_mask']
    context_bridge=cv2.dilate(linked.astype(np.uint8),np.ones((3,3),np.uint8))>0
    _,paint_components=cv2.connectedComponents((paint|context_bridge).astype(np.uint8),8)
    role_ids=np.unique(paint_components[paint&((role|observed)>0)])
    lamp_ids=np.unique(paint_components[context_bridge])
    ambiguous_ids=np.intersect1d(role_ids[role_ids>0],lamp_ids[lamp_ids>0])
    ambiguous_paint=paint&np.isin(paint_components,ambiguous_ids)
    ambiguous_paint=cv2.dilate(ambiguous_paint.astype(np.uint8),np.ones((5,5),np.uint8))>0
    context=dict(role=role>0,observed_role=observed>0,components=components,
        linked_halo=halo,ambiguous_paint=ambiguous_paint,polygons=polygons,
        audit=dict(method='height_aware_crosswalk_role_and_overhanging_lamp_component',
            crosswalk_polygons=len(polygons),linked_occluder_components=len(touched),
            known_role_pixels=int(role.sum()),observed_role_pixels=int(observed.sum()),
            crosswalk_lamp_paint_components=len(ambiguous_ids),ambiguous_paint_pixels=int(ambiguous_paint.sum()),
            linked_pole_halo_pixels=int(halo.sum()),baseline_dividers_filtered=False))
    meta['_occlusion_context']=context
    return context


def component_map(meta,labels):
    if '_occlusion_context' in meta:return meta['_occlusion_context']['components']
    if '_boundary_occlusion_components' in meta:return meta['_boundary_occlusion_components']
    raw=np.isin(labels,[6,7,8]).astype(np.uint8)
    raw=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    _,components=cv2.connectedComponents(raw,8)
    meta['_boundary_occlusion_components']=components
    return components


def samples(points,step=.04):
    p=np.asarray(points,float);s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
    keep=np.r_[True,np.diff(s)>1e-10];p,s=p[keep],s[keep]
    at=np.unique(np.r_[s,np.linspace(0,s[-1],max(2,int(np.ceil(s[-1]/step))+1))])
    return np.column_stack([np.interp(at,s,p[:,j]) for j in range(3)])


def forbidden(points,meta,context,policy):
    p=np.asarray(points,float);uv=np.rint(project(p,meta)).astype(int)
    h,w=context['role'].shape;valid=(uv[:,0]>=0)&(uv[:,1]>=0)&(uv[:,0]<w)&(uv[:,1]<h)
    x=np.clip(uv[:,0],0,w-1);y=np.clip(uv[:,1],0,h-1)
    role=np.zeros(len(p),bool)
    for poly,plane in context['polygons']:
        inside=contains(poly,p[:,0],p[:,1])
        role|=inside&(np.abs(p[:,2]-(np.c_[p[:,:2],np.ones(len(p))]@plane))<=policy['divider_crosswalk_height_tolerance_m'])
    observed=valid&context['observed_role'][y,x]
    linked=valid&context['linked_halo'][y,x]
    ambiguous=valid&context['ambiguous_paint'][y,x]
    return role|observed|linked|ambiguous|~valid,dict(crosswalk_role=role,observed_crosswalk=observed,linked_lamp_halo=linked,
        crosswalk_lamp_paint_component=ambiguous,outside_reference=~valid)


def filter_supplements(features,meta,context,policy):
    if not policy['divider_occlusion_context_guard_enabled']:
        return copy.deepcopy(features),dict(enabled=False,rejected=[])
    if context is None:
        # Missing role context must not silently enable automatic additions.
        return [],dict(enabled=True,rejected=[dict(id=f['id'],reason='missing_occlusion_role_context') for f in features])
    kept=[];rejected=[]
    for feature in features:
        p=samples(feature['points_xyz']);bad,reasons=forbidden(p,meta,context,policy)
        if not bad.any():kept.append(copy.deepcopy(feature));continue
        cuts=np.flatnonzero(np.diff(np.r_[False,~bad,False].astype(int)))
        portions=[]
        for a,b in zip(cuts[::2],cuts[1::2]):
            part=p[a:b]
            if len(part)<2 or np.linalg.norm(np.diff(part[:,:2],axis=0),axis=1).sum()<policy['divider_base_min_supplement_m']:continue
            item=copy.deepcopy(feature);item.update(id=uid(part,'guarded_semantic_supplement'),points_xyz=part.tolist())
            item['source'].update(occlusion_role_guard=True,unfiltered_candidate_id=feature['id'])
            kept.append(item);portions.append(item['id'])
        rejected.append(dict(id=feature['id'],reason='crosswalk_or_linked_overhanging_lamp',
            forbidden_samples=int(bad.sum()),samples=len(p),kept_portions=portions,
            reason_sample_counts={k:int(v.sum()) for k,v in reasons.items()}))
    return kept,dict(enabled=True,input_candidates=len(features),output_candidates=len(kept),
        affected_candidates=len(rejected),rejected=rejected,baseline_filtered=False)
