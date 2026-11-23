// Preserve broad plush-leg cross sections with knee translation controls.
// The two real IK chains still determine the knee and ankle trajectories.
const fs=require('fs'),path=require('path');const {load}=require('./extract_motion.cjs');
const dir=path.join(__dirname,'video_fit'),file=path.join(dir,'skin.json');let raw=JSON.parse(fs.readFileSync(file));
for(const name of ['leg_near','leg_far'])if(!raw.bones.some(b=>b.name===name+'_volume'))raw.bones.push({name:name+'_volume',parent:name+'_lower',inherit:'onlyTranslation'});
fs.writeFileSync(file,JSON.stringify(raw,null,2));const r=load(dir);r.sk.updateWorldTransform(require('./extract_motion.cjs').S.Physics.update);
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'source_manifest.json')));
const smooth=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x)};
for(const name of ['leg_near','leg_far']){
 const mesh=raw.skins[0].attachments[name][name],box=manifest.parts.find(p=>p.key===name).canvasBox;
 const [start,knee,end]=name==='leg_near'?[764,803,842]:[751,787,818];mesh.vertices=[];
 for(let i=0;i<mesh.uvs.length;i+=2){const x=box[0]+mesh.uvs[i]*(box[2]-box[0]),y=box[1]+mesh.uvs[i+1]*(box[3]-box[1]);
  const q=smooth((y-start)/(knee-start)),f=smooth((y-knee)/(end-knee));
  const weights=[['pelvis',1-q],[name+'_volume',q*(1-f)],[name+'_foot',f]].filter(x=>x[1]>1e-8);
  mesh.vertices.push(weights.length);for(const [n,w] of weights){const b=r.sk.findBone(n),dx=x-512-b.worldX,dy=1024-y-b.worldY,det=b.a*b.d-b.b*b.c;mesh.vertices.push(raw.bones.findIndex(b=>b.name===n),(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,w);}
 }
}
fs.writeFileSync(file,JSON.stringify(raw,null,2));console.log('Added two IK-driven knee volume controls; PSD pixels unchanged.');
const pfile=path.join(dir,'provenance.json'),p=JSON.parse(fs.readFileSync(pfile));p.volumeControls={bones:2,drivenBy:'IK solved knee origins',purpose:'preserve plush leg cross sections; pelvis-pinned roots and upright feet',additionalTextures:0};fs.writeFileSync(pfile,JSON.stringify(p,null,2));
