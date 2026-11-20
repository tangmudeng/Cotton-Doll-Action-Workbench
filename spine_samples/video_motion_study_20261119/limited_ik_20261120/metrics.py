import sys,json
from pathlib import Path
import numpy as np,cv2
from PIL import Image
R=Path.cwd();sys.path.insert(0,str(R/"frame_audit_20261120"))
from compare import render,source,REGIONS
old=json.loads((R/"frame_audit_20261120/ik_probe.json").read_text());new=json.loads((R/"limited_ik_20261120/ik_probe.json").read_text())
rows=[]
for name in old:
 for j,label in [(1,"plus"),(2,"minus")]:
  rec={"test":name,"direction":label}
  for var,obj in [("old",old),("new",new)]:
   rgb,alpha,_=render(obj[name][j]["slots"]);orig,mask,_=source(70)
   diff=np.max(np.abs(rgb.astype(int)-orig.astype(int)),axis=2)
   for area,(x0,y0,x1,y1) in REGIONS.items():
    rmask=mask[y0:y1,x0:x1]
    a=alpha[y0:y1,x0:x1]>.5
    e=diff[y0:y1,x0:x1]>=24
    rec[f"{var}_{area}_missing"]=int(np.sum(rmask&~a))
    rec[f"{var}_{area}_extra"]=int(np.sum(~rmask&a))
    rec[f"{var}_{area}_rgb24"]=int(np.sum(rmask&a&e))
  rows.append(rec)
Path(R/"limited_ik_20261120/ik_metrics.json").write_text(json.dumps(rows,indent=2))
# summarize visible differences in regions
for r in rows:
 print(r["test"],r["direction"], {k:v for k,v in r.items() if k.endswith(("missing","extra")) and ("old_" in k or "new_" in k) and v})
# find most similar loop endpoints with lag 16..30 using foreground masks and bbox-normalized character crops
masks=[]
for f in range(107):
 im=np.array(Image.open(R/f"frames/{f:04}.png").convert("RGB"))
 m=(im[:,:,0].astype(int)-im[:,:,2]>12).astype("uint8")
 cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 mask=np.zeros_like(m);cv2.drawContours(mask,[max(cs,key=cv2.contourArea)],-1,1,-1)
 ys,xs=np.where(mask)
 box=(max(xs.min()-4,0),max(ys.min()-4,0),min(xs.max()+5,864),min(ys.max()+5,480))
 crop=cv2.resize(mask[box[1]:box[3],box[0]:box[2]],(200,200),interpolation=cv2.INTER_AREA)
 masks.append((crop,box))
res=[]
for start in range(60,70):
 for lag in range(16,31):
  end=start+lag
  if end>=107:continue
  a,ba=masks[start];b,bb=masks[end]
  iou=np.sum((a>.5)&(b>.5))/max(1,np.sum((a>.5)|(b>.5)))
  res.append({"start":start,"end":end,"lag":lag,"bboxNormalizedMaskIoU":round(float(iou),4)})
Path(R/"limited_ik_20261120/loop_candidates.json").write_text(json.dumps(sorted(res,key=lambda x:-x["bboxNormalizedMaskIoU"]),indent=2))
print("Top loop candidates:",sorted(res,key=lambda x:-x["bboxNormalizedMaskIoU"])[:10])

