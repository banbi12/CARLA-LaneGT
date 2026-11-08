#!/usr/bin/env python3
"""Build map-matched V4.2 assets and local profiles from a user-owned XODR."""
from pathlib import Path
import argparse,copy,json,re,shutil,sys
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src/extraction/code'),str(R/'src/xodr_only/code')]
from semgt.io import load,save,sha


def prepare(repo,xodr,map_id,world_path=None,capture_height=60.):
    from semgt.map_world import generate,capabilities
    from xodrgt.v42.world import connect,validate
    if not re.fullmatch(r'Town\d{2}',map_id):raise ValueError('map_id must be TownXX (Town05, not Town5)')
    if not 10<=capture_height<=200:raise ValueError('Invalid capture height')
    repo=Path(repo).resolve();xodr=Path(xodr).resolve();fingerprint=sha(xodr);cap=capabilities(xodr)
    tag=map_id+'_'+fingerprint[:12];folder=repo/'.local/maps'/tag
    if folder.exists():raise FileExistsError('Map profile already exists; reuse it or choose a fresh checkout: '+str(folder))
    # Validate before creating directories. Cache input is explicit and fingerprint checked.
    world=None
    if world_path:
        world=validate(load(world_path),fingerprint)
        if world.get('map_name')!=map_id:raise ValueError('Cached world map name differs')
    native=None
    if world is None:
        native=generate(xodr,map_id)
        world=connect(native,xodr,progress=lambda p:print(json.dumps(dict(stage='divider_stitch',progress=p)),flush=True))
    mapasset=Path('capture')/tag/'server.xodr';worldasset=Path('maps')/tag/'world_v42.json';baseasset=Path('maps')/tag/'nonboundary_v42.json'
    destinations=[repo/'assets'/p for p in [mapasset,worldasset,baseasset]]
    if any(p.exists() for p in destinations):raise FileExistsError('Resource namespace already exists; no overwrite')
    folder.mkdir(parents=True);destinations[0].parent.mkdir(parents=True);destinations[1].parent.mkdir(parents=True)
    shutil.copy2(xodr,destinations[0])
    if world_path:shutil.copy2(world_path,destinations[1])
    else:save(destinations[1],world)
    if native:save(destinations[1].with_name('native.json'),native)
    base=dict(schema='lanegt_semantic_nonboundary_base_v1',version='XODR-only V4.2',generator=world['generator'],
        map_name=map_id,xodr_sha256=fingerprint,source_world_sha256=sha(destinations[1]),source_world_asset=str(worldasset),
        dividers=[f for f in world['features'] if f['class_name']=='divider'],
        ped_crossing=[f for f in world['features'] if f['class_name']=='ped_crossing'],centerlines=world['centerlines'],
        boundary_included=False,boundary_source='separate pinned V4.2 structure with semantic-supported connections',
        source_divider_preservation=world['v42_audit'],GPU_used=False)
    save(destinations[2],base)
    empty=['ped_crossing'] if not base['ped_crossing'] and cap['crosswalk_objects']==0 else []
    pin=dict(schema='semantic_v43_nonboundary_pin_v1',version='XODR-only V4.2',asset=str(baseasset),sha256=sha(destinations[2]),
        generator=world['generator'],xodr_sha256=fingerprint,map_asset=str(mapasset),source_world_asset=str(worldasset),
        source_world_sha256=sha(destinations[1]),classes=['divider','ped_crossing','centerline'],boundary_included=False,
        declared_empty_classes=empty,empty_class_evidence=dict(xodr_crosswalk_objects=cap['crosswalk_objects']))
    save(folder/'nonboundary_v42.json',pin)
    server=('Town10HD' if map_id=='Town10' else map_id)+'_Opt'
    profile=dict(schema='lanegt_map_profile_v1',map_id=map_id,server_map=server,server_map_aliases=[server,server[:-4]],
        xodr_asset=str(mapasset),xodr_sha256=fingerprint,baseline_pin=str((folder/'nonboundary_v42.json').relative_to(repo)),
        model_z_range_m=[-2.,2.],status='offline_generated_live_fingerprint_and_visual_review_required',capabilities=cap)
    save(folder/'profile.json',profile)
    remove=['Foliage','StreetLights','ParkedVehicles','Particles','Props','Buildings','Walls'];keep=['Ground','Decals']
    if map_id=='Town01':remove.remove('Props');keep.append('Props')
    capture=dict(map_name=server,carla_version='0.9.16',model_z_range_m=[-2.,2.],capture_height_m=capture_height,
        capture_size=[1152,2048],capture_fov_deg=36.,safe_border_px=48,remove_layers=remove,keep_layers=keep,
        selective_objects=[],gpu_stop_MB_decimal=7400,gpu_max_fraction=.9,status='template_requires_measured_ROI_coverage_check')
    save(folder/'capture.json',capture)
    receipt=dict(map_id=map_id,map_profile=str(folder/'profile.json'),capture_config=str(folder/'capture.json'),
        world=str(destinations[1]),xodr_sha256=fingerprint,declared_empty_classes=empty,GPU_used=False,CARLA_started=False)
    save(folder/'PREPARATION.json',receipt);return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',required=True);p.add_argument('--xodr',type=Path,required=True)
    p.add_argument('--world',type=Path,help='Optional previously generated matching V4.2 cache');p.add_argument('--capture-height',type=float,default=60.)
    a=p.parse_args();print(json.dumps(prepare(R,a.xodr,a.map,a.world,a.capture_height),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
