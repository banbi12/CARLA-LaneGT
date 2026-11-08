"""Measured depth geometry and explicit ego-relative vertical supervision ROI."""
import json
from pathlib import Path
import numpy as np

DEFAULT_Z = json.loads((Path(__file__).resolve().parents[4]/'config/geometry_contract.json').read_text())['model_z_range_m']


def z_bounds(meta=None):
    q = np.asarray((meta or {}).get('model_z_range_m', DEFAULT_Z), float)
    if q.shape != (2,) or not np.isfinite(q).all() or q[0] >= q[1]:
        raise ValueError('Invalid model_z_range_m')
    return q


def layer_mask(world, meta):
    matrix = np.asarray(meta['GT_model_from_world'], float)
    z = np.asarray(world) @ matrix[2, :3] + matrix[2, 3]
    lo, hi = z_bounds(meta)
    return np.isfinite(z) & (z >= lo) & (z <= hi)


def depth_world(uv, meta, depth=None):
    from scipy.ndimage import map_coordinates
    depth = meta.get('_depth_m') if depth is None else depth
    if depth is None:
        raise ValueError('Town05 requires measured depth; z=0 projection is disabled')
    uv = np.asarray(uv, float)
    h, w = depth.shape
    if not np.isfinite(uv).all() or np.any(uv < 0) or np.any(uv > [w-1, h-1]):
        raise ValueError('Depth query outside measured reference')
    z = map_coordinates(np.asarray(depth), [uv[:, 1], uv[:, 0]], order=0, mode='nearest')
    if not np.isfinite(z).all() or np.any(z <= 0) or np.any(z >= 999.):
        raise ValueError('Invalid metric optical depth')
    rays = np.c_[uv, np.ones(len(uv))] @ np.linalg.inv(np.asarray(meta['intrinsic'])).T
    t = np.asarray(meta['optical_to_world_carla'])
    return (rays*z[:, None]) @ t[:3, :3].T + t[:3, 3]


def bind(meta, labels, depth):
    """Attach in-memory arrays only; these private fields must not be serialized."""
    meta['_depth_m'] = depth
    yy, xx = np.indices(labels.shape)
    uv = np.c_[xx.ravel(), yy.ravel()]
    rays = np.c_[uv, np.ones(len(uv))] @ np.linalg.inv(np.asarray(meta['intrinsic'])).T
    t = np.asarray(meta['optical_to_world_carla'])
    world = ((rays*depth.ravel()[:, None]) @ t[:3,:3].T+t[:3,3]).reshape((*labels.shape, 3))
    valid = np.isin(labels, [1, 2, 24]) & layer_mask(world, meta) & np.isfinite(depth) & (depth>0) & (depth<999.)
    if not np.any(valid):
        raise ValueError('No visible road in requested vertical ROI; overhead layer may occlude ego road')
    meta['_world_xyz'] = world
    meta['_layer_mask'] = valid
    meta['metric_scale_m_per_pixel'] = float(np.median(depth[valid])/meta['intrinsic'][0][0])
    return world, valid


def lift_xy(points, meta, max_distance=2.1):
    """Lift short generated XY curves from the measured, selected road layer."""
    from scipy.spatial import cKDTree
    if '_surface_tree' not in meta:
        valid = meta['_layer_mask'].copy()
        valid[1::2, :] = False
        valid[:, 1::2] = False
        xyz = meta['_world_xyz'][valid]
        if not len(xyz):
            raise ValueError('No measured surface for curve lifting')
        meta['_surface_xyz'] = xyz
        meta['_surface_tree'] = cKDTree(xyz[:, :2])
    p = np.asarray(points, float)[:, :2]
    distance, index = meta['_surface_tree'].query(p)
    if np.any(distance > max_distance):
        raise ValueError('Generated connector leaves measured road support')
    return np.c_[p, meta['_surface_xyz'][index, 2]]


def clip_xyz(points, roi, vertical=DEFAULT_Z):
    """Clip every 3D segment to a rectangular prism, interpolating all XYZ."""
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all():
        raise ValueError('Finite Nx3 polyline required')
    low = np.array([roi[0], roi[1], vertical[0]])
    high = np.array([roi[2], roi[3], vertical[1]])
    current = []
    result = []
    for a, b in zip(p[:-1], p[1:]):
        d = b-a
        lo, hi = 0., 1.
        for k in range(3):
            if abs(d[k]) < 1e-14:
                if a[k] < low[k] or a[k] > high[k]:
                    hi = -1.
                    break
            else:
                u, v = sorted([(low[k]-a[k])/d[k], (high[k]-a[k])/d[k]])
                lo, hi = max(lo, u), min(hi, v)
        if lo > hi or np.linalg.norm(d*(hi-lo)) < 1e-10:
            if len(current) >= 2:
                result.append(np.asarray(current))
            current = []
            continue
        start, end = a+lo*d, a+hi*d
        if current and np.linalg.norm(current[-1]-start) < 1e-8:
            current.append(end)
        else:
            if len(current) >= 2:
                result.append(np.asarray(current))
            current = [start, end]
    if len(current) >= 2:
        result.append(np.asarray(current))
    return result


def frame_features(features, model_from_world, roi, vertical=DEFAULT_Z):
    from .geometry import transform
    output = []
    inv = np.linalg.inv(np.asarray(model_from_world))
    for feature in nearby_features(features, model_from_world, roi, vertical):
        local = transform(feature['points_xyz'], model_from_world)
        for index, part in enumerate(clip_xyz(local, roi, vertical)):
            if np.linalg.norm(np.diff(part[:, :2], axis=0), axis=1).sum() <= .05:
                continue
            f = dict(feature, id=feature['id']+':layer'+str(index),
                     points_xyz=transform(part, inv).tolist())
            output.append(f)
    return output


def nearby_features(features, model_from_world, roi, vertical=DEFAULT_Z):
    """Conservative world-AABB prefilter before exact 3D clipping.

    Uses all eight corners, so tilted ego frames and elevated roads are retained.
    Bounds overlap is only a rejection test; final clipping remains unchanged.
    """
    corners = np.array([[x,y,z] for x in [roi[0],roi[2]]
                        for y in [roi[1],roi[3]] for z in vertical])
    world = (np.c_[corners,np.ones(len(corners))] @ np.linalg.inv(np.asarray(model_from_world)).T)[:,:3]
    low, high = world.min(axis=0)-1e-7, world.max(axis=0)+1e-7
    output = []
    for feature in features:
        p = np.asarray(feature['points_xyz'],float)
        if np.all(p.max(axis=0)>=low) and np.all(p.min(axis=0)<=high):
            output.append(feature)
    return output
