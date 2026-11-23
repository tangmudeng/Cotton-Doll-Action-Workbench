// Read-only measurements from the accepted rig using the official Spine runtime.
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'../..'),base=path.join(root,'spine_samples/video_motion_study_20261119/pixel_sync_20261120');
const ctx={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'runtime/spine-canvas.js'),'utf8')+';globalThis.S=spine;',ctx);const S=ctx.S;
function load(dir,file='skin.json'){
 const raw=JSON.parse(fs.readFileSync(path.join(dir,file),'utf8'));
 const atlas=new S.TextureAtlas(fs.readFileSync(path.join(dir,'skin.atlas'),'utf8'));
 for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
 const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data);return{raw,data,sk};
}
function at(r,name,t,skin){r.sk.setToSetupPose();if(skin){r.sk.setSkinByName(skin);r.sk.setSlotsToSetupPose();}r.data.findAnimation(name).apply(r.sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);r.sk.updateWorldTransform(S.Physics.update);}
function geometry(a,slot){const v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(slot,0,v.length,v,0,2);return {uv:Array.from(a.regionUVs),xy:Array.from(v),tri:Array.from(a.triangles),path:a.path};}
if(require.main===module){
 const r=load(base),samples=[],keys=r.raw.animations.reference_cycle.slots.head.attachment;
 for(let i=0;i<23;i++){
  at(r,'reference_cycle',(keys[i].time||0)+1e-6);
  const bones=r.sk.bones.map(b=>({name:b.data.name,a:b.a,b:b.b,c:b.c,d:b.d,x:b.worldX,y:b.worldY,length:b.data.length}));
  const parts={};for(const slot of r.sk.slots){parts[slot.data.name]={};for(const [key,a] of Object.entries(r.data.defaultSkin.attachments[slot.data.index]||{}))parts[slot.data.name][key]=geometry(a,slot);}
  samples.push({frame:i+63,time:keys[i].time||0,bones,parts});
 }
 fs.writeFileSync(path.join(__dirname,'probe.json'),JSON.stringify(samples));console.log('Measured 23 source poses and 161 attachment candidates.');
}
module.exports={S,load,at,geometry,root,base};
