"""Isolated reuse experiment. Original RGB only; no generated/inpainted pixels.

Select a bounded exemplar library by measuring each attachment under every
accepted pose. This is a diagnostic prototype, not an automatic acceptance gate.
"""
from pathlib import Path
import json,sys,hashlib,copy,shutil
import cv2
import numpy as np
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=HERE/'clean_sources' if (HERE/'clean_sources').exists() else ROOT/'spine_samples/video_motion_study_20261119/pixel_sync_20261120'
sys.path.insert(0,str(ROOT))
from pixel_atlas import pack

def read(p):return json.loads(Path(p).read_text('utf-8'))
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def render(im,g,scale=.5):
    """Rasterize runtime-evaluated triangles to premultiplied RGBA in source space."""
    width,height=round(384*scale),round(480*scale)
    out=np.zeros((height,width,4),np.float32)
    src=np.asarray(im.convert('RGBA'),dtype=np.float32)/255
    src[:,:,:3]*=src[:,:,3:4]
    uv=np.array(g['uv'],np.float32).reshape(-1,2)*[im.width,im.height]
    xy=np.array(g['xy'],np.float32).reshape(-1,2)
    xy[:,0]=(xy[:,0]+432-248)*scale;xy[:,1]=(480-xy[:,1])*scale
    for tri in np.array(g['tri']).reshape(-1,3):
        a=uv[tri].astype(np.float32);b=xy[tri].astype(np.float32)
        x0=max(0,int(np.floor(b[:,0].min())));y0=max(0,int(np.floor(b[:,1].min())))
        x1=min(width,int(np.ceil(b[:,0].max()))+1);y1=min(height,int(np.ceil(b[:,1].max()))+1)
        d1=a[1]-a[0];d2=a[2]-a[0]
        if x1<=x0 or y1<=y0 or abs(d1[0]*d2[1]-d1[1]*d2[0])<1e-6:continue
        b-=np.array([x0,y0],np.float32)
        mat=cv2.getAffineTransform(a,b)
        tile=cv2.warpAffine(src,mat,(x1-x0,y1-y0),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        mask=np.zeros(tile.shape[:2],np.uint8);cv2.fillConvexPoly(mask,np.rint(b*256).astype(np.int32),1,shift=8)
        roi=out[y0:y1,x0:x1];roi[mask>0]=tile[mask>0]
    return out

def over(a,b):return b+a*(1-b[:,:,3:4])
def rgb(a):return np.clip((a[:,:,:3]+.94*(1-a[:,:,3:4]))*255,0,255).astype(np.uint8)

def select(cost,k):
    # Facility-location selection is bounded by the explicitly chosen budget.
    chosen=[int(np.argmin(cost.mean(axis=0)))];best=cost[:,chosen[0]].copy()
    while len(chosen)<k:
        options=[i for i in range(cost.shape[1]) if i not in chosen]
        q=min(options,key=lambda i:np.minimum(best,cost[:,i]).sum())
        if best.sum()-np.minimum(best,cost[:,q]).sum()<.01:break
        chosen.append(q);best=np.minimum(best,cost[:,q])
    # Penalize frequent attachment swaps; preserve the original temporal order.
    c=cost[:,chosen];dp=c[0].copy();back=[]
    penalty=.045
    for row in c[1:]:
        m=dp[:,None]+penalty*(1-np.eye(len(chosen)));ix=m.argmin(0);back.append(ix);dp=row+m[ix,np.arange(len(chosen))]
    q=int(dp.argmin());seq=[q]
    for ix in reversed(back):q=int(ix[q]);seq.append(q)
    seq.reverse()
    return sorted(chosen),[chosen[i] for i in seq]

def main():
    raw=read(BASE/'skin.json');probe=read(HERE/'probe.json')
    parts=[s['name'] for s in raw['slots']];manifest=read(BASE/'pixel_manifest.json')
    paths={m['part']+'_'+str(m['sourceFrame']):BASE/m['file'] for m in manifest}
    images={k:Image.open(p).convert('RGBA') for k,p in paths.items()}
    library={};metrics={};previews={'single':[np.zeros((240,192,4),np.float32) for _ in probe],'hybrid':[np.zeros((240,192,4),np.float32) for _ in probe],'reference':[np.zeros((240,192,4),np.float32) for _ in probe]}
    budget={'head':1,'torso':1,'shorts':2,'arm_near':3,'arm_far':2,'leg_near':3,'leg_far':3}
    for n in parts:
        keys=list(probe[0]['parts'][n]);pred=[];cost=[]
        for i,p in enumerate(probe):
            target=render(images[f'{n}_{p["frame"]}'],p['parts'][n][f'{n}_{p["frame"]}'])
            row=[];rendered=[]
            for key in keys:
                v=render(images[key],p['parts'][n][key]);rendered.append(v)
                area=max(1,float(target[:,:,3].sum()))
                alpha=float(np.abs(v[:,:,3]-target[:,:,3]).sum())/area
                color=float(np.abs(v[:,:,:3]-target[:,:,:3]).sum())/(area*3)
                row.append(alpha+color*.6)
            cost.append(row);pred.append(rendered);previews['reference'][i]=over(previews['reference'][i],target)
        cost=np.array(cost)
        if n=='arm_far':
            areas=np.array([np.asarray(images[k])[:,:,3].sum() for k in keys],float)
            # Occlusion slivers are evidence of visibility, not a complete arm.
            cost[:,areas<areas.max()*.75]+=100
        one,seq1=select(cost,1);many,seq=select(cost,budget[n])
        library[n]={'single':keys[one[0]],'selected':[keys[j] for j in many],'sequence':[keys[j] for j in seq]}
        metrics[n]={'singleMeanCost':float(cost[:,one[0]].mean()),'hybridMeanCost':float(cost[np.arange(23),seq].mean()),'switches':sum(a!=b for a,b in zip(seq,seq[1:]))}
        for i in range(23):
            previews['single'][i]=over(previews['single'][i],pred[i][one[0]])
            previews['hybrid'][i]=over(previews['hybrid'][i],pred[i][seq[i]])
        print(n,library[n]['selected'],flush=True)
    write(HERE/'selection.json',{'library':library,'metrics':metrics,'meaning':'relative raster mismatch, not anatomical or visual acceptance','budgets':budget})
    for mode in ('single','hybrid'):
        out=HERE/mode;out.mkdir(exist_ok=True);(out/'parts').mkdir(exist_ok=True)
        new=copy.deepcopy(raw);new['skeleton']['images']='./parts/'
        new['skins']=[{'name':'default','attachments':{}}]
        anim=copy.deepcopy(raw['animations']['reference_cycle'])
        for timelines in anim.get('bones',{}).values():
            for keys in timelines.values():
                for key in keys:key.pop('curve',None)
        new['animations']={'walk_reuse':anim}
        selected=[];provenance=[]
        for slot in new['slots']:
            n=slot['name'];seq=library[n]['sequence'] if mode=='hybrid' else [library[n]['single']]*23
            keys=sorted(set(seq));selected+=keys
            new['skins'][0]['attachments'][n]={k:copy.deepcopy(raw['skins'][0]['attachments'][n][k]) for k in keys}
            slot['attachment']=seq[0]
            anim['slots'][n]={'attachment':[{'time':p['time'],'name':seq[i]} for i,p in enumerate(probe)]+[{'time':23/24,'name':seq[0]}]}
            for k in keys:
                shutil.copy2(paths[k],out/'parts'/f'{k}.png')
                item=next(m for m in manifest if m['part']+'_'+str(m['sourceFrame'])==k)
                provenance.append({**item,'sha256':sha(paths[k]),'file':f'parts/{k}.png','repainted':False,'exposedHiddenAreaComplete':False})
        # Keep texture storage bounded; all texture changes are explicitly selected.
        report=pack([(k,images[k]) for k in selected],out,limit=2048)
        report.update(mode='bounded_reusable_mesh_experiment',wardrobeReady=False)
        write(out/'atlas_report.json',report);write(out/'skin.json',new);write(out/'provenance.json',provenance)
    contact=Image.new('RGB',(192*3,240*5),'#f0f0f0')
    for row,i in enumerate([0,5,11,17,22]):
        for col,mode in enumerate(['reference','single','hybrid']):
            im=Image.fromarray(rgb(previews[mode][i]));ImageDraw.Draw(im).text((4,4),f'{mode} f{i+63}',fill='black');contact.paste(im,(col*192,row*240))
    contact.save(HERE/'body_comparison.png')
    write(HERE/'STATUS.json',{'status':'body_experiment_not_accepted','userWardrobeAsset':'I:/彩虹AI/design/AI玩具_design/美术资源/棉花娃娃/基础角色-正式/图层 69.png','secondMotionValidated':False,'wardrobeValidated':False,'reference':str(BASE),'baselineHash':sha(BASE/'skin.json')})

if __name__=='__main__':main()
