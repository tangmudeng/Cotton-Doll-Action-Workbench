"""冻结v2绑定，独立导出人工四姿态与接触设计候选，不调用任何旧build入口。"""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import json
import math
import re
import shutil

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import least_squares

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
V2 = RIG / 'video_guided_walk_v2'
STABLE = RIG / 'stable_parts_v1'
REF = RIG / 'video_parts_v1/cycle_review'
OUT = RIG / 'pose_walk_v3'
DURATION = 2 / 3
FLAGS = {k: False for k in ['prototypeAccepted', 'productionApproved', 'videoFit', 'videoFitPassed', 'videoLoopCandidateAccepted', 'wardrobeVerified', 'crossCharacterVerified', 'mobileVerified']}
FRAMES = [68, 70, 72, 76, 77, 78, 80, 84]
EVENTS = ['展开、近脚接触', '上臂前带、手收胸右', '近臂收胸、passing高位', '远脚接触、收胸低位', '手开始下降', '开始外展', '另一passing高位', '回到68']
# 上下臂角度都是相对body的人工绝对方向（Spine y-up），导出时下臂转为父级局部角。
# 上臂先前带再屈肘；每条链保持稳定关节分支，不读取视频轮廓坐标。
ARM_KEYS = {
    'arm_near': [[-108,-100],[-56,-2],[-39,35],[-37,37],[-54,9],[-78,-50],[-111,-101],[-108,-100]],
    'arm_far': [[-70,-32],[-96,-64],[-104,-76],[-100,-70],[-90,-57],[-78,-41],[-65,-24],[-70,-32]],
}
BODY_Y = [0,-1,7,-2,-3,1,7,0]
FOOT_DESIGN = {
    'leg_near': [[5,-4],[5,-4],[-4,-12],[-8,-13],[-4,-12],[1,-13],[6,-15],[5,-4]],
    'leg_far': [[-5,-15],[-12,-17],[-14,-13],[4,-4],[4,-4],[4,-4],[-6,-15],[-5,-15]],
}
CONTACT = {'leg_near': [0,2/24], 'leg_far': [8/24,10/24]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sample(values, frame):
    for i,(a,b) in enumerate(zip(FRAMES,FRAMES[1:])):
        if a <= frame <= b:
            u=(frame-a)/(b-a)
            u=u*u*(3-2*u)
            return np.asarray(values[i])*(1-u)+np.asarray(values[i+1])*u
    return np.asarray(values[-1])


def bind_slice(text):
    # v2顶层animations排在最后；原始绑定字节前缀原样保留，不重新序列化mesh/weights。
    marker='  "animations":'
    prefix,sep,_=text.rpartition(marker)
    assert sep and '"skins"' in prefix
    return prefix,sep


def load_tools():
    spec=importlib.util.spec_from_file_location('pose_v3_profile_tools', BASE/'build_profile_walk.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    spec=importlib.util.spec_from_file_location('pose_v3_safe_tools', BASE/'build_video_guided_walk.py')
    safe=importlib.util.module_from_spec(spec);spec.loader.exec_module(safe)
    h.OUT=OUT;safe.h.OUT=OUT
    h.render_mesh=safe.safe_render_mesh
    return h


def protect_files():
    directories=[V2,STABLE,RIG/'profile_walk_v1',RIG/'video_parts_v1',BASE/'generated_spine',BASE/'generated_parts']
    protected={p for directory in directories if directory.is_dir() for p in directory.rglob('*') if p.is_file()}
    protected.update(p for p in BASE.iterdir() if p.is_file() and p!=Path(__file__).resolve())
    protected.add(RIG/'source.mp4')
    return {p:sha(p) for p in sorted(protected)}


def anchors_from_material(h,meshes,manifest):
    anchors={}
    for n in ['leg_near','leg_far']:
        part=next(p for p in manifest['parts'] if p['id']==n)
        alpha=np.asarray(Image.open(STABLE/part['file']).convert('RGBA'))[:,:,3]
        ys,xs=np.where(alpha>200);floor=int(ys.max())
        point=[float(np.median(xs[ys>=floor-2]))+part['bbox'][0]+.5,float(floor)+part['bbox'][1]+.5]
        binding=h.material_binding(meshes[n],h.yup(point))
        tri,bary=binding
        influence={bone:float(sum(k*sum(w for b,p,w in meshes[n]['influences'][int(j)] if b==bone) for j,k in zip(tri,bary))) for bone in ['body',n+'_upper',n+'_lower']}
        anchors[n]={'point':point,'binding':binding,'influence':influence}
    return anchors


def make_motion(h,sk,meshes,anchors):
    bones={b['name']:b for b in sk['bones']}
    channels={'body':{'translate':[]}}
    for n in ARM_KEYS:
        channels[n+'_upper']={'rotate':[]};channels[n+'_lower']={'rotate':[]}
    for n in anchors:
        channels[n+'_upper']={'rotate':[]};channels[n+'_lower']={'rotate':[]}
    sk['animations']={'setup':{'bones':{}},'walk':{'bones':channels}}
    projection={n:[] for n in anchors}
    for i in range(97):
        t=DURATION*i/96;f=68+t*24
        body_y=float(sample(BODY_Y,f))
        channels['body']['translate'].append({'time':t,'x':0.,'y':body_y})
        for n,values in ARM_KEYS.items():
            upper,lower=sample(values,f)
            channels[n+'_upper']['rotate'].append({'time':t,'value':float(upper-bones[n+'_upper']['rotation'])})
            channels[n+'_lower']['rotate'].append({'time':t,'value':float(lower-upper-bones[n+'_lower']['rotation'])})
        for n in anchors:
            # 此IK只针对人工设计的真实mesh脚底材料点，不读取视频目标点。
            desired=np.asarray(anchors[n]['point'])+sample(FOOT_DESIGN[n],f)
            upper=bones[n+'_upper'];lower=bones[n+'_lower']
            # 保持绑定膝分支：近膝正向、远膝负向；上腿旋转范围限制为角色自身可达范围。
            bounds=([-125,4],[-55,85]) if n=='leg_near' else ([-115,-85],[-50,-4])
            initial=[upper['rotation'],lower['rotation']]
            def set_angles(q):
                for bone,value in [(n+'_upper',q[0]-upper['rotation']),(n+'_lower',q[1]-lower['rotation'])]:
                    ch=channels[bone]['rotate']
                    if ch and abs(ch[-1]['time']-t)<1e-10:ch[-1]['value']=float(value)
                    else:ch.append({'time':t,'value':float(value)})
            def actual(q):
                set_angles(q)
                return h.screen(h.material_position(meshes[n],h.solve(sk,'walk',t),anchors[n]['binding']))
            # 脚底若有少量混合权重也用完整weighted material求解，不把骨端冒充脚底。
            result=least_squares(lambda q:actual(q)-desired,initial,bounds=bounds,max_nfev=36,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            reached=actual(result.x)
            projection[n].append({'time':t,'referenceFrame':f,'designedMaterialTarget':desired.tolist(),'reachableProjectedMaterial':reached.tolist(),'projectionDistancePx':float(np.linalg.norm(reached-desired)),'absoluteLocalAngles':result.x.tolist()})
    for ch in channels.values():
        for timeline in ch.values():timeline[-1]={**timeline[0],'time':DURATION}
    return projection


def geometry_checks(h,sk,meshes,anchors):
    geometry={n:{'flips':0,'collapsed':0,'minAreaRatio':1e9,'maxAreaRatio':0.,'minPrincipalStretch':1e9,'maxPrincipalStretch':0.} for n in meshes}
    setup={};feet={n:[] for n in anchors}
    inverses={}
    for n,m in meshes.items():
        a=m['bind'][m['triangles']]
        inverses[n]=np.linalg.inv(np.stack([a[:,1]-a[:,0],a[:,2]-a[:,0]],axis=-1))
        setup[n]={'maxWeightSumError':float(max(abs(sum(w for b,p,w in row)-1) for row in m['influences'])),'finiteNonnegativeWeights':all(np.isfinite(w) and w>=0 for row in m['influences'] for b,p,w in row)}
    for i in range(193):
        t=DURATION*i/192;world=h.solve(sk,'walk',t)
        for n,m in meshes.items():
            g,dst=h.mesh_geometry(m,world);a=geometry[n]
            for k in ['flips','collapsed']:a[k]+=g[k]
            a['minAreaRatio']=min(a['minAreaRatio'],g['minAreaRatio']);a['maxAreaRatio']=max(a['maxAreaRatio'],g['maxAreaRatio'])
            b=dst[m['triangles']]
            sv=np.linalg.svd(np.stack([b[:,1]-b[:,0],b[:,2]-b[:,0]],axis=-1)@inverses[n],compute_uv=False)
            a['minPrincipalStretch']=min(a['minPrincipalStretch'],float(sv.min()));a['maxPrincipalStretch']=max(a['maxPrincipalStretch'],float(sv.max()))
        for n in feet:
            feet[n].append({'time':t,'position':h.screen(h.material_position(meshes[n],world,anchors[n]['binding'])).tolist()})
    loop={n:float(np.linalg.norm(h.vertices_world(m,h.solve(sk,'walk',0))-h.vertices_world(m,h.solve(sk,'walk',DURATION)),axis=1).max()) for n,m in meshes.items()}
    foot_metrics={}
    for n,rows in feet.items():
        lo,hi=CONTACT[n];p=np.asarray([r['position'] for r in rows if lo-1e-10<=r['time']<=hi+1e-10])
        foot_metrics[n]={'intendedContactIntervalSeconds':[lo,hi],'sampleCount':len(p),'measuredMaxDriftPx':float(np.linalg.norm(p-p[0],axis=1).max()),'horizontalRangePx':float(np.ptp(p[:,0])),'verticalRangePx':float(np.ptp(p[:,1])),'sourceAnchor':anchors[n]['point'],'anchorWeights':anchors[n]['influence'],'method':'从导出JSON weighted mesh的真实脚底源材料点重心插值；不是骨端、视频轮廓或物理地面验证。'}
    return geometry,setup,loop,feet,foot_metrics


def overlay(h,sk,im,t):
    im=im.copy();d=ImageDraw.Draw(im);world=h.solve(sk,'walk',t)
    for n in ['arm_near','arm_far','leg_near','leg_far']:
        up,low=world[n+'_upper'],world[n+'_lower'];length=next(b['length'] for b in sk['bones'] if b['name']==n+'_lower')
        ps=[h.screen(up[:2,2]),h.screen(low[:2,2]),h.screen((low@np.array([length,0,1]))[:2])]
        ps=[tuple(p) for p in ps];color='#127ba8' if 'arm' in n else '#bc5c3c'
        d.line(ps,fill=color,width=3)
        for x,y in ps:d.ellipse((x-3,y-3,x+3,y+3),fill=color)
    return im


def review(h,sk,page,regions,meshes,geometry):
    assert OUT.is_dir();(OUT/'renders').mkdir(exist_ok=True)
    frames=[];bones=[];raster={}
    for i in range(33):
        t=DURATION*i/32
        image,stats=h.render(sk,page,regions,meshes,'walk',t)
        frames.append(image);bones.append(overlay(h,sk,image,t))
        if i<32:
            frames[-1].save(OUT/f'renders/pose_{i:02d}.png')
            bones[-1].save(OUT/f'renders/bones_{i:02d}.png')
        for n,g in stats.items():raster[n]=max(raster.get(n,0),g['interiorOverlapPixels'])
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16);title=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
    sheet=Image.new('RGB',(2000,1180),'#eef2f6');d=ImageDraw.Draw(sheet)
    d.text((20,15),'POSE WALK V3 / 人工四姿态+事件过渡 / 冻结v2绑定和权重 / 非视频拟合',font=title,fill='#193149')
    for col,(f,label) in enumerate(zip(FRAMES,EVENTS)):
        x=col*250;idx=(f-68)*2
        d.text((x+8,58),f'f{f} / {label}',font=font,fill='#193149')
        ref=Image.open(REF/f'source_{f:03d}.png').convert('RGB').crop((315,275,560,468)).resize((235,185))
        sheet.paste(ref,(x+7,90))
        tile=Image.new('RGBA',(235,320),'white');tile.alpha_composite(frames[idx].crop((155,80,625,720)).resize((235,320)))
        sheet.paste(tile.convert('RGB'),(x+7,290))
        tile=Image.new('RGBA',(235,270),'#dce4ec');tile.alpha_composite(bones[idx].crop((260,415,535,700)).resize((235,244)),(0,0))
        sheet.paste(tile.convert('RGB'),(x+7,625))
    d.text((20,925),'上：未修改的源帧裁剪；中：导出JSON与原atlas CPU解算；下：同一角色叠加固定长度骨链。',font=font,fill='#193149')
    d.text((20,956),'手臂：人工前带与屈肘；腿：人工接触/抬脚材料目标的角色可达投影。没有读取视频轮廓目标、没有改权重。',font=font,fill='#193149')
    d.text((20,987),'193相位翻转总数：'+str(sum(g['flips'] for g in geometry.values()))+'。隐藏结构/官方运行时/换装/生产均未验收。',font=font,fill='#9a4a30')
    sheet.save(OUT/'review.png')
    gif=[]
    for i,im in enumerate(frames[:-1]):
        tile=Image.new('RGB',(1120,650),'#edf1f5');td=ImageDraw.Draw(tile)
        ref=Image.open(REF/f'source_{68+i//2:03d}.png').convert('RGB').crop((310,45,600,470)).resize((350,513))
        tile.paste(ref,(12,80));td.text((12,24),f'源视频 f{68+i//2} / 相位 {i}/32',font=font,fill='#193149')
        for x,img,label in [(380,im,'导出角色'),(750,bones[i],'角色 + 固定骨链')]:
            bg=Image.new('RGBA',(350,513),'white');bg.alpha_composite(img.crop((155,80,625,768)).resize((350,513)))
            tile.paste(bg.convert('RGB'),(x,80));td.text((x,24),label,font=font,fill='#193149')
        td.text((12,615),'人工动作 / 仅视频事件参考 / 独立候选，未验收',font=font,fill='#9a4a30');gif.append(tile)
    gif[0].save(OUT/'review.gif',save_all=True,append_images=gif[1:],duration=[20,20,20,20,20,20,20,30]*4,loop=0,disposal=2)
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pose Walk V3 独立审稿</title><style>body{font:15px system-ui;background:#edf1f5;color:#193149;margin:24px}h1{font-size:23px}main{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;max-width:1500px}section{background:white;padding:12px;border-radius:8px}section img{width:100%;height:520px;object-fit:contain}section:first-child img{object-fit:cover;object-position:center}button,input{padding:8px;margin:5px}p{line-height:1.6}.warning{color:#9a4a30}a{color:#176985}small{display:block}</style><h1>Pose Walk V3 · 人工姿态候选</h1><p class="warning">仅独立审稿辅助，不是正式05入口。原视频只参考事件节奏；绑定/权重/图集冻结。所有验收标志 false。</p><button id="play">暂停</button><button id="prev">上一相位</button><button id="next">下一相位</button><input id="phase" type="range" min="0" max="31" step="1" value="0"><span id="label"></span><main><section><h2>源视频原始PNG</h2><img id="source" alt="源视频逐帧PNG"><small>同帧原始PNG，不加载外部网络；未裁改源文件</small></section><section><h2>导出角色</h2><img id="pose" alt="导出weighted mesh"></section><section><h2>角色与骨骼叠加</h2><img id="bones" alt="固定长度双骨链"></section></main><p><a href="review.png">查看完整姿态表</a> · <a href="review.gif">查看真实循环GIF</a> · <a href="../source.mp4">原始视频</a> · <a href="checks.json">实测检查</a> · <a href="motion-spec.json">人工动作说明</a></p><script>let i=0,playing=true,last=0;const source=document.getElementById('source'),pose=document.getElementById('pose'),bones=document.getElementById('bones'),phase=document.getElementById('phase'),label=document.getElementById('label'),play=document.getElementById('play');const cache=[];for(let j=0;j<32;j++){for(const p of ['pose','bones']){let im=new Image();im.src='renders/'+p+'_'+String(j).padStart(2,'0')+'.png';cache.push(im)}}function draw(){source.src='../video_parts_v1/cycle_review/source_'+String(68+Math.floor(i/2)).padStart(3,'0')+'.png';pose.src='renders/pose_'+String(i).padStart(2,'0')+'.png';bones.src='renders/bones_'+String(i).padStart(2,'0')+'.png';phase.value=i;label.textContent='相位 '+i+'/32 · 源帧 '+(68+Math.floor(i/2))+' · '+(i/48).toFixed(4)+'秒'}function pause(){playing=false;play.textContent='播放'}play.onclick=()=>{playing=!playing;play.textContent=playing?'暂停':'播放';last=performance.now()};document.getElementById('prev').onclick=()=>{pause();i=(i+31)%32;draw()};document.getElementById('next').onclick=()=>{pause();i=(i+1)%32;draw()};phase.oninput=()=>{pause();i=+phase.value;draw()};function tick(t){if(playing&&t-last>=1000/48){const steps=Math.floor((t-last)/(1000/48));i=(i+steps)%32;last+=steps*1000/48;draw()}requestAnimationFrame(tick)}draw();requestAnimationFrame(tick);</script></html>'''
    (OUT/'review.html').write_text(html,encoding='utf-8')
    return int(np.any(np.asarray(frames[0])!=np.asarray(frames[-1]),axis=2).sum()),raster


def main():
    assert BASE.is_dir() and RIG.is_dir() and REF.is_dir() and STABLE.is_dir()
    revise=sys.argv[1:]==['--revise-owned']
    assert not sys.argv[1:] or revise
    prior=None
    if OUT.exists():
        if not revise:raise SystemExit(f'停止：候选目录已存在，不覆盖：{OUT}')
        prior=load(OUT/'checks.json')
        spec=load(OUT/'motion-spec.json')
        assert spec['candidateId']=='pose_walk_v3' and prior['weightsFrozen'] and not prior['productionApproved']
    else:
        assert not revise
    before=protect_files();h=load_tools()
    manifest=load(STABLE/'manifest.json');source_profile=load(V2/'profile.json')
    for p in manifest['parts']:assert sha(STABLE/p['file'])==p['sha256']
    source_text=(V2/'profile_walk.json').read_bytes().decode('utf-8');prefix,sep=bind_slice(source_text)
    sk=json.loads(source_text);source_bind={k:copy.deepcopy(v) for k,v in sk.items() if k!='animations'}
    if not OUT.exists():OUT.mkdir()
    for name in ['profile_walk.atlas','profile_walk.png','profile.json']:shutil.copyfile(V2/name,OUT/name)
    page,regions=h.read_atlas();meshes=h.decode_meshes(sk,regions)
    anchors=anchors_from_material(h,meshes,manifest)
    projection=make_motion(h,sk,meshes,anchors)
    animation=json.dumps(sk['animations'],ensure_ascii=False,indent=2,allow_nan=False)
    (OUT/'profile_walk.json').write_bytes((prefix+sep+' '+animation+'\n}\n').encode('utf-8'))
    exported=load(OUT/'profile_walk.json')
    bind_equal={k:v for k,v in exported.items() if k!='animations'}==source_bind
    assert bind_equal and bind_slice((OUT/'profile_walk.json').read_bytes().decode('utf-8'))[0]==prefix
    sk=exported;meshes=h.decode_meshes(sk,regions)
    geometry,setup,loop,feet,foot_metrics=geometry_checks(h,sk,meshes,anchors)
    decoded=[];cap=cv2.VideoCapture(str(RIG/'source.mp4'))
    for i in range(85):
        ok,bgr=cap.read();assert ok
        if i>=68:
            path=REF/f'source_{i:03d}.png'
            exact=np.array_equal(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),np.asarray(Image.open(path).convert('RGB')))
            assert exact
            decoded.append({'frame':i,'file':'../video_parts_v1/cycle_review/'+path.name,'sha256':sha(path),'decodedPixelsExact':bool(exact)})
    cap.release()
    motion_spec={'schemaVersion':1,'candidateId':'pose_walk_v3',**FLAGS,'method':'人工四姿态与有限过渡；视频仅作事件节奏参考。手臂为手填局部旋转；腿只将人工脚底材料目标投影到原角色可达范围，不追踪视频轮廓。','durationSeconds':DURATION,'fpsReference':24,'mainPoseFrames':[68,72,76,80],'referenceEvents':[{'frame':f,'event':e} for f,e in zip(FRAMES,EVENTS)],'absoluteLocalArmAngles':ARM_KEYS,'bodyYUpOffsetsPx':BODY_Y,'manualFootOffsetsFromSourceMaterialPx':FOOT_DESIGN,'contactIntervalsSeconds':CONTACT,'footProjection':projection,'sourceVideo':{'file':'../source.mp4','sha256':sha(RIG/'source.mp4')},'decodedReferenceFrames':decoded,'bindSource':'../video_guided_walk_v2/profile_walk.json','profileCopiedByteExact':True,'boneLengths':{b['name']:b.get('length',0) for b in sk['bones']},'interpolation':'人工事件键之间smoothstep，97个烘焙角度键；导出线性插值。84显式复制68，既有局部x/y和骨长不变。','limitations':['近远命名只指v2屏幕层，不代表解剖身份。','原角色长躯干短四肢，不照搬视频转面和扁脚；脚底目标不一定全部可达，投影距离逐键保留。','肩髋隐藏图与v2静态权重冻结；可能发生压缩、翻转和轮廓切口，不因数值失败削到不可见。','接触滑动按真实mesh脚底材料点测量，不等于地面物理或接触区域验收。','CPU解算并非Spine官方运行时、换装、跨角色或生产验收。']}
    save('motion-spec.json',motion_spec)
    pixels,raster=review(h,sk,page,regions,meshes,geometry)
    unchanged={p:sha(p)==digest for p,digest in before.items()}
    noflips=all(g['flips']==0 and g['collapsed']==0 for g in geometry.values())
    stretch_ok=all(g['minPrincipalStretch']>.35 and g['maxPrincipalStretch']<1.8 for g in geometry.values())
    checks={'schemaVersion':1,'status':'manual_candidate_pending_visual_review',**FLAGS,'cycleSampleCount':193,'meshGeometry':geometry,'setupWeights':setup,'firstLastMeshMaxErrorPx':loop,'firstLastRenderMismatchPixels':pixels,'meshRasterOverlapPixels':raster,'meshNoFlipsPassed':noflips,'principalStretchRangePassed':stretch_ok,'stretchThresholds':{'min':.35,'max':1.8},'numericalChecksPassed':bool(noflips and stretch_ok and max(loop.values())<1e-8 and pixels==0),'footContactDrift':foot_metrics,'footMaterialSamples':feet,'contactSlipMeasured':True,'contactSlipPassed':all(m['measuredMaxDriftPx']<.1 for m in foot_metrics.values()),'bindBonesSlotsSkinsEqualV2':bind_equal,'bindRawJsonPrefixByteExact':True,'profileJsonCopiedByteExact':sha(OUT/'profile.json')==sha(V2/'profile.json'),'atlasAndPngCopiedByteExact':all(sha(OUT/n)==sha(V2/n) for n in ['profile_walk.atlas','profile_walk.png']),'weightsFrozen':True,'weightOptimizationAttempted':False,'boneCount':len(sk['bones']),'slotCount':len(sk['slots']),'noLimbTranslationOrScaleTimelines':all(set(c)=={'rotate'} for n,c in sk['animations']['walk']['bones'].items() if n!='body'),'noDeformTimeline':True,'protectedOldFilesUnchanged':all(unchanged.values()),'protectedOldFileCount':len(before),'protectedOldFileHashes':[{'file':p.relative_to(BASE).as_posix(),'beforeSha256':before[p],'unchanged':unchanged[p]} for p in before],'sourceVideoSHAAnd17DecodedFramesVerified':True,'visualReview':{'status':'pending','passed':False},'officialSpineRuntimeVerified':False,'shoulderAndLegRootGapFree':False,'reviewPoseFrames':FRAMES,'renderCount':32,'boneOverlayRenderCount':32,'limitations':motion_spec['limitations']}
    if prior:
        checks['finiteRevision']={'count':1,'reason':'实际查看首轮review后修正上下臂绝对角与父级局部角混用；胸前手保持原图比例下可达位置，同时减小近腿后摆不可达目标。未优化权重、未缩成小摆。','previousGeometry':prior['meshGeometry'],'previousReviewObservation':'首轮收臂贴颈、手部轮廓塌缩；腿摆目标最大投影距离16.2688px。'}
    save('checks.json',checks)
    assert all(unchanged.values())
    print(json.dumps({'output':str(OUT),'geometry':geometry,'loopErrorPx':loop,'renderLoopMismatchPixels':pixels,'footContactDrift':foot_metrics,'maxFootProjectionPx':{n:max(r['projectionDistancePx'] for r in rows) for n,rows in projection.items()},'oldFileCount':len(before),'oldInputsUnchanged':True,'approvalFlags':FLAGS},ensure_ascii=False))


def inspection_sheets():
    assert OUT.is_dir() and (OUT/'renders').is_dir()
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    for group in range(4):
        sheet=Image.new('RGB',(1600,970),'#edf1f5');d=ImageDraw.Draw(sheet)
        d.text((15,10),f'完整一圈顺序相位审阅 {group+1}/4（每张8相位，共32相位）',font=font,fill='#193149')
        for j in range(8):
            i=group*8+j;x=(j%4)*400;y=45+(j//4)*460
            im=Image.open(OUT/f'renders/bones_{i:02d}.png').convert('RGBA')
            tile=Image.new('RGBA',(380,410),'white');tile.alpha_composite(im.crop((235,405,555,715)).resize((380,368)))
            sheet.paste(tile.convert('RGB'),(x+10,y+30))
            d.text((x+15,y),f'相位 {i}/32 / f{68+i/2:.1f} / {i/48:.4f}s',font=font,fill='#193149')
        sheet.save(OUT/f'cycle_inspection_{group+1}.png')
    print(json.dumps({'cyclePhaseCount':32,'sheets':[f'cycle_inspection_{i}.png' for i in range(1,5)]}))


def finalize_review():
    assert OUT.is_dir()
    checks=load(OUT/'checks.json');sk=load(OUT/'profile_walk.json')
    # 只重新封装本候选绑定前缀的换行字节，骨架与动画数值完全不变。
    prefix,sep=bind_slice((V2/'profile_walk.json').read_bytes().decode('utf-8'))
    content=prefix+sep+' '+json.dumps(sk['animations'],ensure_ascii=False,indent=2,allow_nan=False)+'\n}\n'
    (OUT/'profile_walk.json').write_bytes(content.encode('utf-8'))
    assert load(OUT/'profile_walk.json')==sk
    actual_prefix=bind_slice((OUT/'profile_walk.json').read_bytes().decode('utf-8'))[0]
    assert actual_prefix.encode('utf-8')==prefix.encode('utf-8')
    checks['bindRawJsonPrefixByteExact']=True
    checks['bindRawPrefixSha256']=hashlib.sha256(prefix.encode('utf-8')).hexdigest()
    checks['absoluteLocalArmAnglesContract']='motion-spec内键为相对body的上下臂绝对方向；动画lower通道先转为相对upper局部角，再减bind局部角。'
    current_protected=[]
    for row in checks['protectedOldFileHashes']:
        exact=sha(BASE/row['file'])==row['beforeSha256']
        row['unchanged']=exact;current_protected.append(exact)
    assert all(current_protected)
    checks['protectedOldFilesUnchanged']=True
    checks['visualReview']={'status':'actually_reviewed_failed_candidate','passed':False,'inspectedWith':'ViewImage','reviewFile':'review.png','reviewSha256':sha(OUT/'review.png'),'cycleScope':'实际查看完整32相位，4张cycle_inspection_1..4.png，按相位0..31顺序覆盖一圈；GIF因工具图像过大未直接显示，不声称已连续播放审阅。','inspectedFiles':['review.png']+[f'cycle_inspection_{i}.png' for i in range(1,5)],'observations':['已实际查看两张参考contact、v2 review及源068/076/084，再查看v3首轮和有限修正后review。','近臂从展开进入胸前屏幕右侧，70帧已收，72..76维持收胸，77下降、78外展，身体有可辨上下起伏；不是旧1度小摆。','近臂收胸时肩臂轮廓宽扁折叠，与源视频圆手造型不符；固定旧权重出现明显压缩与翻转，未获通过。','近腿根切口和扭曲仍可见；换脚在固定原角色可达范围内偏弱，无法声称复现视频步态。','整圈末段回落连贯；精确首尾mesh及渲染像素差为零，但这只证明数值闭环。','所有验收标志保持false，未接入正式入口，也未启动任何项目服务器。']}
    checks['status']='manual_candidate_reviewed_not_accepted'
    checks.update(FLAGS)
    checks['script']={'file':'../../../build_pose_walk_v3.py','sha256':sha(__file__)}
    save('checks.json',checks)
    motion=load(OUT/'motion-spec.json')
    motion['armAngleCoordinateContract']=checks['absoluteLocalArmAnglesContract']
    if 'absoluteLocalArmAngles' in motion:
        motion['manualAbsoluteArmDirectionsRelativeToBodyDegrees']=motion.pop('absoluteLocalArmAngles')
    save('motion-spec.json',motion)
    gif=Image.open(OUT/'review.gif');duration=0
    for i in range(gif.n_frames):gif.seek(i);duration+=gif.info.get('duration',0)
    checks['gifVerified']={'frameCount':gif.n_frames,'loop':gif.info.get('loop'),'durationMs':duration,'renderFrameCount':32,'durationRoundingNote':f'GIF仅支持10ms时基；实测循环{duration}ms，导出动作时长666.6667ms；HTML按48Hz相位。'}
    checks['assetHashes']={name:sha(OUT/name) for name in ['profile_walk.json','profile_walk.atlas','profile_walk.png','profile.json','motion-spec.json','review.png','review.gif','review.html']}
    save('checks.json',checks)
    print(json.dumps({'status':checks['status'],'protectedOldFileCount':len(current_protected),'protectedOldFilesUnchanged':True,'bindRawPrefixByteExact':True,'gif':checks['gifVerified'],'visualReviewPassed':False},ensure_ascii=False))


if __name__=='__main__':
    if sys.argv[1:]==['--inspection-sheets']:inspection_sheets()
    elif sys.argv[1:]==['--finalize-reviewed']:finalize_review()
    else:main()
