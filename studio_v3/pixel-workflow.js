(function(root){
'use strict';
function workflow(p,{dirty=false,job=null,reviewed=false}={}){
 const running=job?.state==='running';
 const built=!!p&&!dirty&&!running&&p.builtRevision===p.revision&&p.artifact?.audit?.ok===true;
 const a=p?.automation;
 const accepted=built&&a?.accepted===true&&a.acceptedRevision===p.revision;
 const hard=(a?.issues||[]).some(i=>['runtime_rejected','degenerate_chain','empty_part','invalid_fit','bend_flip'].includes(i.code));
 const canAccept=built&&!!a&&!hard&&!['failed','interrupted'].includes(job?.state)&&!accepted&&reviewed;
 const canExport=built&&!running&&(accepted||(!a&&p.artifact?.acceptedCopy===true));
 const steps=[['视频分析',p?'区间已确认':'待导入 / 选区间'],['部件拆分',built?'已生成':running?'处理中':'待生成'],['姿态与 IK',built?'已拟合，需视觉核对':running?'处理中':'待拟合'],['蒙皮与动画',built?'当前版本已生成':'待生成'],['自动质检',built?(accepted?'已人工验收 / 保留诊断':'待整段视觉核对'):'待检查'],['导出',canExport?'可导出真实 Spine':'待验收']];
 let action='reference',label='选择视频与动作区间',hint='先选择视频，分析并预览动作区间建议；也可手动选择起止帧。';
 if(p){
  if(running){action=null;label='自动生成中';hint=job.message||'正在处理，完成后自动进入动画核查。';}
  else if(['failed','interrupted'].includes(job?.state)&&!accepted){action=p.baseline?'build':'auto';label='重试 / 继续自动生成';hint=job.message||'任务中断，重试会复用同源识别缓存。';}
  else if(canExport){action='export';label='导出已验收版本';hint=`当前 r${p.revision} 已通过验收，导出会执行真实 Spine 导入回导。`;}
  else if(canAccept){action='autoAccept';label='登记整段验收通过';hint='你已确认核对整段效果和诊断，可以登记当前版本验收。';}
  else if(built){action='inspect';label='查看当前动画与诊断';hint=hard?'存在结构错误，请查看具体帧和部件后修正。':'请核对皮肤、遮挡、关节与手脚端点；技术通过不等于姿态正确。';}
  else{action=p.baseline?'build':'auto';label=['failed','interrupted'].includes(job?.state)?'重试 / 继续自动生成':'自动生成拆件、IK 与动画';hint=dirty?'输入已修改，旧预览、验收与下载已失效；下一步先保存再生成。':'自动执行原像素拆件、时序拟合、同步绑定与质量检查。';}
 }
 return {steps,action,label,hint,autoAccept:canAccept,export:canExport,reviewExport:built&&!running};
}
if(typeof module==='object'&&module.exports)module.exports=workflow;else root.PixelWorkflow=workflow;
})(typeof window==='object'?window:globalThis);
