"""Town05 synchronized topdown capture. GPU execution must be explicit."""
from pathlib import Path
import argparse
import hashlib
import json
import queue
import shutil
import time
import sys
import numpy as np
from PIL import Image

R=Path(__file__).resolve().parents[1]


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.writing')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)



def profile_sha(cfg):
    return hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def complete_valid(out,case,cfg,map_sha):
    proof_path=out/'COMPLETE.json'
    if not proof_path.exists():return False
    proof=json.loads(proof_path.read_text());required={'rgb.png','semantic_labels.png','depth_m.npy','metadata.json'}
    if not required<=set(proof.get('files',{})):raise ValueError('Incomplete capture proof '+str(out))
    for name in required:
        if hashlib.sha256((out/name).read_bytes()).hexdigest()!=proof['files'][name]:raise ValueError('Capture hash mismatch '+str(out/name))
    meta=json.loads((out/'metadata.json').read_text())
    if (meta.get('case_id')!=case['case_id'] or meta.get('source_frame_token')!=case['frame']['token'] or
        meta.get('GT_model_from_world')!=case['frame']['transform'] or meta.get('xodr_sha256')!=map_sha or
        meta.get('image_size')!=cfg['capture_size'] or meta.get('capture_profile_sha256')!=profile_sha(cfg)):
        raise ValueError('Completed capture input/profile differs '+str(out))
    return True

