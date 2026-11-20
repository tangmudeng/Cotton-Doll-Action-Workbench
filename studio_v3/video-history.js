(() => {
  'use strict';

  const HISTORY = 'cotton_video_history_v1';
  const terminal = new Set(['succeeded', 'failed', 'cancelled', 'canceled', 'expired']);
  const states = {queued:'排队中',running:'生成中',succeeded:'已生成',failed:'生成失败',cancelled:'已取消',canceled:'已取消',expired:'已过期',unknown:'待查询'};
  const actions = [['idle_stand','待机·站立'],['walk','行走'],['think','思考'],['scratch_head','扣脑袋']];
  const views = [['front','正面'],['back','背面'],['right_front_3q','右前¾侧'],['right_back_3q','右后¾侧'],['left_front_3q','左前¾侧'],['left_back_3q','左后¾侧']];
  const $ = selector => document.querySelector(selector);
  const read = () => { try { const value=JSON.parse(localStorage.getItem(HISTORY)||'[]');return Array.isArray(value)?value:[]; } catch (_) { return []; } };
  let records=read().map(record=>({...record,characterId:record.characterId||'legacy_six_view'}));
  const refreshing=new Map(),deletedIds=new Set(),queryRevisions=new Map(),deleteStates=new Map();

  function markDeleted(id){deletedIds.add(id);queryRevisions.set(id,(queryRevisions.get(id)||0)+1)}
  function syncRecords(){
    const latest=read().map(record=>({...record,characterId:record.characterId||'legacy_six_view'})),ids=new Set(latest.map(record=>record.task_id));
    for(const record of records)if(!ids.has(record.task_id))markDeleted(record.task_id);
    records=latest;
  }
  function isDeleted(id){syncRecords();return deletedIds.has(id)}
  function characterId(){return window.activeCharacterId||localStorage.getItem('cotton_active_character')||'legacy_six_view'}
  function find(id){return records.find(record=>record.task_id===id)}
  function report(message){const node=$('#historyStatus');if(node)node.textContent=message}
  function persist(){try{localStorage.setItem(HISTORY,JSON.stringify(records));return true}catch(error){report('历史记录保存失败：'+error.message+'。请检查浏览器存储。');return false}}
  function safeUrl(value){if(typeof value!=='string'||!value.trim())return '';try{const url=new URL(value,location.href);return ['http:','https:'].includes(url.protocol)?url.href:''}catch(_){return ''}}
  function normalizedView(value){return views.find(([id,label])=>id===value||label===value)?.[0]||'front'}
  function upsert(value){
    if(!value?.task_id)return null;
    syncRecords();if(deletedIds.has(value.task_id))return null;
    let item=find(value.task_id);
    if(item&&value.characterId&&item.characterId!==value.characterId){report('该任务属于其他角色，请切换到对应角色；不能更改已有任务归属。');return null}
    if(!item){item={task_id:value.task_id,status:'unknown',prompt:'',action:'',viewId:'front',characterId:'legacy_six_view',createdAt:'',accepted:false};records.push(item)}
    for(const [key,next] of Object.entries(value))if(next!==undefined&&next!==null&&(next!==''||!(key in item)))item[key]=next;
    item.viewId=normalizedView(item.viewId||item.view);item.characterId=item.characterId||'legacy_six_view';item.video_url=safeUrl(item.video_url);persist();return item;
  }
  function resultPatch(result={}){
    const patch={};if(result.status)patch.status=String(result.status).toLowerCase();
    const url=result.content?.video_url||result.video_url;if(url)patch.video_url=url;
    const text=Array.isArray(result.content)?result.content.filter(part=>part.type==='text').map(part=>part.text||'').join('\n'):'';
    if(result.prompt||text)patch.prompt=result.prompt||text;if(result.model)patch.model=result.model;
    for(const key of ['original_prompt','prompt_model','effective_duration'])if(result[key]!==undefined)patch[key]=result[key];
    if(result.created_at){const date=new Date(typeof result.created_at==='number'?result.created_at*1000:result.created_at);if(!Number.isNaN(date.getTime()))patch.createdAt=date.toISOString()}
    return patch;
  }
  function accepted(record){return record?.accepted===true||localStorage.getItem('cotton_video_accepted_'+record?.task_id)==='1'}
  function make(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node}
  function button(label,callback,disabled=false,className=''){const node=make('button',label,className);node.type='button';node.disabled=disabled;node.onclick=callback;return node}
  async function copy(text,message){try{await navigator.clipboard.writeText(text);report(message)}catch(_){report('复制失败，可在卡片中选中文字手动复制。')}}
  function setBadge(selector,text,state){const node=$(selector);if(node){node.textContent=text;node.className='step-state state-'+state}}

  function updateWorkflowState(){
    const taskId=$('#videoTaskId')?.value.trim(),record=find(taskId),isAccepted=accepted(record)&&record?.characterId===characterId();
    setBadge('#videoStageBadge',isAccepted?'当前视频已验收':'可生成 / 选择历史视频',isAccepted?'done':'ready');
    const next=$('#nextSteps');if(next)next.classList.toggle('hidden',!isAccepted);
  }

  function renderHistory(){
    const list=$('#videoHistoryList');if(!list)return;
    const ordered=records.filter(record=>(record.characterId||'legacy_six_view')===characterId()).sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||''));
    $('#historyCount').textContent=ordered.length+' 条（当前角色）';
    if(!ordered.length){list.replaceChildren(make('div','暂无历史记录。可输入任务 ID 找回已有任务；此后生成的任务会自动保存。','history-empty'));return}
    const visibleIds=new Set(ordered.map(record=>record.task_id)),existing=new Map();
    for(const node of [...list.children]){if(!visibleIds.has(node.dataset.taskId))node.remove();else existing.set(node.dataset.taskId,node)}
    for(const record of ordered){
      const deletion=deleteStates.get(record.task_id),signature=JSON.stringify(record)+'|'+accepted(record)+'|'+refreshing.has(record.task_id)+'|'+JSON.stringify(deletion),old=existing.get(record.task_id);
      if(old?.dataset.signature===signature)continue;
      const card=make('article',undefined,'history-item');card.dataset.taskId=record.task_id;card.dataset.signature=signature;
      const action=actions.find(([id])=>id===record.action)?.[1]||'待确认动作',view=views.find(([id])=>id===record.viewId)?.[1]||'正面';
      card.append(make('h3',`${action} · ${view}`));card.append(make('div',`${states[record.status]||record.status} · ${accepted(record)?'已验收':'待验收'}${record.createdAt?' · '+new Date(record.createdAt).toLocaleString():''}`,'history-meta'));card.append(make('div','任务 ID：'+record.task_id,'history-meta'));
      if(record.video_url){const player=make('video');player.controls=true;player.playsInline=true;player.preload='metadata';player.src=record.video_url;player.setAttribute('aria-label','历史动作视频 '+record.task_id);const message=make('p','','history-message');player.onerror=()=>{message.textContent='视频加载失败，链接可能已过期。点击“刷新结果”重新查询，不会重新生成。'};card.append(player,message)}else card.append(make('p',record.status==='failed'?'任务失败，请刷新结果查看状态。':'暂无可播放结果，请刷新任务状态。','history-message'));
      card.append(make('div','生成提示词','history-meta'),make('pre',record.prompt||'此历史任务未保存原始提示词。','history-prompt'));
      const fields=make('div',undefined,'history-fields'),actionLabel=make('label','动作'),actionSelect=make('select'),viewLabel=make('label','朝向'),viewSelect=make('select');
      actionSelect.setAttribute('aria-label','历史动作 '+record.task_id);viewSelect.setAttribute('aria-label','历史朝向 '+record.task_id);
      for(const [id,label] of [['','请选择动作'],...actions]){const option=make('option',label);option.value=id;actionSelect.append(option)}
      for(const [id,label] of views){const option=make('option',label);option.value=id;viewSelect.append(option)}
      actionSelect.value=record.action||'';viewSelect.value=record.viewId;actionLabel.append(actionSelect);viewLabel.append(viewSelect);fields.append(actionLabel,viewLabel);card.append(fields);
      actionSelect.onchange=()=>{record.action=actionSelect.value;upsert({task_id:record.task_id,action:actionSelect.value});renderHistory()};viewSelect.onchange=()=>{upsert({task_id:record.task_id,viewId:viewSelect.value});renderHistory()};
      const acceptance=make('label'),check=make('input');check.type='checkbox';check.checked=accepted(record);check.disabled=!record.video_url;check.setAttribute('aria-label','验收历史视频 '+record.task_id);acceptance.append(check,document.createTextNode('我已验收此视频'));check.onchange=()=>setAccepted(record.task_id,check.checked);card.append(acceptance);
      const row=make('div',undefined,'row');row.append(button('制作序列帧',()=>useVideo(record),!record.video_url),button('复制提示词',()=>copy(record.prompt,'提示词已复制'),!record.prompt),button('复制任务 ID',()=>copy(record.task_id,'任务 ID 已复制')),button(refreshing.has(record.task_id)?'查询中…':'刷新结果',()=>refreshRecord(record.task_id),refreshing.has(record.task_id)),button(deletion?.pending?'删除请求中…':'删除视频',()=>deleteVideo(record.task_id,record.characterId),!!deletion?.pending,'history-delete-button'));card.append(row);if(deletion?.message){const notice=make('p',deletion.message,'history-message');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');card.append(notice)}if(old)old.replaceWith(card);else list.append(card);
    }
    ordered.forEach((record,index)=>{const node=[...list.children].find(item=>item.dataset.taskId===record.task_id);if(node&&list.children[index]!==node)list.insertBefore(node,list.children[index]||null)});
  }

  async function deleteVideo(id,owner){
    if(deleteStates.get(id)?.pending)return;
    const canDelete=()=>owner===characterId()&&find(id)?.characterId===owner;
    syncRecords();
    if(!canDelete()){report('视频记录不存在或角色归属已改变，未删除任何内容。');renderHistory();return}
    if(!window.confirm('彻底删除任务 '+id+' 对应的视频文件？\n只有服务器确认输出文件已物理删除后，才会移除本地历史。此操作不可恢复。'))return;
    syncRecords();
    if(!canDelete()){report('角色已切换、记录已不存在或归属已改变，已取消删除。');renderHistory();return}
    const revision=queryRevisions.get(id)||0;
    deleteStates.set(id,{pending:true,message:'正在请求服务器确认物理删除；确认前保留视频与历史。'});renderHistory();
    try{
      report('正在请求服务器彻底删除视频文件…');
      const response=await fetch('/api/video/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:id})});
      let data={};try{data=await response.json()}catch(_){}
      if(!response.ok||data.ok!==true||data.deleted!==true)throw new Error(data.error||'服务器未确认视频文件已物理删除。');
      syncRecords();
      if(!canDelete()||owner!==characterId()||(queryRevisions.get(id)||0)!==revision){report('服务器已确认文件删除，但本地角色或记录已变化；请刷新历史核对。');renderHistory();return}
      const previous=records;
      records=records.filter(record=>!(record.task_id===id&&record.characterId===owner));
      if(!persist()){records=previous;const message='服务器已删除视频文件，但本地历史保存失败；请刷新页面核对任务 '+id+'。';deleteStates.set(id,{pending:false,message});if(owner===characterId())report(message);return}
      markDeleted(id);refreshing.delete(id);
      try{
        localStorage.removeItem('cotton_video_accepted_'+id);localStorage.removeItem('cotton_video_notes_'+id);
        let active=null;try{active=JSON.parse(localStorage.getItem('cotton_active_video_task')||'null')}catch(_){}
        if(active?.task_id===id&&(active.characterId||'legacy_six_view')===owner)localStorage.removeItem('cotton_active_video_task');
      }catch(error){report('视频文件已删除；验收信息或活动任务清理失败：'+error.message)}
      window.dispatchEvent(new CustomEvent('cotton-video-record-deleted',{detail:{taskId:id,characterId:owner}}));
      renderHistory();updateWorkflowState();report('服务器已确认视频文件彻底删除，并已移除本地历史。');
    }catch(error){const message='彻底删除失败；未移除本地历史，文件删除未获确认：'+error.message;deleteStates.set(id,{pending:false,message});if(owner===characterId())report(message)}
    finally{const state=deleteStates.get(id);if(state?.pending)deleteStates.delete(id);renderHistory()}
  }
  function setAccepted(id,value){
    const record=find(id);if(!record?.video_url)return;
    localStorage.setItem('cotton_video_accepted_'+id,value?'1':'0');upsert({task_id:id,accepted:value});
    if($('#videoTaskId')?.value.trim()===id){$('#videoAccepted').checked=value;$('#nextSteps').classList.toggle('hidden',!value)}
    renderHistory();updateWorkflowState();
  }
  function useVideo(record){
    if(!record?.video_url){report('请先查询到可播放的视频结果。');return}
    if(record.characterId!==characterId()){report('该视频属于其他角色，请切换到对应角色后再制作序列帧。');return}
    const workflow=window.SequenceWorkflow;
    if(!workflow||typeof workflow.useVideo!=='function'){report('序列帧模块尚未就绪，请稍后重试。');return}
    window.goToTab?.('sequence');
    Promise.resolve(workflow.useVideo({url:record.video_url,taskId:record.task_id,characterId:record.characterId,action:record.action,viewId:record.viewId})).catch(error=>{report(error.message);const status=$('#sqVideoStatus');if(status)status.textContent=error.message;});
  }
  function prepareTaskQuery(id,owner=characterId()){
    if(!/^[A-Za-z0-9_-]{1,256}$/.test(id)){report('请输入有效任务 ID。');return false}
    if(owner!==characterId()){report('角色已切换，请重新查询。');return false}
    syncRecords();const record=find(id);
    if(record&&record.characterId!==owner){report('该任务属于其他角色，请切换到对应角色后查询；未更改任务归属。');return false}
    if(deletedIds.delete(id))queryRevisions.set(id,(queryRevisions.get(id)||0)+1);
    if(!record&&!upsert({task_id:id,characterId:owner}))return false;
    renderHistory();return true;
  }
  async function refreshRecord(id,quiet=false){
    syncRecords();if(refreshing.has(id))return;
    const owner=find(id)?.characterId||characterId();
    if(quiet){if(!find(id)||deletedIds.has(id))return}else if(!prepareTaskQuery(id,owner))return;
    const revision=queryRevisions.get(id)||0;
    refreshing.set(id,revision);renderHistory();
    try{
      const response=await fetch('/api/video/tasks/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:id})}),data=await response.json();
      if(isDeleted(id)||(queryRevisions.get(id)||0)!==revision)return;
      if(!response.ok||!data.ok)throw new Error(data.error||'查询失败');
      const item=recordResult(id,data.result||{},owner);if(item&&!quiet&&owner===characterId())report('已更新任务 '+id+' 的历史记录。');
    }
    catch(error){if(!isDeleted(id)&&(queryRevisions.get(id)||0)===revision&&owner===characterId())report('任务 '+id+' 查询失败：'+error.message+'。已保留本地历史；可稍后重试。')}
    finally{if(refreshing.get(id)===revision)refreshing.delete(id);renderHistory()}
  }
  function recordResult(id,result,owner=find(id)?.characterId||characterId()){if(!id||isDeleted(id))return null;const item=upsert({task_id:id,characterId:owner,...resultPatch(result)});renderHistory();updateWorkflowState();return item}
  function recordCreated(record,result){if(!record?.task_id||isDeleted(record.task_id))return null;const item=upsert({...record,...resultPatch(result)});renderHistory();updateWorkflowState();return item}
  async function importTask(){
    const input=$('#historyTaskId'),id=input.value.trim(),owner=characterId();
    if(!prepareTaskQuery(id,owner))return;
    $('#importHistoryTask').disabled=true;report('正在找回任务，不会创建新视频…');
    try{await refreshRecord(id)}finally{$('#importHistoryTask').disabled=false}
  }
  function useCurrentVideo(){
    const id=$('#videoTaskId')?.value.trim(),record=find(id);
    if(record?.video_url){useVideo(record);return}
    const url=safeUrl($('#videoPlayer')?.currentSrc||$('#videoPlayer')?.getAttribute('src'));
    if(url){const item=upsert({task_id:id||'local_result_'+Date.now(),characterId:characterId(),video_url:url,status:'succeeded'});if(item){useVideo(item);return}}
    window.goToTab?.('sequence');report('当前视频地址缺失，请从历史选择视频，或在转帧页导入本地视频。');const status=$('#sqVideoStatus');if(status)status.textContent='没有可带入的视频地址；请导入本地视频。';
  }

  window.CottonHistory={recordCreated,recordResult,prepareTaskQuery,isDeleted,updateWorkflowState,useCurrentVideo};
  $('#importHistoryTask').onclick=importTask;$('#historyTaskId').addEventListener('keydown',event=>{if(event.key==='Enter')importTask()});
  $('#videoAccepted').addEventListener('change',()=>setAccepted($('#videoTaskId').value.trim(),$('#videoAccepted').checked));
  $('#videoAcceptanceNotes').addEventListener('change',()=>{const id=$('#videoTaskId').value.trim();if(id)localStorage.setItem('cotton_video_notes_'+id,$('#videoAcceptanceNotes').value)});
  window.addEventListener('cotton-character-changed',()=>{renderHistory();updateWorkflowState()});
  window.addEventListener('storage',event=>{if(event.key===HISTORY||event.key===null){syncRecords();renderHistory();updateWorkflowState()}});

  const active=(()=>{try{return JSON.parse(localStorage.getItem('cotton_active_video_task')||'null')}catch(_){return null}})();
  if(active?.task_id)upsert({...active,characterId:active.characterId||'legacy_six_view'});
  for(const key of Object.keys(localStorage)){
    if(!key.startsWith('cotton_video_accepted_')&&!key.startsWith('cotton_video_notes_'))continue;
    const id=key.replace(/^cotton_video_(accepted|notes)_/,'');if(!/^[A-Za-z0-9_-]{1,256}$/.test(id))continue;
    if(!find(id))upsert({task_id:id,characterId:'legacy_six_view',accepted:localStorage.getItem('cotton_video_accepted_'+id)==='1'});
  }
  renderHistory();updateWorkflowState();
  const unresolved=records.filter(record=>!record.video_url&&!terminal.has(record.status)).map(record=>record.task_id);let cursor=0;
  Promise.all(Array.from({length:Math.min(2,unresolved.length)},async()=>{while(cursor<unresolved.length)await refreshRecord(unresolved[cursor++],true)}));
})();
