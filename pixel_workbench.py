"""Source-pixel projects. Accepted sample is read-only; all work is revisioned."""
from pathlib import Path
import base64, copy, hashlib, json, math, os, re, shutil, subprocess, threading, uuid, zipfile
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
STORE = ROOT / 'studio_v3/pixel_projects'
STUDY = ROOT / 'spine_samples/video_motion_study_20261119'
BASE = STUDY / 'pixel_sync_20261120'
PARTS = ['arm_far', 'leg_far', 'leg_near', 'torso', 'shorts', 'arm_near', 'head']
CHAINS = {'arm_far': ['shoulder_far', 'hand_far'], 'leg_far': ['hip_far', 'foot_far'],
          'arm_near': ['shoulder_near', 'hand_near'], 'leg_near': ['hip_near', 'foot_near']}
POINTS = ['neck', 'pelvis', 'shoulder_near', 'shoulder_far', 'hip_near', 'hip_far',
          'hand_near', 'hand_far', 'foot_near', 'foot_far']
LOCK = threading.RLock()

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def folder(pid):
    if not isinstance(pid, str) or not re.fullmatch(r'px_[a-f0-9]{12}', pid):
        raise ValueError('无效工程 ID')
    return STORE / pid

def url(p):
    return '/' + p.relative_to(ROOT).as_posix()

def load(pid):
    return read(folder(pid) / 'project.json')

def listing():
    return [dict(id=p['id'], name=p['name'], revision=p['revision']) for f in sorted(STORE.glob('*/project.json')) for p in [read(f)]]

def fresh(name, source):
    pid = 'px_' + uuid.uuid4().hex[:12]
    d = folder(pid)
    (d / 'frames').mkdir(parents=True)
    return d, dict(schema='walulu-pixel-project/1', id=pid, name=name, source=source,
                   revision=1, baseline=False, frames=[], order=PARTS[:], builtRevision=None, artifact=None)

def freeze_check():
    expected = read(ROOT / 'docs/ACCEPTED_BASELINE_SHA256.json')
    for name, digest in expected.items():
        if sha(BASE / name) != digest:
            raise ValueError('已验收基准哈希不符：' + name)
    return len(expected)

def clone():
    freeze_check()
    annotations = read(STUDY / 'motion_annotations.json')
    d, p = fresh('右前行走 · 已验收样板副本', dict(width=864, height=480, fps=24,
        name='右前行走.mp4', identity='accepted:pixel_sync_20261120', start=63, end=85))
    p['baseline'] = True
    (d / 'seed_parts').mkdir()
    manifest = read(BASE / 'pixel_manifest.json')
    for sample in annotations['samples']:
        f = sample['frame']
        shutil.copy2(BASE / 'reference_frames' / f'{f:04}.png', d / 'frames' / f'{f:04}.png')
        parts = {}
        for item in manifest:
            if item['sourceFrame'] == f:
                name = item['part']
                shutil.copy2(BASE / item['file'], d / 'seed_parts' / Path(item['file']).name)
                parts[name] = dict(polygon=None, reviewed=True)
        p['frames'].append(dict(frame=f, points=sample['points'],
            joints={k: v['joint'] for k, v in sample['chains'].items()}, parts=parts, poseReviewed=True))
    write(d / 'seed_manifest.json', manifest)
    write(d / 'seed_project.json', p)
    write(d / 'project.json', p)
    return p

