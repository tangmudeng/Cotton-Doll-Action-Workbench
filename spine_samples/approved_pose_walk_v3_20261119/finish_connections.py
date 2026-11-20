from pathlib import Path
import numpy as np,cv2,json
from PIL import Image
from scipy.ndimage import distance_transform_edt
r=Path.cwd();places=json.loads(Path('placements.json').read_text());b=places['arm_near'];im=np.array(Image.open('parts/arm_near.png'));yy,xx=np.indices(im.shape[:2]);fade=np.clip((yy+b[1]-417)/17,0,1);im[:,:,3]=(im[:,:,3]*fade).astype('uint8');Image.fromarray(im).save('parts/arm_near.png')
for n in ['leg_near','leg_far']:
 im=np.array(Image.open(r.parent/'approved_pose_walk_20261119'/'parts'/f'{n}.png').convert('RGBA'));alpha=im[:,:,3];dist,idx=distance_transform_edt(alpha<200,return_indices=True);yy,xx=np.indices(alpha.shape);added=(alpha<200)&(dist<=1.5)&(yy+places[n][1]<580);im[added]=im[idx[0][added],idx[1][added]];Image.fromarray(im).save('parts/'+n+'.png')
