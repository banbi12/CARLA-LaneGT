"""Offline UI assembly. Copies code, links immutable source assets, emits file:// data."""
from pathlib import Path
import gzip, hashlib, json, os, shutil

PACKAGE = Path(__file__).resolve().parents[1]
from workspace import settings
DEFAULT_SOURCE = Path(settings(PACKAGE)['base_review'])
BASE=Path(json.loads(Path(settings(PACKAGE)['paths_file']).read_text())['data_root'])


def load(p):
    p = Path(p)
    if p.suffix == '.gz':
        with gzip.open(p, 'rt') as f: return json.load(f)
    return json.loads(p.read_text())


def save(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)
    if p.suffix == '.gz':
        with gzip.open(p, 'wt') as f: f.write(text)
    else: p.write_text(text+'\n')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def index(root):
    text = (root/'audit/data/index.js').read_text().strip()
    assert text.startswith('window.DATASET=')
    return json.loads(text[len('window.DATASET='):].rstrip(';'))


def link(dest, source):
    if dest.exists() or dest.is_symlink():
        if dest.resolve() != source.resolve(): raise ValueError('Refuse to replace '+str(dest))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True); dest.symlink_to(source.resolve(), target_is_directory=source.is_dir())


def source_config(root):
    return settings(PACKAGE,root)


