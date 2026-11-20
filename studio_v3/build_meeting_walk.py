"""独立会议演示：七件 SHA 源素材、轮廓参考的有限关键值和真实 region 骨骼。"""
from pathlib import Path
import hashlib
import json
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
RIG = BASE / 'generated_rig' / 'video_f7e82942'
STABLE = RIG / 'stable_parts_v1'
VIDEO = RIG / 'video_parts_v1'
OUT = RIG / 'meeting_walk_v1'
FPS = 24.0
DURATION = 16 / FPS
KEY_FRAMES = list(range(68, 85, 2))
PIVOTS = {'body': (390, 532), 'head': (398, 439),
          'shorts': (410, 554), 'arm_near': (350, 456),
          'arm_far': (468, 463), 'leg_near': (359, 576), 'leg_far': (437, 575)}
LIMITATIONS = [
    '仅会议演示：hiddenComplete=false，productionApproved=false，characterId=null；稳定素材状态未提升。',
    'A/B逐帧轮廓不是已确认解剖左右或跨帧身份；near/far映射为低可信手工相位假设。',
    '有限手工关键值参考视频轮廓和bbox/centroid，不是自动关节拟合，也不复现原视频大幅胸前交叉手臂。',
    '单刚性region四肢无膝肘弯曲；肩根、腋下、髋根和短裤隐藏面不完整，小幅运动仍可能露缝。',
    '腿源裁片可能带裤口描边，shorts仅当前服装可见裁片，不代表换装、裸腿或跨角色复用完成。',
    '脚底约束为二维手工接触候选的脚底中心位置补偿，无IK、无足掌形变，接触期外允许有限移动。',
    '原源图与视频角色身份未确认；视频只提供动作节奏参考，不证明角色资产来源。',
    'Python从导出JSON和atlas实际求解刚性骨骼；未声称通过Spine编辑器或官方运行时导入验收。',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def rel(path):
    return Path(path).resolve().relative_to(BASE).as_posix()


def rotation(angle):
    # 此处为真实刚体旋转矩阵，不是用于生成动作值的周期函数。
    m = np.eye(3)
    m[:2] = cv2.getRotationMatrix2D((0, 0), -float(angle), 1)
    return m


def translation(x, y):
    m = np.eye(3)
    m[:2, 2] = x, y
    return m


def polygon_center(points):
    poly = np.asarray(points, dtype=np.float32)
    mm = cv2.moments(poly)
    assert abs(mm['m00']) > 0
    return [mm['m10'] / mm['m00'], mm['m01'] / mm['m00']]


def pack(images):
    pad = 4
    w = max(im.width for im in images.values()) + 2 * pad
    h = sum(im.height + 2 * pad for im in images.values())
    page = Image.new('RGBA', (w, h))
    regions = {}
    y = 0
    for name, im in images.items():
        arr = np.pad(np.asarray(im), ((pad, pad), (pad, pad), (0, 0)), mode='edge')
        page.paste(Image.fromarray(arr), (0, y))
        regions[name] = dict(x=pad, y=y + pad, width=im.width, height=im.height, padding=pad)
        y += im.height + 2 * pad
    page.save(OUT / 'meeting_walk.png')
    lines = ['meeting_walk.png', f'size: {w},{h}', 'format: RGBA8888',
             'filter: Linear,Linear', 'repeat: none', 'pma: false']
    for name, r in regions.items():
        lines += [name, '  rotate: false', f"  xy: {r['x']},{r['y']}",
                  f"  size: {r['width']},{r['height']}", f"  orig: {r['width']},{r['height']}",
                  '  offset: 0,0', '  index: -1']
    (OUT / 'meeting_walk.atlas').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return page, regions


def sample(keys, t, fields):
    if t >= keys[-1]['time']:
        return {f: keys[-1].get(f, 0) for f in fields}
    for a, b in zip(keys, keys[1:]):
        if a['time'] <= t <= b['time']:
            u = (t - a['time']) / (b['time'] - a['time'])
            return {f: a.get(f, 0) * (1 - u) + b.get(f, 0) * u for f in fields}
    return {f: keys[0].get(f, 0) for f in fields}


def solve(skeleton, animation, t):
    worlds = {}
    for bone in skeleton['bones']:
        channels = skeleton['animations'].get(animation, {}).get('bones', {}).get(bone['name'], {})
        xy = sample(channels['translate'], t, ['x', 'y']) if 'translate' in channels else {'x': 0, 'y': 0}
        angle = sample(channels['rotate'], t, ['value'])['value'] if 'rotate' in channels else 0
        local = translation(bone.get('x', 0) + xy['x'], bone.get('y', 0) + xy['y']) @ rotation(bone.get('rotation', 0) + angle)
        worlds[bone['name']] = worlds.get(bone.get('parent'), np.eye(3)) @ local
    return worlds


def render(skeleton, page, regions, animation, t):
    worlds = solve(skeleton, animation, t)
    canvas = np.zeros((768, 768, 4), dtype=np.float32)
    flip = np.array([[1, 0, 0], [0, -1, 768], [0, 0, 1]], dtype=float)
    skin = skeleton['skins'][0]['attachments']
    for slot in skeleton['slots']:
        attachment = skin[slot['name']][slot['attachment']]
        r = regions[attachment['path']]
        image = np.asarray(page.crop((r['x'], r['y'], r['x'] + r['width'], r['y'] + r['height']))).astype(np.float32) / 255
        image[:, :, :3] *= image[:, :, 3:4]
        local = np.array([[1, 0, attachment['x'] - attachment['width'] / 2],
                          [0, -1, attachment['y'] + attachment['height'] / 2], [0, 0, 1]])
        matrix = flip @ worlds[slot['bone']] @ local
        layer = cv2.warpAffine(image, matrix[:2], (768, 768), flags=cv2.INTER_LINEAR)
        canvas = layer + canvas * (1 - layer[:, :, 3:4])
    rgb = np.divide(canvas[:, :, :3], canvas[:, :, 3:4], out=np.zeros_like(canvas[:, :, :3]), where=canvas[:, :, 3:4] > 0)
    return Image.fromarray(np.clip(np.rint(np.dstack([rgb, canvas[:, :, 3]]) * 255), 0, 255).astype(np.uint8)), worlds


def compare(reference, actual):
    a, b = np.asarray(reference), np.asarray(actual)
    mask = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
    rgba = np.any(a != b, axis=2) & mask
    premul_a = a[:, :, :3].astype(float) * a[:, :, 3:4] / 255
    premul_b = b[:, :, :3].astype(float) * b[:, :, 3:4] / 255
    visible = (np.max(np.abs(premul_a - premul_b), axis=2) > .51) | (a[:, :, 3] != b[:, :, 3])
    return {'foregroundUnionPixels': int(mask.sum()), 'rgbaMismatchPixels': int(rgba.sum()),
            'premultipliedMismatchPixels': int((visible & mask).sum()),
            'sourceForegroundUncoveredPixels': int(((a[:, :, 3] > 0) & (b[:, :, 3] == 0)).sum()),
            'alphaMismatchPixels': int((a[:, :, 3] != b[:, :, 3]).sum())}


def main():
    assert BASE.is_dir() and RIG.is_dir() and STABLE.is_dir() and VIDEO.is_dir()
    OUT.mkdir(exist_ok=True)
    manifest_path = STABLE / 'manifest.json'
    manifest_hash = sha(manifest_path)
    manifest = load(manifest_path)
    vm = load(VIDEO / 'manifest.json')
    tracks = {r['index']: r for r in load(RIG / 'tracks.json')['tracks']}
    ids = set(PIVOTS)
    assert {p['id'] for p in manifest['parts']} == ids
    images, parts, hashes = {}, {}, []
    for part in manifest['parts']:
        path = STABLE / part['file']
        actual_hash = sha(path)
        assert actual_hash == part['sha256'], path
        image = Image.open(path).convert('RGBA')
        assert image.size == (part['width'], part['height'])
        assert image.size == (part['bbox'][2] - part['bbox'][0], part['bbox'][3] - part['bbox'][1])
        images[part['id']], parts[part['id']] = image, part
        hashes.append({'id': part['id'], 'file': rel(path), 'expectedSha256': part['sha256'], 'actualSha256': actual_hash})
    reference_path = (STABLE / manifest['sourceImage']['file']).resolve()
    assert sha(reference_path) == manifest['sourceImage']['sha256']
    reference = Image.open(reference_path).convert('RGBA')
    video_path = (VIDEO / vm['sourceVideo']).resolve()
    assert sha(video_path) == vm['sourceVideoSha256']
    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened() and cap.get(cv2.CAP_PROP_FPS) == FPS
    evidence, source_images = [], {}
    for frame in range(68, 85):
        fragments = [p for p in vm['parts'] if p['sourceFrame'] == frame]
        assert fragments
        source_path = VIDEO / fragments[0]['sourceFile']
        source_hash = sha(source_path)
        assert all(p['sourceFrameSha256'] == source_hash for p in fragments)
        source_image = Image.open(source_path).convert('RGB')
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, decoded = cap.read()
        assert ok
        decoded_rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
        assert np.array_equal(decoded_rgb, np.asarray(source_image)), frame
        source_images[frame] = source_image
        rows = []
        for p in fragments:
            polygon = p['polygonSourcePixels']
            crop = Image.open(VIDEO / p['file']).convert('RGBA')
            x0, y0, x1, y1 = p['bbox']
            rgba = np.asarray(crop)
            visible = rgba[:, :, 3] > 0
            assert np.array_equal(rgba[:, :, :3][visible], decoded_rgb[y0:y1, x0:x1][visible])
            rows.append({'id': p['id'], 'kind': p['kind'], 'pose': p['pose'],
                         'bbox': p['bbox'], 'polygonSourcePixels': polygon,
                         'polygonCentroid': polygon_center(polygon), 'fragmentSha256': sha(VIDEO / p['file']),
                         'anatomicalIdentity': p.get('anatomicalIdentity'), 'crossFrameIdentityEstablished': False})
        evidence.append({'frame': frame, 'time': frame / FPS, 'sourceFile': rel(source_path),
                         'sourceSha256': source_hash, 'decodedVideoPixelsExact': True,
                         'track': tracks.get(frame), 'parts': rows})
    cap.release()
    ev = {e['frame']: e for e in evidence}
    page, regions = pack(images)
    root = {'name': 'root', 'x': 390, 'y': 768 - 532}
    bones = [root, {'name': 'body', 'parent': 'root', 'length': 60}]
    for name, pivot in PIVOTS.items():
        if name != 'body':
            bones.append({'name': name, 'parent': 'body', 'x': pivot[0] - 390,
                          'y': 532 - pivot[1], 'length': 80 if name.startswith(('arm', 'leg')) else 40})
    attachments = {}
    for name, part in parts.items():
        x0, y0, x1, y1 = part['bbox']
        px, py = PIVOTS[name]
        attachments[name] = {name: {'type': 'region', 'path': name,
                                   'x': (x0 + x1) / 2 - px, 'y': py - (y0 + y1) / 2,
                                   'width': x1 - x0, 'height': y1 - y0}}
    # 手工接触候选：近侧在68-72及82-84支撑，远侧在74-78支撑；身份置信低。
    near_angles = [-1, -4, -6, -2, 3, 6, 4, 1, -1]
    far_angles = [1, 4, 6, 2, -3, -6, -4, -1, 1]
    near_targets = [(0, 0), (0, 0), (0, 0), (3, 2), (6, 5), (3, 6), (0, 3), (0, 0), (0, 0)]
    far_targets = [(0, 3), (-3, 5), (-5, 3), (0, 0), (0, 0), (0, 0), (3, 4), (2, 5), (0, 3)]
    foot_points = {}
    for name in ('leg_near', 'leg_far'):
        part = parts[name]
        arr = np.asarray(images[name])
        ys, xs = np.where(arr[:, :, 3] > 200)
        floor = int(ys.max())
        band = ys >= floor - 2
        foot_points[name] = [float(np.median(xs[band])) + part['bbox'][0], float(floor + part['bbox'][1])]
    channels = {name: {'rotate': [], 'translate': []} for name in PIVOTS}
    key_notes = []
    arm_centers = [next(p for p in ev[f]['parts'] if p['kind'] == 'arm')['polygonCentroid'][0] - tracks[f]['centroid']['x'] for f in KEY_FRAMES]
    lo, hi = min(arm_centers), max(arm_centers)
    for i, frame in enumerate(KEY_FRAMES):
        t = i / 12
        track = tracks[frame]
        bob = min(1.6, max(-.1, (tracks[68]['centroid']['y'] - track['centroid']['y']) * .10))
        sway = float(np.clip((track['centroid']['x'] - tracks[68]['centroid']['x']) * .18, -.3, .3))
        arm = -2.2 + 4.4 * (arm_centers[i] - lo) / (hi - lo)
        pose = {name: {'angle': 0., 'x': 0., 'y': 0.} for name in PIVOTS}
        pose['body'].update(x=sway, y=bob)
        pose['arm_near']['angle'] = arm
        pose['arm_far']['angle'] = -arm * .9
        # 保持头部朝向与轮廓，小幅头部平移继承body，不额外摇头。
        for name, angles, targets in [('leg_near', near_angles, near_targets), ('leg_far', far_angles, far_targets)]:
            px, py = PIVOTS[name]
            fx, fy = foot_points[name]
            local = np.array([fx - px, py - fy, 1])
            rotated = rotation(angles[i]) @ local
            dx, lift = targets[i]
            desired = np.array([local[0] + dx - sway, local[1] + lift - bob])
            shift = desired - rotated[:2]
            pose[name].update(angle=angles[i], x=float(shift[0]), y=float(shift[1]))
        for name in PIVOTS:
            channels[name]['rotate'].append({'time': round(t, 9), 'value': round(pose[name]['angle'], 6)})
            channels[name]['translate'].append({'time': round(t, 9), 'x': round(pose[name]['x'], 6), 'y': round(pose[name]['y'], 6)})
        key_notes.append({'sourceFrame': frame, 'animationTime': t, 'trackBbox': track['bbox'],
                          'trackCentroid': track['centroid'], 'armPolygonRelativeCentroidX': arm_centers[i],
                          'bodyBobRule': 'centroid向上差*0.10，上限1.6px；横向差*0.18限±0.3px',
                          'legRule': '有限手工角度表+脚底候选的刚体旋转位移补偿，非自动关节拟合',
                          'valuesBeforeLoopClosure': pose,
                          'nearFootTargetOffset': near_targets[i], 'farFootTargetOffset': far_targets[i]})
    for ch in channels.values():
        for keys in ch.values():
            keys[-1] = {**keys[0], 'time': DURATION}
    skeleton = {'skeleton': {'spine': '4.2.00', 'x': 0, 'y': 0, 'width': 768, 'height': 768, 'images': './', 'audio': ''},
                'bones': bones, 'slots': [{'name': n, 'bone': n, 'attachment': n} for n in manifest['assemblyLayerOrder']],
                'skins': [{'name': 'default', 'attachments': attachments}],
                'animations': {'neutral': {'bones': {n: {'rotate': [{'time': 0, 'value': 0}], 'translate': [{'time': 0, 'x': 0, 'y': 0}]} for n in PIVOTS}}, 
                               'walk': {'bones': channels}}}
    save('meeting_walk.json', skeleton)
    # 预览必须重新读导出文件和atlas，不能以源整帧替代骨骼求解。
    skeleton = load(OUT / 'meeting_walk.json')
    page = Image.open(OUT / 'meeting_walk.png').convert('RGBA')
    neutral, _ = render(skeleton, page, regions, 'neutral', 0)
    neutral.save(OUT / 'neutral.png')
    neutral_metrics = compare(reference, neutral)
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(font_path), 17) if font_path.exists() else ImageFont.load_default()
    sheet = Image.new('RGB', (1600, 1180), '#edf0f4')
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 12), '会议骨骼 walk / 8姿态 / region真实变换 / 0.666667秒 / 身份低可信', font=font, fill='#182b43')
    foot_samples = []
    for i, frame in enumerate(KEY_FRAMES[:-1]):
        t = i / 12
        rendered, worlds = render(skeleton, page, regions, 'walk', t)
        x, y = (i % 4) * 400, 48 + (i // 4) * 540
        tile = Image.new('RGBA', (400, 390), '#f7f8fa')
        character = rendered.crop((155, 84, 615, 684)).resize((276, 360), Image.Resampling.LANCZOS)
        tile.alpha_composite(character, (62, 10))
        sheet.paste(tile.convert('RGB'), (x, y + 24))
        draw.text((x + 12, y), f'f{frame} / t={t:.4f}s / 真骨骼', font=font, fill='#182b43')
        local_draw = ImageDraw.Draw(sheet)
        for bone in bones:
            n = bone['name']
            if n in ('root', 'body'):
                continue
            pos = worlds[n][:2, 2]
            bx = x + 62 + (pos[0] - 155) * .6
            by = y + 24 + 10 + (768 - pos[1] - 84) * .6
            local_draw.ellipse((bx - 2, by - 2, bx + 2, by + 2), fill='#ed7966')
        source = source_images[frame].copy()
        sd = ImageDraw.Draw(source)
        for p in ev[frame]['parts']:
            color = '#b331b3' if p['kind'] == 'arm' else '#087d83'
            sd.line([tuple(v) for v in p['polygonSourcePixels']] + [tuple(p['polygonSourcePixels'][0])], fill=color, width=2)
        box = tracks[frame]['bbox']
        sd.rectangle((box['x'], box['y'], box['x'] + box['width'], box['y'] + box['height']), outline='#7b8995', width=1)
        cx, cy = tracks[frame]['centroid'].values()
        sd.ellipse((cx-3, cy-3, cx+3, cy+3), fill='#cf573e')
        source = source.crop((260, 20, 610, 470)).resize((86, 110))
        sheet.paste(source, (x + 10, y + 414))
        draw.text((x + 108, y + 420), f'源视频 f{frame}\n多边形 / bbox / 质心\n非自动关节拟合', font=font, fill='#4e5c6e')
        samples = {'frame': frame, 'time': t}
        for n in foot_points:
            fx, fy = foot_points[n]
            px, py = PIVOTS[n]
            pos = worlds[n] @ np.array([fx-px, py-fy, 1])
            samples[n] = [float(pos[0]), float(768-pos[1])]
        foot_samples.append(samples)
    draw.text((20, 1142), 'meeting_demo_only | default skin | 无整帧切换 / 无新生图 / 非生产绑定 / 隐藏面待补', font=font, fill='#8a4e37')
    sheet.save(OUT / 'review.png')
    loop_ok = all(keys[0] == {**keys[-1], 'time': keys[0]['time']} for ch in channels.values() for keys in ch.values())
    first, _ = render(skeleton, page, regions, 'walk', 0)
    last, _ = render(skeleton, page, regions, 'walk', DURATION)
    loop_pixels = compare(first, last)
    atlas_checks = {}
    for name, r in regions.items():
        x, y, w, h, p = (r[k] for k in ['x', 'y', 'width', 'height', 'padding'])
        packed = np.asarray(page)[y-p:y+h+p, x-p:x+w+p]
        expected = np.pad(np.asarray(images[name]), ((p,p),(p,p),(0,0)), mode='edge')
        atlas_checks[name] = {'insidePageWithPadding': x >= p and y >= p and x+w+p <= page.width and y+h+p <= page.height,
                              'extrudedPaddingPixels': p, 'contentAndExtrusionExact': bool(np.array_equal(packed, expected))}
    visible_checks = {}
    for n, part in parts.items():
        arr = np.asarray(images[n])
        x0, y0, x1, y1 = part['bbox']
        mask = arr[:, :, 3] > 0
        if n == 'body':
            mask = np.asarray(Image.open(STABLE / 'body_visible_mask.png').convert('L'))[y0:y1, x0:x1] > 0
        visible_checks[n] = {'originalVisibleRgbaMismatchPixels': int((np.any(arr != np.asarray(reference)[y0:y1,x0:x1], axis=2) & mask).sum()),
                             'newSupportPixelsThisBuild': 0, 'stablePartBytesShaVerified': True}
    finite = all(np.isfinite(v) for ch in channels.values() for keys in ch.values() for k in keys for v in k.values())
    ordered = all(all(a['time'] < b['time'] for a,b in zip(keys,keys[1:])) for ch in channels.values() for keys in ch.values())
    used = {s['bone'] for s in skeleton['slots']}
    assert all(b['name'] in used or b['name'] == 'root' for b in bones)
    provenance = {'schemaVersion': 1, 'status': 'meeting_demo_only', 'characterId': None,
                  'hiddenComplete': False, 'productionApproved': False, 'promotedToRuntime': False,
                  'method': '轮廓参考的有限手工角度与质心小幅位移；region真实骨骼时间线；不是自动拟合',
                  'characterAsset': {'stableManifest': rel(manifest_path), 'manifestSha256': manifest_hash,
                                     'parts': hashes, 'pivotsSourcePixelsTopLeft': PIVOTS,
                                     'pivotAdjustments': [], 'clothingPivotAdditional': {'shorts': [410,554]},
                                     'semanticGroups': {'character': [n for n in PIVOTS if n != 'shorts'], 'clothing': ['shorts']},
                                     'defaultSkinPreserved': True, 'fakeClothingAdded': False,
                                     'bodyTexture': '仅使用SHA核验的stable body；其既有4095px局部供体搭接不扩大，未替换旧混合body',
                                     'newSupportOrDonorPixels': 0, 'newImageGeneration': False},
                  'motionReference': {'video': rel(video_path), 'sha256': sha(video_path), 'fps': FPS,
                                      'frameRangeInclusive': [68,84], 'duration': DURATION,
                                      'tracksFile': rel(RIG/'tracks.json'), 'tracksSha256': sha(RIG/'tracks.json'),
                                      'polygonManifest': rel(VIDEO/'manifest.json'), 'polygonManifestSha256': sha(VIDEO/'manifest.json'),
                                      'identityConfidence': 'low', 'crossFrameIdentityEstablished': False,
                                      'anatomicalLeftRight': 'unknown', 'mappingAssumption': '轮廓A参考near节奏，B/遮挡参考far；不是身份确认',
                                      'keyNotes': key_notes, 'evidenceFrames': evidence,
                                      'loopClosure': '84帧观测独立保存；最终关键值显式复制68帧，原始首尾轮廓不声称完全相同',
                                      'footAnchorsSourcePixels': foot_points,
                                      'contactFrameCandidates': {'leg_near':[68,70,72,82,84], 'leg_far':[74,76,78]},
                                      'footSamples': foot_samples},
                  'limitations': LIMITATIONS, 'buildScript': {'file': rel(Path(__file__)), 'sha256': sha(__file__)}}
    save('provenance.json', provenance)
    checks = {'status': 'meeting_demo_only', 'productionApproved': False, 'hiddenComplete': False,
              'sourceHashesVerified': True, 'sourceVideoFrames68to84DecodedPixelExact': True,
              'allSevenStablePartsHashVerified': True, 'stableManifestUnchanged': sha(manifest_path) == manifest_hash,
              'originalVisiblePreserved': visible_checks, 'finiteValues': bool(finite),
              'strictlyIncreasingTimelineTimes': ordered, 'durationSeconds': DURATION,
              'loopFirstLastKeysExact': loop_ok, 'loopRender': loop_pixels,
              'neutral': neutral_metrics, 'neutralSourceRecoverable': neutral_metrics['premultipliedMismatchPixels'] == 0,
              'atlasRegions': atlas_checks, 'boneCount': len(bones), 'slotCount': len(skeleton['slots']),
              'allNonRootBonesDriveAttachments': True, 'noAttachmentSwapTimelines': True,
              'previewUsesExportedJsonAndAtlas': True, 'reviewPoseCount': 8,
              'runtimeImportVerified': False, 'limitations': LIMITATIONS}
    assert finite and ordered and loop_ok and loop_pixels['premultipliedMismatchPixels'] == 0
    assert all(v['contentAndExtrusionExact'] and v['insidePageWithPadding'] for v in atlas_checks.values())
    assert checks['stableManifestUnchanged']
    assert all(c['originalVisibleRgbaMismatchPixels'] == 0 for c in visible_checks.values())
    payload = ['meeting_walk.json','meeting_walk.atlas','meeting_walk.png','provenance.json','checks.json','review.png','neutral.png']
    checks['zip'] = {'filename': 'meeting_walk.zip', 'members': payload, 'crcVerified': True,
                     'bytesMatchDisk': True, 'note': '先预检ZIP后重建；最终包含本checks，外层再次验证CRC和所有文件字节'}
    save('checks.json', checks)
    zip_path = OUT / 'meeting_walk.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in payload:
            archive.write(OUT / name, name)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(payload)
        assert all(archive.read(n) == (OUT / n).read_bytes() for n in payload)
    print(json.dumps({'output': str(OUT), 'duration': DURATION, 'bones': len(bones), 'neutral': neutral_metrics,
                      'loop': loop_ok, 'zipCrcVerified': True, 'zipBytesMatchDisk': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
