"""Build a source-pixel torso union and a five-piece garment fitting experiment."""
from build import *
from scipy.interpolate import RBFInterpolator

GARMENT=Path('I:/彩虹AI/design/AI玩具_design/美术资源/棉花娃娃/基础角色-正式/图层 69.png')
GARMENT_MOTION=.35  # Deliberately limited until the source view/fit is approved.

def mesh(points,uv,tri,weights,bones,width,height,hull):
    packed=[]
    for p,ws in zip(points,weights):
        ws=[(n,w) for n,w in ws if w>1e-5];total=sum(w for n,w in ws)
        packed.append(len(ws))
        for name,w in ws:
            b=next(b for b in bones if b['name']==name);mat=np.array([[b['a'],b['b']],[b['c'],b['d']]])
            q=np.linalg.solve(mat,np.array([p[0]-432,480-p[1]])-[b['x'],b['y']])
            packed.extend([next(i for i,b in enumerate(bones) if b['name']==name),float(q[0]),float(q[1]),float(w/total)])
    edges=sorted({tuple(sorted((int(a),int(b)))) for t in tri for a,b in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0]))})
    return dict(type='mesh',uvs=np.asarray(uv).ravel().tolist(),triangles=np.asarray(tri).ravel().tolist(),vertices=packed,width=width,height=height,hull=hull,edges=[2*v for e in edges for v in e])

def grid(nx,ny):
    a=[(x,0) for x in range(nx+1)]+[(nx,y) for y in range(1,ny+1)]+[(x,ny) for x in range(nx-1,-1,-1)]+[(0,y) for y in range(ny-1,0,-1)]
    hull=len(a);a +=[(x,y) for y in range(1,ny) for x in range(1,nx)]
    index={p:i for i,p in enumerate(a)};tri=[]
    for y in range(ny):
        for x in range(nx):
            aa,bb,cc,dd=[index[p] for p in [(x,y),(x+1,y),(x,y+1),(x+1,y+1)]];tri += [(aa,cc,bb),(bb,cc,dd)]
    return np.array(a)/[nx,ny],tri,hull

