# Walulu V3 / 05 骨骼动画 Codex 接手说明

## 项目结构

本包是从工作区复制出的独立开发副本，主要内容：

- `spine_workbench/studio_v3/`：V3 统一工作台01-05源码、05生成器、所有05候选、输入、参考视频、manifest、检查报告、渲染和失败审阅证据。
- `spine_workbench/runtime/`：Spine Canvas/WebGL运行时脚本。
- `spine_workbench/server_v3.py`：本地HTTP服务入口。
- `spine_workbench/h3_comfy.py`、`h3_prompt_agent.py`：V3服务导入的可选H3模块。
- `spine_workbench/Spine动画工作台设计文档_v1.md`：05目标与验收原则。

请在Codex中打开解压后的 `spine_workbench` 目录作为工作区。所有修改仅针对此副本；不要覆盖原始项目。

## 本地启动

需要Python 3.10+。打开终端进入 `spine_workbench`：

```powershell
py -3 server_v3.py --host 127.0.0.1 --port 8770
```

浏览器访问 `http://127.0.0.1:8770/studio_v3/`。如果8770已占用，可替换端口。V3基础页面由Python标准库服务；部分可选处理需要安装 Pillow、NumPy、opencv-python，特定拟合/研究脚本还需要 SciPy。项目没有统一requirements文件，建议按要运行的脚本建立单独虚拟环境并安装其实际依赖，不要假设仅服务启动即能执行全部研究脚本。

## 只读回归

在 `spine_workbench` 目录运行：

```powershell
node studio_v3/tests/test_sequence_loop.cjs
node studio_v3/tests/test_sequence_workflow_lifecycle.cjs
```

这两项是当前可直接运行的Node测试入口，不会启动服务或调用外部API。其他测试或构建脚本可能写入 `generated_rig` 结果目录；运行前先阅读脚本的输出路径和保护断言，避免在基线副本上覆盖证据。

## 05当前状态与边界

- 正式目标是视频驱动的Meowa式拆件、骨骼/动画联合编辑；AI视频用于关键姿态、节奏、遮挡与补画判断。不能声称从视频自动恢复骨骼。
- `profile_walk_v1` 是七件/12骨的有限步态原型，不是生产验收通过的动画。
- `video_guided_walk_v2`、`pose_walk_v3`、`joint_structure_v4` 都是候选或失败研究材料，不能作为已修复成果、正式可编辑工程或生产导出包。v3/v4审阅报告中的失败指标和图像必须一并保留、如实参考。
- 现有候选不能解锁正式导出。Spine JSON/atlas/PNG、浏览器预览、可编辑源工程、Unity实机验收是不同交付层级，不能互相替代。
- 不得通过压低动作幅度、逐帧贴片、无限追加局部修形值或增加每帧/每件衣服专属骨骼来掩盖结构问题。优先检查近臂收胸时枢轴与材料控制点语义、有效肘部内部边流、最小肩根搭接；保持通用双骨链与七逻辑件边界。换装、跨角色和六方向均需独立验收。
- 当前六方向规则：四套源方向覆盖运行六方向；front/back独立，front_right_3q镜像为front_left_3q，back_right_3q镜像为back_left_3q。正/背面可以先做待机互动，前后3/4承担走跑。
- 目标动作包括走、跑、挠头、双手胸前摆弄、坐下和躺下；坐躺遮挡/补图/软体形变需独立验证。手机性能与同屏角色数未经实机测试不得承诺。

## 外部依赖与限制

- `server_v3.py` 中 `/res`、`/fill`、`/character-source` 映射到原开发机的绝对路径。本包不包含这些项目外资源；换机器后对应页面区域可能缺图。需要在目标环境按本地素材实际位置修改映射，勿从原机盲目复制个人或无关素材。
- H3工作流JSON指向原开发机I盘路径，外部Comfy服务和可选的方舟API也需单独配置。密钥必须由使用者在目标环境通过环境变量提供，本包不含密钥。
- MediaPipe相关前端流程可能从CDN加载依赖；离线环境无法保证该功能。
- `h3_prompt_agent.py` 读取 `h3_agent_source/conversation-data.json`。该文件是原开发机Agent来源上下文，因隐私原因未纳入包；对应本机提示词Agent功能不可用。不要将原文件复制到共享包或提交版本库。
- `build_pose_walk_v3.py` 和 `build_joint_structure_v4.py` 中的V2变量指向包内 `video_guided_walk_v2` 候选，并非V2工作台，相关候选输入已收录。另有 `constraint_pose_trial.py`、`test_arm_mesh.py` 的历史保护检查引用兄弟目录 `studio_v2`；该V2工作台未收录，运行这两类历史研究入口前需先检查其输入和保护范围，不应静默更改基线数据。
- 生成审阅图的部分脚本引用 `C:/Windows/Fonts/msyh.ttc` 或Arial字体；非Windows环境需调整字体路径。
- 浏览器IndexedDB草稿、登录态和原浏览器历史不在源码包中，无法随ZIP迁移。

## 建议的Codex接手顺序

1. 先运行上面的两项只读Node回归并检查生成目录的manifest引用和SHA闭包。
2. 阅读 `Spine动画工作台设计文档_v1.md`、`generated_rig/video_f7e82942/profile_walk_v1/`、`video_guided_walk_v2/`、`pose_walk_v3/`、`joint_structure_v4/` 的来源/检查文件与对照图，确认原型、失败候选和验收门槛。
3. 先做收胸极限姿态的枢轴与材料对应核查，再决定是否需要局部结构实验；实验必须新建隔离输出目录，不能覆盖正式素材或旧候选。
4. 动画结果必须回到工作台与视频时间轴并列审阅；通过后再分别开展Spine可编辑工程、换装/跨角色、Unity手机实机验收。

## 验证范围与历史记录

包根目录的 `verify_handoff.py` 可只读检查核心05 manifest和四套候选的profile/provenance/checks/evidence路径字段；`verification.json` 保存打包时结果。文件名式视频观察引用按包内现有同名文件解析，不会补写或伪造原manifest。该检查不等于穷尽所有研究报告的历史保护哈希，也不代表动画视觉验收。

`video_guided_walk_v2/provenance.json` 记录的构建脚本SHA和当前 `build_video_guided_walk.py` SHA不同。此差异在原项目中已经存在，原样保留并记入验证报告；因此不能承诺当前脚本逐字重建当时的v2产物。素材与清单本身未因打包被改写。

## 打包说明

此包不包含完整1.78GB工作区、studio_v2、Unity工程、房间素材、本机日志/缓存、`.workbuddy`私有记忆或本机Agent会话数据。`studio_v3`及05关联的生成证据已完整收录（排除缓存和临时验证脚本）；原始项目仍保留在本机。