def import_video(payload):
    if payload.get('projectId'):
        source_project=load(payload['projectId'])
        blob=(folder(source_project['id'])/'source.mp4').read_bytes()
        payload={**payload,'name':source_project['source'].get('name',source_project['name'])}
    elif payload.get('videoId'):
        import pixel_video
        blob = pixel_video.resolve(payload['videoId']).read_bytes()
    else:
        blob = base64.b64decode(payload['data'], validate=True)
    if not blob or len(blob) > 96_000_000:
        raise ValueError('视频限 96 MB')
    raw_start,raw_end=payload.get('start',0),payload.get('end',22)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or int(v)!=v for v in (raw_start,raw_end)):
        raise ValueError('起止源帧必须为整数')
    start,end=int(raw_start),int(raw_end)
    if start < 0 or not start <= end < start + 120:
        raise ValueError('每次请选择 1–120 个连续源帧')
    d, p = fresh(str(payload.get('name', '新视频'))[:160], {})
    video = d / 'source.mp4'
    video.write_bytes(blob)
    cap = cv2.VideoCapture(str(video))
    try:
        w, h = int(cap.get(3)), int(cap.get(4))
        fps, count = cap.get(5), int(cap.get(7))
        if not cap.isOpened() or not 1 <= fps <= 240 or w*h > 4096*2160 or min(w,h) < 16 or end >= count:
            raise ValueError('视频尺寸、帧率或帧区间无效')
        p['source'] = dict(width=w, height=h, fps=fps, count=count, start=start, end=end,
                           name=p['name'], identity=sha(video))
        if payload.get('videoId'):
            analysis=read(pixel_video.resolve(payload['videoId']).parent/'analysis.json')
            p['videoAnalysis']=dict(version=analysis['version'],videoId=analysis['videoId'],selectedStart=start,selectedEnd=end,candidates=analysis['candidates'])
        # Seek once, then decode consecutively. Every output retains the decoded RGB.
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        for f in range(start, end+1):
            ok, im = cap.read()
            if not ok:
                raise ValueError('源视频解码失败，帧 ' + str(f))
            Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)).save(d / 'frames' / f'{f:04}.png')
            p['frames'].append(dict(frame=f, points={}, joints={}, poseReviewed=False,
                parts={n: dict(polygon=None, reviewed=False) for n in PARTS}))
        write(d / 'project.json', p)
        return p
    finally:
        cap.release()

def xy(value, w, h):
    if not isinstance(value, list) or len(value) != 2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):
        raise ValueError('坐标必须是有限数值')
    if not 0 <= value[0] <= w or not 0 <= value[1] <= h:
        raise ValueError('坐标超出源图')
    return value

def contour_polygon(mask):
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours: raise ValueError('轮廓没有有效像素')
    contour=max(contours,key=cv2.contourArea)
    epsilon=.6
    while True:
        poly=cv2.approxPolyDP(contour,epsilon,True).reshape(-1,2)
        if len(poly)<=256: break
        epsilon*=1.5
    if len(poly)<3: raise ValueError('轮廓退化，需重新描边')
    return poly

def save(payload):
    old = load(payload['id'])
    if payload['revision'] != old['revision']:
        raise ValueError('工程已被另一页面更新，请重新载入后编辑')
    candidate = payload['project']
    frames = candidate['frames']
    if len(frames) != len(old['frames']) or sorted(candidate['order']) != sorted(PARTS):
        raise ValueError('帧数或图层列表无效')
    w,h = old['source']['width'], old['source']['height']
    clean = []
    for f, prev in zip(frames, old['frames']):
        if f['frame'] != prev['frame']:
            raise ValueError('源帧不能被替换')
        points = {k: xy(v,w,h) for k,v in f['points'].items() if k in POINTS}
        joints = {k: xy(v,w,h) for k,v in f['joints'].items() if k in CHAINS}
        parts = {}
        for n in PARTS:
            v = f['parts'][n]; poly = v.get('polygon')
            mask=v.get('mask')
            if mask is not None and (not isinstance(mask,str) or not re.fullmatch(r'masks/[a-f0-9]{12}_'+n+'_'+str(f['frame'])+r'\.png',mask) or not (folder(old['id'])/mask).is_file()):
                raise ValueError('遮罩只能来自本工程的追踪结果')
            if poly is not None:
                if not isinstance(poly,list) or not 3 <= len(poly) <= 256:
                    raise ValueError('轮廓需要 3–256 个顶点')
                poly = [xy(q,w,h) for q in poly]
            elif not old['baseline'] and not mask:
                v = {**v, 'reviewed': False}
            parts[n] = dict(polygon=poly, reviewed=v.get('reviewed') is True)
            if v.get('visible') is False:parts[n]['visible']=False
            if mask: parts[n]['mask']=mask
        clean.append(dict(frame=f['frame'], points=points, joints=joints, parts=parts, poseReviewed=f.get('poseReviewed') is True))
    write(folder(old['id'])/'revisions'/f"r{old['revision']}.json",old)
    old.update(frames=clean, order=candidate['order'], revision=old['revision']+1, builtRevision=None, artifact=None)
    # Manual edits invalidate automatic approval; prior evidence remains in revisions.
    old.pop('automation', None)
    write(folder(old['id']) / 'project.json', old)
    return old

