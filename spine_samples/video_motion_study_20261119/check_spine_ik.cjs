const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};
vm.createContext(c);vm.runInContext(fs.readFileSync('runtime/spine-canvas.js','utf8')+';globalThis.s=spine;',c);
const S=c.s,atlas=new S.TextureAtlas(fs.readFileSync('ik.atlas','utf8'));
for(const p of atlas.pages)p.setTexture({getImage:()=>({width:32,height:32}),setFilters(){},setWraps(){}});
const raw=JSON.parse(fs.readFileSync('roundtrip/video_motion_ik.json')),data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data),anim=data.findAnimation('reference_cycle');
const annotations=JSON.parse(fs.readFileSync('motion_annotations.json'));let targetError=0,jointError=0,lengthError=0;const poses=[];
for(const sample of annotations.samples){
 sk.setToSetupPose();anim.apply(sk,0,(sample.frame-63)/24,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);sk.updateWorldTransform(S.Physics.update);
 const out={frame:sample.frame,chains:{}};
 for(const [name,chain] of Object.entries(sample.chains)){
  const up=sk.findBone(name+'_upper'),lo=sk.findBone(name+'_lower'),target=sample.points[chain.target],end=[lo.worldX+lo.a*lo.data.length+432,480-(lo.worldY+lo.c*lo.data.length)],joint=[lo.worldX+432,480-lo.worldY],root=[up.worldX+432,480-up.worldY];
  targetError=Math.max(targetError,Math.hypot(end[0]-target[0],end[1]-target[1]));jointError=Math.max(jointError,Math.hypot(joint[0]-chain.joint[0],joint[1]-chain.joint[1]));lengthError=Math.max(lengthError,Math.abs(Math.hypot(joint[0]-root[0],joint[1]-root[1])-chain.lengths[0]),Math.abs(Math.hypot(end[0]-joint[0],end[1]-joint[1])-chain.lengths[1]));
  out.chains[name]={root,joint,end};
 }poses.push(out);
}
assert.equal(data.ikConstraints.length,4);assert(targetError<.02);assert(lengthError<.02);assert(jointError<.05);
const report={bones:data.bones.length,nativeIKConstraints:data.ikConstraints.length,frames:poses.length,maxTargetError:targetError,maxJointDifferenceVsAnalyticSolver:jointError,maxBoneLengthError:lengthError,motionAccuracyValidated:false,groundContactsValidated:false};
fs.writeFileSync('native_ik_checks.json',JSON.stringify(report,null,2));fs.writeFileSync('native_ik_poses.json',JSON.stringify(poses));console.log(report);

