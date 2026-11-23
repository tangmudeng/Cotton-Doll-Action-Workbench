from pathlib import Path
import cv2,json,hashlib
from PIL import Image,ImageDraw
src=Path(r'I:/彩虹AI/design/视频素材_design/Walulu萌宠/蘑菇秃秃方向/基础角色-测试/右前行走-拆图层.mp4')
out=Path('spine_samples/video_reference_right_front_split_20261121');frames=out/'frames';frames.mkdir(parents=True,exist_ok=True)
cap=cv2.VideoCapture(str(src));fps=cap.get(cv2.CAP_PROP_FPS);start=round(2.4583333333333335*fps);end=round(3.458333333333333*fps);rows=[]
for i in range(start,end):
 cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,bgr=cap.read();
 if not ok:break
 rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);im=Image.fromarray(rgb);p=frames/f'{i:04}.png';im.save(p);rows.append({'frame':i,'time':i/fps,'file':f'frames/{i:04}.png','sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
cap.release();sheet=Image.new('RGB',(6*288,4*220),'#ececec');d=ImageDraw.Draw(sheet)
for j,r in enumerate(rows):
 im=Image.open(out/r['file']);im.thumbnail((280,180));x=(j%6)*288;y=(j//6)*220;sheet.paste(im,(x,y+22));d.text((x+4,y+4),f"frame {r['frame']} · {r['time']:.3f}s",fill='black')
sheet.save(out/'contact_sheet.jpg',quality=94)
meta={'sourceVideo':str(src),'sourceSha256':hashlib.sha256(src.read_bytes()).hexdigest(),'fps':fps,'frameCount':int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if False else 107,'selectedStartSeconds':2.4583333333333335,'selectedEndSeconds':3.458333333333333,'selectedStartFrame':start,'selectedEndFrameExclusive':end,'selectedFrameCount':len(rows),'selectionReason':'workbench selected loop interval from user-provided screenshot','frames':rows,'loopEndpointPolicy':'end frame is excluded from extracted interval; verify seam against first frame'}
(out/'selection.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8');print(meta['selectedStartFrame'],meta['selectedEndFrameExclusive'],len(rows))
