"""Optional local SAM2 segmentation of visible source pixels; no image generation."""
import threading
import cv2
import numpy as np
from PIL import Image

MODEL_ID='facebook/sam2.1-hiera-tiny'
VERSION=7
_LOCK=threading.Lock()
_MODEL=None
_PROCESSOR=None

def refine(rgb,polygons,anchors=None):
    import torch
    global _MODEL,_PROCESSOR
    from transformers import Sam2Model,Sam2Processor
    h,w=rgb.shape[:2];names=list(polygons);cores={};raw={};boxes=[]
    for name,poly in polygons.items():
        m=np.zeros((h,w),np.uint8);cv2.fillPoly(m,[np.array(poly,np.int32)],1);raw[name]=m
        dt=cv2.distanceTransform(m,cv2.DIST_L2,5);y,x=np.unravel_index(np.argmax(dt),dt.shape)
        cores[name]=[int(x),int(y)]
        ys,xs=np.where(m>0)
        pad=max(6,int(min(h,w)*.035))
        boxes.append([max(0,int(xs.min())-pad),max(0,int(ys.min())-pad),min(w-1,int(xs.max())+pad),min(h-1,int(ys.max())+pad)])
    points=[];labels=[]
    for name in names:
        dt=cv2.distanceTransform(raw[name],cv2.DIST_L2,5)
        region=dt>=max(2.,float(dt.max())*.15)
        yy,xx=np.where(region);positive=[cores[name]]
        for _ in range(4):
            if not len(xx):positive.append(cores[name]);continue
            distances=np.min(np.stack([(xx-q[0])**2+(yy-q[1])**2 for q in positive]),axis=0)
            k=int(np.argmax(distances));positive.append([int(xx[k]),int(yy[k])])
        endpoints={'arm_near':'hand_near','arm_far':'hand_far','leg_near':'foot_near','leg_far':'foot_far'}
        if anchors and name in endpoints:
            endpoint=[int(round(z)) for z in anchors[endpoints[name]]]
            endpoint=[int(np.clip(endpoint[0],0,w-1)),int(np.clip(endpoint[1],0,h-1))]
            positive[-1]=endpoint
            i=names.index(name);boxes[i]=[max(0,min(boxes[i][0],endpoint[0]-8)),max(0,min(boxes[i][1],endpoint[1]-8)),min(w-1,max(boxes[i][2],endpoint[0]+8)),min(h-1,max(boxes[i][3],endpoint[1]+8))]
        points.append(positive+[cores[other] for other in names if other!=name])
        labels.append([1]*len(positive)+[0 for other in names if other!=name])
    with _LOCK:
        if _MODEL is None:
            torch.set_num_threads(min(4,torch.get_num_threads()))
            _PROCESSOR=Sam2Processor.from_pretrained(MODEL_ID)
            _MODEL=Sam2Model.from_pretrained(MODEL_ID).eval()
        inputs=_PROCESSOR(images=Image.fromarray(rgb),input_points=[points],input_labels=[labels],input_boxes=[boxes],return_tensors='pt')
        with torch.inference_mode():outputs=_MODEL(**inputs,multimask_output=True)
        masks=_PROCESSOR.post_process_masks(outputs.pred_masks,inputs['original_sizes'])[0].cpu().numpy()
        scores=outputs.iou_scores[0].cpu().numpy()
    result={};records={}
    for i,name in enumerate(names):
        candidates=masks[i];rank=[]
        for index,m in enumerate(candidates):
            m=m.astype(bool);r=raw[name].astype(bool)
            intersection=np.count_nonzero(m&r);union=np.count_nonzero(m|r)
            overlap=intersection/max(1,union)
            support=sum(bool(m[q[1],q[0]]) for q in points[i][:5])/5
            rank.append(float(scores[i,index])+.5*overlap+2*support)
        chosen=int(np.argmax(rank));mask=candidates[chosen].astype(np.uint8)*255
        # A semantic part includes internal eye/face/cloth pixels: fill enclosed holes,
        # retaining the model's outer contour rather than cutting out pale textures.
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        filled=np.zeros_like(mask)
        if contours:cv2.drawContours(filled,[max(contours,key=cv2.contourArea)],-1,255,-1)
        if name=='head' and np.any(filled):
            # Head is a composite semantic region (hair, ears, face), not just a
            # texture selected by SAM. Recover its interior from observed silhouette.
            cv2.fillConvexPoly(filled,cv2.convexHull(cv2.findNonZero(filled)),255)
        result[name]=filled
        records[name]={'modelIoU':float(scores[i,chosen]),'prompt':points[i][:5],'ranks':rank,'box':boxes[i],'candidate':chosen}
    return result,records
