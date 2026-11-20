from pathlib import Path
import json,math,cv2,numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import distance_transform_edt
R=Path(__file__).resolve().parent;O=R/'parts';O.mkdir(exist_ok=True)
def save(n,d):(R/n).write_text(json.dumps(d,indent=2),encoding='utf-8')
names=['body','shorts','arm_far','arm_near','leg_near','leg_far']
source=np.array(Image.open(R/'reference/character.png').convert('RGBA'));sheet=np.array(Image.open(R/'painted_parts_corrected.png').convert('RGB'));h,w=sheet.shape[:2]
target=np.median(source[470:510,383:430,:3].reshape(-1,3),axis=0)
outline=source[475:575,285:375,:3].reshape(-1,3);outline=np.median(outline[(outline[:,0]>110)&(outline[:,0]<190)&(outline[:,1]<145)],axis=0)
places={'head':[179,104,589,445],'body':[320,418,485,580],'shorts':[339,524,481,595],'arm_near':[287,435,380,577],'arm_far':[438,435,506,555],'leg_near':[319,550,404,664],'leg_far':[405,550,478,648]};colors={}
for i,n in enumerate(names):
 tile=sheet[i//3*h//2:(i//3+1)*h//2,i%3*w//3:(i%3+1)*w//3].copy();mask=(tile.min(axis=2)<225).astype('uint8');cnts,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);c=max(cnts,key=cv2.contourArea);solid=np.zeros(mask.shape,np.uint8);cv2.drawContours(solid,[c],-1,1,-1);inner=cv2.erode(solid,np.ones((3,3),np.uint8));_,inds=distance_transform_edt(1-inner,return_indices=True);fg=tile[inds[0],inds[1]].astype(float)
 alpha=np.clip(np.sum((255-tile)*(255-fg),axis=2)/np.maximum(np.sum((255-fg)**2,axis=2),1),0,1);alpha[inner>0]=1;alpha[cv2.dilate(solid,np.ones((3,3),np.uint8))==0]=0
 rgb=tile.astype(float);edge=(alpha>0)&(alpha<1);rgb[edge]=(rgb[edge]-255*(1-alpha[edge,None]))/alpha[edge,None];rgb=np.clip(rgb,0,255)
 if n!='shorts':
  skin=(inner>0)&(rgb[:,:,0]>220)&(rgb[:,:,1]>165)&(rgb[:,:,2]>125);med=np.median(rgb[skin],axis=0);delta=target-med;rgb=np.clip(rgb+np.clip((rgb[:,:,0]-170)/60,0,1)[:,:,None]*delta,0,255);colors[n]={'skinTarget':target.tolist(),'rgbCorrection':delta.tolist()}
 dark=(inner>0)&(rgb[:,:,0]<190)&(rgb[:,:,1]<155)
 if dark.any():rgb=np.clip(rgb+np.clip((215-rgb[:,:,0])/40,0,1)[:,:,None]*(outline-np.median(rgb[dark],axis=0)),0,255)
 out=Image.fromarray(np.dstack([np.uint8(rgb),np.uint8(alpha*255)]));out=out.crop(out.getbbox());b=places[n];out=out.resize((b[2]-b[0],b[3]-b[1]),Image.Resampling.LANCZOS)
 if n.startswith('arm'):
  ar=np.array(out);ar[:,:,3]=np.uint8(ar[:,:,3]*np.clip(np.arange(ar.shape[0])/(ar.shape[0]*.14),0,1)[:,None]);out=Image.fromarray(ar)
 out.save(O/f'{n}.png')
Image.fromarray(source).crop(tuple(places['head'])).save(O/'head.png');save('placements.json',places);save('color_matching.json',colors)
piv={'root':(384,664),'body':(405,532),'head':(406,438),'shorts':(406,554),'arm_near':(351,456),'arm_far':(456,456),'leg_near':(359,571),'leg_far':(443,569)}
parents={'body':'root','head':'body','shorts':'body','arm_near':'body','arm_far':'body','leg_near':'shorts','leg_far':'shorts'}
joints={'arm_near':(334,510),'arm_far':(477,501),'leg_near':(359,612),'leg_far':(440,607)}
for n,xy in joints.items():piv[n+'_tip']=xy;parents[n+'_tip']=n
bones=[{'name':'root'}]
for n in list(parents):
 x,y=piv[n];px,py=piv[parents[n]];bones.append({'name':n,'parent':parents[n],'x':x-px,'y':py-y,'length':40})
indices={b['name']:i for i,b in enumerate(bones)};order=['arm_far','leg_far','leg_near','body','shorts','arm_near','head'];slots=[{'name':n,'bone':n,'attachment':n} for n in order];attachments={}
page=Image.new('RGBA',(1024,1024));atlas=['walk.png','size: 1024,1024','filter: Linear,Linear','repeat: none'];ax=4;ay=4;row=0
for n in order:
 im=Image.open(O/f'{n}.png');w,h=im.size
 if ax+w+4>1024:ax=4;ay+=row+8;row=0
 assert ay+h<1024
 page.paste(im,(ax,ay));atlas +=[n,'  rotate: false',f'  xy: {ax}, {ay}',f'  size: {w}, {h}',f'  orig: {w}, {h}','  offset: 0, 0','  index: -1'];ax+=w+8;row=max(row,h)
 x0,y0,_,_=places[n];nx,ny=(10,14) if n in joints else (4,4);uv=[];chunks=[];tri=[]
 for iy in range(ny+1):
  for ix in range(nx+1):
   u,v=ix/nx,iy/ny;x,y=x0+u*w,y0+v*h;uv.extend([u,v]);weights={n:1.0}
   if n in joints:
    px,py=piv[n];jx,jy=joints[n];length=math.hypot(jx-px,jy-py);along=((x-px)*(jx-px)+(y-py)*(jy-py))/length;root=max(0,min(1,(along+14)/70));tip=max(0,min(1,(along-length+18)/36));weights={parents[n]:1-root,n:root*(1-tip),n+'_tip':root*tip}
   weights={k:v for k,v in weights.items() if v>1e-7};chunk=[len(weights)]
   for k,weight in weights.items():bx,by=piv[k];chunk.extend([indices[k],x-bx,by-y,weight])
   chunks.append(chunk)
 for iy in range(ny):
  for ix in range(nx):a=iy*(nx+1)+ix;b=a+1;c=a+nx+1;d=c+1;tri.extend([a,c,b,b,c,d])
 boundary=list(range(nx+1))+[iy*(nx+1)+nx for iy in range(1,ny+1)]+[ny*(nx+1)+ix for ix in range(nx-1,-1,-1)]+[iy*(nx+1) for iy in range(ny-1,0,-1)];seq=boundary+[i for i in range(len(chunks)) if i not in boundary];remap={v:i for i,v in enumerate(seq)}
 attachments[n]={n:{'type':'mesh','uvs':[a for i in seq for a in uv[i*2:i*2+2]],'triangles':[remap[i] for i in tri],'vertices':[a for i in seq for a in chunks[i]],'hull':len(boundary),'width':w,'height':h}}
frames=[64,67,70,73,76,79,82,85];angles={'arm_near':[0,21,38,32,12,-17,-27,0],'arm_far':[0,-12,-21,-15,1,16,22,0],'leg_near':[0,-16,-27,-18,6,24,30,0],'leg_far':[0,22,33,21,-6,-21,-24,0],'arm_near_tip':[0,-8,-14,-9,0,5,8,0],'arm_far_tip':[0,6,11,7,0,-4,-7,0],'leg_near_tip':[0,12,23,12,0,-11,-16,0],'leg_far_tip':[0,-11,-18,-10,0,15,21,0],'head':[0,-.7,-1.4,-.6,0,.7,1,0],'body':[0,1,1.8,.7,0,-1,-1.5,0]}
anim={n:{'rotate':[{'time':(f-64)/24,'value':v} for f,v in zip(frames,vals)]} for n,vals in angles.items()}
anim['body']['translate']=[{'time':(f-64)/24,'x':x,'y':y} for f,x,y in zip(frames,[0,1,2,1,0,-1,-2,0],[0,3,7,3,0,3,7,0])]
p={'skeleton':{'spine':'4.2.43','images':'./parts/','x':-220,'y':0,'width':450,'height':570},'bones':bones,'slots':slots,'skins':[{'name':'default','attachments':attachments}],'animations':{'walk':{'bones':anim},'setup':{}}}
save('walk.json',p);page.save(R/'walk.png');(R/'walk.atlas').write_text('\n'.join(atlas)+'\n');save('animation_observations.json',{'frames':frames,'method':'manual visual rotation fit, not automatic motion capture','visualApproved':False});print('Built 12 bones, 7 attachments and walk animation.')
