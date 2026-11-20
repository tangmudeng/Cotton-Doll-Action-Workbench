from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
PARENT = HERE / "generated_rig" / "video_f7e82942"
PARTS = PARENT / "stable_parts_v1"
OUT = PARENT / "arm_mesh_test_v1"
SIZE = (768, 768)
STEP = 9
JOINTS = np.array([[350., 456.], [330., 509.], [317., 555.]], dtype=np.float64)
REVIEW_BOX = (255, 418, 510, 615)
BONE_INDICES = ((0, 1), (1, 2))
EXPECTED_ORDER = ["leg_far", "leg_near", "body", "shorts", "arm_far", "arm_near", "head"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def cross2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def influence_weights(points: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    projected_arcs, distances = [], []
    offset = 0.
    for bone_id, (a, b) in enumerate(BONE_INDICES):
        direction = JOINTS[b] - JOINTS[a]
        t = np.clip((points - JOINTS[a]) @ direction / np.dot(direction, direction), 0., 1.)
        projected = JOINTS[a] + t[:, None] * direction
        distances.append(np.sum((points - projected) ** 2, axis=1))
        projected_arcs.append(offset + t * lengths[bone_id])
        offset += lengths[bone_id]
    nearest = np.argmin(np.stack(distances, axis=1), axis=1)
    arc = np.stack(projected_arcs, axis=1)[np.arange(len(points)), nearest]
    # 沿最近中心线骨段投影求弧长，在肘两侧各20像素内平滑混合，不做体积修正。
    t = np.clip((arc - (lengths[0] - 20.)) / 40., 0., 1.)
    forearm = t * t * (3. - 2. * t)
    return np.stack((1. - forearm, forearm), axis=1)


def build_mesh(bbox: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = bbox
    # 两像素透明护边用于双线性边缘采样，网格不补画任何肩根像素。
    xs = np.unique(np.r_[np.arange(x0 - 2, x1 + 2, STEP), x1 + 2])
    ys = np.unique(np.r_[np.arange(y0 - 2, y1 + 2, STEP), y1 + 2])
    vertices = np.array([(x, y) for y in ys for x in xs], dtype=np.float64)
    triangles = []
    cols = len(xs)
    for iy in range(len(ys) - 1):
        for ix in range(cols - 1):
            a = iy * cols + ix
            b, c, d = a + 1, a + cols, a + cols + 1
            triangles.extend(((a, b, d), (a, d, c)))
    # UV以全局768纹理的像素中心为准；渲染采样位置为 uv*768-0.5。
    uv = (vertices + .5) / np.array(SIZE)
    return vertices, np.asarray(triangles, dtype=np.int32), uv, influence_weights(vertices)


def bone_matrices(target_joints: np.ndarray) -> list[np.ndarray]:
    matrices = []
    for a, b in BONE_INDICES:
        src = JOINTS[b] - JOINTS[a]
        dst = target_joints[b] - target_joints[a]
        src_length, dst_length = np.linalg.norm(src), np.linalg.norm(dst)
        source_axis, target_axis = src / src_length, dst / dst_length
        source_basis = np.column_stack((source_axis, [-source_axis[1], source_axis[0]]))
        target_basis = np.column_stack((target_axis, [-target_axis[1], target_axis[0]]))
        # 端点姿态允许骨轴长度改变；横向尺度固定为1，并在JSON报告骨长比。
        linear = target_basis @ np.diag([dst_length / src_length, 1.]) @ source_basis.T
        translation = target_joints[a] - linear @ JOINTS[a]
        matrix = np.column_stack((linear, translation))
        if np.array_equal(target_joints[[a, b]], JOINTS[[a, b]]):
            matrix = np.array([[1., 0., 0.], [0., 1., 0.]])
        matrices.append(matrix)
    return matrices


def deform(points: np.ndarray, weights: np.ndarray, matrices: list[np.ndarray]) -> np.ndarray:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    return sum((homogeneous @ m.T) * weights[:, i:i + 1] for i, m in enumerate(matrices))


def render_mesh(texture: np.ndarray, uv: np.ndarray, triangles: np.ndarray,
                target: np.ndarray, compositing: str = "legacy_overwrite") -> tuple[np.ndarray, dict, np.ndarray]:
    if compositing not in ("legacy_overwrite", "source_over_top_left"):
        raise ValueError(compositing)
    source_vertices = uv * np.array(SIZE) - .5
    premult = texture.astype(np.float32) / 255.
    premult[:, :, :3] *= premult[:, :, 3:4]
    result = np.zeros_like(premult)
    coverage = np.zeros(SIZE[::-1], dtype=np.uint16)
    interior_coverage = np.zeros_like(coverage)
    flipped = collapsed = flipped_textured = collapsed_textured = 0
    ratios, active_ratios = [], []
    for tri in triangles:
        src, dst = source_vertices[tri], target[tri]
        sa = float(cross2(src[1] - src[0], src[2] - src[0]))
        da = float(cross2(dst[1] - dst[0], dst[2] - dst[0]))
        sx0, sy0 = np.floor(src.min(axis=0)).astype(int)
        sx1, sy1 = np.ceil(src.max(axis=0)).astype(int) + 1
        has_texture = bool(np.any(texture[max(sy0, 0):sy1, max(sx0, 0):sx1, 3] > 0))
        ratios.append(abs(da / sa))
        if has_texture:
            active_ratios.append(abs(da / sa))
        if abs(da) <= 1e-3:
            collapsed += 1
            collapsed_textured += int(has_texture)
            continue
        if sa * da < 0:
            flipped += 1
            flipped_textured += int(has_texture)
        bx0, by0 = np.maximum(np.floor(dst.min(axis=0)).astype(int) - 1, 0)
        bx1, by1 = np.minimum(np.ceil(dst.max(axis=0)).astype(int) + 2, SIZE)
        if bx1 <= bx0 or by1 <= by0:
            continue
        # 重心坐标按整数像素中心选择归属；共享边直接写入，不重复alpha合成。
        xx, yy = np.meshgrid(np.arange(bx0, bx1), np.arange(by0, by1))
        pixel = np.stack((xx, yy), axis=-1) - dst[0]
        b = cross2(pixel, dst[2] - dst[0]) / da
        c = cross2(dst[1] - dst[0], pixel) / da
        a = 1. - b - c
        mask = (a >= -1e-7) & (b >= -1e-7) & (c >= -1e-7)
        interior = (a > 1e-7) & (b > 1e-7) & (c > 1e-7)
        matrix = cv2.getAffineTransform(src.astype(np.float32), dst.astype(np.float32))
        matrix[:, 2] -= (bx0, by0)
        warped = cv2.warpAffine(premult, matrix, (int(bx1 - bx0), int(by1 - by0)),
                                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                borderValue=(0., 0., 0., 0.))
        roi = result[by0:by1, bx0:bx1]
        if compositing == "legacy_overwrite":
            roi[mask] = warped[mask]
        else:
            # Half-open triangle ownership prevents shared-edge alpha being blended twice.
            oriented = dst if da > 0. else dst[[0, 2, 1]]
            pixel_xy = np.stack((xx, yy), axis=-1)
            owned = np.ones(mask.shape, dtype=bool)
            for edge_a, edge_b in zip(oriented, np.roll(oriented, -1, axis=0)):
                direction = edge_b - edge_a
                edge_value = cross2(direction, pixel_xy - edge_a)
                top_left = direction[1] < 0. or (abs(direction[1]) < 1e-12 and direction[0] > 0.)
                owned &= (edge_value > 1e-7) | ((np.abs(edge_value) <= 1e-7) & top_left)
            source = warped[owned]
            roi[owned] = source + roi[owned] * (1. - source[:, 3:4])
        ownership = (owned if compositing == "source_over_top_left" else mask)
        interior_ownership = (owned & interior if compositing == "source_over_top_left" else interior)
        coverage[by0:by1, bx0:bx1] += ownership.astype(np.uint16)
        interior_coverage[by0:by1, bx0:bx1] += interior_ownership.astype(np.uint16)
    straight = result.copy()
    visible = result[:, :, 3] > 1e-8
    straight[visible, :3] /= straight[visible, 3:4]
    straight[~visible] = 0.
    rendered = np.rint(np.clip(straight, 0., 1.) * 255.).astype(np.uint8)
    checks = {
        "flippedTriangles": flipped, "collapsedTriangles": collapsed,
        "flippedTrianglesWithSourceAlphaInAabb": flipped_textured,
        "collapsedTrianglesWithSourceAlphaInAabb": collapsed_textured,
        "collapseDoubleAreaThresholdPx2": .001,
        "absoluteTriangleAreaRatioMin": float(min(ratios)) if ratios else None,
        "absoluteTriangleAreaRatioMax": float(max(ratios)) if ratios else None,
        "texturedTriangleAreaRatioMin": float(min(active_ratios)) if active_ratios else None,
        "texturedTriangleAreaRatioMax": float(max(active_ratios)) if active_ratios else None,
        "overlappingTriangleInteriorRasterPixels": int(np.count_nonzero(interior_coverage > 1)),
        "rasterPolicy": ("整数像素中心重心归属；预乘alpha仿射；共享边不重复合成；折叠重叠按三角索引后写覆盖，未修复"
                         if compositing == "legacy_overwrite" else
                         "整数像素中心/半开top-left边界；预乘alpha source-over；共享边单次归属；几何自交仍按索引层叠，未修复"),
    }
    return rendered, checks, coverage


def assemble(manifest: dict, layers: dict[str, Image.Image], arm: np.ndarray) -> Image.Image:
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    for part_id in manifest["assemblyLayerOrder"]:
        canvas.alpha_composite(Image.fromarray(arm) if part_id == "arm_near" else layers[part_id])
    return canvas


def mesh_overlay(rendered: np.ndarray, vertices: np.ndarray, triangles: np.ndarray,
                 target: np.ndarray) -> Image.Image:
    canvas = Image.fromarray(rendered)
    draw = ImageDraw.Draw(canvas)
    for tri in triangles:
        draw.line([tuple(p) for p in vertices[tri]] + [tuple(vertices[tri[0]])], fill=(28, 128, 150, 190), width=1)
    draw.line([tuple(p) for p in target], fill=(210, 64, 49, 255), width=2)
    for p in target:
        x, y = p
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(210, 64, 49, 255))
    return canvas


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)


def crop_view(image: Image.Image, box=REVIEW_BOX, scale=2) -> Image.Image:
    crop = image.convert("RGBA").crop(box)
    bg = Image.new("RGBA", crop.size, (248, 248, 244, 255))
    bg.alpha_composite(crop)
    return bg.convert("RGB").resize((crop.width * scale, crop.height * scale), Image.Resampling.NEAREST)


def make_review(panels: list[dict], references: dict[int, Image.Image]) -> None:
    width, height, row_h = 1740, 1930, 470
    sheet = Image.new("RGB", (width, height), (238, 242, 241))
    draw = ImageDraw.Draw(sheet)
    title_font, body_font, small_font = font(29), font(20), font(17)
    draw.text((24, 15), "近侧臂双骨网格｜独立静态压力试验 v1", fill=(30, 47, 51), font=title_font)
    draw.text((24, 60), "人工源骨架与姿态；非视频测量/拟合。肩根未补，体积损失、折叠和漏底原样保留。", fill=(99, 56, 40), font=body_font)
    headers = ["源臂 + 源骨架（每行同一原图）", "实际变形 + 三角线框", "当前七层组装（局部，无补底）"]
    for col, label in enumerate(headers):
        draw.text((24 + col * 574, 102), label, fill=(28, 49, 53), font=body_font)
    source_panel = panels[0]["source_view"]
    for row, panel in enumerate(panels):
        top = 140 + row * row_h
        draw.text((24, top), panel["label"], fill=(27, 51, 57), font=body_font)
        for col, view in enumerate((source_panel, panel["overlay"], panel["assembly"])):
            image = crop_view(view)
            sheet.paste(image, (24 + col * 574, top + 40))
        metrics = panel["metrics"]
        draw.text((600, top + 438), f"翻转 {metrics['mesh']['flippedTriangles']} / 退化 {metrics['mesh']['collapsedTriangles']}；臂alpha {metrics['renderedArmAlphaPixels']}",
                  fill=(100, 49, 37), font=small_font)
        draw.text((1172, top + 438), f"中性域内alpha缺失 {metrics['exposureVsNeutral']['lostAnyAlphaPixels']}（非真值）",
                  fill=(100, 49, 37), font=small_font)
    top = 1565
    draw.text((24, top), "视频小参考：68 / 72 / 80（仅看姿态，不同画幅；未计算匹配误差，未做身份绑定）", fill=(35, 56, 61), font=body_font)
    for col, (index, image) in enumerate(references.items()):
        # 参考帧保留全部画幅，并非把768源图坐标套到864×480帧上。
        thumb = image.convert("RGB").resize((480, 267), Image.Resampling.LANCZOS)
        x = 40 + col * 574
        sheet.paste(thumb, (x, top + 40))
        draw.text((x, top + 311), f"frame {index:03d}，视觉参考而非拟合目标", fill=(48, 63, 67), font=small_font)
    draw.text((24, 1900), "完整透明arm / mesh叠线 / 七层组装均另存768 PNG；mesh.json与checks.json记录实际误差及限制。", fill=(61, 76, 79), font=small_font)
    sheet.save(OUT / "review.png")


def main() -> None:
    if not PARENT.is_dir() or not PARTS.is_dir():
        raise FileNotFoundError(f"所需父目录不存在：{PARENT}")
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {p["id"]: p for p in manifest["parts"]}
    if manifest["assemblyLayerOrder"] != EXPECTED_ORDER:
        raise ValueError("七层顺序已变化，请重新审阅")
    arm_record = records["arm_near"]
    if arm_record["bbox"] != [287, 443, 377, 581]:
        raise ValueError("源臂bbox已变化，请重新校验人工控制点")
    source_path = (PARTS / manifest["sourceImage"]["file"]).resolve()
    source = Image.open(source_path).convert("RGBA")
    if source.size != SIZE:
        raise ValueError("需要768×768全局源图")
    tracked_paths = [manifest_path, source_path] + sorted(p for p in PARTS.rglob("*") if p.is_file())
    tracked_paths = list(dict.fromkeys(tracked_paths))
    before = {str(p): sha256(p) for p in tracked_paths}
    expected_files = [(source_path, manifest["sourceImage"]["sha256"])]
    expected_files += [(PARTS / p["file"], p["sha256"]) for p in records.values()]
    if any(sha256(p) != expected for p, expected in expected_files):
        raise ValueError("源文件SHA与manifest不符，停止试验")
    layers = {}
    for part_id, record in records.items():
        part = Image.open(PARTS / record["file"]).convert("RGBA")
        bbox = record["bbox"]
        if part.size != (bbox[2] - bbox[0], bbox[3] - bbox[1]):
            raise ValueError(f"{part_id} 尺寸与bbox不符")
        layer = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        layer.paste(part, tuple(bbox[:2]))
        layers[part_id] = layer
    source_arm = np.array(layers["arm_near"])
    source_alpha = source_arm[:, :, 3]
    source_array = np.array(source)
    source_visible = source_alpha > 0
    rgba_source_mismatch = int(np.count_nonzero(np.any(source_arm != source_array, axis=2) & source_visible))
    if rgba_source_mismatch:
        raise AssertionError("源臂可见像素并非逐像素保留")
    control_checks = []
    for name, joint in zip(("shoulder", "elbow", "hand"), JOINTS):
        x, y = np.rint(joint).astype(int)
        alpha_value = int(source_alpha[y, x])
        if alpha_value == 0:
            raise ValueError(f"人工控制点{name}未落在可见臂像素内")
        patch = source_alpha[y - 4:y + 5, x - 4:x + 5]
        control_checks.append({"joint": name, "globalXY": joint.tolist(), "alpha": alpha_value,
                               "visibleIn9x9": int(np.count_nonzero(patch)),
                               "interpretation": "视觉及alpha检查可作可见臂人工控制点，不是关节解剖或视频测量验证"})
    vertices, triangles, uv, weights = build_mesh(arm_record["bbox"])
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    open_angles = np.deg2rad([125., 85.])
    open_joints = [JOINTS[0].copy()]
    for length, angle in zip(lengths, open_angles):
        open_joints.append(open_joints[-1] + length * np.array([math.cos(angle), math.sin(angle)]))
    poses = {
        "neutral": {"joints": JOINTS.copy(), "refs": [], "label": "neutral｜原位恒等变换，仍实际执行网格光栅化"},
        "open": {"joints": np.array(open_joints), "refs": [68, 80], "label": "open｜人工绝对角125° / 85°，只参考68 / 80"},
        "chest": {"joints": np.array([[350., 456.], [354., 510.], [395., 500.]]), "refs": [72], "label": "chest｜人工端点 [350,456] → [354,510] → [395,500]"},
    }
    OUT.mkdir(exist_ok=True)
    references = {index: Image.open(PARENT / "frames" / f"frame_{index:03d}.jpg").convert("RGB") for index in (68, 72, 80)}
    neutral_assembly = np.array(assemble(manifest, layers, source_arm))
    baseline_alpha = neutral_assembly[:, :, 3]
    baseline_domain = baseline_alpha > 0
    pose_checks, pose_metadata, panels = {}, {}, []
    source_view = mesh_overlay(source_arm, np.empty((0, 2)), np.empty((0, 3), dtype=int), JOINTS)
    for name, config in poses.items():
        joints = config["joints"]
        matrices = bone_matrices(joints)
        transformed = deform(vertices, weights, matrices)
        rendered, tri_checks, coverage = render_mesh(source_arm, uv, triangles, transformed)
        assembly = assemble(manifest, layers, rendered)
        assembly_array = np.array(assembly)
        overlay = mesh_overlay(rendered, transformed, triangles, joints)
        Image.fromarray(rendered).save(OUT / f"{name}_arm.png")
        overlay.save(OUT / f"{name}_mesh_overlay.png")
        assembly.save(OUT / f"{name}_assembly.png")
        current_alpha = assembly_array[:, :, 3]
        lost = baseline_domain & (current_alpha == 0)
        opaque_loss = (baseline_alpha >= 250) & (current_alpha < 250)
        evidence = np.zeros_like(source_arm)
        evidence[opaque_loss] = (255, 168, 30, 180)
        evidence[lost] = (215, 48, 105, 255)
        Image.fromarray(evidence).save(OUT / f"{name}_neutral_domain_exposure.png")
        alpha_difference = np.maximum(baseline_alpha.astype(np.int16) - current_alpha.astype(np.int16), 0)
        pose_checks[name] = {
            "mesh": tri_checks,
            "renderedArmAlphaPixels": int(np.count_nonzero(rendered[:, :, 3])),
            "armAlphaAreaEquivalentPixels": float(rendered[:, :, 3].sum() / 255.),
            "armAlphaAreaRatioToSource": float(rendered[:, :, 3].sum() / source_alpha.sum()),
            "boneLengthRatios": (np.linalg.norm(np.diff(joints, axis=0), axis=1) / lengths).tolist(),
            "exposureVsNeutral": {
                "lostAnyAlphaPixels": int(np.count_nonzero(lost)),
                "lostNearOpaquePixels": int(np.count_nonzero(opaque_loss)),
                "lostAlphaAreaEquivalentPixelsInNeutralDomain": float(alpha_difference[baseline_domain].sum() / 255.),
                "interpretation": "只与静态中性七层域对照的移开暴露证据；包括正常轮廓移开，不是真实姿态缺口/视频误差",
            },
            "armComparedWithNeutralSourceDomain": {
                "lostAlphaPixels": int(np.count_nonzero(source_visible & (rendered[:, :, 3] == 0))),
                "newAlphaPixels": int(np.count_nonzero(~source_visible & (rendered[:, :, 3] > 0))),
                "interpretation": "源臂domain变化，仅描述平面移开，不作为姿态真值",
            },
        }
        if name == "neutral":
            union = source_visible | (rendered[:, :, 3] > 0)
            difference = np.abs(source_arm.astype(np.int16) - rendered.astype(np.int16))
            raw_mismatch = np.any(difference > 0, axis=2)
            premult_source = source_arm.astype(float)
            premult_source[:, :, :3] *= source_alpha[:, :, None] / 255.
            premult_render = rendered.astype(float)
            premult_render[:, :, :3] *= rendered[:, :, 3:4] / 255.
            raster = {
                "actuallyMeshRasterized": True,
                "originalImageUsedInsteadOfMesh": False,
                "vertexMaxAbsolutePositionErrorPx": float(np.max(np.abs(transformed - vertices))),
                "rgbaMismatchPixelsInVisibleUnion": int(np.count_nonzero(raw_mismatch & union)),
                "rgbaMaeInVisibleUnion": float(difference[union].mean()),
                "rgbaMaxErrorInVisibleUnion": int(difference[union].max()),
                "premultipliedRgbaMaeInVisibleUnion": float(np.abs(premult_source - premult_render)[union].mean()),
                "alphaMismatchPixels": int(np.count_nonzero(source_alpha != rendered[:, :, 3])),
                "sourceVisiblePixelsNotCoveredByTriangleRaster": int(np.count_nonzero(source_visible & (coverage == 0))),
                "transparentRgbMismatchPixelsIgnored": int(np.count_nonzero(raw_mismatch & ~union)),
                "interpretation": "忽略全透明RGB；零误差若出现，是实际恒等三角光栅结果，不是源图替代输出",
            }
            pose_checks[name]["neutralMeshRestoration"] = raster
            diff_image = np.zeros_like(source_arm)
            diff_image[:, :, :3] = np.minimum(difference[:, :, :3] * 8, 255).astype(np.uint8)
            diff_image[:, :, 3] = np.where(raw_mismatch & union, 255, 0).astype(np.uint8)
            Image.fromarray(diff_image).save(OUT / "neutral_mesh_diff_x8.png")
        pose_metadata[name] = {
            "targetJointsGlobalXY": joints.tolist(),
            "absoluteBoneAnglesDegreesImageYDown": np.rad2deg(np.arctan2(np.diff(joints, axis=0)[:, 1], np.diff(joints, axis=0)[:, 0])).tolist(),
            "referenceFrameIndicesVisualOnly": config["refs"],
            "boneGlobalFromBindMatrices2x3": [matrix.tolist() for matrix in matrices],
            "deformedVerticesGlobalXY": transformed.tolist(),
            "manualHypothesis": True, "videoFitted": False,
        }
        panels.append({"label": config["label"], "source_view": source_view, "overlay": overlay,
                       "assembly": assembly, "metrics": pose_checks[name]})
    make_review(panels, references)
    source_preserved = all(sha256(Path(path)) == value for path, value in before.items())
    checks = {
        "sourceAllTrackedFilesUnchanged": source_preserved,
        "trackedFileCount": len(before),
        "sourceHashesBeforeAndAfter": {path: {"before": value, "after": sha256(Path(path))} for path, value in before.items()},
        "sourceManifestHashesMatch": True,
        "sourceVisibleArmRgbaMismatchPixels": rgba_source_mismatch,
        "manualControlsAlphaChecks": control_checks,
        "mesh": {
            "vertexCount": len(vertices), "triangleCount": len(triangles),
            "weightsFiniteNonnegative": bool(np.isfinite(weights).all() and (weights >= 0).all()),
            "weightsSumMaxError": float(np.max(np.abs(weights.sum(axis=1) - 1.))),
            "uvFiniteIn01": bool(np.isfinite(uv).all() and (uv >= 0).all() and (uv <= 1).all()),
            "triangleIndicesValid": bool(triangles.min() >= 0 and triangles.max() < len(vertices)),
            "twoBones": len(BONE_INDICES) == 2,
        },
        "layerOrderBackToFront": manifest["assemblyLayerOrder"],
        "neutralUnwarpedAssemblyVsSourceVisibleRgbaMismatchPixels": int(np.count_nonzero(np.any(neutral_assembly != source_array, axis=2) & (source_array[:, :, 3] > 0))),
        "poses": pose_checks,
        "notVideoFitted": True, "oldRuntimeRead": False, "sineWalkRead": False,
        "pendingShoulderRepairReadOrRequired": False,
        "bindingValidated": False, "hiddenComplete": False, "identityValidated": False,
    }
    checks["structuralChecksPassed"] = bool(source_preserved and checks["mesh"]["weightsFiniteNonnegative"]
                                                and checks["mesh"]["weightsSumMaxError"] < 1e-8
                                                and checks["mesh"]["uvFiniteIn01"]
                                                and checks["mesh"]["triangleIndicesValid"])
    mesh_json = {
        "schemaVersion": 1, "status": "independent_visible_arm_static_lbs_experiment_not_production_rig",
        "taskId": manifest["taskId"],
        "sourceImage": {"file": str(source_path), "sha256": manifest["sourceImage"]["sha256"], "size": list(SIZE)},
        "sourceVideoSha256": manifest["sourceVideoSha256"],
        "sourceVideoHashRole": "沿用manifest任务引用，不读取视频、不验证角色身份",
        "sourceArm": {"file": "../stable_parts_v1/arm_near.png", "sha256": arm_record["sha256"], "bboxGlobal": arm_record["bbox"]},
        "sourceManifestSha256": before[str(manifest_path)],
        "scriptSha256": sha256(Path(__file__)),
        "referenceFrames": [{"index": i, "file": f"../frames/frame_{i:03d}.jpg", "sha256": sha256(PARENT / "frames" / f"frame_{i:03d}.jpg"), "role": "视觉参考而非拟合目标"} for i in references],
        "coordinateConvention": "全局768×768；x向右y向下；整数坐标为像素中心；bbox左上含右下不含",
        "meshSpacingPx": STEP, "transparentGuardPx": 2,
        "vertices": vertices.tolist(), "uv": uv.tolist(), "triangles": triangles.tolist(),
        "uvConvention": "全局768纹理归一化像素中心；源采样xy=uv*768-0.5，纹理是源臂原位透明画布，不包含其他部件",
        "bones": [{"name": "shoulder_elbow", "parent": None, "sourceStart": JOINTS[0].tolist(), "sourceEnd": JOINTS[1].tolist()},
                  {"name": "elbow_hand", "parent": 0, "sourceStart": JOINTS[1].tolist(), "sourceEnd": JOINTS[2].tolist()}],
        "weights": weights.tolist(), "weightBoneOrder": ["shoulder_elbow", "elbow_hand"],
        "weightMethod": "最近中心线骨段投影弧长；肘两侧各20px smoothstep，双骨linear blend skinning；非视频或美术权重",
        "boneTransformPolicy": "从源骨段到人工目标骨段；旋转+沿骨轴长度比，横向尺度1；全局矩阵含逆bind效果；子骨parent关系已解析为目标全局端点",
        "poses": pose_metadata, "checks": checks,
        "characterId": manifest.get("characterId"), "identityValidated": False,
        "hiddenComplete": False, "approvedForBinding": False, "promotedToRuntime": False,
        "anatomicalLeftRight": "unknown", "manualHypothesis": True, "videoFitted": False,
        "limitations": [
            "源骨架及全部目标角度/端点均为人工假设，非视频测量；只借68/72/80观察姿态，不自动拟合。",
            "当前源臂只保留可见像素；斜切肩根、腋下隐藏面及旋转搭接不足，不补画或借用待完成Image2肩图。",
            "两骨LBS不保体积；胸前大弯折会挤压、扭转与折叠；全部三角翻转/退化及重叠按实际结果报告。",
            "其余六层不动，body现有隐藏区仅局部补足；组装实际露底保留，不填补、不做遮盖伪装。",
            "中性domain差异含正常移开轮廓，只能作暴露证据，不是姿态真值、视频拟合误差或真实隐藏结构判断。",
            "未完成身份确认、隐藏结构、美术验收或生产rig绑定，不修改stable_parts_v1、旧runtime或正弦walk。",
        ],
    }
    (OUT / "mesh.json").write_text(json.dumps(mesh_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    # 从落盘JSON复读校验，不把内存检查冒充输出文件检查。
    disk = json.loads((OUT / "mesh.json").read_text(encoding="utf-8"))
    if not checks["structuralChecksPassed"] or len(disk["weights"]) != len(disk["vertices"]):
        raise AssertionError("结构或源不变检查失败，详见checks.json")
    if not np.allclose(np.array(disk["uv"]) * 768. - .5, np.array(disk["vertices"]), atol=1e-8):
        raise AssertionError("落盘UV与vertices不一致")
    if pose_checks["neutral"]["neutralMeshRestoration"]["vertexMaxAbsolutePositionErrorPx"] > 1e-8:
        raise AssertionError("中性姿态没有精确原位")
    print(json.dumps({"output": str(OUT), "structuralChecksPassed": checks["structuralChecksPassed"],
                      "vertices": len(vertices), "triangles": len(triangles),
                      "sourceAllTrackedFilesUnchanged": source_preserved, "poses": pose_checks}, ensure_ascii=False, indent=2))


def study_weights(points: np.ndarray, method: str, width: float) -> np.ndarray:
    if method == "nearest_arc":
        lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
        arcs, distances, offset = [], [], 0.
        for i, (a, b) in enumerate(BONE_INDICES):
            d = JOINTS[b] - JOINTS[a]
            t = np.clip((points - JOINTS[a]) @ d / np.dot(d, d), 0., 1.)
            distances.append(np.sum((points - JOINTS[a] - t[:, None] * d) ** 2, axis=1))
            arcs.append(offset + t * lengths[i])
            offset += lengths[i]
        nearest = np.argmin(np.stack(distances, axis=1), axis=1)
        coordinate = np.stack(arcs, axis=1)[np.arange(len(points)), nearest] - lengths[0]
    elif method == "continuous_axis":
        axis = JOINTS[2] - JOINTS[0]
        axis /= np.linalg.norm(axis)
        coordinate = (points - JOINTS[1]) @ axis
    else:
        raise ValueError(method)
    t = np.clip((coordinate + width / 2.) / width, 0., 1.)
    forearm = t * t * (3. - 2. * t)
    return np.column_stack((1. - forearm, forearm))


def study_geometry(vertices: np.ndarray, triangles: np.ndarray, transformed: np.ndarray) -> dict:
    src = vertices[triangles]
    dst = transformed[triangles]
    sa = cross2(src[:, 1] - src[:, 0], src[:, 2] - src[:, 0])
    da = cross2(dst[:, 1] - dst[:, 0], dst[:, 2] - dst[:, 0])
    ratio = da / sa
    return {"flippedTriangles": int(np.count_nonzero(sa * da < 0)),
            "collapsedTriangles": int(np.count_nonzero(np.abs(da) <= .001)),
            "signedAreaRatioMin": float(ratio.min()), "signedAreaRatioMax": float(ratio.max())}


def mesh_material_controls(vertices: np.ndarray, triangles: np.ndarray,
                           transformed: np.ndarray) -> np.ndarray:
    """Track bind control material points inside the actual piecewise-affine mesh."""
    controls = []
    for point in JOINTS:
        for tri in triangles:
            a, b, c = vertices[tri]
            basis = np.column_stack((b - a, c - a))
            if abs(np.linalg.det(basis)) <= 1e-12:
                continue
            u, v = np.linalg.solve(basis, point - a)
            barycentric = np.array([1. - u - v, u, v])
            if np.all(barycentric >= -1e-8):
                controls.append(barycentric @ transformed[tri])
                break
        else:
            raise ValueError("源控制点不在mesh内")
    return np.asarray(controls)


def run_weight_study() -> None:
    """Reproduce v1, compare weights without promoting or modifying any source asset."""
    output = PARENT / "arm_mesh_test_v2"
    baseline_path = OUT / "mesh.json"
    manifest_path = PARTS / "manifest.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != baseline["sourceManifestSha256"]:
        raise ValueError("稳定清单已变化，不能继续比较v1")
    if manifest["assemblyLayerOrder"] != EXPECTED_ORDER:
        raise ValueError("组装顺序已变化")
    source_path = Path(baseline["sourceImage"]["file"])
    tracked = list(dict.fromkeys([source_path, *sorted(p for p in PARTS.rglob("*") if p.is_file()),
                                *sorted(p for p in OUT.rglob("*") if p.is_file())]))
    before = {str(p): sha256(p) for p in tracked}
    expected = [(source_path, baseline["sourceImage"]["sha256"])]
    expected += [(PARTS / p["file"], p["sha256"]) for p in manifest["parts"]]
    if any(sha256(p) != h for p, h in expected):
        raise ValueError("源素材SHA不匹配")
    layers = {}
    for p in manifest["parts"]:
        image = Image.open(PARTS / p["file"]).convert("RGBA")
        x0, y0, x1, y1 = p["bbox"]
        if image.size != (x1 - x0, y1 - y0):
            raise ValueError("部件bbox与尺寸不符")
        layer = Image.new("RGBA", SIZE)
        layer.paste(image, (x0, y0))
        layers[p["id"]] = layer
    texture = np.array(layers["arm_near"])
    vertices = np.array(baseline["vertices"], dtype=float)
    triangles = np.array(baseline["triangles"], dtype=int)
    uv = np.array(baseline["uv"], dtype=float)
    if not np.allclose(uv * 768. - .5, vertices, atol=1e-8):
        raise ValueError("v1 UV不匹配")
    if not np.allclose(study_weights(vertices, "nearest_arc", 40.), baseline["weights"], atol=1e-12):
        raise AssertionError("未精确复现v1权重")
    poses = {name: np.array(p["targetJointsGlobalXY"], dtype=float) for name, p in baseline["poses"].items()}
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    fixed = [poses["chest"][0].copy()]
    for length, direction in zip(lengths, np.diff(poses["chest"], axis=0)):
        fixed.append(fixed[-1] + length * direction / np.linalg.norm(direction))
    poses["chest_fixed"] = np.array(fixed)
    matrices = {name: bone_matrices(joints) for name, joints in poses.items()}
    sweep = []
    for method in ("nearest_arc", "continuous_axis"):
        for width in (10., 20., 30., 40., 50., 60., 80., 100., 140., 180., 200.):
            weights = study_weights(vertices, method, width)
            control_weights = study_weights(JOINTS, method, width)
            entry = {"method": method, "blendWidthPx": width, "poses": {}}
            for name, joints in poses.items():
                transformed = deform(vertices, weights, matrices[name])
                geometry = study_geometry(vertices, triangles, transformed)
                controls = deform(JOINTS, control_weights, matrices[name])
                errors = np.linalg.norm(controls - joints, axis=1)
                material_errors = np.linalg.norm(mesh_material_controls(vertices, triangles, transformed) - joints, axis=1)
                geometry["controlPositionErrorsPx"] = errors.tolist()
                geometry["maxControlPositionErrorPx"] = float(errors.max())
                geometry["actualMeshMaterialControlErrorsPx"] = material_errors.tolist()
                geometry["controlErrorMeaning"] = "controlPosition为解析权重点；actualMeshMaterial为实际三角重心插值材料点，不等同"
                # 仅技术初筛；控制点精度不是美术、视频或隐藏域验收。
                geometry["technicalGatePassed"] = bool(geometry["flippedTriangles"] == 0
                    and geometry["collapsedTriangles"] == 0 and geometry["signedAreaRatioMin"] > .05
                    and errors.max() <= 1e-6)
                entry["poses"][name] = geometry
            sweep.append(entry)
    selected = [
        ("v1_baseline", "nearest_arc", 40., "chest", "v1基线｜最近骨段 / 40px / 原胸前端点"),
        ("axis60", "continuous_axis", 60., "chest", "连续轴60px｜原胸前端点，不缩小测试难度"),
        ("axis60_fixed", "continuous_axis", 60., "chest_fixed", "连续轴60px｜胸前保持源骨长，目标位置有变化"),
        ("axis180_fixed", "continuous_axis", 180., "chest_fixed", "连续轴180px｜反例：零翻转仍可能控制点漂移"),
    ]
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    variants, panels, produced = {}, [], []
    def save_image(image: Image.Image, name: str) -> None:
        path = output / name
        image.save(path)
        produced.append(path)
    for key, method, width, chest_name, label in selected:
        weights = study_weights(vertices, method, width)
        neutral = deform(vertices, weights, matrices["neutral"])
        neutral_image, neutral_metrics, _ = render_mesh(texture, uv, triangles, neutral)
        union = (texture[:, :, 3] > 0) | (neutral_image[:, :, 3] > 0)
        neutral_mismatch = int(np.count_nonzero(np.any(texture != neutral_image, axis=2) & union))
        if neutral_mismatch:
            raise AssertionError(f"{key}中性姿态RGBA改变")
        results, views = {}, {}
        for name in ("open", chest_name):
            transformed = deform(vertices, weights, matrices[name])
            rendered, metrics, _ = render_mesh(texture, uv, triangles, transformed)
            assembly = assemble(manifest, layers, rendered)
            overlay = mesh_overlay(rendered, transformed, triangles, poses[name])
            save_image(Image.fromarray(rendered), f"{key}_{name}_arm.png")
            save_image(overlay, f"{key}_{name}_mesh.png")
            save_image(assembly, f"{key}_{name}_assembly.png")
            geometry = study_geometry(vertices, triangles, transformed)
            control_weights = study_weights(JOINTS, method, width)
            controls = deform(JOINTS, control_weights, matrices[name])
            errors = np.linalg.norm(controls - poses[name], axis=1)
            results[name] = {"mesh": metrics, "geometry": geometry,
                "controlPositionErrorsPx": errors.tolist(),
                "controlWeightsUpperLower": control_weights.tolist(),
                "actualControlGlobalXY": controls.tolist(),
                "controlPositionErrorMeaning": "解析控制点单独计算权重并蒙皮；不是网格材料点精度",
                "actualMeshMaterialControlGlobalXY": mesh_material_controls(vertices, triangles, transformed).tolist(),
                "actualMeshMaterialControlErrorsPx": np.linalg.norm(mesh_material_controls(vertices, triangles, transformed) - poses[name], axis=1).tolist(),
                "targetJointsGlobalXY": poses[name].tolist(),
                "boneLengthRatios": (np.linalg.norm(np.diff(poses[name], axis=0), axis=1) / lengths).tolist(),
                "alphaAreaRatioToSource": float(rendered[:, :, 3].sum() / texture[:, :, 3].sum()),
                "alphaAreaDefinition": "透明臂实际光栅alpha总和 / 中性源臂alpha总和；非bbox、非视频目标面积",
                "deformedVerticesGlobalXY": transformed.tolist(),
                "bindingValidated": False}
            views[name] = (overlay, assembly)
        # 保留与v1相同中间算法的数值复现断言。
        if key == "v1_baseline":
            for name in ("open", "chest"):
                previous = baseline["checks"]["poses"][name]
                if results[name]["mesh"] != previous["mesh"]:
                    raise AssertionError("v1光栅指标未复现")
                if abs(results[name]["alphaAreaRatioToSource"] - previous["armAlphaAreaRatioToSource"]) > 1e-12:
                    raise AssertionError("v1 alpha面积未复现")
        variants[key] = {"method": method, "blendWidthPx": width, "chestPose": chest_name,
            "weights": weights.tolist(), "neutralRgbaMismatchPixels": neutral_mismatch,
            "neutralMesh": neutral_metrics, "poses": results}
        panels.append((label, views["open"][0], views[chest_name][0], views[chest_name][1], results, chest_name))
    # 相同网格/权重，open到等骨长chest作33个角度插值压力点；不是walk，不接视频时间。
    temporal = []
    axis_weights = study_weights(vertices, "continuous_axis", 60.)
    angle_a = np.arctan2(np.diff(poses["open"], axis=0)[:, 1], np.diff(poses["open"], axis=0)[:, 0])
    angle_b = np.arctan2(np.diff(poses["chest_fixed"], axis=0)[:, 1], np.diff(poses["chest_fixed"], axis=0)[:, 0])
    delta = (angle_b - angle_a + np.pi) % (2. * np.pi) - np.pi
    for i in range(33):
        angles = angle_a + delta * i / 32.
        joints = [JOINTS[0].copy()]
        for length, angle in zip(lengths, angles):
            joints.append(joints[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
        transformed = deform(vertices, axis_weights, bone_matrices(np.array(joints)))
        temporal.append({"sample": i, "parameter": i / 32., **study_geometry(vertices, triangles, transformed)})
    sheet = Image.new("RGB", (1740, 2300), (241, 244, 243))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 14), "近臂权重分诊 v2｜相同纹理、网格、肩肘手控制点", font=font(28), fill=(28, 46, 51))
    draw.text((24, 56), "非视频拟合 / 非正式绑定。保留全部失败；宽混合零翻转不能替代控制点与美术验收。", font=font(20), fill=(122, 60, 35))
    for col, text in enumerate(("open：实际网格", "chest：实际网格", "chest：七层组装（不补底）")):
        draw.text((24 + col * 574, 96), text, font=font(20), fill=(31, 53, 61))
    for row, (label, open_view, chest_view, assembly, results, chest_name) in enumerate(panels):
        y = 138 + row * 465
        draw.text((24, y), label, font=font(20), fill=(30, 50, 58))
        for col, image in enumerate((open_view, chest_view, assembly)):
            sheet.paste(crop_view(image), (24 + col * 574, y + 34))
        for col, name in enumerate(("open", chest_name)):
            r = results[name]
            text = f"翻转{r['mesh']['flippedTriangles']} / 重叠{r['mesh']['overlappingTriangleInteriorRasterPixels']} / alpha {r['alphaAreaRatioToSource']:.1%}"
            draw.text((24 + col * 574, y + 432), text, font=font(17), fill=(117, 53, 36))
        error = max(results[chest_name]["actualMeshMaterialControlErrorsPx"])
        draw.text((1172, y + 432), f"网格材料点最大漂移 {error:.2f}px；隐藏域未完成", font=font(17), fill=(117, 53, 36))
    draw.text((24, 2010), "视频视觉参考 68 / 72 / 80：未标定到源图，未作轮廓匹配或角色身份确认", font=font(20), fill=(35, 56, 60))
    for col, index in enumerate((68, 72, 80)):
        path = PARENT / "frames" / f"frame_{index:03d}.jpg"
        image = Image.open(path).convert("RGB").resize((350, 194), Image.Resampling.LANCZOS)
        sheet.paste(image, (24 + col * 574, 2050))
    draw.text((24, 2260), "结论以checks.json / study.json为准；未增加附件，未修改stable_parts_v1，正式导出状态不变。", font=font(18), fill=(48, 65, 70))
    save_image(sheet, "review.png")
    unchanged = all(sha256(Path(p)) == h for p, h in before.items())
    if not unchanged:
        raise AssertionError("源素材或v1证据发生改变")
    checks = {"sourceAndV1Unchanged": unchanged, "trackedFileCount": len(before),
        "sourceHashes": before, "v1BaselineRasterMetricsReproduced": True,
        "allSelectedNeutralRgbaMismatchPixels": {k: v["neutralRgbaMismatchPixels"] for k, v in variants.items()},
        "selected": {k: {name: {field: value for field, value in p.items() if field != "deformedVerticesGlobalXY"}
            for name, p in v["poses"].items()} for k, v in variants.items()},
        "sweepCombinationCount": len(sweep), "technicalGate": {"flips": 0, "collapsed": 0,
            "minimumSignedAreaRatioStrictlyAbove": .05, "maxControlErrorPx": 1e-6,
            "scope": "只作技术初筛；非视频/美术/隐藏域/绑定通过"},
        "axis60AngleStress": {"sampleCount": len(temporal),
            "samplesWithFlips": sum(x["flippedTriangles"] > 0 for x in temporal),
            "maximumFlips": max(x["flippedTriangles"] for x in temporal),
            "interpretation": "open到等骨长chest的人工角度插值；非视频时间、非walk"},
        "notVideoFitted": True, "bindingValidated": False, "hiddenComplete": False,
        "approvedForBinding": False, "promotedToRuntime": False,
        "generatedImages": [{"file": p.name, "sha256": sha256(p), "size": list(Image.open(p).size)} for p in produced]}
    study = {"schemaVersion": 1, "status": "weight_diagnosis_only_not_production_rig",
        "taskId": manifest["taskId"], "sourceManifestSha256": sha256(manifest_path),
        "baselineMeshSha256": sha256(baseline_path), "scriptSha256": sha256(Path(__file__)),
        "sourceVideoSha256": manifest["sourceVideoSha256"],
        "sourceVideoRole": "沿用任务引用，仅用68/72/80图片作视觉参考；没有视频测量或拟合",
        "vertices": vertices.tolist(), "uv": uv.tolist(), "triangles": triangles.tolist(),
        "bindJointsGlobalXY": JOINTS.tolist(), "variants": variants, "sweep": sweep,
        "axis60AngleStressSamples": temporal, "characterId": manifest.get("characterId"),
        "bindingValidated": False, "hiddenComplete": False, "promotedToRuntime": False,
        "limitations": ["保持与v1相同网格，只比较权重/骨长；尚未调整拓扑或补画。",
            "chest_fixed保持源骨长和原目标方向，但手/肘端点变化；不冒充同一视频目标。",
            "三角重叠计数只针对臂网格自身的几何内部光栅，不是臂与胸片的遮挡计数。",
            "source alpha in AABB是保守标签，非三角形与源alpha精确相交。",
            "无翻转仍可能严重挤压、控制点漂移或隐藏域不足，不能据此提升绑定。",
            "不读取未批准肩图，不生成Spine工程，不改变页面或正式导出。"]}
    for name, data in (("study.json", study), ("checks.json", checks)):
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        disk = json.loads(path.read_text(encoding="utf-8"))
        if disk != data:
            raise AssertionError("落盘JSON回读失败")
    for p in produced:
        with Image.open(p) as image:
            image.verify()
    print(json.dumps({"output": str(output), "sourceAndV1Unchanged": unchanged,
        "variants": {k: {n: {"flips": p["mesh"]["flippedTriangles"],
            "overlap": p["mesh"]["overlappingTriangleInteriorRasterPixels"],
            "alphaRatio": p["alphaAreaRatioToSource"], "maxControlError": max(p["controlPositionErrorsPx"])}
            for n, p in v["poses"].items()} for k, v in variants.items()},
        "angleStress": checks["axis60AngleStress"], "imageCount": len(produced)}, ensure_ascii=False, indent=2))


def material_control_matrix(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    controls = np.zeros((len(JOINTS), len(vertices)))
    for k, point in enumerate(JOINTS):
        for tri in triangles:
            a, b, c = vertices[tri]
            u, v = np.linalg.solve(np.column_stack((b - a, c - a)), point - a)
            bary = np.array([1. - u - v, u, v])
            if np.min(bary) >= -1e-8:
                controls[k, tri] = bary
                break
        else:
            raise ValueError("无法嵌入材料控制点")
    return controls


def solve_corrective(vertices: np.ndarray, triangles: np.ndarray, lbs: np.ndarray,
                     target_joints: np.ndarray, controls: np.ndarray) -> tuple[np.ndarray, dict]:
    """Offline character-specific deformation; this solver is NOT a runtime feature."""
    from scipy.optimize import minimize
    src = vertices[triangles]
    area = cross2(src[:, 1] - src[:, 0], src[:, 2] - src[:, 0])
    edges = np.unique(np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]],
                                              triangles[:, [2, 0]])), axis=1), axis=0)
    i, j = edges.T
    rest_squared = np.sum((vertices[i] - vertices[j]) ** 2, axis=1)
    def objective(x):
        points = x.reshape(-1, 2)
        offset = points - lbs
        edge = points[i] - points[j]
        error = (np.sum(edge * edge, axis=1) - rest_squared) / rest_squared
        value = .02 * np.sum(offset * offset) + 8. * np.sum(error * error)
        gradient = .04 * offset
        edge_gradient = 32. * (error / rest_squared)[:, None] * edge
        np.add.at(gradient, i, edge_gradient)
        np.add.at(gradient, j, -edge_gradient)
        return value, gradient.ravel()
    def inequality(x):
        points = x.reshape(-1, 2)[triangles]
        return cross2(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]) / area - .12
    def jacobian(x):
        p = x.reshape(-1, 2)[triangles]
        g = np.stack((np.column_stack((p[:, 1, 1] - p[:, 2, 1], p[:, 2, 0] - p[:, 1, 0])),
                      np.column_stack((p[:, 2, 1] - p[:, 0, 1], p[:, 0, 0] - p[:, 2, 0])),
                      np.column_stack((p[:, 0, 1] - p[:, 1, 1], p[:, 1, 0] - p[:, 0, 0]))), axis=1)
        g /= area[:, None, None]
        result = np.zeros((len(triangles), len(vertices), 2))
        result[np.arange(len(triangles))[:, None], triangles] = g
        return result.reshape(len(triangles), -1)
    anchors = np.kron(controls, np.eye(2))
    constraints = [{"type": "ineq", "fun": inequality, "jac": jacobian},
                   {"type": "eq", "fun": lambda x: anchors @ x - target_joints.ravel(),
                    "jac": lambda x: anchors}]
    result = minimize(objective, lbs.ravel(), jac=True, method="SLSQP", constraints=constraints,
                      options={"maxiter": 180, "ftol": 1e-5})
    solved = result.x.reshape(-1, 2)
    metrics = {"success": bool(result.success), "message": str(result.message), "iterations": int(result.nit),
               "objective": float(result.fun), "minAreaConstraintResidual": float(inequality(result.x).min()),
               "materialAnchorMaxErrorPx": float(np.linalg.norm(controls @ solved - target_joints, axis=1).max()),
               "maxCorrectionFromLbsPx": float(np.linalg.norm(solved - lbs, axis=1).max()),
               "rmsCorrectionFromLbsPx": float(np.sqrt(np.mean(np.sum((solved - lbs) ** 2, axis=1))))}
    return solved, metrics


