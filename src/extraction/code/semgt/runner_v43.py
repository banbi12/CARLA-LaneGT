"""Explicit on-demand extraction, never executed by checks or collect dry-run."""
from pathlib import Path
import copy,os
import numpy as np
from PIL import Image
from .io import load,save,sha,fresh_output
from .engine import dividers,assemble,repair_boundaries
from .crosswalks import select
from .sampling import actual_targets,diagnostics
from . import LEGACY_VERSION as VERSION
from .nonboundary_base import load_baseline,crosswalk_world

def reference(row,paths,project,out,policy,old_world=None,reference_case=None,baseline=None,baseline_info=None):
    if baseline is None:baseline,baseline_info=load_baseline(project,map_profile=paths.get('map_profile'))
    source=Path(paths['topdown_root'])/row['reference'];proof=load(source/'COMPLETE.json')
    for file,digest in proof['files'].items():
        if sha(source/file)!=digest:raise ValueError('Reference hash mismatch: '+str(source/file))
    meta=load(source/'metadata.json')
    from .input_contract import validate
    validate(row,meta,reference_case,baseline['xodr_sha256'])
    from .bev import coverage
    coverage_report=coverage(meta,row['transform'],row.get('BEV_range_m'),policy['border_px'])
    meta=dict(meta,GT_model_from_world=copy.deepcopy(row['transform']))
    labels=np.asarray(Image.open(source/'semantic_labels.png'));depth=np.load(source/'depth_m.npy');rgb=np.asarray(Image.open(source/'rgb.png').convert('RGB'))
    from .surface import bind,frame_features
    bind(meta,labels,depth)
    base=frame_features(baseline['dividers'],row['transform'],row.get('BEV_range_m'))
    features,audit,hints=dividers(meta,labels,depth,rgb,policy,old_world,None,base,baseline['ped_crossing'])
    from .town05_geometry import boundary_observations
    boundaries=boundary_observations(meta,labels,depth)
    features+=boundaries
    coverage=dict(method='measured_depth_ego_relative_vertical_ROI',pixels=int(meta['_layer_mask'].sum()))
    seams=[];skipped=[]
    crossings=crosswalk_world(baseline)
    features+=select(crossings,row['transform'],meta,row.get('BEV_range_m'))
    features,boundary_gaps,boundary_rejected=repair_boundaries(features,meta,labels,depth,audit['observed_crosswalk_mask'],policy)
    audit['boundary_small_gap_connections']=boundary_gaps
    audit['boundary_smooth_gap_connections']=[record for record in boundary_gaps if record.get('boundary_smooth_connection')]
    audit['small_gap_connections']+=boundary_gaps
    audit['rejected_connections']+=boundary_rejected
    audit['nonboundary_baseline']=baseline_info
    audit['class_sources']=dict(divider='XODR-only V4.2 plus height-aware semantic supplements' if policy['divider_semantic_supplements_enabled'] else 'XODR-only V4.2; semantic candidates kept for audit only',
        boundary='semantic road/sidewalk and measured depth; observed-boundary connections',
        ped_crossing='XODR-only V4.2 crosswalk objects',centerline='V4.2 baseline when centerline=generate')
    stripe_mask=audit.pop('observed_crosswalk_mask');Image.fromarray((stripe_mask*255).astype(np.uint8)).save(out/'observed_crosswalk_paint_mask.png')
    context=meta['_occlusion_context']
    Image.fromarray((context['role']*255).astype(np.uint8)).save(out/'crosswalk_role_mask.png')
    Image.fromarray((context['linked_halo']*255).astype(np.uint8)).save(out/'linked_overhanging_lamp_mask.png')
    Image.fromarray((context['ambiguous_paint']*255).astype(np.uint8)).save(out/'crosswalk_lamp_paint_component_mask.png')
    save(out/'candidates.json',features);save(out/'audit.json',audit);save(out/'optional_map_hints.json',hints)
    save(out/'reference_manifest.json',dict(reference=row['reference'],source=str(source),source_complete_sha256=sha(source/'COMPLETE.json'),version=VERSION,map_hints_affect_geometry=False,
        nonboundary_baseline=baseline_info,boundary_from_XODR=False,
        xodr_connection_constraints=dict(generator=baseline['generator'],baseline_version='XODR-only V4.2'),
        xodr_sha256=meta['xodr_sha256'],BEV_coverage=coverage_report,boundary_coverage=coverage,boundary_seams=seams,boundary_skipped=skipped))
    return features

