"""隔离近臂试验；只写审阅PNG和JSON，不构建或提升运行包。"""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import ast
import copy
import hashlib
import json
import math
import types

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
OUT = RIG / 'arm_setup_review_v8'
REF = RIG / 'video_parts_v1/cycle_review'
STABLE = RIG / 'stable_parts_v1'
DONOR = RIG / 'image2_repairs/arm_near_video_setup_v8.png'
SOURCE = BASE / 'generated_rig/right_front_walk/source768.png'
FLAGS = {'prototypeAccepted': False, 'productionApproved': False}
# 已实际查看v8原图。三点均为人工语义推断，不是观测关节或自动检测。
DONOR_JOINTS = np.array([[690., 290.], [535., 580.], [420., 790.]])
CROP = (240, 410, 560, 620)


def load_builder(filename, name, injected=None):
    # 只重定向模块OUT；视频模块复用已加载h，避免再次导入并指向保护目录。
    path = BASE / filename
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    nodes = []
    for node in tree.body:
        if injected and isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('spec', 'h') for t in node.targets):
            continue
        if injected and isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'spec.loader.exec_module':
            continue
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'OUT' for t in node.targets):
            node.value = ast.parse('Path(' + repr(str(OUT)) + ')', mode='eval').body
        nodes.append(node)
    tree.body = nodes
    ast.fix_missing_locations(tree)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    if injected:
        module.__dict__.update(injected)
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    assert module.OUT == OUT
    return module


