"""Build a source-pixel torso union and a five-piece garment fitting experiment."""
from build import *
from scipy.interpolate import RBFInterpolator

GARMENT=Path('I:/彩虹AI/design/AI玩具_design/美术资源/棉花娃娃/图层 10.png')
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
    """Reassign upper-leg-owned waist pixels to a canonical torso in bone space."""
    original=ROOT/'spine_samples/video_motion_study_20261119/pixel_sync_20261120'
    entries=read(original/'pixel_manifest.json');crops={(m['part'],m['sourceFrame']):m for m in entries}
    canvas=np.zeros((480,384,4),np.uint8);origin=np.zeros((480,384),np.uint8);srcxy=np.full((480,384,2),-1,np.int16)
    def matrix(b):return np.array([[b['a'],b['b'],b['x']],[b['c'],b['d'],b['y']],[0,0,1.]])
    target=matrix(next(b for b in probe[0]['bones'] if b['name']=='torso'))
    pixel_to_world=np.array([[1,0,-432],[0,-1,480],[0,0,1.]])
    world_to_canvas=np.array([[1,0,432-248],[0,-1,480],[0,0,1.]])
    donors=[]
    for sample in probe:
        frame=sample['frame'];alpha=np.zeros((480,864),np.uint8)
        for part in ['torso','leg_near','leg_far']:
            m=crops[part,frame];x0,y0,x1,y1=m['crop'];image=np.array(Image.open((BASE if part=='torso' else original)/m['file']).convert('RGBA'));a=image[:,:,3].copy()
            if part.startswith('leg'):
                bone=next(b for b in sample['bones'] if b['name']==part+'_upper');limit=480-bone['y']+3
                a[np.arange(y0,y1)[:,None]>=np.full(a.shape,limit)]=0
            alpha[y0:y1,x0:x1]=np.maximum(alpha[y0:y1,x0:x1],a)
        rgb_source=np.array(Image.open(original/f'reference_frames/{frame:04}.png').convert('RGB'))
        image=np.dstack([rgb_source,alpha]);bone=next(b for b in sample['bones'] if b['name']=='torso')
        mat=world_to_canvas@target@np.linalg.inv(matrix(bone))@pixel_to_world
        donors.append((int(alpha.sum()),frame,image,mat))
    sy,sx=np.mgrid[:480,:864];coord=np.dstack([sx,sy]).astype(np.float32)
    for _,frame,source,mat in sorted(donors,reverse=True):
        warped=cv2.warpPerspective(source,mat,(384,480),flags=cv2.INTER_NEAREST)
        xy=cv2.warpPerspective(coord,mat,(384,480),flags=cv2.INTER_NEAREST,borderValue=(-1,-1))
        take=warped[:,:,3]>canvas[:,:,3];canvas[take]=warped[take];origin[take]=frame;srcxy[take]=xy[take]
    envelope=np.zeros(canvas.shape[:2],np.uint8)
    outline=np.array([[405,288],[479,288],[495,316],[506,361],[501,399],[400,403],[393,380],[404,326]])-[248,0]
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
    mismatch=0
    for f in np.unique(origin):
        if f==0:continue
        source=np.array(Image.open(original/f'reference_frames/{f:04}.png').convert('RGB'))
        m=origin==f;coords=srcxy[m];mismatch+=int(np.any(canvas[m][:,:3]!=source[coords[:,1],coords[:,0]],axis=1).sum())
    assert mismatch==0
    write(out/'torso_provenance.json',{'sourceFrames':sorted(int(x) for x in np.unique(origin) if x),'changedTexels':mismatch,'mapping':'nearest original video pixel; full-frame source xy and frame maps included','sourceMasks':'torso plus visible waist pixels previously assigned above leg roots','hiddenPixelsInvented':0,'trimmedOutsideBodyPixels':removed,'authoringEnvelope':(outline+[248,0]).tolist(),'geometryComplete':False})

