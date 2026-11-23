const fs=require('fs'),path=require('path'),{load,at,geometry}=require('./probe.cjs'),dir=path.join(__dirname,'fitted');
const r=load(dir),alpha=JSON.parse(fs.readFileSync(path.join(dir,'triangle_alpha_support.json'),'utf8')),counts={};
for(let i=0;i<23;i++)for(const phase of [0,.25,.5,.75,.999]){
 at(r,'walk_reuse',(i+phase)/24+.000001,'outfit/green_overalls');
 for(const slot of r.sk.slots){const a=slot.getAttachment();if(!a||a.color.a===0)continue;const g=geometry(a,slot);
  for(let j=0;j<g.tri.length;j+=3){if(!alpha[a.path][j/3])continue;const [p,q,s]=g.tri.slice(j,j+3).map(k=>k*2),area=v=>(v[q]-v[p])*(v[s+1]-v[p+1])-(v[q+1]-v[p+1])*(v[s]-v[p]);if(area(g.xy)*area(g.uv)>0)counts[slot.data.name]=(counts[slot.data.name]||0)+1;}
 }
}
console.log(JSON.stringify(counts));
