"""Automatic source-frame proposals. Vision output never implies human approval."""
import base64, copy, hashlib, json, os, threading, time, urllib.request, urllib.error
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pixel_workbench as pw

CONTRACT = 'pixel_sync_20261120/1'
DETECTOR_VERSION = 2
MODEL = 'doubao-seed-2-1-pro-260915'
ACTIVE = set()

def fingerprint(p):
    data = {k:p[k] for k in ('source','frames','order')}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def retry_detection(operation, progress, frame):
    """Retry transient service or malformed-output failures; never mark success early."""
    for attempt in range(3):
        try:return operation()
        except (ValueError, KeyError, TypeError, OSError) as exc:
            progress(event='retry' if attempt<2 else 'failed_request',frame=frame,attempt=attempt+1,error=str(exc)[:500])
            if attempt==2:raise
            progress(message=f'源帧 {frame} 识别暂未完成，正在重试 {attempt+1}/2')
            time.sleep(attempt+1)


def infer(path, width, height):
    base = os.environ.get('ARK_BASE_URL','').rstrip('/')
    key = os.environ.get('ARK_API_KEY')
    if not base.startswith('https://') or not key:
        raise ValueError('未配置视觉识别服务 ARK_BASE_URL / ARK_API_KEY')
    prompt = f'''Analyze the plush character in this {width}x{height} source video frame.
Return JSON only. ALL coordinates MUST be normalized 0..1000 integers: x=1000*pixelX/imageWidth, y=1000*pixelY/imageHeight. No markdown.
Schema: {{"points":{{name:[x,y]}},"joints":{{name:[x,y]}},"polygons":{{part:[[x,y],...]}},"uncertainties":["..."]}}.
points keys: {','.join(pw.POINTS)}. joints keys: {','.join(pw.CHAINS)}.
polygons keys: {','.join(pw.PARTS)}. Use 12-40 contour vertices per visible part.
Near/far refer to camera depth, NOT character left/right. Preserve the same identities.
Shoulder and hip roots are attachment centers, hands/feet endpoints are distal-region centers,
elbows/knees follow the visible limb axis. Do not mistake fingers or pants hem for joints.
Separate pants (shorts) from both legs; torso excludes head and arms. Include original visible
fur pixels, exclude background. No invented hidden anatomy: record uncertain/occluded points
or parts in uncertainties. Polygons describe VISIBLE pixels only, no repaint or hallucinated fill.
This is detection only. Do not claim validation or approval.'''
    body = dict(model=os.environ.get('PIXEL_VISION_MODEL',MODEL),temperature=0,max_tokens=6500,
        response_format={'type':'json_object'},thinking={'type':'disabled'},messages=[dict(role='user',content=[dict(type='text',text=prompt),
        dict(type='image_url',image_url={'url':'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()})])])
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=150) as r: result=json.load(r)
    except urllib.error.HTTPError as e:
        raise ValueError(f'视觉接口 HTTP {e.code}；未修改工程') from None
    except (OSError,TimeoutError):
        raise ValueError('视觉接口连接失败或超时；可重试，已有逐帧响应保留') from None
    from pixel_vision_response import parse_response
    value=parse_response(result,path,'coarse')
    for field,keys in [('points',pw.POINTS),('joints',pw.CHAINS),('polygons',pw.PARTS)]:
        if isinstance(value.get(field),dict):value[field]={k:v for k,v in value[field].items() if k in keys}
    validate(value,1000,1000)
    for field in ('points','joints'):
        value[field]={k:[q[0]*width/1000,q[1]*height/1000] for k,q in value[field].items()}
    value['polygons']={k:[[q[0]*width/1000,q[1]*height/1000] for q in poly] for k,poly in value['polygons'].items()}
    value['coordinateSpace']='source_pixels'
    return value

def validate(v,w,h):
    for field,keys in [('points',pw.POINTS),('joints',pw.CHAINS),('polygons',pw.PARTS)]:
        if not isinstance(v.get(field),dict) or set(v[field])!=set(keys):
            raise ValueError('识别结果缺少必要字段：'+field)
        for value in v[field].values():
            if field=='polygons':
                if not isinstance(value,list) or not 3<=len(value)<=256: raise ValueError('部件轮廓不完整')
                for q in value: pw.xy(q,w,h)
            else: pw.xy(value,w,h)
    if not isinstance(v.get('uncertainties'),list): raise ValueError('缺少遮挡/不确定性记录')

def segment(rgb,polygons,refined=None,hidden=()):
    """Uniform-background scope only. Never synthesize RGB or use sample masks."""
    h,w=rgb.shape[:2]
    corners=np.concatenate([rgb[:8,:8].reshape(-1,3),rgb[:8,-8:].reshape(-1,3),
                            rgb[-8:,:8].reshape(-1,3),rgb[-8:,-8:].reshape(-1,3)]).astype(float)
    if np.max(np.std(corners,axis=0))>12:
        raise ValueError('当前自动拆件仅支持均匀背景；该视频需要更强的分割模型')
    foreground=(np.max(np.abs(rgb.astype(float)-np.median(corners,axis=0)),axis=2)>18).astype(np.uint8)
    contours,_=cv2.findContours(foreground,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours: raise ValueError('没有可分离的角色前景')
    sil=np.zeros((h,w),np.uint8);cv2.drawContours(sil,[max(contours,key=cv2.contourArea)],-1,255,-1)
    masks={};union=np.zeros((h,w),bool)
    # Keep model ownership; unexplained pixels are an exception, never silently assign to a limb.
    for n in pw.PARTS:
        mask=np.zeros((h,w),np.uint8)
        if refined is None:cv2.fillPoly(mask,[np.array(polygons[n],np.int32)],255)
        else:mask=refined[n] if n not in hidden else np.zeros((h,w),np.uint8)
        masks[n]=cv2.bitwise_and(mask,sil);union|=masks[n]>0
    missing=(sil>0)&~union
    initial_missing=int(np.count_nonzero(missing))
    if refined is not None:
        from skimage.segmentation import watershed
        # Only consensus interiors become seeds. Image gradients decide the remaining
        # boundaries; source foreground is partitioned rather than hidden by overlaps.
        strengths=[]
        for n in pw.PARTS:
            prior=np.zeros((h,w),np.uint8);cv2.fillPoly(prior,[np.array(polygons[n],np.int32)],1)
            inside=cv2.distanceTransform(prior,cv2.DIST_L2,5)
            strengths.append(np.where((inside>=2)&(refined[n]>0)&(sil>0)&(n not in hidden),inside/max(1,float(inside.max())),0))
        strengths=np.stack(strengths)
        # A confident near arm or clothing interior owns its pixels before deeper
        # layers. Broad torso polygons must not steal the hand or pants opening.
        for front in ('arm_near','shorts','head'):
            i=pw.PARTS.index(front);foreground_seed=strengths[i]>.2
            for behind in range(i):strengths[behind][foreground_seed]=0
        seed_score=np.max(strengths,axis=0)
        markers=np.where(seed_score>0,np.argmax(strengths,axis=0)+1,0).astype(np.int32)
        for i,n in enumerate(pw.PARTS):
            if n not in hidden and not np.any(markers==i+1):raise ValueError('分割缺少可信的部件内部像素：'+n)
        lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
        blur=cv2.GaussianBlur(lab,(3,3),.7)
        gradient=np.sqrt(np.sum(cv2.Sobel(blur,cv2.CV_32F,1,0)**2+cv2.Sobel(blur,cv2.CV_32F,0,1)**2,axis=2))
        owner=watershed(gradient,markers,mask=sil>0)
        masks={n:np.where(owner==i+1,255,0).astype(np.uint8) for i,n in enumerate(pw.PARTS)}
        # Coverage is a structural invariant here, not a semantic accuracy claim.
        seams=np.zeros((h,w),bool)
        seams[:,1:]|=(owner[:,1:]!=owner[:,:-1])&(owner[:,1:]>0)&(owner[:,:-1]>0)
        seams[1:,:]|=(owner[1:,:]!=owner[:-1,:])&(owner[1:,:]>0)&(owner[:-1,:]>0)
        weak=seams&(gradient<24)
        return masks,dict(initialUncoveredPixels=initial_missing,boundaryExtendedPixels=int(np.count_nonzero((sil>0)&(markers==0))),
            ambiguousBoundaryPixels=int(np.count_nonzero(weak)),foregroundPixels=int(np.count_nonzero(sil)),
            uncoveredPixels=int(np.count_nonzero((sil>0)&(owner==0))),coverage=float(np.count_nonzero(owner)/max(1,np.count_nonzero(sil))),
            method='SAM2/vision consensus seeds + source gradient watershed',seedPixels=int(np.count_nonzero(markers)),
            partitionIsNotSemanticValidation=True)

    # Extend only locally into observed foreground; never fill hidden/background RGB.
    # Ambiguous inter-part boundaries remain explicit exceptions, not quality proof.
    distances=np.stack([cv2.distanceTransform((masks[n]==0).astype(np.uint8),cv2.DIST_L2,3) for n in pw.PARTS])
    nearest=np.argmin(distances,axis=0);ordered=np.sort(distances,axis=0)
    nearby=missing & (ordered[0]<=(3 if refined is not None else max(3,min(h,w)*.035)))
    ambiguous=nearby & ((ordered[1]-ordered[0])<2)
    for index,n in enumerate(pw.PARTS):
        masks[n][nearby & (nearest==index)]=255
    union=np.any(np.stack([m>0 for m in masks.values()]),axis=0)
    missing=(sil>0)&~union
    return masks,dict(initialUncoveredPixels=initial_missing,
        boundaryExtendedPixels=int(np.count_nonzero(nearby)),
        ambiguousBoundaryPixels=int(np.count_nonzero(ambiguous)),foregroundPixels=int(np.count_nonzero(sil)),
        uncoveredPixels=int(np.count_nonzero(missing)),
        coverage=float(np.count_nonzero(union)/max(1,np.count_nonzero(sil))))

def geometry(f,masks,previous=None):
    issues=[]
    def issue(code,part,detail): issues.append(dict(frame=f['frame'],code=code,part=part,detail=detail))
    for n,(start,end) in pw.CHAINS.items():
        a,b,c=[np.array(q,float) for q in (f['points'][start],f['joints'][n],f['points'][end])]
        lengths=[float(np.linalg.norm(b-a)),float(np.linalg.norm(c-b))]
        if min(lengths)<2: issue('degenerate_chain',n,'骨骼长度不足 2 像素')
        distance=cv2.distanceTransform((masks[n]==0).astype(np.uint8),cv2.DIST_L2,3)
        # Visible endpoints must have skin support, independently of inverse binding.
        x,y=np.rint(c).astype(int);y=np.clip(y,0,distance.shape[0]-1);x=np.clip(x,0,distance.shape[1]-1)
        if f.get('parts',{}).get(n,{}).get('visible') is not False and distance[y,x]>max(3,min(lengths)*.2): issue('endpoint_outside_skin',n,'手脚端点缺少对应部件像素支持')
        cross=float((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
        if abs(cross)<1: issue('ambiguous_bend',n,'肘膝接近共线，弯曲方向无法可靠判断')
        if previous:
            pa,pb,pc=[np.array(q,float) for q in (previous['points'][start],previous['joints'][n],previous['points'][end])]
            old=(pb[0]-pa[0])*(pc[1]-pb[1])-(pb[1]-pa[1])*(pc[0]-pb[0])
            if (cross>=0)!=(old>=0): issue('bend_flip',n,'相邻帧 IK 弯曲方向翻转；需要重新识别，不能强制翻折')
            if np.linalg.norm(c-pc)>max(8,sum(lengths)*.25): issue('endpoint_jump',n,'相邻帧手脚端点跳变')
            for length,prior in zip(lengths,[np.linalg.norm(pb-pa),np.linalg.norm(pc-pb)]):
                if prior>0 and not .7<=length/prior<=1.3: issue('length_jump',n,'相邻帧投影骨长变化超过 30%')
    for n,mask in masks.items():
        if f.get('parts',{}).get(n,{}).get('visible') is not False and np.count_nonzero(mask)<4: issue('empty_part',n,'没有足够可见原像素')
    return issues

def fit_sequence(frames):
    """Choose one IK bend per chain, fit stable projected lengths to observed endpoints.

    Output is a constrained 2D estimate, not independently recovered hidden anatomy.
    Large changes remain blocking exceptions; raw detections are retained in cache.
    """
    notes=[]
    for n,(start,end) in pw.CHAINS.items():
        lengths=np.array([[np.linalg.norm(np.array(f['joints'][n])-f['points'][start]),
                           np.linalg.norm(np.array(f['points'][end])-f['joints'][n])] for f in frames])
        l1,l2=np.median(lengths,axis=0)
        if min(l1,l2)<2: continue
        choices=[]
        for sign in (-1,1):
            joints=[];score=0
            for f in frames:
                root=np.array(f['points'][start],float);target=np.array(f['points'][end],float)
                delta=target-root;distance=float(np.linalg.norm(delta))
                if distance<1: joints.append(np.array(f['joints'][n],float));score+=1e6;continue
                # Only minimal reach accommodation; no unconstrained frame-to-frame bone scaling.
                reach=max(1.,distance/(l1+l2)*1.02)
                upper,lower=l1*reach,l2*reach
                along=(upper*upper-lower*lower+distance*distance)/(2*distance)
                height=np.sqrt(max(0.,upper*upper-along*along));axis=delta/distance
                q=root+axis*along+sign*np.array([-axis[1],axis[0]])*height
                score+=float(np.sum((q-f['joints'][n])**2));joints.append(q)
            choices.append((score,joints))
        fitted=min(choices,key=lambda x:x[0])[1]
        for f,q in zip(frames,fitted):
            residual=float(np.linalg.norm(q-f['joints'][n]))
            if residual>max(4.,(l1+l2)*.12):
                notes.append(dict(frame=f['frame'],code='fit_disagreement',part=n,
                    detail=f'时序 IK 拟合与视觉关节相差 {residual:.1f} px，需检查遮挡或重新识别'))
            if not (0<=q[0]<=100000 and 0<=q[1]<=100000):
                notes.append(dict(frame=f['frame'],code='invalid_fit',part=n,detail='关节拟合越界'))
                continue
            f['joints'][n]=q.tolist()
    return notes

def stabilize_identity(value, neighbors):
    """Repair isolated near/far swaps only when surrounding frames agree strongly.

    No absolute screen-side convention: rear views may have near limbs on the right.
    Ambiguous or rotating sequences retain the detector result for human inspection.
    """
    result=copy.deepcopy(value);repairs=[]
    for limb,root,end in [('arm','shoulder','hand'),('leg','hip','foot')]:
        differences=[n['points'][root+'_near'][0]-n['points'][root+'_far'][0] for n in neighbors]
        if len(differences)<4:continue
        signs=np.sign(differences);median=float(np.median(differences))
        if abs(median)<10 or np.count_nonzero(signs==np.sign(median))<len(signs)*.8:continue
        current=result['points'][root+'_near'][0]-result['points'][root+'_far'][0]
        if current*median>=0:continue
        distal=[n['points'][end+'_near'][0]-n['points'][end+'_far'][0] for n in neighbors]
        distal_median=float(np.median(distal))
        current_distal=result['points'][end+'_near'][0]-result['points'][end+'_far'][0]
        # A crossed/mislocated hip alone is not proof that the whole leg identity flipped.
        if abs(distal_median)<10 or current_distal*distal_median>=0:continue
        if np.count_nonzero(np.sign(distal)==np.sign(distal_median))<len(distal)*.8:continue
        for point in (root,end):
            a,b=point+'_near',point+'_far';result['points'][a],result['points'][b]=result['points'][b],result['points'][a]
        a,b=limb+'_near',limb+'_far'
        for field in ('joints','polygons'):result[field][a],result[field][b]=result[field][b],result[field][a]
        result['hiddenParts']=[b if n==a else a if n==b else n for n in result.get('hiddenParts',[])]
        repairs.append(dict(limb=limb,method='surrounding-frame consensus',neighbors=len(neighbors),medianRootSeparation=median))
    return result,repairs


def status(pid):
    path=pw.folder(pid)/'automation/job.json'
    if not path.is_file(): return dict(state='idle')
    result=pw.read(path)
    if result.get('state')=='running' and result.get('startedAt'):result['elapsedSeconds']=round(time.time()-result['startedAt'],1)
    if result['state']=='running' and pid not in ACTIVE:
        result.update(state='interrupted',message='服务曾重启；点击自动生成可复用已保存的识别结果')
    return result

def start(payload):
    p=pw.load(payload['id']);pid=p['id']
    if p['revision']!=payload['revision']: raise ValueError('工程版本已更新')
    if pid in ACTIVE: return status(pid)
    if p['baseline']: raise ValueError('已验收样板保持只读；请导入视频建立独立工程后自动分析')
    if not os.environ.get('ARK_API_KEY'): raise ValueError('未配置视觉识别服务')
    import importlib.util
    missing=[n for n in ('torch','torchvision','transformers','scipy','skimage') if importlib.util.find_spec(n) is None]
    if missing:raise ValueError('自动分割依赖未安装：'+', '.join(missing)+'；请安装 requirements-pixel-vision.txt')
    ACTIVE.add(pid)
    job=dict(state='running',startedAt=time.time(),completed=0,total=len(p['frames']),revision=p['revision'],message='正在逐帧识别原视频')
    pw.write(pw.folder(pid)/'automation/job.json',job)
    threading.Thread(target=worker,args=(copy.deepcopy(p),job),daemon=True).start()
    return job

def reuse_source_cache(p):
    """Reuse machine observations only for the exact video/frame/model/version."""
    import shutil
    import pixel_detail
    copied=0;destination=pw.folder(p['id'])/'automation'
    destination.mkdir(parents=True,exist_ok=True)
    model=os.environ.get('PIXEL_VISION_MODEL',MODEL)
    for entry in pw.listing():
        if entry['id']==p['id']:continue
        other=pw.load(entry['id'])
        if other['source'].get('identity')!=p['source'].get('identity'):continue
        source=pw.folder(other['id'])/'automation'
        for f in p['frames']:
            digest=pw.sha(pw.folder(p['id'])/'frames'/f"{f['frame']:04}.png")
            name=f"vision_{f['frame']}_{digest[:16]}.json";cache=source/name
            if (destination/name).exists() or not cache.exists():continue
            record=pw.read(cache)
            if not (record.get('sourceSha256')==digest and record.get('model')==model and record.get('contract')==CONTRACT and record.get('detectorVersion')==DETECTOR_VERSION):continue
            shutil.copy2(cache,destination/name);copied+=1
            detail=f"detail_{f['frame']}_v{pixel_detail.VERSION}.json"
            if (source/detail).exists() and pw.read(source/detail).get('sourceSha256')==digest:
                shutil.copy2(source/detail,destination/detail)
            for masks in source.glob(f"sam_{f['frame']}_{digest[:16]}_*"):
                if masks.is_dir():shutil.copytree(masks,destination/masks.name,dirs_exist_ok=True)
    return copied


def worker(p,job):
    pid=p['id'];d=pw.folder(pid);auto=d/'automation';previous=None;issues=[];records=[]
    auto.mkdir(parents=True,exist_ok=True)
    log_lock=threading.Lock();started=time.monotonic()
    def progress(**kw):
        with log_lock:
            event=dict(at=time.time(),elapsedSeconds=round(time.monotonic()-started,2),**kw)
            with (auto/'events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
            job.update(kw,elapsedSeconds=event['elapsedSeconds']);pw.write(auto/'job.json',job)
    try:
        pw.freeze_check()
        reused=reuse_source_cache(p)
        progress(reusedFrames=reused,message=f'开始分析；复用 {reused} 帧同视频同版本机器识别缓存')
        # Finish detections across the selected segment before assigning identities.
        # Otherwise later neighboring observations would be absent on the first run.
        import pixel_detail
        model=os.environ.get('PIXEL_VISION_MODEL',MODEL)
        def detect_frame(f):
            frame_started=time.monotonic()
            path=d/'frames'/f"{f['frame']:04}.png";digest=pw.sha(path)
            coarse=auto/f"vision_{f['frame']}_{digest[:16]}.json"
            model=os.environ.get('PIXEL_VISION_MODEL',MODEL)
            cached=pw.read(coarse) if coarse.exists() else None
            if not (cached and cached.get('model')==model and cached.get('contract')==CONTRACT and cached.get('detectorVersion')==DETECTOR_VERSION):
                progress(stage='detection',message=f'正在识别源帧 {f["frame"]} 的角色部件与关节')
                value=retry_detection(lambda:infer(path,p['source']['width'],p['source']['height']),progress,f['frame'])
                cached=dict(contract=CONTRACT,detectorVersion=DETECTOR_VERSION,model=model,sourceSha256=digest,result=value)
                pw.write(coarse,cached)
            detailcache=auto/f"detail_{f['frame']}_v{pixel_detail.VERSION}.json"
            if not (detailcache.exists() and pw.read(detailcache).get('sourceSha256')==digest):
                progress(stage='detail',message=f'正在核对源帧 {f["frame"]} 的手脚与裤衩边界')
                value=retry_detection(lambda:pixel_detail.infer(path,cached['result']),progress,f['frame'])
                pw.write(detailcache,dict(sourceSha256=digest,result=value))
            progress(event='frame_detected',frame=f['frame'],frameSeconds=round(time.monotonic()-frame_started,2))
        from concurrent.futures import ThreadPoolExecutor,as_completed
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(detect_frame,f) for f in p['frames']]
            failures=[]
            for done,future in enumerate(as_completed(futures),1):
                try:future.result()
                except Exception as exc:failures.append(exc)
                progress(stage='detection',completed=done,message=f'识别阶段已结束 {done}/{len(p["frames"])} 帧；失败 {len(failures)} 帧')
            if failures:raise failures[0]
        for i,f in enumerate(p['frames']):
            path=d/'frames'/f"{f['frame']:04}.png"
            cache=auto/f"vision_{f['frame']}_{pw.sha(path)[:16]}.json"
            model=os.environ.get('PIXEL_VISION_MODEL',MODEL)
            cached=pw.read(cache) if cache.exists() else None
            if cached and cached.get('model')==model and cached.get('contract')==CONTRACT and cached.get('detectorVersion')==DETECTOR_VERSION:
                v=cached['result'];validate(v,p['source']['width'],p['source']['height'])
            else:
                v=retry_detection(lambda:infer(path,p['source']['width'],p['source']['height']),progress,f['frame'])
                pw.write(cache,dict(contract=CONTRACT,detectorVersion=DETECTOR_VERSION,model=model,sourceSha256=pw.sha(path),result=v))
            import pixel_detail
            detailcache=auto/f"detail_{f['frame']}_v{pixel_detail.VERSION}.json"
            if detailcache.exists() and pw.read(detailcache).get('sourceSha256')==pw.sha(path):v=pw.read(detailcache)['result']
            else:
                initial=v
                v=retry_detection(lambda:pixel_detail.infer(path,initial),progress,f['frame'])
                pw.write(detailcache,dict(sourceSha256=pw.sha(path),result=v))
            neighbors=[]
            for other in p['frames'][max(0,i-3):min(len(p['frames']),i+4)]:
                if other['frame']==f['frame']:continue
                cached_neighbor=auto/f"detail_{other['frame']}_v{pixel_detail.VERSION}.json"
                if cached_neighbor.exists():neighbors.append(pw.read(cached_neighbor)['result'])
            v,identity_repairs=stabilize_identity(v,neighbors)
            f.update(points=v['points'],joints=v['joints'],poseReviewed=False)
            rgb=np.array(Image.open(path).convert('RGB'))
            progress(stage='segmentation',message=f"正在细化第 {i+1}/{len(p['frames'])} 帧原像素部件边界")
            import pixel_segmentation as segmentation
            cache_key=hashlib.sha256(json.dumps({'polygons':v['polygons'],'anchors':v['points']},sort_keys=True).encode()).hexdigest()[:16]
            maskdir=auto/f"sam_{f['frame']}_{pw.sha(path)[:16]}_{cache_key}_v{segmentation.VERSION}"
            if (maskdir/'report.json').exists():
                refined={n:np.array(Image.open(maskdir/(n+'.png'))) for n in pw.PARTS}
                segmentation_report=pw.read(maskdir/'report.json')
            else:
                refined,segmentation_report=segmentation.refine(rgb,v['polygons'],v['points'])
                maskdir.mkdir(parents=True,exist_ok=True)
                for n,m in refined.items():Image.fromarray(m).save(maskdir/(n+'.png'))
                pw.write(maskdir/'report.json',segmentation_report)
            masks,coverage=segment(rgb,v['polygons'],refined,v.get('hiddenParts',[]))
            for n,r in segmentation_report.items():
                if n not in v.get('hiddenParts',[]) and r['modelIoU']<.75:issues.append(dict(frame=f['frame'],code='segmentation_uncertain',part=n,detail='分割模型可信度不足，需重新定位部件'))
            # Sequence geometry is checked again after constrained temporal fitting.
            if coverage['ambiguousBoundaryPixels']>max(20,coverage['foregroundPixels']*.001):
                issues.append(dict(frame=f['frame'],code='ambiguous_boundary',part='all',detail=f"{coverage['ambiguousBoundaryPixels']} 个边缘像素的部件归属不明确"))
            if coverage['coverage']<.995:
                issues.append(dict(frame=f['frame'],code='coverage_gap',part='all',detail=f"原像素覆盖率 {coverage['coverage']:.2%}，存在缺口"))
            for note in v['uncertainties']:
                issues.append(dict(frame=f['frame'],code='vision_uncertain',part='unknown',detail=str(note)[:500]))
            for n in pw.PARTS:
                f['parts'][n]=dict(polygon=None,mask=pw.save_mask(d,n,f['frame'],masks[n]),reviewed=False,visible=n not in v.get('hiddenParts',[]))
            records.append(dict(frame=f['frame'],sourceSha256=pw.sha(path),identityRepairs=identity_repairs,segmentation=segmentation_report,**coverage))
            previous=copy.deepcopy(f)
            progress(completed=i+1,message=f"已识别 {i+1}/{len(p['frames'])} 帧，发现 {len(issues)} 项待检查问题")
        import pixel_pose
        sequence_masks=[{n:np.array(Image.open(d/f['parts'][n]['mask']))[:,:,3] for n in pw.PARTS} for f in p['frames']]
        progress(stage='pose',message='正在整段拟合骨骼与 IK')
        pose_issues,pose_evidence=pixel_pose.fit(p['frames'],sequence_masks)
        issues.extend(pose_issues)
        previous=None
        for f in p['frames']:
            masks={n:np.array(Image.open(d/f['parts'][n]['mask']))[:,:,3] for n in pw.PARTS}
            issues.extend(geometry(f,masks,previous));previous=f
            for q in f['joints'].values(): pw.xy(q,p['source']['width'],p['source']['height'])
        with pw.LOCK:
            if pw.load(pid)['revision']!=p['revision']:
                raise ValueError('识别期间工程已修改；保留识别缓存，不覆盖当前编辑')
            report=dict(contract=CONTRACT,model=model,sourceIdentity=p['source']['identity'],
                inputFingerprint=fingerprint(p),issues=issues,frames=records,
                jointMethod='segmented-source-support, fixed-bend sequence fit; occluded joints inferred',poseEvidence=pose_evidence,
                semanticValidation='candidate_requires_visual_acceptance',accepted=False,
                segmentationMethod='SAM2.1 tiny + semantic consensus seeds + source-edge watershed',
                segmentationVersion=segmentation.VERSION,detailDetectorVersion=pixel_detail.VERSION)
            p['automation']=report
            p=pw.save_generated(p)
            pw.write(auto/'report.json',report)
            if not any(x['code'] in {'bend_flip','degenerate_chain','empty_part'} for x in issues):
                try:
                    progress(stage='build',message='正在生成同步附件、IK 与动画预览')
                    p=pw.build(pid)
                except ValueError as e:
                    issues.append(dict(frame=p['frames'][0]['frame'],code='runtime_rejected',part='all',detail=str(e)[-500:]))
                    p['automation']['issues']=issues
                    pw.write(d/'project.json',p);pw.write(auto/'report.json',p['automation'])
        import pixel_quality
        progress(stage='quality',message='正在生成逐帧对照和像素检查')
        quality=pixel_quality.audit(p)
        with pw.LOCK:
            current=pw.load(pid)
            if current['revision']==p['revision']:
                current['automation']['qualityReview']=quality['url'];pw.write(d/'project.json',current)
        progress(state='needs_review',resultRevision=p['revision'],issues=len(issues),message='自动识别完成；请查看原帧、拆件和骨骼对照。未自动验收。')
    except Exception as e:
        progress(state='failed',message=str(e)[:700])
    finally:
        ACTIVE.discard(pid)

def candidate(p):
    a=p.get('automation')
    return bool(a and a.get('contract')==CONTRACT and a.get('inputFingerprint')==fingerprint(p))

def accept(payload):
    p=pw.load(payload['id'])
    if p['revision']!=payload['revision'] or not candidate(p): raise ValueError('自动候选已过期，请重新生成')
    if p['builtRevision']!=p['revision']: raise ValueError('请先生成并查看当前动画')
    audit=(p.get('artifact') or {}).get('audit',{})
    if audit.get('ok') is not True:raise ValueError('运行时检查未通过，不能登记验收')
    issues=p['automation']['issues']
    hard={'runtime_rejected','degenerate_chain','empty_part','invalid_fit','bend_flip'}
    if any(i['code'] in hard for i in issues):raise ValueError('存在结构错误，不能登记验收')
    if issues and payload.get('reviewedDiagnostics') is not True:
        raise ValueError('存在识别诊断；请在视觉核对后明确确认已查看诊断')
    from datetime import datetime, timezone
    p['automation']['acceptance']=dict(type='human_visual_review',at=datetime.now(timezone.utc).isoformat(),
        revision=p['revision'],inputFingerprint=fingerprint(p),diagnosticCount=len(issues),
        reviewedDiagnostics=payload.get('reviewedDiagnostics') is True,
        note=str(payload.get('note','工作台整段视觉验收'))[:1000])
    p['automation']['semanticValidation']='human_accepted'
    p['automation']['accepted']=True
    p['automation']['acceptedRevision']=p['revision']
    pw.write(pw.folder(p['id'])/'project.json',p)
    pw.write(pw.folder(p['id'])/'acceptances'/f"r{p['revision']}.json",p['automation']['acceptance'])
    return p
