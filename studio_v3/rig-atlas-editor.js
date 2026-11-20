(function (global) {
  'use strict';
  const W = 864, H = 480, SHA = /^[a-f0-9]{64}$/;
  const ID = /^f(\d{3})_(arm|leg)_[AB](?:_chest|_fragment)?_visible$/;
  const SHA_K = new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ]);
  function sha256Fallback(input) {
    const length = input.length, bitLength = length * 8, paddedLength = Math.ceil((length + 9) / 64) * 64;
    const bytes = new Uint8Array(paddedLength); bytes.set(input); bytes[length] = 0x80;
    const view = new DataView(bytes.buffer);
    view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false);
    view.setUint32(paddedLength - 4, bitLength >>> 0, false);
    let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
    const w = new Uint32Array(64);
    for (let offset=0; offset<paddedLength; offset+=64) {
      for (let i=0;i<16;i++) w[i]=view.getUint32(offset+i*4,false);
      for (let i=16;i<64;i++) { const a=w[i-15], b=w[i-2], s0=((a>>>7)|(a<<25))^((a>>>18)|(a<<14))^(a>>>3), s1=((b>>>17)|(b<<15))^((b>>>19)|(b<<13))^(b>>>10); w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0; }
      let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
      for (let i=0;i<64;i++) { const S1=((e>>>6)|(e<<26))^((e>>>11)|(e<<21))^((e>>>25)|(e<<7)), ch=(e&f)^(~e&g), temp1=(h+S1+ch+SHA_K[i]+w[i])>>>0, S0=((a>>>2)|(a<<30))^((a>>>13)|(a<<19))^((a>>>22)|(a<<10)), maj=(a&b)^(a&c)^(b&c), temp2=(S0+maj)>>>0; h=g;g=f;f=e;e=(d+temp1)>>>0;d=c;c=b;b=a;a=(temp1+temp2)>>>0; }
      h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+h)>>>0;
    }
    return [h0,h1,h2,h3,h4,h5,h6,h7].map(value=>value.toString(16).padStart(8,'0')).join('');
  }
  async function sha256Hex(bytes) {
    if (global.crypto?.subtle?.digest) return [...new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');
    return sha256Fallback(new Uint8Array(bytes));
  }
  const CSS = `
.rae{--rae-bg:#171c23;--rae-panel:#202730;--rae-line:#37424f;--rae-text:#e7edf5;box-sizing:border-box;width:100%;color:var(--rae-text);background:var(--rae-bg);border:1px solid var(--rae-line);border-radius:8px;overflow:hidden;font:12px/1.5 system-ui}
.rae *{box-sizing:border-box}.rae [hidden]{display:none!important}.rae button,.rae select,.rae input{font:inherit;color:inherit;background:var(--rae-panel);border:1px solid var(--rae-line);border-radius:5px;padding:6px;min-width:0}.rae button{cursor:pointer}.rae button:disabled,.rae input:disabled{opacity:.42;cursor:not-allowed}.rae button:focus-visible,.rae input:focus-visible,.rae select:focus-visible{outline:2px solid #9ddfc9;outline-offset:2px}
.rae-workspace{display:grid;grid-template-columns:190px minmax(0,1fr) 232px;min-height:650px;height:min(78vh,900px)}.rae-library{min-width:0;border-right:1px solid var(--rae-line);display:flex;flex-direction:column;overflow:hidden}.rae-library-head{padding:12px 10px;display:flex;justify-content:space-between;align-items:center}.rae-library-head strong{font-size:12px}.rae-count{color:#91a1b6;font-size:11px}.rae-search{margin:0 9px 9px;width:calc(100% - 18px)}.rae-tree{overflow:auto;flex:1;padding:0 6px 10px}.rae-row{display:block;margin:2px 0}.rae .rae-row button{display:flex;align-items:center;gap:8px;width:100%;height:46px;text-align:left;background:transparent;border:1px solid transparent;padding:4px 6px;overflow:hidden;color:#c8d3e1}.rae .rae-row button:hover{background:#293542}.rae .rae-row button[aria-pressed=true]{background:#0c1220;color:#fff;border-color:#8fd2bf}.rae-row img{width:32px;height:36px;object-fit:contain;flex:0 0 32px}.rae-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rae-row small{display:block;color:#8d9bad;font-size:9px}.rae-main{min-width:0;display:flex;flex-direction:column;overflow:hidden;background:#222b36}.rae-toolbar{display:flex;align-items:center;gap:5px;padding:8px;flex-wrap:wrap;border-bottom:1px solid var(--rae-line);background:var(--rae-bg)}.rae .rae-toolbar button{font-size:11px;padding:5px 7px}.rae-spacer{flex:1}.rae-zoom{display:flex;align-items:center;gap:5px;font-size:10px}.rae-zoom input{width:70px;padding:0}.rae-stage{flex:1;min-height:260px;min-width:0;overflow:auto;padding:16px;position:relative;overscroll-behavior:contain}.rae .rae-stage canvas{display:block;height:auto;max-width:none;touch-action:none;background-color:#343e4c;background-image:conic-gradient(#424f5f 25%,transparent 0 50%,#424f5f 0 75%,transparent 0);background-size:16px 16px;box-shadow:0 0 0 1px #4b596b}.rae-status{padding:7px 10px;border-top:1px solid var(--rae-line);color:#9fafc2;font-size:10px;min-height:30px}.rae-props{min-width:0;overflow:auto;padding:12px;border-left:1px solid var(--rae-line);background:var(--rae-bg)}.rae-title{font-size:12px;margin:0 0 9px;overflow-wrap:anywhere}.rae-preview{height:190px;display:flex;align-items:center;justify-content:center;border:1px solid var(--rae-line);border-radius:8px;background-color:#2b3542;background-image:conic-gradient(#333f4e 25%,transparent 0 50%,#333f4e 0 75%,transparent 0);background-size:14px 14px;margin-bottom:7px;overflow:hidden}.rae-preview img{max-width:90%;max-height:90%;object-fit:contain;image-rendering:auto}.rae-file{font-size:9px;color:#91a2b9;overflow-wrap:anywhere;margin:5px 0 12px}.rae-fields{display:grid;gap:10px}.rae-fields label{display:flex;flex-direction:column;gap:4px;font-size:10px;color:#a8b7ca}.rae-fields input{width:100%;font-size:12px;color:var(--rae-text)}.rae-style-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.rae-style-fields input[type=color]{height:30px;padding:3px}.rae-wide{width:100%;margin-top:8px}.rae-rotate{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}.rae-info{font-size:10px;color:#9aaabd;line-height:1.7;overflow-wrap:anywhere;border-top:1px solid var(--rae-line);padding-top:9px;margin-top:12px}.rae-recompose{display:flex;gap:8px;flex-wrap:wrap;padding:8px 10px;border-bottom:1px solid var(--rae-line)}.rae-recompose label{display:inline-flex;gap:4px;align-items:center}.rae footer{padding:9px 12px;border-top:1px solid var(--rae-line);color:#acb4c5;font-size:10px}.rae-error{color:#ffb4b9!important}.rae-empty{padding:20px;color:#9aaabd}.rae-notice{padding:8px 10px;border-bottom:1px solid var(--rae-line);font-size:10px;color:#c3d0df;background:#242f3c}
#tab-spineRig .rw .rae .rae-row button{background:transparent;border:1px solid transparent;border-radius:5px;padding:4px 6px;font-size:12px;color:#c8d3e1}#tab-spineRig .rw .rae .rae-row button:hover{background:#293542}#tab-spineRig .rw .rae .rae-row button[aria-pressed=true]{background:#0c1220;border-color:#8fd2bf;color:#fff}#tab-spineRig .rw .rae .rae-toolbar button{font-size:11px;padding:5px 7px}
@media(max-width:1100px){.rae-workspace{grid-template-columns:150px minmax(0,1fr) 204px}.rae-preview{height:160px}.rae-toolbar .rae-spacer{display:none}}@media(max-width:720px){.rae-workspace{grid-template-columns:120px minmax(0,1fr);height:auto;min-height:0}.rae-library{max-height:560px}.rae-main{height:560px}.rae-props{grid-column:1/-1;border-left:0;border-top:1px solid var(--rae-line)}.rae-props [data-ui=props]{display:grid;grid-template-columns:140px minmax(0,1fr);gap:10px}.rae-preview{height:140px}.rae-fields{grid-row:1/5;grid-column:2}.rae-title{grid-column:1/-1}.rae-file{grid-column:1}.rae-info{grid-column:1/-1}.rae-row span{font-size:10px}}
`;
  function transformPoint(point, origin, rotation = 0, scale = 1) {
    const r = rotation * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
    const x = (point.x - origin.x) * scale, y = (point.y - origin.y) * scale;
    return Object.freeze({x:origin.x + x*c - y*s, y:origin.y + x*s + y*c});
  }
  function inversePoint(point, origin, rotation = 0, scale = 1) {
    if (!Number.isFinite(scale) || scale === 0) throw new Error('缩放比例无效');
    const p = transformPoint(point, origin, -rotation);
    return Object.freeze({x:origin.x + (p.x-origin.x)/scale, y:origin.y + (p.y-origin.y)/scale});
  }
  function clientToCanvas(point, rect, width, height) {
    return Object.freeze({x:(point.x-rect.left)*width/rect.width, y:(point.y-rect.top)*height/rect.height});
  }
  const geometry = Object.freeze({transformPoint, inversePoint, clientToCanvas});
  const power2 = n => {let v=1;while(v<n)v*=2;return v;};
  // 预览和导出只消费这一份排布；坐标是图集左上角，不写回源帧或骨骼坐标。
  function packParts(parts) {
    const sorted=parts.slice().sort((a,b)=>a.order-b.order || a.meta.id.localeCompare(b.meta.id));
    const sizes=sorted.map(p=>({p,w:p.atlasTurns%2?p.h:p.w,h:p.atlasTurns%2?p.w:p.h}));
    const area=sizes.reduce((n,t)=>n+(t.w+16)*(t.h+30),0);
    const width=power2(Math.max(256,...sizes.map(t=>t.w+16),Math.ceil(Math.sqrt(area))));
    let x=8,y=8,row=0;const tiles=[];
    for(const t of sizes){if(x+t.w+8>width){x=8;y+=row;row=0;}tiles.push({...t,x,y});x+=t.w+16;row=Math.max(row,t.h+30);}
    return {width,height:power2(Math.max(64,y+row+8)),tiles};
  }
  function surface(w = W, h = H) {const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
  function validate(m, taskId, sha256) {
    if (!taskId || !SHA.test(sha256) || !m || m.taskId !== taskId || m.sourceVideoSha256 !== sha256 ||
        m.characterId !== null || m.promotedToRuntime !== false || m.status !== 'video_visible_pose_fragments_not_reusable_rig_parts') throw new Error('task/SHA/status 或 character/runtime 保护校验失败');
    if (m.sourceCoordinateSystem !== '864x480 source pixels, top-left origin, zero-based frame index' ||
        !Array.isArray(m.frameIndices) || m.frameIndices.length !== 22 || new Set(m.frameIndices).size !== 22 ||
        !m.frameIndices.includes(72) || m.frameIndices.some(i=>!Number.isInteger(i)||i<0||i>999) ||
        !Array.isArray(m.parts) || m.parts.length !== 74 || m.partCount !== 74) throw new Error('帧索引、源尺寸或部件数量不符');
    const ids = new Set(), sources = new Map();
    for (const p of m.parts) {
      const match = typeof p?.id === 'string' && p.id.match(ID), b = p?.bbox;
      if (!match || ids.has(p.id) || Number(match[1]) !== p.sourceFrame || match[2] !== p.kind ||
          p.file !== p.id+'.png' || p.maskFile !== p.id+'_mask.png' || p.sourceFile !== 'source_'+match[1]+'.png' ||
          !m.frameIndices.includes(p.sourceFrame) || !SHA.test(p.sourceFrameSha256) ||
          !Array.isArray(p.sourceSize) || p.sourceSize.length !== 2 || p.sourceSize[0] !== W || p.sourceSize[1] !== H ||
          !Array.isArray(b) || b.length !== 4 || b.some(v=>!Number.isInteger(v)) || b[0]<0 || b[1]<0 || b[2]>W || b[3]>H || b[0]>=b[2] || b[1]>=b[3] ||
          p.anatomicalIdentity !== 'unknown' || p.crossFrameIdentityEstablished !== false || p.notReusableRigPart !== true ||
          p.status !== 'pose_evidence_coarse_boundary_review_required' || !['coarse_boundary_review_required','ai_foot_shape_review_required'].includes(p.shapeReview)) throw new Error('部件身份、状态、文件名或 bbox 校验失败');
      if (sources.has(p.sourceFrame) && sources.get(p.sourceFrame) !== p.sourceFrameSha256) throw new Error('同帧来源 SHA 冲突');
      sources.set(p.sourceFrame,p.sourceFrameSha256); ids.add(p.id);
    }
    if (m.frameIndices.some(i=>!sources.has(i))) throw new Error('索引存在未提取帧');return m;
  }
  function crc32(bytes){let c=0xffffffff;for(const b of bytes){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;}
  function zipStore(files){
    const encoder=new TextEncoder(),chunks=[],central=[];let offset=0;
    for(const file of files){const name=encoder.encode(file.name),data=file.data,crc=crc32(data),h=new Uint8Array(30+name.length),v=new DataView(h.buffer);
      v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(12,33,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);h.set(name,30);
      const ch=new Uint8Array(46+name.length),cv=new DataView(ch.buffer);cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint16(14,33,true);cv.setUint32(16,crc,true);cv.setUint32(20,data.length,true);cv.setUint32(24,data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);ch.set(name,46);central.push(ch);chunks.push(h,data);offset+=h.length+data.length;
    }
    const size=central.reduce((n,c)=>n+c.length,0),end=new Uint8Array(22),ev=new DataView(end.buffer);ev.setUint32(0,0x06054b50,true);ev.setUint16(8,files.length,true);ev.setUint16(10,files.length,true);ev.setUint32(12,size,true);ev.setUint32(16,offset,true);
    return new Blob([...chunks,...central,end],{type:'application/zip'});
  }
  function mount({host, base, taskId, sha256, onRequestFrame} = {}) {
    if (!host || typeof host.replaceChildren !== 'function') throw new Error('需要有效 host');
    const root=document.createElement('section');root.className='rae';
    root.innerHTML=`<div class="rae-notice">视频粗片图集 · 全部 74 张 / 22 源帧；不是 74 个独立解剖部位。隐藏补画与绑定未完成。图集 PNG 导出不包含标框、文字或背景。</div>
<div class="rae-workspace"><aside class="rae-library"><div class="rae-library-head"><strong>图集部件</strong><span class="rae-count" data-ui="count">加载中</span></div><input class="rae-search" data-ui="search" type="search" placeholder="搜索名称 / 帧号" aria-label="搜索图集部件"><div class="rae-tree" role="listbox" aria-label="图集部件列表"></div></aside>
<div class="rae-main"><div class="rae-toolbar"><button data-ui="magic" disabled title="完整补画能力尚未接入，不以可见片冒充补画">万能编辑</button><button disabled title="需先具备完整角色部件与换装皮肤">整套换皮</button><button data-ui="layout" disabled>重置布局</button><button data-ui="outlines" aria-pressed="false">隐藏标框</button><button data-ui="partsExport" disabled>导出拆件</button><button data-ui="atlasExport" disabled title="仅粗片审阅素材，不是正式角色图集">导出粗片审阅 PNG + atlas</button><button disabled title="骨骼、权重、动作尚未制作，不能生成正式 Spine 运行包">导出 Spine ZIP</button><span class="rae-spacer"></span><label class="rae-zoom">缩放<input data-ui="zoom" type="range" min="25" max="250" step="5" value="100" aria-label="图集缩放"><span data-ui="zoomText">100%</span></label><button data-ui="fit">适应视图</button><select data-ui="mode" aria-label="图集或重组模式"><option value="atlas">完整图集</option><option value="recompose">逐帧重组 / 缺口</option></select></div>
<div class="rae-recompose" data-ui="recomposeControls" hidden><label>源帧<select data-ui="frame" disabled></select></label><label><input type="checkbox" data-ui="base" checked>底图</label><label><input type="checkbox" data-ui="gap" checked>缺口检查</label><label><input type="checkbox" data-ui="ghost">源图叠加</label><label><input type="checkbox" data-ui="only">仅看选中</label><button data-ui="show">全部显示</button><button data-ui="reset">重置选中</button><button data-ui="resetAll">重置当前帧</button></div>
<div class="rae-stage"><canvas data-ui="stage" width="1024" height="1024" aria-label="完整部件图集，与PNG导出共用排布"></canvas></div><div class="rae-status" role="status" aria-live="polite">正在校验全部部件和源帧…</div></div>
<aside class="rae-props"><div data-ui="props"><div class="rae-empty">加载完成后，点击左侧或图集中的部件查看图像与属性。</div></div></aside></div>
<footer>当前为视频可见粗片，A/B 身份未知；74–77 帧脚形待审。导出的是粗片素材，不是完整绑定图集或 .spine 工程。右侧名称/排序/旋转仅编辑当前会话图集；不会改写源 PNG。逐帧紫色区域仅提示缺口，不是补画。</footer>`;
    const style=document.createElement('style');style.textContent=CSS;root.prepend(style);host.replaceChildren(root);
    const ui=key=>root.querySelector('[data-ui="'+key+'"]'),canvas=ui('stage'),ctx=canvas.getContext('2d'),status=root.querySelector('.rae-status'),tree=root.querySelector('.rae-tree');
    const state={manifest:null,frame:null,requested:72,loaded:null,parts:[],selected:null,token:0,drag:null,failed:false,loading:false,tiles:[],partsForFrame:[],atlas:null,atlasReady:false,zoom:1,autoFit:true,exporting:false,showOutlines:true};
    let directory;
    const atlasMode=()=>ui('mode').value==='atlas';
    function stopDrag(){const d=state.drag;state.drag=null;if(d&&canvas.hasPointerCapture(d.pointer))canvas.releasePointerCapture(d.pointer);}
    function fail(error){stopDrag();state.token++;state.failed=true;state.loaded=null;ctx.clearRect(0,0,canvas.width,canvas.height);root.querySelectorAll('button,input,select').forEach(el=>{el.disabled=true;});tree.replaceChildren();ui('props').replaceChildren();status.className='rae-status rae-error';status.textContent='已停止校验：'+error.message;}
    function url(file){if(!/^(?:manifest\.json|source_\d{3}\.png|f\d{3}_(?:arm|leg)_[AB](?:_chest|_fragment)?_visible(?:_mask)?\.png)$/.test(file))throw new Error('不安全文件名');const r=new URL(file,directory);if(r.origin!==directory.origin||!r.pathname.startsWith(directory.pathname)||r.search||r.hash)throw new Error('资源路径越界');return r;}
    async function read(file){const r=await fetch(url(file),{cache:'no-store',redirect:'error',credentials:'same-origin'});if(!r.ok)throw new Error(file+' HTTP '+r.status);return r;}
    async function png(file,w,h,digest){
      const bytes=await(await read(file)).arrayBuffer(),sig=new Uint8Array(bytes,0,Math.min(bytes.byteLength,8));if([137,80,78,71,13,10,26,10].some((v,i)=>sig[i]!==v))throw new Error(file+' 非PNG');
      if(digest){const actual=await sha256Hex(bytes);if(actual!==digest)throw new Error(file+' SHA不符');}
      const image=new Image(),objectUrl=URL.createObjectURL(new Blob([bytes],{type:'image/png'}));try{image.src=objectUrl;await image.decode();if(image.naturalWidth!==w||image.naturalHeight!==h)throw new Error(file+' 尺寸不符');const c=surface(w,h);c.getContext('2d').drawImage(image,0,0);return c;}finally{URL.revokeObjectURL(objectUrl);}
    }
    function shortName(meta){const side=meta.id.match(/_[AB](?:_|$)/)?.[0].slice(1,2)||'';return (meta.kind==='arm'?(meta.id.includes('_chest_')?'胸前臂 ':'手臂 '):'腿片 ')+side+' · '+String(meta.sourceFrame).padStart(3,'0');}
    function currentParts(){return state.partsForFrame;}
    function editingParts(){return atlasMode()?state.parts:currentParts();}
    function selected(){return editingParts().find(p=>p.meta.id===state.selected);}
    function visible(p){return p.visible&&(!ui('only').checked||state.selected===p.meta.id);}
    function select(id){if(!editingParts().some(p=>p.meta.id===id))return;state.selected=id;render();updateTree();properties();}
    function updateTree(){
      tree.replaceChildren();if(!state.atlasReady)return;
      const query=ui('search').value.trim().toLowerCase(),parts=editingParts().slice().sort((a,b)=>a.order-b.order||a.meta.id.localeCompare(b.meta.id));
      const shown=parts.filter(p=>(p.name+' '+p.meta.id+' '+p.meta.sourceFrame).toLowerCase().includes(query));ui('count').textContent=query?shown.length+' / '+parts.length:String(parts.length);
      for(const p of shown){const row=document.createElement('div');row.className='rae-row';const button=document.createElement('button');button.type='button';button.title=p.meta.id;button.setAttribute('aria-pressed',String(state.selected===p.meta.id));
        const image=new Image();image.src=p.preview;image.alt=p.name+' 部件缩略图';const text=document.createElement('span');text.textContent=p.name;const small=document.createElement('small');small.textContent=p.w+' × '+p.h+' · 源帧 '+p.meta.sourceFrame;text.append(small);button.append(image,text);button.onclick=()=>select(p.meta.id);row.append(button);tree.append(row);
      }
      if(!shown.length){const empty=document.createElement('p');empty.className='rae-empty';empty.textContent='没有匹配部件';tree.append(empty);}
    }
    function inputField(parent,labelText,type,value,handler,attrs={}){const label=document.createElement('label');label.textContent=labelText;const input=document.createElement('input');input.type=type;input.value=String(value);for(const [k,v]of Object.entries(attrs))input.setAttribute(k,String(v));input.onchange=()=>handler(input);label.append(input);parent.append(label);return input;}
    function properties(){
      const host=ui('props'),p=selected();host.replaceChildren();if(!p){host.textContent='点击部件查看对应图像';return;}
      const title=document.createElement('h3');title.className='rae-title';title.textContent=p.name;const preview=document.createElement('div');preview.className='rae-preview';const image=new Image();image.src=p.preview;image.alt=p.meta.id+' 选中部件预览';image.style.transform='rotate('+p.atlasTurns*90+'deg)';preview.append(image);
      const file=document.createElement('p');file.className='rae-file';file.textContent=p.w+' × '+p.h+' px · '+p.meta.file;host.append(title,preview,file);
      const fields=document.createElement('div');fields.className='rae-fields';host.append(fields);
      inputField(fields,'标注名称','text',p.name,input=>{p.name=input.value.trim().slice(0,80)||shortName(p.meta);updateTree();render();title.textContent=p.name;input.value=p.name;},{maxlength:80,'aria-label':'部件标注名称'});
      inputField(fields,'排序编号','number',p.order,input=>{const n=Number(input.value);if(Number.isInteger(n)&&n>=1&&n<=state.parts.length){const ordered=state.parts.slice().sort((a,b)=>a.order-b.order);ordered.splice(ordered.indexOf(p),1);ordered.splice(n-1,0,p);ordered.forEach((item,i)=>item.order=i+1);rebuildAtlas();updateTree();properties();render();}else input.value=p.order;},{min:1,max:74,step:1,'aria-label':'部件排序编号'});
      const styles=document.createElement('div');styles.className='rae-style-fields';fields.append(styles);
      inputField(styles,'线框颜色','color',p.color,input=>{p.color=input.value;render();},{'aria-label':'线框颜色'});
      inputField(styles,'线框粗细','number',p.lineWidth,input=>{const n=Number(input.value);if(Number.isFinite(n)&&n>=1&&n<=8)p.lineWidth=n;else input.value=p.lineWidth;render();},{min:1,max:8,step:1,'aria-label':'线框粗细'});
      inputField(styles,'标注字号','number',p.fontSize,input=>{const n=Number(input.value);if(Number.isInteger(n)&&n>=8&&n<=18)p.fontSize=n;else input.value=p.fontSize;render();},{min:8,max:18,step:1,'aria-label':'标注字号'});
      const apply=document.createElement('button');apply.textContent='将线框和字号应用到全部部件';apply.className='rae-wide';apply.onclick=()=>{for(const item of state.parts){item.color=p.color;item.lineWidth=p.lineWidth;item.fontSize=p.fontSize;}render();};fields.append(apply);
      const rotate=document.createElement('div');rotate.className='rae-rotate';for(const direction of [-1,1]){const b=document.createElement('button');b.textContent=(direction<0?'↶':'↷')+' 90°';b.title=direction<0?'逆时针旋转图集部件90度':'顺时针旋转图集部件90度';b.disabled=!atlasMode();b.onclick=()=>{p.atlasTurns=(p.atlasTurns+direction+4)%4;rebuildAtlas();render();properties();};rotate.append(b);}fields.append(rotate);
      const jump=document.createElement('button');jump.textContent='查看源帧 '+p.meta.sourceFrame;jump.className='rae-wide';jump.onclick=()=>{if(typeof onRequestFrame==='function')onRequestFrame(p.meta.sourceFrame);};fields.append(jump);
      if(!atlasMode()){
        for(const [key,label]of [['x','源帧 x'],['y','源帧 y'],['rotation','重组旋转°']])inputField(fields,label,'number',Number(p[key].toFixed(2)),input=>{const n=Number(input.value);if(input.value.trim()&&Number.isFinite(n)&&Math.abs(n)<=100000){p[key]=n;render();}else input.value=p[key];},{step:0.1,'aria-label':label});
        const show=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=p.visible;check.onchange=()=>{p.visible=check.checked;render();};show.append(check,'在重组中显示');fields.append(show);
      }
      const tile=state.atlas?.tiles.find(t=>t.p===p),info=document.createElement('div');info.className='rae-info';info.textContent=(tile?'图集区域：'+[tile.x,tile.y,tile.w,tile.h].join(', ')+' · 旋转 '+p.atlasTurns*90+'°\n':'')+'导出 region：'+p.meta.id+'\n源 bbox：'+p.meta.bbox.join(', ')+'\n身份：unknown · '+(p.meta.shapeReview==='ai_foot_shape_review_required'?'脚形待审':'粗边界待审')+'\n标框与文字不写入PNG。图集旋转不修改源帧/骨骼坐标。';info.style.whiteSpace='pre-line';host.append(info);
    }
    function drawTile(target,t){target.save();target.translate(t.x+t.w/2,t.y+t.h/2);target.rotate(t.p.atlasTurns*Math.PI/2);target.drawImage(t.p.part,-t.p.w/2,-t.p.h/2);target.restore();}
    function rebuildAtlas(){if(!state.atlasReady)return;const layout=packParts(state.parts),image=surface(layout.width,layout.height);for(const t of layout.tiles)drawTile(image.getContext('2d'),t);state.atlas={...layout,image};}
    function setCanvasSize(w,h){if(canvas.width!==w)canvas.width=w;if(canvas.height!==h)canvas.height=h;ctx.clearRect(0,0,w,h);}
    function applyZoom(){const stage=root.querySelector('.rae-stage'),available=Math.max(150,stage.clientWidth-32),availableHeight=Math.max(150,stage.clientHeight-32);const scale=state.autoFit?Math.min(1,available/canvas.width,availableHeight/canvas.height):state.zoom;canvas.style.width=Math.round(canvas.width*scale)+'px';ui('zoomText').textContent=Math.round(scale*100)+'%';ui('zoom').value=String(Math.round(scale*100));}
    function drawPart(target,p){target.save();target.translate(p.x+p.w/2,p.y+p.h/2);target.rotate(p.rotation*Math.PI/180);target.drawImage(p.part,-p.w/2,-p.h/2);target.restore();}
    function hit(p,q){const local=inversePoint(q,{x:p.x+p.w/2,y:p.y+p.h/2},p.rotation),px=Math.floor(local.x-p.x),py=Math.floor(local.y-p.y);return px>=0&&py>=0&&px<p.w&&py<p.h&&p.alpha[(py*p.w+px)*4+3]>0;}
    function render(){
      if(state.failed||!state.atlasReady)return;
      try{
        if(atlasMode()){
          const a=state.atlas;setCanvasSize(a.width,a.height);ctx.drawImage(a.image,0,0);state.tiles=a.tiles;
          if(state.showOutlines)for(const t of a.tiles){const chosen=state.selected===t.p.meta.id;ctx.strokeStyle=chosen?'#a5ffe1':t.p.color;ctx.lineWidth=chosen?Math.max(2,t.p.lineWidth):t.p.lineWidth;ctx.strokeRect(t.x-.5,t.y-.5,t.w+1,t.h+1);ctx.fillStyle=chosen?'#c0ffe9':'#cbd6e5';ctx.font=t.p.fontSize+'px system-ui';ctx.save();ctx.beginPath();ctx.rect(t.x-3,t.y+t.h+2,t.w+10,23);ctx.clip();ctx.fillText(t.p.order+'. '+t.p.name,t.x,t.y+t.h+16);ctx.restore();}
          status.textContent='全部 '+state.parts.length+' 张 · '+a.width+' × '+a.height+' px · 预览/PNG/atlas 使用同一排布 · 点击任一边框区域选中 · 源帧 '+state.requested+' · 粗片待补画';
        }else{
          setCanvasSize(W,H);state.tiles=[];const f=state.loaded;
          if(!f){status.textContent=state.loading?'源帧 '+state.frame+' 加载中…':'源帧 '+state.frame+' 未提取；不显示其他帧部件。';applyZoom();return;}
          const coverage=f.coverage.getContext('2d');coverage.clearRect(0,0,W,H);for(const p of currentParts())if(visible(p))drawPart(coverage,p);
          const pixels=coverage.getImageData(0,0,W,H).data,overlay=f.gap.getContext('2d'),gap=overlay.createImageData(W,H);let count=0;
          for(let i=3;i<pixels.length;i+=4)if(f.domainAlpha[i]>0&&pixels[i]===0){count++;gap.data[i-3]=190;gap.data[i-2]=65;gap.data[i-1]=245;gap.data[i]=200;}overlay.putImageData(gap,0,0);
          if(ui('base').checked)ctx.drawImage(f.base,0,0);for(const p of currentParts())if(visible(p))drawPart(ctx,p);if(ui('gap').checked)ctx.drawImage(f.gap,0,0);if(ui('ghost').checked){ctx.globalAlpha=.3;ctx.drawImage(f.source,0,0);ctx.globalAlpha=1;}
          status.textContent='源帧 '+state.frame+' · '+currentParts().length+' 张 · 缺口 '+count+' 像素 · 补画像素 0 · 紫色不是补画'+(ui('ghost').checked?' · 完整源图叠加可能掩盖缺口':'');
        }applyZoom();
      }catch(e){fail(e);}
    }
    async function decodeFrame(index){
      const entries=state.parts.filter(p=>p.meta.sourceFrame===index),first=entries[0].meta;
      const source=await png(first.sourceFile,W,H,first.sourceFrameSha256),sourcePixels=source.getContext('2d').getImageData(0,0,W,H).data,domain=surface(),dctx=domain.getContext('2d');let originalCount=0;
      const loaded=await Promise.all(entries.map(async p=>{
        const [part,rawMask]=await Promise.all([p.part?Promise.resolve(p.part):png(p.meta.file,p.w,p.h),png(p.meta.maskFile,W,H)]),alpha=part.getContext('2d').getImageData(0,0,p.w,p.h).data,mx=rawMask.getContext('2d'),data=mx.getImageData(0,0,W,H);let opaque=0;const b=p.meta.bbox;
        for(let y=0;y<H;y++)for(let x=0;x<W;x++){const i=(y*W+x)*4,value=data.data[i],inside=x>=b[0]&&x<b[2]&&y>=b[1]&&y<b[3],j=((y-b[1])*p.w+x-b[0])*4;if(value!==data.data[i+1]||value!==data.data[i+2]||data.data[i+3]!==255||(value!==0&&value!==255)||(!inside&&value))throw new Error(p.meta.id+' mask数据不符');if(inside&&alpha[j+3]!==value)throw new Error(p.meta.id+' alpha与mask不符');if(value){opaque++;for(let k=0;k<3;k++)if(alpha[j+k]!==sourcePixels[i+k])throw new Error(p.meta.id+' RGB与源帧不符');}data.data[i]=255;data.data[i+1]=255;data.data[i+2]=255;data.data[i+3]=value;}
        if(!opaque)throw new Error(p.meta.id+' 空部件');originalCount+=opaque;mx.putImageData(data,0,0);return{p,part,mask:rawMask,alpha};
      }));
      for(const item of loaded)dctx.drawImage(item.mask,0,0);const remaining=surface(),bx=remaining.getContext('2d');bx.drawImage(source,0,0);bx.globalCompositeOperation='destination-out';bx.drawImage(domain,0,0);bx.globalCompositeOperation='source-over';return{source,base:remaining,domainAlpha:dctx.getImageData(0,0,W,H).data,coverage:surface(),gap:surface(),originalCount,loaded};
    }
    async function loadFrame(index,notify=false){
      if(state.failed||!Number.isInteger(index)||index<0)return;state.requested=index;if(!state.atlasReady||atlasMode()){if(state.atlasReady)render();return;}
      if(state.frame===index&&(state.loading||state.loaded)){if(!currentParts().some(p=>p.meta.id===state.selected))state.selected=currentParts()[0]?.meta.id||null;updateTree();render();properties();return;}stopDrag();const token=++state.token;state.frame=index;state.loaded=null;state.partsForFrame=[];state.selected=null;state.loading=true;ui('frame').value=String(index);updateTree();properties();render();
      if(!state.manifest.frameIndices.includes(index)){state.loading=false;render();return;}
      try{if(notify&&typeof onRequestFrame==='function')onRequestFrame(index);const result=await decodeFrame(index);if(token!==state.token||state.failed)return;state.loaded=result;state.partsForFrame=result.loaded.map(t=>t.p);state.selected=state.partsForFrame[0]?.meta.id||null;state.loading=false;updateTree();render();properties();}catch(e){if(token===state.token)fail(e);}
    }
    function canvasBytes(c){return new Promise((resolve,reject)=>c.toBlob(async blob=>{try{if(!blob)throw new Error('PNG编码失败');resolve(new Uint8Array(await blob.arrayBuffer()));}catch(e){reject(e);}},'image/png'));}
    function download(blob,name){const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(href),30000);}
    async function exportAssets(kind){
      if(!state.atlasReady||state.failed||state.exporting)return;state.exporting=true;ui('atlasExport').disabled=ui('partsExport').disabled=true;
      try{
        // 同步截取同一layout快照；异步PNG编码期间的UI编辑不能污染本次导出的坐标。
        const a=state.atlas,encoder=new TextEncoder(),metadata={schemaVersion:1,taskId,sourceVideoSha256:sha256,characterId:null,promotedToRuntime:false,status:'video_visible_fragments_atlas_not_rig',hiddenInpaintComplete:false,notSpineProject:true,page:{file:'video_fragments.png',width:a.width,height:a.height},parts:a.tiles.map(t=>({id:t.p.meta.id,label:t.p.name,order:t.p.order,sourceFrame:t.p.meta.sourceFrame,sourceFile:t.p.meta.file,bbox:t.p.meta.bbox,sourceFrameSha256:t.p.meta.sourceFrameSha256,anatomicalIdentity:'unknown',notReusableRigPart:true,shapeReview:t.p.meta.shapeReview,pixelRotation:t.p.atlasTurns*90,atlasBounds:[t.x,t.y,t.w,t.h]}))};
        let files=[];
        if(kind==='atlas'){
          const text=['video_fragments.png','size: '+a.width+','+a.height,'format: RGBA8888','filter: Linear,Linear','repeat: none',...metadata.parts.flatMap(p=>[p.id,'  rotate: false','  xy: '+p.atlasBounds[0]+', '+p.atlasBounds[1],'  size: '+p.atlasBounds[2]+', '+p.atlasBounds[3],'  orig: '+p.atlasBounds[2]+', '+p.atlasBounds[3],'  offset: 0, 0','  index: -1'])].join('\n')+'\n';
          files=[{name:'video_fragments.png',data:await canvasBytes(a.image)},{name:'video_fragments.atlas',data:encoder.encode(text)}];
        }else{
          const snapshots=state.parts.map(p=>({name:p.meta.file,image:p.part}));for(const p of snapshots)files.push({name:'parts/'+p.name,data:await canvasBytes(p.image)});
        }
        files.push({name:'provenance.json',data:encoder.encode(JSON.stringify(metadata,null,2))});download(zipStore(files),kind==='atlas'?'video_fragments_png_atlas_REVIEW_ONLY.zip':'video_visible_parts_REVIEW_ONLY.zip');status.textContent='已发起下载：'+files.length+' 个文件；粗片素材，不包含骨骼、动作或可编辑Spine工程。';
      }catch(e){status.textContent='导出失败：'+e.message;}finally{state.exporting=false;if(!state.failed)ui('atlasExport').disabled=ui('partsExport').disabled=false;}
    }
    ui('outlines').onclick=()=>{state.showOutlines=!state.showOutlines;ui('outlines').textContent=state.showOutlines?'隐藏标框':'显示标框';ui('outlines').setAttribute('aria-pressed',String(!state.showOutlines));render();};
    ui('search').oninput=updateTree;
    ui('mode').onchange=()=>{stopDrag();state.autoFit=true;ui('recomposeControls').hidden=atlasMode();if(atlasMode()){state.selected=state.parts[0]?.meta.id;updateTree();render();properties();}else loadFrame(state.requested);};
    ui('frame').onchange=()=>loadFrame(Number(ui('frame').value),true);
    for(const key of ['base','gap','ghost','only'])ui(key).onchange=()=>{stopDrag();render();};
    ui('zoom').oninput=()=>{state.autoFit=false;state.zoom=Number(ui('zoom').value)/100;applyZoom();};ui('fit').onclick=()=>{state.autoFit=true;applyZoom();};
    ui('layout').onclick=()=>{for(const p of state.parts){p.order=p.originalOrder;p.atlasTurns=0;}rebuildAtlas();render();updateTree();properties();};
    ui('show').onclick=()=>{ui('only').checked=false;for(const p of currentParts())p.visible=true;render();properties();};
    function reset(p){p.x=p.meta.bbox[0];p.y=p.meta.bbox[1];p.rotation=0;p.visible=true;}
    ui('reset').onclick=()=>{const p=selected();if(p)reset(p);render();properties();};ui('resetAll').onclick=()=>{for(const p of currentParts())reset(p);ui('only').checked=false;render();properties();};
    ui('atlasExport').onclick=()=>exportAssets('atlas');ui('partsExport').onclick=()=>exportAssets('parts');
    canvas.onpointerdown=e=>{if(state.failed||!state.atlasReady||state.drag||e.button!==0)return;const q=clientToCanvas({x:e.clientX,y:e.clientY},canvas.getBoundingClientRect(),canvas.width,canvas.height);const p=atlasMode()?state.tiles.find(t=>q.x>=t.x&&q.x<=t.x+t.w&&q.y>=t.y&&q.y<=t.y+t.h)?.p:currentParts().slice().reverse().find(p=>visible(p)&&hit(p,q));if(!p)return;e.preventDefault();select(p.meta.id);if(!atlasMode()){state.drag={pointer:e.pointerId,p,start:q,x:p.x,y:p.y};canvas.setPointerCapture(e.pointerId);}};
    canvas.onpointermove=e=>{const d=state.drag;if(!d||e.pointerId!==d.pointer)return;const q=clientToCanvas({x:e.clientX,y:e.clientY},canvas.getBoundingClientRect(),canvas.width,canvas.height);d.p.x=d.x+q.x-d.start.x;d.p.y=d.y+q.y-d.start.y;render();properties();};
    canvas.onpointerup=canvas.onpointercancel=e=>{if(state.drag?.pointer===e.pointerId)stopDrag();};canvas.onlostpointercapture=()=>{state.drag=null;};
    const observer=new ResizeObserver(()=>{if(state.atlasReady)applyZoom();});observer.observe(root.querySelector('.rae-stage'));
    (async()=>{try{
      if(typeof base!=='string'||!base.endsWith('/'))throw new Error('base必须为目录');const parent=new URL(base,document.baseURI);if(!['http:','https:'].includes(parent.protocol)||parent.origin!==new URL(document.baseURI).origin||parent.search||parent.hash||parent.username||parent.password)throw new Error('base来源不安全');directory=new URL('video_parts_v1/',parent);
      state.manifest=validate(await(await read('manifest.json')).json(),taskId,sha256);state.parts=state.manifest.parts.map((meta,i)=>({meta,name:shortName(meta),order:i+1,originalOrder:i+1,w:meta.bbox[2]-meta.bbox[0],h:meta.bbox[3]-meta.bbox[1],x:meta.bbox[0],y:meta.bbox[1],rotation:0,visible:true,atlasTurns:0,color:'#ce8791',lineWidth:1,fontSize:10}));
      // 顺序按帧校验限制并发/峰值内存；只保留小尺寸部件，不缓存全部源帧画布。
      for(const index of state.manifest.frameIndices){const result=await decodeFrame(index);for(const item of result.loaded){item.p.part=item.part;item.p.alpha=item.alpha;item.p.preview=item.part.toDataURL('image/png');}status.textContent='已校验 '+state.parts.filter(p=>p.part).length+' / '+state.parts.length+' 张部件…';}
      for(const i of state.manifest.frameIndices){const o=document.createElement('option');o.value=String(i);o.textContent='帧 '+i;ui('frame').append(o);}ui('frame').disabled=false;state.atlasReady=true;state.selected=state.parts[0]?.meta.id;rebuildAtlas();updateTree();render();properties();ui('layout').disabled=ui('partsExport').disabled=ui('atlasExport').disabled=false;if(!atlasMode())await loadFrame(state.requested);
    }catch(e){fail(e);}})();
    return Object.freeze({updateSourceFrame:index=>loadFrame(index)});
  }
  const STABLE_IDS = Object.freeze(['head','body','shorts','arm_near','arm_far','leg_near','leg_far']);
  function validateStable(m, taskId, sha256) {
    const hash = value => typeof value === 'string' && SHA.test(value);
    const size = value => Number.isInteger(value) && value > 0 && value <= 8192;
    const bbox = (value,width,height) => Array.isArray(value) && value.length === 4 && value.every(Number.isInteger) && value[0] >= 0 && value[1] >= 0 && value[2] <= width && value[3] <= height && value[0] < value[2] && value[1] < value[3];
    if (typeof taskId !== 'string' || !taskId || !hash(sha256) || !m || m.schemaVersion !== 2 ||
        m.taskId !== taskId || m.sourceVideoSha256 !== sha256 || m.characterId !== null || m.promotedToRuntime !== false ||
        m.status !== 'stable_parts_work_in_progress_not_rig' || m.direction !== 'right_front_3q') throw new Error('稳定部件 v2 task/SHA/status 或角色/runtime 校验失败');
    const source=m.sourceImage, ref=m.sourceReference, review=m.review, bodyReview=m.bodyReview;
    if (!source || source.file !== '../../right_front_walk/source768.png' || !hash(source.sha256) || !size(source.width) || !size(source.height) || source.width!==768 || source.height!==768 ||
        !ref || ref.file !== 'source_reference.png' || ref.role !== 'source_reference' || !hash(ref.sha256) || ref.sha256 !== source.sha256 || ref.width !== source.width || ref.height !== source.height ||
        !review || review.file !== 'review.png' || review.role !== 'candidate_contact_sheet' || !hash(review.sha256) || !size(review.width) || !size(review.height) ||
        !bodyReview || bodyReview.file!=='body_assembly_review.png' || bodyReview.role!=='body_static_assembly_review' || !hash(bodyReview.sha256) || !size(bodyReview.width) || !size(bodyReview.height)) throw new Error('完整原图参考或审阅图来源/尺寸/SHA 无效');
    const roles = { 'source_reference.png':'source_reference', 'review.png':'candidate_contact_sheet', 'source_shorts_detail.png':'source_shorts_zoom_nearest_6x', 'shorts_review.png':'shorts_source_comparison_nearest_4x', 'body_visible_mask.png':'body_original_visible_mask', 'body_repair_mask.png':'body_ai_overlap_mask', 'body_assembly_review.png':'body_static_assembly_review', 'body_interfaces_review.png':'body_interface_detail_review' };
    if (!Array.isArray(m.assets) || m.assets.length !== 8 || new Set(m.assets.map(a=>a?.file)).size !== 8 ||
        m.assets.some(a=>!a || !Object.hasOwn(roles,a.file) || a.role !== roles[a.file] || !hash(a.sha256) || !size(a.width) || !size(a.height))) throw new Error('稳定部件参考资源白名单无效');
    for (const a of [ref,review,bodyReview]) {
      const entry=m.assets.find(item=>item.file===a.file);
      if (!entry || ['sha256','width','height','role'].some(key=>entry[key]!==a[key])) throw new Error('参考资源记录冲突');
    }
    if (!Array.isArray(m.parts) || m.parts.length !== 7) throw new Error('必须为固定7个逻辑件');
    const boundaryReview=m.boundaryReview,boundaryChecks=m.checks?.boundaryReview;
    if (!boundaryReview || boundaryReview.gapPixelCountBefore!==657 || boundaryReview.boundaryAssignmentApproved!==false ||
        ['sourceVisibleAssemblyRgbaMismatchPixels','sourceForegroundUncoveredPixels','sourceForegroundNotCoveredByCandidatesPixels'].some(key=>boundaryReview[key]!==0) ||
        [boundaryReview,boundaryChecks].some(entry=>!entry || entry.count!==3 || entry.addedPixelCount!==657 || entry.status!=='pending_manual_art_review' ||
          !entry.assignments || Object.keys(entry.assignments).length!==3 || entry.assignments.arm_near!==100 || entry.assignments.leg_near!==488 || entry.assignments.leg_far!==69)) throw new Error('边界候选汇总契约无效');
    const boundaryContract = {
      arm_near: {baseOriginalFile:'../../right_front_walk/parts/original/arm_near.png',sourceCoordinateCondition:'y<561 and x<420',addedPixelCount:100},
      leg_near: {baseOriginalFile:'../../right_front_walk/parts/original/leg_near.png',sourceCoordinateCondition:'y>=561 and x<420',addedPixelCount:488},
      leg_far: {baseOriginalFile:'../../right_front_walk/parts/original/leg_far.png',sourceCoordinateCondition:'x>=420',addedPixelCount:69}
    };
    const ids=new Set();
    for (const p of m.parts) {
      if (!p || !STABLE_IDS.includes(p.id) || ids.has(p.id) || p.hiddenComplete !== false || p.approvedForBinding !== false ||
          typeof p.label !== 'string' || !p.label.trim() || typeof p.reason !== 'string' || !p.reason.trim() ||
          !Array.isArray(p.repairNeeded) || !p.repairNeeded.length || p.repairNeeded.some(text=>typeof text!=='string'||!text.trim()) ||
          !Array.isArray(p.evidenceFrames) || p.evidenceFrames.length !== 0) throw new Error('稳定部件 ID/布尔状态/返工说明无效');
      ids.add(p.id);
      const expected=p.id==='body'?'source_preserved_ai_overlap_candidate':p.id==='head'?'source_visible_candidate':p.id==='shorts'?'coarse_clothing_candidate':boundaryContract[p.id]?'source_visible_boundary_reassignment':'visible_incomplete_candidate';
      if (p.status !== expected) throw new Error(p.id+' 候选状态不符');
      if (p.id==='body') {
        const s=p.source,c=s?.counts,staticCounts=['visibleRgbaMismatchPixels','repairOutsideOpaqueOccluders','sourceVisibleAssemblyRgbaMismatchPixels','sourceForegroundUncoveredPixels','sourceForegroundNotCoveredByCandidatesPixels','alphaUnionMismatchPixels','boundaryMaskOverlapPixels','bodyMaskOverlapPixels','repairOutsideFinalUpperOpaqueSafeDomain'],checks=m.checks?.parts?.body;
        if (p.sourcePixelOnly!==false || !s || s.visibleMaskFile!=='body_visible_mask.png' || s.repairMaskFile!=='body_repair_mask.png' || !s.donor || s.donor.file!=='../image2_repairs/body_candidate_v5.png' || !hash(s.donor.sha256) ||
            s.method!=='source_visible_preserved_ai_donor_hidden_overlap' || !c || !Number.isInteger(c.visiblePixels) || c.visiblePixels<=0 || !Number.isInteger(c.repairPixels) || c.repairPixels<=0 || c.visibleRgbaMismatchPixels!==0 || c.repairOutsideOpaqueOccluders!==0 ||
            !checks || staticCounts.some(key=>c[key]!==0 || checks[key]!==0) || checks.visiblePixels!==c.visiblePixels || checks.repairPixels!==c.repairPixels) throw new Error('body来源或局部搭接计数无效');
      } else if (p.sourcePixelOnly!==true) throw new Error(p.id+' 必须保持仅原图像素候选');
      const b=p.bbox;
      if (p.file !== p.id+'.png' || !hash(p.sha256) || !size(p.width) || !size(p.height) ||
          !bbox(b,ref.width,ref.height) || b[2]-b[0]!==p.width || b[3]-b[1]!==p.height) throw new Error(p.id+' 文件/SHA/源768 bbox尺寸无效');
      if (p.id==='head' || p.id==='arm_far') {
        const s=p.source,expectedFile='../../right_front_walk/parts/original/'+p.id+'.png';
        if (!s || s.file!==expectedFile || s.sha256!==p.sha256 || !hash(s.sha256) || s.method!=='byte_exact_original_visible_copy') throw new Error(p.id+' 逐字节复制来源契约无效');
      } else if (p.id==='shorts') {
        const s=p.source;
        if (!s || s.file!=='../../right_front_walk/source768.png' || s.method!=='manual_binary_polygon_visible_pixels' || !Array.isArray(s.polygon) || s.polygon.length<3 || s.polygon.some(point=>!Array.isArray(point)||point.length!==2||!point.every(Number.isInteger)||point[0]<0||point[0]>=source.width||point[1]<0||point[1]>=source.height)) throw new Error('shorts 原图多边形来源契约无效');
      } else if (boundaryContract[p.id]) {
        const s=p.source,c=boundaryContract[p.id],oldBody='../../right_front_walk/parts/original/body.png';
        if (!s || p.status!=='source_visible_boundary_reassignment' || s.file!=='../../right_front_walk/source768.png' || s.sha256!==source.sha256 || s.method!=='source_visible_boundary_reassignment' ||
            s.baseOriginalFile!==c.baseOriginalFile || !hash(s.baseOriginalSha256) || !bbox(s.baseOriginalBbox,source.width,source.height) || s.oldMixedBodyFile!==oldBody || !hash(s.oldMixedBodySha256) || !bbox(s.oldMixedBodyBbox,source.width,source.height) ||
            s.addedPixelCount!==c.addedPixelCount || s.boundaryAssignmentApproved!==false || s.sourceCoordinateCondition!==c.sourceCoordinateCondition) throw new Error(p.id+' 人工边线候选来源契约无效');
      }
    }
    if (ids.size!==STABLE_IDS.length || STABLE_IDS.some(id=>!ids.has(id))) throw new Error('稳定部件逻辑件集合不完整');
    return m;
  }
  function mountStable({host, base, taskId, sha256, onRequestFrame} = {}) {
    if (!host || typeof host.replaceChildren !== 'function') throw new Error('需要有效 host');
    // 静态候选没有视频帧身份；此视图不调用 onRequestFrame，也不挂接证据编辑器状态。
    const root=document.createElement('section');root.className='rae';
    root.innerHTML=`<div class="rae-notice">Meowa · 稳定角色部件 / 7张待审候选。body原可见保留 + AI隐藏域搭接待审；其余6件仅原图可见像素。不是完整隐藏补画，全部未验收、未绑定，不是正式角色图集。</div>
<div class="rae-workspace"><aside class="rae-library"><div class="rae-library-head"><strong>稳定逻辑件</strong><span data-ui="count">校验中</span></div><div class="rae-tree" role="listbox" aria-label="7个稳定逻辑件"></div></aside>
<div class="rae-main"><div class="rae-toolbar"><button data-ui="layout" disabled>重置候选排版</button><button data-ui="outlines" disabled aria-pressed="true">隐藏线框</button><button disabled title="全部approvedForBinding=false，body仅局部搭接待审，正式导出始终禁用">正式 PNG + atlas（禁用）</button><button disabled title="部件未验收，骨骼、权重和动画未完成">Spine ZIP（禁用）</button><span class="rae-spacer"></span><label class="rae-zoom">缩放<input data-ui="zoom" disabled type="range" min="10" max="250" step="1" value="100"><span data-ui="zoomText">100%</span></label><button data-ui="fit" disabled>适应视图</button></div>
<div class="rae-notice" data-ui="missing" role="status">正在核验manifest及所有PNG；尚未显示任何候选。</div><div class="rae-stage"><canvas data-ui="stage" width="512" height="512" aria-label="7张待审候选排版，含body原可见保留与AI局部搭接，非正式atlas，不含完整原图"></canvas></div><div class="rae-status" role="status" aria-live="polite">正在校验来源、SHA与图像尺寸…</div></div>
<aside class="rae-props"><div data-ui="props">校验完成后查看部件与真实返工说明。</div><div class="rae-info" data-ui="references" hidden><label><input data-ui="sourceToggle" type="checkbox">完整原图对照（独立参考，非body）</label><img data-ui="sourceImage" hidden alt="完整原图参考，绝不是body替代" style="width:100%;height:auto;object-fit:contain"><p data-ui="sourceInfo" style="overflow-wrap:anywhere;white-space:pre-line"></p><a data-ui="review" target="_blank" rel="noopener">查看审阅图（非正式图集）</a></div></aside></div>
<footer>body保留原图可见区域，仅采用已生成Image2供体的隐藏域局部搭接；不是完整隐藏补画，仍待审、未绑定。其他6件仅原图可见候选；不晋升旧runtime。near/far仅暂定屏幕层，不代表已验证解剖身份；名称、排序与旋转仅留在当前会话。</footer>`;
    const style=document.createElement('style');style.textContent=CSS;root.prepend(style);host.replaceChildren(root);
    const ui=key=>root.querySelector('[data-ui="'+key+'"]'), tree=root.querySelector('.rae-tree'), status=root.querySelector('.rae-status'), canvas=ui('stage'), ctx=canvas.getContext('2d');
    const state={ready:false,failed:false,parts:[],selected:'head',layout:null,outlines:true,autoFit:true,zoom:1,decoded:new Map()};
    const urls=new Set();let directory;
    root.querySelectorAll('input,button').forEach(el=>{el.disabled=true;});
    function fail(error) {
      state.failed=true;state.ready=false;state.parts=[];state.layout=null;state.decoded.clear();ui('count').textContent='校验失败';
      ctx?.clearRect(0,0,canvas.width,canvas.height);tree.replaceChildren();ui('props').replaceChildren();ui('references').hidden=true;
      ui('sourceImage').removeAttribute('src');ui('review').removeAttribute('href');
      root.querySelectorAll('button,input').forEach(el=>{el.disabled=true;});
      for (const href of urls) URL.revokeObjectURL(href);urls.clear();
      ui('missing').textContent='校验失败，7张待审候选均未开放；不是body正常无图状态，不回退旧素材。';
      status.className='rae-status rae-error';status.textContent='已停止校验：'+error.message;
    }
    function url(file) {
      if (!/^(?:manifest\.json|(?:head|body|shorts|arm_near|arm_far|leg_near|leg_far|source_reference|review|source_shorts_detail|shorts_review|body_visible_mask|body_repair_mask|body_assembly_review|body_interfaces_review)\.png)$/.test(file)) throw new Error('稳定资源文件不在白名单');
      const result=new URL(file,directory);
      if (result.origin!==directory.origin || !result.pathname.startsWith(directory.pathname) || result.search || result.hash) throw new Error('稳定资源路径越界');
      return result;
    }
    async function read(file) {
      const response=await fetch(url(file),{cache:'no-store',redirect:'error',credentials:'same-origin'});
      if (!response.ok) throw new Error(file+' HTTP '+response.status);return response;
    }
    async function png(meta) {
      const bytes=await(await read(meta.file)).arrayBuffer(), signature=new Uint8Array(bytes,0,Math.min(8,bytes.byteLength));
      if ([137,80,78,71,13,10,26,10].some((v,i)=>signature[i]!==v)) throw new Error(meta.file+' 非PNG');
      const digest=await sha256Hex(bytes);
      if (digest!==meta.sha256) throw new Error(meta.file+' SHA不符');
      const href=URL.createObjectURL(new Blob([bytes],{type:'image/png'}));urls.add(href);
      const image=new Image();image.onerror=()=>fail(new Error(meta.file+' 图像解码失败'));image.src=href;await image.decode();
      if (image.naturalWidth!==meta.width || image.naturalHeight!==meta.height) throw new Error(meta.file+' 实际尺寸不符');
      return {image,href};
    }
    function fit() {
      if (!state.ready || state.failed) return;
      const stage=root.querySelector('.rae-stage'), scale=state.autoFit?Math.min(1,Math.max(100,stage.clientWidth-32)/canvas.width,Math.max(100,stage.clientHeight-32)/canvas.height):state.zoom;
      canvas.style.width=Math.round(canvas.width*scale)+'px';ui('zoomText').textContent=Math.round(scale*100)+'%';ui('zoom').value=String(Math.round(scale*100));
    }
    function render() {
      if (!state.ready || state.failed) return;
      const layout=state.layout=packParts(state.parts);
      canvas.width=layout.width;canvas.height=layout.height;
      for (const t of layout.tiles) {
        ctx.save();ctx.translate(t.x+t.w/2,t.y+t.h/2);ctx.rotate(t.p.atlasTurns*Math.PI/2);ctx.drawImage(t.p.image,-t.p.w/2,-t.p.h/2);ctx.restore();
        if (state.outlines) {
          ctx.strokeStyle=state.selected===t.p.meta.id?'#a5ffe1':t.p.color;ctx.lineWidth=t.p.lineWidth;ctx.strokeRect(t.x,t.y,t.w,t.h);
          ctx.fillStyle='#e7edf5';ctx.font='10px system-ui';ctx.fillText(t.p.order+'. '+t.p.name,t.x,t.y+t.h+15,t.w);
        }
      }
      status.textContent='7逻辑件 / 7张已校验待审候选 · '+layout.width+' × '+layout.height+' · body原可见保留 + AI隐藏域局部搭接 · 未绑定 / 非正式atlas · 正式导出禁用';fit();
    }
    function select(id) {if (!state.ready || state.failed) return;state.selected=id;updateTree();properties();render();}
    function updateTree() {
      tree.replaceChildren();
      for (const p of state.parts.slice().sort((a,b)=>a.order-b.order)) {
        const row=document.createElement('div'), button=document.createElement('button'), text=document.createElement('span'), note=document.createElement('small');row.className='rae-row';button.type='button';button.setAttribute('aria-pressed',String(state.selected===p.meta.id));button.title=p.meta.id;
        if (p.href) {const image=new Image();image.alt=p.name+' 未完整候选';image.onerror=()=>fail(new Error(p.meta.id+' 缩略图失败'));image.src=p.href;button.append(image);}
        text.textContent=p.name;note.textContent=p.meta.id==='body'?'原可见保留 + AI局部搭接 / 待审':p.meta.id+' · 仅原图可见候选 / 未验收';text.append(note);button.append(text);button.onclick=()=>select(p.meta.id);row.append(button);tree.append(row);
      }
    }
    function field(parent,labelText,type,value,handler,attrs={}) {
      const label=document.createElement('label'), input=document.createElement('input');label.textContent=labelText;input.type=type;input.value=String(value);
      for (const [key,v] of Object.entries(attrs)) input.setAttribute(key,String(v));
      input.onchange=()=>{if (state.ready&&!state.failed) handler(input);};label.append(input);parent.append(label);
    }
    function properties() {
      const host=ui('props'),p=state.parts.find(item=>item.meta.id===state.selected);host.replaceChildren();if (!p) return;
      const title=document.createElement('h3');title.className='rae-title';title.textContent=p.name;host.append(title);
      const preview=document.createElement('div'),image=new Image();preview.className='rae-preview';image.alt=p.meta.id==='body'?'body原可见保留 + Image2供体隐藏域局部搭接待审候选，非完整补画，未绑定':p.meta.id+' 仅原图可见候选，未完整、未绑定';image.onerror=()=>fail(new Error(p.meta.id+' 预览失败'));image.src=p.href;image.style.transform='rotate('+p.atlasTurns*90+'deg)';preview.append(image);host.append(preview);
      const fields=document.createElement('div');fields.className='rae-fields';host.append(fields);
      field(fields,'会话名称','text',p.name,input=>{p.name=input.value.trim().slice(0,80)||p.meta.label;input.value=p.name;title.textContent=p.name;updateTree();render();},{maxlength:80});
      field(fields,'逻辑件排序','number',p.order,input=>{const n=Number(input.value);if (input.value.trim()&&Number.isInteger(n)&&n>=1&&n<=7) {const ordered=state.parts.slice().sort((a,b)=>a.order-b.order);ordered.splice(ordered.indexOf(p),1);ordered.splice(n-1,0,p);ordered.forEach((item,i)=>{item.order=i+1;});updateTree();render();}else input.value=p.order;},{min:1,max:7,step:1});
      if (p.href) {
        field(fields,'线框颜色','color',p.color,input=>{p.color=input.value;render();});
        field(fields,'线框粗细','number',p.lineWidth,input=>{const n=Number(input.value);if (Number.isInteger(n)&&n>=1&&n<=8) p.lineWidth=n;else input.value=p.lineWidth;render();},{min:1,max:8,step:1});
        const rotate=document.createElement('div');rotate.className='rae-rotate';for (const direction of [-1,1]) {const button=document.createElement('button');button.textContent=(direction<0?'-':'+')+'90°';button.onclick=()=>{if (!state.ready||state.failed) return;p.atlasTurns=(p.atlasTurns+direction+4)%4;render();properties();};rotate.append(button);}fields.append(rotate);
      }
      const info=document.createElement('div');info.className='rae-info';info.style.whiteSpace='pre-wrap';info.style.overflowWrap='anywhere';
      info.textContent='ID：'+p.meta.id+'\nstatus：'+p.meta.status+'\n文件：'+p.meta.file+' · '+p.w+' × '+p.h+'\nSHA-256：'+p.meta.sha256+'\nbbox（源768坐标）：'+p.meta.bbox.join(', ')+'\nhiddenComplete='+p.meta.hiddenComplete+' / approvedForBinding='+p.meta.approvedForBinding+' / sourcePixelOnly='+p.meta.sourcePixelOnly+'\n原因：'+p.meta.reason+'\nrepairNeeded：\n'+p.meta.repairNeeded.map(text=>'• '+text).join('\n')+'\n静态待审候选，无视频帧归属证据；未绑定。';host.append(info);
      if (p.meta.status==='source_visible_boundary_reassignment') {
        const s=p.meta.source,provenance=document.createElement('div');provenance.className='rae-info';provenance.style.whiteSpace='pre-wrap';provenance.style.overflowWrap='anywhere';
        provenance.textContent='人工可见边线归属候选 · 待美术审阅\n新增原图可见像素：'+s.addedPixelCount+'\nboundaryAssignmentApproved='+s.boundaryAssignmentApproved+'\n不是AI新补画；不是逐字节复制旧裁片。\nmethod：'+s.method+'\n原图：'+s.file+'\n原图SHA-256：'+s.sha256+'\n基础原裁片：'+s.baseOriginalFile+'\n基础SHA-256：'+s.baseOriginalSha256+'\n基础bbox：'+s.baseOriginalBbox.join(', ')+'\n旧混合body：'+s.oldMixedBodyFile+'\n旧混合body SHA-256：'+s.oldMixedBodySha256+'\n旧混合body bbox：'+s.oldMixedBodyBbox.join(', ')+'\n源坐标条件：'+s.sourceCoordinateCondition+'\n保留原裁片并加入原图边线像素，不代表完整隐藏结构或正式验收。来源记录未在前端逐像素重算。';host.append(provenance);
      }
      if (p.meta.id==='body') {
        const s=p.meta.source,c=s.counts,provenance=document.createElement('div');provenance.className='rae-info';provenance.style.whiteSpace='pre-wrap';provenance.style.overflowWrap='anywhere';
        provenance.textContent='来源：原图可见区域保留 + 已生成Image2供体的隐藏域局部搭接。\nmethod：'+s.method+'\n供体：'+s.donor.file+'\n供体SHA-256（manifest记录）：'+s.donor.sha256+'\nvisiblePixels：'+c.visiblePixels+' / repairPixels：'+c.repairPixels+'\nvisibleRgbaMismatchPixels：'+c.visibleRgbaMismatchPixels+' / repairOutsideOpaqueOccluders：'+c.repairOutsideOpaqueOccluders+'\n不是完整隐藏补画，仍待审、未绑定。供体与计数为来源记录，前端未重新验证供体像素。';host.append(provenance);
        const links=document.createElement('div');links.className='rae-info';
        for (const [file,label] of [[s.visibleMaskFile,'查看body原图可见区域mask'],[s.repairMaskFile,'查看body AI局部搭接mask'],['body_assembly_review.png','查看body静态试组装审阅图'],['body_interfaces_review.png','查看body接口细节审阅图']]) {
          const link=document.createElement('a');link.textContent=label+'（已校验PNG）';link.href=state.decoded.get(file).href;link.target='_blank';link.rel='noopener';links.append(link,document.createElement('br'));
        }
        host.append(links);
      }
    }
    ui('outlines').onclick=()=>{if (!state.ready||state.failed) return;state.outlines=!state.outlines;ui('outlines').textContent=state.outlines?'隐藏线框':'显示线框';ui('outlines').setAttribute('aria-pressed',String(state.outlines));render();};
    ui('layout').onclick=()=>{if (!state.ready||state.failed) return;for (const p of state.parts) {p.order=p.originalOrder;p.atlasTurns=0;}updateTree();render();properties();};
    ui('fit').onclick=()=>{state.autoFit=true;fit();};ui('zoom').oninput=()=>{state.autoFit=false;state.zoom=Number(ui('zoom').value)/100;fit();};
    ui('sourceToggle').onchange=()=>{ui('sourceImage').hidden=state.failed||!ui('sourceToggle').checked;};
    canvas.onpointerdown=event=>{if (!state.ready||state.failed||event.button!==0) return;const q=clientToCanvas({x:event.clientX,y:event.clientY},canvas.getBoundingClientRect(),canvas.width,canvas.height),tile=state.layout.tiles.find(t=>q.x>=t.x&&q.x<t.x+t.w&&q.y>=t.y&&q.y<t.y+t.h);if (tile) select(tile.p.meta.id);};
    const observer=new ResizeObserver(fit);observer.observe(root.querySelector('.rae-stage'));
    const ready=(async()=>{try {
      if (!ctx) throw new Error('无法创建Canvas 2D上下文');
      if (typeof base!=='string'||!base.endsWith('/')) throw new Error('base必须为父任务目录');
      const parent=new URL(base,document.baseURI);
      if (!['http:','https:'].includes(parent.protocol)||parent.origin!==new URL(document.baseURI).origin||parent.search||parent.hash||parent.username||parent.password) throw new Error('base来源不安全');
      directory=new URL('stable_parts_v1/',parent);
      const manifest=validateStable(await(await read('manifest.json')).json(),taskId,sha256), decoded=new Map();
      // 全部解码校验后一次开放；任一文件失败不展示部分成功结果，也不回退旧runtime。
      for (const meta of [...manifest.parts,...manifest.assets]) {decoded.set(meta.file,await png(meta));if (state.failed) return false;}
      state.decoded=decoded;
      state.parts=STABLE_IDS.map((id,i)=>{const meta=manifest.parts.find(p=>p.id===id);return {meta,name:meta.label,order:i+1,originalOrder:i+1,w:meta.width,h:meta.height,atlasTurns:0,color:'#ce8791',lineWidth:1,...decoded.get(meta.file)};});
      const ref=manifest.sourceReference;ui('sourceImage').onerror=()=>fail(new Error('完整原图参考显示失败'));ui('sourceImage').src=decoded.get(ref.file).href;
      ui('sourceInfo').textContent='完整原图参考（非body）\n'+ref.file+' · '+ref.width+' × '+ref.height+'\nSHA-256：'+ref.sha256;ui('review').href=decoded.get(manifest.review.file).href;
      state.ready=true;ui('references').hidden=false;ui('count').textContent='7项 / 7张待审';
      ui('missing').textContent='7张待审候选：body原可见保留 + 已生成Image2供体的AI隐藏域局部搭接；其余6件仅原图可见像素。不是完整隐藏补画；全部未验收、未绑定，正式PNG+atlas与Spine ZIP始终禁用。';
      for (const key of ['layout','outlines','zoom','fit','sourceToggle']) ui(key).disabled=false;
      updateTree();render();properties();return true;
    } catch (error) {fail(error);return false;}})();
    return Object.freeze({ready});
  }
  global.RigAtlasEditor=Object.freeze({mount,mountStable,validateStable,geometry,packParts});
})(window);
