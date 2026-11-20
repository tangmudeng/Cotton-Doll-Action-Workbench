from pathlib import Path
import copy, hashlib, json, shutil
R=Path(__file__).resolve().parent.parent
B=R/"pixel_bound_controls_20261120"
O=R/"pixel_sync_20261120"
O.mkdir(exist_ok=True)
for n in ["parts","runtime"]:
    shutil.copytree(B/n,O/n,dirs_exist_ok=True)
for n in ["skin.atlas","skin.png","pixel_manifest.json","attachment_provenance.json"]:
    shutil.copy2(B/n,O/n)
data=json.loads((B/"skin.json").read_text())
anim=data["animations"]["reference_cycle"]
data["skeleton"]["fps"]=24
data["skeleton"]["images"]="./parts/"
def timelines(obj):
    if isinstance(obj,dict):
        for v in obj.values():
            yield from timelines(v)
    elif isinstance(obj,list) and obj and isinstance(obj[0],dict):
        yield obj
count=0
for group in ["bones","ik","transform","paths","deform"]:
    for track in timelines(anim.get(group,{})):
        for key in track:
            key["time"]=round(round(key.get("time",0)*24)/24,7)
            key["curve"]="stepped"
            count+=1
        last=copy.deepcopy(track[0])
        last["time"]=round(23/24,7)
        track.append(last)
for track in timelines(anim.get("slots",{})):
    for key in track:
        key["time"]=round(round(key.get("time",0)*24)/24,7)
    last=copy.deepcopy(track[0])
    last["time"]=round(23/24,7)
    track.append(last)
(O/"import_sync.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (O/"parts").glob("*.png")}
assert all(v==hashlib.sha256((B/"parts"/k).read_bytes()).hexdigest() for k,v in hashes.items())
(O/"source_hashes.json").write_text(json.dumps(hashes,indent=2))
print(json.dumps({"steppedKeys":count,"unchangedParts":len(hashes),"fps":24,"duration":23/24}))
