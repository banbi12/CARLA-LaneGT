"""Explicit on-demand extraction, never executed by checks or collect dry-run."""
from pathlib import Path
import copy,os
import numpy as np
from PIL import Image
from .io import load,save,sha,fresh_output
from .engine import assemble
from .crosswalks import select
from .sampling import actual_targets,diagnostics
from . import algorithm_version
from .nonboundary_base import load_baseline,crosswalk_world

def reference(row,paths,project,out,policy,old_world=None,reference_case=None,baseline=None,baseline_info=None,boundary_world=None):
    if baseline is None:baseline,baseline_info=load_baseline(project,map_profile=paths.get('map_profile'))
    if boundary_world is None:
        from .structural_boundary import load_world
        boundary_world=load_world(project,paths['map_profile'])
    source=Path(paths['topdown_root'])/row['reference'];proof=load(source/'COMPLETE.json')
    for file,digest in proof['files'].items():
        if sha(source/file)!=digest:raise ValueError('Reference hash mismatch: '+str(source/file))
    meta=load(source/'metadata.json')
    from .input_contract import validate
    validate(row,meta,reference_case,baseline['xodr_sha256'])
    from .bev import coverage
    coverage_report=coverage(meta,row['transform'],row.get('BEV_range_m'),policy['border_px'])
    meta=dict(meta,GT_model_from_world=copy.deepcopy(row['transform']))
    labels=np.asarray(Image.open(source/'semantic_labels.png'));depth=np.load(source/'depth_m.npy')
    from .surface import bind,frame_features,nearby_features
    from .structural_boundary import connect
    base=frame_features(baseline['dividers'],row['transform'],row.get('BEV_range_m'))
    # Surface visibility governs repair evidence only; it never gates XODR GT.
    try:
        bind(meta,labels,depth)
        visibility=dict(status='available',pixels=int(meta['_layer_mask'].sum()))
    except ValueError as error:
        if 'No visible road in requested vertical ROI' not in str(error):raise
        visibility=dict(status='unavailable_overhead_occlusion',reason=str(error),pixels=0)
    boundary_roi=row.get('BEV_range_m')
    if policy.get('boundary_route_enabled',False) and visibility['status']=='available':
        # Connect in the complete measured reference, then clip annotations to
        # the original BEV. An anchor just outside the BEV must not disappear.
        points=meta['_world_xyz'][48:-48:16,48:-48:16]
        valid=meta['_layer_mask'][48:-48:16,48:-48:16]
        if valid.any():
            transform=np.asarray(row['transform'])
            local=points[valid]@transform[:3,:3].T+transform[:3,3]
            a,b,c,d=boundary_roi
            boundary_roi=[min(a,float(local[:,0].min()))-.5,min(b,float(local[:,1].min()))-.5,
                          max(c,float(local[:,0].max()))+.5,max(d,float(local[:,1].max()))+.5]
    boundary_base=nearby_features(boundary_world['features'],row['transform'],boundary_roi)
    if visibility['status']=='available':
        boundaries,boundary_audit=connect(boundary_base,boundary_world,meta,labels,policy)
    else:
        boundaries=copy.deepcopy(boundary_base)
        boundary_audit=dict(base_features=len(boundary_base),base_geometry_unchanged=True,
            standalone_semantic_boundaries=0,connections=[],rejected_connections=[],semantic_visibility=visibility)
    features=base+boundaries
    features+=select(crosswalk_world(baseline),row['transform'],meta,row.get('BEV_range_m'))
    boundary_gaps=boundary_audit['connections']
    audit=dict(boundary_structure=boundary_audit,boundary_semantic_visibility=visibility,boundary_context_roi_m=boundary_roi,
        boundary_small_gap_connections=boundary_gaps,boundary_smooth_gap_connections=boundary_gaps,
        small_gap_connections=boundary_gaps,rejected_connections=boundary_audit['rejected_connections'],
        double_yellow=[],raw_observations=[],nonboundary_baseline=baseline_info,
        divider_base=dict(base_features=len(base),supplements=0,semantic_supplements_enabled=False,
            base_geometry_unchanged=True,baseline_version='XODR-only V4.2',candidate_supplements=[],
            rule='V44_exact_V42_divider_no_semantic_additions',boundary_included=False),
        class_sources=dict(divider='frozen XODR-only V4.2 geometry; V4.5 divider target normalization; semantic additions disabled',
            boundary='pinned XODR-only V4.2 road-local boundary in XYZ; semantic/depth only connect structural endpoints',
            ped_crossing='XODR-only V4.2 crosswalk objects',centerline='XODR-only V4.2 baseline'),
        divider_semantic_observations_computed=False)
    hints=[]
    # Keep the established review schema; these masks have no divider role in V4.4.
    for name in ['observed_crosswalk_paint_mask','crosswalk_role_mask','linked_overhanging_lamp_mask','crosswalk_lamp_paint_component_mask']:
        Image.fromarray(np.zeros(labels.shape,np.uint8)).save(out/(name+'.png'))
    coverage=visibility;seams=[];skipped=[]
    save(out/'candidates.json',features);save(out/'audit.json',audit);save(out/'optional_map_hints.json',hints)
    save(out/'reference_manifest.json',dict(reference=row['reference'],source=str(source),source_complete_sha256=sha(source/'COMPLETE.json'),version=algorithm_version(policy),map_hints_affect_geometry=False,
        nonboundary_baseline=baseline_info,boundary_from_XODR=True,
        xodr_connection_constraints=dict(generator=baseline['generator'],baseline_version='XODR-only V4.2'),
        xodr_sha256=meta['xodr_sha256'],BEV_coverage=coverage_report,boundary_coverage=coverage,boundary_seams=seams,boundary_skipped=skipped))
    return features