def outfit(raw,probe,out):
    original=Image.open(GARMENT).convert('RGBA');w,h=original.size
    garment_outline=np.array([[249,544],[291,540],[332,548],[383,547],[437,532],[462,548],[480,578],[497,611],[521,645],[533,660],[526,680],[503,693],[504,728],[497,765],[481,789],[471,812],[425,825],[381,818],[373,835],[322,847],[266,843],[233,824],[216,799],[212,769],[214,744],[239,727],[275,724],[271,718],[230,709],[183,688],[173,673],[179,645],[195,610],[219,576]],np.int32)
    mask=np.zeros((h,w),np.uint8);cv2.fillPoly(mask,[garment_outline],1)
    pixels=np.array(original);pixels[:,:,3][mask==0]=0;im=Image.fromarray(pixels)
    # Visible authored boundaries: sleeves, bib and two trouser legs.
    ys,xs=np.mgrid[:h,:w];owner=np.full((h,w),2,np.uint8)
    leftedge=np.interp(ys[:,0],[540,570,610,650,690,725],[249,282,309,309,293,275])[:,None]
    rightedge=np.interp(ys[:,0],[540,580,620,660,695],[462,481,490,499,505])[:,None]
    owner[(xs<leftedge)&(ys<728)]=0;owner[(xs>rightedge)&(ys<697)]=1
    owner[(ys>=765)&(xs<375)]=3;owner[(ys>=765)&(xs>=375)]=4
    # Fit visible front artwork to this directional body. This is geometry only,
    # not a claim to have recovered unobserved side surfaces.
    source=np.array([[260,550],[420,544],[470,577],[280,575],[310,625],[430,615],[200,650],[180,685],[277,722],[230,709],[500,650],[523,680],[340,700],[490,730],[220,770],[375,765],[490,765],[280,830],[370,835],[425,815],[470,811]],float)
    dest=np.array([[409,292],[468,291],[490,306],[408,307],[416,329],[474,326],[369,332],[361,351],[399,368],[377,363],[516,333],[528,349],[443,366],[499,372],[393,405],[450,399],[492,394],[411,441],[445,442],[468,428],[488,424]],float)
    transform=RBFInterpolator(source,dest,kernel='thin_plate_spline',smoothing=2)
    names=['sleeve_near','sleeve_far','bib','pants_near','pants_far'];attachments={};crops=[]
    for index,name in enumerate(names):
        arr=np.array(im);support=(owner==index).astype(np.uint8)
        # Small source-observed overlap at sleeve roots permits separate rigid
        # sleeve rotation. No texture is extended beyond the supplied artwork.
        if index in (0,1,2):support=cv2.dilate(support,np.ones((13,13),np.uint8))
        arr[:,:,3][support==0]=0
        yy,xx=np.where(arr[:,:,3]>0);x0,x1=max(0,xx.min()-2),min(w,xx.max()+3);y0,y1=max(0,yy.min()-2),min(h,yy.max()+3)
        crop=Image.fromarray(arr[y0:y1,x0:x1]);key='outfit_'+name;crop.save(out/'parts'/f'{key}.png')
        crops.append((index,name,key,crop,x0,y0,x1,y1))
    # All pieces use one tessellation and one weight field. Neighboring pixels
    # have identical transforms across a partition boundary, avoiding seams.
    globalx=sorted(set(np.linspace(160,540,26).tolist()+[v for c in crops for v in (c[4],c[6])]))
    globaly=sorted(set(np.linspace(530,850,26).tolist()+[v for c in crops for v in (c[5],c[7])]+[728,765,785]))
    for index,name,key,crop,x0,y0,x1,y1 in crops:
        xx=[x for x in globalx if x0<=x<=x1];yy=[y for y in globaly if y0<=y<=y1]
        unit,tri,hull=grid(len(xx)-1,len(yy)-1)
        src=np.column_stack([np.interp(unit[:,0],np.linspace(0,1,len(xx)),xx),np.interp(unit[:,1],np.linspace(0,1,len(yy)),yy)])
        uv=(src-[x0,y0])/[crop.width,crop.height];points=transform(src)
        weights=[]
        for x,y in src:
            if index in (0,1):
                weights.append([(f'arm_{"near" if index==0 else "far"}_upper',1)])
                continue
            if y<730:weights.append([('torso',1)])
            else:
                hipmix=float(np.clip((y-730)/80,0,1));limbmix=float(np.clip((y-785)/60,0,.8))*GARMENT_MOTION;side='near' if x<375 else 'far'
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
    write(out/'outfit_provenance.json',{'sourcePath':str(GARMENT),'sha256':sha(GARMENT),'size':[w,h],'parts':names,'repainted':False,'sourceTexelRGBChanged':0,'partitionCoverage':1,'coverageMeaning':'partition of manually selected visible garment; sleeve roots additionally overlap 6 source pixels','garmentOutline':garment_outline.tolist(),'crops':{c[2]:[int(v) for v in c[4:]] for c in crops},'missingViews':['back','hidden side surfaces'],'directionalFit':'same-view clothed original; geometry fit still provisional','sleeveBinding':'rigid upper arm with observed root overlap','motionStrength':GARMENT_MOTION,'fitLandmarks':{'source':source.tolist(),'destination':dest.tolist()},'accepted':False})

