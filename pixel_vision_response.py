"""Strict JSON responses with retained diagnostics; never invent missing coordinates."""
import json, time, uuid
import pixel_workbench as pw

def parse_response(result,path,stage):
    record=dict(stage=stage,frame=path.stem,at=time.time(),response=result)
    folder=path.parent.parent/'automation'/'responses'
    name=f'{stage}_{path.stem}_{time.time_ns()}_{uuid.uuid4().hex[:6]}.json'
    try:
        choice=result['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError('模型输出被截断')
        text=choice['message']['content']
        if not isinstance(text,str):raise ValueError('模型未返回文本 JSON')
        text=text.strip()
        if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
        value=json.loads(text)
        if not isinstance(value,dict):raise ValueError('模型结果不是 JSON 对象')
        record['parsed']=True
        return value
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        record.update(parsed=False,error=str(exc))
        raise ValueError(f'源帧 {path.stem} {stage} 响应格式无效；原始响应已留档，可重试') from exc
    finally:pw.write(folder/name,record)