def enqueue_latest(q,image):
    while True:
        try:q.put_nowait(image);return
        except queue.Full:
            try:q.get_nowait()
            except queue.Empty:pass


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=2070)
    ap.add_argument('--resume',action='store_true');ap.add_argument('--cases');ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    if not args.execute:raise SystemExit('Capture requires explicit --execute')
    import carla
    cfg=json.loads((R/'config/map.json').read_text())
    cases=json.loads((R/'cases.json').read_text())
    if args.cases:
        wanted=set(args.cases.split(','));cases=[c for c in cases if c['case_id'] in wanted]
        if {c['case_id'] for c in cases}!=wanted:raise ValueError('Unknown capture case')
    client=carla.Client('127.0.0.1',args.port);client.set_timeout(30)
    world=client.get_world();mp=world.get_map();previous=world.get_settings()
    expected=(R/'evidence/server.xodr').read_bytes();map_sha=hashlib.sha256(expected).hexdigest()
    if mp.name.rsplit('/',1)[-1]!=cfg['map_name'] or hashlib.sha256(mp.to_opendrive().encode()).hexdigest()!=map_sha:
        raise ValueError('Town05 live server map/XODR fingerprint mismatch; inspect before capture')
    if previous.synchronous_mode or world.get_actors().filter('vehicle.*'):
        raise ValueError('Capture requires a fresh, owned, empty server')
    actors=[];queues={name:queue.Queue(maxsize=4) for name in ['RGB','SEMANTIC','DEPTH']}
    optical=np.array([[0,0,1,0],[1,0,0,0],[0,-1,0,0],[0,0,0,1]],float)
    try:
        settings=world.get_settings();settings.synchronous_mode=True;settings.fixed_delta_seconds=.05
        world.apply_settings(settings);world.set_weather(carla.WeatherParameters.ClearNoon)
        print('WORLD_READY',mp.name,flush=True)
        for _ in range(12):world.tick(30)
        for layer in cfg['remove_layers']:
            print('UNLOAD_LAYER',layer,flush=True)
            if layer in cfg['keep_layers']:raise ValueError('Cannot unload evidence layer')
            world.unload_map_layer(getattr(carla.MapLayer,layer))
            for _ in range(6):world.tick(30)
        if cfg.get('selective_objects'):
            raise ValueError('Town05 selective object handling requires an audited object inventory')
        print('LAYERS_READY',flush=True)
        width,height=cfg['capture_size'];fov=cfg['capture_fov_deg']
        focal=width/(2*np.tan(np.deg2rad(fov)/2));K=np.array([[focal,0,width/2],[0,focal,height/2],[0,0,1.]])
        for name,bid in [('RGB','sensor.camera.rgb'),('SEMANTIC','sensor.camera.semantic_segmentation'),('DEPTH','sensor.camera.depth')]:
            bp=world.get_blueprint_library().find(bid)
            for key,value in dict(image_size_x=str(width),image_size_y=str(height),fov=str(fov),sensor_tick='0.05',lens_k='0',lens_kcube='0').items():
                if bp.has_attribute(key):bp.set_attribute(key,value)
            if name=='RGB' and bp.has_attribute('motion_blur_intensity'):bp.set_attribute('motion_blur_intensity','0')
            print('SPAWN_SENSOR',name,flush=True)
            actor=world.spawn_actor(bp,carla.Transform(carla.Location(z=60),carla.Rotation(pitch=-90)))
            actor.listen(lambda image,q=queues[name]:enqueue_latest(q,image));actors.append(actor)
        completed=[]
        for case in cases:
            out=R/'topdown_cases'/case['case_id']
            if args.resume and complete_valid(out,case,cfg,map_sha):
                completed.append(case['case_id']);print('REUSED_CAPTURE',case['case_id'],flush=True);continue
            if out.exists():
                if not args.resume or (out/'COMPLETE.json').exists():raise FileExistsError('Refuse existing capture '+str(out))
                archived=R/'interrupted_cases';archived.mkdir(exist_ok=True)
                shutil.move(str(out),str(archived/(case['case_id']+'_'+str(time.time_ns()))))
            tf=carla.Transform(carla.Location(x=case['center_xy'][0],y=case['center_xy'][1],z=case['capture_z']),
                               carla.Rotation(pitch=-90,yaw=case['capture_yaw']))
            for actor in actors:actor.set_transform(tf)
            for _ in range(8):world.tick(30)
            frame_id=world.tick(30);images={}
            for name,q in queues.items():
                while True:
                    im=q.get(timeout=30)
                    if im.frame==frame_id:images[name]=im;break
                    if im.frame>frame_id:raise ValueError('Sensor skipped requested frame')
            if max(im.timestamp for im in images.values())-min(im.timestamp for im in images.values())>1e-6:
                raise ValueError('Sensors are not synchronized')
            raw={name:np.frombuffer(im.raw_data,dtype=np.uint8).reshape(height,width,4) for name,im in images.items()}
            out.mkdir(parents=True)
            Image.fromarray(raw['RGB'][:,:,:3][:,:,::-1]).save(out/'rgb.png')
            Image.fromarray(raw['SEMANTIC'][:,:,2]).save(out/'semantic_labels.png')
            d=raw['DEPTH'].astype(np.float64)
            depth=(1000*(d[:,:,2]+256*d[:,:,1]+65536*d[:,:,0])/16777215).astype(np.float32)
            np.save(out/'depth_m.npy',depth)
            measured=np.asarray(images['RGB'].transform.get_matrix())@optical
            meta=dict(map_id=case.get('map_id'),capture_map_profile=cfg,capture_profile_sha256=profile_sha(cfg),case_id=case['case_id'],source_frame_token=case['frame']['token'],map_name=mp.name,
                xodr_sha256=map_sha,GT_model_from_world=case['frame']['transform'],
                intrinsic=K.tolist(),optical_to_world_carla=measured.tolist(),image_size=[width,height],
                model_z_range_m=cfg['model_z_range_m'],depth_convention='optical_z_metres',
                sensor_frame_ids={k:v.frame for k,v in images.items()},sensor_timestamps={k:v.timestamp for k,v in images.items()},
                measured_sensor_to_world_carla={n:im.transform.get_matrix() for n,im in images.items()},
                semantic_ids=dict(Roads=1,Sidewalks=2,RoadLines=24),weather='ClearNoon',quality='Epic',
                unloaded_layers=cfg['remove_layers'],selective_objects_hidden=False,
                render_validation_status='pending_manual_review',original_source_images_modified=False)
            save(out/'metadata.json',meta)
            names=['rgb.png','semantic_labels.png','depth_m.npy','metadata.json']
            save(out/'COMPLETE.json',dict(files={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names},synchronized_frame=frame_id))
            completed.append(case['case_id']);save(R/'reports/capture_progress.json',dict(done=len(completed),total=len(cases),last_reference=case['case_id']))
            print('CAPTURED',case['case_id'],flush=True)
    finally:
        for actor in actors:
            try:actor.stop();actor.destroy()
            except RuntimeError:pass
        world.apply_settings(previous)


if __name__=='__main__':main()
