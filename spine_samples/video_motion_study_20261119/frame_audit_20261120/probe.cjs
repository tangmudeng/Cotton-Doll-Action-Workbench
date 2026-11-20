const fs=require('fs'),vm=require('vm');
const base='pixel_sync_20261120/';
const c=vm.createContext({console,Image:class{},window:{},navigator:{}});
vm.runInContext(fs.readFileSync(base+'runtime/spine-canvas.js','utf8')+';globalThis.S=spine;',c);
const S=c.S,atlas=new S.TextureAtlas(fs.readFileSync(base+'skin.atlas','utf8'));
for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
const raw=JSON.parse(fs.readFileSync(base+'skin.json'));
const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data);
const manifest=JSON.parse(fs.readFileSync(base+'pixel_manifest.json'));
function sample(anim,time){
 sk.setToSetupPose();data.findAnimation(anim).apply(sk,0,time,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);sk.updateWorldTransform(S.Physics.update);
 return sk.drawOrder.map(slot=>{
 const a=slot.getAttachment(),m=manifest.find(p=>p.file==='parts/'+a.path+'.png'),v=new Float32Array(a.worldVerticesLength);
 a.computeWorldVertices(slot,0,v.length,v,0,2);const r=atlas.findRegion(a.path);
 return {name:slot.data.name,frame:m.sourceFrame,crop:m.crop,region:[r.x,r.y,r.width,r.height],v:[...v].map((n,i)=>i%2?480-n:432+n),uv:[...a.regionUVs],triangles:[...a.triangles]};
 });
}
const out={};
for(const n of ['test_near_hand','test_far_hand','test_near_foot','test_far_foot'])out[n]=[0,.3,.9].map(t=>({t,slots:sample(n,t)}));
fs.writeFileSync('frame_audit_20261120/ik_probe.json',JSON.stringify(out));
