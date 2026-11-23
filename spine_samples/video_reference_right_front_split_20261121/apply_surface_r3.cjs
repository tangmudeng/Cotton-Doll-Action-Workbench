const fs=require('fs'),path=require('path');
const {S,load,at,geometry}=require('../psd_pixel_sync_binding_20261121/extract_motion.cjs');
const out=path.join(__dirname,'candidate_r3'),name='video_right_front_split_59_82';
// Strip previous deform tracks before runtime construction, so reruns are idempotent.
const clean=JSON.parse(fs.readFileSync(path.join(out,'skin.json')));delete clean.animations[name].attachments;delete clean.animations[name].deform;
fs.writeFileSync(path.join(out,'skin.json'),JSON.stringify(clean,null,2));
const r=load(out),fit=JSON.parse(fs.readFileSync(path.join(out,'surface_fit.json'))),anim=r.raw.animations[name];
delete anim.deform;anim.attachments={default:{}};
for(const n of Object.keys(fit.frames[0].parts))anim.attachments.default[n]={[n]:{deform:[]}};
let maxCorrection=0;
for(const row of fit.frames){at(r,name,row.time);for(const [n,points] of Object.entries(row.parts)){
 const slot=r.sk.findSlot(n),g=geometry(slot.getAttachment(),slot),src=r.raw.skins[0].attachments[n][n].vertices,offsets=[];let cur=0;
 for(let i=0;i<points.length;i++){const [sx,sy]=points[i],blend=row.blend?.[n]?.[i]??1,dx=(sx-432-g.xy[2*i])*blend,dy=(480-sy-g.xy[2*i+1])*blend;maxCorrection=Math.max(maxCorrection,Math.hypot(dx,dy));const count=src[cur++];
  for(let j=0;j<count;j++){const bone=r.sk.bones[src[cur]],det=bone.a*bone.d-bone.b*bone.c;offsets.push((dx*bone.d-dy*bone.b)/det,(dy*bone.a-dx*bone.c)/det);cur+=4;}
 }
 anim.attachments.default[n][n].deform.push({time:row.time,vertices:offsets});
}}
for(const slots of Object.values(anim.attachments.default))for(const attachment of Object.values(slots)){const keys=attachment.deform;keys.push({...keys[0],time:1});}
fs.writeFileSync(path.join(out,'skin.json'),JSON.stringify(r.raw,null,2));
const file=path.join(out,'provenance.json'),p=JSON.parse(fs.readFileSync(file));Object.assign(p,{revision:'r2',surfaceDeform:true,surfaceFit:'surface_fit.json',surfaceMethod:fit.method,maximumSurfaceCorrectionPx:maxCorrection,footRegion:'Fixed PSD texture warped using source contour cages; rigid-foot invariance from r1 no longer applies',humanAccepted:false});fs.writeFileSync(file,JSON.stringify(p,null,2));console.log({maxCorrection});
