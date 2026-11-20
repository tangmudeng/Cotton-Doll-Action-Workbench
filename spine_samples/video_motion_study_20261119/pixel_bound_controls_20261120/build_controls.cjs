const fs=require('fs'),vm=require('vm');const c={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};vm.createContext(c);vm.runInContext(fs.readFileSync('runtime/spine-canvas.js','utf8')+';globalThis.s=spine;',c);const S=c.s,atlas=new S.TextureAtlas(fs.readFileSync('skin.atlas','utf8'));for(const p of atlas.pages)p.setTexture({getImage:()=>({width:2048,height:2048}),setFilters(){},setWraps(){}});
let raw=JSON.parse(fs.readFileSync('baseline.json'));raw.bones.push({name:'head_control',parent:'torso',length:60,rotation:180});
const mapping={head:'head_control',torso:'torso',shorts:'pelvis',arm_far:'arm_far_upper',arm_near:'arm_near_upper',leg_far:'leg_far_upper',leg_near:'leg_near_upper'};
const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data),anim=data.findAnimation('reference_cycle');
for(const slot of raw.slots)slot.bone=mapping[slot.name];
for(const slot of ['head','torso','shorts']){
 const boneName=mapping[slot],boneIndex=raw.bones.findIndex(b=>b.name===boneName);
 const keys=raw.animations.reference_cycle.slots[slot].attachment;
 for(const [name,a] of Object.entries(raw.skins[0].attachments[slot])){
  const key=keys.find(k=>k.name===name),t=(key.time||0)+.000001;
  sk.setToSetupPose();anim.apply(sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);sk.updateWorldTransform(S.Physics.update);
  const bone=sk.findBone(boneName),v=a.vertices;let i=0;
  while(i<v.length){if(v[i]!==1||v[i+1]!==0)throw Error('Unexpected baseline binding');const x=v[i+2]-bone.worldX,y=v[i+3]-bone.worldY,det=bone.a*bone.d-bone.b*bone.c;v[i+1]=boneIndex;v[i+2]=(x*bone.d-y*bone.b)/det;v[i+3]=(y*bone.a-x*bone.c)/det;i+=5;}
 }
}
// Diagnostic clip holds one source pose and all attachments fixed, then perturbs one controller.
const poseTime=(raw.animations.reference_cycle.slots.head.attachment[7].time||0)+.000001;
function sampledHold(){
 sk.setToSetupPose();anim.apply(sk,0,poseTime,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);
 const bones={};for(const b of sk.bones){let d=b.data;bones[d.name]={translate:[{x:b.x-d.x,y:b.y-d.y}],rotate:[{value:b.rotation-d.rotation}],scale:[{x:b.scaleX/d.scaleX,y:b.scaleY/d.scaleY}]}}
 const slots={};for(const s of sk.slots)slots[s.data.name]={attachment:[{name:s.getAttachment().name}]};
 return {bones,slots};
}
const checks=[['head','head_control','rotate',5],['torso','torso','rotate',3],['shorts','pelvis','rotate',4],['near_hand','arm_near_target','translate',5],['far_hand','arm_far_target','translate',5],['near_foot','leg_near_target','translate',4],['far_foot','leg_far_target','translate',4]];
for(const [name,bone,kind,amount] of checks){const a=sampledHold(),base=a.bones[bone][kind][0];a.bones[bone][kind]=[0,.3,.6,.9,1.2].map((t,i)=>{let q={...base,time:t};const delta=[0,amount,0,-amount,0][i];if(kind==='rotate')q.value+=delta;else q.x+=delta;return q});raw.animations['test_'+name]=a;}
fs.writeFileSync('import_controls.json',JSON.stringify(raw,null,2));fs.writeFileSync('control_mapping.json',JSON.stringify({mapping,tests:checks,referencePoseTime:poseTime,notes:'Tests freeze frame70 attachments. These are small perturbations, not proof of arbitrary pose support.'},null,2));console.log('Rebound body/shorts/head; added seven fixed-attachment diagnostic clips.');

