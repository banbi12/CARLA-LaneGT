#!/usr/bin/env python3
"""Read-only public inventory, local links, privacy and source seal checks."""
from pathlib import Path
import argparse,json,re,subprocess,sys
from urllib.parse import unquote,urlsplit
from release_files import collect,fingerprint


def audit(root,verify=False,all_files=False,git_index=False):
    root=Path(root).resolve();names=collect(root);errors=[]
    machine=re.compile(rb'/(?:home|media)/[A-Za-z0-9_.-]+/')
    for name in names:
        p=root/name
        if p.is_symlink():continue
        data=p.read_bytes()
        if machine.search(data):errors.append('machine-specific path: '+name)
        if len(data)>2_000_000:errors.append('unexpected large file: '+name)
        if p.suffix.lower() in ['.pkl','.npy','.npz','.pth','.pt','.ckpt','.xodr']:errors.append('runtime resource: '+name)
        if name.startswith(('data/','outputs/','provenance/','.local/')) or name.endswith('.local.json'):errors.append('private file: '+name)
        if p.suffix=='.md':
            text=data.decode('utf-8')
            for target in re.findall(r'!?\[[^\]\n]*\]\(([^)]+)\)',text):
                target=target.split(' "',1)[0].strip('<> ');parsed=urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:continue
                q=(p.parent/unquote(parsed.path)).resolve()
                try:q.relative_to(root)
                except ValueError:errors.append('external document link: '+name+' -> '+target);continue
                if not q.exists():errors.append('broken document link: '+name+' -> '+target)
                elif q.is_file() and q.relative_to(root).as_posix() not in names:errors.append('unpublished document target: '+name+' -> '+target)
    if verify:
        manifest=json.loads((root/'RELEASE_FILES_SHA256.json').read_text())
        if manifest['files']!=fingerprint(root,names):errors.append('release source seal does not match current public files')
    if all_files:
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and '.git' not in p.relative_to(root).parts}
        errors+=['unlisted file: '+n for n in sorted(actual-set(names)-{'RELEASE_FILES_SHA256.json'})]
    if git_index:
        tracked=set(filter(None,subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')))
        errors+=['unexpected Git tracked file: '+n for n in sorted(tracked-set(names)-{'RELEASE_FILES_SHA256.json'})]
    return dict(passed=not errors,public_files=len(names),errors=errors,source_distribution_only=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--verify-manifest',action='store_true');p.add_argument('--all-files',action='store_true');p.add_argument('--git-index',action='store_true');a=p.parse_args()
    result=audit(a.root,a.verify_manifest,a.all_files,a.git_index);print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['passed'] else 1)
