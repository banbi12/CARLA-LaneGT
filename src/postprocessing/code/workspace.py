"""Resolve source code/assets inside this project; data and model installations stay explicit."""
from pathlib import Path
import json

def settings(package,source=None):
    package=Path(package);cfg={}
    for p in [package/'project.json',Path(source)/'project.json' if source else None]:
        if p is not None and p.exists():cfg.update(json.loads(p.read_text()))
    repo=next((p for p in [package,*package.parents] if (p/'PROJECT_LAYOUT.json').is_file()),None)
    if repo is None and cfg.get('repository_root'):repo=Path(cfg['repository_root'])
    if repo is None or not (repo/'PROJECT_LAYOUT.json').is_file():raise ValueError('Cannot locate CARLA_LaneGT source project')
    paths=repo/'config/paths.local.json'
    if not paths.exists():paths=repo/'config/paths.example.json'
    if source is not None and (Path(source)/'config/paths.json').is_file():
        paths=(Path(source)/'config/paths.json').resolve()
    cfg.update(repository_root=str(repo),paths_file=str(paths),extractor_code=str(repo/'src/extraction/code'),
               review_code=str(repo/'src/review/code'),audit_assets=str(repo/'web/audit'))
    local=json.loads((paths if paths.exists() else repo/'config/paths.example.json').read_text())
    cfg.setdefault('base_review',local['review60']);cfg.setdefault('canonical_review',local['review60'])
    cfg['metadata_root']=local.get('camera_metadata',local.get('native_metadata'));cfg['model_root']=local.get('model_root')
    return cfg


def dataset_identity(map_id,version,frames):
    """Different GT revisions must never share a browser edit-storage namespace."""
    import hashlib
    content=dict(map_id=map_id,version=version,frames=sorted((f['token'],f['gt_sha256']) for f in frames))
    digest=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]
    return str(map_id)+'_LANEGT_'+digest
