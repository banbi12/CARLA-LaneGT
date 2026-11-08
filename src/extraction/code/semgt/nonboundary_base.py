"""Map-matched V4.2 geometry for semantic V4.3; boundary is never a base class."""
from pathlib import Path
import copy
import numpy as np
from .io import load,sha


def validate_base(base,pin,expected):
    if base.get('schema')!='lanegt_semantic_nonboundary_base_v1' or pin.get('schema')!='semantic_v43_nonboundary_pin_v1':
        raise ValueError('Semantic V4.3 non-boundary baseline schema mismatch')
    if base.get('version')!='XODR-only V4.2' or base.get('generator')!=pin.get('generator'):
        raise ValueError('Semantic V4.3 requires pinned XODR-only V4.2')
    if base.get('xodr_sha256')!=expected or pin.get('xodr_sha256')!=expected:
        raise ValueError('Semantic V4.3 baseline/map fingerprint mismatch')
    if base.get('boundary_included') is not False or pin.get('boundary_included') is not False or 'boundary' in base or 'boundaries' in base:
        raise ValueError('XODR boundary is not a semantic V4.3 baseline class')
    if pin.get('classes')!=['divider','ped_crossing','centerline']:
        raise ValueError('Non-boundary baseline classes differ')
    ids=set()
    for group,cls in [(base.get('dividers'), 'divider'),(base.get('ped_crossing'),'ped_crossing'),
                      (base.get('centerlines',{}).get('features'),'centerline')]:
        if not isinstance(group,list) or (not group and cls not in pin.get('declared_empty_classes',[])):raise ValueError('Baseline class missing: '+cls)
        for f in group:
            p=np.asarray(f.get('points_xyz'),float)
            if f.get('class_name',cls)!=cls or p.ndim!=2 or p.shape[1]!=3 or len(p)<2 or not np.isfinite(p).all() or f.get('id') in ids:
                raise ValueError('Invalid non-boundary baseline geometry')
            ids.add(f['id'])
    center=base['centerlines']
    if center.get('xodr_sha256')!=expected or not center.get('audit',{}).get('passed'):
        raise ValueError('V4.2 centerline identity/audit missing')
    return base


def load_baseline(project,meta=None,map_profile=None):
    project=Path(project);repository=project.resolve().parents[1]
    profile=None
    if map_profile:
        from .map_profile import read
        profile=read(project,map_profile)
    pin_path=repository/profile['baseline_pin'] if profile else project/'config/nonboundary_base_v42.json';pin=load(pin_path)
    asset=(repository/'assets'/pin['asset']).resolve()
    source=(repository/'assets'/pin['source_world_asset']).resolve()
    map_path=(repository/'assets'/pin['map_asset']).resolve()
    for p in [asset,source,map_path]:p.relative_to((repository/'assets').resolve())
    if sha(asset)!=pin['sha256'] or sha(source)!=pin['source_world_sha256']:
        raise ValueError('Semantic V4.3 baseline/source file fingerprint mismatch')
    expected=sha(map_path);base=validate_base(load(asset),pin,expected)
    if profile and (expected!=profile['xodr_sha256'] or base.get('map_name')!=profile['map_id']):raise ValueError('Baseline map profile mismatch')
    if profile and meta is not None:
        from .map_profile import validate_capture
        validate_capture(profile,meta)
    if base.get('source_world_sha256')!=pin['source_world_sha256']:
        raise ValueError('Non-boundary baseline source fingerprint mismatch')
    if meta is not None and meta.get('xodr_sha256')!=expected:raise ValueError('Semantic reference map mismatch')
    return base,dict(version='XODR-only V4.2',generator=base['generator'],xodr_sha256=expected,
        asset_sha256=pin['sha256'],source_world_sha256=pin['source_world_sha256'],
        classes=pin['classes'],boundary_included=False)


def crosswalk_world(base):
    return dict(schema='lanegt_xodr_crosswalk_world_v1',xodr_sha256=base['xodr_sha256'],
                features=copy.deepcopy(base['ped_crossing']))
