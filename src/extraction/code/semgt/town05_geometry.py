"""Conservative Town05 observation/base fusion with height-safe short joins."""
import copy
import cv2
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.spatial import cKDTree
from shapely.geometry import LineString
from .geometry import project, uid, xyworld
from .surface import depth_world, layer_mask


def runs(mask):
    cuts = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(int)))
    return zip(cuts[::2], cuts[1::2])


def resample(points, step=.1):
    p = np.asarray(points, float)
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    keep = np.r_[True, np.diff(s)>1e-10]
    p, s = p[keep], s[keep]
    at = np.linspace(0, s[-1], max(2, int(np.ceil(s[-1]/step))+1))
    return np.column_stack([np.interp(at, s, p[:, k]) for k in range(3)])


def simplify_xyz(points, tolerance=.04):
    p = np.asarray(points, float)
    keep = {0, len(p)-1}
    stack = [(0, len(p)-1)]
    while stack:
        a, b = stack.pop()
        if b-a < 2:
            continue
        delta = p[b]-p[a]
        t = np.clip((p[a+1:b]-p[a]) @ delta/max(float(delta@delta), 1e-20), 0, 1)
        distance = np.linalg.norm(p[a+1:b]-(p[a]+t[:, None]*delta), axis=1)
        i = int(np.argmax(distance))
        if distance[i] > tolerance:
            k = a+1+i
            keep.add(k)
            stack.extend([(a, k), (k, b)])
    return p[sorted(keep)]


