from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,math
R=Path(__file__).resolve().parent;data=json.loads((R/'motion_annotations.json').read_text(encoding='utf8'))
frames=[];colors={'near':(0,139,155),'far':(201,107,53)}
for sample in data['samples']:
 src=Image.open(R/'frames'/f"{sample['frame']:04}.png").convert('RGB')
 # Draw annotations on a copy, keeping source frames unchanged.
 rig=Image.new('RGB',src.size,'#f5f7f7');a=ImageDraw.Draw(src);b=ImageDraw.Draw(rig);p=sample['points']
 b.line([tuple(p['neck']),tuple(p['pelvis'])],fill='#b9c9cb',width=30)
 b.line([tuple(p['hip_near']),tuple(p['hip_far'])],fill='#879d9f',width=10)
 for name,ch in sample['chains'].items():
  color=colors['near' if name.endswith('near') else 'far'];pts=[tuple(p[ch['root']]),tuple(ch['joint']),tuple(ch['solvedTarget'])]
  a.line(pts,fill=color,width=2);b.line(pts,fill=color,width=12 if name.startswith('leg') else 8)
  for j,pt in enumerate(pts):
   for d in [a,b]:
    x,y=pt;fill='white' if j<2 or ch['target'] in sample['inferred'] else color
    d.ellipse((x-3,y-3,x+3,y+3),fill=fill,outline=color,width=1)
  if name.startswith('leg'):
   x,y=pts[-1];b.ellipse((x-13,y,x+13,y+9),fill=color)
 out=Image.new('RGB',(960,450),'white');out.paste(src.crop((320,270,560,480)).resize((456,399)),(12,35));out.paste(rig.crop((320,270,560,480)).resize((456,399)),(492,35));d=ImageDraw.Draw(out);d.text((15,10),f"VIDEO + ANNOTATION | frame {sample['frame']}",fill='black');d.text((495,10),'2-BONE IK | INFERRED JOINTS',fill='black');frames.append(out)
# Duration: 22 frames at 24 fps. Endpoint frame85 is kept for inspection, not played twice.
durations=[round((i+1)*1000/24/10)*10-round(i*1000/24/10)*10 for i in range(22)]
frames[0].save(R/'motion_overlay.gif',save_all=True,append_images=frames[1:22],duration=durations,loop=0)
sheet=Image.new('RGB',(960,450*3),'white')
for row,idx in enumerate([0,7,19]):sheet.paste(frames[idx],(0,row*450))
sheet.save(R/'motion_keyframes.png')
print('Rendered source overlay and IK preview without altering source frames.')

