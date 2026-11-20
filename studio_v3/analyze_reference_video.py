import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


TASK_ID = "comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa"
SOURCE_URL = "./generated_rig/video_f7e82942/source.mp4"
SHA256 = "8fc0f8406d6a258640b65d34c5ad7fb0e35f231131d7eec945781dd9d93343e5"
# 人工审阅 inspection_grid.jpg 的源像素坐标；不是模型预测。±12px为审阅误差预算。
# near 身份依据画面左肩连接及前层遮挡暂定，交叉时仍不保证跨帧身份。
MANUAL = {
    0: {"hand_near": (357, 335), "hand_far": (514, 309), "foot_near": (433, 416), "foot_far": None},
    8: {"hand_near": (457, 330), "hand_far": None, "foot_near": (393, 402), "foot_far": (511, 401)},
    16: {"hand_near": (367, 330), "hand_far": (517, 304), "foot_near": (440, 405), "foot_far": None},
    24: {"hand_near": (468, 323), "hand_far": None, "foot_near": (395, 410), "foot_far": (518, 400)},
    32: {"hand_near": (361, 331), "hand_far": (514, 304), "foot_near": (436, 416), "foot_far": None},
}


def foreground(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > 40) & (hsv[:, :, 2] < 253)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[idx, cv2.CC_STAT_AREA] < 1000:
        return None
    return labels == idx