def torso_union(raw,probe,out):
    """Map observed torso pixels to one bind pose. No color blending or fill."""
    original=read(BASE/'skin.json');entries=read(BASE/'pixel_manifest.json')
    crops={m['part']+'_'+str(m['sourceFrame']):m for m in entries}
    allkeys=list(probe[0]['parts']['torso']);allkeys.sort(key=lambda k:np.asarray(Image.open(BASE/crops[k]['file']))[:,:,3].sum(),reverse=True)
    canvas=np.zeros((480,384,4),np.uint8);origin=np.zeros((480,384),np.uint8);srcxy=np.full((480,384,2),-1,np.int16)
    for key in allkeys:
        im=np.array(Image.open(BASE/crops[key]['file']).convert('RGBA'));g=probe[0]['parts']['torso'][key]
        uv=np.array(g['uv']).reshape(-1,2)*[im.shape[1],im.shape[0]];dest=np.array(g['xy']).reshape(-1,2)
        dest[:,0]+=432-248;dest[:,1]=480-dest[:,1]
        mat=cv2.getPerspectiveTransform(uv.astype(np.float32),dest.astype(np.float32))
        warped=cv2.warpPerspective(im,mat,(384,480),flags=cv2.INTER_NEAREST)
        sy,sx=np.mgrid[:im.shape[0],:im.shape[1]]
        coord=cv2.warpPerspective(np.dstack([sx,sy]).astype(np.float32),mat,(384,480),flags=cv2.INTER_NEAREST,borderValue=(-1,-1))
        take=(warped[:,:,3]>canvas[:,:,3]);canvas[take]=warped[take];origin[take]=int(key.split('_')[-1]);srcxy[take]=coord[take]
    # Accepted per-frame masks contain detached arm-edge slivers, hidden by the
    # original pose's arm. They are not reusable torso surface. Trim them using
    # an explicit authoring envelope; this removes pixels, never fills them.
    envelope=np.zeros(canvas.shape[:2],np.uint8)
    outline=np.array([[405,288],[479,288],[495,316],[506,361],[490,379],[400,379],[404,326]])-[248,0]
    cv2.fillPoly(envelope,[outline.astype(np.int32)],1)
    removed=int(np.count_nonzero((canvas[:,:,3]>0)&(envelope==0)))
    canvas[envelope==0]=0;origin[envelope==0]=0;srcxy[envelope==0]=-1
    ys,xs=np.where(canvas[:,:,3]>0);x0,x1=max(0,xs.min()-2),min(384,xs.max()+3);y0,y1=max(0,ys.min()-2),min(480,ys.max()+3)
    im=Image.fromarray(canvas[y0:y1,x0:x1]);im.save(out/'parts/torso_observed.png')
    Image.fromarray(origin[y0:y1,x0:x1]).save(out/'torso_source_frames.png');np.savez_compressed(out/'torso_source_coordinates.npz',xy=srcxy[y0:y1,x0:x1])
    uv,tri,hull=grid(8,8);pos=uv*[im.width,im.height]+[x0+248,y0]
    a=mesh(pos,uv,tri,[[('torso',1)]]*len(uv),probe[0]['bones'],im.width,im.height,hull);a['path']='torso_observed'
    raw['skins'][0]['attachments']['torso']={'torso_observed':a}
    next(s for s in raw['slots'] if s['name']=='torso')['attachment']='torso_observed'
    raw['animations']['walk_reuse']['slots']['torso']={'attachment':[{'name':'torso_observed'}]}
    # Verify that each visible output texel is literally a recorded source texel.
    mismatch=0
    for f in np.unique(origin):
        if f==0:continue
        source=np.array(Image.open(BASE/crops[f'torso_{f}']['file']).convert('RGBA'))
        m=origin==f;coords=srcxy[m];mismatch+=int(np.any(canvas[m]!=source[coords[:,1],coords[:,0]],axis=1).sum())
    assert mismatch==0
    write(out/'torso_provenance.json',{'sourceFrames':sorted(int(x) for x in np.unique(origin) if x),'changedTexels':mismatch,'mapping':'nearest source texel; pixel source frame and xy maps included','hiddenPixelsInvented':0,'trimmedOutsideBodyPixels':removed,'authoringEnvelope':(outline+[248,0]).tolist(),'geometryComplete':False})

