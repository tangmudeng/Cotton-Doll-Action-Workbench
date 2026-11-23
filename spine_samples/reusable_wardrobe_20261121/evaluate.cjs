const fs=require('fs'),path=require('path'),{load,at,geometry}=require('./probe.cjs');
const dir=process.argv[2]||path.join(__dirname,'fitted'),file=process.argv[3]||'skin.json';
const r=load(dir,file),skins=r.data.skins.filter(s=>s.name!=='default').map(s=>s.name),result={};
for(const skin of skins.length?skins:['default']){
 const frames=[];
 for(let i=0;i<23;i++){
  at(r,'walk_reuse',i/24+.00006,skin);
  const meshes=[];for(const slot of r.sk.drawOrder){const a=slot.getAttachment();if(a&&a.color.a>0)meshes.push({slot:slot.data.name,...geometry(a,slot)});}
  frames.push({frame:i+63,meshes,bones:r.sk.bones.map(b=>({name:b.data.name,x:b.worldX,y:b.worldY,ex:b.worldX+b.a*b.data.length,ey:b.worldY+b.c*b.data.length}))});
 }
 result[skin]=frames;
}
fs.writeFileSync(path.join(dir,file==='skin.json'?'evaluated.json':'roundtrip_evaluated.json'),JSON.stringify(result));
console.log(JSON.stringify({skins:Object.keys(result),frames:23,bones:r.sk.bones.length,ik:r.sk.ikConstraints.length}));
