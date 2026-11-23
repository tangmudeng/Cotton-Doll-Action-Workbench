"""Source-only cycle diagnostics and explicitly authored observations for a PSD trial.

No image generation, no video textures in the delivered skin. Hidden joints are
uncertain; sampled pose landmarks are human-style visual estimates, not mocap.
"""
from pathlib import Path
import json, hashlib
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
selection = json.loads((HERE/'selection.json').read_text('utf8'))
images = [cv2.imdecode(np.frombuffer((HERE/'frames'/f'{i:04}.png').read_bytes(),np.uint8),cv2.IMREAD_COLOR) for i in range(59,83)]
cap = cv2.VideoCapture(selection['sourceVideo'])
cap.set(cv2.CAP_PROP_POS_FRAMES, 83)
ok, boundary = cap.read(); cap.release(); assert ok
(HERE/'boundary_0083.png').write_bytes(cv2.imencode('.png',boundary)[1].tobytes())

def foreground(im):
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    mask = np.uint8((hsv[:,:,1]>30)&(hsv[:,:,2]<250))
    n,lab,stats,centers = cv2.connectedComponentsWithStats(mask)
    idx=1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
    return lab==idx,stats[idx,:4].tolist(),centers[idx].tolist()

masks=[foreground(im)[0] for im in images]
def change(a,b,ma,mb):
    union=ma|mb
    return dict(rgbMAE=float(np.abs(a.astype(float)-b).mean(axis=2)[union].mean()),
                silhouetteIoU=float((ma&mb).sum()/union.sum()))
changes=[change(images[i-1],images[i],masks[i-1],masks[i]) for i in range(1,24)]
seam=change(images[-1],images[0],masks[-1],masks[0])
boundary_match=change(boundary,images[0],foreground(boundary)[0],masks[0])
diagnosis=dict(start=59,endInclusive=82,endExclusive=83,duration=1,fps=24,
    seam82to59=seam,boundary83to59=boundary_match,
    adjacentMedianRGBMAE=float(np.median([v['rgbMAE'] for v in changes])),
    adjacentMaximumRGBMAE=max(v['rgbMAE'] for v in changes),
    frames=[dict(frame=i+59,bbox=foreground(im)[1],centroid=foreground(im)[2]) for i,im in enumerate(images)],
    note='Source pixels are not perfectly closed. Frame 83 is diagnostic only, not an extra animation frame. No automatic semantic acceptance.')
(HERE/'cycle_diagnostics.json').write_text(json.dumps(diagnosis,indent=2),encoding='utf8')

# Coordinates were inspected on body_keyframes.jpg, not copied from the old rig.
# Order: shoulder near/far, hand near/far, hip near/far, distal foot near/far.
keyframes={
59:[[421,298],[477,297],[444,351],[478,334],[416,369],[474,365],[391,400],[485,405]],
62:[[420,290],[477,291],[421,351],[485,333],[419,366],[472,365],[411,403],[465,405]],
65:[[421,287],[477,288],[398,342],[492,329],[426,365],[473,361],[425,406],[462,404]],
68:[[424,288],[480,289],[379,340],[509,332],[431,369],[473,363],[444,408],[451,393]],
71:[[423,295],[479,296],[371,344],[519,335],[425,373],[472,366],[440,407],[451,397]],
74:[[420,292],[479,292],[392,348],[496,337],[419,369],[475,364],[428,408],[464,401]],
77:[[419,289],[477,288],[410,345],[483,329],[415,363],[474,360],[410,407],[477,397]],
80:[[420,289],[476,290],[435,344],[478,327],[416,364],[475,361],[395,403],[496,394]],
82:[[421,295],[477,295],[444,349],[477,331],[416,368],[474,364],[390,399],[487,401]],
}
names=['shoulder_near','shoulder_far','hand_near','hand_far','hip_near','hip_far','foot_near','foot_far']
keylist=sorted(keyframes)
interpolator=PchipInterpolator(keylist,np.array([keyframes[k] for k in keylist]),axis=0)

# Head tracking uses robust image correspondences, independent of the authored limbs.
sift=cv2.SIFT_create();headmask=np.zeros(images[0].shape[:2],np.uint8);headmask[50:282,300:565]=255
k0,d0=sift.detectAndCompute(cv2.cvtColor(images[0],cv2.COLOR_BGR2GRAY),headmask)
matcher=cv2.BFMatcher();poses=[]
for i,im in enumerate(images):
    frame=i+59;k,d=sift.detectAndCompute(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),headmask)
    matches=[m for m,n in matcher.knnMatch(d0,d,k=2) if m.distance<.72*n.distance]
    a=np.float32([k0[m.queryIdx].pt for m in matches]);b=np.float32([k[m.trainIdx].pt for m in matches])
    mat,inliers=cv2.estimateAffinePartial2D(a,b,method=cv2.RANSAC,ransacReprojThreshold=2)
    assert mat is not None and inliers.sum()>10
    row=dict(frame=frame,time=i/24,points=dict(zip(names,interpolator(frame).round(4).tolist())),
        headMatrix=mat.tolist(),headInliers=int(inliers.sum()),
        landmarkMethod='visual observation' if frame in keyframes else 'PCHIP interpolation between observed key poses',
        uncertainties=['All shoulder/hip centers and elbow/knee anatomy are inferred beneath the surface.'])
    if 65<=frame<=74:
        row['uncertainties'].append('Far foot is partly or fully occluded; its target is an uncertain continuity estimate, placed behind the visible near foot, not the visible pants tip.')
        row['inferredPoints']=['foot_far']
    if frame<=62 or frame>=78:row['uncertainties'].append('Far hand is mostly occluded.')
    poses.append(row)
(HERE/'motion_observations.json').write_text(json.dumps(dict(
    sourceSha256=selection['sourceSha256'],coordinateSpace='864x480 source pixels',
    automaticPoseExtraction=False,observedFrames=keylist,frames=poses),indent=2),encoding='utf8')

sheet=Image.new('RGB',(4*400,6*350),'#f4f5f3');draw=ImageDraw.Draw(sheet)
for i,row in enumerate(poses):
    im=Image.open(HERE/'frames'/f'{row["frame"]:04}.png').crop((330,275,530,440)).resize((400,330))
    d=ImageDraw.Draw(im)
    for n,xy in row['points'].items():
        x,y=(xy[0]-330)*2,(xy[1]-275)*2;c='#f16152' if n.endswith('near') else '#158fc4'
        d.ellipse((x-4,y-4,x+4,y+4),fill=c)
    sheet.paste(im,(i%4*400,i//4*350+20));draw.text((i%4*400+4,i//4*350+3),str(row['frame']),fill='black')
sheet.save(HERE/'observations_contact.jpg',quality=93)
print(json.dumps({k:diagnosis[k] for k in ['seam82to59','boundary83to59','adjacentMedianRGBMAE','adjacentMaximumRGBMAE']}))
