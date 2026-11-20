from __future__ import annotations

import hashlib
import json
import math
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"I:\彩虹AI\design\AI玩具_design\美术资源\棉花娃娃\基础角色-测试\右前¾侧图层.png")
OUT = ROOT / "generated_rig" / "right_front_walk"
PARTS = OUT / "parts"
CANVAS = (768, 768)
STATUS = "已提取/程序补底·待美术精修"
DURATION = 0.8
KEY_COUNT = 25

# 二值分区只裁切原像素，不重复乘原始透明度；局部补底单独记录。
MASKS = {
    "head": [(150, 90), (610, 90), (610, 410), (488, 425), (454, 433), (427, 441), (399, 444), (371, 439), (344, 431), (319, 439), (278, 438), (150, 410)],
    "arm_far": [(452, 450), (479, 464), (497, 501), (508, 535), (502, 550), (480, 556), (472, 545), (468, 514), (461, 485)],
    "arm_near": [(344, 442), (366, 451), (376, 466), (365, 493), (355, 523), (349, 546), (334, 567), (319, 580), (296, 575), (282, 555), (282, 532), (296, 490), (318, 459)],
    "leg_far": [(402, 589), (431, 577), (478, 550), (485, 586), (468, 606), (486, 626), (486, 650), (448, 657), (413, 648), (398, 625)],
    "leg_near": [(312, 561), (348, 565), (374, 576), (398, 590), (405, 607), (399, 627), (411, 645), (408, 672), (332, 679), (310, 650), (310, 623), (319, 606)],
}
PART_ORDER = ["leg_far", "leg_near", "body", "arm_far", "arm_near", "head"]
PART_META = {
    "body": {"label": "躯干", "bone": "body", "slot": "slot_body", "pivot": (390, 532), "status": STATUS},
    "head": {"label": "头部", "bone": "head", "slot": "slot_head", "pivot": (398, 439), "status": "已提取·待美术精修"},
    "arm_far": {"label": "远侧手臂", "bone": "arm_far", "slot": "slot_arm_far", "pivot": (461, 470), "status": "已提取·待美术精修；摆幅±3.5°"},
    "arm_near": {"label": "近侧手臂", "bone": "arm_near", "slot": "slot_arm_near", "pivot": (351, 465), "status": "已提取·待美术精修；摆幅±3.5°"},
    "leg_far": {"label": "远侧腿", "bone": "leg_far", "slot": "slot_leg_far", "pivot": (437, 579), "status": STATUS + "；未做IK/脚锁"},
    "leg_near": {"label": "近侧腿", "bone": "leg_near", "slot": "slot_leg_near", "pivot": (359, 582), "status": STATUS + "；未做IK/脚锁"},
}
LIMITATIONS = [
    "局部程序补底，不是AI补画；隐藏区未AI补全，不代表完全没有补底",
    "仅颈肩/髋窄带及腿切口内部重叠带有程序支撑色，不代表真实被遮挡结构",
    "当前为刚性region，不含mesh/weights/IK；没有脚锁，不保证脚底不滑动",
    "摆幅受有限支撑范围约束，样件待美术精修及Spine/Unity目标运行时验收",
]


