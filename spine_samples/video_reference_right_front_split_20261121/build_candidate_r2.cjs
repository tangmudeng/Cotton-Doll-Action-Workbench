// Reusable PSD textures, calibrated accepted topology, new-video motion only.
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {S,load,at,geometry,base,root}=require('../psd_pixel_sync_binding_20261121/extract_motion.cjs');
const out=path.join(__dirname,'candidate_r2'),src=path.join(__dirname,'../psd_pixel_sync_binding_20261121/rig');
const read=p=>JSON.parse(fs.readFileSync(p)),write=(p,x)=>fs.writeFileSync(p,JSON.stringify(x,null,2)),copy=x=>JSON.parse(JSON.stringify(x));
const accepted=read(path.join(base,'skin.json')),manifest=read(path.join(src,'source_manifest.json')),motion=read(path.join(__dirname,'motion_observations.json')),M=read(path.join(__dirname,'head_registration.json')).matrix;
fs.mkdirSync(path.join(out,'parts'),{recursive:true});fs.mkdirSync(path.join(out,'runtime'),{recursive:true});
for(const f of ['skin.atlas','skin_0.png','source_manifest.json','atlas_report.json'])fs.copyFileSync(path.join(src,f),path.join(out,f));
for(const f of fs.readdirSync(path.join(src,'parts')))fs.copyFileSync(path.join(src,'parts',f),path.join(out,'parts',f));
for(const f of ['spine-canvas.js','pixel-renderer.js'])fs.copyFileSync(path.join(root,f==='spine-canvas.js'?'runtime/'+f:'studio_v3/'+f),path.join(out,'runtime',f));
const img=p=>[M[0][0]*p[0]+M[0][1]*p[1]+M[0][2],M[1][0]*p[0]+M[1][1]*p[1]+M[1][2]],world=p=>[p[0]-432,480-p[1]],fromPSD=p=>world(img(p));
const points={arm_near:[[477,604],[423,737]],arm_far:[[591,600],[646,708]],leg_near:[[476,746],[481,855]],leg_far:[[584,738],[585,838]]};
const bones=copy(accepted.bones),by=Object.fromEntries(bones.map(b=>[b.name,b]));
const set=(n,p)=>Object.assign(by[n],{x:p[0],y:p[1]});
set('torso',fromPSD([536,582]));set('pelvis',fromPSD([536,735]));
by.torso.length=153*Math.hypot(M[0][0],M[1][0]);by.pelvis.length=60*Math.hypot(M[0][0],M[1][0]);
for(const [n,[a,b]] of Object.entries(points)){
 const A=fromPSD(a),B=fromPSD(b),d=Math.hypot(B[0]-A[0],B[1]-A[1]),u=by[n+'_upper'],l=by[n+'_lower'],ratio=u.length/(u.length+l.length);
 set(n+'_upper',A);set(n+'_target',B);u.length=d*1.035*ratio;l.length=d*1.035*(1-ratio);l.x=u.length;
}
// Bind using the same setup precision that Spine 4.2 persists.
for(const b of bones)for(const k of ['x','y','length','rotation'])if(typeof b[k]==='number')b[k]=Number(b[k].toFixed(2));
const raw={skeleton:{spine:'4.2.43',fps:24,images:'./parts/'},bones,ik:copy(accepted.ik),slots:accepted.slots.map(s=>({...s,attachment:s.name})),skins:[{name:'default',attachments:{}}],animations:{}};
const file=path.join(out,'skin.json');write(file,raw);const r=load(out);r.sk.updateWorldTransform(S.Physics.update);
const clamp=x=>Math.max(0,Math.min(1,x)),smooth=x=>{x=clamp(x);return x*x*(3-2*x)};
function grid(nx,ny){const p=[];for(let x=0;x<=nx;x++)p.push([x,0]);for(let y=1;y<=ny;y++)p.push([nx,y]);for(let x=nx-1;x>=0;x--)p.push([x,ny]);for(let y=ny-1;y>0;y--)p.push([0,y]);const hull=p.length;for(let y=1;y<ny;y++)for(let x=1;x<nx;x++)p.push([x,y]);const ids=new Map(p.map((p,i)=>[p.join(),i])),tri=[];for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const a=ids.get([x,y].join()),b=ids.get([x+1,y].join()),c=ids.get([x,y+1].join()),d=ids.get([x+1,y+1].join());tri.push(a,c,b,b,c,d)}return{uv:p.flatMap(([x,y])=>[x/nx,y/ny]),tri,hull}}
for(const part of manifest.parts){
 const n=part.key,limb=/^(arm|leg)_/.test(n),g=grid(limb?12:n==='shorts'?20:n==='torso'?12:1,limb?24:n==='shorts'?12:n==='torso'?12:1),[x0,y0,x1,y1]=part.canvasBox,vertices=[],weightsRecord=[];
 for(let i=0;i<g.uv.length;i+=2){const px=x0+g.uv[i]*(x1-x0),py=y0+g.uv[i+1]*(y1-y0),[x,y]=fromPSD([px,py]);let weights=[[raw.slots.find(s=>s.name===n).bone,1]];
  if(limb){const [A,B]=points[n],dx=B[0]-A[0],dy=B[1]-A[1],t=((px-A[0])*dx+(py-A[1])*dy)/(dx*dx+dy*dy),lower=clamp(t);
   if(n.startsWith('leg')){
    const foot=smooth((py-755)/70),move=smooth((py-720)/105);
    weights=[['pelvis',1-move],[n+'_upper',move*(1-foot)*(1-lower)],[n+'_lower',move*(1-foot)*lower],[n+'_target',move*foot]];
   }else{weights=[[n+'_upper',1-lower],[n+'_lower',lower]];}
  }
  if(n==='shorts'){const hem=smooth((py-710)/80)*.35,side=smooth((px-490)/90);weights=[['pelvis',1-hem],['leg_near_upper',hem*(1-side)],['leg_far_upper',hem*side]];}
  weights=weights.filter(([,w])=>w>1e-8);vertices.push(weights.length);weightsRecord.push(weights);
  for(const [n,w] of weights){const b=r.sk.findBone(n),dx=x-b.worldX,dy=y-b.worldY,det=b.a*b.d-b.b*b.c;vertices.push(bones.findIndex(b=>b.name===n),(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,w)}
 }
 const edges=new Set();for(let j=0;j<g.tri.length;j+=3){const [a,b,c]=g.tri.slice(j,j+3);for(const [u,v] of [[a,b],[b,c],[c,a]])edges.add([Math.min(u,v)*2,Math.max(u,v)*2].join(','));}
 raw.skins[0].attachments[n]={[n]:{type:'mesh',path:n,uvs:g.uv,vertices,triangles:g.tri,hull:g.hull,edges:[...edges].flatMap(e=>e.split(',').map(Number)),width:x1-x0,height:y1-y0}};
}
const tracks={};function add(n,ch,time,values){((tracks[n]??={})[ch]??=[]).push({time,...values})}
function translate(n,p,time){const w=world(p);add(n,'translate',time,{x:w[0]-(by[n].x||0),y:w[1]-(by[n].y||0)})}
const angle=(a,b)=>Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI,neck0=img([536,582]),hip0=img([536,735]),torsoAngle0=angle(neck0,hip0);
const minReach=[];
for(const row of motion.frames){const t=row.time,p=row.points,H=row.headMatrix,headRot=-Math.atan2(H[1][0],H[0][0])*180/Math.PI,neck=[H[0][0]*neck0[0]+H[0][1]*neck0[1]+H[0][2],H[1][0]*neck0[0]+H[1][1]*neck0[1]+H[1][2]],hip=[(p.hip_near[0]+p.hip_far[0])/2,(p.hip_near[1]+p.hip_far[1])/2-7],bodyRot=torsoAngle0-angle(neck,hip);
 translate('torso',neck,t);add('torso','rotate',t,{value:bodyRot});
 const rad=-bodyRot*Math.PI/180,followBody=q=>{const dx=q[0]-neck0[0],dy=q[1]-neck0[1];return[neck[0]+Math.cos(rad)*dx-Math.sin(rad)*dy,neck[1]+Math.sin(rad)*dx+Math.cos(rad)*dy]};
 translate('pelvis',followBody(hip0),t);add('pelvis','rotate',t,{value:bodyRot});
 add('head_control','rotate',t,{value:headRot-bodyRot});
 for(const n of Object.keys(points)){const isLeg=n.startsWith('leg'),side=n.endsWith('near')?'near':'far',A=isLeg?followBody(img(points[n][0])):p['shoulder_'+side],B=p[(isLeg?'foot_':'hand_')+side];
  translate(n+'_upper',A,t);translate(n+'_target',B,t);
  // Target bones are rigid distal surface controls as well as IK endpoints.
  // Keep foot soles rigid; modest hand orientation follows the observed limb axis.
  {const [sa,sb]=points[n].map(img);add(n+'_target','rotate',t,{value:(angle(sa,sb)-angle(A,B))*(isLeg?.8:1)})}
  const distance=Math.hypot(B[0]-A[0],B[1]-A[1]),length=by[n+'_upper'].length+by[n+'_lower'].length;
  // A fixed 2D length forces deep bends when the video limb points into depth.
  // Arm transverse scale stays fixed. Leg chain projection is uniform to avoid
  // anisotropic IK shearing; the rigid foot does NOT inherit this scale.
  add(n+'_upper','scale',t,{x:distance*1.035/length,y:isLeg?distance*1.035/length:1});
  if(distance>length)minReach.push({frame:row.frame,chain:n,excess:distance-length});
 }
}
// One interpolation segment from source frame 82 to 59; do not duplicate 83.
for(const channels of Object.values(tracks))for(const keys of Object.values(channels))keys.push({...keys[0],time:1});
raw.animations.video_right_front_split_59_82={bones:tracks};raw.animations.psd_bind_pose={bones:{root:{translate:[{time:0},{time:1}]}}};write(file,raw);
const boneChanges=bones.filter((b,i)=>JSON.stringify(b)!==JSON.stringify(accepted.bones[i])).map(b=>({name:b.name,accepted:accepted.bones.find(a=>a.name===b.name),calibrated:b}));
write(path.join(out,'provenance.json'),{status:'candidate_pending_visual_review',humanAccepted:false,sourcePSD:manifest.source,sourcePSDSha256:manifest.sha256,sourceVideo:read(path.join(__dirname,'selection.json')),motionObservationFile:'motion_observations.json',acceptedRigReference:'spine_samples/video_motion_study_20261119/pixel_sync_20261120',topologyUnchanged:true,ikUnchanged:true,restPoseCalibratedToPSD:true,boneChanges,oldAnimationReused:false,attachmentCount:7,noRepaint:true,noVideoTextures:true,projectedLengthTracks:true,scalePolicy:'upper scaleX = observed endpoint distance / calibrated setup distance; arms scaleY=1, legs scaleY=scaleX; target bones do not inherit limb scaling',hipPolicy:'PSD hip attachments follow the pelvis/torso registration so pants and thigh roots remain connected; raw hip estimates are not treated as exact anatomy',footRegion:'PSD y >= 825: 100% rigid target bone; no multi-bone blending',registration:M,reachWarnings:minReach,uncertainties:'Hidden far foot trajectory is inferred, not independently recovered anatomy.'});
assert.deepStrictEqual(raw.ik,accepted.ik);assert.deepStrictEqual(bones.map(b=>[b.name,b.parent]),accepted.bones.map(b=>[b.name,b.parent]));
console.log(JSON.stringify({out,bones:bones.length,ik:raw.ik.length,textures:manifest.parts.length,reachWarnings:minReach}));
