"""Read layered PSD into an isolated, source-traceable rig experiment."""
from pathlib import Path
import argparse,json,hashlib,sys
import numpy as np
import cv2
from PIL import Image,ImageDraw
from psd_tools import PSDImage
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from pixel_atlas import pack

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('psd',type=Path);args=parser.parse_args()
    before=sha(args.psd);psd=PSDImage.open(args.psd);out=HERE/'rig';out.mkdir(exist_ok=True);(out/'parts').mkdir(exist_ok=True)
    names={'handwear-l':'arm_far','legwear-l':'leg_far','legwear-r':'leg_near','topwear':'torso','bottomwear':'shorts','handwear-r':'arm_near','headwear':'head'}
    rows=[];images=[];assembled=Image.new('RGBA',psd.size)
    for layer in psd:
        if layer.is_group() or layer.name not in names:raise ValueError('Unexpected layer structure; review mapping before import')
        image=layer.composite(force=True).convert('RGBA');rgba=np.array(image);alpha=rgba[:,:,3]
        # Only exclude remote stray pixels. Keep every original edge pixel
        # within an eight-pixel margin; do not threshold the actual silhouette.
        n,labels,stats,_=cv2.connectedComponentsWithStats((alpha>32).astype(np.uint8),8)
        main=[i for i in range(1,n) if stats[i,4]>100]
        yy,xx=np.where(np.isin(labels,main));x0=max(0,int(xx.min())-8);y0=max(0,int(yy.min())-8);x1=min(image.width,int(xx.max())+9);y1=min(image.height,int(yy.max())+9)
        crop=image.crop((x0,y0,x1,y1));key=names[layer.name];dest=out/'parts'/f'{key}.png';crop.save(dest)
        outside=alpha.copy();outside[y0:y1,x0:x1]=0
        box=[layer.left+x0,layer.top+y0,layer.left+x1,layer.top+y1]
        assembled.alpha_composite(crop,box[:2]);images.append((key,crop))
        rows.append({'key':key,'layerName':layer.name,'sourceLayerBox':list(layer.bbox),'cropWithinLayer':[x0,y0,x1,y1],'canvasBox':box,'sha256':sha(dest),'croppedAwayAlphaPixels':int((outside>0).sum()),'croppedAwayMaxAlpha':int(outside.max()),'changedRetainedRGBA':0,'visible':layer.visible})
    assembled.save(out/'assembly.png');report=pack(images,out,2048)
    report.update(mode='psd_full_limb_master',wardrobeReady=False,explanation='Seven PSD textures; independent arms and legs. Joint validation prototype.')
    write(out/'atlas_report.json',report)
    write(out/'source_manifest.json',{'source':str(args.psd),'sha256':before,'canvas':list(psd.size),'parts':rows,'noGeneratedPixels':True,'legsIndependent':True})
    assert before==sha(args.psd)
    print(json.dumps({'layers':len(rows),'textures':report['uniqueImages'],'rgbaBytes':report['rgbaBytes'],'sourceUnchanged':True}))
if __name__=='__main__':main()
