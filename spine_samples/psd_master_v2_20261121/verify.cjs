const fs=require('fs'),path=require('path'),vm=require('vm'),root=path.resolve(__dirname,'../..'),dir=path.join(__dirname,'rig');
const c={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'runtime/spine-canvas.js'),'utf8')+';globalThis.S=spine;',c);const S=c.S;
function load(name){const atlas=new S.TextureAtlas(fs.readFileSync(path.join(dir,'skin.atlas'),'utf8'));for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(JSON.parse(fs.readFileSync(path.join(dir,name),'utf8')));return{data,sk:new S.Skeleton(data)};}
function sample(r,name,t){r.sk.setToSetupPose();r.data.findAnimation(name).apply(r.sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);r.sk.updateWorldTransform(S.Physics.update);}
const a=load('skin.json'),b=load('roundtrip/skin.json');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'source_manifest.json'),'utf8')),feet={};let contactDrift=0;
sample(b,'setup_hold',0);
for(const slot of b.sk.slots){if(!slot.data.name.startsWith('leg_'))continue;const aa=slot.getAttachment(),v=new Float32Array(aa.worldVerticesLength);aa.computeWorldVertices(slot,0,v.length,v,0,2);feet[slot.data.name]=Array.from(v);}
let delta=0,endpoint=0,checks=0,flips=0;const locations=[];const frames=[];
for(const name of ['setup_hold','test_arm_near','test_arm_far','test_leg_near','test_leg_far','test_ground_contact'])for(let i=0;i<=96;i++){
 const t=i/48;sample(a,name,t);sample(b,name,t);const parts=[];
 for(let j=0;j<a.sk.slots.length;j++){
  const as=a.sk.slots[j],bs=b.sk.slots[j],aa=as.getAttachment(),bb=bs.getAttachment();if(aa.name!==bb.name)throw Error('Attachment changed');const av=new Float32Array(aa.worldVerticesLength),bv=new Float32Array(bb.worldVerticesLength);aa.computeWorldVertices(as,0,av.length,av,0,2);bb.computeWorldVertices(bs,0,bv.length,bv,0,2);
  for(let k=0;k<av.length;k++){if(!Number.isFinite(av[k])||!Number.isFinite(bv[k]))throw Error('Invalid vertex');delta=Math.max(delta,Math.abs(av[k]-bv[k]));}
  for(let k=0;k<aa.triangles.length;k+=3){const [p,q,r]=Array.from(aa.triangles).slice(k,k+3).map(x=>x*2),area=v=>(v[q]-v[p])*(v[r+1]-v[p+1])-(v[q+1]-v[p+1])*(v[r]-v[p]);if(area(av)*area(aa.regionUVs)>0){flips++;locations.push({animation:name,time:t,part:aa.name,triangle:k/3});}}
  if(name==='test_ground_contact'&&feet[aa.name]){const box=manifest.parts.find(p=>p.key===aa.name).canvasBox,limit=aa.name==='leg_near'?842:818;for(let k=0;k<av.length;k+=2){if(box[1]+aa.regionUVs[k+1]*(box[3]-box[1])>=limit)contactDrift=Math.max(contactDrift,Math.hypot(bv[k]-feet[aa.name][k],bv[k+1]-feet[aa.name][k+1]));}}
  if(i%24===0)parts.push({name:aa.name,xy:Array.from(av),uv:Array.from(aa.regionUVs),tri:Array.from(aa.triangles)});
 }
 for(const n of ['arm_near','arm_far','leg_near','leg_far']){const l=b.sk.findBone(n+'_lower'),target=b.sk.findBone(n+'_target');endpoint=Math.max(endpoint,Math.hypot(l.worldX+l.a*l.data.length-target.worldX,l.worldY+l.c*l.data.length-target.worldY));}
 if(parts.length)frames.push({animation:name,time:t,parts});checks++;
}
const report={roundtripPass:delta<.25&&endpoint<.25&&flips===0&&contactDrift<.25,checks,maxSoleVertexDrift:contactDrift,maxRoundtripVertexDelta:delta,maxIKEndpointError:endpoint,invertedTriangleObservations:flips,inversions:locations,legsTested:true,sourceVideoFitted:false,humanAccepted:false};fs.writeFileSync(path.join(dir,'technical_audit.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(dir,'sample_geometry.json'),JSON.stringify(frames));console.log(JSON.stringify(report));if(!report.roundtripPass)process.exitCode=1;
