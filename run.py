#!/usr/bin/env python3
"""CARLA LaneGT MultiTown: explicit per-map CPU extraction and offline review."""
from pathlib import Path
import argparse,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parent
COMMANDS=['doctor','prepare-map','check','collect-plan','collect','extract','xodr-only','review',
          'export-maptr','geometry-check','dataset-check','postprocess','cad']


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,epilog='See docs/QUICKSTART.md. Capture requires collect --execute.')
    p.add_argument('--paths',type=Path,default=ROOT/'config/paths.local.json',help='Explicit per-map local configuration')
    p.add_argument('command',choices=COMMANDS);a,args=p.parse_known_args(argv)
    paths_file=a.paths.resolve();paths=json.loads(paths_file.read_text()) if paths_file.is_file() else {}
    help_requested=any(x in args for x in ['-h','--help'])
    if a.command=='prepare-map':script=ROOT/'tools/prepare_map.py'
    elif a.command=='doctor':
        q=argparse.ArgumentParser();q.add_argument('--topdown-only',action='store_true');q.add_argument('--xodr-only',action='store_true');q.add_argument('--centerline',choices=['none','generate','provided'],default='none');b=q.parse_args(args)
        if not paths:raise SystemExit('Create a per-map configuration with tools/configure.py; see docs/CONFIGURATION.md')
        keys=['map_profile','frame_manifest']+([] if b.xodr_only else ['topdown_root'])
        if not b.topdown_only:keys+=['native_metadata','native_images']
        if b.centerline=='provided':keys+=['native_labels']
        inputs={k:dict(path=paths.get(k),exists=bool(paths.get(k) and Path(paths[k]).exists())) for k in keys}
        ok=all(v['exists'] for v in inputs.values());report=dict(inputs=inputs,GPU_started=False,CARLA_started=False)
        if ok:
            sys.path.insert(0,str(ROOT/'src/extraction/code'))
            from semgt.nonboundary_base import load_baseline
            base,info=load_baseline(ROOT/'src/extraction',map_profile=paths['map_profile']);report['baseline']=info
        report['passed']=ok;print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if ok else 1
    else:
        if not paths and not help_requested:raise SystemExit('Configuration missing; see docs/CONFIGURATION.md')
        scripts={'xodr-only':'src/xodr_only/code/cli.py','review':'src/review/code/prepare_review.py',
            'export-maptr':'tools/export_maptr.py','geometry-check':'tools/check_geometry.py',
            'dataset-check':'src/review/code/check_dataset.py','postprocess':'src/postprocessing/code/postprocess.py','cad':'src/postprocessing/code/cad.py'}
        script=ROOT/scripts.get(a.command,'src/extraction/code/cli.py')
        if a.command in ['check','extract','collect','collect-plan']:
            if a.command=='collect-plan' and '--execute' in args:raise SystemExit('collect-plan never executes capture')
            args=['--paths',str(paths_file),'collect' if a.command=='collect-plan' else a.command,*args]
        elif a.command in ['review','export-maptr','xodr-only']:
            args=['--paths',str(paths_file),*args]
            if a.command=='xodr-only' and not help_requested and '--world' not in args:
                profile=json.loads(Path(paths['map_profile']).read_text());pin=json.loads((ROOT/profile['baseline_pin']).read_text())
                args+=['--world',str(ROOT/'assets'/pin['source_world_asset'])]
    sampled=(('--sampler' in args and args[args.index('--sampler')+1]=='maptr') or a.command in ['export-maptr','dataset-check']) and not help_requested
    if sampled and (not paths.get('model_root') or not paths.get('maptr_python')):raise SystemExit('MapTR sampling requires model_root and maptr_python')
    python=paths.get('maptr_python') if sampled else paths.get('runtime_python',sys.executable)
    if a.command=='prepare-map':python=sys.executable
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    if a.command!='collect' or '--execute' not in args:env['CUDA_VISIBLE_DEVICES']=''
    if sampled:
        sys.path.insert(0,str(ROOT/'src/extraction/code'))
        from semgt.sampling_runtime import environment
        env.update(environment(python))
    return subprocess.call([python,'-B',str(script),*args],cwd=ROOT,env=env)


if __name__=='__main__':raise SystemExit(main())
