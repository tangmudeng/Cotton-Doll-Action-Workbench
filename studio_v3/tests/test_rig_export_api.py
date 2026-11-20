"""Integration tests for export input validation and edited/custom part roundtrip."""
from pathlib import Path
import base64,copy,hashlib,json,sys,urllib.request,urllib.error,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import rig_export
p=json.loads((rig_export.CANDIDATE/'draft.json').read_text(encoding='utf-8'))
def request(project,origin='http://127.0.0.1:8770'):
    req=urllib.request.Request('http://127.0.0.1:8770/api/rig/export',data=json.dumps({'project':project}).encode(),headers={'Content-Type':'application/json','Origin':origin})
    try:
        with urllib.request.urlopen(req,timeout=120) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
assert request(p,'https://example.com')[0]==403
for mutate in [lambda p:p['source'].update(videoSha='wrong'),lambda p:p['source'].update(clipEnd=90),lambda p:p['parts'][0].update(parent='head'),lambda p:p['parts'][0].update(bbox=[0,0,12,12])]:
    bad=copy.deepcopy(p);mutate(bad);status,result=request(bad);assert status==422 and not result['ok'],(status,result)
edited=copy.deepcopy(p);head=next(x for x in edited['parts'] if x['id']=='head');head['name']='Edited head';head['texture']='data:image/png;base64,'+base64.b64encode((rig_export.CANDIDATE/'images/head.png').read_bytes()).decode()
head['keys'][2]['angle']+=1
status,result=request(edited);assert status==200,result
out=Path(result['directory'])
with zipfile.ZipFile(out/'walulu_walk_spine_4.2.43.zip') as z:
    assert z.testzip() is None
    manifest=json.loads(z.read('SHA256.json'))
    for n,h in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
    exported=json.loads(z.read('draft.json'));assert exported['parts'][0]['name']=='Edited head'
print(json.dumps({'passed':True,'negativeCases':5,'editedCustomPngRoundtrip':True,'zipShaEntries':len(manifest),'roundtrip':result['checks']}))
