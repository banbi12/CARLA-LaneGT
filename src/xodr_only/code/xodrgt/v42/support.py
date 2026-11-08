"""Native road support for generated divider bridges; never selects GT lines."""
import math
import numpy as np
from shapely.geometry import LineString,Polygon,Point
from shapely.prepared import prep
from shapely.strtree import STRtree
from semgt.legacy_xodr import road_boundaries
from ..lanelines import DRIVABLE_LANE_TYPES


class NativeSupport:
    def __init__(self,xmap,margin=0.,shared=None):
        self.xmap=xmap;self.margin=margin
        if shared is None:
            strips=[];refs={}
            for road in xmap.roads:
                s=np.linspace(0,road.length,max(24,int(math.ceil(road.length/.5))+1))
                refs[road.id]=LineString(np.column_stack(road.ref_xy(s))[:,:2]*[1,-1])
                bounds={(b.section_s,b.lane_id):b for b in road_boundaries(road)}
                for index,section in enumerate(road.sections):
                    end=road.sections[index+1].s if index+1<len(road.sections) else road.length
                    ss=np.linspace(section.s,end,max(24,int(math.ceil((end-section.s)/.5))+1))
                    for sign in (1,-1):
                        lanes=sorted([l for l in section.lanes if l.id*sign>0],key=lambda l:abs(l.id))
                        run=[]
                        for lane in lanes+[None]:
                            if lane is not None and lane.type in DRIVABLE_LANE_TYPES:
                                run.append(lane);continue
                            if run:
                                first,last=run[0].id,run[-1].id
                                inner=bounds[(section.s,0 if abs(first)==1 else first-sign)];outer=bounds[(section.s,last)]
                                polygon=Polygon(np.vstack([outer.xy(road,ss),inner.xy(road,ss)[::-1]]))
                                if not polygon.is_valid:polygon=polygon.buffer(0)
                                if not polygon.is_empty:strips.append((road.id,polygon))
                                run=[]
            shared=dict(strips=strips,refs=refs,buffers={})
        self.shared=shared
        if margin not in shared['buffers']:
            polys=[p.buffer(margin) for rid,p in shared['strips']]
            shared['buffers'][margin]=dict(polys=polys,prepared=[prep(p) for p in polys],
                                           tree=STRtree(polys),indices={id(p):i for i,p in enumerate(polys)})
        self.data=shared['buffers'][margin];self.is_empty=not shared['strips']

    def buffer(self,margin):return NativeSupport(self.xmap,self.margin+margin,self.shared)

    def heights(self,xy):
        for item in self.data['tree'].query(xy):
            i=int(item) if isinstance(item,(int,np.integer)) else self.data['indices'][id(item)]
            if self.data['prepared'][i].covers(xy):
                rid=self.shared['strips'][i][0]
                s=self.shared['refs'][rid].project(xy)
                yield self.xmap.by_id[rid].elevation_at(s)

    def covers(self,p):
        return any(not p.has_z or abs(z-p.z)<=.25 for z in self.heights(Point(p.x,p.y)))

    def bridge_points(self,a,b,pa,pb,ra,rb):
        gap=float(np.linalg.norm(pa[-1,:2]-pb[0,:2]))
        t=np.linspace(0,1,max(2,int(math.ceil(gap/.25))+1))
        points=pa[-1]+t[:,None]*(pb[0]-pa[-1])
        support=self.buffer(.05)
        for i,p in enumerate(points[1:-1],1):
            candidates=[z for z in support.heights(Point(p[:2])) if abs(z-p[2])<=.25]
            if candidates:points[i,2]=min(candidates,key=lambda z:abs(z-p[2]))
        points[0]=pa[-1];points[-1]=pb[0]
        return points
