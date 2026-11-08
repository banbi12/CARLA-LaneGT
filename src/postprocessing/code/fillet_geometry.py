"""True circular XY fillets for two open polylines; mirrored by fillet_geometry.js."""
import copy
import math

EPS=1e-8


def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def dot(a,b):return a[0]*b[0]+a[1]*b[1]
def sub(a,b):return [a[0]-b[0],a[1]-b[1]]
def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])


def direction(points):
    end=points[-1]
    for p in reversed(points[:-1]):
        length=distance(p,end)
        if length>EPS:return [(end[0]-p[0])/length,(end[1]-p[1])/length],(end[2]-p[2])/length
    raise ValueError('所选线的端部没有有效方向')


def endpoint(points,target,extension,allow_trim):
    """Extend, or trim only the final collinear run; preserve all other points."""
    p=copy.deepcopy(points);u,grade=direction(p);end=p[-1]
    if extension>=-EPS:
        q=end[:] if abs(extension)<EPS else [target[0],target[1],end[2]+extension*grade]
        if extension>EPS:p.append(q)
        return p,q,grade,[],0.
    if not allow_trim:raise ValueError('该半径需要修剪原线；请减小半径或勾选允许修剪')
    cut=-extension;run_start=len(p)-2
    while run_start>=0:
        v=sub(p[run_start],end)
        if abs(cross(v,u))>1e-5 or dot(v,u)>EPS:break
        run_start-=1
    run_start+=1
    available=-dot(sub(p[run_start],end),u)
    if cut>available+EPS:raise ValueError('修剪超出端部直线段；请减小半径或改选端点')
    i=len(p)-2
    while i>0 and -dot(sub(p[i],end),u)<cut-EPS:i-=1
    a,b=p[i],p[i+1];length=distance(a,b)
    if length<=EPS:raise ValueError('端部重复点导致修剪位置无效')
    t=dot(sub(target,a),u)/length
    q=[target[0],target[1],a[2]+t*(b[2]-a[2])]
    grade=(b[2]-a[2])/length
    kept=p[:i+1]
    if distance(kept[-1],q)>EPS:kept.append(q)
    else:kept[-1]=q
    if len(kept)<2 or sum(distance(x,y) for x,y in zip(kept,kept[1:]))<.01:
        raise ValueError('该半径会裁掉整条线；请减小半径')
    return kept,q,grade,[q]+p[i+1:],cut


