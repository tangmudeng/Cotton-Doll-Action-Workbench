"""Render fixed crops for reproducible visual comparisons; metrics are not acceptance."""
from pathlib import Path
from PIL import Image,ImageDraw
import json,numpy as np

HERE=Path(__file__).resolve().parent;OUT=HERE/'candidate_r3'
selected=[59,63,68,71,74]
canvas=Image.new('RGB',(1200,len(selected)*255),'white');draw=ImageDraw.Draw(canvas)
for i,f in enumerate(selected):
    for j,folder in enumerate(['frames','candidate_r2/renders','candidate_r3/renders']):
        im=Image.open(HERE/folder/f'{f:04}.png').crop((365,325,525,440)).resize((320,230))
        canvas.paste(im,(j*400+40,i*255+20));draw.text((j*400+40,i*255+3),f'{f}  '+['SOURCE','r2','r3'][j],fill='black')
canvas.save(OUT/'targeted_comparison.jpg',quality=95)
rows=[]
for f in range(59,83):
    imgs=[np.array(Image.open(HERE/folder/f'{f:04}.png').convert('RGB')) for folder in ['frames','candidate_r2/renders','candidate_r3/renders']]
    row={'frame':f,'regions':{}}
    for n,(x0,y0,x1,y1) in {'cuff':[380,350,435,405],'lower_body':[340,335,540,438]}.items():
        row['regions'][n]={}
        for cutoff in [230,240,248]:
            masks=[im[y0:y1,x0:x1].min(2)<cutoff for im in imgs]
            row['regions'][n][str(cutoff)]={version:float((masks[0]&mask).sum()/max(1,(masks[0]|mask).sum())) for version,mask in zip(['r2','r3'],masks[1:])}
    rows.append(row)
report={'method':'Fixed ROI binary foreground IoU at three thresholds, source vs actual Spine roundtrip rendered images. Sensitive to colors/background; not an anatomical or art acceptance test.','frames':rows}
report['summary']={region:{threshold:{v:float(np.mean([r['regions'][region][threshold][v] for r in rows])) for v in ['r2','r3']} for threshold in ['230','240','248']} for region in ['cuff','lower_body']}
(OUT/'silhouette_audit.json').write_text(json.dumps(report,indent=2),'utf8')
print(json.dumps(report['summary']))
