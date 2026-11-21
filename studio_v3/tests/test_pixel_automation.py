import unittest, tempfile, copy, json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pixel_workbench as p
import pixel_automation as a
import numpy as np

class AutomaticSafety(unittest.TestCase):
 def test_observation_cache_never_crosses_video_identity(self):
  from unittest.mock import patch
  import pixel_detail
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp, patch.object(p,'STORE',Path(tmp)):
   source=p.clone();source['source']['identity']='same-video';p.write(p.folder(source['id'])/'project.json',source)
   target=p.clone();target['source']['identity']='different-video';p.write(p.folder(target['id'])/'project.json',target)
   f=source['frames'][0];digest=p.sha(p.folder(source['id'])/'frames'/f"{f['frame']:04}.png")
   name=f"vision_{f['frame']}_{digest[:16]}.json"
   p.write(p.folder(source['id'])/'automation'/name,dict(sourceSha256=digest,model=a.MODEL,contract=a.CONTRACT,detectorVersion=a.DETECTOR_VERSION,result={}))
   self.assertEqual(a.reuse_source_cache(target),0)
   target['source']['identity']='same-video';p.write(p.folder(target['id'])/'project.json',target)
   self.assertEqual(a.reuse_source_cache(target),1)
   self.assertTrue((p.folder(target['id'])/'automation'/name).exists())

 def test_generated_candidate_persists_without_acceptance(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp, patch.object(p,'STORE',Path(tmp)):
   x=p.clone();revision=x['revision']
   x['automation']=dict(contract=a.CONTRACT,inputFingerprint=a.fingerprint(x),accepted=False,issues=[])
   y=p.save_generated(x)
   self.assertEqual(y['revision'],revision+1)
   self.assertTrue(a.candidate(y))
   self.assertFalse(y['automation']['accepted'])
   self.assertIsNone(y['artifact'])

 def test_foreground_gaps_not_invented(self):
  rgb=np.full((80,80,3),255,np.uint8);rgb[20:60,20:60]=[180,110,90]
  polygons={n:[[20,20],[30,20],[30,60],[20,60]] for n in p.PARTS}
  masks,report=a.segment(rgb,polygons)
  self.assertLess(report['coverage'],.4)
  self.assertGreater(report['uncoveredPixels'],1000)
  self.assertFalse(masks['head'][40,50])
 def test_endpoint_support_is_separate_from_binding(self):
  f=dict(frame=0,points={},joints={})
  masks={n:np.zeros((80,80),np.uint8) for n in p.PARTS}
  for n,(r,t) in p.CHAINS.items():
   f['points'][r]=[20,20];f['joints'][n]=[30,40];f['points'][t]=[60,60]
   masks[n][15:45,15:45]=255
  issues=a.geometry(f,masks)
  self.assertEqual(sum(x['code']=='endpoint_outside_skin' for x in issues),4)
 def test_candidate_cannot_survive_input_changes(self):
  v=dict(source={'identity':'different-video'},frames=[],order=p.PARTS[:])
  v['automation']=dict(contract=a.CONTRACT,inputFingerprint=a.fingerprint(v))
  self.assertTrue(a.candidate(v))
  v['source']['identity']='another-video';self.assertFalse(a.candidate(v))
 def test_temporal_fit_keeps_one_bend_and_reports_disagreement(self):
  frames=[]
  for i,joint in enumerate(([30,40],[40,30],[30,40])):
   f=dict(frame=i,points={},joints={})
   for n,(root,end) in p.CHAINS.items():
    f['points'][root]=[20,20];f['points'][end]=[60,60];f['joints'][n]=list(joint)
   frames.append(f)
  issues=a.fit_sequence(frames)
  self.assertTrue(any(x['code']=='fit_disagreement' for x in issues))
  for n,(root,end) in p.CHAINS.items():
   signs=[]
   for f in frames:
    u=np.array(f['joints'][n])-f['points'][root];v=np.array(f['points'][end])-f['joints'][n]
    signs.append(u[0]*v[1]-u[1]*v[0]>=0)
   self.assertEqual(len(set(signs)),1)
 def test_source_mask_constrains_joint_fit(self):
  import pixel_pose
  frames=[];masks=[]
  for i in range(5):
   f=dict(frame=i,points={n:[40,20] for n in p.POINTS},joints={n:[70,45] for n in p.CHAINS})
   for n,(start,end) in p.CHAINS.items():f['points'][start]=[40,20];f['points'][end]=[40,70]
   frames.append(f);parts={n:np.zeros((90,90),np.uint8) for n in p.PARTS}
   for n in p.CHAINS:parts[n][15:76,30:51]=255
   masks.append(parts)
  issues,evidence=pixel_pose.fit(frames,masks)
  self.assertEqual(len(evidence),20)
  self.assertTrue(any(i['code']=='fit_disagreement' for i in issues))
  for f in frames:
   for q in f['joints'].values():self.assertLessEqual(q[0],51);self.assertGreaterEqual(q[0],30)
 def test_refined_partition_preserves_foreground_and_is_disjoint(self):
  rgb=np.full((80,80,3),255,np.uint8);rgb[10:70,10:70]=[180,110,90]
  polys={};refined={}
  for i,n in enumerate(p.PARTS):
   left=10+i*8;polys[n]=[[left,10],[left+8,10],[left+8,70],[left,70]]
   mask=np.zeros((80,80),np.uint8);mask[10:70,left:left+9]=255;refined[n]=mask
  masks,report=a.segment(rgb,polys,refined)
  occupancy=np.sum(np.stack([m>0 for m in masks.values()]),axis=0)
  self.assertTrue(np.all(occupancy[10:70,10:70]==1))
  self.assertEqual(int(occupancy[:10].sum()),0)
  self.assertTrue(report['partitionIsNotSemanticValidation'])
 def test_detection_retry_does_not_hide_permanent_failure(self):
  from unittest.mock import patch
  attempts=[]
  def flaky():
   attempts.append(1)
   if len(attempts)<2:raise OSError('network')
   return {'ok':True}
  with patch('pixel_automation.time.sleep'):
   self.assertEqual(a.retry_detection(flaky,lambda **kwargs:None,63),{'ok':True})
   self.assertEqual(len(attempts),2)
   with self.assertRaises(ValueError):a.retry_detection(lambda:(_ for _ in ()).throw(ValueError('invalid')),lambda **kwargs:None,63)
 def test_identity_repair_is_relative_not_screen_side(self):
  original=dict(points={},joints={},polygons={},hiddenParts=[])
  for limb,root,end in [('arm','shoulder','hand'),('leg','hip','foot')]:
   for side,x in [('near',70),('far',30)]:
    original['points'][root+'_'+side]=[x,20];original['points'][end+'_'+side]=[x,60]
    original['joints'][limb+'_'+side]=[x,40];original['polygons'][limb+'_'+side]=[[x,20],[x+5,60],[x,60]]
  swapped=copy.deepcopy(original)
  for field,prefixes in [('points',['shoulder','hand']),('joints',['arm']),('polygons',['arm'])]:
   for prefix in prefixes:
    akey,bkey=prefix+'_near',prefix+'_far';swapped[field][akey],swapped[field][bkey]=swapped[field][bkey],swapped[field][akey]
  repaired,notes=a.stabilize_identity(swapped,[original]*6)
  self.assertEqual(repaired['points'],original['points']);self.assertEqual(len(notes),1)
  unchanged,notes=a.stabilize_identity(original,[original]*6)
  self.assertEqual(unchanged,original);self.assertFalse(notes)
  crossed=copy.deepcopy(original);crossed['points']['hip_near'],crossed['points']['hip_far']=crossed['points']['hip_far'],crossed['points']['hip_near']
  unchanged,notes=a.stabilize_identity(crossed,[original]*6)
  self.assertEqual(unchanged,crossed);self.assertFalse(notes)
 def test_review_gate_and_conflicting_job(self):
  with tempfile.TemporaryDirectory(dir=p.ROOT) as temp:
   old=p.STORE;p.STORE=Path(temp)
   try:
    x=p.clone();x['baseline']=False
    x['automation']=dict(contract=a.CONTRACT,inputFingerprint=a.fingerprint(x),issues=[{'code':'coverage_gap'}],accepted=False)
    x['builtRevision']=x['revision'];x['artifact']={'audit':{'ok':True}};p.write(p.folder(x['id'])/'project.json',x)
    with self.assertRaisesRegex(ValueError,'诊断'):a.accept(dict(id=x['id'],revision=x['revision']))
    accepted=a.accept(dict(id=x['id'],revision=x['revision'],reviewedDiagnostics=True,note='用户明确通过'))
    self.assertEqual(len(accepted['automation']['issues']),1)
    self.assertTrue((p.folder(x['id'])/'acceptances/r1.json').is_file())
    x['automation']['issues']=[{'code':'runtime_rejected'}];p.write(p.folder(x['id'])/'project.json',x)
    with self.assertRaisesRegex(ValueError,'结构错误'):a.accept(dict(id=x['id'],revision=x['revision'],reviewedDiagnostics=True))
    x['automation']['issues']=[];p.write(p.folder(x['id'])/'project.json',x)
    self.assertTrue(a.accept(dict(id=x['id'],revision=x['revision']))['automation']['accepted'])
    with self.assertRaises(ValueError):a.accept(dict(id=x['id'],revision=99))
    p.write(p.folder(x['id'])/'automation/job.json',dict(state='running'))
    self.assertEqual(a.status(x['id'])['state'],'interrupted')
   finally:p.STORE=old

if __name__=='__main__':unittest.main()
