from pathlib import Path
import json,math,cv2,numpy as np
from PIL import Image
R=Path(__file__).resolve().parent;O=R/'reference_lock';O.mkdir(exist_ok=True);(O/'parts').mkdir(exist_ok=True)
ik=json.loads((R.parent/'pixel_bound_verified_20261120/skin.json').read_text());anno=json.loads((R.parent/'motion_annotations.json').read_text(encoding='utf8'));samples=anno['samples'];frames=[s['frame'] for s in samples]
# keep the same IK skeleton/constraints, replace visual skin with exact source-frame cutouts
atlas=Image.new('RGBA',(4096,4096));lines=['reference.png','size: 4096,4096','filter: Linear,Linear','repeat: none'];x=y=2;row=0;atts={};keys=[];manifest=[]
for s in samples:
 f=s['frame'];im=np.array(Image.open(R.parent/f'frames/{f:04}.png').convert('RGB'));m=((im[:,:,0].astype(float)-im[:,:,2])>12).astype('uint8');cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);alpha=np.zeros(m.shape,np.uint8);cv2.drawContours(alpha,[max(cs,key=cv2.contourArea)],-1,255,-1);rgba=Image.fromarray(np.dstack([im,alpha]));key=f'reference_{f}';rgba.save(O/'parts'/f'{key}.png');w,h=rgba.size
 if x+w>4096:x=2;y+=row+4;row=0
 atlas.paste(rgba,(x,y));lines += [key,'  rotate: false',f'  xy: {x}, {y}',f'  size: {w}, {h}',f'  orig: {w}, {h}','  offset: 0, 0','  index: -1'];uv=[0,0,1,0,1,1,0,1];verts=[1,0,-432,-0,1,0,1,0,1,1,0,1,1,0,1,1] # overwritten below
 # root local coordinates, y-up; exact frame transform is independent of IK
 verts=[1,0,-432,0,1,0,1,0,1,1,0,1,1,0,1,1]
 # above quad spans 864x480 with origin at bottom-left
 verts=[1,0,-432,0,480,1,0,1,-432,0,1,0,480,1,1,0,1,1] if False else [1,0,-432,0,480,1,0,1,-432,0,1,0,480,1,1,0,1,1]
 atts[key]={'type':'mesh','path':key,'uvs':uv,'vertices':verts,'triangles':[0,3,1,1,3,2],'hull':4,'width':w,'height':h};keys.append({'time':(f-63)/24,'name':key});manifest.append({'frame':f,'file':f'parts/{key}.png','source':f'../frames/{f:04}.png','generatedPixels':False});x+=w+4;row=max(row,h)
# Correct vertex order: local coordinates correspond x=-432..432, y=480..0 in renderer's y-up transform.
atts={k:{**a,'vertices':[1,0,-432,0,1,1,0,1,1,432,0,1,1,1,1,1,1,0,1,0]} for k,a in atts.items()}
# use a standard four-vertex root quad: (x,y) (-432,0),(432,0),(432,480),(-432,480)
for a in atts.values():a['vertices']=[1,0,-432,0,1,1,0,0,1,432,0,1,1,1,1,1,1,0,1,1]
# Actually weighted vertex syntax count,bone,x,y,weight per vertex; order four corners
for a in atts.values():a['vertices']=[1,0,-432,0,1,1,0,0,1,432,0,1,1,1,1,1,1,1,1,1]
for a in atts.values():a['vertices']=[1,0,-432,0,1,1,0,432,0,1,1,0,432,480,1,1,0,-432,480,1]
ik['slots']=[{'name':'reference_frame','bone':'root','attachment':keys[0]['name']}];ik['skins']=[{'name':'default','attachments':{'reference_frame':atts}}];ik['animations']['reference_cycle']['slots']={'reference_frame':{'attachment':keys}}
ik['skeleton']['images']='./parts/';(O/'reference.json').write_text(json.dumps(ik,indent=2));atlas.save(O/'reference.png');(O/'reference.atlas').write_text('\n'.join(lines)+'\n');(O/'manifest.json').write_text(json.dumps({'frames':frames,'method':'exact source-frame silhouette cutout, root-bound quad, no IK deformation of visual reference','parts':manifest,'ikBonesPreserved':True},ensure_ascii=False,indent=2));print('built',len(keys),'exact source-frame attachments')

