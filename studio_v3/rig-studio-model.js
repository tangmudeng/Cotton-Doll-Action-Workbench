(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.RigStudioModel=api;})(globalThis,()=>{
  'use strict';
  const IDS=['head','body','shorts','arm_near','arm_far','leg_near','leg_far'];
  const ORDER=['leg_far','leg_near','body','shorts','arm_far','arm_near','head'];
  const clone=x=>JSON.parse(JSON.stringify(x));
  const finite=x=>typeof x==='number'&&Number.isFinite(x);
  const point=p=>Array.isArray(p)&&p.length===2&&p.every(finite);
  function pose(keys,t){
    if(!keys.length)return {x:0,y:0,angle:0};
    let a=keys[0],b=keys[keys.length-1];
    if(t<=a.time)return {...a};if(t>=b.time)return {...b};
    for(let i=1;i<keys.length;i++)if(keys[i].time>=t){a=keys[i-1];b=keys[i];break;}
    const u=a.interpolation==='stepped'?0:(t-a.time)/(b.time-a.time);
    return {x:a.x+(b.x-a.x)*u,y:a.y+(b.y-a.y)*u,angle:a.angle+(b.angle-a.angle)*u,...(a.bend!==undefined||b.bend!==undefined?{bend:(a.bend||0)+((b.bend||0)-(a.bend||0))*u}:{})};
  }
  function putKey(keys,key,duration){
    if(![key.time,key.x,key.y,key.angle,duration].every(finite)||duration<=0||key.time<0||key.time>duration||Math.abs(key.angle)>180||(key.bend!==undefined&&(!finite(key.bend)||Math.abs(key.bend)>60)))throw Error('关键帧数值无效');
    const result=keys.filter(k=>Math.abs(k.time-key.time)>1e-6).map(clone);result.push(clone(key));
    if(key.time>0&&key.time<duration&&!keys.length){result.push({time:0,x:0,y:0,angle:0,interpolation:'linear'},{time:duration,x:0,y:0,angle:0,interpolation:'linear'});}
    if(key.time===0||Math.abs(key.time-duration)<1e-6){const other=key.time===0?duration:0;const i=result.findIndex(k=>Math.abs(k.time-other)<1e-6);if(i>=0)result.splice(i,1);result.push({...key,time:other});}
    return result.sort((a,b)=>a.time-b.time);
  }
  function cropBounds(points){
    if(points.length<3||!points.every(point))throw Error('至少需要三个有效轮廓点');
    const area=Math.abs(points.reduce((v,p,i)=>{const n=points[(i+1)%points.length];return v+p[0]*n[1]-n[0]*p[1];},0))/2;
    if(area<4)throw Error('轮廓面积过小');
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);return [Math.floor(Math.min(...xs)),Math.floor(Math.min(...ys)),Math.ceil(Math.max(...xs)),Math.ceil(Math.max(...ys))];
  }
  function validate(p,expected){
    p=clone(p);
    if(!p||p.schema!=='walulu-video-rig-draft/1'||p.productionApproved!==false||p.source?.videoSha!==expected.videoSha||p.source?.imageSha!==expected.imageSha||p.source?.taskId!==expected.taskId||p.source?.characterId!==null||p.duration!==((expected.clipEnd??84)-(expected.clipStart??68))/(expected.fps??24)||p.fps!==(expected.fps??24)||['clipStart','clipEnd','fps','frameCount'].some(k=>p.source[k]!==expected[k]))throw Error('工程类型、视频来源或时间范围不符');
    if(!Array.isArray(p.parts)||p.parts.length!==7||new Set(p.parts.map(x=>x.id)).size!==7)throw Error('工程必须保留七个逻辑件');
    for(const part of p.parts){
      if(!IDS.includes(part.id)||typeof part.name!=='string'||part.name.length>60||!point(part.pivot)||!part.pivot.every(v=>v>=0&&v<=768)||!Array.isArray(part.bbox)||part.bbox.length!==4||!part.bbox.every(v=>Number.isInteger(v)&&v>=0&&v<=768)||part.bbox[2]<=part.bbox[0]||part.bbox[3]<=part.bbox[1]||!finite(part.order)||typeof part.visible!=='boolean')throw Error('部件数据无效');
      if(part.texture!=='legacy'&&!(typeof part.texture==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(part.texture)&&part.texture.length<3000000))throw Error('仅允许包内裁片或 PNG 数据');
      if(!Array.isArray(part.keys)||part.keys.length>1000||!Array.isArray(part.evidence)||part.evidence.length>100||!Array.isArray(part.polygon)||part.polygon.length>1000||!part.polygon.every(p=>point(p)&&p.every(v=>v>=0&&v<=768)))throw Error('工程数据超出范围');
      if(part.parent!==undefined&&part.parent!==null&&(!IDS.includes(part.parent)||part.parent===part.id))throw Error('父骨骼无效');
      if(part.joint!==undefined&&(!point(part.joint)||!part.joint.every(v=>v>=0&&v<=768)||!point(part.tip)||!part.tip.every(v=>v>=0&&v<=768)||Math.hypot(part.joint[0]-part.pivot[0],part.joint[1]-part.pivot[1])<2))throw Error('关节坐标无效');
      if(part.rootBand!==undefined&&(!part.joint||!part.parent||!point(part.rootBand)||part.rootBand[0]<-100||part.rootBand[1]>100||part.rootBand[1]-part.rootBand[0]<10))throw Error('根部权重区间无效');
      if(part.blend!==undefined&&(!finite(part.blend)||part.blend<10||part.blend>60))throw Error('关节权重范围无效');
      let prev=-1;
      for(const k of part.keys){if(![k.time,k.x,k.y,k.angle].every(finite)||k.time<0||k.time>p.duration||k.time<=prev||Math.abs(k.x)>768||Math.abs(k.y)>768||Math.abs(k.angle)>180||(k.bend!==undefined&&(!finite(k.bend)||Math.abs(k.bend)>60))||!['linear','stepped'].includes(k.interpolation))throw Error('动作关键帧无效');prev=k.time;}
      if(part.keys.length){const a=part.keys[0],b=part.keys[part.keys.length-1];if(a.time!==0||Math.abs(b.time-p.duration)>1e-6||['x','y','angle','bend'].some(k=>(a[k]||0)!==(b[k]||0)))throw Error('循环首尾关键帧必须匹配');}
      for(const e of part.evidence){if(expected.frameCount&&!e.origin)e.origin='review_candidate';if(e.origin!==undefined&&!['review_candidate','manual_review'].includes(e.origin))throw Error('观察来源无效');if(!Number.isInteger(e.frame)||e.frame<(expected.frameCount?0:68)||e.frame>=(expected.frameCount??85)||!['visible','occluded','uncertain'].includes(e.visibility)||typeof e.note!=='string'||e.note.length>1000||!Array.isArray(e.points)||e.points.length>1000||!e.points.every(p=>point(p)&&p[0]>=0&&p[0]<=864&&p[1]>=0&&p[1]<=480))throw Error('视频依据无效');}
    }
    for(const part of p.parts){const seen=new Set();let a=part;while(a){if(seen.has(a.id))throw Error('骨骼层级存在循环');seen.add(a.id);a=p.parts.find(x=>x.id===a.parent);}}
    return clone(p);
  }
  // Source-space affine matrices: rest pose is identity for every parent/child.
  const identity=()=>[1,0,0,1,0,0];
  function apply(m,p){return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]];}
  function multiply(a,b){return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]];}
  function matrices(parts,t,active=true){const result=new Map(),visiting=new Set();function visit(p){if(result.has(p.id))return result.get(p.id);if(visiting.has(p.id))throw Error('骨骼层级存在循环');visiting.add(p.id);const a=active?pose(p.keys,t):{x:0,y:0,angle:0},r=a.angle*Math.PI/180,c=Math.cos(r),s=Math.sin(r),[x,y]=p.pivot;const local=[c,s,-s,c,x+a.x-c*x+s*y,y+a.y-s*x-c*y],parent=parts.find(x=>x.id===p.parent);const world=multiply(parent?visit(parent):identity(),local);result.set(p.id,world);visiting.delete(p.id);return world;}parts.forEach(visit);return result;}
  function deform(p,xy,bend=0){if(!p.joint||!bend)return [...xy];const j=p.joint,v=[j[0]-p.pivot[0],j[1]-p.pivot[1]],len=Math.hypot(...v),d=((xy[0]-j[0])*v[0]+(xy[1]-j[1])*v[1])/len;
    const u=Math.max(0,Math.min(1,(d+(p.blend||28))/(2*(p.blend||28)))),w=u*u*(3-2*u),r=bend*Math.PI/180,c=Math.cos(r),s=Math.sin(r),x=xy[0]-j[0],y=xy[1]-j[1];return [xy[0]+w*(j[0]+c*x-s*y-xy[0]),xy[1]+w*(j[1]+s*x+c*y-xy[1])];}
  function vertex(p,xy,a){const d=deform(p,xy,a.bend||0);if(!p.rootBand)return d;const v=[p.joint[0]-p.pivot[0],p.joint[1]-p.pivot[1]],s=((xy[0]-p.pivot[0])*v[0]+(xy[1]-p.pivot[1])*v[1])/Math.hypot(...v),u=Math.max(0,Math.min(1,(s-p.rootBand[0])/(p.rootBand[1]-p.rootBand[0]))),w=u*u*(3-2*u),r=-a.angle*Math.PI/180,c=Math.cos(r),sn=Math.sin(r),x=xy[0]-p.pivot[0]-a.x,y=xy[1]-p.pivot[1]-a.y,b=[p.pivot[0]+c*x-sn*y,p.pivot[1]+sn*x+c*y];return [w*d[0]+(1-w)*b[0],w*d[1]+(1-w)*b[1]];}
  return {IDS,ORDER,clone,pose,putKey,cropBounds,validate,apply,multiply,matrices,deform,vertex};
});
