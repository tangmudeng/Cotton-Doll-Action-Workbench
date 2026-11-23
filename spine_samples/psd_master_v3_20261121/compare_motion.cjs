// Motion-path comparison only. This is not an image-similarity or visual pass test.
const fs=require('fs'),path=require('path'),{load,at}=require('./extract_motion.cjs');
const dir=path.join(__dirname,'video_fit'),current=load(dir,'roundtrip/skin.json'),old=load(path.join(__dirname,'../psd_master_v2_20261121/video_fit'),'roundtrip/skin.json');
const motion=JSON.parse(fs.readFileSync(path.join(__dirname,'motion_reference.json'))),config=JSON.parse(fs.readFileSync(path.join(dir,'provenance.json'))),results={};
for(const n of ['arm_near','arm_far','leg_near','leg_far']){
 const src=motion.map(f=>{const a=f.bones.find(b=>b.name===n+'_upper'),b=f.bones.find(b=>b.name===n+'_target');return[b.x-a.x,b.y-a.y]}),max=Math.max(...src.map(v=>Math.hypot(...v)));
 const row={};for(const [label,r] of [['previous',old],['updated',current]]){
  const setup=r.raw.bones.find(b=>b.name===n+'_upper'),total=r.raw.bones.find(b=>b.name===n+'_upper').length+r.raw.bones.find(b=>b.name===n+'_lower').length;let err=0;const measured=[];
  const scale=label==='updated'?config.chains[n].scale:total*.98/max;
  for(let i=0;i<23;i++){at(r,'video_walk_fit',i/24);const target=r.sk.findBone(n+'_target'),body=r.sk.findBone('torso'),bodySetup=r.raw.bones.find(b=>b.name==='torso');const v=[(target.worldX-setup.x)/scale,(target.worldY-setup.y-(body.worldY-bodySetup.y))/scale];measured.push(v);err+=(v[0]-src[i][0])**2+(v[1]-src[i][1])**2;}
  row[label]={endpointPathRMSESourcePixels:Math.sqrt(err/23),nearFarVerticalRangeSourcePixels:Math.max(...measured.map(p=>p[1]))-Math.min(...measured.map(p=>p[1]))};
 }
 results[n]=row;
}
const report={scope:'end-effector trajectories in normalized source-video coordinates; same nominal PSD root, body bounce removed',reference:'previously accepted reference_cycle rig, not independent motion capture',notVisualAcceptance:true,sourceFrameCount:23,results};
fs.writeFileSync(path.join(dir,'motion_comparison.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
