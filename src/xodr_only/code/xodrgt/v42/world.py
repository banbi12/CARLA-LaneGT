"""XODR-only V4.2: preserved native labels with divider-only connections."""
from pathlib import Path
import copy
import numpy as np
from mapgt.common import digest
from semgt.io import load,sha
from semgt.legacy_xodr import XodrMap
from semgt.town05_world import validate as validate_native
from . import DISPLAY_NAME,VERSION
MULTITOWN_VERSION='xodr_only_v42_multitown_native_divider_connections_v1'


def preserved_subsequence(original,joined):
    """Every original vertex and segment remains an unchanged substring."""
    p=np.asarray(original,float);q=np.asarray(joined,float)
    for candidate in (p,p[::-1]):
        for start in np.flatnonzero(np.all(q==candidate[0],axis=1)):
            if start+len(p)<=len(q) and np.array_equal(q[start:start+len(p)],candidate):return True
    return False


def native_order(base,dividers):
    owners={identity:f for f in dividers for identity in f['source'].get('native_ids',[f['id']])}
    features=[];seen=set()
    for f in base['features']:
        new=owners[f['id']] if f['class_name']=='divider' else f
        if new['id'] not in seen:features.append(copy.deepcopy(new));seen.add(new['id'])
    return features


def connect(base,xodr,source_sha256=None,progress=None):
    from .stitch_dividers import stitch_dividers
    from .xodr_topology import XodrTopology
    from .support import NativeSupport
    validate_native(base,sha(xodr))
    if base['generator'] not in ('xodr_town05_elevation_v1','xodr_multitown_elevation_v1'):
        raise ValueError('V4.2 must start from the preserved native roadMark baseline')
    xmap=XodrMap.from_file(xodr);raw=[];original={}
    for f in base['features']:
        if f['class_name']!='divider':continue
        original[f['id']]=f;src=copy.deepcopy(f['source'])
        src['junction']=xmap.by_id[src['road_id']].junction
        src['source_refs']=[dict(native_id=f['id'],**copy.deepcopy(src))]
        raw.append(dict(points=copy.deepcopy(f['points_xyz']),source=src))
    # Preserve every native source curve. Do not apply V4.1's selection,
    # recovery, surface exterior or geometry-suppressing dedup stages.
    stitched,audit=stitch_dividers(raw,NativeSupport(xmap),topology=XodrTopology.from_file(xodr),
                                  max_iterations=max(200,len(raw)+1),progress=progress)
    if audit['joins']>=max(200,len(raw)+1):raise ValueError('Divider stitching exhausted its budget')
    output=[];represented=set();merged=0
    for f in stitched:
        ids=[r['native_id'] for r in f['source']['source_refs']]
        for identity in ids:
            if identity in represented:raise ValueError('Native source assigned twice')
            if not preserved_subsequence(original[identity]['points_xyz'],f['points']):
                raise ValueError('Divider connection changed original geometry: '+identity)
            represented.add(identity)
        if len(ids)==1:
            output.append(copy.deepcopy(original[ids[0]]))
        else:
            merged+=1
            src=copy.deepcopy(f['source']);src['kind']='V42_native_roadmark_connected';src['native_ids']=ids
            output.append(dict(id='divider:'+digest(dict(source=src,geometry=f['points']))[:24],
                               class_name='divider',points_xyz=f['points'],source=src))
    if represented!=set(original):raise ValueError('Native divider source coverage lost')
    world=copy.deepcopy(base)
    world.update(generator=VERSION if base['map_name']=='Town05' else MULTITOWN_VERSION,display_name=DISPLAY_NAME,revision='divider_connections_r1',
                 features=native_order(base,output),
                 method='native_roadmark_XYZ_and_curb_preserved_with_V41_referenced_divider_connections')
    world['v42_audit']=dict(baseline_generator=base['generator'],baseline_world_sha256=source_sha256,
        input_dividers=len(raw),output_dividers=len(output),merged_chains=merged,
        original_divider_substrings_preserved=True,represented_native_sources=len(represented),
        native_feature_order_preserved=True,
        boundary_unchanged=True,ped_crossing_unchanged=True,centerline_unchanged=True,
        surface_selection_applied=False,rejected_recovery_applied=False,deduplication_applied=False,
        stitch=audit,connection_reference='V4.1 same-paint endpoint/topology rules, isolated V4.2 copy',
        connection_scope='positive gaps above 0.02m; already touching native instances unchanged',
        bridge_support='native drivable lanes including narrow shoulders; XYZ height compatible',
        boundary_scope='unchanged road-local curb geometry; junction boundary repair deferred')
    return validate(world,base['xodr_sha256'])


def generate(repository,xodr,lane_decisions=None,boundary_decisions=None):
    if lane_decisions or boundary_decisions:raise ValueError('V4.2 preserves native Town05 labels')
    from semgt.town05_world import generate as native_generate
    repository=Path(repository);cache=repository/'assets/maps/town05_world.json'
    if cache.exists():
        resources=load(repository/'config/resources.town05.json')
        if sha(cache)!=resources['files']['maps/town05_world.json']:raise ValueError('Native baseline cache changed')
        base=load(cache);fingerprint=sha(cache)
    else:
        base=native_generate(repository,xodr);fingerprint=None
    return connect(base,xodr,fingerprint)


def validate(world,expected):
    if world.get('generator') not in (VERSION,MULTITOWN_VERSION):return validate_native(world,expected)
    if world.get('xodr_sha256')!=expected or world.get('display_name')!=DISPLAY_NAME:
        raise ValueError('V4.2 identity mismatch')
    audit=world.get('v42_audit',{})
    if not all(audit.get(k) for k in ['original_divider_substrings_preserved','boundary_unchanged','ped_crossing_unchanged','centerline_unchanged']):
        raise ValueError('V4.2 native geometry preservation audit missing')
    native=copy.copy(world);native['generator']='xodr_town05_elevation_v1'
    validate_native(native,expected)
    return world
