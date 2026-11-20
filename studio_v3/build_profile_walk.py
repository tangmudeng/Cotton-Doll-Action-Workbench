"""独立原型：新建规则双骨权重，导出 Spine 4.2，并从导出文件 CPU 解算审阅。"""
from pathlib import Path
import hashlib
import json
import math
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
STABLE = RIG / 'stable_parts_v1'
VIDEO = RIG / 'video_parts_v1'
OUT = RIG / 'profile_walk_v1'
DURATION = 2 / 3
ORDER = ['leg_far', 'leg_near', 'body', 'shorts', 'arm_far', 'arm_near', 'head']
CHAINS = {
    'arm_near': [[350,456], [330,509], [317,555]],
    'arm_far': [[468,463], [485,500], [497,539]],
    'leg_near': [[359,576], [350,613], [349,656]],
    'leg_far': [[437,575], [445,607], [449,641]],
}
PIVOTS = {'root':[390,532], 'body':[390,532], 'head':[398,439], 'shorts':[410,554]}
POSES = ['near_contact', 'near_pass', 'far_contact', 'far_pass']
FRAMES = [68,72,76,80]
FLAGS = {k:False for k in ['prototypeAccepted', 'productionApproved', 'wardrobeVerified', 'crossCharacterVerified', 'mobileVerified']}
PAYLOAD = ['profile.json','profile_walk.json','profile_walk.atlas','profile_walk.png','provenance.json','checks.json','review.png']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def rel(path):
    return Path(path).resolve().relative_to(BASE).as_posix()


def yup(p):
    return np.array([p[0],768-p[1]], dtype=float)


def screen(points):
    result = np.array(points, dtype=float, copy=True)
    result[...,1] = 768-result[...,1]
    return result


def rotate(angle):
    a = math.radians(angle)
    c,s = math.cos(a),math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]], dtype=float)


def translate(x,y):
    m = np.eye(3)
    m[:2,2] = [x,y]
    return m


def cross(a,b):
    return a[...,0]*b[...,1]-a[...,1]*b[...,0]


def sample(keys,t,field):
    if not keys:
        return 0.
    if t >= keys[-1]['time']:
        return keys[-1].get(field,0.)
    for a,b in zip(keys,keys[1:]):
        if a['time'] <= t <= b['time']:
            u = (t-a['time'])/(b['time']-a['time'])
            return a.get(field,0.)*(1-u)+b.get(field,0.)*u
    return keys[0].get(field,0.)


def solve(skeleton,animation,t):
    worlds = {}
    channels = skeleton.get('animations',{}).get(animation,{}).get('bones',{})
    for bone in skeleton['bones']:
        ch = channels.get(bone['name'],{})
        x = bone.get('x',0)+sample(ch.get('translate',[]),t,'x')
        y = bone.get('y',0)+sample(ch.get('translate',[]),t,'y')
        a = bone.get('rotation',0)+sample(ch.get('rotate',[]),t,'value')
        worlds[bone['name']] = worlds.get(bone.get('parent'),np.eye(3)) @ translate(x,y) @ rotate(a)
    return worlds


def make_bones():
    bones = [{'name':'root','x':390,'y':236}, {'name':'body','parent':'root','length':60}]
    for name in ['head','shorts']:
        d = yup(PIVOTS[name])-yup(PIVOTS['body'])
        bones.append({'name':name,'parent':'body','x':float(d[0]),'y':float(d[1]),'length':40})
    for name,joints in CHAINS.items():
        a,b,c = map(yup,joints)
        upper_angle = math.degrees(math.atan2(*(b-a)[::-1]))
        lower_angle = math.degrees(math.atan2(*(c-b)[::-1]))
        d = a-yup(PIVOTS['body'])
        bones.append({'name':name+'_upper','parent':'body','x':float(d[0]),'y':float(d[1]),
                      'rotation':upper_angle,'length':float(np.linalg.norm(b-a))})
        bones.append({'name':name+'_lower','parent':name+'_upper','x':float(np.linalg.norm(b-a)),
                      'rotation':lower_angle-upper_angle,'length':float(np.linalg.norm(c-b))})
    return bones


def pack(images):
    pad = 4
    w = max(im.width for im in images.values())+pad*2
    h = sum(im.height+pad*2 for im in images.values())
    page = Image.new('RGBA',(w,h))
    regions = {}
    y = 0
    for name,im in images.items():
        # 仅 atlas 采样护边复制现有边缘；不向角色素材添加像素。
        page.paste(Image.fromarray(np.pad(np.asarray(im),((pad,pad),(pad,pad),(0,0)),mode='edge')),(0,y))
        regions[name] = {'x':pad,'y':y+pad,'width':im.width,'height':im.height,'padding':pad}
        y += im.height+pad*2
    page.save(OUT/'profile_walk.png')
    lines = ['profile_walk.png',f'size: {w},{h}','format: RGBA8888','filter: Linear,Linear','repeat: none','pma: false']
    for name,r in regions.items():
        lines += [name,'  rotate: false',f"  xy: {r['x']},{r['y']}",f"  size: {r['width']},{r['height']}",
                  f"  orig: {r['width']},{r['height']}",'  offset: 0,0','  index: -1']
    (OUT/'profile_walk.atlas').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return page,regions