def outfit(raw,probe,out):
    im=Image.open(GARMENT).convert('RGBA');w,h=im.size
    # Visible authored boundaries: sleeves, bib and two trouser legs.
    ys,xs=np.mgrid[:h,:w];owner=np.full((h,w),2,np.uint8)
    leftedge=np.interp(ys[:,0],[0,40,105,170,235,290,330],[152,182,188,176,145,114,104])[:,None]
    rightedge=np.interp(ys[:,0],[0,40,105,170,235,290,330],[391,404,420,439,460,477,478])[:,None]
    owner[(xs<leftedge)&(ys<325)]=0;owner[(xs>rightedge)&(ys<325)]=1
    owner[(ys>=365)&(xs<286)]=3;owner[(ys>=365)&(xs>=286)]=4
    # Fit visible front artwork to this directional body. This is geometry only,
    # not a claim to have recovered unobserved side surfaces.
    source=np.array([[145,30],[390,30],[270,40],[270,190],[120,300],[475,300],[75,245],[500,245],[185,210],[415,210],[95,365],[285,365],[470,365],[90,515],[270,515],[310,515],[460,515],[125,570],[240,570],[330,570],[440,570]],float)
    dest=np.array([[402,297],[484,300],[449,294],[451,323],[386,350],[523,345],[369,348],[528,342],[412,324],[488,323],[392,386],[450,398],[499,382],[390,433],[442,438],[457,421],[486,418],[400,445],[436,447],[463,432],[480,430]],float)
    transform=RBFInterpolator(source,dest,kernel='thin_plate_spline',smoothing=2)
    names=['sleeve_near','sleeve_far','bib','pants_near','pants_far'];attachments={};crops=[]
    for index,name in enumerate(names):
        arr=np.array(im);arr[:,:,3][owner!=index]=0
        yy,xx=np.where(arr[:,:,3]>0);x0,x1=max(0,xx.min()-2),min(w,xx.max()+3);y0,y1=max(0,yy.min()-2),min(h,yy.max()+3)
        crop=Image.fromarray(arr[y0:y1,x0:x1]);key='outfit_'+name;crop.save(out/'parts'/f'{key}.png')
        crops.append((index,name,key,crop,x0,y0,x1,y1))
    # All pieces use one tessellation and one weight field. Neighboring pixels
    # have identical transforms across a partition boundary, avoiding seams.
    globalx=sorted(set(np.linspace(0,w,24).tolist()+[v for c in crops for v in (c[4],c[6])]))
    globaly=sorted(set(np.linspace(0,h,28).tolist()+[v for c in crops for v in (c[5],c[7])]+[300,365,390]))
    for index,name,key,crop,x0,y0,x1,y1 in crops:
        xx=[x for x in globalx if x0<=x<=x1];yy=[y for y in globaly if y0<=y<=y1]
        unit,tri,hull=grid(len(xx)-1,len(yy)-1)
        src=np.column_stack([np.interp(unit[:,0],np.linspace(0,1,len(xx)),xx),np.interp(unit[:,1],np.linspace(0,1,len(yy)),yy)])
        uv=(src-[x0,y0])/[crop.width,crop.height];points=transform(src)
        weights=[]
        for x,y in src:
            left=float(np.interp(y,[0,40,105,170,235,290,330],[152,182,188,176,145,114,104]));right=float(np.interp(y,[0,40,105,170,235,290,330],[391,404,420,439,460,477,478]))
            near=float(np.clip((left+16-x)/45,0,1));far=float(np.clip((x-right+16)/45,0,1))
            arm=max(near,far)*float(np.clip((y-25)/110,0,1))*float(np.clip((340-y)/30,0,1))
            if arm>0:
                side='near' if near>far else 'far';blend=np.clip((y-160)/210,0,.50)
                root=arm*GARMENT_MOTION
                weights.append([('torso',1-root),(f'arm_{side}_upper',root*(1-blend)),(f'arm_{side}_lower',root*blend)])
            elif y<300:weights.append([('torso',1)])
            else:
                hipmix=float(np.clip((y-300)/90,0,1));limbmix=float(np.clip((y-390)/140,0,.8))*GARMENT_MOTION;side='near' if x<286 else 'far'
                weights.append([('torso',1-hipmix),('pelvis',hipmix*(1-limbmix)),(f'leg_{side}_upper',hipmix*limbmix)])
        a=mesh(points,uv,tri,weights,probe[0]['bones'],crop.width,crop.height,hull);a['path']=key;attachments[key]={key:a}
    base=raw['skins'][0]['attachments'];raw['skins']=[{'name':'default','attachments':{}},{'name':'body/base','attachments':copy.deepcopy(base)},{'name':'outfit/green_overalls','attachments':copy.deepcopy(base)}]
    dressed=raw['skins'][2]['attachments'];dressed.update(attachments)
    # Override underwear rather than omitting it: absent skin entries fall back
    # to the default skin. A transparent override keeps swaps deterministic.
    for a in dressed['shorts'].values():a['color']='ffffff00'
    order=[]
    for slot in raw['slots']:
        order.append(slot)
        add={'arm_far':['outfit_sleeve_far'],'leg_far':['outfit_pants_far'],'leg_near':['outfit_pants_near'],'shorts':['outfit_bib'],'arm_near':['outfit_sleeve_near']}.get(slot['name'],[])
        for n in add:order.append({'name':n,'bone':'torso','attachment':n})
    raw['slots']=order
    shutil.copy2(GARMENT,out/'outfit_source.png')
    # Reconstruction must exactly partition the visible source image.
    total=np.zeros((h,w),np.uint16)
    for i in range(5):total+=(owner==i).astype(np.uint16)
    assert np.all(total==1)
    write(out/'outfit_provenance.json',{'sourcePath':str(GARMENT),'sha256':sha(GARMENT),'size':[w,h],'parts':names,'repainted':False,'sourceTexelRGBChanged':0,'partitionCoverage':1,'missingViews':['back','hidden side surfaces'],'directionalFit':'geometry-only provisional fit; needs visual review','fitLandmarks':{'source':source.tolist(),'destination':dest.tolist()},'accepted':False})

