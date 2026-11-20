"""视频可见轮廓手工标注、固定长度双骨链和独立候选导出。"""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
import math
import zipfile
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
STABLE = RIG / 'stable_parts_v1'
REF = RIG / 'video_parts_v1/cycle_review'
OUT = RIG / 'video_guided_walk_v2'
SHA_JS = BASE / 'video-guided-source.js'
TASK = 'comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa'
PACKAGE = 'video_guided_walk_v2'
DURATION = 2/3
ORDER = ['leg_far','leg_near','body','shorts','arm_far','arm_near','head']
FLAGS = {k:False for k in ['prototypeAccepted','productionApproved','wardrobeVerified','crossCharacterVerified','mobileVerified']}
FILES = ['profile.json','profile_walk.json','provenance.json','checks.json','profile_walk.atlas','profile_walk.png','evidence.json']
spec = importlib.util.spec_from_file_location('profile_tools', BASE/'build_profile_walk.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
h.OUT = OUT
# 原图中的语义骨链，末端取可见手掌/脚背材料中心；肩肘膝髋均为绑定推断。
CHAINS = {
 'arm_near':[[350,456],[330,509],[317,549]],
 'arm_far':[[468,463],[485,500],[491,535]],
 'leg_near':[[359,576],[350,613],[357,647]],
 'leg_far':[[437,575],[445,607],[443,631]],
}
h.CHAINS = CHAINS
# 864x480原视频坐标。由已实际查看的17张源PNG人工估计，非自动关节提取。
# near/far只为候选屏幕层；隐藏后脚及手臂条目保留推断标签，不作观测拟合通过。
CENTERS = [[443,340],[444,341],[445,329],[445,326],[445,325],[445,323],[445,332],[443,338],[441,344],[439,347],[440,330],[439,324],[439,325],[439,326],[438,333],[440,338],[443,340]]
POINTS = {
 'arm_near':[[374,352],[389,361],[429,350],[450,339],[461,332],[472,325],[473,331],[469,341],[461,350],[447,358],[413,354],[393,350],[380,345],[370,339],[361,340],[363,347],[373,352]],
 'arm_far':[[526,330],[519,340],[504,338],[501,333],[498,329],[398,316],[398,324],[398,330],[398,338],[399,342],[514,342],[522,331],[528,319],[532,312],[533,315],[533,322],[527,331]],
 'leg_near':[[434,440],[425,440],[412,438],[400,435],[395,432],[387,422],[391,404],[395,409],[405,414],[414,415],[410,413],[422,421],[434,422],[443,423],[447,434],[444,439],[434,441]],
 'leg_far':[[458,412],[465,415],[470,415],[483,417],[495,418],[504,415],[509,426],[498,433],[487,435],[477,435],[459,432],[453,431],[461,416],[409,413],[402,408],[405,410],[458,413]],
}
VISIBLE = {
 'arm_near':[True]*17,
 'arm_far':[True,True,False,False,False,False,False,False,False,False,True,True,True,True,True,True,True],
 'leg_near':[True]*17,
 'leg_far':[False,False,True,True,True,True,True,True,True,True,True,True,False,True,True,False,False],
}
# 一个固定相似变换，不逐帧拉伸原角色：视频基准胸腹[443,340]对应原图[410,505]。
SCALE = 1.45

def mapped(p):
    return np.array([410,505]) + SCALE*(np.array(p,dtype=float)-[443,340])

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rel(p):
    return Path(p).resolve().relative_to(BASE).as_posix()

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def write_source_map():
    value = {PACKAGE+'/'+n:sha(OUT/n) for n in FILES}
    SHA_JS.write_text('window.CottonVideoGuidedSourceSha = '+json.dumps(value,indent=2)+';\n',encoding='utf-8')
    with zipfile.ZipFile(OUT/'video_guided_walk_v2.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in FILES+['review.png','review.gif']:
            if (OUT/n).is_file():
                z.write(OUT/n,n)
    with zipfile.ZipFile(OUT/'video_guided_walk_v2.zip') as z:
        assert z.testzip() is None
        assert all(z.read(n)==(OUT/n).read_bytes() for n in z.namelist())
    return value

def new_mesh(name,part,bind,bones,root_span=34,hinge_span=52):
    x0,y0,x1,y1 = part['bbox']
    xs=np.linspace(x0,x1,round((x1-x0)/8)+1)
    ys=np.linspace(y0,y1,round((y1-y0)/8)+1)
    pts=np.array([(x,y) for y in ys for x in xs])
    tris=[]
    cols=len(xs)
    for y in range(len(ys)-1):
        for x in range(cols-1):
            a=y*cols+x
            tris.extend([[a,a+1,a+cols+1],[a,a+cols+1,a+cols]])
    a,b,c=np.array(CHAINS[name],float)
    axis=(c-a)/np.linalg.norm(c-a)
    s=(pts-a)@axis
    elbow=(b-a)@axis
    # 近端搭接较旧包前移；终端保留纯lower，以便可见材料点确实跟随IK。
    u=np.clip((s+14)/root_span,0,1)
    limb=u*u*(3-2*u)
    v=np.clip((s-elbow+hinge_span/2)/hinge_span,0,1)
    lower=v*v*(3-2*v)
    weights=np.stack([1-limb,limb*(1-lower),limb*lower],axis=1)
    # 原图手掌/脚材料点附近保持末骨刚性，其他顶点仍按静态平滑权重过渡。
    terminal=np.linalg.norm(pts-c,axis=1)<15
    weights[terminal]=[0,0,1]
    data={'points':pts,'triangles':np.array(tris,int),'uv':(pts-[x0,y0])/[x1-x0,y1-y0],
          'weights':weights,'chain':['body',name+'_upper',name+'_lower'],'rootSpan':root_span,'hingeSpan':hinge_span}
    return encode_mesh(name,part,data,bind,bones),data

def encode_mesh(name,part,data,bind,bones):
    hom=np.column_stack([h.screen(data['points']),np.ones(len(data['points']))])
    local=np.stack([(hom@np.linalg.inv(bind[b]).T)[:,:2] for b in data['chain']],axis=1)
    indices={b['name']:i for i,b in enumerate(bones)}
    stream=[]
    for i in range(len(hom)):
        active=np.flatnonzero(data['weights'][i]>1e-12)
        stream.append(len(active))
        for j in active:
            stream += [indices[data['chain'][j]],float(local[i,j,0]),float(local[i,j,1]),float(data['weights'][i,j])]
    return {'type':'mesh','path':name,'uvs':data['uv'].ravel().tolist(),'triangles':data['triangles'].ravel().tolist(),
            'vertices':stream,'width':part['width'],'height':part['height']}

def make_motion(skeleton):
    bones={b['name']:b for b in skeleton['bones']}
    channels={'body':{'translate':[]}}
    inferred={}
    for i,center in enumerate(CENTERS):
        d=SCALE*(np.array(center)-CENTERS[0])
        channels['body']['translate'].append({'time':i/24,'x':float(d[0]),'y':float(-d[1])})
    for name,j in CHAINS.items():
        a,b,c=np.array(j,float)
        l1=np.linalg.norm(b-a);l2=np.linalg.norm(c-b)
        upper=math.atan2(*(b-a)[::-1]); lower=math.atan2(*(c-b)[::-1])
        values=[]; rows=[]
        last=None
        for i,point in enumerate(POINTS[name]):
            body_shift=SCALE*(np.array(CENTERS[i])-CENTERS[0])
            root=a+body_shift
            target=mapped(point)
            vector=target-root
            distance=np.linalg.norm(vector)
            reach=np.clip(distance,abs(l1-l2)+.3,l1+l2-.3)
            direction=math.atan2(vector[1],vector[0])
            elbow=math.acos(np.clip((reach*reach-l1*l1-l2*l2)/(2*l1*l2),-1,1))
            candidates=[]
            for sign in [-1,1]:
                q2=sign*elbow
                q1=direction-math.atan2(l2*math.sin(q2),l1+l2*math.cos(q2))
                while q1-upper>math.pi:q1-=2*math.pi
                while q1-upper<-math.pi:q1+=2*math.pi
                # 近臂胸前曲肘向下外凸；其它链选最接近上一帧的分支。
                preference = -1 if name=='arm_far' else 1
                cost=(q1-upper)**2+q2*q2*.2 if last is None else (q1-last[0])**2+(q2-last[1])**2
                cost += 10 if sign!=preference else 0
                candidates.append((cost,q1,q2))
            _,q1,q2=min(candidates)
            last=(q1,q2)
            # screen y-down角度反号后转为Spine y-up；lower为相对角。
            values.append([math.degrees(upper-q1),math.degrees((lower-upper)-q2)])
            e=root+l1*np.array([math.cos(q1),math.sin(q1)])
            end=e+l2*np.array([math.cos(q1+q2),math.sin(q1+q2)])
            rows.append({'frame':68+i,'time':i/24,'visibleTarget':bool(VISIBLE[name][i]),
                         'videoPoint':point,'mappedTarget':target.tolist(),'inferredRoot':root.tolist(),
                         'inferredJoint':e.tolist(),'projectedBoneEndpoint':end.tolist(),
                         'fixedLengthProjectionResidualPx':float(np.linalg.norm(end-target)),
                         'jointObservation':False})
        # 只在最后四帧分布闭环角度修正，原始84目标保留，真实残差稍后从导出材料点测量。
        original=np.array(values,float)
        correction=original[-1]-original[0]
        for i in range(13,17):
            values[i]=(original[i]-correction*((i-12)/4)).tolist()
        channels[name+'_upper']={'rotate':[{'time':i/24,'value':float(v[0])} for i,v in enumerate(values)]}
        channels[name+'_lower']={'rotate':[{'time':i/24,'value':float(v[1])} for i,v in enumerate(values)]}
        inferred[name]={'rows':rows,'rawAnglesDegrees':original.tolist(),'closureCorrectionDegrees':correction.tolist(),
                        'upperLength':float(l1),'lowerLength':float(l2)}
    skeleton['animations']={'walk':{'bones':channels},'setup':{'bones':{}}}
    return inferred

def optimize_weights(name,data,skeleton,bind,part,bones):
    # 静态weights优化只改绑定，不改目标或动画幅度；所有采样均来自同一套骨链。
    pts=data['points'];tri=data['triangles'];original=data['weights'].copy();nv=len(pts)
    hom=np.column_stack([h.screen(pts),np.ones(nv)])
    times=np.linspace(0,DURATION,193)
    transforms=[]
    for t in times:
        world=h.solve(skeleton,'walk',float(t))
        transforms.append(np.stack([(hom@(world[b]@np.linalg.inv(bind[b])).T)[:,:2] for b in data['chain']],axis=1))
    coords=np.array(transforms)
    base_area=h.cross(hom[tri[:,1],:2]-hom[tri[:,0],:2],hom[tri[:,2],:2]-hom[tri[:,0],:2])
    # 以softmax静态变量约束非负归一；纯body与手脚材料区锁定，不能通过缩小动作骗过检测。
    locked=(original[:,0]>.999999)|(original[:,2]>.999999)
    free=np.flatnonzero(~locked)
    if not len(free):return {'attempted':False}
    x0=np.log(np.maximum(original[free,:2],.001)/np.maximum(original[free,2:3],.001)).ravel()
    edges=np.unique(np.sort(np.vstack([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
    def unpack(x):
        logits=np.column_stack([x.reshape(-1,2),np.zeros(len(free))])
        logits-=logits.max(axis=1,keepdims=True)
        exp=np.exp(logits)
        w=original.copy();w[free]=exp/exp.sum(axis=1,keepdims=True)
        return w
    def residual(x):
        w=unpack(x)
        dst=(coords*w[None,:,:,None]).sum(axis=2)
        ratio=h.cross(dst[:,tri[:,1]]-dst[:,tri[:,0]],dst[:,tri[:,2]]-dst[:,tri[:,0]])/base_area
        area=np.maximum(.16-ratio,0)*40
        regular=(w-original)*.003
        smooth=(w[edges[:,0]]-w[edges[:,1]])*.005
        return np.r_[area.ravel(),regular.ravel(),smooth.ravel()]
    nr=len(times)*len(tri)+nv*3+len(edges)*3
    sparsity=lil_matrix((nr,len(free)*2),dtype=int)
    lookup={int(v):i for i,v in enumerate(free)}
    for ti,t in enumerate(tri):
        for v in t:
            if int(v) in lookup:
                k=lookup[int(v)]*2
                for phase in range(len(times)):
                    sparsity[phase*len(tri)+ti,k:k+2]=1
    off=len(times)*len(tri)
    for v,k in lookup.items():sparsity[off+v*3:off+v*3+3,k*2:k*2+2]=1
    off+=nv*3
    for i,edge in enumerate(edges):
        for v in edge:
            if int(v) in lookup:
                k=lookup[int(v)]*2;sparsity[off+i*3:off+i*3+3,k:k+2]=1
    result=least_squares(residual,x0,jac_sparsity=sparsity.tocsr(),max_nfev=180,ftol=1e-5,xtol=1e-5,gtol=1e-5)
    data['weights']=unpack(result.x)
    recovery={'attempted':False}
    if name=='leg_near':
        # softmax饱和时改用单纯形上的直接变量，逐三角约束最坏相位；不改变骨链或材料点。
        from scipy.optimize import minimize
        start=data['weights'].copy()
        lookup=np.full(nv,-1,dtype=int);lookup[free]=np.arange(len(free))
        delta=coords[:,:,:2,:]-coords[:,:,2:3,:]
        def direct_weights(x):
            w=start.copy();w[free,:2]=x.reshape(-1,2)
            w[free,2]=1-w[free,:2].sum(axis=1)
            return w
        def area_constraints(x):
            w=direct_weights(x);dst=(coords*w[None,:,:,None]).sum(axis=2)
            a,b,c=(dst[:,tri[:,j]] for j in range(3))
            ratio=h.cross(b-a,c-a)/base_area
            phase=ratio.argmin(axis=0);indices=np.arange(len(tri))
            gradient=np.stack([
                np.stack([b[:,:,1]-c[:,:,1],c[:,:,0]-b[:,:,0]],axis=-1),
                np.stack([c[:,:,1]-a[:,:,1],a[:,:,0]-c[:,:,0]],axis=-1),
                np.stack([a[:,:,1]-b[:,:,1],b[:,:,0]-a[:,:,0]],axis=-1)],axis=2)/base_area[None,:,None,None]
            jac=np.zeros((len(tri),len(free)*2))
            for corner in range(3):
                vertices=tri[:,corner];eligible=lookup[vertices]>=0
                rows=indices[eligible];columns=lookup[vertices[eligible]]*2
                g=gradient[phase[eligible],rows,corner]
                change=delta[phase[eligible],vertices[eligible]]
                for j in range(2):jac[rows,columns+j]=np.sum(g*change[:,j,:],axis=1)
            return ratio[phase,indices],jac
        x_start=start[free,:2].ravel()
        before_ratio,_=area_constraints(x_start)
        if before_ratio.min()<.02:
            cache={}
            def evaluate(x):
                if 'x' not in cache or not np.array_equal(cache['x'],x):
                    cache.update(x=x.copy(),value=area_constraints(x))
                return cache['value']
            sum_jac=np.zeros((len(free),len(free)*2))
            for i in range(len(free)):sum_jac[i,i*2:i*2+2]=-1
            constraints=[{'type':'ineq','fun':lambda x:1-x.reshape(-1,2).sum(axis=1),'jac':lambda x:sum_jac},
                         {'type':'ineq','fun':lambda x:evaluate(x)[0]-.02,'jac':lambda x:evaluate(x)[1]}]
            refined=minimize(lambda x:float(np.sum((x-x_start)**2)),x_start,
                             jac=lambda x:2*(x-x_start),method='SLSQP',bounds=[(0,1)]*len(x_start),
                             constraints=constraints,options={'maxiter':300,'ftol':1e-10})
            candidate=direct_weights(refined.x)
            valid=bool(np.isfinite(candidate).all() and candidate.min()>=-1e-10)
            # 独立加密8倍复核，不因求解器报告成功便接受；失败时保留原候选并如实报告。
            dense_min=1e9;dense_flips=0
            if valid:
                candidate=np.maximum(candidate,0);candidate/=candidate.sum(axis=1,keepdims=True)
                for t in np.linspace(0,DURATION,1537):
                    world=h.solve(skeleton,'walk',float(t))
                    transformed=np.stack([(hom@(world[b]@np.linalg.inv(bind[b])).T)[:,:2] for b in data['chain']],axis=1)
                    dst=(transformed*candidate[:,:,None]).sum(axis=1)
                    ratio=h.cross(dst[tri[:,1]]-dst[tri[:,0]],dst[tri[:,2]]-dst[tri[:,0]])/base_area
                    dense_min=min(dense_min,float(ratio.min()));dense_flips+=int((ratio<0).sum())
            accepted=bool(valid and refined.success and dense_flips==0 and dense_min>.005)
            if accepted:data['weights']=candidate
            recovery={'attempted':True,'solver':'SLSQP static simplex weights with analytic signed-area constraints',
                      'success':bool(refined.success),'accepted':accepted,'iterations':int(refined.nit),
                      'beforeMinAreaRatio':float(before_ratio.min()),'denseSampleCount':1537,
                      'denseMinAreaRatio':float(dense_min) if valid else None,'denseFlips':dense_flips if valid else None,
                      'lockedRootAndTerminalWeightsPreserved':bool(np.array_equal(data['weights'][locked],original[locked]))}
    return {'attempted':True,'solver':'scipy sparse least_squares static softmax weights','nfev':result.nfev,
            'finalCost':float(result.cost),'targetsOrAnglesReduced':False,'optimizedVertexCount':len(free),
            'signedAreaRecovery':recovery}

def safe_render_mesh(source,mesh,world):
    # 失败网格也要导出真实审阅：保留翻转三角形贴图，反转其栅格绕序以便绘制，不修改Spine数据。
    stats,dst=h.mesh_geometry(mesh,world)
    canvas=np.zeros((768,768,4),np.float32);coverage=np.zeros((768,768),np.uint16)
    dst=h.screen(dst)
    for tr in mesh['triangles']:
        d=dst[tr];src=mesh['source'][tr]
        area=h.cross(d[1]-d[0],d[2]-d[0])
        if abs(area)<1e-7:continue
        if area<0:d=d[[0,2,1]];src=src[[0,2,1]]
        lo=np.maximum(np.floor(d.min(axis=0)).astype(int)-1,0)
        hi=np.minimum(np.ceil(d.max(axis=0)).astype(int)+1,768)
        x0,y0=lo;x1,y1=hi
        if x1<=x0 or y1<=y0:continue
        mat=cv2.getAffineTransform(src.astype(np.float32),(d-.5-lo).astype(np.float32))
        warped=cv2.warpAffine(source,mat,(int(x1-x0),int(y1-y0)),flags=cv2.INTER_LINEAR)
        xx,yy=np.meshgrid(np.arange(x0,x1)+.5,np.arange(y0,y1)+.5)
        pixels=np.stack([xx,yy],axis=-1);owned=np.ones(xx.shape,bool)
        for a,b in zip(d,np.roll(d,-1,axis=0)):
            edge=b-a;e=h.cross(edge,pixels-a)
            top_left=edge[1]<0 or (abs(edge[1])<1e-10 and edge[0]>0)
            owned&=(e>1e-7)|((np.abs(e)<=1e-7)&top_left)
        canvas[y0:y1,x0:x1][owned]=warped[owned]
        coverage[y0:y1,x0:x1]+=owned.astype(np.uint16)
    stats['interiorOverlapPixels']=int((coverage>1).sum())
    return canvas,stats

h.render_mesh=safe_render_mesh

def build():
    assert BASE.is_dir() and RIG.is_dir() and REF.is_dir() and STABLE.is_dir()
    allowed=set(FILES+['review.png','review.gif','video_guided_walk_v2.zip'])
    if OUT.exists():assert all(p.name in allowed for p in OUT.iterdir())
    else:OUT.mkdir()
    # 只为本候选目录显式允许重建；旧研究目录从不写入。
    protected=[p for directory in [STABLE,RIG/'profile_walk_v1',RIG/'video_parts_v1'] for p in directory.rglob('*') if p.is_file()]
    before={p:sha(p) for p in protected}
    stable=load(STABLE/'manifest.json');sources=load(REF/'sources.json')
    assert sha(RIG/'source.mp4')==sources['sourceVideoSha256']
    cap=cv2.VideoCapture(str(RIG/'source.mp4'));assert cap.isOpened()
    decoded=[]
    for i in range(85):
        ok,bgr=cap.read();assert ok
        if i>=68:
            record=next(r for r in sources['frames'] if r['sourceFrame']==i)
            p=REF/record['sourceFile'];assert sha(p)==record['sourceFrameSha256']
            assert np.array_equal(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),np.asarray(Image.open(p).convert('RGB')))
            decoded.append({'frame':i,'file':rel(p),'sha256':sha(p),'decodedPixelsExact':True})
    assert abs(cap.get(cv2.CAP_PROP_FPS)-24)<1e-5
    cap.release()
    parts={p['id']:p for p in stable['parts']};images={};stable_hashes=[]
    for n,p in parts.items():
        path=STABLE/p['file'];actual=sha(path);assert actual==p['sha256']
        images[n]=Image.open(path).convert('RGBA')
        stable_hashes.append({'id':n,'file':rel(path),'expectedSha256':p['sha256'],'actualSha256':actual})
    page,regions=h.pack({n:images[n] for n in ORDER})
    bones=h.make_bones()
    skeleton={'skeleton':{'spine':'4.2.00','width':768,'height':768,'images':'./'},'bones':bones,
              'slots':[],'skins':[{'name':'default','attachments':{}}],'animations':{}}
    bind=h.solve(skeleton,'setup',0);skin=skeleton['skins'][0]['attachments'];designed={}
    for n in ORDER:
        if n in CHAINS:
            attachment,designed[n]=new_mesh(n,parts[n],bind,bones);bone=n+'_upper'
        else:
            x0,y0,x1,y1=parts[n]['bbox'];px,py=h.PIVOTS[n]
            attachment={'type':'region','path':n,'x':(x0+x1)/2-px,'y':py-(y0+y1)/2,'width':x1-x0,'height':y1-y0};bone=n
        skin[n]={n:attachment};skeleton['slots'].append({'name':n,'bone':bone,'attachment':n})
    inference=make_motion(skeleton)
    attempts={}
    for n,data in designed.items():
        initial= h.decode_meshes(skeleton,regions)[n]
        pre=[h.mesh_geometry(initial,h.solve(skeleton,'walk',i*DURATION/192))[0] for i in range(193)]
        attempts[n]={'beforeOptimizationFlips':sum(g['flips'] for g in pre),'beforeMinAreaRatio':min(g['minAreaRatio'] for g in pre)}
        if attempts[n]['beforeMinAreaRatio']<.10:
            attempts[n].update(optimize_weights(n,data,skeleton,bind,parts[n],bones))
            skin[n][n]=encode_mesh(n,parts[n],data,bind,bones)
        else:attempts[n]['attempted']=False
    save('profile_walk.json',skeleton)
    # 实际导出的weighted vertices与atlas再次从磁盘解析，不能用设计内存代替导出验证。
    skeleton=load(OUT/'profile_walk.json');page,regions=h.read_atlas();meshes=h.decode_meshes(skeleton,regions)
    material={n:h.material_binding(meshes[n],h.yup(CHAINS[n][-1])) for n in CHAINS}
    geometry={n:{'flips':0,'collapsed':0,'minAreaRatio':1e9,'maxAreaRatio':0,'minPrincipalStretch':1e9,'maxPrincipalStretch':0} for n in meshes}
    loop={};trajectory={n:[] for n in meshes};setup={}
    for n,m in meshes.items():
        setup[n]={'maxReconstructionErrorPx':float(np.linalg.norm(m['bind']-h.screen(designed[n]['points']),axis=1).max()),
                  'maxWeightSumError':float(max(abs(sum(w for b,p,w in r)-1) for r in m['influences'])),
                  'finiteNonnegativeWeights':bool(all(np.isfinite(w) and w>=0 for r in m['influences'] for b,p,w in r))}
        loop[n]=float(np.linalg.norm(h.vertices_world(m,h.solve(skeleton,'walk',0))-h.vertices_world(m,h.solve(skeleton,'walk',DURATION)),axis=1).max())
    for i in range(193):
        t=DURATION*i/192;world=h.solve(skeleton,'walk',t)
        for n,m in meshes.items():
            g,dst=h.mesh_geometry(m,world);acc=geometry[n]
            for k in ['flips','collapsed']:acc[k]+=g[k]
            acc['minAreaRatio']=min(acc['minAreaRatio'],g['minAreaRatio']);acc['maxAreaRatio']=max(acc['maxAreaRatio'],g['maxAreaRatio'])
            tri=m['triangles'];a=m['bind'][tri];b=dst[tri]
            ae=np.stack([a[:,1]-a[:,0],a[:,2]-a[:,0]],axis=-1);be=np.stack([b[:,1]-b[:,0],b[:,2]-b[:,0]],axis=-1)
            sv=np.linalg.svd(be@np.linalg.inv(ae),compute_uv=False)
            acc['minPrincipalStretch']=min(acc['minPrincipalStretch'],float(sv.min()));acc['maxPrincipalStretch']=max(acc['maxPrincipalStretch'],float(sv.max()))
            trajectory[n].append(h.screen(h.material_position(m,world,material[n])).tolist())
    residuals=[]
    for n in CHAINS:
        for i,row in enumerate(inference[n]['rows']):
            w=h.solve(skeleton,'walk',i/24);actual=h.screen(h.material_position(meshes[n],w,material[n]))
            row.update({'exportedMaterialPoint':actual.tolist(),'materialResidualPx':float(np.linalg.norm(actual-row['mappedTarget'])),
                        'videoEquivalentResidualPx':float(np.linalg.norm(actual-row['mappedTarget'])/SCALE)})
            residuals.append({'part':n,**row})
    noflips=all(g['flips']==0 and g['collapsed']==0 for g in geometry.values())
    limitations=['七件纹理均为稳定静态原图素材；body保留既有4095px AI供体搭接，本构建不新增纹理、不从视频裁片、不补全隐藏面。',
      '肩、肘、髋、膝为语义双骨链推断，不是自动关节提取或直接观测；near/far不确立解剖左右或跨帧身份。',
      '采用单一1.45倍映射，固定原图骨长和纹理比例，AI视频的转面/扁脚/逐帧比例变化没有照搬；误差逐点如实保留。',
      '原侧臂可见纹理弯到胸前有隐藏轮廓缺失和切口外露风险；数值无翻转不能替代造型匹配。',
      '68/84只是候选周期；81–84分布角度闭环修正使数值循环成立，不等于视频闭环成立。',
      'CPU导出解算未通过Spine官方运行时、换装、跨角色、移动端或生产验收。']
    part_notes={
      'head':('68/72/76/80/84完整源PNG的头发、面部、耳朵外轮廓可见；保持原图头部比例，不匹配AI表情。','头颈连接/头部背面不可完整观测。'),
      'body':('68/80/84两臂展开时胸腹外轮廓可见，70–77胸前臂覆盖身体。','弯臂下方、腋下及肩根被遮挡；隐藏身体不从其它帧替换。'),
      'shorts':('各帧腰线、裤口及交叉腿上缘可见，用于独立region与腿根层次复核。','手臂和腿遮挡部分裤口，静态原图粗切边不声称逐帧准确。'),
      'arm_near':('68–69外侧圆形末端；70–76胸前前臂/手掌可见轮廓向屏幕右收，77下降，78–84展开。','肩、肘内部位置不可确立；骨链关节是推断，材料点是圆形手部轮廓人工近似。'),
      'arm_far':('68–69与78–84屏幕右侧圆手可见；74后侧窄边可见。','70–73/75–77完整手部不可见，目标标为推断；不当作可见观测计入拟合结论。'),
      'leg_near':('68/80/84前层脚，72两腿展开；74–77屏幕左脚变扁转面，78前腿抬起。','髋、膝隐藏，腿脚相接处有AI形变；材料点为脚下部中心近似，不是物理标记。'),
      'leg_far':('70–79两脚下部有可见外轮廓，81–82可见后脚残片。','68–69/80/83–84后脚大部分遮挡；目标是推断，不声称完整轮廓或接地。')}
    evidence={'schemaVersion':1,'taskId':TASK,'packageId':PACKAGE,'characterId':None,
       'parts':[{'id':n,'frames':[r for r in decoded if r['frame'] in [68,70,72,74,76,77,78,80,81,82,84]],
                 'visibleBasis':part_notes[n][0],'occlusion':part_notes[n][1],'limitations':limitations[:4]} for n in ORDER],
       'annotationMethod':'已用ViewImage实际查看两张contact及source_068..084全部17PNG后手工估计轮廓点，非自动关节提取。',
       'reviewedContacts':[{'file':rel(REF/n),'sha256':sha(REF/n)} for n in ['contact_068_075.jpg','contact_076_084.jpg']],
       'videoFrames':decoded,'mapping':{'videoSize':[864,480],'targetCanvas':[768,768],'origin':'top-left y-down',
          'rule':'p_target=[410,505]+1.45*(p_video-[443,340]); body位移=1.45*(每帧胸腹中心-[443,340]); 单一等比映射，骨长不变。',
          'uniformScale':SCALE,'videoAnchor':[443,340],'sourceAnchor':[410,505],'torsoCenterVideoPixels':CENTERS,
          'manualVisiblePointUncertaintyVideoPx':[4,8],'inferredHiddenPointUncertaintyVideoPx':[12,25],
          'uncertaintyIsNotMeasuredAccuracy':True,'materialDefinition':'静态原图末端材料中心以重心坐标绑定mesh；视频脚/手轮廓中心为代理，不宣称真实跨帧物理点。'},
       'pointAnnotations':residuals,'boneInference':inference,'textureSource':'stable_parts_v1静态原图七件，并非视频裁片/隐藏补全。'}
    save('evidence.json',evidence)
    profile={'schemaVersion':1,'profileId':PACKAGE,'characterId':None,'sourceDirection':stable['direction'],
       'root':{'sourcePixelsTopLeft':[390,532],'setupYUp':[390,236]},
       'coordinateContract':'Spine y-up=768-source_y; UV局部0..1; 视频到原图为evidence中单一相似映射。',
       'proportions':{'canvas':[768,768],'partsBbox':{n:parts[n]['bbox'] for n in ORDER},'pivots':h.PIVOTS,'limbChainsSourcePixels':CHAINS},
       'bind':{'bones':bones,'slots':skeleton['slots'],'attachments':skin},
       'mesh':{n:{'verticesSourcePixels':d['points'].tolist(),'triangles':d['triangles'].tolist(),'weights':d['weights'].tolist(),
                  'regionUV':d['uv'].tolist(),'boneOrder':d['chain'],'weightBoneOrder':d['chain'],'bindingMode':'双骨链+body近端锚',
                  'staticWeights':True,'weightRule':'近端沿轴-14起body搭接，静态softmax权重优化避免翻折，末端材料区域锁定lower；不缩小运动目标。',
                  'optimization':attempts[n]} for n,d in designed.items()},
       'textureMapping':{'page':'profile_walk.png','atlas':'profile_walk.atlas','regions':regions,'newTexturePixels':0,'oldWeightsReused':False},
       'clothingChainContract':{'headBodyShorts':'region','sleeves':'衣袖必须用独立mesh/UV/静态weights，共用对应arm上下双骨链，可用现有body根锚；不强制同UV或同权重。','sleevesAdded':False,'wardrobeVerified':False},
       'motionSeparated':True,'motionFile':'profile_walk.json','motionPhasesStoredHere':False}
    save('profile.json',profile)
    visible_res=[r['materialResidualPx'] for r in residuals if r['visibleTarget']]
    maxr=max((r for r in residuals if r['visibleTarget']),key=lambda r:r['materialResidualPx'])
    rawclosure={n:{'videoPointDeltaPx':float(np.linalg.norm(np.array(POINTS[n][-1])-POINTS[n][0])),
                   'mappedTargetDeltaPx':float(np.linalg.norm(mapped(POINTS[n][-1])-mapped(POINTS[n][0]))),
                   'rawProjectedEndpointDeltaPx':float(np.linalg.norm(np.array(inference[n]['rows'][-1]['projectedBoneEndpoint'])-inference[n]['rows'][0]['projectedBoneEndpoint'])),
                   'distributedAngleCorrectionDegrees':inference[n]['closureCorrectionDegrees'],
                   'finalMaterialResidualAt84Px':inference[n]['rows'][-1]['materialResidualPx'],
                   'finalMaterialLoopErrorPx':loop[n]} for n in CHAINS}
    visual={'status':'pending_generated_review','inspectedWith':None,'productionAcceptance':False}
    provenance={'schemaVersion':1,'taskId':TASK,'packageId':PACKAGE,'characterId':None,**FLAGS,'status':'candidate_pending_visual_review',
       'stableManifest':{'file':rel(STABLE/'manifest.json'),'sha256':sha(STABLE/'manifest.json')},'stableParts':stable_hashes,
       'reference':{'fps':24,'video':rel(RIG/'source.mp4'),'videoSha256':sha(RIG/'source.mp4'),
                    'sources':{'file':rel(REF/'sources.json'),'sha256':sha(REF/'sources.json')},'evidence':{'file':'evidence.json','sha256':sha(OUT/'evidence.json')}},
       'motion':{'method':'可见轮廓中心人工坐标目标→固定长度语义双骨IK分支→81–84有限闭环修正；无手填摆幅替代视频目标。',
                 'duration':DURATION,'targetFrames':list(range(68,85)),'automaticJointExtraction':False,'isIK':True,
                 'mapping':'固定等比1.45，原图比例不随AI每帧变化','closure':rawclosure,
                 'maxVisibleMaterialResidualPx':max(visible_res),'rmsVisibleMaterialResidualPx':float(np.sqrt(np.mean(np.square(visible_res)))),
                 'maxResidualExample':maxr,'numericalLoopDoesNotProveVideoFit':True},
       'textureStatement':limitations[0],'rendering':'从磁盘Spine JSON weighted vertices和atlas解码；CPU逐三角纹理采样；失败三角仅调整栅格绕序显示，不更改导出。',
       'visualReview':visual,'limitations':limitations,'script':{'file':rel(__file__),'sha256':sha(__file__)}}
    save('provenance.json',provenance)
    unchanged=all(sha(p)==digest for p,digest in before.items());assert unchanged
    checks={'schemaVersion':1,**FLAGS,'status':'candidate_pending_visual_review','boneCount':len(bones),'slotCount':len(skeleton['slots']),'meshCount':len(meshes),
       'spineVersion':'4.2.00','duration':DURATION,'cycleSampleCount':193,'meshGeometry':geometry,'weightOptimization':attempts,
       'setupWeightedReconstruction':setup,'firstLastMeshMaxErrorPx':loop,'meshNoFlipsPassed':noflips,
       'numericalChecksPassed':bool(noflips and max(loop.values())<1e-8 and all(v['maxReconstructionErrorPx']<1e-8 for v in setup.values())),
       'allSevenStablePartsHashVerified':True,'stableManifestUnchanged':sha(STABLE/'manifest.json')==before[STABLE/'manifest.json'],
       'protectedOldFilesUnchanged':unchanged,'protectedOldFileCount':len(before),'sourceVideoSHAAnd17DecodedFramesVerified':len(decoded)==17,
       'profileBindEqualsRuntime':bool(profile['bind']['bones']==skeleton['bones'] and profile['bind']['slots']==skeleton['slots'] and profile['bind']['attachments']==skeleton['skins'][0]['attachments']),
       'fixedLimbLengths':True,'noLimbTranslationOrScaleTimelines':all('translate' not in ch and 'scale' not in ch for n,ch in skeleton['animations']['walk']['bones'].items() if n!='body'),
       'noDeformTimeline':True,'visibleTargetFit':{'maxResidualPx':max(visible_res),'rmsResidualPx':float(np.sqrt(np.mean(np.square(visible_res)))),
          'withinMappedManualUncertainty11_6Px':bool(max(visible_res)<=8*SCALE),'maxResidualExample':maxr},
       'videoFitPassed':False,'videoLoopCandidateAccepted':False,'closureResiduals':rawclosure,
       'officialSpineImportVerified':False,'shoulderAndLegRootGapFree':False,'visualReview':visual,'limitations':limitations}
    save('checks.json',checks)
    render_review(skeleton,page,regions,meshes,geometry,residuals)
    hashes=write_source_map()
    print(json.dumps({'output':str(OUT),'geometry':geometry,'maxResidual':maxr,'closure':rawclosure,'sourceMap':hashes,'flags':FLAGS},ensure_ascii=False))

def render_review(skeleton,page,regions,meshes,geometry,residuals):
    fontfile='C:/Windows/Fonts/msyh.ttc';font=ImageFont.truetype(fontfile,16);title=ImageFont.truetype(fontfile,24)
    sheet=Image.new('RGB',(1750,1400),'#eaf0f5');d=ImageDraw.Draw(sheet)
    d.text((20,12),'VIDEO-GUIDED V2 / 视频可见点 → 固定骨长候选 / 尚未验收',font=title,fill='#19334b')
    frames=[];rasters={}
    for i in range(17):
        im,stats=h.render(skeleton,page,regions,meshes,'walk',i/24);frames.append(im)
        rasters[str(68+i)]=stats
    for column,i in enumerate([0,2,4,8,9,12,16]):
        x=column*250
        d.text((x+12,52),f'f{68+i} / t={i/24:.4f}s',font=font,fill='#19334b')
        ref=Image.open(REF/f'source_{68+i:03d}.png').convert('RGB')
        crop=ref.crop((330,270,555,465)).resize((225,195))
        dc=ImageDraw.Draw(crop)
        for n in CHAINS:
            p=POINTS[n][i];q=(p[0]-330,p[1]-270);color='#e04b30' if VISIBLE[n][i] else '#8a8a8a'
            dc.ellipse((q[0]-3,q[1]-3,q[0]+3,q[1]+3),outline=color,width=2)
        sheet.paste(crop,(x+10,82))
        bg=Image.new('RGBA',(230,320),'#ffffff');bg.alpha_composite(frames[i].crop((160,90,620,730)).resize((230,320)))
        sheet.paste(bg.convert('RGB'),(x+10,292))
        detail=Image.new('RGBA',(230,290),'#edf2f7');detail.alpha_composite(frames[i].crop((265,420,530,710)).resize((230,252)),(0,0))
        dd=ImageDraw.Draw(detail);world=h.solve(skeleton,'walk',i/24)
        for n in CHAINS:
            upper=world[n+'_upper'];lower=world[n+'_lower'];length=next(b['length'] for b in skeleton['bones'] if b['name']==n+'_lower')
            ps=[h.screen(upper[:2,2]),h.screen(lower[:2,2]),h.screen((lower@np.array([length,0,1]))[:2])]
            ps=[((p[0]-265)*230/265,(p[1]-420)*252/290) for p in ps]
            dd.line(ps,fill='#267fab',width=2)
            for px,py in ps:dd.ellipse((px-2,py-2,px+2,py+2),fill='#143a57')
            r=next(r for r in residuals if r['part']==n and r['frame']==68+i);p=r['mappedTarget']
            px=(p[0]-265)*230/265;py=(p[1]-420)*252/290
            dd.ellipse((px-3,py-3,px+3,py+3),outline='#e04b30',width=2)
        sheet.paste(detail.convert('RGB'),(x+10,627))
        vals=[r['materialResidualPx'] for r in residuals if r['frame']==68+i and r['visibleTarget']]
        d.text((x+10,920),f'可见材料点最大残差 {max(vals):.1f}px',font=font,fill='#8b472e')
    d.text((20,965),'上：视频轮廓人工标注（红=可见，灰=推断）；中：导出weighted mesh；下：蓝骨链/红目标。',font=font,fill='#19334b')
    d.text((20,994),'观察范围包含胸前弯臂70–77和过渡；同一套静态网格，无逐帧碎片/修形。固定原图骨长，不照搬AI扁脚和转面。',font=font,fill='#8b472e')
    for column,i in enumerate([1,3,5,6,7,10,11,13,14,15]):
        x=column*174+5
        tile=Image.new('RGBA',(165,226),'white');tile.alpha_composite(frames[i].crop((200,400,545,720)).resize((165,153)))
        sheet.paste(tile.convert('RGB'),(x,1030));d.text((x+5,1190),f'过渡f{68+i}',font=font,fill='#19334b')
    d.text((20,1272),'193相位翻转总数 '+str(sum(v['flips'] for v in geometry.values()))+'；数值循环与视频拟合分别报告；所有验收标志保持false。',font=font,fill='#8b472e')
    sheet.save(OUT/'review.png')
    gif=[]
    for im in frames[:-1]:
        bg=Image.new('RGBA',(768,768),'white');bg.alpha_composite(im)
        gif.append(bg.convert('RGB').resize((460,460)))
    gif[0].save(OUT/'review.gif',save_all=True,append_images=gif[1:],duration=[42,41,42]*5+[42],loop=0,disposal=2)
    checks=load(OUT/'checks.json');checks['meshRasterSamples']=rasters
    checks['firstLastRenderMismatchPixels']=int(np.any(np.asarray(frames[0])!=np.asarray(frames[-1]),axis=2).sum())
    checks['reviewPoseFrames']=[68,70,72,76,77,80,84];checks['reviewTransitionFrames']=[69,71,73,74,75,78,79,81,82,83]
    save('checks.json',checks)

def record_review():
    # 仅在外部已实际ViewImage查看导出review后调用。
    review={'status':'actually_reviewed_candidate_failed_video_match','inspectedWith':'ViewImage','file':'review.png','sha256':sha(OUT/'review.png'),
      'scope':'7主姿态含68/72/76/80/84及10过渡的真实导出图，蓝色骨链/红色目标与原视频对照。',
      'observations':['动作已由视频可见点驱动而非旧小摆幅；胸前收臂与换脚有明显变化。',
                      '原图肩根/腿根及侧臂纹理不足，视频转面与胸前圆手轮廓不能仅凭当前静态四mesh完整复现。',
                      '最终193相位仍有近腿12个三角×相位翻转，最小面积比-0.1009817864；74–77过渡腿口/肩根切口和轮廓扭曲可见。',
                      '最大可见材料点残差36.6414px（视频等价25.2700px），出现在f74 leg_far；数值循环误差0并不代表视频复现通过。',
                      '更强权重及反向膝弯分支已实际试验，反向分支造成更明显腿根拉脱，最终保留原分支较优失败候选。'],
      'passed':False}
    for name in ['checks.json','provenance.json']:
        data=load(OUT/name);data['visualReview']=review;data['status']='candidate_reviewed_not_accepted';data.update(FLAGS)
        if name=='provenance.json':data['script']['sha256']=sha(__file__)
        save(name,data)
    write_source_map()
    print(json.dumps(review,ensure_ascii=False))

if __name__=='__main__':
    if sys.argv[1:]==['--record-reviewed']:record_review()
    else:
        assert not sys.argv[1:]
        build()
