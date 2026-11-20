(() => {
  'use strict';
  const root = document.querySelector('#tab-spineRig');
  if (!root || root.dataset.videoWorkbenchBuilt === 'true') return;
  root.dataset.videoWorkbenchBuilt = 'true';

  const asset = Object.freeze({
    characterId: 'legacy_six_view',
    taskId: 'comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa',
    base: './generated_rig/video_f7e82942/',
    sha256: '8fc0f8406d6a258640b65d34c5ad7fb0e35f231131d7eec945781dd9d93343e5',
    sourcePng: '/character-source/' + encodeURIComponent('右前¾侧图层.png')
  });
  const videoUrl = asset.base + 'source.mp4';
  const storageKey = `cotton_spine_video_draft_v2:${asset.characterId}:${asset.taskId}`;
  const profileSourceSha = window.CottonVideoGuidedSourceSha;
  const profilePackageId = profileSourceSha === undefined ? 'profile_walk_v1' : 'video_guided_walk_v2';
  const profileSourceNote = profileSourceSha === undefined
    ? '新包 manifest 未加载，已回退源 walk_v1 设计步态（profile_walk_v1）；不是视频拟合结果。'
    : '动作来自视频参考候选 video_guided_walk_v2/profile_walk.json；候选未通过，视频 PNG 仅作同步参考，禁止写键与导出。';
  const steps = [['A', '源图与视频'], ['B', '稳定部件 / 证据'], ['C', '来源审阅 / 观测'], ['D', '视频对照与动作预览'], ['E', '来源校验与运行包导出']];
  const nextSteps = {A: 'B', B: 'C', C: 'D', D: 'E', E: 'D'};
  const pointDefinitions = [
    {id: 'foregroundCentroid', label: '前景重心（非关节）'},
    {id: 'hand_near', label: '近侧手 · 身份低可信'},
    {id: 'hand_far', label: '远侧手 · 身份低可信'},
    {id: 'foot_near', label: '近侧脚 · 身份低可信'},
    {id: 'foot_far', label: '远侧脚 · 身份低可信'}
  ];
  const pointIds = new Set(pointDefinitions.map(point => point.id));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const activeId = () => String(window.activeCharacterId || asset.characterId);
  const clone = value => JSON.parse(JSON.stringify(value));

  root.innerHTML = `
    <style>
      #tab-spineRig .rw{color:var(--text,var(--ink,#e8e6e1));font-size:13px;line-height:1.5;min-width:0}
      #tab-spineRig .rw *{box-sizing:border-box}
      #tab-spineRig .rw h2,#tab-spineRig .rw h3{margin:0 0 8px;color:inherit}
      #tab-spineRig .rw [hidden]{display:none!important}
      #tab-spineRig .rw-header{position:static;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:0 0 12px;background:transparent}
      #tab-spineRig .rw-eyebrow{color:var(--accent);font-size:11px}
      #tab-spineRig .rw-status,#tab-spineRig .rw-muted{font-size:11px;color:var(--muted);overflow-wrap:anywhere}
      #tab-spineRig .rw-error{color:#ffb5ab!important;white-space:pre-wrap}
      #tab-spineRig .rw-note{padding:9px 12px;background:var(--panel2);border-left:3px solid var(--accent);margin:8px 0}
      #tab-spineRig .rw-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:12px 0}
      #tab-spineRig .rw-tab{min-height:60px;text-align:left;border:1px solid var(--line);border-radius:6px;background:var(--panel2);color:var(--muted);padding:9px 12px;cursor:pointer}
      #tab-spineRig .rw-tab strong{display:block;color:inherit;font-size:13px}
      #tab-spineRig .rw-tab span{font-size:11px}
      #tab-spineRig .rw-tab[aria-selected=true]{background:var(--accent);color:#181b20;border:3px solid #fff0cc;font-weight:800;padding:7px 10px}
      #tab-spineRig .rw-panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}
      #tab-spineRig .rw-layout{display:grid;grid-template-columns:180px minmax(0,1fr) 245px;border:1px solid var(--line);border-radius:6px;overflow:hidden}
      #tab-spineRig .rw-two{display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:12px;align-items:start}
      #tab-spineRig .rw-sidebar,#tab-spineRig .rw-inspector{padding:12px;background:var(--panel2);min-width:0}
      #tab-spineRig .rw-sidebar{border-right:1px solid var(--line)}
      #tab-spineRig .rw-inspector{border-left:1px solid var(--line)}
      #tab-spineRig .rw-workarea{display:flex;flex-direction:column;min-width:0;background:#171c23}
      #tab-spineRig .rw-toolbar,#tab-spineRig .rw-control-row{display:flex;align-items:center;gap:8px;padding:8px;flex-wrap:wrap}
      #tab-spineRig .rw-toolbar{border-bottom:1px solid var(--line)}
      #tab-spineRig .rw button:not(.rw-tab),#tab-spineRig .rw select{font:inherit;padding:6px 9px;border:1px solid var(--line);border-radius:5px;background:var(--panel2);color:inherit;cursor:pointer}
      #tab-spineRig .rw button:disabled,#tab-spineRig .rw input:disabled{opacity:.45;cursor:not-allowed}
      #tab-spineRig .rw :is(button,input,select,summary):focus-visible{outline:2px solid var(--accent);outline-offset:2px}
      #tab-spineRig .rw-video{width:100%;height:auto;background:#111;display:block}
      #tab-spineRig .rw-canvas-wrap{position:relative;width:100%;background:#111}
      #tab-spineRig .rw-canvas-wrap canvas{display:block;width:100%;height:auto;aspect-ratio:16/9;touch-action:manipulation}
      #tab-spineRig #rwEvidenceCanvas{max-height:40vh;object-fit:contain}
      #tab-spineRig .rw-canvas-label{padding:5px 8px;font-size:11px;color:var(--muted)}
      #tab-spineRig .rw-source{width:100%;height:auto;max-height:300px;object-fit:contain;background:repeating-conic-gradient(#333 0 25%,#555 0 50%) 50%/16px 16px;display:block}
      #tab-spineRig .rw-list{list-style:none;padding:0;margin:8px 0}
      #tab-spineRig .rw-list button{width:100%;text-align:left;margin-bottom:4px}
      #tab-spineRig .rw-list button[aria-pressed=true]{background:var(--accent);color:#181b20}
      #tab-spineRig .rw-kv{font-size:11px;border-top:1px solid var(--line);padding:7px 0;overflow-wrap:anywhere;white-space:pre-line}
      #tab-spineRig .rw-evidence{display:grid;grid-template-columns:repeat(auto-fill,minmax(105px,1fr));gap:6px;padding:8px}
      #tab-spineRig .rw-evidence button{padding:4px;text-align:left;font-size:11px}
      #tab-spineRig .rw-evidence button[aria-current=true]{border-color:var(--accent);color:var(--accent)}
      #tab-spineRig .rw-evidence img{width:100%;height:auto;aspect-ratio:16/9;object-fit:contain;display:block}
      #tab-spineRig .rw-evidence small{display:block}
      #tab-spineRig .rw-timeline{padding:8px 12px;border-top:1px solid var(--line)}
      #tab-spineRig .rw-timeline input{width:100%;accent-color:var(--accent)}
      #tab-spineRig .rw-keyframes{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
      #tab-spineRig .rw-tracks{display:grid;gap:4px;margin-top:8px}
      #tab-spineRig .rw-track{display:grid;grid-template-columns:95px 1fr;gap:5px;font-size:10px}
      #tab-spineRig .rw-track-bar{height:15px;background:#39424d;position:relative}
      #tab-spineRig .rw-track-bar button{position:absolute;top:0;width:6px;height:15px;padding:0!important;border:0!important;border-radius:0!important;background:var(--accent)!important;transform:translateX(-50%)}
      #tab-spineRig .rw-track-bar button[data-missing=true]{background:#8c96a4!important;height:7px;top:4px}
      #tab-spineRig .rw-bottom{display:flex;justify-content:space-between;gap:8px;margin-top:10px;flex-wrap:wrap}
      #tab-spineRig .rw details{border-top:1px solid var(--line);padding-top:8px;margin-top:8px}
      #tab-spineRig .rw summary{cursor:pointer}
      #tab-spineRig .rw pre{white-space:pre-wrap;overflow-wrap:anywhere}
      #tab-spineRig .rw .rpe-main{padding:0;margin:0;max-width:none}
      #tab-spineRig #rwProfileExportHost{margin:12px 0}
      @media(max-width:950px){#tab-spineRig .rw-layout{grid-template-columns:150px minmax(0,1fr)}#tab-spineRig .rw-inspector{grid-column:1/-1;border:0;border-top:1px solid var(--line)}}
      @media(max-width:560px){#tab-spineRig .rw-tabs{grid-template-columns:repeat(2,1fr)}#tab-spineRig .rw-layout,#tab-spineRig .rw-two{grid-template-columns:1fr}#tab-spineRig .rw-sidebar{border:0;border-bottom:1px solid var(--line)}}
    </style>
    <div class="rw">
      <header class="rw-header"><div><div class="rw-eyebrow">05 · 骨骼与动作制作工作台</div><h2>右前¾ walk · 来源审阅 → Profile 联合编辑 → 非生产导出</h2></div><div class="rw-status">固定任务 ${asset.taskId}</div></header>
      <div class="rw-note"><p class="rw-muted">按照 A–E 正式流程继续推进：C 查看视频可见轮廓、观测证据与周期参考；D 内嵌七件 / 四肢 weighted mesh / 12 bones 的视频对照与动作预览，高级编辑可选；E 校验来源并导出 source / edited 任务运行包（非生产）。设计步态不是视频精确复现；衣袖、跨角色、手机未验收。</p><details><summary class="rw-muted">历史会议演示与审计（非制作入口）</summary><a href="./walk_demo.html" target="_blank" rel="noopener">旧 meeting walk 会议演示</a> · <a href="./generated_rig/video_f7e82942/meeting_walk_v1/checks.json" target="_blank" rel="noopener">旧会议样件审计</a></details></div>
      <div class="rw-note" id="rwCharacterNotice" role="status"></div>
      <div class="rw-tabs" role="tablist" aria-label="05 制作步骤">${steps.map(([id,label],i)=>`<button type="button" id="rwTab${id}" class="rw-tab" role="tab" data-step="${id}" aria-controls="rwPanel${id}" aria-selected="${i===0}" aria-current="${i===0?'step':'false'}" tabindex="${i===0?0:-1}"><strong>${id} ${label}</strong><span>待查看</span></button>`).join('')}</div>
      <section id="rwPanelA" class="rw-panel" role="tabpanel" aria-labelledby="rwTabA">
        <h3>A 源图与动作参考</h3><div class="rw-two">
          <div class="rw-workarea"><div class="rw-toolbar"><span>指定视频 · 右前¾ walk</span><span id="rwVideoStatus" class="rw-status" role="status">正在读取视频…</span></div><video id="rwVideo" class="rw-video" controls playsinline preload="auto"></video></div>
          <aside><h3>角色源 PNG</h3><img class="rw-source" data-source-image alt="默认六方向角色右前¾源 PNG"><div class="rw-status" data-source-status role="status">读取源 PNG…</div><div class="rw-kv">原图：默认六方向素材参考；视频角色归属待核实</div><div class="rw-kv" id="rwVideoMeta">视频 metadata 读取中</div><div class="rw-kv">SHA-256：${asset.sha256}</div></aside>
        </div><div class="rw-note rw-muted">视频与已有分析可直接查看，不需要先标关节点。轮廓重心不是关节；near/far 身份仍低可信。B 页可查待审部件与局部搭接；C 保留独立视频证据，D 已接入任务 Profile 骨骼动作编辑，E 导出非生产运行包。来源校验通过不等于视觉或生产验收。</div>
      </section>
      <section id="rwPanelB" class="rw-panel" role="tabpanel" aria-labelledby="rwTabB" hidden>
        <h3>B 稳定角色部件与视频证据</h3><h4>稳定角色部件 / 7逻辑件</h4><div class="rw-muted" style="margin-bottom:10px">Meowa三栏：左侧7个逻辑件 · 中央7张待审候选排版 · 右侧真实部件预览、来源、mask与审阅图链接及独立完整原图参考。body原可见保留 + 已生成Image2供体的AI隐藏域局部搭接待审；其他6件仅原图可见像素。不是完整隐藏补画；全部未验收、未绑定，正式 PNG + atlas / Spine ZIP 始终禁用。</div>
        <section class="rw-note" id="rwVideoPartReview"><h4>视频分件复核依据</h4><p>待完成：按视频进行拆件。七件逻辑不变，原静态七件未重拆、未补全；原纹理不足以复现胸前弯臂、转面及肩腿根遮挡。目前是视频约束候选，增加证据帧不等于完成拆件。</p><div id="rwVideoPartReviewStatus" class="rw-status" role="status">等待同包 evidence 校验…</div><div id="rwVideoPartReviewItems"></div><button type="button" data-show-part-video>在本页展开现有视频定位区</button></section>
        <section class="rw-note" id="rwReworkV8"><h4>最新返工 · 近臂 v8 与腿部投影（未采用）</h4><p class="rw-muted">用原角色、旧臂裁片及真实视频68/72帧垫图生成轻屈完整近臂，再以固定骨长、单mesh、双骨链测试。未增加碎片、deform或attachment切换，未缩小视频动作；v8手端分瓣与曲肘折叠未通过，未替换上方七件。下面只展示隔离制作检查，不是运行资产，也不提升任何验收状态。</p><details><summary>近臂真实组装 / 连续权重三档失败记录</summary><p class="rw-muted">1537相位检查：混合带24 / 36 / 52 px，实纹理翻转累计6475 / 3561 / 2351（三角形×采样，不是帧数）；最小面积比 -1.1985 / -0.6319 / -0.2599，全部失败。52px只是三档中翻转较少的诊断项，不是采用方案。主体mesh覆盖全部alpha&gt;8像素；489个alpha=1像素在包络外，原PNG未修改。腰裤口背景缺口与肩根分开记录，原因待确认。</p><img class="rw-source" loading="lazy" src="./generated_rig/video_f7e82942/arm_setup_review_v8/continuous_donor_setup_review.png" alt="近臂v8连续权重三档实际组装与网格失败对照，未采用"><a href="./generated_rig/video_f7e82942/arm_setup_review_v8/continuous_donor_setup_hinge52_contact.png" target="_blank" rel="noopener">17帧视频 / 无网格组装 / mesh对照</a> · <a href="./generated_rig/video_f7e82942/arm_setup_review_v8/continuous_donor_setup_checks.json" target="_blank" rel="noopener">完整检查与限制</a></details><details><summary>远腿 frame74：为何不能只靠刷权重或统一缩放解决</summary><p class="rw-muted">现有1.45映射：推断腿根到脚部轮廓代理93.41px，固定双骨最大触达57.07px，几何缺口36.34px（加0.3px伸直留量即现有36.64px残差）。找到的全可达统一映射约0.851倍，却只保留源躯干约61%的高度，因此拒绝作为修复。此诊断固定零旋转及既有推断根；代理不是物理标记，根/膝不是实测关节，不能推论所有重新绑定或投影策略不可行。</p><a href="./generated_rig/video_f7e82942/projection_review_v1/contact_reachability.png" target="_blank" rel="noopener">查看可达性 / 躯干比例冲突对照</a> · <a href="./generated_rig/video_f7e82942/projection_review_v1/projection_diagnosis.json" target="_blank" rel="noopener">查看来源、人工地标与诊断</a></details></section>
        <div id="rwStableAtlas"></div>
        <details id="rwBodyConstraintReview" style="margin-top:14px"><summary>当前推进 · 躯干 / 肩根 / 胸前臂共同约束审阅</summary><p class="rw-muted">本轮先做当前角色右前¾ walk，不扩展完整编辑器。头下接触线与腰线共同配准比仅腰线更接近人工视频参考，但肩根白缝、胸前臂轮廓与静态远臂仍未通过；图中肩区仅低可信允许区，不是真实关节。手臂冻结旧实验姿态，未重新拟合。仿射列只作诊断，不能作为角色profile或运行缩放；本研究不提升绑定、补画或正式导出状态。</p><a href="./generated_rig/video_f7e82942/body_constraint_v1/joint_review.png" target="_blank" rel="noopener">查看三帧共同约束对照图</a> · <a href="./generated_rig/video_f7e82942/body_constraint_v1/study.json" target="_blank" rel="noopener">查看观察点 / 配准 / 误差与限制</a> · <a href="./generated_rig/video_f7e82942/body_constraint_v1/checks.json" target="_blank" rel="noopener">查看来源及保护校验</a><p class="rw-muted">连续68–84审阅已完成，详见下方结果。光流仅作配准辅助；锚切换、失效点和多锚差异不视为置信区间或通过评分。71–76可确认胸前臂覆盖躯干但解剖归属未知；74–77脚形异常属于源视频待设计修正。一次冲突复核已收口：固定躯干相似矩阵、七件层序、单一arm_near、原mesh/weights/骨长，仅对68/72/80做双骨角度的隔离假设拟合。本次候选未通过：68/80帧单向残差虽下降，却新增17/5个翻转三角，肩根白缝仍在；72帧零翻转也不等于形体通过。目标是网格拓扑边（包含肩内切口），不是可见alpha边，因此不能把残差下降当作动作改善。此固定mesh/weights下的角度拟合候选不用于后续生产，不确认near/far或跨帧身份，也不是真实walk；保持生产、profile、绑定、补画mask和连续walk关闭。</p><a href="./generated_rig/video_f7e82942/continuous_constraint_v1/contact_068_073.png" target="_blank" rel="noopener">查看68–73连续审阅</a> · <a href="./generated_rig/video_f7e82942/continuous_constraint_v1/contact_074_079.png" target="_blank" rel="noopener">查看74–79连续审阅</a> · <a href="./generated_rig/video_f7e82942/continuous_constraint_v1/contact_080_084.png" target="_blank" rel="noopener">查看80–84连续审阅</a><br><a href="./generated_rig/video_f7e82942/continuous_constraint_v1/study.json" target="_blank" rel="noopener">查看17帧记录与传播诊断</a> · <a href="./generated_rig/video_f7e82942/continuous_constraint_v1/checks.json" target="_blank" rel="noopener">查看来源及保护校验</a><br><a href="./generated_rig/video_f7e82942/constraint_pose_trial_v1/overview.png" target="_blank" rel="noopener">查看三帧隔离姿态试验总览</a> · <a href="./generated_rig/video_f7e82942/constraint_pose_trial_v1/trial.json" target="_blank" rel="noopener">查看隔离试验记录</a> · <a href="./generated_rig/video_f7e82942/constraint_pose_trial_v1/checks.json" target="_blank" rel="noopener">查看隔离来源及保护校验</a></details>
        <details style="margin-top:14px"><summary>独立躯干补画 v5 · 历史完整候选未采用，局部搭接候选已显示、仍待审</summary><p class="rw-muted">历史记录：已用角色源图及视频68/72/80帧制作Image2躯干候选，并修正明显短臂鼓包与开放颈口。原始v5整体未采用，历史试组装仍有肩颈露缝、轮廓和腰口融合问题。当前稳定区body保留原图可见区域，仅采用v5供体的隐藏域局部搭接，已作为待审候选显示；不是完整隐藏补画，未批准绑定，正式导出仍禁用。下方历史对照仅人工静态配准，不是骨骼或动作拟合；当前body的已校验mask与审阅图请在上方选中body查看。</p><a href="./generated_rig/video_f7e82942/image2_repairs/body_candidate_v5_alignment_review.jpg" target="_blank" rel="noopener">查看原图 / v5静态试组装对照</a> · <a href="./generated_rig/video_f7e82942/image2_repairs/body_candidate_review_v5.json" target="_blank" rel="noopener">查看候选来源与返工记录</a></details>
        <details id="rwAtlasEvidence" style="margin-top:14px"><summary>视频姿态证据 / 74粗片（不进入角色主图集）</summary><p class="rw-muted">74张仅为22帧可见姿态粗片，身份未知。下方保留逐帧检查和带来源的审阅素材导出，不作为正式角色图集。</p><div id="rwAtlasEditor"></div></details>
        <details id="rwPartVideoWorkspace" style="margin-top:14px"><summary>视频证据与补画依据 · 原审阅工作区</summary>
        <div class="rw-layout">
          <aside class="rw-sidebar"><strong>部位与补画规划</strong><ul class="rw-list" id="rwPartsList"></ul><p class="rw-muted">选择部位会更新证据帧清单与所需补画说明。</p></aside>
          <div class="rw-workarea"><div class="rw-toolbar"><button type="button" data-play disabled>播放源视频</button><button type="button" data-fit>适配全图</button><label>缩放 <select data-zoom aria-label="拆件证据缩放"><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label><span class="rw-status" data-time>等待视频</span></div><div class="rw-canvas-wrap"><canvas id="rwEvidenceCanvas" width="960" height="540" aria-label="拆件规划的真实源视频帧"></canvas></div><div class="rw-canvas-label">画布直接读取 source.mp4；下方缩略图仅为明确编号的采样证据</div><div class="rw-canvas-label" data-seek-status role="status">尚未请求跳帧</div><div id="rwEvidenceFrames" class="rw-evidence"></div><details open style="padding:12px"><summary>视频姿态片 · 点击跳回源帧</summary>
            <div class="rw-control-row"><label for="rwVideoPartsSource">姿态片来源</label><select id="rwVideoPartsSource"><option value="sampled_poses">原采样证据</option><option value="continuous_068_084" selected>连续68–84</option><option value="current_frame">当前源帧</option></select></div>
            <div class="rw-status" id="rwVideoPartsStatus" role="status">读取视频姿态片…</div><div id="rwVideoParts" class="rw-evidence"></div>
            <a href="./generated_rig/video_f7e82942/video_parts_v1/pose_parts_review.jpg" target="_blank" rel="noopener">源帧 / 深浅底切片对照</a> · <a href="./generated_rig/video_f7e82942/video_parts_v1/contours_review.jpg" target="_blank" rel="noopener">轮廓叠加检查</a><br>
            <a href="./generated_rig/video_f7e82942/video_parts_v1/cycle_parts_068_075.jpg" target="_blank" rel="noopener">连续68–75姿态片 · 深浅底对照</a> · <a href="./generated_rig/video_f7e82942/video_parts_v1/cycle_parts_076_084.jpg" target="_blank" rel="noopener">连续76–84姿态片 · 深浅底对照</a></details><details style="padding:12px"><summary>连续帧68–84 · 遮挡与形变审阅</summary><div class="rw-status" id="rwCycleStatus" role="status">读取逐帧记录…</div><div id="rwCycleFrames" class="rw-evidence"></div><div class="rw-note" id="rwCycleDecisions"></div><a href="./generated_rig/video_f7e82942/video_parts_v1/cycle_review/contact_068_075.jpg" target="_blank" rel="noopener">68–75连续对照</a> · <a href="./generated_rig/video_f7e82942/video_parts_v1/cycle_review/contact_076_084.jpg" target="_blank" rel="noopener">76–84连续对照</a></details></div>
          <aside class="rw-inspector"><h3 id="rwPartTitle">拆件规划</h3><div class="rw-kv" id="rwPartReason">等待分析…</div><div class="rw-kv" id="rwPartMethod"></div><details><summary>局部搭接试验 · 非视频重拆</summary><img id="rwRepairImage" class="rw-source" alt="当前部位局部返工候选，非已验收资产" hidden><div id="rwRepairStatus" class="rw-status" role="status">读取返工记录…</div><a href="./generated_rig/video_f7e82942/image2_repairs/rework_v3/assembly_review.jpg" target="_blank" rel="noopener">原图 / 重组 / 补画区域对照</a><br><a href="./generated_rig/video_f7e82942/image2_repairs/rework_v3/parts_review.jpg" target="_blank" rel="noopener">全部部件切口检查</a></details><div class="rw-note rw-muted">已生成 Image2 候选并做局部纹理搭接返工；完整隐藏肢体、前摆姿态、动态露缝、权重及动作拟合仍未完成。</div><strong>源 PNG 对照（非拆件）</strong><img class="rw-source" data-source-image alt="拆件规划对照用完整源 PNG"><div class="rw-status" data-source-status role="status">读取源 PNG…</div></aside>
        </div></details>
      </section>
      <section id="rwPanelC" class="rw-panel" role="tabpanel" aria-labelledby="rwTabC" hidden>
        <h3>C 来源审阅 / 视频可见轮廓与观测</h3><p class="rw-muted">这里是独立观测证据，不是骨架。源视频、轮廓、低可信观测及周期候选仅供 D 的 Profile 动作编辑参考，不自动转成关节、权重或已拟合动作。</p><div class="rw-note rw-muted" data-profile-status role="status">D 已接入任务动作包；正在校验来源，数值检查结果另列，不代表视觉或生产验收。</div><div class="rw-layout">
          <aside class="rw-sidebar"><strong>来源观测树（独立证据）</strong><div class="rw-kv">C：可见轮廓 / 低可信观测 / 周期参考<br>D：任务 Profile 骨骼与动作联合编辑</div><strong>视频观测（非骨架）</strong><ul id="rwPointList" class="rw-list"></ul><p class="rw-muted">前景重心来自轮廓测量；手脚来自已有低可信审阅。缺失和遮挡点保留 null，不插值，不推断近远侧身份。</p></aside>
          <div class="rw-workarea"><div class="rw-toolbar"><button type="button" data-play disabled>播放源视频</button><button id="rwOverlay" type="button" aria-pressed="true">证据点：显示</button><button type="button" data-fit>适配全图</button><label>缩放 <select data-zoom aria-label="来源观测缩放"><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label></div><div class="rw-canvas-wrap"><canvas id="rwEditCanvas" width="960" height="540" aria-label="真实源视频与当前帧观测点"></canvas></div><div class="rw-canvas-label">显示实际源视频帧；只叠加该整数帧的证据点，不作轨迹拟合</div><div class="rw-timeline"><label for="rwTimeline">源视频帧时间轴</label><input id="rwTimeline" type="range" min="0" max="0" step="1" value="0" disabled><div id="rwTimeReadout" class="rw-status" data-time>等待视频 metadata / loadeddata</div><div class="rw-status" data-seek-status role="status">尚未请求跳帧</div><div id="rwKeyFrames" class="rw-keyframes" aria-label="关键证据帧"></div><div id="rwTracks" class="rw-tracks" aria-label="观测记录时间轴"></div><div class="rw-muted">黄色：有坐标记录；灰色：null / 遮挡。标记可点击跳回源帧。</div></div></div>
          <aside class="rw-inspector"><h3 id="rwPointTitle">当前点属性</h3><div id="rwPointValue" class="rw-kv">等待分析</div><div id="rwPointEvidence" class="rw-kv"></div><div class="rw-kv">坐标：源视频像素，左上为原点。采样帧以外不显示最近采样点。</div><details id="rwAdvanced"><summary>进阶修正（可选）</summary><p class="rw-muted">不是使用前提。暂停并选定真实源帧后，可修正所选观测；不会创建骨骼或提升近远侧身份置信度。</p><label><input id="rwEnableEdit" type="checkbox" disabled> 允许点击画布修正当前点</label><div class="rw-control-row"><button id="rwClearPoint" type="button" disabled>当前点设为缺失</button><button id="rwUndo" type="button" disabled>撤销上次修正</button></div><div id="rwDraftStatus" class="rw-status" role="status"></div></details></aside>
        </div>
        <div id="rwCycleReference" class="rw-note rw-muted" role="status">读取视频周期候选；仅相位参考，不是已拟合动作。</div><div id="rwCurrentContours" hidden></div>
        <details class="rw-legacy-evidence"><summary>C 历史观测证据导出（旧 D，保留但不覆盖 D 编辑）</summary><p class="rw-muted">仅导出固定任务的源帧观测草稿；不是 Spine JSON、atlas 或 .spine 工程。prototypeAccepted 来源记录不等于 edited 版本通过。</p><button id="rwExportDraft" type="button" disabled>导出视频观测草稿 JSON</button><div id="rwExportStatus" class="rw-status" role="status">等待分析与视频 loadeddata…</div><pre id="rwExportSummary" class="rw-status">读取分析…</pre></details>
      </section>
      <div id="rwProfileWorkspace" class="rw-panel" hidden>
        <section id="rwPanelD" role="tabpanel" aria-labelledby="rwTabD" hidden>
          <div class="rw-header"><h3>D 视频对照与动作预览</h3><span class="rw-muted">非生产预览 · ${profileSourceNote}</span></div><p class="rw-muted">先点播放看左右同步对照，也可调速度、选四相位或拖动时间轴；专业骨骼编辑、草稿与制作记录默认折叠。切走 D 会暂停，返回后不会自动播放。</p><div class="rw-note rw-muted" data-profile-status role="status">任务 Profile 来源校验中…</div><div id="rwProfileEditorHost" aria-label="视频对照与任务动作预览"></div>
        </section>
        <section id="rwPanelE" role="tabpanel" aria-labelledby="rwTabE" hidden>
          <h3>E 来源校验与运行包导出 · D 同区子面板</h3><p class="rw-muted">E 是明确的来源校验与导出步骤；下方控件仍挂在 D 同一工作区，不跳转独立页。导出当前 source / edited 任务运行包（非生产），不是 .spine 源工程。来源 SHA 与数值检查不代表视觉验收；prototypeAccepted 只保留为 source_checks 来源记录，不能视为 edited 版本通过。编辑版 accepted=false、production=false，需重新视觉验收。</p><button type="button" data-step="D">返回 D 视频对照与动作预览</button>
        </section>
        <div id="rwProfileExportHost" aria-label="E 当前任务来源校验与运行包导出"></div>
      </div>
      <div class="rw-bottom"><span id="rwMainStatus" class="rw-status" role="status">读取视频及证据…</span><button type="button" id="rwNext">下一步：B 稳定部件 / 证据</button></div>
    </div>`;

  const $ = selector => root.querySelector(selector);
  const video = $('#rwVideo');
  const canvases = [$('#rwEvidenceCanvas'), $('#rwEditCanvas')];
  const contexts = canvases.map(canvas => canvas.getContext('2d'));
  let reference = null, referenceFrames = new Map(), trackFrames = new Map();
  let ready = false, metadataReady = false, videoReady = false, videoError = false;
  let sourceReady = false, sourceErrors = 0, sourceLoaded = 0;
  let currentStep = 'A', selectedPart = 0, selectedPoint = 'hand_near';
  let contextCharacterId = activeId(), observations = {}, undo = null;
  let showOverlay = true, zoom = 1, raf = 0, lastFrameIndex = -1;
  let displayedFrameIndex = null, displayedTransform = null;
  let storageMessage = '', trackWarning = '';
  let repairManifest = null, videoPartsManifest = null, videoPartsError = '', atlasEditor = null;
  let pendingSeek = null, seekTimer = 0;
  let profileEditor = null, profileReady = false, profileError = '', profileVisible = false, profileChecks = null;
  function profileBlocked() { return profileChecks?.numericalChecksPassed === false || profileChecks?.videoFitPassed === false; }
  function showPartVideo() { $('#rwPartVideoWorkspace').open = true; $('#rwEvidenceCanvas').scrollIntoView({block: 'nearest'}); }
  function renderVideoPartEvidence(data) {
    profileChecks = data.checks;
    const host = $('#rwVideoPartReviewItems'); host.replaceChildren();
    if (!data.evidence) { status('#rwVideoPartReviewStatus', '当前 '+data.packageId+' 未提供视频依据；视频拆件仍待完成。'); return; }
    status('#rwVideoPartReviewStatus', data.packageId+' · evidence 与源帧固定 SHA 已核对；仅证明来源关联，候选'+(profileBlocked()?'未通过，禁止写键与导出':'仍待视觉验收')+'。', profileBlocked());
    for (const item of data.evidence.parts ?? data.evidence.items) {
      const row = document.createElement('div'), title = document.createElement('strong'), basis = document.createElement('div'), frames = document.createElement('div'), limits = document.createElement('details'), summary = document.createElement('summary'), limitations = document.createElement('div');
      row.className = 'rw-kv'; title.textContent = item.id; basis.textContent = '可见依据：'+item.visibleBasis+' 遮挡：'+item.occlusion; frames.className = 'rw-keyframes'; summary.textContent = '限制'; limitations.textContent = item.limitations.join('；'); limits.append(summary, limitations);
      for (const entry of item.frames) { const button = document.createElement('button'); button.type = 'button'; button.textContent = String(entry.frame); button.dataset.seekFrame = String(entry.frame); button.title = '定位现有源视频第 '+entry.frame+' 帧；固定源 SHA 已核对'; frames.append(button); }
      row.append(title, basis, frames, limits); host.append(row);
    }
    setStep(currentStep);
  }
  function profileStatus() {
    return profileError ? '任务 Profile 加载 / 来源校验失败：' + profileError
      : profileBlocked() ? '视频参考候选 · 未通过：腿部折叠、根部露口，禁止导出。源包193采样近腿12个triangle×sample翻转，最大残差36.64 px；只读预览，禁止写键，浏览器65采样不能覆盖源包失败。'
      : profileReady ? 'D 已载入 '+profilePackageId+' · 17 张源视频 PNG 同步参考；来源与浏览器检查分别展示，源检查未标失败且浏览器数值通过时才允许非生产导出。'+profileSourceNote
        : 'D 正在校验 '+profilePackageId+' 来源。'+profileSourceNote;
  }
  function syncProfileVisibility() {
    const next = currentStep === 'D' && root.isConnected && root.getClientRects().length > 0;
    if (profileEditor && next !== profileVisible) {
      profileEditor.setVisible(next);
      profileVisible = next;
    }
  }
  function mountProfileEditor() {
    try {
      if (typeof window.RigProfileEditor?.mount !== 'function') throw new Error('Profile 编辑器模块未载入');
      profileEditor = window.RigProfileEditor.mount({
        host: $('#rwProfileEditorHost'), exportHost: $('#rwProfileExportHost'),
        base: asset.base, taskId: asset.taskId, onRequestFrame: seekFrame,
        packageId: profilePackageId, sourceSha: profileSourceSha,
        duration: 2 / 3, frameStart: 68, frameEnd: 84, fps: 24,
        onSourceVerified: renderVideoPartEvidence
      });
      profileEditor.setVisible(false);
      profileEditor.setContext({characterId: contextCharacterId});
      Promise.resolve(profileEditor.ready).then(loaded => {
        profileReady = loaded === true;
        if (!profileReady) { profileError = '请查看模块内具体来源校验错误；导出保持禁用。'; status('#rwVideoPartReviewStatus', '同包依据未通过完整来源校验，不展示可点击证据。', true); }
        setStep(currentStep);
      }).catch(error => { profileError = error.message; setStep(currentStep); });
    } catch (error) {
      profileError = error.message;
      status('#rwProfileEditorHost', profileStatus(), true);
      status('#rwProfileExportHost', profileStatus(), true);
    }
  }
  function mountStableAtlas() {
    const host = $('#rwStableAtlas');
    if (host.dataset.mounted) return;
    host.dataset.mounted = 'true';
    try {
      if (typeof window.RigAtlasEditor?.mountStable !== 'function') throw new Error('稳定部件编辑器未载入');
      window.RigAtlasEditor.mountStable({host, base: asset.base, taskId: asset.taskId, sha256: asset.sha256, onRequestFrame: seekFrame});
    } catch (error) { host.classList.add('rw-error'); host.textContent = '稳定部件不可用：' + error.message; }
  }
  function mountAtlasEvidence() {
    const host = $('#rwAtlasEditor');
    if (!$('#rwAtlasEvidence').open || host.dataset.mounted) return;
    host.dataset.mounted = 'true';
    try {
      if (typeof window.RigAtlasEditor?.mount !== 'function') throw new Error('视频粗片证据编辑器未载入');
      atlasEditor = window.RigAtlasEditor.mount({host, base: asset.base, taskId: asset.taskId, sha256: asset.sha256, onRequestFrame: seekFrame});
      atlasEditor.updateSourceFrame(frameIndex());
    } catch (error) { host.classList.add('rw-error'); host.textContent = '视频粗片证据不可用：' + error.message; }
  }
  $('#rwAtlasEvidence').addEventListener('toggle', mountAtlasEvidence);
  function seekStatus(text, error = false) {
    root.querySelectorAll('[data-seek-status]').forEach(element => {
      element.textContent = text;
      element.classList.toggle('rw-error', error);
    });
  }
  function checkSeek() {
    if (pendingSeek === null || video.seeking || !mediaReady()) return;
    const actual = frameIndex();
    if (actual !== pendingSeek) return;
    clearTimeout(seekTimer);
    seekTimer = 0;
    seekStatus(`已到达源帧 ${actual} · 媒体 ${video.currentTime.toFixed(3)} 秒；画布${displayedFrameIndex === actual ? '已更新' : '待显示'}`);
    pendingSeek = null;
  }

  function status(selector, text, error = false) {
    const element = $(selector);
    element.textContent = text;
    element.classList.toggle('rw-error', error);
  }
  function ownerActive() { return reference?.characterId === asset.characterId && activeId() === asset.characterId && contextCharacterId === asset.characterId; }
  function mediaReady() {
    return metadataReady && videoReady && !videoError && video.readyState >= 2;
  }
  function visible() { return !document.hidden && root.isConnected && root.getClientRects().length > 0; }
  function canvasVisible() { return visible() && (currentStep === 'B' || currentStep === 'C'); }
  function maxFrame() { return reference ? reference.frameCount - 1 : 0; }
  function frameIndex() {
    if (!reference) return 0;
    // 此资产为恒定帧率；currentTime 属于 [n/fps, (n+1)/fps) 的第 n 帧。
    return Math.min(maxFrame(), Math.max(0, Math.floor(video.currentTime * reference.fps + 0.00001)));
  }
  function sourceMatches(value) {
    return object(value) && value.characterId === asset.characterId && value.taskId === asset.taskId && value.sha256 === asset.sha256;
  }
  function sourceInfo() {
    return {characterId: asset.characterId, taskId: asset.taskId, sha256: asset.sha256,
      video: videoUrl, sourcePng: asset.sourcePng, fps: reference.fps,
      width: reference.width, height: reference.height, frameCount: reference.frameCount,
      direction: 'right_front_3q', action: 'walk'};
  }
  function safeThumbnail(path) {
    const base = new URL(asset.base, document.baseURI), url = new URL(path, document.baseURI);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname + 'frames/') || url.search || url.hash) throw new Error('证据图片路径不属于固定视频任务');
    return url.href;
  }
  function validateReference(data) {
    if (!object(data) || data.taskId !== asset.taskId || data.sha256 !== asset.sha256 || data.direction !== 'right_front_3q' || data.action !== 'walk' || (data.characterId !== null && data.characterId !== asset.characterId)) throw new Error('reference.json 来源与固定角色任务不符');
    if (!finite(data.fps) || data.fps <= 0 || data.fps > 240 || !Number.isInteger(data.frameCount) || data.frameCount < 1 || data.frameCount > 100000 || !finite(data.width) || data.width <= 0 || !finite(data.height) || data.height <= 0 || !finite(data.duration) || data.duration <= 0 || !Array.isArray(data.frames) || !data.frames.length) throw new Error('reference.json 视频规格无效');
    const indexes = new Set();
    for (const frame of data.frames) {
      if (!object(frame) || !Number.isInteger(frame.index) || frame.index < 0 || frame.index >= data.frameCount || indexes.has(frame.index) || !finite(frame.time) || !object(frame.landmarks) || typeof frame.file !== 'string') throw new Error('采样帧索引或证据字段无效');
      safeThumbnail(frame.file);
      indexes.add(frame.index);
    }
    const cycle = data.cycle;
    if (!object(cycle) || !Number.isInteger(cycle.startFrame) || !Number.isInteger(cycle.endFrame) || cycle.startFrame < 0 || cycle.endFrame >= data.frameCount || cycle.endFrame <= cycle.startFrame || !Number.isInteger(cycle.lagFrames) || cycle.lagFrames <= 0) throw new Error('周期候选无效');
    if (!Array.isArray(data.repairNeeds) || !data.repairNeeds.length) throw new Error('缺少补画规划');
    for (const repair of data.repairNeeds) {
      if (!object(repair) || !['partId','title','reason','methodNeeded'].every(key => typeof repair[key] === 'string') || !Array.isArray(repair.evidenceFrames) || repair.evidenceFrames.some(index => !Number.isInteger(index) || index < 0 || index >= data.frameCount)) throw new Error('补画规划或证据帧无效');
    }
    return data;
  }
  function cleanPoint(point, index, id) {
    if (!object(point)) throw new Error('观测点不是有效对象');
    const missing = point.x === null && point.y === null;
    if (!missing && (!finite(point.x) || !finite(point.y) || point.x < 0 || point.x > reference.width || point.y < 0 || point.y > reference.height)) throw new Error('观测坐标超出源视频');
    if (!['low','medium','high'].includes(point.confidence)) throw new Error('观测置信度无效');
    const clean = {x: point.x, y: point.y, confidence: id === 'foregroundCentroid' ? point.confidence : 'low', sourceFrameIndex: index};
    for (const key of ['method','evidence','visibility','identityConfidence','note']) if (typeof point[key] === 'string') clean[key] = point[key].slice(0, 2000);
    if (typeof point.visible === 'boolean') clean.visible = point.visible;
    if (finite(point.annotationUncertaintyPx) && point.annotationUncertaintyPx >= 0) clean.annotationUncertaintyPx = point.annotationUncertaintyPx;
    if (id !== 'foregroundCentroid') clean.identityConfidence = 'low';
    return clean;
  }
  function validateObservations(data) {
    if (!object(data)) throw new Error('草稿 observations 格式无效');
    const clean = {};
    for (const [key, points] of Object.entries(data)) {
      const index = Number(key);
      if (!/^(0|[1-9]\d*)$/.test(key) || !Number.isInteger(index) || index < 0 || index > maxFrame() || !object(points)) throw new Error('草稿 source frameIndex 无效');
      clean[index] = {};
      for (const [id, point] of Object.entries(points)) {
        if (!pointIds.has(id)) throw new Error('草稿包含未知观测点');
        clean[index][id] = cleanPoint(point, index, id);
      }
    }
    return clean;
  }
  function initialObservations() {
    const result = {};
    for (const frame of reference.frames) {
      const landmarks = frame.landmarks;
      result[frame.index] = {};
      for (const {id} of pointDefinitions) {
        const point = landmarks[id] || trackFrames.get(frame.index)?.landmarks?.[id];
        if (!point) continue;
        const evidenceFile = landmarks[id] ? 'reference.json' : 'tracks.json';
        result[frame.index][id] = cleanPoint({...point, evidence: `${evidenceFile} / source frameIndex ${frame.index}`}, frame.index, id);
      }
    }
    return result;
  }
  function loadDraft() {
    observations = reference ? initialObservations() : {};
    undo = null;
    storageMessage = '';
    if (!reference) return;
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw !== null) {
        const draft = JSON.parse(raw);
        if (draft.schemaVersion !== 2 || !sourceMatches(draft.source)) throw new Error('草稿来源或版本不符');
        observations = validateObservations(draft.observations);
      }
    } catch (error) {
      storageMessage = '本地草稿无法读取或校验失败，显示原始分析；未覆盖原记录。' + error.message;
    }
  }
  function saveDraft() {
    if (!ready || !ownerActive()) return false;
    try {
      const draft = {schemaVersion: 2, source: sourceInfo(), observations: validateObservations(observations)};
      localStorage.setItem(storageKey, JSON.stringify(draft));
      storageMessage = '当前固定角色任务草稿已保存到本机。';
      return true;
    } catch (error) {
      storageMessage = '本机保存失败，修改仅留在当前页面；可导出备份。' + error.message;
      return false;
    } finally { status('#rwDraftStatus', storageMessage); }
  }
  function syncCharacter() {
    const nextCharacterId = activeId();
    if (nextCharacterId !== contextCharacterId) profileEditor?.setContext({characterId: nextCharacterId});
    contextCharacterId = nextCharacterId;
    $('#rwEnableEdit').checked = false;
    loadDraft();
    status('#rwCharacterNotice', reference?.characterId == null
      ? `任务：${asset.taskId}。reference / profile 的 characterId=null，角色归属未核实；原图仅为外观参考。C 原角色观测草稿仍只读；D 允许本任务 Profile 动作编辑、保存，E 允许来源校验后的非生产任务运行包导出，均不归属当前角色。B 的7件候选审阅不等于 D Profile 或生产验收；不覆盖原图。`
      : ownerActive()
        ? `固定来源：${asset.characterId} / ${asset.taskId}。已载入分析可直接查看；不要求用户完成专业标关节点。`
        : `当前角色：${contextCharacterId}。C 原角色观测草稿只读；D / E 仍是固定任务 ${asset.taskId} 的 Profile 编辑和非生产导出，不转移角色归属。`);
    status('#rwDraftStatus', storageMessage || '原始分析已载入；进阶修正不是使用前提。');
    renderTracks();
    updateInspector();
    updateControls();
    drawPaused();
  }
  function updateControls() {
    const loaded = ready && mediaReady();
    root.querySelectorAll('[data-play]').forEach(button => {
      button.disabled = !loaded;
      button.textContent = video.paused ? '播放源视频' : '暂停源视频';
    });
    $('#rwTimeline').disabled = !loaded;
    $('#rwEnableEdit').disabled = !loaded || !ownerActive();
    $('#rwClearPoint').disabled = !loaded || !ownerActive() || !video.paused || video.seeking || !observations[displayedFrameIndex]?.[selectedPoint];
    $('#rwUndo').disabled = !loaded || !ownerActive() || !undo;
    $('#rwExportDraft').disabled = !loaded || !ownerActive() || !sourceReady;
    if (!ownerActive()) status('#rwExportStatus', '只读专用资产：不能将本视频导出为其他角色。');
    else if (!ready) status('#rwExportStatus', '分析数据未就绪，禁止导出。');
    else if (!mediaReady()) status('#rwExportStatus', '视频 metadata / loadeddata 未就绪或读取失败，禁止导出。');
    else if (!sourceReady) status('#rwExportStatus', sourceErrors ? 'source PNG 读取失败，禁止导出。' : 'source PNG 尚未就绪。');
    else status('#rwExportStatus', '可以导出观测草稿；不是 Spine 运行包。');
  }
  function setStep(id, focus = false) {
    if (!steps.some(([key]) => key === id)) return;
    stopLoop();
    currentStep = id;
    const labels = {A: mediaReady() ? '视频可查看' : '读取视频', B: '7件候选待审 / 未绑定', C: '轮廓证据 / 周期参考', D: profileError ? 'Profile 来源校验失败' : profileBlocked() ? '候选未通过 / 只读预览' : profileReady ? '同步对照 / 可选编辑' : 'Profile 来源校验中', E: profileBlocked() ? '候选未通过 / 禁止导出' : '来源校验 / 非生产导出'};
    const profileArea = $('#rwProfileWorkspace');
    profileArea.hidden = !['D','E'].includes(id);
    profileArea.setAttribute('aria-hidden', String(!['D','E'].includes(id)));
    for (const [key] of steps) {
      const active = id === key, tab = $('#rwTab' + key);
      tab.setAttribute('aria-selected', String(active));
      tab.setAttribute('aria-current', active ? 'step' : 'false');
      tab.tabIndex = active ? 0 : -1;
      tab.querySelector('span').textContent = active ? '当前步骤 · ' + labels[key] : labels[key];
      const panel = $('#rwPanel' + key);
      panel.hidden = !active;
    }
    if (id === 'D' || id === 'E') video.pause();
    syncProfileVisibility();
    root.querySelectorAll('[data-profile-status]').forEach(element => { element.textContent = profileStatus(); element.classList.toggle('rw-error', profileBlocked()); });
    $('#rwNext').textContent = `${id === 'E' ? '返回' : '下一步：'}${nextSteps[id]} ${steps.find(([key]) => key === nextSteps[id])[1]}`;
    if (focus) $('#rwTab' + id).focus();
    drawPaused();
    schedule();
  }
  function seekFrame(index) {
    if (!ready || !metadataReady || videoError || !Number.isInteger(index) || index < 0 || index > maxFrame()) {
      seekStatus('跳帧未执行：视频规格/分析未就绪，或目标帧无效。', true);
      return;
    }
    video.pause();
    clearTimeout(seekTimer);
    pendingSeek = index;
    displayedFrameIndex = null;
    seekStatus(`正在请求源帧 ${index}；尚未确认到达。`);
    try {
      const time = (index + 0.05) / reference.fps;
      video.currentTime = Math.min(time, video.duration - 0.00001);
      $('#rwTimeline').value = String(index);
      seekTimer = setTimeout(() => {
        if (pendingSeek !== index) return;
        const ranges = Array.from({length: video.seekable.length}, (_, i) =>
          `${video.seekable.start(i).toFixed(3)}..${video.seekable.end(i).toFixed(3)}`).join(', ') || '空';
        seekStatus(`跳帧未确认：目标 ${index}，媒体 ${video.currentTime.toFixed(3)} 秒，seeking=${video.seeking}，readyState=${video.readyState}，seekable=${ranges}。不将旧画面当成目标帧。`, true);
        pendingSeek = null;
        seekTimer = 0;
      }, 8000);
      drawPaused();
      checkSeek();
    } catch (error) {
      clearTimeout(seekTimer); seekTimer = 0; pendingSeek = null;
      seekStatus('跳帧失败：' + error.message, true);
    }
    updateControls();
  }
  function transform(canvas) {
    const scale = Math.min(canvas.width / reference.width, canvas.height / reference.height) * zoom;
    return {scale, x: (canvas.width - reference.width * scale) / 2, y: (canvas.height - reference.height * scale) / 2};
  }
  function draw() {
    if (!ready || !mediaReady() || video.seeking || !canvasVisible()) return;
    const index = frameIndex(), which = currentStep === 'B' ? 0 : 1;
    const canvas = canvases[which], ctx = contexts[which], view = transform(canvas);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(video, view.x, view.y, reference.width * view.scale, reference.height * view.scale);
    if (which === 1 && showOverlay) {
      for (const {id} of pointDefinitions) {
        const point = observations[index]?.[id];
        if (!point || !finite(point.x) || !finite(point.y)) continue;
        const x = view.x + point.x * view.scale, y = view.y + point.y * view.scale;
        ctx.beginPath();
        ctx.fillStyle = id === selectedPoint ? '#ffca58' : id === 'foregroundCentroid' ? '#6fd7dd' : '#ff788f';
        ctx.strokeStyle = '#111'; ctx.lineWidth = 2;
        ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.font = '12px sans-serif'; ctx.fillStyle = '#fff'; ctx.fillText(id, x + 8, y - 8);
      }
    }
    displayedFrameIndex = index;
    displayedTransform = view;
    renderTime(index);
    checkSeek();
    updateControls();
  }
  function drawPaused() {
    if (video.paused && !video.seeking) draw();
  }
  function stopLoop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
  function tick() {
    raf = 0;
    if (video.paused || video.ended || video.seeking || !ready || !mediaReady() || !canvasVisible()) return;
    draw();
    raf = requestAnimationFrame(tick);
  }
  function schedule() {
    if (!raf && !video.paused && !video.seeking && ready && mediaReady() && canvasVisible()) raf = requestAnimationFrame(tick);
  }
  function renderTime(index = frameIndex()) {
    $('#rwTimeline').value = String(index);
    root.querySelectorAll('[data-time]').forEach(element => {
      element.textContent = `source frameIndex ${index} / ${maxFrame()} · ${video.currentTime.toFixed(3)} / ${video.duration.toFixed(3)} 秒`;
    });
    if (index !== lastFrameIndex) {
      lastFrameIndex = index;
      if (atlasEditor) atlasEditor.updateSourceFrame(index);
      updateInspector();
      if ($('#rwVideoPartsSource').value === 'current_frame') renderVideoParts(index);
      renderCurrentContours(index);
      root.querySelectorAll('[data-seek-frame]').forEach(button => button.setAttribute('aria-current', String(Number(button.dataset.seekFrame) === index)));
    }
  }
  function renderParts() {
    const list = $('#rwPartsList');
    list.replaceChildren();
    reference.repairNeeds.forEach((repair, index) => {
      const item = document.createElement('li'), button = document.createElement('button');
      button.type = 'button'; button.textContent = repair.title;
      button.setAttribute('aria-pressed', String(index === selectedPart));
      button.addEventListener('click', () => { selectedPart = index; renderParts(); renderEvidence(); });
      item.append(button); list.append(item);
    });
    const repair = reference.repairNeeds[selectedPart];
    status('#rwPartTitle', repair.title);
    status('#rwPartReason', `部位：${repair.partId}\n视频依据：${repair.reason}`);
    status('#rwPartMethod', `所需补画：${repair.methodNeeded}\n正式制作：未通过（原分析：${repair.status || '未完成'}）`);
    renderVideoParts();
    renderRepair(repair.partId);
  }
  function videoPartKindsFor(repair) {
    if (!repair) return [];
    if (repair.partId === 'arm_near' || repair.partId === 'arm_far') return ['arm'];
    if (repair.partId === 'leg_near' || repair.partId === 'leg_far') return ['leg'];
    return [];
  }
  function renderVideoParts(index = frameIndex()) {
    const host = $('#rwVideoParts');
    host.replaceChildren();
    const repair = reference?.repairNeeds?.[selectedPart];
    const allowedKinds = videoPartKindsFor(repair);
    const source = $('#rwVideoPartsSource').value;
    const frameIndexes = repair?.evidenceFrames || [];
    const parts = videoPartsManifest?.parts.filter(part => allowedKinds.includes(part.kind) && (
      source === 'current_frame' ? part.sourceFrame === index :
      source === 'continuous_068_084' ? part.evidenceGroup === source && part.sourceFrame >= 68 && part.sourceFrame <= 84 :
      part.evidenceGroup === 'sampled_poses' && frameIndexes.includes(part.sourceFrame)
    )) || [];
    const range = source === 'current_frame' ? `当前源帧 ${index}` : source === 'continuous_068_084' ? '连续68–84（17帧范围）' : `原采样证据（当前事项源帧：${frameIndexes.join('、') || '无'}）`;
    for (const part of parts) {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.seekFrame = String(part.sourceFrame); button.title = `源帧 ${part.sourceFrame} · ${part.id} · 可见姿态片，不是绑定件`;
      button.setAttribute('aria-current', String(part.sourceFrame === index));
      const image = document.createElement('img'); image.src = asset.base + 'video_parts_v1/' + part.file; image.alt = button.title;
      image.addEventListener('error', () => { image.hidden = true; button.title = '切片图片加载失败：' + part.id; });
      const small = document.createElement('small'); small.textContent = `帧${part.sourceFrame} · ${part.kind === 'arm' ? '手臂' : '腿'} · 身份未知 · 仅可见片`;
      const labels = [];
      if (part.id.includes('_chest_') || part.pose === 'chest_crossing') labels.push('胸前臂');
      if (part.id.includes('_fragment_') || part.pose === 'crossing_fragment') labels.push('遮挡残片');
      labels.push(part.shapeReview === 'ai_foot_shape_review_required' ? '脚形待审' : '粗边界待审');
      const review = document.createElement('small'); review.textContent = labels.join(' · ');
      button.append(image, small, review); host.append(button);
    }
    const prefix = `选中源范围：${range}；部件数量：${parts.length}。A/B不是近远侧，解剖身份未知。`;
    if (!allowedKinds.length) {
      status('#rwVideoPartsStatus', prefix + '当前躯干事项无可归属姿态片；保持证据缺失，不用臂腿片冒充躯干补画。' + (videoPartsError ? '读取失败：' + videoPartsError : ''), Boolean(videoPartsError));
    } else if (!videoPartsManifest) {
      status('#rwVideoPartsStatus', prefix + (videoPartsError ? '视频姿态片读取失败：' + videoPartsError : '正在读取视频姿态片…'), Boolean(videoPartsError));
    } else {
      status('#rwVideoPartsStatus', prefix + (parts.length ? '保留遮挡缺失，不补造、不跨帧合并，不是可复用绑定件。' : '当前事项暂无匹配姿态片；保持证据缺失。'));
    }
  }
  function renderCurrentContours(index = frameIndex()) {
    const host = $('#rwCurrentContours');
    const exists = videoPartsManifest?.parts.some(part => part.sourceFrame === index) || false;
    host.hidden = !exists;
    if (!exists) { host.replaceChildren(); delete host.dataset.sourceFrame; return; }
    if (host.dataset.sourceFrame === String(index)) return;
    host.dataset.sourceFrame = String(index);
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.seekFrame = String(index);
    button.setAttribute('aria-current', 'true');
    button.setAttribute('aria-label', `当前源帧${index}轮廓审阅图，点击同步源视频`);
    button.style.width = '100%';
    const image = document.createElement('img');
    image.width = 864; image.height = 480; image.className = 'rw-video';
    image.alt = `源帧${index}轮廓审阅图（864×480，非绑定资产）`;
    const caption = document.createElement('small');
    caption.textContent = `当前源帧 ${index} · 轮廓审阅图（864×480）· 点击同步源视频；仅审阅，不代表轮廓已验收。`;
    image.addEventListener('error', () => { image.hidden = true; caption.textContent = `源帧 ${index} 轮廓审阅图读取失败；仍可点击请求源视频帧。`; });
    image.src = asset.base + 'video_parts_v1/contours_' + String(index).padStart(3, '0') + '.jpg';
    button.append(image, caption); host.replaceChildren(button);
  }
  async function loadVideoParts() {
    try {
      const response = await fetch(asset.base + 'video_parts_v1/manifest.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (data.taskId !== asset.taskId || data.sourceVideoSha256 !== '8fc0f8406d6a258640b65d34c5ad7fb0e35f231131d7eec945781dd9d93343e5' || data.characterId !== null || data.promotedToRuntime !== false || data.status !== 'video_visible_pose_fragments_not_reusable_rig_parts') throw new Error('视频姿态片来源或状态无效');
      if (!Array.isArray(data.parts) || data.parts.length > 1000) throw new Error('姿态片列表无效');
      for (const part of data.parts) {
        if (!/^f\d{3}_(?:arm|leg)_[AB](?:_chest|_fragment)?_visible$/.test(part.id) || part.notReusableRigPart !== true || part.anatomicalIdentity !== 'unknown' || part.file !== part.id + '.png') throw new Error('视频姿态片边界契约无效');
        if (!Number.isInteger(part.sourceFrame) || !part.polygonSourcePixels?.length) throw new Error('视频姿态片帧记录无效');
        if (!['arm','leg'].includes(part.kind) || !part.id.startsWith(`f${String(part.sourceFrame).padStart(3, '0')}_${part.kind}_`)) throw new Error('视频姿态片部位或源帧不符');
        const continuous = part.sourceFrame >= 68 && part.sourceFrame <= 84;
        if (part.evidenceGroup !== (continuous ? 'continuous_068_084' : 'sampled_poses')) throw new Error('视频姿态片证据分组无效');
        const footReview = part.kind === 'leg' && part.sourceFrame >= 74 && part.sourceFrame <= 77;
        if (part.shapeReview !== (footReview ? 'ai_foot_shape_review_required' : 'coarse_boundary_review_required')) throw new Error('视频姿态片形状审阅状态无效');
      }
      videoPartsManifest = data;
      videoPartsError = '';
      renderVideoParts(); renderCurrentContours();
    } catch (error) {
      videoPartsManifest = null; videoPartsError = error.message;
      renderVideoParts(); renderCurrentContours();
    }
  }
  async function loadCycleReview() {
    try {
      const response = await fetch(asset.base + 'video_parts_v1/cycle_review/sources.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (data.taskId !== asset.taskId || data.sourceVideoSha256 !== asset.sha256 || data.characterId !== null || data.notRuntimeAsset !== true || data.status !== 'visually_reviewed_occlusion_evidence_not_rig' || !Array.isArray(data.frames) || data.frames.length !== 17 || !Array.isArray(data.assetDecisions) || data.assetDecisions.some(text => typeof text !== 'string')) throw new Error('连续审阅来源/状态无效');
      const host = $('#rwCycleFrames');
      host.replaceChildren();
      for (const [offset, frame] of data.frames.entries()) {
        const index = 68 + offset;
        if (frame.sourceFrame !== index || frame.sourceFile !== `source_${index.toString().padStart(3,'0')}.png` || frame.identity !== 'unknown' || frame.notRuntimeAsset !== true || !object(frame.manualObservations) || typeof frame.manualObservations.note !== 'string') throw new Error('连续帧记录无效');
      }
      for (const frame of data.frames) {
        const button = frameButton(frame.sourceFrame, `帧${frame.sourceFrame}${frame.sourceFrame === 84 ? ' · 端点候选' : ''}`);
        const image = document.createElement('img');
        image.src = asset.base + 'video_parts_v1/cycle_review/' + frame.sourceFile;
        image.alt = `真实源帧${frame.sourceFrame}`; image.loading = 'lazy';
        image.addEventListener('error', () => { image.hidden = true; note.textContent = '源帧图读取失败；仍可请求视频跳帧。'; });
        const note = document.createElement('small'); note.textContent = frame.manualObservations.note;
        button.prepend(image); button.append(note); host.append(button);
      }
      $('#rwCycleDecisions').replaceChildren();
      for (const text of data.assetDecisions) {
        const paragraph = document.createElement('p'); paragraph.textContent = text;
        $('#rwCycleDecisions').append(paragraph);
      }
      status('#rwCycleStatus', '17张连续审阅样本，84为重复端点候选；已记录可见遮挡与AI形变，不代表17帧周期、解剖身份或动作拟合。点击请求实际视频帧。');
    } catch (error) {
      $('#rwCycleFrames').replaceChildren();
      status('#rwCycleStatus', '连续帧审阅读取失败：' + error.message, true);
    }
  }
  function renderRepair(partId) {
    const image = $('#rwRepairImage');
    const part = repairManifest?.parts.find(item => item.id === partId);
    image.hidden = !part;
    if (!part) { image.removeAttribute('src'); status('#rwRepairStatus', '返工候选尚未载入；不使用旧运行动画代替。'); return; }
    image.src = asset.base + 'image2_repairs/rework_v3/' + part.file;
    status('#rwRepairStatus', `原图可见像素保留；新增隐藏搭接 ${part.addedPixels} px。\n仍沿用静态分区，不是视频重拆；完整隐藏轮廓与前摆姿态未解决，动态未验收。`);
  }
  async function loadRepairs() {
    try {
      const response = await fetch(asset.base + 'image2_repairs/rework_v3/manifest.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (data.taskId !== asset.taskId || data.characterId !== null || data.sourceSha256 !== 'a25475d82eec03a42ae89a32026779ab99eb0e32f2a0232ade7302ca844a3a10' || data.promotedToRuntime !== false || !Array.isArray(data.parts)) throw new Error('来源或状态无效');
      for (const part of data.parts) if (!['body','head','arm_near','arm_far','leg_near','leg_far'].includes(part.id) || part.file !== part.id + '.png' || !Number.isInteger(part.addedPixels) || part.addedPixels < 0) throw new Error('部件契约无效');
      repairManifest = data;
      if (reference) renderRepair(reference.repairNeeds[selectedPart].partId);
    } catch (error) { status('#rwRepairStatus', '局部返工读取失败：' + error.message, true); }
  }
  function frameButton(index, label) {
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.seekFrame = String(index);
    button.textContent = label || `帧 ${index}`;
    button.setAttribute('aria-current', String(index === frameIndex()));
    button.title = `跳回 source frameIndex ${index} · ${(index / reference.fps).toFixed(3)} 秒`;
    return button;
  }
  function renderEvidence() {
    const host = $('#rwEvidenceFrames'); host.replaceChildren();
    for (const index of [...new Set(reference.repairNeeds[selectedPart].evidenceFrames)]) {
      const button = frameButton(index), frame = referenceFrames.get(index);
      if (frame) {
        const image = document.createElement('img');
        image.alt = `采样证据 source frameIndex ${index}`; image.loading = 'lazy';
        const state = document.createElement('small'); state.textContent = '采样图；点击跳转实际视频';
        image.addEventListener('error', () => { state.textContent = `帧 ${index} 缩略图失败；仍可跳转视频`; state.className = 'rw-error'; });
        image.src = safeThumbnail(frame.file); button.prepend(image); button.append(state);
      }
      host.append(button);
    }
  }
  function renderPointList() {
    const host = $('#rwPointList'); host.replaceChildren();
    for (const {id, label} of pointDefinitions) {
      const item = document.createElement('li'), button = document.createElement('button');
      button.type = 'button'; button.textContent = label;
      button.setAttribute('aria-pressed', String(id === selectedPoint));
      button.addEventListener('click', () => { selectedPoint = id; renderPointList(); updateInspector(); drawPaused(); });
      item.append(button); host.append(item);
    }
  }
  function renderTracks() {
    const host = $('#rwTracks'); host.replaceChildren();
    if (!reference) return;
    for (const {id} of pointDefinitions) {
      const row = document.createElement('div'), label = document.createElement('span'), bar = document.createElement('div');
      row.className = 'rw-track'; label.textContent = id === 'foregroundCentroid' ? '前景重心' : id;
      bar.className = 'rw-track-bar';
      for (const [key, points] of Object.entries(observations)) {
        if (!points[id]) continue;
        const marker = frameButton(Number(key), '');
        marker.textContent = ''; marker.dataset.missing = String(points[id].x === null);
        marker.setAttribute('aria-label', `${id} 源帧 ${key}${points[id].x === null ? ' 缺失' : ''}`);
        marker.style.left = `${Number(key) / Math.max(1, maxFrame()) * 100}%`;
        bar.append(marker);
      }
      row.append(label, bar); host.append(row);
    }
    const keyframes = $('#rwKeyFrames'); keyframes.replaceChildren();
    const manualFrames = reference.frames.filter(frame => Object.values(frame.landmarks).some(point => point?.method === 'manual_grid_review')).map(frame => frame.index);
    for (const index of [...new Set([...manualFrames, reference.cycle.startFrame, reference.cycle.endFrame])]) keyframes.append(frameButton(index, `${index} ${manualFrames.includes(index) ? '已有审阅' : '周期候选'}`));
  }
  function updateInspector() {
    const index = frameIndex(), point = observations[index]?.[selectedPoint];
    status('#rwPointTitle', pointDefinitions.find(point => point.id === selectedPoint).label);
    status('#rwPointValue', `frameIndex：${index}\npoint：${selectedPoint}\nx：${point?.x ?? 'null'}\ny：${point?.y ?? 'null'}\nconfidence：${point?.confidence || '无当前帧记录'}\n近远侧身份：${selectedPoint === 'foregroundCentroid' ? '不适用（轮廓重心）' : 'low / 暂定'}`);
    status('#rwPointEvidence', `evidence：${point?.evidence || '当前帧无证据，不使用邻近帧冒充'}\nmethod：${point?.method || '未记录'}\nvisibility：${point?.visibility || (point?.x == null ? '缺失 / 未审阅' : '未单独判定')}\n${point?.note || ''}`);
  }
  function canEdit() {
    if (activeId() !== contextCharacterId) { syncCharacter(); return false; }
    return ready && mediaReady() && ownerActive() && video.paused && !video.seeking && displayedFrameIndex !== null && displayedFrameIndex === frameIndex();
  }
  function replacePoint(point) {
    const index = displayedFrameIndex;
    undo = {index, id: selectedPoint, previous: observations[index]?.[selectedPoint] ? clone(observations[index][selectedPoint]) : null};
    observations[index] ||= {};
    observations[index][selectedPoint] = cleanPoint(point, index, selectedPoint);
    saveDraft(); renderTracks(); updateInspector(); drawPaused(); updateControls();
  }
  function persistPoint(event) {
    if (!$('#rwAdvanced').open || !$('#rwEnableEdit').checked || !canEdit() || !displayedTransform) return;
    const rect = canvases[1].getBoundingClientRect(), view = displayedTransform;
    const x = ((event.clientX - rect.left) * canvases[1].width / rect.width - view.x) / view.scale;
    const y = ((event.clientY - rect.top) * canvases[1].height / rect.height - view.y) / view.scale;
    if (!finite(x) || !finite(y) || x < 0 || y < 0 || x > reference.width || y > reference.height) return;
    replacePoint({x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), confidence: 'low', identityConfidence: 'low', evidence: `manual_canvas / source frameIndex ${displayedFrameIndex}`, method: 'optional_manual_correction', visibility: 'unresolved', note: '页面进阶修正；非已验收解剖关节，近远侧身份未确认'});
  }
  function clearPoint() {
    if (!canEdit()) return;
    replacePoint({x: null, y: null, confidence: 'low', evidence: `manual_clear / source frameIndex ${displayedFrameIndex}`, method: 'manual_clear', visibility: 'unresolved', note: '用户设为缺失；不插值'});
  }
  function undoEdit() {
    if (!undo || !ready || !ownerActive()) return;
    const {index, id, previous} = undo;
    if (previous) observations[index][id] = previous;
    else { delete observations[index][id]; if (!Object.keys(observations[index]).length) delete observations[index]; }
    undo = null;
    saveDraft(); renderTracks(); updateInspector(); drawPaused(); updateControls();
  }
  async function togglePlayback() {
    if (!ready || !mediaReady()) return;
    if (!video.paused) { video.pause(); return; }
    try { await video.play(); }
    catch (error) { status('#rwVideoStatus', '播放失败：' + error.message, true); status('#rwMainStatus', '源视频播放失败：' + error.message, true); }
    updateControls();
  }
  function exportDraft() {
    if (activeId() !== contextCharacterId) syncCharacter();
    if (!ready || !mediaReady() || !ownerActive() || !sourceReady) { updateControls(); return; }
    try {
      const payload = {schemaVersion: 2, source: {...sourceInfo(), metadataDuration: video.duration}, coordinateSpace: 'source pixels, origin top-left', frameIndexConvention: 'zero-based integer, floor(currentTime * fps), constant-frame-rate source', cycleCandidate: reference.cycle, repairNeeds: reference.repairNeeds, observations: validateObservations(observations), limitations: reference.limitations || [], status: 'video_observation_draft_only', notSpineRuntimeData: true, animationFitted: false, inpaintExecuted: false, tracksLoaded: trackFrames.size};
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'}));
      const link = document.createElement('a'); link.href = url; link.download = 'legacy_six_view_right_front_walk_observations.json'; link.hidden = true;
      root.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status('#rwExportStatus', '已发起观测草稿下载。不是 Spine JSON；无已拟合动画、无补画图集。');
    } catch (error) { status('#rwExportStatus', '导出失败：' + error.message, true); }
  }
  function checkMediaIdentity() {
    if (!reference || !metadataReady) return;
    if (video.videoWidth !== reference.width || video.videoHeight !== reference.height || Math.abs(video.duration - reference.duration) > 1 / reference.fps) throw new Error('实际视频尺寸或时长与固定任务分析不符');
  }
  async function loadData() {
    try {
      if (contexts.some(ctx => !ctx)) throw new Error('浏览器无法创建 Canvas 2D 上下文');
      const response = await fetch(asset.base + 'reference.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`reference.json：HTTP ${response.status}`);
      reference = validateReference(await response.json());
      referenceFrames = new Map(reference.frames.map(frame => [frame.index, frame]));
      try {
        const trackResponse = await fetch(asset.base + 'tracks.json', {cache: 'no-store'});
        if (!trackResponse.ok) throw new Error(`HTTP ${trackResponse.status}`);
        const data = await trackResponse.json();
        if (!Array.isArray(data.tracks)) throw new Error('tracks 字段无效');
        for (const track of data.tracks) {
          if (!object(track) || !Number.isInteger(track.index) || !referenceFrames.has(track.index) || !object(track.landmarks)) throw new Error('tracks 帧索引无效');
          trackFrames.set(track.index, track);
        }
      } catch (error) { trackFrames.clear(); trackWarning = 'tracks.json 不可用，保留 reference.json 证据：' + error.message; }
      checkMediaIdentity();
      ready = true;
      $('#rwTimeline').max = String(maxFrame());
      status('#rwCycleReference', `视频周期候选：${reference.cycle.startFrame}..${reference.cycle.endFrame} · ${reference.cycle.lagFrames} 帧 / ${reference.fps} fps · ${reference.cycle.confidence}；仅观测与相位参考，不是已拟合动作。${reference.cycle.reason || ''}`);
      renderParts(); renderEvidence(); renderPointList(); syncCharacter();
      const reviewed = reference.frames.filter(frame => Object.values(frame.landmarks).some(point => point?.method === 'manual_grid_review')).length;
      status('#rwMainStatus', `已载入 ${reference.frames.length} 个采样帧，${reviewed} 个已有低可信手工审阅帧；C 仅观测证据，D 为任务 Profile 编辑（非视频精确拟合）。${trackWarning}`, Boolean(trackWarning));
      status('#rwExportSummary', `周期候选：${reference.cycle.startFrame}..${reference.cycle.endFrame}，${reference.cycle.lagFrames} 帧 / ${reference.fps} fps，${reference.cycle.confidence}\n${reference.cycle.reason || ''}\n补画事项：${reference.repairNeeds.length} 项待处理\n${reference.repairNeeds.map(repair => '• ' + repair.title).join('\n')}`);
      drawPaused(); schedule(); updateControls();
    } catch (error) {
      ready = false; stopLoop();
      status('#rwMainStatus', '分析读取 / 校验失败：' + error.message, true); updateControls();
    }
  }

  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.step) setStep(button.dataset.step);
    if (button.hasAttribute('data-show-part-video')) showPartVideo();
    if (button.hasAttribute('data-seek-frame')) { if (button.closest('#rwVideoPartReview')) showPartVideo(); seekFrame(Number(button.dataset.seekFrame)); }
    if (button.hasAttribute('data-play')) togglePlayback();
    if (button.hasAttribute('data-fit')) { zoom = 1; root.querySelectorAll('[data-zoom]').forEach(select => { select.value = '1'; }); drawPaused(); }
    if (button.id === 'rwNext') setStep(nextSteps[currentStep]);
    if (button.id === 'rwOverlay') { showOverlay = !showOverlay; button.textContent = `证据点：${showOverlay ? '显示' : '隐藏'}`; button.setAttribute('aria-pressed', String(showOverlay)); drawPaused(); }
    if (button.id === 'rwClearPoint') clearPoint();
    if (button.id === 'rwUndo') undoEdit();
    if (button.id === 'rwExportDraft') exportDraft();
  });
  root.querySelectorAll('[data-zoom]').forEach(select => select.addEventListener('change', () => {
    zoom = Number(select.value); root.querySelectorAll('[data-zoom]').forEach(other => { other.value = select.value; }); drawPaused();
  }));
  $('#rwVideoPartsSource').addEventListener('change', () => { renderVideoParts(); renderCurrentContours(); });
  $('#rwTimeline').addEventListener('input', event => seekFrame(Number(event.target.value)));
  canvases[1].addEventListener('click', persistPoint);
  $('.rw-tabs').addEventListener('keydown', event => {
    const tab = event.target.closest('[data-step]');
    if (!tab || event.ctrlKey || event.metaKey || event.altKey || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const index = steps.findIndex(([id]) => id === tab.dataset.step);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? steps.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : steps.length - 1)) % steps.length;
    setStep(steps[next][0], true);
  });
  video.addEventListener('loadedmetadata', () => {
    metadataReady = finite(video.duration) && video.duration > 0 && video.videoWidth > 0 && video.videoHeight > 0;
    try { checkMediaIdentity(); }
    catch (error) { videoError = true; status('#rwVideoStatus', error.message, true); updateControls(); return; }
    status('#rwVideoMeta', `${video.videoWidth}×${video.videoHeight} · ${video.duration.toFixed(3)} 秒 · 帧率取任务分析`);
    status('#rwVideoStatus', 'metadata 已读取；等待 loadeddata 才可用。'); updateControls();
  });
  video.addEventListener('loadeddata', () => {
    videoReady = video.readyState >= 2;
    if (videoError) return;
    status('#rwVideoStatus', '源视频 loadeddata 已就绪。'); drawPaused(); schedule(); updateControls();
  });
  video.addEventListener('error', () => {
    videoError = true; videoReady = false; displayedFrameIndex = null; stopLoop();
    status('#rwVideoStatus', `source.mp4 读取失败（media error ${video.error?.code || '未知'}），没有用采样图片代替。`, true);
    status('#rwMainStatus', '真实源视频读取失败，请检查任务文件与本地服务。', true); updateControls();
  });
  video.addEventListener('play', () => { updateControls(); schedule(); });
  video.addEventListener('playing', schedule);
  video.addEventListener('canplay', () => { drawPaused(); checkSeek(); schedule(); updateControls(); });
  video.addEventListener('waiting', stopLoop);
  video.addEventListener('pause', () => { stopLoop(); drawPaused(); updateControls(); });
  video.addEventListener('ended', () => { stopLoop(); drawPaused(); updateControls(); });
  video.addEventListener('seeking', () => { displayedFrameIndex = null; stopLoop(); updateControls(); });
  video.addEventListener('seeked', () => { drawPaused(); checkSeek(); schedule(); updateControls(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stopLoop(); video.pause(); profileEditor?.pause(); }
    syncProfileVisibility();
    if (!document.hidden) { drawPaused(); schedule(); }
  });
  window.addEventListener('cotton-character-changed', () => { video.pause(); syncCharacter(); });
  // 外层工作区的 class/hidden 切换必须停止循环；回到此页时暂停态按需重绘。
  const visibilityObserver = new MutationObserver(() => {
    syncProfileVisibility();
    if (!visible()) { stopLoop(); video.pause(); } else { drawPaused(); schedule(); }
  });
  for (let element = root; element; element = element.parentElement) visibilityObserver.observe(element, {attributes: true, attributeFilter: ['class','style','hidden']});

  root.querySelectorAll('[data-source-image]').forEach(image => {
    const indicator = image.nextElementSibling;
    image.addEventListener('load', () => {
      sourceLoaded++;
      indicator.textContent = `source PNG 已载入 · ${image.naturalWidth}×${image.naturalHeight} · 完整原图`;
      sourceReady = sourceLoaded === root.querySelectorAll('[data-source-image]').length && sourceErrors === 0;
      updateControls();
    });
    image.addEventListener('error', () => {
      sourceErrors++; sourceReady = false;
      indicator.textContent = 'source PNG 读取失败：' + asset.sourcePng; indicator.classList.add('rw-error'); updateControls();
    });
    image.src = asset.sourcePng;
  });
  const nav = document.querySelector('.workflow-tabs');
  if (nav) {
    const buttons = [...nav.querySelectorAll('[data-tab="spineRig"]')];
    const button = buttons[0] || document.createElement('button');
    buttons.slice(1).forEach(duplicate => duplicate.remove());
    button.type = 'button'; button.dataset.tab = 'spineRig'; button.textContent = '05 骨骼与动作制作'; nav.append(button);
  }
  mountStableAtlas();
  mountProfileEditor();
  renderPointList(); syncCharacter(); setStep('A');
  $('#rwRepairImage').addEventListener('error', () => { $('#rwRepairImage').hidden = true; status('#rwRepairStatus', '部件 PNG 读取失败；候选不可用。', true); });
  video.src = videoUrl;
  loadData();
  loadRepairs();
  loadVideoParts();
  loadCycleReview();
  if (window.location.hash === '#spineRig') window.goToTab?.('spineRig');
})();
