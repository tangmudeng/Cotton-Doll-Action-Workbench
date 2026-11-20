import sys,json
from pathlib import Path
import numpy as np,cv2
from PIL import Image,ImageDraw,ImageFont
R=Path.cwd();sys.path.insert(0,str(R/"frame_audit_20261120"))
from compare import render,cp,source
O=R/"limited_ik_20261120";old=json.loads((R/"frame_audit_20261120/ik_probe.json").read_text());new=json.loads((O/"ik_probe.json").read_text())
font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",16)
sheet=Image.new("RGB",(1020,930),"#eeeeea");draw=ImageDraw.Draw(sheet);reports=[]
for i,name in enumerate(old):
 ref,mask,_=source(70)
 for j,(label,p) in enumerate([("旧 +",old[name][1]),("新 +",new[name][1]),("旧 -",old[name][2]),("新 -",new[name][2])]):
  rgb,a,_=render(p["slots"]);sheet.paste(cp(rgb),(j*255,38+i*228))
  draw.text((j*255+5,i*228+10),name.replace("test_","")+" "+label,font=font,fill="#222222")
  holes=(a<.5).astype("uint8");num,lab,stats,c=cv2.connectedComponentsWithStats(holes)
  enclosed=sum(int(st[cv2.CC_STAT_AREA]) for k,st in enumerate(stats) if k>0 and st[0]>0 and st[1]>0 and st[0]+st[2]<864 and st[1]+st[3]<480)
  reports.append({"test":name,"variant":label,"enclosedHolePixels":enclosed})
sheet.save(O/"ik_comparison.png")
(O/"probe_metrics.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf8")
print(reports)
