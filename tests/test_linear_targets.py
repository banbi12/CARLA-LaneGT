"""Class-aware overlap cleanup preserves direction, true forks and boundary cuts."""
import copy,sys,unittest
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src/extraction/code'),str(R/'tests')]
from semgt.linear_targets import normalize,ownership,apply_to_gt
from test_divider_targets import feature


class LinearTargetTests(unittest.TestCase):
    def test_boundary_containment_removes_false_fork_before_chaining(self):
        a=feature('a',[[1,0,0],[2,0,0]],'boundary')
        b=feature('b',[[1,0,0],[2.03,0,0]],'boundary')
        tail=feature('tail',[[0,0,0],[1,0,0]],'boundary')
        raw=[a,b,tail];before=copy.deepcopy(raw);out,audit=normalize(raw)
        self.assertEqual(raw,before);self.assertEqual(len(out),1)
        self.assertEqual(len(ownership(raw,out,'boundary')),3)
        self.assertEqual(audit['classes']['boundary']['contained_instances_removed'],1)
        self.assertEqual(normalize(out)[0],out)

    def test_centerline_never_reverses_direction_to_join(self):
        right=feature('right',[[1,0,0],[3,0,0]],'centerline')
        left=feature('left',[[0,0,0],[1,0,0]],'centerline')
        short=feature('short',[[1,0,0],[2,0,0]],'centerline')
        out,audit=normalize([right,left,short]);self.assertEqual(len(out),1)
        self.assertEqual(out[0]['full_xyz'],[[0,0,0],[1,0,0],[3,0,0]])
        self.assertTrue(out[0]['source']['direction_preserved'])
        self.assertEqual(normalize(out)[0],out)

    def test_reverse_centerline_geometry_is_a_distinct_directed_target(self):
        a=feature('a',[[0,0,0],[2,0,0]],'centerline')
        b=feature('b',[[2,0,0],[0,0,0]],'centerline')
        c=feature('c',[[1.5,0,0],[.5,0,0]],'centerline')
        out,audit=normalize([a,b,c]);self.assertEqual(len(out),2)
        self.assertEqual(out[0],a);self.assertEqual(out[1]['full_xyz'],b['full_xyz'])

    def test_true_directed_fork_and_merge_remain_separate(self):
        for pts in [([[0,0,0],[1,0,0]],[[1,0,0],[2,0,0]],[[1,0,0],[2,1,0]]),
                    ([[0,0,0],[1,0,0]],[[0,1,0],[1,0,0]],[[1,0,0],[2,0,0]])]:
            raw=[feature(str(i),p,'centerline') for i,p in enumerate(pts)]
            self.assertEqual(normalize(raw)[0],raw)

    def test_same_parent_boundary_partitions_are_protected_and_do_not_steal_branch(self):
        a=feature('a',[[0,0,0],[1,0,0]],'boundary');a['parent_id']='parent'
        b=feature('b',[[1,0,0],[2,0,0]],'boundary');b['parent_id']='parent'
        out,audit=normalize([a,b]);self.assertEqual(out,[a,b])
        self.assertEqual(audit['classes']['boundary']['rejected_endpoints'][0]['reason'],'intentional_boundary_partition')
        c=feature('c',[[1,0,0],[1,1,0]],'boundary')
        self.assertEqual(normalize([a,b,c])[0],[a,b,c])

    def test_no_cross_class_parallel_layer_or_gap_merge(self):
        raw=[feature('a',[[0,0,0],[2,0,0]],'boundary'),feature('b',[[0,0,0],[2,0,0]],'centerline'),
             feature('c',[[0,0,.01],[2,0,.01]],'boundary'),feature('d',[[0,.01,0],[2,.01,0]],'boundary'),
             feature('e',[[2.001,0,0],[3,0,0]],'boundary')]
        self.assertEqual({t['id']:t for t in normalize(raw)[0]},{t['id']:t for t in raw})

    def test_classes_and_centerline_fixed20_follow_the_normalized_order(self):
        raw=[feature('a',[[0,0,0],[1,0,0]],'centerline'),feature('b',[[1,0,0],[2,0,0]],'centerline')]
        ts,audit=normalize(raw);gt=dict(classes={c:[] for c in ['divider','boundary','ped_crossing','centerline']},centerline_exact_from_source=True)
        sampled=dict(fixed20=np.zeros((1,20,2)))
        apply_to_gt(gt,ts,audit,sampled)
        self.assertEqual(gt['counts']['centerline'],1);self.assertFalse(gt['centerline_exact_from_source'])
        self.assertEqual(len(gt['classes']['centerline'][0]['points']),20)

    def test_default_boundary_keeps_a_turn_as_one_target(self):
        from semgt.engine import assemble
        from semgt.divider_targets import DEFAULT
        import json
        partition=json.loads((R/'config/extraction/boundary_partition_policy.json').read_text())
        feature=dict(id='continuous',class_name='boundary',source={},
                     points_xyz=[[-10,0,0],[0,0,0],[0,10,0]])
        row=dict(token='test',reference='test',transform=np.eye(4).tolist())
        gt,targets=assemble(row,[feature],[],partition,linear_target_policy=DEFAULT)
        self.assertEqual(len(targets),1)
        self.assertEqual(targets[0]['full_xyz'],feature['points_xyz'])
        self.assertEqual(gt['counts']['boundary'],1)

    def test_shared_assembler_applies_new_rule_after_adding_centerlines(self):
        from semgt.engine import assemble
        from semgt.divider_targets import DEFAULT
        row=dict(token='test',reference='test',transform=np.eye(4).tolist())
        raw=[feature('a',[[0,0,0],[1,0,0]],'centerline'),feature('b',[[1,0,0],[2,0,0]],'centerline')]
        center=[dict(id=t['id'],parent_id=t['parent_id'],source=t['source'],render_points=t['full'],render_xyz=t['full_xyz']) for t in raw]
        gt,targets=assemble(row,[],center,{},linear_target_policy=DEFAULT)
        self.assertEqual(len(targets),1);self.assertEqual(gt['counts']['centerline'],1)
        self.assertEqual(gt['classes']['centerline'][0]['render_xyz'],[[0,0,0],[1,0,0],[2,0,0]])


if __name__=='__main__':unittest.main()
