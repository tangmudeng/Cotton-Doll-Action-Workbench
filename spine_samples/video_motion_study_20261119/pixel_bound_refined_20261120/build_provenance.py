from pathlib import Path
import json,hashlib
r=Path.cwd();manifest=json.loads((r/'pixel_manifest.json').read_text());data=json.loads((r/'skin.json').read_text());provenance=[]
for item in manifest:
 p=r/item['file'];provenance.append({**item,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sourcePath':'../frames/%04d.png'%item['sourceFrame'],'sourcePolicy':'exact RGB crop; alpha is source contour partition; no generated fill','attachmentKey':p.stem})
by={}
for x in provenance:by.setdefault(x['part'],[]).append(x['sourceFrame'])
report={'version':'2026-11-20','sourceVideo':'I:/彩虹AI/design/视频素材_design/Walulu萌宠/蘑菇秃秃方向/基础角色-测试/右前行走.mp4','frameRange':[63,85],'fps':24,'partsByFrame':by,'attachments':provenance,'generatedPixels':False,'visualBaseline':'pixel_bound source-pixel IK trial accepted by user as close to AI video','workbenchStatus':'not integrated; awaiting production attachment reduction review'}
(r/'attachment_provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
(r/'SOURCE_PIXEL_POLICY.md').write_text('''# 原帧像素策略

每个附件的 RGB 来自 `frames/` 中对应帧的矩形裁剪，SHA-256 记录在 `attachment_provenance.json`。透明度只用于把源帧角色轮廓从近白背景中分离，未对缺失区域生成皮肤或布料。

23 个姿态时刻保留原始手、脚、裤衩和躯干轮廓。后续减少附件时，只允许逐像素相同合并，或经过逐帧视觉比较后保留差异；禁止用插值或生成式补画替换原帧轮廓。

`source_pixels_ik_refined.spine` 是可审阅基准。工作台接入前必须重新导入该工程并检查附件相对路径 `parts/`。
''',encoding='utf8')
print('provenance records',len(provenance),'parts',sorted(by))
