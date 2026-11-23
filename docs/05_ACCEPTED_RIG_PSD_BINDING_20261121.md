# 用户纠正：以已验收骨架绑定 PSD

用户明确要求：骨骼建立和 IK 应使用右前行走 pixel_sync_20261120 的已验证结构，再绑定 PSD 图层。

查明 v3 自建骨架将 arm_far_ik 的 bendPositive 设为 false（应 true），leg_far_ik 设为 true（应 false）；执行顺序也不同。其骨长、辅助骨、透视缩放和人工轨迹均不再作为本轮基准。

当前有效候选位于 spine_samples/psd_pixel_sync_binding_20261121。直接复制验收版 16 骨、4 IK、slot/bone 关系、reference_cycle 骨骼时间轴。仅 root 静态统一缩放 1.68 与平移；四肢附件静态对齐到骨架，腿保留横向宽度，再编辑网格权重。PNG 与最新 PSD 导入母版一致，没有补画和逐帧换图。没有新的骨骼缩放或旋转关键帧。

真实 Spine r3 导入回导后：93 个时间点全部骨骼位置与矩阵和验收版等价，最大位置差约 1.71e-13px；IK 默认值规范化后逐项相同。蒙皮回导顶点差约 0.01142px、翻折 0。绑定姿势误差指标针对静态对齐后的附件，而非原 PSD 原位置；不应误报成四肢原位保持。

预览 /spine_samples/psd_pixel_sync_binding_20261121/video_fit/review.html 提供验收骨架青色粗线和当前骨架红色细线叠加。包 psd_bound_pixel_sync.zip，主动画 reference_cycle。

尚未用户视觉验收。后续先修蒙皮的覆盖、厚度与接缝，保持骨架基准。若确需改骨架或 IK，要向用户明确提出原因与影响，不能再次静默用自建 rig 代替已验收 rig。原基准、PSD 和上一轮候选均保留。本轮未提交 Git。
