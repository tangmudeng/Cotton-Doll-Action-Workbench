"""05独立静态关节候选；旧工具只读导入，绝不调用旧构建入口。"""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import copy
import importlib.util
import json
import shutil
import hashlib
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
OUT = RIG / 'joint_structure_v4'
V2 = RIG / 'video_guided_walk_v2'
V3 = RIG / 'pose_walk_v3'
STABLE = RIG / 'stable_parts_v1'
REF = RIG / 'video_parts_v1/cycle_review'
T = 2 / 3
FLAGS = {n: False for n in ['prototypeAccepted', 'productionApproved', 'videoFit', 'videoFitPassed', 'videoLoopCandidateAccepted', 'wardrobeVerified', 'crossCharacterVerified', 'mobileVerified']}
# 唯一预先限定方案：短根带与肘膝带分离，不试扫参数或优化器。
RULE = {'id': 'axis_strips_short_hidden_root', 'rootBandPx': [-12., -2.], 'hingeHalfSpanArmPx': 12., 'hingeHalfSpanLegPx': 9., 'maxLongitudinalStepPx': 6., 'transverseSegments': 12}
FONT = 'C:/Windows/Fonts/msyh.ttc'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def save(p, data):
    assert OUT in p.parents
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def tools():
    spec = importlib.util.spec_from_file_location('joint_v4_safe_tools', BASE / 'build_video_guided_walk.py')
    safe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(safe)
    h = safe.h
    h.OUT = OUT
    h.render_mesh = safe.safe_render_mesh
    return h, safe


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def axis_mesh(n, part, chain, bind, bones, safe):
    a, j, c = np.asarray(chain, float)
    axis = (c - a) / np.linalg.norm(c - a)
    normal = np.array([-axis[1], axis[0]])
    x0, y0, x1, y1 = part['bbox']
    corners = np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], float)
    sp = (corners-a) @ axis
    qp = (corners-a) @ normal
    joint = float((j-a) @ axis)
    half = RULE['hingeHalfSpanArmPx'] if 'arm' in n else RULE['hingeHalfSpanLegPx']
    # 每个肘膝前/中/后横向带都显式存在；不以bbox加密冒充沿轴拓扑。
    rows = np.unique(np.r_[sp, np.linspace(sp.min(), sp.max(), math.ceil(np.ptp(sp)/RULE['maxLongitudinalStepPx'])+1), RULE['rootBandPx'], joint + np.array([-half,-half/2,0,half/2,half])])
    rows = rows[(rows >= sp.min()-1e-8) & (rows <= sp.max()+1e-8)]
    pts, strips = [], []
    for s in rows:
        cuts = []
        for k in range(4):
            l = (k+1) % 4
            if min(sp[k],sp[l])-1e-8 <= s <= max(sp[k],sp[l])+1e-8:
                if abs(sp[l]-sp[k]) < 1e-10:
                    cuts += [qp[k],qp[l]]
                else:
                    cuts.append(qp[k]+(qp[l]-qp[k])*(s-sp[k])/(sp[l]-sp[k]))
        lo, hi = min(cuts), max(cuts)
        qs = [(lo+hi)/2] if hi-lo < 1e-8 else np.linspace(lo,hi,RULE['transverseSegments']+1)
        ids = []
        for q in qs:
            ids.append(len(pts));pts.append(a+s*axis+q*normal)
        strips.append(ids)
    tri = []
    for ri,(up,down) in enumerate(zip(strips,strips[1:])):
        if len(up)==1:
            tri += [[up[0],down[k+1],down[k]] for k in range(len(down)-1)]
        elif len(down)==1:
            tri += [[up[k],up[k+1],down[0]] for k in range(len(up)-1)]
        else:
            for k in range(len(up)-1):
                p,q,r,s=up[k],up[k+1],down[k],down[k+1]
                tri += [[p,q,s],[p,s,r]] if (ri+k)%2==0 else [[p,q,r],[q,s,r]]
    pts=np.asarray(pts);tri=np.asarray(tri, int)
    # 保持统一绑定绕序；动画检查永不改绕序。
    cross=safe.h.cross(pts[tri[:,1]]-pts[tri[:,0]],pts[tri[:,2]]-pts[tri[:,0]])
    tri[cross<0]=tri[cross<0][:,[0,2,1]]
    s=(pts-a)@axis
    limb=smooth((s-RULE['rootBandPx'][0])/np.ptp(RULE['rootBandPx']))
    lower=smooth((s-joint+half)/(2*half))
    weights=np.c_[1-limb,limb*(1-lower),limb*lower]
    data={'points':pts,'triangles':tri,'uv':(pts-[x0,y0])/[x1-x0,y1-y0], 'weights':weights,'chain':['body',n+'_upper',n+'_lower'], 'axis':axis.tolist(),'normal':normal.tolist(),'axisRows':rows.tolist(),'jointS':joint,'hingeBand':[joint-half,joint+half]}
    return safe.encode_mesh(n,part,data,bind,bones),data


