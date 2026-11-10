"""Transport a semantic guide back to the locally measured XODR edge datum."""
import numpy as np
from scipy.spatial import cKDTree
from .surface import layer_mask
from .town05_geometry import resample
from .boundary_occlusion import tangent

REVISION='local_bias_compensated_xodr_boundary_route_v2'


def normals(points):
    t=np.gradient(np.asarray(points),axis=0)[:,:2]
    t/=np.maximum(np.linalg.norm(t,axis=1)[:,None],1e-12)
    return np.c_[-t[:,1],t[:,0]]


def measured_edges(meta,labels):
    cache=meta.get('_boundary_alignment_edges')
    if cache is not None:return cache
    world=meta['_world_xyz'];depth=meta['_depth_m']
    valid=np.isfinite(depth)&(depth>0)&(depth<999.)&layer_mask(world,meta)
    road=np.isin(labels,[1,24])&valid;side=np.isin(labels,[2,10])&valid
    h,w=labels.shape;points=[]
    for dy,dx in [(0,1),(1,0)]:
        a=(slice(0,h-dy),slice(0,w-dx));b=(slice(dy,h),slice(dx,w))
        mask=(road[a]&side[b])|(side[a]&road[b])
        y,x=np.nonzero(mask);good=(x>=48)&(x<w-49)&(y>=48)&(y<h-49);x,y=x[good],y[good]
        p,q=world[y,x],world[y+dy,x+dx]
        good=(np.linalg.norm(p[:,:2]-q[:,:2],axis=1)<.4)&(abs(p[:,2]-q[:,2])<.4)
        points.append((p[good]+q[good])/2)
    xyz=np.concatenate(points) if points else np.empty((0,3))
    cache=dict(xyz=xyz,tree=cKDTree(xyz[:,:2]) if len(xyz) else None)
    meta['_boundary_alignment_edges']=cache
    return cache


def endpoint_bias(points,meta,labels,policy,start=False):
    """Estimate signed left-normal offset on visible native endpoint context."""
    edge=measured_edges(meta,labels)
    if edge['tree'] is None:return None,dict(reason='no_measured_interface')
    p=np.asarray(points,float);n=normals(p)
    s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1))]
    # Use regular physical stations even if native vertex spacing changes.
    at=np.linspace(.15,min(3.,s[-1]),max(2,int(min(3.,s[-1])/.1)))
    stations=at if start else s[-1]-at
    xyz=np.column_stack([np.interp(stations,s,p[:,k]) for k in range(3)])
    normal=np.column_stack([np.interp(stations,s,n[:,k]) for k in range(2)])
    normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-12)
    t=np.c_[normal[:,1],-normal[:,0]]
    distance,ids=edge['tree'].query(xyz[:,:2],k=min(24,len(edge['xyz'])))
    if distance.ndim==1:distance=distance[:,None];ids=ids[:,None]
    observed=edge['xyz'][ids];delta=observed-xyz[:,None,:]
    along=np.sum(delta[:,:,:2]*t[:,None,:],axis=2)
    valid=(distance<=policy['boundary_route_alignment_max_offset_m'])&(abs(along)<=.18)
    valid&=abs(delta[:,:,2])<=policy['boundary_route_alignment_max_height_bias_m']
    scores=np.where(valid,distance,np.inf);best=np.argmin(scores,axis=1)
    good=np.isfinite(scores[np.arange(len(xyz)),best])
    chosen=observed[np.arange(len(xyz)),best]
    d=np.sum((chosen[:,:2]-xyz[:,:2])*normal,axis=1);dz=chosen[:,2]-xyz[:,2]
    # A local interface must agree with the native tail direction. PCA avoids
    # depending on staircase pixel normals on diagonal or curved roads.
    for i in np.flatnonzero(good):
        near=observed[i,valid[i],:2]
        if len(near)<3:good[i]=False;continue
        cov=np.cov(near.T);values,vectors=np.linalg.eigh(cov)
        if values[-1]/max(values.sum(),1e-12)<.7 or abs(vectors[:,-1]@t[i])<.8:good[i]=False
    if good.sum()<policy['boundary_route_alignment_min_samples']:
        return None,dict(reason='insufficient_native_tail_interface',samples=int(good.sum()))
    lateral=float(np.median(d[good]));height=float(np.median(dz[good]))
    keep=good&(abs(d-lateral)<=max(.06,3*float(np.median(abs(d[good]-lateral)))))
    if keep.sum()<policy['boundary_route_alignment_min_samples']:
        return None,dict(reason='unstable_native_tail_interface')
    lateral=float(np.median(d[keep]));height=float(np.median(dz[keep]));mad=float(np.median(abs(d[keep]-lateral)))
    if mad>policy['boundary_route_alignment_max_mad_m']:
        return None,dict(reason='native_tail_bias_variation',mad_m=mad)
    return dict(lateral_m=lateral,interface_height_bias_m=height,samples=int(keep.sum()),mad_m=mad,
                definition='semantic_interface_minus_native_left_normal'),None


