from functools import lru_cache
from pathlib import Path
import csv
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
BASE = ROOT / "pixel_bound_controls_20261120"
W, H = 864, 480
ATLAS = np.array(Image.open(BASE / "skin.png").convert("RGBA"))
CROP = (315, 285, 555, 477)
REGIONS = {"body": (315, 285, 555, 477), "crotch_area": (377, 354, 512, 426),
           "far_hand_area": (492, 298, 548, 387), "feet_area": (331, 424, 550, 477)}

@lru_cache(None)
def part(slot, frame):
    return np.array(Image.open(BASE / "parts" / f"{slot}_{frame}.png").convert("RGBA"))

def render(slots):
    result = np.zeros((H, W, 4), np.float32)
    diagnostics = {}
    for slot in slots:
        x, y, w, h = slot["region"]
        texture = ATLAS[y:y+h, x:x+w]
        assert np.array_equal(texture, part(slot["name"], slot["frame"]))
        points = np.array(slot["v"]).reshape(-1, 2)
        uv = np.array(slot["uv"]).reshape(-1, 2) * (w, h)
        x0, y0, x1, y1 = slot["crop"]
        error = np.linalg.norm(points - (uv + [x0, y0]), axis=1)
        diagnostics[slot["name"]] = round(float(error.max()), 3)
        layer = np.zeros_like(result)
        tex = texture.astype(np.float32) / 255
        tex[:, :, :3] *= tex[:, :, 3:]
        for triangle in np.array(slot["triangles"]).reshape(-1, 3):
            dest = points[triangle]
            src = uv[triangle]
            left, top = np.maximum(np.floor(dest.min(axis=0)).astype(int), 0)
            right, bottom = np.minimum(np.ceil(dest.max(axis=0)).astype(int), (W, H))
            if left >= right or top >= bottom:
                continue
            edges = (dest[1:] - dest[0]).T
            if abs(np.linalg.det(edges)) < 1e-8:
                continue
            yy, xx = np.mgrid[top:bottom, left:right]
            centers = np.stack((xx + .5, yy + .5), axis=-1)
            weights = (centers - dest[0]) @ np.linalg.inv(edges).T
            inside = (weights.min(axis=2) >= -1e-7) & (weights.sum(axis=2) <= 1+1e-7)
            coord = (src[0] + weights @ (src[1:] - src[0]) - .5).astype(np.float32)
            colors = cv2.remap(tex, coord[:,:,0], coord[:,:,1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            target = layer[top:bottom, left:right]
            target[inside] = colors[inside]
        result = layer + result * (1 - layer[:,:,3:])
    rgb = result[:,:,:3] * 255 + (1 - result[:,:,3:]) * 244
    return np.round(rgb).astype(np.uint8), result[:,:,3], diagnostics

@lru_cache(None)
def source(frame):
    rgb = np.array(Image.open(ROOT / "frames" / f"{frame:04}.png").convert("RGB"))
    m = (rgb[:,:,0].astype(np.int16)-rgb[:,:,2] > 12).astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(m)
    cv2.drawContours(mask,[max(contours,key=cv2.contourArea)],-1,1,-1)
    return np.where(mask[:,:,None], rgb, 244), mask.astype(bool), rgb

def cp(im, bounds=CROP):
    x0,y0,x1,y1 = bounds
    return Image.fromarray(im[y0:y1, x0:x1])

if __name__ == "__main__":
    poses = json.loads((OUT / "poses.json").read_text(encoding="utf8"))
    rows = []
    panels = {}
    for variant, data in poses.items():
        for s in data["passes"]:
            f, mode, t, slots = (s[k] for k in ("frame", "mode", "t", "slots"))
            reference, silhouette, original = source(f)
            result, alpha, shifts = render(slots)
            raw_mask = np.zeros((H,W), bool)
            for slot in slots:
                x0,y0,x1,y1 = slot["crop"]
                p = part(slot["name"], slot["frame"])
                _, _, raw_source = source(slot["frame"])
                assert np.array_equal(p[:,:,:3], raw_source[y0:y1,x0:x1])
                raw_mask[y0:y1,x0:x1] |= p[:,:,3] > 0
            error = np.max(np.abs(result.astype(np.int16)-reference),axis=2)
            missing = silhouette & (alpha < .5)
            extra = ~silhouette & (alpha >= .5)
            mismatch = silhouette & (alpha >= .5) & (error >= 24)
            diff = np.where(silhouette[:,:,None], reference*.55+91, 244).astype(np.uint8)
            diff[missing] = [220,46,83]
            diff[extra] = [0,151,180]
            diff[mismatch] = [249,171,33]
            row = {"variant":variant,"video_frame":f,"mode":mode,"seconds":round(t,7),
                   "attachments":",".join(map(str, sorted({p["frame"] for p in slots}))),
                   "raw_missing":int(np.sum(silhouette & ~raw_mask)),
                   "raw_extra":int(np.sum(~silhouette & raw_mask)), **shifts}
            for name,(x0,y0,x1,y1) in REGIONS.items():
                ys,xs = slice(y0,y1),slice(x0,x1)
                for label,mask in [("missing",missing),("extra",extra),("rgb24",mismatch)]:
                    row[f"{name}_{label}"] = int(mask[ys,xs].sum())
            rows.append(row)
            if variant=="spine" and mode in {"key","end","video"}:
                panels[f,mode] = [cp(x) for x in (reference,result,diff)]
                if mode=="key":
                    panels[f,"full"] = [Image.fromarray(x) for x in (reference,result,diff)]
    with (OUT / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer=csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    font = "C:/Windows/Fonts/msyh.ttc"
    from PIL import ImageFont
    small = ImageFont.truetype(font, 16)
    large = ImageFont.truetype(font, 22)
    for start in range(63,86,4):
        frames = range(start,min(start+4,86))
        board = Image.new("RGB",(1032, 45+len(frames)*218),"#ecebe8")
        d = ImageDraw.Draw(board)
        for x,title in [(16,"源帧（角色局部）"),(272,"Spine 同帧"),(528,"同帧像素差"),(784,"切换前一刻")]:
            d.text((x,10),title,font=large,fill="#18251f")
        for i,f in enumerate(frames):
            y=45+i*218
            d.text((16,y),f"第 {f} 帧",font=small,fill="#18251f")
            imgs = panels[f,"key"] + ([panels[f,"end"][1]] if (f,"end") in panels else [])
            for j,img in enumerate(imgs):
                board.paste(img,(16+j*256,y+23))
        board.save(OUT/f"frames_{start}_{frames[-1]}.png")
    for f in (63,70,74,81,85):
        board = Image.new("RGB",(864*3,480),"white")
        for i,img in enumerate(panels[f,"full"]):
            board.paste(img,(864*i,0))
        board.save(OUT/f"full_{f}.png")
    
    files = sorted(Path.home().joinpath("AppData/Local/Temp").glob("codex-clipboard-*.png"))
    prefixes = ("39725ddf","d9940b23","394b7f5e","71dc9573","45a9794d","95afc1c8")
    board=Image.new("RGB",(1440,900),"#ecebe8")
    for i,prefix in enumerate(prefixes):
        image=Image.open(next(f for f in files if f.name.startswith("codex-clipboard-"+prefix))).convert("RGB")
        image.thumbnail((474,418))
        x,y=i%3*480,i//3*450
        board.paste(image,(x,y+24))
        ImageDraw.Draw(board).text((x+5,y),f"截图 {i+1}",font=small,fill="#18251f")
    board.save(OUT/"user_screenshots.jpg",quality=94)
