const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {S,load,at,geometry,base}=require('../psd_pixel_sync_binding_20261121/extract_motion.cjs');
const out=path.join(__dirname,process.env.CANDIDATE_DIR||'candidate'),draft=process.argv.includes('--draft'),read=p=>JSON.parse(fs.readFileSync(p));
const a=load(out),b=load(out,draft?'skin.json':'roundtrip/skin.json'),ref=read(path.join(base,'skin.json')),obs=read(path.join(__dirname,'motion_observations.json')),manifest=read(path.join(out,'source_manifest.json'));
assert.deepStrictEqual(a.raw.ik,ref.ik);assert.deepStrictEqual(a.raw.bones.map(x=>[x.name,x.parent]),ref.bones.map(x=>[x.name,x.parent]));
const ikConfig=data=>data.ikConstraints.map(c=>({name:c.name,bones:c.bones.map(b=>b.name),target:c.target.name,order:c.order,bendDirection:c.bendDirection,mix:c.mix,softness:c.softness,compress:c.compress,stretch:c.stretch,uniform:c.uniform,skinRequired:c.skinRequired}));
assert.deepStrictEqual(ikConfig(b.data),ikConfig(load(base).data));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');for(const part of manifest.parts)assert.equal(hash(path.join(out,'parts',part.key+'.png')),part.sha256);
const name='video_right_front_split_59_82',frames=[],flips=[],footLengths={},initial={},pose=r=>r.sk.drawOrder.map(s=>({name:s.data.name,...geometry(s.getAttachment(),s)}));
let maxVertexDelta=0,maxIKError=0,maxObservedTargetError=0,maxFootDistanceChange=0,maxSetupError=0;
a.sk.setToSetupPose();a.sk.updateWorldTransform(S.Physics.update);const setup=pose(a),M=read(path.join(out,'provenance.json')).registration;
for(const p of setup){const m=manifest.parts.find(m=>m.key===p.name),[x0,y0,x1,y1]=m.canvasBox;for(let j=0;j<p.xy.length;j+=2){const x=x0+p.uv[j]*(x1-x0),y=y0+p.uv[j+1]*(y1-y0),wx=M[0][0]*x+M[0][1]*y+M[0][2]-432,wy=480-(M[1][0]*x+M[1][1]*y+M[1][2]);maxSetupError=Math.max(maxSetupError,Math.hypot(p.xy[j]-wx,p.xy[j+1]-wy));}}
for(let i=0;i<=96;i++){const t=i/96;at(a,name,t);at(b,name,t);const ga=pose(a),gb=pose(b);
 for(let k=0;k<ga.length;k++){const p=ga[k],q=gb[k];for(let j=0;j<p.xy.length;j++){assert(Number.isFinite(p.xy[j]+q.xy[j]));maxVertexDelta=Math.max(maxVertexDelta,Math.abs(p.xy[j]-q.xy[j]));}
  for(let j=0;j<q.tri.length;j+=3){const [u,v,w]=q.tri.slice(j,j+3).map(n=>n*2),area=xy=>(xy[v]-xy[u])*(xy[w+1]-xy[u+1])-(xy[v+1]-xy[u+1])*(xy[w]-xy[u]);if(area(q.xy)*area(q.uv)>0)flips.push({time:t,part:p.name,triangle:j/3});}
  if(p.name.startsWith('leg')){const box=manifest.parts.find(m=>m.key===p.name).canvasBox,ids=[];for(let j=0;j<q.uv.length;j+=2)if(box[1]+q.uv[j+1]*(box[3]-box[1])>=825)ids.push(j);
   const key=p.name,dist=[];for(let j=1;j<ids.length;j++)dist.push(Math.hypot(q.xy[ids[j]]-q.xy[ids[0]],q.xy[ids[j]+1]-q.xy[ids[0]+1]));if(!initial[key])initial[key]=dist;dist.forEach((v,j)=>maxFootDistanceChange=Math.max(maxFootDistanceChange,Math.abs(v-initial[key][j])));
  }
 }
 for(const n of ['arm_near','arm_far','leg_near','leg_far']){const l=b.sk.findBone(n+'_lower'),e=b.sk.findBone(n+'_target');maxIKError=Math.max(maxIKError,Math.hypot(l.worldX+l.a*l.data.length-e.worldX,l.worldY+l.c*l.data.length-e.worldY));if(i%4===0&&i<96){const p=obs.frames[i/4].points[(n.startsWith('arm')?'hand_':'foot_')+(n.endsWith('near')?'near':'far')];maxObservedTargetError=Math.max(maxObservedTargetError,Math.hypot(e.worldX+432-p[0],480-e.worldY-p[1]));}}
 if(i%4===0&&i<96)frames.push({frame:59+i/4,time:t,parts:gb,bones:b.sk.bones.map(x=>({name:x.data.name,x:x.worldX,y:x.worldY,endX:x.worldX+x.a*x.data.length,endY:x.worldY+x.c*x.data.length,length:x.data.length}))});
}
at(b,name,0);const first=pose(b);at(b,name,1);const last=pose(b);let seam=0;first.forEach((p,i)=>p.xy.forEach((v,j)=>seam=Math.max(seam,Math.abs(v-last[i].xy[j]))));
const report={status:'candidate_pending_visual_review',humanAccepted:false,roundtripChecked:!draft,bones:16,ik:4,attachments:7,topologyMatchesAccepted:true,ikConfigMatchesAccepted:true,poseExtractionAutomatic:false,samples:97,maxSetupError,maxRoundtripVertexDelta:draft?null:maxVertexDelta,maxIKError,maxObservedTargetError,maxFootDistanceChange,maxLoopVertexDelta:seam,invertedTriangleObservations:flips.length,flips,technicalPass:!draft&&maxVertexDelta<.25&&maxSetupError<.001&&maxIKError<.05&&maxFootDistanceChange<.05&&seam<.001&&flips.length===0};
fs.writeFileSync(path.join(out,'technical_audit.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(out,'walk_geometry.json'),JSON.stringify(frames));fs.writeFileSync(path.join(out,'setup_geometry.json'),JSON.stringify(setup));console.log(JSON.stringify({...report,flips:flips.slice(0,10)}));
if(!draft&&!report.technicalPass)process.exitCode=1;
