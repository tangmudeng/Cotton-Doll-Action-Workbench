"""Render official-runtime geometry for every keyframe, with premultiplied alpha."""
from pathlib import Path
import json,cv2
import numpy as np
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent;OUT=HERE/'video_fit';ROOT=HERE.parents[1]
def render(im,g):
 out=np.zeros((800,560,4),np.float32);src=np.asarray(im.convert('RGBA'),dtype=np.float32)/255;src[:,:,:3]*=src[:,:,3:4]
 uv=np.array(g['uv'],np.float32).reshape(-1,2)*im.size;xy=np.array(g['xy'],np.float32).reshape(-1,2);xy[:,0]+=512-230;xy[:,1]=1024-110-xy[:,1]
 for tri in np.array(g['tri']).reshape(-1,3):
  a=uv[tri].astype(np.float32);b=xy[tri].astype(np.float32);x0=max(0,int(np.floor(b[:,0].min())));y0=max(0,int(np.floor(b[:,1].min())));x1=min(560,int(np.ceil(b[:,0].max()))+1);y1=min(800,int(np.ceil(b[:,1].max()))+1)
  if x1<=x0 or y1<=y0:continue
  b-=np.array([x0,y0],np.float32);tile=cv2.warpAffine(src,cv2.getAffineTransform(a,b),(x1-x0,y1-y0),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT);mask=np.zeros(tile.shape[:2],np.uint8);cv2.fillConvexPoly(mask,np.rint(b*256).astype(np.int32),1,shift=8);roi=out[y0:y1,x0:x1];roi[mask>0]=tile[mask>0]
 return out
frames=json.loads((OUT/'walk_geometry.json').read_text());sheet=Image.new('RGB',(280*6,400*4),'#eeeeee');(OUT/'renders').mkdir(exist_ok=True)
for i,f in enumerate(frames):
 canvas=np.zeros((800,560,4),np.float32)
 for g in f['parts']:
  p=render(Image.open(OUT/'parts'/f'{g["path"]}.png'),g);canvas=p+canvas*(1-p[:,:,3:4])
 rgb=np.clip((canvas[:,:,:3]+.92*(1-canvas[:,:,3:4]))*255,0,255).astype(np.uint8);im=Image.fromarray(rgb);im.save(OUT/'renders'/f'{f["frame"]:04}.png');small=im.resize((280,400));ImageDraw.Draw(small).text((8,8),f'frame {f["frame"]}',fill='black');sheet.paste(small,((i%6)*280,(i//6)*400))
sheet.save(OUT/'contact_sheet.jpg',quality=94)
print('Rendered all 23 keyframes.')
