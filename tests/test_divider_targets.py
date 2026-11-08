"""V4.5 instance grouping preserves geometry, road layers, branches and old data."""
from pathlib import Path
import copy,sys,unittest
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src/extraction/code'))
from semgt.divider_targets import normalize,RULE
from semgt.io import load


def feature(i,p,cls='divider',mark='solid'):
    return dict(id=i,parent_id=i,class_name=cls,full=[q[:2] for q in p],full_xyz=p,source=dict(kind='native',mark_type=mark))


class DividerTargetTests(unittest.TestCase):
    def test_duplicates_and_coincident_chains_become_one_target(self):
        a=feature('a',[[0,0,0],[1,0,0]])
        b=feature('b',[[1,0,0],[2,0,0]],mark='broken')
        c=feature('duplicate_b',[[2,0,0],[1,0,0]],mark='solid')
        original=copy.deepcopy([a,b,c]);result,audit=normalize(original)
        self.assertEqual(original,[a,b,c]);self.assertEqual(len(result),1)
        self.assertEqual(result[0]['full_xyz'],[[0,0,0],[1,0,0],[2,0,0]])
        self.assertEqual(set(result[0]['source']['input_target_ids']),{'a','b','duplicate_b'})
        self.assertEqual(audit['duplicate_instances_removed'],1);self.assertEqual(audit['joins_count'],1)
        again,_=normalize(result);self.assertEqual(again,result)

    def test_duplicate_straight_geometry_does_not_depend_on_vertex_count(self):
        a=feature('a',[[0,0,1],[1,0,1.1],[2,0,1.2]])
        b=feature('b',[[0,0,1],[2,0,1.2]])
        result,audit=normalize([a,b]);self.assertEqual(len(result),1)
        self.assertEqual(result[0]['full_xyz'],a['full_xyz'])

    def test_parallel_lanes_and_overpass_layers_are_not_deduplicated(self):
        a=feature('a',[[0,0,0],[1,0,0]])
        b=feature('b',[[0,.1,0],[1,.1,0]])
        c=feature('c',[[0,0,8],[1,0,8]])
        out,_=normalize([a,b,c]);self.assertEqual(out,[a,b,c])

    def test_contained_pieces_do_not_form_a_false_endpoint_branch(self):
        short=feature('short',[[1,0,2],[2,0,2]])
        longer=feature('longer',[[1,0,2],[2.000094,0,2]])
        longest=feature('longest',[[1,0,2],[2.03,0,2]])
        tail=feature('tail',[[0,0,2],[1,0,2]])
        raw=[short,longer,longest,tail];before=copy.deepcopy(raw)
        out,audit=normalize(raw)
        self.assertEqual(raw,before);self.assertEqual(len(out),1)
        self.assertEqual(out[0]['full_xyz'],[[2.03,0,2],[1,0,2],[0,0,2]])
        self.assertEqual(set(out[0]['source']['input_target_ids']),{'short','longer','longest','tail'})
        self.assertEqual(audit['contained_instances_removed'],2)
        self.assertEqual(audit['joins_count'],1)
        self.assertEqual(normalize(out)[0],out)

    def test_containment_keeps_height_offsets_forks_and_uncovered_bends(self):
        a=feature('a',[[0,0,0],[2,0,0]])
        for p in [[[.2,.0001,0],[1,.0001,0]],[[.2,0,.001],[1,0,.001]],
                  [[1,0,0],[1,1,0]],[[0,0,0],[1,.1,0],[2,0,0]]]:
            b=feature('b',p)
            out,_=normalize([a,b]);self.assertEqual(len(out),2)

    def test_curved_containment_uses_both_directions_and_does_not_fill_gaps(self):
        a=feature('a',[[0,0,0],[1,1,1],[2,1,2]])
        b=feature('b',[[.5,.5,.5],[1,1,1],[1.5,1,1.5]])
        out,audit=normalize([b,a]);self.assertEqual(len(out),1)
        self.assertEqual(out[0]['full_xyz'],a['full_xyz'])
        self.assertEqual(audit['contained_instances_removed'],1)
        c=feature('c',[[2.001,1,2],[3,1,3]])
        out,_=normalize([a,b,c]);self.assertEqual(len(out),2)

    def test_reported_scene_0324_nested_piece_has_one_owner_with_its_tail(self):
        token='9c859b0c4ef14b7986d56919246f7924'
        source=R/'outputs/SEMANTIC_V44_1_TOWN03_04_06_20261108/Town03/extraction/frames'/token/'targets.json.gz'
        if not source.exists():self.skipTest('Captured example unavailable')
        raw=load(source);before=copy.deepcopy(raw);out,audit=normalize(raw,[-15,-30,15,30])
        ids=['divider:8ebf181bfbe249a458d3fc2f:layer0:clip0','divider:8a692f598c5d97d1eec283c7:layer0:clip0']
        owners=[t for t in out if set(ids)<=set(t['source'].get('input_target_ids',[t['id']]))]
        self.assertEqual(raw,before);self.assertEqual(len(owners),1)
        self.assertGreater(np.linalg.norm(np.diff(owners[0]['full_xyz'],axis=0),axis=1).sum(),40)
        self.assertTrue(audit['contained_instances_removed'])
        self.assertEqual(normalize(out,[-15,-30,15,30])[0],out)
        self.assertEqual([t for t in out if t['class_name']!='divider'],[t for t in raw if t['class_name']!='divider'])

    def test_no_gap_filling_and_no_branch_stealing(self):
        a=feature('a',[[0,0,0],[1,0,0]])
        b=feature('b',[[1.01,0,0],[2,0,0]])
        out,_=normalize([a,b]);self.assertEqual(out,[a,b])
        b=feature('b',[[1,0,0],[2,0,0]])
        c=feature('c',[[1,0,0],[1,1,0]])
        out,audit=normalize([a,b,c]);self.assertEqual(out,[a,b,c]);self.assertTrue(audit['rejected_endpoints'])

    def test_nondivider_geometry_and_order_remain_verbatim(self):
        bd=feature('bd',[[0,1,3],[2,1,3]],cls='boundary')
        center=feature('c',[[0,3,3],[2,3,3]],cls='centerline')
        a=feature('a',[[0,0,3],[1,0,3]]);b=feature('b',[[1,0,3],[2,0,3]])
        out,_=normalize([a,b,bd,center]);self.assertEqual(out[-2:],[bd,center])

    def test_roi_crop_faces_and_sharp_corners_stay_separate(self):
        a=feature('a',[[-15,-2,0],[-15,0,0]])
        b=feature('b',[[-15,0,0],[-15,2,0]])
        self.assertEqual(normalize([a,b],[-15,-30,15,30])[0],[a,b])
        a=feature('a',[[0,0,0],[1,0,0]])
        b=feature('b',[[1,0,0],[1,1,0]])
        self.assertEqual(normalize([a,b])[0],[a,b])

    def test_reported_real_scene_0316_has_twelve_targets_instead_of_37(self):
        source=R/'outputs/SEMANTIC_V44_1_TOWN03_04_06_20261108/Town03/extraction/frames/f286965f68e041a1813a93be5262a6e1/targets.json.gz'
        if not source.exists():self.skipTest('Captured example unavailable')
        raw=load(source);before=copy.deepcopy(raw);out,audit=normalize(raw,[-15,-30,15,30])
        self.assertEqual(raw,before);self.assertEqual(audit['input_dividers'],37)
        self.assertEqual(audit['output_dividers'],12);self.assertEqual(audit['duplicate_instances_removed'],8)
        self.assertEqual(audit['joins_count'],17)
        self.assertEqual([t for t in out if t['class_name']!='divider'],[t for t in raw if t['class_name']!='divider'])
        self.assertEqual(normalize(out,[-15,-30,15,30])[0],out)

    def test_browser_edit_identity_changes_with_gt_revision(self):
        sys.path.insert(0,str(R/'src/postprocessing/code'))
        from workspace import dataset_identity
        a=dataset_identity('Town03','V4.5',[dict(token='a',gt_sha256='1')])
        self.assertEqual(a,dataset_identity('Town03','V4.5',[dict(token='a',gt_sha256='1')]))
        self.assertNotEqual(a,dataset_identity('Town03','V4.5',[dict(token='a',gt_sha256='2')]))
        self.assertNotEqual(a,dataset_identity('Town03','V4.4.1',[dict(token='a',gt_sha256='1')]))


if __name__=='__main__':unittest.main()