h = load_builder('build_profile_walk.py', 'isolated_profile_helpers')
v = load_builder('build_video_guided_walk.py', 'isolated_video_helpers', {'h': h})
assert h.OUT == v.OUT == OUT
OLD = np.asarray(v.CHAINS['arm_near'], float)
LENGTHS = np.linalg.norm(np.diff(OLD, axis=0), axis=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    path = OUT / name
    assert path.parent.resolve() == OUT.resolve()
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def similarity():
    # 以源角色总骨长约束统一缩放；一个固定旋转使肩手方向对齐源角色，不匹配bbox。
    donor_lengths = np.linalg.norm(np.diff(DONOR_JOINTS, axis=0), axis=1)
    scale = LENGTHS.sum() / donor_lengths.sum()
    d = DONOR_JOINTS[-1] - DONOR_JOINTS[0]
    target = OLD[-1] - OLD[0]
    angle = math.atan2(target[1], target[0]) - math.atan2(d[1], d[0])
    linear = scale * np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    offset = OLD[0] - linear @ DONOR_JOINTS[0]
    mapped = DONOR_JOINTS @ linear.T + offset
    directions = np.diff(mapped, axis=0)
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    new = np.vstack([OLD[0], OLD[0] + directions[0]*LENGTHS[0], OLD[0] + directions[0]*LENGTHS[0] + directions[1]*LENGTHS[1]])
    return linear, offset, mapped, new, scale, angle


def strip_mesh(alpha, linear, offset, envelope_mask=None):
    # 轴向条带，每站5个横截面顶点，端帽也包含在同一个连通mesh中。
    # 每相邻两站的边界取该区间所有alpha像素的横向包络，并外留1.5供体像素。
    # 这保留原纹理透明凹口（包括手端分瓣），不填色，不做bbox格栅。
    yy, xx = np.where(alpha > 0)
    pixels = np.column_stack([xx+.5, yy+.5])
    axis = DONOR_JOINTS[-1] - DONOR_JOINTS[0]
    axis /= np.linalg.norm(axis)
    normal = np.array([-axis[1], axis[0]])
    origin = DONOR_JOINTS[0]
    envelope_pixels = pixels if envelope_mask is None else np.column_stack(np.where(envelope_mask)[::-1])+.5
    s = (envelope_pixels-origin) @ axis
    q = (envelope_pixels-origin) @ normal
    stations = np.linspace(s.min()-2, s.max()+2, 37)
    intervals = []
    for left, right in zip(stations[:-1], stations[1:]):
        eligible = (s >= left-1) & (s <= right+1)
        if not eligible.any():
            nearest = np.argsort(np.abs(s-(left+right)/2))[:16]
            eligible[nearest] = True
        intervals.append([float(q[eligible].min()-2), float(q[eligible].max()+2)])
    source = []
    for i, pos in enumerate(stations):
        neighbors = intervals[max(0, i-1):min(len(intervals), i+1)]
        low = min(row[0] for row in neighbors)
        high = max(row[1] for row in neighbors)
        source.extend(origin+pos*axis+x*normal for x in np.linspace(low, high, 5))
    source = np.asarray(source)
    points = source @ linear.T + offset
    triangles = []
    for row in range(len(stations)-1):
        for col in range(4):
            a = row*5+col
            triangles.extend([[a,a+5,a+6], [a,a+6,a+1]])
    triangles = np.asarray(triangles, int)
    signed = h.cross(points[triangles[:,1]]-points[triangles[:,0]], points[triangles[:,2]]-points[triangles[:,0]])
    triangles[signed < 0] = triangles[signed < 0][:,[0,2,1]]
    uv = source / np.array([alpha.shape[1], alpha.shape[0]])
    # 直接在全部alpha像素中心做几何三角覆盖；不是四舍五入多边形近似。
    covered = np.zeros(len(pixels), bool)
    max_alpha = []
    for tri in triangles:
        a,b,c = source[tri]
        selected = np.all(pixels >= np.minimum.reduce([a,b,c])-1e-8,axis=1) & np.all(pixels <= np.maximum.reduce([a,b,c])+1e-8,axis=1)
        indices = np.flatnonzero(selected)
        if not len(indices):
            max_alpha.append(0)
            continue
        coords = (pixels[indices]-a) @ np.linalg.inv(np.column_stack([b-a,c-a])).T
        inside = (coords.min(axis=1)>=-1e-8) & (coords.sum(axis=1)<=1+1e-8)
        owned = indices[inside]
        covered[owned] = True
        max_alpha.append(int(alpha[yy[owned],xx[owned]].max()) if len(owned) else 0)
    edges = np.sort(np.vstack([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return {'points':points, 'source':source, 'uv':uv, 'triangles':triangles, 'triangleMaxAlpha':np.asarray(max_alpha), 'boundaryEdges':unique[counts==1],
            'coverage':{'alphaThreshold':'>0', 'alphaPixelCount':len(pixels), 'omittedAlphaPixels':int((~covered).sum()),
                        'omittedAlphaSum':int(alpha[yy[~covered],xx[~covered]].sum()),
                        'alphaGt8PixelCount':int((alpha[yy,xx]>8).sum()),
                        'omittedAlphaGt8Pixels':int(((~covered)&(alpha[yy,xx]>8)).sum()),
                        'omittedAlphaMaximum':int(alpha[yy[~covered],xx[~covered]].max()) if (~covered).any() else 0,
                        'method':'全部供体alpha像素中心逐三角重心覆盖；透明凹口仅靠UV原alpha保留',
                        'sections':len(stations), 'verticesPerSection':5, 'nonRectangularBboxGrid':True}}


def make_bones(joints):
    a,b,c = map(h.yup,joints)
    upper = math.degrees(math.atan2(*(b-a)[::-1]))
    lower = math.degrees(math.atan2(*(c-b)[::-1]))
    d = a-h.yup(h.PIVOTS['body'])
    return [{'name':'root','x':390.,'y':236.}, {'name':'body','parent':'root'},
            {'name':'arm_near_upper','parent':'body','x':float(d[0]),'y':float(d[1]),'rotation':upper,'length':float(LENGTHS[0])},
            {'name':'arm_near_lower','parent':'arm_near_upper','x':float(LENGTHS[0]),'rotation':lower-upper,'length':float(LENGTHS[1])}]


def skin_weights(points, joints):
    # 只有upper/lower两个影响，不引入body根权重、deform或权重优化。
    arcs, distances = [], []
    for i in range(2):
        a,b = joints[i:i+2]
        t = np.clip((points-a)@(b-a)/np.dot(b-a,b-a),0,1)
        distances.append(np.linalg.norm(points-(a+t[:,None]*(b-a)),axis=1))
        arcs.append(t*LENGTHS[i]+(LENGTHS[0] if i else 0))
    nearest = np.argmin(np.stack(distances,axis=1),axis=1)
    arc = np.stack(arcs,axis=1)[np.arange(len(points)),nearest]
    blend = np.clip((arc-LENGTHS[0]+18)/36,0,1)
    blend = blend*blend*(3-2*blend)
    return np.column_stack([1-blend,blend])


def make_case(name, joints, data, reference, static_weights=None):
    bones = make_bones(joints)
    skeleton = {'bones':bones,'slots':[{'name':'arm_near','bone':'arm_near_upper','attachment':'arm_near'}],
                'skins':[{'name':'default','attachments':{}}], 'animations':{}}
    bind = h.solve(skeleton,'setup',0)
    design = {**data, 'chain':['arm_near_upper','arm_near_lower'],
              'weights':skin_weights(data['points'],joints) if static_weights is None else static_weights}
    attachment = v.encode_mesh('arm_near',{'width':1024,'height':1024},design,bind,bones)
    skeleton['skins'][0]['attachments']['arm_near'] = {'arm_near':attachment}
    channels = copy.deepcopy(reference['animations']['walk']['bones'])
    # 原视频绝对骨角逐键保持不变。仅减去不同setup角，不能改角度幅度或IK分支。
    ref_bones = {b['name']:b for b in reference['bones']}
    for b in bones[2:]:
        shift = ref_bones[b['name']]['rotation']-b['rotation']
        for key in channels[b['name']]['rotate']:
            key['value'] += shift
    channels = {n:channels[n] for n in ('body','arm_near_upper','arm_near_lower')}
    skeleton['animations'] = {'setup':{'bones':{}},'walk':{'bones':channels}}
    filename = name+'_mesh_test.json'
    save(filename, {'purpose':'仅隔离weighted mesh CPU测试数据，不是运行包', **FLAGS, 'skeleton':skeleton,
                    'manualSetupChain':joints.tolist(), 'points':data['points'].tolist(), 'sourceUV':data['uv'].tolist(),
                    'staticTwoBoneWeights':design['weights'].tolist(), 'triangles':data['triangles'].tolist()})
    # 从磁盘JSON重新解码weighted顶点和UV，所有检查与贴图均使用解码数据。
    disk = json.loads((OUT/filename).read_text(encoding='utf-8'))
    skeleton = disk['skeleton']
    mesh = h.decode_meshes(skeleton, {'arm_near':{'x':0,'y':0,'width':1024,'height':1024}})['arm_near']
    local = np.zeros((len(data['points']),2,3))
    weights = np.zeros((len(data['points']),2))
    names = ['arm_near_upper','arm_near_lower']
    for i,row in enumerate(mesh['influences']):
        for bone,p,w in row:
            j = names.index(bone); local[i,j] = p; weights[i,j] = w
    tri = mesh['triangles']; base = mesh['bind'][tri]
    inverse = np.linalg.inv(np.stack([base[:,1]-base[:,0],base[:,2]-base[:,0]],axis=-1))
    material = h.material_binding(mesh,h.yup(MAPPED[-1]))
    return {'name':name,'joints':joints,'skeleton':skeleton,'mesh':mesh,'local':local,'weights':weights,
            'inverse':inverse,'material':material,'triangleMaxAlpha':data['triangleMaxAlpha'],
            'bindError':float(np.linalg.norm(mesh['bind']-h.screen(data['points']),axis=1).max())}


def sample_case(case,t):
    world = h.solve(case['skeleton'],'walk',float(t))
    matrices = np.stack([world[n] for n in ('arm_near_upper','arm_near_lower')])
    dst = np.einsum('bij,vbj->vbi',matrices,case['local'])[:,:,:2]
    dst = (dst*case['weights'][:,:,None]).sum(axis=1)
    tri = case['mesh']['triangles']; p = dst[tri]
    edges = np.stack([p[:,1]-p[:,0],p[:,2]-p[:,0]],axis=-1)
    jac = edges @ case['inverse']
    ratio = np.linalg.det(jac)
    singular = np.linalg.svd(jac,compute_uv=False)
    visible = case['triangleMaxAlpha'] > 8
    binding,bary = case['material']
    hand = h.screen(bary@dst[binding])
    phase = min(float(t)*24,16.)
    i = min(int(phase),15); u = phase-i
    target = v.mapped(np.asarray(v.POINTS['arm_near'][i])*(1-u)+np.asarray(v.POINTS['arm_near'][i+1])*u)
    lower = world['arm_near_lower']
    endpoint = h.screen((lower@np.array([LENGTHS[1],0,1]))[:2])
    row = {'time':float(t),'flips':int((ratio<0).sum()),'collapse':int((np.abs(ratio)<1e-5).sum()),
           'minAreaRatio':float(ratio.min()),'maxAreaRatio':float(ratio.max()),
           'texturedFlips':int(((ratio<0)&visible).sum()),'texturedCollapse':int(((np.abs(ratio)<1e-5)&visible).sum()),
           'texturedMinAreaRatio':float(ratio[visible].min()),'texturedMinSingularValue':float(singular[visible].min()),
           'texturedMaxSingularValue':float(singular[visible].max()),
           'minSingularValue':float(singular.min()),'maxSingularValue':float(singular.max()),
           'mappedTarget':target.tolist(),'materialHand':hand.tolist(),'materialResidualPx':float(np.linalg.norm(hand-target)),
           'boneEndpoint':endpoint.tolist(),'boneEndpointResidualPx':float(np.linalg.norm(endpoint-target))}
    return row,dst


def evaluate(case,count):
    rows = [sample_case(case,t)[0] for t in np.linspace(0,v.DURATION,count)]
    worst = min(rows,key=lambda r:r['minAreaRatio'])
    return {'sampleCount':count,'flipsTriangleSamples':sum(r['flips'] for r in rows),'collapseTriangleSamples':sum(r['collapse'] for r in rows),
            'samplesWithFlips':sum(r['flips']>0 for r in rows),'minAreaRatio':worst['minAreaRatio'],
            'texturedFlipsTriangleSamples':sum(r['texturedFlips'] for r in rows),
            'texturedCollapseTriangleSamples':sum(r['texturedCollapse'] for r in rows),
            'texturedMinAreaRatio':min(r['texturedMinAreaRatio'] for r in rows),
            'texturedMinSingularValue':min(r['texturedMinSingularValue'] for r in rows),
            'texturedMaxSingularValue':max(r['texturedMaxSingularValue'] for r in rows),
            'maxAreaRatio':max(r['maxAreaRatio'] for r in rows),'minSingularValue':min(r['minSingularValue'] for r in rows),
            'maxSingularValue':max(r['maxSingularValue'] for r in rows),'worstAreaTime':worst['time'],
            'maxMaterialResidualPx':max(r['materialResidualPx'] for r in rows),
            'rmsMaterialResidualPx':float(np.sqrt(np.mean([r['materialResidualPx']**2 for r in rows]))),'rows':rows}


def assembly(arm,world,parts,order):
    # 其余六件只随既有body平移；移除旧近臂，避免整张source叠加造成双臂伪装。
    canvas = Image.new('RGBA',(768,768))
    dx,dy = world['body'][:2,2]-h.yup(h.PIVOTS['body'])
    for n in order:
        if n == 'arm_near':
            layer = arm
        else:
            layer = Image.new('RGBA',(768,768))
            p,im = parts[n]
            layer.paste(im,(p['bbox'][0],p['bbox'][1]))
            layer = Image.fromarray(cv2.warpAffine(np.asarray(layer),np.float32([[1,0,dx],[0,1,-dy]]),(768,768)))
        canvas.alpha_composite(layer)
    return canvas


def render_case(case,t,texture,data,parts,order,setup=False):
    world = h.solve(case['skeleton'],'setup' if setup else 'walk',float(t))
    raster,stats = v.safe_render_mesh(texture,case['mesh'],world)
    arm = h.image_from_premul(raster)
    image = assembly(arm,world,parts,order)
    overlay = image.copy(); d = ImageDraw.Draw(overlay)
    points = h.screen(h.vertices_world(case['mesh'],world))
    for tri in case['mesh']['triangles']:
        path = [tuple(p) for p in points[tri]]
        d.line(path+[path[0]],fill=(30,110,210,125),width=1)
    for edge in data['boundaryEdges']:
        d.line([tuple(p) for p in points[edge]],fill=(12,130,75,255),width=2)
    upper,lower = world['arm_near_upper'],world['arm_near_lower']
    chain = [h.screen(upper[:2,2]),h.screen(lower[:2,2]),h.screen((lower@np.array([LENGTHS[1],0,1]))[:2])]
    d.line([tuple(p) for p in chain],fill=(220,70,20,255),width=2)
    if not setup:
        p = sample_case(case,t)[0]['mappedTarget']; x,y = p
        d.ellipse((x-3,y-3,x+3,y+3),outline=(180,20,160,255),width=2)
    return arm,image,overlay,stats


def tile(image,size,box=None):
    if box:
        image = image.crop(box)
    bg = Image.new('RGBA',image.size,'#f5f5f1'); bg.alpha_composite(image.convert('RGBA'))
    return bg.convert('RGB').resize(size,Image.Resampling.LANCZOS)


def main():
    assert BASE.is_dir() and RIG.is_dir() and REF.is_dir()
    OUT.mkdir(exist_ok=True)
    marker = OUT/'checks.json'
    if any(OUT.iterdir()):
        assert marker.is_file() and json.loads(marker.read_text(encoding='utf-8')).get('ownerScript') == Path(__file__).name, '拒绝覆盖未知隔离输出'
    # 明确保护所有stable_parts、V2与所有source map，以及本次读取的源证据。
    protected = set()
    for directory in list(RIG.glob('stable_parts*'))+[RIG/'video_guided_walk_v2']:
        protected.update(p for p in directory.rglob('*') if p.is_file())
    protected.update(p for p in BASE.rglob('*') if p.is_file() and OUT not in p.parents and ('source' in p.name.lower() and p.suffix.lower() in ('.js','.map')))
    inputs = [DONOR,SOURCE,BASE/'build_profile_walk.py',BASE/'build_video_guided_walk.py',REF/'sources.json',RIG/'source.mp4']
    inputs += [REF/f'source_{i:03d}.png' for i in range(68,85)]
    protected.update(inputs)
    before = {p:sha(p) for p in sorted(protected)}
    donor = Image.open(DONOR).convert('RGBA'); assert donor.size == (1024,1024)
    alpha = np.asarray(donor)[:,:,3]
    linear,offset,mapped,new,scale,angle = similarity()
    global MAPPED
    MAPPED = mapped
    data = strip_mesh(alpha,linear,offset)
    # 直接调用纯motion函数；绝不调用build/main/package/write_source_map。
    reference = {'bones':h.make_bones()}
    inference = v.make_motion(reference)['arm_near']
    cases = [make_case('old_setup',OLD,data,reference), make_case('donor_setup',new,data,reference)]
    manifest = json.loads((STABLE/'manifest.json').read_text(encoding='utf-8'))
    assert sha(SOURCE) == manifest['sourceImage']['sha256']
    parts = {}
    for p in manifest['parts']:
        path = STABLE/p['file']; assert sha(path) == p['sha256']
        parts[p['id']] = (p,Image.open(path).convert('RGBA'))
    sources = json.loads((REF/'sources.json').read_text(encoding='utf-8'))
    assert sha(RIG/'source.mp4') == sources['sourceVideoSha256']
    cap = cv2.VideoCapture(str(RIG/'source.mp4')); assert cap.isOpened()
    decoded = []
    for i in range(85):
        ok,bgr = cap.read(); assert ok
        if i>=68:
            path = REF/f'source_{i:03d}.png'
            assert np.array_equal(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),np.asarray(Image.open(path).convert('RGB')))
            decoded.append({'frame':i,'sha256':sha(path),'decodedPixelsExact':True})
    cap.release()
    texture = h.premul(donor)
    results = {}
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
    for case in cases:
        result = {str(n):evaluate(case,n) for n in (17,193,1537)}
        results[case['name']] = result
        for count,values in result.items():
            save(case['name']+'_samples_'+count+'.json',values)
        contact = Image.new('RGB',(1500,2020),'#e9eef3'); draw = ImageDraw.Draw(contact)
        draw.text((15,10),case['name']+' / 视频+单臂实际组装+mesh绿轮廓 / 红骨链 紫目标 / 未验收',font=font,fill='#243b50')
        raster_stats = []
        for i in range(17):
            t = i/24
            arm,image,overlay,stats = render_case(case,t,texture,data,parts,manifest['assemblyLayerOrder'])
            stem = case['name']+f'_f{68+i:03d}'
            arm.save(OUT/(stem+'_arm.png')); image.save(OUT/(stem+'_assembly.png')); overlay.save(OUT/(stem+'_mesh.png'))
            raster_stats.append({'frame':68+i,**stats})
            x,y = (i%6)*250,(i//6)*650+45
            ref = Image.open(REF/f'source_{68+i:03d}.png').convert('RGBA')
            contact.paste(tile(ref,(240,175),(320,275,560,450)),(x+5,y))
            contact.paste(tile(image,(240,240)),(x+5,y+180))
            contact.paste(tile(overlay,(240,158),CROP),(x+5,y+425))
            row = result['17']['rows'][i]
            draw.text((x+7,y+588),f'f{68+i} flip={row["flips"]} minA={row["minAreaRatio"]:.3f}',font=font,fill='#27394a')
            draw.text((x+7,y+611),f'手材料残差={row["materialResidualPx"]:.2f}px',font=font,fill='#7b4226')
        contact.save(OUT/(case['name']+'_contact.png'))
        _,worst_image,worst_mesh,worst_raster = render_case(case,result['1537']['worstAreaTime'],texture,data,parts,manifest['assemblyLayerOrder'])
        worst_image.save(OUT/(case['name']+'_worst_assembly.png')); worst_mesh.save(OUT/(case['name']+'_worst_mesh.png'))
        _,setup_image,setup_mesh,_ = render_case(case,0,texture,data,parts,manifest['assemblyLayerOrder'],setup=True)
        setup_image.save(OUT/(case['name']+'_setup_assembly.png')); setup_mesh.save(OUT/(case['name']+'_setup_mesh.png'))
        case['rasterStats'] = raster_stats
        case['worstRaster'] = worst_raster
    sheet = Image.new('RGB',(1600,1420),'#e9eef3'); d = ImageDraw.Draw(sheet)
    d.text((15,10),'V8 隔离试验：同纹理/同拓扑/同视频绝对骨角，仅比较旧setup与供体语义setup',font=font,fill='#19354b')
    sheet.paste(tile(donor,(350,350)),(10,45))
    annot = donor.copy(); ad = ImageDraw.Draw(annot)
    ad.line([tuple(p) for p in DONOR_JOINTS],fill='#1473e6',width=5)
    for label,p in zip(('肩：人工推断','肘：人工推断','手：人工推断'),DONOR_JOINTS):
        ad.text(tuple(p),label,font=font,fill='#0c499e')
    sheet.paste(tile(annot,(350,350)),(390,45))
    sheet.paste(tile(Image.open(SOURCE).convert('RGBA'),(350,350)),(780,45))
    for i,case in enumerate(cases):
        image = Image.open(OUT/(case['name']+'_setup_mesh.png')).convert('RGBA')
        sheet.paste(tile(image,(350,350)),(20+i*400,440))
        d.text((20+i*400,405),case['name']+' setup实际组装',font=font,fill='#19354b')
    for col,frame in enumerate((68,72,76,80)):
        x=col*400
        for row,case in enumerate(cases):
            im = Image.open(OUT/(case['name']+f'_f{frame:03d}_mesh.png')).convert('RGBA')
            sheet.paste(tile(im,(390,256),CROP),(x+5,820+row*285))
            d.text((x+10,795+row*285),f'{case["name"]} f{frame}',font=font,fill='#19354b')
    d.text((15,1380),'肩根露缝、AI手端分瓣及体积造型待人工审阅；数值结果不能自动通过；全部批准标志false。',font=font,fill='#93442a')
    sheet.save(OUT/'review.png')
    pixels = np.column_stack(np.where(alpha>0)[::-1])+.5
    transformed = pixels@linear.T+offset
    axis = (OLD[-1]-OLD[0])/np.linalg.norm(OLD[-1]-OLD[0]); normal=np.array([-axis[1],axis[0]])
    old_im = np.asarray(parts['arm_near'][1])[:,:,3]
    ys,xs = np.where(old_im>0); old_pixels=np.column_stack([xs+.5,ys+.5])+parts['arm_near'][0]['bbox'][:2]
    summaries = {case['name']:{count:{k:value for k,value in result.items() if k!='rows'} for count,result in results[case['name']].items()} for case in cases}
    def opaque_extent(threshold):
        ys,xs = np.where(alpha>threshold)
        p=(np.column_stack([xs+.5,ys+.5])@linear.T+offset)
        return {'alphaThreshold':threshold,'pixelCount':len(p),'aabbPx':np.ptp(p,axis=0).tolist(),
                'axialLengthPx':float(np.ptp(p@axis)),'transverseWidthPx':float(np.ptp(p@normal))}
    num_labels,labels,component_stats,centroids=cv2.connectedComponentsWithStats((alpha>0).astype(np.uint8))
    largest=1+int(component_stats[1:,cv2.CC_STAT_AREA].argmax())
    orphan=(labels>0)&(labels!=largest)
    checks = {'schemaVersion':1,'ownerScript':Path(__file__).name,**FLAGS,'status':'isolated_test_completed_not_accepted',
              'scriptSha256':sha(__file__),
              'meshCounts':{'vertices':len(data['points']),'triangles':len(data['triangles']),
                            'texturedTrianglesAlphaGt8':int((data['triangleMaxAlpha']>8).sum())},
              'donorAlphaComponents':{'nonzeroComponentCount':num_labels-1,'orphanPixelsOutsideLargestComponent':int(orphan.sum()),
                                       'orphanMaximumAlpha':int(alpha[orphan].max()),'alphaNotCleanedOrDiscarded':True},
              'visibleProportions':[opaque_extent(8),opaque_extent(200)],
              'runtimePackageWritten':False,'builderBuildCalled':False,'builderOutRedirectedBeforeImport':True,
              'singleArmMeshPerCase':True,'limbBoneCount':2,'bodyHasNoVertexWeights':True,'deformUsed':False,'attachmentSwitchUsed':False,
              'boneLengthsOldPx':LENGTHS.tolist(),'boneLengthsNewPx':np.linalg.norm(np.diff(new,axis=0),axis=1).tolist(),
              'boneLengthChangesPx':(np.linalg.norm(np.diff(new,axis=0),axis=1)-LENGTHS).tolist(),
              'motionContract':'逐键复用build_video_guided_walk.make_motion绝对骨角、原分支、原81–84闭环修正；只补偿setup旋转基准；不重新逐插值点做IK',
              'motionAmplitudeReduced':False,'sameAbsoluteBoneAngleMaxWorldDelta':max(float(np.abs(h.solve(cases[0]['skeleton'],'walk',t)[n]-h.solve(cases[1]['skeleton'],'walk',t)[n]).max()) for t in np.linspace(0,v.DURATION,193) for n in ('arm_near_upper','arm_near_lower')),
              'manualSemantics':{'method':'ViewImage后人工推断，不是自动关节提取或直接观测','donorPixels':DONOR_JOINTS.tolist(),'mappedDonorPixels':mapped.tolist(),'newConstrainedChain':new.tolist(),
                                 'mappedDonorElbowVsConstrainedElbowPx':float(np.linalg.norm(mapped[1]-new[1])),
                                 'mappedDonorHandVsConstrainedEndPx':float(np.linalg.norm(mapped[2]-new[2]))},
              'mapping':{'uniformScale':scale,'rotationDegrees':math.degrees(angle),'linear':linear.tolist(),'offset':offset.tolist(),
                         'linearSingularValues':np.linalg.svd(linear,compute_uv=False).tolist(),'nonuniformStretch':False},
              'proportions':{'donorMappedAlphaAabbPx':np.ptp(transformed,axis=0).tolist(),'sourceArmAlphaAabbPx':np.ptp(old_pixels,axis=0).tolist(),
                             'donorMappedAxialLengthPx':float(np.ptp(transformed@axis)),'sourceArmAxialLengthPx':float(np.ptp(old_pixels@axis)),
                             'donorMappedTransverseWidthPx':float(np.ptp(transformed@normal)),'sourceArmTransverseWidthPx':float(np.ptp(old_pixels@normal))},
              'meshCoverage':data['coverage'],'uvMeshConsistencyMaxErrorDonorPx':float(np.abs(data['uv']*[1024,1024]-data['source']).max()),
              'weightedSetupReconstruction':{case['name']:case['bindError'] for case in cases},'geometry':summaries,
              'raster':{case['name']:case['rasterStats'] for case in cases},
              'worstRaster':{case['name']:case['worstRaster'] for case in cases},
              'shoulderRootGap':{'status':'人工待审','gapFreeApproved':False,'noAutomaticGapFreeClaim':True},
              'visualReview':{'status':'待查看实际输出','inputV8InspectedWith':'ViewImage','handEndLobed':True,'shapeAloneIsNotPass':True},
              'limitations':['只测试近臂，其余六件静态纹理随body平移，不测试全身视频动作。','条带包络允许透明余量；供体手端分瓣原alpha保留，没有修形。',
                             '只有CPU weighted mesh导出解算，不是Spine官方运行时验收。','mapped targets本身为既有人工近似；肩肘手全部是人工推断。'],
              'videoEvidence':decoded,'sourceInputs':[{'file':p.relative_to(BASE).as_posix(),'sha256':before[p]} for p in inputs],
              'boneInference':inference,'protectedFileCount':len(before),'protectedFilesUnchanged':all(sha(p)==digest for p,digest in before.items()),
              'protectedHashes':{p.relative_to(BASE).as_posix():digest for p,digest in before.items()}}
    checks['numericalGeometryPassed'] = all(result['1537']['flipsTriangleSamples']==0 and result['1537']['collapseTriangleSamples']==0 for result in results.values())
    checks['failureReasons'] = []
    for case in cases:
        dense=results[case['name']]['1537']
        if dense['flipsTriangleSamples'] or dense['collapseTriangleSamples']:
            checks['failureReasons'].append(f'{case["name"]}:1537采样翻转{dense["flipsTriangleSamples"]}，塌缩{dense["collapseTriangleSamples"]}，最小面积比{dense["minAreaRatio"]:.8f}')
        if dense['minSingularValue']<.35:
            checks['failureReasons'].append(f'{case["name"]}:最小奇异值{dense["minSingularValue"]:.8f}，明显压缩风险')
    checks['failureReasons'] += ['肩根露缝未获人工无缝批准，AI供体手端分瓣尚未解决。','数值合格也不提升候选；prototypeAccepted=false、productionApproved=false。']
    assert checks['protectedFilesUnchanged'] and checks['sameAbsoluteBoneAngleMaxWorldDelta']<1e-8
    assert max(checks['weightedSetupReconstruction'].values())<1e-8
    assert data['coverage']['omittedAlphaPixels']==0
    assert all(np.allclose(np.linalg.norm(np.diff(case['joints'],axis=0),axis=1),LENGTHS) for case in cases)
    review_path=OUT/'visual_review_record.json'
    if review_path.is_file():
        actual_review=json.loads(review_path.read_text(encoding='utf-8'))
        if all(sha(OUT/name)==digest for name,digest in actual_review['inspectedFileHashes'].items()):
            checks['visualReview']=actual_review
    save('checks.json',checks)
    save('candidate_review_handoff.json',{'scope':'主代理同步V3候选状态用；不修改V3主文件或source map',**FLAGS,'candidate':'arm_near_video_setup_v8',
         'status':'actual_isolated_mesh_test_not_accepted','review':'review.png','checks':'checks.json','summary':summaries,
         'shoulderRootGap':'人工待审','runtimePackageWritten':False,'failureReasons':checks['failureReasons']})
    print(json.dumps({'output':str(OUT),'geometry':summaries,'omittedAlphaPixels':data['coverage']['omittedAlphaPixels'],
                      'protectedFilesUnchanged':checks['protectedFilesUnchanged'],**FLAGS},ensure_ascii=False))


def record_visible_review():
    # 仅在会话中实际ViewImage查看下列输出后显式运行；普通测试不会自行声称已看图。
    inspected=['review.png','old_setup_contact.png','donor_setup_contact.png','donor_setup_worst_assembly.png']
    review={'status':'actually_viewed_failed_not_accepted','inspectedWith':'ViewImage',**FLAGS,
            'inspectedFileHashes':{name:sha(OUT/name) for name in inspected},
            'shoulderRootGap':'人工待审，未批准无露缝',
            'observations':['已实际查看旧新setup完整17帧contact、总览与供体setup最坏帧无网格线组装。',
                            'v8供体是右上肩/左下手的近直长形，手端双瓣仍可见；不是旧L形供体。',
                            '两套setup的胸前收臂形变与视频轮廓不一致；供体方向setup没有消除实纹理三角翻转。',
                            'mesh绿色边线的尖翼包括为保留alpha=1孤点而增加的透明包络，不能全部当作可见皮肤尖刺；无网格组装另行核对。',
                            '最坏帧无网格组装中，近臂下方原静态肩腋隐藏域不足，靠腰裤口处有透明缺口；不作肩根无缝通过。',
                            '骨长保持原约束，未靠加长或缩小视频动作通过；手端分瓣和隐藏肩腋结构仍待美术处理。'],
            'passed':False,'shapeAloneIsNotPass':True}
    checks=json.loads((OUT/'checks.json').read_text(encoding='utf-8'))
    assert sha(__file__)==checks['scriptSha256'], '脚本修改后须先重跑测试，不能登记旧数据'
    assert all(sha(BASE/name)==digest for name,digest in checks['protectedHashes'].items())
    save('visual_review_record.json',review)
    checks['visualReview']=review
    checks['status']='isolated_test_actually_reviewed_not_accepted'
    checks.update(FLAGS)
    save('checks.json',checks)
    handoff=json.loads((OUT/'candidate_review_handoff.json').read_text(encoding='utf-8'))
    handoff.update({'visualReview':review,'status':checks['status'],**FLAGS})
    save('candidate_review_handoff.json',handoff)
    print(json.dumps({'status':checks['status'],'protectedFilesUnchanged':True,**FLAGS},ensure_ascii=False))


CONTINUOUS = 'continuous_donor_setup'
HINGE_SPANS = (24, 36, 52)


def continuous_weights(points, shoulder, axis, elbow_s, span):
    # 整个平面共用单值轴向距离；同截面恒定权重，完全不选择最近骨段。
    s = (points-shoulder) @ axis
    u = np.clip((s-elbow_s)/span+.5, 0, 1)
    lower = u*u*(3-2*u)
    return np.column_stack([1-lower, lower])


def bounded_main():
    assert OUT.is_dir() and (OUT/'checks.json').is_file()
    baseline = json.loads((OUT/'checks.json').read_text(encoding='utf-8'))
    historical = {p.name:sha(p) for p in OUT.iterdir() if p.is_file() and not p.name.startswith(CONTINUOUS)}
    protected = {BASE/name:digest for name,digest in baseline['protectedHashes'].items()}
    for directory in list(RIG.glob('stable_parts*'))+[RIG/'video_guided_walk_v2']:
        for p in directory.rglob('*'):
            if p.is_file():
                protected.setdefault(p,sha(p))
    for p in BASE.rglob('*'):
        if p.is_file() and OUT not in p.parents and 'source' in p.name.lower() and p.suffix.lower() in ('.js','.map'):
            protected.setdefault(p,sha(p))
    assert all(sha(p)==digest for p,digest in protected.items())
    donor = Image.open(DONOR).convert('RGBA')
    alpha = np.asarray(donor)[:,:,3]
    n,labels,stats,_ = cv2.connectedComponentsWithStats((alpha>8).astype(np.uint8),connectivity=8)
    largest = 1+int(stats[1:,cv2.CC_STAT_AREA].argmax())
    core = labels==largest
    # 只把主体周围固定2供体像素内的非零alpha用于包络，不改原纹理。
    distance = cv2.distanceTransform((~core).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    envelope = core | ((alpha>0)&(distance<=2.0))
    linear,offset,mapped,new,scale,angle = similarity()
    global MAPPED
    MAPPED = mapped
    data = strip_mesh(alpha,linear,offset,envelope_mask=envelope)
    assert data['coverage']['omittedAlphaGt8Pixels']==0
    # 肩手同一单位轴、肘投影为混合中心；s和span均使用source像素。
    axis = mapped[-1]-mapped[0]; axis /= np.linalg.norm(axis)
    elbow_s = float((mapped[1]-mapped[0])@axis)
    s = (data['points']-mapped[0])@axis
    reference = {'bones':h.make_bones()}
    v.make_motion(reference)
    baseline_skeleton = json.loads((OUT/'donor_setup_mesh_test.json').read_text(encoding='utf-8'))['skeleton']
    manifest = json.loads((STABLE/'manifest.json').read_text(encoding='utf-8'))
    parts = {p['id']:(p,Image.open(STABLE/p['file']).convert('RGBA')) for p in manifest['parts']}
    texture = h.premul(donor)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
    candidates = {}
    sheet = Image.new('RGB',(1500,1150),'#e9eef3'); sd = ImageDraw.Draw(sheet)
    sd.text((15,10),'连续轴向权重 / 固定三档hingeSpan / 仅诊断，全部批准false',font=font,fill='#19354b')
    for column,span in enumerate(HINGE_SPANS):
        name = f'{CONTINUOUS}_hinge{span}'
        weights = continuous_weights(data['points'],mapped[0],axis,elbow_s,span)
        case = make_case(name,new,data,reference,static_weights=weights)
        assert np.allclose(weights.sum(axis=1),1) and np.all((weights>=0)&(weights<=1))
        section_error = float(np.ptp(weights[:,1].reshape(37,5),axis=1).max())
        shifted = continuous_weights(data['points']+37*np.array([-axis[1],axis[0]]),mapped[0],axis,elbow_s,span)
        transverse_error = float(np.abs(shifted-weights).max())
        world_delta = max(float(np.abs(h.solve(case['skeleton'],'walk',t)[bone]-h.solve(baseline_skeleton,'walk',t)[bone]).max())
                          for t in np.linspace(0,v.DURATION,1537) for bone in ('arm_near_upper','arm_near_lower'))
        assert world_delta<1e-8 and section_error<1e-12 and transverse_error<1e-12 and case['bindError']<1e-8
        results = {}
        for count in (17,193,1537):
            result = evaluate(case,count)
            result.update({'candidate':CONTINUOUS,'variant':name,'hingeSpanSourcePx':span,**FLAGS})
            result['maxBoneEndpointResidualPx'] = max(row['boneEndpointResidualPx'] for row in result['rows'])
            result['rmsBoneEndpointResidualPx'] = float(np.sqrt(np.mean([row['boneEndpointResidualPx']**2 for row in result['rows']])))
            result['numericalGeometryPassed'] = result['flipsTriangleSamples']==0 and result['collapseTriangleSamples']==0
            save(f'{name}_samples_{count}.json',result)
            results[str(count)] = {k:value for k,value in result.items() if k!='rows'}
        contact = Image.new('RGB',(1500,2020),'#e9eef3'); draw = ImageDraw.Draw(contact)
        draw.text((15,10),f'{name} / 视频+无网格组装+mesh / 红骨链 紫目标 / 仅诊断，未验收',font=font,fill='#243b50')
        raster = []
        for i in range(17):
            arm,image,overlay,raster_stats = render_case(case,i/24,texture,data,parts,manifest['assemblyLayerOrder'])
            stem = f'{name}_f{68+i:03d}'
            arm.save(OUT/(stem+'_arm.png')); image.save(OUT/(stem+'_assembly.png')); overlay.save(OUT/(stem+'_mesh.png'))
            raster.append({'frame':68+i,**raster_stats})
            x,y = (i%6)*250,(i//6)*650+45
            ref = Image.open(REF/f'source_{68+i:03d}.png').convert('RGBA')
            contact.paste(tile(ref,(240,175),(320,275,560,450)),(x+5,y))
            contact.paste(tile(image,(240,240)),(x+5,y+180))
            contact.paste(tile(overlay,(240,158),CROP),(x+5,y+425))
            row = sample_case(case,i/24)[0]
            draw.text((x+7,y+588),f'f{68+i} 实纹理flip={row["texturedFlips"]} A={row["minAreaRatio"]:.3f}',font=font,fill='#27394a')
            draw.text((x+7,y+611),f'手材料残差={row["materialResidualPx"]:.2f}px',font=font,fill='#7b4226')
        contact.save(OUT/(name+'_contact.png'))
        _,setup_image,setup_mesh,_ = render_case(case,0,texture,data,parts,manifest['assemblyLayerOrder'],setup=True)
        setup_image.save(OUT/(name+'_setup_assembly.png')); setup_mesh.save(OUT/(name+'_setup_mesh.png'))
        worst_t = results['1537']['worstAreaTime']
        _,worst_image,worst_mesh,worst_stats = render_case(case,worst_t,texture,data,parts,manifest['assemblyLayerOrder'])
        worst_image.save(OUT/(name+'_worst_assembly.png')); worst_mesh.save(OUT/(name+'_worst_mesh.png'))
        row,dst = sample_case(case,worst_t)
        p = dst[case['mesh']['triangles']]
        jac = np.stack([p[:,1]-p[:,0],p[:,2]-p[:,0]],axis=-1)@case['inverse']
        ratios = np.linalg.det(jac)
        visible_indices = np.flatnonzero(data['triangleMaxAlpha']>8)
        witness_index = int(visible_indices[np.argmin(ratios[visible_indices])])
        diagnostic = {'candidate':CONTINUOUS,'variant':name,'hingeSpanSourcePx':span,**FLAGS,
                      'geometry':results,'numericalGeometryPassed':all(r['numericalGeometryPassed'] for r in results.values()),
                      'sameAbsoluteBoneAngleMaxWorldDelta':world_delta,'weightedSetupReconstructionMaxErrorPx':case['bindError'],
                      'weightContinuity':{'nearestSegmentUsed':False,'sameSectionMaxWeightRange':section_error,
                                          'transverseShift37PxMaxWeightDelta':transverse_error,
                                          'analyticMaxWeightDerivativePerSourcePx':1.5/span},
                      'failureWitness':{'time':worst_t,'texturedTriangleIndex':witness_index,
                                        'minTexturedAreaRatio':float(ratios[witness_index]),
                                        'triangleIndices':case['mesh']['triangles'][witness_index].tolist(),
                                        'flipsAtTime':row['flips'],'texturedFlipsAtTime':row['texturedFlips']},
                      'raster':raster,'worstRaster':worst_stats}
        save(name+'_checks.json',diagnostic)
        candidates[name] = diagnostic
        x = column*500
        sd.text((x+12,45),f'hingeSpan={span}px / 实纹理翻转={results["1537"]["texturedFlipsTriangleSamples"]}',font=font,fill='#19354b')
        sheet.paste(tile(setup_mesh,(475,310),CROP),(x+10,80))
        sheet.paste(tile(worst_mesh,(475,310),CROP),(x+10,410))
        sheet.paste(tile(worst_image,(350,350)),(x+65,755))
    sheet.save(OUT/(CONTINUOUS+'_review.png'))
    selected = min(candidates,key=lambda name:candidates[name]['geometry']['1537']['texturedFlipsTriangleSamples'])
    historical_unchanged = all(sha(OUT/name)==digest for name,digest in historical.items())
    protected_unchanged = all(sha(p)==digest for p,digest in protected.items())
    assert historical_unchanged and protected_unchanged
    assert np.allclose(np.linalg.norm(np.diff(new,axis=0),axis=1),LENGTHS)
    checks = {'schemaVersion':1,'ownerScript':Path(__file__).name,'scriptSha256':sha(__file__),
              'candidate':CONTINUOUS,'status':'bounded_test_completed_pending_visual_review',**FLAGS,
              'boundedPlan':{'hingeSpansSourcePx':list(HINGE_SPANS),'candidateCount':3,'sampleCounts':[17,193,1537],
                             'fixedBeforeEvaluation':True,'optimizationUsed':False,'parameterSearchExtended':False},
              'envelope':{'basis':'alpha>8最大8连通主体；固定2供体像素周边非零alpha抗锯齿余量',
                          'alphaGt8ComponentCount':n-1,'corePixels':int(core.sum()),'aaRadiusDonorPx':2.0,
                          'extraLowAlphaEnvelopePixels':int((envelope&~core).sum()),'envelopePixels':int(envelope.sum()),
                          'originalPngPixelsModified':False,'donorSha256':sha(DONOR)},
              'meshCounts':{'vertices':len(data['points']),'triangles':len(data['triangles']),
                            'texturedTrianglesAlphaGt8':int((data['triangleMaxAlpha']>8).sum())},
              'meshCoverage':data['coverage'],
              'uvMeshConsistencyMaxErrorDonorPx':float(np.abs(data['uv']*[1024,1024]-data['source']).max()),
              'weightContract':{'coordinate':'s=dot(p-mappedShoulder,unitMappedShoulderHandAxis)，source像素，横向无关',
                                'formula':'u=clip((s-elbowS)/hingeSpan+0.5,0,1); lower=u*u*(3-2*u); upper=1-lower',
                                'hingeSpanMeaning':'混合带总宽，不是半宽','elbowS':elbow_s,'axis':axis.tolist(),
                                'shoulder':mapped[0].tolist(),'nearestSegmentUsed':False,'continuousC1':True,
                                'vertexAxialS':s.tolist()},
              'mapping':baseline['mapping'],'manualSemantics':baseline['manualSemantics'],
              'boneLengthsOldPx':LENGTHS.tolist(),'boneLengthsNewPx':np.linalg.norm(np.diff(new,axis=0),axis=1).tolist(),
              'boneLengthChangesPx':(np.linalg.norm(np.diff(new,axis=0),axis=1)-LENGTHS).tolist(),
              'motionContract':baseline['motionContract'],'motionAmplitudeReduced':False,'targetsModified':False,
              'singleArmMeshPerCase':True,'limbBoneCount':2,'bodyHasNoVertexWeights':True,
              'deformUsed':False,'attachmentSwitchUsed':False,'runtimePackageWritten':False,
              'builderBuildCalled':False,'builderOutRedirectedBeforeImport':h.OUT==v.OUT==OUT,
              'candidates':candidates,'numericalGeometryPassed':all(c['numericalGeometryPassed'] for c in candidates.values()),
              'diagnosticSelection':{'rule':'仅按1537采样实纹理翻转累计最少；并列按预固定24/36/52顺序',
                                     'selectedVariant':selected,'diagnosticOnly':True,**FLAGS},
              'boundedFinitePlansAllFailed':all(not c['numericalGeometryPassed'] for c in candidates.values()),
              'failureReasons':[f'{name}:1537采样实纹理翻转{c["geometry"]["1537"]["texturedFlipsTriangleSamples"]}，塌缩{c["geometry"]["1537"]["texturedCollapseTriangleSamples"]}，最小面积比{c["geometry"]["1537"]["minAreaRatio"]:.12f}' for name,c in candidates.items()],
              'comparisonCaveat':'三档连续候选彼此共享同一新主体拓扑，仅hingeSpan不同；相对旧donor同时改变拓扑包络和权重语义，翻转次数变化不能单独归因于权重。',
              'conclusionScope':'当前v8供体、主体条带、setup、视频pose约束与三档固定连续权重均不合格；仅此有限方案失败，不推论双骨骨骼普遍不可行。',
              'shoulderRootGap':{'status':'人工待审，未确认肩根缝','gapFreeApproved':False,
                                 'confirmedShoulderRootGap':False,'waistGapIsNotShoulderRootEvidence':True},
              'waistTrouserGap':{'historicalObservationLocation':'近臂下方靠腰部/裤口的背景缺口，不是肩根位置',
                                  'causeStatus':'未确认；隐藏域覆盖不足或组装遮挡仅为待验证假设',
                                  'confirmedCause':None,'newCandidateObservation':'待实际看图'},
              'historicalInterpretationCorrection':'旧PNG/JSON按要求保留；旧记录把腰裤口缺口归因肩腋隐藏域的表述不构成已证实原因，更不构成确认肩根缝。',
              'historicalOutputsUnchanged':historical_unchanged,'historicalOutputCount':len(historical),
              'historicalOutputHashes':historical,'historicalScriptSha256':baseline['scriptSha256'],
              'protectedFilesUnchanged':protected_unchanged,'protectedFileCount':len(protected),
              'protectedHashes':{p.relative_to(BASE).as_posix():digest for p,digest in protected.items()},
              'visualReview':{'status':'待实际查看新图','passed':False},
              'limitations':baseline['limitations']+['新条带有意不包络远离主体的低alpha孤点，遗漏按原PNG逐像素公开。']}
    save(CONTINUOUS+'_checks.json',checks)
    save(CONTINUOUS+'_handoff.json',{'candidate':CONTINUOUS,**FLAGS,'diagnosticOnly':True,
         'checks':CONTINUOUS+'_checks.json','review':CONTINUOUS+'_review.png',
         'diagnosticSelection':checks['diagnosticSelection'],'numericalGeometryPassed':checks['numericalGeometryPassed'],
         'conclusionScope':checks['conclusionScope'],'shoulderRootGap':checks['shoulderRootGap'],
         'waistTrouserGap':checks['waistTrouserGap'],'historicalInterpretationCorrection':checks['historicalInterpretationCorrection'],
         'runtimePackageWritten':False})
    print(json.dumps({'candidate':CONTINUOUS,'selected':selected,'meshCoverage':data['coverage'],
                      'geometry':{name:c['geometry'] for name,c in candidates.items()},
                      'historicalOutputsUnchanged':historical_unchanged,'protectedFilesUnchanged':protected_unchanged,**FLAGS},ensure_ascii=False))


def record_continuous_review():
    checks = json.loads((OUT/(CONTINUOUS+'_checks.json')).read_text(encoding='utf-8'))
    assert checks['scriptSha256']==sha(__file__)
    assert all(sha(OUT/name)==digest for name,digest in checks['historicalOutputHashes'].items())
    assert all(sha(BASE/name)==digest for name,digest in checks['protectedHashes'].items())
    inspected = [CONTINUOUS+'_review.png']
    inspected += [f'{CONTINUOUS}_hinge{span}{suffix}.png' for span in HINGE_SPANS for suffix in ('_contact','_worst_assembly')]
    review = {'status':'actually_viewed_not_accepted','inspectedWith':'ViewImage',**FLAGS,'passed':False,
              'inspectedFileHashes':{name:sha(OUT/name) for name in inspected},
              'observations':['三档连续权重contact、三档最坏无网格帧和总览已实际查看。',
                              '主体条带不再为远端alpha=1孤点扩出原有大尖翼；曲肘处仍存在压缩、轮廓折叠风险，详见实纹理翻转数值。',
                              '手端原供体分瓣未修形；新候选不因主体包络改善而获批准。',
                              '无网格组装近臂下方腰裤口附近可见背景缺口；位置不在肩根，不确认其原因。'],
              'shoulderRootGap':checks['shoulderRootGap'],
              'waistTrouserGap':{**checks['waistTrouserGap'],'newCandidateObservation':'无网格组装近臂下方靠腰裤口可见背景缺口；不等同于肩根缝'}}
    save(CONTINUOUS+'_visual_review.json',review)
    checks.update({'status':'bounded_test_actually_reviewed_not_accepted','visualReview':review,
                   'waistTrouserGap':review['waistTrouserGap']})
    save(CONTINUOUS+'_checks.json',checks)
    handoff=json.loads((OUT/(CONTINUOUS+'_handoff.json')).read_text(encoding='utf-8'))
    handoff.update({'status':checks['status'],'visualReview':review,'waistTrouserGap':review['waistTrouserGap']})
    save(CONTINUOUS+'_handoff.json',handoff)
    print(json.dumps({'status':checks['status'],**FLAGS}))


if __name__=='__main__':
    if sys.argv[1:]==['--continuous-bounded']:
        bounded_main()
    elif sys.argv[1:]==['--record-continuous-review']:
        record_continuous_review()
    elif sys.argv[1:]==['--record-visible-review']:
        record_visible_review()
    else:
        assert not sys.argv[1:]
        main()
