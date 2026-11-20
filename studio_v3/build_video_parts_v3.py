from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np,cv2,json,math,hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'generated_rig/video_parts_v3';FR=ROOT/'generated_rig/right_front_import_9c08a83c/frames'
# Manually traced semantic seams, in exact source-video coordinates. Curves are
# supersampled before clipping against the full character foreground.
PARTS={
 'head':(66,[(260,15),(601,15),(608,245),(554,272),(530,284),(510,289),(484,286),(454,289),(422,287),(401,282),(382,285),(346,284),(310,264),(266,238)]),
 'arm_near':(82,[(399,292),(414,293),(425,306),(423,323),(411,345),(396,366),(381,383),(366,390),(353,391),(342,385),(336,375),(336,361),(344,343),(357,327),(375,310),(389,298)]),
 'arm_far':(82,[(482,294),(501,302),(518,316),(532,331),(540,345),(544,357),(541,367),(533,373),(522,376),(507,375),(500,370),(499,352),(493,329)]),
 'leg_near':(82,[(377,394),(389,389),(405,387),(421,389),(438,395),(451,405),(458,417),(462,431),(472,438),(477,449),(473,458),(461,464),(442,469),(425,467),(414,461),(407,452),(403,440),(394,429),(385,415)]),
 'leg_far':(70,[(459,394),(473,384),(492,373),(498,389),(502,407),(515,414),(529,420),(536,432),(533,442),(521,449),(505,455),(488,457),(477,453),(470,441),(461,423),(452,409)]),
 'shorts':(82,[(378,377),(396,361),(416,367),(443,371),(471,368),(491,362),(500,356),(501,376),(496,394),(483,408),(464,423),(459,414),(449,401),(431,392),(410,389),(391,390),(378,398)])
}
# Catmull-Rom interpolation keeps the source seam through supplied contour nodes.
def contour(points):
 p=np.array(points,float);out=[]
 for i in range(len(p)):
  a,b,c,d=p[(i-1)%len(p)],p[i],p[(i+1)%len(p)],p[(i+2)%len(p)]
  for t in np.linspace(0,1,12,endpoint=False):out.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
 return out

def matte(im):
 a=np.asarray(im.convert('RGB'));white=(a.min(axis=2)>236)&(a.max(axis=2)-a.min(axis=2)<18)
 n,labels,stats,_=cv2.connectedComponentsWithStats(white.astype('uint8'),8)
 edge=np.unique(np.concatenate([labels[0],labels[-1],labels[:,0],labels[:,-1]]));bg=np.isin(labels,edge[edge!=0]);alpha=np.where(bg,0,255).astype('uint8')
 dist=cv2.distanceTransform((alpha>0).astype('uint8'),cv2.DIST_L2,3)
 edge=(dist<2)&(alpha>0);alpha[edge]=np.minimum(alpha[edge],np.clip((255-a.min(axis=2)[edge].astype(float))/65,0,1)*255).astype('uint8')
 return alpha

def cut(frame,pts):
 im=Image.open(FR/f'{frame:03}.png').convert('RGBA');mask=Image.new('L',(864*4,480*4));ImageDraw.Draw(mask).polygon([(round(x*4),round(y*4)) for x,y in contour(pts)],fill=255);mask=mask.resize(im.size,Image.Resampling.LANCZOS)
 a=np.array(im);foreground=matte(im);a[:,:,3]=np.minimum(np.array(mask),foreground)
 # Remove white background contamination before resampling transparent edges.
 fraction=foreground.astype(float)/255
 edge=(fraction>0)&(fraction<1)
 for channel in range(3):
  values=(a[:,:,channel].astype(float)-255*(1-fraction))/np.maximum(fraction,.01)
  a[:,:,channel][edge]=np.uint8(np.clip(values[edge],0,255))
 return Image.fromarray(a)

