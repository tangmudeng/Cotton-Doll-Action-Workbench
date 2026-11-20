const fs=require('fs'),vm=require('vm'),assert=require('assert');const O='limited_ik_20261120/',B='pixel_sync_20261120/';
const c=vm.createContext({console,Image:class{},window:{},navigator:{}});
vm.runInContext(fs.readFileSync(O+'runtime/spine-canvas.js','utf8')+';globalThis.S=spine;',c);
const S=c.S,atlas=new S.TextureAtlas(fs.readFileSync(O+'skin.atlas','utf8'));
for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
function load(file){const raw=JSON.parse(fs.readFileSync(file)),data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw);return{raw,data,sk:new S.Skeleton(data)}}
const old=load(B+'skin.json'),fresh=load(O+'skin.json');
function pose(o,t){o.sk.setToSetupPose();o.data.findAnimation('reference_cycle').apply(o.sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);o.sk.updateWorldTransform(S.Physics.update);}
function vertices(o){return o.sk.slots.map(s=>{const a=s.getAttachment(),v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(s,0,v.length,v,0,2);assert(a.triangles.length);assert([...v].every(Number.isFinite));return [...v]})}
let max=0,count=0,minimumAreaRatio=1;const response=[];
const keys=fresh.raw.animations.reference_cycle.slots.head.attachment.slice(0,23);
for(const k of keys){
 const t=(k.time||0)+1e-7;pose(old,t);pose(fresh,t);
 const a=vertices(old),b=vertices(fresh);
 a.forEach((v,i)=>v.forEach((x,j)=>max=Math.max(max,Math.abs(x-b[i][j]))));
 for(const limb of ['arm_near','arm_far','leg_near','leg_far']){
  const amount=limb.startsWith('arm')?5:4;
  for(const [dx,dy] of [[amount,0],[-amount,0],[0,amount],[0,-amount]]){
   pose(fresh,t);
   const target=fresh.sk.findBone(limb+'_target');target.x+=dx;target.y+=dy;fresh.sk.updateWorldTransform(S.Physics.update);
   vertices(fresh);count++;
   const slot=fresh.sk.findSlot(limb),att=slot.getAttachment(),v=new Float32Array(att.worldVerticesLength);
   att.computeWorldVertices(slot,0,v.length,v,0,2);
   const index=fresh.sk.slots.indexOf(slot),base=b[index];
   let movement=0;
   for(let j=0;j<v.length;j+=2)movement=Math.max(movement,Math.hypot(v[j]-base[j],v[j+1]-base[j+1]));
   response.push({attachment:att.name,dx,dy,maxMeshMovementPx:movement});
  }
 }
}
assert(max<.04);
const report={referenceMaxCoordinateDifferencePx:max,checkedFrames:23,axisPerturbations:count,allFinite:true,allMeshesDrawable:true,imagesUnchanged:true,visualAcceptancePending:true,scope:'axis-aligned +/-5px hands, +/-4px feet; no visual pass inferred from finite vertices'};
const crypto=require('crypto');
for(const name of fs.readdirSync(O+'parts')){
 assert(crypto.createHash('sha256').update(fs.readFileSync(O+'parts/'+name)).digest('hex')===crypto.createHash('sha256').update(fs.readFileSync(B+'parts/'+name)).digest('hex'));
}
fs.writeFileSync(O+'validation.json',JSON.stringify(report,null,2));fs.writeFileSync(O+'control_response.json',JSON.stringify(response,null,2));console.log(report);