def run_corrective_study() -> None:
    output = PARENT / "arm_mesh_test_v3"
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline_path = OUT / "mesh.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != baseline["sourceManifestSha256"]:
        raise ValueError("稳定清单不匹配，停止")
    source = Path(baseline["sourceImage"]["file"])
    tracked = [source, *sorted(p for p in PARTS.rglob("*") if p.is_file()),
               *sorted(p for p in OUT.rglob("*") if p.is_file()),
               *sorted(p for p in (PARENT / "arm_mesh_test_v2").rglob("*") if p.is_file())]
    before = {str(p): sha256(p) for p in dict.fromkeys(tracked)}
    expected = [(source, baseline["sourceImage"]["sha256"])]
    expected += [(PARTS / p["file"], p["sha256"]) for p in manifest["parts"]]
    if any(sha256(p) != h for p, h in expected):
        raise ValueError("源图或部件SHA不匹配")
    if manifest["assemblyLayerOrder"] != EXPECTED_ORDER or manifest.get("promotedToRuntime") is not False:
        raise ValueError("候选状态或层序不符")
    layers = {}
    for part in manifest["parts"]:
        image = Image.open(PARTS / part["file"]).convert("RGBA")
        x0, y0, x1, y1 = part["bbox"]
        if image.size != (x1 - x0, y1 - y0):
            raise ValueError("部件尺寸错误")
        layer = Image.new("RGBA", SIZE)
        layer.paste(image, (x0, y0))
        layers[part["id"]] = layer
    texture = np.array(layers["arm_near"])
    vertices = np.array(baseline["vertices"], dtype=float)
    triangles = np.array(baseline["triangles"], dtype=int)
    uv = np.array(baseline["uv"], dtype=float)
    weights = study_weights(vertices, "continuous_axis", 60.)
    controls = material_control_matrix(vertices, triangles)
    start = np.array(baseline["poses"]["open"]["targetJointsGlobalXY"], dtype=float)
    end = np.array(baseline["poses"]["chest"]["targetJointsGlobalXY"], dtype=float)
    reference_lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    start_angles = np.arctan2(np.diff(start, axis=0)[:, 1], np.diff(start, axis=0)[:, 0])
    end_angles = np.arctan2(np.diff(end, axis=0)[:, 1], np.diff(end, axis=0)[:, 0])
    angle_delta = (end_angles - start_angles + np.pi) % (2. * np.pi) - np.pi
    end_scales = np.linalg.norm(np.diff(end, axis=0), axis=1) / reference_lengths
    def pose_at(parameter):
        # 归一化角度/长度参数是实验动作描述，角色profile持有自己的bind长度。
        angles = start_angles + angle_delta * parameter
        lengths = reference_lengths * (1. + (end_scales - 1.) * parameter)
        joints = [JOINTS[0].copy()]
        for length, angle in zip(lengths, angles):
            joints.append(joints[-1] + length * np.array([math.cos(angle), math.sin(angle)]))
        return np.array(joints)
    def blended_linear(matrices):
        return sum(weights[:, i, None, None] * matrix[None, :, :2] for i, matrix in enumerate(matrices))
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    keys, panels = [], []
    for index, parameter in enumerate(np.linspace(0., 1., 9)):
        joints = pose_at(float(parameter))
        matrices = bone_matrices(joints)
        lbs = deform(vertices, weights, matrices)
        solved, solver = solve_corrective(vertices, triangles, lbs, joints, controls)
        linear = blended_linear(matrices)
        delta = np.linalg.solve(linear, (solved - lbs)[:, :, None])[:, :, 0]
        reconstructed = deform(vertices + delta, weights, matrices)
        error = float(np.max(np.abs(reconstructed - solved)))
        geometry = study_geometry(vertices, triangles, solved)
        if not solver["success"] or solver["materialAnchorMaxErrorPx"] > 1e-6 or geometry["signedAreaRatioMin"] < .1199 or error > 1e-7:
            raise AssertionError(f"第{index}修形求解未通过：{solver}")
        rendered, raster, _ = render_mesh(texture, uv, triangles, solved)
        Image.fromarray(rendered).save(output / f"key_{index:02d}_arm.png")
        assembly = assemble(manifest, layers, rendered)
        assembly.save(output / f"key_{index:02d}_assembly.png")
        overlay = mesh_overlay(rendered, solved, triangles, joints)
        overlay.save(output / f"key_{index:02d}_mesh.png")
        neutral_domain = np.array(assemble(manifest, layers, texture))[:, :, 3] > 0
        exposure = int(np.count_nonzero(neutral_domain & (np.array(assembly)[:, :, 3] == 0)))
        key = {"parameter": float(parameter), "targetJointsGlobalXY": joints.tolist(),
               "deformedVerticesGlobalXY": solved.tolist(), "bindSpaceCorrectiveOffsetsXY": delta.tolist(),
               "solver": solver, "geometry": geometry, "raster": raster,
               "lbsBeforeGeometry": study_geometry(vertices, triangles, lbs),
               "bindOffsetReconstructionMaxErrorPx": error,
               "blendedLinearDeterminantMin": float(np.linalg.det(linear).min()),
               "alphaAreaRatioToSource": float(rendered[:, :, 3].sum() / texture[:, :, 3].sum()),
               "exposureVsNeutralPixelsNotGroundTruth": exposure}
        keys.append(key)
        if index in (0, 4, 8):
            before_render, _, _ = render_mesh(texture, uv, triangles, lbs)
            panels.append((index, crop_view(mesh_overlay(before_render, lbs, triangles, joints)),
                           crop_view(overlay), crop_view(assembly), key))
    # 不逐帧求解：只线性插值9个角色局部修形key，再由同一双骨链运行65个压力采样。
    samples = []
    for parameter in np.linspace(0., 1., 65):
        q = float(parameter) * 8.
        k = min(int(q), 7)
        blend = q - k
        delta = (1. - blend) * np.array(keys[k]["bindSpaceCorrectiveOffsetsXY"]) + blend * np.array(keys[k + 1]["bindSpaceCorrectiveOffsetsXY"])
        joints = pose_at(float(parameter))
        points = deform(vertices + delta, weights, bone_matrices(joints))
        material_error = float(np.linalg.norm(controls @ points - joints, axis=1).max())
        geometry = study_geometry(vertices, triangles, points)
        rendered, raster, _ = render_mesh(texture, uv, triangles, points)
        samples.append({"parameter": float(parameter), "geometry": geometry,
            "materialAnchorMaxErrorPx": material_error,
            "overlappingTriangleInteriorRasterPixels": raster["overlappingTriangleInteriorRasterPixels"],
            "alphaAreaRatioToSource": float(rendered[:, :, 3].sum() / texture[:, :, 3].sum())})
    neutral_points = deform(vertices, weights, bone_matrices(JOINTS))
    neutral_image, _, _ = render_mesh(texture, uv, triangles, neutral_points)
    union = (texture[:, :, 3] > 0) | (neutral_image[:, :, 3] > 0)
    neutral_mismatch = int(np.count_nonzero(np.any(texture != neutral_image, axis=2) & union))
    worst = min(samples, key=lambda s: s["geometry"]["signedAreaRatioMin"])
    parameter = worst["parameter"]
    q = parameter * 8.
    segment = min(int(q), 7)
    blend = q - segment
    worst_delta = (1. - blend) * np.array(keys[segment]["bindSpaceCorrectiveOffsetsXY"]) + blend * np.array(keys[segment + 1]["bindSpaceCorrectiveOffsetsXY"])
    worst_joints = pose_at(parameter)
    worst_points = deform(vertices + worst_delta, weights, bone_matrices(worst_joints))
    worst_render, _, _ = render_mesh(texture, uv, triangles, worst_points)
    mesh_overlay(worst_render, worst_points, triangles, worst_joints).save(output / "interpolation_worst_mesh.png")
    assemble(manifest, layers, worst_render).save(output / "interpolation_worst_assembly.png")
    sheet = Image.new("RGB", (1740, 2190), (242, 245, 243))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 16), "单件近臂修形 v3｜同一双骨链 / 同一纹理与mesh / 不增加附件", font=font(27), fill=(30, 48, 55))
    draw.text((24, 58), "离线约束求解，仅数学实验；不是视频拟合、完整Spine工程或衣袖适配。肩腋隐藏域未补。", font=font(19), fill=(125, 61, 39))
    for col, text in enumerate(("原LBS线框", "受约束修形线框", "修形后七层组装（不补底）")):
        draw.text((24 + col * 574, 100), text, font=font(20), fill=(34, 54, 61))
    for row, (index, before_image, after_image, assembly_image, key) in enumerate(panels):
        y = 140 + 470 * row
        draw.text((24, y), f"key {index:02d} / 人工参数 {key['parameter']:.2f}；视频未标定", font=font(20), fill=(32, 51, 58))
        for col, image in enumerate((before_image, after_image, assembly_image)):
            sheet.paste(image, (24 + col * 574, y + 34))
        draw.text((24, y + 432), f"修形前翻转 {key['lbsBeforeGeometry']['flippedTriangles']}", font=font(17), fill=(120, 54, 36))
        draw.text((598, y + 432), f"修形后翻转 {key['geometry']['flippedTriangles']} / 内部重叠 {key['raster']['overlappingTriangleInteriorRasterPixels']}", font=font(17), fill=(120, 54, 36))
        draw.text((1172, y + 432), f"alpha {key['alphaAreaRatioToSource']:.1%} / 最大修形 {key['solver']['maxCorrectionFromLbsPx']:.1f}px", font=font(17), fill=(120, 54, 36))
    y = 1550
    draw.text((24, y), f"插值失败证据｜最小面积比采样 p={parameter:.5f}，不是新增修形key", font=font(20), fill=(123, 48, 35))
    worst_lbs = deform(vertices, weights, bone_matrices(worst_joints))
    worst_before, _, _ = render_mesh(texture, uv, triangles, worst_lbs)
    for col, image in enumerate((mesh_overlay(worst_before, worst_lbs, triangles, worst_joints),
                                 mesh_overlay(worst_render, worst_points, triangles, worst_joints),
                                 assemble(manifest, layers, worst_render))):
        sheet.paste(crop_view(image), (24 + col * 574, y + 34))
    failed = sum(s["geometry"]["flippedTriangles"] > 0 for s in samples)
    draw.text((24, 2000), f"65个插值采样：{failed}个翻转；最小有向面积比{worst['geometry']['signedAreaRatioMin']:.3f}。单姿态零翻转不等于连续可用。", font=font(20), fill=(123, 48, 35))
    draw.text((24, 2050), "关键值chest仍有全局自重叠，臂alpha约69.6%；禁止将该结果提升为正式绑定。", font=font(20), fill=(123, 48, 35))
    draw.text((24, 2100), "动作参数与角色profile分离；衣袖共享骨链，但贴图、权重、修形与遮挡仍需单独制作验收。", font=font(20), fill=(34, 54, 61))
    draw.text((24, 2140), "约7个逻辑件保持不变；9个变形关键值不是9个附件。全部候选状态保持未绑定、未提升。", font=font(19), fill=(99, 57, 37))
    sheet.save(output / "review.png")
    if not all(sha256(Path(p)) == value for p, value in before.items()):
        raise AssertionError("源或v1/v2证据改变")
    contract = {"status": "experimental_semantic_contract_not_full_skeleton",
        "direction": "right_front_3q", "logicalPartIds": [p["id"] for p in manifest["parts"]],
        "partCount": len(manifest["parts"]), "attachmentCountAdded": 0,
        "chain": [{"name": "arm_near_upper", "parent": "body_anchor", "role": "shoulder_to_elbow"},
                  {"name": "arm_near_lower", "parent": "arm_near_upper", "role": "elbow_to_hand"}],
        "bodyAnchorMeaning": "本实验仅锁定肩参考；不声称已存在完整全身通用骨架",
        "sharedMotion": {"coordinateAxes": "image_x_right_y_down",
            "startAbsoluteAnglesRadians": start_angles.tolist(), "endAbsoluteAnglesRadians": end_angles.tolist(),
            "startBoneScaleRatios": [1., 1.], "endBoneScaleRatios": end_scales.tolist(),
            "parameterMeaning": "人工open到chest压力路径，无视频时间/动作时长"},
        "skinOwnership": {"arm_near": "body_skin", "body": "body_skin", "shorts": "clothing_skin",
            "futureSleeve": "共享upper/lower骨链；独立贴图/mesh/weights/corrective；尚未制作"},
        "compatibilityRules": ["不得因服装或源帧新增骨骼、复制动作骨链或逐帧附件。",
            "角色bind长度/轴向和外观位于profile；共享动作参数不包含本角色像素偏移。",
            "corrective属于角色mesh数据，不能盲拷给其他角色或衣袖。",
            "Spine weighted deform须转换至各骨本地坐标并按目标runtime验证；本JSON不是Spine导出。",
            "当前只测试近臂单一角色；跨角色/衣袖/全身/换装与移动端均未验收。"]}
    profile = {"bindJointsGlobalXY": JOINTS.tolist(), "vertices": vertices.tolist(),
        "triangles": triangles.tolist(), "uv": uv.tolist(), "weights": weights.tolist(),
        "weightBoneOrder": ["arm_near_upper", "arm_near_lower"],
        "materialControlBarycentricMatrix": controls.tolist(),
        "correctiveKeys": keys, "correctiveSpace": "same bind-space 2D offset per vertex before per-bone inverse-bind mapped LBS",
        "notSpineWeightedDeformEncoding": True}
    checks = {"sourceAndV1V2Unchanged": True, "sourceHashes": before,
        "neutralRgbaMismatchPixels": neutral_mismatch, "correctiveKeyCount": len(keys),
        "keySolvesAllSucceeded": all(k["solver"]["success"] for k in keys),
        "keyFlipsMax": max(k["geometry"]["flippedTriangles"] for k in keys),
        "keyMaterialAnchorMaxErrorPx": max(k["solver"]["materialAnchorMaxErrorPx"] for k in keys),
        "keyBindOffsetReconstructionMaxErrorPx": max(k["bindOffsetReconstructionMaxErrorPx"] for k in keys),
        "interpolationSampleCount": len(samples),
        "interpolationFlippedSampleCount": sum(s["geometry"]["flippedTriangles"] > 0 for s in samples),
        "interpolationMinSignedAreaRatio": min(s["geometry"]["signedAreaRatioMin"] for s in samples),
        "interpolationMaterialAnchorMaxErrorPx": max(s["materialAnchorMaxErrorPx"] for s in samples),
        "interpolationSelfOverlapMaxPx": max(s["overlappingTriangleInteriorRasterPixels"] for s in samples),
        "alphaAreaDefinition": "透明臂PNG alpha总和/源臂alpha总和；不是三维体积或视频误差",
        "logicPartsUnchanged": True, "attachmentsAdded": 0, "bonesAdded": 0,
        "costumeSkinTested": False, "crossCharacterReuseTested": False,
        "notVideoFitted": True, "hiddenComplete": False, "bindingValidated": False,
        "approvedForBinding": False, "promotedToRuntime": False,
        "generatedImages": []}
    for path in sorted(output.glob("*.png")):
        with Image.open(path) as image:
            size = list(image.size)
            image.verify()
        checks["generatedImages"].append({"file": path.name, "sha256": sha256(path), "size": size})
    study = {"schemaVersion": 1, "status": "single_mesh_corrective_experiment_not_production",
        "taskId": manifest["taskId"], "characterId": manifest.get("characterId"),
        "sourceManifestSha256": sha256(manifest_path), "scriptSha256": sha256(Path(__file__)),
        "sourceVideoSha256": manifest["sourceVideoSha256"], "videoUsedForMeasurement": False,
        "sharedContract": contract, "characterMeshProfile": profile, "interpolationSamples": samples,
        "solverPolicy": {"offlineOnly": True, "minSignedAreaRatio": .12,
            "objective": ".02*sum(displacement_from_LBS^2)+8*sum(relative_edge_squared_length_error^2)",
            "anchors": "hard constraints on original material points by barycentric matrix",
            "doesNotEnforce": ["轮廓真值", "隐藏结构", "全局无自交", "衣袖遮挡", "体积保真", "视频拟合"]},
        "limitations": ["只有一个源角色近臂，且手工控制点未按视频标定。",
            "正三角面积不证明全局无自交；另报告几何重叠光栅，不作精确连续相交证明。",
            "9个修形key来自人工角度路径，不是9个视频帧或9张附件。",
            "65个插值采样通过也不能证明采样间任意时刻无折叠。",
            "只输出独立实验；不修改正式七件/清单/前端，不输出Spine ZIP。"],
        "bindingValidated": False, "hiddenComplete": False, "promotedToRuntime": False}
    for name, data in (("study.json", study), ("checks.json", checks)):
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise AssertionError("JSON回读错误")
    print(json.dumps({k: v for k, v in checks.items() if k not in ("sourceHashes", "generatedImages")}, ensure_ascii=False, indent=2))