def boundary_observations(meta, labels, depth):
    valid = meta['_layer_mask'].copy()
    b = 48
    valid[:b] = valid[-b:] = False
    valid[:, :b] = valid[:, -b:] = False
    valid = cv2.erode(valid.astype(np.uint8), np.ones((3,3), np.uint8))>0
    road = np.isin(labels, [1,24]) & valid
    near_side = cv2.dilate(((labels==2)&valid).astype(np.uint8), np.ones((5,5), np.uint8))>0
    contours, _ = cv2.findContours(road.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    output = []
    for contour in contours:
        uv = contour[:, 0, :]
        ok = valid[uv[:,1],uv[:,0]] & near_side[uv[:,1],uv[:,0]]
        if len(uv)<2:
            continue
        if ok.all():
            parts = [np.vstack([uv, uv[0]])]
        else:
            offset = int(np.flatnonzero(~ok)[0])
            uv, ok = np.roll(uv,-offset,axis=0), np.roll(ok,-offset)
            parts = [uv[a:b] for a,b in runs(ok) if b-a>=2]
        for part in parts:
            xyz = simplify_xyz(xyworld(part,meta))
            if np.linalg.norm(np.diff(xyz[:,:2],axis=0),axis=1).sum()<=.05:
                continue
            output.append(dict(id=uid(xyz,'boundary'),class_name='boundary',points_xyz=xyz.tolist(),
                               source=dict(kind='Town05_observed_road_sidewalk_depth_boundary'),review='pending'))
    return output


def supported(curve, cls, meta, labels, stripes=None, boundary_masks=None):
    uv = np.rint(project(curve,meta)).astype(int)
    h,w = labels.shape
    if np.any(uv<[48,48]) or np.any(uv>=[w-48,h-48]):
        return False
    x,y = uv[:,0],uv[:,1]
    measured = meta.get('_depth_m')
    if measured is not None:
        samples = np.asarray(measured)[y,x]
        # A proposed join can cross sky/no-return pixels between valid endpoints.
        # Missing support rejects that proposal; it must not abort the frame.
        if not np.isfinite(samples).all() or np.any(samples<=0) or np.any(samples>=999.):
            return False
    actual = depth_world(uv,meta)
    if not layer_mask(actual,meta).all() or np.max(abs(actual[:,2]-curve[:,2]))>.4:
        return False
    if cls=='divider':
        return bool(np.mean(np.isin(labels[y,x],[1,24]))>=.98 and
                    (stripes is None or not np.any(stripes[y,x])))
    if boundary_masks is None:
        boundary_masks = (
            cv2.dilate(np.isin(labels,[1,24]).astype(np.uint8),np.ones((5,5),np.uint8))>0,
            cv2.dilate((labels==2).astype(np.uint8),np.ones((5,5),np.uint8))>0)
    road, side = boundary_masks
    return bool(np.mean(road[y,x]&side[y,x])>=.8)


def join_features(features, meta, labels, max_gap, stripes=None, policy=None, rejections=None):
    out = copy.deepcopy(features)
    audit = []
    boundary_masks = None
    if any(f['class_name']=='boundary' for f in out):
        # Labels stay fixed throughout this call; share identical full-image masks.
        boundary_masks = (
            cv2.dilate(np.isin(labels,[1,24]).astype(np.uint8),np.ones((5,5),np.uint8))>0,
            cv2.dilate((labels==2).astype(np.uint8),np.ones((5,5),np.uint8))>0)
    for _ in range(150):
        candidates = []
        # A join needs endpoints within max_gap. Keep the original i/j ordering,
        # and a small conservative margin; the exact distance check below decides.
        ends = np.asarray([p for f in out for p in
                           (f['points_xyz'][0],f['points_xyz'][-1])],float)
        neighbors = {}
        if len(ends):
            for a,b in cKDTree(ends[:,:2]).query_pairs(max_gap+1e-8):
                i,j = sorted((a//2,b//2))
                if i!=j:
                    neighbors.setdefault(i,set()).add(j)
        for i,a in enumerate(out):
            pa = np.asarray(a['points_xyz'])
            if a['class_name'] not in ('divider','boundary') or np.allclose(pa[0],pa[-1]):
                continue
            for j in sorted(neighbors.get(i,())):
                b = out[j]
                pb = np.asarray(b['points_xyz'])
                if a['class_name']!=b['class_name'] or np.allclose(pb[0],pb[-1]):
                    continue
                if a.get('mark_color') and b.get('mark_color') and a['mark_color']!=b['mark_color']:
                    continue
                for ra in (False,True):
                    p = pa[::-1] if ra else pa
                    for rb in (False,True):
                        q = pb[::-1] if rb else pb
                        gap = np.linalg.norm(p[-1,:2]-q[0,:2])
                        if not .015<gap<=max_gap or abs(p[-1,2]-q[0,2])>.4:
                            continue
                        if a['class_name']=='boundary' and policy is not None:
                            from .boundary_occlusion import tangent
                            ta,tb=tangent(p),tangent(q,True)
                        else:
                            ta,tb = p[-1]-p[-2], q[1]-q[0]
                        ta = ta/max(np.linalg.norm(ta[:2]),1e-9)
                        tb = tb/max(np.linalg.norm(tb[:2]),1e-9)
                        chord = (q[0]-p[-1])/gap
                        minimum=policy['boundary_smooth_min_tangent_dot'] if a['class_name']=='boundary' and policy else .2
                        if min(ta[:2]@chord[:2],tb[:2]@chord[:2])<minimum:
                            continue
                        curve = CubicHermiteSpline([0,gap],[p[-1],q[0]],[ta,tb])(np.linspace(0,gap,max(5,int(gap/.04)+1)))
                        ratio=policy['boundary_smooth_max_curve_ratio'] if a['class_name']=='boundary' and policy else 1.5
                        if LineString(curve).length>ratio*gap:
                            continue
                        evidence=dict(method='measured_depth_and_semantic_support',inferred_not_measured=False)
                        if not supported(curve,a['class_name'],meta,labels,stripes,boundary_masks):
                            if a['class_name']!='boundary' or policy is None:continue
                            from .boundary_occlusion import support
                            accepted,evidence=support(curve,p,q,meta,labels,boundary_masks,policy)
                            if not accepted:
                                if rejections is not None and len(rejections)<256:
                                    rejections.append(dict(source_ids=[a['id'],b['id']],gap_m=float(gap),**evidence))
                                continue
                        merged = np.vstack([p,curve[1:-1],q])
                        if not LineString(merged).is_simple:
                            continue
                        candidates.append((gap,i,j,ra,rb,merged,curve,evidence))
        if not candidates:
            break
        selected = None
        for c in sorted(candidates,key=lambda q:q[:5]):
            end_a,end_b = (c[1],c[3]),(c[2],not c[4])
            competing = [v for v in candidates if v is not c and
                         (end_a in [(v[1],v[3]),(v[2],not v[4])] or end_b in [(v[1],v[3]),(v[2],not v[4])])]
            if any(v[0]<c[0]+.05 for v in competing):
                continue
            selected = c
            break
        if selected is None:
            break
        gap,i,j,ra,rb,merged,curve,evidence = selected
        a,b = out[i],out[j]
        record = dict(kind='Town05_height_safe_Hermite',class_name=a['class_name'],gap_m=float(gap),
                      source_ids=[a['id'],b['id']],points_xyz=curve.tolist(),evidence=evidence)
        a.update(id=uid(merged,a['class_name']),points_xyz=merged.tolist(),
                 source=dict(kind='Town05_height_safe_join',sources=[a['source'],b['source']],
                    contains_occlusion_inference=bool(evidence.get('inferred_not_measured') or
                        (isinstance(a['source'],dict) and a['source'].get('contains_occlusion_inference')) or
                        (isinstance(b['source'],dict) and b['source'].get('contains_occlusion_inference')))),
                 connections=a.get('connections',[])+b.get('connections',[])+[record])
        out.pop(j)
        audit.append(record)
    return out,audit


def fuse(base, observed, meta, labels, policy, stripes,context=None):
    base = copy.deepcopy(base)
    if any(f.get('class_name')!='divider' for f in base):
        raise ValueError('semantic V4.3 divider fusion accepts only V4.2 divider base features')
    supplements = []
    if base:
        cloud = np.vstack([resample(f['points_xyz']) for f in base])
        tree = cKDTree(cloud[:,:2])
    for feature in observed:
        if feature['class_name']!='divider':
            continue
        p = resample(feature['points_xyz'])
        covered = np.zeros(len(p),bool)
        if base:
            for i,near in enumerate(tree.query_ball_point(p[:,:2],policy['divider_base_coverage_m'])):
                covered[i] = any(abs(cloud[j,2]-p[i,2])<=.25 for j in near)
        fraction = covered.mean()
        if fraction>=policy['divider_base_duplicate_coverage']:
            continue
        if fraction<=policy['divider_base_supplement_coverage']:
            parts = [np.asarray(feature['points_xyz'])]
        else:
            # Keep uncovered endpoint extensions; middle bridges stay pending.
            parts = [p[max(0,a-1):min(len(p),b+1)] for a,b in runs(~covered) if a==0 or b==len(p)]
        for part in parts:
            if LineString(part).length<policy['divider_base_min_supplement_m']:
                continue
            f = copy.deepcopy(feature)
            f.update(id=uid(part,'semantic_supplement'),points_xyz=part.tolist(),
                     source=dict(kind='Town05_semantic_supplement',original_source=feature['source'],base_coverage=float(fraction)))
            supplements.append(f)
    from .occlusion_context import filter_supplements
    raw_supplements=copy.deepcopy(supplements)
    supplements,guard_audit=filter_supplements(supplements,meta,context,policy)
    enabled=policy['divider_semantic_supplements_enabled']
    return base+(supplements if enabled else []),dict(rule='semantic_v43_xodr_v42_XYZ_base_with_semantic_supplement',
                                 base_features=len(base),supplements=len(supplements) if enabled else 0,
                                 semantic_supplements_enabled=enabled,
                                 candidate_supplements=supplements,
                                 candidate_supplement_count=len(supplements),
                                 unfiltered_candidate_supplements=raw_supplements,
                                 occlusion_role_guard=guard_audit,
                                 base_geometry_unchanged=True,baseline_version='XODR-only V4.2',
                                 boundary_included=False)
