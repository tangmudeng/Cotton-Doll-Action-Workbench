const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const M=require('../rig-studio-model.js'),E=require('../rig-spine-export.js');
const root=path.resolve(__dirname,'..'),input=process.argv[2]||path.join(root,'generated_rig/walk_acceptance_v1/draft.json');
const p=JSON.parse(fs.readFileSync(input,'utf8')),result=E.build(p,p.source);
if(process.argv[4])result.skeleton=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
const context={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'../runtime/spine-canvas.js'),'utf8')+';globalThis.runtime=spine;',context);const spine=context.runtime;
const atlas=new spine.TextureAtlas(result.atlas);for(const page of atlas.pages){page.setTexture({getImage:()=>({width:result.packing.width,height:result.packing.height}),setFilters(){},setWraps(){}});}
const data=new spine.SkeletonJson(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(result.skeleton),skeleton=new spine.Skeleton(data),animation=data.findAnimation('walk');
let maxError=0,minAreaRatio=Infinity,flips=0,loopError=0;const setup={};
skeleton.setToSetupPose();skeleton.updateWorldTransform(spine.Physics.update);
function vertices(slot){const a=slot.getAttachment(),v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(slot,0,v.length,v,0,2);return v;}
for(const slot of skeleton.slots)setup[slot.data.name]=vertices(slot);
const poses=[];for(let i=0;i<=192;i++){const t=p.duration*i/192;skeleton.setToSetupPose();animation.apply(skeleton,0,process.argv[4]?animation.duration*i/192:t,false,[],1,spine.MixBlend.replace,spine.MixDirection.mixIn);skeleton.updateWorldTransform(spine.Physics.update);const transforms=M.matrices(p.parts,t),all={};
for(const slot of skeleton.slots){const name=slot.data.name,part=p.parts.find(p=>p.id===name),a=slot.getAttachment(),v=vertices(slot),keys=M.pose(part.keys,t);all[name]=Array.from(v);
 for(let k=0;k<v.length;k+=2){const uv=a.regionUVs,xy=[part.bbox[0]+uv[k]*(part.bbox[2]-part.bbox[0]),part.bbox[1]+uv[k+1]*(part.bbox[3]-part.bbox[1])],expected=M.apply(transforms.get(name),M.vertex(part,xy,keys));maxError=Math.max(maxError,Math.hypot(expected[0]-v[k],768-expected[1]-v[k+1]));}
 const area=(arr,ia,ib,ic)=>(arr[ib*2]-arr[ia*2])*(arr[ic*2+1]-arr[ia*2+1])-(arr[ib*2+1]-arr[ia*2+1])*(arr[ic*2]-arr[ia*2]);
 for(let k=0;k<a.triangles.length;k+=3){const ids=a.triangles.slice(k,k+3),ratio=area(v,...ids)/area(setup[name],...ids);minAreaRatio=Math.min(minAreaRatio,ratio);if(ratio<=0)flips++;}
}if(i===0||i===192)poses.push(all);}
for(const name of Object.keys(poses[0]))for(let i=0;i<poses[0][name].length;i++)loopError=Math.max(loopError,Math.abs(poses[0][name][i]-poses[1][name][i]));
assert.equal(data.bones.length,12);assert.equal(data.slots.length,7);assert.equal(data.animations.length,2);assert.ok(maxError<(process.argv[4]?0.1:0.003),`editor/export parity error ${maxError}`);assert.equal(flips,0);assert.ok(loopError<0.003);
const report={samples:193,bones:data.bones.length,attachments:data.slots.length,duration:animation.duration,maxEditorSpineVertexErrorPx:maxError,minTriangleAreaRatio:minAreaRatio,flippedTriangles:flips,loopVertexErrorPx:loopError,runtime:'bundled Spine official runtime',passed:true};console.log(JSON.stringify(report));
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(report,null,2));
