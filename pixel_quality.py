"""Read-only original-pixel / semantic ownership audit and visual evidence."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
import pixel_workbench as pw

COLORS=np.array([[153,105,200],[55,140,172],[232,175,71],[223,128,101],[64,155,131],[96,151,219],[183,122,158]],np.uint8)

def stabilize_review(html, width, height, accepted=False, revision=None):
    """Keep frame-dependent text and image loading from changing document geometry."""
    css=(f'<style id="stable-review-layout">'
         f'html{{scrollbar-gutter:stable}}'
         f'#issues{{box-sizing:border-box;height:180px;min-height:180px;max-height:180px;'
         f'overflow:auto;overflow-wrap:anywhere;scrollbar-gutter:stable;contain:layout paint;overflow-anchor:none}}'
         f'#compare{{aspect-ratio:{width*3}/{height};object-fit:contain}}'
         f'#parts{{aspect-ratio:{width*2}/{height};object-fit:contain}}'
         f'#label{{display:inline-block;min-width:13ch;font-variant-numeric:tabular-nums}}'
         f'header{{z-index:2}}</style>')
    import re
    html=re.sub(r'<style id="stable-review-layout">.*?</style>','',html,flags=re.S)
    html=html.replace('</style>', '</style>'+css,1)
    if accepted:
        html=html.replace('未验收候选',f'用户已验收 · r{revision}')
        html=html.replace('此页不能通过验收。','用户已在 Spine 中验收通过；以下保留历史诊断。')
    return html


def boundary_report(project):
    d=pw.folder(project['id']);frames=project['frames'];images=[]
    for f in frames:
        im=np.array(Image.open(d/'frames'/f"{f['frame']:04}.png").convert('RGB'))
        images.append(cv2.resize(im,(96,64)).astype(np.float32)/255)
    if len(images)<2:return dict(status='insufficient_frames')
    changes=[float(np.mean(np.abs(b-a))) for a,b in zip(images,images[1:])]
    seam=float(np.mean(np.abs(images[-1]-images[0])))
    ratio=seam/max(float(np.median(changes)),.0001)
    joints=[]
    for key in list(pw.POINTS)+list(pw.CHAINS):
        values=[np.array((f['points'] if key in pw.POINTS else f['joints'])[key]) for f in frames]
        steps=[float(np.linalg.norm(b-a)) for a,b in zip(values,values[1:])]
        jump=float(np.linalg.norm(values[-1]-values[0]))
        joints.append(dict(point=key,pixels=jump,ratio=jump/max(float(np.median(steps)),1)))
    return dict(status='review_loop_boundary' if ratio>3 or any(x['ratio']>3 for x in joints) else 'no_large_numeric_jump',
        sourcePixelRatio=ratio,joints=joints,claim='首尾跳变数值诊断；非循环动作无需闭环，数值正常也不代表语义通过')


def audit(project):
    d=pw.folder(project['id']);out=d/f"quality_r{project['revision']}";out.mkdir(exist_ok=True)
    report={'revision':project['revision'],'frames':[],'claim':'pixel coverage and ownership diagnostics, not automatic semantic acceptance'}
    built=pw.ROOT/project['artifact']['base'].lstrip('/') if project.get('artifact') else None
    manifest=pw.read(built/'pixel_manifest.json') if built else []
    sheets=[]
    for f in project['frames']:
        rgb=np.array(Image.open(d/'frames'/f"{f['frame']:04}.png").convert('RGB'));h,w=rgb.shape[:2]
        masks={n:np.array(Image.open(d/f['parts'][n]['mask']))[:,:,3] for n in pw.PARTS}
        owner=np.full((h,w),-1,np.int8);count=np.zeros((h,w),np.uint8)
        assembled=np.full_like(rgb,232);changed=0
        for index,n in enumerate(pw.PARTS):
            if f['parts'][n].get('visible') is False:continue
            m=masks[n]>0;owner[m]=index;count+=m.astype(np.uint8);assembled[m]=rgb[m]
            entry=next((m for m in manifest if m['part']==n and m['sourceFrame']==f['frame']),None)
            if entry:
                x0,y0,x1,y1=entry['crop'];actual=np.array(Image.open(built/entry['file']).convert('RGBA'))
                changed+=int(np.count_nonzero(np.any(actual[:,:,:3]!=rgb[y0:y1,x0:x1],axis=2)&(actual[:,:,3]>0)))
        color=np.full_like(rgb,232);inside=owner>=0;color[inside]=(rgb[inside]*.35+COLORS[owner[inside]]*.65).astype(np.uint8)
        visual=Image.fromarray(assembled);draw=ImageDraw.Draw(visual)
        for n,(a,b) in pw.CHAINS.items():
            draw.line([tuple(f['points'][a]),tuple(f['joints'][n]),tuple(f['points'][b])],fill=(10,130,150),width=2)
        row=Image.new('RGB',(w*3,h),'white');row.paste(Image.fromarray(rgb));row.paste(visual,(w,0));row.paste(Image.fromarray(color),(w*2,0));row.save(out/f"frame_{f['frame']:04}.jpg",quality=93)
        part_sheet=Image.new('RGB',(w*4,h*2),(232,232,232))
        for i,n in enumerate(pw.PARTS):
            im=np.full_like(rgb,232);m=masks[n]>0;im[m]=rgb[m];tile=Image.fromarray(im);ImageDraw.Draw(tile).text((10,10),n,fill='black');part_sheet.paste(tile,((i%4)*w,(i//4)*h))
        part_sheet.resize((w*2,h)).save(out/f"parts_{f['frame']:04}.jpg",quality=94)
        report['frames'].append({'frame':f['frame'],'changedRGBPixels':changed,'overlapPixels':int(np.count_nonzero(count>1)),
            'visiblePixels':{n:int(np.count_nonzero(owner==i)) for i,n in enumerate(pw.PARTS)},
            'hiddenParts':[n for n in pw.PARTS if f['parts'][n].get('visible') is False]})
    report['loopBoundary']=boundary_report(project)
    report['exportPixelsChecked']=bool(built)
    report['changedRGBPixels']=sum(f['changedRGBPixels'] for f in report['frames']) if built else None
    pw.write(out/'pixel_audit.json',report)
    data=json.dumps({'frames':[f['frame'] for f in project['frames']],'issues':project.get('automation',{}).get('issues',[]),'audit':report},ensure_ascii=False).replace('<','\\u003c')
    html='''<!doctype html><meta charset="utf-8"><title>05 完整周期逐帧检查 · 未验收候选</title><style>body{font:16px system-ui;background:#eef2ef;color:#203c38;margin:24px}button,select,input{font:inherit;padding:8px;margin:4px}img{width:100%;display:block;background:#fff;margin:12px 0}header{position:sticky;top:0;background:#eef2ef;padding:10px;border-bottom:1px solid #abc}#issues{white-space:pre-wrap;background:white;padding:12px}small{color:#536c66}</style><header><h2>完整周期逐帧检查 · 未验收候选</h2><p>左：视频原帧　中：源像素组装与骨骼　右：部件归属着色</p><button id="prev">上一帧</button><button id="play">播放 / 暂停</button><button id="next">下一帧</button><input id="seek" type="range" min="0"><b id="label"></b><select id="speed"><option value="250">慢放</option><option value="42">原速</option></select><small>下方展示独立部件；组装正确不代表部件归属正确。此页不能通过验收。</small></header><img id="compare"><div id="issues"></div><h3>独立附件：远手 / 远腿 / 近腿 / 躯干 / 裤衩 / 近手 / 头部</h3><img id="parts"><script>const data=DATA;let i=0,playing=false,last=0;const $=id=>document.getElementById(id);$('seek').max=data.frames.length-1;function draw(){const f=data.frames[i],key=String(f).padStart(4,'0');$('label').textContent=`源帧 ${f} · ${i+1}/${data.frames.length}`;$('seek').value=i;$('compare').src=`frame_${key}.jpg`;$('parts').src=`parts_${key}.jpg`;$('issues').textContent=data.issues.filter(x=>x.frame===f).map(x=>`${x.part}：${x.detail}`).join('\\n')||'此帧未发现自动异常，仍需视觉核对';}function move(n){i=(i+n+data.frames.length)%data.frames.length;draw()}$('prev').onclick=()=>{playing=false;move(-1)};$('next').onclick=()=>{playing=false;move(1)};$('play').onclick=()=>playing=!playing;$('seek').oninput=()=>{playing=false;i=+$('seek').value;draw()};function tick(t){if(playing&&t-last>+$('speed').value){move(1);last=t}requestAnimationFrame(tick)}draw();requestAnimationFrame(tick);</script>'''.replace('DATA',data)
    html=html.replace('value="42"',f'value="{1000/project["source"]["fps"]:.4f}"')
    boundary=report['loopBoundary']
    html=html.replace('<img id="compare">','<p>首尾衔接检查：'+('需核对首尾跳变（非循环动作可忽略闭环要求）' if boundary['status']=='review_loop_boundary' else '未发现明显数值跳变，仍需视觉核对')+'</p><img id="compare">')
    html=stabilize_review(html,project['source']['width'],project['source']['height'],project.get('automation',{}).get('accepted',False),project['revision'])
    (out/'review.html').write_text(html,encoding='utf8')
    return dict(url=pw.url(out/'review.html'),report=report)

if __name__=='__main__':
    import sys
    result=audit(pw.load(sys.argv[1]));print(json.dumps({'url':result['url'],'changedRGBPixels':result['report']['changedRGBPixels']},ensure_ascii=False))
