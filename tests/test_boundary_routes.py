"""Boundary route regressions with real projected semantic/depth evidence."""
from pathlib import Path
import copy,sys,unittest
import numpy as np
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/'src/extraction/code'),str(R/'tests')]
from semgt.surface import bind
from semgt.structural_boundary import connect,assert_preserved
from semgt.policy import checked


def reference(z=8.,slope=.08):
    h,w=768,512
    K=np.array([[600.,0,w/2],[0,600.,h/2],[0,0,1.]])
    T=np.diag([1.,-1.,-1.,1.]);T[2,3]=z+60.
    model=np.eye(4);model[2,3]=-z
    yy,xx=np.indices((h,w));rays=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(K).T
    depth=(60./(1+slope*rays[:,:,0])).astype(np.float32)
    world_x=rays[:,:,0]*depth
    labels=np.where(abs(world_x)<6,1,2).astype(np.uint8)
    labels[(abs(world_x-1.5)<.09)|(abs(world_x+1.5)<.09)]=24
    rgb=np.full((h,w,3),80,np.uint8);rgb[labels==24]=255
    meta=dict(case_id='synthetic-ref',source_frame_token='synthetic-frame',intrinsic=K.tolist(),
              optical_to_world_carla=T.tolist(),GT_model_from_world=model.tolist(),image_size=[w,h],
              model_z_range_m=[-2.,2.],depth_convention='optical_z_metres',
              semantic_ids=dict(Roads=1,Sidewalks=2,RoadLines=24),
              sensor_frame_ids=dict(RGB=1,SEMANTIC=1,DEPTH=1),sensor_timestamps=dict(RGB=.05,SEMANTIC=.05,DEPTH=.05))
    return meta,labels,depth,rgb


def policy(**kw):
    return checked(dict(dict(boundary_route_enabled=True,boundary_route_align_to_xodr=False),**kw))


def features(a,b):
    return [dict(id='a',class_name='boundary',points_xyz=a,source=dict(road_id=1)),
            dict(id='b',class_name='boundary',points_xyz=b,source=dict(road_id=2))]


