"""Shared BEV bounds and calibrated ground-plane coverage checks."""
import numpy as np
from .geometry import transform,project,validate_meta
DEFAULT=[-15.,-30.,15.,30.]

def bounds(value=None):
    q=np.asarray(DEFAULT if value is None else value,dtype=float)
    if q.shape!=(4,) or not np.isfinite(q).all() or q[0]>=q[2] or q[1]>=q[3]:
        raise ValueError('BEV范围必须为有限的[xmin,ymin,xmax,ymax]，且最小值小于最大值')
    return q.tolist()

def ring(value=None):
    a,b,c,d=bounds(value);return [[a,b],[c,b],[c,d],[a,d],[a,b]]

def sampler_patch(value=None):
    a,b,c,d=bounds(value)
    # LiDARInstanceLines clamps about zero. A symmetric envelope preserves
    # original model coordinates even for an asymmetric, already-clipped ROI.
    return (2*max(abs(b),abs(d)),2*max(abs(a),abs(c)))

def display(value=None):
    a,b,c,d=bounds(value);scale=min(600/(c-a),1200/(d-b))
    return scale,(a+c)/2,(b+d)/2

def coverage(meta,model_from_world,value=None,border=48):
    validate_meta(meta);value=bounds(value);inv=np.linalg.inv(np.asarray(model_from_world,float))
    from .surface import z_bounds
    xy=np.asarray(ring(value),float)
    local=np.vstack([np.c_[xy,np.full(len(xy),z)] for z in z_bounds(meta)])
    world=transform(local,inv);uv=project(world,meta)
    w,h=meta['image_size'];ok=np.isfinite(uv).all() and np.all(uv>=[border,border]) and np.all(uv<=[w-1-border,h-1-border])
    if not ok:raise ValueError('BEV范围超出顶视相机有效覆盖（含安全边缘）；缩小范围或重新采集更高/更宽视角的顶视图')
    return dict(passed=True,BEV_range_m=value,safe_border_px=border,ground_corners_world=world.tolist(),corners_uv=uv.tolist())