def main():
 (OUT/'source_cuts').mkdir(parents=True,exist_ok=True);records=[]
 sheet=Image.new('RGB',(1200,800),'#c5d5de');d=ImageDraw.Draw(sheet)
 for i,(name,(f,poly)) in enumerate(PARTS.items()):
  im=cut(f,poly);im.save(OUT/'source_cuts'/f'{name}.png');box=im.getbbox();crop=im.crop(box);crop.save(OUT/'source_cuts'/f'{name}_crop.png');crop.thumbnail((350,330));x=i%3*400;y=i//3*400;sheet.paste(crop,(x+25,y+40),crop);d.text((x+15,y+15),f'{name} / source frame {f}',fill='black')
  records.append({'id':name,'sourceFrame':f,'sourceSha256':hashlib.sha256((FR/f'{f:03}.png').read_bytes()).hexdigest(),'sourcePolygon':poly,'cropBox':box,'method':'manual semantic contour on video frame; original RGB inside visible mask'})
 sheet.save(OUT/'source_cut_review.png');(OUT/'source_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')


# Video-space source points and the common neutral binding-space targets.
BIND={'body':{'parent':None,'pivot':[445,375]},'head':{'parent':'body','pivot':[445,288]},'shorts':{'parent':'body','pivot':[445,375]},'arm_near':{'parent':'body','pivot':[405,305],'joint':[393,348],'tip':[388,383]},'arm_far':{'parent':'body','pivot':[489,305],'joint':[500,339],'tip':[505,369]},'leg_near':{'parent':'shorts','pivot':[410,397],'joint':[408,430],'tip':[410,458]},'leg_far':{'parent':'shorts','pivot':[475,390],'joint':[479,420],'tip':[480,446]}}
SOURCE_AXES={'arm_near':([405,305],[374,351]),'arm_far':([489,305],[520,338]),'leg_near':([410,397],[433,431]),'leg_far':([475,390],[490,424])}
# Bind directly to the observed frame 82 pose. Historical landmarks are only
# a starting annotation; hidden far-side joints remain explicitly estimated.
LANDMARKS=json.loads((ROOT/'generated_rig/walk_acceptance_v1/landmarks.json').read_text(encoding='utf8'))
for limb in SOURCE_AXES:
 idx=LANDMARKS['frames'].index(PARTS[limb][0]);A,J,T=LANDMARKS['points'][limb][idx]
 SOURCE_AXES[limb]=(A,J)
 BIND[limb].update(pivot=A,joint=J,tip=T)

def unpose(name,source_override=None):
 spec=source_override or PARTS[name]
 idx=LANDMARKS['frames'].index(spec[0]);A,J,T=[np.array(p,float) for p in LANDMARKS['points'][name][idx]]
 b=BIND[name];P,Q,R=[np.array(b[k],float) for k in ['pivot','joint','tip']]
 heading=lambda v:math.atan2(v[1],v[0])
 angle=heading(J-A)-heading(Q-P);bend=heading(T-J)-heading(J-A)-heading(R-Q)+heading(Q-P)
 yy,xx=np.mgrid[:480,:864];v=Q-P;d=((xx-Q[0])*v[0]+(yy-Q[1])*v[1])/np.linalg.norm(v)
 u=np.clip((d+60/1.4)/(120/1.4),0,1);w=u*u*(3-2*u)
 x=xx-Q[0];y=yy-Q[1];c,sn=math.cos(bend),math.sin(bend)
 dx=xx+w*(Q[0]+c*x-sn*y-xx);dy=yy+w*(Q[1]+sn*x+c*y-yy)
 c,sn=math.cos(angle),math.sin(angle);mx=A[0]+c*(dx-P[0])-sn*(dy-P[1]);my=A[1]+sn*(dx-P[0])+c*(dy-P[1])
 a=np.array(cut(*spec)).astype(float)/255;a[:,:,:3]*=a[:,:,3:4]
 out=cv2.remap(a,mx.astype('float32'),my.astype('float32'),cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT);out=np.clip(out,0,1)
 out[:,:,:3]=np.divide(out[:,:,:3],out[:,:,3:4],out=np.zeros_like(out[:,:,:3]),where=out[:,:,3:4]>.001)
 return Image.fromarray(np.uint8(out*255))

