from pathlib import Path
import json,math,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont
R=Path(__file__).resolve().parent
frames=list(range(63,86))
near_hand=[[374,374],[379,375],[388,378],[398,380],[406,380],[415,380],[424,378],[427,378],[429,376],[427,376],[421,378],[415,381],[406,380],[398,379],[390,379],[380,376],[371,373],[363,369],[359,369],[358,370],[361,372],[367,374],[374,376]]
near_foot=[[423,449],[418,450],[410,450],[404,448],[397,447],[392,444],[388,442],[390,439],[389,438],[391,439],[394,442],[397,445],[403,447],[407,447],[414,448],[420,448],[427,446],[433,444],[436,442],[436,441],[433,445],[429,449],[424,449]]
far_foot=[[465,431],[467,431],[474,432],[484,433],[492,433],[499,432],[503,432],[503,432],[501,436],[499,439],[496,442],[490,444],[482,445],[472,438],[466,431],[464,425],[465,425],[467,425],[466,427],[464,428],[464,427],[465,429],[465,430]]
far_hand=[[515,356],[513,355],[511,356],[508,358],[502,360],[499,364],[496,367],[494,368],[494,368],[496,367],[499,365],[503,363],[507,357],[510,358],[514,359],[519,359],[523,359],[526,358],[527,358],[526,358],[523,358],[520,358],[516,358]]
# These are manually interpreted 2D anchors, NOT motion-capture ground truth.
# Occluded joint positions are deliberately tagged as inferred.
def ik(root,target,l1,l2,side):
 root=np.array(root,dtype=float);target=np.array(target,dtype=float);v=target-root;raw=np.linalg.norm(v);d=np.clip(raw,abs(l1-l2)+1e-5,l1+l2-1e-5);u=v/max(raw,1e-9);base=(l1*l1-l2*l2+d*d)/(2*d);height=math.sqrt(max(0,l1*l1-base*base));joint=root+u*base+np.array([-u[1],u[0]])*height*side;end=root+u*d
 return joint.tolist(),end.tolist(),float(abs(raw-d))
samples=[]
for i,f in enumerate(frames):
 bob=[0,0,-1,-2,-2,-1,0,1,2,3,2,1,0,-1,-2,-2,-1,0,1,2,2,1,0][i]
 p={'neck':[446,292+bob],'pelvis':[445,387+bob],
 'shoulder_near':[412,305+bob],'shoulder_far':[485,305+bob],
 'hip_near':[414,395+bob],'hip_far':[475,388+bob],
 'hand_near':near_hand[i],'hand_far':far_hand[i],'foot_near':near_foot[i],'foot_far':far_foot[i]}
 inferred=['neck','pelvis','shoulder_near','shoulder_far','hip_near','hip_far']
 if 67<=f<=74:inferred+=['hand_far']
 chains={}
 for name,root,end,l1,l2,side in [('arm_near','shoulder_near','hand_near',42,43,1),('arm_far','shoulder_far','hand_far',35,36,1),('leg_near','hip_near','foot_near',30,30,1),('leg_far','hip_far','foot_far',30,31,-1)]:
  joint,solved,error=ik(p[root],p[end],l1,l2,side);chains[name]={'root':root,'target':end,'joint':joint,'solvedTarget':solved,'lengths':[l1,l2],'bend':side,'reachError':error}
 phase='待确认：近脚较低 / 远脚抬起候选' if f<=66 or f>=78 else ('待确认：换步过渡' if f<=70 else ('待确认：远脚落下候选' if f<=76 else '待确认：换步过渡'))
 samples.append({'frame':f,'videoTime':f/24,'points':p,'inferred':inferred,'chains':chains,'contactHypothesis':phase})
