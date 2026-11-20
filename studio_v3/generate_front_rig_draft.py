from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

SOURCE_DIR = Path(r"I:\彩虹AI\design\AI玩具_design\美术资源\棉花娃娃\基础角色-测试")
SOURCE = SOURCE_DIR / "正面图层.png"
PACKAGE = Path(__file__).resolve().parent / "generated_parts" / "six_view_alignment_package_1280x736"
OUT = PACKAGE / "diagnostics_invalid_template_masks"
VIEW_FILES = {
    "front": "正面图层.png",
    "back": "背面图层.png",
    "right_front_3q": "右前¾侧图层.png",
    "right_back_3q": "右后¾侧图层.png",
    "left_front_3q": "左前¾侧图层.png",
    "left_back_3q": "左后¾侧图层.png",
}
CANVAS = (1280, 736)

# Coarse normalized masks for review only. Joint overlap is intentional; each view is fitted to its own alpha bounds.
POLYGONS = {
    "front_head": [(236, 0), (425, 0), (550, 92), (666, 196), (696, 322), (676, 442), (615, 520), (544, 558), (456, 570), (250, 565), (154, 535), (69, 488), (10, 409), (0, 315), (33, 226), (113, 137)],
    "front_body": [(278, 545), (429, 545), (477, 579), (506, 651), (515, 734), (500, 790), (480, 828), (440, 845), (359, 852), (270, 846), (220, 822), (194, 770), (190, 700), (201, 650), (235, 578)],
    "front_arm_l": [(218, 557), (267, 556), (286, 583), (268, 650), (245, 717), (231, 756), (206, 774), (178, 768), (153, 742), (145, 704), (160, 640), (185, 585)],
    "front_arm_r": [(427, 555), (470, 572), (503, 621), (531, 679), (555, 720), (553, 752), (526, 773), (494, 772), (470, 747), (452, 700), (431, 647)],
    "front_leg_l": [(210, 742), (263, 756), (315, 782), (355, 800), (362, 824), (347, 866), (335, 901), (315, 920), (261, 925), (228, 916), (211, 893), (205, 846)],
    "front_leg_r": [(346, 800), (400, 780), (454, 748), (484, 760), (500, 800), (493, 837), (492, 886), (477, 912), (451, 923), (399, 926), (374, 916), (356, 891)],
}
REFERENCE_ALPHA_BBOX = (0, 0, 708, 926)