def warp(im,angle,origin,target,size=(864,480)):
 r=math.radians(angle);c=math.cos(r);sn=math.sin(r);A=np.array([[c,-sn,target[0]-c*origin[0]+sn*origin[1]],[sn,c,target[1]-sn*origin[0]-c*origin[1]]],dtype=float)
 a=np.array(im).astype(float)/255;a[:,:,:3]*=a[:,:,3:4];b=cv2.warpAffine(a,A,size,flags=cv2.INTER_CUBIC);b=np.clip(b,0,1);b[:,:,:3]=np.divide(b[:,:,:3],b[:,:,3:4],out=np.zeros_like(b[:,:,:3]),where=b[:,:,3:4]>0.001);return Image.fromarray(np.uint8(np.clip(b*255,0,255)))
def world(im):
 a=np.array(im).astype(float)/255;a[:,:,:3]*=a[:,:,3:4];b=cv2.warpAffine(a,np.array([[1.4,0,-220.8],[0,1.4,40]]),(768,768),flags=cv2.INTER_CUBIC);b=np.clip(b,0,1);b[:,:,:3]=np.divide(b[:,:,:3],b[:,:,3:4],out=np.zeros_like(b[:,:,:3]),where=b[:,:,3:4]>.001);return Image.fromarray(np.uint8(np.clip(b*255,0,255)))