def run(project,paths,rows,output,policy,old_world=None,use_sampler=False,centerline_mode="none",bev_range=None,topdown_only=False,centerline_world=None):
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import cv2
    cv2.setNumThreads(1)
    from .policy import checked
    policy=checked(policy)
    if policy['divider_semantic_supplements_enabled']:raise ValueError('V4.5 requires semantic divider supplements disabled')
    from .bev import bounds
    bev_range=bounds(bev_range);rows=copy.deepcopy(rows)
    for row in rows:
        row['BEV_range_m']=bev_range
        if topdown_only:row['image_paths']={}
    protected=[paths['topdown_root'],Path(paths['frame_manifest']).parent,paths['native_images'],paths['native_metadata'],paths['native_labels']]+paths.get('protected_output_roots',[])
    from .bev import coverage
    from .input_contract import cases as read_cases,validate
    cases=read_cases(paths)
    baseline,baseline_info=load_baseline(project,map_profile=paths.get('map_profile'))
    from .structural_boundary import load_world
    boundary_world=load_world(project,paths['map_profile'])
    expected=baseline['xodr_sha256']
    profile=None
    if paths.get('map_profile'):
        from .map_profile import read,validate_rows,validate_capture
        profile=read(project,paths['map_profile']);validate_rows(profile,rows)
    for row in rows:
        metadata=load(Path(paths['topdown_root'])/row['reference']/'metadata.json')
        if profile:validate_capture(profile,metadata)
        validate(row,metadata,cases.get(row['reference']),expected)
        coverage(metadata,row['transform'],bev_range,policy['border_px'])
    out=fresh_output(output,protected);partition=load(project/'config/boundary_partition_policy.json');completed_references=set();summary=[]
    divider_policy=load(project/'config/divider_target_policy.json')
    linear_policy=load(project/'config/linear_target_policy.json')
    save(out/'boundary_world.json',boundary_world)
    version=algorithm_version(policy)
    save(out/'manifest.json',dict(version=version,scheme='semantic',nonboundary_baseline=baseline_info,
        boundary_from_XODR=True,boundary_generator=boundary_world['generator'],boundary_world_sha256=sha(out/'boundary_world.json'),frames=rows,policy=policy,divider_target_policy=divider_policy,linear_target_policy=linear_policy,target_revision='R3',BEV_range_m=bev_range,centerline_mode=centerline_mode,topdown_only=topdown_only,candidate_only=True,approved_for_training=False,GPU_used=False))
    center_world=None
    if centerline_mode=='generate':
        target=out/'centerlines_world.json'
        from .centerlines import validate_world
        if centerline_world:
            center_world=validate_world(load(centerline_world),expected)
            if center_world!=baseline['centerlines']:
                raise ValueError('semantic V4.4 generated centerline cache must match its V4.2 baseline')
        else:
            center_world=validate_world(baseline['centerlines'],expected)
        save(target,center_world)
    for row in rows:
        ref=row['reference'];folder=out/'geometry'/ref;folder.mkdir(parents=True,exist_ok=True)
        if ref not in completed_references:
            features=reference(row,paths,project,folder,policy,old_world,cases.get(ref),baseline,baseline_info,boundary_world);completed_references.add(ref)
        else:features=load(folder/'candidates.json')
        centerline=[]
        if centerline_mode=='provided':
            centerline=load(Path(paths['native_labels'])/(row['token']+'.json.gz'))['classes']['centerline']
            if bev_range!=[-15.,-30.,15.,30.]:
                from .centerlines import clip_provided
                centerline=clip_provided(centerline,bev_range)
        elif centerline_mode=='generate':
            from .centerlines import local
            centerline=local(center_world,row,bev_range)
        gt,targets=assemble(row,features,centerline,partition,divider_target_policy=divider_policy,linear_target_policy=linear_policy)
        sampled=actual_targets(targets,paths['model_root'],bev_range) if use_sampler else None
        if sampled is not None:gt,targets=assemble(row,features,centerline,partition,sampled,divider_target_policy=divider_policy,linear_target_policy=linear_policy)
        sampling_report=diagnostics(targets,sampled) if sampled is not None else dict(status='not_run_diagnostic_only')
        frame=out/'frames'/row['token'];frame.mkdir(parents=True,exist_ok=False);gt.update(scheme='semantic',
            nonboundary_baseline=baseline_info,boundary_from_XODR=True,
            centerline_source='XODR-only V4.2 baseline' if centerline_mode=='generate' else centerline_mode,
            centerline_mode=centerline_mode,centerline_exact_from_source=centerline_mode=='provided' and bev_range==[-15.,-30.,15.,30.] and gt.get('centerline_exact_from_source',True))
        gt['algorithm_version']=version
        gt['algorithm_accepted_by_user']=True
        gt['boundary_generator']=boundary_world['generator']
        save(frame/'gt.json.gz',gt)
        if sampled is not None:np.savez_compressed(frame/'actual_sampler_targets.npz',target_ids=np.asarray([f['id'] for f in targets]),**sampled)
        save(frame/'targets.json.gz',targets)
        save(frame/'sampling_diagnostics.json',sampling_report)
        save(frame/'input_binding.json',dict(token=row['token'],image_paths=row['image_paths'],native_metadata=str(Path(paths['native_metadata'])/(row['token']+'.json.gz')) if not topdown_only else None,reference=ref,
            semantic_version=version,nonboundary_baseline=baseline_info))
        summary.append(dict(token=row['token'],counts=gt['counts'],capacity_passed=gt['capacity_passed'],actual_sampler_applied=gt['actual_sampler_applied']))
        if len(summary)%10==0 or len(summary)==len(rows):
            print(__import__('json').dumps(dict(completed=len(summary),total=len(rows),version=version)),flush=True)
    save(out/'SUMMARY.json',dict(status='candidate_generated_pending_manual_review',version=version,frames=summary,approved_for_training=False))
    return out
