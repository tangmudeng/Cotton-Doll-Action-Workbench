from pathlib import Path
import hashlib,json,zipfile

HERE=Path(__file__).resolve().parent;OUT=HERE/'candidate'
audit=json.loads((OUT/'technical_audit.json').read_text('utf8'))
assert audit['technicalPass'] and audit['roundtripChecked'] and not audit['humanAccepted']
selection=json.loads((HERE/'selection.json').read_text('utf8'))
assert hashlib.sha256(Path(selection['sourceVideo']).read_bytes()).hexdigest()==selection['sourceSha256']
manifest=json.loads((OUT/'source_manifest.json').read_text('utf8'))
assert hashlib.sha256(Path(manifest['source']).read_bytes()).hexdigest()==manifest['sha256']
for row in selection['frames']:
    row['file']='reference_frames/'+Path(row['file']).name
    assert hashlib.sha256((OUT/row['file']).read_bytes()).hexdigest()==row['sha256']
(OUT/'selection.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2),'utf8')
provenance=json.loads((OUT/'provenance.json').read_text('utf8'));provenance['sourceVideo']=selection
(OUT/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),'utf8')
names=['right_front_split_psd.spine','skin.json','skin.atlas','skin_0.png','source_manifest.json','atlas_report.json','provenance.json','selection.json','motion_observations.json','cycle_diagnostics.json','technical_audit.json','README.md','contact_sheet.jpg','body_contact_sheet.jpg','browser_check.png','roundtrip/skin.json']
files={name:(OUT/name).read_bytes() for name in names}
for folder in ['parts','runtime','reference_frames']:
    for p in (OUT/folder).iterdir():
        if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
html=(OUT/'review.html').read_text('utf8').replace('<a href="../right_front_split_psd_candidate.zip">下载 Spine 候选工程</a> · ','')
files['review.html']=html.encode('utf8')
hashes={n:hashlib.sha256(v).hexdigest() for n,v in files.items()};files['SHA256.json']=json.dumps(hashes,indent=2).encode('utf8')
dest=HERE/'right_front_split_psd_candidate.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
    for name,value in files.items():z.writestr(name,value)
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in json.loads(z.read('SHA256.json')).items())
    assert len([n for n in z.namelist() if n.startswith('parts/') and n.endswith('.png')])==7
report=dict(files=len(files),bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),crcPassed=True,fileHashesPassed=True,humanAccepted=False)
(HERE/'package_audit.json').write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(report))
