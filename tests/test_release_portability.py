"""Offline installation boundary: no local datasets, CARLA or model required."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'tools'),str(R/'src/extraction/code')]
from prepare_map import prepare
from semgt.io import load
from semgt.nonboundary_base import load_baseline
from semgt.structural_boundary import load_world

XODR='''<OpenDRIVE><header revMajor="1" revMinor="4"/>
<road id="1" name="fixture" length="10" junction="-1"><planView>
<geometry s="0" x="0" y="0" hdg="0" length="10"><line/></geometry></planView>
<elevationProfile><elevation s="0" a="0" b="0.05" c="0" d="0"/></elevationProfile>
<lanes><laneSection s="0"><left><lane id="1" type="driving" level="false">
<width sOffset="0" a="3.5" b="0" c="0" d="0"/><roadMark sOffset="0" type="curb" color="white"/></lane></left>
<center><lane id="0" type="none" level="false"><roadMark sOffset="0" type="broken" color="yellow"/></lane></center>
<right><lane id="-1" type="driving" level="false"><width sOffset="0" a="3.5" b="0" c="0" d="0"/>
<roadMark sOffset="0" type="curb" color="white"/></lane></right></laneSection></lanes></road></OpenDRIVE>'''


class ReleasePortabilityTests(unittest.TestCase):
    def test_map_resources_are_built_from_xodr_without_a_legacy_checkout(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t)/'checkout';project=repo/'src/extraction';project.mkdir(parents=True)
            x=Path(t)/'map.xodr';x.write_text(XODR)
            receipt=prepare(repo,x,'Town03');p=Path(receipt['map_profile']);self.assertTrue(p.is_file())
            base,info=load_baseline(project,map_profile=p);world=load_world(project,p)
            self.assertEqual(base['map_name'],'Town03');self.assertEqual(base['ped_crossing'],[])
            self.assertTrue(world['features']);self.assertEqual(len(base['centerlines']['features']),2)
            self.assertEqual(load(repo/load(p)['baseline_pin'])['declared_empty_classes'],['ped_crossing'])
            self.assertFalse(receipt['GPU_used']);self.assertFalse(receipt['CARLA_started'])
            with self.assertRaises(FileExistsError):prepare(repo,x,'Town03')

    def test_configure_writes_an_explicit_map_local_file_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);source=t/'input.json';target=t/'paths.town03.local.json'
            source.write_text(json.dumps(dict(map_profile=str(t/'profile.json'),frame_manifest=str(t/'frames.json'),topdown_root=str(t/'topdown'),data_root=str(t/'work'),camera_images=str(t/'images'))))
            cmd=[sys.executable,'-B',str(R/'tools/configure.py'),'--from-json',str(source),'--output',str(target)]
            subprocess.run(cmd,check=True,capture_output=True);content=target.read_bytes();d=load(target)
            self.assertEqual(d['camera_images'],d['native_images']);self.assertEqual(d['map_profile'],str(t/'profile.json'))
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(target.read_bytes(),content)

    def test_run_help_and_prepare_map_help_require_no_config(self):
        for args in [['--help'],['prepare-map','--help']]:
            p=subprocess.run([sys.executable,'-B',str(R/'run.py'),*args],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('prepare',p.stdout.lower())


if __name__=='__main__':unittest.main()
