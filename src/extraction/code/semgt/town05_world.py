"""Road-local XODR XYZ base. Never union different road elevations in XY."""
from pathlib import Path
import numpy as np
from mapgt.common import digest
from mapgt.world import flat_map_guard
from .io import load, sha
from .legacy_xodr import XodrMap

GENERATOR = 'xodr_town05_elevation_v1'
CENTER_GENERATOR = 'town05_elevated_lane_centers_v1'


def centers(xmap, step=.5):
    from .legacy_centerlines import selected_lanes, deduplicate_centerlines, parse_topology, build_edges
    raw, deferred, issues = selected_lanes(xmap, {'lane_inclusion_overrides': []}, step)
    curves, stats = deduplicate_centerlines(raw)
    roads, junctions = parse_topology(Path(xmap.source))
    edges = build_edges(raw, roads, junctions)
    features = [dict(id='center:'+digest(dict(source=f['source'], points=f['points']))[:24],
                     points_xyz=f['points'], source=f['source']) for f in curves]
    return dict(schema='lanegt_centerline_world_v2', generator=CENTER_GENERATOR,
                map_name='Town05', xodr_sha256=sha(xmap.source), features=features,
                raw_centerlines=raw, deduplication=stats,
                topology=dict(edges=edges), deferred_lanes=deferred, geometry_issues=issues,
                audit=dict(passed=bool(features) and stats['source_ids']==stats['represented_source_ids'],
                           scope='finite_geometry_and_height_aware_source_coverage_not_render_accuracy',
                           topology_status_counts={s: sum(e['status']==s for e in edges) for s in {e['status'] for e in edges}}),
                human_review_required=True, GPU_used=False)


def generate(repository, xodr, lane_decisions=None, boundary_decisions=None):
    if lane_decisions or boundary_decisions:
        raise ValueError('Town10 manual map decisions cannot be applied to Town05')
    from xodrgt.lanelines import extract_all_segments, classify_ex
    repository = Path(repository)
    expected = load(repository/'config/resources.town05.json')['files']['capture/server_Town05.xodr']
    if sha(xodr) != expected:
        raise ValueError('Town05 XODR fingerprint mismatch')
    guard = flat_map_guard(xodr)
    xmap = XodrMap.from_file(xodr)
    features = []
    for seg in extract_all_segments(xmap, step=.25, include_unpainted=True):
        road = xmap.by_id[seg.road_id]
        cls, reason = classify_ex(seg, {road.id: road.section_at(seg.s_start).lanes})
        if cls not in ('divider', 'boundary') or seg.length <= .05:
            continue
        source = dict(kind='Town05_native_roadmark' if cls=='divider' else 'Town05_road_local_edge',
                      road_id=road.id, lane_id=seg.lane_id, section_s=road.section_at(seg.s_start).s,
                      s_start=seg.s_start, s_end=seg.s_end, mark_type=seg.mark_type,
                      mark_color=seg.mark_color, selection=reason,
                      boundary_scope='road_local_candidate_no_global_XY_union')
        points = seg.points.tolist()
        features.append(dict(id=cls+':'+digest(dict(source=source,points=points))[:24],
                             class_name=cls, points_xyz=points, source=source))
    for road in xmap.roads:
        for obj in road.objects:
            if obj.type!='crosswalk' or len(obj.corners)<3:
                continue
            points = obj.outline_world(road)
            if not np.allclose(points[0], points[-1]):
                points = np.vstack([points, points[0]])
            source = dict(kind='Town05_XODR_crosswalk', road_id=road.id, object_id=obj.id)
            features.append(dict(id='ped_crossing:'+digest(source)[:24], class_name='ped_crossing',
                                 points_xyz=points.tolist(), source=source))
    center = centers(xmap)
    world = dict(schema='lanegt_xodr_world_v1', generator=GENERATOR, xodr_sha256=expected,
                 map_name='Town05', plane=guard, features=features, centerlines=center,
                 decision_files={}, semantic_images_used=False, GPU_used=False, CARLA_started=False,
                 candidate_only=True, human_approved=False,
                 method='road_local_elevation_profile_base_not_Town10_V41_stitched_reproduction')
    return validate(world, expected)


def validate(world, expected):
    allowed={'xodr_multitown_elevation_v1',GENERATOR,'xodr_town05_elevation_v41_divider_pilot_v1','xodr_only_v41_town05_elevation_v1'}
    if world.get('generator') not in allowed or world.get('xodr_sha256')!=expected:
        raise ValueError('Town05 elevation world identity mismatch')
    if world['generator']=='xodr_town05_elevation_v41_divider_pilot_v1' and not world.get('divider_refinement',{}).get('scope_tokens'):
        raise ValueError('A scoped V4.1 divider pilot must declare its frame scope')
    if world['generator']=='xodr_only_v41_town05_elevation_v1':
        audit=world.get('v41_audit',{})
        required={'surface','selection','recovery','deduplication','stitch','boundary'}
        if not required.issubset(audit) or audit.get('completed_stages')!=sorted(required):
            raise ValueError('Full V4.1 world must include all stage audits')
    ids = set()
    for f in world['features']+world['centerlines']['features']:
        p = np.asarray(f['points_xyz'], float)
        if p.ndim!=2 or p.shape[1]!=3 or len(p)<2 or not np.isfinite(p).all() or f['id'] in ids:
            raise ValueError('Invalid or duplicate elevated world geometry')
        ids.add(f['id'])
    if not world['centerlines']['audit']['passed']:
        raise ValueError('Centerline source coverage failed')
    return world
