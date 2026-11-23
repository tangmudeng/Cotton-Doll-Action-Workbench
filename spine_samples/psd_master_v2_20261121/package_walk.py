from pathlib import Path
import json,shutil,zipfile,hashlib
HERE=Path(__file__).resolve().parent;OUT=HERE/'video_fit'
audit=json.loads((OUT/'technical_audit.json').read_text())
assert audit['technicalPass'] and audit['roundtripChecked']
shutil.copy2(OUT/'walk_fit_r2.spine',OUT/'psd_walk_candidate.spine')
names=['psd_walk_candidate.spine','skin.json','skin.atlas','skin_0.png','source_manifest.json','provenance.json','technical_audit.json','atlas_report.json','README.md','contact_sheet.jpg','roundtrip/skin.json']
files={n:(OUT/n).read_bytes() for n in names}
for folder in ['parts','runtime','reference_frames']:
 for p in (OUT/folder).glob('*'):
  if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
html=(OUT/'review.html').read_text('utf8').replace('<a href="../psd_walk_candidate.zip">下载 Spine 检查包</a> · ','').replace(' · <a href="../review.html">原关节测试版</a>','')
files['review.html']=html.encode('utf8')
files['SHA256.json']=json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in files.items()},indent=2).encode()
dest=HERE/'psd_walk_candidate.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 for name,content in files.items():z.writestr(name,content)
with zipfile.ZipFile(dest) as z:assert z.testzip() is None
print(json.dumps({'file':str(dest),'files':len(files),'bytes':dest.stat().st_size,'crc':'passed'}))
