"""Local motion/recurrence proposals, never a semantic or visual acceptance."""
import base64, hashlib, math, re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pixel_workbench as pw

VERSION=2

def store():
    return pw.ROOT/'studio_v3/pixel_video_analysis'

def resolve(video_id):
    if not isinstance(video_id,str) or not re.fullmatch(r'[a-f0-9]{64}',video_id):
        raise ValueError('视频分析 ID 无效')
    path=store()/video_id/'source.mp4'
    if not path.is_file() or pw.sha(path)!=video_id:raise ValueError('分析视频已丢失或改变，请重新分析')
    return path

def sources():
    result=[];seen=set()
    for item in pw.listing():
        p=pw.load(item['id']);path=pw.folder(p['id'])/'source.mp4'
        identity=p['source'].get('identity')
        if path.is_file() and identity not in seen:
            seen.add(identity);result.append(dict(id=p['id'],name=p['source'].get('name',p['name'])))
    return result

def proposals(descriptors,indices,fps,count):
    """Seek repeated motion across a whole window, not just similar endpoints."""
    x=np.asarray(descriptors,dtype=np.float32)
    stride=indices[1]-indices[0] if len(indices)>1 else 1
    adjacent=np.mean(np.abs(np.diff(x,axis=0)),axis=1)
    activity=float(np.quantile(adjacent,.75)) if len(adjacent) else 0
    options=[]
    minlag=max(3,round(fps*.3/stride));maxlag=min(120//stride,(len(x)-1)//2)
    if activity>.002:
        for lag in range(minlag,maxlag+1):
            errors=np.mean(np.abs(x[lag:]-x[:-lag]),axis=1)
            if len(errors)<lag:continue
            recurrence=np.convolve(errors,np.ones(lag)/lag,mode='valid')
            motion=np.convolve(adjacent,np.ones(lag)/lag,mode='valid')
            for start in np.argsort(recurrence)[:5]:
                movement=float(motion[start]);error=float(recurrence[start])
                if movement<max(.002,activity*.3):continue
                ratio=error/max(movement,.001)
                # The end is exclusive: don't duplicate the first pose at the seam.
                first=int(indices[start]);end=int(indices[start+lag])-1
                if end>=count or end-first+1>120:continue
                seam=float(np.mean(np.abs(x[start+lag-1]-x[start])))
                options.append(dict(start=first,end=end,periodFrames=end-first+1,
                    recurrenceError=error,motion=movement,recurrenceRatio=ratio,
                    seamRatio=seam/max(movement,.001),score=ratio+max(0,seam/max(movement,.001)-2)*.25))
    options.sort(key=lambda z:z['score'])
    chosen=[]
    for item in options:
        if item['recurrenceRatio']>2.5:continue
        if any(abs(item['start']-v['start'])<min(item['periodFrames'],v['periodFrames'])//2 and abs(item['periodFrames']-v['periodFrames'])<max(3,v['periodFrames']*.2) for v in chosen):continue
        item['kind']='cycle_candidate';item['confidence']='较强重复信号' if item['recurrenceRatio']<.8 else '弱重复信号，需核对'
        chosen.append(item)
        if len(chosen)==3:break
    if not chosen:
        peak=int(np.argmax(adjacent)) if len(adjacent) else 0
        length=min(count,120,max(1,round(fps*2)))
        start=max(0,min(count-length,int(indices[peak])-length//2))
        chosen=[dict(start=start,end=start+length-1,periodFrames=None,kind='motion_segment',confidence='未确认循环；仅建议动作片段')]
    return chosen,activity

def analyze(payload):
    if payload.get('projectId'):
        p=pw.load(payload['projectId']);path=pw.folder(p['id'])/'source.mp4'
        blob=path.read_bytes();name=p['source'].get('name',p['name'])
    else:
        blob=base64.b64decode(payload['data'],validate=True);name=str(payload.get('name','AI 视频'))[:160]
    if not blob or len(blob)>96_000_000:raise ValueError('视频限 96 MB')
    identity=hashlib.sha256(blob).hexdigest();d=store()/identity;d.mkdir(parents=True,exist_ok=True)
    path=d/'source.mp4';path.write_bytes(blob)
    cached=d/'analysis.json'
    if cached.exists() and pw.read(cached).get('version')==VERSION:
        return {**pw.read(cached),'name':name}
    cap=cv2.VideoCapture(str(path))
    try:
        w,h=int(cap.get(3)),int(cap.get(4));fps=float(cap.get(5));count=int(cap.get(7))
        if not cap.isOpened() or not math.isfinite(fps) or not 1<=fps<=240 or min(w,h)<16 or w*h>4096*2160 or count<2:
            raise ValueError('视频尺寸或帧率无效，至少需要两帧')
        if count/fps>60:raise ValueError('请先裁剪为 60 秒以内的单动作视频')
        stride=max(1,math.ceil(count/720));indices=[];features=[]
        for i in range(count):
            ok,im=cap.read()
            if not ok:raise ValueError('源视频解码失败：'+str(i))
            if i%stride:continue
            small=cv2.resize(im,(48,32),interpolation=cv2.INTER_AREA).astype(np.float32)/255
            # Lower body receives equal weight to the large head, preserving limb signal.
            features.append(np.concatenate([small.reshape(-1),small[16:].reshape(-1)]))
            indices.append(i)
        candidates,activity=proposals(features,indices,fps,count)
        for number,c in enumerate(candidates):
            positions=np.linspace(c['start'],c['end'],5).round().astype(int).tolist()
            images=[]
            for frame in positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,im=cap.read()
                if not ok:raise ValueError('关键姿势预览解码失败')
                image=cv2.resize(im,(240,round(h*240/w)))
                image=cv2.copyMakeBorder(image,0,28,0,0,cv2.BORDER_CONSTANT,value=(245,245,245))
                cv2.putText(image,f'frame {frame}',(8,image.shape[0]-8),cv2.FONT_HERSHEY_SIMPLEX,.5,(40,40,40),1)
                images.append(image)
            sheet=d/f'candidate_{number}.jpg';Image.fromarray(cv2.cvtColor(np.concatenate(images,axis=1),cv2.COLOR_BGR2RGB)).save(sheet,quality=90)
            c.update(keyframes=positions,previewUrl=pw.url(sheet))
        result=dict(version=VERSION,videoId=identity,name=name,width=w,height=h,fps=fps,count=count,
            videoUrl=pw.url(path),sampleStride=stride,activity=activity,candidates=candidates,
            warnings=['基于画面运动与重复性提出区间，不能确认角色解剖、遮挡或循环接缝质量。','请预览并确认起止帧；非循环动作不会被强制标成循环。'])
        pw.write(cached,result);return result
    finally:cap.release()