def point_measure(mask, box):
    x, y, w, h = box
    crop = mask[y:y + h, x:x + w]
    yy, xx = np.where(crop)
    if not len(xx):
        return None
    points = {}
    points["foregroundCentroid"] = {"x": round(float(xx.mean() + x), 2), "y": round(float(yy.mean() + y), 2), "confidence": "high"}
    for side, xa, xb in (("screenLeft", 0, int(w * .5)), ("screenRight", int(w * .5), w)):
        region = crop[int(h * .76):, xa:xb]
        ry, rx = np.where(region)
        key = side + "FootCandidate"
        if len(rx) < 8:
            points[key] = {"visible": False, "confidence": "low", "occlusion": "not separable from silhouette"}
        else:
            maxrow = ry.max()
            bottom_x = rx[ry == maxrow]
            points[key] = {"x": round(float(x + xa + bottom_x.mean()), 2), "y": round(float(y + int(h * .76) + maxrow), 2), "visible": True, "confidence": "low", "identity": "screen-side candidate; near/far unknown", "method": "lower-silhouette extremum"}
    for side, xa, xb in (("screenLeft", 0, int(w * .40)), ("screenRight", int(w * .60), w)):
        region = crop[int(h * .60):int(h * .78), xa:xb]
        ry, rx = np.where(region)
        key = side + "HandCandidate"
        if len(rx) < 10:
            points[key] = {"visible": False, "confidence": "low", "occlusion": "not separable from silhouette"}
        else:
            # This is only an extremum on the arm-height silhouette, not an anatomical hand annotation.
            edge = 0 if side == "screenLeft" else len(region[0]) - 1
            edge_pixels = np.where(region[:, edge])[0]
            if len(edge_pixels):
                px, py = xa + edge, int(h * .60) + int(np.median(edge_pixels))
                method = "outer silhouette at arm-height; hand may be occluded"
            else:
                distance = rx if side == "screenLeft" else (len(region[0]) - 1 - rx)
                k = int(np.argmin(distance))
                px, py = xa + int(rx[k]), int(ry[k]) + int(h * .60)
                method = "nearest arm-height silhouette pixel; hand not isolated"
            points[key] = {"x": round(float(x + px), 2), "y": round(float(y + py), 2), "visible": True, "confidence": "low", "visibility": "unresolved", "identity": "screen-side candidate; near/far unknown", "method": method, "anatomicalPoint": False}
    return points


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    project = Path(args.project).resolve()
    out_dir = project / "generated_rig" / "video_f7e82942"
    frame_dir = out_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "source.mp4"
    digest = hashlib.sha256(video_path.read_bytes()).hexdigest()
    cap = cv2.VideoCapture(str(video_path))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps
    measurements = []
    raw_frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        mask = foreground(frame)
        if mask is not None:
            ys, xs = np.where(mask)
            box = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
            moments = cv2.moments(mask.astype(np.uint8))
            cx, cy = moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]
            measurements.append({"index": idx, "bbox": box, "centroid": [cx, cy], "area": int(mask.sum())})
        else:
            measurements.append({"index": idx, "bbox": None, "centroid": None, "area": 0})
        raw_frames.append(frame)
        idx += 1
    cap.release()

    assert digest == SHA256, f"源视频SHA256不符: {digest}"
    assert idx == frame_count == 107 and (width, height, fps) == (864, 480, 24.0)
    # 归一化轮廓的下半身匹配，避免头部大面积静止导致bbox假周期。
    valid = [m for m in measurements if m["bbox"]]
    normalized = []
    for frame, m in zip(raw_frames, measurements):
        if m["bbox"]:
            x, y, w, h = m["bbox"]
            mask = foreground(frame)[y:y+h, x:x+w].astype(np.uint8)
            normalized.append(cv2.resize(mask, (128, 160), interpolation=cv2.INTER_NEAREST)[85:])
        else:
            normalized.append(None)
    candidates = []
    for lag in range(8, min(45, frame_count // 2 + 1)):
        pairs = [(measurements[i], measurements[i + lag]) for i in range(frame_count - lag) if measurements[i]["bbox"] and measurements[i + lag]["bbox"]]
        if len(pairs) < frame_count * .65:
            continue
        errors = []
        for a, b in pairs:
            ba, bb = a["bbox"], b["bbox"]
            errors.append(abs(ba[2] - bb[2]) / max(ba[2], bb[2]) + abs(ba[3] - bb[3]) / max(ba[3], bb[3]) + math.dist(a["centroid"], b["centroid"]) / max(ba[2], ba[3]))
        iou_errors = []
        for i in range(frame_count - lag):
            a, b = normalized[i], normalized[i + lag]
            if a is not None and b is not None:
                iou_errors.append(1 - float(np.logical_and(a, b).sum()) / float(np.logical_or(a, b).sum()))
        candidates.append((float(np.median(iou_errors)) + float(np.median(errors)), lag, len(pairs)))
    candidates.sort()
    if candidates:
        err, lag, pair_count = candidates[0]
        cycle_conf = "medium" if err < .35 else "low"
        cycle_reason = f"候选周期由相隔帧的下半身归一化轮廓1-IoU中位数+bbox尺寸/重心中位归一化差最小确定；lag={lag}帧，组合误差={err:.4f}，有效配对={pair_count}。人工网格审阅0/16/32与8/24姿态分别相近；仍不声称稳定解剖周期或正式循环验收。"
        local_candidates = []
        for start in range(frame_count - lag):
            a,b = normalized[start],normalized[start+lag]
            if a is not None and b is not None:
                seam = 1 - float(np.logical_and(a,b).sum())/float(np.logical_or(a,b).sum())
                local_candidates.append((seam,start))
        seam,start = min(local_candidates)
        cycle = {"start": round(start / fps, 6), "end": round((start + lag) / fps, 6), "startFrame": start, "endFrame": start+lag, "lagFrames": lag, "confidence": cycle_conf, "reason": cycle_reason + f" 起止帧在该lag下按下半身轮廓接缝误差最小选择为{start}..{start+lag}。", "medianNormalizedError": round(err, 5), "endpointSilhouetteIou": round(1-seam, 5), "validPairs": pair_count}
    else:
        lag, cycle = None, {"start": None, "end": None, "confidence": "low", "reason": "未找到足够可靠的轮廓重复周期。"}

    selected = sorted(set(list(range(0, frame_count, 2)) + [65, 89] + ([cycle["startFrame"], cycle["endFrame"]] if lag is not None else []) + [frame_count - 1]))
    frames = []
    tracks = []
    for i in selected:
        m = measurements[i]
        filename = f"frame_{i:03d}.jpg"
        frame = raw_frames[i]
        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(frame_dir / filename, quality=92)
        if m["bbox"]:
            landmarks = point_measure(foreground(frame), m["bbox"])
            for name in ("hand_near", "hand_far", "foot_near", "foot_far"):
                xy = MANUAL.get(i, {}).get(name)
                if i in MANUAL and xy is not None:
                    landmarks[name] = {"x": xy[0], "y": xy[1], "confidence": "low", "visibility": "visible", "visible": True, "identityConfidence": "low", "method": "manual_grid_review", "annotationUncertaintyPx": 12, "sourceFrame": i, "note": "掌心/脚掌中心人工近似，近远侧身份暂定，不可用于正式绑定"}
                else:
                    landmarks[name] = {"x": None, "y": None, "confidence": "low", "visibility": "occluded" if i in MANUAL else "unresolved", "visible": False, "method": "manual_grid_review" if i in MANUAL else "not_annotated", "note": "无法独立识别的遮挡肢体" if i in MANUAL else "未人工审阅该帧解剖身份，禁止将屏幕侧极值填入"}
            bbox = {"x": m["bbox"][0], "y": m["bbox"][1], "width": m["bbox"][2], "height": m["bbox"][3]}
            tracks.append({"index": i, "time": round(i / fps, 5), "bbox": bbox, "centroid": {"x": round(m["centroid"][0], 2), "y": round(m["centroid"][1], 2)}, "areaPx": m["area"], "landmarks": landmarks})
            overall_conf = "high" if m["area"] > 50000 else "medium"
        else:
            landmarks, bbox, overall_conf = {}, None, "low"
        frames.append({"index": i, "time": round(i / fps, 5), "file": f"./generated_rig/video_f7e82942/frames/{filename}", "bbox": bbox, "landmarks": landmarks, "confidence": "low", "foregroundConfidence": overall_conf, "measurement": "HSV chromatic foreground connected component; bbox and centroid measured from source frame"})

    # Contact sheet with bbox and trace markers, for audit rather than presentation.
    thumb_w, thumb_h, cols = 216, 120, 6
    rows = math.ceil(len(selected) / cols)
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 22)), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for n, i in enumerate(selected):
        m = measurements[i]
        im = Image.fromarray(cv2.cvtColor(raw_frames[i], cv2.COLOR_BGR2RGB)).resize((thumb_w, thumb_h))
        x, y = (n % cols) * thumb_w, (n // cols) * (thumb_h + 22)
        sheet.paste(im, (x, y + 22))
        draw.text((x + 4, y + 4), f"frame {i}  {i / fps:.3f}s", fill="#222222")
        if m["bbox"]:
            bx, by, bw, bh = m["bbox"]
            sx, sy = thumb_w / width, thumb_h / height
            draw.rectangle((x + bx * sx, y + 22 + by * sy, x + (bx + bw) * sx, y + 22 + (by + bh) * sy), outline="#d43f3a", width=1)
    sheet.save(out_dir / "contact_measured.jpg", quality=92)

    # Measured trajectories in source-pixel coordinates, with no interpolation across occlusion.
    plot = Image.new("RGB", (900, 580), "white")
    d = ImageDraw.Draw(plot)
    d.text((20, 10), "Measured screen-side silhouette candidates (source pixels; no near/far identity)", fill="black")
    colors = {"foregroundCentroid": "#444444", "screenLeftFootCandidate": "#cc3344", "screenRightFootCandidate": "#2266bb", "screenLeftHandCandidate": "#b06a18", "screenRightHandCandidate": "#16846a"}
    box = (60, 55, 840, 520)
    d.rectangle(box, outline="#999999")
    for name, color in colors.items():
        points = []
        for f in frames:
            p = f["landmarks"].get(name, {})
            if p.get("x") is not None and p.get("visible", True):
                px = box[0] + p["x"] / width * (box[2] - box[0])
                py = box[1] + p["y"] / height * (box[3] - box[1])
                points.append((px, py))
        for p in points:
            d.ellipse((p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2), fill=color)
        d.text((65 + list(colors).index(name) * 145, 545), name, fill=color)
    plot.save(out_dir / "trajectory_measured.png")
    # 人工解剖点按时间展示；空缺不连线，避免遮挡处虚构路径。
    manual_plot = Image.new("RGB", (1100, 650), "white")
    md = ImageDraw.Draw(manual_plot)
    md.text((20,10), "Manual source-pixel trajectories: LOW identity confidence; +/-12px review budget; gaps NOT interpolated", fill="black")
    names = ("hand_near", "hand_far", "foot_near", "foot_far")
    palette = ("#c33b50", "#3079b8", "#ba751b", "#16846a")
    for j,name in enumerate(names):
        px,py = 45+(j%2)*540,55+(j//2)*290
        md.text((px,py),name+" (x circles / y squares)",fill=palette[j])
        md.rectangle((px,py+25,px+480,py+235),outline="#cccccc")
        for frame in frames:
            point = frame["landmarks"].get(name,{})
            if point.get("visible"):
                x=px+frame["index"]/32*480
                for axis,shape in (("x","circle"),("y","square")):
                    value=point[axis]
                    y=py+235-(value-250)/300*210
                    if shape=="circle":
                        md.ellipse((x-4,y-4,x+4,y+4),outline=palette[j],width=2)
                    else:
                        md.rectangle((x-4,y-4,x+4,y+4),outline=palette[j],width=2)
                md.text((x-10,py+242),str(frame["index"]),fill="black")
        md.text((px,py+260),"horizontal: source frame 0..32; vertical: source value 250..550px",fill="#555555")
    manual_plot.save(out_dir/"trajectory_manual.png")

    reference = {"taskId": TASK_ID, "sourceUrl": SOURCE_URL, "sha256": digest, "width": width, "height": height, "fps": fps, "frameCount": frame_count, "duration": round(duration, 6), "characterId": None, "direction": "right_front_3q", "action": "walk", "cycle": cycle, "frames": frames, "motionEvidence": {"method": "OpenCV HSV foreground segmentation, largest connected component, per-frame bbox/centroid/area; screen-side lower-silhouette and arm-height extrema are heuristic candidates only", "sourceFrameCount": idx, "foregroundThreshold": "HSV saturation > 40 and value < 253; morphological close 5x5; largest component >= 1000px", "cycleSearch": "integer lag 8..44; median normalized bbox size and centroid discrepancy", "tracksFile": "./generated_rig/video_f7e82942/tracks.json", "visualizations": ["./generated_rig/video_f7e82942/contact_measured.jpg", "./generated_rig/video_f7e82942/trajectory_measured.png"], "animationFit": None}, "repairNeeds": [{"id": "video-redraw-separate-limbs", "partId": "legs-arms", "title": "按视频姿态重拆并补画四肢", "reason": "视频存在多种腿部交叉、伸展和遮挡姿态；旧静态拆件不能恢复被遮挡区域，需逐姿态补画并明确近远侧。", "evidenceTimes": [0.25, 0.333, 0.958, 2.708, 3.708, 4.333], "status": "needs_inpaint", "methodNeeded": "基于源帧人工标注近远侧后，在交叉/遮挡处做逐姿态重绘与分层拆件；此自动测量不等于修复"}], "limitations": ["轮廓分割是像素证据而非人体关键点标注；阴影、浅色边缘和衣物交界会影响掩膜。", "screenLeft/screenRight候选不能推断为near/far；手点是臂高轮廓极值，脚点是下部轮廓极值，均为low可信度且不代表解剖端点。", "未建立可靠逐肢光流身份对应，遮挡/交叉处不插值、不生成骨骼角度。", "未生成video_motion.json：现有视频证据不足以支持高可信度Spine关节绑定，原图部件仍待视频驱动的重拆与补画。", "方向和action walk按用户意图记录，不代表质量验收。"], "animationGenerated": False}
    reference["motionEvidence"]["screenCandidateCaveat"] = "脚候选搜索bbox下24%，仍可能命中投影/衣物；手候选搜索bbox高度60%..78%外轮廓，仍可能命中躯干。候选不是掌心/脚掌标注，禁止用于绑定。"
    reference["motionEvidence"]["visualizations"].append("./generated_rig/video_f7e82942/trajectory_manual.png")
    reference["schemaVersion"] = 1
    reference["coordinateSpace"] = {"origin": "top_left", "x": "right", "y": "down", "units": "source_pixels", "bboxFormat": "x_y_width_height", "timeUnit": "seconds", "durationConvention": "frameCount/fps; last sample time=(frameCount-1)/fps"}
    reference["motionEvidence"]["cycleSearch"] = "integer lag 8..44 (minimum 65% valid pairs); median lower-body normalized silhouette 1-IoU + median bbox/centroid discrepancy"
    reference["motionEvidence"]["cycleCandidates"] = [{"lagFrames": l, "duration": round(l/fps, 6), "score": round(e, 6), "validPairs": n} for e, l, n in candidates[:10]]
    reference["motionEvidence"]["manualReview"] = {"frames": list(MANUAL), "coordinateUncertaintyPx": 12, "identityConfidence": "low", "method": "源帧坐标网格人工审阅掌心/脚掌中心；独立于屏幕侧轮廓候选", "occlusionHandling": "缺失记录null，不插值、不外推、不假定反相", "reviewArtifact": "./generated_rig/video_f7e82942/inspection_grid.jpg"}
    reference["motionEvidence"]["qualityMetrics"] = {"decodedFrameCount": idx, "segmentationSuccessRate": len(valid)/idx, "sampleCount": len(frames), "manualFrameCount": len(MANUAL), "anatomicalHighConfidencePointCount": 0, "bboxRangePx": {"width": [min(m["bbox"][2] for m in valid), max(m["bbox"][2] for m in valid)], "height": [min(m["bbox"][3] for m in valid), max(m["bbox"][3] for m in valid)]}, "centroidRangePx": {"x": [round(min(m["centroid"][0] for m in valid),2), round(max(m["centroid"][0] for m in valid),2)], "y": [round(min(m["centroid"][1] for m in valid),2), round(max(m["centroid"][1] for m in valid),2)]}, "segmentationAccuracy": "unvalidated against ground-truth masks; saturation mask includes shadow and excludes some pale pixels", "fitResidualPx": None, "fitResidualReason": "未拟合Spine动作；不得将候选周期组合误差当作关键点拟合残差"}
    reference["repairNeeds"] = [
        {"id": "near-leg-crossing", "partId": "leg_near", "title": "近侧腿交叉轮廓重拆", "reason": "0/16/32帧前层腿跨越另一腿，静态拆件无法覆盖脚掌透视与轮廓变形。近侧身份仍需人工确认。", "evidenceTimes": [0.0, 0.66667, 1.33333], "evidenceFrames": [0,16,32], "status": "needs_inpaint", "methodNeeded": "确认近侧身份后按视频交叉/伸展姿态重拆并补画大腿内缘及脚掌"},
        {"id": "far-leg-occlusion", "partId": "leg_far", "title": "远侧腿被遮挡区域补画", "reason": "0/16/32帧远侧脚无法独立标注，8/24帧展开后才可见双脚，缺失轮廓不能靠轨迹插值恢复。", "evidenceTimes": [0.0,0.33333,0.66667,1.0,1.33333], "evidenceFrames": [0,8,16,24,32], "status": "needs_inpaint", "methodNeeded": "以展开帧为形状依据重建遮挡大腿和脚掌，人工检查遮挡层序"},
        {"id": "near-arm-forward", "partId": "arm_near", "title": "近侧手臂前摆姿态补画", "reason": "0/16/32帧左肩外侧可见臂，8/24帧手掌前摆至躯干前方；旋转单张侧臂不足以表达掌形与自遮挡。", "evidenceTimes": [0.0,0.33333,0.66667,1.0], "evidenceFrames": [0,8,16,24], "status": "needs_inpaint", "methodNeeded": "分离上臂/前臂/手掌并按视频前摆帧重绘连接区域"},
        {"id": "far-arm-hidden", "partId": "arm_far", "title": "远侧手臂隐藏轮廓补画", "reason": "8/24帧远侧手无法与躯干分离，0/16/32帧伸出。不能使用屏幕右极值当作远侧手掌中心。", "evidenceTimes": [0.0,0.33333,0.66667,1.0,1.33333], "evidenceFrames": [0,8,16,24,32], "status": "needs_inpaint", "methodNeeded": "依据伸出姿态补齐隐藏臂、肩接口与躯干底图，重新确认draw order"},
        {"id": "torso-pose-deformation", "partId": "body", "title": "躯干与裆部遮挡底图重建", "reason": "视频躯干透视与胯部轮廓随步态改变；分割只给出可见像素，不包含臂腿下方完整底图。", "evidenceTimes": [0.33333,1.0,2.70833,3.70833], "evidenceFrames": [8,24,65,89], "status": "needs_inpaint", "methodNeeded": "视频姿态分层重拆、遮挡底图补画与必要的网格变形；未执行修复"}
    ]
    reference["limitations"].append("前景重心是饱和度掩膜的像素质心，不是人体质量中心或骨盆关节；掩膜含投影，不能直接绑定root。")
    reference["limitations"].append("人工审阅帧的near/far仅为低可信度身份假设，脚掌/掌心点误差预算±12px，未验证所有中间帧。")
    # 保存可重现的人工审阅网格，确保脚本单独重跑也能提供坐标证据。
    grid = Image.new("RGB", (1900,1820), "#dddddd")
    gd = ImageDraw.Draw(grid)
    for j, i in enumerate(range(0,34,2)):
        im = Image.fromarray(cv2.cvtColor(raw_frames[i],cv2.COLOR_BGR2RGB)).crop((260,40,620,475))
        ad = ImageDraw.Draw(im)
        for x in range(280,620,40):
            ad.line((x-260,0,x-260,435),fill="#bbbbbb")
            ad.text((x-258,0),str(x),fill="black")
        for y in range(80,475,40):
            ad.line((0,y-40,360,y-40),fill="#bbbbbb")
            ad.text((0,y-38),str(y),fill="black")
        if i in MANUAL:
            for name, xy in MANUAL[i].items():
                if xy is not None:
                    x,y = xy[0]-260,xy[1]-40
                    ad.ellipse((x-4,y-4,x+4,y+4),outline="#ff00aa",width=2)
                    ad.text((x+5,y),name,fill="#cc0077")
        x,y = j%5*380,j//5*455
        grid.paste(im,(x,y+20))
        gd.text((x,y),f"source frame {i}",fill="black")
    grid.save(out_dir/"inspection_grid.jpg",quality=94)
    (out_dir / "reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "tracks.json").write_text(json.dumps({"coordinateSpace": "source pixels, origin top-left", "tracks": tracks, "schemaVersion": 1, "rawMeasurements": measurements, "manualFrames": list(MANUAL), "note": "屏幕侧候选是轮廓极值；near/far人工点身份低可信，缺失为null且不插值；rawMeasurements为107帧bbox/掩膜质心测量。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sha256": digest, "dimensions": [width, height], "fps": fps, "frameCount": frame_count, "duration": round(duration, 6), "cycle": cycle, "sampledFrames": len(frames), "animationGenerated": False, "output": str(out_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
