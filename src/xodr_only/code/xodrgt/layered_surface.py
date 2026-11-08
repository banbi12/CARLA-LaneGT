"""V4.1 surface operations localized by native road elevation.

Short road-strip cells are unioned only with spatially overlapping cells at a
compatible height. This preserves the V4.1 XY rules without collapsing decks.
"""
from dataclasses import dataclass
from collections import defaultdict
import math
import numpy as np
from shapely import set_precision
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .legacy_map import build_strips,make_surface
from .xodr import road_boundaries
from .elevation_support import ElevationSurface


def parts(g):
    if g.is_empty:return []
    if g.geom_type=='LineString':return [g]
    return [p for child in getattr(g,'geoms',[]) for p in parts(child)]


@dataclass
class Cell:
    road_id:int
    side:str
    lane_ids:list
    polygon:object
    s0:float
    s1:float
    zlo:float
    zhi:float


class LayeredSurface:
    def __init__(self,xmap,crosswalks=(),shared=None,margin=0.):
        self.xmap=xmap;self.margin=margin
        if shared is not None:
            self.shared=shared
        else:
            strips,shoulders=build_strips(xmap,1.5,.5,{},{});cells=[];refs={}
            for road in xmap.roads:
                s=np.linspace(0,road.length,max(24,int(math.ceil(road.length/.5))+1))
                z=np.asarray([road.elevation_at(float(q)) for q in s]);ref=np.column_stack(road.ref_xy(s))[:,:2]*[1,-1]
                refs[road.id]=LineString(ref)
                bounds={b.lane_id:b for b in road_boundaries(road)}
                for strip in [p for p in strips if p.road_id==road.id]:
                    sign=1 if strip.side=='left' else -1
                    first,last=strip.lane_ids[0],strip.lane_ids[-1]
                    inner=bounds[0 if abs(first)==1 else first-sign];outer=bounds[last]
                    start=0
                    while start<len(s)-1:
                        end=start+1
                        while end+1<len(s) and s[end+1]-s[start]<=10. and np.ptp(z[start:end+2])<=.1:
                            end+=1
                        ss=s[start:end+1]
                        poly=Polygon(np.vstack([outer.xy(road,ss),inner.xy(road,ss)[::-1]]))
                        if not poly.is_valid:poly=poly.buffer(0)
                        # Keep snapped coordinates but clear GEOS's precision
                        # model: sub-grid query buffers otherwise become empty
                        # on some oblique polygons in GEOS 3.13.
                        poly=set_precision(set_precision(poly,.005),0)
                        if not poly.is_empty:
                            cells.append(Cell(road.id,strip.side,strip.lane_ids,poly,float(s[start]),float(s[end]),float(z[start:end+1].min()),float(z[start:end+1].max())))
                        start=end
            self.shared=dict(cells=cells,tree=STRtree([c.polygon for c in cells]),refs=refs,
                             crossings=list(crosswalks),unions={},masks={},buffers={},shoulders=shoulders,
                             stats=defaultdict(int))
        self.cells=self.shared['cells'];self.tree=self.shared['tree'];self.is_empty=not self.cells

    def buffer(self,margin):return LayeredSurface(self.xmap,shared=self.shared,margin=self.margin+margin)

    def height(self,index,p):
        c=self.cells[index]
        return self.xmap.by_id[c.road_id].elevation_at(self.shared['refs'][c.road_id].project(p))

    def covers(self,p):
        xy=Point(p.x,p.y);query=xy.buffer(abs(self.margin)+.001)
        for i in self.tree.query(query):
            i=int(i);key=(i,self.margin)
            if key not in self.shared['buffers']:
                self.shared['buffers'][key]=self.cells[i].polygon.buffer(self.margin)
            if self.shared['buffers'][key].covers(xy) and (not p.has_z or abs(self.height(i,xy)-p.z)<=.25):return True
        return False

    bridge_points=ElevationSurface.bridge_points

    def union(self,indices):
        key=tuple(sorted(set(map(int,indices))))
        if key not in self.shared['unions']:
            if not key:return Polygon()
            cells=[self.cells[i] for i in key];lo=min(c.zlo for c in cells);hi=max(c.zhi for c in cells)
            crossing=[p for p in self.shared['crossings'] if np.asarray(p)[:,2].max()>=lo-.25 and np.asarray(p)[:,2].min()<=hi+.25]
            surface,_,_,holes=make_surface(cells,.005,crossing,5.,[],surface_only=True)
            self.shared['unions'][key]=set_precision(surface,0)
            self.shared['stats']['local_unions']+=1
            self.shared['stats']['local_hole_fill_decisions']+=sum(str(h['decision']).startswith('fill_') for h in holes)
        return self.shared['unions'][key]

    def surface_for_line(self,line):
        key=line.wkb
        if key in self.shared['masks']:return self.shared['masks'][key]
        indices=[]
        # The caller erodes the resulting union by up to 5cm. Include
        # neighboring cells across this margin before erosion: a line-only
        # query drops the opposite side of a seam displaced by the 5mm grid,
        # wrongly classifying an internal painted line as a surface edge.
        for i in self.tree.query(line.buffer(.06)):
            i=int(i);shared=line.intersection(self.cells[i].polygon.buffer(.06))
            if shared.is_empty:continue
            probes=[]
            for part in parts(shared):probes.extend(part.interpolate(part.length*t) for t in (0,.5,1))
            if not probes:probes=[shared.representative_point()]
            if not line.has_z or all(abs(line.interpolate(line.project(p)).z-self.height(i,p))<=.25 for p in probes):indices.append(i)
            else:self.shared['stats']['other_level_mask_candidates_rejected']+=1
        result=self.union(indices);self.shared['masks'][key]=result
        return result

    def boundary_fragments(self,progress=None):
        raw=[]
        for i,c in enumerate(self.cells):
            from shapely.geometry import box
            x0,y0,x1,y1=c.polygon.bounds
            neighbors=[int(j) for j in self.tree.query(box(x0-.001,y0-.001,x1+.001,y1+.001))
                       if self.cells[int(j)].zlo<=c.zhi+.25 and self.cells[int(j)].zhi>=c.zlo-.25]
            # Fixed-precision polygon unions snap intersection nodes to the
            # 5mm grid. An exact line/line intersection can consequently
            # drop an entire curved sample edge, despite a <4mm displacement.
            # Select the union's actual outline in a narrow strip around the
            # owner's boundary; do not reconstruct or bridge its gaps.
            outer=self.union(neighbors).boundary.intersection(c.polygon.boundary.buffer(.008))
            for line in parts(outer):
                if line.length<.05:continue
                xy=np.asarray(line.coords)[:,:2]
                xyz=np.c_[xy,[self.height(i,Point(p)) for p in xy]]
                raw.append(dict(points=xyz.tolist(),cell=i,road_id=c.road_id))
            if progress is not None and (i+1)%200==0:progress(dict(boundary_cells=i+1,total=len(self.cells)))
        return raw

    def describe(self):
        return dict(mode='height_compatible_local_V41_surface_unions',cells=len(self.cells),
                    cell_max_length_m=10.,cell_target_max_height_span_m=.1,height_tolerance_m=.25,
                    surface_grid_m=.005,surface_step_m=.5,fill_hole_max_area_m2=5.,
                    boundary_owner_tolerance_m=.008,
                    divider_surface_neighbor_margin_m=.06,
                    stats=dict(self.shared['stats']))