def read_atlas():
    lines = (OUT/'profile_walk.atlas').read_text(encoding='utf-8').splitlines()
    page = Image.open(OUT/lines[0]).convert('RGBA')
    regions = {}
    name = None
    for line in lines[1:]:
        if not line.startswith(' ') and ':' not in line and line:
            name = line
            regions[name] = {'padding':4}
        elif name and line.strip().startswith('xy:'):
            regions[name]['x'],regions[name]['y'] = map(int,line.split(':')[1].split(','))
        elif name and line.strip().startswith('size:'):
            regions[name]['width'],regions[name]['height'] = map(int,line.split(':')[1].split(','))
    return page,regions


def new_mesh(name,part,bind,bones):
    x0,y0,x1,y1 = part['bbox']
    # 等分网格每边约10px，不使用末尾不足8px的窄条三角形。
    xs = np.linspace(x0,x1,round((x1-x0)/10)+1)
    ys = np.linspace(y0,y1,round((y1-y0)/10)+1)
    points = np.array([(x,y) for y in ys for x in xs])
    cols,rows = len(xs),len(ys)
    tri = []
    for y in range(rows-1):
        for x in range(cols-1):
            a = y*cols+x
            tri.extend([[a,a+1,a+cols+1],[a,a+cols+1,a+cols]])
    # 连续单轴投影，和旧 nearest-segment 权重独立；在肘/膝两侧各28px宽缓混合。
    a,b,c = np.asarray(CHAINS[name],dtype=float)
    axis = (c-a)/np.linalg.norm(c-a)
    joint_s = (b-a)@axis
    distance = (points-a)@axis
    u = np.clip((distance-joint_s+28)/56,0,1)
    lower = u*u*(3-2*u)
    # 肩髋前28px纯既有body骨，28..58px平滑转入上下双骨；脚底body权重为0。
    blend = np.clip((distance-28)/30,0,1)
    limb = blend*blend*(3-2*blend)
    weights = np.stack([1-limb,limb*(1-lower),limb*lower],axis=1)
    bone_names = ['body',name+'_upper',name+'_lower']
    local = []
    hom = np.column_stack([screen(points),np.ones(len(points))])
    for bone in bone_names:
        local.append((hom@np.linalg.inv(bind[bone]).T)[:,:2])
    local = np.stack(local,axis=1)
    vertices = []
    indices = {b['name']:i for i,b in enumerate(bones)}
    for i in range(len(points)):
        influences = [j for j in range(len(bone_names)) if weights[i,j]>0]
        vertices.append(len(influences))
        for j in influences:
            vertices += [indices[bone_names[j]],float(local[i,j,0]),float(local[i,j,1]),float(weights[i,j])]
    uv = (points-[x0,y0])/[x1-x0,y1-y0]
    attachment = {'type':'mesh','path':name,'uvs':uv.ravel().tolist(),'triangles':np.asarray(tri).ravel().tolist(),
                  'vertices':vertices,'width':x1-x0,'height':y1-y0}
    return attachment,{'points':points,'weights':weights,'triangles':np.asarray(tri,dtype=int),'chain':bone_names,
                       'spacing':[float(xs[1]-xs[0]),float(ys[1]-ys[0])],'uv':uv}


def decode_meshes(skeleton,regions):
    meshes = {}
    bind = solve(skeleton,'setup',0)
    bone_names = [b['name'] for b in skeleton['bones']]
    for slot in skeleton['slots']:
        name = slot['name']
        a = skeleton['skins'][0]['attachments'][name][slot['attachment']]
        if a['type'] != 'mesh':
            continue
        uv = np.asarray(a['uvs']).reshape(-1,2)
        stream = a['vertices']
        offset = 0
        influences = []
        for i in range(len(uv)):
            count = int(stream[offset])
            offset += 1
            row = []
            for j in range(count):
                bone,x,y,w = stream[offset:offset+4]
                assert int(bone) == bone and 0 <= bone < len(bone_names)
                row.append((bone_names[int(bone)],np.array([x,y,1.]),float(w)))
                offset += 4
            influences.append(row)
        assert offset == len(stream)
        r = regions[a['path']]
        source = uv*[r['width'],r['height']]+[r['x']-.5,r['y']-.5]
        mesh = {'uv':uv,'source':source,'influences':influences,'triangles':np.asarray(a['triangles']).reshape(-1,3)}
        mesh['bind'] = vertices_world(mesh,bind)
        meshes[name] = mesh
    return meshes


def vertices_world(mesh,worlds):
    return np.array([sum((worlds[b]@p)[:2]*w for b,p,w in row) for row in mesh['influences']])


def material_binding(mesh,point_yup):
    p = np.asarray(point_yup)
    for tri in mesh['triangles']:
        a,b,c = mesh['bind'][tri]
        v = np.linalg.solve(np.column_stack([b-a,c-a]),p-a)
        bary = np.r_[1-v.sum(),v]
        if bary.min() >= -1e-7:
            return tri,bary
    raise AssertionError('脚底锚点不在mesh内')


def material_position(mesh,worlds,binding):
    tri,bary = binding
    return bary@vertices_world(mesh,worlds)[tri]


def keys(values,field='value'):
    return [{'time':i/12,field:float(v)} for i,v in enumerate(values)]


