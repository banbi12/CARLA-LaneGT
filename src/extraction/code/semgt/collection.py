"""Capture preparation is inert by default; CARLA imports live only in the child template."""
from pathlib import Path
import copy,shutil,subprocess,json
from .io import load,save,sha,fresh_output
from . import VERSION

def planned(project,paths,rows):
    if not paths.get('cases') or not Path(paths['cases']).is_file():raise ValueError('Capture planning requires explicit cases with measured camera placement')
    cases={c['case_id']:c for c in load(paths['cases'])};selected=[];seen=set()
    for row in rows:
        if row['reference'] in seen:continue
        case=copy.deepcopy(cases[row['reference']]);seen.add(row['reference'])
        if case['frame']['transform']!=row['transform']:
            raise ValueError('Capture must use exact full native pose, no nearest-pose substitution')
        selected.append(case)
    repo=project.resolve().parents[1]
    from .map_profile import read,validate_rows
    map_profile=read(project,paths['map_profile']);validate_rows(map_profile,rows)
    profile=load(paths['capture_config'])
    if profile['map_name']!=map_profile['server_map']:raise ValueError('Capture profile/map mismatch')
    return dict(version=VERSION,status='dry_run_no_capture_started',source_rows=len(rows),exact_pose_cases=selected,
        quality='Epic',map=profile['map_name'],camera_reference=dict(height_m=profile['capture_height_m'],size=profile['capture_size'],fov_deg=profile['capture_fov_deg'],sensors=['RGB','SEMANTIC','DEPTH'],synchronized=True),
        layer_variant=profile['remove_layers'],keep_layers=profile['keep_layers'],hide_confirmed_objects=0,
        gpu_stop_MB_decimal=7400,gpu_trigger_MiB=7057,hot_map_switch=False,owned_server_only=True,
        model_z_range_m=profile['model_z_range_m'],render_validation_status='not_yet_run',
        annotation_contract=dict(divider='exact_V42_native_XYZ_no_semantic_supplements',boundary='pinned_V42_structure_semantic_endpoint_connections_only',crosswalk='map_matched_V42_XODR_objects',centerline='map_matched_V42_XODR_centers'),GPU_started=False,CARLA_started=False)


def execute(project,paths,rows,output):
    plan=planned(project,paths,rows)
    out=fresh_output(output,[Path(paths['frame_manifest']).parent,paths['native_images'],paths['native_metadata'],paths['native_labels']]+paths.get('protected_output_roots',[]))
    shutil.copytree(project/'capture_template',out,dirs_exist_ok=True)
    from .map_profile import read
    map_profile=read(project,paths['map_profile'])
    save(out/'config/map.json',load(paths['capture_config']))
    (out/'evidence').mkdir(exist_ok=True)
    shutil.copy2(project.resolve().parents[1]/'assets'/map_profile['xodr_asset'],out/'evidence/server.xodr')
    runtime_paths=load(out/'config/runtime_paths.json') if (out/'config/runtime_paths.json').exists() else dict(carla_root=paths.get('carla_root',''),carla_python=paths['carla_python']);runtime_paths.update(carla_python=paths['carla_python'],carla_root=paths.get('carla_root',runtime_paths['carla_root']));save(out/'config/runtime_paths.json',runtime_paths)
    for name in ['runtime','logs','tmp','cache','reports','topdown_cases']:(out/name).mkdir(exist_ok=True)
    save(out/'cases.json',plan['exact_pose_cases']);save(out/'COLLECTION_PLAN.json',plan)
    manifest=dict(version=VERSION,status='capture_prepared',map_identity_basis='explicit_map_profile_requires_live_server_exact_fingerprint',annotation_contract=plan['annotation_contract'],approved_for_training=False,capture_execution_requested=True)
    save(out/'RUN_MANIFEST.json',manifest)
    # No world is loaded, client created, NVML queried or subprocess started before this explicit call.
    try:
        subprocess.run([paths['carla_python'],'-B','-u',str(out/'code/run_topdown.py'),'--stage','selective','--execute'],check=True)
        manifest['status']='capture_completed'
    except BaseException as error:
        manifest.update(status='capture_failed_or_interrupted',error=repr(error));save(out/'RUN_MANIFEST.json',manifest);raise
    save(out/'RUN_MANIFEST.json',manifest)
    return out
