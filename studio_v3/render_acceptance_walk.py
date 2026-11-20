from pathlib import Path
import importlib.util,json,sys,numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'generated_rig/walk_acceptance_v1'
spec=importlib.util.spec_from_file_location('read_only_render',ROOT/'build_profile_walk.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
s=json.loads((OUT/'walulu_walk.json').read_text());pack=json.loads((OUT/'packing.json').read_text());page=Image.open(OUT/'walulu_walk.png').convert('RGBA');meshes=h.decode_meshes(s,pack['regions'])
report={};T=22/24
for name,m in meshes.items():
 vals=[h.mesh_geometry(m,h.solve(s,'walk',float(t)))[0] for t in np.linspace(0,T,133)]
 report[name]={'minAreaRatio':min(v['minAreaRatio'] for v in vals),'flips':sum(v['flips'] for v in vals),'collapsed':sum(v['collapsed'] for v in vals)}
print(json.dumps(report));(OUT/'geometry_checks.json').write_text(json.dumps(report,indent=2))
frames=[];sheet=Image.new('RGB',(6*320,640),'#d9e1e8');d=ImageDraw.Draw(sheet)
for i,f in enumerate([66,70,74,78,82,86]):
 im,stats=h.render(s,page,pack['regions'],meshes,'walk',(f-66)/24);im.save(OUT/f'render_{f}.png');frames.append(im)
 view=im.crop((170,90,600,700));view.thumbnail((320,440));sheet.paste(view,(i*320,30),view)
 detail=im.crop((270,425,530,690));detail.thumbnail((300,190));sheet.paste(detail,(i*320,445),detail)
 d.text((i*320+10,5),f'frame {f}',fill='black')
sheet.save(OUT/'review.png')
