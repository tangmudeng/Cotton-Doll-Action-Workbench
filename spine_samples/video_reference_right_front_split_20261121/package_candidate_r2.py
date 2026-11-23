from pathlib import Path
import hashlib,json,zipfile

HERE=Path(__file__).resolve().parent;OUT=HERE/'candidate_r2'
audit=json.loads((OUT/'technical_audit.json').read_text('utf8'))
assert audit['technicalPass'] and audit['roundtripChecked'] and not audit['humanAccepted']
selection=json.loads((HERE/'selection.json').read_text('utf8'))
manifest=json.loads((OUT/'source_manifest.json').read_text('utf8'))
assert hashlib.sha256(Path(selection['sourceVideo']).read_bytes()).hexdigest()==selection['sourceSha256']
assert hashlib.sha256(Path(manifest['source']).read_bytes()).hexdigest()==manifest['sha256']
for row in selection['frames']:
    frame=HERE/'frames'/f"{row['frame']:04}.png"
    assert hashlib.sha256(frame.read_bytes()).hexdigest()==row['sha256']
files={}
for name in ['right_front_split_psd.spine','skin.json','skin.atlas','skin_0.png','source_manifest.json','provenance.json','motion_observations.json','surface_fit.json','ik_fit.json','silhouette_audit.json','spine_export_audit.json','technical_audit.json','README.md','review.html','contact_sheet.jpg','body_contact_sheet.jpg','six_pose_comparison.jpg','atlas_report.json','roundtrip/skin.json']:
    files[name]=(OUT/name).read_bytes()
# A standalone unpacked preview must not depend on its parent download link.
files['review.html']=files['review.html'].decode('utf8').replace('<a href="../right_front_split_psd_candidate_r2.zip">下载完整 Spine r2 包</a> · ','').encode('utf8')
for folder in ['parts','runtime']:
    for p in (OUT/folder).rglob('*'):
        if p.is_file():files[p.relative_to(OUT).as_posix()]=p.read_bytes()
for row in selection['frames']:
    frame=HERE/'frames'/f"{row['frame']:04}.png"
    files[f"reference_frames/{frame.name}"]=frame.read_bytes()
hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
files['SHA256.json']=json.dumps(hashes,indent=2).encode('utf8')
dest=HERE/'right_front_split_psd_candidate_r2.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items():z.writestr(name,data)
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    expected=json.loads(z.read('SHA256.json'))
    assert all(hashlib.sha256(z.read(name)).hexdigest()==digest for name,digest in expected.items())
    assert len([n for n in z.namelist() if n.startswith('parts/') and n.endswith('.png')])==7
report={'files':len(files),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'crcPassed':True,'fileHashesPassed':True,'humanAccepted':False}
(HERE/'package_audit_r2.json').write_text(json.dumps(report,indent=2),'utf8')
print(json.dumps(report))
