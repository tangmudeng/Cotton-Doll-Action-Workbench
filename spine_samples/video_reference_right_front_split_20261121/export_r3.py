"""Always import into a new Spine project; re-importing appends skeletons."""
from pathlib import Path
import json,shutil,subprocess,time

HERE=Path(__file__).resolve().parent;OUT=HERE/'candidate_r3'
stage=OUT/('export_'+str(time.time_ns()));stage.mkdir()
exe='E:/MyTools/Spine/Spine.com'
commands=[['-i',str(OUT/'skin.json'),'-o',str(stage/'right_front_split_psd.spine'),'-r','right_front_split_psd'],
          ['-i',str(stage/'right_front_split_psd.spine'),'-o',str(stage/'roundtrip'),'-e','json']]
for args in commands:
    result=subprocess.run([exe,'-u','4.2.43']+args,cwd=OUT,capture_output=True,timeout=90)
    if result.returncode:raise RuntimeError('Spine command failed: '+str(result.returncode))
files=list((stage/'roundtrip').glob('*.json'))
assert len(files)==1,'Export must contain exactly one skeleton'
data=json.loads(files[0].read_text('utf8'))
assert set(data['animations'])=={'video_right_front_split_59_82','psd_bind_pose'}
shutil.copy2(stage/'right_front_split_psd.spine',OUT/'right_front_split_psd.spine')
(OUT/'roundtrip').mkdir(exist_ok=True);shutil.copy2(files[0],OUT/'roundtrip/skin.json')
(OUT/'spine_export_audit.json').write_text(json.dumps({'freshProject':True,'skeletons':1,'exportedAnimationNames':list(data['animations']),'stage':stage.name},indent=2),'utf8')
print('Fresh Spine 4.2.43 project exported and reimported: one skeleton, two animations.')
