// Smooth, broad two-bone weights; separate toe orientation and waist/pelvis blend.
const fs=require('fs'),path=require('path'),{load,S}=require('./extract_motion.cjs');
const dir=path.join(__dirname,'video_fit'),file=path.join(dir,'skin.json');const raw=JSON.parse(fs.readFileSync(file)),r=load(dir);r.sk.updateWorldTransform(S.Physics.update);
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'source_manifest.json'))),clamp=x=>Math.max(0,Math.min(1,x)),smooth=x=>{x=clamp(x);return x*x*(3-2*x)};
for(const name of ['arm_near','arm_far','leg_near','leg_far','shorts']){
 const mesh=raw.skins[0].attachments[name][name],box=manifest.parts.find(p=>p.key===name).canvasBox;mesh.vertices=[];
 for(let i=0;i<mesh.uvs.length;i+=2){const x=box[0]+mesh.uvs[i]*(box[2]-box[0]),y=box[1]+mesh.uvs[i+1]*(box[3]-box[1]);let weights;
  if(name==='shorts'){const m=smooth((y-710)/75);weights=[['torso',1-m],['pelvis',m]];}
  else{const a=r.sk.findBone(name+'_upper'),b=r.sk.findBone(name+'_target'),dx=b.worldX-a.worldX,dy=b.worldY-a.worldY,t=clamp(((x-512-a.worldX)*dx+(1024-y-a.worldY)*dy)/(dx*dx+dy*dy));weights=[[name+'_upper',1-t],[name+'_lower',t]];
   if(name.startsWith('leg')){const root=smooth((y-715)/75),foot=clamp((t-.15)/.85),hip=smooth((y-710)/75);weights=[['torso',(1-root)*(1-hip)],['pelvis',(1-root)*hip],[name+'_upper',root*(1-foot)*(1-t)],[name+'_lower',root*(1-foot)*t],[name+'_foot',root*foot]];}
  }
  weights=weights.filter(x=>x[1]>1e-8);mesh.vertices.push(weights.length);
  for(const [n,w] of weights){const b=r.sk.findBone(n),dx=x-512-b.worldX,dy=1024-y-b.worldY,det=b.a*b.d-b.b*b.c;mesh.vertices.push(raw.bones.findIndex(b=>b.name===n),(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,w);}
 }
}
fs.writeFileSync(file,JSON.stringify(raw,null,2));console.log('Bound 18-bone rig: broad limb weights, independent feet, waist-to-pelvis shorts mesh.');
