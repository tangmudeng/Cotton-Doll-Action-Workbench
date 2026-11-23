// The accepted skeleton/IK/animation is authoritative. Only the root registration
// and PSD attachment geometry differ. Never infer a replacement rig from PSD.
const fs=require('fs'),path=require('path');const {load,S,base}=require('./extract_motion.cjs');
const dir=path.join(__dirname,'video_fit'),rig=path.join(__dirname,'rig'),accepted=JSON.parse(fs.readFileSync(path.join(base,'skin.json'))),manifest=JSON.parse(fs.readFileSync(path.join(rig,'source_manifest.json')));
const copy=x=>JSON.parse(JSON.stringify(x)),scale=1.68,offset=[24-17*scale,442-191*scale];
fs.mkdirSync(path.join(dir,'parts'),{recursive:true});for(const f of fs.readdirSync(path.join(rig,'parts')))fs.copyFileSync(path.join(rig,'parts',f),path.join(dir,'parts',f));
for(const f of ['skin.atlas','skin_0.png','source_manifest.json','atlas_report.json','assembly.png'])fs.copyFileSync(path.join(rig,f),path.join(dir,f));
const bones=copy(accepted.bones);Object.assign(bones[0],{x:offset[0],y:offset[1],scaleX:scale,scaleY:scale});
const raw={skeleton:{spine:'4.2.43',fps:24,images:'./parts/'},bones,ik:copy(accepted.ik),slots:accepted.slots.map(s=>({...s,attachment:s.name})),skins:[{name:'default',attachments:{}}],animations:{reference_cycle:{bones:copy(accepted.animations.reference_cycle.bones)}}};
const file=path.join(dir,'skin.json');fs.writeFileSync(file,JSON.stringify(raw));const runtime=load(dir);runtime.sk.updateWorldTransform(S.Physics.update);
// Registration landmarks belong to PSD pixels, not replacement skeleton joints.
const landmarks={arm_near:[[477,604],[423,737]],arm_far:[[591,600],[646,708]],leg_near:[[476,746],[481,855]],leg_far:[[584,738],[585,838]]},registration={};
for(const [name,[a,b]] of Object.entries(landmarks)){const root=runtime.sk.findBone(name+'_upper'),tip=runtime.sk.findBone(name+'_target'),A=[root.worldX+512,1024-root.worldY],B=[tip.worldX+512,1024-tip.worldY],dx=b[0]-a[0],dy=b[1]-a[1],ex=B[0]-A[0],ey=B[1]-A[1],den=dx*dx+dy*dy,p=(ex*dx+ey*dy)/den,q=(ey*dx-ex*dy)/den;registration[name]={sourceAnchors:[a,b],targetAnchors:[A,B],matrix:[p,-q,A[0]-p*a[0]+q*a[1],q,p,A[1]-q*a[0]-p*a[1]],scale:Math.hypot(p,q),rotationDegrees:Math.atan2(q,p)*180/Math.PI};}
for(const name of ['leg_near','leg_far']){const v=registration[name],[a,b]=v.sourceAnchors,[A,B]=v.targetAnchors,L=Math.hypot(b[0]-a[0],b[1]-a[1]),M=Math.hypot(B[0]-A[0],B[1]-A[1]),u=[(b[0]-a[0])/L,(b[1]-a[1])/L],w=[(B[0]-A[0])/M,(B[1]-A[1])/M],s=M/L,m00=s*w[0]*u[0]+w[1]*u[1],m01=s*w[0]*u[1]-w[1]*u[0],m10=s*w[1]*u[0]-w[0]*u[1],m11=s*w[1]*u[1]+w[0]*u[0];v.matrix=[m00,m01,A[0]-m00*a[0]-m01*a[1],m10,m11,A[1]-m10*a[0]-m11*a[1]];v.scaleAlong=s;v.scaleAcross=1;delete v.scale;}
const clamp=t=>Math.max(0,Math.min(1,t)),smooth=t=>{t=clamp(t);return t*t*(3-2*t)};
function grid(nx,ny){const points=[];for(let x=0;x<=nx;x++)points.push([x,0]);for(let y=1;y<=ny;y++)points.push([nx,y]);for(let x=nx-1;x>=0;x--)points.push([x,ny]);for(let y=ny-1;y>0;y--)points.push([0,y]);const hull=points.length;for(let y=1;y<ny;y++)for(let x=1;x<nx;x++)points.push([x,y]);const ids=new Map(points.map((p,i)=>[p.join(),i])),tri=[];for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const a=ids.get([x,y].join()),b=ids.get([x+1,y].join()),c=ids.get([x,y+1].join()),d=ids.get([x+1,y+1].join());tri.push(a,c,b,b,c,d)}return{uv:points.flatMap(([x,y])=>[x/nx,y/ny]),tri,hull}}
for(const part of manifest.parts){
 const name=part.key,limb=/^(arm|leg)_/.test(name),g=grid(limb?8:1,limb?14:1),[x0,y0,x1,y1]=part.canvasBox,vertices=[];
 for(let i=0;i<g.uv.length;i+=2){let px=x0+g.uv[i]*(x1-x0),py=y0+g.uv[i+1]*(y1-y0);if(registration[name]){const m=registration[name].matrix,[sx,sy]=[px,py];px=m[0]*sx+m[1]*sy+m[2];py=m[3]*sx+m[4]*sy+m[5];}const x=px-512,y=1024-py;let weights=[[raw.slots.find(s=>s.name===name).bone,1]];
  if(limb){const a=runtime.sk.findBone(name+'_upper'),e=runtime.sk.findBone(name+'_target'),dx=e.worldX-a.worldX,dy=e.worldY-a.worldY,t=clamp(((x-a.worldX)*dx+(y-a.worldY)*dy)/(dx*dx+dy*dy));
   weights=[[name+'_upper',1-t],[name+'_lower',t]];
   if(name.startsWith('leg')){const pin=clamp((py-710)/100),foot=.65*clamp((t-.1)/.9);weights=[['pelvis',1-pin],[name+'_upper',pin*(1-foot)*(1-t)],[name+'_lower',pin*(1-foot)*t],[name+'_target',pin*foot]];}
  }
  weights=weights.filter(([,w])=>w>1e-8);vertices.push(weights.length);for(const [n,w] of weights){const b=runtime.sk.findBone(n),dx=x-b.worldX,dy=y-b.worldY,det=b.a*b.d-b.b*b.c;vertices.push(bones.findIndex(b=>b.name===n),(dx*b.d-dy*b.b)/det,(dy*b.a-dx*b.c)/det,w)}
 }
 const edges=new Set();for(let j=0;j<g.tri.length;j+=3){const t=g.tri.slice(j,j+3);for(const [a,b] of [[t[0],t[1]],[t[1],t[2]],[t[2],t[0]]])edges.add([Math.min(a,b)*2,Math.max(a,b)*2].join(','));}
 raw.skins[0].attachments[name]={[name]:{type:'mesh',path:name,uvs:g.uv,vertices,triangles:g.tri,hull:g.hull,edges:[...edges].flatMap(e=>e.split(',').map(Number)),width:x1-x0,height:y1-y0}};
}
fs.writeFileSync(file,JSON.stringify(raw,null,2));
fs.writeFileSync(path.join(dir,'attachment_registration.json'),JSON.stringify({method:'static attachment alignment to accepted setup endpoints; legs retain original transverse width; skeleton unchanged',landmarks:registration},null,2));
const provenance={sourcePSD:manifest.sha256,acceptedSkeleton:path.relative(path.resolve(__dirname,'../..'),base).replaceAll('\\','/'),registration:{scale,offset,sourceNeck:[449,289],psdNeck:[536,582]},exactBoneDefinitionsExceptRoot:true,exactIK:true,exactBoneTimelines:true,additionalBones:0,animation:'reference_cycle',newBoneScaleTimelines:false,newRotationKeys:false,newAttachmentTimelines:false,textureCount:7,noRepaint:true,humanAccepted:false};fs.writeFileSync(path.join(dir,'provenance.json'),JSON.stringify(provenance,null,2));console.log(JSON.stringify(provenance));
