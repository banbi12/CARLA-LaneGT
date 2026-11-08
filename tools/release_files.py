"""Explicit source distribution inventory; runtime trees are never traversed."""
from pathlib import Path
import fnmatch,hashlib,json,os


def collect(root):
    root=Path(root).resolve();policy=json.loads((root/'config/release.json').read_text());names=set(policy['files'])
    for name in policy['trees']:
        for p in (root/name).rglob('*'):
            if p.is_symlink() or p.is_file():names.add(p.relative_to(root).as_posix())
    names={n for n in names if not any(fnmatch.fnmatch(n,x) for x in policy['exclude'])}
    for name in names:
        p=root/name
        if not p.exists() and not p.is_symlink():raise FileNotFoundError('Missing public file: '+name)
        if p.is_symlink():
            p.resolve().relative_to(root)
            if not p.resolve().exists():raise ValueError('Broken public symlink: '+name)
    return sorted(names)


def fingerprint(root,names):
    root=Path(root);result={}
    for name in names:
        if name=='RELEASE_FILES_SHA256.json':continue
        p=root/name
        result[name]=dict(symlink=os.readlink(p)) if p.is_symlink() else dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size)
    return result