def stabilize_head(raw,probe,out):
    """Fit a single head texture's similarity transform to observed source features."""
    original=ROOT/'spine_samples/video_motion_study_20261119/pixel_sync_20261120'
    entries={m['sourceFrame']:m for m in read(BASE/'pixel_manifest.json') if m['part']=='head'}
    key=next(iter(raw['skins'][0]['attachments']['head']));source_frame=int(key.split('_')[-1]);im=Image.open(out/'parts'/f'{key}.png').convert('RGBA');rgba=np.array(im)
    sx,sy,_,_=entries[source_frame]['crop'];center=np.array([sx+im.width/2,sy+im.height/2])
    sift=cv2.SIFT_create();kp,desc=sift.detectAndCompute(cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2GRAY),rgba[:,:,3]);matcher=cv2.BFMatcher();poses=[];evidence=[]
    for sample in probe:
        f=sample['frame'];m=entries[f];target=np.array(Image.open(BASE/m['file']).convert('RGBA'))
        tk,td=sift.detectAndCompute(cv2.cvtColor(target[:,:,:3],cv2.COLOR_RGB2GRAY),target[:,:,3])
        pairs=matcher.knnMatch(desc,td,k=2);matches=[x for x,y in pairs if x.distance<.72*y.distance]
        source=np.float32([np.array(kp[x.queryIdx].pt)+[sx,sy] for x in matches]);dest=np.float32([np.array(tk[x.trainIdx].pt)+m['crop'][:2] for x in matches])
        M,inliers=cv2.estimateAffinePartial2D(source,dest,method=cv2.RANSAC,ransacReprojThreshold=2,maxIters=4000,confidence=.999)
        if M is None or int(inliers.sum())<12:raise ValueError(f'Head tracking requires review at frame {f}')
        mapped=M[:,:2]@center+M[:,2];scale=float(np.hypot(M[0,0],M[1,0]));rotation=-float(np.degrees(np.arctan2(M[1,0],M[0,0])))
        residual=np.linalg.norm(source@M[:,:2].T+M[:,2]-dest,axis=1)
        poses.append((mapped,scale,rotation));evidence.append({'frame':f,'matches':len(matches),'inliers':int(inliers.sum()),'medianInlierResidual':float(np.median(residual[inliers[:,0]>0])),'matrix':M.tolist()})
    pos,s0,r0=poses[0];index=len(raw['bones']);raw['bones'].append({'name':'head_visual','parent':'root','x':float(pos[0]-432),'y':float(480-pos[1]),'rotation':r0,'scaleX':s0,'scaleY':s0})
    uv,tri,hull=grid(1,1);vertices=[]
    for u,v in uv:vertices.extend([1,index,float((u-.5)*im.width),float((.5-v)*im.height),1])
    raw['skins'][0]['attachments']['head']={key:dict(type='mesh',path=key,uvs=uv.ravel().tolist(),triangles=np.array(tri).ravel().tolist(),vertices=vertices,width=im.width,height=im.height,hull=hull,edges=[0,2,2,4,4,6,6,0,2,6])}
    translate=[];scale=[];rotate=[]
    for sample,(p,s,r) in zip(probe,poses):
        translate.append({'time':sample['time'],'x':float(p[0]-pos[0]),'y':float(pos[1]-p[1])});scale.append({'time':sample['time'],'x':s/s0,'y':s/s0});rotate.append({'time':sample['time'],'value':r-r0})
    for keys in [translate,scale,rotate]:keys.append({**keys[0],'time':23/24})
    raw['animations']['walk_reuse']['bones']['head_visual']={'translate':translate,'scale':scale,'rotate':rotate}
    write(out/'head_tracking.json',{'sourceTexture':key,'method':'SIFT + RANSAC similarity transform on source head pixels','observations':evidence,'newTexturesPerFrame':0,'anatomicalClaim':False,'bonesAdded':['head_visual']})

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
