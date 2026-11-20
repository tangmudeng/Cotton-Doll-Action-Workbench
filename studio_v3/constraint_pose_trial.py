from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE / "generated_rig" / "video_f7e82942"
OUT = PARENT / "constraint_pose_trial_v1"
V2 = HERE.parent / "studio_v2"
SCRIPT = Path(__file__).resolve()
FRAMES = (68, 72, 80)
ROI = (300, 230, 570, 475)
SCALE = 2
MAX_NFEV = 100
GATE = {name: False for name in (
    "production", "profileSelected", "bindingApproved", "minimumRepairMaskReady",
    "continuousWalkProduced", "promotedToRuntime")}
IDENTITY = "将同一候选逻辑臂对准本帧可见A轮廓的假设；A的near/far身份未知，不确认跨帧身份。"
LIMITATIONS = [
    IDENTITY,
    "仅68/72/80三个独立代表姿态；不建立时间分支关联，不是真实walk。",
    "开放粗轮廓为低可信人工观察，不是独立解剖真值。",
    "单向最近距离可命中肩内切口或对侧边，只是拟合参考残差/诊断，不是质量评分。",
    "躯干相似矩阵固定沿用旧研究；不重新配准，旧躯干误差和肩根问题仍未解决。",
    "有纹理AABB仅保守可观测代理，不代表三角内实际alpha或七件遮挡后可见。",
    "隐藏肩腋、对侧臂、腿/躯干动态、衣袖和跨角色未验收；不声明共同约束通过。",
]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    def reject(value):
        raise ValueError(f"非有限JSON常量：{value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def save_json(name, value):
    path = OUT / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if load(path) != value:
        raise AssertionError(f"严格JSON回读失败：{name}")


def protected_snapshot(extra):
    paths = set(extra)
    # 除自己的入口与输出外，额外保护整个studio_v3，覆盖PARENT全部现有文件。
    for folder in (HERE, V2):
        paths.update(p.resolve() for p in folder.rglob("*") if p.is_file()
                     and OUT not in p.resolve().parents and p.resolve() != SCRIPT)
    return {str(p): sha256(p) for p in sorted(paths)}


def main():
    if not sys.dont_write_bytecode:
        raise RuntimeError("必须以python -B运行，禁止写入旧目录pycache")
    if not all(p.is_dir() for p in (HERE, PARENT, V2)):
        raise FileNotFoundError("允许输出父目录或V2不存在")
    if OUT.exists():
        raise FileExistsError("一次性试验拒绝覆盖已有输出")
    syntax = SCRIPT.read_text(encoding="utf-8")
    ast.parse(syntax, filename=str(SCRIPT))
    compile(syntax, str(SCRIPT), "exec")
    legacy_path = HERE / "test_arm_mesh.py"
    continuous_path = PARENT / "continuous_constraint_v1" / "checks.json"
    old_checks = load(continuous_path)
    old_713 = old_checks["protectedHashesBeforeAfter"]
    if len(old_713) != 713 or old_checks["protectedFileCount"] != 713:
        raise AssertionError("旧连续检查不是713文件合同")
    fixed_source = HERE / "generated_rig" / "right_front_walk" / "source768.png"
    extra = {Path(p).resolve() for p in old_713} | {fixed_source, legacy_path, SCRIPT}
    before = protected_snapshot(extra)
    for p, h in old_713.items():
        if before[str(Path(p).resolve())] != h["after"] or h["before"] != h["after"]:
            raise AssertionError(f"旧713来源已发生变化：{p}")
    OUT.mkdir()
    # 在导入任何第三方包之前，限制本进程文件写入只能发生在新输出目录。
    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            mode, flags = args[1], args[2]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (1 | 2 | 64 | 512 | 1024)))
            if writing:
                p = Path(args[0]).resolve()
                if OUT not in p.parents:
                    raise PermissionError(f"试验写入越界：{p}")
        if event in ("os.remove", "os.rmdir", "os.rename"):
            raise PermissionError(f"试验禁止破坏性文件操作：{event}")
        if event == "os.mkdir":
            p = Path(args[0]).resolve()
            if p != OUT and OUT not in p.parents:
                raise PermissionError(f"试验建目录越界：{p}")
    sys.addaudithook(audit)
    import cv2
    import numpy as np
    import scipy
    from PIL import Image, ImageDraw
    from scipy.optimize import least_squares

    spec = importlib.util.spec_from_file_location("constraint_trial_readonly_legacy", legacy_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    if old.__name__ == "__main__" or old.PARENT != PARENT:
        raise AssertionError("只读import路径错误")
    paths = {
        "stableManifest": PARENT / "stable_parts_v1" / "manifest.json",
        "v7Study": PARENT / "arm_mesh_test_v7" / "study.json",
        "bodyStudy": PARENT / "body_constraint_v1" / "study.json",
        "v9Study": PARENT / "arm_mesh_test_v9" / "study.json",
        "videoManifest": PARENT / "video_parts_v1" / "manifest.json",
        "cycleSources": PARENT / "video_parts_v1" / "cycle_review" / "sources.json",
    }
    manifest, v7, body, v9, evidence, sources = [load(p) for p in paths.values()]
    for document in (evidence, sources):
        assert document["taskId"] == manifest["taskId"]
    for document in (body, v9):
        assert document["sourceTaskId"] == manifest["taskId"]
    for document in (body, v9, evidence, sources):
        assert document["sourceVideoSha256"] == manifest["sourceVideoSha256"]
    source_video = PARENT / "source.mp4"
    assert old.sha256(source_video) == manifest["sourceVideoSha256"]
    source_image = (paths["stableManifest"].parent / manifest["sourceImage"]["file"]).resolve()
    assert source_image == fixed_source
    assert sha256(source_image) == manifest["sourceImage"]["sha256"] == v7["sourceImage"]["sha256"]
    assert sha256(paths["stableManifest"]) == v7["sourceManifestSha256"]
    for document in (body, v9):
        for p, expected in document["sourceHashes"].items():
            assert sha256(p) == expected, f"历史来源SHA不符：{p}"
    assert len(manifest["parts"]) == 7
    assert manifest["assemblyLayerOrder"] == old.EXPECTED_ORDER
    layers = {}
    for part in manifest["parts"]:
        path = paths["stableManifest"].parent / part["file"]
        assert sha256(path) == part["sha256"]
        image = Image.open(path).convert("RGBA")
        assert list(image.size) == [part["width"], part["height"]]
        layer = Image.new("RGBA", old.SIZE)
        layer.paste(image, tuple(part["bbox"][:2]))
        layers[part["id"]] = layer
    texture = np.asarray(layers["arm_near"])
    mesh = v7["meshes"]["linear_12_94"]
    vertices = np.asarray(mesh["vertices"], dtype=np.float64)
    triangles = np.asarray(mesh["triangles"], dtype=np.int32)
    weights = np.asarray(mesh["weights"], dtype=np.float64)
    uv = np.asarray(mesh["uv"], dtype=np.float64)
    assert vertices.shape == (360, 2) and triangles.shape == (624, 3) and weights.shape == (360, 2)
    assert np.isfinite(weights).all() and (weights >= 0).all()
    assert np.allclose(weights.sum(axis=1), 1., atol=1e-12)
    assert hashlib.sha256(weights.tobytes()).hexdigest() == mesh["weightsSha256Float64"]
    assert np.allclose(uv, (vertices + .5) / 768., atol=1e-15)
    bind = old.JOINTS.copy()
    assert np.array_equal(bind, v7["bindJointsGlobalXY"])
    lengths = np.linalg.norm(np.diff(bind, axis=0), axis=1)
    assert np.array_equal(lengths, v7["bindBoneLengthsPx"])
    bind_angles = np.arctan2(np.diff(bind, axis=0)[:, 1], np.diff(bind, axis=0)[:, 0])
    edge_counts = Counter(tuple(sorted((int(a), int(b)))) for tri in triangles
                          for a, b in zip(tri, np.roll(tri, -1)))
    boundary = np.asarray([edge for edge, count in sorted(edge_counts.items()) if count == 1], dtype=np.int32)
    assert boundary.size and max(edge_counts.values()) == 2
    source_edges = np.transpose(vertices[triangles][:, 1:] - vertices[triangles][:, :1], (0, 2, 1))
    inverse_edges = np.linalg.inv(source_edges)
    affected = np.any(weights[triangles, 1] > 0., axis=1)
    textured = []
    for tri in triangles:
        lo = np.maximum(np.floor(vertices[tri].min(axis=0)).astype(int), 0)
        hi = np.minimum(np.ceil(vertices[tri].max(axis=0)).astype(int) + 1, 768)
        textured.append(bool(np.any(texture[lo[1]:hi[1], lo[0]:hi[0], 3] > 0)))
    textured = np.asarray(textured)

    def project(points, matrix):
        return np.column_stack((points, np.ones(len(points)))) @ matrix.T

    def pose(degrees):
        delta = np.deg2rad(degrees)
        joints = [bind[0].copy()]
        matrices = []
        for k in range(2):
            theta = bind_angles[k] + delta[k]
            joints.append(joints[-1] + lengths[k] * np.array([np.cos(theta), np.sin(theta)]))
            c, s = np.cos(delta[k]), np.sin(delta[k])
            rotation = np.array([[c, -s], [s, c]])
            matrices.append(np.column_stack((rotation, joints[k] - rotation @ bind[k])))
        joints = np.asarray(joints)
        assert np.array_equal(joints[0], bind[0])
        assert np.allclose(np.linalg.norm(np.diff(joints, axis=0), axis=1), lengths, atol=1e-12)
        return old.deform(vertices, weights, matrices), matrices, joints

    def nearest(points, mesh_points):
        a, b = mesh_points[boundary[:, 0]], mesh_points[boundary[:, 1]]
        direction = b - a
        denom = np.einsum("ij,ij->i", direction, direction)
        relative = points[:, None, :] - a[None, :, :]
        t = np.einsum("nbi,bi->nb", relative, direction) / np.maximum(denom, np.finfo(float).tiny)
        closest = a[None] + np.clip(t, 0., 1.)[:, :, None] * direction[None]
        return np.sqrt(np.min(np.sum((points[:, None] - closest) ** 2, axis=2), axis=1))

    assert np.allclose(nearest(project(vertices[boundary[:, 0]], np.eye(2, 3)), vertices), 0., atol=1e-12)

    def geometry(points):
        edges = np.transpose(points[triangles][:, 1:] - points[triangles][:, :1], (0, 2, 1))
        det = np.linalg.det(edges @ inverse_edges)
        result = {"diagnosticOnlyNotSelection": True,
                  "determinantDefinition": "变形三角边矩阵乘bind边矩阵逆的行列式；未含固定视频投影尺度",
                  "texturedAabbObservability": "仅bind三角AABB含alpha>0的保守代理；不等于三角内或遮挡后实际可见。纯透明AABB不算可见。"}
        for name, mask in (("allTriangles", np.ones(len(triangles), dtype=bool)),
                           ("weightAffectedTriangles", affected),
                           ("texturedAabbTriangles", textured),
                           ("weightAffectedTexturedAabbTriangles", affected & textured)):
            ids = np.flatnonzero(mask)
            flipped = ids[det[ids] < 0.]
            result[name] = {"count": int(len(ids)), "minimumDeterminant": float(det[ids].min()),
                            "minimumDeterminantTriangle": int(ids[np.argmin(det[ids])]),
                            "flippedTriangleCount": int(len(flipped)), "flippedTriangleIds": flipped.tolist()}
        result["determinantsByTriangle"] = det.tolist()
        return result

    source_records = {r["sourceFrame"]: r for r in sources["frames"]}
    results, pngs, reviews = {}, [], []
    frame_inputs = {}
    for index in FRAMES:
        key = str(index)
        matrix = np.asarray(body["results"][key]["methods"]["torso_similarity"]["matrix"], dtype=float)
        box = np.asarray(body["observations"]["frames"][key]["shoulderAllowBox"], dtype=float)
        record = source_records[index]
        frame_path = paths["cycleSources"].parent / record["sourceFile"]
        assert sha256(frame_path) == record["sourceFrameSha256"] == body["results"][key]["sourceFrameSha256"]
        frame = Image.open(frame_path).convert("RGB")
        assert frame.size == (864, 480)
        part = next(p for p in evidence["parts"] if p["id"] == body["results"][key]["armEvidenceId"])
        assert part["sourceFrame"] == index and part["sourceFrameSha256"] == sha256(frame_path)
        assert part["anatomicalIdentity"] == "unknown" and not part["crossFrameIdentityEstablished"]
        other_frame = paths["videoManifest"].parent / part["sourceFile"]
        assert sha256(other_frame) == sha256(frame_path)
        curve = np.asarray(part["polygonSourcePixels"], dtype=float)
        assert len(curve) >= 2 and not np.array_equal(curve[0], curve[-1])
        raw, segment_info = [], []
        # 每个存储分段均匀采样，间距至多1源视频像素；共享端点去重，不添加末首闭合段。
        for k, (a, b) in enumerate(zip(curve[:-1], curve[1:])):
            intervals = max(1, int(np.ceil(np.linalg.norm(b - a))))
            ts = np.linspace(0., 1., intervals + 1)
            if k:
                ts = ts[1:]
            samples = a + ts[:, None] * (b - a)
            raw.extend(samples)
            segment_info.append({"segment": k, "lengthPx": float(np.linalg.norm(b - a)),
                                 "intervals": intervals, "contributedSamples": len(samples)})
        raw = np.asarray(raw)
        endpoint_distance = np.linalg.norm(raw[:, None] - curve[[0, -1]][None], axis=2).min(axis=1)
        endpoint_excluded = endpoint_distance <= 5.
        shoulder_excluded = ((raw >= box[:2]) & (raw <= box[2:])).all(axis=1)
        valid = ~(endpoint_excluded | shoulder_excluded)
        observed = raw[valid]
        assert len(observed) > 0
        baseline = np.asarray(v9["results"]["baseline"][key]["sameTargetDiscreteSolutions"][0]["rotationDeltaDegrees"])
        seeds = [baseline, baseline + 20., baseline - 20.]
        assert all(((s >= -150.) & (s <= 150.)).all() for s in seeds)
        evaluations = [0]

        def residual(degrees):
            evaluations[0] += 1
            points, _, _ = pose(degrees)
            return nearest(observed, project(points, matrix))

        candidates = []
        for seed_id, seed in enumerate(seeds):
            start_calls = evaluations[0]
            solve = least_squares(residual, seed, bounds=(-150., 150.), max_nfev=MAX_NFEV,
                                  method="trf", loss="linear", ftol=1e-8, xtol=1e-8, gtol=1e-8)
            loss = float(np.mean(solve.fun ** 2))
            finite = bool(np.isfinite(loss) and np.isfinite(solve.x).all() and np.isfinite(solve.fun).all())
            candidates.append({"seedId": seed_id, "initialRotationDeltaDegrees": seed.tolist(),
                               "rotationDeltaDegrees": solve.x.tolist(), "fitLossMeanSquaredPx": loss if finite else None,
                               "finite": finite, "solverSuccess": bool(solve.success), "status": int(solve.status),
                               "message": str(solve.message), "nfev": int(solve.nfev),
                               "njev": int(solve.njev) if solve.njev is not None else None,
                               "actualResidualCallsIncludingNumericalJacobian": evaluations[0] - start_calls})
        finite_candidates = [c for c in candidates if c["finite"]]
        assert finite_candidates
        chosen = min(finite_candidates, key=lambda c: c["fitLossMeanSquaredPx"])
        pose_records, images = {}, [frame]
        for label, angles in (("baseline", baseline), ("fitted", chosen["rotationDeltaDegrees"])):
            points, matrices, joints = pose(angles)
            distances = nearest(observed, project(points, matrix))
            arm, raster, _ = old.render_mesh(texture, uv, triangles, points, "source_over_top_left")
            assembly = old.assemble(manifest, layers, arm)
            warped = cv2.warpAffine(np.asarray(assembly), matrix, (864, 480), flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
            display = Image.new("RGBA", (864, 480), (249, 249, 246, 255))
            display.alpha_composite(Image.fromarray(warped))
            images.append(display.convert("RGB"))
            joint_error = np.linalg.norm(np.diff(joints, axis=0), axis=1) - lengths
            pose_records[label] = {
                "rotationDeltaDegrees": np.asarray(angles).tolist(),
                "rotationSemantics": "每骨绝对bind-relative旋转差，不是parent-local Spine旋转key",
                "boneMatricesBindToCharacterXY": [m.tolist() for m in matrices],
                "boneMatricesBindToVideoXY": [(matrix @ np.vstack((m, [0., 0., 1.]))).tolist() for m in matrices],
                "boneEndpointsCharacterXY": joints.tolist(), "boneEndpointsVideoXY": project(joints, matrix).tolist(),
                "maximumBoneLengthErrorPx": float(np.abs(joint_error).max()),
                "deformedVerticesCharacterXY": points.tolist(), "projectedVerticesVideoXY": project(points, matrix).tolist(),
                "fitLossMeanSquaredPx": float(np.mean(distances ** 2)),
                "fitRmsPx": float(np.sqrt(np.mean(distances ** 2))),
                "referenceDistancesPx": distances.tolist(), "effectivePointCount": len(observed),
                "oneSidedFitDiagnosticNotQualityScore": True, "geometry": geometry(points), "raster": raster}
        sampling = {"allStoredSegmentsUsed": True, "closed": False, "maximumSpacingSourceVideoPx": 1.,
                    "endpointExclusionRadiusPx": 5., "shoulderAllowBox": box.tolist(),
                    "rawCount": len(raw), "effectiveCount": len(observed),
                    "excludedEndpointCount": int(endpoint_excluded.sum()),
                    "excludedShoulderCount": int(shoulder_excluded.sum()),
                    "excludedUnionCount": int((~valid).sum()), "segments": segment_info,
                    "storedOpenCurveSourceVideoXY": curve.tolist(), "rawSamplesSourceVideoXY": raw.tolist(),
                    "validSampleMask": valid.tolist(), "effectiveSamplesSourceVideoXY": observed.tolist()}
        results[key] = {"sourceFrame": index, "identityHypothesis": IDENTITY, "anatomicalIdentity": "unknown",
                        "crossFrameIdentityEstablished": False, "temporalBranchAssociation": False,
                        "fixedTorsoSimilarityMatrix": matrix.tolist(), "armEvidenceId": part["id"],
                        "sampling": sampling, "solverCandidates": candidates, "selectedSeedId": chosen["seedId"],
                        "selection": "三个预声明有限求解结果中最小有限MSE；不依几何/遮挡择解，也不选时间分支",
                        **pose_records}
        frame_inputs[key] = {"file": str(frame_path), "sha256": sha256(frame_path),
                             "duplicateEvidenceSourceFile": str(other_frame), "evidenceId": part["id"]}
        width, height = 1716, 765
        sheet = Image.new("RGB", (width, height), (238, 242, 241))
        draw = ImageDraw.Draw(sheet)
        text_checks = []

        def text(x, y, value, size=19, color=(38, 57, 65)):
            f = old.font(size)
            bounds = draw.textbbox((x, y), value, font=f)
            assert bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= width - 12 and bounds[3] <= height - 10, value
            draw.text((x, y), value, font=f, fill=color)
            text_checks.append(list(bounds))

        text(18, 12, f"隔离姿态拟合试验 v1｜代表帧 {index:03d}｜固定骨长 / 单一arm_near / 七件层序", 26)
        text(18, 54, "身份未知：仅假设同一候选臂对准本帧可见A轮廓；不确认near/far或跨帧身份。", 20, (132, 58, 37))
        text(18, 88, "不是真实walk，不建立时间分支关联，不代表共同约束通过。肩根未补、其他六件不单独拟合。", 20, (132, 58, 37))
        for col, (image, title) in enumerate(zip(images, ("源视频局部（开放参考点）", "旧v9基线七件（固定躯干矩阵）", "有限拟合七件（仅调整两个角）"))):
            x = 18 + col * 566
            text(x, 131, title, 21)
            sheet.paste(image.crop(ROI).resize(((ROI[2] - ROI[0]) * SCALE, (ROI[3] - ROI[1]) * SCALE), Image.Resampling.NEAREST), (x, 170))
            for point in observed:
                px, py = x + (point[0] - ROI[0]) * SCALE, 170 + (point[1] - ROI[1]) * SCALE
                if x <= px < x + 540 and 170 <= py < 660:
                    draw.ellipse((px - 1, py - 1, px + 1, py + 1), fill=(225, 136, 28))
        text(18, 674, f"有效点{len(observed)}；基线RMS {pose_records['baseline']['fitRmsPx']:.3f}px → 拟合 {pose_records['fitted']['fitRmsPx']:.3f}px；单向残差不是质量分数。", 20)
        text(18, 708, f"统一视频ROI {ROI} / 固定{SCALE}倍nearest；无自动bbox缩放。橙点仅拟合参考，未使用holdout。", 19)
        filename = f"f{index:03d}_review.png"
        sheet.save(OUT / filename)
        reviews.append(sheet)
        pngs.append({"file": filename, "size": list(sheet.size), "sha256": sha256(OUT / filename),
                     "allTextInsideCanvas": True, "textBounds": text_checks})
    overview = Image.new("RGB", (1716, 765 * 3), (238, 242, 241))
    for row, review in enumerate(reviews):
        overview.paste(review, (0, row * 765))
    overview.save(OUT / "overview.png")
    pngs.append({"file": "overview.png", "size": list(overview.size), "sha256": sha256(OUT / "overview.png")})
    for artifact in pngs:
        with Image.open(OUT / artifact["file"]) as image:
            image.verify()
        with Image.open(OUT / artifact["file"]) as image:
            image.load()
            assert list(image.size) == artifact["size"] and image.format == "PNG"
    mesh_fingerprint = {k: hashlib.sha256(np.asarray(mesh[k], dtype=np.float64 if k != "triangles" else np.int32).tobytes()).hexdigest()
                        for k in ("vertices", "triangles", "uv", "weights")}
    source_hashes = {str(p): sha256(p) for p in list(paths.values()) + [source_video, source_image, legacy_path]}
    source_hashes.update({str(paths["stableManifest"].parent / p["file"]): p["sha256"] for p in manifest["parts"]})
    source_hashes.update({r["file"]: r["sha256"] for r in frame_inputs.values()})
    after = protected_snapshot(extra)
    assert before == after, "受保护文件发生增删或内容变化"
    reuse = {"logicalParts": 7, "testedArmLogicalParts": 1, "armId": "arm_near", "existingArmBones": 2,
             "newBones": 0, "newAttachments": 0, "newCorrectiveKeys": 0, "sourceAssetsChanged": False,
             "meshWeightsChanged": False, "assemblyLayerOrder": manifest["assemblyLayerOrder"]}
    trial = {"schemaVersion": 1, "status": "isolated_three_pose_hypothesis_fit_not_common_constraint_pass",
             **GATE, "sourceTaskId": manifest["taskId"], "sourceVideoSha256": manifest["sourceVideoSha256"],
             "scriptSha256": sha256(SCRIPT), "sourceHashes": source_hashes,
             "historicalStudyScriptSha256Preserved": {n: d["scriptSha256"] for n, d in (("v7", v7), ("v9", v9), ("body", body))},
             "inputFrames": frame_inputs, "reuseContract": reuse,
             "frozenMesh": {"sourceFile": str(paths["v7Study"]), "jsonPath": "meshes.linear_12_94",
                            "vertexCount": 360, "triangleCount": 624, "boundaryEdgeCount": len(boundary),
                            "outerBoundaryExtraction": "三角无向边出现一次；包含肩内切口/对侧边，不等于可见alpha边界",
                            "boundaryVertexPairs": boundary.tolist(), "arraySha256": mesh_fingerprint,
                            "bindJointsGlobalXY": bind.tolist(), "bindBoneLengthsPx": lengths.tolist()},
             "solverPolicy": {"method": "scipy.optimize.least_squares", "degreesOfFreedomPerFrame": 2,
                              "initialSeeds": "旧v9基线、两个角同时+20deg、两个角同时-20deg；共三个固定初值",
                              "rotationBoundsDegreesPerAngle": [-150, 150], "maxNfevPerSeed": MAX_NFEV,
                              "ftol": 1e-8, "xtol": 1e-8, "gtol": 1e-8, "loss": "linear",
                              "objective": "有效开放观察点到固定网格变形投影边线段的最近欧氏距离；MSE仅用于本帧有限候选择解",
                              "geometryUsedForSelection": False, "holdoutUsedForFit": False, "registrationRefit": False,
                              "elbowPivotSweep": False, "thresholdTuning": False, "temporalBranchAssociation": False,
                              "finiteDifferenceResidualCallsMayExceedNfev": True},
             "reviewPolicy": {"fixedSourceVideoRoi": list(ROI), "fixedScale": SCALE, "resampling": "nearest",
                              "automaticBboxScaling": False, "otherSixPartsFrozen": True},
             "results": results, "generatedImages": pngs, "limitations": LIMITATIONS,
             "environment": {"python": sys.version, "executable": sys.executable, "numpy": np.__version__,
                             "scipy": scipy.__version__, "opencv": cv2.__version__}}
    checks = {**GATE, "scriptSha256": sha256(SCRIPT), "allProtectedUnchanged": True,
              "protectedFileCount": len(before), "protectedScopes": [str(HERE), str(PARENT), str(V2), str(fixed_source)],
              "excludedFromProtection": [str(OUT)], "scriptSelfShaTracked": True,
              "protectedHashesBeforeAfter": {p: {"before": h, "after": after[p]} for p, h in before.items()},
              "oldContinuousChecks": {"file": str(continuous_path), "sha256Before": before[str(continuous_path)],
                                      "sha256After": after[str(continuous_path)], "protectedFileCount": 713,
                                      "all713RecordedHashesStillMatch": True},
              "sourceShaChainPassed": True, "allGeneratedPngVerifyAndLoadPassed": True,
              "allGeneratedTextInsideCanvas": True, "strictJsonAllowNanFalseRoundTripPassed": True,
              "astParseAndCompileInMemoryPassed": True, "noPycacheWrites": True,
              "legacyImportedReadOnlyNotExecuted": True, "writeScopeAuditEnforced": True,
              "reuseContract": reuse, "visualReview": {"status": "pending_actual_ViewImage_review"},
              "generatedImages": pngs, "limitations": LIMITATIONS}
    save_json("trial.json", trial)
    checks["trialJsonSha256"] = sha256(OUT / "trial.json")
    save_json("checks.json", checks)
    assert protected_snapshot(extra) == before, "JSON写出后受保护文件发生变化"
    print(json.dumps({"output": str(OUT), "protectedFileCount": len(before), "old713Preserved": True,
                      "summary": {k: {"points": r["sampling"]["effectiveCount"],
                                       "baselineRmsPx": r["baseline"]["fitRmsPx"], "fittedRmsPx": r["fitted"]["fitRmsPx"],
                                       "rotationDeltaDegrees": r["fitted"]["rotationDeltaDegrees"],
                                       "geometry": r["fitted"]["geometry"]["weightAffectedTexturedAabbTriangles"]}
                                  for k, r in results.items()}, **GATE}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
