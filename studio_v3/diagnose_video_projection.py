"""只读源资产的全局投影诊断；不导入构建器，只写projection_review_v1。"""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import hashlib
import json
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig/video_f7e82942'
OUT = RIG / 'projection_review_v1'
PACKAGE = RIG / 'video_guided_walk_v2'
REF = RIG / 'video_parts_v1/cycle_review'
FONT = 'C:/Windows/Fonts/msyh.ttc'
ANCHOR = np.array([443., 340.])
ORIGIN = np.array([410., 505.])
# 从真实源图格线和原视频图人工落点；不是自动提取或解剖关节。
LANDMARK_NAMES = ['颏下中央交界', '裤腰曲线中央', '可见腰线左端', '可见腰线右端']
SOURCE_LANDMARKS = np.array([[410,440],[410,537],[357,531],[470,520]], float)
VIDEO_LANDMARKS = {
    68: [[451,299],[448,369],[395,356],[498,358]],
    80: [[451,281],[450,351],[405,342],[498,341]],
    84: [[451,299],[448,369],[395,356],[498,358]],
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(name, value):
    assert OUT.parent.is_dir()
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    files = {p for p in BASE.iterdir() if p.suffix in ('.py','.js','.html') and p.name != Path(__file__).name}
    for folder in (RIG/'stable_parts_v1', PACKAGE):
        files.update(p for p in folder.rglob('*') if p.is_file())
    files.update(REF.glob('source_*.png'))
    files.update([RIG/'source.mp4', REF/'sources.json', RIG/'../right_front_walk/source768.png'])
    return {p.resolve().relative_to(BASE).as_posix(): sha(p) for p in sorted(files)}


def constants():
    tree = ast.parse((BASE/'build_video_guided_walk.py').read_text(encoding='utf-8'))
    result = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
              if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)
              and n.targets[0].id in ('CHAINS','CENTERS','POINTS','SCALE')}
    rows = load(PACKAGE/'evidence.json')['pointAnnotations']
    result['VISIBLE'] = {name: [r['visibleTarget'] for r in rows if r['part']==name] for name in result['CHAINS']}
    return result


def text(d, xy, value, size=16, color='#20364b'):
    d.text(xy, value, font=ImageFont.truetype(FONT,size), fill=color)


