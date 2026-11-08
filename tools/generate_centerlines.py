#!/usr/bin/env python3
"""按原版XODR车道几何、局部重叠去重与校验流程生成中心线。"""
from pathlib import Path
import argparse,json,sys
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src/extraction/code'))
from mapgt.world import flat_map_guard
from semgt.io import save,sha
from semgt.town05_world import CENTER_GENERATOR as ENGINE

def generate(xodr,step):
    if not .05<=step<=2:raise ValueError('采样间隔应为0.05～2米')
    flat_map_guard(xodr)
    pin=json.loads((R/'config/resources.town05.json').read_text())['files']['capture/server_Town05.xodr']
    if sha(xodr)!=pin:raise ValueError('仅支持指纹匹配的Town05 XODR')
    from semgt.town05_world import centers
    from semgt.legacy_xodr import XodrMap
    return centers(XodrMap.from_file(xodr),step)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--xodr',type=Path,default=R/'assets/capture/server_Town05.xodr')
    p.add_argument('--step-m',type=float,default=.5);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():raise FileExistsError('输出文件必须不存在')
    result=generate(a.xodr,a.step_m);save(a.output,result)
    print(json.dumps(dict(passed=True,generator=ENGINE,raw_lanes=len(result['raw_centerlines']),curves=len(result['features']),output=str(a.output),GPU_used=False,CARLA_API_used=False)))
if __name__=='__main__':main()
