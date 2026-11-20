const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const base = 'pixel_sync_20261120/';
const context = vm.createContext({ console, Image: class {}, window: {}, navigator: {} });
vm.runInContext(fs.readFileSync(base+'runtime/spine-canvas.js','utf8')+'; globalThis.runtime = spine;', context);
const S = context.runtime;
const atlas = new S.TextureAtlas(fs.readFileSync(base+'skin.atlas','utf8'));
for (const p of atlas.pages) p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});
const manifest = JSON.parse(fs.readFileSync(base+'pixel_manifest.json'));
const records = {};
for(const [label,file] of [['sync','skin.json']]){
  const raw = JSON.parse(fs.readFileSync(base+file));
  const data = new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw);
  const sk = new S.Skeleton(data);
  const anim = data.findAnimation('reference_cycle');
  const keys = raw.animations.reference_cycle.slots.head.attachment.map(k=>k.time||0);
  const passes = [];
  for(const [index,key] of keys.entries()){
    if(index===23) continue; const next = keys[index+1];
    for(const [mode,t] of [['key',key+1e-7], ...(next===undefined?[]:[['quarter',key+(next-key)/4],['mid',(key+next)/2],['threequarter',key+3*(next-key)/4],['end',next-1e-7]])]){
      sk.setToSetupPose();
      anim.apply(sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);
      sk.updateWorldTransform(S.Physics.update);
      const slots = sk.drawOrder.map(slot=>{
        const a = slot.getAttachment();
        const info = manifest.find(p=>p.file===`parts/${a.path}.png`);
        assert(info && a.triangles.length>0);
        const v = new Float32Array(a.worldVerticesLength);
        a.computeWorldVertices(slot,0,v.length,v,0,2);
        assert([...v].every(Number.isFinite));
        const region = atlas.findRegion(a.path);
        return {name:slot.data.name, frame:info.sourceFrame, crop:info.crop, region:[region.x,region.y,region.width,region.height],
                v:[...v].map((n,i)=>i%2?480-n:432+n), uv:[...a.regionUVs], triangles:[...a.triangles]};
      });
      passes.push({frame:index+63,mode,t,slots});
    }
  }
  records[label] = {duration:anim.duration,passes};
}
fs.writeFileSync('frame_audit_20261120/sync_poses.json',JSON.stringify(records));
