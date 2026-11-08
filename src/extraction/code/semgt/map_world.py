"""Section-aware adapter for the frozen V4.2 native geometry algorithm."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import numpy as np
from mapgt.common import digest
from .io import sha
from .legacy_xodr import XodrMap,road_boundaries,mark_segments
from .legacy_centerlines import selected_lanes,deduplicate_centerlines,parse_topology,build_edges

GENERATOR='xodr_multitown_elevation_v1'
CENTER_GENERATOR='multitown_elevated_lane_centers_v1'


def capabilities(xodr):
    root=ET.parse(xodr).getroot()
    geometries={c.tag for g in root.findall('road/planView/geometry') for c in g}
    unsupported=geometries-{'line','arc','spiral','poly3','paramPoly3'}
    if unsupported:raise ValueError('Unsupported plan geometry '+str(unsupported))
    for node in root.findall('road/lateralProfile/*'):
        if node.tag not in ('superelevation','crossfall') or any(abs(float(node.get(k,0)))>1e-10 for k in ('a','b','c','d')):
            raise ValueError('Banking/lateral profile is not supported; refuse flattening')
    return dict(supported=True,max_lane_sections=max(len(r.findall('lanes/laneSection')) for r in root.findall('road')),
                road_count=len(root.findall('road')),plan_geometries=sorted(geometries),
                vertical_geometry='road-local XYZ; no nonzero banking accepted',
                crosswalk_objects=len(root.findall('road/objects/object[@type="crosswalk"]')))


def sections(road):
    return [(sec,road.sections[i+1].s if i+1<len(road.sections) else road.length) for i,sec in enumerate(road.sections)]


def native_segments(xmap,step=.25):
    from xodrgt.lanelines import LaneLineSegment
    for road in xmap.roads:
        ends={sec.s:end for sec,end in sections(road)}
        for boundary in road_boundaries(road):
            for a,b,mark in mark_segments(boundary,road):
                a=max(a,boundary.section_s);b=min(b,ends[boundary.section_s])
                if b-a<=1e-8:continue
                s=np.linspace(a,b,max(2,int(math.ceil((b-a)/step))+1))
                points=np.column_stack([boundary.xy(road,s,carla_frame=True),[road.elevation_at(float(v)) for v in s]])
                yield LaneLineSegment(road.id,boundary.lane_id,boundary.side,boundary.lane_type,
                    mark.type,mark.color,mark.lane_change,mark.width,a,b,road.junction,points)


def section_edges(raw,xmap):
    """Directed source graph keyed by (road, section_s, lane), including internal links."""
    roads,junctions=parse_topology(Path(xmap.source))
    by_key={(f['source']['road_id'],f['source']['section_s'],f['source']['lane_id']):f for f in raw}
    edges=[]
    def endpoint(rid,lid,contact):
        road=xmap.by_id[rid]
        return (rid,road.sections[0 if contact=='start' else -1].s,lid)
    def add(kind,src,dst,detail):
        a,b=by_key.get(src),by_key.get(dst)
        row=dict(kind=kind,**detail);row.update({'from':src,'to':dst})
        if a is None or b is None:row.update(status='excluded',reason='lane_not_selected_or_missing')
        else:
            gap=float(np.linalg.norm(np.asarray(a['points'][-1])-b['points'][0]))
            row.update(gap_m=round(gap,5),status='accepted' if gap<=.5 else 'review',
                       reason='source_topology_and_endpoint_agree' if gap<=.5 else 'endpoint_gap_gt_0.5m')
        edges.append(row)
    for key,f in by_key.items():
        rid,ss,lid=key;road=xmap.by_id[rid];idx=[s.s for s in road.sections].index(ss)
        direction='successor' if lid<0 else 'predecessor';nextidx=idx+(1 if lid<0 else -1)
        lane_link=roads[rid]['lanes'].get((ss,lid),{}).get(direction)
        if 0<=nextidx<len(road.sections):
            if lane_link is not None:add('section_link',key,(rid,road.sections[nextidx].s,lane_link),{})
            else:edges.append(dict(kind='section_link',source=key,status='review',reason='missing_lane_link'))
        else:
            link=roads[rid]['links'].get(direction)
            if link and link.get('elementType')=='road' and lane_link is not None:
                add('road_link',key,endpoint(int(link['elementId']),lane_link,link['contactPoint']),dict(road_contact_point=link['contactPoint']))
    for link in junctions:
        a=endpoint(link['incoming_road'],link['from_lane'],'end')
        b=endpoint(link['connecting_road'],link['to_lane'],link['contact_point'])
        add('junction_laneLink',a,b,link)
    return edges


def centers(xmap,map_id):
    raw,deferred,issues=selected_lanes(xmap,{'lane_inclusion_overrides':[]},.5)
    curves,stats=deduplicate_centerlines(raw)
    roads,junctions=parse_topology(Path(xmap.source))
    edges=build_edges(raw,roads,junctions) if all(len(r.sections)==1 for r in xmap.roads) else section_edges(raw,xmap)
    features=[dict(id='center:'+digest(dict(source=f['source'],points=f['points']))[:24],points_xyz=f['points'],source=f['source']) for f in curves]
    return dict(schema='lanegt_centerline_world_v2',generator=CENTER_GENERATOR,map_name=map_id,
        xodr_sha256=sha(xmap.source),features=features,raw_centerlines=raw,deduplication=stats,
        topology=dict(edges=edges),deferred_lanes=deferred,geometry_issues=issues,
        audit=dict(passed=bool(features) and stats['source_ids']==stats['represented_source_ids'],
            scope='finite_geometry_and_height_aware_source_coverage_not_render_accuracy',
            topology_status_counts={s:sum(e['status']==s for e in edges) for s in {e['status'] for e in edges}}),
        human_review_required=True,GPU_used=False)


def generate(xodr,map_id):
    from xodrgt.lanelines import classify_ex
    guard=capabilities(xodr);xmap=XodrMap.from_file(xodr);features=[]
    for seg in native_segments(xmap):
        road=xmap.by_id[seg.road_id];section=road.section_at(seg.s_start)
        cls,reason=classify_ex(seg,{road.id:section.lanes})
        if cls not in ('divider','boundary') or seg.length<=.05:continue
        source=dict(kind=map_id+('_native_roadmark' if cls=='divider' else '_road_local_edge'),road_id=road.id,
            lane_id=seg.lane_id,section_s=section.s,s_start=seg.s_start,s_end=seg.s_end,
            mark_type=seg.mark_type,mark_color=seg.mark_color,selection=reason,
            boundary_scope='road_local_candidate_no_global_XY_union')
        points=seg.points.tolist()
        features.append(dict(id=cls+':'+digest(dict(source=source,points=points))[:24],class_name=cls,points_xyz=points,source=source))
    for road in xmap.roads:
        for obj in road.objects:
            if obj.type!='crosswalk' or len(obj.corners)<3:continue
            points=obj.outline_world(road)
            if not np.allclose(points[0],points[-1]):points=np.vstack([points,points[0]])
            source=dict(kind=map_id+'_XODR_crosswalk',road_id=road.id,object_id=obj.id)
            features.append(dict(id='ped_crossing:'+digest(source)[:24],class_name='ped_crossing',points_xyz=points.tolist(),source=source))
    return dict(schema='lanegt_xodr_world_v1',generator=GENERATOR,xodr_sha256=sha(xodr),map_name=map_id,
        plane=guard,features=features,centerlines=centers(xmap,map_id),decision_files={},
        semantic_images_used=False,GPU_used=False,CARLA_started=False,candidate_only=True,human_approved=False,
        method='section_bounded_native_roadMark_XYZ_without_global_XY_union')