def seed_annotation(payload):
    p=load(payload['id']);d=folder(p['id'])
    if p['revision']!=payload['revision']: raise ValueError('请重新载入最新工程')
    annotations=read(STUDY/'motion_annotations.json')
    original=Path(annotations['source']['source'])
    if not original.is_file() or p['source']['identity']!=sha(original):
        raise ValueError('仅支持内容哈希完全相同的已验收参考视频；其他视频请手工标注')
    first=p['frames'][0];sample=next((s for s in annotations['samples'] if s['frame']==first['frame']),None)
    if sample is None: raise ValueError('请将起始帧设在已验收的 63–85 帧内，再追踪后续新帧')
    freeze_check()
    first['points']=copy.deepcopy(sample['points']);first['joints']={n:c['joint'] for n,c in sample['chains'].items()}
    first['poseReviewed']=False
    for item in read(BASE/'pixel_manifest.json'):
        if item['sourceFrame']!=first['frame']: continue
        alpha=np.array(Image.open(BASE/item['file']))[:,:,3]
        full=np.zeros((p['source']['height'],p['source']['width']),np.uint8)
        x0,y0,x1,y1=item['crop'];full[y0:y1,x0:x1]=alpha
        first['parts'][item['part']]=dict(polygon=None,mask=save_mask(d,item['part'],first['frame'],full),reviewed=False)
    return save_generated(p)

def save_mask(d,part,frame,alpha):
    rel=f'masks/{uuid.uuid4().hex[:12]}_{part}_{frame}.png'
    (d/'masks').mkdir(exist_ok=True)
    rgb=np.full((*alpha.shape,3),255,np.uint8)
    Image.fromarray(np.dstack([rgb,alpha])).save(d/rel)
    return rel

def save_generated(p):
    d=folder(p['id']);old=load(p['id'])
    write(d/'revisions'/f"r{old['revision']}.json",old)
    if p.get('automation'):
        import pixel_automation
        if not pixel_automation.candidate(p): p.pop('automation', None)
    p.update(revision=p['revision']+1,builtRevision=None,artifact=None)
    write(d/'project.json',p)
    return p