def evaluate(h, sk, meshes, page, parts):
    geometry={};alpha_geometry={};setup={};loop={};inverses={};alpha_masks={}
    anchors={};feet={}
    for n,m in meshes.items():
        a=m['bind'][m['triangles']]
        inverses[n]=np.linalg.inv(np.stack([a[:,1]-a[:,0],a[:,2]-a[:,0]],axis=-1))
        # 有alpha有效域使用三角形覆盖区域真实alpha，而非只看顶点或质心。
        import cv2
        alpha=np.asarray(page)[:,:,3]
        mask=[]
        for tr in m['triangles']:
            src=m['source'][tr];lo=np.floor(src.min(axis=0)).astype(int)-1;hi=np.ceil(src.max(axis=0)).astype(int)+2
            lo=np.maximum(lo,0);hi=np.minimum(hi,[page.width,page.height]);x,y=lo;w,hh=hi-lo
            raster=np.zeros((hh,w),np.uint8)
            cv2.fillConvexPoly(raster,np.rint((src-lo)*16).astype(np.int32),1,shift=4)
            mask.append(bool(np.any((raster>0)&(alpha[y:y+hh,x:x+w]>16))))
        alpha_masks[n]=np.array(mask)
        geometry[n]={'flips':0,'collapsed':0,'minAreaRatio':1e9,'maxAreaRatio':0.,'minPrincipalStretch':1e9,'maxPrincipalStretch':0.,'finite':True,'triangleCount':len(m['triangles'])}
        alpha_geometry[n]=copy.deepcopy(geometry[n]);alpha_geometry[n]['triangleCount']=int(sum(mask))
        setup[n]={'maxWeightSumError':float(max(abs(sum(w for b,p,w in row)-1) for row in m['influences'])), 'finiteNonnegativeWeights':bool(all(np.isfinite(w) and w>=0 for row in m['influences'] for b,p,w in row)), 'finiteBind':bool(np.isfinite(m['bind']).all())}
        loop[n]=float(np.linalg.norm(h.vertices_world(m,h.solve(sk,'walk',0))-h.vertices_world(m,h.solve(sk,'walk',T)),axis=1).max())
        if n.startswith('leg'):
            part=parts[n];al=np.asarray(Image.open(STABLE/part['file']).convert('RGBA'))[:,:,3]
            ys,xs=np.where(al>200);floor=int(ys.max())
            pt=np.array([float(np.median(xs[ys>=floor-2]))+part['bbox'][0]+.5,floor+part['bbox'][1]+.5])
            binding=h.material_binding(m,h.yup(pt))
            anchors[n]={'sourcePoint':pt.tolist(),'binding':binding};feet[n]=[]
    for i in range(193):
        t=T*i/192;world=h.solve(sk,'walk',t)
        for n,m in meshes.items():
            dst=h.vertices_world(m,world);a=m['bind'][m['triangles']];b=dst[m['triangles']]
            de=np.stack([b[:,1]-b[:,0],b[:,2]-b[:,0]],axis=-1)
            ratio=h.cross(b[:,1]-b[:,0],b[:,2]-b[:,0])/h.cross(a[:,1]-a[:,0],a[:,2]-a[:,0])
            sv=np.linalg.svd(de@inverses[n],compute_uv=False)
            for target,mask in [(geometry[n],np.ones(len(ratio),bool)),(alpha_geometry[n],alpha_masks[n])]:
                r=ratio[mask];v=sv[mask]
                target['flips']+=int((r<0).sum());target['collapsed']+=int((np.abs(r)<1e-5).sum())
                target['minAreaRatio']=min(target['minAreaRatio'],float(r.min()));target['maxAreaRatio']=max(target['maxAreaRatio'],float(r.max()))
                target['minPrincipalStretch']=min(target['minPrincipalStretch'],float(v.min()));target['maxPrincipalStretch']=max(target['maxPrincipalStretch'],float(v.max()))
                target['finite'] &= bool(np.isfinite(dst).all() and np.isfinite(v).all())
        for n in feet:
            feet[n].append({'time':t,'position':h.screen(h.material_position(meshes[n],world,anchors[n]['binding'])).tolist()})
    metrics={}
    for n,rows in feet.items():
        interval=[0,2/24] if n=='leg_near' else [8/24,10/24]
        p=np.array([r['position'] for r in rows if interval[0]-1e-10<=r['time']<=interval[1]+1e-10])
        tr,bary=anchors[n]['binding'];weights={bone:float(sum(k*sum(w for b,p,w in meshes[n]['influences'][int(v)] if b==bone) for v,k in zip(tr,bary))) for bone in ['body',n+'_upper',n+'_lower']}
        metrics[n]={'sourceAnchor':anchors[n]['sourcePoint'],'anchorWeights':weights,'intendedContactIntervalSeconds':interval,'sampleCount':len(p),'measuredMaxDriftPx':float(np.linalg.norm(p-p[0],axis=1).max()),'horizontalRangePx':float(np.ptp(p[:,0])),'verticalRangePx':float(np.ptp(p[:,1])),'method':'真实alpha脚底材料点经导出weighted mesh重心插值；不以骨端替代，不等同物理地面验收。'}
    good=all(g['finite'] and g['flips']==0 and g['collapsed']==0 and g['minPrincipalStretch']>.35 and g['maxPrincipalStretch']<1.8 for g in geometry.values())
    good &= all(g['finiteNonnegativeWeights'] and g['finiteBind'] and g['maxWeightSumError']<1e-12 for g in setup.values()) and max(loop.values())<1e-8
    return {'cycleSampleCount':193,'meshGeometry':geometry,'alphaEffectiveGeometry':alpha_geometry,'alphaEffectiveDefinition':'源纹理alpha>16的三角覆盖域；只作附加报告，完整mesh仍是验收主体。','setupWeights':setup,'firstLastMeshMaxErrorPx':loop,'footContactDrift':metrics,'footMaterialSamples':feet,'contactSlipPassed':all(m['measuredMaxDriftPx']<.1 for m in metrics.values()),'stretchThresholds':{'min':.35,'max':1.8},'numericalChecksPassed':bool(good)}


