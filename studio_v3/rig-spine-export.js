(function(root,factory){const api=factory(typeof module==='object'?require('./rig-studio-model.js'):root.RigStudioModel);if(typeof module==='object')module.exports=api;else root.RigSpineExport=api;})(globalThis,M=>{
'use strict';
const rad=a=>a*Math.PI/180,deg=a=>a*180/Math.PI;
const rotate=(p,a)=>{const c=Math.cos(rad(a)),s=Math.sin(rad(a));return [c*p[0]-s*p[1],s*p[0]+c*p[1]];};
const yup=p=>[p[0],768-p[1]];
function pack(parts){let x=4,y=4,row=0;const regions={};for(const p of parts){const w=p.bbox[2]-p.bbox[0],h=p.bbox[3]-p.bbox[1];if(x+w+4>1024){x=4;y+=row+8;row=0;}regions[p.id]={x,y,width:w,height:h};x+=w+8;row=Math.max(row,h);}let height=1;while(height<y+row+4)height*=2;return {width:1024,height,regions};}
function grid(p){const cols=p.joint?8:1,rows=p.joint?16:1,raw=[];for(let y=0;y<=rows;y++)for(let x=0;x<=cols;x++)raw.push([x/cols,y/rows]);const boundary=[];for(let x=0;x<=cols;x++)boundary.push(x);for(let y=1;y<=rows;y++)boundary.push(y*(cols+1)+cols);for(let x=cols-1;x>=0;x--)boundary.push(rows*(cols+1)+x);for(let y=rows-1;y>0;y--)boundary.push(y*(cols+1));const order=[...boundary,...raw.map((_,i)=>i).filter(i=>!boundary.includes(i))],index=new Map(order.map((n,i)=>[n,i])),tri=[];for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){const a=y*(cols+1)+x,b=a+1,c=a+cols+1,d=c+1;tri.push(...[a,b,c,b,d,c].map(i=>index.get(i)));}return {uv:order.flatMap(i=>raw[i]),tri,hull:boundary.length};}
function build(project,expected){const p=M.validate(project,expected),parts=p.parts,bones=[{name:'root'}],indices={root:0},rests={},ordered=[];
 function visit(part){if(rests[part.id])return;const parent=parts.find(x=>x.id===part.parent);if(parent)visit(parent);const pos=yup(part.pivot),parentPos=parent?rests[parent.id].pos:[0,0],parentAngle=parent?rests[parent.id].angle:0;const end=part.joint||[(part.bbox[0]+part.bbox[2])/2,(part.bbox[1]+part.bbox[3])/2],d=[end[0]-part.pivot[0],part.pivot[1]-end[1]],angle=deg(Math.atan2(d[1],d[0])),local=rotate([pos[0]-parentPos[0],pos[1]-parentPos[1]],-parentAngle);
 const b={name:part.id,parent:parent?.id||'root',x:local[0],y:local[1],rotation:angle-parentAngle,length:Math.hypot(...d)};indices[part.id]=bones.length;bones.push(b);rests[part.id]={pos,angle};ordered.push(part);
 if(part.joint){const jp=yup(part.joint),tip=yup(part.tip),a=deg(Math.atan2(tip[1]-jp[1],tip[0]-jp[0])),v=rotate([jp[0]-pos[0],jp[1]-pos[1]],-angle),name=part.id+'_bend';indices[name]=bones.length;bones.push({name,parent:part.id,x:v[0],y:v[1],rotation:a-angle,length:Math.hypot(tip[0]-jp[0],tip[1]-jp[1])});rests[name]={pos:jp,angle:a};}}
 parts.forEach(visit);const skin={},slots=[],channels={},packing=pack(parts);
 for(const part of [...parts].sort((a,b)=>a.order-b.order)){const g=grid(part),vertices=[];for(let i=0;i<g.uv.length;i+=2){const x=part.bbox[0]+g.uv[i]*(part.bbox[2]-part.bbox[0]),y=part.bbox[1]+g.uv[i+1]*(part.bbox[3]-part.bbox[1]);let lower=0;if(part.joint){const j=part.joint,v=[j[0]-part.pivot[0],j[1]-part.pivot[1]],len=Math.hypot(...v),d=((x-j[0])*v[0]+(y-j[1])*v[1])/len,u=Math.max(0,Math.min(1,(d+(part.blend||28))/(2*(part.blend||28))));lower=u*u*(3-2*u);}let limb=1;if(part.rootBand){const j=part.joint,v=[j[0]-part.pivot[0],j[1]-part.pivot[1]],d=((x-part.pivot[0])*v[0]+(y-part.pivot[1])*v[1])/Math.hypot(...v),u=Math.max(0,Math.min(1,(d-part.rootBand[0])/(part.rootBand[1]-part.rootBand[0])));limb=u*u*(3-2*u);}const inf=[[part.parent||'root',1-limb],[part.id,limb*(1-lower)],[part.id+'_bend',limb*lower]].filter(v=>v[1]>1e-10);vertices.push(inf.length);for(const [name,w]of inf){const r=rests[name],v=rotate([x-r.pos[0],768-y-r.pos[1]],-r.angle);vertices.push(indices[name],v[0],v[1],w);}}
 const region=packing.regions[part.id];skin[part.id]={[part.id]:{type:'mesh',path:part.id,uvs:g.uv,triangles:g.tri,vertices,hull:g.hull,edges:Array.from({length:g.hull},(_,i)=>[i*2,((i+1)%g.hull)*2]).flat(),width:region.width,height:region.height}};slots.push({name:part.id,bone:part.id,attachment:part.id,...(!part.visible?{color:'ffffff00'}:{})});
 const parentAngle=part.parent?rests[part.parent].angle:0;
 const keys=part.keys.length?part.keys:[{time:0,x:0,y:0,angle:0,bend:0},{time:p.duration,x:0,y:0,angle:0,bend:0}];
 const curve=k=>k.interpolation==='stepped'?{curve:'stepped'}:{};
 channels[part.id]={rotate:keys.map(k=>({time:k.time,value:-k.angle,...curve(k)})),translate:keys.map(k=>{const v=rotate([k.x,-k.y],-parentAngle);return {time:k.time,x:v[0],y:v[1],...curve(k)};})};
 if(part.joint)channels[part.id+'_bend']={rotate:keys.map(k=>({time:k.time,value:-(k.bend||0),...curve(k)}))};
 }
 const skeleton={skeleton:{spine:'4.2.43',width:768,height:768,images:'./images/',fps:p.fps},bones,slots,skins:[{name:'default',attachments:skin}],animations:{walk:{bones:channels},setup:{}}};
 let atlas=`walulu_walk.png\nsize: ${packing.width},${packing.height}\nformat: RGBA8888\nfilter: Linear,Linear\nrepeat: none\npma: false\n`;for(const part of parts){const r=packing.regions[part.id];atlas+=`${part.id}\n  rotate: false\n  xy: ${r.x},${r.y}\n  size: ${r.width},${r.height}\n  orig: ${r.width},${r.height}\n  offset: 0,0\n  index: -1\n`;}
 return {skeleton,atlas,packing};
}
return {build,grid,pack};
});
