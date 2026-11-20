from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "generated_rig/right_front_walk"
OUT = ROOT / "generated_rig/video_f7e82942/stable_parts_v1"
ORDER = ["head", "body", "shorts", "arm_near", "arm_far", "leg_near", "leg_far"]
# 根据原图及[328,510,486,604]六倍放大图手描，仅保留可见衣物。
SHORTS_POLYGON = [
    (357, 532), (366, 535), (382, 538), (398, 539), (415, 538),
    (431, 535), (447, 531), (459, 526), (467, 520), (469, 519),
    (471, 522), (472, 528), (473, 536), (475, 545), (466, 552),
    (456, 561), (445, 571), (434, 580), (422, 587), (412, 591),
    (404, 592), (400, 584), (392, 577), (382, 570), (371, 565),
    (358, 561), (345, 559), (350, 551), (354, 541),
]
DETAIL_BOX = (328, 510, 486, 604)
META = {
    "head": (
        "头部",
        "来自旧originalFile原始可见裁片；仅当前视角头部，颈部切口与遮挡面未完整提供。",
        ["复核颈部切口和毛发边缘；隐藏侧头部及颈部连接未补全，不能视为完整绑定头部。"],
        "Visible head only; neck/hidden surfaces unverified.",
    ),
    "body": (
        "躯干",
        "从旧original混合件仅保留裤腰以上可见躯干，原RGBA不改；已生成Image2 v5供体仅在原姿态被不透明上层遮挡的局部补足搭接。",
        ["肩颈、腋下和腰髋仅局部搭接，非完整隐藏结构；接缝颜色、动态露缝和换装覆盖仍待验收。"],
        "Source torso + local AI donor overlap; dynamic untested.",
    ),
    "shorts": (
        "短裤",
        "仅用原图可见短裤像素按手描多边形裁出透明轮廓；腰线、手臂遮挡边和腿口仍是粗边界待审。",
        ["逐像素审阅裤腰、近侧手臂遮挡边、两侧裤口及裆部描边；被手臂与身体遮挡的衣物未补全。"],
        "Coarse clothing outline; waist/leg openings need review.",
    ),
    "arm_near": (
        "近屏幕层手臂（暂定）",
        "保留original可见手臂裁片，并加入原图左上缺口沿手臂遮挡轮廓边线的人工归属候选；未获正式美术批准，肩根隐藏面仍不完整。",
        ["缺肩根与腋下遮挡面及旋转重叠余量；需复核斜切口，未补画。"],
        "Visible arm only; shoulder/armpit and overlap missing.",
    ),
    "arm_far": (
        "远屏幕层手臂（暂定）",
        "仅复制original可见窄条手臂；内侧与肩根被躯干遮挡，非完整手臂。",
        ["缺肩根、内侧手臂与腋下隐藏轮廓及旋转重叠余量，未补画。"],
        "Visible arm sliver; inner arm/shoulder missing.",
    ),
    "leg_near": (
        "近屏幕层腿（暂定）",
        "保留original可见腿裁片，并加入原图左下缺口的人工归属候选；髋根被短裤遮挡，旧分区切口可能带裤口描边，不等于完整裸腿，未获正式美术批准。",
        ["缺短裤下的髋根和上腿隐藏连接；需审阅裤口描边归属，未使用旧补底或延伸像素。"],
        "Visible leg only; hip root missing; inspect clothing edge.",
    ),
    "leg_far": (
        "远屏幕层腿（暂定）",
        "保留original可见腿裁片，并加入原图右侧缺口的人工归属候选；髋根与内侧上腿被短裤和近侧腿遮挡，旧切口可能带裤口描边，未获正式美术批准。",
        ["缺髋根、内侧上腿与重叠余量；需审阅裤口描边归属，未使用旧补底或延伸像素。"],
        "Visible leg only; hip/inner upper leg missing.",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_check(path: Path, bbox: list[int], source: np.ndarray) -> dict:
    with Image.open(path) as im:
        if im.mode != "RGBA":
            raise ValueError(f"非RGBA图像：{path}")
        data = np.array(im)
    x0, y0, x1, y1 = bbox
    if data.shape != (y1 - y0, x1 - x0, 4):
        raise ValueError(f"裁切边界尺寸不匹配：{path}")
    original = source[y0:y1, x0:x1]
    visible = data[:, :, 3] > 0
    if not visible.any() or not (data[:, :, 3] == 0).any():
        raise ValueError(f"缺少可见像素或透明轮廓：{path}")
    rgb_errors = int(np.count_nonzero(np.any(data[:, :, :3] != original[:, :, :3], axis=2) & visible))
    alpha_errors = int(np.count_nonzero((data[:, :, 3] != original[:, :, 3]) & visible))
    if rgb_errors or alpha_errors:
        raise ValueError(f"可见RGB或alpha并非原图原像素：{path}")
    return {
        "visiblePixels": int(visible.sum()),
        "transparentPixels": int((~visible).sum()),
        "partialAlphaPixels": int(((data[:, :, 3] > 0) & (data[:, :, 3] < 255)).sum()),
        "visibleRgbMismatchPixels": rgb_errors,
        "visibleAlphaMismatchPixels": alpha_errors,
        "newVisiblePixelsOutsideSource": int((visible & (original[:, :, 3] == 0)).sum()),
    }


def checker(size: tuple[int, int], cell: int = 12) -> Image.Image:
    im = Image.new("RGBA", size, "#edf0f4")
    draw = ImageDraw.Draw(im)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#cbd2dc")
    return im


def font(size: int):
    path = Path("C:/Windows/Fonts/arial.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def make_review(parts: list[dict]) -> None:
    sheet = Image.new("RGB", (1280, 1030), "#f3f5f8")
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 12), "STABLE PARTS v1 - WORK IN PROGRESS / NOT A RIG", font=font(23), fill="#172033")
    draw.text((20, 46), "Body: source torso + AI overlap. All hiddenComplete=false / approvedForBinding=false. Not a rig.", font=font(17), fill="#4b5668")
    for i, part in enumerate(parts):
        x, y = (i % 4) * 320 + 10, 90 + (i // 4) * 460
        draw.text((x + 10, y), part["id"], font=font(22), fill="#172033")
        draw.text((x + 10, y + 29), part["status"], font=font(12), fill="#88570b")
        panel = checker((300, 295))
        if part["file"]:
            im = Image.open(OUT / part["file"]).convert("RGBA")
            im.thumbnail((280, 275), Image.Resampling.NEAREST)
            panel.alpha_composite(im, ((300 - im.width) // 2, (295 - im.height) // 2))
        else:
            ImageDraw.Draw(panel).text((56, 125), "NO BODY ASSET", font=font(22), fill="#a12b2b")
        sheet.paste(panel.convert("RGB"), (x, y + 53))
        words = META[part["id"]][3].split()
        lines, line = [], ""
        for word in words:
            test = f"{line} {word}".strip()
            if draw.textlength(test, font=font(16)) > 288:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
        for j, text in enumerate(lines):
            draw.text((x + 5, y + 361 + j * 22), text, font=font(16), fill="#364152")
    x, y = 980, 560
    draw.text((x, y), "NOT READY FOR BINDING", font=font(17), fill="#a12b2b")
    draw.text((x, y + 36), "near/far = provisional", font=font(16), fill="#364152")
    draw.text((x, y + 60), "screen-depth labels only", font=font(16), fill="#364152")
    draw.text((x, y + 96), "Anatomical left/right: unknown", font=font(15), fill="#364152")
    draw.text((x, y + 132), "characterId: null", font=font(17), fill="#364152")
    sheet.save(OUT / "review.png")


def make_shorts_review(source: Image.Image, part: dict) -> None:
    detail = source.crop(DETAIL_BOX)
    detail.resize((948, 564), Image.Resampling.NEAREST).save(OUT / "source_shorts_detail.png")
    local = Image.new("RGBA", detail.size)
    local.alpha_composite(Image.open(OUT / part["file"]).convert("RGBA"),
                          (part["bbox"][0] - DETAIL_BOX[0], part["bbox"][1] - DETAIL_BOX[1]))
    panel = checker((632, 376), 16)
    panel.alpha_composite(local.resize(panel.size, Image.Resampling.NEAREST))
    sheet = Image.new("RGB", (1294, 460), "#f3f5f8")
    sheet.paste(detail.resize((632, 376), Image.Resampling.NEAREST).convert("RGB"), (10, 48))
    sheet.paste(panel.convert("RGB"), (652, 48))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 10), "SOURCE: [328,510,486,604] - 4x", font=font(21), fill="#172033")
    draw.text((652, 10), "SHORTS: source pixels / coarse outline - 4x", font=font(21), fill="#172033")
    draw.text((10, 431), "Review required: waist, occluding arm edge, leg openings and crotch. No hidden clothing generated.", font=font(18), fill="#88570b")
    sheet.save(OUT / "shorts_review.png")


def build_body(source: np.ndarray, old_parts: dict) -> tuple[dict, dict, dict]:
    """保留可见躯干，用已有供体补遮挡搭接；源图边线归属均为未验收人工候选。"""
    record = old_parts["body"]
    old = np.zeros_like(source)
    x0, y0, x1, y1 = record["originalCrop"]
    old[y0:y1, x0:x1] = np.array(Image.open(OLD / record["originalFile"]).convert("RGBA"))
    yy, xx = np.indices(source.shape[:2])
    waist = [(338, 526), *SHORTS_POLYGON[:11], (478, 514)]
    waist.sort()
    boundary = np.interp(xx, [p[0] for p in waist], [p[1] for p in waist])
    visible = (old[:, :, 3] > 0) & (yy < boundary)
    if not np.array_equal(old[visible], source[visible]):
        raise ValueError("躯干原可见RGBA与源图不符")
    occluders = np.zeros_like(visible)
    layers = {}
    for name in ["head", "arm_near", "arm_far", "shorts", "leg_near", "leg_far"]:
        layer = np.zeros_like(source)
        if name == "shorts":
            image = Image.open(OUT / "shorts.png").convert("RGBA")
            bounds = image.getchannel("A").getbbox()
            # Independent shorts crop is generated above with the same polygon.
            mask_image = Image.new("L", (768, 768))
            ImageDraw.Draw(mask_image).polygon(SHORTS_POLYGON, fill=255)
            keep = np.array(mask_image) > 0
            layer[keep] = source[keep]
        else:
            p = old_parts[name]
            a, b, c, d = p["originalCrop"]
            layer[b:d, a:c] = np.array(Image.open(OLD / p["originalFile"]).convert("RGBA"))
        layers[name] = layer
        occluders |= layer[:, :, 3] == 255
    safely_hidden = cv2.erode(occluders.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    donor_path = OUT.parent / "image2_repairs/body_candidate_v5.png"
    if sha256(donor_path) != "f2bf1a8c97d669ba7f0a11d24e5d4f5bda696521886e5701f52ebfa1019ae2c6":
        raise ValueError("Image2供体SHA不符")
    donor = np.array(Image.open(donor_path).convert("RGBA"))
    donor[donor[:, :, 3] < 8] = 0
    donor_image = Image.fromarray(donor).crop((254, 196, 1029, 1096))
    donor_image = donor_image.resize((182, 211), Image.Resampling.LANCZOS)
    mapped = np.zeros_like(source)
    mapped[407:618, 316:498] = np.array(donor_image)
    distance = cv2.distanceTransform((~visible).astype(np.uint8), cv2.DIST_L2, 5)
    zone = (xx >= 328) & (xx <= 483) & (yy >= 416) & (yy <= 587)
    repair = zone & safely_hidden & ~visible & (distance <= 24) & (mapped[:, :, 3] >= 240)
    count, labels = cv2.connectedComponents((visible | repair).astype(np.uint8))
    connected = np.unique(labels[visible])
    repair &= np.isin(labels, connected[connected != 0])
    if not visible.any() or not repair.any():
        raise ValueError("躯干可见或局部补画为空")
    local = visible & (source[:, :, 3] >= 240)
    target = np.median(source[local, :3], axis=0)
    donor_target = np.median(mapped[local & (mapped[:, :, 3] >= 240), :3], axis=0)
    rgb = np.clip(mapped[:, :, :3].astype(float) + target - donor_target, 0, 255).astype(np.uint8)
    body = np.zeros_like(source)
    body[visible] = source[visible]
    body[repair, :3] = rgb[repair]
    body[repair, 3] = 255
    support = body[:, :, 3] > 0
    for layer in layers.values():
        support |= layer[:, :, 3] > 0
    gap = (source[:, :, 3] > 0) & ~support
    old_support = old[:, :, 3] > 0
    if int(gap.sum()) != 657 or np.any(gap & ~old_support):
        raise ValueError("源图缺口必须恰为657像素且全部位于旧混合body支持内")
    if not np.array_equal(old[gap], source[gap]):
        raise ValueError("缺口处旧混合body与同坐标源图RGBA不符")
    regions = {
        "arm_near": gap & (yy < 561) & (xx < 420),
        "leg_near": gap & (yy >= 561) & (xx < 420),
        "leg_far": gap & (xx >= 420),
    }
    expected = {"arm_near": 100, "leg_near": 488, "leg_far": 69}
    assignment_coverage = np.sum(list(regions.values()), axis=0)
    if np.any(assignment_coverage > 1) or not np.array_equal(assignment_coverage > 0, gap):
        raise ValueError("边界候选mask重叠或未完整覆盖缺口")
    for name, mask in regions.items():
        if int(mask.sum()) != expected[name] or np.any(mask & support):
            raise ValueError(f"边界候选像素/原支持检查失败：{name}={int(mask.sum())}")
    boundary = {}
    for name, mask in regions.items():
        added = int(mask.sum())
        layers[name][mask] = source[mask]
        out_image = Image.fromarray(layers[name])
        out_bbox = list(out_image.getchannel("A").getbbox())
        out_path = OUT / f"{name}.png"
        out_image.crop(out_bbox).save(out_path)
        boundary[name] = {"file": out_path.name, "sha256": sha256(out_path), "bbox": out_bbox,
                          "width": out_bbox[2] - out_bbox[0], "height": out_bbox[3] - out_bbox[1],
                          "addedPixelCount": added}
    if int(gap.sum()) != 657 or int(np.logical_or.reduce(list(regions.values())).sum()) != 657:
        raise ValueError("源图可见缺口总数或分区覆盖数不为657")
    image = Image.fromarray(body)
    bbox = list(image.getchannel("A").getbbox())
    image.crop(bbox).save(OUT / "body.png")
    for name, mask in [("body_visible_mask.png", visible), ("body_repair_mask.png", repair)]:
        Image.fromarray((mask * 255).astype(np.uint8)).save(OUT / name)
    counts = {"visiblePixels": int(visible.sum()), "repairPixels": int(repair.sum()),
              "visibleRgbaMismatchPixels": int(np.any(body[visible] != source[visible], axis=1).sum()),
              "repairOutsideOpaqueOccluders": int((repair & ~safely_hidden).sum())}
    if counts["visibleRgbaMismatchPixels"] or counts["repairOutsideOpaqueOccluders"]:
        raise ValueError("躯干可见像素或遮挡域检查失败")
    if np.any(visible & repair) or not np.array_equal(body[:, :, 3] > 0, visible | repair):
        raise ValueError("body可见/补画mask重叠或alpha支持并集不符")
    if np.any(repair & (mapped[:, :, 3] < 240)):
        raise ValueError("补画像素不满足供体alpha阈值")
    upper_opaque = np.logical_or.reduce([layers[name][:, :, 3] == 255
                                       for name in ["shorts", "arm_far", "arm_near", "head"]])
    upper_safe = cv2.erode(upper_opaque.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if np.any(repair & ~upper_safe):
        raise ValueError("正确层序下补画未完全处于不透明上层安全遮挡域")
    assembly = Image.new("RGBA", (768, 768))
    for name in ["leg_far", "leg_near"]:
        assembly.alpha_composite(Image.fromarray(layers[name]))
    assembly.alpha_composite(Image.fromarray(body))
    for name in ["shorts", "arm_far", "arm_near", "head"]:
        assembly.alpha_composite(Image.fromarray(layers[name]))
    assembled = np.array(assembly)
    source_visible = source[:, :, 3] > 0
    rgba_mismatch = int(np.any(assembled[source_visible] != source[source_visible], axis=1).sum())
    uncovered = source_visible & (assembled[:, :, 3] == 0)
    candidate_cover = np.logical_or.reduce(list(regions.values()))
    revised_support = (body[:, :, 3] > 0) | np.logical_or.reduce([layer[:, :, 3] > 0 for layer in layers.values()])
    counts.update(sourceVisibleAssemblyRgbaMismatchPixels=rgba_mismatch,
                  sourceForegroundUncoveredPixels=int(uncovered.sum()),
                  sourceForegroundNotCoveredByCandidatesPixels=int((uncovered & ~candidate_cover).sum()),
                  alphaUnionMismatchPixels=int(np.count_nonzero(revised_support != source_visible)),
                  boundaryMaskOverlapPixels=int(np.count_nonzero(assignment_coverage > 1)),
                  bodyMaskOverlapPixels=int(np.count_nonzero(visible & repair)),
                  repairOutsideFinalUpperOpaqueSafeDomain=int(np.count_nonzero(repair & ~upper_safe)))
    if rgba_mismatch or uncovered.any() or counts["alphaUnionMismatchPixels"]:
        raise ValueError(f"源图可见组装RGBA/前景覆盖/alpha支持并集检查失败：{counts}")
    # 分别展示原图、实际候选组装及body；原图绝不充当遮盖层。
    review = Image.new("RGB", (1536, 600), "#f3f5f8")
    draw = ImageDraw.Draw(review)
    tinted = body.copy()
    tinted[repair] = (194, 55, 174, 255)
    panels = [("SOURCE", Image.fromarray(source)), ("CANDIDATE ASSEMBLY", assembly),
              ("BODY / MAGENTA = AI OVERLAP", Image.fromarray(tinted))]
    for i, (label, panel) in enumerate(panels):
        draw.text((i * 512 + 14, 14), label, font=font(18), fill="#172033")
        panel = panel.resize((512, 512), Image.Resampling.LANCZOS)
        review.paste(panel, (i * 512, 45), panel)
    draw.text((14, 567), "VISIBLE RGBA PRESERVED. LOCAL OVERLAP ONLY. NOT BOUND / NOT DYNAMICALLY APPROVED.", font=font(19), fill="#a12b2b")
    review.save(OUT / "body_assembly_review.png")
    details = Image.new("RGB", (1440, 510), "#f3f5f8")
    detail_draw = ImageDraw.Draw(details)
    for i, (label, panel) in enumerate([("SOURCE", Image.fromarray(source)), ("ASSEMBLY", assembly), ("BODY ONLY + MASK", Image.fromarray(tinted))]):
        crop = panel.crop((305, 410, 510, 610)).resize((451, 440), Image.Resampling.NEAREST)
        detail_draw.text((i * 480 + 10, 10), label, font=font(19), fill="#172033")
        details.paste(crop, (i * 480 + 10, 45), crop)
    details.save(OUT / "body_interfaces_review.png")
    label, reason, repairs, _ = META["body"]
    part = {"id": "body", "label": label, "file": "body.png", "sha256": sha256(OUT / "body.png"),
            "bbox": bbox, "width": bbox[2]-bbox[0], "height": bbox[3]-bbox[1],
            "status": "source_preserved_ai_overlap_candidate", "hiddenComplete": False,
            "approvedForBinding": False, "sourcePixelOnly": False, "reason": reason,
            "repairNeeded": repairs, "evidenceFrames": [],
            "source": {"method": "source_visible_preserved_ai_donor_hidden_overlap",
                       "visibleMaskFile": "body_visible_mask.png", "repairMaskFile": "body_repair_mask.png",
                       "donor": {"file": "../image2_repairs/body_candidate_v5.png", "sha256": sha256(donor_path)},
                       "counts": counts, "waistCutPolyline": waist,
                       "donorMapping": {"crop": [254, 196, 1029, 1096], "size": [182, 211], "topLeft": [316, 407], "alphaCutoff": 8},
                       "localColorMedianShift": (target - donor_target).tolist(),
                       "geometry": "manual waist cut + distance<=24px + eroded opaque occluders; not hidden anatomy reconstruction"}}
    return part, counts, boundary


def main() -> None:
    source_path = OLD / "source768.png"
    source = Image.open(source_path).convert("RGBA")
    if source.size != (768, 768):
        raise ValueError("原图必须为768x768")
    source_data = np.array(source)
    old_manifest_path = OLD / "manifest.json"
    old_parts = {p["id"]: p for p in json.loads(old_manifest_path.read_text(encoding="utf-8"))["parts"]}
    OUT.mkdir(parents=True, exist_ok=True)
    preserved_hashes = {name: sha256(OUT / f"{name}.png")
                        for name in ["body", "shorts", "head", "arm_far"]
                        if (OUT / f"{name}.png").exists()}
    shutil.copyfile(source_path, OUT / "source_reference.png")
    parts, checks = [], {}
    for name in ORDER:
        label, reason, repair, _ = META[name]
        part = {
            "id": name, "label": label, "file": None, "sha256": None,
            "width": 0, "height": 0, "bbox": None,
            "status": "missing_hidden_body_needed" if name == "body" else (
                "source_visible_candidate" if name == "head" else (
                    "coarse_clothing_candidate" if name == "shorts" else "visible_incomplete_candidate")),
            "hiddenComplete": False, "approvedForBinding": False, "sourcePixelOnly": True,
            "reason": reason, "repairNeeded": repair, "evidenceFrames": [],
        }
        if name == "body":
            parts.append(part)
            continue
        path = OUT / f"{name}.png"
        if name == "shorts":
            mask = Image.new("L", source.size, 0)
            ImageDraw.Draw(mask).polygon(SHORTS_POLYGON, fill=255)
            keep = (np.array(mask) == 255) & (source_data[:, :, 3] > 0)
            layer = np.zeros_like(source_data)
            layer[keep] = source_data[keep]
            im = Image.fromarray(layer)
            bbox = list(im.getchannel("A").getbbox())
            im.crop(bbox).save(path)
            part["source"] = {"file": "../../right_front_walk/source768.png", "method": "manual_binary_polygon_visible_pixels", "polygon": [list(p) for p in SHORTS_POLYGON]}
        else:
            old = old_parts[name]
            original = OLD / old["originalFile"]
            if not original.resolve().is_relative_to((OLD / "parts/original").resolve()):
                raise ValueError("仅允许旧parts/original可见裁片")
            shutil.copyfile(original, path)
            bbox = old["originalCrop"]
            if sha256(path) != sha256(original):
                raise ValueError("original裁片复制校验失败")
            part["source"] = {"file": f"../../right_front_walk/{old['originalFile']}", "sha256": sha256(original), "method": "byte_exact_original_visible_copy"}
        part.update(file=path.name, sha256=sha256(path), width=bbox[2] - bbox[0], height=bbox[3] - bbox[1], bbox=bbox)
        checks[name] = source_check(path, bbox, source_data)
        parts.append(part)
    body_part, body_counts, boundary = build_body(source_data, old_parts)
    parts[ORDER.index("body")] = body_part
    checks["body"] = body_counts
    for name, record in boundary.items():
        part = parts[ORDER.index(name)]
        part.update(file=record["file"], sha256=record["sha256"], bbox=record["bbox"], width=record["width"], height=record["height"])
        part["status"] = "source_visible_boundary_reassignment"
        part["source"] = {
            "file": "../../right_front_walk/source768.png",
            "sha256": sha256(source_path),
            "method": "source_visible_boundary_reassignment",
            "baseOriginalFile": f"../../right_front_walk/{old_parts[name]['originalFile']}",
            "baseOriginalSha256": sha256(OLD / old_parts[name]["originalFile"]),
            "baseOriginalBbox": old_parts[name]["originalCrop"],
            "oldMixedBodyFile": f"../../right_front_walk/{old_parts['body']['originalFile']}",
            "oldMixedBodySha256": sha256(OLD / old_parts["body"]["originalFile"]),
            "oldMixedBodyBbox": old_parts["body"]["originalCrop"],
            "supportCondition": "source alpha>0 and all current layers alpha==0 and old mixed body alpha>0",
            "assignmentBasis": "按已查看原图提出的人工可见边线归属候选；arm_near沿手臂遮挡轮廓边线；不使用最近距离推断语义。", 
            "sourceCoordinateCondition": {"arm_near": "y<561 and x<420", "leg_near": "y>=561 and x<420", "leg_far": "x>=420"}[name],
            "addedPixelCount": record["addedPixelCount"],
            "boundaryAssignmentApproved": False,
        }
        checks[name] = source_check(OUT / record["file"], record["bbox"], source_data)
    for name, original_hash in preserved_hashes.items():
        if sha256(OUT / f"{name}.png") != original_hash:
            raise ValueError(f"要求保持不变的PNG哈希发生变化：{name}")
    make_review(parts)
    make_shorts_review(source, next(p for p in parts if p["id"] == "shorts"))
    assets = []
    for filename, role in [
        ("source_reference.png", "source_reference"), ("review.png", "candidate_contact_sheet"),
        ("source_shorts_detail.png", "source_shorts_zoom_nearest_6x"),
        ("shorts_review.png", "shorts_source_comparison_nearest_4x"),
        ("body_visible_mask.png", "body_original_visible_mask"),
        ("body_repair_mask.png", "body_ai_overlap_mask"),
        ("body_assembly_review.png", "body_static_assembly_review"),
        ("body_interfaces_review.png", "body_interface_detail_review"),
    ]:
        with Image.open(OUT / filename) as image:
            width, height = image.size
        assets.append({"file": filename, "sha256": sha256(OUT / filename), "width": width, "height": height, "role": role})
    manifest = {
        "schemaVersion": 2,
        "taskId": "comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa",
        "sourceVideoSha256": "8fc0f8406d6a258640b65d34c5ad7fb0e35f231131d7eec945781dd9d93343e5",
        "characterId": None, "promotedToRuntime": False,
        "status": "stable_parts_work_in_progress_not_rig", "direction": "right_front_3q",
        "sourceImage": {"file": "../../right_front_walk/source768.png", "sha256": sha256(source_path), "width": 768, "height": 768},
        "sourceReference": next(a for a in assets if a["role"] == "source_reference"),
        "review": next(a for a in assets if a["role"] == "candidate_contact_sheet"),
        "bodyReview": next(a for a in assets if a["role"] == "body_static_assembly_review"),
        "assets": assets, "parts": parts,
        "boundaryReview": {
            "count": 3, "gapPixelCountBefore": 657, "addedPixelCount": 657,
            "assignments": {name: record["addedPixelCount"] for name, record in boundary.items()},
            "boundaryAssignmentApproved": False, "status": "pending_manual_art_review",
            "sourceVisibleAssemblyRgbaMismatchPixels": body_counts["sourceVisibleAssemblyRgbaMismatchPixels"],
            "sourceForegroundUncoveredPixels": body_counts["sourceForegroundUncoveredPixels"],
            "sourceForegroundNotCoveredByCandidatesPixels": body_counts["sourceForegroundNotCoveredByCandidatesPixels"],
            "note": "按已查看原图的可见区域及边线提出人工候选归属；不以最近距离推断语义，未获正式美术批准。新生成review由主线程视觉审阅；该记录不是新asset。",
        },
        "assemblyLayerOrder": ["leg_far", "leg_near", "body", "shorts", "arm_far", "arm_near", "head"],
        "bboxConvention": "源图像素坐标，左上包含、右下不包含：[x0,y0,x1,y1]；缺件为null，尺寸为0。",
        "layerSemantics": {"nearFar": "仅当前静态视角暂定屏幕层，不代表解剖左右或已验证视频身份。", "anatomicalLeftRight": "unknown"},
        "provenance": {
            "oldManifest": {"file": "../../right_front_walk/manifest.json", "sha256": sha256(old_manifest_path)},
            "sourceVideoHashRole": "任务引用标识；本脚本未读取或校验视频，不据此声称原图角色归属。",
            "evidenceFrames": "全部为空：本批候选来自静态原图，不捏造视频帧证据。",
            "methods": ["head和arm_far逐字节复制旧originalFile；arm_near及两腿保留原裁片并加入原图可见边界像素的人工归属候选；拒绝旧runtime与补底裁片。", "短裤二值多边形仅裁出原图RGBA，未重采样或改变保留像素透明度。", "body保留裤腰以上旧original可见RGBA；已有Image2 v5纹理仅用于不透明上层遮挡内的局部搭接，做色彩中位数平移；没有新生图、程序inpaint或运行时提升。", "review及放大参考仅供查看，不是候选部件的像素来源。"],
            "visualReview": {
                "status": "coarse_candidate_pending_art_review", "sourceDetailBox": list(DETAIL_BOX),
                "inspectedWith": "ViewImage", "inspectedFiles": ["source_shorts_detail.png", "shorts_review.png", "review.png"],
                "observations": [
                    "已实际查看完整原图、短裤六倍放大参考、四倍左右对照图及七件审阅图。",
                    "短裤为沿腰线、手臂遮挡边、两侧裤口和裆部的独立透明轮廓，不是带手臂皮肤的矩形截图。",
                    "放大可见多边形边界有锯齿及描边裁切近似，仍需美术逐像素审阅；不据此断言边缘完全准确。",
                    "头部颈下有原分区残片，四肢有明显切口，腿部带原裤口附近描边；均未修补。",
                ],
                "shortsAcceptedForBinding": False,
            },
        },
        "checks": {"parts": checks, "copiedOriginalFilesByteExact": False, "copiedOriginalPartIds": ["head", "arm_far"], "sourceVisibleCandidateRgbaExact": True, "sourceReferenceByteExact": sha256(source_path) == sha256(OUT / "source_reference.png"), "allOriginalVisiblePixelsMatchSourceRgba": True, "aiDonorOverlapPixels": body_counts["repairPixels"], "newAiGenerationThisBuild": False, "bindingValidated": False, "boundaryReview": {"count": 3, "addedPixelCount": 657, "assignments": {name: record["addedPixelCount"] for name, record in boundary.items()}, "status": "pending_manual_art_review", "note": "三处是按原图可见边线提出的人工候选归属，不是正式美术批准，也不是新asset。"}, "maskNonOverlapping": True, "alphaUnionValidated": True, "donorValidated": True},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 写盘后重新打开并核对每张输出图及来源，哈希供浏览器消费。
    saved = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    for record in saved["parts"] + saved["assets"]:
        if record["file"] is not None and sha256(OUT / record["file"]) != record["sha256"]:
            raise ValueError(f"输出sha256校验失败：{record['file']}")
    for part in saved["parts"]:
        if part["file"] is not None and part["id"] != "body":
            source_check(OUT / part["file"], part["bbox"], source_data)
    print(json.dumps({"output": str(OUT), "logicalParts": len(parts), "imageCandidates": 7, "bodyFile": "body.png", "pixelChecks": checks, "promotedToRuntime": False, "bindingValidated": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
