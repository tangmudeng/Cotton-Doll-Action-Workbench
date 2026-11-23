const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {load,at,geometry}=require('./extract_motion.cjs'),dir=path.join(__dirname,'video_fit');
const draft=process.argv.includes('--draft'),a=load(dir),b=load(dir,draft?'skin.json':'roundtrip/skin.json'),duration=23/24;
const frames=[],inversions=[];let delta=0,endpoint=0,loop=0;
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const textures=fs.readdirSync(path.join(dir,'parts')).filter(n=>n.endsWith('.png'));
if(textures.length!==7||textures.some(n=>hash(path.join(dir,'parts',n))!==hash(path.join(__dirname,'rig/parts',n))))throw Error('PSD texture changed');
function pose(r,t){at(r,'video_walk_fit',t);return r.sk.drawOrder.map(s=>({name:s.data.name,...geometry(s.getAttachment(),s)}));}
for(let i=0;i<=92;i++){
 const t=i/96,ga=pose(a,t),gb=pose(b,t);
 for(let j=0;j<ga.length;j++){
  const p=ga[j],q=gb[j];
  for(let k=0;k<p.xy.length;k++){if(!Number.isFinite(p.xy[k]+q.xy[k]))throw Error('Nonfinite vertex');delta=Math.max(delta,Math.abs(p.xy[k]-q.xy[k]));}
  for(let k=0;k<p.tri.length;k+=3){const [u,v,w]=p.tri.slice(k,k+3).map(x=>x*2),area=xy=>(xy[v]-xy[u])*(xy[w+1]-xy[u+1])-(xy[v+1]-xy[u+1])*(xy[w]-xy[u]);if(area(p.xy)*area(p.uv)>0)inversions.push({frame:63+t*24,part:p.name,triangle:k/3});}
 }
 for(const n of ['arm_near','arm_far','leg_near','leg_far']){const l=b.sk.findBone(n+'_lower'),e=b.sk.findBone(n+'_target');endpoint=Math.max(endpoint,Math.hypot(l.worldX+l.a*l.data.length-e.worldX,l.worldY+l.c*l.data.length-e.worldY));}
 if(i%4===0&&i<92)frames.push({frame:63+i/4,time:t,parts:gb,bones:b.sk.bones.map(x=>({name:x.data.name,x:x.worldX,y:x.worldY,endX:x.worldX+x.a*x.data.length,endY:x.worldY+x.c*x.data.length,length:x.data.length}))});
}
const first=pose(b,0),last=pose(b,duration+1e-6);for(let j=0;j<first.length;j++)for(let k=0;k<first[j].xy.length;k++)loop=Math.max(loop,Math.abs(first[j].xy[k]-last[j].xy[k]));
const report={technicalPass:!draft&&delta<.25&&endpoint<.25&&inversions.length===0&&loop<.001,roundtripChecked:!draft,samples:93,sourceFrames:23,textures:7,texturesEqualPSDMaster:true,bones:a.raw.bones.length,ik:a.raw.ik.length,maxRoundtripVertexDelta:draft?null:delta,maxIKEndpointError:endpoint,maxLoopVertexDelta:loop,invertedTriangleObservations:inversions.length,inversions,humanAccepted:false,groundContactValidated:false,appearance:'PSD master',motion:'retargeted accepted reference_cycle; not an automatic new-video pipeline'};
fs.writeFileSync(path.join(dir,'walk_geometry.json'),JSON.stringify(frames));fs.writeFileSync(path.join(dir,'technical_audit.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,inversions:report.inversions.slice(0,5)}));if(!draft&&!report.technicalPass)process.exitCode=1;
