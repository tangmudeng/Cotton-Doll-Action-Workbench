# 右前行走：原帧皮肤同步修订（待视觉验收）

解压整个目录后，在 Spine 打开 walulu_walk_pixel_sync.spine，选择 reference_cycle 动画播放。parts 必须与工程同级。工程使用 Spine 4.2.43 导入并重新导出验证，时间线为24fps。不要用 test_* 动画判断本轮行走效果；它们保留的是旧有控制器诊断。

主要修复：旧版附件每帧更换，而骨骼在两帧之间连续插值，导致旧皮肤被拉裂。现在骨骼姿态和原帧附件同时切换。保留161张原始部件、16根骨骼和4组IK；没有补画、没有替换成整张帧图驱动。

这仍是24fps原帧样板，不是可任意改动作的最终自由变形皮肤。循环边界、透明边缘、遮挡关节及独立调整IK仍待验收。尚未接回05工作台。

23个源帧和115个帧内采样已通过修订数据检查；详见 audit/REPORT.md 和 audit/sync_validation.json。数值检查不代替你的视觉验收。

网页核查：在解压目录运行 py -3 -m http.server 8780，然后打开 http://127.0.0.1:8780/review.html。
左侧是原视频，中间是旧版，右侧是同步修订。选择“附件切换前”可以直接看到修复针对的差异。

文件：
- walulu_walk_pixel_sync.spine：可打开工程
- skin.json / skin.atlas / skin.png：本轮运行时数据、图集
- parts：独立附件，和上个controls版SHA256一致
- reference_frames：原视频第63–85帧，用于网页对照
- audit：逐帧证据和验证记录
- baseline.json：网页中间栏旧版对照，不能当成修订数据导入
