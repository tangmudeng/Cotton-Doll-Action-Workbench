"""Retarget accepted video-reference trajectories to a fixed PSD rig.
No source-video textures, new pixel generation or per-frame skin swaps.
"""
from pathlib import Path
import json,math,shutil,hashlib
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RIG=HERE/'rig';OUT=HERE/'video_fit'
OUT.mkdir(exist_ok=True);(OUT/'parts').mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text('utf-8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
raw=read(RIG/'skin.json');samples=read(HERE/'motion_reference.json');frames=[{b['name']:b for b in f['bones']} for f in samples];bones={b['name']:b for b in raw['bones']};fps=24;N=len(frames)
for p in (RIG/'parts').glob('*.png'):shutil.copy2(p,OUT/'parts'/p.name)
for n in ['skin.atlas','skin_0.png','atlas_report.json','source_manifest.json']:shutil.copy2(RIG/n,OUT/n)
def position(b):return np.array([b.get('x',0.),b.get('y',0.)],dtype=float)
def timeline(values):
 out=[dict(time=round(i/fps,6),**v) for i,v in enumerate(values)];out.append(dict(time=round(N/fps,6),**values[0]));return out
# Periodic local smoothing removes quantization from stepped reference tracks.
def smooth(x):return (.25*np.roll(x,1,axis=0)+.5*x+.25*np.roll(x,-1,axis=0))
anim={'bones':{}};diagnostics={}
# Scale only the observed body bounce, not absolute source positions.
body_scale=abs(bones['head']['y']-bones['pelvis']['y'])/abs(frames[0]['torso']['y']-frames[0]['pelvis']['y'])
bounce=smooth(np.array([f['pelvis']['y'] for f in frames]));bounce=(bounce-bounce.mean())*body_scale
for n in ['torso','pelvis','head']:
 anim['bones'][n]={'translate':timeline([dict(x=0,y=float(y)) for y in bounce])}
for name in ['arm_near','arm_far','leg_near','leg_far']:
 setup_root=position(bones[name+'_upper']);setup_end=position(bones[name+'_target']);setup_vec=setup_end-setup_root
 l1=bones[name+'_upper']['length'];l2=bones[name+'_lower']['length'];total=l1+l2
 src=np.array([position(f[name+'_target'])-position(f[name+'_upper']) for f in frames]);src=smooth(src)
 angles=np.unwrap(np.arctan2(src[:,1],src[:,0]));angle_offset=np.arctan2(setup_vec[1],setup_vec[0])-np.mean(angles)
 distances=np.linalg.norm(src,axis=1);nominal=np.linalg.norm(setup_vec)
 # Transfer relative reach changes while retaining fixed master bone lengths.
 scale=min(nominal/float(np.median(distances)),total*.985/float(distances.max()));requested=distances*scale
 # Projected reference shortening includes depth motion, not just elbow/knee flexion.
 # Retain its phase but bound flexion for the broad fixed PSD silhouettes.
 extension_floor=.96 if name.startswith('arm') else .93
 reach_phase=(distances-distances.min())/max(1e-9,float(np.ptp(distances)))
 requested=total*(extension_floor+(.985-extension_floor)*reach_phase)
 reach=np.minimum(requested,total*.985);lower=abs(l1-l2)+1.;reach=np.maximum(reach,lower)
 theta=angles+angle_offset;vectors=np.column_stack([np.cos(theta),np.sin(theta)])*reach[:,None]
 roots=np.tile(setup_root,(N,1));roots[:,1]+=bounce;ends=roots+vectors
 keys=[dict(x=float(q[0]-setup_end[0]),y=float(q[1]-setup_end[1])) for q in ends]
 anim['bones'][name+'_upper']={'translate':timeline([dict(x=0,y=float(y)) for y in bounce])}
 anim['bones'][name+'_target']={'translate':timeline(keys)}
 diagnostics[name]={'sourceAngleRangeDegrees':np.degrees([angles.min(),angles.max()]).tolist(),'angleOffsetDegrees':float(np.degrees(angle_offset)),'initialRelativeReachScale':float(scale),'extensionFractionRange':[extension_floor,.985],'clampedFrames':[int(i+63) for i in np.where(requested>total*.985+1e-8)[0]],'boneLengths':[l1,l2],'sourceVectors':src.tolist(),'targetEndpoints':ends.tolist(),'mapping':'full source angular swing aligned to PSD mean; source reach phase remapped to bounded flexion, not exact source reach'}
raw['animations']['video_walk_fit']=anim;raw['skeleton']['images']='./parts/'
write(OUT/'skin.json',raw)
source=ROOT/'spine_samples/video_motion_study_20261119/pixel_sync_20261120/skin.json'
write(OUT/'provenance.json',{'referenceSkeleton':str(source.relative_to(ROOT)),'referenceSHA256':hashlib.sha256(source.read_bytes()).hexdigest(),'sourceFrames':[f['frame'] for f in samples],'fps':fps,'animation':'video_walk_fit','motionMethod':'retarget previously accepted rig trajectories; not new video AI inference','periodicFilter':[.25,.5,.25],'bodyBounceScale':body_scale,'chains':diagnostics,'texturesReused':True,'attachmentTimelineAdded':False,'humanAccepted':False,'contactSegmentsValidated':False})
print(json.dumps({'frames':N,'textures':len(list((OUT/'parts').glob('*.png'))),'animation':'video_walk_fit','clampedFrames':{k:len(v['clampedFrames']) for k,v in diagnostics.items()}}))
