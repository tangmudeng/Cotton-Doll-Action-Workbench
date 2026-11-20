"""Build a new video-directed walk candidate without changing historical candidates."""
from pathlib import Path
import json,math,hashlib,shutil,subprocess
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'generated_rig/walk_acceptance_v1'
OLD=ROOT/'generated_rig/video_f7e82942/stable_parts_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
BIND={ 'body':{'parent':None,'pivot':[410,537]},'head':{'parent':'body','pivot':[407,440]},'shorts':{'parent':'body','pivot':[410,537]},'arm_near':{'parent':'body','pivot':[351,451],'joint':[331,506],'tip':[320,562]},'arm_far':{'parent':'body','pivot':[463,454],'joint':[480,490],'tip':[488,538]},'leg_near':{'parent':'shorts','pivot':[366,564],'joint':[362,608],'tip':[363,649]},'leg_far':{'parent':'shorts','pivot':[439,558],'joint':[443,597],'tip':[443,634]}}
FRAMES=[66,70,74,78,82,86,88]
LANDMARKS={
'arm_near':[[[399,290],[394,337],[394,380]],[[402,292],[415,339],[428,380]],[[402,294],[404,337],[412,380]],[[402,304],[382,346],[370,382]],[[404,307],[366,339],[350,369]],[[405,302],[382,344],[373,381]],[[402,290],[392,338],[390,382]]],
'arm_far':[[[487,292],[496,322],[502,351]],[[488,295],[487,323],[491,349]],[[488,294],[490,323],[493,352]],[[488,300],[510,333],[516,359]],[[488,306],[521,332],[530,354]],[[488,300],[506,329],[512,354]],[[487,292],[496,322],[502,351]]],
'leg_near':[[[413,388],[404,420],[404,448]],[[413,385],[392,412],[389,445]],[[411,386],[395,417],[390,447]],[[411,387],[416,420],[422,448]],[[412,387],[437,419],[446,448]],[[413,385],[421,418],[420,450]],[[413,387],[410,422],[410,450]]],
'leg_far':[[[477,380],[478,410],[480,440]],[[477,379],[496,408],[506,431]],[[477,380],[488,410],[490,440]],[[477,380],[457,409],[452,437]],[[477,380],[457,409],[453,435]],[[477,380],[467,408],[469,433]],[[477,380],[481,408],[482,435]]]
}
def angle(a,b):return math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
def prepare_part(record):
 n=record['id'];box=record['bbox'];original=Image.new('RGBA',(768,768));original.alpha_composite(Image.open(OLD/record['file']).convert('RGBA'),(box[0],box[1]));layer=Image.new('RGBA',(768,768))
 if n=='body':
  donor=Image.open(OLD.parent/'image2_repairs/body_candidate_v5.png').convert('RGBA').crop((254,196,1029,1096)).resize((182,211),Image.Resampling.LANCZOS)
  da=np.array(donor);da[:,:,:3]=np.clip(da[:,:,:3].astype(float)+[-2,-10,-13],0,255).astype('uint8');donor=Image.fromarray(da);layer.alpha_composite(donor,(316,407));arr=np.array(layer);mask=Image.new('L',(768,768));ImageDraw.Draw(mask).polygon([(351,425),(450,425),(480,444),(490,510),(470,527),(440,537),(398,540),(355,535),(337,526),(330,480)],fill=255);arr[:,:,3]=np.minimum(arr[:,:,3],np.asarray(mask));layer=Image.fromarray(arr)
 elif n=='shorts':
  hi=Image.new('RGBA',(768*3,768*3));d=ImageDraw.Draw(hi);poly=[(337,530),(357,535),(351,544),(345,559),(337,551)]
  pts=[(x*3,y*3) for x,y in poly];d.polygon(pts,fill=(255,240,222,255));d.line([pts[0],pts[-1],pts[-2]],fill=(160,108,76,255),width=4);layer=hi.resize((768,768),Image.Resampling.LANCZOS)
 elif n.startswith('leg_'):
  # Only a proximal hidden cap is added; existing visible pixels remain intact.
  px,py=BIND[n]['pivot'];radius=28 if 'arm' in n else 38
  hi=Image.new('RGBA',(768*3,768*3));d=ImageDraw.Draw(hi);color=(250,220,190,255)
  d.ellipse(((px-radius)*3,(py-24)*3,(px+radius)*3,(py+35)*3),fill=color)
  layer=hi.resize((768,768),Image.Resampling.LANCZOS)
 layer.alpha_composite(original)
 bounds=layer.getbbox();layer.crop(bounds).save(OUT/'images'/record['file']);record['bbox']=list(bounds);record['width']=bounds[2]-bounds[0];record['height']=bounds[3]-bounds[1];record['sha256']=sha(OUT/'images'/record['file']);record['status']='video_directed_seven_parts_hidden_root_completion';record['hiddenComplete']=False
 return record
