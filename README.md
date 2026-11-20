# Cotton Doll Action Workbench

棉花娃娃动作设计工作台，包含 V3 工作台源码、05 骨骼动画研究及 Spine 样板。

## 当前验收基准（2026-11-20）

用户已通过 review.html 与 Spine 工程验收“右前行走”骨骼/附件同步版本：
`spine_samples/video_motion_study_20261119/pixel_sync_20261120/`。

正式动画是 `reference_cycle`；`test_*` 是单部位控制诊断。Spine 中需要点击动画行最左侧小圆点激活动画，再播放。
该样板保留 161 张原帧部件、16 根骨骼、4 组 IK，按 24fps 同步切换附件与骨骼姿态。用户已决定不再优化本轮样板。
这是当前样板的验收，不表示任意视频自动处理、自由姿态、跨角色或 Unity 验收通过。尚未接回 05 工作台。
历史文档中的“待视觉验收”是当时记录；本段及 docs/ACCEPTED_BASELINE.md 记录最新状态。

## 启动

需要 Python 3.10+，在仓库根目录运行：

```powershell
py -3 server_v3.py --host 127.0.0.1 --port 8770
```

工作台：http://127.0.0.1:8770/studio_v3/
样板：http://127.0.0.1:8770/spine_samples/video_motion_study_20261119/pixel_sync_20261120/review.html

样板包含本地参考帧。工作台其他素材映射、H3服务及字体等仍有原开发机依赖，详见 CODEX_HANDOFF.md。运行研究脚本所需 Pillow、NumPy、OpenCV、SciPy 请按脚本依赖配置。

## 基础回归

```powershell
node studio_v3/tests/test_sequence_loop.cjs
node studio_v3/tests/test_sequence_workflow_lifecycle.cjs
```

## 快照与大文件

本次提交是05工作台接入前快照。历史失败候选保留用于追溯，不能当成已验收成果。
缓存、日志、重复ZIP不纳入Git；已验收工程ZIP和超限历史研究数据保存于同次Release。
超限数据还原路径及SHA256见 docs/EXTERNAL_SNAPSHOT_ASSETS.json。下载并将历史数据ZIP解压到仓库根目录即可还原。
原始外部磁盘素材、浏览器草稿、账号与密钥不在快照中。

Spine运行时沿用原项目文件及其内嵌许可，使用时遵守 Esoteric Software 的授权要求。

## 下一阶段

1. 固化已验收样板与来源记录。
2. 整理可复现制作流程及人工判断环节。
3. 将样板数据与预览接入05。
4. 整理视频参考、图集拆件、骨骼动画、检查导出界面。
5. 从工作台导出并在Spine复验。
6. 再用新素材验证复用能力。
