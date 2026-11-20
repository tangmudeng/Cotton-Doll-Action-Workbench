from pathlib import Path
import numpy as np,cv2,json
from PIL import Image
r=Path.cwd();im=np.array(Image.open('arms_completed.png').convert('RGB'));places=json.loads(Path('placements.json').read_text());report={}
for i,n in enumerate(['arm_near','arm_far']):
 a=im[:,i*im.shape[1]//2:(i+1)*im.shape[1]//2];m=((a[:,:,0].astype(float)-a[:,:,2])>22).astype('uint8');cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);c=max(cs,key=cv2.contourArea);mask=np.zeros(m.shape,np.uint8);cv2.drawContours(mask,[c],-1,255,-1);x,y,w,h=cv2.boundingRect(c)
 old=np.array(Image.open(r.parent/'approved_pose_walk_20261119'/'parts'/f'{n}.png').convert('RGBA'));new=cv2.resize(np.dstack([a,mask])[y:y+h,x:x+w],(old.shape[1],old.shape[0]),interpolation=cv2.INTER_AREA)
 safe=(old[:,:,3]>250)&(old[:,:,0]>220)&(old[:,:,1]>175)&(old[:,:,2]<235);safe2=(new[:,:,3]>250)&(new[:,:,0]>220)&(new[:,:,1]>175)&(new[:,:,2]<235)
 delta=np.median(old[:,:,:3][safe],axis=0)-np.median(new[:,:,:3][safe2],axis=0);new[:,:,:3]=np.clip(new[:,:,:3].astype(float)+delta,0,255).astype('uint8');Image.fromarray(new).save(r/'parts'/f'{n}.png');report[n]={'source':'arms_completed.png','crop':[x+i*im.shape[1]//2,y,w,h],'medianColorOffset':delta.tolist()}
Path('arms_repair_audit.json').write_text(json.dumps(report,indent=2))
