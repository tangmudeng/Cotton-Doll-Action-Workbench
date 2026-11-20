from pathlib import Path
import json,math
from PIL import Image
R=Path(__file__).resolve().parent;O=R/'parts'
places=json.loads((R/'placements.json').read_text())
def save(n,d):(R/n).write_text(json.dumps(d,indent=2),encoding='utf-8')
piv={'root':(384,664),'body':(405,510),'head':(406,410),'shorts':(397,540),'arm_near':(355,427),'arm_far':(449,428),'leg_near':(348,542),'leg_far':(451,540)}
parents={'body':'root','head':'body','shorts':'body','arm_near':'body','arm_far':'body','leg_near':'shorts','leg_far':'shorts'}
joints={'arm_near':(382,485),'arm_far':(458,470),'leg_near':(331,602),'leg_far':(480,593)}
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
 x0,y0,_,_=places[n];nx,ny=(10,18) if n in joints else ((18,12) if n=='shorts' else (4,4));uv=[];chunks=[];tri=[]
 for iy in range(ny+1):
  for ix in range(nx+1):
   u,v=ix/nx,iy/ny;x,y=x0+u*w,y0+v*h;uv.extend([u,v]);weights={n:1.0}
   if n in joints:
    px,py=piv[n];jx,jy=joints[n];length=math.hypot(jx-px,jy-py);along=((x-px)*(jx-px)+(y-py)*(jy-py))/length;root=max(0,min(1,(along+14)/70));tip=max(0,min(1,(along-length+26)/52));weights={parents[n]:1-root,n:root*(1-tip),n+'_tip':root*tip}
   if n.startswith('arm'):weights={n+'_tip':1.0}
   if n=='shorts':
    # Only the leg opening follows its thigh; waistband and crotch remain stable.
    limb='leg_near' if x<397 else 'leg_far'
    hem_pts=([(311,535),(345,541),(366,555),(383,575),(397,581)] if x<397 else [(397,581),(418,573),(441,556),(461,537),(478,524)])
    hx,hy=hem_pts[0]
    for (xa,ya),(xb,yb) in zip(hem_pts,hem_pts[1:]):
     if x>=xa:hx,hy=x,ya+(yb-ya)*max(0,min(1,(x-xa)/(xb-xa)))
    follow=max(0,min(1,(y-(hy-60))/60));follow*=.6
    crotch=max(0,min(1,abs(x-397)/60));follow*=crotch
    px,py=piv[limb];jx,jy=joints[limb];length=math.hypot(jx-px,jy-py);along=((x-px)*(jx-px)+(y-py)*(jy-py))/length
    root=max(0,min(1,(along+14)/70))
    weights={'shorts':1-follow*root,limb:follow*root}
   weights={k:v for k,v in weights.items() if v>1e-7};chunk=[len(weights)]
   for k,weight in weights.items():bx,by=piv[k];chunk.extend([indices[k],x-bx,by-y,weight])
   chunks.append(chunk)
 for iy in range(ny):
  for ix in range(nx):a=iy*(nx+1)+ix;b=a+1;c=a+nx+1;d=c+1;tri.extend([a,c,b,b,c,d])
 boundary=list(range(nx+1))+[iy*(nx+1)+nx for iy in range(1,ny+1)]+[ny*(nx+1)+ix for ix in range(nx-1,-1,-1)]+[iy*(nx+1) for iy in range(ny-1,0,-1)];seq=boundary+[i for i in range(len(chunks)) if i not in boundary];remap={v:i for i,v in enumerate(seq)}
 attachments[n]={n:{'type':'mesh','uvs':[a for i in seq for a in uv[i*2:i*2+2]],'triangles':[remap[i] for i in tri],'vertices':[a for i in seq for a in chunks[i]],'hull':len(boundary),'width':w,'height':h}}
frames=[64,67,70,73,76,79,82,85];angles={'arm_near':[0,21,38,32,12,-17,-27,0],'arm_far':[0,-12,-21,-15,1,16,22,0],'leg_near':[0,-16,-27,-18,6,24,30,0],'leg_far':[0,22,33,21,-6,-21,-24,0],'arm_near_tip':[0,-8,-14,-9,0,5,8,0],'arm_far_tip':[0,6,11,7,0,-4,-7,0],'leg_near_tip':[0,12,23,12,0,-11,-16,0],'leg_far_tip':[0,-11,-18,-10,0,15,21,0],'head':[0,-.7,-1.4,-.6,0,.7,1,0],'body':[0,1,1.8,.7,0,-1,-1.5,0]}
anim={n:{'rotate':[{'time':(f-64)/24,'value':v-vals[2]} for f,v in zip(frames,vals)]} for n,vals in angles.items()}
for limb in ['arm_near_tip','arm_far_tip']:
 for key in anim[limb]['rotate']:key['value']=0
anim['body']['translate']=[{'time':(f-64)/24,'x':x-2,'y':y-7} for f,x,y in zip(frames,[0,1,2,1,0,-1,-2,0],[0,3,7,3,0,3,7,0])]
p={'skeleton':{'spine':'4.2.43','images':'./parts/','x':-220,'y':0,'width':450,'height':570},'bones':bones,'slots':slots,'skins':[{'name':'default','attachments':attachments}],'animations':{'walk':{'bones':anim},'setup':{}}}
save('walk.json',p);page.save(R/'walk.png');(R/'walk.atlas').write_text('\n'.join(atlas)+'\n');save('animation_observations.json',{'frames':frames,'method':'manual visual rotation fit, not automatic motion capture','visualApproved':False});print('Built 12 bones, 7 attachments and walk animation.')
