# Walulu 右前行走：重建样板

打开 walulu_right_front_walk_review.spine，选择 walk 动画。保持 parts/ 与工程同级。有效工程为 Spine 4.2.43 CLI 从JSON新建，含12根骨骼、7个加权网格附件、0.875秒 walk 循环和 setup。不是视频帧替代骨骼，也不声称全程在编辑器手工制作。

本轮旧目录由用户删除后重新创建。附件重新依据用户原画与视频关键帧补画；头部直接裁自原画。肤色和描边按原画采样校正。补画细节、脚形与原画仍有差异，visualApproved=false；不得接回工作台作为已通过质量基准。

验证：有效.spine经Spine 4.2.43导入、重新导出 final_roundtrip/right_front_walk.json，再用官方运行时检查193个时刻，零三角翻折，首尾误差0，手脚末端内部距离误差小于0.00003。49个渲染姿态保持一个主体连通区；肩颈、躯干未检出大于3像素的内部孔洞。腿间因双脚交叠形成的封闭背景区域保留在silhouette_checks.json，不宣称全身零孔洞。

编辑器GUI播放仍未验证：窗口最小化，恢复操作被用户输入保护拦截。不能将CLI导入重导出等同编辑器播放验收。

本地预览：在本目录执行 py -3 -m http.server 8772 --bind 127.0.0.1 后访问 http://127.0.0.1:8772/review.html。支持播放、半速、逐帧时间拖动和骨骼开关。左侧为原视频提取帧，右侧为实时骨骼运行时绘制；PNG序列仅用于左侧参考。Canvas预览增加0.45像素三角裁切重叠来消除浏览器抗锯齿细线，不改变导出网格。GIF使用官方运行时姿态经CPU渲染，时间粒度导致循环约0.88秒。

附件制作与绑定：build.py；运行时检查：check.cjs；GIF与轮廓检查：render.py。Python依赖Pillow、numpy、opencv-python、scipy；检查需Node。Spine runtime使用遵循其文件内许可与用户Spine授权。所有最终资产SHA256见manifest.json。
