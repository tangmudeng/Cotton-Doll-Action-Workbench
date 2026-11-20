"""Source-pixel-preserving overlap rework, NOT video motion fitting.
Uses a previously generated Image2 sheet only as a texture donor inside hidden
joint bands. Never executes legacy animation generation or changes old assets.
"""
from pathlib import Path
import hashlib
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw

from generate_right_front_walk_rig import extract_layers, PART_ORDER, PART_META

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'generated_rig' / 'video_f7e82942'
OUT = BASE / 'image2_repairs' / 'rework_v3'
SOURCE = ROOT / 'generated_rig' / 'right_front_walk' / 'source768.png'
DONOR = BASE / 'image2_repairs' / 'repair_sheet_v1.png'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert OUT.parent.is_dir()
    OUT.mkdir(exist_ok=True)
    source = np.array(Image.open(SOURCE).convert('RGBA'))
    assert source.shape == (768, 768, 4)
    assert sha(SOURCE) == 'a25475d82eec03a42ae89a32026779ab99eb0e32f2a0232ade7302ca844a3a10'
    assert sha(DONOR) == '435b8412ba58fd05432125be4d41767dc16eb6575076657dab7712e6e42bf599'
    # Reuse ONLY archival visible-pixel ownership as a provisional baseline.
    # No old walk timelines, procedural fill, rig or runtime data is consumed.
    originals, _, _, _ = extract_layers(source)
    donor = np.array(Image.open(DONOR).convert('RGBA'))
    roi = donor[115:215, 245:365]
    valid = roi[:, :, 3] > 240
    if valid.sum() < 100:
        raise ValueError('Insufficient opaque donor texture')
    donor_median = np.median(roi[valid, :3], axis=0)
    # Filling transparent fringe in this texture swatch is procedural sampling,
    # not an additional AI generation. Geometry comes from constrained masks.
    texture = roi[:, :, :3].copy()
    texture[~valid] = donor_median.astype(np.uint8)
    tiles = np.tile(texture, (9, 7, 1))[:768, :768].astype(float)
    yy, xx = np.indices((768, 768))
    masks, layers, parts = {}, {}, []
    selected = {'body': (390, 490, 100, 85), 'arm_near': (351, 461, 30, 30),
                'arm_far': (461, 467, 24, 28), 'leg_near': (359, 578, 37, 38),
                'leg_far': (437, 577, 34, 35)}
    occlusion = np.zeros((768, 768), bool)
    for name in reversed(PART_ORDER):
        original = originals[name]
        known = original[:, :, 3] > 0
        mask = np.zeros_like(known)
        if name in selected:
            cx, cy, rx, ry = selected[name]
            zone = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1
            distance = cv2.distanceTransform((~known).astype(np.uint8), cv2.DIST_L2, 5)
            # Deliberately local. This does not reconstruct the entire hidden limb.
            radius = 30 if name == 'body' else 20
            safely_hidden = cv2.erode(occlusion.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            mask = zone & (distance <= radius) & ~known & safely_hidden
        repaired = original.copy()
        if mask.any():
            local = known & (np.abs(xx - selected[name][0]) < 70) & (np.abs(yy - selected[name][1]) < 85) & (original[:, :, 3] > 240)
            if not local.any():
                local = known & (original[:, :, 3] > 240)
            target = np.median(original[local, :3], axis=0)
            matched = np.clip(tiles - donor_median + target, 0, 255).astype(np.uint8)
            repaired[mask, :3] = matched[mask]
            repaired[mask, 3] = 255
        layers[name] = repaired
        masks[name] = mask
        occlusion |= original[:, :, 3] == 255
    assembly = Image.new('RGBA', (768, 768))
    for name in PART_ORDER:
        assembly.alpha_composite(Image.fromarray(layers[name]))
    assembled = np.array(assembly)
    source_visible = source[:, :, 3] > 0
    delta = np.abs(assembled.astype(int) - source.astype(int))
    foreground_exact = bool(np.array_equal(assembled[source_visible], source[source_visible]))
    checks = {
        'sourceDimensions768': True,
        'visibleSourcePixelsUnchangedPerPart': all(bool(np.array_equal(layers[n][originals[n][:, :, 3] > 0], originals[n][originals[n][:, :, 3] > 0])) for n in PART_ORDER),
        'staticForegroundRGBAExact': foreground_exact,
        'noNewOutsideSourcePixels': bool(np.all(assembled[~source_visible, 3] == 0)),
        'allFiveJointRegionsHaveAddedPixels': all(bool(masks[n].any()) for n in selected),
        'headUnmodified': bool(np.array_equal(layers['head'], originals['head'])),
    }
    for name in PART_ORDER:
        layer = Image.fromarray(layers[name])
        bbox = layer.getchannel('A').getbbox()
        layer.crop(bbox).save(OUT / (name + '.png'))
        Image.fromarray((masks[name] * 255).astype(np.uint8)).save(OUT / (name + '_repair_mask.png'))
        parts.append({'id': name, 'file': name + '.png', 'repairMask': name + '_repair_mask.png',
                      'bbox': list(bbox), 'pivotSourcePixels': list(PART_META[name]['pivot']),
                      'addedPixels': int(masks[name].sum()), 'sourceVisiblePixelCount': int((originals[name][:, :, 3] > 0).sum()),
                      'geometryStatus': 'archival_visible_partition_provisional_not_video_redissection',
                      'status': 'local_overlap_candidate_dynamic_untested'})
    assembly.save(OUT / 'assembly.png')
    # Explicit source/assembly/mask views, same positions and same scale.
    preview = Image.new('RGB', (1152, 460), '#f1f0ec')
    draw = ImageDraw.Draw(preview)
    union = np.logical_or.reduce(list(masks.values()))
    overlay = Image.fromarray(source)
    tint = np.zeros_like(source); tint[union] = (210, 55, 190, 210)
    overlay.alpha_composite(Image.fromarray(tint))
    for col, (label, im) in enumerate([('Source PNG', Image.fromarray(source)), ('Rework: static assembly', assembly), ('Magenta: added hidden pixels', overlay)]):
        im = im.resize((384, 384), Image.Resampling.LANCZOS)
        preview.paste(im, (col * 384, 30), im)
        draw.text((col * 384 + 12, 10), label, fill='#292c30')
    draw.text((12, 425), 'Static only. Original visible pixels preserved. No fitted animation / no complete hidden-limb reconstruction.', fill='#292c30')
    preview.save(OUT / 'assembly_review.jpg', quality=95)
    sheet = Image.new('RGB', (1200, 500), '#f1f0ec')
    draw = ImageDraw.Draw(sheet)
    for i, part in enumerate(parts):
        im = Image.open(OUT / part['file']).convert('RGBA')
        im.thumbnail((180, 390), Image.Resampling.LANCZOS)
        x = i * 200 + (200 - im.width) // 2
        sheet.paste(im, (x, 45), im)
        draw.text((i * 200 + 8, 12), part['id'], fill='#292c30')
        draw.text((i * 200 + 8, 445), 'added: ' + str(part['addedPixels']) + 'px', fill='#292c30')
    sheet.save(OUT / 'parts_review.jpg', quality=95)
    report = {
        'version': 3, 'taskId': 'comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa', 'characterId': None,
        'status': 'local_overlap_candidate_not_motion_ready', 'sourceFile': '../../right_front_walk/source768.png',
        'sourceSha256': sha(SOURCE), 'donorFile': '../repair_sheet_v1.png', 'donorSha256': sha(DONOR),
        'method': 'Original visible pixels + locally color-matched existing Image2 texture donor in hidden overlap masks. No new generation. Geometry constrained by joint neighborhood and eroded opaque higher-layer masks.',
        'legacyReuse': 'Visible-pixel ownership masks and provisional pivots ONLY; no old animation/runtime/procedural texture fills.',
        'videoEvidence': {'file': '../../frames/frame_008.jpg', 'sourceFrameIndex': 8, 'role': 'Shows chest-crossing arm and separated feet; establishes limitations/need, not fitted coordinates or generated new pose'},
        'parts': parts, 'checks': checks, 'allChecksPassed': all(checks.values()),
        'staticForegroundMaxRGBADelta': int(delta[source_visible].max()),
        'assembly': 'assembly.png', 'assemblyReview': 'assembly_review.jpg', 'partsReview': 'parts_review.jpg',
        'resolved': ['Original visible design, proportions, and contours are not redrawn', 'No generated frontal torso replaces master right-front view', 'Hidden local overlaps no longer rely on generated open cross-section caps'],
        'unresolved': ['Visible partition still inherited from archival static draft; not a new video-driven dissection', 'Complete hidden shoulder/upper-thigh structure not recovered', 'Chest-crossing near arm shape from frame 8 not supplied', 'Leg perspective and draw-order transitions require video-driven fitting', 'Near/far anatomy remains provisional', 'No dynamic gap/silhouette acceptance', 'No mesh, weights, IK, fitted walk or Spine runtime export'],
        'promotedToRuntime': False,
    }
    # Source paths relative to OUT, not the earlier review directory.
    report['sourceFile'] = '../../../right_front_walk/source768.png'
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'checks': checks, 'addedPixels': {n: int(m.sum()) for n, m in masks.items()}, 'maxForegroundDelta': report['staticForegroundMaxRGBADelta']}, ensure_ascii=False))
    if not all(checks.values()):
        raise RuntimeError('Rework checks failed')


if __name__ == '__main__':
    main()
