from pathlib import Path
import cv2,numpy as np,json
from PIL import Image,ImageDraw
from scipy.ndimage import distance_transform_edt
R=Path(__file__).resolve().parent;src=np.array(Image.open(R/'reference/walk_bind.png').convert('RGB'));gen=np.array(Image.open(R/'hidden_body_shorts.png').convert('RGB'))
# Register unchanged feet/shorts/right torso to the approved source crop, not the erased arm.
target=src[400:650,270:530];large=cv2.resize(target,(1024,1024));sift=cv2.SIFT_create();k1,d1=sift.detectAndCompute(cv2.cvtColor(gen,cv2.COLOR_RGB2GRAY),None);k2,d2=sift.detectAndCompute(cv2.cvtColor(large,cv2.COLOR_RGB2GRAY),None);matches=cv2.BFMatcher().knnMatch(d1,d2,k=2);good=[a for a,b in matches if a.distance<.73*b.distance];a=np.float32([k1[m.queryIdx].pt for m in good]);b=np.float32([k2[m.trainIdx].pt for m in good]);M,inliers=cv2.estimateAffinePartial2D(a,b,method=cv2.RANSAC,ransacReprojThreshold=5);assert M is not None
# Explicit contour landmarks keep waistband and crotch on the approved silhouette.
from scipy.spatial import Delaunay
sp=np.float32([[0,0],[1023,0],[1023,1023],[0,1023],[350,60],[650,60],[228,365],[790,385],[500,457],[170,520],[820,493],[500,700],[50,800],[390,940],[990,800]])
dp=np.float32([[270,400],[530,400],[530,650],[270,650],[355,415],[443,415],[322,497],[471,500],[397,518],[312,535],[476,526],[397,581],[283,600],[367,635],[522,600]])
fill=src.copy()
for tri in Delaunay(dp).simplices:
 dst=dp[tri];sourcepts=sp[tri];mat=cv2.getAffineTransform(sourcepts,dst);warped=cv2.warpAffine(gen,mat,(768,768),flags=cv2.INTER_LINEAR,borderValue=(255,255,255));m=np.zeros((768,768),np.uint8);cv2.fillConvexPoly(m,np.round(dst).astype('int32'),255);fill[m>0]=warped[m>0]
places=json.loads((R/'placements.json').read_text());layers={}
for n,box in places.items():
 f=np.zeros((768,768,4),np.uint8);f[box[1]:box[3],box[0]:box[2]]=np.array(Image.open(R/'parts'/f'{n}.png'));layers[n]=f
# Color offsets from the still-visible chest and fabric respectively.
for n,patch in [('body',(420,450,439,480)),('shorts',(425,532,442,544))]:
 x0,y0,x1,y1=patch;delta=np.median(src[y0:y1,x0:x1].reshape(-1,3),axis=0)-np.median(fill[y0:y1,x0:x1].reshape(-1,3),axis=0);colored=np.uint8(np.clip(fill.astype(float)+delta,0,255));layer=layers[n];occ=layers['arm_near'][:,:,3];m=cv2.dilate((occ>0).astype('uint8'),np.ones((13,13),np.uint8))*255
 # Use the completed substrate across each surface to avoid patch-border artifacts.
 layer[:,:,:3]=colored
 if n=='body':
  yy=np.indices(m.shape)[0];skin=colored[450:480,413:439];texture=cv2.resize(skin,(768,768),interpolation=cv2.INTER_CUBIC)
  layer[:,:,:3][yy>512]=texture[yy>512]
  # Head covers the rebuilt neck; original chest color is retained by correction above.
 layers[n]=layer
# Replace far-arm fragment by the full limb from the approved standing panel.
stand=np.array(Image.open(R/'reference/stand_bind.png').convert('RGB'));mask=np.zeros((768,768),np.uint8)
pts=np.array([(446,438),(457,437),(474,455),(489,478),(503,506),(505,526),(497,543),(482,550),(473,542),(466,516),(459,488),(449,460)],np.int32);cv2.fillPoly(mask,[pts],255)
rot=cv2.getRotationMatrix2D((453,447),-16,0.88);rot[:,2]+=np.array([-4,-20]);ar=cv2.warpAffine(np.dstack([stand,mask]),rot,(768,768),flags=cv2.INTER_LINEAR);layers['arm_far']=ar
# Fill hidden leg roots with continuous nearest interior texture, then feather only the seam.
for n in ['leg_near','leg_far']:
 layer=layers[n];alpha=layer[:,:,3];yy,xx=np.indices(alpha.shape);safe=(alpha>250)&(yy>570)&(layer[:,:,0]>215)&(layer[:,:,1]>165);dist,idx=distance_transform_edt(~safe,return_indices=True);texture=layer[:,:,:3][idx[0],idx[1]];weight=np.clip((575-yy)/35,0,1)*(alpha>0);layer[:,:,:3]=np.uint8(layer[:,:,:3]*(1-weight[:,:,None])+texture*weight[:,:,None]);layers[n]=layer
# Remove contaminated white exterior pixels; retain brown contour alpha.
for n,f in layers.items():
 if n!='head':
  nearwhite=(f[:,:,:3].min(axis=2)>245);interior=cv2.distanceTransform((f[:,:,3]>0).astype('uint8'),cv2.DIST_L2,5);f[:,:,3][nearwhite&(interior<2.5)]=0
 out=Image.fromarray(f);box=out.getbbox();out.crop(box).save(R/'parts'/f'{n}.png');places[n]=box
(R/'placements.json').write_text(json.dumps(places,indent=2));(R/'hidden_registration.json').write_text(json.dumps({'registrationMethod':'piecewise affine Delaunay with explicit contour landmarks','sourceLandmarks':sp.tolist(),'targetLandmarks':dp.tolist(),'siftDiagnosticOnly':{'affine':M.tolist(),'inliers':int(inliers.sum()),'matches':len(good)},'edits':'continuous body and shorts repaint accepted by user; far arm from approved standing screenshot; hidden leg roots from local skin texture'},indent=2))
canvas=Image.new('RGBA',(768,768),'white')
for n in ['arm_far','leg_far','leg_near','body','shorts','arm_near','head']:canvas.alpha_composite(Image.open(R/'parts'/f'{n}.png'),places[n][:2])
canvas.save(R/'bind_assembly.png');cmp=Image.new('RGB',(1536,800),'white');cmp.paste(Image.fromarray(src),(0,32));cmp.paste(canvas,(768,32));d=ImageDraw.Draw(cmp);d.text((15,8),'APPROVED WALK',fill='black');d.text((783,8),'REPAIRED HIDDEN SURFACES',fill='black');cmp.save(R/'bind_comparison.png')
print('Registration',len(good),'matches',int(inliers.sum()),'inliers')