def track(payload):
    """Optical-flow proposals only. Never mark them visually reviewed."""
    p=load(payload['id']);d=folder(p['id'])
    if p['revision']!=payload['revision']: raise ValueError('请重新载入最新工程')
    start=int(payload.get('index',0))
    if not 0<=start<len(p['frames'])-1: raise ValueError('请选择有后续帧的起始姿势')
    seed=p['frames'][start]
    if set(seed['points'])!=set(POINTS) or set(seed['joints'])!=set(CHAINS): raise ValueError('先完成起始帧的所有关节点')
    seeds={(m['sourceFrame'],m['part']):m for m in read(d/'seed_manifest.json')} if p['baseline'] else {}
    masks={}
    w,h=p['source']['width'],p['source']['height']
    for n in PARTS:
        mask=np.zeros((h,w),np.uint8);poly=seed['parts'][n]['polygon']
        if poly:
            cv2.fillPoly(mask,[np.array(poly,np.int32)],255)
        elif seed['parts'][n].get('mask'):
            mask=np.array(Image.open(d/seed['parts'][n]['mask']))[:,:,3]
        elif p['baseline']:
            item=seeds[(seed['frame'],n)];x0,y0,x1,y1=item['crop']
            mask[y0:y1,x0:x1]=np.array(Image.open(d/'seed_parts'/Path(item['file']).name))[:,:,3]
        else: raise ValueError('先完成起始帧的七个轮廓')
        masks[n]=mask
    previous=np.array(Image.open(d/'frames'/f"{seed['frame']:04}.png").convert('L'))
    previous_pose=copy.deepcopy(seed)
    xx,yy=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32))
    for f in p['frames'][start+1:]:
        image=Image.open(d/'frames'/f"{f['frame']:04}.png").convert('RGB')
        current=np.array(image.convert('L'))
        forward=cv2.calcOpticalFlowFarneback(previous,current,None,.5,4,25,5,7,1.5,0)
        backward=cv2.calcOpticalFlowFarneback(current,previous,None,.5,4,25,5,7,1.5,0)
        for field in ['points','joints']:
            f[field]={}
            for k,q in previous_pose[field].items():
                x,y=map(int,q);patch=forward[max(0,y-3):min(h,y+4),max(0,x-3):min(w,x+4)]
                delta=np.median(patch.reshape(-1,2),axis=0)
                f[field][k]=[float(np.clip(q[0]+delta[0],0,w-1)),float(np.clip(q[1]+delta[1],0,h-1))]
        for n in PARTS:
            masks[n]=cv2.remap(masks[n],xx+backward[:,:,0],yy+backward[:,:,1],cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT)
        if payload.get('uniformBackground') is True:
            rgb=np.array(image).astype(np.float32)
            corners=np.concatenate([rgb[:8,:8].reshape(-1,3),rgb[:8,-8:].reshape(-1,3),rgb[-8:,:8].reshape(-1,3),rgb[-8:,-8:].reshape(-1,3)])
            bg=np.median(corners,axis=0)
            if np.max(np.std(corners,axis=0))>12: raise ValueError('四角背景不均匀，请关闭均匀背景补全或手动描边')
            foreground=(np.max(np.abs(rgb-bg),axis=2)>18).astype(np.uint8)
            contours,_=cv2.findContours(foreground,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if not contours: raise ValueError('未识别到角色前景')
            sil=np.zeros((h,w),np.uint8);cv2.drawContours(sil,[max(contours,key=cv2.contourArea)],-1,255,-1)
            distances=np.stack([cv2.distanceTransform((masks[n]==0).astype(np.uint8),cv2.DIST_L2,3) for n in PARTS])
            owner=np.argmin(distances,axis=0)
            for index,n in enumerate(PARTS):
                region=cv2.dilate((owner==index).astype(np.uint8),np.ones((3,3),np.uint8))
                masks[n]=np.where((region>0)&(sil>0),255,0).astype(np.uint8)
        for n in PARTS:
            if not np.any(masks[n]): raise ValueError('追踪丢失：'+n)
            f['parts'][n]=dict(polygon=None,mask=save_mask(d,n,f['frame'],masks[n]),reviewed=False)
        f['poseReviewed']=False;previous=current;previous_pose=copy.deepcopy(f)
    return save_generated(p)

def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=180)
    if result.returncode:
        output=result.stderr or result.stdout
        errors=[line for line in output.splitlines() if line.startswith('Error:')]
        raise ValueError(errors[0] if errors else output[-1600:])

