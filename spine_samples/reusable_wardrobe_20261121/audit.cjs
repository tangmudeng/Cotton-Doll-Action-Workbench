// Independent native-roundtrip and per-subframe mesh/IK checks.
const fs=require('fs'),path=require('path'),{load,at,geometry}=require('./probe.cjs');
const dir=path.join(__dirname,'fitted'),a=load(dir),b=load(dir,'roundtrip/skin.json');
const alpha=JSON.parse(fs.readFileSync(path.join(dir,'triangle_alpha_support.json'),'utf8'));
const skins=['body/base','outfit/green_overalls'];let maxDelta=0,maxTargetError=0,finite=true,checks=0,flips=0,visibleFlips=0;
const locations=[];
for(const skin of skins)for(let i=0;i<23;i++)for(const phase of [0,.25,.5,.75,.999]){
 const time=(i+phase)/24+.000001;at(a,'walk_reuse',time,skin);at(b,'walk_reuse',time,skin);
 for(let si=0;si<a.sk.slots.length;si++){
  const aa=a.sk.slots[si].getAttachment(),bb=b.sk.slots[si].getAttachment();
  if(!!aa!==!!bb)throw Error('Roundtrip visibility changed');if(!aa)continue;
  if(aa.name!==bb.name)throw Error('Roundtrip attachment changed');
  const x=geometry(aa,a.sk.slots[si]),y=geometry(bb,b.sk.slots[si]);
  if(x.xy.length!==y.xy.length)throw Error('Roundtrip mesh topology changed');
  for(let j=0;j<x.xy.length;j++){finite&&=Number.isFinite(x.xy[j])&&Number.isFinite(y.xy[j]);maxDelta=Math.max(maxDelta,Math.abs(x.xy[j]-y.xy[j]));}
  // Geometry inversion alone includes transparent grid cells. Retain as a
  // diagnostic, never silently reclassify it as visible-pixel failure.
  let f=0,vf=0;
  for(let j=0;j<x.tri.length;j+=3){const [p,q,r]=x.tri.slice(j,j+3).map(k=>k*2);const area=v=>(v[q]-v[p])*(v[r+1]-v[p+1])-(v[q+1]-v[p+1])*(v[r]-v[p]);if(area(x.xy)*area(x.uv)>0){f++;if(aa.color.a>0&&alpha[aa.path][j/3]>0)vf++;}}
  if(f){flips+=f;visibleFlips+=vf;locations.push({skin,frame:i+63,phase,slot:a.sk.slots[si].data.name,count:f,alphaSupported:vf});}
 }
 for(const chain of ['arm_near','arm_far','leg_near','leg_far']){
  const lower=b.sk.findBone(chain+'_lower'),target=b.sk.findBone(chain+'_target');
  maxTargetError=Math.max(maxTargetError,Math.hypot(lower.worldX+lower.a*lower.data.length-target.worldX,lower.worldY+lower.c*lower.data.length-target.worldY));
 }
 checks++;
}
const report={roundtripPass:finite&&maxDelta<.25&&maxTargetError<.25,geometryPass:visibleFlips===0,productionReady:false,checks,frames:23,phasesPerFrame:5,skins:2,bones:a.sk.bones.length,ik:a.sk.ikConstraints.length,finite,maxRoundtripVertexDelta:maxDelta,maxIKEndpointError:maxTargetError,invertedTriangleObservations:flips,alphaSupportedInversionObservations:visibleFlips,inversions:locations,visualAccepted:false,secondVideoValidated:false,meaning:'Roundtrip and endpoint consistency only. Alpha-supported inversions require review; diagnostic counts are observations, not unique visible defects.'};
fs.writeFileSync(path.join(dir,'technical_audit.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,inversions:locations.slice(0,3)}));if(!report.roundtripPass)process.exitCode=1;
