import json, hashlib, csv
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from compare import OUT, ROOT, render, source, cp, CROP
from PIL import ImageFont
font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
data=json.loads((OUT/"sync_poses.json").read_text())["sync"]
old=json.loads((OUT/"poses.json").read_text())["spine"]
report={"scope":"source frames 63-85 (zero-based), not entire 107-frame video","method":"official Spine 4.2 runtime vertices; independent CPU triangle rasterizer, not editor screenshot","frames":23,"sampledTimes":len(data["passes"]),"sourceVideo":{},"maxVertexShiftPx":0,"maxIntraFrameVertexMovementPx":0,"framesDetail":[]}
source_info=json.loads((ROOT/"source.json").read_text(encoding="utf8"))
cap=cv2.VideoCapture(source_info["source"])
report["sourceVideo"]={"fps":cap.get(cv2.CAP_PROP_FPS),"width":cap.get(cv2.CAP_PROP_FRAME_WIDTH),"height":cap.get(cv2.CAP_PROP_FRAME_HEIGHT),"count":cap.get(cv2.CAP_PROP_FRAME_COUNT)}
frames=[]
panels={}
for f in range(63,86):
    cap.set(cv2.CAP_PROP_POS_FRAMES,f)
    ok,video=cap.read()
    assert ok
    video=cv2.cvtColor(video,cv2.COLOR_BGR2RGB)
    ref,sil,raw=source(f)
    assert np.array_equal(video,raw),f"source mismatch at {f}"
    poses=[s for s in data["passes"] if s["frame"]==f]
    start=poses[0]
    assert all(all(p["frame"]==f for p in s["slots"]) for s in poses)
    err=max(float(np.max(np.abs(np.array(a["v"])-b["v"]))) for s in poses for a,b in zip(start["slots"],s["slots"]))
    assert err<1e-5,(f,err)
    report["maxIntraFrameVertexMovementPx"]=max(err,report["maxIntraFrameVertexMovementPx"])
    rgb,alpha,diag=render(start["slots"])
    report["maxVertexShiftPx"]=max(report["maxVertexShiftPx"],max(diag.values()))
    miss=int(np.sum(sil&(alpha<.5)))
    extra=int(np.sum(~sil&(alpha>=.5)))
    mae=float(np.abs(rgb.astype(float)-ref)[sil].mean())
    changed=int(np.sum(sil & (np.max(abs(rgb.astype(int)-ref),axis=2)>=24)))
    report["framesDetail"].append({"frame":f,"missingPixels":miss,"extraPixels":extra,"pixelsWithChannelError24":changed,"meanRGBError":mae,"maxVertexShiftPx":max(diag.values())})
    assert miss==extra==changed==0,(f,miss,extra,changed)
    prev=next((p for p in old["passes"] if p["frame"]==f and p["mode"]=="end"),None)
    oldrgb=render(prev["slots"])[0] if prev else render(next(p for p in old["passes"] if p["frame"]==f and p["mode"]=="key")["slots"])[0]
    panels[f]=[cp(ref),cp(oldrgb),cp(rgb)]
    board=Image.new("RGB",(984,414),"#efefea")
    d=ImageDraw.Draw(board)
    for j,(title,img) in enumerate(zip(["原视频","旧版：切换前","修订：骨骼/皮肤同步"],panels[f])):
        d.text((j*328+7,8),title,font=font,fill="#23352c")
        board.paste(img.resize((320,256)),(j*328+4,43))
    d.text((10,319),f"源视频第 {f} 帧｜修订保留原帧像素、拆件、IK，不补画",font=font,fill="#23352c")
    d.text((10,351),"旧版栏用于显示帧间拉扯，并非同一时间的源视频误差。",font=font,fill="#23352c")
    d.text((10,382),"本轮仅验证 63–85 帧样板，循环边界及自由改动作仍待验收。",font=font,fill="#23352c")
    frames.append(board)
    board.save(OUT/f"fixed_{f}.png")
cap.release()
for start in range(63,86,4):
    fs=list(range(start,min(start+4,86)))
    sheet=Image.new("RGB",(784,40+len(fs)*216),"#efefea")
    draw=ImageDraw.Draw(sheet)
    for j,title in enumerate(["源视频","旧版切换前","同步修订"]):
        draw.text((8+260*j,10),title,font=font,fill="#23352c")
    for i,f in enumerate(fs):
        draw.text((8,40+i*216),f"第 {f} 帧",font=font,fill="#23352c")
        for j,p in enumerate(panels[f]):
            sheet.paste(p,(8+260*j,64+i*216))
    sheet.save(OUT/f"fixed_sheet_{start}.png")
frames[0].save(OUT/"comparison.gif",save_all=True,append_images=frames[1:],duration=125,loop=0)
out=cv2.VideoWriter(str(OUT/"comparison.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),24,(984,414))
for _ in range(4):
    for frame in frames:
        out.write(cv2.cvtColor(np.array(frame),cv2.COLOR_RGB2BGR))
out.release()
report["sourceFramesIdenticalToVideo"]=True
report["visualAcceptancePending"]=True
report["loopBoundaryReviewed"]=False
(OUT/"sync_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k!="framesDetail"},ensure_ascii=False))
