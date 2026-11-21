"""Focused source-body remeasurement; never creates replacement image pixels."""
import base64,io,json,os,urllib.request
import numpy as np
from PIL import Image
import pixel_workbench as pw
from pixel_automation import validate,MODEL
VERSION=1

def infer(path,existing):
    im=Image.open(path).convert('RGB');w,h=im.size
    names=[n for n in pw.PARTS if n!='head']
    coords=np.concatenate([np.array(existing['polygons'][n]) for n in names]+[np.array(list(existing['points'].values()))])
    left=max(0,int(coords[:,0].min())-25);right=min(w,int(coords[:,0].max())+25)
    top=max(0,int(coords[:,1].min())-20);bottom=min(h,int(coords[:,1].max())+20)
    crop=im.crop((left,top,right,bottom));cw,ch=crop.size
    buffer=io.BytesIO();crop.resize((cw*3,ch*3),Image.Resampling.LANCZOS).save(buffer,format='PNG')
    prompt=f'''Inspect this enlarged crop of ONE plush character's BODY. Precisely identify visible original parts.
Return JSON only. Coordinates normalized 0..1000 across THIS CROP, not the full source.
points keys: {','.join(pw.POINTS)}; joints keys: {','.join(pw.CHAINS)}.
polygons keys: {','.join(names)}. Each polygon needs 16-60 vertices tightly following visible original pixels.
Schema: {{"points":{{key:[x,y]}},"joints":{{key:[x,y]}},"polygons":{{key:[[x,y],...]}},"uncertainties":["only genuine ambiguity"]}}.
Near/far means camera depth. Identify them from occlusion and relative size. The larger foreground arm MUST include its rounded hand at its lower end, even when that hand overlaps the pants. DO NOT assign hand skin to shorts. Shorts are visible CLOTH only, not the hand or thighs. Follow pants leg openings.
Far arm may be mostly occluded behind the torso: include only visible pixels, never copy torso pixels into its outline.
The near leg may overlap the far leg. Keep visible legs separate. Hand/foot endpoints lie inside the distal flesh region, not at clothing edges. Shoulders and hips are anatomical attachment roots, even if occluded. Elbows/knees without visible articulation are inferred: record this uncertainty. No generated hidden pixels, no repaint. Do not put object descriptions such as rounded fingers or white underwear in uncertainties.'''
    body=dict(model=os.environ.get('PIXEL_VISION_MODEL',MODEL),temperature=0,max_tokens=7500,response_format={'type':'json_object'},thinking={'type':'disabled'},messages=[dict(role='user',content=[dict(type='text',text=prompt),dict(type='image_url',image_url={'url':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()})])])
    req=urllib.request.Request(os.environ['ARK_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['ARK_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=150) as r:result=json.load(r)
    from pixel_vision_response import parse_response
    v=parse_response(result,path,'detail')
    pw.write(path.parent.parent/'automation'/('detail_raw_'+path.stem+'.json'),v)
    return parse_result(v,existing,w,h,(left,top,right,bottom))

def parse_result(v,existing,w,h,bounds):
    left,top,right,bottom=bounds;cw=right-left;ch=bottom-top
    names=[n for n in pw.PARTS if n!='head']
    unresolved=[]
    if not isinstance(v.get('uncertainties'),list):v['uncertainties']=[]
    for field,keys in [('points',pw.POINTS),('joints',pw.CHAINS),('polygons',names)]:
        if not isinstance(v.get(field),dict) or not v[field]:raise ValueError('局部识别缺少必要字段 '+field)
        missing=set(keys)-set(v[field])
        for key in missing:
            def local(q):return [(q[0]-left)*1000/cw,(q[1]-top)*1000/ch]
            v[field][key]=[local(q) for q in existing[field][key]] if field=='polygons' else local(existing[field][key])
            unresolved.append(field+'.'+key)
            v['uncertainties'].append('局部重识别无法定位 '+field+'.'+key+'；保留首轮推定，尚未验证')
        v[field]={k:v[field][k] for k in keys}
    v['unresolvedFields']=unresolved
    for field in ('points','joints'):
        for q in v[field].values():pw.xy(q,1000,1000)
        v[field]={k:[left+q[0]*cw/1000,top+q[1]*ch/1000] for k,q in v[field].items()}
    hidden=[]
    for n,poly in v['polygons'].items():
        if isinstance(poly,list) and len(poly)==1 and isinstance(poly[0],list) and poly[0] and isinstance(poly[0][0],list):
            poly=poly[0];v['polygons'][n]=poly
        if poly==[]:
            hidden.append(n);v['polygons'][n]=[[(q[0]-left)*1000/cw,(q[1]-top)*1000/ch] for q in existing['polygons'][n]];poly=v['polygons'][n]
        if not 3<=len(poly)<=256:raise ValueError('局部部件轮廓无效')
        for q in poly:pw.xy(q,1000,1000)
    v['polygons']={k:[[left+q[0]*cw/1000,top+q[1]*ch/1000] for q in poly] for k,poly in v['polygons'].items()}
    v['polygons']['head']=existing['polygons']['head'];v['hiddenParts']=hidden
    validate(v,w,h);v['coordinateSpace']='source_pixels';v['detailCrop']=[left,top,right,bottom]
    return v