def pair_bias(p,q,meta,labels,policy):
    a,err_a=endpoint_bias(p,meta,labels,policy)
    b,err_b=endpoint_bias(q,meta,labels,policy,start=True)
    if a is None or b is None:
        return None,dict(reason='native_bias_unavailable',p=err_a,q=err_b)
    return dict(p=a,q=b,global_constant_offset_used=False),None


def validation_tail(points,bias,meta,labels,start=False):
    from .boundary_routes import in_reference
    p=np.asarray(points,float).copy();p[:,:2]+=normals(p)*bias['lateral_m']
    p[:,2]+=bias['interface_height_bias_m']
    # Perspective changes after translating the evidence guide can move part
    # of a previously visible tail past the safe border. Count only contiguous
    # observed context next to the anchor, never unseen padding as a side vote.
    p=resample(p,.1);visible=in_reference(p,meta,labels)
    if visible[0 if start else -1]:
        outside=np.flatnonzero(~visible)
        if len(outside):p=p[:outside[0]] if start else p[outside[-1]+1:]
    return p


def aligned_shapes(seed,p,q,bias,meta,labels,policy):
    """Fit in semantic space and invert the same reference normal transport.

    Emitted Z always comes from the native endpoint Hermite profile. Measured
    surface height affects the evidence guide only, never the emitted datum.
    """
    from .boundary_routes import fit
    s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(seed[:,:2],axis=0),axis=1))]
    u=s/max(s[-1],1e-12);blend=u*u*(3-2*u)
    normal=normals(seed)
    a,b=tangent(p),tangent(q,True)
    normal[0]=[-a[1],a[0]];normal[-1]=[-b[1],b[0]]
    lateral=(1-blend)*bias['p']['lateral_m']+blend*bias['q']['lateral_m']
    height=(1-blend)*bias['p']['interface_height_bias_m']+blend*bias['q']['interface_height_bias_m']
    guide_seed=seed.copy();guide_seed[:,:2]+=normal*lateral[:,None];guide_seed[:,2]+=height
    fitted,info=fit(guide_seed,meta,labels,policy)
    candidates=[]
    if fitted is not None:candidates.append((fitted,info))
    candidates.append((guide_seed,dict(method='semantic_guide_hermite_fallback',fitting_failure=info if fitted is None else None)))
    gs=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(guide_seed[:,:2],axis=0),axis=1))]
    output=[]
    for guide,fit_info in candidates:
        # fit() resamples at uniform seed arc-length before changing offsets.
        at=np.linspace(0,gs[-1],len(guide)) if guide is fitted else gs
        n=np.column_stack([np.interp(at,gs,normal[:,k]) for k in range(2)])
        d=np.interp(at,gs,lateral)
        curve=guide.copy();curve[:,:2]-=n*d[:,None]
        curve[:,2]=np.interp(at,gs,seed[:,2])
        curve[0]=seed[0];curve[-1]=seed[-1]
        detail=dict(method=REVISION,source_fit_method=fit_info['method'],local_bias=bias,
                    native_height_profile=True,measured_surface_height_used_as_output=False,
                    fixed_native_endpoints=True,guide_fitting=fit_info,
                    evidence_context_visibility='contiguous_safe_reference_tail')
        output.append((curve,detail,guide,validation_tail(p,bias['p'],meta,labels),
                       validation_tail(q,bias['q'],meta,labels,start=True)))
    return output