def build(pid):
    p = load(pid); d = folder(pid)
    import pixel_automation
    automatic = pixel_automation.candidate(p)
    for f in p['frames']:
        if (not f['poseReviewed'] and not automatic) or set(f['points']) != set(POINTS) or set(f['joints']) != set(CHAINS):
            raise ValueError(f"帧 {f['frame']} 尚未完成骨骼锚点审核")
        if not automatic and any(not x['reviewed'] for x in f['parts'].values()):
            raise ValueError(f"帧 {f['frame']} 尚未完成七个附件审核")
    out = d / ('build_' + str(p['revision']) + '_' + uuid.uuid4().hex[:6])
    (out / 'parts').mkdir(parents=True)
    seed = read(d / 'seed_project.json') if p['baseline'] else None
    same = seed and p['frames'] == seed['frames'] and p['order'] == seed['order']
    if same:
        freeze_check()
        for name in ['skin.json','skin.atlas','skin.png']:
            shutil.copy2(BASE/name, out/name)
        shutil.copytree(BASE/'parts', out/'parts', dirs_exist_ok=True)
        manifest = read(BASE/'pixel_manifest.json')
    else:
        manifest=[]; images=[]
        seeds = {(x['sourceFrame'],x['part']):x for x in read(d/'seed_manifest.json')} if seed else {}
        for f in p['frames']:
            src = np.array(Image.open(d/'frames'/f"{f['frame']:04}.png").convert('RGB'))
            for part in p['order']:
                if f['parts'][part].get('visible') is False:continue
                poly=f['parts'][part]['polygon']
                if poly is None and f['parts'][part].get('mask'):
                    alpha=np.array(Image.open(d/f['parts'][part]['mask']))[:,:,3]
                    rows,cols=np.where(alpha>0)
                    if not len(rows): raise ValueError('附件遮罩为空')
                    crop=[int(cols.min()),int(rows.min()),int(cols.max()+1),int(rows.max()+1)]
                    x0,y0,x1,y1=crop
                    rgba=np.dstack([src,alpha])[y0:y1,x0:x1]
                elif poly is None:
                    item=seeds[(f['frame'],part)]; crop=item['crop']
                    rgba=np.array(Image.open(d/'seed_parts'/Path(item['file']).name).convert('RGBA'))
                else:
                    alpha=np.zeros(src.shape[:2],np.uint8)
                    cv2.fillPoly(alpha,[np.array(poly,np.int32)],255)
                    rows,cols=np.where(alpha>0)
                    if len(rows)<4: raise ValueError('轮廓没有有效像素')
                    crop=[int(cols.min()),int(rows.min()),int(cols.max()+1),int(rows.max()+1)]
                    x0,y0,x1,y1=crop
                    rgba=np.dstack([src,alpha])[y0:y1,x0:x1]
                x0,y0,x1,y1=crop
                if not np.array_equal(rgba[:,:,:3],src[y0:y1,x0:x1]):
                    raise ValueError('附件 RGB 与来源帧不一致')
                key=f"{part}_{f['frame']}"; im=Image.fromarray(rgba)
                im.save(out/'parts'/f'{key}.png');images.append((key,im))
                manifest.append(dict(part=part,sourceFrame=f['frame'],crop=crop,file=f'parts/{key}.png',rgbExact=True,hiddenPixelsCompleted=False))
        import pixel_atlas
        pixel_atlas.pack(images,out)
    write(out/'project.json',p);write(out/'pixel_manifest.json',manifest)
    run(['node',str(ROOT/'studio_v3/pixel_pipeline.cjs'),str(out),'audit' if same else 'build'],ROOT)
    audit=read(out/'audit.json')
    if (out/'atlas_report.json').exists():audit['atlas']=read(out/'atlas_report.json')
    p.update(builtRevision=p['revision'],artifact=dict(base=url(out),audit=audit,acceptedCopy=bool(same)))
    write(d/'project.json',p)
    return p

def verify_artifact(p, built):
    """Do not package a different project's or stale input's animation."""
    import pixel_automation
    saved=read(built/'project.json')
    if (saved.get('id')!=p['id'] or saved.get('revision')!=p['revision']
            or pixel_automation.fingerprint(saved)!=pixel_automation.fingerprint(p)):
        raise ValueError('动画与当前工程来源或姿态不一致，请重新生成')


