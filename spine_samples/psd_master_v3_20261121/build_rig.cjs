// Independent four-limb rig. All coordinates refer to the supplied PSD.
const fs=require('fs'),path=require('path'),vm=require('vm'),root=path.resolve(__dirname,'../..'),out=path.join(__dirname,'rig');
const ctx={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'runtime/spine-canvas.js'),'utf8')+';globalThis.S=spine;',ctx);const S=ctx.S;
const read=f=>JSON.parse(fs.readFileSync(path.join(out,f),'utf8')),write=(f,x)=>fs.writeFileSync(path.join(out,f),JSON.stringify(x,null,2));
const manifest=read('source_manifest.json'),[W,H]=manifest.canvas;
const xy=p=>[p[0]-W/2,H-p[1]],dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]),angle=(a,b)=>Math.atan2(a[1]-b[1],b[0]-a[0])*180/Math.PI;
const chains={arm_near:[[477,604],[442,670],[423,737]],arm_far:[[591,600],[622,648],[646,708]],leg_near:[[476,746],[465,803],[481,855]],leg_far:[[584,738],[574,791],[585,838]]};
const bones=[{name:'root'},{name:'torso',parent:'root',x:28,y:377},{name:'pelvis',parent:'root',x:26,y:278},{name:'head',parent:'root',x:24,y:442}],ik=[];
for(const [n,[a,b,c]] of Object.entries(chains)){
 const [x,y]=xy(a),[tx,ty]=xy(c),u=angle(a,b),v=angle(b,c),l1=dist(a,b),l2=dist(b,c),A=xy(a),B=xy(b),C=xy(c);
 bones.push({name:n+'_upper',parent:'root',x,y,length:l1,rotation:u},{name:n+'_lower',parent:n+'_upper',x:l1,length:l2,rotation:v-u},{name:n+'_target',parent:'root',x:tx,y:ty});
 ik.push({name:n+'_ik',bones:[n+'_upper',n+'_lower'],target:n+'_target',order:ik.length,bendPositive:(B[0]-A[0])*(C[1]-B[1])-(B[1]-A[1])*(C[0]-B[0])>=0});
}
for(const name of ['leg_near','leg_far'])bones.push({name:name+'_foot',parent:name+'_target'});
const map={arm_far:'arm_far_upper',arm_near:'arm_near_upper',leg_near:'leg_near_upper',leg_far:'leg_far_upper',torso:'torso',shorts:'pelvis',head:'head'};
const raw={skeleton:{spine:'4.2.43',fps:24,images:'./parts/'},bones,ik,slots:manifest.parts.map(p=>({name:p.key,bone:map[p.key],attachment:p.key})),skins:[{name:'default',attachments:{}}],animations:{}};
function runtime(raw){const atlas=new S.TextureAtlas(fs.readFileSync(path.join(out,'skin.atlas'),'utf8'));for(const p of atlas.pages)p.setTexture({getImage:()=>({width:p.width,height:p.height}),setFilters(){},setWraps(){}});const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas)).readSkeletonData(raw);return{data,sk:new S.Skeleton(data)};}
const rig=runtime(raw);rig.sk.updateWorldTransform(S.Physics.update);
function grid(nx,ny){const p=[];for(let x=0;x<=nx;x++)p.push([x,0]);for(let y=1;y<=ny;y++)p.push([nx,y]);for(let x=nx-1;x>=0;x--)p.push([x,ny]);for(let y=ny-1;y>0;y--)p.push([0,y]);const hull=p.length;for(let y=1;y<ny;y++)for(let x=1;x<nx;x++)p.push([x,y]);const ids=new Map(p.map((a,i)=>[a.join(),i])),tri=[];for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const a=ids.get([x,y].join()),b=ids.get([x+1,y].join()),c=ids.get([x,y+1].join()),d=ids.get([x+1,y+1].join());tri.push(a,c,b,b,c,d);}return{p:p.map(([x,y])=>[x/nx,y/ny]),tri,hull};}
for(const part of manifest.parts){
 const name=part.key,[x0,y0,x1,y1]=part.canvasBox,w=x1-x0,h=y1-y0,g=grid(chains[name]||name==='shorts'?8:1,chains[name]?12:name==='shorts'?8:1),uvs=[],vertices=[];
 for(const [u,v] of g.p){const x=x0+u*w,y=y0+v*h;uvs.push(u,v);let weights=[[map[name],1]];
  if(chains[name]){const [a,b,c]=chains[name],d=[c[0]-a[0],c[1]-a[1]],t=((x-a[0])*d[0]+(y-a[1])*d[1])/(d[0]*d[0]+d[1]*d[1]);const z=Math.max(0,Math.min(1,(t-(name.startsWith('leg')?.2:.35))/(name.startsWith('leg')?.75:.45))),mix=z*z*(3-2*z);const rootBlend=name.startsWith('leg')?Math.max(0,Math.min(1,t/.38)):1;const fz=name.startsWith('leg')?Math.max(0,Math.min(1,(y-(name==='leg_near'?814:790))/28)):0,foot=fz*fz*(3-2*fz);weights=[['pelvis',(1-rootBlend)*(1-foot)],[name+'_upper',rootBlend*(1-mix)*(1-foot)],[name+'_lower',rootBlend*mix*(1-foot)],[name+'_foot',foot]].filter(x=>x[1]>1e-8);}
  vertices.push(weights.length);for(const [bn,weight] of weights){const b=rig.sk.findBone(bn),dx=x-W/2-b.worldX,dy=H-y-b.worldY,det=b.a*b.d-b.b*b.c;vertices.push(bones.findIndex(q=>q.name===bn),(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,weight);}
 }
 const edges=new Set();for(let j=0;j<g.tri.length;j+=3){const t=g.tri.slice(j,j+3);for(const [a,b] of [[t[0],t[1]],[t[1],t[2]],[t[2],t[0]]])edges.add([Math.min(a,b)*2,Math.max(a,b)*2].join(','));}
 raw.skins[0].attachments[name]={[name]:{type:'mesh',path:name,uvs,vertices,triangles:g.tri,hull:g.hull,edges:[...edges].flatMap(x=>x.split(',').map(Number)),width:w,height:h}};
}
raw.animations.setup_hold={bones:{root:{translate:[{}, {time:2}]}}};
for(const [name,chain] of Object.entries(chains)){
 const [a,b,c]=chain,l1=dist(a,b),l2=dist(b,c),upper=angle(a,b),lower=angle(b,c);const keys=[];
 // Bounded joint stress, not a claim to match the reference video.
 for(let i=0;i<=48;i++){const t=i/24,s=Math.sin(t*Math.PI),swing=(name.startsWith('leg')?10:14)*s,flex=(name.startsWith('leg')?12:8)*Math.sin(t*2*Math.PI),u=(upper+swing)*Math.PI/180,v=(lower+swing+flex)*Math.PI/180;const q=[a[0]+l1*Math.cos(u)+l2*Math.cos(v),a[1]-l1*Math.sin(u)-l2*Math.sin(v)];keys.push({time:t,x:q[0]-c[0],y:c[1]-q[1]});}
 raw.animations['test_'+name]={bones:{[name+'_target']:{translate:keys}}};
}
// Body compression with fixed leg endpoints is an explicit planted-foot test.
const contact={bones:{}};
for(const name of ['torso','pelvis','head','arm_near_upper','arm_far_upper','arm_near_target','arm_far_target','leg_near_upper','leg_far_upper'])contact.bones[name]={translate:Array.from({length:49},(_,i)=>({time:i/24,y:-8*Math.sin(i/48*Math.PI)**2}))};
raw.animations.test_ground_contact=contact;
write('skin.json',raw);write('binding_notes.json',{stage:'four-limb-joint-validation',manualAnchors:chains,coordinateSpace:'PSD canvas pixels; y down',legsIndependent:true,referenceVideoMotionFitted:false,visualAccepted:false});
const check=runtime(raw);check.sk.updateWorldTransform(S.Physics.update);let max=0;
for(const slot of check.sk.slots){const a=slot.getAttachment(),p=manifest.parts.find(x=>x.key===slot.data.name),[x0,y0,x1,y1]=p.canvasBox,v=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(slot,0,v.length,v,0,2);for(let i=0;i<v.length;i+=2)max=Math.max(max,Math.hypot(v[i]-(x0+a.regionUVs[i]*(x1-x0)-W/2),v[i+1]-(H-y0-a.regionUVs[i+1]*(y1-y0))));}
if(max>.001)throw Error('Static assembly moved: '+max);write('static_audit.json',{maxSourceVertexError:max,attachments:manifest.parts.length,bones:bones.length,ik:ik.length,visualAccepted:false});console.log(JSON.stringify({maxSourceVertexError:max,bones:bones.length,ik:ik.length}));
