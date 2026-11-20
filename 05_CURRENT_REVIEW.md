# 05 拆件当前进度

## 最新进展：以原视频为主要依据的独立样板

用户再次明确：AI 视频关键帧是重点，完整角色图仅为辅助参考。新目录 spine_samples/right_front_walk_video_master 独立从原 MP4 重新取帧、重新描轮廓，未读取被否决版本的附件图片或关节点文件。

已生成 6 附件、12 骨骼和带网格修正的 walk 动画，在 Spine 4.3.26 实际播放、调整头颈并保存，实际从编辑器导出 4.2 JSON，通过官方运行时 193 相位结构检查。有效审阅文件只在该目录 review_bundle。该版尚未获视觉认可，肩根、髋部线条和脚掌形状仍需审阅；未接回工作台，不能称最终质量基准。详见新目录 README.md。

## 最新纠正：Spine 样板素材基准错误

2026-11-19 用户指出当前 Spine 样板沿用了不合格拆件。spine_samples/right_front_walk_v1 和 right_front_walk_v2 均标为不合格并停止制作，不得作为工作台质量基准。新指定的完整角色外观图已保存到 spine_samples/approved_visual_reference/user_character_reference.png；此图仅确认外观基准，不表示拆件已获认可。后续须重新建立附件并核对静态还原，再进行绑定与动作。工作台默认素材未切换。

用户拒绝上一版，并明确附件完整性、接缝、动作贴合度三项都不能接受。

2026-11-19 新实验位于 studio_v3/generated_rig/video_parts_v3，未通过内部视觉检查，未切换工作台默认附件、未生成新的合格验收包。详见该目录 README.md、visual_review.json 和 comparison.png。不要把运行时 193 相位通过当作用户验收。

构建脚本：studio_v3/build_video_parts_v3.py。对照与轮廓计算：studio_v3/render_video_parts_v3.py。

本轮新增 Image2 肩根补图，原始输入、输出及映射都保留在候选目录。只把肩部受限区域混入附件，脚掌仍来源视频。躯干仍沿用上轮补图，未完成结构重建。