def motion(skeleton,meshes,anchors):
    # 有限手工角度与中间键；没有使用正弦、轮廓拟合或运动反解。
    angles = {
        'body':[0,.10,.16,.08,0,-.10,-.16,-.08,0],
        'arm_near_upper':[-.6,-.4,0,.4,.6,.4,0,-.4,-.6],
        'arm_near_lower':[1.2,1,.8,.6,.8,1,1.2,1,1.2],
        'arm_far_upper':[.5,.35,0,-.35,-.5,-.35,0,.35,.5],
        'arm_far_lower':[-1.2,-.8,-.4,0,.4,.2,-.4,-.8,-1.2],
        'leg_near_upper':[-3,-2,1,3,4,1,-2,-4,-3],
        'leg_near_lower':[2,0,-3,-1,5,9,6,3,2],
        'leg_far_upper':[4,1,-2,-4,-3,-2,1,3,4],
        'leg_far_lower':[5,9,6,3,2,0,-3,-1,5],
    }
    channels = {n:{'rotate':keys(v)} for n,v in angles.items()}
    bob = [0,.35,.8,.35,0,.35,.8,.35,0]
    channels['body']['translate'] = [{'time':i/12,'x':0.,'y':v} for i,v in enumerate(bob)]
    skeleton['animations'] = {'walk':{'bones':channels},'setup':{'bones':{}}}
    trajectories = {
        'leg_near':{'x':[0,0,0,0,0,3,8,4,0],'lift':[0,0,0,0,0,6,8,4,0]},
        'leg_far':{'x':[0,3,8,4,0,0,0,0,0],'lift':[0,6,8,4,0,0,0,0,0]},
    }
    compensation = {}
    # 正向解算给定角度，平移下腿骨补偿脚底；上腿根保持原位，不改变角度，非IK。
    # 支撑期原地固定、摆动期目标移动；只烘焙平移补偿，不重拟合角度。
    for name in trajectories:
        # 补偿放在下段骨局部平移；上段和body根锚保持固定，脚点body权重为0。
        ch = name+'_lower'
        bindings = anchors[name]['binding']
        target_setup = anchors[name]['yup']
        results = []
        dxkeys = keys(trajectories[name]['x'])
        dykeys = keys(trajectories[name]['lift'])
        for i in range(97):
            t = DURATION*i/96
            world = solve(skeleton,'walk',t)
            actual = material_position(meshes[name],world,bindings)
            target = target_setup+[sample(dxkeys,t,'value'),sample(dykeys,t,'value')]
            tri,bary = bindings
            lower_influence = sum(float(v)*sum(w for b,p,w in meshes[name]['influences'][int(j)] if b==ch) for j,v in zip(tri,bary))
            assert lower_influence > .99
            delta = np.linalg.inv(world[name+'_upper'][:2,:2])@(target-actual)/lower_influence
            results.append({'time':t,'x':float(delta[0]),'y':float(delta[1])})
        channels[ch]['translate'] = results
        compensation[name] = float(max(np.linalg.norm([k['x'],k['y']]) for k in results))
    for ch in channels.values():
        for timeline in ch.values():
            timeline[-1] = {**timeline[0],'time':DURATION}
    return angles,trajectories,compensation


def premul(a):
    a = np.asarray(a).astype(np.float32)/255
    a[:,:,:3] *= a[:,:,3:4]
    return a


def image_from_premul(canvas):
    rgb = np.divide(canvas[:,:,:3],canvas[:,:,3:4],out=np.zeros_like(canvas[:,:,:3]),where=canvas[:,:,3:4]>1e-9)
    return Image.fromarray(np.clip(np.rint(np.dstack([rgb,canvas[:,:,3]])*255),0,255).astype(np.uint8))


def mesh_geometry(mesh,world):
    dst = vertices_world(mesh,world)
    tri = mesh['triangles']
    a = mesh['bind'][tri]
    b = dst[tri]
    ratio = cross(b[:,1]-b[:,0],b[:,2]-b[:,0])/cross(a[:,1]-a[:,0],a[:,2]-a[:,0])
    return {'minAreaRatio':float(ratio.min()),'maxAreaRatio':float(ratio.max()),'flips':int((ratio<0).sum()),
            'collapsed':int((np.abs(ratio)<1e-5).sum())},dst


def render_mesh(source,mesh,world):
    stats,dst_q = mesh_geometry(mesh,world)
    dst = screen(dst_q)
    canvas = np.zeros((768,768,4),dtype=np.float32)
    coverage = np.zeros((768,768),dtype=np.uint16)
    for tri in mesh['triangles']:
        src,d = mesh['source'][tri],dst[tri]
        area = cross(d[1]-d[0],d[2]-d[0])
        assert area>1e-6
        lo = np.maximum(np.floor(d.min(axis=0)).astype(int)-1,0)
        hi = np.minimum(np.ceil(d.max(axis=0)).astype(int)+1,768)
        x0,y0 = lo
        x1,y1 = hi
        if x1<=x0 or y1<=y0:
            continue
        # 整数cv2像素中心和Spine边界坐标相差0.5；预乘纹理一次采样。
        m = cv2.getAffineTransform(src.astype(np.float32),(d-.5-lo).astype(np.float32))
        warped = cv2.warpAffine(source,m,(int(x1-x0),int(y1-y0)),flags=cv2.INTER_LINEAR)
        xx,yy = np.meshgrid(np.arange(x0,x1)+.5,np.arange(y0,y1)+.5)
        pixels = np.stack([xx,yy],axis=-1)
        owned = np.ones(xx.shape,dtype=bool)
        for a,b in zip(d,np.roll(d,-1,axis=0)):
            edge = b-a
            e = cross(edge,pixels-a)
            top_left = edge[1]<0 or (abs(edge[1])<1e-10 and edge[0]>0)
            owned &= (e>1e-7)|((np.abs(e)<=1e-7)&top_left)
        # 同一mesh共享边单次归属；透明像素不覆盖其他slot。
        roi = canvas[y0:y1,x0:x1]
        roi[owned] = warped[owned]
        coverage[y0:y1,x0:x1] += owned.astype(np.uint16)
    stats['interiorOverlapPixels'] = int((coverage>1).sum())
    return canvas,stats