BONES = {
    "skeleton": "cotton_doll_six_view",
    "spineVersion": "4.2",
    "source": str(SOURCE),
    "status": "view_alignment_verified_rigging_not_started",
    "coordinateSystem": {"canvasWidth": 1280, "canvasHeight": 736, "origin": "top-left; shared source canvas and foot baseline retained"},
    "referenceCanvas": {"width": 708, "height": 926, "mapping": "legacy diagnostic template only; not valid for per-view segmentation"},
    "nextProductionGate": "Use a segmentation workflow that identifies each view's actual limb boundaries; then artist-review masks and inpaint hidden joints before Spine binding.",
    "viewAlignment": {}, 
    "bones": [
        {"name": "root", "parent": None, "role": "桌面位置与整体移动"},
        {"name": "view_root", "parent": "root", "role": "当前方向共同根骨"},
        {"name": "hip", "parent": "view_root", "role": "身体重心与腿部连接"},
        {"name": "body", "parent": "hip", "role": "躯干摆动"},
        {"name": "neck", "parent": "body", "role": "头部连接"},
        {"name": "head", "parent": "neck", "role": "头部整体（脸、发型、耳朵与发夹暂不再拆）"},
        {"name": "arm_l", "parent": "body", "role": "画面左臂，肩部 pivot"},
        {"name": "arm_r", "parent": "body", "role": "画面右臂，肩部 pivot"},
        {"name": "leg_l", "parent": "hip", "role": "画面左腿，髋部 pivot"},
        {"name": "leg_r", "parent": "hip", "role": "画面右腿，髋部 pivot"},
    ],
    "slotTemplate": ["{view}_leg_l", "{view}_leg_r", "{view}_body", "{view}_arm_l", "{view}_arm_r", "{view}_head"],
    "parts": [name.replace("front_", "{view}_", 1) for name in POLYGONS],
    "viewSet": [
        {"id": "front", "sourceName": "正面图层.png", "attachment": "view_front", "mirror": False, "slotOrder": ["front_leg_l", "front_leg_r", "front_body", "front_arm_l", "front_arm_r", "front_head"]},
        {"id": "back", "sourceName": "背面图层.png", "attachment": "view_back", "mirror": False, "slotOrder": ["back_leg_l", "back_leg_r", "back_body", "back_arm_l", "back_arm_r", "back_head"]},
        {"id": "right_front_3q", "sourceName": "右前¾侧图层.png", "attachment": "view_right_front_3q", "mirror": False, "slotOrder": ["right_front_3q_leg_l", "right_front_3q_leg_r", "right_front_3q_body", "right_front_3q_arm_l", "right_front_3q_arm_r", "right_front_3q_head"]},
        {"id": "right_back_3q", "sourceName": "右后¾侧图层.png", "attachment": "view_right_back_3q", "mirror": False, "slotOrder": ["right_back_3q_leg_l", "right_back_3q_leg_r", "right_back_3q_body", "right_back_3q_arm_l", "right_back_3q_arm_r", "right_back_3q_head"]},
        {"id": "left_front_3q", "sourceName": "左前¾侧图层.png", "attachment": "view_left_front_3q", "mirror": False, "slotOrder": ["left_front_3q_leg_l", "left_front_3q_leg_r", "left_front_3q_body", "left_front_3q_arm_l", "left_front_3q_arm_r", "left_front_3q_head"]},
        {"id": "left_back_3q", "sourceName": "左后¾侧图层.png", "attachment": "view_left_back_3q", "mirror": False, "slotOrder": ["left_back_3q_leg_l", "left_back_3q_leg_r", "left_back_3q_body", "left_back_3q_arm_l", "left_back_3q_arm_r", "left_back_3q_head"]}
    ],
    "sharedRigPolicy": "Use one semantic bone-name contract, but keep per-view attachment placement and pose corrections. Do not mirror asymmetric hair clips or hidden-side silhouettes.",
    "pivotReviewRequired": ["head-neck", "left-shoulder", "right-shoulder", "left-hip", "right-hip", "left-foot", "right-foot"],
    "knownLimitations": [
        "All six diagnostic layers reused the same normalized front polygon template fitted to each view alpha bounds. They are invalid for rigging and are retained only as a diagnostic demonstration of coverage, not as deliverable part art.",
        "Do not import files named *_head.png, *_body.png, *_arm_*.png or *_leg_*.png from the diagnostics_invalid_template_masks folder into Spine.",
        "Masks can cross fur contours or garment boundaries; uncovered source pixels are retained on the torso for gap-free preview.",
        "The source has no separated rear/front hair or ear layers; the head remains one attachment.",
        "Hidden pixels under arms, head and legs are not present in the source and still need inpainting before large rotations.",
        "The six direction images are 1280x736 transparent RGBA sources with near-matched alpha bounds; each view still needs per-view pivot review before attachment swapping.",
        "Image2 concept output was rejected because it returned a white RGB sheet and merged body/legs instead of separate alpha parts.",
        "Same action across views shares timing and event semantics; pose keys and draw order require per-view corrections.",
        "This file is a rig design specification, not a native editable Spine project or runtime export."
    ],
    "actions": {
        "idle_stand": {"phase": "prototype", "sharedAcrossViews": ["timing", "breath rhythm", "event markers"], "viewSpecific": ["pose keys", "depth order", "anchor correction"]},
        "walk": {"phase": "after idle approval", "sharedAcrossViews": ["cycle duration", "contact-to-swing timing", "footstep event rhythm"], "viewSpecific": ["limb pose", "occlusion order", "foot plant correction"]}
    }
}


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    OUT.mkdir(parents=True, exist_ok=True)
    PACKAGE.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != CANVAS:
        raise ValueError(f"Expected normalized canvas {CANVAS}, got {source.size}")

    alignment = {}
    for view_id, filename in VIEW_FILES.items():
        path = SOURCE_DIR / filename
        image = Image.open(path).convert("RGBA")
        if image.size != CANVAS:
            raise ValueError(f"{filename} is {image.size}, expected {CANVAS}")
        bbox = image.getchannel("A").getbbox()
        alignment[view_id] = {"file": filename, "alphaBounds": list(bbox), "footY": bbox[3] - 1, "centerX": round((bbox[0] + bbox[2]) / 2, 2), "opaquePixels": sum(1 for value in image.getchannel("A").tobytes() if value > 16)}
        image.save(PACKAGE / f"{view_id}.png")
    bottoms = [item["footY"] for item in alignment.values()]
    if max(bottoms) - min(bottoms) > 3:
        raise ValueError(f"View foot baselines differ by more than 3px: {bottoms}")
    BONES["viewAlignment"] = alignment

    from PIL import ImageChops
    reports = {}
    tile_size = (640, 368)
    contact_sheet = Image.new("RGBA", (tile_size[0] * 3, tile_size[1] * 2), (24, 27, 31, 255))
    order_suffix = ["leg_l", "leg_r", "body", "arm_l", "arm_r", "head"]
    for index, (view_id, filename) in enumerate(VIEW_FILES.items()):
        view_source = Image.open(SOURCE_DIR / filename).convert("RGBA")
        bbox = view_source.getchannel("A").getbbox()
        layers: dict[str, Image.Image] = {}
        for base_name, polygon in POLYGONS.items():
            mask = Image.new("L", (708, 926), 0)
            ImageDraw.Draw(mask).polygon(polygon, fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(0.45))
            mapped = mask.resize((bbox[2] - bbox[0], bbox[3] - bbox[1]), Image.Resampling.LANCZOS)
            full_mask = Image.new("L", CANVAS, 0)
            full_mask.paste(mapped, (bbox[0], bbox[1]))
            part_alpha = ImageChops.multiply(view_source.getchannel("A"), full_mask)
            layer = view_source.copy()
            layer.putalpha(part_alpha)
            name = base_name.replace("front_", view_id + "_", 1)
            layer.save(OUT / f"{name}.png")
            layers[base_name.removeprefix("front_")] = layer

        draw_order = ["leg_l", "leg_r", "body", "arm_l", "arm_r", "head"]
        preview = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        for suffix in draw_order:
            preview.alpha_composite(layers[suffix])
        preview_path = OUT / f"{view_id}_idle_assembly_draft.png"
        preview.save(preview_path)
        union = Image.new("L", CANVAS, 0)
        for layer in layers.values():
            union = ImageChops.lighter(union, layer.getchannel("A"))
        source_alpha = view_source.getchannel("A")
        missing_mask = ImageChops.subtract(source_alpha, union)
        missing = sum(1 for value in missing_mask.tobytes() if value > 16)
        opaque = sum(1 for value in source_alpha.tobytes() if value > 16)
        if missing:
            missing_pixels = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
            missing_pixels.paste(view_source, (0, 0), missing_mask)
            layers["body"] = Image.alpha_composite(layers["body"], missing_pixels)
            body_name = f"{view_id}_body.png"
            layers["body"].save(OUT / body_name)
            preview = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
            for suffix in draw_order:
                preview.alpha_composite(layers[suffix])
            preview.save(preview_path)
        reports[view_id] = {
            "source": filename,
            "canvas": list(CANVAS),
            "alphaBounds": list(bbox),
            "opaquePixels": opaque,
            "uncoveredPixels": 0,
            "recoveredOutsideMaskPixels": missing,
            "coverage": 1.0,
            "preview": preview_path.name,
            "slotOrder": [f"{view_id}_leg_back", f"{view_id}_body", f"{view_id}_arm_back", f"{view_id}_head", f"{view_id}_arm_front", f"{view_id}_leg_front"],
            "maskMethod": "same normalized polygon template fitted to this view alpha bounds",
            "status": "template_mask_not_valid_for_rigging",
        }
        tile = preview.resize(tile_size, Image.Resampling.LANCZOS)
        tile_back = Image.new("RGBA", tile_size, (24, 27, 31, 255))
        tile_back.alpha_composite(tile)
        ImageDraw.Draw(tile_back).text((12, 10), view_id, fill=(240, 242, 244, 255))
        contact_sheet.alpha_composite(tile_back, ((index % 3) * tile_size[0], (index // 3) * tile_size[1]))

    BONES["viewAlignment"] = alignment
    BONES["viewSet"] = [
        {"id": view_id, "sourceName": filename, "attachment": f"view_{view_id}", "mirror": False,
         "slotOrder": [f"{view_id}_leg_back", f"{view_id}_body", f"{view_id}_arm_back", f"{view_id}_head", f"{view_id}_arm_front", f"{view_id}_leg_front"]}
        for view_id, filename in VIEW_FILES.items()
    ]
    (OUT / "coverage_report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheet.save(OUT / "six_view_contact_sheet.png")
    (OUT / "six_view_rig_spec.json").write_text(json.dumps(BONES, ensure_ascii=False, indent=2), encoding="utf-8")

    PACKAGE_BONES = dict(BONES)
    PACKAGE_BONES["status"] = "view_alignment_verified_rigging_not_started"
    PACKAGE_BONES["warning"] = "No per-view part masks, hidden-pixel inpainting, pivot review, or Spine binding are included. The diagnostic template masks must not be imported."
    (PACKAGE / "six_view_rig_spec.json").write_text(json.dumps(PACKAGE_BONES, ensure_ascii=False, indent=2), encoding="utf-8")
    (PACKAGE / "alignment_report.json").write_text(json.dumps({"canvas": list(CANVAS), "footBaselineRange": [min(bottoms), max(bottoms)], "views": alignment, "maskingStatus": "not_produced_validly", "nextGate": "create view-specific masks and inpaint occluded regions, then validate pivots"}, ensure_ascii=False, indent=2), encoding="utf-8")
    package_sheet = Image.new("RGBA", (tile_size[0] * 3, tile_size[1] * 2), (24, 27, 31, 255))
    for index, (view_id, filename) in enumerate(VIEW_FILES.items()):
        original = Image.open(SOURCE_DIR / filename).convert("RGBA").resize(tile_size, Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", tile_size, (24, 27, 31, 255))
        tile.alpha_composite(original)
        ImageDraw.Draw(tile).text((12, 10), view_id, fill=(240, 242, 244, 255))
        package_sheet.alpha_composite(tile, ((index % 3) * tile_size[0], (index // 3) * tile_size[1]))
    package_sheet.save(PACKAGE / "six_view_source_contact_sheet.png")
    print(f"Created alignment package at {PACKAGE}")
    print(f"Diagnostic masks (not for Spine): {OUT}")
    print(f"Contact sheet: {PACKAGE / 'six_view_source_contact_sheet.png'}")
    print(f"Alignment report: {PACKAGE / 'alignment_report.json'}")


if __name__ == "__main__":
    main()
