from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np,cv2,json,math,hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'generated_rig/video_parts_v2';FR=ROOT/'generated_rig/right_front_import_9c08a83c/frames'
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
 a=np.array(im);a[:,:,3]=np.minimum(np.array(mask),matte(im));return Image.fromarray(a)

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
 # Limb completion artwork is used only for the missing hidden hinge areas.
 completed=Image.open(OUT/'limb_completion.png').convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS)
 tiles={'arm_near':(0,0,512,512),'arm_far':(512,0,1024,512),'leg_near':(0,512,512,1024),'leg_far':(512,512,1024,1024)}
 for n,tilebox in tiles.items():
  tile=completed.crop(tilebox);ta=np.array(tile);ta[:,:,3]=matte(tile);tile=Image.fromarray(ta);bbox=tile.getbbox();tile=tile.crop(bbox)
  targetbox=layers[n].getbbox();tile=tile.resize((targetbox[2]-targetbox[0],targetbox[3]-targetbox[1]),Image.Resampling.LANCZOS)
  donorlayer=Image.new('RGBA',(864,480));donorlayer.alpha_composite(tile,(targetbox[0],targetbox[1]))
  original=cut(*PARTS[n]);origin,j=SOURCE_AXES[n];b=BIND[n];original=warp(original,source_rotations[n],origin,b['pivot'])
  va=np.array(original).astype(float);da=np.array(donorlayer).astype(float);mask=(va[:,:,3]>250)&(da[:,:,3]>250)
  for ch in range(3):da[:,:,ch]=np.clip(da[:,:,ch]+np.median(va[:,:,ch][mask])-np.median(da[:,:,ch][mask]),0,255)
  donorlayer=Image.fromarray(da.astype('uint8'))
  # Preserve video interior/distal pixels; soften only the seam with the new cap.
  yy,xx=np.mgrid[:480,:864];vx=b['joint'][0]-b['pivot'][0];vy=b['joint'][1]-b['pivot'][1];distance=((xx-b['pivot'][0])*vx+(yy-b['pivot'][1])*vy)/math.hypot(vx,vy)
  edge=cv2.distanceTransform((va[:,:,3]>128).astype('uint8'),cv2.DIST_L2,3)
  weight=np.clip((distance-9)/12,0,1)*np.clip(edge/6,0,1);va[:,:,3]*=weight
  donorlayer.alpha_composite(Image.fromarray(va.astype('uint8')));layers[n]=donorlayer
  Image.fromarray(np.uint8(np.clip(weight*255,0,255))).save(OUT/'masks'/f'{n}_video_preserved.png')
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
 body.alpha_composite(Image.fromarray(va.astype('uint8')));layers['body']=body
 visible.getchannel('A').save(OUT/'masks/body_video_visible.png')
 source_config=json.loads((ROOT/'generated_rig/right_front_import_9c08a83c/reference.json').read_text(encoding='utf-8'));source_config['source'].update(clipStart=66,clipEnd=88)
 source_config['assetBase']='./generated_rig/video_parts_v2/images/';source_config['assetRevision']='video-parts-v2';source_config['assetOrigin']={'status':'video_keyframe_extraction','manifest':'./generated_rig/video_parts_v2/source_manifest.json'}
 names={'head':'头部','body':'躯干','shorts':'短裤','arm_near':'近侧手臂','arm_far':'远侧手臂','leg_near':'近侧腿脚','leg_far':'远侧腿脚'}
 order=['leg_far','leg_near','body','shorts','arm_far','arm_near','head'];records=[];parts=[]
 previous=json.loads((ROOT/'generated_rig/walk_acceptance_v1/landmarks.json').read_text(encoding='utf-8'));frames=previous['frames']
 for name in ['head','body','shorts','arm_near','arm_far','leg_near','leg_far']:
  im=world(layers[name]);box=im.getbbox();im.crop(box).save(OUT/'images'/f'{name}.png');b=BIND[name];f=PARTS[name][0] if name in PARTS else 82
  bind={k:pt(v) if k in ['pivot','joint','tip'] else v for k,v in b.items()};keys=[]
  for i,frame in enumerate(frames):
   angle=bend=dy=0
   if name in SOURCE_AXES:
    A,J,T=previous['points'][name][i];angle=math.degrees(math.atan2(J[1]-A[1],J[0]-A[0])-math.atan2(b['joint'][1]-b['pivot'][1],b['joint'][0]-b['pivot'][0]));bend=math.degrees(math.atan2(T[1]-J[1],T[0]-J[0])-math.atan2(J[1]-A[1],J[0]-A[0])-math.atan2(b['tip'][1]-b['joint'][1],b['tip'][0]-b['joint'][0])+math.atan2(b['joint'][1]-b['pivot'][1],b['joint'][0]-b['pivot'][0]))
   if name=='body':dy=[0,1,3,6,9,2,0][i]
   if name=='head':angle=[-1,0,1,2,3,0,-1][i]
   keys.append({'time':(frame-66)/24,'x':0,'y':dy,'angle':round(angle,5),'bend':round(bend,5),'interpolation':'linear'})
  for k in ['angle','bend']:keys[0][k]=round((keys[0][k]+keys[-1][k])/2,5)
  keys[-1]={**keys[0],'time':22/24}
  evidence=[{'frame':f,'visibility':'uncertain' if name.endswith('far') else 'visible','note':f'附件可见像素重新提取自视频第 {f} 帧；根部小范围延展为隐藏搭接，躯干隐藏区使用本轮 AI 补图。','points':PARTS[name][1] if name in PARTS else [],'origin':'review_candidate'}]
  part={'id':name,'name':names[name],'bbox':list(box),**bind,'order':order.index(name),'visible':True,'texture':'legacy','polygon':[],'keys':keys,'evidence':evidence}
  # Independent full proximal caps remove the need for the previous root-pinning workaround.
  if 'joint' in bind:part['blend']=40
  parts.append(part)
  records.append({'id':name,'label':names[name],'file':f'{name}.png','sha256':hashlib.sha256((OUT/'images'/f'{name}.png').read_bytes()).hexdigest(),'bbox':list(box),'width':box[2]-box[0],'height':box[3]-box[1],'sourceFrame':f,'sourcePixelOnly':name in ['head','shorts'],'hiddenComplete':False,'status':'video_keyframe_extracted_pending_visual_acceptance'})
 draft={'schema':'walulu-video-rig-draft/1','source':source_config['source'],'fps':24,'duration':22/24,'productionApproved':False,'parts':parts,'assetRevision':'video-parts-v2'}
 source_config['parts']=records;source_config['initialDraft']=draft
 source_config['review']='./generated_rig/video_parts_v2/review.png';source_config['partsReview']='./generated_rig/video_parts_v2/parts_review.png'
 for rec in records:
  rec['sourceCrop']='./generated_rig/video_parts_v2/source_cuts/'+rec['id']+'_crop.png' if rec['id']!='body' else './generated_rig/video_parts_v2/frame_82_body_reference.png'
  rec['repairMethod']='视频原帧裁片' if rec['sourcePixelOnly'] else '视频裁片 + 本轮 AI 补足连接区，保留可见区域并融合接缝'
 source_config['exportReference']='./generated_rig/video_parts_v2/reference.json'
 # The cut workspace now uses the actual video frame, not the previous source artwork.
 ref=world(Image.open(FR/'066.png').convert('RGBA'));ref.save(OUT/'images/source_reference.png');source_config['source']['imageSha']=hashlib.sha256((OUT/'images/source_reference.png').read_bytes()).hexdigest()
 for name,obj in [('reference.json',source_config),('draft.json',draft),('landmarks.json',previous)]: (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
 setup=Image.new('RGBA',(768,768))
 for n in order:setup.alpha_composite(world(layers[n]))
 setup.save(OUT/'assembly.png')
 sheet=Image.new('RGB',(1200,800),'#c5d5de');d=ImageDraw.Draw(sheet)
 for i,rec in enumerate(records):
  im=Image.open(OUT/'images'/rec['file']);im.thumbnail((250,320));x=i%4*300;y=i//4*400;sheet.paste(im,(x+(280-im.width)//2,y+40),im);d.text((x+10,y+10),f"{rec['id']} / frame {rec['sourceFrame']}",fill='black')
 setup.thumbnail((260,330));sheet.paste(setup,(920,440),setup);d.text((920,410),'Common bind pose',fill='black');sheet.save(OUT/'parts_review.png')
 (ROOT/'rig-reference-config.js').write_text('window.RigReferenceConfig = '+json.dumps(source_config,ensure_ascii=False)+';\n',encoding='utf-8')
 print('Built video-derived attachments',OUT)
if __name__=='__main__':
 main();assemble()
