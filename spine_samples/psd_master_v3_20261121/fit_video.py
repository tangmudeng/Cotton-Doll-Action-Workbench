"""Direction-preserving Cartesian motion transfer, without mean-angle recentering."""
from pathlib import Path
import json,shutil,hashlib
import numpy as np
from scipy.interpolate import CubicSpline
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RIG=HERE/'rig';OUT=HERE/'video_fit';OUT.mkdir(exist_ok=True);(OUT/'parts').mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text('utf8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
raw=read(RIG/'skin.json');samples=read(HERE/'motion_reference.json');frames=[{b['name']:b for b in f['bones']} for f in samples];bones={b['name']:b for b in raw['bones']};N=len(frames);fps=24
for p in (RIG/'parts').glob('*.png'):shutil.copy2(p,OUT/'parts'/p.name)
for n in ['skin.atlas','skin_0.png','atlas_report.json','source_manifest.json']:shutil.copy2(RIG/n,OUT/n)
def pos(b):return np.array([b.get('x',0),b.get('y',0)],float)
def smooth(v):return .15*np.roll(v,1,axis=0)+.7*v+.15*np.roll(v,-1,axis=0)
def keys(v):
 # Sample a periodic cubic at 96 Hz for smooth, closed position/velocity trajectories.
 a=np.asarray(v);curve=CubicSpline(np.arange(N+1),np.concatenate([a,a[:1]]),bc_type='periodic');out=[]
 for t,q in zip(np.arange(N*4+1)/4,curve(np.arange(N*4+1)/4)):
  out.append({'time':round(float(t/fps),6),'x':float(q[0]),'y':float(q[1])})
 return out
body_scale=abs(bones['head']['y']-bones['pelvis']['y'])/abs(frames[0]['torso']['y']-frames[0]['pelvis']['y'])
bounce=smooth(np.array([f['pelvis']['y'] for f in frames]));bounce=(bounce-bounce.mean())*body_scale
anim={'bones':{},'drawOrder':[{'time':0,'offsets':[{'slot':'leg_near','offset':1}]}]};diag={}
# Manually reviewed silhouette landmarks, not hidden-anatomy ground truth.
landmarks=[[63,450,410],[67,440,415],[71,433,415],[75,440,414],[79,463,408],[82,463,407],[85,453,410],[86,450,410]]
lm=np.array(landmarks,float);crotch=CubicSpline(lm[:,0],lm[:,1:],bc_type='periodic')(np.arange(63,86));hip_x=(crotch[:,0]-450)*body_scale
for name in ['torso','pelvis','head']:anim['bones'][name]={'translate':keys(np.column_stack([hip_x if name=='pelvis' else np.zeros(N),bounce]))}
for name in ['arm_near','arm_far','leg_near','leg_far']:
 root=pos(bones[name+'_upper']);end=pos(bones[name+'_target']);l1=bones[name+'_upper']['length'];l2=bones[name+'_lower']['length']
 source=np.array([pos(f[name+'_target'])-pos(f[name+'_upper']) for f in frames]);vectors=smooth(source)
 # One scalar for x/y preserves the observed directions and relative extension.
 scale=(l1+l2)*.98/np.linalg.norm(vectors,axis=1).max();vectors*=scale
 roots=np.tile(root,(N,1));roots[:,1]+=bounce;endpoints=roots+vectors
 if name.startswith('leg'):roots[:,0]+=hip_x*(.55 if name=='leg_near' else .3)
 anim['bones'][name+'_upper']={'translate':keys(roots-root)}
 # Depth foreshortening is represented explicitly by uniform projected chain
 # scale, rather than changing the target path or forcing a sharp elbow bend.
 actual_vectors=endpoints-roots
 projection=np.linalg.norm(actual_vectors,axis=1)/((l1+l2)*.95)
 anim['bones'][name+'_upper']['scale']=keys(np.column_stack([projection,projection]))
 anim['bones'][name+'_target']={'translate':keys(endpoints-end)}
 if name.startswith('leg'):
  angle=np.unwrap(np.arctan2(actual_vectors[:,1],actual_vectors[:,0]));rest=np.arctan2((end-root)[1],(end-root)[0]);rot=np.degrees(angle-rest)*.5
  anim['bones'][name+'_foot']={'rotate':[{'time':k['time'],'value':k['x']} for k in keys(np.column_stack([rot,np.zeros(N)]))]}
 diag[name]={'scale':float(scale),'angleOffsetDegrees':0,'extensionRange':(np.linalg.norm(vectors,axis=1)/(l1+l2)).tolist(),'projectionScale':projection.tolist(),'referenceVectors':source.tolist(),'mappedVectors':vectors.tolist(),'root':root.tolist(),'endpointKeys':endpoints.tolist(),'noPerFrameReachClamp':True}
raw['animations']={'setup_hold':raw['animations']['setup_hold'],'video_walk_fit':anim};raw['skeleton']['images']='./parts/';write(OUT/'skin.json',raw)
write(OUT/'provenance.json',{'sourcePSD':read(RIG/'source_manifest.json')['sha256'],'sourceMotion':'accepted pixel_sync_20261120 reference_cycle, checked against original video frames','frames':list(range(63,86)),'fps':24,'bodyBounceScale':body_scale,'motionMethod':'Cartesian endpoint trajectories with explicit projected chain scaling and manual hip silhouette keys','hipSilhouetteLandmarks':landmarks,'hipLandmarkUncertaintySourcePixels':4,'periodicFilter':[.15,.7,.15],'chains':diag,'humanAccepted':False,'noVideoTextures':True,'noRepaint':True})
print('Transferred direction and shortening for all four limbs; no static-pose recentering.')
