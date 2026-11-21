(() => {
'use strict';
const host=document.querySelector('#tab-spineRig');if(!host)return;
host.dataset.videoWorkbenchBuilt='true';
const nav=document.querySelector('.workflow-tabs');
if(nav&&!nav.querySelector('[data-tab="spineRig"]')){const b=document.createElement('button');b.type='button';b.dataset.tab='spineRig';b.textContent='05 骨骼动画';b.onclick=()=>window.goToTab?.('spineRig');nav.append(b);}
const labels={arm_far:'远侧手臂',leg_far:'远侧腿',leg_near:'近侧腿',torso:'躯干',shorts:'裤衩',arm_near:'近侧手臂',head:'头部'};
const partColors={arm_far:'#9969c8',leg_far:'#378cac',leg_near:'#e8af47',torso:'#df8065',shorts:'#409b83',arm_near:'#6097db',head:'#b77a9e'};
const anchors={neck:'颈部',pelvis:'骨盆中心',shoulder_near:'近侧肩',shoulder_far:'远侧肩',hip_near:'近侧髋',hip_far:'远侧髋',hand_near:'近侧手端',hand_far:'远侧手端',foot_near:'近侧脚端',foot_far:'远侧脚端',arm_near:'近侧肘',arm_far:'远侧肘',leg_near:'近侧膝',leg_far:'远侧膝'};
host.innerHTML=`<div class="px-workbench">
<header><div><small>WALULU / SOURCE PIXEL STUDIO</small><h2>05 骨骼动画</h2></div><div class="px-actions"><select data-id="projects" aria-label="已保存工程"></select><button data-action="load">载入</button><button data-action="clone">从验收样板创建</button><button data-action="save">保存工程</button></div></header>
<section class="px-auto"><ol data-id="workflow" class="px-workflow" aria-label="制作流程"></ol><p data-id="nextHint"></p><button data-action="nextStep">下一步</button><h3>导入视频 → 自动生成 → 预览验收 → Spine 导出</h3><p>自动识别逐帧部件与关节，保留原视频 RGB。当前仅支持均匀背景的单角色视频；结果需要整段视觉验收。</p><details><summary>生成与恢复选项</summary><button data-action="auto">自动识别部件与骨骼</button><button data-action="autoStatus">查看生成进度</button><button data-action="build">生成动画预览</button></details><label><input type="checkbox" data-id="reviewedDiagnostics">我已核对整段效果及识别诊断</label><button data-action="autoAccept">登记人工验收通过</button><details><summary>自动检查结果 / 异常</summary><div data-id="exceptions"></div></details></section><p class="px-status" data-id="status" role="status">从已验收样板开始，或导入视频建立独立工程。</p>
<label><input data-id="advanced" type="checkbox"> 启用手工纠错（修改后须重新验收）</label><nav><button data-pane="reference">① 视频参考</button><button data-pane="parts">② 图集拆件</button><button data-pane="pose">③ 骨骼 / IK</button><button data-pane="inspect">④ 动画核查与导出</button></nav>
<section data-panel="reference"><div class="px-import"><select data-id="videoSources" aria-label="已导入的视频"><option value="">选择已有视频，或上传新视频</option></select><button data-action="analyze">分析视频并推荐区间</button><label>AI 视频 <input data-id="video" type="file" accept="video/mp4,video/webm"></label><label>起始源帧 <input data-id="start" type="number" min="0" value="0"></label><label>结束源帧（包含）<input data-id="end" type="number" min="0" value="23"></label><button data-action="import">使用此区间建立工程</button><button data-action="importAuto">使用此区间并自动生成</button><button data-action="seed">同视频载入起始标注草稿</button></div><p>先分析视频并预览推荐片段，也可以手动调整起止帧。保留原始分辨率和帧率，每次最多 120 帧。新视频使用自动识别入口；下方描边与锚点编辑保留为高级纠错工具。不会继承样板验收状态。</p><div data-id="analysis"></div><video data-id="referenceVideo" controls playsinline hidden aria-label="选段视频预览"></video><button data-action="previewSegment" hidden>播放所选片段</button><p data-id="segmentHint"></p></section>
<div class="px-grid"><aside><h3 data-id="tree-title">部件 / 来源</h3><div data-id="parts"></div><p>列表顺序从后到前。</p><button data-action="back">图层后移</button><button data-action="front">图层前移</button><hr><div data-id="info"></div></aside>
<main><div class="px-stage-head"><b data-id="stage-title">视频原帧与拆件</b><label><input data-id="bones" type="checkbox" checked> 骨骼</label><select data-id="display" aria-label="拆件显示模式"><option value="source">源视频帧</option><option value="assembly">拆件原位组装</option><option value="ownership">部件归属着色</option><option value="isolated">仅选中部件</option></select><label><input data-id="overlay" type="checkbox" checked> 原图垫底</label></div><div class="px-canvas-scroll"><canvas data-id="source" width="864" height="480" aria-label="源帧轮廓和骨骼编辑画布"></canvas><canvas data-id="preview" width="864" height="480" aria-label="Spine 实际动画预览" hidden></canvas></div><label>画布缩放 <select data-id="zoom" aria-label="画布缩放"><option value="100">适应宽度</option><option value="150">150%</option><option value="200">200%</option><option value="300">300%</option></select></label><p data-id="hint">导入视频或创建样板副本。</p></main>
<aside><section data-panel="parts"><h3>源像素轮廓</h3><p>点击源图逐点描边，再完成轮廓。只取当前源帧 RGB，不补画。隐藏区域可在其他源帧选择不同附件轮廓。</p><button data-action="cut">开始重描</button><button data-action="finish">完成轮廓</button><button data-action="cancel">取消描边</button><button data-action="reviewPart">确认此帧此部件</button><p data-id="part-state"></p></section>
<section data-panel="pose"><h3>骨骼与 IK 锚点</h3><select data-id="anchor" aria-label="要设置的关节点">${Object.entries(anchors).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><p>在原帧点击设置选中关节点。肩/髋 → 肘/膝 → 手/脚构成双骨 IK；绑定时按当前姿势反算权重。</p><button data-action="reviewPose">确认此帧骨骼</button><button data-action="copyPose">复制上一帧锚点（待审核）</button><label><input data-id="uniform" type="checkbox"> 均匀背景前景补全（仍只取原帧像素）</label><button data-action="track">从此帧追踪后续轮廓 / 锚点</button><p>追踪会覆盖后续帧的轮廓和锚点，并全部重置为待审核。先保存后再追踪。</p></section>
<section data-panel="inspect"><h3>同步动画检查</h3><p>附件、骨骼和 IK 逐帧保持。此模式复现视频，不能代替任意姿势连续蒙皮。</p><button data-action="build">保存并生成当前动画</button><button data-action="reviewExport">下载 Spine 待验收检查包</button><button data-action="export">导出真实 Spine 工程</button><div data-id="audit"></div><div data-id="download"></div></section>
<hr><button data-action="undo">撤销</button><button data-action="redo">重做</button><p data-id="progress"></p></aside></div>
<footer><button data-action="prev">上一帧</button><button data-action="play">播放 / 暂停</button><button data-action="next">下一帧</button><input data-id="seek" type="range" min="0" max="22" value="0" aria-label="时间轴"><span data-id="frame"></span><select data-id="phase" aria-label="帧内核查位置"><option value="0">帧起点</option><option value=".5">帧内中点</option><option value=".999">切换前</option></select><select data-id="speed" aria-label="播放速度"><option value="1">1×</option><option value=".25">0.25×</option></select></footer>
</div>`;
// Keep controls in task order: source -> generate -> inspect -> review -> deliver.
const autoPanel=host.querySelector('.px-auto');
const mainButton=autoPanel.querySelector('[data-action="nextStep"]');
const generation=document.createElement('section');generation.className='px-generation';
generation.innerHTML='<h3>② 自动制作</h3><p>确认区间后，系统完成拆件、骨骼与 IK、绑定及动画。新视频首次识别较慢；已缓存帧可续跑。</p>';
generation.append(mainButton,autoPanel.querySelector('details'));
host.querySelector('.px-status').after(generation);
const referencePanel=host.querySelector('section[data-panel="reference"]');generation.before(referencePanel);
referencePanel.insertAdjacentHTML('afterbegin','<h3>① 选视频与动作区间</h3>');
const inspectPanel=host.querySelector('section[data-panel="inspect"]');
const reviewBox=document.createElement('div');reviewBox.className='px-acceptance';reviewBox.innerHTML='<h3>⑤ Spine 检查后登记验收</h3>';
reviewBox.append(autoPanel.querySelector('label'),autoPanel.querySelector('[data-action="autoAccept"]'));
const delivery=document.createElement('div');delivery.className='px-delivery';delivery.innerHTML='<h3>⑥ 正式交付</h3>';delivery.append(inspectPanel.querySelector('[data-action="export"]'));inspectPanel.append(reviewBox,delivery);
inspectPanel.querySelector('h3').textContent='④ 下载 Spine 检查包';
const inspectionHeading=document.createElement('h3');inspectionHeading.textContent='③ 整段动画、拆件与 IK 检查';host.querySelector('.px-workbench nav').before(inspectionHeading);
const diagnostics=autoPanel.querySelector('details');
if(diagnostics)inspectPanel.prepend(diagnostics);
autoPanel.querySelector('h3').textContent='源视频 → 自动制作 → 整段检查 → Spine 验收 → 正式交付';
for(const b of host.querySelectorAll('[data-pane]'))b.textContent=b.textContent.replace(/^[①②③④] /,'');
host.querySelector('[data-action="clone"]').textContent='复制验收样板（非新视频入口）';
const $=id=>host.querySelector(`[data-id="${id}"]`),S={p:null,i:0,part:'head',pane:'reference',dirty:false,busy:false,cut:null,undo:[],redo:[],images:new Map(),seed:[],rig:null,playing:false,time:0,job:null,analysis:null,rangeEdited:false};
function status(t){$('status').textContent=t;}
async function api(action,payload={}){const r=await fetch('/api/pixel/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const v=await r.json();if(!r.ok||!v.ok)throw Error(v.error||'请求失败');return v;}
async function list(){const v=await api('list'),sel=$('projects');sel.replaceChildren(...v.projects.map(p=>{const o=new Option(p.name+' · r'+p.revision,p.id);return o}));if(S.p)sel.value=S.p.id;}
function dirty(){S.dirty=true;$('reviewedDiagnostics').checked=false;S.playing=false;S.rig=null;$('download').replaceChildren();$('audit').textContent='输入已修改，旧动画与旧下载已失效。';refresh();}
function checkpoint(){S.undo.push(JSON.stringify({frames:S.p.frames,order:S.p.order}));if(S.undo.length>50)S.undo.shift();S.redo=[];}
function frame(){return S.p.frames[S.i];}
function picture(url){if(!S.images.has(url)){const im=new Image();im.src=url;im.onload=draw;S.images.set(url,im)}return S.images.get(url);}
function base(){return '/studio_v3/pixel_projects/'+S.p.id;}
function restoreDownloads(){if(!S.p||S.dirty)return;const links=Object.values(S.p.exports||{}).filter(v=>v.revision===S.p.revision).map(v=>{const a=document.createElement('a');a.href=v.zipUrl;a.textContent=`下载 r${v.revision} ${v.kind==='technical_review'?'Spine 待验收检查包':'正式 Spine 包'}`;a.download='';return a;});$('download').replaceChildren(...links);}
function adopt(p){S.rangeEdited=false;clearTimeout(autoTimer);S.job=null;$('reviewedDiagnostics').checked=false;S.seed=[];if(p.baseline)fetch('/studio_v3/pixel_projects/'+p.id+'/seed_manifest.json').then(r=>r.json()).then(v=>{if(S.p===p){S.seed=v;draw()}});$('download').replaceChildren();$('audit').textContent='尚未生成当前动画。';S.p=p;$('start').value=p.source.start;$('end').value=p.source.end;$('projects').value=p.id;S.i=0;S.dirty=false;S.cut=null;S.undo=[];S.redo=[];S.rig=null;S.playing=false;localStorage.setItem('walulu-pixel-last',p.id);restoreDownloads();for(const id of ['source','preview']){$(id).width=p.source.width;$(id).height=p.source.height;}refresh();if(p.artifact)loadRig().catch(e=>status(e.message));autoStatus().catch(e=>status(e.message));}
function refresh(){
 for(const id of ['video','videoSources','start','end','projects','advanced'])$(id).disabled=S.busy;
 const selecting=!!(S.rangeEdited||S.analysis||$('video').files.length||$('videoSources').value);host.querySelector('.px-grid').hidden=selecting;host.querySelector('footer').hidden=selecting;
 const advanced=$('advanced').checked;for(const action of ['seed','track','cut','finish','cancel','reviewPart','reviewPose','copyPose','back','front'])host.querySelectorAll(`[data-action="${action}"]`).forEach(b=>b.hidden=!advanced);
 host.querySelectorAll('[data-panel]').forEach(e=>e.hidden=e.dataset.panel!==S.pane);
 host.querySelectorAll('[data-pane]').forEach(e=>e.setAttribute('aria-selected',String(e.dataset.pane===S.pane)));
 $('source').hidden=S.pane==='inspect'&&!!S.rig;$('preview').hidden=!$('source').hidden;
 $('display').hidden=S.pane==='inspect';
 $('stage-title').textContent=S.pane==='inspect'?'Spine 运行时 / 原帧同步核查':S.pane==='pose'?'原帧关节标注':'原帧附件轮廓';
 host.querySelectorAll('button').forEach(b=>{b.disabled=S.busy||(!S.p&&!['clone','load','import','importAuto','analyze'].includes(b.dataset.action)&&!b.dataset.pane)});
 if(selecting)host.querySelectorAll('[data-pane]').forEach(b=>b.disabled=b.dataset.pane!=='reference'||S.busy);
 renderWorkflow();
 if(!S.p)return;
 $('parts').replaceChildren(...S.p.order.map(n=>{const b=document.createElement('button');b.disabled=S.busy;b.textContent=(frame().parts[n].reviewed?'✓ ':'○ ')+labels[n];b.style.borderLeft='5px solid '+partColors[n];b.setAttribute('aria-pressed',String(S.part===n));b.onclick=()=>{S.part=n;S.cut=null;refresh()};return b}));
 const exceptionKey=[S.p.id,S.p.revision,S.dirty,S.p.automation?.accepted,S.p.automation?.issues?.length,S.p.automation?.qualityReview].join('|');
 if(S.exceptionKey!==exceptionKey){S.exceptionKey=exceptionKey;const exceptions=$('exceptions');exceptions.replaceChildren();
 if(!S.dirty&&S.p.automation?.accepted&&S.p.automation.acceptedRevision===S.p.revision){const accepted=document.createElement('p');accepted.textContent='此版本已由用户视觉验收通过。以下保留自动诊断，不代表人工验收未通过。';exceptions.append(accepted);}
 if(!S.dirty&&S.p.builtRevision===S.p.revision&&S.p.automation?.qualityReview){const link=document.createElement('a');link.href=S.p.automation.qualityReview;link.textContent='打开完整周期逐帧对照（含独立附件）';link.target='_blank';link.rel='noopener';exceptions.append(link);}
 const groups=new Map();for(const item of S.p.automation?.issues||[]){if(!groups.has(item.code))groups.set(item.code,[]);groups.get(item.code).push(item);}
 for(const [code,items] of groups){const group=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`${items[0].detail.split('，')[0]} · ${items.length} 处`;group.append(summary);for(const item of items){const row=document.createElement('p'),jump=document.createElement('button');jump.textContent=`查看源帧 ${item.frame}`;jump.onclick=()=>{S.pane='parts';$('display').value='ownership';go(S.p.frames.findIndex(f=>f.frame===item.frame));};row.append(jump,document.createTextNode(` ${labels[item.part]||item.part}：${item.detail}`));group.append(row);}exceptions.append(group);}
 if(S.p.automation&&!S.p.automation.issues.length&&!exceptions.childNodes.length)exceptions.textContent='未发现结构异常，仍需对照原视频验收语义和像素。';
 }
 const selected=[...$('projects').options].find(o=>o.value===S.p.id);if(selected)selected.textContent=S.p.name+' · r'+S.p.revision;
 $('seek').max=S.p.frames.length-1;$('seek').value=S.i;
 $('frame').textContent=`源帧 ${frame().frame} · ${S.i+1}/${S.p.frames.length}`;
 $('info').textContent=`${S.p.name} · ${S.p.source.width}×${S.p.source.height} · ${S.p.source.fps} fps · r${S.p.revision}${S.dirty?'（未保存）':''}`;
 const reviewed=S.p.frames.filter(f=>f.poseReviewed&&Object.values(f.parts).every(v=>v.reviewed)).length;
 $('progress').textContent=S.job?.state==='running'?`自动生成中 · 已耗时 ${Math.round(S.job.elapsedSeconds||0)} 秒 · ${S.job.completed||0}/${S.job.total||S.p.frames.length} 帧 · ${S.job.message||''}`:S.dirty?'输入已修改，需重新生成并验收。':S.p.automation?`${S.p.automation.accepted?'已验收工程':'自动候选'} · ${S.p.frames.length} 帧 · ${S.p.automation.issues.length} 条${S.p.automation.accepted?'历史诊断':'待核查诊断'} · ${S.p.automation.accepted?'整段已验收':'尚未验收'}`:`审核完成 ${reviewed}/${S.p.frames.length} 帧。${S.p.artifact?.acceptedCopy&&!S.dirty?'当前生成结果是已验收样板的完整副本。':'当前编辑工程需独立视觉验收。'}`;
 $('part-state').textContent=`${labels[S.part]} · ${frame().parts[S.part].polygon?'用户轮廓':frame().parts[S.part].mask?(S.p.automation?'自动分割遮罩':'追踪遮罩'):S.p.baseline?'已验收原附件':'尚未描边'} · ${frame().parts[S.part].reviewed?'已审核':'待审核'}`;
 $('hint').textContent=S.cut?`描边中：${S.cut.length} 个顶点；点击“完成轮廓”应用。`:S.pane==='pose'?($('advanced').checked?'点击画布设置所选关节点；橙色为肘膝。':'只读核对关节与手脚端点；需要修改时启用手工纠错。'):'每帧可使用自己的附件轮廓；切换帧查看真实像素。';
 draw();
}
function draw(){
 if(!S.p)return;const canvas=$('source'),ctx=canvas.getContext('2d'),f=frame(),im=picture(base()+'/frames/'+String(f.frame).padStart(4,'0')+'.png');
 ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#e7eae6';ctx.fillRect(0,0,canvas.width,canvas.height);
 if(im.complete&&im.naturalWidth){ctx.globalAlpha=$('display').value==='source'?1:($('overlay').checked?.18:0);ctx.drawImage(im,0,0);ctx.globalAlpha=1;}
 if($('display').value!=='source')for(const n of S.p.order){
  if(f.parts[n].visible===false||($('display').value==='isolated'&&n!==S.part))continue;
  const poly=f.parts[n].polygon;
  if(poly&&im.complete&&im.naturalWidth){ctx.save();ctx.beginPath();poly.forEach((v,i)=>i?ctx.lineTo(...v):ctx.moveTo(...v));ctx.closePath();ctx.clip();ctx.drawImage(im,0,0);ctx.restore();}
  else if(f.parts[n].mask&&im.complete&&im.naturalWidth){const mask=picture(base()+'/'+f.parts[n].mask);if(mask.complete&&mask.naturalWidth){const layer=document.createElement('canvas');layer.width=canvas.width;layer.height=canvas.height;const lc=layer.getContext('2d');if($('display').value==='ownership'){lc.fillStyle=partColors[n];lc.fillRect(0,0,canvas.width,canvas.height);}else lc.drawImage(im,0,0);lc.globalCompositeOperation='destination-in';lc.drawImage(mask,0,0);ctx.globalAlpha=$('display').value==='ownership'?.65:1;ctx.drawImage(layer,0,0);ctx.globalAlpha=1;}}
  else {const item=S.seed.find(v=>v.sourceFrame===f.frame&&v.part===n);if(item){const part=picture(base()+'/seed_parts/'+item.file.split('/').pop());if(part.complete&&part.naturalWidth)ctx.drawImage(part,item.crop[0],item.crop[1]);}}
 }
 const poly=S.cut||f.parts[S.part].polygon;
 if(poly?.length){ctx.beginPath();poly.forEach((v,i)=>i?ctx.lineTo(...v):ctx.moveTo(...v));if(!S.cut)ctx.closePath();ctx.fillStyle='#38a5a333';ctx.strokeStyle='#008f95';ctx.lineWidth=2;ctx.fill();ctx.stroke();for(const v of poly){ctx.beginPath();ctx.arc(...v,3,0,Math.PI*2);ctx.fillStyle='#008f95';ctx.fill();}}
 if($('bones').checked){
  const pairs=[['shoulder_near','arm_near','hand_near'],['shoulder_far','arm_far','hand_far'],['hip_near','leg_near','foot_near'],['hip_far','leg_far','foot_far']];
  for(const [a,b,c] of pairs){const pts=[f.points[a],f.joints[b],f.points[c]];if(pts.every(Boolean)){ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle='#118e9c';ctx.lineWidth=2;ctx.stroke();}}
  for(const [key,v] of Object.entries({...f.points,...f.joints})){ctx.beginPath();ctx.arc(...v,3.5,0,2*Math.PI);ctx.fillStyle=key===$('anchor').value?'#ec3152':f.joints[key]?'#f5a025':'#008caa';ctx.fill();}
 }
 if(S.rig)drawRig();
}
function go(i){S.i=Math.max(0,Math.min(S.p.frames.length-1,i));S.cut=null;S.playing=false;refresh();}
$('source').onclick=e=>{if(!S.p||S.busy)return;const r=e.target.getBoundingClientRect(),q=[(e.clientX-r.left)/r.width*S.p.source.width,(e.clientY-r.top)/r.height*S.p.source.height];
 if(S.cut){S.cut.push(q);refresh();return;}if(S.pane==='pose'&&$('advanced').checked){checkpoint();const k=$('anchor').value;(k in labels?frame().joints:frame().points)[k]=q;frame().poseReviewed=false;dirty();}};
$('seek').oninput=()=>go(Number($('seek').value));$('phase').onchange=()=>{S.playing=false;draw()};$('bones').onchange=draw;$('overlay').onchange=draw;$('anchor').onchange=draw;$('display').onchange=draw;$('zoom').onchange=()=>{for(const id of ['source','preview'])$(id).style.width=$('zoom').value+'%';};
host.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>{S.pane=b.dataset.pane;S.cut=null;refresh()});
async function save(){if(!S.p)throw Error('请先建立工程');if(S.dirty){const v=await api('save',{id:S.p.id,revision:S.p.revision,project:S.p});S.p=v.project;S.dirty=false;}refresh();}
async function loadRig(){
 const p=S.p,revision=p.revision,asset=p.artifact;if(!asset||S.dirty||p.builtRevision!==revision)return;const manager=new spine.AssetManager();await Promise.all([manager.loadJsonAsync(asset.base+'/skin.json'),manager.loadTextureAtlasAsync(asset.base+'/skin.atlas')]);if(S.p!==p||S.dirty||S.p.revision!==revision||S.p.artifact!==asset)return;
 const raw=manager.get(asset.base+'/skin.json'),data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(manager.get(asset.base+'/skin.atlas'))).readSkeletonData(raw),sk=new spine.Skeleton(data),anim=data.findAnimation('reference_cycle'),ctx=$('preview').getContext('2d'),renderer=new spine.SkeletonRenderer(ctx);renderer.triangleRendering=true;
 window.PixelTriangleRenderer?.(renderer);
 S.rig={raw,sk,anim,ctx,renderer};$('audit').textContent=`技术核查通过：${asset.audit.checks} 次采样 · 源坐标误差 ${asset.audit.sourceError.toFixed(4)} px · 帧内漂移 ${asset.audit.intraFrameDrift} px。仍需检查轮廓和遮挡。`+(asset.audit.atlas?` 图集：${asset.audit.atlas.pages.length}页，解码RGBA约${(asset.audit.atlas.rgbaBytes/1048576).toFixed(1)} MiB；${asset.audit.atlas.uniqueImages}张独立像素图。当前为逐帧复现模式，非换装资产。`:'');refresh();
}
function drawRig(){const {raw,sk,anim,ctx,renderer}=S.rig,keys=raw.animations.reference_cycle.slots.head.attachment,a=keys[S.i].time||0,b=keys[S.i+1]?.time??anim.duration,t=a+(b-a)*Number($('phase').value)+1e-7;
 sk.setToSetupPose();anim.apply(sk,0,t,false,[],1,spine.MixBlend.replace,spine.MixDirection.mixIn);sk.updateWorldTransform(spine.Physics.update);
 ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,ctx.canvas.width,ctx.canvas.height);ctx.fillStyle='#e7eae6';ctx.fillRect(0,0,ctx.canvas.width,ctx.canvas.height);
 if($('overlay').checked){const im=picture(base()+'/frames/'+String(frame().frame).padStart(4,'0')+'.png');if(im.complete&&im.naturalWidth){ctx.globalAlpha=.25;ctx.drawImage(im,0,0);ctx.globalAlpha=1;}}
 ctx.setTransform(1,0,0,-1,S.p.source.width/2,S.p.source.height);renderer.draw(sk);
 if($('bones').checked)for(const b of sk.bones)if(b.data.length){ctx.beginPath();ctx.moveTo(b.worldX,b.worldY);ctx.lineTo(b.worldX+b.a*b.data.length,b.worldY+b.c*b.data.length);ctx.strokeStyle='#009bad';ctx.lineWidth=1;ctx.stroke();}ctx.setTransform(1,0,0,1,0,0);
}
let autoTimer=null;
async function autoStatus(){
 if(!S.p)return;const pid=S.p.id,v=await api('auto-status',{id:pid});if(S.p.id!==pid)return;
 S.job=v.job;refresh();if(v.job.state==='idle'||v.job.state==='accepted')return;const selecting=!!(S.rangeEdited||S.analysis||$('video').files.length||$('videoSources').value);if(!selecting)status(v.job.message||'尚未开始自动生成');
 if(v.job.state==='running'||(v.job.state==='needs_review'&&selecting)){clearTimeout(autoTimer);autoTimer=setTimeout(()=>autoStatus().catch(e=>status(e.message)),2500);}
 else if(v.job.state==='failed'&&!S.dirty&&!selecting){const p=(await api('load',{id:pid})).project;if(S.p?.id===pid&&p.revision!==S.p.revision)adopt(p);}
 else if(v.job.state==='needs_review'&&!S.dirty&&v.job.resultRevision!==S.p.revision){S.pane='inspect';adopt((await api('load',{id:pid})).project);status(v.job.message);}
}
function workflowState(){
 const pending=!!(S.rangeEdited||S.analysis||$('video').files.length||$('videoSources').value);
 const w=window.PixelWorkflow(pending?null:S.p,{dirty:S.dirty,job:pending?null:S.job,reviewed:$('reviewedDiagnostics').checked});
 if(S.rangeEdited&&!S.analysis&&!$('video').files.length&&!$('videoSources').value){w.action='importAuto';w.label='按自选区间建立工程并生成';w.hint='使用当前工程的原视频与手动起止帧，创建独立工程；不会覆盖当前结果。';}
 else if(S.analysis){w.steps[0]=['视频分析','候选待确认'];w.action='importAuto';w.label='确认区间并自动生成';w.hint='先播放推荐片段，确认动作完整；可修改起止帧。将为此区间创建独立工程。';}
 else if($('video').files.length||$('videoSources').value){w.action='analyze';w.label='分析视频并推荐动作区间';w.hint='使用画面运动和重复性提出片段；推荐不等于质量通过。';}
 return w;
}
async function videoPayload(){
 const f=$('video').files[0];if(!f){if($('videoSources').value)return {projectId:$('videoSources').value};throw Error('请选择 AI 视频');}
 if(f.size>96000000)throw Error('视频限 96 MB');
 const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(f)});
 return {data,name:f.name};
}
function segment(){
 if(!S.analysis)return;const a=S.analysis,start=Number($('start').value),end=Number($('end').value);
 $('segmentHint').textContent=`源帧 ${start}–${end} · ${end-start+1} 帧 · ${a.fps} fps；预览在所选区间循环。确认后再自动生成。`;
 const video=$('referenceVideo');video.currentTime=start/a.fps;
}
function showAnalysis(a){
 S.analysis=a;S.pane='reference';const panel=$('analysis');panel.replaceChildren();
 const note=document.createElement('p');note.textContent=`${a.name} · ${a.width}×${a.height} · ${a.count} 帧。`+a.warnings.join(' ');panel.append(note);
 a.candidates.forEach((c,i)=>{const card=document.createElement('div');card.className='px-candidate';const b=document.createElement('button');b.textContent=`选用片段 ${i+1}：${c.start}–${c.end} 帧 · ${c.confidence}`;b.onclick=()=>{if(S.busy)return;$('start').value=c.start;$('end').value=c.end;segment();};const im=document.createElement('img');im.src=c.previewUrl;im.alt='候选片段五个源帧姿势';card.append(b,im);panel.append(card);});
 const video=$('referenceVideo');video.hidden=false;video.src=a.videoUrl;video.onloadedmetadata=segment;
 S.rangeEdited=false;$('start').value=a.candidates[0].start;$('end').value=a.candidates[0].end;segment();refresh();
}
function clearAnalysis(){S.analysis=null;S.rangeEdited=false;$('analysis').replaceChildren();$('referenceVideo').pause();$('referenceVideo').hidden=true;$('referenceVideo').removeAttribute('src');$('segmentHint').textContent='';}
$('video').onchange=()=>{clearAnalysis();$('videoSources').value='';S.pane='reference';refresh();};
$('videoSources').onchange=()=>{clearAnalysis();$('video').value='';if(!$('videoSources').value&&S.p){$('start').value=S.p.source.start;$('end').value=S.p.source.end;}S.pane='reference';refresh();};
function rangeChanged(){S.rangeEdited=true;segment();refresh();}
$('start').oninput=rangeChanged;$('end').oninput=rangeChanged;$('start').onchange=rangeChanged;$('end').onchange=rangeChanged;
$('referenceVideo').ontimeupdate=()=>{if(!S.analysis)return;const v=$('referenceVideo'),a=S.analysis,start=Number($('start').value)/a.fps,end=(Number($('end').value)+1)/a.fps;if(end>start&&(v.currentTime>=end||v.currentTime<start-.5/a.fps))v.currentTime=start;};
$('referenceVideo').onended=()=>{if(S.analysis){segment();$('referenceVideo').play().catch(()=>{});}};
async function importSelection(){
 if(S.dirty)throw Error('请先保存当前工程');
 const start=Number($('start').value),end=Number($('end').value);
 if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<start||end-start>=120)throw Error('请填写1–120个连续源帧，结束帧需不小于起始帧');
 const payload=S.analysis?{videoId:S.analysis.videoId,name:S.analysis.name}:S.p&&!$('video').files.length&&!$('videoSources').value?{projectId:S.p.id}:await videoPayload();
 const p=(await api('import',{...payload,start,end})).project;
 clearAnalysis();$('video').value='';$('videoSources').value='';adopt(p);await list();return p;
}
function renderWorkflow(){
 if(S.job?.state==='running'){host.querySelectorAll('[data-action=auto],[data-action=build],[data-action=save]').forEach(b=>b.disabled=true);$('advanced').checked=false;$('advanced').disabled=true;S.cut=null;}
 const w=workflowState();$('nextHint').textContent=w.hint;
 $('workflow').replaceChildren(...w.steps.map(([label,state])=>{const li=document.createElement('li');li.textContent=label+' · '+state;return li;}));
 const previewButton=host.querySelector('[data-action="previewSegment"]');previewButton.hidden=!S.analysis;previewButton.disabled=S.busy||!S.analysis;
 const next=host.querySelector('[data-action="nextStep"]');next.textContent=w.label;next.disabled=S.busy||!w.action;
 for(const name of ['autoAccept','export','reviewExport'])host.querySelectorAll(`[data-action="${name}"]`).forEach(b=>b.disabled=S.busy||!w[name]);
}
$('reviewedDiagnostics').onchange=refresh;$('advanced').onchange=()=>{S.cut=null;refresh();};
const actions={
 previewSegment:async()=>{if(!S.analysis)return;segment();await $('referenceVideo').play();status('正在循环预览所选源视频片段。');},
 nextStep:async()=>{const w=workflowState();if(w.action==='reference'){S.pane='reference';return;}if(w.action==='inspect'){S.pane='inspect';await loadRig();return;}if(w.action)await actions[w.action]();},
 auto:async()=>{await save();const v=await api('auto-start',{id:S.p.id,revision:S.p.revision});status(v.job.message);await autoStatus();},
 autoStatus,
 autoAccept:async()=>{if(S.dirty)throw Error('输入已修改，请重新生成');S.p=(await api('auto-accept',{id:S.p.id,revision:S.p.revision,reviewedDiagnostics:$('reviewedDiagnostics').checked})).project;status('已记录当前版本的整段视觉验收，可以导出。');},
 clone:async()=>{if(S.dirty)throw Error('请先保存当前工程');adopt((await api('clone')).project);await list();},
 load:async()=>{if(S.dirty)throw Error('请先保存当前工程');clearAnalysis();$('video').value='';$('videoSources').value='';adopt((await api('load',{id:$('projects').value})).project);},
 import:importSelection,
 importAuto:async()=>{await importSelection();await actions.auto();},
 analyze:async()=>{if(S.dirty)throw Error('请先保存当前工程');status('正在分析运动与重复片段…');showAnalysis((await api('analyze-video',await videoPayload())).analysis);status('已提出片段建议，请播放核对后确认区间。');},
 save:async()=>{await save();await list();},
 seed:async()=>{await save();adopt((await api('seed',{id:S.p.id,revision:S.p.revision})).project);},
 track:async()=>{await save();const i=S.i;const previous=JSON.stringify({frames:S.p.frames,order:S.p.order});const p=(await api('track',{id:S.p.id,revision:S.p.revision,index:i,uniformBackground:$('uniform').checked})).project;adopt(p);S.undo.push(previous);go(i+1);},
 cut:()=>{S.cut=[];S.playing=false;},cancel:()=>{S.cut=null;},
 finish:()=>{if(!S.cut||S.cut.length<3)throw Error('至少描 3 个顶点');checkpoint();frame().parts[S.part]={polygon:S.cut,reviewed:false};S.cut=null;dirty();},
 reviewPart:()=>{if(!frame().parts[S.part].polygon&&!frame().parts[S.part].mask&&!S.p.baseline)throw Error('请先绘制轮廓');checkpoint();frame().parts[S.part].reviewed=true;dirty();},
 reviewPose:()=>{if(Object.keys(frame().points).length!==10||Object.keys(frame().joints).length!==4)throw Error('请设置全部 10 个端点和 4 个肘膝');checkpoint();frame().poseReviewed=true;dirty();},
 copyPose:()=>{if(!S.i)throw Error('没有上一帧');checkpoint();frame().points=structuredClone(S.p.frames[S.i-1].points);frame().joints=structuredClone(S.p.frames[S.i-1].joints);frame().poseReviewed=false;dirty();},
 back:()=>reorder(-1),front:()=>reorder(1),prev:()=>go(S.i-1),next:()=>go(S.i+1),
 play:()=>{S.playing=!S.playing;S.time=S.i/S.p.source.fps;},
 undo:()=>history(S.undo,S.redo),redo:()=>history(S.redo,S.undo),
 build:async()=>{await save();S.p=(await api('build',{id:S.p.id,revision:S.p.revision})).project;S.pane='inspect';await loadRig();},
 reviewExport:async()=>{if(S.dirty||S.p.builtRevision!==S.p.revision)throw Error('请先生成当前动画');const v=await api('review-export',{id:S.p.id,revision:S.p.revision});(S.p.exports??={})[v.kind]=v;const a=document.createElement('a');a.href=v.zipUrl;a.textContent=`下载 r${v.revision} Spine 待验收检查包`;a.download='';$('download').replaceChildren(a);status('检查包已通过 Spine 导入回导；请在 Spine 中核对效果，成功导出不代表质量验收。');},
 export:async()=>{if(S.dirty||S.p.builtRevision!==S.p.revision)throw Error('请先保存并生成当前动画');const v=await api('export',{id:S.p.id,revision:S.p.revision});(S.p.exports??={})[v.kind]=v;const a=document.createElement('a');a.href=v.zipUrl;a.textContent='下载当前版本 Spine 工程 ZIP';a.download='';$('download').replaceChildren(a);status(`已导出 r${v.revision}：Spine 实际导入回导通过，顶点最大偏差 ${v.audit.roundtripMaxDelta.toFixed(4)} px。`);}
};
function reorder(delta){const i=S.p.order.indexOf(S.part),j=i+delta;if(j<0||j>=7)return;checkpoint();[S.p.order[i],S.p.order[j]]=[S.p.order[j],S.p.order[i]];dirty();}
function history(from,to){if(!from.length)return;to.push(JSON.stringify({frames:S.p.frames,order:S.p.order}));Object.assign(S.p,JSON.parse(from.pop()));S.cut=null;dirty();}
host.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{if(S.busy)return;S.busy=true;refresh();status('处理中…');try{await actions[b.dataset.action]();if(!['export','reviewExport','auto','autoStatus','autoAccept','nextStep','analyze','importAuto','previewSegment'].includes(b.dataset.action))status('完成。'+(S.dirty?'修改尚未保存。':'工程已保存在本机。'));}catch(e){status('未完成：'+e.message);console.error(e)}finally{S.busy=false;refresh()}});
window.addEventListener('beforeunload',e=>{if(S.dirty){e.preventDefault();e.returnValue='';}});
let last=performance.now();function tick(now){if(S.playing&&S.p&&!S.busy){S.time=(S.time+(now-last)/1000*Number($('speed').value))%(S.p.frames.length/S.p.source.fps);const i=Math.floor(S.time*S.p.source.fps);if(i!==S.i){S.i=i;refresh();}}last=now;requestAnimationFrame(tick)}requestAnimationFrame(tick);
api('video-sources').then(v=>{$('videoSources').append(...v.sources.map(p=>new Option(p.name,p.id)));}).catch(e=>status(e.message));
refresh();list().then(async()=>{const id=localStorage.getItem('walulu-pixel-last');if(id&&[...$('projects').options].some(o=>o.value===id))adopt((await api('load',{id})).project)}).catch(e=>status('需要启动新版 server_v3.py：'+e.message));
if(location.hash==='#spineRig')window.goToTab?.('spineRig');
})();
