/* Video -> selected PNG frames -> Spine attachment animations. No user asset deletion. */
(() => {
  'use strict';
  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) { crc ^= byte; for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1)); }
    return (crc ^ -1) >>> 0;
  }
  function zip(entries) {
    const enc = new TextEncoder(), local = [], central = [];
    const u16 = n => [n & 255, n >>> 8 & 255], u32 = n => [...u16(n), ...u16(n >>> 16)];
    let offset = 0;
    for (const item of entries) {
      const name = enc.encode(item.name), data = item.data instanceof Uint8Array ? item.data : new Uint8Array(item.data), crc = crc32(data);
      const common = [...u16(0x800), ...u16(0), ...u16(0), ...u16(33), ...u32(crc), ...u32(data.length), ...u32(data.length), ...u16(name.length), ...u16(0)];
      const header = new Uint8Array([...u32(0x04034b50), ...u16(20), ...common, ...name]);
      local.push(header, data);
      central.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...common, ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...name]));
      offset += header.length + data.length;
    }
    const size = central.reduce((n, part) => n + part.length, 0);
    return new Blob([...local, ...central, new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(entries.length), ...u16(entries.length), ...u32(size), ...u32(offset), ...u16(0)])], {type:'application/zip'});
  }
  function validateGroups(groups) {
    if (!groups.length) throw new Error('请先添加动画组。');
    const names = new Set();
    for (const group of groups) {
      const name = group.name.trim();
      if (!name || names.has(name)) throw new Error('动画名称不能为空或重复。');
      if (['__proto__', 'prototype', 'constructor'].includes(name)) throw new Error('请更换此保留动画名称。');
      names.add(name);
      if (!group.frames.length) throw new Error(name + ' 尚无帧，请带入处理结果或导入图片。');
      if (!Number.isFinite(Number(group.fps)) || group.fps < 1 || group.fps > 60) throw new Error(name + ' 的帧率须为 1–60。');
      if (group.event && (!Number.isInteger(Number(group.eventFrame)) || group.eventFrame < 1 || group.eventFrame > group.frames.length)) throw new Error(name + ' 的事件帧超出范围。');
    }
  }
  function spineJson(groups, regions, version) {
    validateGroups(groups);
    const attachments = Object.create(null), animations = Object.create(null), events = Object.create(null);
    for (const r of regions) attachments[r.id] = {x:0, y:0, width:r.width, height:r.height};
    for (const group of groups) {
      const frames = regions.filter(r => r.groupId === group.id), keys = frames.map((r, i) => ({time:i / group.fps, name:r.id}));
      // Preserve the last frame for a complete 1/fps interval. Looping is a runtime option.
      keys.push({time:frames.length / group.fps, name:group.loop ? frames[0].id : frames[frames.length - 1].id});
      const animation = {slots:{frame:{attachment:keys}}};
      if (group.event.trim()) { events[group.event.trim()] = {}; animation.events = [{time:(group.eventFrame - 1) / group.fps, name:group.event.trim()}]; }
      animations[group.name.trim()] = animation;
    }
    const result = {skeleton:{hash:' ',spine:version,x:0,y:0,width:0,height:0,images:'./',audio:''},bones:[{name:'root'}],slots:[{name:'frame',bone:'root',attachment:regions[0].id}],skins:[{name:'default',attachments:{frame:attachments}}],animations};
    if (Object.keys(events).length) result.events = events;
    return result;
  }
  function atlasText(filename, width, height, regions) {
    const lines = [filename + '.png', `size: ${width},${height}`, 'format: RGBA8888', 'filter: Linear,Linear', 'repeat: none'];
    for (const r of regions) lines.push(r.id, '  rotate: false', `  xy: ${r.x},${r.y}`, `  size: ${r.width},${r.height}`, `  orig: ${r.width},${r.height}`, '  offset: 0,0', '  index: -1');
    return lines.join('\n') + '\n';
  }
  function packRegions(regions, {padding = 2, maxSide = 8192, maxArea = 50000000} = {}) {
    if (!Array.isArray(regions) || !regions.length) throw new Error('图集至少需要一帧。');
    if (!Number.isInteger(padding) || padding < 2 || !Number.isInteger(maxSide) || maxSide < 1 || maxSide > 8192 || !Number.isFinite(maxArea) || maxArea < 1 || maxArea > 50000000) throw new Error('图集限制无效：边缘 padding 至少 2px，边长最多 8192，总面积最多 5000 万像素。');
    const items = regions.map((r, index) => {
      if (!Number.isInteger(r.width) || !Number.isInteger(r.height) || r.width < 1 || r.height < 1 || r.width + padding * 2 > maxSide || r.height + padding * 2 > maxSide) throw new Error('单帧尺寸无效或超过图集上限。');
      return {index, w:r.width + padding * 2, h:r.height + padding * 2};
    }).sort((a,b) => b.h - a.h || b.w - a.w || a.index - b.index);
    const area = items.reduce((sum, r) => sum + r.w * r.h, 0);
    if (area > maxArea || area > maxSide * maxSide) throw new Error('图集总面积过大，请减少帧数或降低单帧尺寸。');
    const minWidth = Math.max(...items.map(r => r.w)), target = Math.max(minWidth, Math.ceil(Math.sqrt(area))), widths = new Set([minWidth, target, maxSide]);
    let prefix = 0;
    for (const r of items) { prefix += r.w; if (prefix <= maxSide) widths.add(prefix); }
    const step = Math.max(1, Math.ceil((maxSide - minWidth) / 128));
    for (let w = minWidth; w <= maxSide; w += step) widths.add(w);
    let best = null;
    for (const limit of widths) {
      if (limit > maxSide) continue;
      let x = 0, y = 0, rowHeight = 0, width = 0;
      const positions = [];
      for (const r of items) {
        if (x + r.w > limit) { x = 0; y += rowHeight; rowHeight = 0; }
        positions[r.index] = {x:x + padding, y:y + padding};
        x += r.w; rowHeight = Math.max(rowHeight, r.h); width = Math.max(width, x);
      }
      const height = y + rowHeight;
      if (height > maxSide || width * height > maxArea) continue;
      const score = width * height * (1 + .5 * Math.abs(Math.log(width / height)));
      if (!best || score < best.score) best = {width, height, positions, score};
    }
    if (!best) throw new Error('无法在单张 8192 / 面积限制内排列，请减少帧数或降低尺寸。');
    return {width:best.width, height:best.height, padding, regions:regions.map((r,i) => ({...r, ...best.positions[i]}))};
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = {crc32, zip, spineJson, atlasText, validateGroups, packRegions}; return; }

  const $ = (s, root = document) => root.querySelector(s);
  function node(tag, text, attrs = {}) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, value);
    return n;
  }
  const nav = $('.workflow-tabs');
  if (!nav) return;
  nav.append(node('button', '03 视频转帧', {'data-tab':'sequence',type:'button'}), node('button','04 Spine 序列动画',{'data-tab':'spineSequence',type:'button'}));
  const spineRigButton = nav.querySelector('[data-tab="spineRig"]');
  if (spineRigButton) nav.append(spineRigButton);
  const style = node('style');
  style.textContent = `
    .sq-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.8fr);gap:16px;align-items:start}.sq-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.sq-fields label,.sq-grid label{display:grid;gap:5px;color:var(--muted);font-size:12px}.sq-fields input,.sq-fields select,.sq-grid input,.sq-grid select{min-width:0;width:100%}.sq-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.sq-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}.sq-stage{height:300px;display:flex;align-items:center;justify-content:center;background:#14171a;border:1px solid var(--line);border-radius:8px;overflow:hidden}.sq-stage video,.sq-stage canvas{display:block;max-width:100%;max-height:100%;object-fit:contain}.sq-stage canvas{background-color:#20242a;background-image:linear-gradient(45deg,#30363d 25%,transparent 25%),linear-gradient(-45deg,#30363d 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#30363d 75%),linear-gradient(-45deg,transparent 75%,#30363d 75%);background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0}.sq-frames{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:8px;max-height:370px;overflow:auto}.sq-frame{border:1px solid var(--line);border-radius:7px;overflow:hidden;background:var(--panel2)}.sq-frame.selected{border-color:var(--accent)}.sq-frame img{width:100%;height:86px;object-fit:contain;cursor:pointer}.sq-frame label{display:flex;align-items:center;gap:5px;padding:3px 6px;font-size:11px}.sq-status{color:var(--muted);white-space:pre-wrap;overflow-wrap:anywhere;min-height:20px}.sq-group{border:1px solid var(--line);border-radius:8px;padding:14px;margin:12px 0}.sq-mini{display:flex;gap:5px;overflow:auto;max-height:90px}.sq-mini button{padding:0;min-width:54px;flex:0 0 54px;height:65px}.sq-mini img{width:100%;height:100%;object-fit:contain}.sq-mini button.active{border:2px solid var(--accent)}.sq-group-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}.sq-group-head h3{font-size:14px;margin:0}.sq-input-file{display:none}.sq-advanced{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}.sq-advanced summary{color:var(--muted);cursor:pointer;margin-bottom:10px}.sq-corners{display:flex;gap:12px;flex-wrap:wrap}.sq-corners label{display:flex;align-items:center;gap:5px}.sq-meta{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.sq-sheet{max-height:220px;max-width:100%;object-fit:contain}.sq-toolbar{justify-content:space-between}.sq-primary{background:#244239;border-color:var(--accent)}.sq-disabled{opacity:.6;pointer-events:none}#sqVideo{width:100%;height:100%}.sq-intro{display:flex;justify-content:space-between;align-items:center;gap:12px}.sq-preview-controls{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}.sq-preview-controls input[type=range]{width:100%}@media(max-width:900px){.sq-layout{grid-template-columns:1fr}}@media(max-width:550px){.sq-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.sq-stage{height:250px}.sq-intro{display:block}}
  `;
  style.textContent += `
    #tab-sequence .sq-workflow{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:stretch}#tab-sequence .sq-workflow>.card{min-width:0;margin:0}#tab-sequence .sq-final{grid-column:1/-1}.sq-final-actions{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.sq-downloads{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.sq-checker,.sq-processed-frames img,.sq-stage canvas{background-color:#20242a;background-image:conic-gradient(#30363d 25%,transparent 0 50%,#30363d 0 75%,transparent 0);background-size:16px 16px}.sq-progress{display:grid;gap:5px;margin:10px 0}.sq-progress progress{width:100%;height:10px}.sq-processed-frames button{padding:0;width:100%}.sq-processed-frames .active{outline:2px solid var(--accent);outline-offset:-2px}.sq-parameter-values output{color:var(--text);font-variant-numeric:tabular-nums}.sq-corners label{display:inline-flex;gap:4px;align-items:center}.sq-grid input[type=checkbox]{width:auto;justify-self:start}.sq-atlas-preview{max-width:100%;max-height:360px;object-fit:contain;border:1px solid var(--line)}@media(max-width:640px){#tab-sequence .sq-workflow{grid-template-columns:minmax(0,1fr)}.sq-final-actions{align-items:stretch}.sq-downloads{margin-left:0}}
  `;
  document.head.append(style);
  const frameSection = node('section', undefined, {id:'tab-sequence',class:'hidden'});
  frameSection.innerHTML = `
    <div class="card sq-intro"><div><h2>视频转帧</h2><p class="muted">截取一轮完整动作 → 筛帧 → 处理背景与尺寸 → 直接带入 Spine，不再重复上传。</p></div><span class="badge" id="sqContext">当前角色</span></div>
    <div class="sq-workflow"><div class="card"><h2>1 / 选取视频片段</h2><div class="sq-row"><button id="sqImportVideo" type="button">导入本地视频</button><span id="sqVideoName" class="sq-meta">也可从历史视频点击“制作序列帧”</span><input id="sqVideoFile" class="sq-input-file" type="file" accept="video/*"></div><details><summary>从视频地址导入</summary><div class="sq-row"><input id="sqVideoUrl" type="url" aria-label="视频地址" placeholder="https://…/video.mp4" style="flex:1;min-width:180px"><button id="sqImportUrl" type="button">载入视频地址</button></div><p class="sq-meta">支持可直接播放且允许跨域的视频地址；本机文件仍可用上方按钮导入。</p></details><div class="sq-stage"><video id="sqVideo" controls playsinline preload="auto"></video></div>
    <p id="sqVideoInfo" class="sq-meta">尺寸 / 时长 / 当前时间：等待载入视频</p><div class="sq-progress"><label class="sq-meta">当前播放进度 <span id="sqCurrentProgressLabel">0%</span><progress id="sqCurrentProgress" max="1" value="0"></progress></label><label class="sq-meta">所选区间进度 <span id="sqIntervalProgressLabel">0%</span><progress id="sqIntervalProgress" max="1" value="0"></progress></label></div><div class="sq-row"><button id="sqStartNow" type="button">起点设为当前时间</button><button id="sqEndNow" type="button">终点设为当前时间</button></div>
    <div class="sq-fields" style="margin-top:14px"><label>开始 / 秒<input id="sqStart" type="number" value="0" min="0" step="0.001"></label><label>结束 / 秒<input id="sqEnd" type="number" value="0" min="0" step="0.001"></label><label>抽帧率 / FPS<input id="sqFps" type="number" value="20" min="1" max="60"></label></div>
    <div class="sq-row"><label>起点<input id="sqStartRange" type="range" min="0" max="1" step="0.001" value="0"></label><label>终点<input id="sqEndRange" type="range" min="0" max="1" step="0.001" value="1"></label><select id="sqDurationPreset" aria-label="快捷片段长度"><option value="0">快捷片段</option><option value="1">1 秒</option><option value="2">2 秒</option><option value="3">3 秒</option><option value="5">5 秒</option></select><button id="sqLoop" type="button">循环预览</button><button id="sqAnalyzeLoop" type="button">自动识别循环帧</button></div>
    <div class="sq-row"><span id="sqLoopAnalysis" class="sq-status" role="status">载入视频后自动寻找循环帧并填写起止时间；也可点击“自动识别循环帧”重新分析。候选需抽帧后检查首尾衔接。</span></div>
    <p class="sq-meta" id="sqLoopPreviewNote">“循环预览”用于观察原视频片段，回绕时可能短暂停顿或显示结束点附近画面。抽帧采用不含结束点的区间；请在右侧“播放选中帧”检查实际输出的首尾衔接。</p>
    <div class="sq-row sq-toolbar"><span id="sqEstimate" class="sq-meta">载入视频后选择片段</span><div class="row"><button id="sqCancelExtract" type="button" hidden>取消</button><button id="sqExtract" type="button" class="sq-primary">抽取帧</button></div></div><p id="sqVideoStatus" class="sq-status" role="status"></p></div>
    <div class="card"><div class="sq-group-head"><h2>2 / 筛选连续关键帧</h2><span id="sqFrameCount" class="badge">0 帧</span></div><div class="sq-row"><button id="sqAll" type="button">全选</button><button id="sqNone" type="button">全不选</button><button id="sqPlayFrames" type="button">播放选中帧</button><button id="sqRawZip" type="button">下载原始帧 ZIP</button></div><p class="sq-meta">点击缩略图查看；勾选后按 Shift 再点另一帧，可连续选择一段。拖动下方滑块逐帧检查。</p><div class="sq-stage"><canvas id="sqFrameCanvas" width="640" height="368"></canvas></div><div class="sq-preview-controls"><input id="sqFrameScrub" type="range" value="0" min="0" max="0" step="1" aria-label="原始帧逐帧预览"><span id="sqFrameLabel" class="sq-meta">暂无帧</span></div><div id="sqFrames" class="sq-frames"></div></div>
    <div class="card sq-parameter-values"><h2>3 / 抠图与输出尺寸</h2>
    <div class="sq-grid" style="margin-top:14px"><label>背景处理<select id="sqMatte"><option value="chroma">Chroma Key 纯色抠图</option><option value="none">保留原背景</option><option value="mediapipe">MediaPipe 人像分割</option></select></label><label>背景色<select id="sqColorPreset"><option value="auto">自动采样边缘</option><option value="#00ff00">绿色</option><option value="#0000ff">蓝色</option><option value="#ffffff">白色</option><option value="#000000">黑色</option><option value="custom">自定义</option></select></label><label>颜色容差 <output id="sqToleranceValue">12 / 255</output><input id="sqTolerance" type="range" min="0" max="255" value="12"></label><label>输出画布<select id="sqSize"><option value="original">原尺寸</option><option value="64">64 × 64</option><option value="128">128 × 128</option><option value="256" selected>256 × 256</option><option value="512">512 × 512</option><option value="custom">自定义</option></select></label></div>
    <div class="sq-advanced"><h3>边缘、尺寸与角区设置</h3><div class="sq-grid"><label>自定义色 <output id="sqColorValue">#00ff00</output><input id="sqColor" type="color" value="#00ff00"></label><label>去溢色强度 <output id="sqSpillValue">40%</output><input id="sqSpill" type="range" min="0" max="100" value="40"></label><label>边缘平滑开关<input id="sqSmooth" type="checkbox" checked></label><label>边缘柔化 <output id="sqFeatherValue">12 / 30</output><input id="sqFeather" type="range" min="0" max="30" value="12"></label><label>边缘净化 <output id="sqEdgeCleanValue">1 / 3</output><span class="sq-meta">1 保留轮廓；2–3 加强收边，最多约 0.75 个原图像素，细发梢可能变薄。</span><input id="sqEdgeClean" type="range" min="0" max="3" step="1" value="1"></label><label>缩放质量<select id="sqQuality"><option value="high">浏览器高质量缩放</option><option value="medium">中等</option><option value="pixel">最近邻 / 像素风</option></select></label><label>自定义宽<input id="sqWidth" type="number" value="256" min="1" max="2048"></label><label>自定义高<input id="sqHeight" type="number" value="256" min="1" max="2048"></label></div><p class="sq-meta">保持原比例居中缩放，不拉伸、不逐帧裁边，避免脚底位置跳动。</p><div class="sq-row"><button id="sqCornersAll" type="button">角区全选</button><button id="sqCornersNone" type="button">角区不选</button></div><div class="sq-corners"><label><input type="checkbox" data-sq-corner="tl">左上</label><label><input type="checkbox" data-sq-corner="tr">右上</label><label><input type="checkbox" data-sq-corner="bl">左下</label><label><input type="checkbox" data-sq-corner="br">右下</label></div><label class="sq-meta">角区清除范围 <output id="sqCornerPercentValue">10%</output><input id="sqCornerPercent" type="number" min="1" max="25" value="10"></label><p class="sq-meta">可清除有权编辑素材的角落标记，默认关闭。这会直接透明化角区，不是智能修复；角色或道具经过角落时不要勾选。</p></div>
    <p id="sqMatteNote" class="sq-meta">纯色抠图：连通背景 + 边缘混色还原；自动色锁定同一批首帧，避免逐帧漂色。高容差会安全限幅，不再靠扩大容差吞掉浅色角色。烘焙阴影、封闭同色孔洞仍需单独处理，无法承诺完美分离。</p><div class="sq-row"><button id="sqPreviewProcessed" type="button">预览当前帧效果</button><button id="sqProcess" type="button" class="sq-primary">处理选中帧</button></div><p id="sqProcessStatus" class="sq-status" role="status"></p></div>
    <div class="card"><h2>4 / 抠图后的关键帧预览</h2><p id="sqProcessedMode" class="sq-meta">暂无处理结果；可单帧试看或批量处理。</p><div class="sq-stage"><canvas id="sqProcessedCanvas" width="640" height="368"></canvas></div><div class="sq-preview-controls"><input id="sqProcessedScrub" type="range" value="0" min="0" max="0" step="1" aria-label="处理帧逐帧预览"><span id="sqProcessedLabel" class="sq-meta">暂无处理帧</span></div><div class="sq-row"><label class="sq-meta">边缘检查底色 <select id="sqMattePreviewBg"><option value="checker">透明棋盘</option><option value="#000000">黑底</option><option value="#ffffff">白底</option><option value="#ff00ff">洋红底</option></select></label></div><div class="sq-row"><button id="sqPlayProcessed" type="button">播放处理帧</button><button id="sqShowProcessed" type="button">单帧预览所选处理帧</button><button id="sqPreviewCurrent" type="button">试抠第 2 区当前原始帧</button></div><div id="sqProcessedFrames" class="sq-frames sq-processed-frames"></div><p class="sq-meta">棋盘表示透明背景。单帧试看不会覆盖或冒充批处理结果；下载与带入仅使用批处理帧。</p></div>
    <div class="card sq-final"><h2>5 / 继续制作或下载</h2><p id="sqReady" class="sq-meta">处理完成后可直接添加为 Spine 动画，无需下载再上传。</p><div class="sq-final-actions"><button id="sqToSpine" type="button" class="sq-primary">带入 Spine 动画组 →</button><div class="sq-downloads"><button id="sqProcessedZip" type="button">处理帧 ZIP</button><button id="sqSheet" type="button">生成并下载帧表 PNG</button></div></div><details class="sq-advanced"><summary>帧表 PNG 导出（可选）</summary><div class="sq-grid"><label>布局<select id="sqSheetLayout"><option value="horizontal">横向单行</option><option value="grid">网格</option></select></label><label>网格列数<input id="sqSheetColumns" type="number" min="1" max="120" value="10"></label></div><div class="sq-row"><span id="sqSheetInfo" class="sq-meta"></span></div><img id="sqSheetPreview" class="sq-sheet" hidden alt="输出帧表预览"></details></div></div>`;
  const spineSection = node('section', undefined, {id:'tab-spineSequence',class:'hidden'});
  spineSection.innerHTML = `
    <div class="card sq-intro"><div><h2>Spine 序列帧动画生成器</h2><p class="muted">多组动作、帧率与事件 → 统一预览 → 导出 JSON / atlas / PNG。此路线不需要拆件、锚点或骨骼绑定。</p></div><button id="sqAddGroup" type="button">＋ 添加动画组</button></div>
    <div class="sq-layout"><div><div id="sqGroups"></div></div><div><div class="card"><h2>动画预览</h2><div class="sq-row"><select id="sqPreviewGroup" aria-label="预览动画组"></select><button id="sqPlay" type="button">播放</button><label>背景<input id="sqPreviewBg" type="color" value="#24282d"></label></div><div class="sq-stage"><canvas id="sqAnimationCanvas" width="640" height="368"></canvas></div><div class="sq-preview-controls"><input id="sqAnimationScrub" type="range" min="0" max="0" value="0" step="1" aria-label="动画逐帧预览"><span id="sqAnimationLabel" class="sq-meta">暂无帧</span></div></div>
    <div class="card"><h2>导出</h2><div class="sq-grid"><label>文件名称<input id="sqFilename" value="character_animation" maxlength="80"></label><label>Spine 版本<select id="sqVersion"><option value="4.2.43">4.2.43</option><option value="3.8.75">3.8.75</option></select></label></div><p class="sq-meta">序列帧附件动画，不含网格权重/骨骼变形。预览为帧播放；实际 Spine Runtime 与 Unity 导入仍需单独验收。版本须与引擎运行库匹配。</p><div class="sq-row"><button id="sqExport" type="button" class="sq-primary">生成并下载 Spine ZIP</button></div><p id="sqExportStatus" class="sq-status" role="status"></p><div id="sqExportFiles" class="sq-row"></div><img id="sqAtlasPreview" class="sq-atlas-preview sq-checker" hidden alt="导出图集 PNG 预览"><p id="sqAtlasInfo" class="sq-meta"></p><p id="sqAtlasWarnings" class="sq-status" role="status"></p><p id="sqSaveStatus" class="sq-meta"></p></div></div></div>`;
  $('main').append(frameSection, spineSection);

  const currentCharacter = () => window.activeCharacterId || 'legacy_six_view';
  let state = freshState(), raw = [], processed = [], groups = [], extracting = false, cancelExtract = false, processing = false;
  let previewIndex = 0, lastChecked = -1, loop = false, objectVideo = '', sheetUrl = '', playbackTimer = null, playToken = 0, busy = false, restoreBusy = false;
  let workflowToken = 0, restoreToken = 0, restorePending = false, extractController = null, videoTask = null, frameDrawToken = 0, animationDrawToken = 0;
  let processedIndex = 0, processedDrawToken = 0, singlePreview = null, atlasUrl = '', playbackKind = '';
  let loopAnalysisController = null, loopAnalysisGeneration = 0, selectionRevision = 0, analyzingLoop = false;
  let matteKeyCache = null;
  let loopBoundaryFrame = 0, loopSeeking = false;
  const requestLoopTick = typeof requestAnimationFrame === 'function' ? callback => requestAnimationFrame(callback) : callback => setTimeout(callback,16);
  const cancelLoopTick = typeof cancelAnimationFrame === 'function' ? handle => cancelAnimationFrame(handle) : handle => clearTimeout(handle);
  const intervalFrameCount = (start,end,fps) => Math.max(0,Math.ceil((end-start)*fps-1e-7));
  // 只避开浮点/微秒量化边界，不假定源帧率；绝不越过半开区间终点。
  const sampleSeekTime = (time,end) => time + Math.min(.00001,Math.max(0,end-time)/2);
  function cancelLoopAnalysis() { ++loopAnalysisGeneration; loopAnalysisController?.abort(); loopAnalysisController = null; analyzingLoop = false; }
  function manualIntervalChanged() {
    ++selectionRevision; if (videoTask) videoTask.manualInterval = true; cancelLoopAnalysis();
    tell('sqLoopAnalysis','已保留你的手动区间；可点“自动识别循环帧”重新推荐。');
    updateButtons();
  }
  function stopVideoLoop() { loop = false; loopSeeking = false; video.pause(); cancelLoopTick(loopBoundaryFrame); loopBoundaryFrame = 0; $('#sqLoop').textContent = '循环预览'; }
  function seekLoopStart() {
    if (!loop || loopSeeking || extracting) return;
    const start = Number($('#sqStart').value), end = Number($('#sqEnd').value);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > video.duration + .001) { stopVideoLoop(); tell('sqVideoStatus','循环区间已无效，已停止循环预览。'); return; }
    loopSeeking = true;
    video.currentTime = sampleSeekTime(start,end);
    if (!video.seeking) loopSeeking = false;
    return true;
  }
  function watchLoopBoundary() {
    cancelLoopTick(loopBoundaryFrame);
    if (!loop || video.paused || extracting) { loopBoundaryFrame = 0; return; }
    const tick = () => {
      if (!loop || video.paused || extracting) { loopBoundaryFrame = 0; return; }
      if (loopSeeking && !video.seeking) loopSeeking = false;
      if (!loopSeeking && (video.currentTime >= Number($('#sqEnd').value) || video.currentTime < Number($('#sqStart').value) - .05)) seekLoopStart();
      loopBoundaryFrame = requestLoopTick(tick);
    };
    loopBoundaryFrame = requestLoopTick(tick);
  }
  const taskIsCurrent = (characterId, token) => token === workflowToken && characterId === currentCharacter() && characterId === state.characterId;
  function taskContext() {
    if (restoreBusy || restorePending || state.characterId !== currentCharacter()) return null;
    const characterId = state.characterId, token = workflowToken;
    return {characterId, token, valid:() => taskIsCurrent(characterId, token)};
  }
  function cancelExtraction() { cancelExtract = true; extractController?.abort(); }
  function restoreActiveWhenIdle() {
    if (!restorePending || extracting || processing || busy) return;
    restorePending = false;
    restore(currentCharacter());
  }
  const video = $('#sqVideo');
  const settingDefaults = settings();
  const uiIds = ['sqStart','sqEnd','sqStartRange','sqEndRange','sqFps','sqDurationPreset','sqSheetLayout','sqSheetColumns','sqPreviewBg','sqFilename','sqVersion'];
  const uiDefaults = readUi();
  function readUi() {
    return {values:Object.fromEntries(uiIds.map(id => [id, $('#' + id).value])),duration:$('#sqEndRange').max,previewIndex,processedIndex,groupId:$('#sqPreviewGroup').value,animationIndex:$('#sqAnimationScrub').value,loop};
  }
  function applyUi(ui) {
    const values = {...uiDefaults.values, ...ui?.values};
    for (const id of ['sqStart','sqEnd','sqStartRange','sqEndRange']) $('#' + id).max = ui?.duration ?? uiDefaults.duration;
    for (const id of uiIds) $('#' + id).value = values[id];
    previewIndex = Math.max(0, Math.min(raw.length - 1, Number(ui?.previewIndex) || 0));
    processedIndex = Math.max(0, Math.min(processed.length - 1, Number(ui?.processedIndex) || 0));
    loop = !!ui?.loop; $('#sqLoop').textContent = loop ? '停止循环' : '循环预览';
    $('#sqSheetColumns').disabled = $('#sqSheetLayout').value === 'horizontal';
    estimate();
  }
  function freshState() { return {characterId:currentCharacter(),action:'',viewId:'',taskId:'',videoName:''}; }
  function tell(id, text) { $('#' + id).textContent = text; }
  function showTab(id) { window.goToTab(id); stopPlayback(); }
  function freeFrames(list) { for (const frame of list) if (frame.url) URL.revokeObjectURL(frame.url); }
  function hydrate(frames) { return (frames || []).map(frame => ({...frame, url:URL.createObjectURL(frame.blob)})); }
  function serialize(frames) { return frames.map(({url, ...rest}) => rest); }
  const selected = () => raw.filter(frame => frame.checked);
  function hasWork() { return raw.length || groups.some(group => group.frames.length); }
  function stopPlayback() { playToken++; frameDrawToken++; processedDrawToken++; animationDrawToken++; clearTimeout(playbackTimer); playbackTimer = null; playbackKind = ''; $('#sqPlay').textContent = '播放'; $('#sqPlayFrames').textContent = '播放选中帧'; $('#sqPlayProcessed').textContent = '播放处理帧'; }
  function clearProcessed() {
    stopPlayback(); freeFrames(processed); processed = []; singlePreview = null; processedIndex = 0;
    const c = $('#sqProcessedCanvas'); c.getContext('2d').clearRect(0,0,c.width,c.height);
    $('#sqProcessedFrames').replaceChildren(); $('#sqProcessedScrub').value = 0; $('#sqProcessedScrub').max = 0;
    tell('sqProcessedMode','暂无处理结果；可单帧试看或批量处理。'); tell('sqProcessedLabel','暂无处理帧');
    $('#sqSheetPreview').hidden = true; if (sheetUrl) URL.revokeObjectURL(sheetUrl); sheetUrl = ''; tell('sqSheetInfo',''); updateButtons();
  }
  function clearAtlasPreview() {
    if (atlasUrl) URL.revokeObjectURL(atlasUrl); atlasUrl = '';
    $('#sqAtlasPreview').hidden = true; $('#sqAtlasPreview').removeAttribute('src');
    tell('sqAtlasInfo',''); tell('sqAtlasWarnings','');
  }
  function updateButtons() {
    const locked = extracting || processing || busy || restoreBusy || restorePending || state.characterId !== currentCharacter();
    for (const section of [frameSection,spineSection]) section.querySelectorAll('button,input,select').forEach(input => { input.disabled = locked; });
    $('#sqCancelExtract').disabled = !extracting;
    $('#sqSheetColumns').disabled = locked || $('#sqSheetLayout').value === 'horizontal';
    $('#sqExtract').disabled = locked || analyzingLoop || !video.src;
    $('#sqAnalyzeLoop').disabled = locked || analyzingLoop || !video.src || !Number.isFinite(video.duration);
    $('#sqLoop').disabled = locked || analyzingLoop || !video.src || !Number.isFinite(video.duration);
    video.controls = !extracting;
    $('#sqProcess').disabled = locked || !selected().length;
    $('#sqToSpine').disabled = locked || !processed.length;
    $('#sqProcessedZip').disabled = locked || !processed.length;
    $('#sqSheet').disabled = locked || !processed.length;
    $('#sqRawZip').disabled = locked || !selected().length;
    $('#sqPreviewProcessed').disabled = locked || !raw.length;
    $('#sqPreviewCurrent').disabled = locked || !raw.length;
    $('#sqPlayFrames').disabled = locked || !selected().length;
    $('#sqPlayProcessed').disabled = locked || !processed.length;
    $('#sqShowProcessed').disabled = locked || !processed.length;
    $('#sqProcessedScrub').disabled = locked || !processed.length;
    $('#sqFrameScrub').disabled = locked || !raw.length;
    $('#sqStartNow').disabled = $('#sqEndNow').disabled = locked || !video.src || !Number.isFinite(video.duration);
    $('#sqFrameCount').textContent = `${selected().length} / ${raw.length} 帧`;
    tell('sqReady', processed.length ? `${processed.length} 张处理帧已就绪，可直接带入动画组。` : '处理完成后可直接添加为 Spine 动画，无需下载再上传。');
    tell('sqContext', '角色：' + state.characterId + (state.viewId ? ' / ' + state.viewId : '') + (state.action ? ' / ' + state.action : ''));
  }

  // Dedicated IndexedDB storage; never modifies old history/spec/parts keys.
  const dbReady = new Promise(resolve => {
    try {
      let unavailable = false;
      const request = indexedDB.open('cotton_sequence_projects_v2', 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('projects')) request.result.createObjectStore('projects', {keyPath:'characterId'}); };
      request.onsuccess = () => {
        if (unavailable) { request.result.close(); return; }
        request.result.onversionchange = () => request.result.close();
        resolve(request.result);
      };
      request.onerror = request.onblocked = () => { unavailable = true; tell('sqSaveStatus','本机草稿库不可用；请及时下载导出文件。'); resolve(null); };
    } catch (_) { tell('sqSaveStatus','本机草稿库不可用；请及时下载导出文件。'); resolve(null); }
  });
  let saving = Promise.resolve();
  function save() {
    const task = taskContext(); if (!task) return saving;
    const snapshot = {...state, settings:settings(), ui:readUi(), raw:serialize(raw), processed:serialize(processed), groups:groups.map(g => ({...g, frames:serialize(g.frames)}))};
    if (snapshot.characterId !== state.characterId || !task.valid()) return saving;
    saving = saving.catch(() => {}).then(async () => {
      const db = await dbReady; if (!db) return;
      // 快照只能写入捕获时的角色 key；切换后也保留已排队的原角色保存。
      await new Promise((resolve, reject) => { const tx = db.transaction('projects','readwrite'); tx.oncomplete = resolve; tx.onerror = tx.onabort = () => reject(tx.error || new Error('草稿事务已中止')); tx.objectStore('projects').put(snapshot); });
      if (task.valid()) tell('sqSaveStatus','当前角色的帧与动画组已保存在本机草稿库。');
    }).catch(error => { if (task.valid()) tell('sqSaveStatus','草稿保存失败：' + error.message + '。请下载文件保留成果。'); });
    return saving;
  }
  async function restore(characterId) {
    const token = ++restoreToken, generation = ++workflowToken;
    cancelExtraction(); cancelLoopAnalysis(); stopVideoLoop(); stopPlayback(); videoTask = null;
    if (extracting || processing || busy) { restorePending = true; restoreBusy = true; updateButtons(); return; }
    restorePending = false; restoreBusy = true; updateButtons();
    const valid = () => token === restoreToken && generation === workflowToken && characterId === currentCharacter();
    try {
      await saving; if (!valid()) return;
      const db = await dbReady; if (!valid()) return;
      const saved = db ? await new Promise((resolve, reject) => { const request = db.transaction('projects').objectStore('projects').get(characterId); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }) : null;
      if (!valid()) return;
      stopPlayback(); freeFrames(raw); clearProcessed(); groups.forEach(g => freeFrames(g.frames));
      state = {characterId,action:saved?.action || '',viewId:saved?.viewId || '',taskId:saved?.taskId || '',videoName:saved?.videoName || ''};
      raw = hydrate(saved?.raw); matteKeyCache=null; processed = hydrate(saved?.processed); groups = (saved?.groups || []).map(g => ({...g,frames:hydrate(g.frames)}));
      lastChecked = -1; applySettings({...settingDefaults, ...saved?.settings}); applyUi(saved?.ui);
      stopVideoLoop(); video.removeAttribute('src'); video.load();
      tell('sqLoopAnalysis','重新载入视频后将自动分析循环帧；已保存帧与动画组不变。');
      if (objectVideo) URL.revokeObjectURL(objectVideo); objectVideo = '';
      for (const id of ['sqVideoStatus','sqProcessStatus','sqSheetInfo','sqExportStatus']) tell(id, '');
      $('#sqExportFiles').replaceChildren(); clearAtlasPreview(); $('#sqSheetPreview').removeAttribute('src'); updateVideoInfo();
      $('#sqFrameCanvas').getContext('2d').clearRect(0,0,$('#sqFrameCanvas').width,$('#sqFrameCanvas').height);
      $('#sqAnimationCanvas').getContext('2d').clearRect(0,0,$('#sqAnimationCanvas').width,$('#sqAnimationCanvas').height);
      $('#sqFrameScrub').value = previewIndex; tell('sqFrameLabel','暂无帧'); tell('sqAnimationLabel','暂无帧');
      tell('sqVideoName',saved?.videoName ? saved.videoName + '（已恢复帧；重新抽帧需重新载入视频）' : '导入本地视频或从历史视频继续');
      renderFrames(); renderGroups(); renderProcessedFrames();
      if (processed.length) { await drawProcessedFrame(processedIndex,{valid}); if (!valid()) return; }
      if (raw.length) { await drawFrame(previewIndex,false,{valid}); if (!valid()) return; }
      const group = groups.find(g => g.id === saved?.ui?.groupId) || groups[0];
      if (group) { selectGroup(group.id, false); await drawAnimationFrame(group, Number(saved?.ui?.animationIndex) || 0,{valid}); if (!valid()) return; }
    } catch (error) { if (valid()) tell('sqVideoStatus','恢复草稿失败：' + error.message); }
    finally { if (token === restoreToken) { restoreBusy = false; updateButtons(); } }
  }
  function canReplace() {
    if (!taskContext() || extracting || processing || busy) { tell('sqVideoStatus','当前正在处理或恢复，请完成后再切换视频。'); return false; }
    return !raw.length || confirm('换用视频会替换当前抽帧区，已有 Spine 动画组保留。继续？');
  }
  function resetVideoFrames() { cancelLoopAnalysis(); ++selectionRevision; stopVideoLoop(); tell('sqLoopAnalysis','读取视频后将自动分析循环帧…'); stopPlayback(); freeFrames(raw); raw = []; matteKeyCache=null; clearProcessed(); previewIndex = 0; lastChecked = -1; const c = $('#sqFrameCanvas'); c.getContext('2d').clearRect(0,0,c.width,c.height); tell('sqFrameLabel','暂无帧'); renderFrames(); }
  async function useVideo(source) {
    const requestedCharacter = currentCharacter();
    if (source.characterId && source.characterId !== requestedCharacter) throw new Error('该视频不属于当前角色。');
    showTab('sequence');
    if (extracting || processing || busy) throw new Error('转帧区正在处理，请结束或取消后再带入视频。');
    if (restoreBusy || restorePending || state.characterId !== currentCharacter()) await restore(currentCharacter());
    if (currentCharacter() !== requestedCharacter || (source.characterId && source.characterId !== currentCharacter())) throw new Error('载入期间角色已切换，请从当前角色重新选择视频。');
    const task = taskContext(); if (!task) throw new Error('角色草稿尚未就绪，请稍后重试。');
    if (!canReplace()) return false;
    const url = new URL(source.url, location.href); if (!['http:','https:'].includes(url.protocol)) throw new Error('视频地址格式无效。');
    const isArkOutput = url.hostname === 'ark-acg-cn-beijing.tos-cn-beijing.volces.com';
    if (isArkOutput && !/^[A-Za-z0-9_-]{1,256}$/.test(source.taskId || '')) throw new Error('历史视频任务 ID 无效，无法安全读取视频。');
    if (!task.valid()) return;
    workflowToken++; videoTask = {characterId:task.characterId, token:workflowToken};
    resetVideoFrames(); videoTask.manualInterval=false; if (objectVideo) URL.revokeObjectURL(objectVideo); objectVideo = '';
    state = {...state,characterId:task.characterId,taskId:source.taskId || '',action:source.action || '',viewId:source.viewId || '',videoName:source.taskId || source.name || '历史视频'};
    video.crossOrigin = 'anonymous'; video.src = isArkOutput ? '/api/video/ark-output?task_id=' + encodeURIComponent(source.taskId) : url.href; videoTask.source=video.src; video.load(); tell('sqVideoName',state.videoName); tell('sqVideoStatus',isArkOutput ? '正在通过本地服务读取最新历史视频地址…' : source.taskId ? '已从历史视频带入。' : '已从视频地址载入，读取后自动分析循环片段。');
    showTab('sequence'); updateButtons(); save();
  }
  window.SequenceWorkflow = {useVideo};
  $('#sqImportUrl').onclick = async () => {
    const characterId = currentCharacter();
    try {
      const value = $('#sqVideoUrl').value.trim();
      if (!value) throw new Error('请先填写视频地址');
      const url = new URL(value, location.href);
      if (!['http:','https:'].includes(url.protocol) || url.username || url.password) throw new Error('仅支持不含账号密码的 HTTP/HTTPS 视频地址');
      await useVideo({url:url.href, characterId, name:'地址导入视频'});
    } catch (error) {
      if (characterId === currentCharacter()) tell('sqVideoStatus','地址导入失败：' + error.message);
    }
  };
  let videoImportTask = null;
  $('#sqImportVideo').onclick = () => { videoImportTask=taskContext(); if(videoImportTask)$('#sqVideoFile').click(); };
  $('#sqVideoFile').onchange = event => {
    const task = videoImportTask, file = event.target.files[0]; videoImportTask=null;
    if (!task || !task.valid() || !file || !canReplace()) { event.target.value=''; return; }
    workflowToken++; videoTask = {characterId:task.characterId, token:workflowToken};
    resetVideoFrames(); videoTask.manualInterval=false; if (objectVideo) URL.revokeObjectURL(objectVideo); objectVideo = URL.createObjectURL(file);
    video.removeAttribute('crossorigin'); video.src = objectVideo; videoTask.source=video.src; video.load(); state = {...state,videoName:file.name,characterId:task.characterId,taskId:'',action:'',viewId:''};
    tell('sqVideoName',file.name); tell('sqVideoStatus','本地视频仅在浏览器处理。'); save(); event.target.value = '';
  };
  function waitAnalysisMedia(media, eventName, action, signal, targetTime) {
    return new Promise((resolve,reject) => {
      let settled = false, poll = 0;
      const ready = () => media.readyState >= 2 && (eventName !== 'seeked' || (!media.seeking && (targetTime === undefined || Math.abs(media.currentTime-targetTime)<=.002)));
      const done = () => { if (ready()) finish(); }, fail = () => finish(new Error('分析视频解码失败')), abort = () => finish(new DOMException('分析已取消','AbortError'));
      const timer = setTimeout(() => finish(new Error(eventName === 'seeked' ? `分析视频解码超时（定位 ${Number(targetTime ?? media.currentTime).toFixed(3)} 秒，readyState=${media.readyState}，seeking=${!!media.seeking}）` : `分析视频解码超时（首次画面加载，readyState=${media.readyState}）`)),15000);
      function finish(error) {
        if (settled) return; settled = true;
        clearTimeout(timer); clearTimeout(poll); media.removeEventListener(eventName,done); media.removeEventListener('loadeddata',done); media.removeEventListener('canplay',done); media.removeEventListener('error',fail); signal.removeEventListener('abort',abort);
        error ? reject(error) : resolve();
      }
      // 事件是唤醒信号，不是已解码的证明；反过来，已就绪也不必死等遗漏的事件。
      function check() { if (settled) return; if (media.error) return fail(); done(); if (!settled) poll=setTimeout(check,100); }
      media.addEventListener(eventName,done); media.addEventListener('loadeddata',done); media.addEventListener('canplay',done); media.addEventListener('error',fail,{once:true}); signal.addEventListener('abort',abort,{once:true});
      if (signal.aborted) return abort();
      try { action?.(); check(); } catch (error) { finish(error); }
    });
  }
  async function analyzeLoopInterval() {
    const task = taskContext(); if (!task || !videoTask || !video.src || !Number.isFinite(video.duration) || extracting || processing || busy) return;
    cancelLoopAnalysis(); stopVideoLoop();
    const generation = loopAnalysisGeneration, revision = selectionRevision, source = video.src, duration = video.duration;
    if (duration<=.05) return tell('sqLoopAnalysis','视频过短，无法分析完整周期；保留当前区间。');
    const controller = new AbortController(), signal = controller.signal;
    loopAnalysisController = controller; analyzingLoop = true; updateButtons();
    const valid = () => !signal.aborted && generation === loopAnalysisGeneration && revision === selectionRevision && task.valid() && source === video.src;
    const probe = document.createElement('video'); probe.muted = true; probe.playsInline = true; probe.preload = 'auto';
    if (video.crossOrigin) probe.crossOrigin = video.crossOrigin;
    try {
      if (!window.SequenceLoopAnalysis) throw new Error('循环分析组件未载入，请刷新工作台');
      tell('sqLoopAnalysis','正在自动分析循环姿态与衔接运动…');
      await waitAnalysisMedia(probe,'loadeddata',() => { probe.src = source; probe.load(); },signal);
      if (!valid()) return;
      // 有限预算、独立解码器：不拖动用户正在查看的视频，也不改抽帧率。
      const analyzedDuration = Math.min(duration,30), rate = Math.min(24,299 / analyzedDuration);
      const count = Math.max(2,Math.floor(analyzedDuration * rate) + 1), c = canvas(128,72), ctx = c.getContext('2d',{willReadFrequently:true}), samples = [];
      for (let i=0;i<count;i++) {
        if (!valid()) return;
        const time = Math.min(duration-.001,i / rate);
        // 按用户提供的16:00快照恢复精确名义时间采样。
        // 自动识别不再加入后续10µs偏移；抽帧和播放器保持各自现有行为。
        const seekTime = time;
        if (probe.seeking) await waitAnalysisMedia(probe,'seeked',null,signal);
        if (!valid()) return;
        if (Math.abs(probe.currentTime-seekTime)>.000001) await waitAnalysisMedia(probe,'seeked',() => { probe.currentTime=seekTime; },signal,seekTime);
        if (!valid()) return;
        if (probe.seeking || probe.readyState<2 || Math.abs(probe.currentTime-seekTime)>.002) throw new Error('采样时间与解码画面不一致，请重新分析');
        ctx.drawImage(probe,0,0,c.width,c.height);
        samples.push({time,descriptor:window.SequenceLoopAnalysis.describeFrame(ctx.getImageData(0,0,c.width,c.height).data,c.width,c.height)});
        if (i%12===0) { tell('sqLoopAnalysis',`正在自动分析循环片段 ${i+1} / ${count}${duration>30?'（前30秒）':''}…`); await new Promise(resolve => setTimeout(resolve,0)); }
      }
      if (!valid()) return;
      const result = window.SequenceLoopAnalysis.findLoop(samples,{duration:analyzedDuration,sampleRate:rate});
      if (!valid()) return;
      const candidate = result && result.fallback!==true && ['high','medium','low'].includes(result.confidence) && Number.isFinite(result.start) && Number.isFinite(result.end) && result.end>result.start && result.start>=0 && result.end<=duration;
      if (candidate) {
        const start = result.start, end = Math.min(duration,result.end);
        $('#sqStart').value = $('#sqStartRange').value = start;
        $('#sqEnd').value = $('#sqEndRange').value = end;
        $('#sqDurationPreset').value = '0'; estimate();
        const confidence = {high:'较高',medium:'中等',low:'低'}[result.confidence] || '待确认';
        tell('sqLoopAnalysis',`已自动填写 ${start.toFixed(3)}–${end.toFixed(3)} 秒 · 循环置信度${confidence}。${result.reason || ''} 点击“循环预览”检查衔接；结束点不重复抽取。${duration>30?' 仅分析了前30秒，可手动调整到后续片段。':''}`);
        video.currentTime = sampleSeekTime(start,end); save();
      } else {
        tell('sqLoopAnalysis',`未发现可信循环片段，保留当前区间。${result?.reason || '可能是静止、非周期动作或循环差异过大。'} 可直接预览或手动调整，不会把整段标为已验证循环。`);
      }
    } catch (error) { if (valid()) tell('sqLoopAnalysis','自动循环分析未完成：'+error.message+'。当前区间保留，可手动预览或重新分析。'); }
    finally {
      probe.pause(); probe.removeAttribute('src'); probe.load();
      if (generation === loopAnalysisGeneration) { analyzingLoop=false; loopAnalysisController=null; updateButtons(); }
    }
  }
  $('#sqAnalyzeLoop').onclick = analyzeLoopInterval;
  video.onloadedmetadata = () => {
    if (!videoTask || !taskIsCurrent(videoTask.characterId, videoTask.token) || (videoTask.source && video.src !== videoTask.source) || !Number.isFinite(video.duration) || video.duration<=0) return;
    for (const id of ['sqStart','sqEnd','sqStartRange','sqEndRange']) $('#' + id).max = video.duration;
    if (!videoTask.metadataInitialized) {
      videoTask.metadataInitialized=true;
      if (videoTask.manualInterval) {
        const start=Math.max(0,Math.min(video.duration,Number($('#sqStart').value)||0));
        const end=Math.max(start,Math.min(video.duration,Number($('#sqEnd').value)||video.duration));
        $('#sqStart').value=$('#sqStartRange').value=start; $('#sqEnd').value=$('#sqEndRange').value=end;
      } else {
        $('#sqStart').value=$('#sqStartRange').value=0; $('#sqEnd').value=$('#sqEndRange').value=video.duration;
      }
    }
    tell('sqVideoStatus',`${video.videoWidth} × ${video.videoHeight} · ${video.duration.toFixed(2)} 秒`); estimate(); updateButtons(); save();
    if (!videoTask.manualInterval && !videoTask.analysisStarted) { videoTask.analysisStarted=true; analyzeLoopInterval(); }
  };
  video.onerror = () => { if (videoTask && taskIsCurrent(videoTask.characterId,videoTask.token)) tell('sqVideoStatus','视频无法读取：来源可能过期/拒绝跨域，或浏览器不支持此编码。可下载 MP4 后本地导入。'); };
  video.ontimeupdate = () => { updateVideoInfo(); if (loop && !loopSeeking && video.currentTime >= Number($('#sqEnd').value)) seekLoopStart(); };
  video.onseeked = () => { loopSeeking = false; updateVideoInfo(); };
  video.addEventListener('playing',() => { if (loop) watchLoopBoundary(); });
  function updateVideoInfo() {
    const ready = !!video.src && Number.isFinite(video.duration) && video.duration > 0;
    const time = ready ? video.currentTime : 0, duration = ready ? video.duration : 0;
    const start = Number($('#sqStart').value), end = Number($('#sqEnd').value);
    const current = duration ? Math.max(0,Math.min(1,time / duration)) : 0;
    const interval = ready && end > start ? Math.max(0,Math.min(1,(time - start) / (end - start))) : 0;
    tell('sqVideoInfo',ready ? `${video.videoWidth} × ${video.videoHeight} px · 时长 ${duration.toFixed(3)} 秒 · 当前 ${time.toFixed(3)} 秒` : '尺寸 / 时长 / 当前时间：等待载入视频');
    $('#sqCurrentProgress').value = current; $('#sqIntervalProgress').value = interval;
    tell('sqCurrentProgressLabel',`${(current * 100).toFixed(1)}%`); tell('sqIntervalProgressLabel',`${(interval * 100).toFixed(1)}% · 区间 ${start.toFixed(2)}–${end.toFixed(2)} 秒`);
  }
  for (const [buttonId,inputId,rangeId] of [['sqStartNow','sqStart','sqStartRange'],['sqEndNow','sqEnd','sqEndRange']]) $('#' + buttonId).onclick = () => {
    if (!taskContext() || !video.src || !Number.isFinite(video.duration)) return;
    manualIntervalChanged(); $('#' + inputId).value = video.currentTime.toFixed(3); $('#' + rangeId).value = $('#' + inputId).value; estimate(); save();
  };
  video.onended = () => {
    if (!loop) return;
    // timeupdate可能已经先发起回绕；同一次ended仍需续播，但无效区间不得播放全片。
    if (loopSeeking) {
      const start=Number($('#sqStart').value), end=Number($('#sqEnd').value);
      if (!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>video.duration+.001) return stopVideoLoop();
      video.play().catch(() => {});
    } else if (seekLoopStart()) video.play().catch(() => {});
  };
  function estimate() {
    const start = Number($('#sqStart').value), end = Number($('#sqEnd').value), fps = Number($('#sqFps').value);
    const count = intervalFrameCount(start,end,fps);
    tell('sqEstimate', `${Math.max(0,end - start).toFixed(3)} 秒 · 抽帧 ${fps || 0} FPS · 间隔 ${fps > 0 ? (1000 / fps).toFixed(1) : '—'} ms · 预计 ${Number.isFinite(count) ? count : 0} 帧（每段最多 240 帧；此为抽帧率，非源视频 FPS 检测）`);
    updateVideoInfo();
  }
  for (const pair of [['sqStart','sqStartRange'],['sqEnd','sqEndRange']]) for (const id of pair) $('#' + id).oninput = () => { manualIntervalChanged(); $('#' + pair.find(other => other !== id)).value = $('#' + id).value; estimate(); };
  $('#sqFps').oninput = estimate;
  $('#sqDurationPreset').onchange = () => { const length = Number($('#sqDurationPreset').value); if (length) { manualIntervalChanged(); $('#sqEnd').value = Math.min(video.duration || length,Number($('#sqStart').value) + length); $('#sqEndRange').value = $('#sqEnd').value; estimate(); } };
  $('#sqLoop').onclick = () => {
    if (loop) return stopVideoLoop();
    if (!video.src || !Number.isFinite(video.duration)) return tell('sqVideoStatus','先载入视频。');
    const start=Number($('#sqStart').value), end=Number($('#sqEnd').value);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start<0 || end<=start || end>video.duration+.001) return tell('sqVideoStatus','循环区间无效，请先完成分析或调整起止时间。');
    loop=true; loopSeeking=true; $('#sqLoop').textContent='停止循环'; video.currentTime=sampleSeekTime(start,end);
    if (!video.seeking) loopSeeking = false;
    video.play().then(watchLoopBoundary).catch(error => { stopVideoLoop(); tell('sqVideoStatus',error.message); });
  };
  function blobFromCanvas(canvas) { return new Promise((resolve,reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG 编码失败，可能超出浏览器画布上限。')),'image/png')); }
  async function loadImage(blob) { return createImageBitmap(blob); }
  function canvas(width, height) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 16384 || height > 16384 || width * height > 50000000) throw new Error('画布过大，请减小帧尺寸、帧数或使用网格布局。');
    const c = document.createElement('canvas'); c.width = width; c.height = height; return c;
  }
  function videoEvent(eventName, action, signal) {
    return new Promise((resolve,reject) => {
      const timer = setTimeout(() => finish(new Error('视频解码超时，请更换本地 MP4 或缩短片段。')),15000);
      const done = () => finish(), fail = () => finish(new Error('视频解码失败')), abort = () => finish(new Error('抽帧已取消'));
      function finish(error) { clearTimeout(timer); video.removeEventListener(eventName,done); video.removeEventListener('error',fail); signal?.removeEventListener('abort',abort); error ? reject(error) : resolve(); }
      video.addEventListener(eventName,done,{once:true}); video.addEventListener('error',fail,{once:true}); signal?.addEventListener('abort',abort,{once:true});
      if (signal?.aborted) return abort();
      try { if (action) action(); } catch (error) { finish(error); }
    });
  }
  async function seek(time, task, signal) {
    const valid = () => task.valid() && !signal.aborted;
    if (!valid()) return;
    if (video.readyState < 2) { await waitAnalysisMedia(video,'loadeddata',null,signal); if (!valid()) return; }
    if (video.seeking) { await waitAnalysisMedia(video,'seeked',null,signal); if (!valid()) return; }
    if (Math.abs(video.currentTime-time)>.000001) await waitAnalysisMedia(video,'seeked',() => { video.currentTime=time; },signal,time);
    if (!valid()) return;
    if (video.seeking || video.readyState<2 || Math.abs(video.currentTime-time)>.002) throw new Error('抽帧定位或解码尚未就绪');
  }
  $('#sqCancelExtract').onclick = cancelExtraction;
  $('#sqExtract').onclick = async () => {
    const task = taskContext(); if (!task || analyzingLoop || !videoTask || !taskIsCurrent(videoTask.characterId,videoTask.token)) return;
    const characterId = task.characterId, token = task.token;
    const start = Number($('#sqStart').value), end = Number($('#sqEnd').value), fps = Number($('#sqFps').value), count = intervalFrameCount(start,end,fps);
    if (!video.src || !Number.isFinite(video.duration) || start < 0 || end > video.duration + .001 || end <= start || !Number.isFinite(fps) || fps < 1 || fps > 60) return tell('sqVideoStatus','请载入视频并填写有效区间和 1–60 FPS。');
    if (count > 240 || video.videoWidth * video.videoHeight * count > 240000000) return tell('sqVideoStatus','帧数或总像素过大。请缩短片段或降低抽帧率。');
    if (raw.length && !confirm('重新抽帧将替换抽帧区和处理结果，Spine 动画组保持不变。继续？')) return;
    extracting = true; cancelExtract = false; extractController = new AbortController(); const signal=extractController.signal; stopVideoLoop(); stopPlayback(); $('#sqCancelExtract').hidden = false; updateButtons();
    const incoming = [];
    try {
      const c = canvas(video.videoWidth,video.videoHeight), ctx = c.getContext('2d');
      for (let i = 0; i < count && !cancelExtract && taskIsCurrent(characterId,token); i++) {
        const time = start + i / fps; if (time>=end-1e-8) break; await seek(sampleSeekTime(time,end),task,signal); if (!taskIsCurrent(characterId,token) || signal.aborted) break;
        if (Math.abs(video.currentTime-time)>.002) throw new Error('视频时间轴被改变，请暂停播放器后重新抽帧');
        ctx.drawImage(video,0,0,c.width,c.height);
        const blob = await blobFromCanvas(c); if (!taskIsCurrent(characterId,token) || signal.aborted) break;
        incoming.push({blob,time,checked:true,name:`frame_${String(i + 1).padStart(4,'0')}.png`}); tell('sqVideoStatus',`抽取 ${i + 1} / ${count} 帧`);
      }
      if (cancelExtract || !taskIsCurrent(characterId,token) || signal.aborted) { tell('sqVideoStatus','已取消，保留原有帧。'); return; }
      freeFrames(raw); raw = hydrate(incoming); matteKeyCache=null; clearProcessed(); previewIndex = 0; lastChecked = -1; renderFrames(); await drawFrame(0); if (!taskIsCurrent(characterId,token)) return; save(); tell('sqVideoStatus',`已提取 ${raw.length} 帧，筛选完整动作周期后处理。`);
    } catch (error) { if (taskIsCurrent(characterId,token)) tell('sqVideoStatus','抽帧失败：' + error.message + '。旧帧已保留。'); }
    finally { extracting = false; extractController=null; $('#sqCancelExtract').hidden = true; updateButtons(); restoreActiveWhenIdle(); }
  };
  function invalidateSelection() { stopPlayback(); clearProcessed(); tell('sqProcessedMode','选帧已改变，旧处理结果已清理；可重新单帧预览或批量处理。'); drawFrame(previewIndex); save(); }
  function renderFrames() {
    const host = $('#sqFrames'); host.replaceChildren();
    raw.forEach((frame,index) => {
      const card = node('div',undefined,{class:'sq-frame' + (frame.checked ? ' selected' : '')}), img = node('img',undefined,{src:frame.url,alt:`第 ${index + 1} 帧`}), label = node('label'), check = node('input',undefined,{type:'checkbox'});
      check.checked = frame.checked;
      check.onclick = event => {
        const value = check.checked;
        if (event.shiftKey && lastChecked >= 0) for (let i = Math.min(index,lastChecked); i <= Math.max(index,lastChecked); i++) raw[i].checked = value;
        else frame.checked = value;
        lastChecked = index; invalidateSelection(); renderFrames();
      };
      img.onclick = () => { stopPlayback(); drawFrame(index); };
      label.append(check,document.createTextNode(`#${index + 1} · ${frame.time.toFixed(2)}s`)); card.append(img,label); host.append(card);
    });
    $('#sqFrameScrub').max = Math.max(0,raw.length - 1); updateButtons();
  }
  async function drawFrame(index, useProcessed = false, task = taskContext()) {
    if (useProcessed) return drawProcessedFrame(index,task);
    if (!raw.length) return;
    const drawToken = ++frameDrawToken;
    index = Math.max(0,Math.min(raw.length - 1,index)); previewIndex = index;
    const frame = raw[index], img = await loadImage(frame.blob);
    if (!task || !task.valid() || drawToken !== frameDrawToken) { img.close(); return; }
    const c = $('#sqFrameCanvas'); c.width = img.width; c.height = img.height; c.getContext('2d').drawImage(img,0,0); img.close();
    $('#sqFrameScrub').value = index;
    tell('sqFrameLabel',`原始第 ${index + 1} / ${raw.length} 张 · ${frame.checked ? '已选' : '未选'} · ${Number(frame.time || 0).toFixed(3)} 秒 · ${c.width} × ${c.height} px · ${frame.name}`);
  }
  function alphaInfo(data) {
    let transparent = 0, fullyTransparent = 0;
    const pixels = data.length / 4;
    for (let i = 3; i < data.length; i += 4) { if (data[i] < 255) transparent++; if (!data[i]) fullyTransparent++; }
    return {transparentRatio:transparent / pixels, empty:fullyTransparent === pixels};
  }
  function renderProcessedFrames() {
    const host = $('#sqProcessedFrames'); host.replaceChildren();
    processed.forEach((frame,index) => {
      const card = node('div',undefined,{class:'sq-frame'}), b = button('',() => { stopPlayback(); drawProcessedFrame(index); });
      b.title = `批处理第 ${index + 1} 张 · 原始第 ${sourceIndex(frame) + 1} 张`;
      b.append(node('img',undefined,{src:frame.url,alt:b.title}));
      card.append(b,node('span',`#${index + 1} / 原#${sourceIndex(frame) + 1}`,{class:'sq-meta'})); host.append(card);
    });
    $('#sqProcessedScrub').max = Math.max(0,processed.length - 1);
  }
  function sourceIndex(frame) { return Number.isInteger(frame.sourceIndex) ? frame.sourceIndex : raw.findIndex(f => f.name === frame.name && f.time === frame.time); }
  async function drawProcessedFrame(index, task = taskContext(), trial = null) {
    if (!task || (!trial && !processed.length)) return;
    index = Math.max(0,Math.min(processed.length - 1,index));
    const frame = trial || processed[index], drawToken = ++processedDrawToken, img = await loadImage(frame.blob);
    if (!task.valid() || drawToken !== processedDrawToken) { img.close(); return; }
    const c = $('#sqProcessedCanvas'); c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d',{willReadFrequently:true}); ctx.drawImage(img,0,0); img.close();
    const info = alphaInfo(ctx.getImageData(0,0,c.width,c.height).data), source = sourceIndex(frame);
    if (!trial) { singlePreview = null; processedIndex = index; $('#sqProcessedScrub').value = index; }
    updateButtons(); updateMattePreviewBackground();
    tell('sqProcessedMode',trial ? '单帧试看 · 尚未批量应用，下载与带入仍使用已有批处理结果。' : `批处理结果 · 共 ${processed.length} 张，可播放、下载或带入 Spine。`);
    tell('sqProcessedLabel',`${trial ? '单帧试看' : `批处理第 ${index + 1} / ${processed.length} 张`} · 原始第 ${source >= 0 ? source + 1 : '未知'} / ${raw.length} 张 · ${Number(frame.time || 0).toFixed(3)} 秒 · ${c.width} × ${c.height} px · 透明像素（α<255）${(info.transparentRatio * 100).toFixed(1)}%${info.empty ? ' · 警告：全透明' : ''}`);
    $('#sqProcessedFrames').querySelectorAll('button').forEach((b,i) => b.classList.toggle('active',!trial && i === index));
  }
  $('#sqProcessedScrub').oninput = () => { stopPlayback(); drawProcessedFrame(Number($('#sqProcessedScrub').value)); };
  $('#sqShowProcessed').onclick = () => { stopPlayback(); drawProcessedFrame(Number($('#sqProcessedScrub').value)); };
  $('#sqPlayProcessed').onclick = () => {
    if (playbackKind === 'processed') return stopPlayback();
    if (!processed.length) return;
    play(processed,Number($('#sqFps').value),(_,i) => drawProcessedFrame(i)); playbackKind = 'processed'; $('#sqPlayProcessed').textContent = '停止播放处理帧';
  };
  $('#sqFrameScrub').oninput = () => { stopPlayback(); drawFrame(Number($('#sqFrameScrub').value)); };
  $('#sqAll').onclick = () => { raw.forEach(f => f.checked = true); invalidateSelection(); renderFrames(); };
  $('#sqNone').onclick = () => { raw.forEach(f => f.checked = false); invalidateSelection(); renderFrames(); };
  async function play(list, fps, draw, loopPlayback = true) {
    const task=taskContext();if(!task)return;
    stopPlayback(); const token = playToken; let index = 0;
    async function next() {
      if (!task.valid() || token !== playToken || !list.length) return;
      if (index >= list.length) { if (!loopPlayback) { stopPlayback(); return; } index = 0; }
      const before = performance.now(); await draw(list[index],index); index++;
      if (task.valid() && token === playToken) playbackTimer = setTimeout(() => next().catch(fail),Math.max(0,1000 / fps - (performance.now() - before)));
    }
    function fail(error) { if(task.valid() && token===playToken){stopPlayback();tell('sqProcessStatus','播放失败：'+error.message);} }
    next().catch(fail);
    return token;
  }
  $('#sqPlayFrames').onclick = () => {
    if (playbackKind === 'raw') return stopPlayback(); const list = selected(); if (!list.length) return;
    if (!taskContext()) return;
    play(list,Number($('#sqFps').value),frame => drawFrame(raw.indexOf(frame))); playbackKind = 'raw'; $('#sqPlayFrames').textContent = '停止播放';
  };
  function download(blob,name) { const url = URL.createObjectURL(blob), a = node('a',undefined,{href:url,download:name}); a.click(); setTimeout(() => URL.revokeObjectURL(url),30000); }
  async function downloadFrames(frames,name) {
    const task=taskContext();if(!task||!frames.length||busy)return;const list=frames.slice();busy=true;updateButtons();
    try{const items=await Promise.all(list.map((f,i)=>f.blob.arrayBuffer().then(data=>({name:`frame_${String(i+1).padStart(4,'0')}.png`,data}))));if(task.valid())download(zip(items),name);}
    catch(error){if(task.valid())throw error;}finally{busy=false;updateButtons();restoreActiveWhenIdle();}
  }
  $('#sqRawZip').onclick = () => downloadFrames(selected(),'original_frames.zip').catch(error => tell('sqVideoStatus',error.message));
  $('#sqProcessedZip').onclick = () => downloadFrames(processed,'processed_frames.zip').catch(error => tell('sqProcessStatus',error.message));
  const colorRgb = hex => [1,3,5].map(i => parseInt(hex.slice(i,i + 2),16));
  function sampleBorder(data,width,height) {
    const buckets = new Map();
    const sample = (x,y) => { const i = (y * width + x) * 4; if (data[i + 3] < 200) return; const color = [data[i],data[i+1],data[i+2]].map(n => Math.min(255,Math.round(n / 24) * 24)), key = color.join(','); const b = buckets.get(key) || {color,count:0}; b.count++; buckets.set(key,b); };
    for (let x = 0; x < width; x += Math.max(1,Math.floor(width / 100))) { sample(x,0); sample(x,height - 1); }
    for (let y = 0; y < height; y += Math.max(1,Math.floor(height / 100))) { sample(0,y); sample(width - 1,y); }
    return [...buckets.values()].sort((a,b) => b.count - a.count)[0]?.color || [0,255,0];
  }
  let segmentation = null, segmentResult = null, segmentationReady = null;
  async function getSegmentation() {
    if (segmentation) return segmentation;
    if (!segmentationReady) segmentationReady = new Promise((resolve,reject) => {
      const script = node('script',undefined,{src:'https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1.1675465747/selfie_segmentation.js'});
      script.onload = resolve; script.onerror = () => reject(new Error('MediaPipe 组件下载失败，请检查网络或改用纯色抠图。')); document.head.append(script);
    });
    await segmentationReady;
    segmentation = new window.SelfieSegmentation({locateFile:file => 'https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1.1675465747/' + file});
    segmentation.setOptions({modelSelection:1}); segmentation.onResults(result => { if (segmentResult) segmentResult(result); }); return segmentation;
  }
  function settings() {
    return {mode:$('#sqMatte').value,key:$('#sqColorPreset').value,color:$('#sqColor').value,tolerance:Number($('#sqTolerance').value),spill:Number($('#sqSpill').value)/100,feather:Number($('#sqFeather').value),smooth:$('#sqSmooth').checked,edgeClean:Number($('#sqEdgeClean').value),size:$('#sqSize').value,width:Number($('#sqWidth').value),height:Number($('#sqHeight').value),quality:$('#sqQuality').value,corners:[...document.querySelectorAll('[data-sq-corner]:checked')].map(n => n.dataset.sqCorner),cornerPercent:Number($('#sqCornerPercent').value)};
  }
  function applySettings(value) {
    $('#sqMatte').value=value.mode; $('#sqColorPreset').value=value.key; $('#sqColor').value=value.color;
    $('#sqTolerance').value=value.tolerance; $('#sqSpill').value=Math.round(value.spill*100); $('#sqFeather').value=value.feather; $('#sqSmooth').checked=value.smooth !== false; $('#sqEdgeClean').value=value.edgeClean ?? 1;
    $('#sqSize').value=value.size; $('#sqWidth').value=value.width; $('#sqHeight').value=value.height;
    $('#sqQuality').value=value.quality; $('#sqCornerPercent').value=value.cornerPercent;
    document.querySelectorAll('[data-sq-corner]').forEach(input => { input.checked=value.corners.includes(input.dataset.sqCorner); });
    updateParameterValues();
    tell('sqMatteNote',value.mode==='mediapipe'?'首次使用需联网下载 MediaPipe 模型；在本机运行，不上传视频。模型针对人像，对玩偶/非人角色可能分割不准确。':'纯色抠图：连通背景 + 边缘混色还原；自动色锁定同一批首帧。高容差安全限幅，保留内部同色配件；烘焙阴影、封闭同色孔洞无法可靠自动分离。');
  }
  async function matteKey(options, imageData, width, height) {
    if (options.key !== 'auto') return options.key === 'custom' ? colorRgb(options.color) : colorRgb(options.key);
    // 始终从这一批原始帧的第一张估色；先试看哪张、勾选哪些帧都不改变背景色。
    const first = raw[0];
    if (!first) return Array.from(window.SequenceMatting.sampleBackground(imageData,width,height).key);
    if (!matteKeyCache || matteKeyCache.first !== first) {
      const entry = {first,promise:null};
      entry.promise = (async () => {
        const img = await loadImage(first.blob), sample = canvas(img.width,img.height);
        const ctx = sample.getContext('2d',{willReadFrequently:true});
        try { ctx.drawImage(img,0,0); return Array.from(window.SequenceMatting.sampleBackground(ctx.getImageData(0,0,sample.width,sample.height).data,sample.width,sample.height).key); }
        finally { img.close(); }
      })().catch(error => { if (matteKeyCache === entry) matteKeyCache = null; throw error; });
      matteKeyCache = entry;
    }
    return matteKeyCache.promise;
  }
  async function processFrame(frame, options) {
    const img = await loadImage(frame.blob), c = canvas(img.width,img.height), ctx = c.getContext('2d',{willReadFrequently:true}); ctx.drawImage(img,0,0); img.close();
    if (options.mode === 'mediapipe') {
      const model = await getSegmentation();
      const mask = await new Promise((resolve,reject) => { const timeout = setTimeout(() => reject(new Error('MediaPipe 分割超时。')),30000); segmentResult = result => { clearTimeout(timeout); const copy = canvas(c.width,c.height); copy.getContext('2d').drawImage(result.segmentationMask,0,0,c.width,c.height); resolve(copy); }; model.send({image:c}).catch(reject); });
      ctx.globalCompositeOperation = 'destination-in'; ctx.drawImage(mask,0,0); ctx.globalCompositeOperation = 'source-over';
    } else if (options.mode === 'chroma') {
      const imageData = ctx.getImageData(0,0,c.width,c.height), data = imageData.data;
      if (!window.SequenceMatting) throw new Error('边缘抠图组件未加载，请刷新工作台。');
      const key = await matteKey(options,data,c.width,c.height);
      const report = window.SequenceMatting.keyImage(data,c.width,c.height,{key,tolerance:options.tolerance,feather:options.feather,smooth:options.smooth,spill:options.spill,edgeClean:options.edgeClean,edgeChoke:Math.max(0,Math.min(1,(options.edgeClean-1)/2))});
      ctx.putImageData(imageData,0,0);
      if (report.toleranceLimited) tell('sqMatteNote',`容差${options.tolerance}已安全限制到${report.effectiveTolerance.toFixed(1)}，避免吞掉浅色角色；背景估计RGB ${report.key.map(Math.round).join(', ')}。${report.warnings.at(-1)}`);
    }
    const cornerW = Math.ceil(c.width * options.cornerPercent / 100), cornerH = Math.ceil(c.height * options.cornerPercent / 100);
    for (const corner of options.corners) ctx.clearRect(corner.endsWith('r') ? c.width-cornerW : 0,corner.startsWith('b') ? c.height-cornerH : 0,cornerW,cornerH);
    const w = options.size === 'original' ? c.width : options.size === 'custom' ? options.width : Number(options.size), h = options.size === 'original' ? c.height : options.size === 'custom' ? options.height : Number(options.size);
    if (w > 2048 || h > 2048) throw new Error('输出单帧不超过 2048 像素；请选择较小尺寸。');
    const output = canvas(w,h), out = output.getContext('2d'), scale = Math.min(w/c.width,h/c.height);
    out.imageSmoothingEnabled = options.quality !== 'pixel'; out.imageSmoothingQuality = options.quality === 'medium' ? 'medium' : 'high'; out.drawImage(c,(w-c.width*scale)/2,(h-c.height*scale)/2,c.width*scale,c.height*scale);
    return {...frame,sourceIndex:sourceIndex(frame),blob:await blobFromCanvas(output),url:undefined};
  }
  function updateMattePreviewBackground() {
    const c = $('#sqProcessedCanvas'), color = $('#sqMattePreviewBg').value;
    c.style.backgroundImage = color === 'checker' ? '' : 'none';
    c.style.backgroundColor = color === 'checker' ? '' : color;
  }
  $('#sqMattePreviewBg').onchange = updateMattePreviewBackground;
  function updateParameterValues() {
    for (const [id,suffix] of [['sqTolerance',' / 255'],['sqSpill','%'],['sqFeather',' / 30'],['sqEdgeClean',' / 3'],['sqCornerPercent','%'],['sqColor','']]) tell(id + 'Value',$('#' + id).value + suffix);
  }
  function processingChanged() { updateParameterValues(); clearProcessed(); tell('sqProcessedMode','参数已改变，旧处理结果已清理；点击“试抠”可重新预览，批处理后才能下载或带入。'); tell('sqProcessStatus','参数已改变，请重新预览或处理选中帧。'); save(); }
  $('#sqMatte').onchange = () => { processingChanged(); tell('sqMatteNote',$('#sqMatte').value === 'mediapipe' ? '首次使用需联网下载 MediaPipe 模型；在本机运行，不上传视频。模型针对人像，对玩偶/非人角色可能分割不准确。' : '纯色抠图：连通背景 + 边缘混色还原；自动色锁定同一批首帧。高容差安全限幅，保留内部同色配件；烘焙阴影、封闭同色孔洞无法可靠自动分离。'); };
  for (const id of ['sqColorPreset','sqColor','sqTolerance','sqSpill','sqFeather','sqSmooth','sqEdgeClean','sqSize','sqWidth','sqHeight','sqQuality','sqCornerPercent']) $('#' + id).addEventListener('input',processingChanged);
  document.querySelectorAll('[data-sq-corner]').forEach(input => input.onchange = processingChanged);
  for (const [id,checked] of [['sqCornersAll',true],['sqCornersNone',false]]) $('#' + id).onclick = () => { document.querySelectorAll('[data-sq-corner]').forEach(input => { input.checked = checked; }); processingChanged(); };
  $('#sqPreviewProcessed').onclick = async () => {
    const task=taskContext(); if (!task || !raw.length) return; const index=previewIndex, options=settings(); stopPlayback(); processing=true; updateButtons();
    try { const frame=await processFrame(raw[index],options); if(!task.valid())return; singlePreview=frame; await drawProcessedFrame(0,task,singlePreview); if(!task.valid())return; tell('sqProcessStatus',`原始第 ${index+1} 帧的单帧试看（尚未批量应用，未替换批处理结果）。`); }
    catch(error){if(task.valid())tell('sqProcessStatus',error.message);} finally{processing=false;updateButtons();restoreActiveWhenIdle();}
  };
  $('#sqPreviewCurrent').onclick = () => $('#sqPreviewProcessed').click();
  $('#sqProcess').onclick = async () => {
    const task=taskContext(),list=selected(); if(!task||!list.length)return;const options=settings();processing=true;stopPlayback();updateButtons();const incoming=[];
    try { for(let i=0;i<list.length;i++){incoming.push(await processFrame(list[i],options));if(!task.valid())return;tell('sqProcessStatus',`处理 ${i+1} / ${list.length} 帧`);}if(!task.valid())return;clearProcessed();processed=hydrate(incoming);renderProcessedFrames();await drawProcessedFrame(0,task);if(!task.valid())return;tell('sqProcessStatus',`完成 ${processed.length} 帧，可直接带入 Spine。`);save(); }
    catch(error){if(task.valid())tell('sqProcessStatus','处理失败：'+error.message);}finally{processing=false;updateButtons();restoreActiveWhenIdle();}
  };
  $('#sqSheetLayout').onchange = () => { $('#sqSheetColumns').disabled = $('#sqSheetLayout').value === 'horizontal'; };
  $('#sqSheetLayout').onchange();
  $('#sqSheet').onclick = async () => {
    const task=taskContext(),list=processed.slice(),layout=$('#sqSheetLayout').value,columns=Number($('#sqSheetColumns').value);if(!task||!list.length)return;busy=true;updateButtons();
    try {
      const first=await loadImage(list[0].blob),w=first.width,h=first.height;first.close();if(!task.valid())return;
      const cols=layout==='horizontal'?list.length:Math.max(1,Math.min(list.length,Math.floor(columns||10))),rows=Math.ceil(list.length/cols),c=canvas(w*cols,h*rows),ctx=c.getContext('2d');
      for(let i=0;i<list.length;i++){const img=await loadImage(list[i].blob);if(!task.valid()){img.close();return;}ctx.drawImage(img,i%cols*w,Math.floor(i/cols)*h);img.close();}
      const blob=await blobFromCanvas(c);if(!task.valid())return;if(sheetUrl)URL.revokeObjectURL(sheetUrl);sheetUrl=URL.createObjectURL(blob);$('#sqSheetPreview').src=sheetUrl;$('#sqSheetPreview').hidden=false;tell('sqSheetInfo',`${c.width} × ${c.height} · ${rows} 行 ${cols} 列`);download(blob,'sprite_sheet.png');
    }catch(error){if(task.valid())tell('sqSheetInfo',error.message);}finally{busy=false;updateButtons();restoreActiveWhenIdle();}
  };

  function groupId() {
    // randomUUID is secure-context-only; LAN HTTP still provides getRandomValues.
    if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
    if (typeof globalThis.crypto?.getRandomValues === 'function') {
      const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
      const hex = Array.from(bytes, byte => byte.toString(16).padStart(2,'0')).join('');
      return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
    }
    // A local draft identifier, never an authentication or authorization token.
    return `group_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
  }
  function newGroup(frames = [], name = '') { return {id:groupId(),name:name || `animation_${groups.length+1}`,fps:Number($('#sqFps').value) || 20,event:'',eventFrame:1,loop:true,frames,rows:1,columns:1,sheet:null}; }
  function cloneFrames(list) { return hydrate(serialize(list)); }
  $('#sqToSpine').onclick = () => {
    if (!processed.length) return; const name = [state.viewId,state.action].filter(Boolean).join('_');
    let unique = name; let i = 2; while (unique && groups.some(g => g.name === unique)) unique = name + '_' + i++;
    const group = newGroup(cloneFrames(processed),unique); group.sourceTaskId = state.taskId; groups.push(group); renderGroups(); selectGroup(group.id); save(); showTab('spineSequence');
  };
  $('#sqAddGroup').onclick = () => { const group = newGroup(); groups.push(group); renderGroups(); selectGroup(group.id); save(); };
  function button(text,fn) { const b = node('button',text,{type:'button'}); b.onclick = fn; return b; }
  function field(label,input) { const n = node('label',label); n.append(input); return n; }
  function renderGroups() {
    const host = $('#sqGroups'); host.replaceChildren();
    if (!groups.length) { const empty = node('div',undefined,{class:'card'}); empty.append(node('p','尚无动画组。视频处理后点击“带入 Spine 动画组”，也可以添加组并导入已有连续 PNG / 帧表。')); host.append(empty); }
    groups.forEach((group,index) => {
      const card = node('article',undefined,{class:'sq-group','data-group-id':group.id}), head = node('div',undefined,{class:'sq-group-head'}), fields = node('div',undefined,{class:'sq-grid'});
      head.append(node('h3',`动画组 ${index+1} · ${group.frames.length} 帧`),button('移除组',() => { if (group.frames.length && !confirm('移除本工作台中的动画组？源文件与视频处理帧不受影响。')) return; stopPlayback(); freeFrames(group.frames); groups = groups.filter(g => g!==group); renderGroups(); save(); }));
      for (const [key,label,type] of [['name','动画名称','text'],['fps','播放帧率 / FPS','number']]) { const input = node('input',undefined,{type,value:group[key]}); if(type==='number'){input.min=1;input.max=60;} input.onchange = () => { group[key] = type === 'number' ? Number(input.value) : input.value; refreshGroupSelect(group.id); save(); }; fields.append(field(label,input)); }
      const row = node('div',undefined,{class:'sq-row'}), files = node('input',undefined,{type:'file',accept:'image/png,image/jpeg,image/webp',multiple:'',class:'sq-input-file'}), sheet = node('input',undefined,{type:'file',accept:'image/png,image/jpeg,image/webp',class:'sq-input-file'});
      row.append(button('导入连续帧',() => files.click()),button('导入帧表',() => sheet.click()),button('预览本组',() => { selectGroup(group.id); previewAnimation(); }),files,sheet);
      files.onchange = () => runImport(async task => {
        const list = [...files.files]; if (!list.length || !groups.includes(group)) return; if (list.length > 600 || list.reduce((n,f) => n+f.size,0)>128*1024*1024) throw new Error('每组最多 600 帧 / 128 MiB。');
        if (group.frames.length && !confirm('替换此组原有帧？')) return;
        const incoming = list.sort((a,b) => a.name.localeCompare(b.name,undefined,{numeric:true})).map(file => ({name:file.name,blob:file}));
        if (!task.valid() || !groups.includes(group)) return;
        freeFrames(group.frames); group.frames = hydrate(incoming); renderGroups(); selectGroup(group.id); save();
      });
      sheet.onchange = () => runImport(async task => {
        const file = sheet.files[0]; if (!file || !groups.includes(group)) return;
        const img = await loadImage(file); if (!task.valid() || !groups.includes(group)) { img.close(); return; }
        group.sheet=file; group.rows=1; group.columns=Math.max(1,Math.round(img.width/img.height)); img.close(); renderGroups(); save();
      });
      card.append(head,fields,row);
      if (group.sheet) {
        const splitPanel = node('div',undefined,{class:'sq-grid'});
        for (const [key,label] of [['rows','帧表行数'],['columns','帧表列数']]) { const input=node('input',undefined,{type:'number',min:'1',max:'600',value:group[key]}); input.onchange=()=>{group[key]=Number(input.value);save();}; splitPanel.append(field(label,input)); }
        splitPanel.append(button('按行列切分并替换本组帧',() => runImport(async task => {
          if (!groups.includes(group) || (group.frames.length && !confirm('用帧表切分结果替换此组帧？'))) return;
          const incoming = await splitSheet(group.sheet,group.rows,group.columns,task); if (!task.valid() || !groups.includes(group)) return;
          freeFrames(group.frames); group.frames=hydrate(incoming); group.sheet=null; renderGroups(); selectGroup(group.id); save();
        })));
        card.append(node('p',group.sheet.name+' · 行列为建议值，请按原始帧表确认；透明空白格会跳过。',{class:'sq-meta'}),splitPanel);
      }
      const mini = node('div',undefined,{class:'sq-mini'}); let selectedIndex = 0;
      const count = node('span','点击帧后可前移/后移排序',{class:'sq-meta'}), reorder = node('div',undefined,{class:'sq-row'});
      const move = delta => { const target=selectedIndex+delta;if(target<0||target>=group.frames.length)return; [group.frames[selectedIndex],group.frames[target]]=[group.frames[target],group.frames[selectedIndex]];selectedIndex=target;renderMini();save(); };
      function renderMini() {
        mini.replaceChildren(); group.frames.forEach((frame,i) => { const b=button('',()=>{selectedIndex=i;renderMini();selectGroup(group.id);$('#sqAnimationScrub').value=i;drawAnimationFrame(group,i);});b.classList.toggle('active',i===selectedIndex);b.title=`#${i+1} ${frame.name}`;b.append(node('img',undefined,{src:frame.url,alt:frame.name}));b.draggable=true;b.ondragstart=e=>e.dataTransfer.setData('text/plain',group.id+':'+i);b.ondragover=e=>e.preventDefault();b.ondrop=e=>{e.preventDefault();const [id,from]=e.dataTransfer.getData('text/plain').split(':');if(id!==group.id)return;const f=Number(from);if(!Number.isInteger(f)||!group.frames[f])return;const [item]=group.frames.splice(f,1);group.frames.splice(i,0,item);selectedIndex=i;renderMini();save();};mini.append(b); });
        count.textContent=group.frames.length ? `第 ${selectedIndex+1} / ${group.frames.length} 帧 · 可拖动排序` : '尚无帧';
      }
      reorder.append(button('前移',()=>move(-1)),button('后移',()=>move(1)),button('文件名排序',()=>{group.frames.sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));renderMini();save();}),count);renderMini();card.append(mini,reorder);
      const details=node('details',undefined,{class:'sq-advanced'});details.append(node('summary','事件与循环设置'));
      const advanced=node('div',undefined,{class:'sq-grid'}), event=node('input',undefined,{value:group.event,placeholder:'可选，如 footstep'}), eventFrame=node('input',undefined,{type:'number',min:'1',max:Math.max(1,group.frames.length),value:group.eventFrame});
      event.onchange=()=>{group.event=event.value.trim();save();};eventFrame.oninput=()=>{group.eventFrame=Number(eventFrame.value);selectGroup(group.id);drawAnimationFrame(group,group.eventFrame-1);};eventFrame.onchange=save;
      const loopCheck=node('input',undefined,{type:'checkbox'});loopCheck.checked=group.loop;loopCheck.onchange=()=>{group.loop=loopCheck.checked;save();};advanced.append(field('事件名称',event),field('触发帧',eventFrame));details.append(advanced,field('循环预览 / 导出首尾衔接',loopCheck));card.append(details);host.append(card);
    });
    refreshGroupSelect();
  }
  async function runImport(fn) { const task=taskContext();if(!task||busy)return;busy=true;updateButtons();try{await fn(task);if(task.valid())tell('sqExportStatus','已更新动画组。');}catch(error){if(task.valid())tell('sqExportStatus','导入失败：'+error.message);}finally{busy=false;updateButtons();restoreActiveWhenIdle();} }
  async function splitSheet(file,rows,cols,task) {
    if(!Number.isInteger(rows)||!Number.isInteger(cols)||rows<1||cols<1||rows*cols>600)throw new Error('行列必须为正整数，最多 600 格。');
    const img=await loadImage(file),w=img.width/cols,h=img.height/rows,result=[];
    try {
      if (!task.valid()) return [];
      if(!Number.isInteger(w)||!Number.isInteger(h))throw new Error('帧表尺寸无法按当前行列整除，请确认原始行列。');
      for(let y=0;y<rows;y++)for(let x=0;x<cols;x++) { const c=canvas(w,h),ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,x*w,y*h,w,h,0,0,w,h);const data=ctx.getImageData(0,0,w,h).data;let visible=false;for(let i=3;i<data.length;i+=4)if(data[i]){visible=true;break;}if(!visible)continue;result.push({name:`frame_${String(y*cols+x+1).padStart(4,'0')}.png`,blob:await blobFromCanvas(c)}); if(!task.valid())return []; }
      if(!result.length)throw new Error('没有检测到非透明有效帧。');return result;
    }finally{img.close();}
  }
  function refreshGroupSelect(preferred) { const select=$('#sqPreviewGroup'),previous=preferred||select.value;select.replaceChildren(...groups.map(g=>node('option',g.name||'未命名',{value:g.id})));if(groups.some(g=>g.id===previous))select.value=previous; }
  function selectGroup(id,draw=true) { stopPlayback();refreshGroupSelect(id);const group=groups.find(g=>g.id===id);$('#sqAnimationScrub').max=Math.max(0,(group?.frames.length||1)-1);$('#sqAnimationScrub').value=0;if(draw&&group?.frames.length)drawAnimationFrame(group,0); }
  async function drawAnimationFrame(group,index,task=taskContext()) {
    if(!group?.frames.length||!task)return;index=Math.max(0,Math.min(group.frames.length-1,index));const drawToken=++animationDrawToken;
    const img=await loadImage(group.frames[index].blob);
    if(!task.valid()||drawToken!==animationDrawToken||!groups.includes(group)){img.close();return;}
    const c=$('#sqAnimationCanvas'),ctx=c.getContext('2d'),scale=Math.min(c.width/img.width,c.height/img.height);
    ctx.fillStyle=$('#sqPreviewBg').value;ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,(c.width-img.width*scale)/2,(c.height-img.height*scale)/2,img.width*scale,img.height*scale);img.close();$('#sqAnimationScrub').value=index;tell('sqAnimationLabel',`${index+1} / ${group.frames.length}`);
  }
  function previewAnimation() { const group=groups.find(g=>g.id===$('#sqPreviewGroup').value);if(!group?.frames.length)return;play(group.frames,group.fps,(_,i)=>drawAnimationFrame(group,i),group.loop);playbackKind='animation';$('#sqPlay').textContent='停止'; }
  $('#sqPlay').onclick=()=>playbackKind==='animation'?stopPlayback():previewAnimation();
  $('#sqPreviewGroup').onchange=()=>selectGroup($('#sqPreviewGroup').value);
  $('#sqAnimationScrub').oninput=()=>{stopPlayback();drawAnimationFrame(groups.find(g=>g.id===$('#sqPreviewGroup').value),Number($('#sqAnimationScrub').value));};
  $('#sqPreviewBg').oninput=()=>drawAnimationFrame(groups.find(g=>g.id===$('#sqPreviewGroup').value),Number($('#sqAnimationScrub').value));
  $('#sqExport').onclick=async()=>{
    const task=taskContext();if(!task||busy)return;busy=true;$('#sqExport').disabled=true;updateButtons();
    const exportGroups=groups.map(g=>({...g,frames:g.frames.slice()}));
    try{
      validateGroups(exportGroups);const filename=$('#sqFilename').value.trim().replace(/[\\/:*?"<>|\x00-\x1f]/g,'_')||'character_animation',version=$('#sqVersion').value,regions=[];
      for(const group of exportGroups)for(const frame of group.frames){const img=await loadImage(frame.blob);if(!task.valid()){img.close();return;}regions.push({id:'frame_'+regions.length,groupId:group.id,blob:frame.blob,width:img.width,height:img.height});img.close();}
      const packed=packRegions(regions),{width,height,padding}=packed;
      regions.splice(0,regions.length,...packed.regions);
      const c=canvas(width,height),ctx=c.getContext('2d',{willReadFrequently:true}),emptyFrames=[];
      for(let i=0;i<regions.length;i++){
        const r=regions[i],img=await loadImage(r.blob);if(!task.valid()){img.close();return;}
        // 每帧保留独立 2px 外圈并挤出边缘，避免线性采样读到相邻帧。
        ctx.drawImage(img,r.x,r.y);
        ctx.drawImage(img,0,0,1,r.height,r.x-padding,r.y,padding,r.height);
        ctx.drawImage(img,r.width-1,0,1,r.height,r.x+r.width,r.y,padding,r.height);
        ctx.drawImage(img,0,0,r.width,1,r.x,r.y-padding,r.width,padding);
        ctx.drawImage(img,0,r.height-1,r.width,1,r.x,r.y+r.height,r.width,padding);
        for(const sx of [0,r.width-1])for(const sy of [0,r.height-1])ctx.drawImage(img,sx,sy,1,1,sx===0?r.x-padding:r.x+r.width,sy===0?r.y-padding:r.y+r.height,padding,padding);
        img.close();
        if(alphaInfo(ctx.getImageData(r.x,r.y,r.width,r.height).data).empty)emptyFrames.push(`${exportGroups.find(g=>g.id===r.groupId)?.name} / ${r.id}`);
        tell('sqExportStatus',`打包纹理 ${i+1} / ${regions.length}`);
      }
      const info=alphaInfo(ctx.getImageData(0,0,width,height).data),png=await blobFromCanvas(c);
      if(!task.valid())return;
      clearAtlasPreview();atlasUrl=URL.createObjectURL(png);$('#sqAtlasPreview').src=atlasUrl;$('#sqAtlasPreview').hidden=false;
      tell('sqAtlasInfo',`导出 PNG · ${width} × ${height} px · ${regions.length} 帧 · 透明像素（α<255）${(info.transparentRatio*100).toFixed(1)}% · 每侧 ${padding}px padding / 边缘挤出`);
      tell('sqAtlasWarnings',emptyFrames.length?`警告：${emptyFrames.length} 帧全透明（已原样保留，未删除或更改动画时序）：\n${emptyFrames.join('、')}`:'透明验查完成：未发现全透明帧。');
      const json=spineJson(exportGroups,regions,version),files=[{name:filename+'.json',blob:new Blob([JSON.stringify(json,null,2)],{type:'application/json'})},{name:filename+'.atlas',blob:new Blob([atlasText(filename,width,height,regions)],{type:'text/plain'})},{name:filename+'.png',blob:png}];
      if(!task.valid())return;
      const entries=await Promise.all(files.map(async f=>({name:f.name,data:await f.blob.arrayBuffer()})));if(!task.valid())return;download(zip(entries),filename+'_spine_'+version+'.zip');
      const host=$('#sqExportFiles');host.replaceChildren(...files.map(f=>button('下载 '+f.name,()=>download(f.blob,f.name))));tell('sqExportStatus',`${exportGroups.length} 组 · ${regions.length} 帧 · ${width} × ${height}\n已生成 Spine ${version} ZIP；尚未在目标 Spine / Unity 运行库实机验证。`);
    }catch(error){if(task.valid())tell('sqExportStatus','导出失败：'+error.message);}finally{busy=false;$('#sqExport').disabled=false;updateButtons();restoreActiveWhenIdle();}
  };
  for (const id of uiIds) for (const event of ['input','change']) $('#' + id).addEventListener(event,() => save());
  $('#sqPreviewGroup').addEventListener('change',() => save());
  $('#sqFrameScrub').addEventListener('input',() => save());
  $('#sqProcessedScrub').addEventListener('input',() => save());
  $('#sqAnimationScrub').addEventListener('input',() => save());
  $('#sqLoop').addEventListener('click',() => save());
  document.addEventListener('click',event=>{if(event.target.closest('[data-tab]'))stopPlayback();});
  window.addEventListener('cotton-character-changed',()=>{
    ++workflowToken; ++restoreToken; cancelExtraction(); cancelLoopAnalysis(); stopVideoLoop(); stopPlayback(); videoTask=null; restorePending=true;
    tell('sqVideoStatus','角色已切换，当前处理结果将丢弃并恢复新角色草稿。'); updateButtons();
    if(!(extracting||processing||busy))restoreActiveWhenIdle();
  });
  window.addEventListener('beforeunload',event=>{if(extracting||processing||busy){event.preventDefault();event.returnValue='';}});
  renderFrames();renderGroups();restore(currentCharacter());
})();
