"""V4.3: preserved V4.2 divider base, semantic supplements and observed boundaries."""
import copy
import json
from functools import lru_cache
import numpy as np
from shapely.geometry import LineString,box
from . import LEGACY_VERSION as VERSION
from .geometry import transform,parts,validate_meta,uid
from .observations import extract
from .topology import double_yellow
from .policy import checked
from .hints import annotate

def dividers(meta,labels,depth,rgb,policy=None,old_world=None,connection_reference=None,divider_base=None,crosswalks=None):
    from .surface import bind
    from .town05_geometry import join_features, fuse
    policy=checked(policy)
    if '_world_xyz' not in meta: bind(meta,labels,depth)
    atoms,stripes,stats=extract(meta,labels,depth,rgb,policy)
    from .occlusion_context import build
    context=build(meta,labels,policy,crosswalks,stats['stripes'].get('observed_footprints_uv',[]))
    paired,double_audit=double_yellow(atoms,meta,policy,labels,depth)
    connected,joins=join_features(paired,meta,labels,2.,stripes)
    final,base_audit=fuse(divider_base or [],connected,meta,labels,policy,stripes,context)
    audit=dict(observation_stats=stats,double_yellow=double_audit,dash_connections=joins,
               small_gap_connections=[],rejected_connections=[],observed_crosswalk_mask=stripes,
               raw_observations=atoms,divider_base=base_audit,occlusion_context=context['audit'],
               connection_reference=dict(status='V42_nonboundary_XYZ_baseline_semantic_supplement',
                                         version='XODR-only V4.2',boundary_included=False))
    return final,audit,annotate(final,old_world)


def repair_boundaries(features,meta,labels,depth,stripes,policy):
    from .town05_geometry import join_features
    if not policy['boundary_smooth_enabled']:
        return copy.deepcopy(features),[],[]
    boundaries=[f for f in features if f['class_name']=='boundary']
    others=[f for f in features if f['class_name']!='boundary']
    rejected=[]
    repaired,gaps=join_features(boundaries,meta,labels,policy['boundary_smooth_max_gap_m'],policy=policy,rejections=rejected)
    for g in gaps:g['boundary_smooth_connection']=True
    return others+repaired,gaps,rejected


@lru_cache(maxsize=512)
def _boundary_partition(identity,points,policy_json):
    from partition import make_partition,check_partition
    parent=dict(id=identity,points_xyz=points);policy=json.loads(policy_json)
    children=make_partition(parent,policy);check_partition(parent,children,policy)
    return children


def clip_targets(features,model_from_world,partition_policy,bev_range=None):
    from partition import make_partition,check_partition
    matrix=np.asarray(model_from_world,float)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):
        raise ValueError('Full measured model-from-world transform is required')
    if not np.allclose(matrix[:3,:3].T@matrix[:3,:3],np.eye(3),atol=1e-5):
        raise ValueError('The measured model transform must be rigid')
    from .bev import bounds
    roi=box(*bounds(bev_range));targets=[]
    for f in features:
        cls=f['class_name']
        if cls not in ['divider','boundary','ped_crossing']:continue
        if cls=='boundary':
            children=_boundary_partition(f['id'],tuple(tuple(p) for p in f['points_xyz']),json.dumps(partition_policy,sort_keys=True))
        else:children=[f]
        for child in children:
            local=transform(child['points_xyz'],matrix)
            from .surface import clip_xyz
            from .surface import z_bounds
            extent=bounds(bev_range);vertical=z_bounds()
            lo=np.array([extent[0],extent[1],vertical[0]])-1e-7
            hi=np.array([extent[2],extent[3],vertical[1]])+1e-7
            if np.any(local.max(axis=0)<lo) or np.any(local.min(axis=0)>hi):continue
            for index,p in enumerate(clip_xyz(local,bounds(bev_range))):
                if LineString(p).length<=.05:continue
                targets.append(dict(id=child['id']+':clip'+str(index),parent_id=f['id'],class_name=cls,full=p[:,:2].tolist(),full_xyz=p.tolist(),source=f['source']))

    return targets

def assemble(row,features,centerline,partition_policy,sampled=None,bev_range=None,divider_target_policy=None,linear_target_policy=None):
    """Copy centerline verbatim. Full geometry is the base annotation; model sampling is optional."""
    from .bev import bounds
    bev_range=bounds(bev_range if bev_range is not None else row.get('BEV_range_m'))
    targets=clip_targets(features,row['transform'],partition_policy,bev_range)
    divider_audit=None
    if divider_target_policy is not None and linear_target_policy is None:
        from .divider_targets import normalize
        targets,divider_audit=normalize(targets,bev_range,divider_target_policy)
    for f in centerline:
        targets.append(dict(id=f['id'],parent_id=f['parent_id'],class_name='centerline',full=copy.deepcopy(f['render_points']),full_xyz=copy.deepcopy(f['render_xyz']),source=copy.deepcopy(f['source'])))
    linear_audit=None
    if linear_target_policy is not None:
        from .linear_targets import normalize
        targets,linear_audit=normalize(targets,bev_range,linear_target_policy)
    if len({f['id'] for f in targets})!=len(targets):raise ValueError('Duplicate target IDs')
    classes={k:[] for k in ['divider','ped_crossing','boundary','centerline']}
    for index,f in enumerate(targets):
        if f['class_name']=='centerline':continue
        points=sampled['fixed20'][index].tolist() if sampled is not None else None
        classes[f['class_name']].append(dict(id=f['id'],parent_id=f['parent_id'],source=f['source'],render_points=f['full'],render_xyz=f['full_xyz'],points=points,human_approved=False))
    classes['centerline']=copy.deepcopy(centerline)
    from .surface import z_bounds
    gt=dict(model_z_range_m=z_bounds().tolist(),schema='maptrv2_semantic_gt_v1',algorithm_version=VERSION,token=row['token'],reference=row['reference'],classes=classes,counts={k:len(v) for k,v in classes.items()},
            geometry_frame='map_model_local_x_right_y_forward_z_up',BEV_range_m=bev_range,centerline_exact_from_source=True,algorithm_accepted_by_user=False,human_approved=False,
            actual_sampler_applied=sampled is not None,capacity_passed=len(targets)<=128,approved_for_training=False)
    from .portable import finalize
    if divider_audit is not None:gt['divider_target_normalization']=divider_audit
    if linear_audit is not None:
        from .linear_targets import apply_to_gt
        apply_to_gt(gt,targets,linear_audit,sampled)
    return finalize(gt,sampled is not None),targets