def contain(im, size, bg='white'):
    im=im.convert('RGBA');im.thumbnail(size,Image.Resampling.LANCZOS)
    tile=Image.new('RGBA',size,bg);tile.alpha_composite(im,((size[0]-im.width)//2,(size[1]-im.height)//2))
    return tile.convert('RGB')


def topology(h, sk0, sk, old, meshes, parts, designed):
    font=ImageFont.truetype(FONT,18)
    canvas=Image.new('RGB',(1680,1150),'#eef2f6');d=ImageDraw.Draw(canvas)
    d.text((20,12),'近臂 / 近腿：源alpha、完整静态拓扑与三骨权重（红body / 蓝upper / 绿lower）',font=font,fill='#20364a')
    for row,n in enumerate(['arm_near','leg_near']):
        part=parts[n];x0,y0,x1,y1=part['bbox'];scale=min(470/(x1-x0),440/(y1-y0))
        def point(p,ox,oy):return (ox+(p[0]-x0)*scale,oy+(p[1]-y0)*scale)
        for col,m in enumerate([old[n],meshes[n]]):
            ox=25+col*550;oy=100+row*520
            d.text((ox,oy-40),n+(' 旧v3' if col==0 else ' 新v4'),font=font,fill='#20364a')
            im=Image.open(STABLE/part['file']).convert('RGBA').resize((round((x1-x0)*scale),round((y1-y0)*scale)))
            canvas.paste(contain(im,im.size),(ox,oy))
            pts=h.screen(m['bind'])
            for tr in m['triangles']:
                d.line([point(pts[k],ox,oy) for k in [*tr,tr[0]]],fill='#7d93a6',width=1)
            for p,infs in zip(pts,m['influences']):
                w=[sum(v for b,local,v in infs if b==bn) for bn in ['body',n+'_upper',n+'_lower']]
                rgb=tuple(int(40+200*v) for v in [w[0],w[1],w[2]])
                px,py=point(p,ox,oy);d.ellipse((px-3,py-3,px+3,py+3),fill=rgb)
        ox=1130;oy=100+row*520
        data=designed[n]
        d.text((ox,oy-40),'沿轴带 / 根部与关节分离',font=font,fill='#20364a')
        d.text((ox,oy),f"根带 {RULE['rootBandPx']} px",font=font,fill='#8b4732')
        d.text((ox,oy+35),f"关节带 {[round(v,2) for v in data['hingeBand']]} px",font=font,fill='#20364a')
        d.text((ox,oy+70),'横向12格，不跨带长三角',font=font,fill='#20364a')
        d.text((ox,oy+105),'末端纯lower；无全局优化',font=font,fill='#20364a')
        d.text((ox,oy+140),'透明域也完整纳入几何检查',font=font,fill='#20364a')
    canvas.save(OUT/'topology_weights.png')


def render_review(h, sk0, sk, page, regions, old, meshes):
    renders=OUT/'renders';reference=OUT/'reference';renders.mkdir();reference.mkdir()
    for f in range(68,85):shutil.copyfile(REF/f'source_{f:03d}.png',reference/f'source_{f:03d}.png')
    font=ImageFont.truetype(FONT,18)
    # 先完成极限和相邻过渡，而非只挑好看姿态。
    first_frames=[68,70,72,76,78,80,69,71,73,75,77,79,81,83]
    cache={}
    raster={}
    for f in first_frames:
        i=(f-68)*2;t=(f-68)/24
        images=[]
        for prefix,skeleton,mm in [('baseline',sk0,old),('candidate',sk,meshes)]:
            im,stats=h.render(skeleton,page,regions,mm,'walk',t)
            im.save(renders/f'{prefix}_{i:02d}.png');images.append(im)
            for n,g in stats.items():raster[prefix+'/'+n]=max(raster.get(prefix+'/'+n,0),g['interiorOverlapPixels'])
        cache[i]=images
    for batch in range(2):
        fs=first_frames[:6] if batch==0 else first_frames[6:]
        sheet=Image.new('RGB',(1200,80+len(fs)*370),'#eef2f6');d=ImageDraw.Draw(sheet)
        d.text((15,12),'源视频 / 旧v3 / 新v4：同一原v3动画，图像等比例contain',font=font,fill='#20364a')
        for row,f in enumerate(fs):
            i=(f-68)*2;y=60+row*370
            ref=Image.open(reference/f'source_{f:03d}.png').crop((310,45,600,470))
            imgs=[ref]+[im.crop((155,80,625,768)) for im in cache[i]]
            for col,(im,label) in enumerate(zip(imgs,['源视频','旧v3','新v4'])):
                x=col*400;d.text((x+10,y),f'f{f} / {label}',font=font,fill='#20364a')
                sheet.paste(contain(im,(380,330)),(x+10,y+30))
        sheet.save(OUT/('review_extremes.png' if batch==0 else 'review_transitions.png'))
    # 32相位预览保留完整失败，不依赖父目录已有render。
    for i in range(32):
        if i in cache:continue
        cache[i]=[]
        for prefix,skeleton,mm in [('baseline',sk0,old),('candidate',sk,meshes)]:
            im,stats=h.render(skeleton,page,regions,mm,'walk',T*i/32)
            im.save(renders/f'{prefix}_{i:02d}.png');cache[i].append(im)
    for group in range(4):
        sheet=Image.new('RGB',(1600,760),'#eef2f6');d=ImageDraw.Draw(sheet)
        for k in range(8):
            i=group*8+k;x=(k%4)*400;y=(k//4)*380
            d.text((x+10,y+5),f'新v4 相位{i}/32 / f{68+i/2:.1f}',font=font,fill='#20364a')
            sheet.paste(contain(cache[i][1].crop((250,420,555,710)),(380,335)),(x+10,y+35))
        sheet.save(OUT/f'cycle_inspection_{group+1}.png')
    gif=[]
    for i in range(32):
        tile=Image.new('RGB',(990,510),'#eef2f6');d=ImageDraw.Draw(tile)
        refs=Image.open(reference/f'source_{68+i//2:03d}.png').crop((310,45,600,470))
        imgs=[refs]+[im.crop((155,80,625,768)) for im in cache[i]]
        for col,(im,label) in enumerate(zip(imgs,['源视频','旧v3','新v4'])):
            tile.paste(contain(im,(320,465)),(col*330,40));d.text((col*330+10,8),label,font=font,fill='#20364a')
        gif.append(tile)
    gif[0].save(OUT/'review.gif',save_all=True,append_images=gif[1:],duration=[20,20,20,20,20,20,20,30]*4,loop=0,disposal=2)
    mismatch={}
    for prefix,skeleton,mm in [('baseline',sk0,old),('candidate',sk,meshes)]:
        end,_=h.render(skeleton,page,regions,mm,'walk',T)
        mismatch[prefix]=int(np.any(np.asarray(cache[0][0 if prefix=='baseline' else 1])!=np.asarray(end),axis=2).sum())
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>05 关节结构v4独立候选</title><style>body{margin:24px;background:#eef2f6;color:#20364a;font:16px system-ui}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}section{background:white;padding:12px;border-radius:10px}img{width:100%;height:560px;object-fit:contain}.warning{color:#984831}button,input{padding:8px;margin:5px}a{color:#216d91}</style><h1>05 · joint_structure_v4 独立审稿</h1><p class="warning">仅静态轴向网格/权重改动；原七件纹理、12骨setup与v3全部动画原值。保留失败，所有production/videoFit/prototype/wardrobe验收为false。</p><button id="play">播放</button><button id="prev">上一相位</button><button id="next">下一相位</button><input id="phase" type="range" min="0" max="31" value="0"><span id="label"></span><main><section><h2>源视频原始帧</h2><img id="source"></section><section><h2>旧v3基线</h2><img id="baseline"></section><section><h2>新v4候选</h2><img id="candidate"></section></main><p><a href="review_extremes.png">极限姿态</a> · <a href="review_transitions.png">相邻过渡</a> · <a href="topology_weights.png">近臂腿拓扑权重</a> · <a href="review.gif">完整三栏GIF</a> · <a href="checks.json">实测与视觉审阅</a> · <a href="provenance.json">来源改动范围</a> · <a href="protected_hashes.json">旧文件哈希</a></p><script>let i=0,on=false,last=0;const e=id=>document.getElementById(id);function draw(){e('source').src='reference/source_'+String(68+Math.floor(i/2)).padStart(3,'0')+'.png';for(const p of ['baseline','candidate'])e(p).src='renders/'+p+'_'+String(i).padStart(2,'0')+'.png';e('phase').value=i;e('label').textContent='相位 '+i+'/32 / f'+(68+i/2).toFixed(1)}e('phase').oninput=()=>{i=+e('phase').value;on=false;draw()};e('prev').onclick=()=>{i=(i+31)%32;draw()};e('next').onclick=()=>{i=(i+1)%32;draw()};e('play').onclick=()=>{on=!on;e('play').textContent=on?'暂停':'播放'};function step(t){if(on&&t-last>=1000/48){i=(i+1)%32;draw();last=t}requestAnimationFrame(step)}draw();requestAnimationFrame(step);</script></html>'''
    (OUT/'review.html').write_text(html,encoding='utf-8')
    return mismatch,raster


def main():
    resume = sys.argv[1:] == ['--resume-owned-incomplete']
    assert not sys.argv[1:] or resume
    assert BASE.is_dir() and RIG.is_dir() and STABLE.is_dir() and REF.is_dir()
    if OUT.exists():
        if not resume:raise SystemExit('停止：joint_structure_v4已存在，绝不覆盖。')
        assert {p.name for p in OUT.iterdir()} <= {'profile_walk.atlas','profile_walk.png','profile_walk.json','profile.json','initial_incomplete_export'}
        assert load(OUT/'profile.json')['profileId'] == 'joint_structure_v4'
        assert load(OUT/'profile_walk.json')['animations'] == load(V3/'profile_walk.json')['animations']
        # 只保留并修复本次首轮未完成导出；旧源和候选不在此允许范围。
        if not (OUT/'initial_incomplete_export').exists():
            (OUT/'initial_incomplete_export').mkdir()
            for p in list(OUT.iterdir()):
                if p.is_file():shutil.copyfile(p,OUT/'initial_incomplete_export'/p.name)
    else:
        assert not resume
    # 在任何写操作前保护旧资产，包括全部03/05正式与草稿文件。
    protected={p:sha(p) for p in BASE.rglob('*') if p.is_file() and OUT not in p.parents and p!=Path(__file__).resolve() and '__pycache__' not in p.parts}
    h,safe=tools()
    source_profile=load(V2/'profile.json');sk0=load(V3/'profile_walk.json');sk=copy.deepcopy(sk0)
    manifest=load(STABLE/'manifest.json');parts={p['id']:p for p in manifest['parts']}
    assert len(parts)==7 and len(sk['bones'])==12 and len(sk['slots'])==7
    assert all(sha(STABLE/p['file'])==p['sha256'] for p in parts.values())
    if not OUT.exists():OUT.mkdir()
    for name in ['profile_walk.atlas','profile_walk.png']:shutil.copyfile(V3/name,OUT/name)
    page,regions=h.read_atlas();old=h.decode_meshes(sk0,regions);bind=h.solve(sk,'setup',0)
    designed={}
    for n,chain in source_profile['proportions']['limbChainsSourcePixels'].items():
        attachment,designed[n]=axis_mesh(n,parts[n],chain,bind,sk['bones'],safe)
        sk['skins'][0]['attachments'][n][n]=attachment
    save(OUT/'profile_walk.json',sk)
    # 数值和图像从最终落盘的Spine JSON重新读取，不用设计内存代替运行解码。
    sk=load(OUT/'profile_walk.json');meshes=h.decode_meshes(sk,regions)
    profile=copy.deepcopy(source_profile);profile['profileId']='joint_structure_v4';profile.update(FLAGS)
    profile['bind']={'bones':sk['bones'],'slots':sk['slots'],'attachments':sk['skins'][0]['attachments']}
    profile['mesh']={n:{'verticesSourcePixels':d['points'].tolist(),'triangles':d['triangles'].tolist(),'regionUV':d['uv'].tolist(),'weights':d['weights'].tolist(),'boneOrder':d['chain'],'weightBoneOrder':d['chain'],'staticWeights':True,'bindingMode':'沿轴横向带，短body根锚，肘膝局部双骨混合，末端刚性','weightRule':RULE,'axis':d['axis'],'axisRows':d['axisRows'],'hingeBand':d['hingeBand'],'optimization':{'attempted':False},'vertexCount':len(d['points']),'triangleCount':len(d['triangles'])} for n,d in designed.items()}
    save(OUT/'profile.json',profile)
    profile=load(OUT/'profile.json')
    equal=profile['bind']['bones']==sk['bones'] and profile['bind']['slots']==sk['slots'] and profile['bind']['attachments']==sk['skins'][0]['attachments']
    mesh_equal=True
    for n,m in meshes.items():
        p=profile['mesh'][n];bn=p['weightBoneOrder']
        weights=np.array([[sum(w for b,loc,w in row if b==bone) for bone in bn] for row in m['influences']])
        mesh_equal &= np.max(np.abs(weights-np.array(p['weights'])))<1e-12 and np.max(np.linalg.norm(h.screen(m['bind'])-np.array(p['verticesSourcePixels']),axis=1))<1e-8 and np.array_equal(m['triangles'],p['triangles']) and np.array_equal(m['uv'],p['regionUV'])
    baseline=evaluate(h,sk0,old,page,parts);candidate=evaluate(h,sk,meshes,page,parts)
    topology(h,sk0,sk,old,meshes,parts,designed)
    mismatch,raster=render_review(h,sk0,sk,page,regions,old,meshes)
    unchanged=all(sha(p)==digest for p,digest in protected.items())
    save(OUT/'protected_hashes.json',{'protectedRoot':str(BASE),'count':len(protected),'allUnchanged':unchanged,'files':[{'file':p.relative_to(BASE).as_posix(),'beforeSha256':digest,'afterSha256':sha(p),'unchanged':sha(p)==digest} for p,digest in protected.items()]})
    noanim=sk['animations']==sk0['animations'];bones=sk['bones']==sk0['bones'];slots=sk['slots']==sk0['slots']
    candidate['firstLastRenderMismatchPixels']=mismatch['candidate'];candidate['numericalChecksPassed'] &= mismatch['candidate']==0
    baseline['firstLastRenderMismatchPixels']=mismatch['baseline']
    checks={'schemaVersion':1,'candidateId':'joint_structure_v4',**FLAGS,'status':'candidate_pending_visual_review','visualReview':{'status':'pending','passed':False},'baseline':baseline,**candidate,'boneCount':len(sk['bones']),'slotCount':len(sk['slots']),'meshCount':len(meshes),'allV3AnimationsValueExact':noanim,'boneSetupValueExactV3':bones,'slotsValueExactV3':slots,'profileBindEqualsRuntime':equal,'profileMeshEqualsRuntime':bool(mesh_equal),'protectedOldFilesUnchanged':unchanged,'protectedOldFileCount':len(protected),'atlasAndPngByteExactV3':all(sha(OUT/n)==sha(V3/n) for n in ['profile_walk.atlas','profile_walk.png']),'newTexturePixels':0,'deformAdded':False,'newBones':0,'globalWeightOptimization':False,'candidateRuleCount':1,'rule':RULE,'renderCountPerVersion':32,'meshRasterOverlapPixels':raster,'officialSpineRuntimeVerified':False,'shoulderAndLegRootGapFree':False}
    save(OUT/'checks.json',checks)
    sources=[V2/'profile.json',V2/'profile_walk.json',V3/'profile_walk.json',V3/'checks.json',STABLE/'manifest.json',RIG/'source.mp4',BASE/'build_profile_walk.py',BASE/'build_video_guided_walk.py',BASE/'build_pose_walk_v3.py',Path(__file__)]
    provenance={'schemaVersion':1,'profileId':'joint_structure_v4',**FLAGS,'visualReview':{'status':'pending','passed':False},'sourceHashes':[{'file':p.relative_to(BASE).as_posix(),'sha256':sha(p)} for p in sources], 'changeScope':['仅四肢静态mesh拓扑、UV顶点位置和对应静态weights；七逻辑件、12骨setup、slot和v3全部animation字典逐值相同。','近臂/腿为优先修复；远臂/腿同步清理旧全局优化带来的非局部body残留，使同规则对比不混入旧非语义权重。','沿肢轴矩形域裁切横向带，根锚-12..-2px；根带与肘膝带互不重叠；末端纯lower；不扇形扎肘心，不跨带长三角。','atlas及原纹理逐字节复制，不改原像素；参考17帧仅复制到候选内。'], 'rule':RULE,'oldInputsReadOnly':True,'oldBuildMainCalled':False,'limitations':['根部隐藏搭接像素有限，短根带不保证大转肩时轮廓完整；不能用weights补画肩髋缺失面。','二维短粗肢体在固定大转肩与弯肘中仍可能翻转、压缩、露缝；完整mesh指标不因透明像素而隐藏。','CPU safe_render_mesh仅显示失败，不以栅格绕序调整声称修复翻转。','脚底按原v3支撑区间测量真实材料点，改绑定可能破坏原IK材料补偿，不修改动画重新拟合。','非Spine官方运行时或生产、视频匹配、换装验收。'], 'numericalChecksPassed':candidate['numericalChecksPassed'],'selfContainedReview':True}
    save(OUT/'provenance.json',provenance)
    assert unchanged and noanim and bones and slots and equal and mesh_equal
    print(json.dumps({'output':str(OUT),'baselineFlips':{n:g['flips'] for n,g in baseline['meshGeometry'].items()},'candidateGeometry':candidate['meshGeometry'],'feet':candidate['footContactDrift'],'numericalChecksPassed':candidate['numericalChecksPassed'],'protectedOldFileCount':len(protected),'protectedOldFilesUnchanged':unchanged,'profileRuntimeExact':bool(equal and mesh_equal)},ensure_ascii=False))


def finalize_review():
    # 此入口只在实际ViewImage审阅后更新本候选记录，不重新构建或改变几何。
    checks=load(OUT/'checks.json');provenance=load(OUT/'provenance.json')
    files=['review_extremes.png','review_transitions.png','topology_weights.png']+[f'cycle_inspection_{i}.png' for i in range(1,5)]
    visual={'status':'actually_reviewed_failed_candidate','passed':False,'inspectedWith':'ViewImage','inspectedFiles':[{'file':n,'sha256':sha(OUT/n)} for n in files], 'scope':'实际查看6个极限、8个相邻过渡，以及4张局部审阅图完整覆盖相位0..31；GIF已生成但不声称连续播放审阅。','observations':['新v4在f70..76收胸时手臂外缘局部更圆、原大扁片略收，但肩部仍宽、手掌未独立清楚，未达到源视频造型。','近腿根在完整32相位仍有斜切口、缺口和弯折；部分近脚外缘更方，不能声称腿根修复通过。','近臂/腿源件是原始可见裁片，肩髋根隐藏面不完整；权重无法提供缺失像素。','短根混合带虽然与肘膝分开，但短粗截面在固定大转肩下局部强梯度仍造成翻转；四肢统一重做也使原本无翻转远侧出现失败。','整圈保持原v3动作幅度和节奏；无动画修改或逐帧补片；数值首尾相同不代表造型或视频拟合通过。','本候选不优于原v3的完整几何稳健性，保留为失败制作证据，不进入正式入口。']}
    checks['visualReview']=visual;checks['status']='candidate_reviewed_not_accepted';checks.update(FLAGS)
    for name,geo in [('candidate',checks['meshGeometry']),('baseline',checks['baseline']['meshGeometry'])]:
        for n,g in geo.items():
            g['flipTrianglePhaseRate']=g['flips']/(193*g['triangleCount'])
    checks['comparisonCountCaution']='拓扑三角数量不同，翻转次数为三角形×相位总计；同时给出flipTrianglePhaseRate。最差面积比/SVD伸缩不依赖仅比较次数。'
    checks['implementationCorrection']={'candidateRuleCount':1,'initialIncompleteExportPreserved':'initial_incomplete_export','reason':'首轮沿轴裁切未显式加入矩形内部角投影，真实近脚材料锚点落在覆盖域外；修正为所有矩形角投影都作为横带，补全原矩形域，不更改权重参数、骨或动画。'}
    protected=load(OUT/'protected_hashes.json')
    assert all(sha(BASE/r['file'])==r['beforeSha256'] for r in protected['files'])
    checks['protectedOldFilesUnchanged']=True
    checks['referenceCopiesByteExact']=all(sha(OUT/'reference'/f'source_{f:03d}.png')==sha(REF/f'source_{f:03d}.png') for f in range(68,85))
    checks['reviewNoParentDirectoryDependencies']=('../' not in (OUT/'review.html').read_text(encoding='utf-8'))
    checks['allV3AnimationsValueExact']=load(OUT/'profile_walk.json')['animations']==load(V3/'profile_walk.json')['animations']
    checks['boneSetupValueExactV3']=load(OUT/'profile_walk.json')['bones']==load(V3/'profile_walk.json')['bones']
    assert checks['allV3AnimationsValueExact'] and checks['boneSetupValueExactV3'] and checks['referenceCopiesByteExact'] and checks['reviewNoParentDirectoryDependencies']
    checks['script']={'file':'../../../build_joint_structure_v4.py','sha256':sha(__file__)}
    checks['assetHashes']={n:sha(OUT/n) for n in ['profile.json','profile_walk.json','profile_walk.atlas','profile_walk.png','review.html','review.gif']+files}
    provenance['visualReview']=visual;provenance['status']=checks['status'];provenance['implementationCorrection']=checks['implementationCorrection']
    provenance['sourceHashes'][-1]['sha256']=sha(__file__)
    provenance.update(FLAGS)
    save(OUT/'checks.json',checks);save(OUT/'provenance.json',provenance)
    summary={'status':checks['status'],'numericalChecksPassed':checks['numericalChecksPassed'],'visualReviewPassed':False,'protectedOldFileCount':protected['count'],'oldFilesUnchanged':True,'candidate':{n:{'flips':g['flips'],'flipRate':g['flipTrianglePhaseRate'],'svd':[g['minPrincipalStretch'],g['maxPrincipalStretch']]} for n,g in checks['meshGeometry'].items()},'alphaEffectiveFlips':{n:g['flips'] for n,g in checks['alphaEffectiveGeometry'].items()},'loopRenderMismatchPixels':checks['firstLastRenderMismatchPixels']}
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    if sys.argv[1:]==['--finalize-reviewed']:finalize_review()
    else:main()