def inspect_inputs():
    assert OUT.parent.is_dir()
    OUT.mkdir(exist_ok=True)
    before = protected()
    evidence = load(PACKAGE/'evidence.json')
    manifest = load(RIG/'stable_parts_v1/manifest.json')
    source = (RIG/'stable_parts_v1'/manifest['sourceImage']['file']).resolve()
    assert sha(source)==manifest['sourceImage']['sha256']
    assert sha(RIG/'source.mp4')==manifest['sourceVideoSha256']
    cap = cv2.VideoCapture(str(RIG/'source.mp4'))
    assert cap.isOpened() and abs(cap.get(cv2.CAP_PROP_FPS)-24)<1e-6
    records = {r['frame']:r for r in evidence['videoFrames']}
    verified = []
    for frame in range(85):
        ok,bgr = cap.read()
        assert ok
        if frame>=68:
            record = records[frame]; path = BASE/record['file']
            assert sha(path)==record['sha256']
            assert np.array_equal(np.asarray(Image.open(path).convert('RGB')),cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
            verified.append({**record,'decodedPixelsExact':True})
    cap.release()
    sheet = Image.new('RGB',(1500,1400),'#eef2f5'); d=ImageDraw.Draw(sheet); cfg=constants()
    text(d,(15,8),'真实视频068–084 / 每格20px；红=可见脚轮廓代理，灰=遮挡推断，均非关节',21)
    for i,frame in enumerate(range(68,85)):
        tile=Image.open(REF/f'source_{frame:03d}.png').convert('RGB').crop((340,280,550,460)).resize((294,252))
        td=ImageDraw.Draw(tile)
        for x in range(340,551,20):
            xx=(x-340)*1.4; td.line((xx,0,xx,252),fill='#c7cdd2'); text(td,(xx+1,2),str(x),10)
        for y in range(280,461,20):
            yy=(y-280)*1.4; td.line((0,yy,294,yy),fill='#c7cdd2'); text(td,(0,yy+1),str(y),10)
        for name in ('leg_near','leg_far'):
            x,y=(np.array(cfg['POINTS'][name][i])-[340,280])*1.4
            color='#cf3028' if cfg['VISIBLE'][name][i] else '#888888'
            td.ellipse((x-4,y-4,x+4,y+4),outline=color,width=2)
        x,y=(i%5)*300,48+(i//5)*330
        sheet.paste(tile,(x,y+24)); text(d,(x+5,y),f'f{frame} / 原视频解码像素一致',14)
    sheet.save(OUT/'input_frames_contact.png')
    image=Image.open(source).convert('RGBA'); bg=Image.new('RGBA',image.size,'white'); bg.alpha_composite(image)
    crop=bg.convert('RGB').crop((280,420,510,670)).resize((690,750)); d=ImageDraw.Draw(crop)
    for x in range(280,511,10):
        xx=(x-280)*3; d.line((xx,0,xx,750),fill='#c9cdd2'); text(d,(xx,0),str(x),11)
    for y in range(420,671,10):
        yy=(y-420)*3; d.line((0,yy,690,yy),fill='#c9cdd2'); text(d,(0,yy),str(y),11)
    crop.save(OUT/'source_landmark_grid.png')
    save('input_verification.json',{'sourceImage':str(source),'sourceImageSha256':sha(source),
         'sourceVideoSha256':sha(RIG/'source.mp4'),'frames':verified,
         'method':'独立顺序解码原视频068..084，逐像素比较原PNG；未执行构建。'})
    return evidence,source,before,cfg


def observations(cfg):
    result=[]
    for name,chain in cfg['CHAINS'].items():
        a,b,c=np.array(chain,float); l1=np.linalg.norm(b-a); l2=np.linalg.norm(c-b)
        for i,p in enumerate(cfg['POINTS'][name]):
            result.append({'part':name,'frame':68+i,'visible':bool(cfg['VISIBLE'][name][i]),
                           'point':np.array(p,float),'center':np.array(cfg['CENTERS'][i],float),
                           'root':a,'lower':abs(l1-l2),'upper':l1+l2,'lengths':[float(l1),float(l2)]})
    return result


def reach_rows(obs, scale, origin):
    rows=[]
    for o in obs:
        root=o['root']+scale*(o['center']-ANCHOR)
        target=np.asarray(origin)+scale*(o['point']-ANCHOR)
        v=target-root; distance=float(np.linalg.norm(v))
        error=max(o['lower']-distance,0,distance-o['upper'])
        # 无关节角限制的双骨可达环；与构建器0.3px留量分开报告。
        endpoint=root+v/distance*np.clip(distance,o['lower'],o['upper'])
        rows.append({'part':o['part'],'frame':o['frame'],'visibleContourProxy':o['visible'],
                     'videoPoint':o['point'].tolist(),'inferredRoot':root.tolist(),'mappedTarget':target.tolist(),
                     'boneLengths':o['lengths'],'innerReachPx':float(o['lower']),'outerReachPx':float(o['upper']),
                     'distancePx':distance,'outerMarginPx':float(o['upper']-distance),
                     'unreachablePx':float(error),'geometricallyReachable':bool(error<1e-6),
                     'nearestFreeIKEndpoint':endpoint.tolist(),'rootOrJointIsObservation':False})
    return rows


def summary(rows):
    result={}
    for name in sorted({r['part'] for r in rows}):
        rs=[r for r in rows if r['part']==name and r['visibleContourProxy']]
        worst=max(rs,key=lambda r:r['unreachablePx'])
        result[name]={'visibleCount':len(rs),'unreachableCount':sum(not r['geometricallyReachable'] for r in rs),
                      'maxUnreachablePx':worst['unreachablePx'],'worstFrame':worst['frame'],
                      'outerReachPx':worst['outerReachPx']}
    return result


def disk_feasible(obs,scale):
    """固定scale时枚举圆心及两圆交点，检验共有平移可行域；非残差优化。"""
    centers=np.array([o['root']-scale*(o['point']-o['center']) for o in obs])
    radii=np.array([o['upper'] for o in obs]); lower=np.array([o['lower'] for o in obs])
    candidates=[ORIGIN,centers.mean(axis=0),*centers]
    # 内外边界都要枚举；只枚举外圆会漏掉被内圆切出的可行片区。
    boundary_centers=np.concatenate((centers,centers[lower>0]))
    boundary_radii=np.concatenate((radii,lower[lower>0]))
    for center,radius in zip(boundary_centers,boundary_radii):
        candidates.extend(center+radius*np.array([[1,0],[-1,0],[0,1],[0,-1]]))
    for i in range(len(boundary_radii)):
        for j in range(i):
            v=boundary_centers[j]-boundary_centers[i]; dist=np.linalg.norm(v)
            ri,rj=boundary_radii[i],boundary_radii[j]
            if dist<1e-10 or dist>ri+rj+1e-9 or dist<abs(ri-rj)-1e-9: continue
            a=(ri**2-rj**2+dist**2)/(2*dist)
            h=math.sqrt(max(0,ri**2-a*a)); direction=v/dist
            q=boundary_centers[i]+a*direction; normal=np.array([-direction[1],direction[0]])
            candidates.extend((q+h*normal,q-h*normal))
    candidates=np.array(candidates)
    distances=np.linalg.norm(candidates[:,None,:]-centers[None,:,:],axis=2)
    eligible=np.all((distances<=radii+1e-7)&(distances>=lower-1e-7),axis=1)
    if not eligible.any(): return None
    valid=candidates[eligible]
    return valid[np.argmin(np.linalg.norm(valid-ORIGIN,axis=1))]


def max_scale_free_translation(obs):
    # 在已确认可行点上取上界；外圆交集的尺度投影是区间；最后复核内圆排除区。
    lo,hi=.8,2.0
    assert disk_feasible(obs,lo) is not None and disk_feasible(obs,hi) is None
    for _ in range(35):
        mid=(lo+hi)/2
        if disk_feasible(obs,mid) is None: hi=mid
        else: lo=mid
    t=disk_feasible(obs,lo)
    return lo,t


def torso_metrics(scale,origin,cfg):
    metrics=[]; errors=[]
    source_height=SOURCE_LANDMARKS[1,1]-SOURCE_LANDMARKS[0,1]
    source_width=SOURCE_LANDMARKS[3,0]-SOURCE_LANDMARKS[2,0]
    for frame,points in VIDEO_LANDMARKS.items():
        points=np.array(points,float)
        # 统一映射后扣除已有胸腹运动，和静态源图比较；不额外逐帧配准。
        shift=scale*(np.array(cfg['CENTERS'][frame-68])-ANCHOR)
        mapped=np.asarray(origin)+scale*(points-ANCHOR)-shift
        residual=np.linalg.norm(mapped-SOURCE_LANDMARKS,axis=1); errors.extend(residual.tolist())
        h=points[1,1]-points[0,1]; w=points[3,0]-points[2,0]
        metrics.append({'frame':frame,'videoLandmarks':points.tolist(),'mappedBodyLocalLandmarks':mapped.tolist(),
                        'landmarkErrorsSourcePx':residual.tolist(),'torsoHeightVideoPx':float(h),'waistWidthVideoPx':float(w),
                        'requiredScaleHeight':float(source_height/h),'requiredScaleWidth':float(source_width/w),
                        'mappedHeightSourceRatio':float(scale*h/source_height),'mappedWidthSourceRatio':float(scale*w/source_width)})
    return {'frames':metrics,'landmarkRmsSourcePx':float(np.sqrt(np.mean(np.square(errors)))),
            'sourceTorsoHeightPx':float(source_height),'sourceVisibleWaistWidthPx':float(source_width),
            'translationCannotChangeSpanRatios':True}


def landmark_fit(cfg):
    x=[]; y=[]
    for frame,points in VIDEO_LANDMARKS.items():
        x.extend(np.array(points,float)-ANCHOR-(np.array(cfg['CENTERS'][frame-68])-ANCHOR))
        y.extend(SOURCE_LANDMARKS)
    x=np.array(x); y=np.array(y); xc=x-x.mean(axis=0); yc=y-y.mean(axis=0)
    s=float(np.sum(xc*yc)/np.sum(xc*xc)); origin=y.mean(axis=0)-s*x.mean(axis=0)
    return s,origin


def make_contact(source,cases,cfg):
    sheet=Image.new('RGB',(1800,1330),'#f1f4f7'); d=ImageDraw.Draw(sheet)
    text(d,(20,10),'隔离投影诊断 / 非生产验收；红=可见代理，灰=遮挡推断，蓝=自由IK最近端点',23)
    source_image=Image.open(source).convert('RGBA'); white=Image.new('RGBA',source_image.size,'white'); white.alpha_composite(source_image)
    for col,(name,case) in enumerate(cases.items()):
        x=col*450+15; text(d,(x,55),name,19)
        text(d,(x,85),f"s={case['scale']:.5f}  锚点={np.round(case['sourceAnchor'],1)}",14)
        panel=white.convert('RGB').crop((280,420,540,700)).resize((390,420)); pd=ImageDraw.Draw(panel)
        scale=case['scale']; origin=np.array(case['sourceAnchor']); frame=74
        for row in case['rows']:
            if row['frame']!=frame: continue
            root=(np.array(row['inferredRoot'])-[280,420])*1.5
            target=(np.array(row['mappedTarget'])-[280,420])*1.5
            endpoint=(np.array(row['nearestFreeIKEndpoint'])-[280,420])*1.5
            r=row['outerReachPx']*1.5
            pd.ellipse((root[0]-r,root[1]-r,root[0]+r,root[1]+r),outline='#91acbd',width=1)
            pd.line([tuple(root),tuple(endpoint)],fill='#2477ab',width=2)
            color='#d43e2f' if row['visibleContourProxy'] else '#888888'
            pd.ellipse((* (target-4),* (target+4)),outline=color,width=2)
            pd.line([tuple(endpoint),tuple(target)],fill=color,width=2)
        sheet.paste(panel,(x,120)); text(d,(x,545),'f74 源图背景仅表示原比例，不是动画渲染',13)
        for rowi,frame in enumerate((68,80)):
            panel=white.convert('RGB').crop((320,420,500,570)).resize((360,300)); pd=ImageDraw.Draw(panel)
            shift=scale*(np.array(cfg['CENTERS'][frame-68])-ANCHOR)
            for j,(src,vp) in enumerate(zip(SOURCE_LANDMARKS,VIDEO_LANDMARKS[frame])):
                sp=(src-[320,420])*2
                mp=(origin+scale*(np.array(vp)-ANCHOR)-shift-[320,420])*2
                pd.line([tuple(sp),tuple(mp)],fill='#ce4636',width=2)
                pd.ellipse((*(sp-4),*(sp+4)),fill='#2477ab')
                pd.ellipse((*(mp-4),*(mp+4)),outline='#ce4636',width=2)
                text(pd,tuple(sp+[4,0]),str(j+1),13)
            y=590+rowi*350; sheet.paste(panel,(x,y)); text(d,(x,y+305),f'f{frame} 蓝=源地标 红=视频映射（扣胸腹位移）',13)
    sheet.save(OUT/'contact_reachability.png')


def diagnose():
    evidence,source,before,cfg=inspect_inputs(); obs=observations(cfg)
    visible=[o for o in obs if o['visible']]
    smax,tmax=max_scale_free_translation(visible)
    sfit,tfit=landmark_fit(cfg)
    # 固定原锚点仅比较上限，不将其当最终比例选择。
    grid=np.linspace(.75,1.6,341)
    candidates=[(max(r['unreachablePx'] for r in reach_rows(visible,s,ORIGIN)),float(s)) for s in grid]
    best=max(((-err,s) for err,s in candidates))[1]
    cases={}
    for name,s,t in [('原映射1.45',1.45,ORIGIN),('只改scale的残差最小对照',best,ORIGIN),
                     ('可见臂腿最大可达scale+固定平移',smax,tmax),('仅躯干地标拟合的固定映射',sfit,tfit)]:
        rows=reach_rows(obs,s,t)
        cases[name]={'scale':float(s),'sourceAnchor':np.asarray(t).tolist(),
                     'translationInP_equals_sP_plus_t':(np.asarray(t)-s*ANCHOR).tolist(),
                     'scaleRelativeTo145':float(s/1.45),'rows':rows,'visibleSummary':summary(rows),
                     'torso':torso_metrics(s,t,cfg)}
    f74=next(r for r in cases['原映射1.45']['rows'] if r['frame']==74 and r['part']=='leg_far')
    existing=next(r for r in evidence['pointAnnotations'] if r['frame']==74 and r['part']=='leg_far')
    assert abs(f74['unreachablePx']+.3-existing['fixedLengthProjectionResidualPx'])<1e-6
    # 高度和腰宽的敏感性区间：每地标源±3/视频±4，是人工扰动预算，不是统计置信区间。
    height_interval=[(97-6)/(70+8),(97+6)/(70-8)]
    width_interval=[(113-6)/(103+8),(113+6)/(93-8)]
    check=load(PACKAGE/'checks.json')
    result={'schemaVersion':2,'status':'diagnostic_rejected_as_mapping_only_solution','productionApproved':False,
            'prototypeAccepted':False,'automaticGroundTruth':False,
            'coordinateContract':{'rule':'target=T+s*(video-[443,340]); inferredRoot=a+s*(center_i-[443,340]); a/骨长/纹理比例保持源图不变。',
                'TMeaning':'一个全片统一源锚点；等价全局平移t=T-s*[443,340]。不是各肢体或各帧平移。',
                'rotation':'保持既有零旋转，只变一个scale和一个translation',
                'bodyMotion':'沿用既有CENTERS序列，不重新拟合逐帧根；该已存在胸腹运动不等于新增逐帧映射。'},
            'observedBasis':{'sourceImage':str(source),'sourceSha256':sha(source),'frames':list(range(68,85)),
                'actuallyReviewedImages':['input_frames_contact.png','source_landmark_grid.png','source_068.png','source_074.png','source_080.png','source_084.png'],
                'sourceLandmarkNames':LANDMARK_NAMES,'sourceLandmarks':SOURCE_LANDMARKS.tolist(),'videoLandmarks':VIDEO_LANDMARKS,
                'manualSelection':'本次实际查看真实图和坐标格后人工落点；颏下交界与腰线是可见轮廓，不是颈关节/髋。仅68/80/84选择较少胸前遮挡的躯干约束，70–77不声称完整躯干观测。',
                'excludedInvalidMeasurement':'整行前景/alpha宽度混入头发和手臂，已排除；不得用作躯干宽度。',
                'uncertainty':'源地标±3px、视频地标±4px作敏感性预算；已有手脚代理±4..8视频px，均非实测准确度。',
                'headProportion':'源头部约410x347，视频头部约318x250（宽松全轮廓估计），所需scale约1.29/1.39；仅辅助，不用于优化。'},
            'frame74LegFar':{**f74,'semantic':'[509,426]为可见脚下部轮廓中心代理；无物理点身份保证。根/膝均绑定推断，非自动真值。',
                'existingRuntimeResidualPx':existing['materialResidualPx'],'builderReachSafetyMarginPx':.3,
                'lengthMultiplierNeededIfIllegalLimbScaling':float(f74['distancePx']/f74['outerReachPx']),
                'rootDisplacementLowerBoundAtFixed145Px':f74['unreachablePx'],
                'residualAfter8VideoPxProxyPerturbationLowerBound':max(0,f74['unreachablePx']-8*1.45),
                'rootUncertaintyNotIncluded':'推断根未有测量误差界，故这不是无条件人体不可达性证明。'},
            'cases':cases,'globalFeasibility':{'largestScaleWithAnyFixedTranslation':smax,'sourceAnchorAtBoundary':tmax.tolist(),
                'allVisibleArmAndLegTargetsIncluded':len(visible),'hiddenTargetsExcluded':len(obs)-len(visible),
                'method':'固定scale枚举外可达圆交点并验证全部可达环；35步二分最大scale，保留内半径约束；只诊断不运行权重/动画优化。',
                'torsoHeightSensitivityScaleInterval':height_interval,'waistWidthSensitivityScaleInterval':width_interval,
                'torsoHeightIntervalDisjointFromReachableScaleCeiling':bool(height_interval[0]>smax),
                'sensitivityIsNotStatisticalConfidence':True},
            'existingChecksReadOnly':{'videoFitPassed':check['videoFitPassed'],'meshNoFlipsPassed':check['meshNoFlipsPassed'],
                'legNearFlips':check['meshGeometry']['leg_near']['flips'],'runtimeNotRebuilt':True},
            'conclusion':{'decision':'拒绝仅靠全局scale+translation修复当前视频匹配；可继续的只是明确放宽造型/地标/绑定根假设后的隔离实验，不提升运行包。',
                'constraints':['固定1.45下f74远腿目标距离超出源固定骨长，换IK弯膝分支或调权重不能扩大可达圆。',
                    '允许固定全局平移仍受两臂两腿多帧同时触达约束；缩小映射使躯干纵向短于源角色，平移不能修复跨度。',
                    '源角色头/躯干/腰线/腿长与视频转面及扁脚的比例不完全一致；一个相似映射不能产生非等比或逐帧造型变化。',
                    '根/膝遮挡与代理材料点身份不明，当前结论条件于现有绑定；无自动关节真值。',
                    '近臂补画/肩髋隐藏面/拓扑和近腿折叠由主代理处理，本脚本不修改亦不验收这些问题。']},
            'protectedInputHashesBefore':before,'scriptSha256':sha(Path(__file__))}
    make_contact(source,cases,cfg)
    after=protected(); assert before==after,'受保护输入在诊断期间发生变化'
    result['protectedInputsUnchanged']=True
    save('projection_diagnosis.json',result)
    save('protected_input_check.json',{'unchanged':True,'protectedFileCount':len(before),'beforeSha256':before,'afterSha256':after,
         'scope':'studio_v3既有py/js/html、stable_parts_v1、video_guided_walk_v2、源视频/源图/PNG；新增诊断文件不在其中'})
    print(json.dumps({'output':str(OUT),'maxReachableScale':smax,'maxReachableSourceAnchor':tmax.tolist(),
         'torsoOnlyScale':sfit,'heightSensitivityInterval':height_interval,
         'caseSummary':{n:{'scale':c['scale'],'visibleSummary':c['visibleSummary'],'torsoRms':c['torso']['landmarkRmsSourcePx']} for n,c in cases.items()},
         'protectedInputsUnchanged':True},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='只读运行资产，隔离输出投影诊断')
    parser.add_argument('--inspect',action='store_true',help='只生成真实图像坐标审阅图')
    args=parser.parse_args()
    if args.inspect: inspect_inputs()
    else: diagnose()
