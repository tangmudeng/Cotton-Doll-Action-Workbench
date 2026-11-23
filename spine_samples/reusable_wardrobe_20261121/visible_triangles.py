"""Independent alpha support of each exported triangle, for inversion auditing."""
from build import *
out=HERE/'fitted';raw=read(out/'skin.json');result={}
for skin in raw['skins']:
    for slot in skin['attachments'].values():
        for name,a in slot.items():
            key=a.get('path',name)
            if key in result:continue
            im=np.array(Image.open(out/'parts'/f'{key}.png').convert('RGBA'));h,w=im.shape[:2]
            uv=np.array(a['uvs']).reshape(-1,2)*[w,h];counts=[]
            for tri in np.array(a['triangles']).reshape(-1,3):
                mask=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(mask,np.rint(uv[tri]*256).astype(np.int32),1,shift=8)
                counts.append(int(np.count_nonzero((mask>0)&(im[:,:,3]>16))))
            result[key]=counts
write(out/'triangle_alpha_support.json',result)
print('Recorded alpha support for',len(result),'meshes.')