def run(project,paths,rows,output,policy,old_world=None,use_sampler=False,centerline_mode="none",bev_range=None,topdown_only=False,centerline_world=None):
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import cv2
    cv2.setNumThreads(1)
    from .policy import checked
    policy=checked(policy)
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
    save(out/'manifest.json',dict(version=VERSION,scheme='semantic',nonboundary_baseline=baseline_info,
        boundary_from_XODR=False,frames=rows,policy=policy,BEV_range_m=bev_range,centerline_mode=centerline_mode,topdown_only=topdown_only,candidate_only=True,approved_for_training=False,GPU_used=False))
    center_world=None
    if centerline_mode=='generate':
        target=out/'centerlines_world.json'
        from .centerlines import validate_world
        if centerline_world:
            center_world=validate_world(load(centerline_world),expected)
            if center_world!=baseline['centerlines']:
                raise ValueError('semantic V4.3 generated centerline cache must match its V4.2 baseline')
        else:
            center_world=validate_world(baseline['centerlines'],expected)
        save(target,center_world)
    for row in rows:
        ref=row['reference'];folder=out/'geometry'/ref;folder.mkdir(parents=True,exist_ok=True)
        if ref not in completed_references:
            features=reference(row,paths,project,folder,policy,old_world,cases.get(ref),baseline,baseline_info);completed_references.add(ref)
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
        gt,targets=assemble(row,features,centerline,partition)
        sampled=actual_targets(targets,paths['model_root'],bev_range) if use_sampler else None
        if sampled is not None:gt,targets=assemble(row,features,centerline,partition,sampled)
        sampling_report=diagnostics(targets,sampled) if sampled is not None else dict(status='not_run_diagnostic_only')
        frame=out/'frames'/row['token'];frame.mkdir(parents=True,exist_ok=False);gt.update(scheme='semantic',
            nonboundary_baseline=baseline_info,boundary_from_XODR=False,
            centerline_source='XODR-only V4.2 baseline' if centerline_mode=='generate' else centerline_mode,
            centerline_mode=centerline_mode,centerline_exact_from_source=centerline_mode=='provided' and bev_range==[-15.,-30.,15.,30.])
        save(frame/'gt.json.gz',gt)
        if sampled is not None:np.savez_compressed(frame/'actual_sampler_targets.npz',target_ids=np.asarray([f['id'] for f in targets]),**sampled)
        save(frame/'targets.json.gz',targets)
        save(frame/'sampling_diagnostics.json',sampling_report)
        save(frame/'input_binding.json',dict(token=row['token'],image_paths=row['image_paths'],native_metadata=str(Path(paths['native_metadata'])/(row['token']+'.json.gz')) if not topdown_only else None,reference=ref,
            semantic_version=VERSION,nonboundary_baseline=baseline_info))
        summary.append(dict(token=row['token'],counts=gt['counts'],capacity_passed=gt['capacity_passed'],actual_sampler_applied=gt['actual_sampler_applied']))
        if len(summary)%10==0 or len(summary)==len(rows):
            print(__import__('json').dumps(dict(completed=len(summary),total=len(rows),version=VERSION)),flush=True)
    save(out/'SUMMARY.json',dict(status='candidate_generated_pending_manual_review',version=VERSION,frames=summary,approved_for_training=False))
    return out