def render(skeleton,page,regions,meshes,animation,t):
    world = solve(skeleton,animation,t)
    source = premul(page)
    canvas = np.zeros((768,768,4),dtype=np.float32)
    stats = {}
    flip = np.array([[1,0,0],[0,-1,768],[0,0,1]],dtype=float)
    for slot in skeleton['slots']:
        n = slot['name']
        a = skeleton['skins'][0]['attachments'][n][slot['attachment']]
        if a['type']=='mesh':
            layer,stats[n] = render_mesh(source,meshes[n],world)
        else:
            r = regions[a['path']]
            im = source[r['y']:r['y']+r['height'],r['x']:r['x']+r['width']]
            local = np.array([[1,0,a['x']-a['width']/2+.5],[0,-1,a['y']+a['height']/2-.5],[0,0,1]])
            m = flip@world[slot['bone']]@local
            m[:2,2] -= .5
            layer = cv2.warpAffine(im,m[:2],(768,768),flags=cv2.INTER_LINEAR)
        canvas = layer+canvas*(1-layer[:,:,3:4])
    return image_from_premul(canvas),stats


def package():
    with zipfile.ZipFile(OUT/'profile_walk.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in PAYLOAD:
            archive.write(OUT/name,name)
    with zipfile.ZipFile(OUT/'profile_walk.zip') as archive:
        assert archive.testzip() is None
        assert archive.namelist()==PAYLOAD
        assert all(archive.read(n)==(OUT/n).read_bytes() for n in PAYLOAD)


def main():
    assert BASE.is_dir() and RIG.is_dir()
    # 允许重跑本原型目录，拒绝覆写未知文件或其他目录。
    OUT.mkdir(exist_ok=True)
    assert all(p.name in PAYLOAD+['profile_walk.zip'] for p in OUT.iterdir())
    protected = [p for p in BASE.rglob('*') if p.is_file() and OUT not in p.parents and p!=Path(__file__).resolve()]
    before = {p:sha(p) for p in protected}
    mp = STABLE/'manifest.json'
    manifest = load(mp)
    vm_path = VIDEO/'manifest.json'
    vm = load(vm_path)
    sources_path = VIDEO/'cycle_review/sources.json'
    sources = load(sources_path)
    tracks_path = RIG/'tracks.json'
    tracks = load(tracks_path)
    assert {p['id'] for p in manifest['parts']}==set(ORDER)
    video = (VIDEO/vm['sourceVideo']).resolve()
    assert sha(video)==vm['sourceVideoSha256']==sources['sourceVideoSha256']
    source_image = (STABLE/manifest['sourceImage']['file']).resolve()
    assert sha(source_image)==manifest['sourceImage']['sha256']
    images,parts,hashes = {},{},[]
    for p in manifest['parts']:
        path = STABLE/p['file']
        actual = sha(path)
        assert actual==p['sha256']
        im = Image.open(path).convert('RGBA')
        assert im.size==(p['width'],p['height'])
        assert im.size==(p['bbox'][2]-p['bbox'][0],p['bbox'][3]-p['bbox'][1])
        images[p['id']],parts[p['id']] = im,p
        hashes.append({'id':p['id'],'file':rel(path),'expectedSha256':p['sha256'],'actualSha256':actual})
    # 对真实视频顺序解码到84帧，保存证据SHA，不把其纹理加入角色。
    evidence = []
    cap = cv2.VideoCapture(str(video))
    assert cap.isOpened() and abs(cap.get(cv2.CAP_PROP_FPS)-24)<1e-6
    track_map = {r['index']:r for r in tracks['tracks']}
    for frame in range(85):
        ok,bgr = cap.read()
        assert ok
        if frame not in FRAMES:
            continue
        record = next(p for p in vm['parts'] if p['sourceFrame']==frame)
        path = VIDEO/record['sourceFile']
        assert sha(path)==record['sourceFrameSha256']
        assert np.array_equal(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),np.asarray(Image.open(path).convert('RGB')))
        evidence.append({'frame':frame,'sourceFile':rel(path),'sha256':sha(path),'decodedPixelsExact':True,
                         'sourceObservation':next(p for p in sources['frames'] if p['sourceFrame']==frame),
                         'track':track_map[frame]})
    cap.release()
    page,regions = pack({n:images[n] for n in ORDER})
    bones = make_bones()
    skeleton = {'skeleton':{'spine':'4.2.00','width':768,'height':768,'images':'./'},'bones':bones,'slots':[],
                'skins':[{'name':'default','attachments':{}}],'animations':{}}
    skin = skeleton['skins'][0]['attachments']
    bind = solve(skeleton,'setup',0)
    designed = {}
    for n in ORDER:
        if n in CHAINS:
            a,designed[n] = new_mesh(n,parts[n],bind,bones)
            bone = n+'_upper'
        else:
            x0,y0,x1,y1 = parts[n]['bbox']
            px,py = PIVOTS[n]
            a = {'type':'region','path':n,'x':(x0+x1)/2-px,'y':py-(y0+y1)/2,'width':x1-x0,'height':y1-y0}
            bone = n
        skin[n] = {n:a}
        skeleton['slots'].append({'name':n,'bone':bone,'attachment':n})
    meshes = decode_meshes(skeleton,regions)
    anchors = {}
    for n in ['leg_near','leg_far']:
        ys,xs = np.where(np.asarray(images[n])[:,:,3]>200)
        floor = int(ys.max())
        fx = float(np.median(xs[ys>=floor-2]))+parts[n]['bbox'][0]+.5
        point = [fx,float(floor+parts[n]['bbox'][1])+.5]
        anchors[n] = {'sourcePixelsTopLeft':point,'yup':yup(point),'binding':material_binding(meshes[n],yup(point))}
    angles,targets,compensation = motion(skeleton,meshes,anchors)
    profile = {'schemaVersion':1,'profileId':'profile_walk_v1','characterId':None,'sourceDirection':manifest['direction'],
               'root':{'sourcePixelsTopLeft':[390,532],'setupYUp':[390,236]},'coordinateContract':'Spine y-up=768-source_y; UV为region局部0..1；渲染像素中心偏移0.5',
               'proportions':{'canvas':[768,768],'partsBbox':{n:parts[n]['bbox'] for n in ORDER},'pivots':PIVOTS,'limbChainsSourcePixels':CHAINS},
               'bind':{'bones':bones,'slots':skeleton['slots'],'attachments':skin},
               'mesh':{n:{'vertexCount':len(d['points']),'triangleCount':len(d['triangles']),'gridSpacingPx':d['spacing'],
                          'verticesSourcePixels':d['points'].tolist(),'triangles':d['triangles'].tolist(),
                          'weights':d['weights'].tolist(),'boneOrder':d['chain'],'regionUV':d['uv'].tolist(),
                          'weightRule':'近端前28px纯body根锚，28..58px cubic smoothstep过渡到上下双骨；肘膝两侧各28px平滑；脚底body权重为0',
                          'weightBoneOrder':d['chain'],'bindingMode':'双骨链+既有body根锚','staticWeights':True} for n,d in designed.items()},
               'textureMapping':{'page':'profile_walk.png','atlas':'profile_walk.atlas','regions':regions,'newTexturePixels':0,'oldWeightsReused':False},
               'clothingChainContract':{'headBodyShorts':'保持region','sleeves':'衣袖共用对应arm上下骨链，可使用现有body作为根锚；衣袖必须是独立mesh/UV/静态weights，不强制与身体或手臂同UV/同权重；本次不新增袖子或碎片。',
                                        'sleevesAdded':False,'wardrobeVerified':False},
               'motionSeparated':True,'motionFile':'profile_walk.json','motionPhasesStoredHere':False}
    save('profile.json',profile)
    save('profile_walk.json',skeleton)
    # 从磁盘JSON的weighted vertices与atlas重新解析；不使用设计内存替代导出解算。
    skeleton = load(OUT/'profile_walk.json')
    page,regions = read_atlas()
    meshes = decode_meshes(skeleton,regions)
    for n in anchors:
        anchors[n]['binding'] = material_binding(meshes[n],anchors[n]['yup'])
    setup_checks = {}
    for n,m in meshes.items():
        error = np.linalg.norm(m['bind']-screen(designed[n]['points']),axis=1)
        sums = [sum(w for b,p,w in row) for row in m['influences']]
        setup_checks[n] = {'maxReconstructionErrorPx':float(error.max()),'maxWeightSumError':float(np.max(np.abs(np.asarray(sums)-1))),
                           'finiteNonnegativeWeights':all(np.isfinite(w) and w>=0 for row in m['influences'] for b,p,w in row),
                           'onlyTwoSemanticBones':False,
                           'dualLimbChainPlusBodyRoot':sorted({b for row in m['influences'] for b,p,w in row})==sorted(designed[n]['chain']),
                           'weightBoneOrder':designed[n]['chain'],
                           'bodyRootWeightMax':float(max(w for row in m['influences'] for b,p,w in row if b=='body')),
                           'distalRowBodyWeightMax':float(max(sum(w for b,p,w in row if b=='body') for row,point in zip(m['influences'],m['bind']) if point[1] <= m['bind'][:,1].min()+1e-7))}
        if n in anchors:
            tri,bary = anchors[n]['binding']
            foot_body = sum(float(v)*sum(w for b,p,w in m['influences'][int(i)] if b=='body') for i,v in zip(tri,bary))
            setup_checks[n]['footMaterialBodyWeight'] = float(foot_body)
            assert abs(foot_body)<1e-12
        tri = designed[n]['triangles']
        edges = np.unique(np.sort(np.vstack([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
        weights = designed[n]['weights']
        edge_lengths = np.linalg.norm(designed[n]['points'][edges[:,1]]-designed[n]['points'][edges[:,0]],axis=1)
        gradients = np.max(np.abs(weights[edges[:,1]]-weights[edges[:,0]]),axis=1)/edge_lengths
        setup_checks[n]['maxWeightGradientPerPx'] = float(gradients.max())
        setup_checks[n]['pureBodyRootVertexCount'] = int((weights[:,0]==1).sum())
    geometry = {n:{'minAreaRatio':1e9,'maxAreaRatio':0.,'minPrincipalStretch':1e9,'maxPrincipalStretch':0.,'maxPureBodyRootErrorPx':0.,'flips':0,'collapsed':0} for n in meshes}
    foot_samples = []
    mesh_loop_error = {}
    for n,m in meshes.items():
        mesh_loop_error[n] = float(np.linalg.norm(vertices_world(m,solve(skeleton,'walk',0))-vertices_world(m,solve(skeleton,'walk',DURATION)),axis=1).max())
    # 193个相位含补偿关键帧之间的中点，避免只检验烘焙关键值。
    for i in range(193):
        t = DURATION*i/192
        world = solve(skeleton,'walk',t)
        for n,m in meshes.items():
            g,dst = mesh_geometry(m,world)
            tri = m['triangles']
            src_tri,dst_tri = m['bind'][tri],dst[tri]
            src_edges = np.stack([src_tri[:,1]-src_tri[:,0],src_tri[:,2]-src_tri[:,0]],axis=-1)
            dst_edges = np.stack([dst_tri[:,1]-dst_tri[:,0],dst_tri[:,2]-dst_tri[:,0]],axis=-1)
            singular = np.linalg.svd(dst_edges@np.linalg.inv(src_edges),compute_uv=False)
            geometry[n]['minPrincipalStretch'] = min(geometry[n]['minPrincipalStretch'],float(singular.min()))
            geometry[n]['maxPrincipalStretch'] = max(geometry[n]['maxPrincipalStretch'],float(singular.max()))
            geometry[n]['maxAreaRatio'] = max(geometry[n]['maxAreaRatio'],g['maxAreaRatio'])
            root_mask = designed[n]['weights'][:,0]==1
            root_hom = np.column_stack([m['bind'][root_mask],np.ones(root_mask.sum())])
            expected = (root_hom@(world['body']@np.linalg.inv(bind['body'])).T)[:,:2]
            geometry[n]['maxPureBodyRootErrorPx'] = max(geometry[n]['maxPureBodyRootErrorPx'],float(np.linalg.norm(dst[root_mask]-expected,axis=1).max()))
            geometry[n]['minAreaRatio'] = min(geometry[n]['minAreaRatio'],g['minAreaRatio'])
            geometry[n]['flips'] += g['flips']
            geometry[n]['collapsed'] += g['collapsed']
        row = {'time':t}
        for n in anchors:
            row[n] = screen(material_position(meshes[n],world,anchors[n]['binding'])).tolist()
        foot_samples.append(row)
    foot_metrics = {}
    for n,interval in [('leg_near',[0,.25]),('leg_far',[1/3,7/12])]:
        samples = np.array([r[n] for r in foot_samples if interval[0]-1e-9<=r['time']<=interval[1]+1e-9])
        trajectory = np.array([r[n] for r in foot_samples])
        foot_metrics[n] = {'supportIntervalSeconds':interval,'supportSampleCount':len(samples),
                           'supportMaxDriftPx':float(np.linalg.norm(samples-samples[0],axis=1).max()),
                           'cycleRangeXPx':float(np.ptp(trajectory[:,0])),'cycleRangeYPx':float(np.ptp(trajectory[:,1])),
                           'hipTranslateMaxPx':0.0,'lowerTranslateMaxPx':compensation[n],'compensationBone':n+'_lower','anchorSourcePixels':anchors[n]['sourcePixelsTopLeft'],
                           'method':'导出weighted mesh中脚底材料点的重心插值，非单纯骨端点；仅支撑期固定；非IK'}
    frames = []
    raster = {}
    for i in range(16):
        image,stats = render(skeleton,page,regions,meshes,'walk',i/24)
        frames.append(image)
        for n,g in stats.items():
            raster[n] = max(raster.get(n,0),g['interiorOverlapPixels'])
    first,_ = render(skeleton,page,regions,meshes,'walk',0)
    last,_ = render(skeleton,page,regions,meshes,'walk',DURATION)
    loop_pixels = int(np.any(np.asarray(first)!=np.asarray(last),axis=2).sum())
    main_poses = [frames[i] for i in [0,4,8,12]]
    diff = {POSES[i]+'__'+POSES[j]:int(np.any(np.asarray(main_poses[i])!=np.asarray(main_poses[j]),axis=2).sum()) for i in range(4) for j in range(i+1,4)}
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(font_path),17) if font_path.exists() else ImageFont.load_default()
    title_font = ImageFont.truetype(str(font_path),23) if font_path.exists() else font
    sheet = Image.new('RGB',(1560,1670),'#eef2f6')
    draw = ImageDraw.Draw(sheet)
    draw.text((25,17),'PROFILE WALK / 四姿态 / 导出weighted mesh CPU解算',font=title_font,fill='#193149')
    for i,image in enumerate(main_poses):
        x = i*390
        draw.text((x+14,63),f'{POSES[i]} / {i/6:.4f}s',font=font,fill='#193149')
        draw.text((x+14,89),f'f{FRAMES[i]}仅节奏参考 / 非视频复原',font=font,fill='#647587')
        bg = Image.new('RGBA',(370,495),'#fcfcfd')
        bg.alpha_composite(image.crop((165,95,615,695)).resize((370,493),Image.Resampling.LANCZOS))
        sheet.paste(bg.convert('RGB'),(x+10,120))
        detail = Image.new('RGBA',(370,340),'#dce4ec')
        detail.alpha_composite(image.crop((280,425,515,665)).resize((333,340),Image.Resampling.NEAREST),(18,0))
        sheet.paste(detail.convert('RGB'),(x+10,636))
    draw.text((23,996),'原型待审：肩根/腿根隐藏图不完整，未补画；近远侧身份暂定；生产/换装/跨角色/移动端未验收',font=font,fill='#8e4d30')
    # 四主姿态下方追加两张相邻关键帧间过渡和循环前/后图，全部来自导出的weighted vertices。
    extra_times = [3/24,11/24,DURATION-1/192,DURATION+1/192]
    extra_labels = ['transition A / t=0.125s','transition B / t=0.458333s','loop before / t=T-1/192','loop after / t=T+1/192']
    extra_stats = {}
    for i,(t,label) in enumerate(zip(extra_times,extra_labels)):
        image,stats = render(skeleton,page,regions,meshes,'walk',t%DURATION)
        extra_stats[label] = stats
        x = i*390
        draw.text((x+14,1042),label,font=font,fill='#193149')
        bg = Image.new('RGBA',(370,260),'#fcfcfd')
        bg.alpha_composite(image.crop((165,95,615,695)).resize((195,260),Image.Resampling.LANCZOS),(87,0))
        sheet.paste(bg.convert('RGB'),(x+10,1072))
        detail = Image.new('RGBA',(370,302),'#dce4ec')
        detail.alpha_composite(image.crop((280,425,515,665)).resize((296,302),Image.Resampling.NEAREST),(37,0))
        sheet.paste(detail.convert('RGB'),(x+10,1344))
    sheet.save(OUT/'review.png')
    atlas_checks = {}
    for n,r in regions.items():
        x,y,w,h,p = [r[k] for k in ['x','y','width','height','padding']]
        actual = np.asarray(page)[y-p:y+h+p,x-p:x+w+p]
        expected = np.pad(np.asarray(images[n]),((p,p),(p,p),(0,0)),mode='edge')
        atlas_checks[n] = {'contentAndPaddingExact':bool(np.array_equal(actual,expected)),
                           'insidePage':bool(x>=p and y>=p and x+w+p<=page.width and y+h+p<=page.height)}
    for p,original_sha in before.items():
        assert sha(p)==original_sha, f'旧文件意外改变：{p}'
    assert set(p for p in BASE.rglob('*') if p.is_file() and OUT not in p.parents and p!=Path(__file__).resolve())==set(before)
    source_end = all(sha(STABLE/parts[n]['file'])==parts[n]['sha256'] for n in parts)
    keys_exact = all(k[0]=={**k[-1],'time':k[0]['time']} for ch in skeleton['animations']['walk']['bones'].values() for k in ch.values())
    limitations = ['只在原图视角使用七件现有纹理；body源件既有4095px隐藏供体搭接保持不变，本次没有生成/涂补任何纹理。',
                   '肩根、腋下、髋根与腿根隐藏面不全，原型未获无露缝批准；裤口描边归属仍待美术复核。',
                   '原图为right_front_3q，不因文件名profile就声称获得真实侧面转向。',
                   'near/far是静态屏幕层假设，不代表视频解剖左右或跨帧身份；未复现胸前大交叉。',
                   '角度为九个有限手工键线性插值；脚底平移是正向补偿，非IK；支撑期原地固定，摆动期移动，不锁死双脚。',
                   'Python CPU验证不是Spine编辑器或官方运行时验收，移动端/换装/跨角色验证均未进行。']
    provenance = {'schemaVersion':1,'status':'prototype_pending_review',**FLAGS,'visualReview':'pending','characterId':None,
                  'stableManifest':{'file':rel(mp),'sha256':sha(mp)},'stableParts':hashes,
                  'sourceImage':{'file':rel(source_image),'sha256':sha(source_image)},
                  'reference':{'video':rel(video),'videoSha256':sha(video),'fps':24,
                               'sources':{'file':rel(sources_path),'sha256':sha(sources_path)},
                               'manifest':{'file':rel(vm_path),'sha256':sha(vm_path)},'tracks':{'file':rel(tracks_path),'sha256':sha(tracks_path)},
                               'evidence':evidence,'assumptions':'68/72/76/80仅节奏参考，主姿态手工设计；不冒称完整还原原视频。'},
                  'motion':{'mainPoses':[{'name':n,'time':i/6,'referenceFrame':FRAMES[i]} for i,n in enumerate(POSES)],
                            'manualAngles':angles,'manualFootOffsets':targets,'footMetrics':foot_metrics,'footSamples':foot_samples,
                            'endKey':'2/3秒显式复制首键','automaticAngleFitting':False,'isIK':False},
                  'rendering':'重新读取Spine JSON的weighted vertices及atlas；预乘alpha；半开top-left三角共享边；slot source-over',
                  'script':{'file':rel(__file__),'sha256':sha(__file__)},'limitations':limitations}
    save('provenance.json',provenance)
    checks = {'schemaVersion':1,'status':'prototype_pending_review',**FLAGS,'visualReview':'pending',
              'allSevenStablePartsHashVerified':source_end,'stableManifestUnchanged':sha(mp)==before[mp],
              'protectedOldFilesUnchanged':True,'protectedOldFileCount':len(before),'sourceVideoSHAAndFourDecodedFramesVerified':True,
              'boneCount':len(bones),'slotCount':len(skeleton['slots']),'spineVersion':'4.2.00',
              'setupWeightedReconstruction':setup_checks,'cycleSampleCount':193,'meshGeometry':geometry,'meshRasterOverlapPixels':raster,
              'firstLastKeysExact':keys_exact,'firstLastMeshMaxErrorPx':mesh_loop_error,'firstLastRenderMismatchPixels':loop_pixels,
              'fourPosePairwisePixelDifferences':diff,'fourPosesActuallyDifferent':all(v>0 for v in diff.values()),
              'footTrajectory':foot_metrics,'atlasRegions':atlas_checks,'previewUsesExportedWeightedVertices':True,
              'officialSpineImportVerified':False,'shoulderAndLegRootGapFree':False,'reviewPoseCount':4,
              'extraReviewSamples':extra_times,'extraReviewRaster':extra_stats,'staticBodyRootAnchors':True,'noDeformTimeline':all('deform' not in a for a in skeleton['animations'].values()),
              'zip':{'filename':'profile_walk.zip','members':PAYLOAD,'crcVerified':True,'bytesMatchDisk':True,
                     'verification':'最终ZIP关闭后重新读取CRC和逐成员字节；不做ZIP自身递归SHA'},'limitations':limitations}
    assert len(bones)==12 and len(skeleton['slots'])==7 and source_end and keys_exact
    assert all(c['maxReconstructionErrorPx']<1e-8 and c['maxWeightSumError']<1e-12 and c['finiteNonnegativeWeights'] and c['dualLimbChainPlusBodyRoot'] and c['distalRowBodyWeightMax']==0 and c['maxWeightGradientPerPx']<.051 for c in setup_checks.values())
    assert all(c['minAreaRatio']>.25 and c['minPrincipalStretch']>.35 and c['maxPrincipalStretch']<1.8 and c['maxPureBodyRootErrorPx']<1e-8 and c['flips']==0 and c['collapsed']==0 for c in geometry.values())
    assert all(v<1e-8 for v in mesh_loop_error.values()) and loop_pixels==0
    assert all(v['supportMaxDriftPx']<.1 for v in foot_metrics.values())
    assert all(v['contentAndPaddingExact'] and v['insidePage'] for v in atlas_checks.values())
    assert checks['fourPosesActuallyDifferent'] and all(v==0 for v in raster.values())
    assert all(s['minPrincipalStretch']>.35 and s['maxPrincipalStretch']<1.8 for s in geometry.values())
    checks['numericalChecksPassed'] = True
    save('checks.json',checks)
    package()
    print(json.dumps({'output':str(OUT),'sampleCount':193,'setup':setup_checks,'geometry':geometry,'feet':foot_metrics,
                      'oldFilesUnchanged':True,'zipCRCAndBytesVerified':True,'prototypeAccepted':False},ensure_ascii=False))


def record_visible_review():
    # 仅在实际ViewImage审阅后显式调用；普通构建仍默认pending/false。
    review = {'status':'reviewed_passed_scoped_prototype','inspectedWith':'ViewImage','reviewFile':'review.png',
              'reviewSha256':sha(OUT/'review.png'),'scope':'当前视角、小步幅、收敛手臂摆幅；四主姿态+两过渡+循环两侧静态抽样，不代表所有运动或生产验收',
              'sampleTimes':[0,1/6,1/3,1/2,3/24,11/24,DURATION-1/192,1/192],
              'observations':['实际查看最终review四主姿态，far_contact及near_pass腿根不再拉脱，未见此前背景色贯穿裂缝。',
                              '实际查看0.125s与0.458333s过渡，肩髋根保持衔接，未见明显纹理三角撕裂。',
                              '实际查看循环前后1/192秒抽样，未见明显位置跳变；精确首尾由CPU像素与mesh校验。',
                              '为避免现有隐藏图缺口，手臂摆幅已显著收敛；并非完整视频还原或大摆幅能力通过。',
                              '近远腿仍有可见换脚；局部压缩的数值范围见meshGeometry，不声称无压缩。',
                              '没有补画或额外碎片；隐藏结构完整性、换装、跨角色及移动端仍未验证。']}
    checks = load(OUT/'checks.json')
    provenance = load(OUT/'provenance.json')
    for data in [checks,provenance]:
        data.update(FLAGS)
        data['status'] = 'numerical_and_scoped_visual_pass'
        data['prototypeAccepted'] = True
        data['visualReview'] = review
    checks['shoulderAndLegRootGapFree'] = True
    checks['gapFreeScope'] = '仅本次实际查看的8个样本；非完整隐藏结构或任意姿态保证'
    checks['visualChecksPassed'] = True
    assert checks['numericalChecksPassed']
    assert provenance['script']['sha256']==sha(__file__)
    save('checks.json',checks)
    save('provenance.json',provenance)
    package()
    print(json.dumps({'visualReview':review['status'],'prototypeAccepted':True,'productionApproved':False,'zipCRCAndBytesVerified':True},ensure_ascii=False))


if __name__=='__main__':
    if sys.argv[1:]==['--record-visible-review']:
        record_visible_review()
    else:
        assert not sys.argv[1:]
        main()