class BoundaryRouteTests(unittest.TestCase):
    def test_public_defaults_match_selected_policy_and_version(self):
        import json
        from semgt import VERSION,algorithm_version,STRUCTURAL_VERSION
        default=checked()
        selected=checked(json.loads((R/'config/extraction/semantic_policy.json').read_text()))
        for key in default:
            if key.startswith('boundary_route_'):
                self.assertEqual(default[key], selected[key], key)
        self.assertFalse(selected['connection_use_xodr'])
        for relative in ['config/ACTIVE_SCHEME.json', 'config/extraction/runtime_manifest.json']:
            metadata = json.loads((R / relative).read_text())
            self.assertEqual(metadata['version'], VERSION, relative)
        layout = json.loads((R / 'PROJECT_LAYOUT.json').read_text())
        self.assertEqual(layout['algorithm'], VERSION)
        self.assertEqual(layout['release'], (R / 'VERSION').read_text().strip())
        self.assertEqual(algorithm_version(selected), VERSION)
        self.assertTrue(default['boundary_route_enabled'])
        self.assertTrue(default['boundary_route_align_to_xodr'])
        self.assertEqual(algorithm_version(default),VERSION)
        self.assertEqual(algorithm_version(dict(default,boundary_route_enabled=False)),STRUCTURAL_VERSION)
        self.assertEqual(algorithm_version(dict(default,boundary_route_align_to_xodr=False)),STRUCTURAL_VERSION+'+boundary_route_trial_v1')

    def test_aligned_guide_still_rejects_road_opening_and_wrong_topology(self):
        m,lab,depth,_=reference(slope=0);depth[:]=59.76;bind(m,lab,depth)
        lab[:]=np.where(abs(m['_world_xyz'][:,:,0])<6,1,2);bind(m,lab,depth)
        base=features([[6.3,-14,8],[6.3,-10,8]],[[6.3,10,8],[6.3,14,8]])
        pol=policy(boundary_route_align_to_xodr=True)
        _,audit=connect(base,dict(road_relations=[]),m,lab,pol)
        self.assertFalse(audit['connections'])
        lab[364:405,:]=1;bind(m,lab,depth)
        _,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,pol)
        self.assertFalse(audit['connections'])

    def test_aligned_evidence_uses_observed_tail_at_safe_border(self):
        from semgt.boundary_alignment import validation_tail
        from semgt.boundary_routes import in_reference,route_evidence
        m,lab,depth,_=reference(slope=0);depth[:]=59.7;bind(m,lab,depth)
        lab[:]=np.where(abs(m['_world_xyz'][:,:,0])<6,1,2);bind(m,lab,depth)
        p=np.array([[6.3,36,8],[6.3,33.1,8]])
        q=np.array([[6.3,10,8],[6.3,6,8]])
        bias=dict(lateral_m=-.3,interface_height_bias_m=.3)
        a=validation_tail(p,bias,m,lab);b=validation_tail(q,bias,m,lab,start=True)
        self.assertTrue(in_reference(a,m,lab).all())
        self.assertGreaterEqual(len(a),3)
        guide=np.column_stack([np.full(160,6.),np.linspace(33.1,10,160),np.full(160,8.3)])
        accepted,proof=route_evidence(guide,a,b,m,lab,policy(),{},True)
        self.assertTrue(accepted,proof)

    def test_aligned_grade_uses_native_profile_and_missing_bias_stays_native(self):
        for slope,offset in [(.06,.3),(0,.3)]:
            m,lab,depth,_=reference(slope=0)
            yy,_=np.indices(depth.shape)
            depth[:]=60/(1-slope*(yy-384)/600)
            bind(m,lab,depth)
            lab[:]=np.where(abs(m['_world_xyz'][:,:,0])<6,1,2)
            bind(m,lab,depth)
            x=6+offset
            base=features([[x,-14,8-14*slope],[x,-10,8-10*slope]],
                          [[x,10,8+10*slope],[x,14,8+14*slope]])
            kw={} if slope else dict(boundary_route_alignment_max_offset_m=.1)
            _,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy(boundary_route_align_to_xodr=True,**kw))
            self.assertEqual(len(audit['connections']),1)
            record=audit['connections'][0];p=np.asarray(record['points_xyz'])
            np.testing.assert_allclose(p[:,2],8+p[:,1]*slope,atol=.015)
            if not slope:
                self.assertEqual(record['semantic_fitting']['method'],'native_hermite_alignment_unavailable')
                np.testing.assert_allclose(p[:,0],x)

    def test_aligned_straight_uses_local_bias_and_native_height(self):
        for offset in [.17,.3,.45]:
            m,lab,depth,_=reference(slope=0)
            depth[:]=59.76
            bind(m,lab,depth)
            lab[:]=np.where(abs(m['_world_xyz'][:,:,0])<6,1,2)
            bind(m,lab,depth)
            x=6+offset
            base=features([[x,-14,8],[x,-10,8]],[[x,10,8],[x,14,8]])
            result,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy(boundary_route_align_to_xodr=True))
            self.assertEqual(len(audit['connections']),1,offset)
            record=audit['connections'][0];p=np.asarray(record['points_xyz']);guide=np.asarray(record['semantic_guide_xyz'])
            np.testing.assert_array_equal(p[:,2],8)
            self.assertLess(float(np.percentile(abs(p[:,0]-x),95)),.12)
            self.assertLess(float(np.percentile(abs(guide[:,0]-6),95)),.12)
            self.assertAlmostEqual(abs(record['semantic_fitting']['local_bias']['p']['lateral_m']),offset,delta=.08)
            self.assertFalse(record['semantic_fitting']['measured_surface_height_used_as_output'])
            assert_preserved(base,result)

    def test_aligned_quarter_curb_preserves_native_definition(self):
        m,lab,depth,_=reference(slope=0);bind(m,lab,depth)
        xyz=m['_world_xyz'];x,y=xyz[:,:,0],xyz[:,:,1]
        lab[:]=np.where(np.where(x<-7,y>=0,np.where(y>7,x<=0,(x+7)**2+(y-7)**2<=49)),2,1)
        bind(m,lab,depth)
        base=features([[-12,-.3,8],[-7,-.3,8]],[[.3,7,8],[.3,12,8]])
        result,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy(boundary_route_align_to_xodr=True))
        self.assertEqual(len(audit['connections']),1)
        p=np.asarray(audit['connections'][0]['points_xyz'])
        error=abs(np.linalg.norm(p[:,:2]-[-7,7],axis=1)-7.3)
        self.assertLess(float(np.percentile(error,95)),.2)
        np.testing.assert_array_equal(p[:,2],8)
        np.testing.assert_array_equal(p[0],base[0]['points_xyz'][-1])
        np.testing.assert_array_equal(p[-1],base[1]['points_xyz'][0])
        assert_preserved(base,result)

    def test_long_quarter_curb_is_fitted_to_measured_semantic_interface(self):
        m,lab,depth,_=reference(slope=0)
        bind(m,lab,depth)
        xyz=m['_world_xyz'];x,y=xyz[:,:,0],xyz[:,:,1]
        nonroad=np.where(x<-7,y>=0,np.where(y>7,x<=0,(x+7)**2+(y-7)**2<=49))
        lab[:]=np.where(nonroad,2,1)
        bind(m,lab,depth)
        base=features([[-12,0,8],[-7,0,8]],[[0,7,8],[0,12,8]])
        original=copy.deepcopy(base)
        result,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy())
        self.assertEqual(base,original)
        self.assertEqual(len(audit['connections']),1)
        c=audit['connections'][0]
        self.assertGreater(c['gap_m'],8)
        self.assertEqual(c['semantic_fitting']['method'],'endpoint_anchored_semantic_route_v1')
        p=np.asarray(c['points_xyz'])
        error=abs(np.linalg.norm(p[:,:2]-[-7,7],axis=1)-7)
        self.assertLess(float(np.percentile(error,95)),.25)
        np.testing.assert_array_equal(p[0],base[0]['points_xyz'][-1])
        np.testing.assert_array_equal(p[-1],base[1]['points_xyz'][0])
        assert_preserved(base,result)

    def test_long_straight_over_30m_and_optional_cap(self):
        m,lab,depth,_=reference(slope=0);bind(m,lab,depth)
        base=features([[6,-27,8],[6,-22,8]],[[6,22,8],[6,27,8]])
        _,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy())
        self.assertEqual(len(audit['connections']),1)
        self.assertAlmostEqual(audit['connections'][0]['gap_m'],44)
        _,limited=connect(base,dict(road_relations=[[1,2]]),m,lab,policy(boundary_route_search_max_gap_m=30.))
        self.assertFalse(limited['connections'])

    def test_road_opening_wrong_topology_and_wrong_deck_rejected(self):
        m,lab,depth,_=reference(slope=0);bind(m,lab,depth)
        base=features([[6,-14,8],[6,-10,8]],[[6,10,8],[6,14,8]])
        _,a=connect(base,dict(road_relations=[]),m,lab,policy());self.assertFalse(a['connections'])
        lab[364:405,:]=1;bind(m,lab,depth)
        _,a=connect(base,dict(road_relations=[[1,2]]),m,lab,policy());self.assertFalse(a['connections'])
        m,lab,depth,_=reference(slope=0);bind(m,lab,depth)
        high=features([[6,-14,18],[6,-10,18]],[[6,10,18],[6,14,18]])
        _,a=connect(high,dict(road_relations=[[1,2]]),m,lab,policy());self.assertFalse(a['connections'])

    def test_pole_depth_not_used_as_ground_and_no_unanchored_contours(self):
        m,lab,depth,_=reference(slope=0)
        lab[382:386,315:318]=6;depth[382:386,315:318]=50
        bind(m,lab,depth)
        base=features([[6,-3,8],[6,-.4,8]],[[6,.4,8],[6,3,8]])
        result,a=connect(base,dict(road_relations=[[1,2]]),m,lab,policy())
        self.assertEqual(len(a['connections']),1)
        np.testing.assert_allclose(np.asarray(result[0]['points_xyz'])[:,2],8)
        result,a=connect([],dict(road_relations=[]),m,lab,policy())
        self.assertFalse(result);self.assertEqual(a['standalone_semantic_boundaries'],0)

    def test_static_prop_requires_small_footprint_and_measured_elevation(self):
        base=features([[6,-3,8],[6,-.4,8]],[[6,.4,8],[6,3,8]])
        for raised,large,expected in [(True,False,1),(False,False,0),(True,True,0)]:
            m,lab,depth,_=reference(slope=0)
            patch=(slice(340,430),slice(270,360)) if large else (slice(382,386),slice(315,318))
            lab[patch]=20
            depth[patch]=57 if raised else 60
            bind(m,lab,depth)
            result,audit=connect(base,dict(road_relations=[[1,2]]),m,lab,policy())
            self.assertEqual(len(audit['connections']),expected,(raised,large))
            if expected:np.testing.assert_allclose(np.asarray(result[0]['points_xyz'])[:,2],8)


if __name__=='__main__':unittest.main()
