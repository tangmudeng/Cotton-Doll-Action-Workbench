"""Integration tests: source isolation, stale-export guard, actual runtime and CLI."""
import base64, copy, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pixel_workbench as p
import cv2
import numpy as np

class PixelPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='pixel_test_',dir=p.ROOT)
        cls.previous=p.STORE;p.STORE=Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls):
        p.STORE=cls.previous;cls.temp.cleanup()

    def test_review_package_does_not_grant_acceptance(self):
        import pixel_automation as a
        import zipfile
        x=p.clone();x=p.build(x['id'])
        x['automation']=dict(contract=a.CONTRACT,inputFingerprint=a.fingerprint(x),accepted=False,issues=[])
        p.write(p.folder(x['id'])/'project.json',x)
        with self.assertRaises(ValueError):p.export(x['id'],x['revision'])
        result=p.export(x['id'],x['revision'],review=True)
        self.assertEqual(result['kind'],'technical_review')
        self.assertEqual(p.load(x['id'])['exports']['technical_review']['zipUrl'],result['zipUrl'])
        self.assertFalse(p.load(x['id'])['automation']['accepted'])
        with zipfile.ZipFile(p.ROOT/result['zipUrl'].lstrip('/')) as z:
            status=json.loads(z.read('REVIEW_STATUS.json'))
            self.assertTrue(status['requiresVisualReview'])
            self.assertIn('walk.spine',z.namelist())

    def test_export_rejects_mismatched_build_inputs(self):
        x=p.clone();d=p.folder(x['id'])/'fixture_build';d.mkdir()
        p.write(d/'project.json',x)
        p.verify_artifact(x,d)
        altered=copy.deepcopy(x);altered['frames'][0]['points']['neck'][0]+=1
        with self.assertRaisesRegex(ValueError,'不一致'):p.verify_artifact(altered,d)
        altered=copy.deepcopy(x);altered['source']['identity']='another-video'
        with self.assertRaisesRegex(ValueError,'不一致'):p.verify_artifact(altered,d)
        altered=copy.deepcopy(x);altered['id']='px_111111111111'
        with self.assertRaisesRegex(ValueError,'不一致'):p.verify_artifact(altered,d)

    def test_baseline_exact_and_stale_revision(self):
        self.assertEqual(p.freeze_check(),166)
        x=p.clone();built=p.build(x['id']);out=p.ROOT/built['artifact']['base'].lstrip('/')
        for name in ['skin.json','skin.atlas','skin.png']:
            self.assertEqual(p.sha(out/name),p.sha(p.BASE/name))
        self.assertEqual(built['artifact']['audit']['intraFrameDrift'],0)
        y=copy.deepcopy(built);y['frames'][0]['points']['neck'][0]+=1
        saved=p.save(dict(id=y['id'],revision=y['revision'],project=y))
        with self.assertRaises(ValueError):p.export(y['id'],y['revision'])
        with self.assertRaises(ValueError):p.save(dict(id=y['id'],revision=y['revision'],project=y))
        self.assertIsNone(saved['artifact'])
        self.assertTrue((p.folder(y['id'])/'revisions/r1.json').is_file())
        changed=p.build(y['id']);self.assertFalse(changed['artifact']['acceptedCopy'])
        self.assertLess(changed['artifact']['audit']['sourceError'],.001)
        exported=p.export(y['id'],saved['revision'])
        self.assertLess(exported['audit']['roundtripMaxDelta'],.12)
        again=p.export(y['id'],saved['revision'])
        self.assertNotEqual(again['zipUrl'],exported['zipUrl'])
        self.assertEqual(again['audit'],exported['audit'])

    def test_fully_occluded_attachment_hides_and_roundtrips(self):
        x=p.clone();x['frames'][1]['parts']['arm_far']['visible']=False
        x=p.save(dict(id=x['id'],revision=x['revision'],project=x))
        built=p.build(x['id']);out=p.ROOT/built['artifact']['base'].lstrip('/')
        raw=p.read(out/'skin.json')
        self.assertIsNone(raw['animations']['reference_cycle']['slots']['arm_far']['attachment'][1]['name'])
        self.assertEqual(built['artifact']['audit']['attachments'],160)
        result=p.export(x['id'],x['revision'])
        self.assertEqual(result['audit']['intraFrameDrift'],0)

    def test_new_video_dimensions_and_review_gate(self):
        video=Path(self.temp.name)/'synthetic.mp4'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),12,(320,240))
        for i in range(3):
            im=np.zeros((240,320,3),np.uint8);im[:]=[90,120,180]
            cv2.circle(im,(160+i,120),30,(180,200,220),-1);writer.write(im)
        writer.release()
        x=p.import_video(dict(data=base64.b64encode(video.read_bytes()).decode(),name='test.mp4',start=0,end=2))
        self.assertEqual(x['source']['width'],320)
        with self.assertRaises(ValueError):p.build(x['id'])
        with self.assertRaises(ValueError):p.seed_annotation(dict(id=x['id'],revision=x['revision']))
        points=dict(neck=[160,60],pelvis=[160,150],shoulder_near=[140,80],shoulder_far=[180,80],
            hip_near=[145,150],hip_far=[175,150],hand_near=[115,135],hand_far=[205,135],foot_near=[140,210],foot_far=[185,210])
        joints=dict(arm_near=[115,100],arm_far=[190,110],leg_near=[130,180],leg_far=[190,175])
        for i,f in enumerate(x['frames']):
            f['points']={k:[v[0]+i,v[1]] for k,v in points.items()}
            f['joints']={k:[v[0]+i,v[1]] for k,v in joints.items()}
            f['poseReviewed']=True
            f['parts']={n:dict(polygon=[[100+i,40],[220+i,40],[220+i,220],[100+i,220]],reviewed=True) for n in p.PARTS}
        x=p.save(dict(id=x['id'],revision=x['revision'],project=x));x=p.build(x['id'])
        self.assertEqual(x['artifact']['audit']['checks'],15)
        self.assertEqual(x['artifact']['audit']['ik'],4)
        self.assertLess(x['artifact']['audit']['jointError'],.2)
        self.assertEqual(p.export(x['id'],x['revision'])['audit']['intraFrameDrift'],0)
        # Tracking is a draft operation and clears downstream approvals.
        x=p.track(dict(id=x['id'],revision=x['revision'],index=0))
        self.assertFalse(x['frames'][1]['poseReviewed'])
        self.assertTrue(all(not q['reviewed'] for q in x['frames'][1]['parts'].values()))
        with self.assertRaises(ValueError):p.build(x['id'])

    def test_reject_invalid_input(self):
        for pid in ['../escape','px_../../etc','',None]:
            with self.assertRaises(ValueError):p.folder(pid)
        x=p.clone();x['frames'][0]['points']['neck']=[float('nan'),0]
        with self.assertRaises(ValueError):p.save(dict(id=x['id'],revision=x['revision'],project=x))
        with self.assertRaises(ValueError):p.import_video(dict(data='%%%%',start=0,end=2))
        with self.assertRaises(ValueError):p.import_video(dict(data=base64.b64encode(b'invalid').decode(),start=0,end=121))

if __name__=='__main__':unittest.main(verbosity=2)
