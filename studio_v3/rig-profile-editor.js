(function (global, factory) {
  'use strict';
  const api = factory(global);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (global) global.RigProfileEditor = api;
})(typeof window !== 'undefined' ? window : globalThis, function (global) {
  'use strict';

  const DURATION = 2 / 3;
  const FPS = 24;
  const START_FRAME = 68;
  const END_FRAME = 84;
  const MESH_SLOTS = ['leg_far', 'leg_near', 'arm_far', 'arm_near'];
  const DRAFT_MAX_AGE = 30 * 24 * 60 * 60 * 1000;
  const SHA_RE = /^[a-f0-9]{64}$/;
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
  // 旧包兼容默认值；实例使用自己的来源清单，草稿仍按源 SHA 隔离。
  const SOURCE_SHA = Object.freeze({
    'profile_walk_v1/profile.json':'975bac9ec8bde3f537ec709373b7eecbaab89afc00b61a603f1474d275a8cf2e',
    'profile_walk_v1/profile_walk.json':'fd59ae539c48fa2aef48f4a24ad361eed2310b0a5d45f2cf18dffca2afc2b8d0',
    'profile_walk_v1/provenance.json':'2935e185e431ad172869da675c2686cde92e8eee9353c6ea1994e6582edad916',
    'profile_walk_v1/checks.json':'bf39b1575b4b9659bb78d65f32c06724abc4834806b2ccc508709eb59d519fa1',
    'profile_walk_v1/profile_walk.atlas':'eab6996adbed79c81a719bf77f92b383cb1a209f7483114ebf408155d6bf44a6',
    'profile_walk_v1/profile_walk.png':'fa17d490378313cfda33f7100d70c5001f1bbc83a9c54c81f4a417b41b9a5d6b',
    'stable_parts_v1/manifest.json':'c928c89c6f64864359a89e429bc80f5518a3e5149e4dbc5990478c60a243569b',
    'video_parts_v1/cycle_review/sources.json':'e0281aa3dbd8440fa2808603284e9938158bf07eb2c4c148c75b9a8332040f06'
  });
  const CSS = `
.rpe,.rpe-export{--rpe-bg:var(--panel,var(--bg,#fff));--rpe-panel:var(--panel2,var(--bg,#f3f6f5));--rpe-line:var(--line,#d9e2e2);--rpe-text:var(--text,var(--ink,#26343a));--rpe-muted:var(--muted,#68777c);--rpe-accent:var(--accent,#ba5d3d);color:var(--rpe-text);background:var(--rpe-bg);border:1px solid var(--rpe-line);border-radius:6px;font:12px/1.5 system-ui,"Microsoft YaHei",sans-serif;min-width:0;overflow:hidden}
.rpe *,.rpe-export *{box-sizing:border-box}.rpe[hidden],.rpe [hidden]{display:none!important}
.rpe button,.rpe input,.rpe-export button{font:inherit;color:inherit;background:var(--rpe-bg);border:1px solid var(--rpe-line);border-radius:4px;padding:5px 7px;min-width:0}.rpe button,.rpe-export button{cursor:pointer}.rpe button:disabled,.rpe input:disabled,.rpe-export button:disabled{opacity:.45;cursor:not-allowed}.rpe button:focus-visible,.rpe input:focus-visible,.rpe-export button:focus-visible{outline:2px solid var(--rpe-accent);outline-offset:2px}.rpe button[aria-pressed=true]{border-color:var(--rpe-accent);color:var(--rpe-accent);font-weight:600}
.rpe-header,.rpe-toolbar,.rpe-phases,.rpe-controls,.rpe-export-row{display:flex;align-items:center;flex-wrap:wrap;gap:7px;padding:9px 11px;border-bottom:1px solid var(--rpe-line)}.rpe-title{font-size:14px;font-weight:700}.rpe-spacer{flex:1}.rpe-sub,.rpe-status{color:var(--rpe-muted);overflow-wrap:anywhere}.rpe-error{color:var(--error,var(--danger,#a64235))!important}.rpe-status{min-height:20px}.rpe-workspace{display:grid;grid-template-columns:165px minmax(0,1fr) 220px}.rpe-tree,.rpe-inspector{padding:10px;background:var(--rpe-panel);min-width:0;overflow:auto}.rpe-tree{border-right:1px solid var(--rpe-line)}.rpe-inspector{border-left:1px solid var(--rpe-line)}.rpe h3{font-size:12px;margin:0 0 7px}.rpe-list{display:grid;gap:3px}.rpe-list button{text-align:left;overflow-wrap:anywhere;background:transparent}.rpe-bone{padding-left:calc(6px + var(--depth,0)*10px)!important}.rpe-section{border-top:1px solid var(--rpe-line);margin-top:12px;padding-top:10px}.rpe-main{min-width:0}.rpe-comparison{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--rpe-line)}.rpe-stage{position:relative;background:var(--rpe-bg);min-width:0}.rpe-stage canvas{width:100%;height:320px;object-fit:contain;display:block}.rpe-stage-label{display:block;padding:6px 9px;color:var(--rpe-muted);background:var(--rpe-bg)}.rpe-source-stage{height:320px;position:relative;background:var(--rpe-panel)}.rpe-source-stage img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.rpe-overlay{position:absolute;inset:25px 0 0;display:grid;place-items:center;padding:20px;background:var(--rpe-bg);overflow-wrap:anywhere}.rpe-controls input{flex:1;min-width:100px}.rpe-reference{padding:9px}.rpe-reference-grid{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:3px}.rpe-reference-grid button{padding:2px;overflow:hidden}.rpe-reference-grid img{width:100%;aspect-ratio:1.8;object-fit:contain;display:block}.rpe-reference-grid small{display:block;text-align:center}.rpe input[type=number]{width:100%;margin:6px 0}.rpe-inspector button{margin:3px 0}.rpe-pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.6 ui-monospace,monospace;margin:0}.rpe-context{padding:7px 11px;color:var(--rpe-muted);border-bottom:1px solid var(--rpe-line)}.rpe-export-status{padding:10px 11px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--rpe-muted)}.rpe-tag{border:1px solid var(--rpe-line);padding:2px 6px;border-radius:3px}
.rpe-verdict{font-size:20px;font-weight:800;padding:12px;border-bottom:1px solid var(--rpe-line)}.rpe-task-feedback{padding:8px 12px}.rpe .rpe-workspace{display:block}.rpe .rpe-advanced{border-top:1px solid var(--rpe-line);padding:10px}.rpe .rpe-advanced>summary{cursor:pointer;font-weight:700;padding:3px}.rpe .rpe-advanced summary:focus-visible{outline:2px solid var(--rpe-accent)}.rpe .rpe-advanced-workspace{display:grid;grid-template-columns:minmax(160px,1fr) minmax(240px,2fr);margin-top:10px}.rpe .rpe-advanced .rpe-tree,.rpe .rpe-advanced .rpe-inspector{max-height:640px;overflow:auto}.rpe .rpe-evidence{padding:12px 0}.rpe .rpe-comparison{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
@media(max-width:650px){.rpe .rpe-advanced-workspace{display:block}.rpe .rpe-comparison{grid-template-columns:1fr}}
@media(max-width:1100px){.rpe-workspace{grid-template-columns:150px minmax(0,1fr)}.rpe-inspector{grid-column:1/-1;border-left:0;border-top:1px solid var(--rpe-line)}}@media(max-width:650px){.rpe-workspace{display:block}.rpe-tree{max-height:240px;border-right:0}.rpe-comparison{grid-template-columns:1fr}.rpe-stage canvas,.rpe-source-stage{height:280px}}
`;

  function clone(value) { return value == null ? value : JSON.parse(JSON.stringify(value)); }
  function utf8(value) { return new TextEncoder().encode(value); }
  function text(value) { return new TextDecoder().decode(value); }
  function jsonBytes(value) { return utf8(JSON.stringify(value,null,2)+'\n'); }
  function sha256Fallback(input) {
    const length=input.length, bitLength=length*8, paddedLength=Math.ceil((length+9)/64)*64;
    const bytes=new Uint8Array(paddedLength); bytes.set(input); bytes[length]=0x80;
    const view=new DataView(bytes.buffer);
    view.setUint32(paddedLength-8,Math.floor(bitLength/0x100000000),false);
    view.setUint32(paddedLength-4,bitLength>>>0,false);
    let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
    const w=new Uint32Array(64);
    for(let offset=0;offset<paddedLength;offset+=64){
      for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4,false);
      for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2],s0=((a>>>7)|(a<<25))^((a>>>18)|(a<<14))^(a>>>3),s1=((b>>>17)|(b<<15))^((b>>>19)|(b<<13))^(b>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;}
      let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
      for(let i=0;i<64;i++){const s1=((e>>>6)|(e<<26))^((e>>>11)|(e<<21))^((e>>>25)|(e<<7)),ch=(e&f)^(~e&g),t1=(h+s1+ch+SHA_K[i]+w[i])>>>0,s0=((a>>>2)|(a<<30))^((a>>>13)|(a<<19))^((a>>>22)|(a<<10)),maj=(a&b)^(a&c)^(b&c),t2=(s0+maj)>>>0;h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}
      h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+h)>>>0;
    }
    return [h0,h1,h2,h3,h4,h5,h6,h7].map(value=>value.toString(16).padStart(8,'0')).join('');
  }
  async function sha256Hex(bytes) {
    if(global.crypto?.subtle?.digest){
      try{return [...new Uint8Array(await global.crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');}catch(_){/* 内网环境禁用 WebCrypto 时使用同一算法。 */}
    }
    return sha256Fallback(bytes);
  }
  function crc32(bytes) { let c=0xffffffff;for(const b of bytes){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0; }
  function zipStoreBytes(files) {
    const chunks=[],central=[];let offset=0;
    for(const file of files){
      const name=utf8(file.name),data=file.data instanceof Uint8Array?file.data:new Uint8Array(file.data),crc=crc32(data);
      const header=new Uint8Array(30+name.length),hv=new DataView(header.buffer);
      hv.setUint32(0,0x04034b50,true);hv.setUint16(4,20,true);hv.setUint16(6,0x800,true);hv.setUint16(12,33,true);hv.setUint32(14,crc,true);hv.setUint32(18,data.length,true);hv.setUint32(22,data.length,true);hv.setUint16(26,name.length,true);header.set(name,30);
      const record=new Uint8Array(46+name.length),rv=new DataView(record.buffer);
      rv.setUint32(0,0x02014b50,true);rv.setUint16(4,20,true);rv.setUint16(6,20,true);rv.setUint16(8,0x800,true);rv.setUint16(14,33,true);rv.setUint32(16,crc,true);rv.setUint32(20,data.length,true);rv.setUint32(24,data.length,true);rv.setUint16(28,name.length,true);rv.setUint32(42,offset,true);record.set(name,46);
      chunks.push(header,data);central.push(record);offset+=header.length+data.length;
    }
    const centralSize=central.reduce((n,c)=>n+c.length,0),end=new Uint8Array(22),ev=new DataView(end.buffer);
    ev.setUint32(0,0x06054b50,true);ev.setUint16(8,files.length,true);ev.setUint16(10,files.length,true);ev.setUint32(12,centralSize,true);ev.setUint32(16,offset,true);
    const result=new Uint8Array(offset+centralSize+22);let at=0;
    for(const part of [...chunks,...central,end]){result.set(part,at);at+=part.length;}return result;
  }
  function runtimeBoneTimeline(runtime,name) { return runtime?.animations?.walk?.bones?.[name]; }
  function insertRotateKey(runtime,name,time,value,options={}) {
    const duration=options.duration??DURATION;
    if(!runtime?.bones?.some(bone=>bone.name===name))throw new Error('没有选择有效骨骼');
    if(!Number.isFinite(time)||time<0||time>duration||!Number.isFinite(value)||Math.abs(value)>180)throw new Error('时间或角度超出允许范围（角度 ±180°）');
    const result=clone(runtime),bones=result.animations?.walk?.bones;
    if(!bones)throw new Error('runtime 缺少 walk/bones');
    if(!Object.hasOwn(bones,name))bones[name]={};
    const bone=bones[name];
    if(!Array.isArray(bone.rotate))bone.rotate=[{time:0,value:0},{time:duration,value:0}];
    function put(at){const exact=bone.rotate.findIndex(key=>Math.abs((key.time||0)-at)<1e-6);if(exact>=0)bone.rotate[exact]={...bone.rotate[exact],value};else bone.rotate.push({time:at,value});}
    put(time);
    // 循环端点成对写入，保持接缝；不改任何 setup 或 mesh 数据。
    if(time<1e-6)put(duration);
    if(Math.abs(time-duration)<1e-6)put(0);
    bone.rotate.sort((a,b)=>(a.time||0)-(b.time||0));return result;
  }
  function storageKey(taskId,profileId,runtimeSha,profileSha) { return 'rig-profile-editor:v1:'+ [taskId,profileId,runtimeSha,profileSha].map(encodeURIComponent).join(':'); }
  function validRuntimeEdits(runtime,source,options={}) {
    const duration=options.duration??DURATION;
    try{
      if(!runtime||Array.isArray(runtime)||!source)return false;
      const candidate=clone(runtime),original=clone(source),bones=candidate.animations.walk.bones,sourceBones=original.animations.walk.bones,names=new Set(source.bones.map(bone=>bone.name));
      for(const name of Object.keys(bones)){
        if(!names.has(name))return false;
        const rotate=bones[name].rotate,sourceRotate=sourceBones[name]?.rotate;
        if(JSON.stringify(rotate)!==JSON.stringify(sourceRotate)){
          if(!Array.isArray(rotate)||rotate.length<2||rotate.length>4096)return false;
          let last=-1;
          for(const key of rotate){
            const time=key.time??0,value=key.value??0;
            const sourceKey=sourceRotate?.find(item=>Math.abs((item.time||0)-time)<1e-6);
            if(!Number.isFinite(time)||time<0||time>duration||time<=last||!Number.isFinite(value)||(Math.abs(value)>180&&value!==sourceKey?.value))return false;
            if(Object.keys(key).some(field=>!['time','value','curve'].includes(field)))return false;
            if(JSON.stringify(key.curve)!==JSON.stringify(sourceKey?.curve))return false;
            last=time;
          }
          if(Math.abs(rotate[0].time||0)>1e-6||Math.abs(rotate.at(-1).time-duration)>1e-6||Math.abs((rotate[0].value||0)-(rotate.at(-1).value||0))>1e-6)return false;
        }
        delete bones[name].rotate;if(!Object.keys(bones[name]).length)delete bones[name];
      }
      for(const name of Object.keys(sourceBones)){delete sourceBones[name].rotate;if(!Object.keys(sourceBones[name]).length)delete sourceBones[name];}
      return JSON.stringify(candidate)===JSON.stringify(original);
    }catch(_){return false;}
  }
  function validDraft(draft,expected,now=Date.now()) {
    return !!draft&&draft.schemaVersion===1&&draft.taskId===expected.taskId&&draft.profileId===expected.profileId&&draft.characterId===null&&draft.sourceProfileCharacterId===null&&draft.runtimeSha===expected.runtimeSha&&draft.profileSha===expected.profileSha&&typeof draft.edited==='boolean'&&Number.isFinite(draft.savedAt)&&now-draft.savedAt>=0&&now-draft.savedAt<=DRAFT_MAX_AGE&&validRuntimeEdits(draft.runtime,expected.runtimeSource,expected);
  }
  function safePath(base,relative) {
    const root=new URL(base,global.location?.href||'http://localhost/');if(!root.pathname.endsWith('/'))root.pathname+='/';
    const url=new URL(relative,root);
    if(!['http:','https:'].includes(url.protocol)||url.origin!==root.origin||!url.pathname.startsWith(root.pathname)||/%2f|%5c/i.test(url.pathname))throw new Error('资源路径越界');
    return url.href;
  }
  function sourceRelative(file) {
    const prefix='generated_rig/video_f7e82942/';
    if(typeof file!=='string'||!file.startsWith(prefix))throw new Error('来源文件不属于当前源包');
    return file.slice(prefix.length);
  }
  function sourceChecksBlocked(checks) { return checks?.numericalChecksPassed===false||checks?.videoFitPassed===false; }
  function verifyEvidence(evidence,sources,expected) {
    if(evidence.taskId!==expected.taskId||evidence.packageId!==expected.packageId||evidence.characterId!==null)throw new Error('视频依据任务或来源身份不符');
    const items=evidence.parts??evidence.items,slots=new Set(expected.slotNames),frames=sources.frames;
    if(!Array.isArray(items)||items.length!==7||new Set(items.map(item=>item?.id)).size!==7||slots.size!==7)throw new Error('视频依据需要七件唯一记录');
    if(!Array.isArray(frames)||frames.length!==expected.frameEnd-expected.frameStart+1||new Set(frames.map(frame=>frame.sourceFrame)).size!==frames.length)throw new Error('源帧清单重复或缺失');
    function verifyFrames(entries){
      if(!Array.isArray(entries)||!entries.length||new Set(entries.map(entry=>entry?.frame)).size!==entries.length)throw new Error('视频依据帧记录重复或缺失');
      for(const entry of entries){
        const source=frames.find(frame=>frame.sourceFrame===entry?.frame);
        if(!source||!Number.isInteger(entry.frame)||entry.frame<expected.frameStart||entry.frame>expected.frameEnd||entry.decodedPixelsExact!==true||!SHA_RE.test(entry.sha256||'')||entry.sha256!==source.sourceFrameSha256||source.sourceFile!=='source_'+String(entry.frame).padStart(3,'0')+'.png'||sourceRelative(entry.file)!=='video_parts_v1/cycle_review/'+source.sourceFile)throw new Error('视频依据帧路径或固定源 SHA 不符');
      }
    }
    for(const item of items){
      if(!slots.has(item.id)||typeof item.visibleBasis!=='string'||typeof item.occlusion!=='string'||!Array.isArray(item.limitations)||item.limitations.some(value=>typeof value!=='string'))throw new Error('视频依据字段无效：'+item.id);
      verifyFrames(item.frames);
    }
    if(evidence.videoFrames!==undefined){verifyFrames(evidence.videoFrames);if(evidence.videoFrames.length!==frames.length)throw new Error('视频依据完整帧清单缺失');}
    return items;
  }
  function verifyBinding(profile,runtime,expected={}) {
    if(typeof expected==='string')expected={profileId:expected};
    if(typeof profile.profileId!=='string'||!profile.profileId||(expected.profileId!==undefined&&profile.profileId!==expected.profileId)||profile.characterId!==null||profile.motionFile!=='profile_walk.json')throw new Error('源 Profile 身份不符');
    if(!runtime.skeleton?.spine?.startsWith('4.2')||runtime.bones?.length!==12||runtime.slots?.length!==7)throw new Error('需要 Spine 4.2 / 12 bones / 7 slots');
    const attachments=runtime.skins?.find(skin=>skin.name==='default')?.attachments;
    if(!profile.bind||JSON.stringify(profile.bind.bones)!==JSON.stringify(runtime.bones)||JSON.stringify(profile.bind.slots)!==JSON.stringify(runtime.slots)||JSON.stringify(profile.bind.attachments)!==JSON.stringify(attachments))throw new Error('Profile bind 与 runtime 不一致');
    const meshSlots=Object.entries(attachments||{}).filter(([,items])=>Object.values(items).some(item=>item.type==='mesh')).map(([name])=>name).sort();
    if(JSON.stringify(meshSlots)!==JSON.stringify([...(expected.meshSlots??MESH_SLOTS)].sort()))throw new Error('runtime 不是约定的四 mesh');
  }
  function makeRig(spine,atlas,runtime,options={}) {
    const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(runtime),animation=data.findAnimation('walk');
    if(!animation||Math.abs(animation.duration-(options.duration??DURATION))>1e-5||data.bones.length!==12||data.slots.length!==7)throw new Error('runtime 结构或 walk 周期不符');
    return {skeleton:new spine.Skeleton(data),animation};
  }
  function poseRig(spine,rig,time) {
    rig.skeleton.setToSetupPose();
    rig.animation.apply(rig.skeleton,0,time,false,[],1,spine.MixBlend.replace,spine.MixDirection.mixIn);
    rig.skeleton.updateWorldTransform(spine.Physics.update);
  }
  function inspectMeshes(spine,rig,baseline,options={}) {
    const errors=[],signs=baseline||new Map(),first=new Map();
    for(let sample=0;sample<65;sample++){
      poseRig(spine,rig,(options.duration??DURATION)*sample/64);
      if(rig.skeleton.bones.some(bone=>[bone.a,bone.b,bone.c,bone.d,bone.worldX,bone.worldY].some(value=>!Number.isFinite(value))))errors.push('sample '+sample+' 骨骼变换非有限');
      for(const name of options.meshSlots??MESH_SLOTS){
        const slot=rig.skeleton.findSlot(name),mesh=slot?.getAttachment();
        if(!(mesh instanceof spine.MeshAttachment))throw new Error(name+' 不是 mesh');
        const vertices=new Float32Array(mesh.worldVerticesLength);mesh.computeWorldVertices(slot,0,vertices.length,vertices,0,2);
        if(vertices.some(value=>!Number.isFinite(value)))errors.push(name+' sample '+sample+' 顶点非有限');
        if(!sample)first.set(name,vertices);
        if(sample===64&&vertices.some((value,index)=>Math.abs(value-first.get(name)[index])>.01))errors.push(name+' 循环首尾不连续');
        for(let i=0;i<mesh.triangles.length;i+=3){
          const a=mesh.triangles[i]*2,b=mesh.triangles[i+1]*2,c=mesh.triangles[i+2]*2,area=(vertices[b]-vertices[a])*(vertices[c+1]-vertices[a+1])-(vertices[b+1]-vertices[a+1])*(vertices[c]-vertices[a]),key=name+':'+i,sign=Math.sign(area);
          if(!baseline&&!sample)signs.set(key,sign);
          if(!Number.isFinite(area)||Math.abs(area)<1e-7||sign!==signs.get(key))errors.push(name+' sample '+sample+' 三角形退化/翻转');
        }
      }
    }
    return {ok:!errors.length,errors,signs,samples:65};
  }

  function makeEditor(options) {
    const {host,exportHost,base,taskId,onRequestFrame}=options||{};
    if(!host||typeof host.replaceChildren!=='function')throw new Error('需要有效 host');
    if(typeof base!=='string'||typeof taskId!=='string'||!taskId)throw new Error('需要 base 与 taskId');
    const packageId=options.packageId??'profile_walk_v1',duration=options.duration??DURATION,fps=options.fps??FPS,frameStart=options.frameStart??START_FRAME,frameEnd=options.frameEnd??END_FRAME,meshSlots=[...(options.meshSlots??MESH_SLOTS)];
    if(typeof packageId!=='string'||!/^[a-zA-Z0-9_-]+$/.test(packageId))throw new Error('packageId 无效');
    if(!Number.isFinite(duration)||duration<=0||!Number.isFinite(fps)||fps<=0||!Number.isInteger(frameStart)||!Number.isInteger(frameEnd)||frameStart<0||frameEnd<=frameStart||frameEnd-frameStart>1000||Math.abs((frameEnd-frameStart)/fps-duration)>1e-5)throw new Error('时间参数无效：帧范围 / fps 必须与 duration 一致');
    if(meshSlots.length!==4||new Set(meshSlots).size!==4||meshSlots.some(name=>typeof name!=='string'||!name))throw new Error('需要四个唯一 meshSlots');
    const sourceSha={...(packageId==='profile_walk_v1'?SOURCE_SHA:{'stable_parts_v1/manifest.json':SOURCE_SHA['stable_parts_v1/manifest.json'],'video_parts_v1/cycle_review/sources.json':SOURCE_SHA['video_parts_v1/cycle_review/sources.json']}),...options.sourceSha},expectedProfileId=options.profileId??(['profile_walk_v1','video_guided_walk_v2'].includes(packageId)?packageId:undefined),timing={duration,meshSlots},frameCount=frameEnd-frameStart+1,packagePath=file=>packageId+'/'+file;
    for(const file of ['profile.json','profile_walk.json','provenance.json','checks.json','profile_walk.atlas','profile_walk.png'])if(!SHA_RE.test(sourceSha[packagePath(file)]||''))throw new Error('缺少有效来源 SHA：'+packagePath(file));
    const doc=host.ownerDocument||global.document,root=doc.createElement('section'),style=doc.createElement('style');root.className='rpe';style.textContent=CSS;
    root.innerHTML=`
<div class="rpe-header"><div><div class="rpe-title">视频对照与动作预览</div><div class="rpe-sub" data-ui="sourceInfo"></div><div class="rpe-sub">点「播放」同时看左右画面；可调速度、选四相位或拖动时间轴。仅作视频参考，不是精确拟合或生产成品。</div></div><span class="rpe-status" data-ui="status" role="status" aria-live="polite">来源校验中…</span></div>
<div class="rpe-verdict" data-ui="verdict" role="status" aria-live="polite">正在核对源包验收结论，暂不允许写键或导出。</div><div class="rpe-sub rpe-task-feedback" data-ui="taskFeedback">任务要求从视频进行拆件仍待完成：七件逻辑不变；原静态七件未重拆、未补全，当前纹理不足，帧号与视频约束候选不等于完成拆件。</div>
<div class="rpe-context" data-ui="context">源 profile.characterId=null；仅本任务草稿，不归属当前角色。</div>
<div class="rpe-toolbar"><button type="button" data-ui="play" disabled>播放</button><button type="button" data-ui="reset" disabled>重置播放</button><button type="button" data-speed="0.5" disabled>0.5×</button><button type="button" data-speed="1" aria-pressed="true" disabled>1×</button><label><input data-ui="overlay" type="checkbox" disabled> 骨骼 overlay</label><span class="rpe-spacer"></span><button type="button" data-ui="save" disabled>保存本任务草稿</button><button type="button" data-ui="restore" disabled>恢复本任务草稿</button><button type="button" data-ui="clear" disabled>清除本任务草稿</button><button type="button" data-ui="source" disabled>还原源动作</button></div>
<div class="rpe-phases"><span>四相位</span><button type="button" data-frame="68" disabled>68 · 0%</button><button type="button" data-frame="72" disabled>72 · 25%</button><button type="button" data-frame="76" disabled>76 · 50%</button><button type="button" data-frame="80" disabled>80 · 75%</button><span class="rpe-spacer"></span><span data-ui="clock">0.000 / 0.667 s · 68帧</span></div>
<div class="rpe-workspace"><aside class="rpe-tree"><h3>骨骼树</h3><div class="rpe-list" data-ui="bones"></div><div class="rpe-section"><h3>Slot 列表</h3><div class="rpe-list" data-ui="slots"></div></div></aside><main class="rpe-main"><div class="rpe-comparison"><div class="rpe-stage"><span class="rpe-stage-label">源 PNG · 统一时钟 24fps</span><div class="rpe-source-stage" data-ui="sourceStage"></div></div><div class="rpe-stage"><span class="rpe-stage-label">Spine weighted mesh</span><canvas data-ui="canvas" width="768" height="640" aria-label="Spine runtime 预览"></canvas><div class="rpe-overlay" data-ui="load">正在校验源资源…</div></div></div><div class="rpe-controls"><input data-ui="seek" type="range" min="0" max="0.6666666666666666" step="0.000001" value="0" disabled aria-label="动作时间"><span data-ui="selection">未选择骨骼</span></div><div class="rpe-reference"><div class="rpe-sub">17 张源 PNG · 点击定位；仅作相位参考，不是视频精确拟合 · <span data-ui="referenceStatus">0/17</span></div><div class="rpe-reference-grid" data-ui="references"></div></div></main><aside class="rpe-inspector"><h3>当前关键值</h3><label>相对 setup 的 rotate 偏移（°，±180）<input data-ui="angle" type="number" min="-180" max="180" step="0.1" disabled aria-label="当前骨骼旋转偏移"></label><div class="rpe-sub" data-ui="angleInfo">选择骨骼后编辑</div><button type="button" data-ui="write" disabled>写入当前相位关键帧</button><div class="rpe-status" data-ui="editStatus" role="status" aria-live="polite">未选择骨骼</div><div class="rpe-sub">写键前检查完整 65 样本。首尾成对写入；数值通过不等于视觉验收。</div><div class="rpe-section"><h3>Profile 绑定摘要</h3><pre class="rpe-pre" data-ui="summary">读取中</pre></div><div class="rpe-section"><h3>来源及当前检查</h3><pre class="rpe-pre" data-ui="checks">读取中</pre></div></aside></div>`;
    host.replaceChildren(style,root);
    const q=key=>root.querySelector('[data-ui="'+key+'"]');
    const advanced=doc.createElement('details'),advancedTitle=doc.createElement('summary'),advancedControls=doc.createElement('div'),advancedWorkspace=doc.createElement('div'),evidenceSection=doc.createElement('section'),evidenceTitle=doc.createElement('h3'),evidenceBody=doc.createElement('pre');
    advanced.className='rpe-advanced';advancedTitle.textContent='高级编辑与制作记录';advancedControls.className='rpe-toolbar';advancedWorkspace.className='rpe-advanced-workspace';evidenceSection.className='rpe-evidence';evidenceTitle.textContent='七件视频依据';evidenceBody.className='rpe-pre';evidenceBody.dataset.ui='evidence';evidenceBody.textContent='等待来源包；未提供依据不等于已完成审阅。';
    advanced.append(advancedTitle,q('context'),advancedControls,advancedWorkspace,evidenceSection);
    advancedControls.append(q('overlay').parentElement,q('save'),q('restore'),q('clear'),q('source'));
    advancedWorkspace.append(root.querySelector('.rpe-tree'),root.querySelector('.rpe-inspector'));evidenceSection.append(evidenceTitle,evidenceBody);root.append(advanced);q('angleInfo').before(q('selection'));
    q('seek').max=String(duration);q('clock').textContent='0.000 / '+duration.toFixed(3)+' s · '+frameStart+'帧';
    root.querySelectorAll('.rpe-phases [data-frame]').forEach((button,index)=>{const frame=frameStart+Math.floor((frameEnd-frameStart)*index/4);button.dataset.frame=String(frame);button.textContent=frame+' · '+index*25+'%';});
    root.querySelector('.rpe-stage-label').textContent='源视频 PNG 参考 · 同步 '+fps+' fps';root.querySelector('.rpe-reference .rpe-sub').firstChild.textContent=frameCount+' 张源视频 PNG · 点击定位；仅作相位参考，不是视频精确拟合 · ';q('referenceStatus').textContent='0/'+frameCount;
    q('sourceInfo').textContent='动作数据包：'+packageId+' · '+(packageId==='profile_walk_v1'?'源 walk_v1 设计步态（兼容旧包）':'视频参考候选；实际动作取自本包 profile_walk.json')+' · 12 bones / 7 slots / 4 mesh · 非生产';
    const state={loaded:false,visible:true,destroyed:false,playing:false,speed:1,phase:0,frame:frameStart,selectedBone:null,selectedSlot:null,overlay:false,edited:false,characterId:null,contextSet:false,runtime:null,runtimeSource:null,profile:null,checks:null,provenance:null,manifest:null,assets:{},snapshots:{},references:[],objectUrls:new Set(),rig:null,baseline:null,viewBounds:null,lastTime:null,exportRoot:null,profileId:packageId,evidence:null,runtimeSha:null,profileSha:null,numerical:null};
    let raf=0;
    const status=(message,error=false)=>{q('status').textContent=message;q('status').classList.toggle('rpe-error',error);};
    const editStatus=(message,error=false)=>{q('editStatus').textContent=message;q('editStatus').classList.toggle('rpe-error',error);};
    function updateContext(){q('context').textContent='源 profile.characterId=null；仅本任务草稿，不归属当前角色'+(state.contextSet?' '+String(state.characterId)+'。切换角色已暂停并回到起点，未转移/丢弃任务草稿。':'。')+' 草稿按 taskId / profileId / runtime SHA / profile SHA 隔离。左右预览由同一时钟驱动；自动播放更新源 PNG 与 Spine，手动定位额外请求工作台源视频帧。仅允许 rotate 关键帧编辑，setup / mesh / weights 保持本包源数据。';}
    function pause(){state.playing=false;state.lastTime=null;if(raf)global.cancelAnimationFrame(raf);raf=0;q('play').textContent='播放';}
    function sourceBlocked(){return sourceChecksBlocked(state.checks);}
    function canExport(){return state.loaded&&!state.destroyed&&!sourceBlocked()&&state.numerical?.ok===true;}
    function updateVerdict(){
      const blocked=sourceBlocked(),checks=state.checks;
      q('verdict').classList.toggle('rpe-error',blocked||state.numerical?.ok===false);
      if(blocked){
        const reasons=[];if(['leg_near','leg_far'].some(name=>checks.meshGeometry?.[name]?.flips>0))reasons.push('腿部折叠');if(checks.shoulderAndLegRootGapFree===false)reasons.push('根部露口');if(!reasons.length)reasons.push(checks.videoFitPassed===false?'视频复现未通过':'源数值检查未通过');
        q('verdict').textContent='视频参考候选 · 未通过：'+reasons.join('、')+'，禁止导出';
        q('taskFeedback').textContent='只读预览，禁止写键及导出。源包 '+checks.cycleSampleCount+' 采样：近腿 '+checks.meshGeometry?.leg_near?.flips+' 个 triangle×sample 翻转；最大可见材料点残差 '+(Number.isFinite(checks.visibleTargetFit?.maxResidualPx)?checks.visibleTargetFit.maxResidualPx.toFixed(2)+' px':'未记录')+'。浏览器 65 采样或最新渲染无翻转不能覆盖源包失败。任务要求从视频进行拆件仍待完成：七件逻辑不变，原静态七件未重拆、未补全，原纹理不足；当前仅为视频约束候选。';
      }else q('verdict').textContent=state.numerical?.ok===false?'浏览器数值检查未通过 · 禁止导出':'非生产动作预览 · 来源记录与浏览器检查分别展示，不代表视觉验收';
    }
    function currentKey(){return storageKey(taskId,state.profileId,state.runtimeSha,state.profileSha);}
    function expectedDraft(){return {taskId,profileId:state.profileId,runtimeSha:state.runtimeSha,profileSha:state.profileSha,runtimeSource:state.runtimeSource,duration};}
    async function readBytes(relative,expected){
      if(state.destroyed)throw new Error('模块已卸载');
      const response=await global.fetch(safePath(base,relative),{cache:'no-store',redirect:'error',credentials:'same-origin'});
      if(!response.ok)throw new Error(relative+' HTTP '+response.status);
      const bytes=new Uint8Array(await response.arrayBuffer()),actual=await sha256Hex(bytes),required=sourceSha[relative]??expected;
      if(expected&&sourceSha[relative]&&expected!==sourceSha[relative])throw new Error(relative+' 来源 SHA 清单与记录冲突');
      if(required&&(!SHA_RE.test(required)||actual!==required))throw new Error(relative+' SHA-256 不匹配');
      state.snapshots[relative]=actual;return bytes;
    }
    async function readJson(relative,expected){
      const bytes=await readBytes(relative,expected),value=JSON.parse(text(bytes));
      if(!value||typeof value!=='object'||Array.isArray(value))throw new Error(relative+' JSON 格式无效');
      return {bytes,value};
    }
    async function verifySource(){
      const [profile,runtime,provenance,checks,manifest]=await Promise.all([...['profile.json','profile_walk.json','provenance.json','checks.json'].map(packagePath),'stable_parts_v1/manifest.json'].map(path=>readJson(path)));
      state.profile=profile.value;state.runtimeSource=runtime.value;state.runtime=clone(runtime.value);state.provenance=provenance.value;state.checks=checks.value;state.manifest=manifest.value;
      state.assets.profileBytes=profile.bytes;state.assets.sourceRuntimeBytes=runtime.bytes;state.assets.checksBytes=checks.bytes;state.assets.provenanceBytes=provenance.bytes;state.assets.manifestBytes=manifest.bytes;
      state.profileSha=state.snapshots[packagePath('profile.json')];state.runtimeSha=state.snapshots[packagePath('profile_walk.json')];
      verifyBinding(state.profile,state.runtimeSource,{profileId:expectedProfileId,meshSlots});state.profileId=state.profile.profileId;
      if(state.provenance.characterId!==null||state.manifest.characterId!==null||state.manifest.taskId!==taskId||(state.provenance.taskId!==undefined&&state.provenance.taskId!==taskId)||(state.provenance.packageId!==undefined&&state.provenance.packageId!==packageId))throw new Error('任务或 null 来源身份不符');
      if(packageId==='video_guided_walk_v2'&&(state.provenance.taskId!==taskId||state.provenance.packageId!==packageId))throw new Error('视频候选包身份不符');
      updateVerdict();
      if(sourceRelative(state.provenance.stableManifest?.file)!=='stable_parts_v1/manifest.json'||state.provenance.stableManifest.sha256!==state.snapshots['stable_parts_v1/manifest.json'])throw new Error('provenance 与 manifest SHA 不匹配');
      const parts=state.manifest.parts,stable=state.provenance.stableParts,slotNames=state.profile.bind.slots.map(slot=>slot.name);
      if(!Array.isArray(parts)||parts.length!==7||!Array.isArray(stable)||stable.length!==7||new Set(parts.map(part=>part.id)).size!==7||new Set(stable.map(part=>part.id)).size!==7)throw new Error('需要七件唯一 stableParts');
      await Promise.all(parts.map(async part=>{
        const source=stable.find(item=>item.id===part.id),path='stable_parts_v1/'+part.file;
        if(!slotNames.includes(part.id)||!source||sourceRelative(source.file)!==path||source.expectedSha256!==part.sha256||source.actualSha256!==part.sha256)throw new Error('七件来源关联不符：'+part.id);
        await readBytes(path,part.sha256);
      }));
      const reference=state.provenance.reference;
      if(reference?.fps!==fps||sourceRelative(reference.video)!=='source.mp4'||reference.videoSha256!==state.manifest.sourceVideoSha256)throw new Error('源视频关联不符');
      await readBytes('source.mp4',reference.videoSha256);
      state.assets.atlasText=await readBytes(packagePath('profile_walk.atlas'));
      state.assets.atlasPng=await readBytes(packagePath('profile_walk.png'));
      const sourcesPath=sourceRelative(reference.sources?.file);
      if(sourcesPath!=='video_parts_v1/cycle_review/sources.json'||reference.sources.sha256!==SOURCE_SHA[sourcesPath])throw new Error('源帧清单路径或固定 SHA 不符');
      const sources=await readJson(sourcesPath,reference.sources.sha256);state.sources=sources.value;state.assets.sourcesBytes=sources.bytes;
      if(state.sources.taskId!==taskId||state.sources.characterId!==null||state.sources.fps!==fps||state.sources.sampleCount!==frameCount||state.sources.sourceVideoSha256!==reference.videoSha256||JSON.stringify(state.sources.frameIndices)!==JSON.stringify(Array.from({length:frameCount},(_,i)=>frameStart+i)))throw new Error(frameCount+'帧来源清单不符');
      await loadEvidence();
    }
    async function loadEvidence(){
      const path=packagePath('evidence.json'),record=state.provenance.reference?.evidence??state.provenance.evidence;
      let expected=sourceSha[path];
      if(record?.file){const file=record.file;if(file!=='evidence.json'&&file!==path&&file!=='generated_rig/video_f7e82942/'+path)throw new Error('视频依据不属于当前包');expected=expected??record.sha256;}
      if(!Object.hasOwn(sourceSha,path)&&!record?.file){q('evidence').textContent='本包 '+packageId+' 未提供 evidence.json；七件视频依据尚未提供，不代表视频拟合完成。';return;}
      if(!SHA_RE.test(expected||''))throw new Error('evidence.json 缺少有效 SHA-256');
      if(record?.sha256&&record.sha256!==expected)throw new Error('视频依据 SHA 清单与 provenance 冲突');
      const evidence=await readJson(path,expected),items=verifyEvidence(evidence.value,state.sources,{taskId,packageId,frameStart,frameEnd,slotNames:state.profile.bind.slots.map(slot=>slot.name)});
      state.evidence=evidence.value;state.assets.evidenceBytes=evidence.bytes;
      const display=value=>typeof value==='string'?value:JSON.stringify(value,null,2);
      q('evidence').textContent='数据包：'+packageId+' · evidence.json SHA-256 已校验\n\n'+items.map(item=>'id：'+item.id+'\nframes：'+item.frames.map(entry=>entry.frame).join('、')+'\nvisibleBasis（可见依据）：'+display(item.visibleBasis)+'\nocclusion（遮挡）：'+display(item.occlusion)+'\nlimitations（限制）：'+display(item.limitations)).join('\n\n');
    }
    function imageFromBytes(bytes){
      return new Promise((resolve,reject)=>{
        if(state.destroyed){reject(new Error('模块已卸载'));return;}
        const image=doc.createElement('img'),url=global.URL.createObjectURL(new Blob([bytes],{type:'image/png'}));state.objectUrls.add(url);
        image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('已校验 PNG 解码失败'));image.src=url;
      });
    }
    async function loadReferences(){
      const frames=state.sources.frames;if(!Array.isArray(frames)||frames.length!==frameCount)throw new Error('源帧数量不是'+frameCount);
      const entries=await Promise.all(frames.map(async(entry,index)=>{
        const frame=frameStart+index;
        if(entry.sourceFrame!==frame||entry.sourceFile!=='source_'+String(frame).padStart(3,'0')+'.png'||!SHA_RE.test(entry.sourceFrameSha256))throw new Error('源帧索引不符');
        const path='video_parts_v1/cycle_review/'+entry.sourceFile,bytes=await readBytes(path,entry.sourceFrameSha256),image=await imageFromBytes(bytes);
        if(image.naturalWidth!==864||image.naturalHeight!==480||JSON.stringify(entry.sourceSize)!=='[864,480]')throw new Error('源 PNG 尺寸不符');
        image.alt='源视频 '+frame+' 帧';image.hidden=frame!==frameStart;
        const button=doc.createElement('button'),thumbnail=doc.createElement('img'),label=doc.createElement('small');button.type='button';button.disabled=true;button.dataset.frame=String(frame);button.title='定位源帧 '+frame;button.setAttribute('aria-pressed',String(frame===frameStart));thumbnail.src=image.src;thumbnail.alt='源帧 '+frame;label.textContent=String(frame);button.append(thumbnail,label);button.onclick=()=>setPhase((frame-frameStart)/fps);
        return {frame,image,button};
      }));
      if(state.destroyed)return;
      state.references=entries;for(const entry of entries){q('sourceStage').append(entry.image);q('references').append(entry.button);}q('referenceStatus').textContent=frameCount+'/'+frameCount+' SHA 已校验';
    }
    async function loadAtlas(){
      const atlas=new global.spine.TextureAtlas(text(state.assets.atlasText));
      if(atlas.pages.length!==1||atlas.pages[0].name!=='profile_walk.png'||atlas.regions.length!==7)throw new Error('atlas 不是七件单页源包');
      const image=await imageFromBytes(state.assets.atlasPng),page=atlas.pages[0];
      if(image.naturalWidth!==page.width||image.naturalHeight!==page.height)throw new Error('atlas PNG 尺寸不符');
      page.setTexture(new global.spine.CanvasTexture(image));state.assets.atlas=atlas;
    }
    function checkedRig(runtime){
      if(!validRuntimeEdits(runtime,state.runtimeSource,timing))throw new Error('拒绝非 rotate 变更或非法关键帧');
      const rig=makeRig(global.spine,state.assets.atlas,runtime,timing),result=inspectMeshes(global.spine,rig,state.baseline,timing);
      if(!result.ok)throw new Error('65样本四 mesh 检查失败：'+result.errors.slice(0,3).join('；'));
      return {rig,result};
    }
    function installRig(rig){
      state.rig=rig;state.renderer=new global.spine.SkeletonRenderer(q('canvas').getContext('2d'));state.renderer.triangleRendering=true;state.renderer.debugRendering=false;
      let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
      for(let i=0;i<65;i++){poseRig(global.spine,rig,duration*i/64);const bounds=rig.skeleton.getBoundsRect();minX=Math.min(minX,bounds.x);minY=Math.min(minY,bounds.y);maxX=Math.max(maxX,bounds.x+bounds.width);maxY=Math.max(maxY,bounds.y+bounds.height);}
      if(![minX,minY,maxX,maxY].every(Number.isFinite)||maxX<=minX||maxY<=minY)throw new Error('runtime bounds 无效');
      state.viewBounds={x:minX,y:minY,width:maxX-minX,height:maxY-minY};applyPose();
    }
    function applyPose(){if(state.rig)poseRig(global.spine,state.rig,state.phase);}
    function refreshAngle(){
      const bone=state.selectedBone&&state.rig?state.rig.skeleton.findBone(state.selectedBone):null;
      q('angle').disabled=!state.loaded||!bone||sourceBlocked();q('write').disabled=!state.loaded||!bone||sourceBlocked();
      if(!bone)return;
      const offset=bone.rotation-bone.data.rotation;q('angle').value=offset.toFixed(4);
      q('angleInfo').textContent='setup '+bone.data.rotation.toFixed(2)+'° · 当前局部 '+bone.rotation.toFixed(2)+'°';
    }
    function refreshClock(){
      state.frame=frameStart+Math.min(frameEnd-frameStart,Math.max(0,Math.floor(state.phase*fps+1e-8)));q('clock').textContent=state.phase.toFixed(3)+' / '+duration.toFixed(3)+' s · '+state.frame+'帧';q('seek').value=String(state.phase);
      for(const item of state.references){item.image.hidden=item.frame!==state.frame;item.button.setAttribute('aria-pressed',String(item.frame===state.frame));}
      root.querySelectorAll('.rpe-phases [data-frame]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.frame)===state.frame)));
      refreshAngle();
    }
    function draw(){
      if(!state.visible||!state.rig||!state.viewBounds||state.destroyed)return;
      const canvas=q('canvas'),ctx=canvas.getContext('2d'),bounds=state.viewBounds,scale=Math.min((canvas.width-56)/bounds.width,(canvas.height-56)/bounds.height),tx=canvas.width/2-(bounds.x+bounds.width/2)*scale,ty=canvas.height/2+(bounds.y+bounds.height/2)*scale;
      ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.setTransform(scale,0,0,-scale,tx,ty);state.renderer.draw(state.rig.skeleton);
      if(state.overlay){
        const color=global.getComputedStyle(root).getPropertyValue('--rpe-accent').trim();ctx.save();ctx.strokeStyle=color||'#ba5d3d';ctx.fillStyle=color||'#ba5d3d';ctx.lineWidth=1.3/scale;
        for(const bone of state.rig.skeleton.bones){if(!bone.active)continue;ctx.beginPath();ctx.moveTo(bone.worldX,bone.worldY);ctx.lineTo(bone.worldX+bone.a*bone.data.length,bone.worldY+bone.c*bone.data.length);ctx.stroke();ctx.beginPath();ctx.arc(bone.worldX,bone.worldY,(bone.data.name===state.selectedBone?4:2.5)/scale,0,Math.PI*2);ctx.fill();}ctx.restore();
      }
    }
    function setPhase(value,requestSource=true){
      if(!state.loaded||state.destroyed)return;pause();state.phase=Math.max(0,Math.min(duration,Number(value)||0));applyPose();refreshClock();draw();
      if(requestSource&&typeof onRequestFrame==='function'){try{onRequestFrame(state.frame);}catch(error){status('源帧回调失败：'+(error.message||error),true);}}
    }
    function render(time){
      raf=0;if(!state.playing||!state.visible||state.destroyed)return;
      if(state.lastTime!==null)state.phase=(state.phase+Math.min(.1,Math.max(0,(time-state.lastTime)/1000))*state.speed)%duration;
      state.lastTime=time;applyPose();refreshClock();draw();raf=global.requestAnimationFrame(render);
    }
    function renderTree(){
      q('bones').replaceChildren();q('slots').replaceChildren();
      for(const bone of state.rig.skeleton.bones){
        let depth=0;for(let parent=bone.parent;parent;parent=parent.parent)depth++;
        const button=doc.createElement('button');button.type='button';button.className='rpe-bone';button.style.setProperty('--depth',String(depth));button.textContent=bone.data.name;button.setAttribute('aria-pressed',String(state.selectedBone===bone.data.name));button.onclick=()=>selectBone(bone.data.name);q('bones').append(button);
      }
      for(const slot of state.rig.skeleton.slots){const button=doc.createElement('button');button.type='button';button.textContent=slot.data.name+' → '+slot.data.boneData.name;button.setAttribute('aria-pressed',String(state.selectedSlot===slot.data.name));button.onclick=()=>selectBone(slot.data.boneData.name,slot.data.name);q('slots').append(button);}
    }
    function selectBone(name,slotName=null){
      if(!state.loaded||!state.rig.skeleton.findBone(name))return;pause();state.selectedBone=name;state.selectedSlot=slotName;q('selection').textContent='骨骼：'+name;renderTree();refreshAngle();draw();
    }
    function updateSummary(){q('summary').textContent='profileId: '+state.profileId+'\ncharacterId: null（未绑定角色）\n方向: '+state.profile.sourceDirection+'\n12 bones / 7 slots / 4 mesh\n'+state.profile.bind.slots.map(slot=>slot.name+' → '+slot.bone+' / '+slot.attachment).join('\n')+'\n\n衣袖契约：共用对应 arm 上下骨链，可用 body 作根锚；独立 mesh / UV / 静态 weights，不强制同 UV/同权重。本次不新增袖子或碎片。';}
    function updateChecks(){
      const record={packageId,sourceChecksBlocked:sourceBlocked(),sourceChecksStatus:state.checks.status||null,sourceNumericalChecksPassed:state.checks.numericalChecksPassed,sourceVideoFitPassed:state.checks.videoFitPassed,sourcePrototypeAccepted:state.checks.prototypeAccepted===true,sourceVisualScope:state.checks.visualReview?.scope||state.provenance.visualReview?.scope||null,edited:state.edited,currentAccepted:false,productionApproved:false,numericalSamples:state.numerical?.samples||0,numericalChecksPassed:!sourceBlocked()&&state.numerical?.ok===true,browserNumericalChecksPassed:state.numerical?.ok===true,numericalErrors:state.numerical?.errors||[],visualReview:state.edited?'需重新视觉验收':'仅保留本包来源记录；当前未做视觉验收',wardrobeVerified:false,crossCharacterVerified:false,mobileVerified:false,sourceSnapshots:state.snapshots,sourceChecks:state.checks};q('checks').textContent=JSON.stringify(record,null,2);
      if(state.exportRoot){state.exportRoot.querySelector('[data-export-state]').textContent=sourceBlocked()?'候选未通过 / 禁止导出':state.edited?'编辑后待验收':'源动作';state.exportRoot.querySelector('[data-export]').disabled=!canExport();state.exportRoot.querySelector('[data-export-status]').textContent='数据包：'+packageId+'\n'+(sourceBlocked()?'源包明确未通过；当前渲染检查不能覆盖原始失败，禁止导出。\n':'')+(state.edited?'已编辑，accepted false，需重新视觉验收。':'源动作；prototypeAccepted 仅见 source_checks。')+'\nproduction false · 浏览器65样本检查'+(state.numerical?.ok?'通过':'未通过')+'；源包'+(state.checks.cycleSampleCount??'未记录采样数')+'样本/视频检查'+(sourceBlocked()?'未通过':'未标失败')+'。数值通过不代表视觉/生产验收。\n运行包不是 .spine 源工程。';}
    }
    function replaceRuntime(runtime,checked){
      installRig(checked.rig);state.runtime=clone(runtime);state.edited=JSON.stringify(state.runtime)!==JSON.stringify(state.runtimeSource);state.numerical={ok:checked.result.ok,samples:checked.result.samples,errors:checked.result.errors};applyPose();refreshClock();renderTree();updateChecks();updateVerdict();draw();
    }
    function writeKey(){
      if(!state.loaded||!state.selectedBone)return;pause();
      if(sourceBlocked()){editStatus('源包数值或视频拟合检查未通过，只读预览，禁止写键',true);return;}
      const input=q('angle').value.trim(),value=Number(input);
      if(!input||!Number.isFinite(value)||Math.abs(value)>180){editStatus('角度必须在 -180° 到 +180° 内，不能为空',true);return;}
      try{const candidate=insertRotateKey(state.runtime,state.selectedBone,state.phase,value,timing),checked=checkedRig(candidate);replaceRuntime(candidate,checked);editStatus('已写入当前相位 rotate.value；需重新视觉验收');status('关键帧已写入克隆 runtime；源包未修改');}catch(error){editStatus(error.message||String(error),true);}
    }
    function draft(){return {schemaVersion:1,taskId,profileId:state.profileId,characterId:null,sourceProfileCharacterId:null,runtimeSha:state.runtimeSha,profileSha:state.profileSha,savedAt:Date.now(),edited:state.edited,runtime:clone(state.runtime)};}
    function saveDraft(){if(!state.loaded)return;try{global.localStorage.setItem(currentKey(),JSON.stringify(draft()));editStatus('已保存本任务草稿；characterId=null'+(sourceBlocked()?'；候选未通过，保存不解除只读/导出禁令':''));}catch(error){editStatus('草稿保存失败：'+(error.message||error),true);}}
    function restoreDraft(){
      if(!state.loaded)return;pause();if(sourceBlocked()){editStatus('源包未通过，只读预览，禁止恢复编辑动作',true);return;}
      try{const raw=global.localStorage.getItem(currentKey());if(!raw){editStatus('当前 task key 无草稿');return;}const value=JSON.parse(raw);if(!validDraft(value,expectedDraft()))throw new Error('草稿过期、来源不符或包含禁止变更，拒绝覆盖');const checked=checkedRig(value.runtime);replaceRuntime(value.runtime,checked);editStatus('已恢复本任务草稿；仍未归属任何角色'+(state.edited?'；需重新视觉验收':''));}catch(error){editStatus('恢复失败：'+(error.message||error),true);}
    }
    function clearDraft(){if(!state.loaded)return;try{global.localStorage.removeItem(currentKey());editStatus('仅删除当前 task/profile/源 SHA key；未清除其它任务，未改当前动作');}catch(error){editStatus('清除失败：'+(error.message||error),true);}}
    function sourceAction(){if(!state.loaded)return;pause();try{const rig=makeRig(global.spine,state.assets.atlas,state.runtimeSource,timing),result=inspectMeshes(global.spine,rig,state.baseline,timing);replaceRuntime(state.runtimeSource,{rig,result});setPhase(0);editStatus('已还原源动作；未清除保存的任务草稿'+(sourceBlocked()?'；源包未通过，仍为只读预览，禁止写键与导出':result.ok?'':'；浏览器数值检查未通过，导出仍禁用'),sourceBlocked()||!result.ok);}catch(error){editStatus(error.message||String(error),true);}}
    function installExport(){
      if(!exportHost||typeof exportHost.replaceChildren!=='function')return;
      const exportStyle=doc.createElement('style');exportStyle.textContent=CSS;
      const section=doc.createElement('section');section.className='rpe-export';section.innerHTML='<div class="rpe-export-row"><strong>当前任务运行包</strong><span class="rpe-tag">production false</span><span class="rpe-tag" data-export-state>校验中</span><button type="button" data-export disabled>导出当前任务运行包 ZIP</button></div><div class="rpe-export-status" data-export-status role="status" aria-live="polite">等待来源与数值检查；不是 .spine 源工程。</div>';
      exportHost.replaceChildren(exportStyle,section);state.exportStyle=exportStyle;state.exportRoot=section;section.querySelector('[data-export]').onclick=exportZip;
    }
    async function exportZip(){
      if(!canExport())return;pause();const button=state.exportRoot.querySelector('[data-export]'),output=state.exportRoot.querySelector('[data-export-status]');button.disabled=true;
      try{
        const currentRuntime=state.edited?jsonBytes(state.runtime):state.assets.sourceRuntimeBytes,currentDraft=jsonBytes(draft()),provenance={schemaVersion:1,taskId,packageId,profileId:state.profileId,characterId:null,edited:state.edited,accepted:false,productionApproved:false,visualReview:state.edited?'required_after_edit':'source_record_only',sourceChecksPrototypeAccepted:state.checks.prototypeAccepted===true,sourceSnapshots:clone(state.snapshots),currentRuntimeSha256:await sha256Hex(currentRuntime),taskDraftSha256:await sha256Hex(currentDraft),verification:{profileProvenanceManifestSha256:true,bindMatchesRuntime:true,stableParts:7,sourceFrames:frameCount,sourceVideoSha256:true,evidenceSha256:!!state.assets.evidenceBytes,numericalSamples:65,numericalChecksPassed:state.numerical?.ok===true,triangleRendering:true},generatedAt:new Date().toISOString(),limitations:['运行数据包，不是 .spine 源工程','未重新视觉验收；换装、跨角色、移动端及官方导入未验证','65个离散样本不能证明任意连续姿态无缺陷']};
        const files=[{name:'profile_walk.json',data:currentRuntime},{name:'profile_walk.atlas',data:state.assets.atlasText},{name:'profile_walk.png',data:state.assets.atlasPng},{name:'profile.json',data:state.assets.profileBytes},{name:'source_checks.json',data:state.assets.checksBytes},{name:'task_draft.json',data:currentDraft},{name:'provenance.json',data:jsonBytes(provenance)},{name:'source_provenance.json',data:state.assets.provenanceBytes},{name:'source_manifest.json',data:state.assets.manifestBytes},{name:'source_frames.json',data:state.assets.sourcesBytes}];
        if(state.assets.evidenceBytes)files.push({name:'source_evidence.json',data:state.assets.evidenceBytes});
        const bytes=zipStoreBytes(files);if(state.destroyed)return;
        const url=global.URL.createObjectURL(new Blob([bytes],{type:'application/zip'})),anchor=doc.createElement('a');anchor.href=url;anchor.download='rig-task-'+taskId.replace(/[^a-zA-Z0-9_-]/g,'_')+'.zip';anchor.hidden=true;root.append(anchor);anchor.click();anchor.remove();global.setTimeout(()=>global.URL.revokeObjectURL(url),1000);output.classList.remove('rpe-error');output.textContent='已生成 '+files.length+' 项 stored ZIP（CRC32）\nproduction false · accepted false · characterId null\n包含当前 runtime、原始 atlas/PNG/profile/checks、任务草稿及来源快照；未改源包。';
      }catch(error){output.classList.add('rpe-error');output.textContent='导出失败：'+(error.message||error);}finally{button.disabled=!canExport();}
    }
    function bind(){
      q('play').onclick=()=>{if(!state.loaded||!state.visible)return;if(state.playing){pause();return;}state.playing=true;state.lastTime=null;q('play').textContent='暂停';raf=global.requestAnimationFrame(render);};
      q('reset').onclick=()=>setPhase(0);q('seek').oninput=()=>setPhase(q('seek').value);q('overlay').onchange=()=>{state.overlay=q('overlay').checked;draw();};q('angle').onfocus=pause;q('write').onclick=writeKey;q('save').onclick=saveDraft;q('restore').onclick=restoreDraft;q('clear').onclick=clearDraft;q('source').onclick=sourceAction;
      root.querySelectorAll('.rpe-phases [data-frame]').forEach(button=>button.onclick=()=>setPhase((Number(button.dataset.frame)-frameStart)/fps));
      root.querySelectorAll('[data-speed]').forEach(button=>button.onclick=()=>{state.speed=Number(button.dataset.speed);root.querySelectorAll('[data-speed]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));});
    }
    async function load(){
      try{
        if(!global.spine)throw new Error('请由工作台先加载 /runtime/spine-canvas.js');
        await verifySource();await Promise.all([loadReferences(),loadAtlas()]);if(state.destroyed)return false;
        const rig=makeRig(global.spine,state.assets.atlas,state.runtimeSource,timing),result=inspectMeshes(global.spine,rig,undefined,timing);
        state.baseline=result.signs;state.numerical={ok:result.ok,samples:result.samples,errors:result.errors};installRig(rig);state.loaded=true;
        root.querySelectorAll('button,input').forEach(element=>{element.disabled=false;});q('restore').disabled=sourceBlocked();refreshAngle();renderTree();updateSummary();updateChecks();refreshClock();updateContext();updateVerdict();q('load').hidden=true;status(sourceBlocked()?'来源 SHA 已校验 · 候选未通过，仅供只读预览，禁止写键与导出':'来源 SHA 已校验 · '+frameCount+' PNG · 浏览器65样本检查'+(result.ok?'通过':'未通过：'+result.errors.slice(0,3).join('；')),sourceBlocked()||!result.ok);editStatus(sourceBlocked()?'源包193样本或视频检查未通过；只读预览':result.ok?'可播放左右对照；高级编辑可选':'源动作可预览；浏览器检查未通过，导出禁用',sourceBlocked()||!result.ok);
        if(typeof options.onSourceVerified==='function')options.onSourceVerified({packageId,checks:clone(state.checks),evidence:clone(state.evidence)});
        draw();return true;
      }catch(error){if(state.destroyed)return false;state.loaded=false;q('load').hidden=false;q('load').textContent='加载/来源校验失败：'+(error.message||error);q('load').classList.add('rpe-error');status('模块未就绪',true);root.querySelectorAll('button,input').forEach(element=>{element.disabled=true;});if(state.exportRoot){state.exportRoot.querySelector('[data-export]').disabled=true;state.exportRoot.querySelector('[data-export-status]').textContent=q('load').textContent;}return false;}
    }
    bind();installExport();
    const editor={
      // 只控制 C 区预览。D 区可见性由工作台步骤容器管理，切走 C 不隐藏导出。
      setVisible(value){state.visible=!!value;root.hidden=!state.visible;if(!state.visible)pause();else draw();},
      setContext(context){state.contextSet=true;state.characterId=context&&Object.hasOwn(context,'characterId')?context.characterId:null;pause();if(state.loaded)setPhase(0,false);updateContext();editStatus('角色上下文已切换并暂停；任务级动作未归属当前角色');},
      pause(){pause();if(state.loaded)status('已暂停');},
      destroy(){if(state.destroyed)return;pause();state.destroyed=true;state.loaded=false;state.assets.atlas?.dispose();for(const url of state.objectUrls)global.URL.revokeObjectURL(url);state.objectUrls.clear();style.remove();root.remove();state.exportStyle?.remove();state.exportRoot?.remove();},
      ready:null
    };
    editor.ready=load();return editor;
  }

  return {mount:makeEditor,__test:{clone,insertRotateKey,crc32,zipStoreBytes,storageKey,validDraft,validRuntimeEdits,sha256Fallback,sha256Hex,runtimeBoneTimeline,safePath,sourceChecksBlocked,verifyEvidence,verifyBinding,makeRig,poseRig,inspectMeshes,SOURCE_SHA}};
});
