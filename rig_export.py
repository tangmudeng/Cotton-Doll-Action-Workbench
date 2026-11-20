from pathlib import Path
import base64, hashlib, io, json, os, shutil, subprocess, threading, uuid, zipfile
from PIL import Image
ROOT=Path(__file__).resolve().parent
STUDIO=ROOT/'studio_v3'
CANDIDATE=STUDIO/'generated_rig/video_parts_v2'
LOCK=threading.Lock()
class ExportError(Exception): pass
def write_json(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def run(args,label):
    try: result=subprocess.run([str(a) for a in args],cwd=STUDIO,capture_output=True,timeout=120)
    except (OSError,subprocess.TimeoutExpired): raise ExportError(label+'未完成，请检查本机 Node / Spine 安装') from None
    if result.returncode: raise ExportError(label+'未通过；未发布验收包')
def export_project(project):
    raise ExportError('旧拆件已停用；等待新参考素材和 Spine 样板视觉验收后再接回工作台')
    if not isinstance(project,dict): raise ExportError('缺少工程对象')
    if not LOCK.acquire(blocking=False): raise ExportError('已有导出正在运行，请稍后重试')
    try:
        reference=json.loads((CANDIDATE/'reference.json').read_text(encoding='utf-8'))
        node=shutil.which('node'); spine=Path(os.environ.get('WALULU_SPINE_CLI','E:/MyTools/Spine/Spine.com'))
        if not node or not spine.is_file(): raise ExportError('需要 Node 与已授权 Spine；可用 WALULU_SPINE_CLI 指定 Spine.com')
        out=STUDIO/'exports'/('rig_'+uuid.uuid4().hex[:16]);out.mkdir(parents=True)
        write_json(out/'draft.json',project)
        run([node,STUDIO/'export_rig_cli.cjs',out/'draft.json',out,CANDIDATE/'reference.json'],'工程校验')
        packing=json.loads((out/'packing.json').read_text());(out/'images').mkdir()
        page=Image.new('RGBA',(packing['width'],packing['height']));records={p['id']:p for p in reference['parts']};hashes={}
        for part in project['parts']:
            name=part['id'];record=records[name]
            if part['texture']=='legacy':
                raw=(CANDIDATE/'images'/record['file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=record['sha256']: raise ExportError('包内部件 SHA 校验失败：'+name)
            else: raw=base64.b64decode(part['texture'].split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(raw)) as original:
                region=packing['regions'][name]
                if original.format!='PNG' or original.size!=(region['width'],region['height']): raise ExportError('PNG 尺寸与裁片边界不一致：'+name)
                im=original.convert('RGBA')
            (out/'images'/f'{name}.png').write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
            x,y,w,h=[region[k] for k in ('x','y','width','height')];page.paste(im,(x,y))
            for dx,dy,crop in [(-4,0,(0,0,1,h)),(w,0,(w-1,0,w,h)),(0,-4,(0,0,w,1)),(0,h,(0,h-1,w,h))]:
                strip=im.crop(crop).resize((4,h) if dx else (w,4));page.paste(strip,(x+dx,y+dy))
            for dx,dy,px,py in [(-4,-4,0,0),(w,-4,w-1,0),(-4,h,0,h-1),(w,h,w-1,h-1)]: page.paste(Image.new('RGBA',(4,4),im.getpixel((px,py))),(x+dx,y+dy))
        page.save(out/'walulu_walk.png')
        run([node,STUDIO/'tests/test_rig_spine_export.cjs',out/'draft.json',out/'runtime_checks.json'],'骨骼运行时校验')
        run([spine,'-u','4.2.43','-i',out/'walulu_walk.json','-o',out/'walulu_walk.spine','-r','walulu_walk'],'Spine 导入')
        if not (out/'walulu_walk.spine').is_file() or (out/'walulu_walk.spine').stat().st_size<100: raise ExportError('Spine 未生成可编辑工程')
        rt=out/'roundtrip';rt.mkdir()
        run([spine,'-u','4.2.43','-i',out/'walulu_walk.spine','-o',rt,'-e','json'],'Spine 重导出')
        files=list(rt.glob('*.json'))
        if len(files)!=1: raise ExportError('Spine 重导出结果数量异常')
        run([node,STUDIO/'tests/test_rig_spine_export.cjs',out/'draft.json',out/'roundtrip_checks.json',files[0]],'Spine 重导出动作一致性')
        write_json(out/'provenance.json',{'source':project['source'],'method':'manual video landmarks; estimated occluded joints; video frame 66 head; frame 82 arms, near leg, shorts, visible torso; frame 70 far leg; new AI completion blended only into occluded/seam regions','productionApproved':False,'acceptance':'editable Spine and runtime validation passed; visual acceptance pending','partSha256':hashes,'spineVersion':'4.2.43','cycleFrames':[66,88],'duration':project['duration']})
        shutil.copy2(CANDIDATE/'landmarks.json',out/'landmarks.json')
        (out/'README.txt').write_text('Walulu 右前行走 / Spine 4.2.43 验收包\n\n解压整个目录，在 Spine 4.2.43 中打开 walulu_walk.spine，选择 walk 动画并循环播放。保留同目录 images 文件夹。\nwalulu_walk.json + walulu_walk.atlas + walulu_walk.png 为运行时文件，使用兼容 Spine 4.2 的运行时。\ndraft.json 可回载本工作台继续编辑；再次点击“导出 Spine 验收包”会重新构建并检查当前编辑。\n\n7 逻辑件、12 骨骼、加权网格；没有逐帧贴图序列。周期 22/24 秒，参考指定视频零基帧 66–88。\n视频方向为人工标记拟合；远侧遮挡点为估计，闭环首尾取平均。可见裁片重新取自视频关键帧；本轮 AI 补图补足根部并融合边界，未声称全自动 AI 恢复或完整隐藏面。\n数值及真实 Spine 导入/重导出校验通过不等于视觉验收通过；请检查肩髋接缝、极限收胸、脚底滑动和画风。Unity/移动端性能未在此包验收。\n',encoding='utf-8')
        names=['walulu_walk.spine','walulu_walk.json','walulu_walk.atlas','walulu_walk.png','draft.json','provenance.json','landmarks.json','runtime_checks.json','roundtrip_checks.json','README.txt']+[f'images/{p["id"]}.png' for p in project['parts']]+[f'roundtrip/{files[0].name}']
        write_json(out/'SHA256.json',{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names});names.append('SHA256.json')
        archive=out/'walulu_walk_spine_4.2.43.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name in names:z.write(out/name,name)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:raise ExportError('ZIP CRC 检查失败')
        relative='/studio_v3/exports/'+out.name+'/'
        return {'ok':True,'zipUrl':relative+archive.name,'spineUrl':relative+'walulu_walk.spine','directory':str(out),'checks':json.loads((out/'roundtrip_checks.json').read_text())}
    except (ValueError,OSError,KeyError,TypeError) as exc:raise ExportError('导出数据或资源无效；未发布验收包') from exc
    finally:LOCK.release()
