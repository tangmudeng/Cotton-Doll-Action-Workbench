# 原帧皮肤：控制绑定修订

工程：source_pixels_ik_controls.spine；保留parts目录同级。Spine 4.2.43格式。原视频行走动画为reference_cycle。

## 本轮确认的问题

旧verified版的四肢确实使用上下段IK骨骼，但头、躯干和裤衩全部只绑定root；torso与pelvis骨骼不驱动这些部位。因此显示出骨骼不等于所有部位都有对应控制。此版已改为：head→head_control；torso→torso；shorts→pelvis；四肢继续绑定各自upper/lower。

新head_control为torso子骨，其余肩髋与IK目标仍保持原有root参考系。这是分部位控制修订，尚不是完成的全身联动层级；大幅扭转躯干不会自动重建肩髋遮挡。原视频中未露出的像素仍缺失，不做生成补画。

## 如何检查

reference_cycle是正常行走；test_head、test_torso、test_shorts分别做5度、3度、4度小幅转动。test_near_hand/test_far_hand移动手IK目标5px，test_near_foot/test_far_foot移动脚IK目标4px。所有test动画固定第70帧附件，绝不切换贴图，因此可以直接验证皮肤是否由控制器驱动。

测试产生接缝或重叠说明附件不能泛化到该姿态，不代表测试动画是最终动作。当前仍161个原帧附件、23组姿态切换；不宣称单套皮肤可任意动作。正常循环也仍需检查帧间接缝。

## 验证与范围

原verified工程在本机Spine 4.3.26中实际播放确认，观察到不同时间点骨骼、四肢及贴图变化。新版controls工程经过4.2.43 CLI导入重导出、官方运行时验证、浏览器观察，但未在编辑器里重新打开。为保留当前编辑器未保存状态及4.2文件格式，取消了切换文件与另存流程。

新版23个源帧时刻相对旧版最大网格位置差0.007px；关键帧中点最大差约0.51px来自新增躯干骨骼跟随。7项控制测试全部通过：固定附件时对应部位移动、无无效顶点、权重和为1。见binding_checks.json。

RGB图片与旧版逐文件SHA256一致，没有补画。网页直接读取新版Spine重新导出的skin.json。

解压后运行 py -3 -m http.server 8780，打开 http://127.0.0.1:8780/review.html 。菜单可选择原视频行走和7个控制测试。
