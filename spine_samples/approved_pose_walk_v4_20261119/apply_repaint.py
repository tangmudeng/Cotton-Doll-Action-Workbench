from pathlib import Path
import json,cv2,numpy as np
from PIL import Image
r=Path.cwd();report={}
for n,file in [('shorts','shorts_repaint.png'),('arm_far','arm_far_repaint.png')]:
 a=np.array(Image.open(file).convert('RGB'));m=((a[:,:,0].astype(float)-a[:,:,2])>18).astype('uint8');cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);c=max(cs,key=cv2.contourArea);mask=np.zeros(m.shape,np.uint8);cv2.drawContours(mask,[c],-1,255,-1);x,y,w,h=cv2.boundingRect(c)
 old=np.array(Image.open(r.parent/'approved_pose_walk_v3_20261119'/'parts'/f'{n}.png').convert('RGBA'));new=cv2.resize(np.dstack([a,mask])[y:y+h,x:x+w],(old.shape[1],old.shape[0]),interpolation=cv2.INTER_AREA)
 safe=(old[:,:,3]>250)&(old[:,:,0]>230)&(old[:,:,1]>195)&(old[:,:,2]<245);safe2=(new[:,:,3]>250)&(new[:,:,0]>230)&(new[:,:,1]>195)&(new[:,:,2]<245)
 delta=np.median(old[:,:,:3][safe],axis=0)-np.median(new[:,:,:3][safe2],axis=0);new[:,:,:3]=np.clip(new[:,:,:3].astype(float)+delta,0,255).astype('uint8');Image.fromarray(new).save(r/'parts'/f'{n}.png');report[n]={'source':file,'crop':[x,y,w,h],'medianColorOffset':delta.tolist()}
Path('repaint_audit.json').write_text(json.dumps(report,indent=2))
