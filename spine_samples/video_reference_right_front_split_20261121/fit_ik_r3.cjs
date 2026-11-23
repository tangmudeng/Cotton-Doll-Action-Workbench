// IK endpoints refer to the same material anchors as the fitted PSD surface.
// Hidden joint centers are estimates, not independent anatomical ground truth.
const fs=require('fs'),path=require('path');
const dir=path.join(__dirname,'candidate_r3'),read=n=>JSON.parse(fs.readFileSync(path.join(dir,n))),write=(n,v)=>fs.writeFileSync(path.join(dir,n),JSON.stringify(v,null,2));
const raw=read('skin.json'),fit=read('surface_fit.json'),tracks=raw.animations.video_right_front_split_59_82.bones,by=Object.fromEntries(raw.bones.map(b=>[b.name,b]));
const world=p=>[p[0]-432,480-p[1]],dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const M=read('provenance.json').registration,baseAngle=-Math.atan2(M[1][0],M[0][0])*180/Math.PI;
const records=[];
const chains=['leg_near','leg_far','arm_near','arm_far'];
for(const n of chains){tracks[n+'_upper']={translate:[],scale:[]};tracks[n+'_lower']={scale:[]};tracks[n+'_target']={translate:[],rotate:[]};}
for(const row of fit.frames){const record={frame:row.frame,time:row.time,chains:{}};
 for(const [n,anchors] of Object.entries(row.anchors)){
  const [A,K,B,L,R]=anchors.map(world),v=[B[0]-A[0],B[1]-A[1]],d=dist(A,B),u=v.map(x=>x/d),normal=[-u[1],u[0]],k=[K[0]-A[0],K[1]-A[1]];
  const along=Math.max(.25*d,Math.min(.7*d,k[0]*u[0]+k[1]*u[1])),bend=raw.ik.find(c=>c.target===n+'_target').bendPositive===false?-1:1;
  // For a positive bend, the knee lies on the right of the hip-to-foot axis.
  const depth=Math.max(1.25,Math.min(.16*d,Math.abs(k[0]*normal[0]+k[1]*normal[1]))),J=[A[0]+along*u[0]-bend*depth*normal[0],A[1]+along*u[1]-bend*depth*normal[1]];
  const l1=dist(A,J),l2=dist(J,B),scale=l1/by[n+'_upper'].length;
  for(const [suffix,p] of [['upper',A],['target',B]])tracks[n+'_'+suffix].translate.push({time:row.time,x:p[0]-by[n+'_'+suffix].x,y:p[1]-by[n+'_'+suffix].y});
  tracks[n+'_upper'].scale.push({time:row.time,x:scale,y:scale});
  tracks[n+'_lower'].scale.push({time:row.time,x:l2/(scale*by[n+'_lower'].length),y:1});
  tracks[n+'_target'].rotate.push({time:row.time,value:Math.atan2(R[1]-L[1],R[0]-L[0])*180/Math.PI-baseAngle});
  record.chains[n]={hip:anchors[0],foot:anchors[2],kneeEstimate:[J[0]+432,480-J[1]],surfaceKnee:anchors[1],bend,footAxis:[anchors[3],anchors[4]],kneeInferenceAdjustmentPx:dist(J,K)};
 }
 records.push(record);
}
for(const n of chains)for(const suffix of ['upper','lower','target'])for(const keys of Object.values(tracks[n+'_'+suffix]))keys.push({...keys[0],time:1});
write('skin.json',raw);write('ik_fit.json',{automatic:false,method:'Consistent PSD material anchors transferred through source-observed contours; inferred knees constrained to accepted bend directions',frames:records});
const p=read('provenance.json');Object.assign(p,{hipPolicy:'PSD material hip/shoulder points mapped through source-observed silhouette cages; hidden anatomy estimated',scalePolicy:'Upper uniform scale and lower longitudinal scale fitted to inferred hip-knee-foot / shoulder-elbow-hand lengths',footOrientation:'Source-fitted local foot surface axis; no longer inferred from entire limb angle',ikObservationFile:'ik_fit.json',jointRecoveryAutomatic:false});write('provenance.json',p);
console.log('Updated 24 leg IK poses using consistent material anchors; accepted constraint topology and bend directions preserved.');
