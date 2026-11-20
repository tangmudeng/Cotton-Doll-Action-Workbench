const assert=require('node:assert/strict');
const M=require('../rig-studio-model.js');
const source={taskId:'test',characterId:null,videoSha:'abc',imageSha:'def'};
const p={schema:'walulu-video-rig-draft/1',source,fps:24,duration:16/24,productionApproved:false,parts:M.IDS.map((id,i)=>({id,name:id,bbox:[0,0,40,80],pivot:[20,10],order:i,visible:true,texture:'legacy',polygon:[],evidence:[],keys:[]}))};
assert.deepEqual(M.validate(p,source),p);assert.notEqual(M.validate(p,source),p);
for(const mutate of [x=>x.productionApproved=true,x=>x.source.videoSha='other',x=>x.parts[1].id=x.parts[0].id,x=>x.parts[0].texture='https://other.example/image.png',x=>x.parts[0].pivot=[NaN,0],x=>x.parts[0].evidence=[{frame:2,visibility:'visible',note:'bad',points:[]}],x=>x.parts[0].bbox=[0,0,0,0]]){const copy=M.clone(p);mutate(copy);assert.throws(()=>M.validate(copy,source));}
let keys=M.putKey([],{time:0,x:0,y:0,angle:0,interpolation:'linear'},p.duration);
keys=M.putKey(keys,{time:p.duration/2,x:12,y:4,angle:30,interpolation:'linear'},p.duration);
assert.equal(keys.length,3);assert.equal(keys[2].angle,keys[0].angle);
assert.deepEqual(M.pose(keys,p.duration/4),{x:6,y:2,angle:15});
keys=M.putKey(keys,{time:p.duration,x:2,y:3,angle:4,interpolation:'stepped'},p.duration);
assert.equal(keys[0].angle,4);assert.equal(keys[0].x,2);assert.equal(keys[2].angle,4);
assert.equal(M.pose(keys,p.duration/4).angle,4);
assert.throws(()=>M.putKey(keys,{time:-1,x:0,y:0,angle:0},p.duration));
assert.throws(()=>M.putKey(keys,{time:0,x:0,y:0,angle:181},p.duration));
assert.deepEqual(M.cropBounds([[10.2,20.2],[30.2,20.2],[30.2,50.2]]),[10,20,31,51]);
assert.throws(()=>M.cropBounds([[0,0],[1,1],[2,2]]));
const restored=M.clone(p);restored.parts[0].keys=keys;restored.parts[0].evidence=[{frame:72,visibility:'uncertain',note:'crossing arm identity unresolved',points:[[1,2],[3,4]]}];assert.deepEqual(M.validate(JSON.parse(JSON.stringify(restored)),source),restored);
console.log('PASS: source identity, 7-part integrity, import rejection, loop endpoint pairing, interpolation, polygon crop, draft round trip');

const interior=M.putKey([],{time:p.duration/2,x:5,y:0,angle:10,interpolation:'linear'},p.duration);
assert.equal(interior.length,3);assert.equal(interior[0].angle,0);assert.equal(interior[2].angle,0);
const mismatch=M.clone(p);mismatch.parts[0].keys=M.clone(interior);mismatch.parts[0].keys[2].angle=1;
assert.throws(()=>M.validate(mismatch,source),/首尾/);
console.log('PASS: first interior key creates neutral endpoints; mismatched imported loops rejected');

const localSource={...source,clipStart:68,clipEnd:88,fps:24,frameCount:107};
const local=M.clone(p);local.source=localSource;local.duration=20/24;
local.parts[1].pivot=[20,20];local.parts[0].parent='body';
let transforms=M.matrices(local.parts,0);assert.deepEqual(M.apply(transforms.get('head'),[10,30]),[10,30]);
local.parts[1].keys=M.putKey([],{time:0,x:10,y:5,angle:90,interpolation:'linear'},local.duration);
transforms=M.matrices(local.parts,0);const actual=M.apply(transforms.get('head'),[20,30]);assert.ok(Math.abs(actual[0]-20)<1e-8&&Math.abs(actual[1]-25)<1e-8);
assert.doesNotThrow(()=>M.validate(local,localSource));assert.throws(()=>M.validate(local,source));
const cyclic=M.clone(local);cyclic.parts[1].parent='head';assert.throws(()=>M.validate(cyclic,localSource),/循环/);
const limb={pivot:[0,0],joint:[0,40],tip:[0,80]};assert.deepEqual(M.deform(limb,[0,0],30),[0,0]);assert.deepEqual(M.deform(limb,[0,40],30),[0,40]);assert.deepEqual(M.deform(limb,[6,65],0),[6,65]);
const tip=M.deform(limb,[0,80],30);assert.ok(Math.abs(tip[0]+20)<1e-8);assert.ok(Math.abs(Math.hypot(tip[0],tip[1]-40)-40)<1e-8);
const bent=M.putKey([],{time:local.duration/2,x:0,y:0,angle:0,bend:30,interpolation:'linear'},local.duration);assert.equal(M.pose(bent,local.duration/4).bend,15);
assert.throws(()=>M.putKey([],{time:0,x:0,y:0,angle:0,bend:61},local.duration));
console.log('PASS: imported-video identity, variable clip duration, parent transforms, cycle rejection, skinning anchors, distal length and bend interpolation');
