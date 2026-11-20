const fs=require('fs'),vm=require('vm'),assert=require('assert');
let c={console,Image:class{},window:{},navigator:{},Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Math};vm.createContext(c);vm.runInContext(fs.readFileSync('runtime/spine-canvas.js','utf8')+';globalThis.S=spine',c);
const S=c.S,atlas=new S.TextureAtlas(fs.readFileSync('skin.atlas','utf8'));for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
const raw=JSON.parse(fs.readFileSync('roundtrip/walulu_walk_pixel_sync.json')),data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw),sk=new S.Skeleton(data),anim=data.findAnimation('reference_cycle');
function sample(t){sk.setToSetupPose();anim.apply(sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);sk.updateWorldTransform(S.Physics.update);return Object.fromEntries(sk.bones.map(b=>[b.data.name,[+b.worldX.toFixed(3),+b.worldY.toFixed(3),+Math.atan2(b.c,b.a).toFixed(4)]]))}
for(const f of [0,1/24,5/24,10/24,15/24,22/24,23/24])console.log(f.toFixed(4),sample(f));