def make_mask(size: tuple[int, int], points: list[tuple[int, int]]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def crop_layer(layer: np.ndarray) -> tuple[Image.Image, tuple[int, int, int, int]]:
    image = Image.fromarray(layer, "RGBA")
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("拆件遮罩没有提取到可见像素")
    return image.crop(bbox), bbox


def compose(layers: dict[str, np.ndarray]) -> Image.Image:
    result = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for name in PART_ORDER:
        result.alpha_composite(Image.fromarray(layers[name], "RGBA"))
    return result


def nearest_color(rgb: np.ndarray, known: np.ndarray) -> np.ndarray:
    # 只从本部件切口采样支撑色，不复制完整手臂、腿或脚的图形。
    _, labels = cv2.distanceTransformWithLabels(
        (~known).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    colors = np.zeros((int(labels.max()) + 1, 3), dtype=np.uint8)
    colors[labels[known]] = rgb[known]
    return colors[labels]


def paint_support(layer: np.ndarray, support: np.ndarray, source_alpha: np.ndarray) -> np.ndarray:
    known = layer[:, :, 3] > 0
    if not np.any(support):
        return layer.copy()
    seeded = nearest_color(layer[:, :, :3], known)
    painted = cv2.inpaint(seeded, support.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
    result = layer.copy()
    result[support, :3] = painted[support]
    result[support, 3] = source_alpha[support]
    return result


def extract_layers(source: np.ndarray) -> tuple[dict, dict, dict, dict]:
    visible = source[:, :, 3] > 0
    assigned = np.zeros(visible.shape, dtype=bool)
    ownership = {}
    # 高绘制层优先，原图各像素恰好归属一个部件，避免透明边缘重复叠加。
    for name in reversed(PART_ORDER):
        if name == "body":
            continue
        mask = np.asarray(make_mask(CANVAS, MASKS[name])) > 0
        ownership[name] = mask & visible & ~assigned
        assigned |= ownership[name]
    body = visible & ~assigned
    count, labels, stats, _ = cv2.connectedComponentsWithStats(body.astype(np.uint8), 8)
    islands = []
    if count > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        distances = {
            name: cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
            for name, mask in ownership.items()
        }
        for label in range(1, count):
            if label == largest:
                continue
            island = labels == label
            target = min(distances, key=lambda name: float(distances[name][island].mean()))
            ownership[target] |= island
            body[island] = False
            islands.append({"pixels": int(island.sum()), "reassignedTo": target})
    yy, xx = np.indices(visible.shape)
    neck_internal = np.asarray(make_mask(CANVAS, [
        (353, 429), (417, 428), (453, 446), (459, 455), (337, 455),
    ])) > 0
    neck_fragments = body & (yy < 451) & ~neck_internal
    ownership["head"] |= neck_fragments
    body[neck_fragments] = False
    ownership["body"] = body
    originals = {}
    for name, mask in ownership.items():
        layer = np.zeros_like(source)
        layer[mask] = source[mask]
        originals[name] = layer

    # 内部躯干轮廓从颈延至下腹/臀，不沿腿或手臂外形扩张。
    support_outline = np.asarray(make_mask(CANVAS, [
        (354, 430), (416, 429), (452, 445), (466, 480), (470, 522),
        (477, 549), (458, 578), (419, 605), (402, 608), (379, 583),
        (342, 570), (333, 548), (343, 510), (346, 477),
    ])) > 0
    yy, xx = np.indices(visible.shape)
    distance = cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 5)
    bands = {
        "neck": (yy >= 428) & (yy <= 453) & (distance <= 12),
        "shoulder_near": (xx >= 333) & (xx <= 381) & (yy >= 443) & (yy <= 533) & (distance <= 14),
        "shoulder_far": (xx >= 447) & (xx <= 478) & (yy >= 444) & (yy <= 535) & (distance <= 14),
        "hip": (yy >= 543) & (yy <= 608) & (distance <= 12),
    }
    body_support = np.zeros_like(body)
    band_stats = {}
    for name, band in bands.items():
        restricted = band & support_outline & visible & ~body
        band_stats[name] = int(restricted.sum())
        body_support |= restricted
    final = {name: layer.copy() for name, layer in originals.items()}
    final["body"] = paint_support(originals["body"], body_support, source[:, :, 3])
    # 腿在躯干后绘制：静态可见的髋切口窄带保留原色，不让补底抹掉内裤边。
    # 只重叠内部切口最多12px，不复制整条腿，更不包含脚。
    hip_original_overlap = body_support & bands["hip"]
    final["body"][hip_original_overlap] = source[hip_original_overlap]
    support_masks = {name: np.zeros_like(body) for name in PART_ORDER}
    support_masks["body"] = body_support
    for name in ("leg_far", "leg_near"):
        leg = ownership[name]
        extended = np.zeros_like(leg)
        for shift in range(1, 11):
            extended[:-shift] |= leg[shift:]
        # 只向切口上方最多10px延伸，并且必须完全藏在实心躯干内部。
        opaque_body = final["body"][:, :, 3] == 255
        internal = cv2.erode(opaque_body.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        support = extended & ~leg & internal & support_outline & visible
        support &= yy <= PART_META[name]["pivot"][1] + 12
        final[name] = paint_support(originals[name], support, source[:, :, 3])
        support_masks[name] = support
    detail = {
        "method": "局部程序补底，不是AI补画",
        "bodyBandPixels": band_stats,
        "bodyHipOriginalOverlapPixels": int(hip_original_overlap.sum()),
        "bodyInpaintPixelsRetained": int((body_support & ~hip_original_overlap).sum()),
        "neckFragmentsReassignedToHead": int(neck_fragments.sum()),
        "bodyMaximumDistancePx": 14,
        "legUpwardExtensionLimitPx": 10,
        "inpaintRadiusPx": 3,
        "supportPixels": {name: int(mask.sum()) for name, mask in support_masks.items()},
        "bodyIslandsReassigned": islands,
        "originalPixelsPreservedPerPart": {
            name: bool(np.array_equal(final[name][mask], source[mask]))
            for name, mask in ownership.items()
        },
        "newPixelsOutsideSourceSilhouette": int(sum(np.count_nonzero(mask & ~visible) for mask in support_masks.values())),
        "legSupportCoveredByOpaqueBody": all(
            bool(np.all(final["body"][support_masks[name], 3] == 255)) for name in ("leg_far", "leg_near")
        ),
    }
    return originals, final, support_masks, detail


def atlas_pack(images: list[tuple[str, Image.Image]], padding: int = 2) -> tuple[Image.Image, list[dict]]:
    width = max(image.width for _, image in images) + padding * 2
    height = sum(image.height + padding * 2 for _, image in images)
    atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    records = []
    y = 0
    for name, image in images:
        # padding不占region坐标；RGBA边缘实际挤出2px，不是空白间隔。
        extruded = np.pad(np.asarray(image), ((padding, padding), (padding, padding), (0, 0)), mode="edge")
        atlas.paste(Image.fromarray(extruded, "RGBA"), (0, y))
        records.append({"name": name, "x": padding, "y": y + padding, "width": image.width, "height": image.height})
        y += image.height + 2 * padding
    return atlas, records


def contact_sheet(originals: dict, final: dict) -> Image.Image:
    tile_w, tile_h = 230, 340
    sheet = Image.new("RGB", (tile_w * 6, tile_h * 2), "#e6e8ed")
    draw = ImageDraw.Draw(sheet)
    for row, layers in enumerate((originals, final)):
        for column, name in enumerate(PART_ORDER):
            x, y = column * tile_w, row * tile_h
            for by in range(y + 35, y + tile_h - 8, 12):
                for bx in range(x + 5, x + tile_w - 5, 12):
                    draw.rectangle((bx, by, bx + 11, by + 11), fill="#c0c5ce" if ((bx-x)//12 + (by-y)//12) % 2 else "#f2f3f6")
            draw.text((x + 8, y + 10), f"{'original crop' if row == 0 else 'procedural support'}: {name}", fill="#222222")
            image, _ = crop_layer(layers[name])
            image.thumbnail((tile_w - 20, tile_h - 55), Image.Resampling.LANCZOS)
            sheet.paste(image, (x + (tile_w - image.width) // 2, y + 40 + (tile_h - 55 - image.height) // 2), image)
    return sheet


def walk_timelines() -> dict:
    timelines = {
        "body": {"rotate": [], "translate": []},
        "head": {"rotate": []},
        "arm_far": {"rotate": []},
        "arm_near": {"rotate": []},
        "leg_far": {"rotate": [], "translate": []},
        "leg_near": {"rotate": [], "translate": []},
    }
    for i in range(KEY_COUNT):
        time = round(DURATION * i / (KEY_COUNT - 1), 8)
        phase = 2 * math.pi * i / (KEY_COUNT - 1)
        s = math.sin(phase)
        def add(bone: str, channel: str, **values: float) -> None:
            timelines[bone][channel].append({"time": time, **{key: round(value, 6) for key, value in values.items()}})
        add("body", "rotate", value=0.6 * s)
        add("body", "translate", x=0, y=1.5 * (1 - math.cos(2 * phase)))
        add("head", "rotate", value=-0.6 * s)
        add("arm_far", "rotate", value=3.5 * s)
        add("arm_near", "rotate", value=-3.5 * s)
        add("leg_far", "rotate", value=-7 * s)
        add("leg_near", "rotate", value=7 * s)
        add("leg_far", "translate", x=-2 * s, y=4 * max(0, -s) ** 2)
        add("leg_near", "translate", x=2 * s, y=4 * max(0, s) ** 2)
    for channels in timelines.values():
        for keys in channels.values():
            keys[-1] = {**keys[0], "time": DURATION}
    return timelines


def pixel_metrics(reference: Image.Image, actual: Image.Image, support: np.ndarray) -> dict:
    a, b = np.asarray(reference).astype(np.float64), np.asarray(actual).astype(np.float64)
    pa = a[:, :, :3] * a[:, :, 3:4] / 255
    pb = b[:, :, :3] * b[:, :, 3:4] / 255
    alpha_delta = np.abs(a[:, :, 3] - b[:, :, 3])
    rgb_delta = np.abs(pa - pb)
    changed = (alpha_delta > 0) | np.any(rgb_delta > 1e-8, axis=2)
    foreground = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
    return {
        "comparedPixels": int(foreground.sum()),
        "changedPixels": int(changed.sum()),
        "changedPixelsInProceduralSupport": int((changed & support).sum()),
        "changedPixelsOutsideProceduralSupport": int((changed & ~support).sum()),
        "alphaChangedPixels": int((alpha_delta > 0).sum()),
        "alphaMaxAbsoluteError": float(alpha_delta.max()),
        "premultipliedRgbMAEOnForeground": round(float(rgb_delta[foreground].mean()), 6),
        "premultipliedRgbMaxAbsoluteError": round(float(rgb_delta.max()), 6),
        "note": "程序补底覆盖区的有意像素差异不等于美术验收；透明像素RGB不计入重组误差",
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != CANVAS:
        raise ValueError(f"右前¾源图尺寸应为 {CANVAS}，实际为 {source.size}")
    OUT.mkdir(parents=True, exist_ok=True)
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "original").mkdir(exist_ok=True)
    source.save(OUT / "source768.png")
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    source_data = np.asarray(source)
    originals, layers, supports, procedural = extract_layers(source_data)
    cropped, bounds = {}, {}
    for name in PART_ORDER:
        original, _ = crop_layer(originals[name])
        original.save(PARTS / "original" / f"{name}.png")
        cropped[name], bounds[name] = crop_layer(layers[name])
        cropped[name].save(PARTS / f"{name}.png")
    original_assembly = compose(originals)
    original_assembly.save(OUT / "right_front_3q_original_assembly.png")
    assembled = compose(layers)
    assembled.save(OUT / "right_front_3q_assembly.png")
    contact_sheet(originals, layers).save(OUT / "parts_contact.png")
    support_union = np.logical_or.reduce(list(supports.values()))
    Image.fromarray(support_union.astype(np.uint8) * 255, "L").save(OUT / "procedural_support_mask.png")
    assembly_metrics = pixel_metrics(source, assembled, support_union)
    original_metrics = pixel_metrics(source, original_assembly, np.zeros_like(support_union))

    atlas, atlas_records = atlas_pack([(name, cropped[name]) for name in PART_ORDER])
    atlas.save(OUT / "right_front_walk.png")
    atlas_lines = ["right_front_walk.png", f"size: {atlas.width},{atlas.height}", "format: RGBA8888", "filter: Linear,Linear", "repeat: none"]
    for record in atlas_records:
        atlas_lines.extend([
            str(record["name"]), "  rotate: false",
            f"  xy: {record['x']}, {record['y']}",
            f"  size: {record['width']}, {record['height']}",
            f"  orig: {record['width']}, {record['height']}",
            "  offset: 0, 0", "  index: -1",
        ])
    atlas_path = OUT / "right_front_walk.atlas.txt"
    atlas_path.write_text("\n".join(atlas_lines) + "\n", encoding="utf-8")
    # 同时提供标准.atlas后缀，保留原消费端使用的.atlas.txt文件名。
    (OUT / "right_front_walk.atlas").write_text(atlas_path.read_text(encoding="utf-8"), encoding="utf-8")
    parts = []
    for name in PART_ORDER:
        x0, y0, x1, y1 = bounds[name]
        _, original_bbox = crop_layer(originals[name])
        meta = PART_META[name]
        parts.append({
            "id": name, "label": meta["label"], "file": f"parts/{name}.png",
            "originalFile": f"parts/original/{name}.png", "originalCrop": list(original_bbox),
            "bone": meta["bone"], "slot": meta["slot"],
            "crop": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "pivot": {"x": meta["pivot"][0], "y": meta["pivot"][1]},
            "status": meta["status"], "proceduralSupportPixels": procedural["supportPixels"][name],
        })
    # canonical：源图y-down转Spine y-up；子骨位置仍相对于body原始pivot。
    bones = [
        {"name": "root"},
        {"name": "body", "parent": "root", "x": 390, "y": 236},
        {"name": "head", "parent": "body", "x": 8, "y": 93},
        {"name": "arm_far", "parent": "body", "x": 71, "y": 62},
        {"name": "arm_near", "parent": "body", "x": -39, "y": 67},
        {"name": "leg_far", "parent": "body", "x": 47, "y": -47},
        {"name": "leg_near", "parent": "body", "x": -31, "y": -50},
    ]
    slots = [{"name": PART_META[name]["slot"], "bone": name, "attachment": name} for name in PART_ORDER]
    attachments = {}
    for part in parts:
        crop, pivot = part["crop"], part["pivot"]
        attachments[part["slot"]] = {part["id"]: {
            "type": "region", "path": part["id"],
            "x": crop["x"] + crop["width"] / 2 - pivot["x"],
            "y": pivot["y"] - crop["y"] - crop["height"] / 2,
            "width": crop["width"], "height": crop["height"],
        }}
    runtime = {
        "skeleton": {"hash": source_hash[:24], "spine": "4.2.43", "x": 0, "y": 0, "width": CANVAS[0], "height": CANVAS[1], "images": "./"},
        "bones": bones, "slots": slots,
        "skins": [{"name": "default", "attachments": attachments}],
        "animations": {"walk": {"bones": walk_timelines()}},
        "cottonDollProduction": {
            "status": STATUS, "sourceView": "right_front_3q", "action": "walk",
            "source": SOURCE.name, "sourceFile": str(SOURCE), "sourceSha256": source_hash,
            "canvas": list(CANVAS), "parts": parts, "drawOrder": PART_ORDER,
            "assemblyMetrics": assembly_metrics, "originalAssemblyMetrics": original_metrics,
            "proceduralSupport": procedural, "artReview": "待美术精修/验收", "limitations": LIMITATIONS,
        },
    }
    runtime_path = OUT / "right_front_walk.json"
    write_json(runtime_path, runtime)
    manifest = {
        "version": 2, "status": STATUS, "sourceView": "right_front_3q", "sourceLabel": "右前¾",
        "sourceFile": str(SOURCE), "sourceSha256": source_hash, "sourceSnapshot": "source768.png",
        "action": "walk", "actionLabel": "原地行走", "canvas": {"width": 768, "height": 768},
        "assembly": "right_front_3q_assembly.png", "originalAssembly": "right_front_3q_original_assembly.png",
        "contactSheet": "parts_contact.png", "proceduralSupportMask": "procedural_support_mask.png",
        "atlas": "right_front_walk.png", "atlasText": "right_front_walk.atlas.txt",
        "runtimeJson": "right_front_walk.json", "qualityReport": "quality_report.json", "archive": "right_front_walk.zip",
        "parts": parts, "drawOrder": PART_ORDER,
        "animation": {"duration": DURATION, "fps": 30, "keyCount": KEY_COUNT, "loop": True, "mode": "in_place", "sampling": "25键正弦采样，键间线性插值", "footLock": False},
        "method": {
            "summary": "原图可见像素独立裁切，颈肩/髋内部窄带cv2.inpaint程序补底；隐藏区未AI补全。",
            "referenceRules": ["腿→躯干→手臂→头部", "内部支撑不沿四肢外形扩张，不复制完整手脚", "手臂±3.5°，腿±7°、摆动抬脚4px；受支撑范围限制，尚无IK"],
            "proceduralSupport": procedural, "atlasPaddingExtrudePx": 2,
        },
        "assemblyMetrics": assembly_metrics, "originalAssemblyMetrics": original_metrics,
        "artReview": "样件待美术精修/验收", "limitations": LIMITATIONS,
    }
    write_json(OUT / "manifest.json", manifest)

    # 从已写入的JSON/PNG重新读取检查，不用预设的“已验证”标签代替检测。
    saved = json.loads(runtime_path.read_text(encoding="utf-8"))
    timelines = saved["animations"]["walk"]["bones"]
    loops, second_half = {}, {}
    for bone, channels in timelines.items():
        for channel, keys in channels.items():
            name = f"{bone}.{channel}"
            loops[name] = ({k: v for k, v in keys[0].items() if k != "time"} == {k: v for k, v in keys[-1].items() if k != "time"})
            latter = [key for key in keys if key["time"] >= DURATION / 2]
            moving_intervals = sum(any(a[k] != b[k] for k in a if k != "time") for a, b in zip(latter, latter[1:]))
            second_half[name] = {"movingIntervals": moving_intervals, "totalIntervals": len(latter) - 1}
    rgba_files = [OUT / "source768.png", OUT / "right_front_3q_assembly.png", OUT / "right_front_3q_original_assembly.png", OUT / "right_front_walk.png"]
    rgba_files += [PARTS / f"{name}.png" for name in PART_ORDER] + [PARTS / "original" / f"{name}.png" for name in PART_ORDER]
    png_checks = {}
    for path in rgba_files:
        with Image.open(path) as image:
            image.load()
            alpha = np.asarray(image.getchannel("A"))
            png_checks[path.relative_to(OUT).as_posix()] = {
                "mode": image.mode, "size": list(image.size), "alphaMin": int(alpha.min()), "alphaMax": int(alpha.max()),
                "nonzeroAlphaPixels": int(np.count_nonzero(alpha)), "transparentPixels": int(np.count_nonzero(alpha == 0)),
                "partialAlphaPixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
            }
    world = {"root": (0, 0)}
    coordinate_checks = {}
    for bone in saved["bones"][1:]:
        parent = world[bone["parent"]]
        world[bone["name"]] = (parent[0] + bone["x"], parent[1] + bone["y"])
    for part in parts:
        bone_x, bone_y = world[part["id"]]
        att = saved["skins"][0]["attachments"][part["slot"]][part["id"]]
        crop = part["crop"]
        coordinate_checks[part["id"]] = {
            "pivotYUpCorrect": (bone_x, bone_y) == (part["pivot"]["x"], CANVAS[1] - part["pivot"]["y"]),
            "attachmentRestoresCrop": bone_x + att["x"] - att["width"] / 2 == crop["x"] and CANVAS[1] - (bone_y + att["y"] + att["height"] / 2) == crop["y"],
        }
    atlas_checks = {}
    with Image.open(OUT / "right_front_walk.png") as packed:
        for record in atlas_records:
            x, y, w, h = (record[key] for key in ("x", "y", "width", "height"))
            actual = np.asarray(packed.crop((x - 2, y - 2, x + w + 2, y + h + 2)))
            expected = np.pad(np.asarray(cropped[record["name"]]), ((2, 2), (2, 2), (0, 0)), mode="edge")
            atlas_checks[record["name"]] = bool(np.array_equal(actual, expected))
    near = timelines["leg_near"]
    far = timelines["leg_far"]
    leg_antiphase = all(abs(a["value"] + b["value"]) < 1e-6 for a, b in zip(near["rotate"], far["rotate"]))
    body_y = [key["y"] for key in timelines["body"]["translate"]]
    peaks = sum(body_y[i] > body_y[i - 1] and body_y[i] > body_y[i + 1] for i in range(1, len(body_y) - 1))
    checks = {
        "loopEndpointsMatch": all(loops.values()),
        "allTimelinesHave25Keys": all(len(keys) == KEY_COUNT for channels in timelines.values() for keys in channels.values()),
        "timeKeysStrictlyIncreasing": all(all(a["time"] < b["time"] for a, b in zip(keys, keys[1:])) for channels in timelines.values() for keys in channels.values()),
        "noSecondHalfRotationHold": all(second_half[f"{bone}.rotate"]["movingIntervals"] == 12 for bone in ("arm_far", "arm_near", "leg_far", "leg_near")),
        "legsRotateInAntiphase": leg_antiphase, "bodyBobsTwice": peaks == 2,
        "pngRgbaWithTransparentAndVisiblePixels": all(info["mode"] == "RGBA" and info["transparentPixels"] > 0 and info["nonzeroAlphaPixels"] > 0 for info in png_checks.values()),
        "canonicalCoordinatesAndAttachments": all(all(info.values()) for info in coordinate_checks.values()),
        "atlas2pxExtrusionMatches": all(atlas_checks.values()),
        "originalAssemblyPixelExact": original_metrics["changedPixels"] == 0,
        "originalVisiblePixelsPreservedPerPart": all(procedural["originalPixelsPreservedPerPart"].values()),
        "differencesConfinedToProceduralSupport": assembly_metrics["changedPixelsOutsideProceduralSupport"] == 0,
        "sourceSilhouetteAlphaUnchanged": assembly_metrics["alphaChangedPixels"] == 0,
        "legSupportHiddenInOpaqueBody": procedural["legSupportCoveredByOpaqueBody"],
        "noSupportOutsideSourceSilhouette": procedural["newPixelsOutsideSourceSilhouette"] == 0,
    }
    report = {
        "status": STATUS, "sourceFile": str(SOURCE), "sourceSha256": source_hash,
        "checks": checks, "automatedChecksPassed": all(checks.values()),
        "loopEndpoints": loops, "secondHalfMotion": second_half, "bodyBobPeakCount": peaks,
        "legLiftLocalPx": {name: max(key["y"] for key in timelines[name]["translate"]) for name in ("leg_far", "leg_near")},
        "coordinates": coordinate_checks, "pngAlpha": png_checks, "atlasExtrusion": atlas_checks,
        "originalAssemblyMetrics": original_metrics, "assemblyMetrics": assembly_metrics,
        "proceduralSupport": procedural,
        "notVerified": ["动态画面逐帧美术验收", "Spine/Unity实际运行时导入与播放", "脚锁/IK（尚未实现）"],
        "artReview": "样件待美术精修/验收", "limitations": LIMITATIONS,
    }
    report_path = OUT / "quality_report.json"
    write_json(report_path, report)
    outputs = [OUT / name for name in (
        "manifest.json", "right_front_walk.json", "right_front_walk.atlas", "right_front_walk.atlas.txt",
        "right_front_walk.png", "right_front_3q_assembly.png", "right_front_3q_original_assembly.png",
        "source768.png", "parts_contact.png", "procedural_support_mask.png", "quality_report.json",
    )] + [PARTS / f"{name}.png" for name in PART_ORDER] + [PARTS / "original" / f"{name}.png" for name in PART_ORDER]
    archive_path = OUT / "right_front_walk.zip"
    def pack() -> None:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in outputs:
                archive.write(path, path.relative_to(OUT).as_posix())
    pack()
    with zipfile.ZipFile(archive_path) as archive:
        report["archive"] = {"file": archive_path.name, "members": archive.namelist(), "crcCheckPassed": archive.testzip() is None}
    checks["zipContainsExpectedFiles"] = set(report["archive"]["members"]) == {path.relative_to(OUT).as_posix() for path in outputs}
    checks["zipCrcPassed"] = report["archive"]["crcCheckPassed"]
    report["automatedChecksPassed"] = all(checks.values())
    write_json(report_path, report)
    pack()
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or archive.read("quality_report.json") != report_path.read_bytes():
            raise RuntimeError("最终ZIP的CRC或报告内容不一致")
    print(json.dumps({"out": str(OUT), "parts": len(parts), "source": list(source.size), "qualityChecksPassed": report["automatedChecksPassed"], "assemblyMetrics": assembly_metrics, "proceduralSupportPixels": procedural["supportPixels"], "zipMembers": len(outputs), "archive": str(archive_path)}, ensure_ascii=False))
    if not report["automatedChecksPassed"]:
        raise RuntimeError(f"质量检查未通过：{[name for name, passed in checks.items() if not passed]}")


if __name__ == "__main__":
    main()
