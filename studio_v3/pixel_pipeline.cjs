/* Build and independently evaluate source-pixel meshes using the official runtime. */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm');
const c={console,Math,Float32Array,Float64Array,Uint16Array,Uint32Array,Int32Array,ArrayBuffer,Image:class{},window:{},navigator:{}};
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../runtime/spine-canvas.js'),'utf8')+';globalThis.S=spine;',c);
const S=c.S,dir=process.argv[2],mode=process.argv[3],read=n=>JSON.parse(fs.readFileSync(path.join(dir,n),'utf8')),write=(n,v)=>fs.writeFileSync(path.join(dir,n),JSON.stringify(v,null,2));
const p=read('project.json'),manifest=read('pixel_manifest.json'),W=p.source.width,H=p.source.height,FPS=p.source.fps;
const chains={arm_far:['shoulder_far','hand_far'],leg_far:['hip_far','foot_far'],arm_near:['shoulder_near','hand_near'],leg_near:['hip_near','foot_near']};
const mapping={head:'head_control',torso:'torso',shorts:'pelvis',arm_far:'arm_far_upper',arm_near:'arm_near_upper',leg_far:'leg_far_upper',leg_near:'leg_near_upper'};
const xy=a=>[a[0]-W/2,H-a[1]],angle=(a,b)=>Math.atan2(a[1]-b[1],b[0]-a[0])*180/Math.PI,dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function atlas(){const a=new S.TextureAtlas(fs.readFileSync(path.join(dir,'skin.atlas'),'utf8'));for(const page of a.pages)page.setTexture({getImage:()=>({width:page.width,height:page.height}),setFilters(){},setWraps(){}});return a;}
function rig(raw){const data=new S.SkeletonJson(new S.AtlasAttachmentLoader(atlas())).readSkeletonData(raw),sk=new S.Skeleton(data),anim=data.findAnimation('reference_cycle');if(!anim)throw Error('Missing reference_cycle');return {data,sk,anim};}
function pose(r,t){r.sk.setToSetupPose();r.anim.apply(r.sk,0,t,false,[],1,S.MixBlend.replace,S.MixDirection.mixIn);r.sk.updateWorldTransform(S.Physics.update);}
function timeline(values){return values.concat([{...values[0],time:p.frames.length/FPS}]).map(v=>({...v,curve:'stepped'}));}
function build(){
 const f0=p.frames[0],bones=[{name:'root'}],ik=[],anim={bones:{},slots:{}},attachments={};
 for(const [name,a,b] of [['torso','neck','pelvis'],['pelvis','hip_near','hip_far']]){
  const A=f0.points[a],B=f0.points[b],[x,y]=xy(A),rotation=angle(A,B);if(dist(A,B)<1)throw Error('Degenerate body anchors');
  bones.push({name,parent:'root',x,y,rotation,length:dist(A,B)});
  anim.bones[name]={translate:timeline(p.frames.map((f,i)=>({time:i/FPS,x:xy(f.points[a])[0]-x,y:xy(f.points[a])[1]-y}))),rotate:timeline(p.frames.map((f,i)=>({time:i/FPS,value:angle(f.points[a],f.points[b])-rotation})))};
 }
 for(const [name,[a,b]] of Object.entries(chains)){
  const A=f0.points[a],B=f0.joints[name],C=f0.points[b],l1=dist(A,B),l2=dist(B,C),[x,y]=xy(A),[tx,ty]=xy(C),r=angle(A,B);
  if(Math.min(l1,l2)<1)throw Error('骨骼链长度小于 1 像素：'+name);
  bones.push({name:name+'_upper',parent:'root',length:l1,x,y,rotation:r},{name:name+'_lower',parent:name+'_upper',length:l2,x:l1,rotation:angle(B,C)-r},{name:name+'_target',parent:'root',x:tx,y:ty});
  const bend=f=>{const A=xy(f.points[a]),B=xy(f.joints[name]),C=xy(f.points[b]);return (B[0]-A[0])*(C[1]-B[1])-(B[1]-A[1])*(C[0]-B[0])>=0;};
  ik.push({name:name+'_ik',order:ik.length,bones:[name+'_upper',name+'_lower'],target:name+'_target',bendPositive:bend(f0),mix:1});
  if(p.frames.some(f=>bend(f)!==bend(f0)))throw Error('同一骨骼链的弯曲方向发生翻转，请检查肘膝标注：'+name);
  // Per-pose lengths are represented by scale; source video perspective may change projected lengths.
  anim.bones[name+'_upper']={translate:timeline(p.frames.map((f,i)=>({time:i/FPS,x:xy(f.points[a])[0]-x,y:xy(f.points[a])[1]-y}))),scale:timeline(p.frames.map((f,i)=>({time:i/FPS,x:dist(f.points[a],f.joints[name])/l1,y:dist(f.points[a],f.joints[name])/l1})))};
  anim.bones[name+'_lower']={scale:timeline(p.frames.map((f,i)=>{let upper=dist(f.points[a],f.joints[name])/l1;return {time:i/FPS,x:dist(f.joints[name],f.points[b])/l2/upper,y:1/upper}}))};
  anim.bones[name+'_target']={translate:timeline(p.frames.map((f,i)=>({time:i/FPS,x:xy(f.points[b])[0]-tx,y:xy(f.points[b])[1]-ty})))};
 }
 bones.push({name:'head_control',parent:'torso',length:H/8,rotation:180});
 const raw={skeleton:{spine:'4.2.43',fps:FPS,images:'./parts/'},bones,ik,slots:[],skins:[{name:'default',attachments}],animations:{reference_cycle:anim}};
 // Bind against Spine's persisted precision, not transforms it will later round.
 // JSON export uses two decimals for positions/angles and three for scale.
 const round=(v,d)=>Math.round(v*10**d)/10**d;
 for(const b of bones)for(const k of ['x','y','length','rotation'])if(k in b)b[k]=round(b[k],2);
 for(const timelines of Object.values(anim.bones))for(const [kind,keys] of Object.entries(timelines))for(const key of keys)for(const k of ['x','y','value'])if(k in key)key[k]=round(key[k],kind==='scale'?3:2);
 for(const n of p.order){attachments[n]={};raw.slots.push({name:n,bone:mapping[n]});anim.slots[n]={attachment:timeline(p.frames.map((f,i)=>({time:i/FPS,name:f.parts[n].visible===false?null:n+'_'+f.frame})))};}
 // First solve IK, then inverse-bind each source vertex against that exact source pose.
 const r=rig(raw),boneIndex=Object.fromEntries(bones.map((b,i)=>[b.name,i]));
 for(const item of manifest){
  const i=p.frames.findIndex(f=>f.frame===item.sourceFrame),f=p.frames[i],n=item.part,[x0,y0,x1,y1]=item.crop,w=x1-x0,h=y1-y0,key=n+'_'+item.sourceFrame;
  pose(r,i/FPS+1e-7);
  const nx=6,ny=8,coords=[];
  // Boundary first, followed by interior vertices. Spine requires a valid hull on roundtrip.
  for(let x=0;x<=nx;x++)coords.push([x,0]);for(let y=1;y<=ny;y++)coords.push([nx,y]);for(let x=nx-1;x>=0;x--)coords.push([x,ny]);for(let y=ny-1;y>0;y--)coords.push([0,y]);
  const hull=coords.length;
  for(let y=1;y<ny;y++)for(let x=1;x<nx;x++)coords.push([x,y]);
  const index=new Map(coords.map((v,i)=>[v.join(','),i])),uvs=[],vertices=[],triangles=[];
  for(const [gx,gy] of coords){
   const u=gx/nx,v=gy/ny,x=x0+u*w,y=y0+v*h;uvs.push(u,v);
   let weights=[[mapping[n],1]];
   if(chains[n]){const [start,end]=chains[n],a=f.points[start],b=f.points[end],dx=b[0]-a[0],dy=b[1]-a[1],t=((x-a[0])*dx+(y-a[1])*dy)/Math.max(1,dx*dx+dy*dy),mix=Math.max(0,Math.min(1,(t-.3)/.45));weights=[[n+'_upper',1-mix],[n+'_lower',mix]].filter(q=>q[1]>1e-8);}
   vertices.push(weights.length);
   for(const [bn,weight] of weights){const b=r.sk.findBone(bn),dx=x-W/2-b.worldX,dy=H-y-b.worldY,det=b.a*b.d-b.b*b.c;if(Math.abs(det)<1e-8)throw Error('退化骨骼矩阵');vertices.push(boneIndex[bn],(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,weight);}
  }
  for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const a=index.get([x,y].join(',')),b=index.get([x+1,y].join(',')),c=index.get([x,y+1].join(',')),d=index.get([x+1,y+1].join(','));triangles.push(a,c,b,b,c,d);}
  attachments[n][key]={type:'mesh',path:key,width:w,height:h,uvs,vertices,triangles,hull};
 }
 for(const s of raw.slots)if(p.frames[0].parts[s.name].visible!==false)s.attachment=s.name+'_'+p.frames[0].frame;
 write('skin.json',raw);
}
function audit(raw){
 const r=rig(raw);let sourceError=0,intraFrameDrift=0,jointError=0,targetError=0,checks=0;const samples=[];
 for(let i=0;i<p.frames.length;i++){
  let first;
  for(const phase of [0,.25,.5,.75,.999]){
   const keys=raw.animations.reference_cycle.slots.head.attachment;
   const start=keys[i].time||0,end=keys[i+1]?.time??r.anim.duration;
   pose(r,start+(end-start)*phase+1e-7);const all=[];
   for(const [name,[root,end]] of Object.entries(chains)){
    const b=r.sk.findBone(name+'_lower'),f=p.frames[i],joint=xy(f.joints[name]),target=xy(f.points[end]);
    jointError=Math.max(jointError,Math.hypot(b.worldX-joint[0],b.worldY-joint[1]));
    targetError=Math.max(targetError,Math.hypot(b.worldX+b.a*b.data.length-target[0],b.worldY+b.c*b.data.length-target[1]));
   }
   for(const slot of r.sk.slots){
    const a=slot.getAttachment();if(p.frames[i].parts[slot.data.name].visible===false){if(a)throw Error('Hidden part still attached');continue;}if(!a||!a.triangles?.length)throw Error('Empty mesh '+slot.data.name);
    const item=manifest.find(m=>m.part===slot.data.name&&m.sourceFrame===p.frames[i].frame);
    if(a.name!==item.part+'_'+item.sourceFrame)throw Error('附件与源帧不同步');
    const vertices=new Float32Array(a.worldVerticesLength);a.computeWorldVertices(slot,0,vertices.length,vertices,0,2);
    const [x0,y0,x1,y1]=item.crop;
    for(let j=0;j<vertices.length;j+=2){const ex=x0+a.regionUVs[j]*(x1-x0)-W/2,ey=H-y0-a.regionUVs[j+1]*(y1-y0);sourceError=Math.max(sourceError,Math.hypot(vertices[j]-ex,vertices[j+1]-ey));}
    all.push(...vertices);
   }
   if(first)for(let j=0;j<all.length;j++)intraFrameDrift=Math.max(intraFrameDrift,Math.abs(all[j]-first[j]));else first=all;
   checks++;
  }
  samples.push(first);
 }
 // Spine JSON rounds setup geometry and weights. Quarter-pixel is the export tolerance.
 if(sourceError>.25||intraFrameDrift>.001)throw Error(JSON.stringify({sourceError,intraFrameDrift}));
 if(jointError>.2||targetError>.2)throw Error(JSON.stringify({jointError,targetError}));
 return {ok:true,frames:p.frames.length,attachments:manifest.length,bones:r.sk.bones.length,ik:r.sk.ikConstraints.length,checks,sourceError,intraFrameDrift,jointError,targetError,samples};
}
if(mode==='build')build();
const result=audit(mode==='roundtrip'?JSON.parse(fs.readFileSync(process.argv[4],'utf8')):read('skin.json'));
if(mode==='roundtrip'){
 const before=audit(read('skin.json'));let max=0;
 for(let i=0;i<result.samples.length;i++)for(let j=0;j<result.samples[i].length;j++)max=Math.max(max,Math.abs(result.samples[i][j]-before.samples[i][j]));
 if(max>.25)throw Error('Roundtrip changed vertices: '+max);result.roundtripMaxDelta=max;
}
delete result.samples;write(mode==='roundtrip'?'roundtrip_audit.json':'audit.json',result);console.log(JSON.stringify(result));
