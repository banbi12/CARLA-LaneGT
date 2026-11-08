"""Native road-strip support for V4.1 bridges, with independent road heights."""
import math
import numpy as np
from shapely.geometry import LineString,Point
from shapely.prepared import prep
from .legacy_map import build_strips


class ElevationSurface:
    def __init__(self,xmap,margin=0.,shared=None):
        self.xmap=xmap;self.margin=margin
        if shared is None:
            strips,_=build_strips(xmap,1.5,.5,{},{} )
            references={r.id:LineString(np.column_stack(r.ref_xy(np.linspace(0,r.length,max(2,int(math.ceil(r.length/.25))+1))))[:,:2]*[1,-1]) for r in xmap.roads}
            shared=dict(strips=strips,references=references,buffers={})
        self.shared=shared
        if margin not in shared['buffers']:
            shared['buffers'][margin]=[(s.road_id,prep(s.polygon.buffer(margin))) for s in shared['strips']]
        self.polygons=shared['buffers'][margin]
        self.is_empty=not self.polygons

    def buffer(self,margin):
        return ElevationSurface(self.xmap,self.margin+margin,self.shared)

    def covers(self,point):
        xy=Point(point.x,point.y)
        for rid,polygon in self.polygons:
            if polygon.covers(xy):
                if not point.has_z:return True
                s=self.shared['references'][rid].project(xy)
                if abs(self.xmap.by_id[rid].elevation_at(s)-point.z)<=.25:
                    return True
        return False

    def bridge_points(self,a,b,pa,pb,ra,rb):
        gap=np.linalg.norm(pa[-1,:2]-pb[0,:2])
        t=np.linspace(0,1,max(2,int(math.ceil(gap/.25))+1))
        points=pa[-1]+t[:,None]*(pb[0]-pa[-1])
        sa,sb=a['source'],b['source']
        if points.shape[1]==3 and sa['road_id']==sb['road_id']:
            start=sa['s_start'] if ra else sa['s_end']
            end=sb['s_end'] if rb else sb['s_start']
            points[:,2]=[self.xmap.by_id[sa['road_id']].elevation_at(float(s)) for s in start+t*(end-start)]
            points[0]=pa[-1];points[-1]=pb[0]
        return points
