#!/usr/bin/env python3
"""Build a new clean source tree without datasets, maps or machine settings."""
from pathlib import Path
import argparse,json,os,shutil
from release_files import collect,fingerprint
from check_release import audit


def build(root,output):
    root=Path(root).resolve();output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise FileExistsError('Source package output must be new')
    for name in ['src','config','assets','web','docs','tests','tools']:
        if (root/name)==output.resolve() or (root/name) in output.resolve().parents:raise ValueError('Output inside a source component')
    check=audit(root)
    if not check['passed']:raise ValueError(json.dumps(check))
    names=collect(root);output.mkdir(parents=True)
    for name in names:
        p=root/name;q=output/name;q.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():q.symlink_to(os.readlink(p),target_is_directory=p.resolve().is_dir())
        else:shutil.copy2(p,q)
    meta=json.loads((root/'PROJECT_LAYOUT.json').read_text());seal=dict(release=meta['release'],algorithm=meta['algorithm'],target_revision='R3',files=fingerprint(output,names))
    (output/'RELEASE_FILES_SHA256.json').write_text(json.dumps(seal,ensure_ascii=False,indent=2)+'\n')
    result=audit(output,verify=True,all_files=True)
    if not result['passed']:raise ValueError(json.dumps(result))
    print(json.dumps(dict(result,output=str(output)),ensure_ascii=False,indent=2));return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.root,a.output)
