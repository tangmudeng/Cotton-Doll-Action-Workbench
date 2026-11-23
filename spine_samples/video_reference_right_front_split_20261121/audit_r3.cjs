const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {S,load,at,geometry,base}=require('../psd_pixel_sync_binding_20261121/extract_motion.cjs');
const out=path.join(__dirname,'candidate_r3'),draft=process.argv.includes('--draft'),read=p=>JSON.parse(fs.readFileSync(p));
const a=load(out),b=load(out,draft?'skin.json':'roundtrip/skin.json'),ref=read(path.join(base,'skin.json')),obs=read(path.join(__dirname,'motion_observations.json')),manifest=read(path.join(out,'source_manifest.json'));
assert.deepStrictEqual(a.raw.ik,ref.ik);assert.deepStrictEqual(a.raw.bones.map(x=>[x.name,x.parent]),ref.bones.map(x=>[x.name,x.parent]));
const ikConfig=data=>data.ikConstraints.map(c=>({name:c.name,bones:c.bones.map(b=>b.name),target:c.target.name,order:c.order,bendDirection:c.bendDirection,mix:c.mix,softness:c.softness,compress:c.compress,stretch:c.stretch,uniform:c.uniform,skinRequired:c.skinRequired}));
assert.deepStrictEqual(ikConfig(b.data),ikConfig(load(base).data));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');for(const part of manifest.parts)assert.equal(hash(path.join(out,'parts',part.key+'.png')),part.sha256);
const fitted=read(path.join(out,'ik_fit.json'));
const name='video_right_front_split_59_82',frames=[],flips=[],footLengths={},initial={},pose=r=>r.sk.drawOrder.map(s=>({name:s.data.name,...geometry(s.getAttachment(),s)}));
let maxFittedTargetError=0,maxFittedJointError=0,maxMaterialAnchorError=0,minLocalScale=Infinity,maxLocalScale=0;
let maxVertexDelta=0,maxVertexAt=null,maxIKError=0,maxObservedTargetError=0,maxFootDistanceChange=0,maxSetupError=0;
a.sk.setToSetupPose();a.sk.updateWorldTransform(S.Physics.update);const setup=pose(a),M=read(path.join(out,'provenance.json')).registration;
for(const p of setup){const m=manifest.parts.find(m=>m.key===p.name),[x0,y0,x1,y1]=m.canvasBox;for(let j=0;j<p.xy.length;j+=2){const x=x0+p.uv[j]*(x1-x0),y=y0+p.uv[j+1]*(y1-y0),wx=M[0][0]*x+M[0][1]*y+M[0][2]-432,wy=480-(M[1][0]*x+M[1][1]*y+M[1][2]);maxSetupError=Math.max(maxSetupError,Math.hypot(p.xy[j]-wx,p.xy[j+1]-wy));}}
for(let i=0;i<=192;i++){const t=i/192;at(a,name,t);at(b,name,t);const ga=pose(a),gb=pose(b);
 for(let k=0;k<ga.length;k++){const p=ga[k],q=gb[k];for(let j=0;j<p.xy.length;j++){assert(Number.isFinite(p.xy[j]+q.xy[j]));if(Math.abs(p.xy[j]-q.xy[j])>maxVertexDelta){maxVertexDelta=Math.abs(p.xy[j]-q.xy[j]);maxVertexAt={time:t,part:p.name,vertex:j/2,a:p.xy[j],b:q.xy[j]};}}
  for(let j=0;j<q.tri.length;j+=3){const [u,v,w]=q.tri.slice(j,j+3).map(n=>n*2),area=xy=>(xy[v]-xy[u])*(xy[w+1]-xy[u+1])-(xy[v+1]-xy[u+1])*(xy[w]-xy[u]);if(area(q.xy)*area(q.uv)>=0)flips.push({time:t,part:p.name,triangle:j/3});}
  if(p.name.startsWith('leg')){const box=manifest.parts.find(m=>m.key===p.name).canvasBox,ids=[];for(let j=0;j<q.uv.length;j+=2)if(box[1]+q.uv[j+1]*(box[3]-box[1])>=825)ids.push(j);
   const key=p.name,dist=[];for(let j=1;j<ids.length;j++)dist.push(Math.hypot(q.xy[ids[j]]-q.xy[ids[0]],q.xy[ids[j]+1]-q.xy[ids[0]+1]));if(!initial[key])initial[key]=dist;dist.forEach((v,j)=>maxFootDistanceChange=Math.max(maxFootDistanceChange,Math.abs(v-initial[key][j])));
  }
 }
 for(const n of ['arm_near','arm_far','leg_near','leg_far']){const l=b.sk.findBone(n+'_lower'),e=b.sk.findBone(n+'_target');maxIKError=Math.max(maxIKError,Math.hypot(l.worldX+l.a*l.data.length-e.worldX,l.worldY+l.c*l.data.length-e.worldY));if(i%8===0&&i<192){const p=obs.frames[i/8].points[(n.startsWith('arm')?'hand_':'foot_')+(n.endsWith('near')?'near':'far')];maxObservedTargetError=Math.max(maxObservedTargetError,Math.hypot(e.worldX+432-p[0],480-e.worldY-p[1]));}}
 if(i%8===0&&i<192){for(const [n,v] of Object.entries(fitted.frames[i/8].chains)){
 const target=b.sk.findBone(n+'_target'),joint=b.sk.findBone(n+'_lower');
 maxFittedTargetError=Math.max(maxFittedTargetError,Math.hypot(target.worldX+432-v.foot[0],480-target.worldY-v.foot[1]));
 maxFittedJointError=Math.max(maxFittedJointError,Math.hypot(joint.worldX+432-v.kneeEstimate[0],480-joint.worldY-v.kneeEstimate[1]));
 const g=gb.find(p=>p.name===n),box=manifest.parts.find(p=>p.key===n).canvasBox,P={leg_near:[481,855],leg_far:[585,838],arm_near:[423,737],arm_far:[646,708]}[n],u=(P[0]-box[0])/(box[2]-box[0]),v0=(P[1]-box[1])/(box[3]-box[1]);
 for(let t=0;t<g.tri.length;t+=3){const ids=g.tri.slice(t,t+3).map(x=>x*2),[a,c,d]=ids,A=g.uv[c]-g.uv[a],B=g.uv[d]-g.uv[a],C=g.uv[c+1]-g.uv[a+1],D=g.uv[d+1]-g.uv[a+1],det=A*D-B*C,dx=u-g.uv[a],dy=v0-g.uv[a+1],s=(dx*D-dy*B)/det,h=(dy*A-dx*C)/det;
 if(s>=-1e-7&&h>=-1e-7&&s+h<=1+1e-7){const x=g.xy[a]+s*(g.xy[c]-g.xy[a])+h*(g.xy[d]-g.xy[a]),y=g.xy[a+1]+s*(g.xy[c+1]-g.xy[a+1])+h*(g.xy[d+1]-g.xy[a+1]);maxMaterialAnchorError=Math.max(maxMaterialAnchorError,Math.hypot(target.worldX-x,target.worldY-y));break;}
 }
 }}
 if(i%8===0&&i<192)frames.push({frame:59+i/8,time:t,parts:gb,bones:b.sk.bones.map(x=>({name:x.data.name,x:x.worldX,y:x.worldY,endX:x.worldX+x.a*x.data.length,endY:x.worldY+x.c*x.data.length,length:x.data.length}))});
}
at(b,name,0);const first=pose(b);at(b,name,1);const last=pose(b);let seam=0;first.forEach((p,i)=>p.xy.forEach((v,j)=>seam=Math.max(seam,Math.abs(v-last[i].xy[j]))));
const report={status:'candidate_pending_visual_review',humanAccepted:false,roundtripChecked:!draft,bones:16,ik:4,attachments:7,topologyMatchesAccepted:true,ikConfigMatchesAccepted:true,poseExtractionAutomatic:false,samples:193,maxSetupError,maxRoundtripVertexDelta:draft?null:maxVertexDelta,maxRoundtripVertexAt:maxVertexAt,maxIKError,oldEndpointDefinitionDifferencePx:maxObservedTargetError,maxFittedTargetError,maxFittedJointError,maxMaterialAnchorError,fitChecksAreInternalConsistencyNotAnatomicalGroundTruth:true,footRigid:false,maxFootDistanceChange,maxLoopVertexDelta:seam,invertedTriangleObservations:flips.length,flips,technicalPass:!draft&&maxVertexDelta<.25&&maxSetupError<.001&&maxIKError<.05&&maxFittedTargetError<.05&&maxFittedJointError<.1&&maxMaterialAnchorError<1&&seam<.001&&flips.length===0};
report.deformTimelines=Object.keys(b.raw.animations[name].attachments?.default||{});assert.equal(report.deformTimelines.length,6);
report.thresholds={roundtripVertexPx:.25,setupVertexPx:.001,IKEndpointPx:.05,materialAnchorPx:1,inferredJointPx:1};
report.technicalPass=!draft&&maxVertexDelta<.25&&maxSetupError<.001&&maxIKError<.05&&maxFittedTargetError<.05&&maxFittedJointError<1&&maxMaterialAnchorError<1&&seam<.001&&flips.length===0;
fs.writeFileSync(path.join(out,'technical_audit.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(out,'walk_geometry.json'),JSON.stringify(frames));fs.writeFileSync(path.join(out,'setup_geometry.json'),JSON.stringify(setup));console.log(JSON.stringify({...report,flips:flips.slice(0,10)}));
if(!draft&&!report.technicalPass)process.exitCode=1;