def pt(p):return [round(p[0]*1.4-220.8,3),round(p[1]*1.4+40,3)]
def assemble():
 (OUT/'images').mkdir(exist_ok=True);(OUT/'masks').mkdir(exist_ok=True)
 layers={};source_rotations={}
 for name,(f,poly) in PARTS.items():
  im=Image.open(OUT/'source_cuts'/f'{name}.png').convert('RGBA')
  if name in SOURCE_AXES:
   origin,j=SOURCE_AXES[name];b=BIND[name];a=math.degrees(math.atan2(b['joint'][1]-b['pivot'][1],b['joint'][0]-b['pivot'][0])-math.atan2(j[1]-origin[1],j[0]-origin[0]));source_rotations[name]=a
   im=warp(im,a,origin,b['pivot']);cap=Image.new('RGBA',(864,480));d=ImageDraw.Draw(cap);x,y=b['pivot'];radius=19 if name=='arm_near' else 13 if name=='arm_far' else 24
   # Small proximal overlap hidden by head/torso/briefs; source pixels restored above.
   d.ellipse((x-radius,y-17,x+radius,y+20),fill=(244,217,191,255));cap.alpha_composite(im);im=cap
  layers[name]=im
 # Preserve the observed distal contour. Completion is confined to the hinge;
 # never resize generated artwork over the complete hand/foot silhouette.
 for n in SOURCE_AXES:
  origin,j=SOURCE_AXES[n];b=BIND[n]
  original=unpose(n)
  if n=='leg_near':
   secondary=unpose(n,(66,[(375,386),(389,381),(406,386),(423,395),(440,407),(442,415),(434,429),(435,442),(440,452),(437,461),(426,467),(411,470),(397,468),(384,463),(377,454),(374,442),(375,427),(374,411)]))
   # Use the exposed upper thigh from frame 66; retain the lifted foot from 82.
   aa=np.array(secondary);yy,xx=np.mgrid[:480,:864];v=np.subtract(b['joint'],b['pivot']);dd=((xx-b['pivot'][0])*v[0]+(yy-b['pivot'][1])*v[1])/np.linalg.norm(v)
   aa[:,:,3]=np.uint8(aa[:,:,3]*np.clip((37-dd)/12,0,1));under=Image.fromarray(aa);under.alpha_composite(original);original=under
  a=np.array(original);yy,xx=np.mgrid[:480,:864]
  vx,vy=np.subtract(b['joint'],b['pivot']);length=math.hypot(vx,vy)
  along=((xx-b['pivot'][0])*vx+(yy-b['pivot'][1])*vy)/length
  across=((xx-b['pivot'][0])*vy-(yy-b['pivot'][1])*vx)/length
  radius={'arm_near':21,'arm_far':15,'leg_near':25,'leg_far':22}[n]
  cap=((across/radius)**2+((along-9)/22)**2<1)
  # Inpaint only a local proximal patch from this SAME video crop. Remove the
  # artificial cut boundary here while retaining every distal source pixel.
  patch=(abs(across)<radius+5)&(along>-20)&(along<38)
  known=(a[:,:,3]>240)&(along>17)&(abs(across)<radius-3)
  fill=np.median(a[:,:,:3][known],axis=0).astype('uint8')
  rgb=a[:,:,:3].copy();rgb[a[:,:,3]<240]=fill
  repair=((along<(23 if n.startswith('leg_') else 12))&patch).astype('uint8')*255
  rgb=cv2.inpaint(rgb,repair,5,cv2.INPAINT_TELEA)
  cap_alpha=np.clip((1-((across/radius)**2+((along-9)/22)**2))*8,0,1)*255
  alpha=np.maximum(a[:,:,3],cap_alpha.astype('uint8'))
  weight=np.clip((along-(18 if n.startswith('leg_') else 7))/14,0,1)
  weight*=a[:,:,3]/255
  rgb=np.uint8(rgb*(1-weight[:,:,None])+a[:,:,:3]*weight[:,:,None])
  # RGB outside the original is supplied only inside the hinge extension.
  rgb[(a[:,:,3]<128)&cap]=fill
  if n.startswith('arm_'):
   # The proximal cap blends into the torso beneath it, avoiding a closed
   # outline around the shoulder. The hand and forearm remain fully opaque.
   alpha=np.uint8(alpha*np.clip((along+12)/17,0,1))
  layers[n]=Image.fromarray(np.dstack([rgb,alpha]))
  Image.fromarray(np.uint8((1-weight)*255)).save(OUT/'masks'/f'{n}_proximal_repair.png')
 # AI is restricted to occluded torso; visible belly remains from source frame 82.
 donor=Image.open(OUT/'torso_completion.png').convert('RGBA');a=np.array(donor);a[:,:,3]=matte(donor);donor=Image.fromarray(a);donor=donor.crop(donor.getbbox()).resize((112,107),Image.Resampling.LANCZOS)
 body=Image.new('RGBA',(864,480));body.alpha_composite(donor,(389,281))
 visible=cut(82,[(421,301),(478,299),(487,323),(495,348),(494,359),(477,365),(447,368),(419,364),(402,359),(414,341),(421,325)])
 # Match the hidden donor's fabric to the actual video belly before feathering.
 ba=np.array(body).astype(float);va=np.array(visible).astype(float);valid=(va[:,:,3]>250)&(ba[:,:,3]>250)
 for channel in range(3):
  delta=np.median(va[:,:,channel][valid])-np.median(ba[:,:,channel][valid]);ba[:,:,channel]=np.clip(ba[:,:,channel]+delta,0,255)
 body=Image.fromarray(ba.astype('uint8'))
 alpha=va[:,:,3].astype('uint8');dist=cv2.distanceTransform((alpha>128).astype('uint8'),cv2.DIST_L2,3);va[:,:,3]=alpha*np.clip(dist/6,0,1)
 body.alpha_composite(Image.fromarray(va.astype('uint8')))
 layers['body']=body
 visible.getchannel('A').save(OUT/'masks/body_video_visible.png')
 source_config=json.loads((ROOT/'generated_rig/right_front_import_9c08a83c/reference.json').read_text(encoding='utf-8'));source_config['source'].update(clipStart=66,clipEnd=88)
 source_config['assetBase']='./generated_rig/video_parts_v3/images/';source_config['assetRevision']='video-parts-v3';source_config['assetOrigin']={'status':'video_keyframe_extraction','manifest':'./generated_rig/video_parts_v3/source_manifest.json'}
 names={'head':'头部','body':'躯干','shorts':'短裤','arm_near':'近侧手臂','arm_far':'远侧手臂','leg_near':'近侧腿脚','leg_far':'远侧腿脚'}
 order=['leg_far','leg_near','arm_far','body','shorts','arm_near','head'];records=[];parts=[]
 previous=LANDMARKS;frames=previous['frames']
 for name in ['head','body','shorts','arm_near','arm_far','leg_near','leg_far']:
  im=world(layers[name]);b=BIND[name];f=PARTS[name][0] if name in PARTS else 82
  if name.startswith('arm_') and (OUT/'root_repair_ai.png').exists():
   mapping=json.loads((OUT/'root_repair_mapping.json').read_text())[name]
   atlas=Image.open(OUT/'root_repair_ai.png').convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS)
   x,y,w,h=[mapping[k] for k in ['x','y','w','h']];bb=mapping['bbox']
   donor=atlas.crop((x,y,x+w,y+h)).resize((bb[2]-bb[0],bb[3]-bb[1]),Image.Resampling.LANCZOS)
   da=np.array(donor);da[:,:,3]=matte(donor);donor=Image.fromarray(da)
   layer=Image.new('RGBA',(768,768));layer.alpha_composite(donor,(bb[0],bb[1]))
   src=np.array(im).astype(float)/255;dst=np.array(layer).astype(float)/255
   yy,xx=np.mgrid[:768,:768];pivot=pt(b['pivot']);joint=pt(b['joint']);vx,vy=np.subtract(joint,pivot)
   along=((xx-pivot[0])*vx+(yy-pivot[1])*vy)/math.hypot(vx,vy)
   keep=np.clip((along-24)/22,0,1)[:,:,None]
   valid=(src[:,:,3]>.95)&(dst[:,:,3]>.95)&(along>28)&(along<55)
   if valid.any():
    for ch in range(3):dst[:,:,ch]=np.clip(dst[:,:,ch]+np.median(src[:,:,ch][valid]-dst[:,:,ch][valid]),0,1)
   src[:,:,:3]*=src[:,:,3:4];dst[:,:,:3]*=dst[:,:,3:4]
   mix=src*keep+dst*(1-keep);mix[:,:,:3]=np.divide(mix[:,:,:3],mix[:,:,3:4],out=np.zeros_like(mix[:,:,:3]),where=mix[:,:,3:4]>.001)
   im=Image.fromarray(np.uint8(np.clip(mix*255,0,255)))
  box=im.getbbox();im.crop(box).save(OUT/'images'/f'{name}.png')
  bind={k:pt(v) if k in ['pivot','joint','tip'] else v for k,v in b.items()};keys=[]
  for i,frame in enumerate(frames):
   angle=bend=dx=dy=0
   if name in SOURCE_AXES:
    A,J,T=previous['points'][name][i];angle=math.degrees(math.atan2(J[1]-A[1],J[0]-A[0])-math.atan2(b['joint'][1]-b['pivot'][1],b['joint'][0]-b['pivot'][0]));bend=math.degrees(math.atan2(T[1]-J[1],T[0]-J[0])-math.atan2(J[1]-A[1],J[0]-A[0])-math.atan2(b['tip'][1]-b['joint'][1],b['tip'][0]-b['joint'][0])+math.atan2(b['joint'][1]-b['pivot'][1],b['joint'][0]-b['pivot'][0]))
   if name in SOURCE_AXES:
    dx=(A[0]-b['pivot'][0])*1.4;dy=(A[1]-b['pivot'][1])*1.4
   if name=='head':angle=[-1,0,1,2,3,0,-1][i]
   keys.append({'time':(frame-66)/24,'x':dx,'y':dy,'angle':round(angle,5),'bend':round(bend,5),'interpolation':'linear'})
  for k in ['x','y','angle','bend']:keys[0][k]=round((keys[0][k]+keys[-1][k])/2,5)
  keys[-1]={**keys[0],'time':22/24}
  evidence=[{'frame':f,'visibility':'uncertain' if name.endswith('far') else 'visible','note':f'附件可见像素重新提取自视频第 {f} 帧；根部小范围延展为隐藏搭接，躯干隐藏区使用本轮 AI 补图。','points':PARTS[name][1] if name in PARTS else [],'origin':'review_candidate'}]
  part={'id':name,'name':names[name],'bbox':list(box),**bind,'order':order.index(name),'visible':True,'texture':'legacy','polygon':[],'keys':keys,'evidence':evidence}
  # Independent full proximal caps remove the need for the previous root-pinning workaround.
  if 'joint' in bind:part['blend']=60

  parts.append(part)
  records.append({'id':name,'label':names[name],'file':f'{name}.png','sha256':hashlib.sha256((OUT/'images'/f'{name}.png').read_bytes()).hexdigest(),'bbox':list(box),'width':box[2]-box[0],'height':box[3]-box[1],'sourceFrame':f,'sourceFrames':([66,82] if name=='leg_near' else [f]),'sourcePixelOnly':name in ['head','shorts'],'hiddenComplete':False,'status':'video_keyframe_extracted_pending_visual_acceptance'})
 draft={'schema':'walulu-video-rig-draft/1','source':source_config['source'],'fps':24,'duration':22/24,'productionApproved':False,'parts':parts,'assetRevision':'video-parts-v3'}
 source_config['parts']=records;source_config['initialDraft']=draft
 source_config['review']='./generated_rig/video_parts_v3/review.png';source_config['partsReview']='./generated_rig/video_parts_v3/parts_review.png'
 for rec in records:
  rec['sourceCrop']='./generated_rig/video_parts_v3/source_cuts/'+rec['id']+'_crop.png' if rec['id']!='body' else './generated_rig/right_front_import_9c08a83c/frames/082.png'
  rec['repairMethod']=('视频原帧裁片' if rec['sourcePixelOnly'] else '视频第 66 / 82 帧融合，根部局部纹理延展' if rec['id']=='leg_near' else '视频第 70 帧取件，根部局部纹理延展' if rec['id']=='leg_far' else '视频原始手掌保留；肩根局部 AI 补图' if rec['id'].startswith('arm_') else '沿用上一轮躯干遮挡补图；尚待重建')
 source_config['exportReference']='./generated_rig/video_parts_v3/reference.json'
 # The cut workspace now uses the actual video frame, not the previous source artwork.
 ref=world(Image.open(FR/'066.png').convert('RGBA'));ref.save(OUT/'images/source_reference.png');source_config['source']['imageSha']=hashlib.sha256((OUT/'images/source_reference.png').read_bytes()).hexdigest()
 for name,obj in [('reference.json',source_config),('draft.json',draft),('landmarks.json',previous)]: (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
 setup=Image.new('RGBA',(768,768))
 for n in order:
  rec=next(r for r in records if r['id']==n)
  setup.alpha_composite(Image.open(OUT/'images'/rec['file']).convert('RGBA'),tuple(rec['bbox'][:2]))
 setup.save(OUT/'assembly.png')
 sheet=Image.new('RGB',(1200,800),'#c5d5de');d=ImageDraw.Draw(sheet)
 for i,rec in enumerate(records):
  im=Image.open(OUT/'images'/rec['file']);im.thumbnail((250,320));x=i%4*300;y=i//4*400;sheet.paste(im,(x+(280-im.width)//2,y+40),im);d.text((x+10,y+10),f"{rec['id']} / frame {rec['sourceFrame']}",fill='black')
 setup.thumbnail((260,330));sheet.paste(setup,(920,440),setup);d.text((920,410),'Common bind pose',fill='black');sheet.save(OUT/'parts_review.png')
 (OUT/'rig-reference-config.js').write_text('window.RigReferenceConfig = '+json.dumps(source_config,ensure_ascii=False)+';\n',encoding='utf-8')
 print('Built video-derived attachments',OUT)
if __name__=='__main__':
 main();assemble()



