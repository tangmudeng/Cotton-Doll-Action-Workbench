from pathlib import Path
import json,shutil,numpy as np,cv2
from PIL import Image
R=Path.cwd();B=R/"pixel_sync_20261120";O=R/"limited_ik_20261120"
for n in ["parts","runtime","reference_frames"]:shutil.copytree(B/n,O/n,dirs_exist_ok=True)
for n in ["skin.png","skin.atlas","pixel_manifest.json"]:shutil.copy2(B/n,O/n)
d=json.loads((B/"skin.json").read_text());m=json.loads((B/"pixel_manifest.json").read_text())
fields={}
for f in range(63,86):
 masks={}
 for part in ["torso","shorts","head"]:
  a=next(x for x in m if x["sourceFrame"]==f and x["part"]==part)
  mask=np.zeros((480,864),np.uint8);x0,y0,x1,y1=a["crop"]
  mask[y0:y1,x0:x1]=np.array(Image.open(B/a["file"]))[:,:,3]
  masks[part]=mask
 for part in ["arm_far","arm_near","leg_far","leg_near"]:
  a=next(x for x in m if x["sourceFrame"]==f and x["part"]==part)
  at=d["skins"][0]["attachments"][part][f"{part}_{f}"];uv=np.array(at["uvs"]).reshape(-1,2);x0,y0,x1,y1=a["crop"]
  xy=uv*[x1-x0,y1-y0]+[x0,y0];mask=np.maximum(masks["torso"],masks["shorts"])
  if part.startswith("arm"):mask=np.maximum(mask,masks["head"])
  dist=cv2.distanceTransform((mask==0).astype(np.uint8),cv2.DIST_L2,5)
  q=cv2.remap(dist,xy[:,0].astype(np.float32).reshape(-1,1),xy[:,1].astype(np.float32).reshape(-1,1),cv2.INTER_LINEAR).ravel()
  q=np.clip((q-2)/12,0,1);q=q*q*(3-2*q)
  fields[f"{part}_{f}"]=q.tolist()
(O/"seam_factors.json").write_text(json.dumps(fields))
