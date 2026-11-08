"""Browser/CPU parity, tangent circles, trimming and sloped manual geometry."""
import copy,json,math,subprocess,sys,unittest,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src/postprocessing/code'))
from fillet_geometry import plan
from edit_model import replay


def feature(name,points,cls='boundary'):
    return dict(id=name,parent_id=name,class_name=cls,full=[p[:2] for p in points],full_xyz=points,source=dict(kind='fixture'))


def fixture(radius=None,trim=False):
    base=[feature('a',[[-12,0,-.4],[-5,0,0]]),feature('b',[[0,5,.5],[0,12,.9]])]
    op=dict(id='round1',kind='fillet',a=dict(target_id='a',end='end'),b=dict(target_id='b',end='start'),radius_m=radius,allow_trim=trim)
    return dict(base=base,op=op,region=[-15,-30,15,30],vertical=[-2,2])


class ManualFilletTests(unittest.TestCase):
    def test_true_circle_and_unchanged_original_points_without_trim(self):
        f=fixture();before=copy.deepcopy(f);p=plan(f['base'],f['op'],f['region'],f['vertical'])
        self.assertEqual(f,before);self.assertAlmostEqual(p['radius_m'],5.)
        self.assertEqual(p['points_xyz'][:2],f['base'][0]['full_xyz'])
        self.assertEqual(p['points_xyz'][-2:],f['base'][1]['full_xyz'])
        for q in p['arc_xyz']:
            self.assertAlmostEqual(math.hypot(q[0]-p['center_xy'][0],q[1]-p['center_xy'][1]),5.,places=10)
        self.assertLess(abs(p['arc_xyz'][1][1]-p['arc_xyz'][0][1]),.002)
        self.assertLess(abs(p['arc_xyz'][-1][0]-p['arc_xyz'][-2][0]),.002)
        self.assertEqual(p['arc_xyz'][0][2],0.)
        self.assertEqual(p['arc_xyz'][-1][2],.5)

    def test_manual_radius_extends_or_requires_explicit_trimming(self):
        f=fixture(3);p=plan(f['base'],f['op']);self.assertAlmostEqual(p['extend_m'][0],2.)
        f=fixture(7)
        with self.assertRaisesRegex(ValueError,'允许修剪'):plan(f['base'],f['op'])
        f['op']['allow_trim']=True;p=plan(f['base'],f['op'])
        self.assertAlmostEqual(p['trim_m'][0],2.)
        self.assertAlmostEqual(p['points_xyz'][1][0],-7.)
        self.assertAlmostEqual(p['tangent_points'][0][2],-.4+5/7*.4)
        self.assertEqual(p['points_xyz'][0],f['base'][0]['full_xyz'][0])
        self.assertEqual(p['points_xyz'][-1],f['base'][1]['full_xyz'][-1])

    def test_wrong_lines_parallel_closed_and_invalid_radius_rejected(self):
        cases=[]
        f=fixture();f['op']['b']['target_id']='a';cases.append(f)
        f=fixture();f['base'][1]['class_name']='divider';cases.append(f)
        f=fixture();f['base'][1]=feature('b',[[2,4,0],[8,4,0]]);cases.append(f)
        f=fixture();f['base'][0]=feature('a',[[-5,0,0],[-8,3,0],[-5,0,0]]);cases.append(f)
        for radius in [0,-1,True,'5',float('nan'),float('inf')]:cases.append(fixture(radius))
        for f in cases:
            with self.subTest(f=f):
                with self.assertRaises(ValueError):plan(f['base'],f['op'])

    def test_trim_cannot_remove_entire_line_or_follow_a_curved_tail(self):
        for radius in [12,20]:
            f=fixture(radius,True)
            with self.assertRaises(ValueError):plan(f['base'],f['op'])
        f=fixture(7,True);f['base'][0]=feature('a',[[-12,2,0],[-6,0,0],[-5,0,0]])
        with self.assertRaisesRegex(ValueError,'端部直线段'):plan(f['base'],f['op'])

    def test_bounds_and_vertical_layer_checked(self):
        f=fixture(7,True)
        with self.assertRaisesRegex(ValueError,'BEV'):plan(f['base'],f['op'],[-6,-5,6,13])
        with self.assertRaisesRegex(ValueError,'高程'):plan(f['base'],f['op'],vertical=[-.1,.2])

    def test_chained_fillet_and_old_edits_replay_without_mutating_base(self):
        f=fixture();original=copy.deepcopy(f['base']);first=replay(f['base'],[f['op']])
        self.assertEqual(len(first),1);self.assertEqual(first[0]['source']['operation_kind'],'fillet')
        result=replay(f['base'],[f['op'],dict(id='line',kind='add',class_name='boundary',points=[[2,2],[3,3]])])
        self.assertEqual(len(result),2);self.assertEqual(f['base'],original)
        result=replay(f['base'],[f['op'],dict(id='remove',kind='delete',target_id='manual:round1')]);self.assertFalse(result)
        self.assertEqual(replay(f['base'],[]),original)

    @unittest.skipUnless(shutil.which('node'),'Node.js is optional; required for JS/Python parity')
    def test_javascript_python_geometry_and_validation_parity(self):
        cases=[]
        for angle in [-135,-90,-45,30,90,135]:
            f=fixture();r=math.radians(angle);u=[1,0];v=[math.cos(r),math.sin(r)]
            f['base'][1]=feature('b',[[v[0]*5,v[1]*5,.5],[v[0]*12,v[1]*12,.9]])
            for reverse_a in [False,True]:
                for reverse_b in [False,True]:
                    g=copy.deepcopy(f)
                    for index,reverse,key in [(0,reverse_a,'a'),(1,reverse_b,'b')]:
                        if reverse:
                            g['base'][index]['full_xyz'].reverse();g['base'][index]['full'].reverse()
                            g['op'][key]['end']='start' if index==0 else 'end'
                    cases.append(g)
        cases.extend([fixture(3),fixture(7,True),fixture(7),fixture(40,True),fixture(-1)])
        raw=subprocess.run(['node',str(R/'tests/fillet_bridge.cjs')],input=json.dumps(cases),text=True,capture_output=True,check=True)
        actual=json.loads(raw.stdout)
        def equal(a,b):
            if isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for k in a:equal(a[k],b[k])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for p,q in zip(a,b):equal(p,q)
            elif type(a) in (int,float) and type(b) in (int,float):self.assertAlmostEqual(a,b,places=9)
            else:self.assertEqual(a,b)
        for f,got in zip(cases,actual):
            try:expected=plan(f['base'],f['op'],f['region'],f['vertical'])
            except ValueError as error:self.assertEqual(str(error),got.get('error'));continue
            self.assertNotIn('error',got);equal(expected,got['plan'])
            equal(replay(f['base'],[f['op']],f['region'],f['vertical']),got['targets'])


if __name__=='__main__':unittest.main()
