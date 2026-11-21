import sys, unittest, tempfile, base64
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pixel_video as v
import pixel_workbench as p

class VideoAnalysis(unittest.TestCase):
    def test_repeated_motion_finds_period_without_duplicate_endpoint(self):
        phase=np.arange(72)*2*np.pi/12
        features=np.column_stack([np.sin(phase),np.cos(phase)])
        choices,_=v.proposals(features,list(range(72)),24,72)
        self.assertEqual(choices[0]['periodFrames'],12)
        self.assertEqual(choices[0]['end']-choices[0]['start']+1,12)
    def test_static_and_nonrepeating_are_not_declared_cycles(self):
        for features in [np.zeros((80,4)),np.arange(80)[:,None]/80]:
            choices,_=v.proposals(features,list(range(80)),24,80)
            self.assertEqual(choices[0]['kind'],'motion_segment')
    def test_upload_analyze_import_retains_source_and_frame_range(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp:
            root=Path(tmp);video=root/'input.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(96,64))
            for i in range(60):
                im=np.full((64,96,3),240,np.uint8)
                cv2.circle(im,(48+int(15*np.sin(i*2*np.pi/12)),35),12,(60,110,140),-1);writer.write(im)
            writer.release()
            with patch.object(v,'store',return_value=root/'analysis'),patch.object(p,'STORE',root/'projects'):
                a=v.analyze(dict(data=base64.b64encode(video.read_bytes()).decode(),name='new.mp4'))
                c=a['candidates'][0]
                self.assertTrue((p.ROOT/c['previewUrl'].lstrip('/')).is_file())
                project=p.import_video(dict(videoId=a['videoId'],name=a['name'],start=c['start'],end=c['end']))
                self.assertEqual(project['source']['identity'],p.sha(video))
                self.assertEqual([f['frame'] for f in project['frames']],list(range(c['start'],c['end']+1)))
                self.assertFalse(project.get('automation',{}).get('accepted',False))
                (root/'analysis'/a['videoId']/'source.mp4').write_bytes(b'changed')
                with self.assertRaises(ValueError):v.resolve(a['videoId'])
    def test_invalid_analysis_id_is_rejected(self):
        for value in ['../escape','a'*63,None]:
            with self.assertRaises(ValueError):v.resolve(value)

if __name__=='__main__':unittest.main(verbosity=2)