def boundary_curves(raw):
    """Deduplicate shared surface edges, then join degree-two XYZ endpoints."""
    lines=[LineString(f['points']) for f in raw];tree=STRtree(lines);accepted=[];owners=defaultdict(list)
    for i in sorted(range(len(raw)),key=lambda j:(-lines[j].length,j)):
        line=lines[i];matches=[]
        for j in tree.query(line.buffer(.006)):
            for item in owners[int(j)]:
                other=item['line']
                if line.distance(other)>.006:continue
                shared=line.intersection(other.buffer(.005))
                if shared.length<min(.05,.8*min(line.length,other.length)):continue
                probes=[part.interpolate(part.length*t) for part in parts(shared) for t in (0,.5,1)]
                if all(abs(line.interpolate(line.project(p)).z-other.interpolate(other.project(p)).z)<=.25 for p in probes):matches.append(item)
        for item in matches:item['cells'].add(raw[i]['cell'])
        remainder=line.difference(unary_union([m['line'].buffer(.005) for m in matches])) if matches else line
        for part in parts(remainder):
            if part.length<.05:continue
            item=dict(line=part,cells={raw[i]['cell']});accepted.append(item);owners[i].append(item)
    nodes=[];buckets=defaultdict(list);adj=defaultdict(list);edges=[]
    def node(point):
        q=np.asarray(point);key=tuple(np.floor(q[:2]/.04).astype(int));choices=[]
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for n in buckets[(key[0]+dx,key[1]+dy)]:
                    distance=np.linalg.norm(q[:2]-nodes[n][:2])
                    if distance<=.03 and abs(q[2]-nodes[n][2])<=.25:choices.append((distance,n))
        if choices:return min(choices)[1]
        n=len(nodes);nodes.append(q);buckets[key].append(n);return n
    for item in accepted:
        p=np.asarray(item['line'].coords);a,b=node(p[0]),node(p[-1]);i=len(edges)
        edges.append(dict(points=p,cells=item['cells'],ends=(a,b)));adj[a].append(i);adj[b].append(i)
    used=set();output=[];max_seam=0.
    def walk(start,edge):
        nonlocal max_seam
        at=start;coords=None;cells=set()
        while edge not in used:
            used.add(edge);item=edges[edge];a,b=item['ends'];q=item['points'] if at==a else item['points'][::-1]
            if coords is None:coords=q.copy()
            else:
                max_seam=max(max_seam,float(np.linalg.norm(coords[-1]-q[0])))
                seam=(coords[-1]+q[0])/2;coords[-1]=seam;coords=np.vstack([coords,q[1:]])
            cells.update(item['cells']);at=b if at==a else a
            remaining=[k for k in adj[at] if k not in used]
            if len(adj[at])!=2 or not remaining:break
            edge=remaining[0]
        if at==start and len(coords)>2:
            seam=(coords[0]+coords[-1])/2;coords[0]=coords[-1]=seam
        output.append(dict(points=coords.tolist(),cells=sorted(cells)))
    for n,indices in sorted(adj.items()):
        if len(indices)!=2:
            for i in indices:
                if i not in used:walk(n,i)
    for i,e in enumerate(edges):
        if i not in used:walk(e['ends'][0],i)
    return output,dict(raw_edges=len(raw),deduplicated_edges=len(accepted),curves=len(output),
                       endpoint_XY_tolerance_m=.03,endpoint_Z_tolerance_m=.25,maximum_seam_reconciliation_m=max_seam)