data={'version':1,'source':json.loads((R/'source.json').read_text(encoding='utf8')),'range':[63,85],'fps':24,'periodCandidate':22/24,
 'method':'manual 2D silhouette-center annotation; elbow/knee positions solved by fixed-length 2-bone IK; not independently measured anatomy',
 'limits':['手脚中心为人工标注，仍需逐帧审核','肩髋和遮挡端点为推定','源视频没有地面，未锁脚；接触时刻仅为候选','画面内脚的移动可能包含原地行走与透视，不等于世界坐标滑步','第85帧保留原始标注差异，没有强制改成第63帧'],
 'samples':samples}
# Observe local bottom contours only where feet are not mutually occluded.
for sample in samples:
 image=np.array(Image.open(R/'frames'/f"{sample['frame']:04}.png").convert('RGB')).astype(float)
 sample['soleContours']={}
 for side in ['near','far']:
  center=sample['points']['foot_'+side];x,y=map(int,center)
  if side=='far' and abs(x-sample['points']['foot_near'][0])<48:
   sample['soleContours'][side]={'visible':False,'reason':'被近脚遮挡，不能独立读取脚底'};continue
  patch=image[y+4:min(480,y+32),x-9:x+10];mask=(patch[:,:,0]-patch[:,:,2]>18)&(patch[:,:,0]>90)
  ys,xs=np.where(mask)
  if len(ys):
   bottom=int(ys.max()+y+4);sample['soleContours'][side]={'visible':True,'point':[x,bottom],'method':'local source contour; not a ground-contact claim'}
(R/'motion_annotations.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
# Source-only candidate windows. These are NOT final isolated attachments.
candidates=[
('near_arm_front',70,[382,288,454,405],'近侧手前摆','手形完整，肩根仍被头部遮挡'),
('near_arm_back',82,[332,288,429,394],'近侧手后摆','保留侧边轮廓，不与前摆手强行拼成单张'),
('far_arm_open',63,[482,292,535,381],'远侧手展开','躯干侧的肩根和上臂内缘不可见'),
('far_arm_back',82,[484,290,546,380],'远侧手另一摆姿','可作为姿态替换，不能据此虚构被遮挡上臂'),
('shorts_open',70,[366,347,505,419],'裤衩迈步','近侧手遮住左腰部分；裆部及裤口取原像素'),
('shorts_cross',82,[370,353,508,418],'裤衩交叉步','保留原帧轮廓；左腰仍被手臂遮挡'),
('near_leg_open',70,[352,379,439,466],'近腿迈步','上腿根在裤衩下，不能称为完整拆件'),
('far_leg_open',70,[448,374,540,459],'远腿迈步','完整脚形可见；髋根遮挡'),
('feet_cross',82,[383,384,496,470],'交叉步双脚','远脚部分遮挡，只作遮挡关系参考')]
(R/'source_candidates').mkdir(exist_ok=True)
records=[]
for name,f,box,label,limit in candidates:
 path=R/'source_candidates'/f'{name}.png';src=Image.open(R/'frames'/f'{f:04}.png');crop=src.crop(box);crop.save(path)
 assert np.array_equal(np.asarray(crop),np.asarray(src)[box[1]:box[3],box[0]:box[2]])
 records.append({'name':name,'label':label,'frame':f,'time':f/24,'box':box,'file':path.relative_to(R).as_posix(),'limitations':limit,'pixelExact':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(R/'asset_sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
err=max(ch['reachError'] for sample in samples for ch in sample['chains'].values())
metrics={'frames':23,'chainsPerFrame':4,'maxIKReachError':err,'maxBoneLengthError':max(abs(math.dist(s['points'][c['root']],c['joint'])-c['lengths'][0]) for s in samples for c in s['chains'].values()),'pixelExactCrops':len(records),'motionAccuracyValidated':False,'groundContactsValidated':False,'sourceLoopEndpointDifference':{k:math.dist(samples[0]['points'][k],samples[-1]['points'][k]) for k in ['hand_near','hand_far','foot_near','foot_far']}}
assert err<1e-4
(R/'checks.json').write_text(json.dumps(metrics,indent=2),encoding='utf8')
print(json.dumps(metrics))

