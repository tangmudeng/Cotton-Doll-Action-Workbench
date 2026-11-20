from pathlib import Path
import hashlib,zipfile
R=Path(__file__).resolve().parent
(R/'README.md').write_text('''# 右前行走：视频动作标定与原像素取材研究

这是正式绑定美术前的第一阶段。源视频864×480、24 fps；当前标定区间为第63—85帧（22帧循环候选）。

先用HTTP服务打开review.html。左侧为原始视频帧加人工标注，右侧为固定骨长两段IK色块。空心点代表推定或遮挡位置，不是动捕关节。可以勾选调整标注、拖动点后下载修订JSON。

video_ik_study.spine是纯色块研究工程，含15根骨骼和4组Spine原生IK约束。解压后保持ik_parts/与工程同级，在Spine中激活动画reference_cycle。本轮仅验证目标轨迹和约束，不包含角色附件，也不代表动作已验收。

source_candidates/中9个候选窗口直接从原视频帧裁剪，逐像素核对；它们保留背景与遮挡，尚非完整透明附件。asset_sources.json记录帧号、裁剪框、SHA-256及限制。后续优先使用不同姿态的原帧附件，不将不同角度硬拼成一张；原视频未出现的像素不擅自补画。

IK技术检查：23帧、4组约束，Spine重新导出后最大目标误差小于0.01px，骨长误差小于0.000001。这个数值只说明求解正确，不说明人工标注准确。脚底接触仍为候选，未锁到虚构地面；肩髋及遮挡端点包含推定。

motion_overlay.gif与motion_keyframes.png用于快速检查。用户确认骨架叠加后才进入原帧附件绑定。本轮未在Spine GUI内检查，已做CLI导入、重新导出与官方运行时验证。
''',encoding='utf8')
files=[p for p in R.rglob('*') if p.is_file() and p.suffix not in ['.zip','.log']]
manifest={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
out=R/'motion_study_v1_review.zip'
with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(R).as_posix())
 z.writestr('SHA256SUMS.txt',''.join(h+'  '+n+'\n' for n,h in sorted(manifest.items())))
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for n,h in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
print('study package verified',len(files),'files')