def stabilize_head(raw,probe,out):
    """One head texture, with source-observed bounding-box motion correction.

    This is not a new texture per frame nor an anatomical tracking claim.
    """
    entries={m['sourceFrame']:m for m in read(BASE/'pixel_manifest.json') if m['part']=='head'}
    key=next(iter(raw['skins'][0]['attachments']['head']));im=Image.open(out/'parts'/f'{key}.png')
    x0,y0,x1,y1=entries[63]['crop'];cx=(x0+x1)/2;cy=(y0+y1)/2
    raw['bones'].append({'name':'head_visual','parent':'root','x':cx-432,'y':480-cy})
    bones=probe[0]['bones']+[{'name':'head_visual','a':1,'b':0,'c':0,'d':1,'x':cx-432,'y':480-cy}]
    uv,tri,hull=grid(1,1);a=mesh(uv*[x1-x0,y1-y0]+[x0,y0],uv,tri,[[('head_visual',1)]]*len(uv),bones,im.width,im.height,hull);a['path']=key
    raw['skins'][0]['attachments']['head']={key:a}
    translate=[];scale=[]
    for sample in probe:
        a0,b0,a1,b1=entries[sample['frame']]['crop'];translate.append({'time':sample['time'],'x':(a0+a1)/2-cx,'y':cy-(b0+b1)/2});scale.append({'time':sample['time'],'x':(a1-a0)/(x1-x0),'y':(b1-b0)/(y1-y0)})
    translate.append({**translate[0],'time':23/24});scale.append({**scale[0],'time':23/24})
    raw['animations']['walk_reuse']['bones']['head_visual']={'translate':translate,'scale':scale}
    write(out/'head_tracking.json',{'sourceTexture':key,'observations':'head bounding boxes from accepted source frame partitions','newTexturesPerFrame':0,'anatomicalClaim':False,'bonesAdded':['head_visual']})

def main():
    source=HERE/'hybrid';out=HERE/'fitted';out.mkdir(exist_ok=True);shutil.copytree(source/'parts',out/'parts',dirs_exist_ok=True)
    raw=read(source/'skin.json');probe=read(HERE/'probe.json')
    torso_union(raw,probe,out);stabilize_head(raw,probe,out);outfit(raw,probe,out)
    # The garment is composed as a complete skin for editor review. Base meshes
    # use the same texture paths, so the atlas does not duplicate the body.
    keys={a.get('path',key) for s in raw['skins'] for slot in s['attachments'].values() for key,a in slot.items()}
    report=pack([(k,Image.open(out/'parts'/f'{k}.png')) for k in sorted(keys)],out,2048)
    report.update(mode='reusable_mesh_wardrobe_experiment',wardrobeReady=False,explanation='Bounded source textures with continuous bone motion. Visual seams and missing views remain under review.')
    write(out/'atlas_report.json',report);write(out/'skin.json',raw)
    # Keep only referenced assets, avoiding a misleading orphan-texture budget.
    for p in (out/'parts').glob('*.png'):
        if p.stem not in keys:p.unlink()
    print(json.dumps({'textures':len(keys),'rgbaBytes':report['rgbaBytes'],'skins':[s['name'] for s in raw['skins']]}))

if __name__=='__main__':main()
