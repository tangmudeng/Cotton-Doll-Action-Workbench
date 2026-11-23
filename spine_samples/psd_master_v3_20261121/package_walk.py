from pathlib import Path
import json,hashlib,zipfile,shutil,cv2
import numpy as np
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent;OUT=HERE/'video_fit';OLD=HERE.parent/'psd_master_v2_20261121/video_fit'
audit=json.loads((OUT/'technical_audit.json').read_text());assert audit['technicalPass'] and audit['roundtripChecked']
shutil.copy2(OUT/'walk_updated_feet_r2.spine',OUT/'psd_walk_updated_feet.spine')
sheet=Image.new('RGB',(840,6*420),'#eeeeee');frames=[63,67,70,74,78,81]
for row,frame in enumerate(frames):
 im=np.asarray(Image.open(OUT/'reference_frames'/f'{frame:04}.png').convert('RGB'))
 matrix=np.array([[1.68,0,536-449*1.68-230],[0,1.68,582-289*1.68-110]],np.float32)
 ref=Image.fromarray(cv2.warpAffine(im,matrix,(560,800),borderValue=(235,235,235)))
 for col,(name,img) in enumerate([('video',ref),('previous',Image.open(OLD/'renders'/f'{frame:04}.png')),('updated',Image.open(OUT/'renders'/f'{frame:04}.png'))]):
  sheet.paste(img.resize((280,400)),(col*280,row*420+20));ImageDraw.Draw(sheet).text((col*280+8,row*420+4),f'{name} frame {frame}',fill='black')
sheet.save(OUT/'comparison.jpg',quality=93)
names=['psd_walk_updated_feet.spine','skin.json','skin.atlas','skin_0.png','source_manifest.json','provenance.json','technical_audit.json','atlas_report.json','motion_comparison.json','README.md','contact_sheet.jpg','comparison.jpg','roundtrip/skin.json']
files={n:(OUT/n).read_bytes() for n in names}
for folder in ['parts','runtime','reference_frames','previous']:
 for p in (OUT/folder).glob('*'):
  if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
html=(OUT/'review.html').read_text('utf8').replace('<a href="../psd_walk_updated_feet.zip">下载新版 Spine 工程</a> · ','')
files['review.html']=html.encode('utf8');files['SHA256.json']=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in files.items()},indent=2).encode()
dest=HERE/'psd_walk_updated_feet.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(dest) as z:
 assert z.testzip() is None
 checks=json.loads(z.read('SHA256.json'));assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in checks.items())
print(json.dumps({'files':len(files),'bytes':dest.stat().st_size,'crc':'passed','sha256':'passed','spine':'psd_walk_updated_feet.spine'}))
