"""V4.5 R3: class-aware organization of existing linear XYZ targets."""
import copy
from .divider_targets import normalize as normalize_dividers,normalize_class,checked

RULE='linear_target_duplicate_containment_chains_v3'
CLASSES=('divider','boundary','centerline')


def normalize(targets,bev_range=None,policy=None):
    policy=checked(policy)
    out,divider=normalize_dividers(targets,bev_range,policy)
    audits=dict(divider=divider)
    for cls in ('boundary','centerline'):
        out,a=normalize_class(out,bev_range,policy,class_name=cls,directed=cls=='centerline',
            preserve_parent_cuts=cls=='boundary',rule=RULE+'_'+cls)
        a.pop('input_dividers',None);a.pop('output_dividers',None);audits[cls]=a
    return out,dict(rule=RULE,classes=audits,raw_world_modified=False,
        added_geometry=False,semantic_connections_reused=True,
        centerline_direction_preserved=True,boundary_intentional_partitions_preserved=True)


def ownership(raw,targets,cls):
    """Immediate input ownership, also when a previous revision has provenance."""
    original={t['id'] for t in raw if t['class_name']==cls};result={}
    for target in targets:
        if target['class_name']!=cls:continue
        members=[target['id']] if target['id'] in original else target['source'].get('input_target_ids',[])
        if not members:raise ValueError('Missing target provenance: '+target['id'])
        for identity in members:
            if identity not in original or identity in result:raise ValueError('Invalid or repeated target ownership: '+identity)
            result[identity]=target
    if set(result)!=original:raise ValueError('Missing input target ownership')
    return result


def apply_to_gt(gt,targets,audit,sampled=None):
    """Keep extra fields of unmerged entries and expose the sampled target order."""
    originals={f['id']:f for entries in gt['classes'].values() for f in entries}
    classes={k:[] for k in gt['classes']}
    for i,t in enumerate(targets):
        f=copy.deepcopy(originals.get(t['id'],dict(human_approved=False)))
        f.update(id=t['id'],parent_id=t['parent_id'],source=copy.deepcopy(t['source']),
            render_points=copy.deepcopy(t['full']),render_xyz=copy.deepcopy(t['full_xyz']),
            points=sampled['fixed20'][i].tolist() if sampled is not None else None)
        classes[t['class_name']].append(f)
    gt.update(classes=classes,counts={k:len(v) for k,v in classes.items()},
        linear_target_normalization=audit,divider_target_normalization=audit['classes']['divider'],
        centerline_geometry_preserved=True,centerline_target_direction_preserved=True)
    c=audit['classes']['centerline']
    if c['duplicate_instances_removed'] or c['joins_count']:gt['centerline_exact_from_source']=False
    return gt