def build_web(dest, source, dataset=None):
    """dest may be a fresh editing workspace or a materialized corrected dataset."""
    import numpy as np
    cfg = source_config(source); canonical = Path(cfg['canonical_review'])
    if dest != PACKAGE:
        for folder in ['code', 'web']:
            if (PACKAGE/folder).exists(): shutil.copytree(PACKAGE/folder, dest/folder, dirs_exist_ok=True)
    for name in ['topdown_cases', 'native_images']:
        link(dest/name, source/name)
    if not (dest/'frames').exists(): link(dest/'frames', source/'frames')
    if not (dest/'geometry').exists(): link(dest/'geometry', source/'geometry')
    (dest/'manifest').mkdir(exist_ok=True)
    if source.resolve()!=dest.resolve(): shutil.copy2(source/'manifest/frames.json', dest/'manifest/frames.json')
    (dest/'audit/assets').mkdir(parents=True, exist_ok=True); (dest/'audit/data').mkdir(parents=True, exist_ok=True)
    for name in ['audit.js', 'audit.css']:
        shutil.copy2(Path(cfg['audit_assets'])/'assets'/name, dest/'audit/assets'/name)
    for name in ['bev_view.js','fillet_geometry.js','edit_core.js', 'editor.js', 'editor.css','cad_geometry.js','cad_core.js','cad_ui.js','dxf_template.js']:
        shutil.copy2(dest/'web'/name, dest/'audit/assets'/name)
    ds = dataset or index(source)
    if 'BEV_range_m' not in ds:
        first=load(dest/'manifest/frames.json')[0]
        ds['BEV_range_m']=load(dest/'frames'/first['token']/'gt.json.gz').get('BEV_range_m',[-15,-30,15,30])
    (dest/'audit/data/index.js').write_text('window.DATASET='+json.dumps(ds, ensure_ascii=False, separators=(',', ':'))+';')
    html = (Path(cfg['audit_assets'])/'gallery.base.html').read_text()
    run_paths=load(cfg['paths_file'])
    if run_paths.get('capture_config'):
        capture_profile=load(run_paths['capture_config']);height=capture_profile['capture_height_m']
        html=html.replace('位于车辆原点上方 60 米','位于车辆原点上方 '+str(height)+' 米')
    html=html.replace('Town10 v1 候选待审',str(ds.get('map_id','CARLA'))+' · semantic V4.3 跨地图测试，候选待审')
    algorithm=ds.get('version','').split('+')[0]
    title='CARLA LaneGT · '+str(ds['frames'])+'帧审核与后处理'
    if algorithm=='semantic_v4_3_xodr_v42_base':
        title='CARLA LaneGT · '+str(ds.get('map_id',''))+' · semantic V4.3 · '+str(ds['frames'])+'帧审核与后处理'
        html=html.replace('divider采用实际semantic/RGB观测，XODR仅辅助约束歧义补线；斑马线沿用XODR，centerline沿用原版。。',
            'divider保留XODR-only V4.2基线并用semantic补充漏线；ped_crossing和centerline采用同一V4.2基线；boundary来自semantic与实测深度，并连接有观测支持的断点。')
        if ds.get('divider_semantic_supplements_enabled') is False:
            html=html.replace('divider保留XODR-only V4.2基线并用semantic补充漏线',
                'divider仅采用XODR-only V4.2基线；semantic补线候选仅作审计，不自动加入GT')
        if ds.get('experimental_guarded_divider_supplements'):
            title+=' · 受控补线实验'
            html=html.replace('divider保留XODR-only V4.2基线并用semantic补充漏线',
                'divider保留V4.2基线，实验加入经斑马线角色与关联灯杆过滤的semantic候选；该实验尚待人工确认')
        html=html.replace('centerline：沿用原版','centerline：XODR-only V4.2基线').replace('含原版 centerline','含 V4.2 centerline')
    if algorithm in ('semantic_v4_4_xodr_structure_semantic_connections','semantic_v4_4_1_xodr_structure_semantic_connections','semantic_v4_5_xodr_structure_semantic_connections'):
        display_version='semantic V4.5' if algorithm=='semantic_v4_5_xodr_structure_semantic_connections' else 'semantic V4.4.1' if algorithm=='semantic_v4_4_1_xodr_structure_semantic_connections' else 'semantic V4.4'
        title='CARLA LaneGT · '+str(ds.get('map_id',''))+' · '+display_version+' · '+str(ds['frames'])+'帧审核与后处理'
        html=html.replace('semantic V4.3 跨地图测试',display_version+' 结构边界测试')
        html=html.replace('divider采用实际semantic/RGB观测，XODR仅辅助约束歧义补线；斑马线沿用XODR，centerline沿用原版。。',
            'divider仅使用XODR-only V4.2；boundary保留V4.2结构，semantic与深度仅提供端点连接证据；没有结构锚点的漏边需人工处理。ped_crossing与centerline沿用V4.2。顶视遮挡不影响XODR基线，但会阻止自动补连。')
        html=html.replace('centerline：沿用原版','centerline：XODR-only V4.2基线').replace('含原版 centerline','含 V4.2 centerline')
        html=html.replace('boundary：道路与人行道交界','boundary：XODR结构与证据连接')
        if algorithm=='semantic_v4_5_xodr_structure_semantic_connections':
            html=html.replace('divider仅使用XODR-only V4.2','divider几何采用XODR-only V4.2；线实例按同类三维重合与唯一端点接续整理，centerline保留方向、boundary保留有意切分')
    if '+manual_v1' in ds.get('version',''):
        title+=' · 已应用人工修改'
        html=html.replace('当前图册中的GT仍待人工审核；','当前图册已应用人工几何修改；下文来源说明对应自动基线，人工修改仍待审核；')
    html = html.replace('{{GALLERY_TITLE}}',title).replace('{{FRAME_COUNT}}',str(ds['frames']))
    import re,html as html_module
    from collections import Counter
    splits=Counter(f['sample_split'] for f in ds['frames_index'])
    split_options='<option value="">全部'+str(ds['frames'])+'帧</option>'+''.join('<option value="'+html_module.escape(k,quote=True)+'">'+html_module.escape(k)+' ('+str(v)+')</option>' for k,v in sorted(splits.items()))
    html=re.sub(r'(<select id="split">).*?(</select>)',lambda m:m[1]+split_options+m[2],html,count=1,flags=re.S)
    html = html.replace('audit/assets/audit.css">', 'audit/assets/audit.css"><link rel="stylesheet" href="audit/assets/editor.css?v=20261108.fillet1">')
    html = html.replace('<main>', '<main><section><h2>人工后处理工作区</h2><p>下方原始审核用于对照；人工补线区可连接、添加和删除实例。'
        '旧页面审核记录可导出 JSON 后在此恢复。补线另存为独立 JSON。<a href="#manualEditor">跳到补线画布</a> · <a href="#cadEditor">跳到 CAD 往返</a> · <a href="README.md">使用说明</a></p></section>')
    html = html.replace('<section><details><summary>待分类观测证据', (dest/'web/editor.html').read_text()+(dest/'web/cad.html').read_text()+'\n<section><details><summary>待分类观测证据')
    html = html.replace('</body>', '<script src="audit/assets/cad_geometry.js?v=20261101.cad1"></script><script src="audit/assets/fillet_geometry.js?v=20261108.fillet1"></script><script src="audit/assets/edit_core.js?v=20261108.fillet1"></script><script src="audit/assets/editor.js?v=20261108.fillet1"></script><script src="audit/assets/dxf_template.js"></script><script src="audit/assets/cad_core.js?v=20261101.cad1"></script><script src="audit/assets/cad_ui.js?v=20261101.cad1"></script></body>')
    # Baseline comparison/evidence links retain their original URL resolution.
    for href in ['comparison.html', 'map_intervention.html', 'REPORT.md', 'KNOWN_ISSUES.md']:
        html = html.replace('href="'+href+'"', 'href="'+os.path.relpath(canonical/href, dest)+'"')
    b=ds['BEV_range_m'];html=html.replace('30×60',str(b[2]-b[0])+'×'+str(b[3]-b[1]))
    (dest/'gallery.html').write_text(html)
    (dest/'editor_data').mkdir(exist_ok=True)
    paths = load(cfg['paths_file']); (dest/'config').mkdir(exist_ok=True);save(dest/'config/paths.json',paths); rows = load(dest/'manifest/frames.json')
    input_hashes = {}
    for row in rows:
        token = row['token']; folder = dest/'frames'/token
        gt = load(folder/'gt.json.gz'); targets = load(folder/'targets.json.gz')
        ref = dest/'topdown_cases'/row['reference']; meta = load(ref/'metadata.json')
        projection = np.asarray(meta['intrinsic']) @ np.linalg.inv(np.asarray(meta['optical_to_world_carla']))[:3] @ np.linalg.inv(np.asarray(row['transform']))
        data = dict(token=token, base_gt_sha256=sha(folder/'gt.json.gz'), gt=gt,
            target_order=[f['id'] for f in targets], model_to_topdown=projection.tolist())
        (dest/'editor_data'/(token+'.js')).write_text('window.receiveEditorBase('+json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+');')
        input_hashes[str((folder/'gt.json.gz').resolve())] = data['base_gt_sha256']
        input_hashes[str((folder/'targets.json.gz').resolve())] = sha(folder/'targets.json.gz')
    save(dest/'project.json', dict(schema='manual_gt_editor_project_v1', base_review=str(dest if dataset else source),
        canonical_review=str(canonical), dataset_id=ds['dataset_id'], manifest_sha256=ds['manifest_sha256'],
        metadata_root=paths['native_metadata'], model_root=paths.get('model_root'),repository_root=cfg['repository_root'],paths_file=cfg['paths_file'],extractor_code=cfg['extractor_code'],review_code=cfg['review_code'],audit_assets=cfg['audit_assets'],
        source_GT_modified=False, supports=['connect', 'fillet', 'add', 'delete', 'undo', 'redo', 'patch_import_export', 'geometry_json_export', 'CPU_materialize','CAD_DXF_roundtrip'],
        centerline_editable=False))
    save(dest/'reports/BUILD_REVIEW.json',dict(passed=True,frames=len(rows),source=str(source),source_GT_modified=False,approved_for_training=False,GPU_used=False))
    save(dest/'SOURCE_FILES_SHA256.json', dict(files=input_hashes,
        baseline_delivery_seal=str(canonical/'reports/DELIVERY_FILES_SHA256.json'),
        baseline_delivery_seal_sha256=sha(canonical/'reports/DELIVERY_FILES_SHA256.json') if (canonical/'reports/DELIVERY_FILES_SHA256.json').exists() else None))
    if (Path(cfg['repository_root'])/'docs/CAD_GUIDE.md').exists() and dest!=PACKAGE:
        guide=(Path(cfg['repository_root'])/'docs/CAD_GUIDE.md').read_text().replace('(../outputs/review60/gallery.html#cadEditor)','(gallery.html#cadEditor)').replace('(POSTPROCESSING.md)','(README.md)').replace('python3 run.py cad','python3 -B code/cad.py').replace('从项目根目录导出一帧','在本图册目录导出一帧');(dest/'CAD_GUIDE.md').write_text(guide)
    if (PACKAGE/'README.md').exists(): shutil.copy2(PACKAGE/'README.md', dest/'README.md') if dest != PACKAGE else None
    shutil.copy2(Path(cfg['repository_root'])/'KNOWN_ISSUES.md', dest/'KNOWN_ISSUES.md')
    shutil.copy2(Path(cfg['repository_root'])/'docs/POSTPROCESSING.md',dest/'POSTPROCESSING.md')
    if dest != PACKAGE:(dest/'README.md').write_text('# LaneGT人工后处理\n\n[HTML说明](POSTPROCESSING.md) · [CAD说明](CAD_GUIDE.md) · [已知限制](KNOWN_ISSUES.md)\n')
    # Ship the instructions referenced by generated review documents.
    repository=Path(cfg['repository_root'])
    if dest != PACKAGE:
        shutil.copytree(repository/'docs',dest/'docs',dirs_exist_ok=True)
        shutil.copytree(repository/'LICENSES',dest/'LICENSES',dirs_exist_ok=True)
        for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:
            shutil.copy2(repository/name,dest/name)
        for name in ['CAD_GUIDE.md','POSTPROCESSING.md']:
            instruction=dest/name;text=instruction.read_text()
            for guide in (repository/'docs').glob('*.md'):
                if guide.name not in ['CAD_GUIDE.md','POSTPROCESSING.md']:
                    text=text.replace(']('+guide.name+')','](docs/'+guide.name+')')
            instruction.write_text(text)
    return ds


def install(dest):
    if dest.exists() or dest.is_symlink(): raise FileExistsError(dest)
    dest.mkdir(parents=True); build_web(dest, DEFAULT_SOURCE)
    shutil.copy2(PACKAGE/'README.md', dest/'README.md')
    save(dest/'reports/INSTALL.json', dict(passed=True, frames=index(DEFAULT_SOURCE)['frames'], source=str(DEFAULT_SOURCE), GPU_used=False, baseline_GT_modified=False))
    print('INSTALLED', dest)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('--install', type=Path, required=True); args = ap.parse_args()
    install(args.install)
