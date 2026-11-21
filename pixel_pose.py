"""Sequence pose fitting constrained by independently segmented source pixels."""
import cv2
import numpy as np
from scipy.signal import savgol_filter
from scipy.optimize import least_squares
from pixel_workbench import CHAINS,POINTS

def fit(frames,all_masks):
    issues=[];evidence=[];raw=[{'points':dict(f['points']),'joints':dict(f['joints'])} for f in frames]
    count=len(frames)
    # Denoise measured trajectories, retaining each frame's source identity.
    for name in POINTS:
        values=np.array([f['points'][name] for f in frames],float)
        if count>=5:
            initial=savgol_filter(values,5,2,axis=0,mode='interp')
            def residual(flat):
                q=flat.reshape(-1,2)
                return np.concatenate([(q-values).ravel(),(np.diff(q,2,axis=0)*3).ravel()])
            smooth=least_squares(residual,initial.ravel(),loss='soft_l1',f_scale=3).x.reshape(-1,2)
        else:smooth=values
        for i,f in enumerate(frames):
            delta=float(np.linalg.norm(smooth[i]-values[i]))
            if delta>8:issues.append(dict(frame=f['frame'],code='anchor_remeasurement',part=name,detail=f'端点时序去噪偏移 {delta:.1f} px，需重新核查'))
            f['points'][name]=smooth[i].tolist()
    # Shoulder/hip roots belong to the body, not the moving pant opening.
    # Fit robust offsets from the reference torso motion; no sample coordinates.
    for root,base in [('shoulder_near','neck'),('shoulder_far','neck'),('hip_near','pelvis'),('hip_far','pelvis')]:
        offsets=np.array([np.array(f['points'][root])-f['points'][base] for f in frames])
        offset=np.median(offsets,axis=0)
        for f in frames:
            q=np.array(f['points'][base])+offset
            deviation=float(np.linalg.norm(q-f['points'][root]))
            if deviation>8:issues.append(dict(frame=f['frame'],code='root_fit_disagreement',part=root,detail=f'躯干约束与检测根关节相差 {deviation:.1f} px，需核对隐藏关节'))
            f['points'][root]=q.tolist()
    for name,(start,end) in CHAINS.items():
        results=[]
        states=[(r,h) for r in (.4,.45,.5,.55,.6) for h in (.10,.13,.16,.19,.22,.25)]
        for sign in (-1,1):
            options=[];costs=[]
            for i,f in enumerate(frames):
                a=np.array(f['points'][start],float);c=np.array(f['points'][end],float);delta=c-a;length=np.linalg.norm(delta)
                normal=np.array([-delta[1],delta[0]])/max(1.,length)
                limb=all_masks[i][name]>0
                # Occluded far-side elbows may be behind torso; knees may be behind shorts.
                support=limb.copy()
                if name=='arm_far':support|=all_masks[i]['torso']>0
                if name.startswith('leg'):support|=all_masks[i]['shorts']>0
                distance=cv2.distanceTransform((~support).astype(np.uint8),cv2.DIST_L2,5)
                points=[];errors=[]
                original=np.array(raw[i]['joints'][name])
                for r,h in states:
                    q=a+delta*r+normal*(sign*h*length);points.append(q)
                    x,y=np.rint(q).astype(int)
                    outside=float(distance[np.clip(y,0,distance.shape[0]-1),np.clip(x,0,distance.shape[1]-1)])
                    # Every candidate is grounded in source support. Model elbow/knee
                    # positions remain weak observations, not anatomical ground truth.
                    err=.06*np.sum((q-original)**2)+40*outside**2+.04*(h*length)**2+.1*((r-.5)*length)**2
                    errors.append(err)
                options.append(np.array(points));costs.append(np.array(errors))
            dp=costs[0].copy();back=[]
            for i in range(1,count):
                # Smooth relative bend/ratio while allowing the whole limb to move.
                state=np.array(states);transition=np.sum((state[:,None,:]-state[None,:,:])**2,axis=2)*1500
                full=dp[:,None]+transition;indices=np.argmin(full,axis=0);dp=costs[i]+full[indices,np.arange(len(states))];back.append(indices)
            j=int(np.argmin(dp));path=[j]
            for prev in reversed(back):j=int(prev[j]);path.append(j)
            path.reverse();results.append((float(np.min(dp)),[options[i][j] for i,j in enumerate(path)]))
        fitted=min(results,key=lambda x:x[0])[1]
        for i,(f,q) in enumerate(zip(frames,fitted)):
            residual=float(np.linalg.norm(q-np.array(raw[i]['joints'][name])))
            f['joints'][name]=q.tolist()
            evidence.append(dict(frame=f['frame'],chain=name,rawJoint=raw[i]['joints'][name],fittedJoint=q.tolist(),detectorResidual=residual))
            a=np.array(f['points'][start]);c=np.array(f['points'][end]);length=float(np.linalg.norm(c-a))
            if residual>max(4,length*.12):issues.append(dict(frame=f['frame'],code='fit_disagreement',part=name,detail=f'原像素约束拟合与粗识别关节相差 {residual:.1f} px；遮挡关节为推定，需视觉核对'))
    return issues,evidence
