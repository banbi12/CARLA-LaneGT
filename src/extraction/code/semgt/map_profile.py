"""Explicit map identities. No implicit Town05 fallback for multi-map runs."""
from pathlib import Path
import re
from .io import load,sha


def read(project,path):
    repository=Path(project).resolve().parents[1]
    profile=load(path)
    if profile.get('schema')!='lanegt_map_profile_v1':raise ValueError('Unknown map profile')
    map_id=profile['map_id']
    if not isinstance(map_id,str) or re.fullmatch(r'Town[0-9]{2}',map_id) is None:
        raise ValueError('Unregistered map '+map_id)
    asset=(repository/'assets'/profile['xodr_asset']).resolve()
    asset.relative_to((repository/'assets').resolve())
    if sha(asset)!=profile['xodr_sha256']:raise ValueError('Map profile XODR mismatch')
    return profile


def validate_rows(profile,rows):
    for row in rows:
        if row.get('map_id',row.get('map_name'))!=profile['map_id']:
            raise ValueError('Selection map identity mismatch')
        if profile['map_id']!='Town05' and not row['reference'].startswith(profile['map_id']+'_'):
            raise ValueError('Cross-map reference namespace')


def validate_capture(profile,meta):
    if meta.get('map_name','').rsplit('/',1)[-1] not in profile['server_map_aliases']:
        raise ValueError('Capture map name mismatch')
    if meta.get('xodr_sha256')!=profile['xodr_sha256']:
        raise ValueError('Capture map hash mismatch')
