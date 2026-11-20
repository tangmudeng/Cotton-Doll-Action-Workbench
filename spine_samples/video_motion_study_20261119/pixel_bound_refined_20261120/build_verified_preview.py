from pathlib import Path
r=Path.cwd();o=r.parent/'pixel_bound_verified_20261120'
s=(r/'review.html').read_text(encoding='utf8')
s=s.replace('原帧附件 IK · 精简验证','Spine 工程一致性验证')
s=s.replace('<label><input id="bones"','<label><input id="freeze" type="checkbox">冻结当前姿态附件</label> <button id="prevFrame">上一源帧</button> <button id="nextFrame">下一源帧</button> <label><input id="bones"')
s=s.replace('lastVideo=0','lastVideo=-1')
a=s.index("$('play').onclick=")
s=s[:a]+"""const keys=assets.get('skin.json').animations.reference_cycle.slots.head.attachment; let held=null; const nearKey=()=>Math.max(0,keys.findLastIndex(k=>(k.time||0)<=t)); const go=(i)=>{i=Math.max(0,Math.min(keys.length-1,i));t=(keys[i].time||0)+.000001;playing=false;$('play').textContent='播放';$('referenceMode').value='video';lastVideo=-1};$('prevFrame').onclick=()=>go(nearKey()-1);$('nextFrame').onclick=()=>go(nearKey()+1);$('freeze').onchange=()=>{held=$('freeze').checked?sk.slots.map(s=>s.getAttachment()):null};
"""+s[a:]
s=s.replace('t=7/24','t=(keys[7].time||0)+.000001')
s=s.replace('sk.updateWorldTransform(spine.Physics.update);ctx','if(held)sk.slots.forEach((s,i)=>s.setAttachment(held[i]));sk.updateWorldTransform(spine.Physics.update);ctx')
a=s.index("if($('bones').checked){");b=s.index("$('seek').value=t",a)
s=s[:a]+"""if($('bones').checked){for(const b of sk.bones){if(b.data.name.endsWith('_target')){ctx.strokeStyle='#d74b8a';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(b.worldX-4,b.worldY);ctx.lineTo(b.worldX+4,b.worldY);ctx.moveTo(b.worldX,b.worldY-4);ctx.lineTo(b.worldX,b.worldY+4);ctx.stroke()}else if(b.data.length>0){ctx.strokeStyle=b.data.name.includes('far')?'#bd6b22':'#008b9b';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(b.worldX,b.worldY);ctx.lineTo(b.worldX+b.a*b.data.length,b.worldY+b.c*b.data.length);ctx.stroke();ctx.beginPath();ctx.arc(b.worldX,b.worldY,2,0,7);ctx.stroke()}}}"""+s[b:]
s=s.replace('const fi=Math.min(22,Math.floor(t*24))','const fi=nearKey()')
a=s.index('</p><small>')+4;b=s.index('</small>',a)
s=s[:a]+"""<small>本页直接读取此 Spine 工程重新导出的 JSON。实线为骨段，粉色十字为 IK 目标。<br>“冻结当前姿态附件”用于观察仅由骨骼带动皮肤的效果；冻结后出现的形变或露白，表示当前附件复用范围有限，不是正常播放结果。<br>当前仍依赖 23 组姿态附件切换：头、躯干、裤衩绑定根节点；四肢绑定 IK 上下段。此版本不是通用单套皮肤绑定。"""+s[b:]
(o/'review.html').write_text(s,encoding='utf8')

