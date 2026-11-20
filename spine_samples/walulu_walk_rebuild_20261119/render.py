from pathlib import Path
import json,cv2,numpy as np
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parent;poses=json.loads((R/'runtime_poses.json').read_text());frames=[];reports=[]
for pose in poses:
 canvas=np.ones((768,768,3),np.float32)*255;coverage=np.zeros((768,768),np.float32)
 for part in pose:
  tex=np.array(Image.open(R/'parts'/(part['name']+'.png')).convert('RGBA')).astype(np.float32)/255;tex[:,:,:3]*=tex[:,:,3:4];h,w=tex.shape[:2];uv=np.array(part['uv'],np.float32).reshape(-1,2)*[w,h];dst=np.array(part['vertices'],np.float32).reshape(-1,2);dst[:,0]+=384;dst[:,1]=664-dst[:,1];layer=np.zeros((768,768,4),np.float32)
  for tri in np.array(part['triangles']).reshape(-1,3):
   d=dst[tri].astype(np.float32);s=uv[tri].astype(np.float32);x,y,bw,bh=cv2.boundingRect(d);x0=max(0,x);y0=max(0,y);x1=min(768,x+bw+1);y1=min(768,y+bh+1)
   if x1<=x0 or y1<=y0:continue
   local=d-[x0,y0];mat=cv2.getAffineTransform(s,local.astype(np.float32));patch=cv2.warpAffine(tex,mat,(x1-x0,y1-y0),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT);mask=np.zeros((y1-y0,x1-x0),np.uint8);cv2.fillConvexPoly(mask,np.round(local*16).astype(np.int32),255,shift=4);region=layer[y0:y1,x0:x1];region[mask>0]=patch[mask>0]
  alpha=layer[:,:,3:4];canvas=layer[:,:,:3]*255+canvas*(1-alpha);coverage=layer[:,:,3]+coverage*(1-layer[:,:,3])
 binary=(coverage>.5).astype('uint8');_,_,stats,_=cv2.connectedComponentsWithStats(binary);flood=binary.copy();cv2.floodFill(flood,None,(0,0),1);_,_,holes,_=cv2.connectedComponentsWithStats(1-flood);reports.append({'phase':len(frames)/48,'components':int(sum(s[4]>10 for s in stats[1:])),'holes':[s.tolist() for s in holes[1:] if s[4]>3]});frames.append(Image.fromarray(np.uint8(np.clip(canvas,0,255))))
frames[0].save(R/'walk_preview.gif',save_all=True,append_images=frames[1:-1],duration=[(round((i+1)*87.5/48)-round(i*87.5/48))*10 for i in range(48)],loop=0)
sheet=Image.new('RGB',(1536,816),'white');d=ImageDraw.Draw(sheet)
for k,i in enumerate([0,7,14,21,28,35,42,48]):sheet.paste(frames[i].resize((384,384)),(k%4*384,k//4*408));d.text((k%4*384+10,k//4*408+390),f'phase {i/48:.3f}',fill='black')
sheet.save(R/'walk_contact.png');(R/'silhouette_checks.json').write_text(json.dumps(reports,indent=2));print('Rendered',len(frames),'poses; frames with holes:',sum(bool(x['holes']) for x in reports))
