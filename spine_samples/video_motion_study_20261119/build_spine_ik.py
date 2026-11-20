from pathlib import Path
import json,math
from PIL import Image
R=Path(__file__).resolve().parent;data=json.loads((R/'motion_annotations.json').read_text(encoding='utf8'));samples=data['samples'];s0=samples[0];origin=(432,480)
def xy(p):return [p[0]-origin[0],origin[1]-p[1]]
def angle(a,b):return math.degrees(math.atan2(a[1]-b[1],b[0]-a[0]))
bones=[{'name':'root'}];slots=[];attachments={};ik=[];anim={}
def region(name,bone,length,width,color):
 slots.append({'name':name,'bone':bone,'attachment':name,'color':color})
 attachments[name]={name:{'path':'white','x':length/2,'y':0,'width':length,'height':width}}
for name,pa,pb,width in [('torso','neck','pelvis',30),('pelvis','hip_near','hip_far',10)]:
 p=s0['points'];a,b=p[pa],p[pb];x,y=xy(a);ang=angle(a,b);length=math.dist(a,b);bones.append({'name':name,'parent':'root','x':x,'y':y,'rotation':ang,'length':length});region(name,name,length,width,'a8babdff')
 anim[name]={'translate':[{'time':(s['frame']-63)/24,'x':xy(s['points'][pa])[0]-x,'y':xy(s['points'][pa])[1]-y} for s in samples],'rotate':[{'time':(s['frame']-63)/24,'value':angle(s['points'][pa],s['points'][pb])-ang} for s in samples]}
for order,name in enumerate(['arm_far','leg_far','arm_near','leg_near']):
 ch=s0['chains'][name];a=s0['points'][ch['root']];b=ch['joint'];end=ch['solvedTarget'];l1,l2=ch['lengths'];x,y=xy(a);ang1=angle(a,b);ang2=angle(b,end);tx,ty=xy(end)
 upper,lower,target=name+'_upper',name+'_lower',name+'_target'
 bones += [{'name':upper,'parent':'root','x':x,'y':y,'rotation':ang1,'length':l1},{'name':lower,'parent':upper,'x':l1,'rotation':ang2-ang1,'length':l2},{'name':target,'parent':'root','x':tx,'y':ty}]
 ik.append({'name':name+'_ik','order':order,'bones':[upper,lower],'target':target,'mix':1,'bendPositive':ch['bend']>0})
 color='008b9bff' if name.endswith('near') else 'c96b35ff'
 region(upper,upper,l1,12 if name.startswith('leg') else 8,color);region(lower,lower,l2,12 if name.startswith('leg') else 8,color)
 anim[upper]={'translate':[{'time':(s['frame']-63)/24,'x':xy(s['points'][ch['root']])[0]-x,'y':xy(s['points'][ch['root']])[1]-y} for s in samples]}
 anim[target]={'translate':[{'time':(s['frame']-63)/24,'x':xy(s['points'][ch['target']])[0]-tx,'y':xy(s['points'][ch['target']])[1]-ty} for s in samples]}
p={'skeleton':{'spine':'4.2.43','images':'./ik_parts/'},'bones':bones,'slots':slots,'ik':ik,'skins':[{'name':'default','attachments':attachments}],'animations':{'reference_cycle':{'bones':anim}}}
(R/'ik_study.json').write_text(json.dumps(p,indent=2),encoding='utf8');(R/'ik_parts').mkdir(exist_ok=True);Image.new('RGBA',(32,32),'white').save(R/'ik_parts/white.png');Image.new('RGBA',(32,32),'white').save(R/'ik.png')
(R/'ik.atlas').write_text('ik.png\nsize: 32,32\nfilter: Linear,Linear\nrepeat: none\nwhite\n  rotate: false\n  xy: 0, 0\n  size: 32, 32\n  orig: 32, 32\n  offset: 0, 0\n  index: -1\n')
print('Built',len(bones),'bones,',len(ik),'native Spine IK constraints.')

