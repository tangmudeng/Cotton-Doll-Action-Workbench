from pathlib import Path
import json,cv2,numpy as np
from PIL import Image,ImageDraw
from scipy.interpolate import CubicSpline
R=Path(__file__).resolve().parent;O=R/'parts';O.mkdir(exist_ok=True)
src=np.array(Image.open(R/'reference/walk_bind.png').convert('RGB'));H,W=src.shape[:2]
# Derive exterior alpha from the approved artwork; no generated parts are read.
bin=(src.min(axis=2)<235).astype('uint8');cs,_=cv2.findContours(bin,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);sil=np.zeros((H,W),np.uint8);cv2.drawContours(sil,[max(cs,key=cv2.contourArea)],-1,255,-1)
sil=cv2.dilate(sil,np.ones((3,3),np.uint8))
def mask(points):
 a=np.zeros((H*3,W*3),np.uint8);p=np.array(points+[points[0]],float);v=CubicSpline(np.arange(len(p)),p,bc_type='periodic')(np.linspace(0,len(p)-1,600));cv2.fillPoly(a,[np.round(v*3).astype('int32')],255);return np.array(Image.fromarray(a).resize((W,H),Image.Resampling.LANCZOS))
near=[(351,410),(372,414),(383,442),(394,464),(408,488),(417,509),(417,528),(405,542),(391,551),(371,545),(356,533),(347,512),(339,489),(334,466),(337,439)]
shorts=[(322,497),(348,508),(389,518),(431,515),(471,500),(478,524),(461,537),(441,556),(418,573),(397,581),(383,575),(366,555),(345,541),(327,534),(311,535),(315,516)]
near_vis=[(312,535),(332,534),(351,542),(373,556),(391,576),(381,590),(367,606),(369,620),(355,638),(334,645),(310,638),(293,627),(283,612),(283,595),(291,581),(301,572)]
far_vis=[(476,526),(486,547),(498,573),(514,582),(523,597),(521,612),(508,624),(487,633),(463,639),(444,633),(431,617),(419,596),(408,579),(428,567),(451,545)]
polys={'body':[(350,402),(444,402),(457,437),(471,475),(477,511),(467,537),(426,566),(377,568),(318,536),(321,501),(330,462)],'arm_near':near,'arm_far':[(442,410),(453,419),(461,441),(464,468),(473,493),(472,506),(461,510),(449,495),(443,469),(438,440)],'shorts':shorts,'leg_near':[(312,535),(320,512),(344,507),(370,522),(390,547)]+near_vis[4:],'leg_far':[(423,545),(442,513),(465,510)]+far_vis[:13]}
masks={n:mask(p) for n,p in polys.items()};vis={'leg_near':mask(near_vis),'leg_far':mask(far_vis)}
# Construct hidden skin from local same-source texture and blend only within root overlap.
placements={};audit={}
for n,a in masks.items():
 rgb=src.copy();edit=np.zeros((H,W),np.uint8)
 if n.startswith('leg'):
  keep=vis[n];edit=((a>0)&(keep<250)).astype('uint8')*255
  # Explicitly exclude clothes and the adjacent limb from the rebuilt hidden root.
  patch=src[584:603,316:345] if n=='leg_near' else src[579:599,454:477]
  texture=cv2.resize(patch,(W,H),interpolation=cv2.INTER_CUBIC)
  rgb[edit>0]=texture[edit>0]
  # All approved visible leg pixels stay untouched.
  a=np.maximum(a,keep);external=np.minimum(a,sil);yy=np.indices(a.shape)[0];a=np.where(yy>575,external,a).astype('uint8')
 elif n=='body':
  patch=src[448:479,414:439];texture=cv2.resize(patch,(W,H),interpolation=cv2.INTER_CUBIC)
  cover=np.maximum(masks['arm_near'],masks['arm_far']);cover=np.maximum(cover,masks['shorts']);cover=cv2.dilate(cover,np.ones((7,7),np.uint8));edit=((cover>10)&(a>0)).astype('uint8')*255;rgb[edit>0]=texture[edit>0]
 elif n=='shorts':
  edit=((masks['arm_near']>5)&(a>0)).astype('uint8')*255
  # Inpaint arm occlusion only; preserve the original visible hems, crotch and far opening.
  rgb=cv2.inpaint(rgb,cv2.dilate(edit,np.ones((3,3),np.uint8)),5,cv2.INPAINT_TELEA)
 else:a=np.minimum(a,sil)
 out=Image.fromarray(np.dstack([rgb,a]));box=out.getbbox();out.crop(box).save(O/f'{n}.png');placements[n]=box;audit[n]={'editedPixelCount':int(np.sum(edit>0)),'source':'reference/walk_bind.png'}
# Head exterior and lower jaw copied exactly; no repainting.
headmask=np.zeros((H,W),np.uint8);headmask[:418]=255
a=np.minimum(headmask,sil);out=Image.fromarray(np.dstack([src,a]));box=out.getbbox();out.crop(box).save(O/'head.png');placements['head']=box
# Lock ALL visible pixels back to the approved artwork. Hidden completions remain underneath.
# This is restricted to source-derived contour partitions, not whole-frame animation.
order=['arm_far','leg_far','leg_near','body','shorts','arm_near','head']
layers={}
for n in order:
 full=np.zeros((H,W,4),np.uint8);b=placements[n];full[b[1]:b[3],b[0]:b[2]]=np.array(Image.open(O/f'{n}.png'));layers[n]=full
owner=np.full((H,W),-1,np.int16)
for i,n in enumerate(order):owner[layers[n][:,:,3]>64]=i
# Restore missed exterior contour pixels to the nearest drawn attachment, within 6px only.
from scipy.ndimage import distance_transform_edt
dist,idx=distance_transform_edt(owner<0,return_indices=True)
missing=(sil>0)&(owner<0)&(dist<6);owner[missing]=owner[idx[0][missing],idx[1][missing]]
for i,n in enumerate(order):
 full=layers[n];visible=(owner==i)&(sil>0)
 if n=='body':
  # Rebuild underneath the moving near arm, extending past its original interior stroke.
  covered=cv2.dilate(masks['arm_near'],np.ones((17,17),np.uint8))>0
  patch=src[448:479,414:439];texture=cv2.resize(patch,(W,H),interpolation=cv2.INTER_CUBIC)
  full[:,:,:3][covered]=texture[covered]
  visible=visible&(~covered)
 full[:,:,:3][visible]=src[visible];full[:,:,3][visible]=255
 # Remove painted source-white fringes outside the approved external contour in bind pose.
 full[:,:,3][(owner==i)&(sil==0)]=0
 out=Image.fromarray(full);box=out.getbbox();out.crop(box).save(O/f'{n}.png');placements[n]=box

canvas=Image.new('RGBA',(W,H),'white')
for n in ['arm_far','leg_far','leg_near','body','shorts','arm_near','head']:canvas.alpha_composite(Image.open(O/f'{n}.png'),placements[n][:2])
canvas.save(R/'bind_assembly.png');sheet=Image.new('RGB',(1536,800),'white');sheet.paste(Image.fromarray(src),(0,32));sheet.paste(canvas,(768,32));d=ImageDraw.Draw(sheet);d.text((15,8),'APPROVED WALK POSE',fill='black');d.text((783,8),'SOURCE-EXTRACTED BIND POSE / REVIEW',fill='black');sheet.save(R/'bind_comparison.png');(R/'placements.json').write_text(json.dumps(placements,indent=2));(R/'extraction_audit.json').write_text(json.dumps(audit,indent=2))