def export(pid, revision, review=False):
    p=load(pid)
    if p['revision'] != revision or p['builtRevision'] != revision or not p['artifact']:
        raise ValueError('请先保存并生成当前版本；禁止导出过期动画')
    if p.get('automation') and not review:
        import pixel_automation
        if not pixel_automation.candidate(p) or not p['automation'].get('accepted') or p['automation'].get('acceptedRevision') != revision:
            raise ValueError('自动识别候选须先完成整段视觉验收；技术核查不等于语义正确')
    if p['artifact'].get('audit',{}).get('ok') is not True:
        raise ValueError('运行时检查未通过，无法生成检查包')
    built=ROOT/p['artifact']['base'].lstrip('/')
    verify_artifact(p, built)
    # Spine imports append skeletons when the target already exists. Each export
    # gets a fresh directory so repeated clicks cannot accumulate duplicate rigs.
    kind='technical_review' if review else 'export'
    out=folder(pid)/f'{kind}_{revision}_{uuid.uuid4().hex[:8]}'
    out.mkdir()
    for f in built.iterdir():
        if f.is_file() and (f.name.startswith('skin') or f.name in {'project.json','pixel_manifest.json','audit.json','atlas_report.json'}):
            shutil.copy2(f,out/f.name)
    shutil.copytree(built/'parts',out/'parts')
    write(out/'project.json',p)
    if p.get('automation',{}).get('acceptance'):
        write(out/'ACCEPTANCE.json',p['automation']['acceptance'])
    spine=Path(os.environ.get('SPINE_CLI','E:/MyTools/Spine/Spine.com'))
    if not spine.is_file(): raise ValueError('未找到 Spine CLI，无法生成真实 .spine 工程')
    run([str(spine),'-u','4.2.43','-i',str(out/'skin.json'),'-o',str(out/'walk.spine'),'-r','skin'],out)
    roundtrip=out/'roundtrip';roundtrip.mkdir(exist_ok=True)
    run([str(spine),'-u','4.2.43','-i',str(out/'walk.spine'),'-o',str(roundtrip),'-e','json'],out)
    files=list(roundtrip.glob('*.json'))
    if not (out/'walk.spine').is_file() or len(files)!=1: raise ValueError('Spine 导入回导未完成')
    run(['node',str(ROOT/'studio_v3/pixel_pipeline.cjs'),str(out),'roundtrip',str(files[0])],ROOT)
    # Portable package includes all frames, project state and exact image inputs.
    shutil.copytree(folder(pid)/'frames',out/'frames',dirs_exist_ok=True)
    if (folder(pid)/'masks').exists(): shutil.copytree(folder(pid)/'masks',out/'masks',dirs_exist_ok=True)
    if review:
        write(out/'REVIEW_STATUS.json',dict(kind='technical_review',projectId=pid,revision=revision,requiresVisualReview=True,warning='此包用于 Spine 检查；成功导出不代表质量验收。'))
    quality=folder(pid)/f'quality_r{revision}'
    if quality.is_dir():shutil.copytree(quality,out/'quality')
    (out/'README.md').write_text(('待验收检查包：请核对整段动画、部件归属和关节；回到工作台登记验收。\n' if review else '当前版本正式导出。\n')+'动画：reference_cycle。Spine 中点击动画左侧圆点激活动画，再播放。\n源像素逐帧同步；不代表任意姿势连续蒙皮已验收。\nproject.json / pixel_manifest.json 记录来源及绑定输入。\n',encoding='utf8')
    hashes={f.relative_to(out).as_posix():sha(f) for f in out.rglob('*') if f.is_file() and f.suffix!='.zip' and f.name!='SHA256.json'}
    write(out/'SHA256.json',hashes)
    dest=out/'walk_spine.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob('*'):
            if f.is_file() and f!=dest: z.write(f,f.relative_to(out))
    result=dict(zipUrl=url(dest),spineUrl=url(out/'walk.spine'),audit=read(out/'roundtrip_audit.json'),revision=revision,kind=kind)
    p.setdefault('exports',{})[kind]=result
    write(folder(pid)/'project.json',p)
    return result

def dispatch(action, payload):
    with LOCK:
        if action in {'auto-start','auto-status','auto-accept'}:
            import pixel_automation as auto
            if action=='auto-start': return dict(job=auto.start(payload))
            if action=='auto-status': return dict(job=auto.status(payload['id']))
            return dict(project=auto.accept(payload))
        if action=='video-sources':
            import pixel_video
            return dict(sources=pixel_video.sources())
        if action=='analyze-video':
            import pixel_video
            return dict(analysis=pixel_video.analyze(payload))
        if action=='list': return dict(projects=listing())
        if action=='load': return dict(project=load(payload['id']))
        if action=='clone': return dict(project=clone())
        if action=='import': return dict(project=import_video(payload))
        if action=='save': return dict(project=save(payload))
        if action=='track': return dict(project=track(payload))
        if action=='seed': return dict(project=seed_annotation(payload))
        if action=='build':
            if load(payload['id'])['revision']!=payload['revision']: raise ValueError('工程版本已更新')
            return dict(project=build(payload['id']))
        if action in {'export','review-export'}: return export(payload['id'],payload['revision'],review=action=='review-export')
        raise ValueError('未知操作')