def plan(targets,op,region=None,vertical=None):
    """Return merged geometry and preview, without modifying targets or operations."""
    from edit_model import checked_bounds
    region=checked_bounds(region);lookup={f['id']:f for f in targets}
    ends=[op.get('a'),op.get('b')]
    if any(not isinstance(e,dict) or e.get('end') not in ('start','end') or e.get('target_id') not in lookup for e in ends):
        raise ValueError('圆角端点无效，实例可能已被删除或合并')
    a,b=[lookup[e['target_id']] for e in ends]
    if a['id']==b['id']:raise ValueError('圆角需要选择两条不同的线')
    if a['class_name'] not in ('divider','boundary') or a['class_name']!=b['class_name']:
        raise ValueError('圆角只支持两条同类 divider 或 boundary')
    for f in [a,b]:
        ps=f['full_xyz']
        if len(ps)<2 or any(len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in ps):
            raise ValueError('圆角输入必须为有效的三维折线')
        if distance(ps[0],ps[-1])<EPS:raise ValueError('闭合实例没有可连接的开放端点')
    allow=op.get('allow_trim',False)
    if type(allow) is not bool:raise ValueError('允许修剪必须为布尔值')
    aa=copy.deepcopy(a['full_xyz']);bb=copy.deepcopy(b['full_xyz'])
    if ends[0]['end']=='start':aa.reverse()
    if ends[1]['end']=='end':bb.reverse()
    u,_=direction(aa);back,_=direction(list(reversed(bb)));v=[-back[0],-back[1]]
    den=cross(u,v);turn=math.atan2(den,dot(u,v))
    if abs(turn)<math.radians(.5) or abs(turn)>math.radians(175):
        raise ValueError('两线近乎平行或反向，无法生成唯一圆角；可使用直线连接')
    delta=sub(bb[0],aa[-1]);alpha=cross(delta,v)/den;beta=cross(u,delta)/den
    radius=op.get('radius_m')
    automatic=radius is None
    if automatic:
        if min(alpha,beta)<=.01:raise ValueError('端部方向没有可自动补接的缺口；请改选端点或输入半径并允许修剪')
        radius=min(alpha,beta)/math.tan(abs(turn)/2)
    if type(radius) not in (int,float) or not math.isfinite(radius) or not .01<=radius<=1000:
        raise ValueError('圆角半径须为 0.01 至 1000 米，或留空自动')
    tangent=radius*math.tan(abs(turn)/2)
    intersection=[aa[-1][k]+u[k]*alpha for k in (0,1)]
    t1=[intersection[k]-u[k]*tangent for k in (0,1)]
    t2=[intersection[k]+v[k]*tangent for k in (0,1)]
    kept_a,q1,g1,removed_a,cut_a=endpoint(aa,t1,alpha-tangent,allow)
    rb,q2,neg_g2,removed_b,cut_b=endpoint(list(reversed(bb)),t2,beta-tangent,allow)
    kept_b=list(reversed(rb));g2=-neg_g2
    sign=1 if turn>0 else -1
    center=[q1[0]-sign*u[1]*radius,q1[1]+sign*u[0]*radius]
    start=math.atan2(q1[1]-center[1],q1[0]-center[0]);length=radius*abs(turn)
    n=max(4,int(math.ceil(length/.1)),int(math.ceil(abs(turn)/math.radians(5))))
    if n>4096:raise ValueError('圆角过长；请减小半径')
    arc=[]
    for i in range(n+1):
        t=i/n;angle=start+turn*t
        z=(2*t**3-3*t**2+1)*q1[2]+(t**3-2*t**2+t)*length*g1+(-2*t**3+3*t**2)*q2[2]+(t**3-t**2)*length*g2
        arc.append([center[0]+radius*math.cos(angle),center[1]+radius*math.sin(angle),z])
    arc[0]=q1[:];arc[-1]=q2[:]
    connector=[aa[-1][:]] if cut_a==0 and alpha-tangent>EPS else []
    connector+=arc
    if cut_b==0 and beta-tangent>EPS:connector.append(bb[0][:])
    xyz=kept_a+arc[1:-1]+kept_b
    if any(any(not math.isfinite(v) for v in p) for p in xyz):raise ValueError('圆角生成了无效的三维坐标')
    if any(not (region[0]-EPS<=p[0]<=region[2]+EPS and region[1]-EPS<=p[1]<=region[3]+EPS) for p in xyz):
        raise ValueError('圆角超出当前 BEV 范围；请调整半径或端点')
    if vertical is not None:
        if not isinstance(vertical,list) or len(vertical)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in vertical) or vertical[0]>=vertical[1]:
            raise ValueError('圆角高程范围无效')
        if any(not vertical[0]-EPS<=p[2]<=vertical[1]+EPS for p in xyz):
            raise ValueError('圆角超出本帧高程范围；请检查所选道路层')
    return dict(class_name=a['class_name'],source_ids=[a['id'],b['id']],points_xyz=xyz,
        connector_xyz=connector,removed_segments=[s for s in [removed_a,removed_b] if s],
        arc_xyz=arc,tangent_points=[q1,q2],radius_m=radius,center_xy=center,turn_deg=math.degrees(turn),
        trim_m=[cut_a,cut_b],extend_m=[max(0.,alpha-tangent),max(0.,beta-tangent)],
        parameters=dict(schema='two_line_circular_fillet_v1',radius_m=radius,automatic_radius=automatic,
            allow_trim=allow,center_xy=center,turn_deg=math.degrees(turn),trim_m=[cut_a,cut_b],
            height_source='endpoint_grades_and_arc_length_Hermite'))
