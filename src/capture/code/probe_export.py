"""Export the live map and lane-section waypoint evidence before extraction."""
from pathlib import Path
import argparse,json,hashlib
import carla
R=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=2070)
    ap.add_argument('--execute',action='store_true');ap.add_argument('--cases');ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    if not a.execute:raise ValueError('Explicit GPU execution required')
    cfg=json.loads((R/'config/map.json').read_text());client=carla.Client('127.0.0.1',a.port);client.set_timeout(60)
    world=client.get_world();mp=world.get_map()
    if mp.name.rsplit('/',1)[-1]!=cfg['map_name']:raise ValueError('Unexpected live map')
    text=mp.to_opendrive();(R/'evidence/server.xodr').write_text(text)
    rows=[]
    # Use the simulator's own lane enumeration; include every represented section.
    for w in mp.generate_waypoints(10):
        p=w.transform.location
        rows.append(dict(road_id=w.road_id,section_id=w.section_id,lane_id=w.lane_id,s=w.s,xyz=[p.x,p.y,p.z]))
    report=dict(map_name=mp.name,server_version=client.get_server_version(),client_version=client.get_client_version(),
        xodr_sha256=hashlib.sha256(text.encode()).hexdigest(),available_maps=client.get_available_maps(),
        waypoints=rows,vehicle_count=len(world.get_actors().filter('vehicle.*')))
    (R/'evidence/LIVE_MAP.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(map_name=mp.name,waypoints=len(rows),xodr_sha256=report['xodr_sha256'])),flush=True)

if __name__=='__main__':main()
