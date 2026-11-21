import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pixel_workbench as p
from pixel_atlas import pack
from pixel_vision_response import parse_response

class Reliability(unittest.TestCase):
 def test_json_response_is_logged_and_rejected_without_guessing(self):
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp:
   path=Path(tmp)/'frames'/'0071.png';path.parent.mkdir()
   for text,reason in [('{bad: 1}','stop'),('{"points":{}}','length')]:
    with self.assertRaises(ValueError):parse_response({'choices':[{'finish_reason':reason,'message':{'content':text}}]},path,'detail')
   value=parse_response({'choices':[{'message':{'content':'```json\n{"points":{}}\n```'}}]},path,'detail')
   self.assertEqual(value,{'points':{}})
   self.assertEqual(len(list((Path(tmp)/'automation/responses').glob('*.json'))),3)
 def test_atlas_exact_dedup_and_every_region_pixels(self):
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp:
   out=Path(tmp);a=Image.new('RGBA',(30,20),(120,60,80,255));b=Image.new('RGBA',(20,25),(80,130,90,255))
   report=pack([('a',a),('same',a.copy()),('different',b)],out,64)
   self.assertEqual(report['exactDuplicates'],1)
   self.assertLess(report['rgbaBytes'],2*64*64*4)
   text=(out/'skin.atlas').read_text();self.assertIn('same\n',text)
   import re
   for name,im in [('a',a),('same',a),('different',b)]:
    for block in text.strip().split('\n\n'):
     found=re.search(r'(?:^|\n)'+name+r'\n  rotate: false\n  xy: (\d+), (\d+)',block)
     if found:
      x,y=map(int,found.groups());page=Image.open(out/block.splitlines()[0]);self.assertTrue(np.array_equal(np.array(page.crop((x,y,x+im.width,y+im.height))),np.array(im)));break
    else:self.fail('missing region')
 def test_current_project_manual_range_creates_independent_project(self):
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp,patch.object(p,'STORE',Path(tmp)):
   import cv2
   root=Path(tmp);video=root/'test.mp4';writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(64,64))
   for i in range(10):writer.write(np.full((64,64,3),i*20,np.uint8))
   writer.release()
   import base64
   first=p.import_video(dict(data=base64.b64encode(video.read_bytes()).decode(),start=0,end=3))
   second=p.import_video(dict(projectId=first['id'],start=4,end=8))
   self.assertEqual([f['frame'] for f in second['frames']],[4,5,6,7,8])
   self.assertNotEqual(first['id'],second['id'])
   self.assertEqual(p.load(first['id'])['source']['end'],3)
   for end in [3.5,10,-1]:
    with self.assertRaises(ValueError):p.import_video(dict(projectId=first['id'],start=0,end=end))

 def test_bounded_parallel_detection_retains_good_frames_after_failure(self):
  import pixel_automation as a,pixel_detail,threading,time,copy
  with tempfile.TemporaryDirectory(dir=p.ROOT) as tmp,patch.object(p,'STORE',Path(tmp)):
   x=p.clone();x['frames']=x['frames'][:3];x['baseline']=False
   p.write(p.folder(x['id'])/'project.json',x)
   lock=threading.Lock();active=0;maximum=0
   def infer(path,w,h):
    nonlocal active,maximum
    with lock:active+=1;maximum=max(maximum,active)
    time.sleep(.03)
    with lock:active-=1
    if path.stem=='0064':raise ValueError('fixture bad response')
    return {'points':{}}
   with patch.object(a,'infer',side_effect=infer),patch.object(pixel_detail,'infer',side_effect=lambda path,v:v),patch.object(a,'reuse_source_cache',return_value=0),patch.object(a,'retry_detection',side_effect=lambda fn,progress,frame:fn()):
    a.worker(copy.deepcopy(x),dict(state='running',revision=1))
   self.assertEqual(maximum,2)
   self.assertEqual(p.read(p.folder(x['id'])/'automation/job.json')['state'],'failed')
   self.assertEqual(len(list((p.folder(x['id'])/'automation').glob('vision_*.json'))),2)
   self.assertTrue((p.folder(x['id'])/'automation/events.jsonl').is_file())

if __name__=='__main__':unittest.main(verbosity=2)