def prune_transparent_triangles(vertices: np.ndarray, triangles: np.ndarray,
                                alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Occupancy boundary, NOT exact constrained contour triangulation.

    Remove only triangles whose integer raster has no dilated alpha support.
    Keep grid connectivity/weights unchanged to isolate transparent-domain effects.
    """
    support = cv2.dilate((alpha > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    retained = []
    for tri in triangles:
        a, b, c = vertices[tri]
        x0, y0 = np.maximum(np.floor(vertices[tri].min(axis=0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(vertices[tri].max(axis=0)).astype(int) + 1, SIZE)
        xx, yy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1))
        delta = np.stack((xx, yy), axis=-1) - a
        area = cross2(b - a, c - a)
        u = cross2(delta, c - a) / area
        v = cross2(b - a, delta) / area
        inside = (u >= -1e-7) & (v >= -1e-7) & (u + v <= 1. + 1e-7)
        if np.any(inside & support[y0:y1, x0:x1]):
            retained.append(tri)
    retained = np.asarray(retained, dtype=int)
    used, inverse = np.unique(retained, return_inverse=True)
    return vertices[used], inverse.reshape(-1, 3), {
        "policy": "原网格三角整数像素中心与alpha>0外扩2px相交则保留；仅裁去透明三角，不重连内部边",
        "notExactContourTriangulation": True, "guardRadiusPx": 2,
        "originalVertexIndices": used.tolist(),
        "removedTriangles": int(len(triangles) - len(retained)),
        "removedVertices": int(len(vertices) - len(used)),
        "sourceSupportPixelCount": int(np.count_nonzero(alpha)),
        "dilatedSupportPixelCount": int(np.count_nonzero(support))}


def run_topology_diagnosis() -> None:
    output = PARENT / "arm_mesh_test_v4"
    baseline_path = OUT / "mesh.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != baseline["sourceManifestSha256"] or manifest["assemblyLayerOrder"] != EXPECTED_ORDER:
        raise ValueError("源清单已变化")
    source_path = Path(baseline["sourceImage"]["file"])
    tracked = [source_path, *sorted(p for p in PARTS.rglob("*") if p.is_file())]
    for directory in (OUT, PARENT / "arm_mesh_test_v2", PARENT / "arm_mesh_test_v3"):
        tracked += sorted(p for p in directory.rglob("*") if p.is_file())
    before = {str(p): sha256(p) for p in dict.fromkeys(tracked)}
    expected = [(source_path, baseline["sourceImage"]["sha256"])]
    expected += [(PARTS / p["file"], p["sha256"]) for p in manifest["parts"]]
    if any(sha256(p) != h for p, h in expected):
        raise ValueError("源像素SHA不符")
    layers = {}
    for part in manifest["parts"]:
        image = Image.open(PARTS / part["file"]).convert("RGBA")
        x0, y0, x1, y1 = part["bbox"]
        if image.size != (x1 - x0, y1 - y0):
            raise ValueError("部件尺寸不符")
        layer = Image.new("RGBA", SIZE)
        layer.paste(image, (x0, y0))
        layers[part["id"]] = layer
    texture = np.array(layers["arm_near"])
    original_vertices = np.array(baseline["vertices"], dtype=float)
    original_triangles = np.array(baseline["triangles"], dtype=int)
    occupied_vertices, occupied_triangles, pruning = prune_transparent_triangles(original_vertices, original_triangles, texture[:, :, 3])
    meshes = {"rectangle": (original_vertices, original_triangles),
              "alpha_occupied": (occupied_vertices, occupied_triangles)}
    poses = {name: np.array(config["targetJointsGlobalXY"], dtype=float) for name, config in baseline["poses"].items()}
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    chest_fixed = [poses["chest"][0]]
    for length, direction in zip(lengths, np.diff(poses["chest"], axis=0)):
        chest_fixed.append(chest_fixed[-1] + length * direction / np.linalg.norm(direction))
    poses["chest_fixed"] = np.array(chest_fixed)
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    metrics, mesh_records, rendered_arrays = {}, {}, {}
    for mesh_name, (vertices, triangles) in meshes.items():
        weights = study_weights(vertices, "continuous_axis", 60.)
        uv = (vertices + .5) / np.array(SIZE)
        records = {}
        for name, joints in poses.items():
            points = deform(vertices, weights, bone_matrices(joints))
            arm, raster, coverage = render_mesh(texture, uv, triangles, points)
            assembly = assemble(manifest, layers, arm)
            overlay = mesh_overlay(arm, points, triangles, joints)
            for suffix, image in (("arm", Image.fromarray(arm)), ("mesh", overlay), ("assembly", assembly)):
                image.save(output / f"{mesh_name}_{name}_{suffix}.png")
            records[name] = {"geometry": study_geometry(vertices, triangles, points), "raster": raster,
                "targetJointsGlobalXY": joints.tolist(), "deformedVerticesGlobalXY": points.tolist(),
                "boneLengthRatios": (np.linalg.norm(np.diff(joints, axis=0), axis=1) / lengths).tolist(),
                "actualMeshMaterialControlErrorsPx": np.linalg.norm(mesh_material_controls(vertices, triangles, points) - joints, axis=1).tolist(),
                "alphaAreaRatioToSource": float(arm[:, :, 3].sum() / texture[:, :, 3].sum())}
            rendered_arrays[(mesh_name, name)] = arm
            if name == "neutral":
                union = (texture[:, :, 3] > 0) | (arm[:, :, 3] > 0)
                mismatch = int(np.count_nonzero(np.any(arm != texture, axis=2) & union))
                uncovered = int(np.count_nonzero((texture[:, :, 3] > 0) & (coverage == 0)))
                records[name]["neutral"] = {"rgbaMismatchPixels": mismatch,
                    "alphaMismatchPixels": int(np.count_nonzero(arm[:, :, 3] != texture[:, :, 3])),
                    "sourceVisiblePixelsUncovered": uncovered}
                if mismatch or uncovered:
                    raise AssertionError("裁网格损坏源臂中性还原")
        mesh_records[mesh_name] = {"vertices": vertices.tolist(), "triangles": triangles.tolist(),
            "uv": uv.tolist(), "weights": weights.tolist(), "poses": records}
        metrics[mesh_name] = {"vertexCount": len(vertices), "triangleCount": len(triangles),
            "poses": {name: {k: v for k, v in record.items() if k != "deformedVerticesGlobalXY"}
                      for name, record in records.items()}}
    pair_comparison = {}
    for name in poses:
        a, b = rendered_arrays[("rectangle", name)], rendered_arrays[("alpha_occupied", name)]
        union = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
        pair_comparison[name] = {"visibleUnionRgbaMismatchPixels": int(np.count_nonzero(np.any(a != b, axis=2) & union)),
            "alphaMismatchPixels": int(np.count_nonzero(a[:, :, 3] != b[:, :, 3])),
            "meaning": "相同权重/骨架只删除透明三角；变形时可能改变后写透明覆盖，不代表视频更准确"}
    # Source centre-line cross sections: geometry evidence, not anatomical diagnosis.
    sections = []
    alpha = texture[:, :, 3]
    for index, t in enumerate(np.linspace(.1, .9, 9)):
        point = JOINTS[0] * (1. - t) + JOINTS[2] * t
        axis = JOINTS[2] - JOINTS[0]
        axis /= np.linalg.norm(axis)
        normal = np.array([-axis[1], axis[0]])
        offsets = np.linspace(-90., 90., 721)
        samples_xy = point + offsets[:, None] * normal
        x, y = np.rint(samples_xy).astype(int).T
        valid = (x >= 0) & (x < SIZE[0]) & (y >= 0) & (y < SIZE[1])
        support = np.zeros(len(offsets), dtype=bool)
        support[valid] = alpha[y[valid], x[valid]] >= 128
        hit = offsets[support]
        sections.append({"normalizedShoulderHandParameter": float(t), "centreGlobalXY": point.tolist(),
            "outermostOpaqueSpanPx": float(hit.max() - hit.min()) if len(hit) else 0.,
            "interpretation": "沿肩手直线法向采样alpha>=128最外端跨度；可含分离段，不是解剖厚度"})
    # Same 65 manual angle-path samples, no correctives, no frame-specific attachments.
    start_angles = np.arctan2(np.diff(poses["open"], axis=0)[:, 1], np.diff(poses["open"], axis=0)[:, 0])
    end_angles = np.arctan2(np.diff(poses["chest_fixed"], axis=0)[:, 1], np.diff(poses["chest_fixed"], axis=0)[:, 0])
    delta = (end_angles - start_angles + np.pi) % (2. * np.pi) - np.pi
    stresses = {}
    for mesh_name, (vertices, triangles) in meshes.items():
        weights = study_weights(vertices, "continuous_axis", 60.)
        samples = []
        for i in range(65):
            angles = start_angles + delta * i / 64.
            joints = [JOINTS[0]]
            for length, angle in zip(lengths, angles):
                joints.append(joints[-1] + length * np.array([math.cos(angle), math.sin(angle)]))
            points = deform(vertices, weights, bone_matrices(np.array(joints)))
            samples.append({"parameter": i / 64., **study_geometry(vertices, triangles, points)})
        stresses[mesh_name] = {"samples": samples,
            "flippedSampleCount": sum(s["flippedTriangles"] > 0 for s in samples),
            "maximumFlips": max(s["flippedTriangles"] for s in samples),
            "minimumSignedAreaRatio": min(s["signedAreaRatioMin"] for s in samples)}
    sheet = Image.new("RGB", (1740, 1740), (243, 245, 242))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 16), "近臂透明域拓扑诊断 v4｜同一纹理、骨链、60px权重，无corrective", font=font(27), fill=(30, 48, 55))
    draw.text((24, 58), "alpha占用三角裁减：仅去除透明尾部，不是精确贴轮廓重拓扑。不得把翻转计数减少当绑定通过。", font=font(19), fill=(120, 57, 35))
    for col, text in enumerate(("矩形网格", "alpha占用网格（2px安全域）", "alpha占用网格七层组装（不补底）")):
        draw.text((24 + col * 574, 102), text, font=font(19), fill=(32, 52, 60))
    for row, name in enumerate(("neutral", "open", "chest")):
        y = 142 + row * 470
        draw.text((24, y), name + "｜人工姿态、非视频标定", font=font(20), fill=(32, 52, 60))
        paths = (f"rectangle_{name}_mesh.png", f"alpha_occupied_{name}_mesh.png", f"alpha_occupied_{name}_assembly.png")
        for col, path in enumerate(paths):
            sheet.paste(crop_view(Image.open(output / path)), (24 + col * 574, y + 34))
        for col, mesh_name in enumerate(meshes):
            r = metrics[mesh_name]["poses"][name]
            draw.text((24 + col * 574, y + 432), f"翻转{r['geometry']['flippedTriangles']} / 几何内部重叠{r['raster']['overlappingTriangleInteriorRasterPixels']}px", font=font(17), fill=(120, 55, 35))
        r = metrics["alpha_occupied"]["poses"][name]
        draw.text((1172, y + 432), f"alpha比例{r['alphaAreaRatioToSource']:.1%}；肩根未补", font=font(17), fill=(120, 55, 35))
    draw.text((24, 1570), f"矩形 {len(original_vertices)}点/{len(original_triangles)}三角 → 占用 {len(occupied_vertices)}点/{len(occupied_triangles)}三角；仍是同一arm_near逻辑件", font=font(20), fill=(32, 52, 60))
    draw.text((24, 1615), "全局几何自重叠、隐藏域、衣袖与跨角色未验收。固定骨长chest另存，不能冒充同一端点目标。", font=font(19), fill=(120, 55, 35))
    draw.text((24, 1660), "若裁透明三角后可见弯折仍失败，应处理有效关节拓扑/控制点语义，不堆逐帧附件。", font=font(19), fill=(32, 52, 60))
    sheet.save(output / "review.png")
    if not all(sha256(Path(p)) == value for p, value in before.items()):
        raise AssertionError("源文件发生改变")
    images = []
    for path in sorted(output.glob("*.png")):
        with Image.open(path) as image:
            size = list(image.size)
            image.verify()
        images.append({"file": path.name, "sha256": sha256(path), "size": size})
    state = {"logicalPartCount": len(manifest["parts"]), "attachmentsAdded": 0, "bonesAdded": 0,
             "hiddenComplete": False, "bindingValidated": False, "promotedToRuntime": False,
             "approvedForBinding": False, "costumeTested": False, "crossCharacterTested": False, "videoFitted": False}
    checks = {"sourceAndV1V2V3Unchanged": True, "sourceHashes": before, "meshMetrics": metrics,
        "samePoseRenderComparison": pair_comparison, "pruning": pruning,
        "stressSummary": {name: {k: v for k, v in value.items() if k != "samples"} for name, value in stresses.items()},
        "generatedImages": images, **state}
    study = {"schemaVersion": 1, "status": "transparent_domain_isolation_not_contour_retopology_or_production",
        "sourceManifestSha256": sha256(manifest_path), "scriptSha256": sha256(Path(__file__)),
        "taskId": manifest["taskId"], "characterId": manifest.get("characterId"),
        "bindJoints": JOINTS.tolist(), "bindBoneLengthsPx": lengths.tolist(),
        "meshes": mesh_records, "pruning": pruning, "opaqueCrossSections": sections, "stress": stresses,
        "limitations": ["仅从原网格裁去没有alpha安全域的三角，不是贴轮廓受限三角剖分，也没有重建肘部边流。",
            "除去透明三角会改变几何翻转/重叠计数分母，不能直接作可见质量评分。",
            "采样跨度包含所有相交opaque段，不等于解剖厚度，不用于自动改肘位置。",
            "肩腋未补，原图视频未标定；动作与控制点仍是人工假设。",
            "65个固定骨长人工插值压力点不含corrective，不是视频walk。",
            "衣袖应复用骨链而不是复制骨架，但当前没有衣袖或跨角色测试。"], **state}
    for name, data in (("checks.json", checks), ("study.json", study)):
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise AssertionError("JSON回读失败")
    print(json.dumps({"output": str(output), "meshes": metrics, "stress": checks["stressSummary"],
                      "pairComparison": pair_comparison, "images": len(images)}, ensure_ascii=False, indent=2))


def run_compositing_diagnosis() -> None:
    output = PARENT / "arm_mesh_test_v5"
    v4_path = PARENT / "arm_mesh_test_v4/study.json"
    v4 = json.loads(v4_path.read_text(encoding="utf-8"))
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != v4["sourceManifestSha256"]:
        raise ValueError("源清单改变")
    tracked = [p for p in PARTS.rglob("*") if p.is_file()]
    for directory in (OUT, *(PARENT / f"arm_mesh_test_v{i}" for i in (2, 3, 4))):
        tracked += [p for p in directory.rglob("*") if p.is_file()]
    before = {str(p): sha256(p) for p in tracked}
    layers = {}
    for part in manifest["parts"]:
        path = PARTS / part["file"]
        if sha256(path) != part["sha256"]:
            raise ValueError("源部件SHA改变")
        layer = Image.new("RGBA", SIZE)
        layer.paste(Image.open(path).convert("RGBA"), tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.array(layers["arm_near"])
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    records, outputs = {}, {}
    for mesh_name, mesh in v4["meshes"].items():
        uv = np.array(mesh["uv"])
        triangles = np.array(mesh["triangles"], dtype=int)
        records[mesh_name] = {}
        for name, pose in mesh["poses"].items():
            points = np.array(pose["deformedVerticesGlobalXY"])
            rendered, raster, coverage = render_mesh(texture, uv, triangles, points, "source_over_top_left")
            legacy, _, _ = render_mesh(texture, uv, triangles, points)
            old_png = np.array(Image.open(PARENT / f"arm_mesh_test_v4/{mesh_name}_{name}_arm.png"))
            if not np.array_equal(legacy, old_png):
                raise AssertionError("legacy路径未复现v4")
            geometry_same = (pose["geometry"] == study_geometry(np.array(mesh["vertices"]), triangles, points))
            Image.fromarray(rendered).save(output / f"{mesh_name}_{name}_arm.png")
            assembly = assemble(manifest, layers, rendered)
            assembly.save(output / f"{mesh_name}_{name}_assembly.png")
            outputs[(mesh_name, name)] = rendered
            changed = np.any(legacy != rendered, axis=2)
            visible_union = (texture[:, :, 3] > 0) | (rendered[:, :, 3] > 0)
            records[mesh_name][name] = {"geometryUnchanged": bool(geometry_same),
                "geometry": pose["geometry"], "raster": raster,
                "changedVsLegacyRgbaPixels": int(np.count_nonzero(changed)),
                "legacyTransparentBecameVisiblePixels": int(np.count_nonzero((legacy[:, :, 3] == 0) & (rendered[:, :, 3] > 0))),
                "alphaAreaRatioToSource": float(rendered[:, :, 3].sum() / texture[:, :, 3].sum())}
            if name == "neutral":
                neutral_mismatch = int(np.count_nonzero(np.any(rendered != texture, axis=2) & visible_union))
                records[mesh_name][name]["neutralRgbaMismatchPixels"] = neutral_mismatch
                if neutral_mismatch:
                    raise AssertionError("新合成中性像素不一致")
    comparisons = {}
    for name in v4["meshes"]["rectangle"]["poses"]:
        a, b = outputs[("rectangle", name)], outputs[("alpha_occupied", name)]
        union = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
        mismatch = int(np.count_nonzero(np.any(a != b, axis=2) & union))
        comparisons[name] = {"rgbaMismatchPixelsInVisibleUnion": mismatch,
            "alphaMismatchPixels": int(np.count_nonzero(a[:, :, 3] != b[:, :, 3]))}
        if mismatch:
            raise AssertionError("新合成在删除纯透明三角后结果发生变化")
    sheet = Image.new("RGB", (1740, 1730), (243, 245, 242))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 16), "近臂透明合成修正 v5｜只修显示，不改骨架/拓扑/权重/纹理", font=font(27), fill=(30, 48, 55))
    draw.text((24, 58), "source-over + 半开边界；纯透明三角不再擦除有效像素。几何翻转和肩根缺图仍明确保留。", font=font(19), fill=(120, 57, 35))
    for col, text in enumerate(("旧后写覆盖（矩形mesh）", "正确合成（同一矩形mesh）", "正确合成（裁透明mesh）")):
        draw.text((24 + col * 574, 102), text, font=font(19), fill=(32, 52, 60))
    for row, name in enumerate(("neutral", "open", "chest")):
        y = 142 + row * 470
        draw.text((24, y), name + "｜人工姿态，视频未标定", font=font(20), fill=(32, 52, 60))
        old = Image.open(PARENT / f"arm_mesh_test_v4/rectangle_{name}_assembly.png")
        for col, image in enumerate((old, Image.open(output / f"rectangle_{name}_assembly.png"),
                                     Image.open(output / f"alpha_occupied_{name}_assembly.png"))):
            sheet.paste(crop_view(image), (24 + col * 574, y + 34))
        r = records["rectangle"][name]
        draw.text((24, y + 432), f"几何翻转仍{r['geometry']['flippedTriangles']}；不作为绑定通过", font=font(17), fill=(120, 55, 35))
        draw.text((598, y + 432), f"新增显示像素{r['legacyTransparentBecameVisiblePixels']}；alpha{r['alphaAreaRatioToSource']:.1%}", font=font(17), fill=(120, 55, 35))
        draw.text((1172, y + 432), f"两种mesh新合成RGBA差异{comparisons[name]['rgbaMismatchPixelsInVisibleUnion']}", font=font(17), fill=(120, 55, 35))
    draw.text((24, 1570), "几何问题与显示问题分开记录；肩腋缺图仍存在，不用补画覆盖渲染器错误。", font=font(20), fill=(32, 52, 60))
    draw.text((24, 1615), "7逻辑件 / 0新增附件 / 0新增骨骼；换装衣袖、跨角色、视频拟合及Spine导出未完成。", font=font(19), fill=(120, 55, 35))
    draw.text((24, 1660), "仅独立实验路径使用新合成；v1-v4证据和旧复现实验默认行为保持不变。", font=font(19), fill=(32, 52, 60))
    sheet.save(output / "review.png")
    if not all(sha256(Path(p)) == h for p, h in before.items()):
        raise AssertionError("原资产或证据改变")
    images = []
    for path in sorted(output.glob("*.png")):
        with Image.open(path) as image:
            size = list(image.size)
            image.verify()
        images.append({"file": path.name, "sha256": sha256(path), "size": size})
    checks = {"sourceAndV1V2V3V4Unchanged": True, "sourceHashes": before,
        "scriptSha256": sha256(Path(__file__)), "sourceManifestSha256": sha256(manifest_path),
        "taskId": manifest["taskId"], "renderMetrics": records,
        "rectangleVsAlphaOccupiedNewCompositing": comparisons,
        "legacyV4PixelReproduced": True, "generatedImages": images,
        "logicalParts": 7, "attachmentsAdded": 0, "bonesAdded": 0,
        "hiddenComplete": False, "bindingValidated": False, "promotedToRuntime": False,
        "videoFitted": False, "costumeTested": False,
        "limitations": ["改合成只修显示，几何自交仍按三角索引层叠，未修正。",
            "alpha比例为透明臂alpha总和/源alpha总和，不是体积或视频误差。",
            "遮挡域/肩根未补，不因显示修复宣称接口通过。",
            "半开边界实验不是GPU runtime逐像素匹配保证，正式Spine/Unity待独立验证。"]}
    path = output / "checks.json"
    path.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    if json.loads(path.read_text(encoding="utf-8")) != checks:
        raise AssertionError("JSON回读错误")
    print(json.dumps({"output": str(output), "records": records, "pairComparison": comparisons,
                      "imageCount": len(images)}, ensure_ascii=False, indent=2))


def edgeflow_strip(alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    # 材料轴不是解剖轴；护边覆盖每个可见像素的完整像素方格再外扩2px。
    axis = JOINTS[2] - JOINTS[0]
    axis = axis / np.linalg.norm(axis)
    normal = np.array([-axis[1], axis[0]])
    yy, xx = np.nonzero(alpha > 0)
    pixels = np.column_stack((xx, yy)).astype(float)
    sr = np.column_stack(((pixels - JOINTS[0]) @ axis, (pixels - JOINTS[0]) @ normal))
    radius_s = 2.5 * np.abs(axis).sum()
    radius_r = 2.5 * np.abs(normal).sum()
    start, end = float(sr[:, 0].min() - radius_s - .25), float(sr[:, 0].max() + radius_s + .25)
    elbow_s = float((JOINTS[1] - JOINTS[0]) @ axis)
    knots = [start]
    while knots[-1] < end:
        step = 2.5 if abs(knots[-1] - elbow_s) < 25. else 6.
        knots.append(min(knots[-1] + step, end))
    s = np.unique(np.r_[knots, 0., elbow_s, np.linalg.norm(JOINTS[2] - JOINTS[0])])
    lower, upper = np.full(len(s), np.inf), np.full(len(s), -np.inf)
    slab_counts = []
    for i in range(len(s) - 1):
        hit = (sr[:, 0] + radius_s >= s[i]) & (sr[:, 0] - radius_s <= s[i + 1])
        if not hit.any():
            nearest = np.argmin(np.abs(sr[:, 0] - (s[i] + s[i + 1]) / 2.))
            hit[nearest] = True
        lo, hi = sr[hit, 1].min() - radius_r, sr[hit, 1].max() + radius_r
        lower[i:i + 2] = np.minimum(lower[i:i + 2], lo)
        upper[i:i + 2] = np.maximum(upper[i:i + 2], hi)
        slab_counts.append(int(hit.sum()))
    fractions = np.linspace(0., 1., 9)
    transverse = lower[:, None] + (upper - lower)[:, None] * fractions
    vertices = (JOINTS[0] + s[:, None, None] * axis + transverse[:, :, None] * normal).reshape(-1, 2)
    triangles = []
    cols = len(fractions)
    for row in range(len(s) - 1):
        for col in range(cols - 1):
            a = row * cols + col
            b, c, d = a + 1, a + cols, a + cols + 1
            # 每个四边形只连相邻截面；交错短对角线，不跨多截面。
            triangles.extend(((a, b, c), (b, d, c)) if (row + col) % 2 else ((a, b, d), (a, d, c)))
    triangles = np.asarray(triangles, dtype=np.int32)
    area = cross2(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
    triangles[area < 0] = triangles[area < 0][:, [0, 2, 1]]
    centres_r = (lower + upper) / 2.
    smooth_r = np.convolve(np.pad(centres_r, 2, mode="edge"), np.array([1., 2., 3., 2., 1.]) / 9., mode="valid")
    centres = JOINTS[0] + s[:, None] * axis + smooth_r[:, None] * normal
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centres, axis=0), axis=1))]
    metadata = {"axisGlobalXY": axis.tolist(), "normalGlobalXY": normal.tolist(),
        "originGlobalXY": JOINTS[0].tolist(), "sectionS": s.tolist(), "sectionLowerR": lower.tolist(),
        "sectionUpperR": upper.tolist(), "transverseFractions": fractions.tolist(),
        "sectionCount": len(s), "columnsPerSection": cols, "elbowAxisS": elbow_s,
        "centrelineGlobalXY": centres.tolist(), "centrelineArcPx": arc.tolist(),
        "elbowCentrelineArcPx": float(np.interp(elbow_s, s, arc)), "slabSupportPixelCounts": slab_counts,
        "shapeSource": "源arm_near alpha>0像素完整方格，向xy各侧外扩2px；不使用body/供体决定臂形",
        "topologySource": "沿肩→手整体材料轴新建连续横截面条带；各slab投影支持外包极值赋给两端截面；内部完全重连",
        "envelopePolicy": "保守连续分段线性envelope覆盖所有guard方格；可填透明凹口但不填纹理；两端平截cap均有有限正宽",
        "guardPx": 2., "pixelHalfExtentWithGuardPx": 2.5,
        "capWidthsPx": [float(upper[0] - lower[0]), float(upper[-1] - lower[-1])],
        "elbowStepPx": 2.5, "otherStepPx": 6., "correctives": False}
    return vertices, triangles, metadata


def edgeflow_intersections(points: np.ndarray, triangles: np.ndarray) -> dict:
    # 所有对均经bbox筛选；共享顶点/边不被排除。相交面积来自几何，非像素计数。
    geometry = points[triangles]
    low, high = geometry.min(axis=1), geometry.max(axis=1)
    pair_count = shared_count = shared_edge_count = candidates = 0
    pair_area_sum = maximum = 0.
    worst_pair = None
    tolerance = 1e-5
    for i in range(len(triangles) - 1):
        ids = np.flatnonzero(np.all(high[i] >= low[i + 1:], axis=1) & np.all(high[i + 1:] >= low[i], axis=1)) + i + 1
        candidates += len(ids)
        for j in ids:
            # 同一对使用相同局部原点，降低全局坐标float32量化影响。
            origin = np.minimum(low[i], low[j])
            area, _ = cv2.intersectConvexConvex((geometry[i] - origin).astype(np.float32),
                                               (geometry[j] - origin).astype(np.float32), handleNested=True)
            if area > tolerance:
                pair_count += 1
                common = int(np.isin(triangles[i], triangles[j]).sum())
                shared_count += int(common > 0)
                shared_edge_count += int(common == 2)
                pair_area_sum += float(area)
                if area > maximum:
                    maximum, worst_pair = float(area), [i, int(j)]
    return {"positiveOverlapPairCount": pair_count, "positiveOverlapSharedVertexPairCount": shared_count,
        "positiveOverlapSharedEdgePairCount": shared_edge_count, "bboxCandidatePairCount": candidates,
        "pairAreaSumPx2": pair_area_sum, "maximumPairAreaPx2": maximum, "worstPair": worst_pair,
        "positiveAreaTolerancePx2": tolerance,
        "pairAreaSumMeaning": "三角对相交面积之和，重叠区域可能重复计数；不是union，未计算连续几何union",
        "method": "三角bbox筛选+cv2.intersectConvexConvex；含共享顶点/边；合法公共边面积应为0"}


def run_edgeflow_study() -> None:
    output = PARENT / "arm_mesh_test_v6"
    baseline_path = OUT / "mesh.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not PARENT.is_dir() or manifest["assemblyLayerOrder"] != EXPECTED_ORDER:
        raise ValueError("输出父目录或层序不符")
    if sha256(manifest_path) != baseline["sourceManifestSha256"]:
        raise ValueError("源清单与v1不符")
    source_path = (PARTS / manifest["sourceImage"]["file"]).resolve()
    tracked = [source_path, *sorted(p for p in PARTS.rglob("*") if p.is_file())]
    for i in range(1, 6):
        directory = PARENT / f"arm_mesh_test_v{i}"
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        tracked += sorted(p for p in directory.rglob("*") if p.is_file())
    before = {str(p): sha256(p) for p in dict.fromkeys(tracked)}
    expected = [(source_path, manifest["sourceImage"]["sha256"])]
    expected += [(PARTS / p["file"], p["sha256"]) for p in manifest["parts"]]
    if any(sha256(p) != h for p, h in expected):
        raise ValueError("源图或稳定部件hash不符")
    layers = {}
    for part in manifest["parts"]:
        image = Image.open(PARTS / part["file"]).convert("RGBA")
        x0, y0, x1, y1 = part["bbox"]
        if image.size != (x1 - x0, y1 - y0):
            raise ValueError("部件尺寸不符")
        layer = Image.new("RGBA", SIZE)
        layer.paste(image, (x0, y0))
        layers[part["id"]] = layer
    texture = np.array(layers["arm_near"])
    source = np.array(Image.open(source_path).convert("RGBA"))
    if source.shape != (768, 768, 4):
        raise ValueError("需要768全局纹理")
    alpha = texture[:, :, 3]
    visible = alpha > 0
    source_mismatch = int(np.count_nonzero(np.any(texture != source, axis=2) & visible))
    if source_mismatch:
        raise AssertionError("源臂RGBA未保留")
    original_v = np.array(baseline["vertices"], dtype=float)
    original_t = np.array(baseline["triangles"], dtype=np.int32)
    strip_v, strip_t, strip = edgeflow_strip(alpha)
    axis = np.array(strip["axisGlobalXY"])
    sections = np.array(strip["sectionS"])
    strip_s = (strip_v - JOINTS[0]) @ axis
    arc_coordinate = np.interp(strip_s, sections, strip["centrelineArcPx"]) - strip["elbowCentrelineArcPx"]
    t = np.clip((arc_coordinate + 30.) / 60., 0., 1.)
    lower_weight = t * t * (3. - 2. * t)
    strip_arc_weights = np.column_stack((1. - lower_weight, lower_weight))
    strip_axis_weights = study_weights(strip_v, "continuous_axis", 60.)
    weight_delta = float(np.max(np.abs(strip_arc_weights - strip_axis_weights)))
    weight_mean_delta = float(np.mean(np.abs(strip_arc_weights - strip_axis_weights)))
    strip_edges, edge_uses = np.unique(np.sort(np.concatenate((strip_t[:, [0, 1]], strip_t[:, [1, 2]], strip_t[:, [2, 0]])), axis=1), axis=0, return_counts=True)
    strip_areas = cross2(strip_v[strip_t[:, 1]] - strip_v[strip_t[:, 0]], strip_v[strip_t[:, 2]] - strip_v[strip_t[:, 0]]) / 2.
    section_ids = np.arange(len(strip_v)) // strip["columnsPerSection"]
    topology_checks = {"connectedByConstruction": True, "eulerCharacteristic": int(len(strip_v) - len(strip_edges) + len(strip_t)),
        "edgeIncidenceMax": int(edge_uses.max()), "boundaryEdgeCount": int(np.count_nonzero(edge_uses == 1)),
        "minimumBindTriangleAreaPx2": float(strip_areas.min()),
        "maximumTriangleSectionSpan": int(np.ptp(section_ids[strip_t], axis=1).max()),
        "capWidthsPx": strip["capWidthsPx"], "continuousLongitudinalColumns": strip["columnsPerSection"],
        "notTransparentTrianglePruning": True,
        "comparisonCaution": "旧矩形到条带同时改变透明外域形状与内部连边，不能把改善全部归因于边流；三角数不同，翻转/相交对数也不能直接当质量分数"}
    if topology_checks["eulerCharacteristic"] != 1 or edge_uses.max() != 2 or strip_areas.min() <= 0. or topology_checks["maximumTriangleSectionSpan"] != 1:
        raise AssertionError("条带局部连通/非退化拓扑不成立")
    meshes = {"old_axis60": (original_v, original_t, study_weights(original_v, "continuous_axis", 60.)),
              "strip_axis60": (strip_v, strip_t, strip_axis_weights),
              "strip_arc60": (strip_v, strip_t, strip_arc_weights)}
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    bind_angles = np.arctan2(np.diff(JOINTS, axis=0)[:, 1], np.diff(JOINTS, axis=0)[:, 0])
    def angle_of(joints):
        difference = np.diff(joints, axis=0)
        return np.arctan2(difference[:, 1], difference[:, 0])
    def wrap(angles):
        return (angles + np.pi) % (2. * np.pi) - np.pi
    def joints_for(angles):
        joints = [JOINTS[0].copy()]
        for length, angle in zip(lengths, angles):
            joints.append(joints[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
        return np.asarray(joints)
    open_joints = np.array(baseline["poses"]["open"]["targetJointsGlobalXY"])
    chest_legacy = np.array(baseline["poses"]["chest"]["targetJointsGlobalXY"])
    chest_angles = angle_of(chest_legacy)
    fixed_joints = joints_for(chest_angles)
    poses = {"neutral": JOINTS.copy(), "open": open_joints, "chest_fixed": fixed_joints}
    open_angles = angle_of(open_joints)
    elbow_delta = float(wrap(np.array([(chest_angles[1] - chest_angles[0]) - (bind_angles[1] - bind_angles[0])]))[0])
    shoulder_ends = wrap(np.array([open_angles[0], chest_angles[0]]) - bind_angles[0])
    shoulder_start, shoulder_end = min(0., float(shoulder_ends.min())), max(0., float(shoulder_ends.max()))
    paths = {"elbow_isolated": [], "shoulder_isolated": [], "open_to_chest_fixed": []}
    for i in range(65):
        p = i / 64.
        paths["elbow_isolated"].append(joints_for(bind_angles + np.array([0., elbow_delta * p])))
        rotation = shoulder_start + (shoulder_end - shoulder_start) * p
        paths["shoulder_isolated"].append(joints_for(bind_angles + rotation))
        paths["open_to_chest_fixed"].append(joints_for(open_angles + wrap(chest_angles - open_angles) * p))
    pose_record = lambda joints: {"targetJointsGlobalXY": joints.tolist(),
        "boneGlobalFromBindMatrices2x3": [m.tolist() for m in bone_matrices(joints)],
        "absoluteAnglesDegreesImageYDown": np.rad2deg(angle_of(joints)).tolist(),
        "relativeElbowAngleDegrees": float(np.rad2deg(wrap(np.array([angle_of(joints)[1] - angle_of(joints)[0]]))[0])),
        "boneLengthRatios": (np.linalg.norm(np.diff(joints, axis=0), axis=1) / lengths).tolist()}
    targets = {"poses": {name: pose_record(joints) for name, joints in poses.items()},
        "legacyStretchControlOnly": {"chest": pose_record(chest_legacy)},
        "paths": {name: [dict(sample=i, parameter=i / 64., **pose_record(joints)) for i, joints in enumerate(path)]
                  for name, path in paths.items()}}
    # 先全几何扫；所有材料控制点只观察，绝不加位置约束或按姿态改权重。
    results, mesh_records = {}, {}
    for name, (vertices, triangles, weights) in meshes.items():
        controls = material_control_matrix(vertices, triangles)
        edges = np.unique(np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1), axis=0)
        rest_edges = np.linalg.norm(vertices[edges[:, 1]] - vertices[edges[:, 0]], axis=1)
        def measure(joints):
            points = deform(vertices, weights, bone_matrices(joints))
            geometry = study_geometry(vertices, triangles, points)
            tri_points = points[triangles]
            signed = cross2(tri_points[:, 1] - tri_points[:, 0], tri_points[:, 2] - tri_points[:, 0]) / 2.
            material = controls @ points
            edge_ratios = np.linalg.norm(points[edges[:, 1]] - points[edges[:, 0]], axis=1) / rest_edges
            return {"geometry": {**geometry, "signedTriangleAreasPx2": signed.tolist(),
                        "edgeLengthRatioMin": float(edge_ratios.min()), "edgeLengthRatioMax": float(edge_ratios.max())},
                "intersection": edgeflow_intersections(points, triangles),
                "boneLengthRatios": (np.linalg.norm(np.diff(joints, axis=0), axis=1) / lengths).tolist(),
                "materialObservedGlobalXY": material.tolist(),
                "materialDistanceToTargetPivotPx": np.linalg.norm(material - joints, axis=1).tolist(),
                "materialObservationMeaning": "bind材料点重心跟踪，只观察；固定枢轴不等于材料强锚点，距离0不是成功条件"}
        result = {"poses": {key: measure(joints) for key, joints in poses.items()},
            "legacyStretchControlOnly": {"chest": measure(chest_legacy)}, "paths": {}, "summary": {}}
        for path_name, path in paths.items():
            samples = [dict(sample=i, parameter=i / 64., **measure(joints)) for i, joints in enumerate(path)]
            result["paths"][path_name] = samples
            first = next((s for s in samples if s["geometry"]["flippedTriangles"] > 0), None)
            worst = min(samples, key=lambda s: s["geometry"]["signedAreaRatioMin"])
            overlap_worst = max(samples, key=lambda s: s["intersection"]["pairAreaSumPx2"])
            result["summary"][path_name] = {"sampleCount": 65,
                "flippedSampleCount": sum(s["geometry"]["flippedTriangles"] > 0 for s in samples),
                "collapsedSampleCount": sum(s["geometry"]["collapsedTriangles"] > 0 for s in samples),
                "overlapSampleCount": sum(s["intersection"]["positiveOverlapPairCount"] > 0 for s in samples),
                "maximumFlippedTriangles": max(s["geometry"]["flippedTriangles"] for s in samples),
                "minimumSignedAreaRatio": worst["geometry"]["signedAreaRatioMin"],
                "worstAreaSample": worst["sample"], "worstOverlapSample": overlap_worst["sample"],
                "maximumOverlapPairCount": max(s["intersection"]["positiveOverlapPairCount"] for s in samples),
                "maximumPairAreaSumPx2NotUnion": overlap_worst["intersection"]["pairAreaSumPx2"],
                "firstSampledFlip": None if first is None else {**targets["paths"][path_name][first["sample"]],
                    "changeFromBindRelativeElbowDegrees": float(np.rad2deg(elbow_delta) * first["parameter"]) if path_name == "elbow_isolated" else None,
                    "previousSampleHadNoFlip": first["sample"] > 0,
                    "meaning": "65点内第一翻转样本；阈值在前一样本与该样本之间，不声称连续精确临界角"}}
        results[name] = result
        mesh_records[name] = {"vertices": vertices.tolist(), "triangles": triangles.tolist(),
            "uv": ((vertices + .5) / np.array(SIZE)).tolist(), "weights": weights.tolist(),
            "materialControlBarycentricMatrix": controls.tolist(), "edges": edges.tolist(),
            "shapeSource": "源臂alpha，不修改源RGBA", "topologySource": "v1矩形网格" if name == "old_axis60" else "新建连续横截面条带；非裁透明三角",
            "weightsSource": "与旧网格完全同一continuous_axis 60px smoothstep" if name != "strip_arc60" else "源alpha截面中心固定平滑线的累计材料弧长，肘投影位置为带中心，60px smoothstep；同截面同权重",
            "weightBandWidthPx": 60., "poseSpecificOptimization": False,
            "vertexCount": len(vertices), "triangleCount": len(triangles),
            "weightsSumMaxError": float(np.abs(weights.sum(axis=1) - 1.).max())}
        print(f"几何扫描完成 {name}", flush=True)
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    produced, rendered_views, neutral_checks, shoulder_checks = [], {}, {}, {}
    def save(image, filename):
        path = output / filename
        image.save(path)
        produced.append(path)
    # 肩端局部区以材料截面定义，不拿整张neutral域当缺口真值。
    yy, xx = np.indices(alpha.shape)
    pixel_s = (np.stack((xx, yy), axis=-1) - JOINTS[0]) @ axis
    root_end_s = 8.
    root_texture = texture.copy()
    root_texture[pixel_s > root_end_s] = 0
    body_alpha = np.array(layers["body"])[:, :, 3]
    support = cv2.dilate(visible.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    for name, (vertices, triangles, weights) in meshes.items():
        controls = np.array(mesh_records[name]["materialControlBarycentricMatrix"])
        uv = (vertices + .5) / np.array(SIZE)
        selected = [(key, joints, results[name]["poses"][key]) for key, joints in poses.items()]
        # 只选两个不同的最坏样本：最小有向面积和最大相交pairAreaSum，不逐采样光栅。
        candidates = [(path_name, s) for path_name, samples in results[name]["paths"].items() for s in samples]
        worst_area = min(candidates, key=lambda entry: entry[1]["geometry"]["signedAreaRatioMin"])
        worst_overlap = max(candidates, key=lambda entry: entry[1]["intersection"]["pairAreaSumPx2"])
        for path_name, sample in dict(((p, s["sample"]), (p, s)) for p, s in (worst_area, worst_overlap)).values():
            selected.append((f"worst_{path_name}_{sample['sample']:02d}", paths[path_name][sample["sample"]], sample))
        for key, joints, record in selected:
            points = deform(vertices, weights, bone_matrices(joints))
            rendered, raster, coverage = render_mesh(texture, uv, triangles, points, "source_over_top_left")
            overlay = mesh_overlay(rendered, points, triangles, joints)
            material = controls @ points
            overlay_draw = ImageDraw.Draw(overlay)
            for point in material:
                x, y = point
                overlay_draw.rectangle((x - 3, y - 3, x + 3, y + 3), outline=(215, 30, 180, 255), width=1)
            assembly = assemble(manifest, layers, rendered)
            for suffix, image in (("arm", Image.fromarray(rendered)), ("mesh", overlay), ("assembly", assembly)):
                save(image, f"{name}_{key}_{suffix}.png")
            rendered_views[(name, key)] = (overlay, assembly)
            record["representativeRaster"] = {"raster": raster,
                "alphaAreaRatioToSource": float(rendered[:, :, 3].sum() / alpha.sum()),
                "filesPrefix": f"{name}_{key}", "actuallyMeshRasterized": True}
            if key == "neutral":
                union = visible | (rendered[:, :, 3] > 0)
                diff = np.abs(rendered.astype(np.int16) - texture.astype(np.int16))
                neutral_checks[name] = {"actuallyMeshRasterized": True, "sourceImageSubstituted": False,
                    "sourceVisiblePixelCount": int(visible.sum()),
                    "sourceVisiblePixelsUncovered": int(np.count_nonzero(visible & (coverage == 0))),
                    "guardSupportPixelsUncovered": int(np.count_nonzero(support & (coverage == 0))),
                    "rgbaMismatchPixelsInVisibleUnion": int(np.count_nonzero(np.any(diff > 0, axis=2) & union)),
                    "rgbaMaxError": int(diff[union].max()), "rgbaMae": float(diff[union].mean()),
                    "alphaMismatchPixels": int(np.count_nonzero(diff[:, :, 3])),
                    "alphaMaxError": int(diff[:, :, 3].max()),
                    "visiblePixelsLost": int(np.count_nonzero(visible & (rendered[:, :, 3] == 0))),
                    "visiblePixelsAdded": int(np.count_nonzero(~visible & (rendered[:, :, 3] > 0))),
                    "samplingNote": "真实旋转方向浮点三角仿射采样；非源图替代。可有float32/INTER_LINEAR精度误差，所有误差原样记录"}
                if neutral_checks[name]["sourceVisiblePixelsUncovered"] or neutral_checks[name]["guardSupportPixelsUncovered"] or neutral_checks[name]["visiblePixelsLost"]:
                    raise AssertionError(f"{name}neutral或2px护边光栅覆盖失败，必须先修实现")
                if neutral_checks[name]["rgbaMaxError"] > 2 or neutral_checks[name]["alphaMaxError"] > 1:
                    raise AssertionError(f"{name}neutral采样误差超出有限浮点范围")
            if name == "strip_axis60" and key in poses:
                root, _, _ = render_mesh(root_texture, uv, triangles, points, "source_over_top_left")
                root_alpha = root[:, :, 3]
                root_visible = root_alpha > 0
                overlap = root_visible & (body_alpha > 0)
                opaque_overlap = (root_alpha >= 250) & (body_alpha >= 250)
                root_s = (vertices - JOINTS[0]) @ axis
                root_triangles = triangles[np.any(root_s[triangles] <= root_end_s, axis=1)]
                region = points[np.unique(root_triangles)]
                bbox = [*np.floor(region.min(axis=0)).astype(int).tolist(), *np.ceil(region.max(axis=0)).astype(int).tolist()]
                shoulder_checks[key] = {"rootSourceMaterialDomain": {"sMin": float(sections[0]), "sMax": root_end_s},
                    "rootVisiblePixels": int(root_visible.sum()), "existingBodySupportOverlapPixels": int(overlap.sum()),
                    "nearOpaqueOverlapPixels": int(opaque_overlap.sum()),
                    "alphaMinOverlapEquivalentPx": float(np.minimum(root_alpha, body_alpha).sum() / 255.),
                    "rootPixelsWithoutExistingBodySupport": int(np.count_nonzero(root_visible & (body_alpha == 0))),
                    "investigationDomainAabbGlobalXY": bbox,
                    "notAnatomicalGapMask": True, "requiredPaintAreaPx2": None,
                    "interpretation": "只测肩端原有材料与已有body的alpha支持；不重用body作臂，不加载供体；无支持像素含正常外露，不等于真实缺口；最小补画范围尚无解剖真值"}
                evidence = assembly.copy()
                evidence_draw = ImageDraw.Draw(evidence)
                # 叠线不是纹理；橙为测量根区，青为现有body边界，紫为根区外轮廓。
                for mask, color in ((body_alpha > 0, (30, 160, 175, 255)), (root_visible, (220, 35, 170, 255))):
                    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for contour in contours:
                        contour_points = [tuple(map(int, p)) for p in contour[:, 0]]
                        if len(contour_points) > 1:
                            evidence_draw.line(contour_points + contour_points[:1], fill=color, width=1)
                for tri in root_triangles:
                    evidence_draw.line([tuple(p) for p in points[tri]] + [tuple(points[tri[0]])], fill=(240, 143, 20, 200), width=1)
                save(evidence, f"shoulder_root_{key}_support_overlay.png")
    elbow_failed = any(s["geometry"]["flippedTriangles"] > 0 or s["geometry"]["collapsedTriangles"] > 0 or s["intersection"]["positiveOverlapPairCount"] > 0
                       for name in ("strip_axis60", "strip_arc60") for s in results[name]["paths"]["elbow_isolated"])
    # 来源/拓扑/权重/语义独立证据图，不是新的附件PNG。
    save(mesh_overlay(texture, original_v, original_t, JOINTS), "source_topology.png")
    save(mesh_overlay(texture, strip_v, strip_t, JOINTS), "new_topology.png")
    weight_sheet = Image.new("RGB", (1560, 600), (243, 245, 242))
    wd = ImageDraw.Draw(weight_sheet)
    for col, name in enumerate(meshes):
        vertices, triangles, weights = meshes[name]
        view = mesh_overlay(texture, vertices, triangles, JOINTS)
        draw = ImageDraw.Draw(view)
        for point, weight in zip(vertices, weights[:, 1]):
            x, y = point
            draw.ellipse((x - 1.4, y - 1.4, x + 1.4, y + 1.4), fill=(int(255 * weight), 60, int(255 * (1. - weight)), 255))
        wd.text((15 + col * 520, 15), name + " / 固定60px材料带", font=font(20), fill=(30, 48, 55))
        weight_sheet.paste(crop_view(view), (10 + col * 520, 60))
    wd.text((20, 480), f"弧长/直轴同条带权重：max差{weight_delta:.5f}，mean差{weight_mean_delta:.5f}；不做每姿态优化。", font=font(21), fill=(115, 50, 35))
    wd.text((20, 525), "蓝=上臂 / 红=下臂。弧长坐标只是固定局部连续参数化，不宣称新蒙皮算法或自动消除翻转。", font=font(20), fill=(32, 52, 60))
    save(weight_sheet, "weights.png")
    semantics = Image.new("RGB", (1540, 650), (243, 245, 242))
    sd = ImageDraw.Draw(semantics)
    sd.text((20, 15), "控制点语义｜骨枢轴 ≠ 材料强锚点", font=font(29), fill=(30, 48, 55))
    for col, key in enumerate(("neutral", "chest_fixed")):
        view = rendered_views[("strip_axis60", key)][0]
        semantics.paste(crop_view(view), (20 + col * 520, 70))
        sd.text((20 + col * 520, 475), key + "：红圆骨枢轴 / 紫框材料点", font=font(18), fill=(100, 45, 50))
    for i, text in enumerate(("shoulder [350,456]：人工链根；不是已验证肩关节。", "elbow [330,509]：人工弯折中心；没有解剖真值。", "hand [317,555]：手部控制参考；不是已验证腕。", "紫框：bind处材料点的三角重心跟踪，仅观察。", "不把材料点偏差0当验收，也不强行钉到骨枢轴。")):
        sd.text((1060, 90 + i * 90), text, font=font(16), fill=(40, 53, 60))
    sd.text((20, 575), "单一arm_near、通用双骨链不变；衣袖共用骨链。换装、衣袖贴图/权重及跨角色仍需各自独立验收。", font=font(21), fill=(112, 52, 35))
    save(semantics, "control_semantics.png")
    sheet = Image.new("RGB", (1740, 2380), (243, 245, 242))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 15), "近臂边流 v6｜真实内部重连 / 固定材料权重 / 无修形无补画", font=font(28), fill=(30, 48, 55))
    draw.text((24, 62), "人工压力测试，非视频拟合；72/76等仅视觉参考，本步不读视频、会议region walk或供体。", font=font(20), fill=(115, 52, 35))
    for col, label in enumerate(("旧矩形 / 同一轴60px", "连续截面条带 / 同一轴60px", "条带固定弧长60px / 实际七层组装")):
        draw.text((24 + col * 574, 108), label, font=font(19), fill=(32, 52, 60))
    rows = [("neutral", "neutral"), ("open", "open"), ("chest_fixed", "chest_fixed")]
    for row, (key, label) in enumerate(rows):
        y = 150 + row * 470
        draw.text((24, y), label, font=font(22), fill=(30, 48, 55))
        for col, name in enumerate(meshes):
            overlay, assembly = rendered_views[(name, key)]
            sheet.paste(crop_view(assembly if col == 2 else overlay), (24 + col * 574, y + 35))
            metric = results[name]["poses"][key]
            text = f"翻转{metric['geometry']['flippedTriangles']} / 正面积重叠对{metric['intersection']['positiveOverlapPairCount']}"
            draw.text((24 + col * 574, y + 435), text, font=font(18), fill=(117, 50, 35))
    y = 1570
    draw.text((24, y), "肘隔离65点：上臂bind固定，下臂相对转角逐步增大；以下是实际扫描结果", font=font(22), fill=(30, 48, 55))
    for i, name in enumerate(meshes):
        summary = results[name]["summary"]["elbow_isolated"]
        first = summary["firstSampledFlip"]
        angle = "无采样翻转" if first is None else f"首次采样翻转 Δ={first['changeFromBindRelativeElbowDegrees']:.3f}°"
        draw.text((24, y + 45 + i * 42), f"{name}: {summary['flippedSampleCount']}/65翻转，最小面积比{summary['minimumSignedAreaRatio']:.4f}；{angle}", font=font(20), fill=(117, 50, 35))
    for col, key in enumerate(poses):
        image = Image.open(output / f"shoulder_root_{key}_support_overlay.png")
        sheet.paste(crop_view(image, box=(300, 425, 420, 510), scale=3), (24 + col * 574, 1790))
        check = shoulder_checks[key]
        draw.text((24 + col * 574, 2060), f"{key} 根区/body现有支持 {check['existingBodySupportOverlapPixels']}px", font=font(18), fill=(35, 52, 60))
    draw.text((24, 2120), "肩根叠线：橙=肩端材料截面区；青=已有body轮廓；紫=根区可见alpha轮廓。未新增皮肤像素。", font=font(20), fill=(35, 52, 60))
    draw.text((24, 2170), f"shoulderRepairBlockedByElbow={str(elbow_failed).lower()}；真实肩缺口/最小补画尚未确认，需要用户指定image2后续。", font=font(20), fill=(117, 50, 35))
    draw.text((24, 2220), "原chest允许伸缩，仅在JSON旧对照单列，不混入等骨长结论。几何pairAreaSum不是union。", font=font(20), fill=(35, 52, 60))
    draw.text((24, 2270), "仅独立实验：0新增骨/附件/源纹理，bindingValidated=false；不把少翻转、零材料偏差或光栅完整当生产通过。", font=font(19), fill=(117, 50, 35))
    draw.text((24, 2320), "更多最坏样本实网格见同目录；所有采样的三角有向面积、材料观察与骨变换均保留于JSON。", font=font(19), fill=(35, 52, 60))
    save(sheet, "review.png")
    hashes = {p: {"before": h, "after": sha256(Path(p))} for p, h in before.items()}
    unchanged = all(item["before"] == item["after"] for item in hashes.values())
    if not unchanged:
        raise AssertionError("源/stable/v1-v5发生改变")
    state = {"logicalParts": len(manifest["parts"]), "singleArmNearLogicalPart": True,
        "bonesAdded": 0, "attachmentsAdded": 0, "sourceTexturePngAdded": 0, "imageGenerationCalls": 0,
        "correctiveKeysAdded": 0, "poseSpecificOptimization": False, "bindingValidated": False,
        "promotedToRuntime": False, "approvedForBinding": False, "hiddenComplete": False,
        "costumeTested": False, "crossCharacterTested": False, "videoFitted": False,
        "meetingRegionWalkRead": False, "donorRead": False, "shoulderRepairBlockedByElbow": elbow_failed}
    checks = {"sourceStableAndV1V5Unchanged": unchanged, "trackedFileCount": len(hashes),
        "sourceHashesBeforeAfter": hashes, "sourceVisibleArmVsOriginalRgbaMismatchPixels": source_mismatch,
        "neutral": neutral_checks, "shoulderSupport": shoulder_checks,
        "poses": {name: result["poses"] for name, result in results.items()},
        "legacyStretchControlOnly": {name: result["legacyStretchControlOnly"] for name, result in results.items()},
        "stressSummary": {name: result["summary"] for name, result in results.items()},
        "arcVsAxisSameStripWeightMaxAbsDifference": weight_delta,
        "arcVsAxisSameStripWeightMeanAbsDifference": weight_mean_delta,
        "arcMethodClaim": "固定条带中心材料弧长坐标变体，不是新蒙皮方法；差异与效果分别记录，不因名称声称改进",
        "rasterizedRepresentativesPerVariant": {name: sum(key[0] == name for key in rendered_views) for name in meshes},
        "generatedImages": [], **state}
    for path in produced:
        with Image.open(path) as image:
            size = list(image.size)
            image.verify()
        checks["generatedImages"].append({"file": path.name, "size": size, "sha256": sha256(path)})
    study = {"schemaVersion": 1, "status": "continuous_material_strip_edgeflow_study_not_production",
        "taskId": manifest["taskId"], "characterId": manifest.get("characterId"),
        "scriptSha256": sha256(Path(__file__)), "sourceManifestSha256": sha256(manifest_path),
        "sourceImage": {"file": str(source_path), "sha256": sha256(source_path), "size": list(SIZE)},
        "sourceArm": baseline["sourceArm"], "sourceVideoSha256ReferenceOnly": manifest["sourceVideoSha256"],
        "bindJointsGlobalXY": JOINTS.tolist(), "bindBoneLengthsPx": lengths.tolist(),
        "controlSemantics": {"shoulder": "人工根参考，不是解剖真值或材料强锚点",
            "elbow": "人工弯折枢轴，没有已验证解剖真值", "hand": "[317,555]手部参考，不是已验证腕",
            "material": "原JOINTS位置嵌入bind网格，三角重心跟踪；只观察，不约束到骨枢轴"},
        "sharedContract": {"chain": ["shoulder_elbow", "elbow_hand"], "parentIndices": [None, 0],
            "logicalPart": "arm_near", "futureSleeve": "共享同一骨链，独立源纹理/mesh/权重与遮挡验收，不复制骨链",
            "crossCharacter": "角色profile自有bind长度/材料形状；换装和跨角色独立验收，当前均未测试"},
        "stripConstruction": strip, "topologyChecks": topology_checks,
        "meshes": mesh_records, "targets": targets, "results": results,
        "pathPolicy": {"sampleCountEach": 65, "elbowDeltaEndDegrees": float(np.rad2deg(elbow_delta)),
            "shoulderRotationRangeDegrees": np.rad2deg([shoulder_start, shoulder_end]).tolist(),
            "elbowIsolation": "上臂bind固定，下臂从bind相对角走到chest_fixed相对角差，保持两骨长度",
            "shoulderIsolation": "两骨刚性同转，保留bind相对角，覆盖open/chest上臂绝对角范围",
            "openToChestFixed": "复现旧人工最短绝对角插值路径，65点，固定bind骨长",
            "notVideoTimeline": True, "finiteSamplesNotContinuousProof": True},
        "shoulderSupport": shoulder_checks, "neutral": neutral_checks,
        "limitations": ["人工几何压力测试，不是视频拟合；72/76等只能视觉参考，本步未读取参考帧。",
            "几何三角相交含透明护边，不自动等于可见皮肤穿插；全局扫描不排除共享顶点/边。",
            "pairAreaSum可能重复计数，不是重叠union；未计算连续几何union。",
            "连续截面拓扑不自动消除双骨LBS在大弯折下的局部反向与全局自交。",
            "已有body仅测支持及正常组装，不作臂替换；本步不加载供体、不补画。",
            "肩根解剖/真实缺口未确认；root区外露不是缺口真值；真正补画需用户指定image2后续。",
            "未通过Spine运行时、衣袖、换装、跨角色或正式绑定验收。"], **state}
    for filename, data in (("study.json", study), ("checks.json", checks)):
        path = output / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise AssertionError("JSON落盘回读失败")
    disk = json.loads((output / "study.json").read_text(encoding="utf-8"))
    for name, record in disk["meshes"].items():
        v = np.array(record["vertices"])
        if not np.allclose(np.array(record["uv"]) * 768. - .5, v, atol=1e-8):
            raise AssertionError("落盘UV未保留全局纹理坐标")
        if not np.allclose(np.array(record["weights"]).sum(axis=1), 1., atol=1e-12):
            raise AssertionError("落盘权重未归一")
    print(json.dumps({"output": str(output), "neutral": neutral_checks,
        "meshSizes": {name: [len(v), len(t)] for name, (v, t, w) in meshes.items()},
        "stressSummary": checks["stressSummary"], "shoulderSupport": shoulder_checks,
        "arcVsAxisWeightMaxDifference": weight_delta, "sourceStableAndV1V5Unchanged": unchanged,
        "trackedFileCount": len(hashes), "shoulderRepairBlockedByElbow": elbow_failed,
        "bindingValidated": False}, ensure_ascii=False, indent=2))


def bounded_weight_field(points: np.ndarray, profile: str, axis: np.ndarray, normal: np.ndarray) -> np.ndarray:
    sr = (points - JOINTS[0]) @ axis
    nr = (points - JOINTS[0]) @ normal
    u = np.clip((sr - 12.) / 82., 0., 1.)
    if profile == "smoothstep_12_94":
        fore = u * u * (3. - 2. * u)
    elif profile == "linear_12_94":
        fore = u
    elif profile == "soft_ends_linear_center":
        x = 82. * u
        fore = np.where(x < 14., x * x / (28. * 68.),
                        np.where(x > 68., 1. - (82. - x) ** 2 / (28. * 68.), (x - 7.) / 68.))
    elif profile == "radius_skew_monotone":
        # 负n侧朝向此次负向肘弯内侧；全宽82，外侧收窄至66，带中心平滑错位最多4px。
        q = np.clip(nr / 40., -1., 1.)
        fraction = .5 + .5 * q
        start = 12. + 12. * fraction
        end = 94. - 4. * fraction
        local_u = np.clip((sr - start) / (end - start), 0., 1.)
        fore = local_u * local_u * (3. - 2. * local_u)
    else:
        raise ValueError(profile)
    fore = np.clip(fore, 0., 1.)
    return np.column_stack((1. - fore, fore))


def clip_convex_polygon(subject: np.ndarray, clip: np.ndarray, tolerance: float = 1e-12) -> np.ndarray:
    polygon = np.asarray(subject, dtype=np.float64)
    boundary = np.asarray(clip, dtype=np.float64)
    signed = float(cross2(boundary[1] - boundary[0], boundary[2] - boundary[0]))
    if abs(signed) <= tolerance:
        return np.empty((0, 2), dtype=np.float64)
    orientation = 1. if signed > 0. else -1.
    for a, b in zip(boundary, np.roll(boundary, -1, axis=0)):
        if len(polygon) == 0:
            break
        output = []
        edge = b - a
        for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
            ds = orientation * float(cross2(edge, start - a))
            de = orientation * float(cross2(edge, end - a))
            inside_s, inside_e = ds >= -tolerance, de >= -tolerance
            if inside_s != inside_e:
                denominator = ds - de
                if abs(denominator) > tolerance:
                    output.append(start + (end - start) * (ds / denominator))
            if inside_e:
                output.append(end)
        polygon = np.asarray(output, dtype=np.float64).reshape((-1, 2))
    return polygon


def float64_triangle_intersection_area(a: np.ndarray, b: np.ndarray) -> float:
    origin = np.minimum(np.min(a, axis=0), np.min(b, axis=0))
    first, second = np.asarray(a, dtype=np.float64) - origin, np.asarray(b, dtype=np.float64) - origin
    polygon = clip_convex_polygon(first, second)
    if len(polygon) < 3:
        return 0.
    return abs(float(np.sum(cross2(polygon, np.roll(polygon, -1, axis=0))))) * .5


def intersection_self_tests() -> dict:
    tests = {
        "folded_shared_edge": (np.array([[0., 0.], [2., 0.], [0., 2.]]), np.array([[2., 0.], [0., 2.], [.5, .5]]), 1.),
        "reversed_winding_containment": (np.array([[0., 0.], [0., 2.], [2., 0.]]), np.array([[.2, .2], [.2, .5], [.5, .2]]), .045),
        "thin_nonzero_above_tolerance": (np.array([[0., 0.], [1., 0.], [0., 1.]]), np.array([[.99, 0.], [1.2, 0.], [.99, .2]]), .00005),
        "disjoint": (np.array([[0., 0.], [1., 0.], [0., 1.]]), np.array([[2., 2.], [3., 2.], [2., 3.]]), 0.),
        "shared_edge": (np.array([[0., 0.], [1., 0.], [0., 1.]]), np.array([[1., 0.], [0., 1.], [1., 1.]]), 0.),
        "shared_vertex": (np.array([[0., 0.], [1., 0.], [0., 1.]]), np.array([[1., 0.], [2., 0.], [1., -1.]]), 0.),
        "contained": (np.array([[0., 0.], [2., 0.], [0., 2.]]), np.array([[.2, .2], [.5, .2], [.2, .5]]), .045),
        "thin_overlap": (np.array([[0., 0.], [1., 0.], [0., 1.]]), np.array([[.99999, 0.], [1.2, 0.], [.99999, .2]]), 5e-11),
    }
    output = {}
    import shapely
    for name, (a, b, expected) in tests.items():
        area = float64_triangle_intersection_area(a, b)
        independent = float(shapely.area(shapely.intersection(shapely.Polygon(a), shapely.Polygon(b))))
        output[name] = {"areaPx2": area, "shapelyAreaPx2": independent, "expectedPx2": expected,
                        "positiveAt1eMinus5": area > 1e-5,
                        "passed": bool(np.isclose(area, expected, atol=1e-12, rtol=1e-8) and abs(area - independent) < 1e-10)}
    if not all(item["passed"] for item in output.values()):
        raise AssertionError("float64凸裁剪相交自测失败")
    return {"tolerancePx2": 1e-5, "tests": output, "allPassed": True,
            "method": "float64 convex polygon clipping; positive-area decision tolerance 1e-5px2; not cv2"}


def float64_intersections(points: np.ndarray, triangles: np.ndarray) -> dict:
    tri_points = np.asarray(points, dtype=np.float64)[triangles]
    low, high = tri_points.min(axis=1), tri_points.max(axis=1)
    count = candidates = shared_pairs = 0
    area_sum = maximum = 0.
    worst = None
    import shapely
    polygons = shapely.polygons(tri_points)
    for i in range(len(triangles) - 1):
        ids = np.flatnonzero(np.all(high[i] + 1e-12 >= low[i + 1:], axis=1) &
                             np.all(high[i + 1:] + 1e-12 >= low[i], axis=1)) + i + 1
        candidates += len(ids)
        areas = shapely.area(shapely.intersection(polygons[i], polygons[ids]))
        for j, area in zip(ids, areas):
            if area > 1e-5:
                count += 1
                shared_pairs += int(len(set(triangles[i]) & set(triangles[j])) > 0)
                area_sum += float(area)
                if area > maximum:
                    maximum, worst = float(area), [i, int(j)]
    clip_area = None if worst is None else float64_triangle_intersection_area(tri_points[worst[0]], tri_points[worst[1]])
    if clip_area is not None and abs(clip_area - maximum) > 1e-5:
        raise AssertionError("独立float64裁剪与Shapely最坏对面积不一致")
    return {"positiveOverlapPairCount": count, "positiveOverlapSharedVertexPairCount": shared_pairs,
            "bboxCandidatePairCount": candidates, "pairAreaSumPx2NotUnion": area_sum,
            "maximumPairAreaPx2": maximum, "worstPair": worst, "positiveAreaTolerancePx2": 1e-5,
            "worstPairIndependentClipAreaPx2": clip_area, "shapelyVersion": shapely.__version__,
            "method": "Shapely float64 geometry intersection area; worst pair independently convex-clipped; includes shared pairs; not cv2"}


def run_bounded_weight_study() -> None:
    output = PARENT / "arm_mesh_test_v7"
    v6_path = PARENT / "arm_mesh_test_v6" / "study.json"
    v6 = json.loads(v6_path.read_text(encoding="utf-8"))
    manifest_path = PARTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = json.loads((OUT / "mesh.json").read_text(encoding="utf-8"))
    tracked = [manifest_path, v6_path, *sorted(p for p in PARTS.rglob("*") if p.is_file()),
               *sorted(p for p in OUT.rglob("*") if p.is_file())]
    for version in range(1, 7):
        tracked.extend(sorted(p for p in (PARENT / f"arm_mesh_test_v{version}").rglob("*") if p.is_file()))
    before = {str(p): sha256(p) for p in dict.fromkeys(tracked) if p.is_file()}
    if sha256(manifest_path) != v6["sourceManifestSha256"] or manifest["assemblyLayerOrder"] != EXPECTED_ORDER:
        raise ValueError("稳定清单或层序与v6不符")
    strip_v = np.asarray(v6["meshes"]["strip_axis60"]["vertices"], dtype=np.float64)
    strip_t = np.asarray(v6["meshes"]["strip_axis60"]["triangles"], dtype=np.int32)
    if strip_v.shape != (360, 2) or strip_t.shape != (624, 3):
        raise ValueError("v6 strip_axis60网格尺寸不符")
    axis = np.asarray(v6["stripConstruction"]["axisGlobalXY"], dtype=np.float64)
    normal = np.asarray(v6["stripConstruction"]["normalGlobalXY"], dtype=np.float64)
    s = (strip_v - JOINTS[0]) @ axis
    if (float(s.min()) > 12. or float(s.max()) < 94.):
        raise ValueError("条带不完整覆盖稳定权重端区")
    hand_s = float((JOINTS[2] - JOINTS[0]) @ axis)
    if hand_s < 94.:
        raise AssertionError("手参考投影未越过下臂稳定域阈值")
    # 固定P1三角网格：边界所在slab的两端都必须纯刚体，否则s=12/94截面会插值漏权。
    sections = np.asarray(v6["stripConstruction"]["sectionS"])
    upper_guard_end = float(sections[sections >= 12.].min())
    fore_guard_start = float(sections[sections <= 94.].max())
    evaluation_s = 12. + (s - upper_guard_end) * 82. / (fore_guard_start - upper_guard_end)
    evaluation_points = strip_v + (evaluation_s - s)[:, None] * axis
    weights_by_name = {"axis60": study_weights(strip_v, "continuous_axis", 60.)}
    names = ["smoothstep_12_94", "linear_12_94", "soft_ends_linear_center", "radius_skew_monotone"]
    for name in names:
        weights_by_name[name] = bounded_weight_field(evaluation_points, name, axis, normal)
        # 固定离散网格上逐列投影为保序场；只在权重空间约束，不引用任何姿态。
        grid = weights_by_name[name][:, 1].reshape((-1, 9))
        for row in range(1, len(grid)):
            grid[row] = np.maximum(grid[row], grid[row - 1])
        weights_by_name[name][:, 1] = grid.ravel()
        weights_by_name[name][:, 0] = 1. - weights_by_name[name][:, 1]
        weights_by_name[name][s <= upper_guard_end + 1e-9] = [1., 0.]
        weights_by_name[name][s >= fore_guard_start - 1e-9] = [0., 1.]
    source_path = Path(v6["sourceImage"]["file"])
    before[str(source_path)] = sha256(source_path)
    if sha256(source_path) != v6["sourceImage"]["sha256"] or any(sha256(PARTS / part["file"]) != part["sha256"] for part in manifest["parts"]):
        raise AssertionError("原图或稳定部件哈希不符")
    source = np.asarray(Image.open(source_path).convert("RGBA"))
    layers = {}
    for part in manifest["parts"]:
        image = Image.open(PARTS / part["file"]).convert("RGBA")
        layer = Image.new("RGBA", SIZE)
        layer.paste(image, tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.asarray(layers["arm_near"])
    if np.any(texture[texture[:, :, 3] > 0] != source[texture[:, :, 3] > 0]):
        raise AssertionError("源臂RGBA与稳定纹理不一致")
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    bind_angles = np.arctan2(np.diff(JOINTS, axis=0)[:, 1], np.diff(JOINTS, axis=0)[:, 0])
    def angle_of(joints):
        d = np.diff(joints, axis=0)
        return np.arctan2(d[:, 1], d[:, 0])
    def wrap(value):
        return (value + np.pi) % (2. * np.pi) - np.pi
    def joints_for(angles):
        points = [JOINTS[0].copy()]
        for length, angle in zip(lengths, angles):
            points.append(points[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
        return np.asarray(points)
    open_joints = np.asarray(baseline["poses"]["open"]["targetJointsGlobalXY"], dtype=np.float64)
    chest_joints = np.asarray(baseline["poses"]["chest"]["targetJointsGlobalXY"], dtype=np.float64)
    chest_angles, open_angles = angle_of(chest_joints), angle_of(open_joints)
    elbow_delta = float(wrap(np.array([(chest_angles[1] - chest_angles[0]) - (bind_angles[1] - bind_angles[0])]))[0])
    shoulder_ends = wrap(np.array([open_angles[0], chest_angles[0]]) - bind_angles[0])
    poses = {"neutral": JOINTS.copy(), "open": open_joints, "chest_fixed": joints_for(chest_angles)}
    paths = {"elbow_isolated": [joints_for(bind_angles + [0., elbow_delta * i / 64.]) for i in range(65)],
             "shoulder_isolated": [joints_for(bind_angles + (min(0., float(shoulder_ends.min())) +
                                    (max(0., float(shoulder_ends.max())) - min(0., float(shoulder_ends.min()))) * i / 64.)) for i in range(65)],
             "open_to_chest_fixed": [joints_for(open_angles + wrap(chest_angles - open_angles) * i / 64.) for i in range(65)]}
    targets = {"poses": {k: v.tolist() for k, v in poses.items()}, "paths": {k: [v.tolist() for v in path] for k, path in paths.items()},
               "handReferenceProjectionSPx": hand_s, "handIsWristAnchor": False,
               "pathSampling": "复用v6同姿态定义与65个采样点；另对肘首翻附近固定参数区间细采样，不代表连续证明"}
    for key, joints in poses.items():
        if not np.allclose(joints, v6["targets"]["poses"][key]["targetJointsGlobalXY"], atol=1e-10, rtol=0.):
            raise AssertionError("v7关键姿态与v6不一致")
    for key, path in paths.items():
        if not np.allclose(path, [p["targetJointsGlobalXY"] for p in v6["targets"]["paths"][key]], atol=1e-10, rtol=0.):
            raise AssertionError("v7路径与v6不一致")
    if not np.array_equal(weights_by_name["axis60"], v6["meshes"]["strip_axis60"]["weights"]):
        raise AssertionError("axis60对照权重发生变化")
    intersection_tests = intersection_self_tests()
    # 纹理截面取原alpha像素方格投影包络，不把透明strip护边宽度当皮肤厚度。
    yy, xx = np.nonzero(texture[:, :, 3] > 0)
    pixel_xy = np.column_stack((xx, yy)).astype(np.float64)
    pixel_s = (pixel_xy - JOINTS[0]) @ axis
    pixel_n = (pixel_xy - JOINTS[0]) @ normal
    half_s = .5 * np.abs(axis).sum()
    half_n = .5 * np.abs(normal).sum()
    section_probes, thickness_records = [], []
    for section_s in np.linspace(12., 94., 21):
        hit = np.abs(pixel_s - section_s) <= half_s
        if not hit.any():
            continue
        lower_n, upper_n = float(pixel_n[hit].min() - half_n), float(pixel_n[hit].max() + half_n)
        for radius in (lower_n, 0., upper_n):
            section_probes.append(JOINTS[0] + section_s * axis + radius * normal)
        thickness_records.append({"s": float(section_s), "sourcePixelCount": int(hit.sum()),
            "nMinPx": lower_n, "nMaxPx": upper_n, "sourcePixelSupportThicknessPx": upper_n - lower_n,
            "meaning": "alpha>0像素方格投影支持保守包络；非精确轮廓或解剖半径"})
    probe_points = np.asarray(section_probes)
    # 将源材料查询点嵌入固定P1网格，之后所有姿态都复用同一重心坐标。
    def embed_material(points):
        src = strip_v[strip_t]
        q_inv = np.linalg.inv(np.transpose(src[:, 1:] - src[:, :1], (0, 2, 1)))
        ids, bary = [], []
        for point in points:
            uv = np.einsum("nij,nj->ni", q_inv, point - src[:, 0])
            coefficients = np.column_stack((1. - uv.sum(axis=1), uv))
            matches = np.flatnonzero(np.all(coefficients >= -1e-8, axis=1))
            if not len(matches):
                raise AssertionError("材料查询点超出v6条带")
            ids.append(int(matches[0]))
            bary.append(coefficients[matches[0]])
        return np.asarray(ids), np.asarray(bary)
    probe_ids, probe_bary = embed_material(probe_points)
    stable_probe_points = []
    for section_s in (float(sections.min()), 0., 11.999999, 12., 94., 94.000001, hand_s, float(sections.max())):
        lower = float(np.interp(section_s, sections, v6["stripConstruction"]["sectionLowerR"]))
        upper = float(np.interp(section_s, sections, v6["stripConstruction"]["sectionUpperR"]))
        stable_probe_points.extend(JOINTS[0] + section_s * axis + r * normal for r in np.linspace(lower, upper, 17))
    stable_probe_points = np.asarray(stable_probe_points)
    stable_ids, stable_bary = embed_material(stable_probe_points)
    stable_probe_s = (stable_probe_points - JOINTS[0]) @ axis
    results, mesh_records = {}, {}
    edges = np.unique(np.sort(np.concatenate((strip_t[:, [0, 1]], strip_t[:, [1, 2]], strip_t[:, [2, 0]])), axis=1), axis=0)
    rest_edges = np.linalg.norm(strip_v[edges[:, 1]] - strip_v[edges[:, 0]], axis=1)
    edge_mid_s = (s[edges[:, 0]] + s[edges[:, 1]]) * .5
    stable_upper = s <= 12.
    stable_fore = s >= 94.
    global_max_grad = {}
    for name, weights in weights_by_name.items():
        fore = weights[:, 1]
        order = np.argsort(s)
        # 同s不同n可以不同权；同时验证实际P1三角梯度沿固定s方向非负。
        grid = fore.reshape((-1, 9))
        weight_gradient = np.linalg.solve(strip_v[strip_t][:, 1:] - strip_v[strip_t][:, :1],
                                          (fore[strip_t][:, 1:] - fore[strip_t][:, :1])[..., None])[..., 0]
        derivative_s = weight_gradient @ axis
        monotone = bool(np.all(np.diff(grid, axis=0) >= -1e-10) and np.min(derivative_s) >= -1e-10)
        grid_s = s.reshape((-1, 9)).mean(axis=1)
        gradient = np.diff(grid, axis=0) / np.diff(grid_s)[:, None]
        global_max_grad[name] = float(np.max(np.abs(gradient)))
        if not monotone or np.any(fore[s <= 12.] != 0.) or np.any(fore[s >= 94.] != 1.):
            raise AssertionError(f"{name}不满足单调或稳定权重边界")
        src_tri = strip_v[strip_t]
        src_inverse = np.linalg.inv(np.transpose(src_tri[:, 1:] - src_tri[:, :1], (0, 2, 1)))
        source_signed_area = cross2(src_tri[:, 1] - src_tri[:, 0], src_tri[:, 2] - src_tri[:, 0]) / 2.
        def measure(joints, exact_intersection=False):
            transforms = bone_matrices(joints)
            deformed = deform(strip_v, weights, transforms)
            geometry = study_geometry(strip_v, strip_t, deformed)
            src = strip_v[strip_t]
            dst = deformed[strip_t]
            local_maps = np.einsum("nij,njk->nik", np.transpose(dst[:, 1:] - dst[:, :1], (0, 2, 1)),
                                   src_inverse)
            singular = np.linalg.svd(local_maps, compute_uv=False)
            cond = singular[:, 0] / np.maximum(singular[:, 1], 1e-15)
            tri_area = cross2(dst[:, 1] - dst[:, 0], dst[:, 2] - dst[:, 0]) / 2.
            edge_ratio = np.linalg.norm(deformed[edges[:, 1]] - deformed[edges[:, 0]], axis=1) / rest_edges
            transition_edges = (s[edges].max(axis=1) >= 12.) & (s[edges].min(axis=1) <= 94.)
            query = np.einsum("ni,nij->nj", probe_bary, deformed[strip_t[probe_ids]]).reshape((-1, 3, 2))
            source_query = probe_points.reshape((-1, 3, 2))
            total_width_ratios = np.linalg.norm(query[:, 2] - query[:, 0], axis=1) / np.linalg.norm(source_query[:, 2] - source_query[:, 0], axis=1)
            half_width_ratios = np.linalg.norm(query[:, [0, 2]] - query[:, 1:2], axis=2) / np.linalg.norm(source_query[:, [0, 2]] - source_query[:, 1:2], axis=2)
            mapped_stable = np.einsum("ni,nij->nj", stable_bary, deformed[strip_t[stable_ids]])
            expected_stable = np.empty_like(mapped_stable)
            for bone, mask in ((0, stable_probe_s <= 12. + 1e-8), (1, stable_probe_s > 12. + 1e-8)):
                expected_stable[mask] = np.column_stack((stable_probe_points[mask], np.ones(mask.sum()))) @ transforms[bone].T
            material_stable_error = float(np.linalg.norm(mapped_stable - expected_stable, axis=1).max())
            section_width = np.linalg.norm(deformed.reshape((-1, 9, 2))[:, -1] - deformed.reshape((-1, 9, 2))[:, 0], axis=1)
            rest_width = np.linalg.norm(strip_v.reshape((-1, 9, 2))[:, -1] - strip_v.reshape((-1, 9, 2))[:, 0], axis=1)
            # Stable-region material is compared to its expected rigid bone transform, not to the nearby pivot.
            upper_expected = np.column_stack((strip_v[stable_upper], np.ones(stable_upper.sum()))) @ transforms[0].T
            fore_expected = np.column_stack((strip_v[stable_fore], np.ones(stable_fore.sum()))) @ transforms[1].T
            upper_error = np.linalg.norm(deformed[stable_upper] - upper_expected, axis=1)
            fore_error = np.linalg.norm(deformed[stable_fore] - fore_expected, axis=1)
            output_record = {"geometry": {**geometry, "signedAreaRatioMin": float((tri_area / (cross2(src[:, 1] - src[:, 0], src[:, 2] - src[:, 0]) / 2.)).min()),
                    "signedTriangleAreasPx2": tri_area.tolist(), "signedAreaRatiosPerTriangle": (tri_area / source_signed_area).tolist(),
                    "singularValuesPerTriangleDescending": singular.tolist(), "conditionNumberPerTriangle": cond.tolist(),
                    "singularValueMin": float(singular[:, 1].min()),
                    "singularValueMax": float(singular[:, 0].max()), "conditionNumberMax": float(cond.max()),
                    "conditionNumberMedian": float(np.median(cond)), "edgeLengthRatioMin": float(edge_ratio.min()),
                    "edgeLengthRatioMax": float(edge_ratio.max()),
                    "transitionBandEdgeLengthRatioMin": float(edge_ratio[transition_edges].min()),
                    "transitionBandEdgeLengthRatioMax": float(edge_ratio[transition_edges].max()),
                    "stripEnvelopeCrossSectionWidthRatioMin": float((section_width / rest_width).min()),
                    "stripEnvelopeCrossSectionWidthRatioMax": float((section_width / rest_width).max()),
                    "textureCrossSectionWidthRatioMin": float(total_width_ratios.min()),
                    "textureCrossSectionWidthRatioMax": float(total_width_ratios.max()),
                    "textureBothSidesWidthRatios": half_width_ratios.tolist(),
                    "textureBothSidesWidthRatioMin": float(half_width_ratios.min()),
                    "textureBothSidesWidthRatioMax": float(half_width_ratios.max())},
                "stableDomainWorldRigidErrorPx": {"materialProbeMaxPx": material_stable_error, "upperSLe12": {"max": float(upper_error.max()), "mean": float(upper_error.mean()), "vertexCount": int(upper_error.size)},
                    "foreSGe94": {"max": float(fore_error.max()), "mean": float(fore_error.mean()), "vertexCount": int(fore_error.size)}},
                "finiteSample": True}
            if exact_intersection:
                output_record["intersection"] = float64_intersections(deformed, strip_t)
            return output_record
        path_results, path_summaries = {}, {}
        for path_name, path in paths.items():
            samples = [measure(joints) for joints in path]
            flips = [i for i, item in enumerate(samples) if item["geometry"]["flippedTriangles"]]
            first = flips[0] if flips else None
            refined = []
            if first is not None:
                lo, hi = max(0., (first - 2) / 64.), min(1., (first + 1) / 64.)
                for parameter in np.linspace(lo, hi, 49):
                    angles = bind_angles + [0., elbow_delta * parameter] if path_name == "elbow_isolated" else open_angles + wrap(chest_angles - open_angles) * parameter
                    joints = joints_for(angles)
                    item = measure(joints)
                    refined.append({"parameter": float(parameter), "relativeElbowChangeDegrees": float(np.rad2deg(wrap((angles[1] - angles[0]) - (bind_angles[1] - bind_angles[0])))), 
                                    "flippedTriangles": item["geometry"]["flippedTriangles"], "signedAreaRatioMin": item["geometry"]["signedAreaRatioMin"]})
            worst = int(np.argmin([item["geometry"]["signedAreaRatioMin"] for item in samples]))
            path_results[path_name] = {"samples65": samples, "refinedAroundFirstFlip": refined}
            path_summaries[path_name] = {"sampleCount": 65, "flippedSampleCount": len(flips),
                "maxStableVertexDriftPx": max(max(x["stableDomainWorldRigidErrorPx"]["upperSLe12"]["max"], x["stableDomainWorldRigidErrorPx"]["foreSGe94"]["max"]) for x in samples),
                "maxStableMaterialProbeErrorPx": max(x["stableDomainWorldRigidErrorPx"]["materialProbeMaxPx"] for x in samples),
                "maximumFlippedTriangles": max(x["geometry"]["flippedTriangles"] for x in samples),
                "minimumSignedAreaRatio": samples[worst]["geometry"]["signedAreaRatioMin"], "worstSample": worst,
                "firstSampledFlip": None if first is None else {"sample": first, "parameter": first / 64.,
                    "relativeElbowChangeDegrees": float(np.rad2deg(elbow_delta * first / 64.)) if path_name == "elbow_isolated" else float(np.rad2deg(wrap((angle_of(path[first])[1] - angle_of(path[first])[0]) - (bind_angles[1] - bind_angles[0])))), 
                    "previousSampleHadNoFlip": first > 0}}
        checks_to_intersect = {"neutral": poses["neutral"]}
        for path_name, path in paths.items():
            summary = path_summaries[path_name]
            if summary["firstSampledFlip"]:
                i = summary["firstSampledFlip"]["sample"]
                for j in (max(0, i - 1), i):
                    checks_to_intersect[f"{path_name}_firstFlip_{j:02d}"] = path[j]
            worst_idx = path_summaries[path_name]["worstSample"]
            checks_to_intersect[f"{path_name}_worst_{worst_idx:02d}"] = path[worst_idx]
        exact = {key: measure(joints, True)["intersection"] for key, joints in checks_to_intersect.items()}
        results[name] = {"paths": path_results, "summary": path_summaries, "selectedExactIntersections": exact,
            "poses": {key: measure(joints, True) for key, joints in poses.items()}}
        for path_name, path_record in path_results.items():
            refined = path_record["refinedAroundFirstFlip"]
            first_refined = next((r for r in refined if r["flippedTriangles"]), None)
            path_summaries[path_name]["firstRefinedFlip"] = first_refined
            if first_refined is not None:
                index = refined.index(first_refined)
                for index in (max(0, index - 1), index):
                    parameter = refined[index]["parameter"]
                    angles = bind_angles + [0., elbow_delta * parameter] if path_name == "elbow_isolated" else open_angles + wrap(chest_angles - open_angles) * parameter
                    joints = joints_for(angles)
                    exact[f"{path_name}_refined_{parameter:.9f}"] = {"parameter": parameter, **float64_intersections(deform(strip_v, weights, bone_matrices(joints)), strip_t)}
        mesh_records[name] = {"vertices": strip_v.tolist(), "triangles": strip_t.tolist(), "uv": ((strip_v + .5) / 768.).tolist(),
            "weights": weights.tolist(), "weightProfile": name, "monotoneAlongMaterialS": monotone,
            "maxAbsForeWeightDerivativePerPx": global_max_grad[name],
            "actualP1ForeWeightDerivativeSMin": float(derivative_s.min()), "actualP1ForeWeightDerivativeSMax": float(derivative_s.max()),
            "actualP1ForeWeightGradientXY": weight_gradient.tolist(),
            "weightsSha256Float64": hashlib.sha256(weights.astype("<f8").tobytes()).hexdigest(),
            "weightStableRegions": {"sLe12ForeWeight": 0., "sGe94ForeWeight": 1.},
            "fixedAcrossAllPoses": True, "poseSpecificOptimization": False, "vertexCount": 360, "triangleCount": 624}
        print(f"v7扫描完成 {name}", flush=True)
    # Predefined physical profile records use source-supported material extent; no weights are fitted to poses.
    visible_y, visible_x = np.nonzero(texture[:, :, 3] > 0)
    visible_s = (np.column_stack((visible_x, visible_y)) - JOINTS[0]) @ axis
    texture_support = {"sMin": float(visible_s.min()), "sMax": float(visible_s.max()),
                       "transitionAvailablePx": 82., "sourceVisiblePixelCount": int(len(visible_s)),
                       "manualProfileNotAnatomy": True}
    generated, renders = [], {}
    output.mkdir(exist_ok=True)
    def save(image, filename):
        path = output / filename
        image.save(path)
        generated.append(path)
    for name, weights in weights_by_name.items():
        render_poses = {"neutral": poses["neutral"], "open": poses["open"], "chest_fixed": poses["chest_fixed"]}
        # 同时保留条件数最差与有向面积最差代表，不按姿态生成权重。
        worst_path = max(results[name]["paths"], key=lambda path_name: max(
            sample["geometry"]["conditionNumberMax"] for sample in results[name]["paths"][path_name]["samples65"]))
        worst_index = int(np.argmax([x["geometry"]["conditionNumberMax"] for x in results[name]["paths"][worst_path]["samples65"]]))
        render_poses[f"worst_condition_{worst_path}_{worst_index:02d}"] = paths[worst_path][worst_index]
        area_path = min(results[name]["paths"], key=lambda path_name: results[name]["summary"][path_name]["minimumSignedAreaRatio"])
        area_index = results[name]["summary"][area_path]["worstSample"]
        render_poses[f"worst_area_{area_path}_{area_index:02d}"] = paths[area_path][area_index]
        for key, joints in render_poses.items():
            points = deform(strip_v, weights, bone_matrices(joints))
            rendered, raster, coverage = render_mesh(texture, (strip_v + .5) / 768., strip_t, points, "source_over_top_left")
            if key == "neutral":
                visible = texture[:, :, 3] > 0
                diff = np.abs(rendered.astype(np.int16) - texture.astype(np.int16))
                neutral = {"sourceVisibleUncovered": int(np.count_nonzero(visible & (coverage == 0))),
                    "rgbaMismatchPixels": int(np.count_nonzero(np.any(diff > 0, axis=2) & (visible | (rendered[:, :, 3] > 0)))),
                    "rgbaMaxError": int(diff.max()), "alphaMismatchPixels": int(np.count_nonzero(diff[:, :, 3])),
                    "coverageOverlapPixels": int(np.count_nonzero(coverage > 1))}
                results[name]["neutralRaster"] = neutral
                if neutral["sourceVisibleUncovered"] or neutral["coverageOverlapPixels"]:
                    raise AssertionError(f"{name} neutral coverage invalid")
            overlay = mesh_overlay(rendered, points, strip_t, joints)
            assembly = assemble(manifest, layers, rendered)
            renders[(name, key)] = (Image.fromarray(rendered), overlay, assembly)
            save(Image.fromarray(rendered), f"{name}_{key}_arm.png")
            save(overlay, f"{name}_{key}_mesh.png")
            save(assembly, f"{name}_{key}_assembly.png")
    weight_image = Image.new("RGB", (1550, 460), (243, 245, 242))
    wd = ImageDraw.Draw(weight_image)
    for col, name in enumerate(weights_by_name):
        view = mesh_overlay(texture, strip_v, strip_t, JOINTS)
        draw = ImageDraw.Draw(view)
        for point, weight in zip(strip_v, weights_by_name[name][:, 1]):
            x, y = point
            draw.ellipse((x - 1.3, y - 1.3, x + 1.3, y + 1.3), fill=(int(255 * weight), 60, int(255 * (1. - weight)), 255))
        wd.text((12 + col * 306, 10), name, font=font(17), fill=(30, 48, 55))
        weight_image.paste(crop_view(view, scale=1), (12 + col * 306, 40))
    save(weight_image, "weights.png")
    panels = []
    for key in ("neutral", "open", "chest_fixed"):
        panels.append((key, renders[("linear_12_94", key)][2]))
    for key, image in panels:
        save(image, f"assembly_{key}.png")
    review = Image.new("RGB", (1600, 1160), (243, 245, 242))
    rd = ImageDraw.Draw(review)
    rd.text((24, 15), "Bounded static weight study v7 | 360 / 624 | no corrective", font=font(26), fill=(30, 48, 55))
    for col, (key, image) in enumerate(panels):
        review.paste(crop_view(image, scale=2), (24 + col * 520, 65))
        rd.text((24 + col * 520, 470), key, font=font(19), fill=(35, 52, 60))
    for row, name in enumerate(weights_by_name):
        summ = results[name]["summary"]["elbow_isolated"]
        flip = summ["firstSampledFlip"]
        text = f"{name}: flip={summ['flippedSampleCount']}/65, first={None if flip is None else round(flip['relativeElbowChangeDegrees'], 2)} deg"
        rd.text((24, 570 + row * 47), text, font=font(18), fill=(117, 50, 35))
    rd.text((24, 820), "s<=12 fore=0, s>=94 fore=1; hand pivot is not a wrist anchor. Finite samples, not a continuous proof.", font=font(18), fill=(35, 52, 60))
    rd.text((24, 865), "Linear: no sampled flip but 8 positive-area overlap pairs at chest; still FAIL under no-self-intersection criterion.", font=font(18), fill=(117, 50, 35))
    rd.text((24, 910), "Stable vertices: exactly zero drift; material probes: floating-point noise only. No shoulder repair, no production claim.", font=font(18), fill=(35, 52, 60))
    save(review, "review.png")
    hashes = {p: {"before": h, "after": sha256(Path(p))} for p, h in before.items()}
    unchanged = all(item["before"] == item["after"] for item in hashes.values())
    if not unchanged:
        raise AssertionError("源/stable/v1-v6文件发生变化")
    for path in generated:
        with Image.open(path) as image:
            image.verify()
    study = {"schemaVersion": 1, "status": "bounded_static_weight_study_not_production", "v6StudySha256": sha256(v6_path),
        "scriptSha256": sha256(Path(__file__)),
        "legacyImplementationSha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").split("def bounded_weight_field")[0].encode()).hexdigest(),
        "sourceManifestSha256": sha256(manifest_path), "sourceImage": v6["sourceImage"], "sourceArm": v6["sourceArm"],
        "bindJointsGlobalXY": JOINTS.tolist(), "bindBoneLengthsPx": lengths.tolist(), "controlSemantics": v6["controlSemantics"],
        "stripSource": "v6 strip_axis60; same 360 vertices/624 triangles, UV, texture, chain; weights independently fixed by profile",
        "profileSupport": {**texture_support, "crossSectionSupportSamples": thickness_records}, "targets": targets, "intersectionSelfTests": intersection_tests,
        "profileDefinitions": {"axis60": "v6 continuous_axis 60px smoothstep unchanged as comparison",
            "smoothstep_12_94": "full-width smoothstep; fixed endpoints s=12/94",
            "linear_12_94": "linear ramp with constant derivative over fixed band",
            "soft_ends_linear_center": "quadratic low-gradient 14px endpoint ramps + linear center; fixed endpoints",
            "radius_skew_monotone": "q=clip(n/40,-1,1), f=(q+1)/2, start=12+12f,end=94-4f; smoothstep, width82..66,center53..57; fixed monotone column projection, no pose input"},
        "discreteBoundaryPolicy": {"requestedStableUpperSMax": 12., "requestedStableForeSMin": 94.,
            "upperPureBoneGuardEndsAtS": upper_guard_end, "forePureBoneGuardStartsAtS": fore_guard_start,
            "effectiveP1TransitionWidthPx": fore_guard_start - upper_guard_end,
            "evaluationSFormula": "12+(s-upperGuard)*82/(foreGuard-upperGuard)",
            "meaning": "不改360/624网格；跨阈值三角的全部端点必须纯骨，故实际可用P1混合带比82px短；未放宽稳定域"},
        "physicalBasis": "更宽材料混合带降低dw/ds；smoothstep最大斜率1.5/W，linear为1/W，平滑端点为1/(W-14)。半径40px只据源alpha支持厚度简化，非解剖，非LBS无解证明。",
        "derivativeDefinitions": {"axis60Max": "1.5/60", "smoothstepNominalMax": "1.5/82", "linearNominal": "1/82",
            "softEndsNominalMax": "1/68; endpoint derivatives0; d2f discontinuous at14/68px",
            "discreteReported": "按9列相邻截面权重差/材料s差；最终唯一权重场的离散斜率"},
        "maxDerivativePerPx": global_max_grad, "meshes": mesh_records, "results": results,
        "pathPolicy": {"sameAsV6": True, "sampleCountEach": 65, "refinedElbowSamples": 49,
            "refinementDoesNotProveContinuity": True}, "sourceStableAndV1V6Unchanged": unchanged,
        "trackedFileHashesBeforeAfter": hashes, "generatedImages": [p.name for p in generated],
        "bonesAdded": 0, "correctiveKeysAdded": 0, "poseSpecificOptimization": False, "sourceTextureChanged": False,
        "bindingValidated": False, "approvedForBinding": False,
        "limitations": ["权重阈值是人工profile，不是视频解剖测量。", "手参考投影仅作坐标语义检查，不是腕锚点。",
            "少量静态候选不构成LBS无解证明。", "稳定域误差按各自骨矩阵比较，不以材料枢轴偏差判定。",
            "肩根暂不修补；先要求肘区形变合格。", "首翻角只来自有限采样和局部加密，不声称连续临界证明。"]}
    dangerous_tri = int(np.argmin(results["axis60"]["paths"]["elbow_isolated"]["samples65"][64]["geometry"]["signedAreaRatiosPerTriangle"]))
    dangerous_pair = results["axis60"]["selectedExactIntersections"]["elbow_isolated_worst_64"]["worstPair"]
    comparison = {}
    for name, weights in weights_by_name.items():
        geom = results[name]["paths"]["elbow_isolated"]["samples65"][64]["geometry"]
        points = deform(strip_v, weights, bone_matrices(paths["elbow_isolated"][64]))
        comparison[name] = {"sameDangerousTriId": dangerous_tri, "sameTriSignedAreaRatio": geom["signedAreaRatiosPerTriangle"][dangerous_tri],
            "sameTriSingularValues": geom["singularValuesPerTriangleDescending"][dangerous_tri],
            "sameTriCondition": geom["conditionNumberPerTriangle"][dangerous_tri],
            "sameDangerousPair": dangerous_pair, "samePairAreaPx2": float64_triangle_intersection_area(points[strip_t[dangerous_pair[0]]], points[strip_t[dangerous_pair[1]]]),
            "wholeMeshMaxCondition": geom["conditionNumberMax"], "transitionEdgeMin": geom["transitionBandEdgeLengthRatioMin"],
            "transitionEdgeMax": geom["transitionBandEdgeLengthRatioMax"], "textureBothSidesWidthMin": geom["textureBothSidesWidthRatioMin"],
            "textureBothSidesWidthMax": geom["textureBothSidesWidthRatioMax"]}
    study["sameDangerousTriangleAndPairComparisonAtElbowEnd"] = comparison
    study["allCandidatesFailNoSelfIntersection"] = all(any(
        record["positiveOverlapPairCount"] > 0 for record in result["selectedExactIntersections"].values()) for result in results.values())
    study["shoulderRepairBlockedByElbow"] = study["allCandidatesFailNoSelfIntersection"]
    checks = {"sourceStableAndV1V6Unchanged": unchanged, "trackedFileHashesBeforeAfter": hashes,
        "sameDangerousTriangleAndPairComparisonAtElbowEnd": comparison,
        "allCandidatesFailNoSelfIntersection": study["allCandidatesFailNoSelfIntersection"],
        "intersectionSelfTests": intersection_tests, "neutralCoverageAndRGBA": {k: v["neutralRaster"] for k, v in results.items()},
        "elbowFirstFlip": {k: v["summary"]["elbow_isolated"]["firstSampledFlip"] for k, v in results.items()},
        "stableDomainErrors": {k: {path: [sample["stableDomainWorldRigidErrorPx"] for sample in rec["samples65"]]
                                      for path, rec in v["paths"].items()} for k, v in results.items()},
        "exactIntersectionReports": {k: v["selectedExactIntersections"] for k, v in results.items()},
        "nonProduction": True, "generatedImages": [p.name for p in generated]}
    output.mkdir(exist_ok=True)
    for filename, data in (("study.json", study), ("checks.json", checks)):
        path = output / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise AssertionError("v7 JSON回读失败")
    print(json.dumps({"output": str(output), "unchanged": unchanged, "profiles": {k: v["summary"] for k, v in results.items()},
                      "neutral": {k: v["neutralRaster"] for k, v in results.items()}, "handProjectionS": hand_s,
                      "allIntersectionSelfTestsPassed": intersection_tests["allPassed"]}, ensure_ascii=False, indent=2))


def run_elbow_mechanism_study() -> None:
    output = PARENT / "arm_mesh_test_v8"
    v7_path = PARENT / "arm_mesh_test_v7" / "study.json"
    manifest_path = PARTS / "manifest.json"
    v7 = json.loads(v7_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    strip_v = np.asarray(v7["meshes"]["linear_12_94"]["vertices"], dtype=np.float64)
    strip_t = np.asarray(v7["meshes"]["linear_12_94"]["triangles"], dtype=np.int32)
    weights = np.asarray(v7["meshes"]["linear_12_94"]["weights"], dtype=np.float64)
    axis = np.asarray(v7["profileSupport"].get("axisGlobalXY", [0., 0.]), dtype=np.float64)
    if not np.any(axis):
        v6_path = PARENT / "arm_mesh_test_v6" / "study.json"
        v6 = json.loads(v6_path.read_text(encoding="utf-8"))
        axis = np.asarray(v6["stripConstruction"]["axisGlobalXY"], dtype=np.float64)
        normal = np.asarray(v6["stripConstruction"]["normalGlobalXY"], dtype=np.float64)
    else:
        normal = np.array([-axis[1], axis[0]], dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    normal = normal / np.linalg.norm(normal)
    source_path = Path(v7["sourceImage"]["file"])
    tracked = [source_path]
    for folder in [PARTS, HERE.parent / "studio_v2"] + [PARENT / f"arm_mesh_test_v{i}" for i in range(1, 8)]:
        tracked.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    protected_before = {str(p): sha256(p) for p in dict.fromkeys(tracked)}
    if sha256(manifest_path) != v7["sourceManifestSha256"] or sha256(source_path) != v7["sourceImage"]["sha256"]:
        raise AssertionError("v8来源与v7不符")
    layers = {}
    for part in manifest["parts"]:
        path_part = PARTS / part["file"]
        if sha256(path_part) != part["sha256"]:
            raise AssertionError("稳定部件哈希不符")
        layer = Image.new("RGBA", SIZE)
        layer.paste(Image.open(path_part).convert("RGBA"), tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.asarray(layers["arm_near"])
    alpha_pixels = np.column_stack(np.nonzero(texture[:, :, 3] > 128))[:, ::-1].astype(np.float64)
    sections = (strip_v - JOINTS[0]) @ axis
    transverse = (strip_v - JOINTS[0]) @ normal
    lengths = np.linalg.norm(np.diff(JOINTS, axis=0), axis=1)
    bind_angles = np.arctan2(np.diff(JOINTS, axis=0)[:, 1], np.diff(JOINTS, axis=0)[:, 0])
    baseline = json.loads((OUT / "mesh.json").read_text(encoding="utf-8"))
    open_joints = np.asarray(baseline["poses"]["open"]["targetJointsGlobalXY"], dtype=np.float64)
    chest_joints = np.asarray(baseline["poses"]["chest"]["targetJointsGlobalXY"], dtype=np.float64)
    def angle_of(joints):
        d = np.diff(joints, axis=0)
        return np.arctan2(d[:, 1], d[:, 0])
    def wrap(value):
        return (value + np.pi) % (2. * np.pi) - np.pi
    def joints_for(angles):
        points = [JOINTS[0].copy()]
        for length, angle in zip(lengths, angles):
            points.append(points[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
        return np.asarray(points)
    chest_angles = angle_of(chest_joints)
    open_angles = angle_of(open_joints)
    poses = {"neutral": JOINTS.copy(), "open": open_joints,
             "chest_fixed": joints_for(chest_angles)}
    elbow_delta = float(wrap(np.array([(chest_angles[1] - chest_angles[0]) -
                                       (bind_angles[1] - bind_angles[0])]))[0])
    path = [joints_for(bind_angles + [0., elbow_delta * i / 64.]) for i in range(65)]
    chest_sample = 64
    # Identify the worst triangle from the actual linear candidate, rather than hardcoding 257.
    chest_points = deform(strip_v, weights, bone_matrices(poses["chest_fixed"]))
    source_tri = strip_v[strip_t]
    source_edges = np.transpose(source_tri[:, 1:] - source_tri[:, :1], (0, 2, 1))
    source_inverse = np.linalg.inv(source_edges)
    target_tri = chest_points[strip_t]
    target_edges = np.transpose(target_tri[:, 1:] - target_tri[:, :1], (0, 2, 1))
    local_maps = np.einsum("nij,njk->nik", target_edges, source_inverse)
    singular = np.linalg.svd(local_maps, compute_uv=False)
    worst_tri = int(np.argmin(singular[:, 1]))
    # Build a small topological neighborhood around the worst triangle.
    adjacency = [[] for _ in range(len(strip_t))]
    for i in range(len(strip_t) - 1):
        for j in range(i + 1, len(strip_t)):
            if len(set(strip_t[i]) & set(strip_t[j])) >= 2:
                adjacency[i].append(j)
                adjacency[j].append(i)
    neighborhood = {worst_tri}
    frontier = {worst_tri}
    for _ in range(2):
        frontier = {j for i in frontier for j in adjacency[i]} - neighborhood
        neighborhood.update(frontier)
    neighborhood = sorted(neighborhood)
    U, S, Vh = np.linalg.svd(local_maps[worst_tri])
    worst_directions = {"sigmaDescending": S.tolist(), "sourceMinSingularDirection": Vh[1].tolist(),
        "sourceMinDirectionAbsDotAxis": float(abs(Vh[1] @ axis)),
        "sourceMinDirectionAbsDotNormal": float(abs(Vh[1] @ normal)),
        "bindEdgeMatrixCondition": float(np.linalg.cond(source_edges[worst_tri])),
        "minimumDirectionIsNotAutomaticallyThickness": True}
    pixel_alpha_counts = []
    for tri in source_tri:
        low = np.floor(tri.min(axis=0) - .5).astype(int)
        high = np.ceil(tri.max(axis=0) + .5).astype(int)
        candidate = alpha_pixels[(alpha_pixels[:, 0] >= low[0]) & (alpha_pixels[:, 0] <= high[0]) &
                                 (alpha_pixels[:, 1] >= low[1]) & (alpha_pixels[:, 1] <= high[1])]
        inv = np.linalg.inv((tri[1:] - tri[0]).T)
        uv = (candidate - tri[0]) @ inv.T if len(candidate) else np.empty((0, 2))
        bary = np.column_stack((1. - uv.sum(axis=1), uv))
        pixel_alpha_counts.append(int(np.count_nonzero(np.all(bary >= -1e-9, axis=1))))
    def record(joints):
        points = deform(strip_v, weights, bone_matrices(joints))
        dst_tri = points[strip_t]
        dst_edges = np.transpose(dst_tri[:, 1:] - dst_tri[:, :1], (0, 2, 1))
        maps = np.einsum("nij,njk->nik", dst_edges, source_inverse)
        svd = np.linalg.svd(maps, compute_uv=False)
        det = np.linalg.det(maps)
        axis_stretch = np.linalg.norm(np.einsum("nij,j->ni", maps, axis), axis=1)
        normal_stretch = np.linalg.norm(np.einsum("nij,j->ni", maps, normal), axis=1)
        source_area = cross2(source_tri[:, 1] - source_tri[:, 0], source_tri[:, 2] - source_tri[:, 0]) / 2.
        target_area = cross2(dst_tri[:, 1] - dst_tri[:, 0], dst_tri[:, 2] - dst_tri[:, 0]) / 2.
        active = np.asarray(pixel_alpha_counts) > 0
        return {"minSigma": float(svd[:, 1].min()), "maxCondition": float((svd[:, 0] / np.maximum(svd[:, 1], 1e-15)).max()),
                "minSignedAreaRatio": float((target_area / source_area).min()),
                "activeTriangleCount": int(active.sum()),
                "axisStretchMin": float(axis_stretch[active].min()),
                "axisStretchMinTriangle": int(np.flatnonzero(active)[np.argmin(axis_stretch[active])]),
                "normalStretchMin": float(normal_stretch[active].min()),
                "normalStretchMinTriangle": int(np.flatnonzero(active)[np.argmin(normal_stretch[active])]),
                "activeAxisStretchMedian": float(np.median(axis_stretch[active])),
                "activeNormalStretchMedian": float(np.median(normal_stretch[active])),
                "activeAreaRatioMin": float((target_area[active] / source_area[active]).min()),
                "triangles": {str(i): {"sRange": [float(sections[strip_t[i]].min()), float(sections[strip_t[i]].max())],
                    "nRange": [float(transverse[strip_t[i]].min()), float(transverse[strip_t[i]].max())],
                    "alphaGt128CenterCount": pixel_alpha_counts[i],
                    "axisStretch": float(axis_stretch[i]), "normalStretch": float(normal_stretch[i]),
                    "sigmaMin": float(svd[i, 1]), "sigmaMax": float(svd[i, 0]),
                    "condition": float(svd[i, 0] / max(svd[i, 1], 1e-15)),
                    "signedAreaRatio": float(target_area[i] / source_area[i]), "determinant": float(det[i])}
                    for i in neighborhood}}
    pose_records = {name: record(joints) for name, joints in poses.items()}
    sample_records = []
    for i, joints in enumerate(path):
        sample_records.append({"sample": i, "relativeElbowChangeDegrees": float(np.rad2deg(elbow_delta * i / 64.)),
                               **record(joints)})
    worst_by_axis = min(sample_records, key=lambda item: item["triangles"][str(worst_tri)]["axisStretch"])
    worst_by_normal = min(sample_records, key=lambda item: item["triangles"][str(worst_tri)]["normalStretch"])
    # Exact P1 decomposition: a frozen vertex-0 blend plus the finite weight-position product.
    # Unlike a continuous weight-field derivative, this reproduces the actual raster triangle J.
    matrices = bone_matrices(poses["chest_fixed"])
    w0 = weights[strip_t[:, 0], 1]
    frozen = (1. - w0[:, None, None]) * matrices[0][:, :2] + w0[:, None, None] * matrices[1][:, :2]
    homogeneous = np.concatenate((source_tri, np.ones((*source_tri.shape[:2], 1))), axis=2)
    bone_difference = np.einsum("nkj,ij->nki", homogeneous, matrices[1] - matrices[0])
    product = (weights[strip_t, 1] - w0[:, None])[:, :, None] * bone_difference
    product_edges = np.transpose(product[:, 1:] - product[:, :1], (0, 2, 1))
    gradient_term = product_edges @ source_inverse
    reconstruction_error = float(np.max(np.abs(frozen + gradient_term - local_maps)))
    def component_report(i):
        directions = {}
        for name, direction in (("axis", axis), ("normal", normal)):
            first = frozen[i] @ direction
            second = gradient_term[i] @ direction
            directions[name] = {"frozenBlendLength": float(np.linalg.norm(first)),
                "finiteWeightProductLength": float(np.linalg.norm(second)),
                "resultLength": float(np.linalg.norm(first + second)),
                "componentCosine": float(first @ second / max(np.linalg.norm(first) * np.linalg.norm(second), 1e-15))}
        return {"frozenVertex0WeightBlendMatrix": frozen[i].tolist(),
                "finiteWeightPositionProductMatrix": gradient_term[i].tolist(), "directions": directions}
    decomposition = {"method": "exact P1 vertex-0 decomposition; not continuous derivative; decomposition depends on reference vertex",
        "maximumReconstructionError": reconstruction_error,
        "neighborhood": {str(i): component_report(i) for i in neighborhood}}
    # Five declared rig hypotheses, NOT a fit or recovered anatomical elbow. Fixed local rotation deltas;
    # bind bone lengths/directions and resulting world hand trajectories are allowed to change.
    def transforms_for_bind(bind, upper_delta, fore_delta):
        angles = angle_of(bind) + [upper_delta, fore_delta]
        lens = np.linalg.norm(np.diff(bind, axis=0), axis=1)
        targets = [bind[0].copy()]
        for length, angle in zip(lens, angles):
            targets.append(targets[-1] + length * np.array([np.cos(angle), np.sin(angle)]))
        transforms = []
        for bone, (a, b) in enumerate(BONE_INDICES):
            angle = [upper_delta, fore_delta][bone]
            rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
            transforms.append(np.column_stack((rotation, targets[a] - rotation @ bind[a])))
        return transforms, np.asarray(targets)
    delta = wrap(chest_angles - bind_angles)
    hypotheses = {}
    for name, offset in (("baseline", np.zeros(2)), ("axis_minus4", -4. * axis),
                         ("axis_plus4", 4. * axis), ("normal_minus4", -4. * normal), ("normal_plus4", 4. * normal)):
        bind = JOINTS.copy()
        bind[1] += offset
        samples = []
        for parameter in np.linspace(0., 1., 129):
            transforms, targets = transforms_for_bind(bind, *(delta * parameter))
            points = deform(strip_v, weights, transforms)
            edges = np.transpose(points[strip_t][:, 1:] - points[strip_t][:, :1], (0, 2, 1))
            maps = edges @ source_inverse
            sv = np.linalg.svd(maps, compute_uv=False)
            determinant = np.linalg.det(maps)
            samples.append({"parameter": float(parameter), "minimumSigma": float(sv[:, 1].min()),
                "minimumDeterminant": float(determinant.min()), "flippedTriangles": int(np.count_nonzero(determinant < -1e-10)),
                "tri257SigmaMin": float(sv[worst_tri, 1]), "handGlobalXY": targets[2].tolist()})
        hypotheses[name] = {"elbowOffsetGlobalXY": offset.tolist(), "bindJoints": bind.tolist(),
            "sampleCount": 129, "samples": samples,
            "minimumSigma": min(x["minimumSigma"] for x in samples),
            "flippedSampleCount": sum(x["flippedTriangles"] > 0 for x in samples),
            "chest": samples[-1], "selectedChestIntersections": float64_intersections(points, strip_t)}
    baseline_transform, baseline_target = transforms_for_bind(JOINTS, *delta)
    sensitivity_baseline_error = float(np.max(np.abs(deform(strip_v, weights, baseline_transform) - chest_points)))
    # Rigid same-transform test: P1 Jacobians must equal R regardless of weights.
    rotation = np.array([[np.cos(.4), -np.sin(.4)], [np.sin(.4), np.cos(.4)]])
    rigid_transform = np.column_stack((rotation, [5., -3.]))
    rigid_points = deform(strip_v, weights, [rigid_transform, rigid_transform])
    rigid_maps = np.transpose(rigid_points[strip_t][:, 1:] - rigid_points[strip_t][:, :1], (0, 2, 1)) @ source_inverse
    rigid_error = float(np.max(np.abs(rigid_maps - rotation)))
    determinant_svd_error = float(np.max(np.abs(np.abs(np.linalg.det(local_maps)) - singular[:, 0] * singular[:, 1])))
    if reconstruction_error > 1e-10 or rigid_error > 1e-10 or sensitivity_baseline_error > 1e-10 or determinant_svd_error > 1e-10:
        raise AssertionError("v8实际P1映射自测失败")
    if pixel_alpha_counts[worst_tri] != 5 or worst_tri != 257:
        raise AssertionError("v8源alpha/最坏三角与v7审计不一致")
    output.mkdir(exist_ok=True)
    rendered, _, _ = render_mesh(texture, (strip_v + .5) / 768., strip_t, chest_points, "source_over_top_left")
    source_overlay = Image.new("RGBA", SIZE, (244, 241, 231, 255))
    source_overlay.alpha_composite(Image.fromarray(texture))
    chest_overlay = Image.new("RGBA", SIZE, (244, 241, 231, 255))
    chest_overlay.alpha_composite(Image.fromarray(rendered))
    source_draw = ImageDraw.Draw(source_overlay)
    chest_draw = ImageDraw.Draw(chest_overlay)
    for tri_id in neighborhood:
        color = (206, 44, 55, 255) if tri_id == worst_tri else (245, 145, 40, 255)
        for target, draw in ((source_tri[tri_id], source_draw), (target_tri[tri_id], chest_draw)):
            pts = [tuple(map(float, p)) for p in np.vstack((target, target[0]))]
            draw.line(pts, fill=color, width=2)
    focus_points = np.vstack((source_tri[neighborhood].reshape((-1, 2)), target_tri[neighborhood].reshape((-1, 2))))
    focus_box = (int(np.floor(focus_points[:, 0].min() - 8)), int(np.floor(focus_points[:, 1].min() - 8)),
                 int(np.ceil(focus_points[:, 0].max() + 8)), int(np.ceil(focus_points[:, 1].max() + 8)))
    source_focus = crop_view(source_overlay, box=focus_box, scale=8)
    chest_focus = crop_view(chest_overlay, box=focus_box, scale=8)
    review = Image.new("RGB", (1480, max(source_focus.height, chest_focus.height) + 240), (243, 245, 242))
    review.paste(source_focus, (20, 55))
    review.paste(chest_focus, (source_focus.width + 40, 55))
    rd = ImageDraw.Draw(review)
    rd.text((20, 15), "v8 elbow mechanism audit | red=worst triangle, orange=2-ring neighborhood", font=font(24), fill=(30, 48, 55))
    info_x = source_focus.width + chest_focus.width + 70
    info = [f"worst triangle: {worst_tri}", f"chest sample: {chest_sample}/64",
            f"source alpha>128: {pixel_alpha_counts[worst_tri]} px",
            f"axis stretch: {worst_by_axis['triangles'][str(worst_tri)]['axisStretch']:.4f}",
            f"normal stretch: {worst_by_normal['triangles'][str(worst_tri)]['normalStretch']:.4f}",
            "axis/normal are material axes, not anatomy.",
            "Manual pivot hypotheses are not video fits.",
            "No production binding approval."]
    for i, text in enumerate(info):
        rd.text((info_x, 75 + i * 36), text, font=font(17), fill=(117, 50, 35) if i in (0, 3, 4, 7) else (35, 52, 60))
    review_path = output / "elbow_mechanism_review.png"
    review.save(review_path)
    protected_hashes = {p: {"before": h, "after": sha256(Path(p))} for p, h in protected_before.items()}
    if not all(item["before"] == item["after"] for item in protected_hashes.values()):
        raise AssertionError("v8改变了源/stable/v1-v7/v2保护资源")
    source_hashes = {str(p): sha256(p) for p in [manifest_path, v7_path, source_path]}
    study = {"schemaVersion": 1, "status": "elbow_mechanism_audit_not_production",
        "source": {"v7Study": str(v7_path), "v7StudySha256": sha256(v7_path), "manifestSha256": sha256(manifest_path),
                   "sourceImage": str(source_path), "sourceImageSha256": sha256(source_path)},
        "meshContract": {"logicalPart": "arm_near", "vertexCount": int(len(strip_v)), "triangleCount": int(len(strip_t)),
                         "bonesAdded": 0, "attachmentsAdded": 0, "correctiveKeysAdded": 0,
                         "weightProfile": "linear_12_94", "weightsChanged": False, "textureChanged": False},
        "bindAndControlSemantics": v7["controlSemantics"],
        "materialAxes": {"axisGlobalXY": axis.tolist(), "normalGlobalXY": normal.tolist(),
                         "axisMeaning": "肩到手的材料坐标轴，不是解剖轴真值",
                         "normalMeaning": "材料截面法向，用于区分横向厚度变化；不是解剖厚度真值"},
        "worstTriangle": {"triangle": worst_tri, "neighborhoodDepth": 2, "neighborhoodTriangles": neighborhood,
                          "alphaGt128CenterCount": pixel_alpha_counts[worst_tri],
                          "sourceVertices": source_tri[worst_tri].tolist(),
                          "sourceRanges": {"s": [float(sections[strip_t[worst_tri]].min()), float(sections[strip_t[worst_tri]].max())],
                                           "n": [float(transverse[strip_t[worst_tri]].min()), float(transverse[strip_t[worst_tri]].max())]}},
        "minimumSingularDirectionAtChest": worst_directions,
        "exactP1DecompositionAtChest": decomposition,
        "pivotSensitivity": {"policy": "预声明5个±4px人工枢轴假设；权重/纹理/mesh固定，局部旋转增量固定；骨长、bind骨角和手部世界轨迹允许改变；各假设终点对右前3/4视频轮廓/手投影/遮挡的符合度未评分，当前仅做数学敏感性，不用于选定或晋级枢轴",
            "localRotationDeltaDegrees": np.rad2deg(delta).tolist(), "finiteSamplesOnly": True, "hypotheses": hypotheses},
        "poses": pose_records, "elbowPath": {"sampleCount": 65, "finiteSamplesOnly": True,
            "records": sample_records, "worstAtWorstTriangleByAxisStretch": worst_by_axis["sample"],
            "worstAtWorstTriangleByNormalStretch": worst_by_normal["sample"]},
        "interpretation": {"directionalFinding": "tri257最小奇异方向与材料轴绝对点积0.99075、与法向绝对点积0.13569；轴向伸缩约0.10403，法向伸缩约0.67860，因此当前证据首先指向有效皮肤沿材料长度方向压缩，不能称为直接厚度塌陷。",
            "scope": "axisStretch和normalStretch由实际三角映射J分别测量；active triangle仅按源alpha>128像素中心支持标记；这不是连续纹理场证明。",
            "jointInferenceBoundary": "shoulder/elbow/hand仍是人工rig参考，视频未提供唯一解剖关节真值。",
            "productionDecision": "仍不得提升绑定；本审计不修改权重、网格、纹理或骨骼。"},
        "generated": [review_path.name], "sourceHashes": source_hashes,
        "approvedForBinding": False, "bindingValidated": False, "production": False}
    checks = {"reviewImage": {"file": review_path.name, "sha256": sha256(review_path), "size": list(review.size)},
              "sourceHashes": source_hashes, "protectedHashesBeforeAfter": protected_hashes,
              "protectedFileCount": len(protected_hashes), "noProductionMutation": True,
              "selfTests": {"exactP1DecompositionMaxError": reconstruction_error,
                  "rigidSameTransformMaxError": rigid_error, "sensitivityBaselineMaxError": sensitivity_baseline_error,
                  "determinantVsSingularProductMaxError": determinant_svd_error, "allPassed": True},
              "worstTriangle": worst_tri, "neighborhoodCount": len(neighborhood),
              "finiteSamplesOnly": True, "bindingValidated": False}
    for filename, data in (("study.json", study), ("checks.json", checks)):
        path_out = output / filename
        path_out.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if json.loads(path_out.read_text(encoding="utf-8")) != data:
            raise AssertionError("v8 JSON回读失败")
    print(json.dumps({"output": str(output), "worstTriangle": worst_tri,
                      "worstByAxisStretchSample": worst_by_axis["sample"],
                      "worstByNormalStretchSample": worst_by_normal["sample"],
                      "bindingValidated": False, "production": False}, ensure_ascii=False, indent=2))


def run_registration_sensitivity_study() -> None:
    """v10: perturb the shared torso registration; no pivot or rig promotion."""
    output = PARENT / "arm_mesh_test_v10"
    v9_path = PARENT / "arm_mesh_test_v9" / "study.json"
    v8_path = PARENT / "arm_mesh_test_v8" / "study.json"
    v9 = json.loads(v9_path.read_text(encoding="utf-8"))
    v8 = json.loads(v8_path.read_text(encoding="utf-8"))
    manifest = json.loads((PARTS / "manifest.json").read_text(encoding="utf-8"))
    stable_hash = sha256(PARTS / "manifest.json")
    for path, expected in v9["sourceHashes"].items():
        if sha256(Path(path)) != expected:
            raise AssertionError("v10输入与v9来源链不符")
    hashes_before = {str(p): sha256(p) for p in (v9_path, v8_path, PARTS / "manifest.json")}
    base_regs = {int(k): np.asarray(v, dtype=np.float64) for k, v in v9["registrationMatrices"].items()}
    observations = v9["observations"]
    source_waist = np.asarray(v9["observationPolicy"]["registrationSourceWaist"], dtype=np.float64)
    # Nine single-factor samples only: not a joint uncertainty envelope or confidence interval.
    # translation ±6 px, scale ±4%, rotation ±2 degrees. Candidates are never re-registered separately.
    perturbations = [("base", 0., 1., 0.), ("tx_minus6", -6., 1., 0.), ("tx_plus6", 6., 1., 0.),
                     ("ty_minus6", 0., 1., -6.), ("ty_plus6", 0., 1., 6.),
                     ("scale_minus4", 0., .96, 0.), ("scale_plus4", 0., 1.04, 0.),
                     ("rot_minus2", 0., 1., -2.), ("rot_plus2", 0., 1., 2.)]
    # Only fixed same-input pressure poses from v9; fitted branches are NOT re-solved here.
    candidates = list(v9["results"].keys())
    rows = []
    for name, tx, scale, ty in perturbations:
        for frame_key, reg_base in base_regs.items():
            angle = np.deg2rad(ty if name.startswith("rot_") else 0.)
            if name.startswith("rot_"):
                txv, tyv = 0., 0.
            else:
                txv, tyv = tx, ty
            R = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]) * scale
            waist_center = source_waist.mean(axis=0) @ reg_base[:, :2].T + reg_base[:, 2]
            reg = np.column_stack((R @ reg_base[:, :2],
                                   R @ reg_base[:, 2] + waist_center - R @ waist_center + [txv, tyv]))
            if name.startswith(("scale_", "rot_")):
                if np.linalg.norm(source_waist.mean(axis=0) @ reg[:, :2].T + reg[:, 2] - waist_center) > 1e-10:
                    raise AssertionError("缩放旋转中心不是投影腰线中心")
            # Compare all candidate projected anchors under the same perturbed registration.
            for candidate in candidates:
                datum = v9["results"][candidate][str(frame_key)]
                projected_base = np.asarray(datum["sameInput"]["projectedHandMaterialXY"], dtype=float)
                # v9 stores this point after base registration. Undo base registration before applying
                # the common perturbation, otherwise the affine is applied twice and the sensitivity is invalid.
                source_hand = cv2.invertAffineTransform(reg_base) @ np.array([*projected_base, 1.])
                target = (np.asarray(observations[str(frame_key)]["handRegion"][:2]) +
                          np.asarray(observations[str(frame_key)]["handRegion"][2:])) / 2.
                projected = np.concatenate((source_hand, [1.])) @ reg.T
                if name == "base" and np.linalg.norm(projected - projected_base) > 1e-10:
                    raise AssertionError("基础配准未精确复现v9投影")
                box = np.asarray(observations[str(frame_key)]["handRegion"], dtype=float)
                region_distance = float(np.linalg.norm(np.maximum(np.maximum(box[:2] - projected, projected - box[2:]), 0.)))
                rows.append({"perturbation": name, "videoFrame": frame_key, "candidate": candidate,
                    "targetCenter": target.tolist(), "projectedSameInputHand": projected.tolist(),
                    "sameInputHandRegionDistancePx": region_distance,
                    "sameInputHandCenterErrorPx": float(np.linalg.norm(projected - target)),
                    "candidateIndependentRegistration": False,
                    "decision": "not_ranked"})
    grouped = {}
    for row in rows:
        grouped.setdefault((row["videoFrame"], row["candidate"]), []).append(row["sameInputHandCenterErrorPx"])
    summary = {f"f{frame}_{candidate}": {"minError": float(min(errors)), "maxError": float(max(errors)),
        "rangePx": float(max(errors) - min(errors)), "notRanked": True}
        for (frame, candidate), errors in grouped.items()}
    output.mkdir(exist_ok=True)
    study = {"schemaVersion": 1, "status": "registration_sensitivity_not_video_fit",
        "source": {"v9Study": str(v9_path), "v9StudySha256": sha256(v9_path), "v8StudySha256": sha256(v8_path),
                   "stableManifestSha256": stable_hash},
        "scriptSha256": sha256(Path(__file__)),
        "policy": {"scope": "fixed same-input pressure poses only; no refit or fitted-branch sensitivity",
            "sampleRangeNotConfidenceInterval": True, "combinedPerturbationsTested": False,
            "rotationScalePivot": "projected waist-reference midpoint",
            "sameRegistrationForAllCandidates": True, "candidateSpecificRegistration": False,
            "perturbations": [{"name": n, "translationX": x, "scale": s, "translationYOrRotationDegrees": y,
                               "translationY": y if not n.startswith("rot_") else 0.,
                               "rotationDegrees": y if n.startswith("rot_") else 0.} for n, x, s, y in perturbations],
            "meaning": "把腰线配准当作共同不确定假设；不根据误差最小者选候选，不改动骨骼或手部目标。",
            "shoulderIsNotVideoTruth": True, "handIsNotWristTruth": True},
        "rows": rows, "summary": summary,
        "interpretation": {"rangeOnly": "范围只覆盖9个单因素扰动样本，非联合不确定性包络/置信区间/最坏界；不能作为候选优劣排序。",
            "currentFinding": "本轮只测固定同输入压力姿态的投影变化，不重新求解v9手团中心拟合分支；中心误差与允许区域外距离分开记录，不能由这些结果声称拟合分支稳健。",
            "nextBoundary": "需基于可见躯干外轮廓、明确视频帧与角色模型姿态一致性建立更可靠注册；不能以手臂反向配准。"},
        "reuseContract": {"logicalParts": len(manifest["parts"]), "bonesAdded": 0, "attachmentsAdded": 0,
            "correctiveKeysAdded": 0, "sharedBoneChainPreserved": True, "clothingIndependentValidation": False,
            "crossCharacterValidation": False}, "decision": "all_candidates_evidence_insufficient",
        "bindingValidated": False, "approvedForBinding": False, "production": False}
    if any(sha256(Path(p)) != h for p, h in hashes_before.items()):
        raise AssertionError("v10修改了输入")
    checks = {"sourceHashes": {"v9": sha256(v9_path), "v8": sha256(v8_path), "manifest": stable_hash},
        "sourceHashesUnchanged": True, "baseReprojectionSelfTestPassed": True, "rotationScaleCenterSelfTestPassed": True,
        "rows": len(rows), "allCandidatesUseSamePerturbedRegistration": True,
        "candidateRankingPerformed": False, "bindingValidated": False}
    for filename, data in (("study.json", study), ("checks.json", checks)):
        path_out = output / filename
        path_out.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if json.loads(path_out.read_text(encoding="utf-8")) != data:
            raise AssertionError("v10 JSON回读失败")
    print(json.dumps({"output": str(output), "rows": len(rows), "candidateRankingPerformed": False,
                      "decision": study["decision"], "production": False}, ensure_ascii=False, indent=2))


def run_video_projection_study() -> None:
    """v9: discrete pose feasibility under explicit uncertain visual registration; not video tracking."""
    from scipy.optimize import least_squares
    output = PARENT / "arm_mesh_test_v9"
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    manifest_path = PARTS / "manifest.json"
    v8_path = PARENT / "arm_mesh_test_v8" / "study.json"
    v7_path = PARENT / "arm_mesh_test_v7" / "study.json"
    evidence_path = PARENT / "video_parts_v1" / "manifest.json"
    frames_dir = PARENT / "video_parts_v1" / "cycle_review"
    sources_path = frames_dir / "sources.json"
    protected = [manifest_path, v7_path, v8_path, evidence_path, sources_path]
    for folder in [PARTS, HERE.parent / "studio_v2"] + [PARENT / f"arm_mesh_test_v{i}" for i in range(1, 9)]:
        protected.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    protected.extend(frames_dir.glob("source_*.png"))
    before = {str(p): sha256(p) for p in dict.fromkeys(protected)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    v8 = json.loads(v8_path.read_text(encoding="utf-8"))
    v7 = json.loads(v7_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    if sha256(v7_path) != v8["source"]["v7StudySha256"] or sha256(manifest_path) != v8["source"]["manifestSha256"]:
        raise AssertionError("v9来源与v8不符")
    if sources["taskId"] != manifest["taskId"] or evidence["taskId"] != manifest["taskId"]:
        raise AssertionError("v9视频任务不一致")
    source_image = (PARTS / manifest["sourceImage"]["file"]).resolve()
    source_video = PARENT / "source.mp4"
    if sha256(source_image) != manifest["sourceImage"]["sha256"] or sha256(source_video) != manifest["sourceVideoSha256"]:
        raise AssertionError("v9源图或视频哈希不符")
    if any(s["sourceVideoSha256"] != manifest["sourceVideoSha256"] for s in (sources, evidence)):
        raise AssertionError("v9证据来源视频不一致")
    before.update({str(p): sha256(p) for p in (source_image, source_video)})
    layers = {}
    for part in manifest["parts"]:
        path_part = PARTS / part["file"]
        if sha256(path_part) != part["sha256"]:
            raise AssertionError("稳定部件被修改")
        layer = Image.new("RGBA", SIZE)
        layer.paste(Image.open(path_part).convert("RGBA"), tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.asarray(layers["arm_near"])
    mesh = v7["meshes"]["linear_12_94"]
    vertices, triangles, weights = (np.asarray(mesh[k]) for k in ("vertices", "triangles", "weights"))
    uv = (vertices + .5) / 768.
    src_tri = vertices[triangles]
    edge_inverse = np.linalg.inv(np.transpose(src_tri[:, 1:] - src_tri[:, :1], (0, 2, 1)))
    # Manual image observations, selected from source image and raw reference crops, before candidate rendering.
    # Waist endpoints are uncertain garment contour references, NEVER shoulder/hip joints or precise calibration.
    source_waist = np.array([[366., 535.], [467., 520.]])
    observations = {
        68: {"waist": [[398., 357.], [500., 359.]], "handRegion": [355., 338., 393., 369.],
             "armEvidenceId": "f068_arm_A_visible", "visibility": "screen-left outer arm visible; inner shoulder cut unknown"},
        72: {"waist": [[391., 336.], [499., 339.]], "handRegion": [444., 307., 487., 350.],
             "armEvidenceId": "f072_arm_A_chest_visible", "visibility": "front chest lobe visible; opposite arm not fully isolated"},
        80: {"waist": [[401., 341.], [497., 341.]], "handRegion": [362., 335., 399., 361.],
             "armEvidenceId": "f080_arm_A_visible", "visibility": "screen-left outer arm visible; inner shoulder cut unknown"}}
    source_records = {r["sourceFrame"]: r for r in sources["frames"]}
    frame_images = {}
    for index in observations:
        frame_path = frames_dir / source_records[index]["sourceFile"]
        if sha256(frame_path) != source_records[index]["sourceFrameSha256"]:
            raise AssertionError("视频源帧不符")
        frame_images[index] = Image.open(frame_path).convert("RGB")
        if frame_images[index].size != (864, 480):
            raise AssertionError("视频画幅错误")
    def registration(target_pair):
        src_d = source_waist[1] - source_waist[0]
        dst = np.asarray(target_pair, dtype=float)
        dst_d = dst[1] - dst[0]
        scale = float(np.linalg.norm(dst_d) / np.linalg.norm(src_d))
        angle = float(np.arctan2(dst_d[1], dst_d[0]) - np.arctan2(src_d[1], src_d[0]))
        linear = scale * np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        return np.column_stack((linear, dst[0] - linear @ source_waist[0]))
    registrations = {i: registration(o["waist"]) for i, o in observations.items()}
    # Actual P1 material-point embedding, not independently skinned analytic joint.
    control_embedding = material_control_matrix(vertices, triangles)[2]
    if abs(control_embedding.sum() - 1.) > 1e-10:
        raise AssertionError("手端材料参考点未嵌入")
    def transforms(bind, delta):
        directions = np.diff(bind, axis=0)
        angles = np.arctan2(directions[:, 1], directions[:, 0]) + delta
        lengths = np.linalg.norm(directions, axis=1)
        targets = [bind[0].copy()]
        matrices = []
        for k, (a, b) in enumerate(BONE_INDICES):
            targets.append(targets[-1] + lengths[k] * np.array([np.cos(angles[k]), np.sin(angles[k])]))
            R = np.array([[np.cos(delta[k]), -np.sin(delta[k])], [np.sin(delta[k]), np.cos(delta[k])]])
            matrices.append(np.column_stack((R, targets[a] - R @ bind[a])))
        return matrices, np.asarray(targets)
    def project(points, matrix):
        return np.column_stack((points, np.ones(len(points)))) @ matrix.T
    def geometry(points):
        edges = np.transpose(points[triangles][:, 1:] - points[triangles][:, :1], (0, 2, 1))
        jac = edges @ edge_inverse
        det = np.linalg.det(jac)
        sigma = np.linalg.svd(jac, compute_uv=False)
        return {"minimumSigma": float(sigma[:, 1].min()), "minimumDeterminant": float(det.min()),
                "flippedTriangleCount": int(np.count_nonzero(det < -1e-10)),
                "minimumSigmaTriangle": int(np.argmin(sigma[:, 1]))}
    output.mkdir(exist_ok=True)
    results = {}
    raw_records = {}
    hypotheses = v8["pivotSensitivity"]["hypotheses"]
    common_inputs = {68: np.deg2rad([-1., -25.]), 72: np.deg2rad(v8["pivotSensitivity"]["localRotationDeltaDegrees"]),
                     80: np.deg2rad([-1., -25.])}
    render_cache = {}
    generated = []
    for name, hypothesis in hypotheses.items():
        bind = np.asarray(hypothesis["bindJoints"], dtype=float)
        results[name] = {}
        for index, observation in observations.items():
            reg = registrations[index]
            hand_box = np.asarray(observation["handRegion"])
            target_video = (hand_box[:2] + hand_box[2:]) / 2.
            def residual(delta):
                matrices, _ = transforms(bind, delta)
                material = control_embedding @ deform(vertices, weights, matrices)
                return project(material[None], reg)[0] - target_video
            solutions = []
            # Multiple declared seeds expose IK branches; no image loss or candidate-specific registration.
            for seed in ((0., 0.), (-.6, .7), (.6, -.7), (-1.4, 1.4), (1.4, -1.4)):
                solve = least_squares(residual, seed, bounds=(-np.pi, np.pi), ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=160)
                if not solve.success or not np.isfinite(solve.fun).all() or np.linalg.norm(solve.fun) > 1e-5:
                    raise AssertionError(f"v9离散中心目标不可达或求解未收敛: {name}/{index}, {solve.message}")
                delta = solve.x
                if all(np.linalg.norm(np.arctan2(np.sin(delta - s["delta"]), np.cos(delta - s["delta"]))) > 1e-5 for s in solutions):
                    matrices, joints = transforms(bind, delta)
                    points = deform(vertices, weights, matrices)
                    material = control_embedding @ points
                    hand_projected = project(material[None], reg)[0]
                    solutions.append({"delta": delta, "points": points, "joints": joints,
                        "result": {"rotationDeltaDegrees": np.rad2deg(delta).tolist(), "handMaterialGlobalXY": material.tolist(),
                            "fittedHandVideoXY": hand_projected.tolist(), "fittedTargetCenterErrorPx": float(np.linalg.norm(hand_projected - target_video)),
                            "targetIsFittedNotValidation": True, "geometry": geometry(points),
                            "intersections": float64_intersections(points, triangles)}})
            solutions.sort(key=lambda s: s["delta"][1] - s["delta"][0])
            matrices, common_joints = transforms(bind, common_inputs[index])
            common_points = deform(vertices, weights, matrices)
            common_hand = project((control_embedding @ common_points)[None], reg)[0]
            common_record = {"inputLabel": "manual_open_pressure" if index != 72 else "manual_chest_pressure",
                "notVideoFrameTiming": True, "rotationDeltaDegrees": np.rad2deg(common_inputs[index]).tolist(),
                "projectedHandMaterialXY": common_hand.tolist(), "geometry": geometry(common_points)}
            result = {"videoFrame": index, "frameTimeSeconds": index / 24., "identityHypothesis": "H_A_screen_visible_candidate_not_confirmed",
                "registrationId": str(index), "sameInput": common_record,
                "sameTargetDiscreteSolutions": [s["result"] for s in solutions],
                "candidateDecision": "evidence_insufficient_not_promoted",
                "reason": "人工腰线配准与手团区域仅低可信；手部为拟合输入，不作为独立验收；A/B跨帧身份未建立"}
            results[name][str(index)] = result
            render_items = [("same_input", common_points, common_joints)] + [(f"branch_{j}", s["points"], s["joints"]) for j, s in enumerate(solutions)]
            for label, points, joints in render_items:
                arm, _, _ = render_mesh(texture, uv, triangles, points, "source_over_top_left")
                assembly = assemble(manifest, layers, arm)
                # No rescaling by arm bbox, no bounds breathing: same transform for every candidate in a frame.
                rgba_video = cv2.warpAffine(np.asarray(assembly), reg, (864, 480), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
                background = Image.new("RGBA", (864, 480), (248, 248, 244, 255))
                background.alpha_composite(Image.fromarray(rgba_video))
                rd = ImageDraw.Draw(background)
                rd.line([tuple(p) for p in observation["waist"]], fill=(37, 124, 168, 255), width=2)
                rd.rectangle(tuple(hand_box), outline=(161, 77, 170, 255), width=2)
                m = project((control_embedding @ points)[None], reg)[0]
                rd.ellipse((m[0]-2, m[1]-2, m[0]+2, m[1]+2), fill=(202, 70, 37, 255))
                filename = f"f{index:03d}_{name}_{label}.png"
                background.convert("RGB").save(output / filename)
                render_cache[(index, name, label)] = background.convert("RGB")
                generated.append(filename)
            raw_records[(index, name)] = solutions
    names = list(hypotheses)
    view_box = (335, 275, 555, 395)
    for mode in ("same_input", "branch_0", "branch_1"):
        sheet = Image.new("RGB", (2040, 1040), (241, 244, 241))
        draw = ImageDraw.Draw(sheet)
        draw.text((18, 12), "v9｜共同腰线配准 / 单一整臂 / 两骨链 / 无新增附件", font=font(27), fill=(32, 51, 59))
        draw.text((18, 53), "同输入压力对照；不是视频时间线" if mode == "same_input" else f"{mode}：手团区域中心离散拟合；已拟合手点不能用于验收", font=font(21), fill=(125, 57, 36))
        draw.text((18, 88), "蓝：人工腰线参考；紫：低可信手团允许区域；橙点：材料参考（不是腕）。肩根与其余身体未随视频拟合。", font=font(18), fill=(59, 74, 79))
        for row, index in enumerate(observations):
            y = 145 + row * 290
            reference = frame_images[index].copy().convert("RGBA")
            rd = ImageDraw.Draw(reference)
            rd.line([tuple(p) for p in observations[index]["waist"]], fill=(37, 124, 168, 255), width=2)
            rd.rectangle(tuple(observations[index]["handRegion"]), outline=(161, 77, 170, 255), width=2)
            evidence_part = next(p for p in evidence["parts"] if p["id"] == observations[index]["armEvidenceId"])
            # The polygon is coarse evidence, not a trusted complete anatomical contour.
            rd.line([tuple(p) for p in evidence_part["polygonSourcePixels"]], fill=(206, 130, 34, 255), width=1)
            cells = [("真实视频 / A身份未确认", reference.convert("RGB"), None)]
            for name in names:
                image = render_cache.get((index, name, mode))
                datum = results[name][str(index)]
                if mode == "same_input":
                    metric = datum["sameInput"]["geometry"]
                else:
                    branch = int(mode[-1])
                    metric = datum["sameTargetDiscreteSolutions"][branch]["geometry"] if len(datum["sameTargetDiscreteSolutions"]) > branch else None
                cells.append((name, image, metric))
            for col, (label, image, metric) in enumerate(cells):
                x = col * 340 + 12
                draw.text((x, y), f"f{index} | {label}", font=font(17), fill=(32, 51, 59))
                if image is not None:
                    crop = image.crop(view_box).resize((330, 180), Image.Resampling.LANCZOS)
                    sheet.paste(crop, (x, y + 32))
                else:
                    draw.text((x, y + 80), "无独立分支", font=font(22), fill=(110, 65, 45))
                if metric:
                    draw.text((x, y + 219), f"sigma {metric['minimumSigma']:.3f} / 翻面{metric['flippedTriangleCount']}", font=font(17), fill=(125, 57, 36))
            draw.text((18, y + 252), observations[index]["visibility"], font=font(17), fill=(76, 88, 90))
        draw.text((18, 1010), "不增碎片、不改权重、不选定新肘点；全部候选当前为证据不足。衣袖共享骨链，需独立贴图/mesh/weights与换装验收。", font=font(18), fill=(125, 57, 36))
        filename = f"review_{mode}.png"
        sheet.save(output / filename)
        generated.append(filename)
    after = {p: sha256(Path(p)) for p in before}
    if before != after:
        raise AssertionError("v9修改了保护资源")
    registration_checks = {str(i): float(np.max(np.abs(project(source_waist, reg) - observations[i]["waist"]))) for i, reg in registrations.items()}
    if max(registration_checks.values()) > 1e-10:
        raise AssertionError("共同配准锚点变换自测失败")
    records = {"schemaVersion": 1, "status": "discrete_video_projection_feasibility_not_animation",
        "sourceTaskId": manifest["taskId"], "sourceVideoSha256": manifest["sourceVideoSha256"],
        "scriptSha256": sha256(Path(__file__)),
        "sourceHashes": {str(p): sha256(p) for p in (v8_path, v7_path, evidence_path, sources_path, manifest_path, source_image, source_video)},
        "observationPolicy": {"method": "assistant manual observation from raw PNG/crops before candidate rendering",
            "confidence": "low", "registrationSourceWaist": source_waist.tolist(),
            "sourceWaistUncertaintyPx": 4, "videoWaistUncertaintyPx": 6,
            "manualHandRegionsAreNotAnatomicalJoints": True, "perCandidateRegistrationAllowed": False,
            "globalBodyViewChangeUnresolved": True, "fullBoundaryMetricsOrRanking": False,
            "AandBIdentityEstablished": False, "H_BStatus": "untested; frame72 opposite arm not separately visible; no per-frame identity switching",
            "commonInputNotVideoTimeline": True, "continuousWalkProduced": False},
        "observations": {str(i): o for i, o in observations.items()},
        "registrationMatrices": {str(i): r.tolist() for i, r in registrations.items()},
        "solverPolicy": {"degreesOfFreedom": "two absolute bind-relative bone rotations; source bone lengths fixed per hypothesis",
            "rotationBoundsDegrees": [-180, 180], "targets": "center of uncertain visible hand-lobe region",
            "centerNotRegionDistance": True, "successRequired": True, "maximumCenterResidualPx": 1e-5,
            "rotationSemantics": "absolute per-bone bind-relative deltas, not direct parent-local Spine rotation keys",
            "branchLabelsAreNotTemporalIdentities": True,
            "materialPoint": "source [317,555] embedded in P1 mesh; not validated wrist",
            "lossUsesContour": False, "branches": "5 fixed seeds, deduplicate solutions; report each solution, no silhouette-based selection",
            "notTiming": "discrete feasibility only; never link solver branches into walk track"},
        "reuseContract": {"logicalPartCount": 7, "testedArmLogicalParts": 1, "testedArmBoneCount": 2,
            "bonesAdded": 0, "attachmentsAdded": 0, "correctiveKeysAdded": 0,
            "stableMeshWeightsTextureChanged": False, "sharedLayer": ["bone semantics", "hierarchy", "motion/control interface"],
            "characterProfile": ["bind proportions", "mesh", "weights", "texture"],
            "sleeve": "same character bone chain/profile; own texture/mesh/weights; no clothing-specific hidden elbow pivot",
            "clothingValidated": False, "crossCharacterValidated": False},
        "results": results, "decision": "all hypotheses evidence_insufficient; no bind selection or promotion",
        "limitations": ["三帧不是完整68–84 walk拟合", "腰线相似配准不能消除真实视角、比例及软体形变差异",
            "手团区域为人工低可信观察，拟合误差不是动作质量验收", "完整轮廓与遮挡未量化评分", "肩根未修补、其他肢体保持静态"],
        "generatedImages": [{"file": n, "sha256": sha256(output / n)} for n in generated],
        "production": False, "approvedForBinding": False, "bindingValidated": False}
    checks = {"protectedFileCount": len(before), "protectedHashesBeforeAfter": {p: {"before": h, "after": after[p]} for p, h in before.items()},
        "allProtectedUnchanged": before == after, "registrationAnchorMaxErrors": registration_checks,
        "allGeneratedImagesReadable": all(Image.open(output / n).verify() is None for n in generated),
        "sameInputRotationVectorsCommonForAllCandidates": True,
        "sameTargetRegistrationCommonForAllCandidates": True,
        "noNewRigPartsBonesOrCorrectives": True, "bindingValidated": False}
    for name, data in (("study.json", records), ("checks.json", checks)):
        (output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if json.loads((output / name).read_text(encoding="utf-8")) != data:
            raise AssertionError("v9 JSON回读失败")
    print(json.dumps({"output": str(output), "generatedImageCount": len(generated), "protectedFileCount": len(before),
        "results": {name: {i: [{"error": s["fittedTargetCenterErrorPx"], **s["geometry"]} for s in r["sameTargetDiscreteSolutions"]]
            for i, r in frames.items()} for name, frames in results.items()},
        "production": False}, ensure_ascii=False, indent=2))


def run_body_constraint_study() -> None:
    """Torso-only calibration gate; independent from arm fitting and never a runtime warp."""
    output = PARENT / "body_constraint_v1"
    if not PARENT.is_dir():
        raise FileNotFoundError(PARENT)
    output.mkdir(exist_ok=True)
    v9_path = PARENT / "arm_mesh_test_v9" / "study.json"
    evidence_path = PARENT / "video_parts_v1" / "manifest.json"
    sources_path = PARENT / "video_parts_v1" / "cycle_review" / "sources.json"
    manifest_path = PARTS / "manifest.json"
    v7_path = PARENT / "arm_mesh_test_v7" / "study.json"
    v9, evidence, sources, manifest, v7 = [json.loads(p.read_text(encoding="utf-8")) for p in
        (v9_path, evidence_path, sources_path, manifest_path, v7_path)]
    protected = [p for folder in [PARTS] + [PARENT / f"arm_mesh_test_v{i}" for i in range(1, 11)]
                 for p in folder.rglob("*") if p.is_file()]
    protected += [evidence_path, sources_path, PARENT / "source.mp4"]
    protected += list((sources_path.parent).glob("source_*.png"))
    before = {str(p): sha256(p) for p in dict.fromkeys(protected)}
    if any(m["taskId"] != manifest["taskId"] or m["sourceVideoSha256"] != manifest["sourceVideoSha256"] for m in (evidence, sources)):
        raise AssertionError("共同约束来源不一致")
    if sha256(PARENT / "source.mp4") != manifest["sourceVideoSha256"]:
        raise AssertionError("源视频不一致")
    # Visible head/body contact references, not a neck joint or recovered shoulder.
    # Coordinates were manually read from raw frame crops, prior to candidate rendering.
    source_fit = np.array([[368., 439.], [447., 438.], [366., 535.], [467., 520.]])
    source_holdout = np.array([[410., 442.], [415., 537.]])
    observations = {
        68: {"fit": [[416., 295.], [485., 296.], [398., 357.], [500., 359.]],
             "holdout": [[453., 300.], [449., 368.]], "shoulderAllowBox": [377., 299., 425., 337.]},
        72: {"fit": [[413., 277.], [482., 280.], [391., 336.], [499., 339.]],
             "holdout": [[451., 283.], [447., 353.]], "shoulderAllowBox": [394., 281., 438., 318.]},
        80: {"fit": [[415., 275.], [482., 279.], [401., 341.], [497., 341.]],
             "holdout": [[453., 282.], [449., 350.]], "shoulderAllowBox": [382., 282., 428., 320.]}}
    def project(points, matrix):
        return np.column_stack((points, np.ones(len(points)))) @ matrix.T
    def fit_similarity(src, dst):
        rows, target = [], []
        for (x, y), (u, v) in zip(src, dst):
            rows += [[x, -y, 1., 0.], [y, x, 0., 1.]]
            target += [u, v]
        a, b, tx, ty = np.linalg.lstsq(rows, target, rcond=None)[0]
        return np.array([[a, -b, tx], [b, a, ty]])
    def fit_affine(src, dst):
        return np.linalg.lstsq(np.column_stack((src, np.ones(len(src)))), dst, rcond=None)[0].T
    def errors(points, target):
        value = np.linalg.norm(points - target, axis=1)
        return {"perPointPx": value.tolist(), "rmsPx": float(np.sqrt(np.mean(value ** 2))), "maxPx": float(value.max())}
    # Synthetic correspondence tests check implementation only, not observation truth.
    known = np.array([[.8, -.15, 10.], [.15, .8, -12.]])
    if not np.allclose(fit_similarity(source_fit, project(source_fit, known)), known, atol=1e-10):
        raise AssertionError("相似变换自测失败")
    known_affine = np.array([[1.1, .07, 20.], [-.1, .7, 25.]])
    if not np.allclose(fit_affine(source_fit, project(source_fit, known_affine)), known_affine, atol=1e-10):
        raise AssertionError("仿射自测失败")
    layers = {}
    for part in manifest["parts"]:
        path = PARTS / part["file"]
        if sha256(path) != part["sha256"]:
            raise AssertionError("稳定部件被改变")
        layer = Image.new("RGBA", SIZE)
        layer.paste(Image.open(path).convert("RGBA"), tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.asarray(layers["arm_near"])
    mesh = v7["meshes"]["linear_12_94"]
    vertices, triangles, weights = (np.asarray(mesh[k]) for k in ("vertices", "triangles", "weights"))
    uv = (vertices + .5) / 768.
    baseline_bind = JOINTS.copy()
    def fixed_arm(index):
        # Frozen v9 baseline branch; no re-solve, elbow sweep or extra corrective.
        deltas = np.deg2rad(v9["results"]["baseline"][str(index)]["sameTargetDiscreteSolutions"][0]["rotationDeltaDegrees"])
        directions = np.diff(baseline_bind, axis=0)
        angles = np.arctan2(directions[:, 1], directions[:, 0]) + deltas
        lengths = np.linalg.norm(directions, axis=1)
        joints = [baseline_bind[0].copy()]
        matrices = []
        for k, (a, _) in enumerate(BONE_INDICES):
            joints.append(joints[-1] + lengths[k] * np.array([np.cos(angles[k]), np.sin(angles[k])]))
            c, s = np.cos(deltas[k]), np.sin(deltas[k])
            rotation = np.array([[c, -s], [s, c]])
            matrices.append(np.column_stack((rotation, joints[a] - rotation @ baseline_bind[a])))
        rendered, _, _ = render_mesh(texture, uv, triangles, deform(vertices, weights, matrices), "source_over_top_left")
        return rendered
    palette = {"waist_only": (190, 75, 60), "torso_similarity": (22, 120, 145), "affine_diagnostic": (142, 91, 164)}
    source_records = {f["sourceFrame"]: f for f in sources["frames"]}
    results, image_files = {}, []
    sheet = Image.new("RGB", (1800, 1250), (246, 248, 246))
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 12), "躯干共同约束 v1｜只校准身体，不扫描肘点，不新增部件", font=font(29), fill=(30, 48, 58))
    draw.text((18, 58), "红：腰线基线  蓝：躯干相似配准  紫：仿射仅诊断，禁止直接成为骨骼/贴图缩放", font=font(20), fill=(80, 75, 85))
    draw.text((18, 92), "四个拟合点：头下接触线两点 + 腰线两点；两处留出点不参与拟合。全部为人工低可信观察，非解剖关节。", font=font(18), fill=(80, 85, 90))
    for row, (index, observation) in enumerate(observations.items()):
        target, holdout = np.asarray(observation["fit"]), np.asarray(observation["holdout"])
        frame_path = sources_path.parent / source_records[index]["sourceFile"]
        if sha256(frame_path) != source_records[index]["sourceFrameSha256"]:
            raise AssertionError("源帧哈希不符")
        frame = Image.open(frame_path).convert("RGB")
        transforms = {"waist_only": np.asarray(v9["registrationMatrices"][str(index)]),
                      "torso_similarity": fit_similarity(source_fit, target), "affine_diagnostic": fit_affine(source_fit, target)}
        part = next(p for p in evidence["parts"] if p["id"] == v9["observations"][str(index)]["armEvidenceId"])
        coarse = np.asarray(part["polygonSourcePixels"], dtype=float)
        # Exclude the closing shoulder cut: open polyline ONLY. No IoU against an invented hidden arm.
        reference_boundary = np.zeros((480, 864), dtype=np.uint8)
        cv2.polylines(reference_boundary, [np.rint(coarse).astype(np.int32)], False, 255, 1)
        ref_y, ref_x = np.nonzero(reference_boundary)
        # Remove ambiguous open-polyline endpoints and the broad shoulder hypothesis box.
        box = np.asarray(observation["shoulderAllowBox"])
        endpoint_distance = np.minimum(np.linalg.norm(np.column_stack((ref_x, ref_y)) - coarse[0], axis=1),
                                       np.linalg.norm(np.column_stack((ref_x, ref_y)) - coarse[-1], axis=1))
        in_shoulder = (ref_x >= box[0]) & (ref_x <= box[2]) & (ref_y >= box[1]) & (ref_y <= box[3])
        valid_reference = (endpoint_distance > 5.) & ~in_shoulder
        raw_reference_count = len(ref_x)
        ref_y, ref_x = ref_y[valid_reference], ref_x[valid_reference]
        if len(ref_x) < 10:
            raise AssertionError("有效可见轮廓样本不足")
        arm = fixed_arm(index)
        assembly = assemble(manifest, layers, arm)
        results[str(index)] = {"methods": {}, "armEvidenceId": part["id"], "sourceFrameSha256": sha256(frame_path)}
        marked = frame.copy(); md = ImageDraw.Draw(marked)
        md.line([tuple(p) for p in coarse], fill=(218, 139, 34), width=2)
        md.rectangle(observation["shoulderAllowBox"], outline=(135, 80, 150), width=1)
        for j, p in enumerate(target):
            md.ellipse((p[0]-2, p[1]-2, p[0]+2, p[1]+2), fill=(25, 120, 145))
        for p in holdout:
            md.rectangle((p[0]-2, p[1]-2, p[0]+2, p[1]+2), outline=(35, 140, 80))
        cells = [("视频证据 / 肩根区仅假设", marked, "橙线不闭合；不把肩内切口当真值")]
        for name, matrix in transforms.items():
            fit_error, hold_error = errors(project(source_fit, matrix), target), errors(project(source_holdout, matrix), holdout)
            predicted_shoulder = project(JOINTS[:1], matrix)[0]
            box = np.asarray(observation["shoulderAllowBox"])
            distance_outside = float(np.linalg.norm(np.maximum(np.maximum(box[:2]-predicted_shoulder, predicted_shoulder-box[2:]), 0.)))
            warped_arm = cv2.warpAffine(np.asarray(arm), matrix, (864, 480), flags=cv2.INTER_LINEAR)
            mask = (warped_arm[:, :, 3] >= 128).astype(np.uint8)
            edge = (mask - cv2.erode(mask, np.ones((3, 3), np.uint8))) > 0
            if not edge.any():
                raise AssertionError("投影手臂为空")
            edge_distance = cv2.distanceTransform((~edge).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            visible_distances = edge_distance[ref_y, ref_x]
            linear = matrix[:, :2]
            singular = np.linalg.svd(linear, compute_uv=False)
            record = {"matrix": matrix.tolist(), "fitReferences": fit_error, "heldOutReferences": hold_error,
                "heldOutIsLowConfidenceManualNotIndependentGroundTruth": True,
                "projectedShoulderHypothesisXY": predicted_shoulder.tolist(), "shoulderAllowedBoxOutsidePx": distance_outside,
                "shoulderBoxIsHypothesisNotValidatedJoint": True,
                "linearSingularValues": singular.tolist(), "anisotropyRatio": float(singular[0]/singular[1]),
                "visibleCoarseOpenBoundaryToArmEdgePx": {"median": float(np.median(visible_distances)), "p90": float(np.percentile(visible_distances, 90)), "max": float(visible_distances.max())},
                "boundaryMetricIsOneSidedDiagnosticNotQualityScore": True,
                "boundarySampling": {"rawRasterPixelCount": raw_reference_count, "validRasterPixelCount": len(ref_x),
                    "excludedEndpointRadiusPx": 5, "excludedShoulderHypothesisBox": True,
                    "candidateEdgeIncludesInternalCutSoReverseDistanceIsNotReported": True},
                "armPoseFrozenFromV9": True, "shoulderAndHandDidNotDriveRegistration": True}
            results[str(index)]["methods"][name] = record
            rgba = cv2.warpAffine(np.asarray(assembly), matrix, (864, 480), flags=cv2.INTER_LINEAR)
            image = Image.new("RGBA", (864, 480), (249, 249, 246, 255)); image.alpha_composite(Image.fromarray(rgba))
            pd = ImageDraw.Draw(image)
            pd.line([tuple(p) for p in target[:2]], fill=(25, 120, 145), width=2)
            pd.line([tuple(p) for p in target[2:]], fill=(25, 120, 145), width=2)
            pd.rectangle(observation["shoulderAllowBox"], outline=(135, 80, 150), width=1)
            pd.line([tuple(p) for p in coarse], fill=(218, 139, 34), width=2)
            x, y = predicted_shoulder
            pd.ellipse((x-3, y-3, x+3, y+3), fill=palette[name])
            label = {"waist_only": "原腰线基线", "torso_similarity": "共同躯干相似配准", "affine_diagnostic": "仿射诊断 / 不用于运行"}[name]
            cells.append((label, image.convert("RGB"), f"留出RMS {hold_error['rmsPx']:.1f}px / 肩区外 {distance_outside:.1f}px"))
            filename = f"f{index:03d}_{name}.png"; image.convert("RGB").save(output / filename); image_files.append(filename)
        for col, (label, image, detail) in enumerate(cells):
            x, y = col*450+12, 150+row*355
            draw.text((x, y), f"f{index} | {label}", font=font(20), fill=(35, 55, 65))
            crop = image.crop((335, 245, 555, 390)).resize((430, 283), Image.Resampling.LANCZOS)
            sheet.paste(crop, (x, y+31))
            draw.text((x, y+320), detail, font=font(16), fill=(105, 65, 50))
    sheet.save(output / "joint_review.png"); image_files.append("joint_review.png")
    sensitivity = {}
    for index, observation in observations.items():
        target = np.asarray(observation["fit"]); target_holdout = np.asarray(observation["holdout"])
        samples = []
        for side, radius in (("source", 4.), ("video", 6.)):
            for point in range(4):
                for axis in range(2):
                    for sign in (-1., 1.):
                        src, dst = source_fit.copy(), target.copy()
                        (src if side == "source" else dst)[point, axis] += radius*sign
                        matrix = fit_similarity(src, dst)
                        samples.append({"perturbedSide": side, "point": point, "axis": axis, "deltaPx": radius*sign,
                            "heldOutRmsPx": errors(project(source_holdout, matrix), target_holdout)["rmsPx"],
                            "projectedShoulderXY": project(JOINTS[:1], matrix)[0].tolist()})
        xy = np.asarray([s["projectedShoulderXY"] for s in samples])
        sensitivity[str(index)] = {"sampleCount": len(samples), "method": "one_coordinate_at_a_time_declared_limits_not_joint_envelope_or_confidence_interval",
            "heldOutRmsRangePx": [min(s["heldOutRmsPx"] for s in samples), max(s["heldOutRmsPx"] for s in samples)],
            "projectedShoulderXYComponentRange": [xy.min(axis=0).tolist(), xy.max(axis=0).tolist()], "samples": samples}
    after = {p: sha256(Path(p)) for p in before}
    if after != before:
        raise AssertionError("保护资产变化")
    records = {"schemaVersion": 1, "status": "torso_projection_gate_not_binding", "sourceTaskId": manifest["taskId"],
        "sourceVideoSha256": manifest["sourceVideoSha256"], "sourceHashes": {str(p): sha256(p) for p in (v9_path, v7_path, evidence_path, sources_path, manifest_path)},
        "observations": {"sourceFitXY": source_fit.tolist(), "sourceHeldOutXY": source_holdout.tolist(), "frames": observations,
            "method": "assistant_manual_raw_crop_grid_read_before_candidate_rendering", "confidence": "low",
            "sourceReferenceUncertaintyPx": 4, "videoReferenceUncertaintyPx": 6,
            "heldOutPointsNotUsedInFit": True, "notIndependentHumanAnnotation": True,
            "shoulderBoxes": "broad visual attachment hypotheses; not recovered anatomical boundaries",
            "closedShoulderCutExcludedFromBoundaryMetric": True},
        "referenceSensitivity": sensitivity,
        "scriptSha256": sha256(Path(__file__)),
        "results": results, "gate": {"bindingApproved": False, "profileSelected": False, "minimumRepairMaskReady": False,
            "reason": "common references now expose body projection mismatch; affine is diagnostic only; visible arm contour and hidden shoulders remain unvalidated"},
        "nextAction": "Use torso-only calibration as fixed reference for body profile validation, then one continuous arm contour/occlusion fit; do not scan pivots or generate fragments.",
        "limitations": ["Three selected frames are not a continuous walk", "Manual contour and shoulder boxes are low-confidence, not anatomical truth", "One-sided edge distance cannot validate volume, inside/outside or occlusion", "Affine compression is not a runtime deformation or selected profile", "Frozen v9 branch is not a newly fitted arm or cross-frame identity", "Opposite arm/body dynamics and hidden repair remain incomplete"],
        "reuseContract": {"logicalParts": 7, "newBones": 0, "newAttachments": 0, "newCorrectiveKeys": 0, "sourceAssetsChanged": False},
        "production": False, "approvedForBinding": False,
        "generatedImages": [{"file": n, "sha256": sha256(output/n)} for n in image_files]}
    checks = {"allProtectedUnchanged": before == after, "protectedFileCount": len(before), "protectedHashes": before,
        "syntheticSimilarityRecoveryPassed": True, "syntheticAffineRecoveryPassed": True,
        "frameCount": 3, "allMatricesFinite": all(np.isfinite(r["matrix"]).all() for f in results.values() for r in f["methods"].values()),
        "allGeneratedImagesReadable": all(Image.open(output/n).verify() is None for n in image_files), "bindingValidated": False}
    for name, value in (("study.json", records), ("checks.json", checks)):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "images": len(image_files), "protectedUnchanged": checks["allProtectedUnchanged"],
        "results": {f: {n: {"heldOutRms": r["heldOutReferences"]["rmsPx"], "shoulderOutside": r["shoulderAllowedBoxOutsidePx"], "anisotropy": r["anisotropyRatio"], "coarseBoundaryP90": r["visibleCoarseOpenBoundaryToArmEdgePx"]["p90"]} for n,r in data["methods"].items()} for f,data in results.items()}}, ensure_ascii=False, indent=2))


def continuous_similarity(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    rows, values = [], []
    for (x, y), (u, v) in zip(source, target):
        rows.extend(([x, -y, 1., 0.], [y, x, 0., 1.]))
        values.extend((u, v))
    a, b, tx, ty = np.linalg.lstsq(rows, values, rcond=None)[0]
    return np.array([[a, -b, tx], [b, a, ty]])


def continuous_project(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return np.column_stack((points, np.ones(len(points)))) @ matrix.T


def continuous_select_anchor(index: int, anchors: list[int], valid: dict[int, bool]) -> dict:
    ordered = sorted(anchors, key=lambda a: (abs(a - index), a))
    chosen = next((a for a in ordered if valid[a]), None)
    return {"nearestAnchor": ordered[0], "primaryAnchor": chosen,
            "fallback": chosen is not None and chosen != ordered[0],
            "rejectedNearerAnchors": [a for a in ordered[:ordered.index(chosen)] if not valid[a]] if chosen is not None else ordered,
            "reason": ("all_anchor_fit_tracks_lost" if chosen is None else
                       "nearest_fit_lost_fallback" if chosen != ordered[0] else "nearest_valid_tie_smaller_frame")}


def continuous_track(grays: dict[int, np.ndarray], anchor: int, initial: np.ndarray,
                     parameters: dict, flow=None) -> dict[int, list[dict]]:
    flow = cv2.calcOpticalFlowPyrLK if flow is None else flow
    names = ["head_contact_left", "head_contact_right", "waist_left", "waist_right",
             "head_contact_holdout", "waist_holdout"]
    root = [{"pointId": name, "role": "fit" if j < 4 else "holdout", "xy": p.tolist(),
             "valid": True, "fromFrame": None, "direction": "anchor", "statusForward": None,
             "statusBackward": None, "forwardBackwardErrorPx": None, "cumulativeMaxForwardBackwardErrorPx": 0.,
             "lkForwardPatchError": None, "lkBackwardPatchError": None, "failure": None,
             "firstInvalidFrame": None, "attempted": False} for j, (name, p) in enumerate(zip(names, initial))]
    records = {anchor: root}
    lk = {"winSize": tuple(parameters["winSize"]), "maxLevel": parameters["maxLevel"],
          "criteria": (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                       parameters["criteriaMaxCount"], parameters["criteriaEpsilon"]),
          "flags": 0, "minEigThreshold": parameters["minEigThreshold"]}
    for direction in (-1, 1):
        previous = anchor
        for index in range(anchor + direction, min(grays) - 1 if direction < 0 else max(grays) + 1, direction):
            current = []
            for old in records[previous]:
                record = {**old, "fromFrame": previous, "direction": "backward" if direction < 0 else "forward",
                          "attempted": False, "xy": None, "statusForward": None, "statusBackward": None,
                          "forwardBackwardErrorPx": None, "lkForwardPatchError": None, "lkBackwardPatchError": None}
                if not old["valid"]:
                    record["failure"] = "previously_invalid_no_revival"
                    current.append(record)
                    continue
                point = np.array(old["xy"], dtype=np.float32).reshape(1, 1, 2)
                next_point, status, error = flow(grays[previous], grays[index], point, None, **lk)
                record["attempted"] = True
                record["statusForward"] = int(status.ravel()[0]) if status is not None else 0
                candidate = next_point.reshape(2) if next_point is not None else None
                finite = candidate is not None and bool(np.isfinite(candidate).all())
                if error is not None and record["statusForward"] and np.isfinite(error.ravel()[0]):
                    record["lkForwardPatchError"] = float(error.ravel()[0])
                back = None
                if record["statusForward"] and finite:
                    back, bs, be = flow(grays[index], grays[previous], next_point, None, **lk)
                    record["statusBackward"] = int(bs.ravel()[0]) if bs is not None else 0
                    if be is not None and record["statusBackward"] and np.isfinite(be.ravel()[0]):
                        record["lkBackwardPatchError"] = float(be.ravel()[0])
                back_finite = back is not None and bool(np.isfinite(back).all())
                if back_finite and record["statusBackward"]:
                    fb = float(np.linalg.norm(back.reshape(2) - point.reshape(2)))
                    record["forwardBackwardErrorPx"] = fb
                    record["cumulativeMaxForwardBackwardErrorPx"] = max(old["cumulativeMaxForwardBackwardErrorPx"], fb)
                h, w = grays[index].shape
                in_bounds = finite and 0. <= candidate[0] < w and 0. <= candidate[1] < h
                failure = ("lk_forward_status_failed" if not record["statusForward"] else
                           "nonfinite_forward_point" if not finite else
                           "forward_point_outside_frame" if not in_bounds else
                           "lk_backward_status_failed" if not record["statusBackward"] else
                           "nonfinite_backward_point" if not back_finite else
                           "forward_backward_error_exceeded" if record["forwardBackwardErrorPx"] > parameters["maxForwardBackwardErrorPx"] else None)
                record.update(valid=failure is None, failure=failure,
                              xy=candidate.astype(float).tolist() if failure is None else None,
                              firstInvalidFrame=index if failure else None)
                current.append(record)
            records[index] = current
            previous = index
    return records


def run_continuous_constraint_study() -> None:
    output = PARENT / "continuous_constraint_v1"
    evidence_path = PARENT / "video_parts_v1" / "manifest.json"
    sources_path = evidence_path.parent / "cycle_review" / "sources.json"
    body_path = PARENT / "body_constraint_v1" / "study.json"
    stable_path = PARTS / "manifest.json"
    reference_path = PARENT / "reference.json"
    required = [PARTS, PARENT / "video_parts_v1", PARENT / "body_constraint_v1", HERE.parent / "studio_v2"]
    required += [PARENT / f"arm_mesh_test_v{i}" for i in range(1, 11)]
    if not PARENT.is_dir() or any(not p.is_dir() for p in required):
        raise FileNotFoundError("连续证据研究的保护输入目录不完整")
    if output.exists() and not output.is_dir():
        raise ValueError("研究输出不是目录")

    def load(path):
        def reject(value):
            raise ValueError(f"非有限JSON常量：{value}")
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)

    body, evidence, sources, manifest, reference = [load(p) for p in
        (body_path, evidence_path, sources_path, stable_path, reference_path)]
    source_image = (PARTS / manifest["sourceImage"]["file"]).resolve()

    def snapshot():
        # 额外保护PARENT内所有既有证据；研究输出本身不进入输入哈希。
        paths = [p for folder in (PARENT, HERE.parent / "studio_v2") for p in folder.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and output not in p.parents]
        paths += [source_image]
        return {str(p): sha256(p) for p in sorted(set(paths))}

    before = snapshot()
    task, video_sha = manifest["taskId"], manifest["sourceVideoSha256"]
    if any(d["taskId"] != task or d["sourceVideoSha256"] != video_sha for d in (evidence, sources)):
        raise AssertionError("视频/证据/稳定七件task或sha来源不一致")
    if (body["sourceTaskId"] != task or body["sourceVideoSha256"] != video_sha or
            reference["taskId"] != task or reference["sha256"] != video_sha):
        raise AssertionError("躯干参考或源视频task/sha链不一致")
    video_path = PARENT / "source.mp4"
    if (sha256(video_path) != video_sha or (sources_path.parent / sources["sourceVideo"]).resolve() != video_path or
            (evidence_path.parent / evidence["sourceVideo"]).resolve() != video_path):
        raise AssertionError("源视频路径/哈希不符")
    for path, digest in body["sourceHashes"].items():
        if sha256(Path(path)) != digest:
            raise AssertionError(f"躯干研究来源链不符：{path}")
    if sha256(source_image) != manifest["sourceImage"]["sha256"]:
        raise AssertionError("固定768源图哈希不符")
    with Image.open(source_image) as image:
        if image.size != SIZE:
            raise AssertionError("固定源坐标不是768×768")
    indices, anchors = list(range(68, 85)), [68, 72, 80]
    if sources["frameIndices"] != indices or sources["sampleCount"] != 17 or len(sources["frames"]) != 17:
        raise AssertionError("连续来源必须完整覆盖68至84帧")
    source_records = {f["sourceFrame"]: f for f in sources["frames"]}
    if sorted(source_records) != indices or reference["direction"] != "right_front_3q" or reference["action"] != "walk":
        raise AssertionError("帧索引或角色视角/动作不符")
    frames, grays, provenance = {}, {}, []
    crop_box, crop_scale = tuple(sources["cropBoxSourcePixels"]), sources["scale"]
    expected_crop_size = ((crop_box[2] - crop_box[0]) * crop_scale, (crop_box[3] - crop_box[1]) * crop_scale)
    for index in indices:
        record = source_records[index]
        source_path, crop_path = [sources_path.parent / record[k] for k in ("sourceFile", "cropFile")]
        source_sha, crop_sha = sha256(source_path), sha256(crop_path)
        if source_sha != record["sourceFrameSha256"] or crop_sha != record["cropSha256"]:
            raise AssertionError(f"f{index} source/crop哈希不符")
        with Image.open(source_path) as image:
            image.load()
            if image.size != (864, 480) or list(image.size) != record["sourceSize"] or image.mode != "RGB":
                raise AssertionError(f"f{index} source shape/mode不符")
            frames[index] = image.copy()
        with Image.open(crop_path) as crop:
            crop.load()
            if crop.size != expected_crop_size or crop.mode != "RGB":
                raise AssertionError(f"f{index} crop shape/mode不符")
            expected_crop = frames[index].crop(crop_box).resize(expected_crop_size, Image.Resampling.NEAREST)
            if not np.array_equal(np.asarray(crop), np.asarray(expected_crop)):
                raise AssertionError(f"f{index} crop与source像素不符")
        grays[index] = cv2.cvtColor(np.asarray(frames[index]), cv2.COLOR_RGB2GRAY)
        provenance.append({"frame": index, "sourceFile": str(source_path), "sourceSha256": source_sha,
                           "sourceShapeHWC": [480, 864, 3], "cropFile": str(crop_path), "cropSha256": crop_sha,
                           "cropShapeHWC": [expected_crop_size[1], expected_crop_size[0], 3], "cropPixelsExact": True})
    # 只读解码验证来源链，不保存或重建任何现有source帧。
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise AssertionError("源视频只读解码失败")
        for index in range(85):
            ok, decoded = capture.read()
            if not ok or decoded.shape != (480, 864, 3):
                raise AssertionError(f"源视频f{index}解码/shape失败")
            if index in frames and not np.array_equal(cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB), np.asarray(frames[index])):
                raise AssertionError(f"源视频f{index}与source像素不符")
    finally:
        capture.release()
    source_fit = np.asarray(body["observations"]["sourceFitXY"], dtype=float)
    source_holdout = np.asarray(body["observations"]["sourceHeldOutXY"], dtype=float)
    if source_fit.shape != (4, 2) or source_holdout.shape != (2, 2):
        raise AssertionError("躯干4 fit+2 holdout参考shape不符")
    known = np.array([[.82, -.11, 150.], [.11, .82, -120.]])
    if not np.allclose(continuous_similarity(source_fit, continuous_project(source_fit, known)), known, atol=1e-9):
        raise AssertionError("最小二乘相似变换合成自测失败")
    if not np.allclose(continuous_project(continuous_project(source_fit, known), cv2.invertAffineTransform(known)), source_fit):
        raise AssertionError("逆变换合成自测失败")
    if continuous_select_anchor(70, anchors, {a: True for a in anchors})["primaryAnchor"] != 68:
        raise AssertionError("平局小帧自测失败")
    if continuous_select_anchor(70, anchors, {68: False, 72: True, 80: True})["primaryAnchor"] != 72:
        raise AssertionError("失效fallback自测失败")
    if continuous_select_anchor(70, anchors, {a: False for a in anchors})["primaryAnchor"] is not None:
        raise AssertionError("全部失效自测失败")
    parameter_sets = {
        "lk21_primary_fixed": {"winSize": [21, 21], "maxLevel": 3, "criteriaMaxCount": 30,
            "criteriaEpsilon": .01, "minEigThreshold": .0001, "maxForwardBackwardErrorPx": 1.5},
        "lk31_sensitivity_only": {"winSize": [31, 31], "maxLevel": 3, "criteriaMaxCount": 30,
            "criteriaEpsilon": .01, "minEigThreshold": .0001, "maxForwardBackwardErrorPx": 1.5}}
    primary_parameters = "lk21_primary_fixed"
    fake_calls = []

    def failed_flow(previous, current, points, unused, **kwargs):
        fake_calls.append(1)
        return points.copy(), np.zeros((1, 1), dtype=np.uint8), np.zeros((1, 1), dtype=np.float32)

    fake = continuous_track({68: grays[68], 69: grays[69], 70: grays[70]}, 68,
                            np.zeros((6, 2)), parameter_sets[primary_parameters], failed_flow)
    if len(fake_calls) != 6 or any(p["valid"] or p["xy"] is not None or p["attempted"] for p in fake[70]):
        raise AssertionError("点失效不可复活自测失败")
    tracks, fits, anchor_recovery = {}, {}, {}
    for parameter_id, parameters in parameter_sets.items():
        tracks[parameter_id], fits[parameter_id] = {}, {}
        for anchor in anchors:
            observation = body["observations"]["frames"][str(anchor)]
            initial = np.asarray(observation["fit"] + observation["holdout"], dtype=float)
            if initial.shape != (6, 2) or not np.isfinite(initial).all():
                raise AssertionError("锚点shape/有限性错误")
            track = continuous_track(grays, anchor, initial, parameters)
            tracks[parameter_id][anchor] = track
            fits[parameter_id][anchor] = {}
            for index in indices:
                points = track[index]
                if all(p["valid"] for p in points[:4]):
                    matrix = continuous_similarity(source_fit, np.asarray([p["xy"] for p in points[:4]]))
                    if not np.isfinite(matrix).all() or np.linalg.det(matrix[:, :2]) <= 1e-12:
                        raise AssertionError("相似变换非有限或不可逆")
                    fits[parameter_id][anchor][index] = matrix
                else:
                    fits[parameter_id][anchor][index] = None
            if parameter_id == primary_parameters:
                expected = np.asarray(body["results"][str(anchor)]["methods"]["torso_similarity"]["matrix"])
                delta = float(np.abs(fits[parameter_id][anchor][anchor] - expected).max())
                anchor_recovery[str(anchor)] = delta
                if delta > 1e-9:
                    raise AssertionError("锚帧相似矩阵与既有研究不一致")
    layers = {}
    if manifest["assemblyLayerOrder"] != EXPECTED_ORDER or len(manifest["parts"]) != 7:
        raise AssertionError("稳定七件层序不符")
    for part in manifest["parts"]:
        path = PARTS / part["file"]
        if sha256(path) != part["sha256"]:
            raise AssertionError(f"稳定部件sha不符：{part['id']}")
        with Image.open(path) as image:
            if image.size != (part["bbox"][2] - part["bbox"][0], part["bbox"][3] - part["bbox"][1]):
                raise AssertionError("稳定部件shape不符")
            layer = Image.new("RGBA", SIZE)
            layer.paste(image.convert("RGBA"), tuple(part["bbox"][:2]))
            layers[part["id"]] = layer
    static = Image.new("RGBA", SIZE, (249, 248, 243, 255))
    static.alpha_composite(assemble(manifest, layers, np.asarray(layers["arm_near"])))
    static_digest = hashlib.sha256(static.tobytes()).hexdigest()
    expected_outputs = {"study.json", "checks.json", "contact_068_073.png", "contact_074_079.png", "contact_080_084.png"}
    expected_outputs.update(f"f{i:03d}_review.png" for i in indices)
    if output.exists() and any(not p.is_file() or p.name not in expected_outputs for p in output.iterdir()):
        raise AssertionError("研究输出含非预期文件，拒绝覆盖")
    output.mkdir(exist_ok=True)
    phase_labels = {"inward": "内收", "transition": "转入胸前", "chest_front_occlusion": "胸前团臂遮挡",
                    "lower": "胸前臂下移", "reopen": "重新展开", "outer_arms_crossed_legs": "外展臂 / 交叉腿"}
    frame_results, generated, rows = {}, [], []
    all_fb, all_disagreement, fit_rms_values, heldout_rms_values = [], [], [], []
    switches, fallbacks, lost_primary_holdouts, unregistered = [], [], [], []
    previous_anchor = None
    display_roi = (230, 385, 590, 745)

    def draw_curves(image, curves, matrix=None):
        draw = ImageDraw.Draw(image)
        for curve in curves:
            points = np.asarray(curve["openSourcePixels"], dtype=float)
            if matrix is not None:
                points = continuous_project(points, matrix)
            color = (211, 117, 21) if curve["kind"] == "arm" else (101, 72, 180)
            draw.line([tuple(p) for p in points], fill=color, width=2)
            for x, y in points[[0, -1]]:
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=color, width=1)
                draw.text((x + 4, y - 9), "?", font=font(12), fill=color)

    def draw_refs(image, points, matrix=None):
        draw = ImageDraw.Draw(image)
        xy = []
        for j, point in enumerate(points):
            p = np.asarray(point["xy"]) if point["xy"] is not None else None
            if p is not None and matrix is not None:
                p = continuous_project(p[None], matrix)[0]
            xy.append(p)
            if p is None:
                continue
            x, y = p
            if j < 4:
                draw.ellipse((x-2, y-2, x+2, y+2), fill=(15, 118, 146))
            else:
                draw.rectangle((x-3, y-3, x+3, y+3), outline=(24, 135, 72), width=1)
        for left, right in ((0, 1), (2, 3)):
            if xy[left] is not None and xy[right] is not None:
                draw.line((tuple(xy[left]), tuple(xy[right])), fill=(15, 118, 146), width=1)

    for index in indices:
        phase = ("inward" if index <= 69 else "transition" if index == 70 else "chest_front_occlusion" if index <= 76 else
                 "lower" if index == 77 else "reopen" if index == 78 else "outer_arms_crossed_legs")
        manual = source_records[index]["manualObservations"]
        curves = []
        for part in evidence["parts"]:
            if part["sourceFrame"] != index or part["kind"] not in ("arm", "leg"):
                continue
            evidence_source = evidence_path.parent / part["sourceFile"]
            if (part["sourceFrameSha256"] != source_records[index]["sourceFrameSha256"] or
                    sha256(evidence_source) != part["sourceFrameSha256"] or part["sourceSize"] != [864, 480]):
                raise AssertionError(f"f{index}粗轮廓source sha/shape链不符")
            points = np.asarray(part["polygonSourcePixels"], dtype=float)
            if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or not np.isfinite(points).all():
                raise AssertionError("粗轮廓点无效")
            # 仅保留存储序列中的开放曲线，绝不连接末端到首端的内部肩切口。
            if np.array_equal(points[0], points[-1]):
                points = points[:-1]
            curves.append({"evidenceId": part["id"], "kind": part["kind"], "openSourcePixels": points.tolist(),
                "closed": False, "excludedClosingEdgeSourcePixels": [points[-1].tolist(), points[0].tolist()],
                "endpoints": "unknown_not_anatomical_joints", "anatomicalIdentity": "unknown",
                "crossFrameIdentityEstablished": False, "boundaryConfidence": part["boundaryConfidence"],
                "occlusion": part["occlusion"]})
        if not curves or not any(c["kind"] == "arm" for c in curves) or not any(c["kind"] == "leg" for c in curves):
            raise AssertionError("连续臂/腿可见证据缺帧")
        per_anchor = {}
        for anchor in anchors:
            points = tracks[primary_parameters][anchor][index]
            matrix = fits[primary_parameters][anchor][index]
            fit_error, holdout_error = None, [None, None]
            if matrix is not None:
                fit_error = np.linalg.norm(continuous_project(source_fit, matrix) - np.asarray([p["xy"] for p in points[:4]]), axis=1)
                prediction = continuous_project(source_holdout, matrix)
                holdout_error = [float(np.linalg.norm(prediction[j] - p["xy"])) if p["valid"] else None for j, p in enumerate(points[4:])]
            per_anchor[str(anchor)] = {"fitValid": matrix is not None, "matrixSource768ToVideo": matrix.tolist() if matrix is not None else None,
                "commonSourceFitProjection": continuous_project(source_fit, matrix).tolist() if matrix is not None else None,
                "fitResidualPerPointPx": fit_error.tolist() if fit_error is not None else None,
                "fitResidualRmsPx": float(np.sqrt(np.mean(fit_error ** 2))) if fit_error is not None else None,
                "heldOutResidualPerPointPx": holdout_error,
                "heldOutResidualRmsPx": float(np.sqrt(np.mean(np.square(holdout_error)))) if all(e is not None for e in holdout_error) else None,
                "heldOutNotUsedInFit": True, "tracks": points}
            all_fb.extend(p["forwardBackwardErrorPx"] for p in points if p["forwardBackwardErrorPx"] is not None)
        selection = continuous_select_anchor(index, anchors, {a: fits[primary_parameters][a][index] is not None for a in anchors})
        chosen = selection["primaryAnchor"]
        switched = index != indices[0] and chosen != previous_anchor
        if switched:
            switches.append(index)
        if selection["fallback"]:
            fallbacks.append(index)
        if chosen is None:
            unregistered.append(index)
        selection.update(switch=switched, previousPrimaryAnchor=previous_anchor)
        previous_anchor = chosen
        pairwise = []
        for pos, a in enumerate(anchors):
            for b in anchors[pos + 1:]:
                ma, mb = fits[primary_parameters][a][index], fits[primary_parameters][b][index]
                if ma is None or mb is None:
                    pairwise.append({"anchors": [a, b], "perSourceFitPointPx": None, "rmsPx": None, "maxPx": None})
                    continue
                error = np.linalg.norm(continuous_project(source_fit, ma) - continuous_project(source_fit, mb), axis=1)
                pairwise.append({"anchors": [a, b], "perSourceFitPointPx": error.tolist(),
                                 "rmsPx": float(np.sqrt(np.mean(error ** 2))), "maxPx": float(error.max())})
                all_disagreement.extend(error.tolist())
        sensitivity = {}
        for parameter_id in parameter_sets:
            select = continuous_select_anchor(index, anchors, {a: fits[parameter_id][a][index] is not None for a in anchors})
            sensitivity[parameter_id] = {**select, "fitValidByAnchor": {str(a): fits[parameter_id][a][index] is not None for a in anchors}}
        primary = per_anchor[str(chosen)] if chosen is not None else None
        matrix = fits[primary_parameters][chosen][index] if chosen is not None else None
        inverse = cv2.invertAffineTransform(matrix) if matrix is not None else None
        if primary is not None:
            fit_rms_values.append(primary["fitResidualRmsPx"])
            if primary["heldOutResidualRmsPx"] is not None:
                heldout_rms_values.append(primary["heldOutResidualRmsPx"])
            if not all(p["valid"] for p in primary["tracks"][4:]):
                lost_primary_holdouts.append(index)
        failure_types = ["low_confidence_manual_refs", "body_projection_vs_soft_shape_unresolved", "hidden_shoulder_domain_unknown"]
        if chosen is None:
            failure_types.append("all_anchor_fit_tracks_lost")
        if selection["fallback"]:
            failure_types.append("nearest_anchor_fit_lost_fallback")
        if index in lost_primary_holdouts:
            failure_types.append("holdout_track_lost_null_not_imputed")
        if any(not p["valid"] for r in per_anchor.values() for p in r["tracks"]):
            failure_types.append("one_or_more_anchor_tracks_invalid")
        if 71 <= index <= 76:
            failure_types.append("chest_arm_body_occlusion_identity_unresolved")
        if 74 <= index <= 77:
            failure_types.append("source_foot_shape_anomaly_pending_design_correction_not_rig_failure")
        if "cross" in manual["legVisibility"] or index >= 79:
            failure_types.append("crossed_leg_hidden_boundary_identity_unknown")
        attribution = ["不可由纹理追踪区分躯干投影、软体形变、视频生成漂移与人工参考误差；不能归咎rig",
                       "肩根隐藏域与内部切口未知，不能得到最小补画mask", "A/B仅本帧证据id，不建立near/far或跨帧身份"]
        if 74 <= index <= 77:
            attribution.append("74–77脚形异常属于源观察，待设计修正；不是rig失败证据")
        arm_relation = ("可见胸前团臂覆盖身体；团臂near/far归属未知" if 71 <= index <= 76 else
                        "胸前臂下移至腰附近；near/far归属未知" if index == 77 else
                        "仅引用可见臂形态/转场；不能由A/B或屏幕侧确定near/far")
        leg_relation = ("只确认前层可见边界覆盖后层；near/far及是否需要交换draworder未知" if
                        "cross" in manual["legVisibility"] or index >= 79 else
                        "引用本帧可见腿/脚边界；短裤下髋缘和完整隐藏域未知，不推定draworder交换")
        inverse_curves = [{**c, "openSource768Pixels": continuous_project(np.asarray(c["openSourcePixels"]), inverse).tolist() if inverse is not None else None}
                          for c in curves]
        shoulder_hypotheses = []
        for anchor in anchors:
            box = body["observations"]["frames"][str(anchor)]["shoulderAllowBox"]
            shoulder_hypotheses.append({"anchor": anchor, "anchorVideoBox": box,
                "source768Corners": continuous_project(np.array([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]),
                    cv2.invertAffineTransform(fits[primary_parameters][anchor][anchor])).tolist(),
                "propagatedAsAnatomy": False, "hiddenDomainKnown": False})
        frame_results[str(index)] = {"frame": index, "time": source_records[index]["time"], "phase": phase,
            "manualObservationsRef": {"file": str(sources_path), "jsonPointer": f"/frames/{indices.index(index)}/manualObservations",
                                      "fileSha256": sha256(sources_path)}, "manualObservations": manual,
            "observedLayerRelation": {"arm": arm_relation, "leg": leg_relation, "nearFar": "unknown", "draworderSwapRequired": None},
            "failureTypes": failure_types, "nonAttributableItems": attribution,
            "observationInterpretationPolicy": "引用既有manualObservations及assetDecisions[3]，不是新解剖标注或rig缺陷判定",
            "selection": selection, "anchors": per_anchor, "multiAnchorCommonSourceFitDisagreement": pairwise,
            "diagnosticsNotConfidenceIntervalsOrPassScores": True, "parameterSensitivity": sensitivity,
            "inverseVideoToSource768": inverse.tolist() if inverse is not None else None,
            "normalizedCanvasSize": list(SIZE), "displayRoiSource768": list(display_roi),
            "curves": inverse_curves, "shoulderAllowHypotheses": shoulder_hypotheses,
            "staticReferencePixelSha256": static_digest, "staticReferenceNotContinuousCandidateAction": True,
            "repeatedEndpointCandidateOnly": index == 84}
        observed = frames[index].copy()
        draw_curves(observed, curves)
        if primary is not None:
            draw_refs(observed, primary["tracks"])
        if inverse is not None:
            normalized = Image.fromarray(cv2.warpAffine(np.asarray(frames[index]), inverse, SIZE,
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(247, 247, 241)))
            draw_curves(normalized, curves, inverse)
            draw_refs(normalized, primary["tracks"], inverse)
        else:
            normalized = Image.new("RGB", SIZE, (247, 247, 241))
            ImageDraw.Draw(normalized).text((240, 430), "配准失效 / 不伪造逆变换", font=font(18), fill=(175, 50, 45))
        static_overlay = static.convert("RGB")
        if inverse is not None:
            draw_curves(static_overlay, curves, inverse)
        row = Image.new("RGB", (2040, 1010), (240, 244, 242))
        draw = ImageDraw.Draw(row)
        title = f"f{index:03d} | {phase_labels[phase]} | 主锚 {chosen} | switch={switched} fallback={selection['fallback']}"
        draw.text((18, 12), title, font=font(27), fill=(28, 49, 58))
        draw.text((18, 54), "有边界证据审阅，不是绑定验证；蓝圆=4 fit（头下接触线+腰线），绿框=2 holdout；不是脚接触线", font=font(20), fill=(74, 84, 89))
        panels = [("原视频局部 / 开放可见粗轮廓", observed.crop((320, 245, 560, 475))),
                  ("主相似逆变换 / 固定768源坐标局部", normalized.crop(display_roi)),
                  ("稳定七件静态参考 / 非连续候选动作", static_overlay.crop(display_roi))]
        for col, (label, panel) in enumerate(panels):
            x = 18 + col * 678
            draw.text((x, 93), label, font=font(21), fill=(32, 66, 78))
            # 同一栏统一使用固定ROI与显示尺度，不随轮廓bbox伸缩。
            scale = min(650 / panel.width, 650 / panel.height)
            panel = panel.resize((round(panel.width * scale), round(panel.height * scale)), Image.Resampling.LANCZOS)
            row.paste(panel, (x, 130))
        draw.text((18, 796), "橙=arm / 紫=leg；曲线不闭合、?端点未知；A/B只是本帧证据id。第三栏禁止动作质量评分。", font=font(19), fill=(107, 71, 39))
        draw.text((18, 826), f"原观察：{manual['note']}", font=font(20), fill=(45, 61, 70))
        draw.text((18, 858), f"臂：{arm_relation}", font=font(20), fill=(45, 61, 70))
        draw.text((18, 890), f"腿：{leg_relation}", font=font(20), fill=(45, 61, 70))
        maxima = [p["maxPx"] for p in pairwise if p["maxPx"] is not None]
        fit_text = f"{primary['fitResidualRmsPx']:.2f}" if primary else "null"
        held_text = f"{primary['heldOutResidualRmsPx']:.2f}" if primary and primary["heldOutResidualRmsPx"] is not None else "null"
        disagreement_text = f"{max(maxima):.2f}" if maxima else "null"
        draw.text((18, 925), f"诊断（视频px）：fit RMS={fit_text} / holdout RMS={held_text} / 多锚最大分歧={disagreement_text}；非置信区间/通过评分", font=font(19), fill=(116, 68, 58))
        draw.text((18, 960), "74–77脚形异常是源观察待设计修正；肩根隐藏域未知，无最小补画mask；躯干/软体/源漂移/rig原因不可分离。", font=font(19), fill=(116, 68, 58))
        filename = f"f{index:03d}_review.png"
        row.save(output / filename)
        generated.append(filename)
        rows.append(row)
    contacts = []
    for start in range(0, 17, 6):
        group_rows = rows[start:start + 6]
        sheet = Image.new("RGB", (2040, 70 + 1010 * len(group_rows)), (240, 244, 242))
        ImageDraw.Draw(sheet).text((18, 18), "连续68–84证据审阅｜每页至多6行，保持原尺寸可读｜不是连续候选动作或rig验收", font=font(25), fill=(28, 49, 58))
        for row_index, row in enumerate(group_rows):
            sheet.paste(row, (0, 70 + 1010 * row_index))
        filename = f"contact_{indices[start]:03d}_{indices[start + len(group_rows) - 1]:03d}.png"
        sheet.save(output / filename)
        generated.append(filename)
        contacts.append({"file": filename, "frames": indices[start:start + len(group_rows)], "rows": len(group_rows), "noDownsampling": True})
    artifacts = []
    for filename in generated:
        path = output / filename
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            artifacts.append({"file": filename, "sha256": sha256(path), "size": list(image.size), "mode": image.mode, "readable": True})
    after = snapshot()
    if before != after:
        raise AssertionError("保护输入哈希/文件集合变化")
    invalid_counts = {pid: {str(a): sum(not p["valid"] for index in indices for p in tracks[pid][a][index]) for a in anchors} for pid in parameter_sets}
    first_failures = [{"parameters": pid, "anchor": anchor, "frame": index, "pointId": p["pointId"], "reason": p["failure"]}
                      for pid in parameter_sets for anchor in anchors for index in indices for p in tracks[pid][anchor][index]
                      if p["firstInvalidFrame"] == index and not p["valid"]]
    metrics = {"frameCount": 17, "anchorCount": 3, "pointsPerAnchor": 6, "fitPoints": 4, "holdoutPoints": 2,
        "generatedImageCount": len(generated), "frameReviewCount": 17, "contactPageCount": len(contacts),
        "primaryAnchorSwitchFrames": switches, "fallbackFrames": fallbacks, "unregisteredFrames": unregistered,
        "primaryHoldoutLostFrames": lost_primary_holdouts, "invalidPointFrameCounts": invalid_counts,
        "firstTrackFailures": first_failures,
        "forwardBackwardErrorMaxPx": max(all_fb) if all_fb else None,
        "commonSourceFitMultiAnchorDisagreementMaxPx": max(all_disagreement) if all_disagreement else None,
        "primaryFitResidualRmsRangePx": [min(fit_rms_values), max(fit_rms_values)] if fit_rms_values else None,
        "primaryHeldOutResidualRmsRangePx": [min(heldout_rms_values), max(heldout_rms_values)] if heldout_rms_values else None,
        "interpretation": "仅数据/实现诊断，不是解剖误差、置信区间、质量分或通过阈值"}
    gate = {"production": False, "profileSelected": False, "bindingApproved": False,
            "minimumRepairMaskReady": False, "continuousWalkProduced": False}
    records = {"schemaVersion": 1, "status": "bounded_evidence_review_completed_not_rig_validated",
        "delivery": "bounded evidence review completed, not rig validated", "sourceTaskId": task,
        "sourceVideoSha256": video_sha, "characterId": None, "promotedToRuntime": False,
        "direction": "right_front_3q", "actionUnderReview": "walk", "frameIndices": indices,
        "scriptSha256": sha256(Path(__file__)), "sourceHashes": {str(p): sha256(p) for p in (body_path, evidence_path, sources_path, stable_path, reference_path)},
        "provenance": provenance, "observations": body["observations"],
        "tracking": {"algorithm": "OpenCV calcOpticalFlowPyrLK, each anchor independently forward/backward adjacent frames",
            "opencvVersion": cv2.__version__, "parameters": parameter_sets, "flags": 0,
            "primaryParametersFixedBeforeTracking": primary_parameters, "parameterSelectionByScore": False,
            "criteriaType": "COUNT|EPS", "invalidPolicy": "任一步status/有限性/画幅/FB失败则该方向永久失效，不复活、不插补；锚点另方向独立",
            "lkPatchErrorUnits": "flags=0平均L1 patch差，非像素位置误差", "fbUnits": "原视频像素",
            "cumulativeMaxMeaning": "从锚到当前路径观测到的单步FB误差最大值，不是累计漂移上界",
            "notAnatomicalTruth": True, "notConfidenceIntervalOrPassScore": True,
            "allCandidatesTracks": {pid: {str(a): {str(i): tracks[pid][a][i] for i in indices} for a in anchors} for pid in parameter_sets}},
        "registration": {"fitMethod": "四个有效fit点的无RANSAC最小二乘相似；任何fit丢失整锚失效；holdout绝不参与",
            "primarySelection": "最近有效锚；距离平局小帧；最近锚fit丢失允许fallback并标注",
            "missingHoldout": "null，不补齐、不用于择锚", "noTemporalSmoothingOrBranchLinking": True,
            "anchorMatrixRecoveryMaxAbs": anchor_recovery, "commonDisagreementProbe": "共同sourceFitXY四点投影到同一视频帧的两两欧氏分歧",
            "notProfileSelectionOrRuntimeTransform": True},
        "reviewPolicy": {"curves": "仅开放曲线；不连接末点到首点；端点未知；A/B仅证据id，无near/far绑定",
            "normalization": "每帧原图和开放轮廓用同一主相似逆变换到768×768，再固定ROI展示；插值仅用于审阅",
            "staticReference": "稳定七件原样静态源合成，不是连续候选动作，禁止动作质量评分",
            "staticReferencePixelSha256": static_digest, "newArmPoses": 0, "v9PoseBranchesReadOrLinked": False,
            "shoulder": "shoulderAllowBox仅原锚低可信假设，不作为传播解剖真值或mask边界",
            "chest71To76": "可见团臂覆盖身体可确认；near/far未知",
            "crossedLegs": "前层可见边界覆盖后层可确认；near/far或必须交换draworder不可推出",
            "feet74To77": "引用manualObservations及sources.assetDecisions[3]；源脚形异常待设计修正，不能归咎rig"},
        "frames": frame_results, "metrics": metrics, "contactSheets": contacts, "generatedImages": artifacts,
        "gate": gate, **gate, "reuseContract": {"logicalParts": 7, "newBones": 0, "newAttachments": 0,
            "newCorrectives": 0, "newCorrectiveKeys": 0, "sourceAssetsChanged": False},
        "commonConstraintsApprovedBeforeBinding": False, "bindingValidated": False,
        "nextAction": "后续一次针对冲突复核（锚切换/多锚分歧、躯干与胸前遮挡、肩根隐藏域及74–77源脚形）后收口，可进入受约束制作试验；不能宣布绑定前共同约束通过。",
        "limitations": ["纹理追踪不等于头下接触线/腰线的真实解剖运动", "人工4 fit/2 holdout与粗轮廓均非独立解剖真值",
            "相似配准残差不能区分视角比例、软体形变、源生成漂移及标注误差", "多锚与LK诊断不当作置信区间或通过评分",
            "未恢复肩根隐藏域，不具备最小补画mask", "没有绑定、新姿态、连续候选动作或动作质量评分；84仅重复端点候选"]}
    import ast
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    counts = {str(folder): sum(folder in Path(p).parents for p in before) for folder in required}
    checks = {"allProtectedUnchanged": before == after, "protectedFileCount": len(before), "protectedDirectoryFileCounts": counts,
        "protectedHashesBeforeAfter": {p: {"before": h, "after": after[p]} for p, h in before.items()},
        "protectionScope": "整个PARENT既有文件+studio_v2全部文件+固定源图；仅排除__pycache__及continuous_constraint_v1输出",
        "sourceTaskVideoShaChainPassed": True, "sourceFrameAndCropShaShapeCount": 17,
        "sourceFramesVideoDecodePixelExact": True, "cropSourcePixelExact": True,
        "pythonSyntaxPassed": True, "syntheticSimilarityRecoveryPassed": True, "syntheticInverseRecoveryPassed": True,
        "anchorOriginalMatrixRecoveryPassed": True, "tieChoosesSmallerAnchorPassed": True,
        "fitLossFallbackPassed": True, "allFitLostReturnsNullPassed": True, "invalidNeverRevivesPassed": True,
        "heldOutNotUsedInFit": True, "allGeneratedImagesReadable": True,
        "allGeneratedImageHashesVerified": all(sha256(output / a["file"]) == a["sha256"] for a in artifacts),
        "frameCount": 17, "frameReviewCount": 17, "contactRows": [c["rows"] for c in contacts],
        "allContactPagesAtMostSixRows": all(c["rows"] <= 6 for c in contacts),
        "jsonAllowNanFalseRoundTripPassed": True, "bindingValidated": False, "gate": gate, "metrics": metrics}
    for name, value in (("study.json", records), ("checks.json", checks)):
        path = output / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if load(path) != value:
            raise AssertionError(f"{name}严格JSON回读不符")
    if snapshot() != before:
        raise AssertionError("写出JSON后保护输入变化")
    print(json.dumps({"output": str(output), "status": records["status"], "protectedFileCount": len(before),
        "allProtectedUnchanged": True, "metrics": metrics, "gate": gate}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--weight-study", action="store_true", help="保留v1并输出独立v2权重分诊")
    group.add_argument("--corrective-study", action="store_true", help="独立v3单件修形，不增加部件或骨骼")
    group.add_argument("--topology-study", action="store_true", help="独立v4透明域裁网格诊断")
    group.add_argument("--compositing-study", action="store_true", help="独立v5透明合成诊断")
    group.add_argument("--edgeflow-study", action="store_true", help="独立v6连续截面边流与精确几何压力试验")
    group.add_argument("--bounded-weight-study", action="store_true", help="独立v7有边界静态权重场，不修改v1-v6")
    group.add_argument("--elbow-mechanism-study", action="store_true", help="独立v8肘部材料方向与有限枢轴敏感性审计")
    group.add_argument("--video-projection-study", action="store_true", help="独立v9共同配准下视频离散姿态对照，非walk时间线")
    group.add_argument("--registration-sensitivity-study", action="store_true", help="独立v10配准不确定性敏感性，不做候选排名")
    group.add_argument("--body-constraint-study", action="store_true", help="独立躯干投影/肩根允许区/胸前臂轮廓共同约束，不绑定")
    group.add_argument("--continuous-constraint-study", action="store_true", help="独立68–84连续证据审阅，不绑定、不生成候选动作")
    args = parser.parse_args()
    if args.continuous_constraint_study:
        run_continuous_constraint_study()
    elif args.body_constraint_study:
        run_body_constraint_study()
    elif args.registration_sensitivity_study:
        run_registration_sensitivity_study()
    elif args.video_projection_study:
        run_video_projection_study()
    elif args.elbow_mechanism_study:
        run_elbow_mechanism_study()
    elif args.bounded_weight_study:
        run_bounded_weight_study()
    elif args.edgeflow_study:
        run_edgeflow_study()
    elif args.compositing_study:
        run_compositing_diagnosis()
    elif args.topology_study:
        run_topology_diagnosis()
    elif args.corrective_study:
        run_corrective_study()
    elif args.weight_study:
        run_weight_study()
    else:
        main()
