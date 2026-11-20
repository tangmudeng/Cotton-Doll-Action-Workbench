from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

SOURCE_DIR = Path(r"I:\彩虹AI\design\AI玩具_design\美术资源\棉花娃娃\基础角色-测试")
OUT_DIR = Path(__file__).resolve().parent / "generated_parts" / "six_view_manual_mask_drafts_1280x736"
CANVAS = (1280, 736)
VIEWS = {
    "front": "正面图层.png",
    "back": "背面图层.png",
    "right_front_3q": "右前¾侧图层.png",
    "right_back_3q": "右后¾侧图层.png",
    "left_front_3q": "左前¾侧图层.png",
    "left_back_3q": "左后¾侧图层.png",
}

# Approximate part masks in normalized coordinates within each view's alpha bounds.
# These are editable human-authored drafts, not semantic segmentation results.
MASKS = {
    "front": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.42),(0.87,0.49),(0.73,0.53),(0.30,0.53),(0.14,0.49),(0.00,0.43)],
        "arm_l": [(0.16,0.49),(0.37,0.51),(0.35,0.62),(0.31,0.72),(0.23,0.76),(0.13,0.70),(0.10,0.60)],
        "arm_r": [(0.63,0.51),(0.84,0.49),(0.90,0.60),(0.87,0.70),(0.77,0.76),(0.69,0.72),(0.65,0.62)],
        "leg_l": [(0.23,0.69),(0.49,0.71),(0.51,0.78),(0.50,0.92),(0.47,1.00),(0.28,1.00),(0.23,0.94)],
        "leg_r": [(0.51,0.71),(0.77,0.69),(0.77,0.94),(0.72,1.00),(0.53,1.00),(0.50,0.92)],
        "body": [(0.25,0.48),(0.75,0.48),(0.78,0.70),(0.77,0.82),(0.70,0.86),(0.30,0.86),(0.23,0.82),(0.22,0.70)],
    },
    "back": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.43),(0.86,0.51),(0.72,0.55),(0.28,0.55),(0.13,0.50),(0.00,0.43)],
        "arm_l": [(0.15,0.49),(0.37,0.53),(0.34,0.65),(0.30,0.75),(0.20,0.78),(0.11,0.71),(0.10,0.60)],
        "arm_r": [(0.63,0.53),(0.85,0.49),(0.90,0.60),(0.89,0.71),(0.80,0.78),(0.70,0.75),(0.66,0.65)],
        "leg_l": [(0.24,0.70),(0.49,0.72),(0.51,0.80),(0.50,0.93),(0.47,1.00),(0.28,1.00),(0.23,0.94)],
        "leg_r": [(0.51,0.72),(0.76,0.70),(0.77,0.94),(0.72,1.00),(0.53,1.00),(0.50,0.93)],
        "body": [(0.26,0.50),(0.74,0.50),(0.78,0.72),(0.77,0.83),(0.70,0.87),(0.30,0.87),(0.23,0.83),(0.22,0.72)],
    },
    "right_front_3q": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.42),(0.87,0.49),(0.72,0.53),(0.31,0.54),(0.14,0.49),(0.00,0.43)],
        "arm_l": [(0.15,0.49),(0.37,0.52),(0.35,0.64),(0.30,0.75),(0.21,0.78),(0.11,0.70),(0.09,0.59)],
        "arm_r": [(0.64,0.51),(0.85,0.48),(0.91,0.59),(0.88,0.70),(0.79,0.77),(0.70,0.73),(0.66,0.63)],
        "leg_l": [(0.24,0.70),(0.50,0.72),(0.52,0.80),(0.50,0.94),(0.46,1.00),(0.28,1.00),(0.22,0.93)],
        "leg_r": [(0.50,0.72),(0.77,0.68),(0.78,0.93),(0.73,1.00),(0.53,1.00),(0.50,0.92)],
        "body": [(0.25,0.49),(0.75,0.49),(0.79,0.70),(0.77,0.83),(0.69,0.87),(0.30,0.86),(0.22,0.82),(0.22,0.70)],
    },
    "right_back_3q": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.44),(0.87,0.52),(0.72,0.56),(0.28,0.55),(0.13,0.50),(0.00,0.43)],
        "arm_l": [(0.14,0.50),(0.37,0.53),(0.34,0.65),(0.30,0.75),(0.20,0.78),(0.10,0.71),(0.09,0.60)],
        "arm_r": [(0.64,0.53),(0.86,0.49),(0.91,0.60),(0.89,0.71),(0.80,0.78),(0.70,0.75),(0.66,0.64)],
        "leg_l": [(0.23,0.71),(0.49,0.73),(0.51,0.81),(0.50,0.94),(0.47,1.00),(0.28,1.00),(0.22,0.94)],
        "leg_r": [(0.51,0.72),(0.77,0.69),(0.78,0.94),(0.73,1.00),(0.53,1.00),(0.50,0.93)],
        "body": [(0.25,0.50),(0.75,0.50),(0.79,0.72),(0.77,0.84),(0.69,0.87),(0.30,0.87),(0.22,0.83),(0.21,0.71)],
    },
    "left_front_3q": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.43),(0.86,0.50),(0.70,0.54),(0.30,0.54),(0.14,0.49),(0.00,0.42)],
        "arm_l": [(0.14,0.48),(0.37,0.51),(0.35,0.63),(0.30,0.74),(0.20,0.78),(0.10,0.70),(0.09,0.59)],
        "arm_r": [(0.63,0.52),(0.85,0.49),(0.91,0.60),(0.88,0.71),(0.79,0.78),(0.70,0.73),(0.66,0.64)],
        "leg_l": [(0.23,0.70),(0.49,0.72),(0.51,0.80),(0.50,0.94),(0.47,1.00),(0.28,1.00),(0.22,0.93)],
        "leg_r": [(0.51,0.71),(0.77,0.69),(0.78,0.94),(0.73,1.00),(0.53,1.00),(0.50,0.92)],
        "body": [(0.25,0.49),(0.75,0.49),(0.78,0.70),(0.77,0.83),(0.70,0.87),(0.30,0.86),(0.22,0.82),(0.22,0.70)],
    },
    "left_back_3q": {
        "head": [(0.00,0.00),(1.00,0.00),(1.00,0.43),(0.87,0.51),(0.72,0.55),(0.28,0.55),(0.13,0.50),(0.00,0.43)],
        "arm_l": [(0.14,0.50),(0.37,0.53),(0.34,0.65),(0.30,0.75),(0.20,0.78),(0.10,0.71),(0.09,0.60)],
        "arm_r": [(0.64,0.53),(0.85,0.49),(0.91,0.60),(0.89,0.71),(0.80,0.78),(0.70,0.75),(0.66,0.64)],
        "leg_l": [(0.23,0.71),(0.49,0.73),(0.51,0.81),(0.50,0.94),(0.47,1.00),(0.28,1.00),(0.22,0.94)],
        "leg_r": [(0.51,0.72),(0.77,0.69),(0.78,0.94),(0.73,1.00),(0.53,1.00),(0.50,0.93)],
        "body": [(0.25,0.50),(0.75,0.50),(0.79,0.72),(0.77,0.84),(0.69,0.87),(0.30,0.87),(0.22,0.83),(0.21,0.71)],
    },
}
DRAW_ORDER = ["leg_l", "leg_r", "body", "arm_l", "arm_r", "head"]


