const fs=require('fs'),vm=require('vm'),assert=require('assert');
const B='pixel_sync_20261120/',O='limited_ik_20261120/';
const c=vm.createContext({console,Image:class{},window:{},navigator:{}});
vm.runInContext(fs.readFileSync(B+'runtime/spine-canvas.js','utf8')+';globalThis.S=spine;',c);
const S=c.S,atlas=new S.TextureAtlas(fs.readFileSync(B+'skin.atlas','utf8'));
for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
const raw=JSON.parse(fs.readFileSync(B+'skin.json')), factors=JSON.parse(fs.readFileSync(O+'seam_factors.json'));
const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data),anim=data.findAnimation('reference_cycle');
let max=0;
for(const part of ['arm_far','arm_near','leg_far','leg_near']){
 for(const [name,a] of Object.entries(raw.skins[0].attachments[part])){
  const key=raw.animations.reference_cycle.slots[part].attachment.find(k=>k.name===name);
  sk.setToSetupPose();anim.apply(sk,0,(key.time||0)+1e-7,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);sk.updateWorldTransform(S.Physics.update);
  const slot=sk.findSlot(part),at=slot.getAttachment(),world=new Float32Array(at.worldVerticesLength);
  at.computeWorldVertices(slot,0,world.length,world,0,2);
  const anchor=raw.bones.findIndex(b=>b.name===(part.startsWith('arm')?'torso':'pelvis'));
  const out=[];let k=0,index=0;
  while(k<a.vertices.length){
   const n=a.vertices[k++],w=factors[name][index],weights=[];
   for(let j=0;j<n;j++){weights.push([a.vertices[k],a.vertices[k+3]*w]);k+=4;}
   weights.push([anchor,1-w]);const active=weights.filter(x=>x[1]>1e-8);
   const X=world[index*2],Y=world[index*2+1];out.push(active.length);
   for(const [bone,weight] of active){
    const b=sk.bones[bone],dx=X-b.worldX,dy=Y-b.worldY,det=b.a*b.d-b.b*b.c;
    out.push(bone,(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,weight);
   }
   index++;
  }
  a.vertices=out;
 }
}
raw.skeleton.images='./parts/';
fs.writeFileSync(O+'import.json',JSON.stringify(raw));
console.log('Built seam-anchored candidate; all original image pixels preserved.');
