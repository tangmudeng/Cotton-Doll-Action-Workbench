from pathlib import Path
import importlib.util,json,sys,numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'generated_rig/video_parts_v3'
spec=importlib.util.spec_from_file_location('read_only_render',ROOT/'build_profile_walk.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
import subprocess
subprocess.run(['node',str(ROOT/'export_rig_cli.cjs'),str(OUT/'draft.json'),str(OUT),str(OUT/'reference.json')],check=True)
pack=json.loads((OUT/'packing.json').read_text());page=Image.new('RGBA',(pack['width'],pack['height']))
for name,r in pack['regions'].items():
 im=Image.open(OUT/'images'/f'{name}.png').convert('RGBA');page.paste(Image.fromarray(np.pad(np.asarray(im),((4,4),(4,4),(0,0)),mode='edge')),(r['x']-4,r['y']-4))
page.save(OUT/'walulu_walk.png')
s=json.loads((OUT/'walulu_walk.json').read_text());pack=json.loads((OUT/'packing.json').read_text());page=Image.open(OUT/'walulu_walk.png').convert('RGBA');meshes=h.decode_meshes(s,pack['regions'])
report={};T=22/24
for name,m in meshes.items():
 vals=[h.mesh_geometry(m,h.solve(s,'walk',float(t)))[0] for t in np.linspace(0,T,133)]
 report[name]={'minAreaRatio':min(v['minAreaRatio'] for v in vals),'flips':sum(v['flips'] for v in vals),'collapsed':sum(v['collapsed'] for v in vals)}
print(json.dumps(report));(OUT/'geometry_checks.json').write_text(json.dumps(report,indent=2))
frames=[];sheet=Image.new('RGB',(6*320,640),'#d9e1e8');d=ImageDraw.Draw(sheet)
for i,f in enumerate([66,70,74,78,82,86]):
 im,stats=h.render(s,page,pack['regions'],meshes,'walk',(f-66)/24);im.save(OUT/f'render_{f}.png');frames.append(im)
 view=im.crop((130,40,650,750));view.thumbnail((320,440));sheet.paste(view,(i*320,30),view)
 detail=im.crop((260,425,560,750));detail.thumbnail((300,190));sheet.paste(detail,(i*320,445),detail)
 d.text((i*320+10,5),f'frame {f}',fill='black')
sheet.save(OUT/'review.png')

# Mandatory same-scale video/v2/current comparison; never equate numeric checks
# with visual approval. Full body crops share exactly the same coordinates.
spec2=importlib.util.spec_from_file_location('candidate_builder',ROOT/'build_video_parts_v3.py');builder=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(builder)
compare=Image.new('RGB',(1440,960),'#d9e1e8');draw=ImageDraw.Draw(compare);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
metrics=[]
for i,f in enumerate([66,70,74,78,82,86]):
 raw=Image.open(builder.FR/f'{f:03}.png').convert('RGBA');a=np.array(raw);a[:,:,3]=builder.matte(raw)
 source=builder.world(Image.fromarray(a));imgs=[source,Image.open(ROOT/f'generated_rig/video_parts_v2/render_{f}.png'),Image.open(OUT/f'render_{f}.png')];masks=[]
 for row,im in enumerate(imgs):
  crop=im.crop((230,425,570,710));masks.append(np.array(crop)[:,:,3]>128);crop.thumbnail((230,275));compare.paste(crop,(i*240,row*320+40),crop)
  draw.text((i*240+8,row*320+8),['原视频','上一版（不合格）','本轮候选（待修）'][row]+' · '+str(f),font=font,fill='black')
 metrics.append({'frame':f,'v2SilhouetteIoU':float((masks[0]&masks[1]).sum()/(masks[0]|masks[1]).sum()),'v3SilhouetteIoU':float((masks[0]&masks[2]).sum()/(masks[0]|masks[2]).sum())})
compare.save(OUT/'comparison.png');(OUT/'silhouette_comparison.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics))
