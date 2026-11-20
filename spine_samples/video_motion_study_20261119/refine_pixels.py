from pathlib import Path
import json,shutil,hashlib
from PIL import Image
r=Path.cwd();src=r/'pixel_bound';out=r/'pixel_bound_refined_20261120';out.mkdir(exist_ok=False)
for name in ['parts','runtime']:shutil.copytree(src/name,out/name)
for name in ['review.html','pixel_manifest.json']:shutil.copy2(src/name,out/name)
data=json.loads((src/'skin.json').read_text());before=0;after=0;changed=[]
for slot,items in data['skins'][0]['attachments'].items():
 for name,a in items.items():
  before+=len(a['uvs'])//2
  if slot in ['head','torso','shorts']:
   chunks=[];v=a['vertices'];k=0
   while k<len(v):n=int(v[k]);chunks.append(v[k:k+1+4*n]);k+=1+4*n
   assert all(len(x)==5 and x[1]==0 and x[4]==1 for x in chunks)
   indices=[0,6,62,56];a['vertices']=[x for i in indices for x in chunks[i]];a['uvs']=[0,0,1,0,1,1,0,1];a['triangles']=[0,3,1,1,3,2];a['hull']=4;changed.append(name)
  after+=len(a['uvs'])//2
images=[(p.stem,Image.open(p).convert('RGBA')) for p in (out/'parts').glob('*.png')];images.sort(key=lambda x:-x[1].height)
size=2048;canvas=Image.new('RGBA',(size,size));x=y=2;row=0;lines=['skin.png',f'size: {size},{size}','filter: Linear,Linear','repeat: none'];packed={}
for name,im in images:
 w,h=im.size
 if x+w+2>size:x=2;y+=row+4;row=0
 assert y+h+2<=size,(name,y,h)
 canvas.paste(im,(x,y));assert canvas.crop((x,y,x+w,y+h)).tobytes()==im.tobytes();packed[name]=[x,y,w,h]
 lines += [name,'  rotate: false',f'  xy: {x}, {y}',f'  size: {w}, {h}',f'  orig: {w}, {h}','  offset: 0, 0','  index: -1'];x+=w+4;row=max(row,h)
canvas.save(out/'skin.png');(out/'skin.atlas').write_text('\n'.join(lines)+'\n');(out/'skin.json').write_text(json.dumps(data,indent=2));(out/'optimization.json').write_text(json.dumps({'verticesBefore':before,'verticesAfter':after,'simplifiedRootAttachments':len(changed),'atlasBefore':[4096,4096],'atlasAfter':[2048,2048],'pixelPreserving':True,'attachmentCount':len(images),'poseCount':23,'artApproval':'previous candidate broadly matches reference; this optimization pending review'},indent=2))
s=(out/'review.html').read_text(encoding='utf8').replace('原帧附件 IK 试装','原帧附件 IK · 精简验证').replace('23 组原帧姿态，共 161 个附件。','23 组原帧姿态，共 161 个附件。贴图已无损压缩布局至 2048²，静态平面网格已精简。');(out/'review.html').write_text(s,encoding='utf8');print(before,after,'atlas height',y+row)
