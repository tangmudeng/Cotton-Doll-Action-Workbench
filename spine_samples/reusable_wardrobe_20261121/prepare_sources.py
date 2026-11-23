"""Remove observed cross-part slivers; never add RGB or fill unknown surfaces."""
from pathlib import Path
import json,hashlib,shutil
import numpy as np
import cv2
from PIL import Image
HERE=Path(__file__).resolve().parent;BASE=HERE.parent/'video_motion_study_20261119/pixel_sync_20261120';OUT=HERE/'clean_sources'
OUT.mkdir(exist_ok=True);(OUT/'parts').mkdir(exist_ok=True)
for name in ['skin.json','pixel_manifest.json']:shutil.copy2(BASE/name,OUT/name)
probe=json.loads((HERE/'probe.json').read_text('utf-8'));manifest=json.loads((BASE/'pixel_manifest.json').read_text('utf-8'));records=[]
for m in manifest:
    im=np.array(Image.open(BASE/m['file']).convert('RGBA'));before=im.copy();part=m['part'];frame=m['sourceFrame']
    if part.startswith('leg_'):
        b=next(b for b in probe[frame-63]['bones'] if b['name']==part+'_upper')
        # The thigh surface starts at the hip. Remove torso/waist pixels above it.
        cut=int(np.floor(480-b['y']-3))-m['crop'][1]
        im[:max(0,cut),:,3]=0
    if part!='head':
        count,labels,stats,_=cv2.connectedComponentsWithStats((im[:,:,3]>16).astype(np.uint8),8)
        if count>1:
            keep=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]));core=(labels==keep).astype(np.uint8)
            # Preserve original antialias around the retained component.
            support=cv2.dilate(core,np.ones((3,3),np.uint8));im[:,:,3][support==0]=0
    Image.fromarray(im).save(OUT/m['file'])
    assert np.array_equal(before[:,:,:3],im[:,:,:3])
    records.append({'part':part,'sourceFrame':frame,'originalSHA256':hashlib.sha256((BASE/m['file']).read_bytes()).hexdigest(),'removedAlphaPixels':int(((before[:,:,3]>0)&(im[:,:,3]==0)).sum()),'changedRGBPixels':0})
(OUT/'cleanup.json').write_text(json.dumps(records,indent=2),encoding='utf-8');print('Prepared observed source parts; alpha-only cleanup, no added pixels.')
