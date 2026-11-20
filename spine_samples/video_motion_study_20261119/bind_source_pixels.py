from pathlib import Path
import json,cv2,math,numpy as np
from PIL import Image
R=Path(__file__).resolve().parent
O=R/'pixel_bound';O.mkdir(exist_ok=True);(O/'parts').mkdir(exist_ok=True)
raw=json.loads((R/'ik_study.json').read_text());samples=json.loads((R/'motion_annotations.json').read_text(encoding='utf8'))['samples'];poses=json.loads((R/'native_ik_poses.json').read_text())
names=['arm_far','leg_far','leg_near','torso','shorts','arm_near','head'];ids={b['name']:i for i,b in enumerate(raw['bones'])}
atlas=Image.new('RGBA',(4096,4096));lines=['skin.png','size: 4096,4096','filter: Linear,Linear','repeat: none'];ax=4;ay=4;row=0
attachments={n:{} for n in names};manifest=[];slotkeys={n:{'attachment':[]} for n in names}
def poly(points):
 m=np.zeros((480,864),np.uint8);cv2.fillPoly(m,[np.array(points,np.int32)],1);return m.astype(bool)
def distance(x,y,a,b):
 v=np.array(b)-a;t=np.clip(((x-a[0])*v[0]+(y-a[1])*v[1])/(v@v),0,1);return np.hypot(x-a[0]-t*v[0],y-a[1]-t*v[1])
yy,xx=np.indices((480,864))
for i in range(23):
 s=samples[i];f=s['frame'];src=np.array(Image.open(R/'frames'/f'{f:04}.png').convert('RGB'));p=s['points'];pose=poses[i]['chains']
 # Largest colored character silhouette; original RGB is never modified.
 m=((src[:,:,0].astype(float)-src[:,:,2])>12).astype('uint8');cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);sil=np.zeros(m.shape,np.uint8);cv2.drawContours(sil,[max(cs,key=cv2.contourArea)],-1,255,-1)
 owner=np.full(m.shape,3,np.int16)
 waist=365-0.12*(xx-430);crotch=410-0.018*(xx-445)**2
 owner[(yy>=waist)&(yy<=crotch)]=4
 below=yy>crotch
 dn=distance(xx,yy,p['hip_near'],p['foot_near']);df=distance(xx,yy,p['hip_far'],p['foot_far'])
 owner[below&(dn<df)]=2;owner[below&(dn>=df)]=1
 # Visible near-arm contour approximated from the source hand and shoulder.
 a=np.array(p['shoulder_near']);b=np.array(p['hand_near']);v=b-a;length=np.linalg.norm(v);perp=np.array([-v[1],v[0]])/length
 arm=poly([a-perp*24,a+perp*20,b+perp*23+v/length*10,b+v/length*22,b-perp*23+v/length*10])
 owner[arm&(yy>286)]=5
 far=distance(xx,yy,p['shoulder_far'],p['hand_far'])<17
 owner[far&(xx>499)&(yy>294)&(yy<385)]=0
 owner[yy<291]=6
 # No generated hidden surfaces: each part contains visible source pixels only.
 for j,n in enumerate(names):
  region=cv2.dilate((owner==j).astype('uint8'),np.ones((7,7),np.uint8));alpha=np.where((region>0)&(sil>0),255,0).astype('uint8');rows,cols=np.where(alpha>0)
  if len(rows)==0:continue
  x0,x1=int(cols.min()),int(cols.max()+1);y0,y1=int(rows.min()),int(rows.max()+1);im=Image.fromarray(np.dstack([src,alpha])[y0:y1,x0:x1]);w,h=im.size;key=f'{n}_{f}';im.save(O/'parts'/f'{key}.png')
  assert np.array_equal(np.array(im)[:,:,:3],src[y0:y1,x0:x1])
  if ax+w+4>4096:ax=4;ay+=row+4;row=0
  assert ay+h<4096
  atlas.paste(im,(ax,ay));lines.extend([key,'  rotate: false',f'  xy: {ax}, {ay}',f'  size: {w}, {h}',f'  orig: {w}, {h}','  offset: 0, 0','  index: -1']);ax+=w+4;row=max(row,h)
  uv=[];vertices=[];tri=[];nx,ny=6,8
  for iy in range(ny+1):
   for ix in range(nx+1):
    u,v=ix/nx,iy/ny;x,y=x0+u*w,y0+v*h;uv.extend([u,v])
    if n in pose:
     ch=pose[n];a=np.array(ch['root']);b=np.array(ch['joint']);c=np.array(ch['end']);along=((np.array([x,y])-a)@(c-a))/max(1,np.linalg.norm(c-a)**2);mix=float(np.clip((along-.3)/.45,0,1));weights=[(n+'_upper',a,b,1-mix),(n+'_lower',b,c,mix)];weights=[t for t in weights if t[3]>1e-8];vertices.append(len(weights))
     for bone,start,end,weight in weights:
      ang=math.atan2(-(end[1]-start[1]),end[0]-start[0]);dx=x-start[0];dy=start[1]-y;lx=math.cos(ang)*dx+math.sin(ang)*dy;ly=-math.sin(ang)*dx+math.cos(ang)*dy;vertices.extend([ids[bone],lx,ly,weight])
    else:vertices.extend([1,ids['root'],x-432,480-y,1])
  for iy in range(ny):
   for ix in range(nx):
    a=iy*(nx+1)+ix;b=a+1;c=a+nx+1;tri.extend([a,c,b,b,c,c+1])
  attachments[n][key]={'type':'mesh','path':key,'uvs':uv,'vertices':vertices,'triangles':tri,'width':w,'height':h}
  slotkeys[n]['attachment'].append({'time':(f-63)/24,'name':key})
  manifest.append({'part':n,'sourceFrame':f,'crop':[x0,y0,x1,y1],'file':'parts/'+key+'.png','rgbExact':True,'hiddenPixelsCompleted':False})
raw['slots']=[{'name':n,'bone':'root','attachment':next(iter(attachments[n]))} for n in names]
raw['skins']=[{'name':'default','attachments':attachments}];raw['skeleton']['images']='./parts/';raw['animations']['reference_cycle']['slots']=slotkeys
(O/'skin.json').write_text(json.dumps(raw,indent=2));atlas.save(O/'skin.png');(O/'skin.atlas').write_text('\n'.join(lines)+'\n')
(O/'pixel_manifest.json').write_text(json.dumps(manifest,indent=2))
print('Created',len(manifest),'visible-only source attachments across 23 sampled poses; native IK preserved.')

