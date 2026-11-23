from pathlib import Path
import json,zipfile,hashlib
HERE=Path(__file__).resolve().parent;OUT=HERE/'video_fit'
audit=json.loads((OUT/'technical_audit.json').read_text());assert audit['technicalPass'] and audit['acceptedRigEquivalent'] and audit['roundtripChecked']
names=['psd_bound_pixel_sync.spine','skin.json','skin.atlas','skin_0.png','source_manifest.json','provenance.json','attachment_registration.json','accepted_reference_bones.json','reference_times.json','technical_audit.json','atlas_report.json','README.md','contact_sheet.jpg','roundtrip/skin.json']
files={n:(OUT/n).read_bytes() for n in names}
for folder in ['parts','runtime','reference_frames']:
 for p in (OUT/folder).glob('*'):
  if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
html=(OUT/'review.html').read_text('utf8').replace('<a href="../psd_bound_pixel_sync.zip">下载绑定修正工程</a> · ','');files['review.html']=html.encode('utf8')
files['SHA256.json']=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in files.items()},indent=2).encode()
dest=HERE/'psd_bound_pixel_sync.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(dest) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in json.loads(z.read('SHA256.json')).items())
print(json.dumps({'files':len(files),'bytes':dest.stat().st_size,'crc':'passed','sha256':'passed'}))
