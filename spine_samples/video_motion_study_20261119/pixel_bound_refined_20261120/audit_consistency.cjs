const fs=require('fs'),vm=require('vm'),assert=require('assert');let c={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};vm.createContext(c);vm.runInContext(fs.readFileSync('runtime/spine-canvas.js','utf8')+';globalThis.s=spine;',c);const S=c.s;
const atlas=new S.TextureAtlas(fs.readFileSync('skin.atlas','utf8'));for(const p of atlas.pages)p.setTexture({getImage:()=>({width:2048,height:2048}),setFilters(){},setWraps(){}});
function load(file){const raw=JSON.parse(fs.readFileSync(file)),data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw);return {raw,data,sk:new S.Skeleton(data),anim:data.findAnimation('reference_cycle')}}
const a=load('skin.json'),b=load('audit_roundtrip/source_pixels_ik.json');
let times=new Set([0,a.anim.duration,b.anim.duration]);for(let i=0;i<=880;i++)times.add(i/960);
for(const obj of [a,b])for(const s of Object.values(obj.raw.animations.reference_cycle.slots))for(const k of s.attachment)for(const e of [-.000001,0,.000001])if(k.time+e>=0)times.add((k.time||0)+e);
let maxBone=0,maxVertex=0,switchMismatches=[],sameCount=0;
for(const t of [...times].sort((x,y)=>x-y)){
 for(const o of [a,b]){o.sk.setToSetupPose();o.anim.apply(o.sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);o.sk.updateWorldTransform(S.Physics.update)}
 for(let i=0;i<a.sk.bones.length;i++)for(const k of ['worldX','worldY','a','b','c','d'])maxBone=Math.max(maxBone,Math.abs(a.sk.bones[i][k]-b.sk.bones[i][k]));
 for(let i=0;i<a.sk.slots.length;i++){const x=a.sk.slots[i],y=b.sk.slots[i],ax=x.getAttachment(),ay=y.getAttachment();if(ax.name!==ay.name){switchMismatches.push({t,slot:x.data.name,browser:ax.name,export:ay.name});continue}sameCount++;const vx=new Float32Array(ax.worldVerticesLength),vy=new Float32Array(ay.worldVerticesLength);ax.computeWorldVertices(x,0,vx.length,vx,0,2);ay.computeWorldVertices(y,0,vy.length,vy,0,2);assert.equal(vx.length,vy.length);for(let k=0;k<vx.length;k++)maxVertex=Math.max(maxVertex,Math.abs(vx[k]-vy[k]))}
}
const report={sampleTimes:times.size,maxBoneTransformDifference:maxBone,maxSameAttachmentVertexDifferencePx:maxVertex,matchingAttachmentSamples:sameCount,attachmentSwitchMismatchCount:switchMismatches.length,mismatchExamples:switchMismatches.slice(0,20),note:'Original browser input versus freshly exported packaged Spine project. Exact key-time precision can change discrete attachment selection.'};fs.writeFileSync('consistency_audit.json',JSON.stringify(report,null,2));console.log(report);

