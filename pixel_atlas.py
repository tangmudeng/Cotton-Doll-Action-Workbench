"""Lossless pixel deduplication and trimmed shelf packing; no approximate reuse."""
import hashlib,math
from PIL import Image
import numpy as np
import pixel_workbench as pw

def pack(images,out,limit=4096):
    unique={};aliases={};canonical=[]
    for key,image in images:
        rgba=np.array(image.convert('RGBA'));rgba[rgba[:,:,3]==0,:3]=0
        digest=hashlib.sha256(str(image.size).encode()+rgba.tobytes()).hexdigest()
        if digest in unique:aliases[key]=unique[digest]
        else:
            unique[digest]=key;aliases[key]=key;canonical.append((key,Image.fromarray(rgba)))
    pages=[];placements={};page=[];x=y=4;row=0
    for key,im in sorted(canonical,key=lambda pair:(-pair[1].height,-pair[1].width,pair[0])):
        w,h=im.size
        if max(w,h)+8>limit:raise ValueError('单附件超过图集尺寸')
        if x+w+4>limit:x=4;y+=row+4;row=0
        if y+h+4>limit:pages.append(page);page=[];x=y=4;row=0
        page.append((key,im,x,y));x+=w+4;row=max(row,h)
    if page:pages.append(page)
    stats=[];lines=[]
    for index,items in enumerate(pages):
        width=math.ceil(max(x+im.width+4 for _,im,x,y in items)/4)*4
        height=math.ceil(max(y+im.height+4 for _,im,x,y in items)/4)*4
        canvas=Image.new('RGBA',(width,height));name=f'skin_{index}.png'
        lines+=['',name,f'size: {width},{height}','filter: Linear,Linear','repeat: none']
        for key,im,x,y in items:
            canvas.paste(im,(x,y));placements[key]=(index,x,y,im.width,im.height)
        # Same pixels can be addressed by distinct attachment names without duplication.
        for key,original in aliases.items():
            loc=placements.get(original)
            if loc is None or loc[0]!=index:continue
            _,x,y,w,h=loc
            lines += [key,'  rotate: false',f'  xy: {x}, {y}',f'  size: {w}, {h}',f'  orig: {w}, {h}','  offset: 0, 0','  index: -1']
        canvas.save(out/name)
        stats.append(dict(file=name,width=width,height=height,rgbaBytes=width*height*4,pngBytes=(out/name).stat().st_size))
    (out/'skin.atlas').write_text('\n'.join(lines).lstrip()+'\n',encoding='utf-8')
    report=dict(attachments=len(images),uniqueImages=len(canonical),exactDuplicates=len(images)-len(canonical),pages=stats,
        rgbaBytes=sum(s['rgbaBytes'] for s in stats),pngBytes=sum(s['pngBytes'] for s in stats),
        mode='source_pixel_sequence',wardrobeReady=False,
        explanation='逐帧源像素复现；仅完全相同可见RGBA去重，不代表可复用换装资产。')
    pw.write(out/'atlas_report.json',report)
    return report
