import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from compare import render,source,cp,OUT,ROOT
font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",18)
data=json.loads((OUT/"ik_probe.json").read_text())
sheet=Image.new("RGB",(780,940),"#eeeeea");d=ImageDraw.Draw(sheet)
labels=["近手 IK","远手 IK","近脚 IK","远脚 IK"]
for i,((name,poses),label) in enumerate(zip(data.items(),labels)):
 d.text((8,10+i*232),label+"：基准 / 正向调整 / 反向调整",font=font,fill="#222222")
 for j,p in enumerate(poses):
  rgb,alpha,_=render(p["slots"]);sheet.paste(cp(rgb),(8+j*260,38+i*232))
sheet.save(OUT/"ik_limits.png")
ref0,mask0,raw0=source(63);ref1,mask1,raw1=source(85)
frame=Image.new("RGB",(720,230),"#eeeeea");dr=ImageDraw.Draw(frame)
for i,(label,rgb) in enumerate([("末帧85",ref1),("回到首帧63",ref0),("差异放大",np.minimum(abs(ref1.astype(int)-ref0)*5,255).astype("uint8"))]):
 dr.text((i*240+4,4),label,font=font,fill="#222222");frame.paste(cp(rgb),(i*240,32))
frame.save(OUT/"loop_boundary.png")
edge=[]
for f in range(63,86):
 ref,mask,raw=source(f)
 import cv2
 boundary=mask & ~cv2.erode(mask.astype("uint8"),np.ones((3,3),"uint8")).astype(bool)
 vals=raw[boundary]
 edge.append({"frame":f,"boundaryPixels":int(boundary.sum()),"brightLowChromaBoundary":int(((vals.min(axis=1)>200)&(np.ptp(vals.astype(int),axis=1)<30)).sum())})
(OUT/"edge_probe.json").write_text(json.dumps(edge,indent=2))
print("IK and loop diagnostic panels generated")