def make_mask(size: tuple[int, int], bbox: tuple[int, int, int, int], points: list[tuple[float, float]]) -> Image.Image:
    x0, y0, x1, y1 = bbox
    local = Image.new("L", (1024, 1024), 0)
    pts = [(round(x * 1024), round(y * 1024)) for x, y in points]
    ImageDraw.Draw(local).polygon(pts, fill=255)
    local = local.filter(ImageFilter.GaussianBlur(0.5))
    fitted = local.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    mask.paste(fitted, (x0, y0))
    return mask


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {}
    contact = Image.new("RGBA", (1920, 736), (28, 31, 35, 255))
    parts_sheet = Image.new("RGBA", (6 * 240, 6 * 160), (28, 31, 35, 255))
    part_labels = ["head", "body", "arm_l", "arm_r", "leg_l", "leg_r"]
    for idx, (view, filename) in enumerate(VIEWS.items()):
        source = Image.open(SOURCE_DIR / filename).convert("RGBA")
        if source.size != CANVAS:
            raise ValueError(f"{filename}: expected {CANVAS}, got {source.size}")
        bbox = source.getchannel("A").getbbox()
        alpha = source.getchannel("A")
        layers = {}
        masks = MASKS[view]
        for part, points in masks.items():
            region = make_mask(CANVAS, bbox, points)
            region = ImageChops.multiply(region, alpha)
            layer = source.copy()
            layer.putalpha(region)
            layer.save(OUT_DIR / f"{view}_{part}.png")
            layers[part] = layer
            part_tile = Image.new("RGBA", (240, 160), (28, 31, 35, 255))
            part_crop = layer.crop(bbox)
            part_crop.thumbnail((220, 128), Image.Resampling.LANCZOS)
            part_tile.alpha_composite(part_crop, ((240 - part_crop.width) // 2, 25 + (128 - part_crop.height) // 2))
            ImageDraw.Draw(part_tile).text((8, 6), f"{view} / {part}", fill=(240, 242, 244, 255))
            col = part_labels.index(part)
            row = idx
            parts_sheet.alpha_composite(part_tile, (col * 240, row * 160))

        union = Image.new("L", CANVAS, 0)
        for layer in layers.values():
            union = ImageChops.lighter(union, layer.getchannel("A"))
        missing_mask = ImageChops.subtract(alpha, union)
        missing = sum(v > 16 for v in missing_mask.tobytes())
        recovered = 0
        if missing:
            extra = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
            extra.paste(source, (0, 0), missing_mask)
            layers["body"] = Image.alpha_composite(layers["body"], extra)
            layers["body"].save(OUT_DIR / f"{view}_body.png")
            recovered = missing

        assembled = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        for part in DRAW_ORDER:
            assembled.alpha_composite(layers[part])
        assembled.save(OUT_DIR / f"{view}_assembly_draft.png")

        crop = assembled.crop(bbox)
        tile = Image.new("RGBA", (640, 368), (28, 31, 35, 255))
        fitted = crop.thumbnail((340, 330), Image.Resampling.LANCZOS)
        # thumbnail mutates crop; center it without changing the source-space layers.
        tile.alpha_composite(crop, ((640 - crop.width) // 2, (368 - crop.height) // 2 + 14))
        ImageDraw.Draw(tile).text((12, 8), view, fill=(240, 242, 244, 255))
        contact.alpha_composite(tile, ((idx % 3) * 640, (idx // 3) * 368))
        report[view] = {
            "source": filename,
            "canvas": list(CANVAS),
            "alphaBounds": list(bbox),
            "opaqueSourcePixels": sum(v > 16 for v in alpha.tobytes()),
            "uncoveredSourcePixelsBeforeFallback": missing,
            "pixelsAssignedToBodyFallback": recovered,
            "coverage": 1.0,
            "status": "manual_mask_estimate_requires_visual_review",
            "parts": [f"{view}_{part}.png" for part in masks],
            "knownLimitations": ["Seams are approximate normalized polygons, not traced contours.", "The source contains no hidden pixels behind overlapping limbs/head; inpainting remains separate.", "Do not claim production-ready binding until pivot and movement tests pass."],
        }

    contact.save(OUT_DIR / "six_view_manual_mask_contact_sheet.png")
    parts_sheet.save(OUT_DIR / "six_view_parts_review_sheet.png")
    (OUT_DIR / "segmentation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote review drafts: {OUT_DIR}")


if __name__ == "__main__":
    main()