def main():
 OUT.mkdir(exist_ok=True);(OUT/'images').mkdir(exist_ok=True)
 c=json.loads((ROOT/'generated_rig/right_front_import_9c08a83c/reference.json').read_text(encoding='utf-8'));c['source'].update(clipStart=66,clipEnd=88)
 c['assetBase']='./generated_rig/walk_acceptance_v1/images/';c['assetOrigin']={'status':'seven_source_parts_video_directed_binding','sourceManifest':str(OLD/'manifest.json')}
 order=['leg_far','leg_near','body','shorts','arm_far','arm_near','head'];parts=[]
 for old in c['parts']:
  n=old['id'];old=prepare_part(old);b={**BIND[n]};
  if n.startswith('leg_'):b['rootBand']=[-20,30]
  keys=[]
  for i,f in enumerate(FRAMES):
   a=be=0;dy=0
   if n in LANDMARKS:
    A,J,T=LANDMARKS[n][i];ra=angle(b['pivot'],b['joint']);rl=angle(b['joint'],b['tip']);ua=angle(A,J);la=angle(J,T);a=ua-ra;be=(la-ua)-(rl-ra)
    assert abs(be)<=60,(n,f,be)
   if n=='body':dy=[0,1.25,3.75,7.5,11.25,2.5,0][i]
   if n=='head':a=[-1,0,1,2,3,0,-1][i]
   keys.append({'time':(f-66)/24,'x':0,'y':dy,'angle':round(a,5),'bend':round(be,5),'interpolation':'linear'})
  if n in LANDMARKS:
   for k in ['angle','bend']:keys[0][k]=round((keys[0][k]+keys[-1][k])/2,5)
  keys[-1]={**keys[0],'time':22/24}
  evidence=[{'frame':f,'visibility':'uncertain' if n.endswith('far') else 'visible','note':'按指定右前行走视频人工观察标记；遮挡点为估计，供拟合与验收对照，非自动恢复。','points':LANDMARKS[n][i] if n in LANDMARKS else [],'origin':'review_candidate'}for i,f in enumerate(FRAMES)]
  parts.append({'id':n,'name':old['label'],'bbox':old['bbox'],**b,'order':order.index(n),'visible':True,'texture':'legacy','polygon':[],'evidence':evidence,'keys':keys})
 shutil.copy2(OLD/'source_reference.png',OUT/'images/source_reference.png')
 draft={'schema':'walulu-video-rig-draft/1','source':c['source'],'fps':24,'duration':22/24,'productionApproved':False,'parts':parts}
 c['initialDraft']=draft;c['clipReason']='66–88，躯干/四肢 ROI 的重复匹配候选；骨骼端点平均闭合，视频本身不完全重合。';c['exportReference']='./generated_rig/walk_acceptance_v1/reference.json'
 for name,obj in [('reference.json',c),('draft.json',draft),('landmarks.json',{'frames':FRAMES,'points':LANDMARKS,'method':'manual visual semantic points; hidden points estimated; limb directions transferred without shrinking swing amplitude','endpoints':'66/88 averaged for closed curve'})]:
  (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
 (ROOT/'rig-reference-config.js').write_text('window.RigReferenceConfig = '+json.dumps(c,ensure_ascii=False)+';\n',encoding='utf-8')
 subprocess.run(['node','export_rig_cli.cjs',str(OUT/'draft.json'),str(OUT),str(OUT/'reference.json')],cwd=ROOT,check=True)
 pack=json.loads((OUT/'packing.json').read_text());page=Image.new('RGBA',(pack['width'],pack['height']))
 for n,r in pack['regions'].items():
  im=Image.open(OUT/'images'/f'{n}.png').convert('RGBA');a=np.asarray(im);page.paste(Image.fromarray(np.pad(a,((4,4),(4,4),(0,0)),mode='edge')),(r['x']-4,r['y']-4))
 page.save(OUT/'walulu_walk.png')
 print('Built independent walk',OUT)
if __name__=='__main__':main()
