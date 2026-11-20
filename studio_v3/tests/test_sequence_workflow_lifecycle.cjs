'use strict';
const strict = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');
const workflowPath = path.join(__dirname, '../sequence-workflow.js');
const source = fs.readFileSync(workflowPath, 'utf8');
let assertions = 0;
const assert = Object.fromEntries(['equal', 'notEqual', 'deepEqual', 'ok', 'match', 'rejects'].map(name => [name, (...args) => { assertions++; return strict[name](...args); }]));
const cases = [];
const test = (name, run) => cases.push({ name, run });
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

async function fixture(config = {}) {
  const elements = new Map(), probes = [], timers = new Map(), revoked = [], draws = [], dbGets = [], dbPuts = [], mattingCalls = [], backgroundSamples = [], objectUrls = new Map(), downloads = [], pendingBlobs = [];
  let timerId = 0, blobId = 0, descriptorCalls = 0, findCalls = 0, pendingGet = null;
  const candidate = { start: .1, end: .4, confidence: 'medium', fallback: false, reason: '测试候选' };
  class Element {
    constructor(tag = 'div') {
      this.tagName = tag; this.children = []; this.listeners = new Map(); this.value = ''; this.textContent = ''; this.dataset = {}; this.style = {}; this.width = 8; this.height = 4;
      this.disabled = false; this.checked = false; this.hidden = false;
      this.classList = { toggle() {}, add() {}, remove() {} };
    }
    setAttribute(key, value) { this[key] = String(value); if (key === 'id') elements.set(String(value), this); }
    removeAttribute(key) { this[key] = ''; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    addEventListener(name, fn, options) {
      if (!this.listeners.has(name)) this.listeners.set(name, new Map());
      this.listeners.get(name).set(fn, options);
    }
    removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
    emit(name, extra = {}) {
      const event = { target: this, ...extra };
      this['on' + name]?.(event);
      for (const [fn, options] of [...(this.listeners.get(name) || [])]) {
        if (options?.once) this.removeEventListener(name, fn);
        fn(event);
      }
    }
    listenerCount() { return [...this.listeners.values()].reduce((n, map) => n + map.size, 0); }
    click() {
      if (this.tagName === 'a') downloads.push({name:this.download, blob:objectUrls.get(this.href)});
      return this.onclick?.({ target: this });
    }
    querySelector(selector) { return selector.startsWith('#') ? elements.get(selector.slice(1)) : null; }
    querySelectorAll(selector) {
      const descendants = this.children.flatMap(child => [child, ...(child.querySelectorAll?.('*') || [])]);
      if (selector === '*') return descendants;
      return descendants.filter(child => selector.split(',').includes(child.tagName));
    }
    set innerHTML(html) {
      this.children = [];
      for (const match of html.matchAll(/<(input|select|video|canvas|button|span|p|div|img|progress|output)\b([^>]*)>/g)) {
        const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
        if (!attrs.id) continue;
        const el = document.createElement(match[1]);
        for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
        el.checked = /\bchecked\b/.test(match[2]);
        if (match[1] === 'select') {
          const end = html.indexOf('</select>', match.index);
          const options = [...html.slice(match.index, end).matchAll(/<option\b([^>]*)value="([^"]*)"([^>]*)>/g)];
          el.value = (options.find(option => /selected/.test(option[1] + option[3])) || options[0])?.[2] || '';
        }
        this.append(el);
      }
    }
  }
  class Media extends Element {
    constructor(isProbe = false) {
      super('video'); this.isProbe = isProbe; this.src = ''; this.duration = config.duration || .5; this.readyState = 2; this.videoWidth = 8; this.videoHeight = 4;
      this._time = .23; this.paused = true; this.controls = true; this.seeking = false; this.loads = 0; this.pauses = 0; this.seekTimes = [];
      this.holdLoad = isProbe && !!config.holdLoad; this.holdSeek = false;
    }
    emit(name, extra) { if (name === 'loadeddata' || name === 'canplay') this.readyState = 2; super.emit(name, extra); }
    get currentTime() { return this._time; }
    set currentTime(time) {
      this.seekTimes.push(time);
      if (!this.isProbe && config.sameTimeNoSeek && this._time === time) { this.seeking = false; return; }
      this._time = time; this.seeking = true;
      if (!this.holdSeek) {
        if (this.isProbe && config.silentSeek) this.seeking = false;
        else queueMicrotask(() => { this.seeking = false; this.emit('seeked'); });
      }
    }
    load() {
      this.loads++;
      if (!this.src) { this.readyState = 0; return; }
      this.readyState = this.isProbe && (this.holdLoad || config.loadError) ? 0 : 2;
      if (this.isProbe && !this.holdLoad && !config.silentLoad) queueMicrotask(() => this.emit(config.loadError ? 'error' : 'loadeddata'));
    }
    pause() { this.pauses++; this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
  }
  class Canvas extends Element {
    constructor() { super('canvas'); this.image = null; this.ctx = {
      drawImage: (image, ...args) => {
        if (config.drawError && image instanceof Media) throw new Error('模拟画布失败');
        this.image = image instanceof Canvas ? {data:image.ctx.getImageData().data} : image;
        if (image instanceof Media) draws.push({ media: image, time: image.currentTime, args });
      },
      clearRect() {}, putImageData: image => { this.image = {data:image.data.slice()}; },
      getImageData: () => ({ data: this.image?.data?.slice() || new Uint8ClampedArray(this.width * this.height * 4).fill(255) }),
    }; }
    getContext() { return this.ctx; }
    getBoundingClientRect() { return {left:10,top:20,width:this.width*2,height:this.height*2}; }
    setPointerCapture() {}
    toBlob(callback) {
      const data=this.ctx.getImageData().data, blob=new Blob([data],{type:'image/png'});
      Object.assign(blob,{width:this.width,height:this.height,data});
      const finish=()=>callback(config.blobError ? null : blob);
      if(config.holdBlob)pendingBlobs.push(finish);else queueMicrotask(finish);
    }
  }
  function createElement(tag) {
    if (tag === 'video') { const probe = new Media(true); probes.push(probe); return probe; }
    return tag === 'canvas' ? new Canvas() : new Element(tag);
  }
  const video = new Media();
  const nav = new Element(), main = new Element(), document = new Element();
  document.head = new Element();
  document.createElement = tag => tag === 'video' && !elements.has('sqVideo') ? video : createElement(tag);
  document.createTextNode = text => ({ textContent: text });
  document.querySelector = selector => selector === '.workflow-tabs' ? nav : selector === 'main' ? main : elements.get(selector.slice(1)) || null;
  document.querySelectorAll = () => [];
  const window = new Element(); window.activeCharacterId = '角色A'; window.goToTab = () => {};
  window.SequenceLoopAnalysis = {
    describeFrame(data, width, height) { descriptorCalls++; assert.equal(data.length, width * height * 4); return { values: [descriptorCalls] }; },
    findLoop(samples, options) { findCalls++; config.onFind?.({ samples, options, window }); return config.result === undefined ? candidate : config.result; },
  };
  window.SequenceMatting = {
    sampleBackground(data, width, height) { const key = Array.from(data.slice(0, 3)); backgroundSamples.push({ key, width, height }); return { key }; },
    keyImage(data, width, height, options) {
      mattingCalls.push({ width, height, options: { ...options, key: Array.from(options.key) }, input: Array.from(data.slice(0, 4)) });
      data[3] = 0;
      return { toleranceLimited: false, key: options.key, warnings: [] };
    },
  };
  const database = { transaction(name, mode) {
    const tx = { objectStore() { return {
      get(characterId) {
        const request = {}; dbGets.push({ characterId, request });
        if (pendingGet) { pendingGet.request = request; pendingGet = null; }
        else queueMicrotask(() => { request.result = null; request.onsuccess?.(); });
        return request;
      },
      put(snapshot) { dbPuts.push(snapshot); queueMicrotask(() => tx.oncomplete?.()); },
    }; } }; return tx;
  } };
  const context = vm.createContext({
    document, window, console, AbortController, DOMException, Blob, TextEncoder, Uint8Array, Uint8ClampedArray,
    URL: class extends URL { static createObjectURL(blob) { const url = 'blob:测试/' + (++blobId); objectUrls.set(url,blob); return url; } static revokeObjectURL(url) { revoked.push(url); objectUrls.delete(url); } },
    location: { href: 'http://localhost/' }, confirm: () => true,
    createImageBitmap: async blob => ({ width: blob.width || 8, height: blob.height || 4, data: blob.data, close() {} }),
    setTimeout(fn, ms) { const id = ++timerId; timers.set(id, { fn, ms }); if (!ms) queueMicrotask(() => { if (timers.delete(id)) fn(); }); return id; },
    clearTimeout(id) { timers.delete(id); }, performance,
    indexedDB: { open() { const request = { result: database }; queueMicrotask(() => request.onsuccess?.()); return request; } },
  });
  // 只追加观测入口，不替换生产函数；所有事件、分析、seek 和 restore 均运行原源码。
  const marker = '  renderFrames();renderGroups();restore(currentCharacter());';
  assert.equal(source.split(marker).length, 2, '源码启动标记必须唯一且存在');
  const instrumented = source.replace(marker, `
  window.__lifecycle = {
    intervalFrameCount, analyzeLoopInterval, cancelLoopAnalysis, restore, processFrame, settings,
    inspect: () => ({ state, raw, processed, videoTask, analyzingLoop, extracting, processing, extractController, loopAnalysisController, restoreBusy, restorePending }),
    seedRaw: frames => { raw = frames; },
  };
${marker}`);
  vm.runInContext(instrumented, context, { filename: workflowPath });
  await flush();
  if (config.history) {
    const store = { cotton_video_history_v1: JSON.stringify(config.history) };
    context.localStorage = { getItem: key => store[key] ?? null, setItem: (key, value) => { store[key] = String(value); } };
    for (const id of ['importHistoryTask', 'historyTaskId', 'videoTaskId', 'videoAccepted', 'videoAcceptanceNotes', 'toSequence']) {
      const el = new Element(); el.setAttribute('id', id);
    }
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../video-history.js'), 'utf8'), context);
    const page = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
    const binding = page.match(/\$\('#toSequence'\)\.onclick=\(\)=>window\.CottonHistory\?\.useCurrentVideo\(\);/);
    assert.ok(binding, '使用02页面真实的制作序列帧绑定');
    vm.runInContext("const $ = selector => document.querySelector(selector); " + binding[0], context);
  }
  const $ = id => elements.get(id);
  function loadSource(name = '本地视频.mp4') {
    $('sqImportVideo').click();
    $('sqVideoFile').onchange({ target: { files: [{ name }], value: name } });
    video.readyState = 2;
  }
  function setInterval(start, end, fps = 20) {
    $('sqStart').value = String(start); $('sqEnd').value = String(end); $('sqFps').value = String(fps);
    $('sqStartRange').value = String(start); $('sqEndRange').value = String(end);
  }
  return {
    $, video, window, api: window.__lifecycle, probes, timers, draws, revoked, dbGets, mattingCalls, backgroundSamples, loadSource, setInterval,
    downloads, objectUrls, pendingBlobs, dbPuts, stats: () => ({ descriptorCalls, findCalls }),
    deferGet() { const holder = {}; pendingGet = holder; return holder; },
    fireTimeout() { const timer = [...timers.values()].find(t => t.ms === 15000); assert.ok(timer, '应存在媒体解码超时计时器'); timer.fn(); },
  };
}
function released(f, probe = f.probes.at(-1)) {
  assert.ok(probe, '应创建独立 probe');
  assert.equal(probe.src, '', '结束后清除 probe src');
  assert.ok(probe.pauses > 0, '结束后暂停 probe');
  assert.equal(probe.loads, 2, '载入与清空各调用一次 load');
  assert.equal(probe.listenerCount(), 0, '清理媒体事件监听');
  assert.equal(f.timers.size, 0, '清理分析计时器');
  assert.equal(f.api.inspect().analyzingLoop, false);
  assert.equal(f.api.inspect().loopAnalysisController, null);
}
function unchanged(f, start = .12, end = .36) {
  assert.equal(Number(f.$('sqStart').value), start);
  assert.equal(Number(f.$('sqEnd').value), end);
}

test('真实 intervalFrameCount 排除浮点结束点', async () => {
  const f = await fixture();
  for (const [start, end, fps, expected] of [[0, 1, 20, 20], [.1, .4, 20, 6], [.1, .2, 30, 3], [.2, .30000000000000004, 30, 3], [0, .31, 20, 7], [1, 1, 20, 0], [1, 0, 20, 0]]) {
    assert.equal(f.api.intervalFrameCount(start, end, fps), expected, `${start}–${end} @ ${fps}`);
  }
});
test('自动识别循环帧按钮紧邻循环预览且只出现一次', async () => {
  const row = source.match(/<div class="sq-row">[^\n]*id="sqLoop"[^\n]*<\/div>/)?.[0];
  assert.ok(row); assert.match(row, /id="sqLoop"[^<]*>循环预览<\/button><button id="sqAnalyzeLoop" type="button">自动识别循环帧<\/button>/);
  assert.equal((source.match(/id="sqAnalyzeLoop"/g) || []).length, 1);
});
test('循环边界并发事件只seek一次，且无效区间时仍可停止', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.1, .4);
  await f.$('sqLoop').click(); await flush();
  assert.equal(f.$('sqLoop').textContent, '停止循环');
  f.video.holdSeek = true; f.video._time = .4; f.video.ontimeupdate();
  const seeksAfterBoundary = f.video.seekTimes.length;
  f.video._time = .4; f.video.ontimeupdate();
  const tick = [...f.timers.values()].find(timer => timer.ms === 16); assert.ok(tick); tick.fn();
  assert.equal(f.video.seekTimes.length, seeksAfterBoundary, '边界只允许一次活动seek');
  f.setInterval(.4, .1); f.$('sqLoop').click();
  assert.equal(f.video.paused, true); assert.equal(f.$('sqLoop').textContent, '循环预览');
});
test('循环起点等于当前时间且不seek时，后续边界仍能正常回绕', async () => {
  const f = await fixture({sameTimeNoSeek:true}); f.loadSource(); f.setInterval(.1,.4); f.video._time=.10001;
  await f.$('sqLoop').click(); await flush();
  assert.equal(f.video.seeking,false); assert.equal(f.video.paused,false);
  const before=f.video.seekTimes.length; f.video._time=.4; f.video.ontimeupdate();
  assert.equal(f.video.seekTimes.length,before+1,'无seeked起播不能卡住后续边界回绕');
  assert.equal(f.video.currentTime,.10001); f.$('sqLoop').click();
});
test('02制作序列帧真实历史交接后自动分析，不依赖手动导入', async () => {
  const f = await fixture({ holdLoad: true, history: [{ task_id: 'generated-task', characterId: '角色A', video_url: 'http://localhost/generated.mp4', action: 'walk', viewId: 'right_front_3q', status: 'succeeded' }] });
  f.$('videoTaskId').value = 'generated-task'; f.$('toSequence').click(); await flush();
  assert.equal(f.video.src, 'http://localhost/generated.mp4');
  assert.equal(f.api.inspect().state.taskId, 'generated-task');
  assert.equal(f.api.inspect().state.action, 'walk'); assert.equal(f.api.inspect().state.viewId, 'right_front_3q');
  f.video.emit('loadedmetadata'); assert.equal(f.api.inspect().analyzingLoop, true);
  f.probes.at(-1).emit('loadeddata'); await flush();
  unchanged(f, .1, .4); assert.equal(f.stats().findCalls, 1); released(f);
});
test('自动无可信结果后可点击新按钮重试，手动区间也支持主动重新识别', async () => {
  const config = { result: { fallback: true, confidence: 'low', reason: '暂未找到' } }, f = await fixture(config);
  f.loadSource(); f.video.emit('loadedmetadata'); await flush(); await flush();
  assert.equal(f.stats().findCalls, 1); assert.match(f.$('sqLoopAnalysis').textContent, /未发现可信循环/);
  f.setInterval(.12, .36); f.$('sqStart').oninput();
  assert.equal(f.api.inspect().videoTask.manualInterval, true); assert.equal(f.$('sqAnalyzeLoop').disabled, false);
  config.result = { start: .1, end: .4, confidence: 'high', fallback: false };
  await f.$('sqAnalyzeLoop').click();
  unchanged(f, .1, .4); assert.equal(f.stats().findCalls, 2); assert.match(f.$('sqLoopAnalysis').textContent, /已自动填写/); released(f);
});
test('缓存加载与定位已就绪但未派发事件仍可完成连续识别', async () => {
  const f = await fixture({ silentLoad: true, silentSeek: true }); f.loadSource();
  await f.api.analyzeLoopInterval(); unchanged(f,.1,.4); released(f);
  await f.$('sqAnalyzeLoop').click(); unchanged(f,.1,.4); released(f);
  assert.equal(f.stats().findCalls,2);
});
test('seeked提前到达但画面未就绪时不得采样，由canplay唤醒', async () => {
  const f = await fixture({ holdLoad:true }); f.loadSource();
  const running=f.api.analyzeLoopInterval(), probe=f.probes.at(-1); probe.holdSeek=true; probe.emit('loadeddata'); await flush();
  probe.readyState=1; probe.seeking=false; probe.emit('seeked'); await flush();
  assert.equal(f.draws.length,0); assert.equal(f.api.inspect().analyzingLoop,true);
  probe.holdSeek=false; probe.emit('canplay'); await running;
  unchanged(f,.1,.4); released(f);
});
test('媒体已就绪但seek事件缺失时由有界状态检查恢复', async () => {
  const f = await fixture({ holdLoad:true }); f.loadSource();
  const running=f.api.analyzeLoopInterval(), probe=f.probes.at(-1); probe.holdSeek=true; probe.emit('loadeddata'); await flush();
  assert.equal(f.draws.length,0); probe.seeking=false; probe.holdSeek=false;
  const timer=[...f.timers.values()].find(timer=>timer.ms===100); assert.ok(timer); timer.fn();
  await running; unchanged(f,.1,.4); released(f);
});
test('可信候选自动回填且独立 probe 采样不拖动主视频', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.12, .36);
  const before = f.video.currentTime;
  await f.api.analyzeLoopInterval();
  assert.equal(Number(f.$('sqStart').value), .1); assert.equal(Number(f.$('sqEnd').value), .4);
  assert.equal(Number(f.$('sqStartRange').value), .1); assert.equal(Number(f.$('sqEndRange').value), .4);
  assert.equal(f.stats().findCalls, 1); assert.ok(f.stats().descriptorCalls > 2);
  assert.ok(f.draws.every(draw => draw.media !== f.video));
  assert.equal(before, .23); assert.deepEqual(f.video.seekTimes, [.10001]);
  assert.equal(f.$('sqFps').value, '20'); assert.match(f.$('sqLoopAnalysis').textContent, /已自动填写/);
  released(f);
});
for (const [name, result, fill] of [
  ['fallback=true 即使 high 也不可回填', { start: .1, end: .4, confidence: 'high', fallback: true }, false],
  ['fallback 未提供的 low 候选可回填', { start: .1, end: .4, confidence: 'low' }, true],
  ['fallback=false 的 low 候选可回填', { start: .1, end: .4, confidence: 'low', fallback: false }, true],
  ['fallback=true 的 low 候选不可回填', { start: .1, end: .4, confidence: 'low', fallback: true }, false],
  ['空结果不回填', null, false],
  ['未知置信度不回填', { start: .1, end: .4, confidence: 'unknown' }, false],
  ['越界结果不回填', { start: .1, end: .8, confidence: 'high' }, false],
  ['非有限结果不回填', { start: NaN, end: .4, confidence: 'high' }, false],
]) test(name, async () => {
  const f = await fixture({ result }); f.loadSource(); f.setInterval(.12, .36);
  await f.api.analyzeLoopInterval();
  if (fill) { assert.equal(Number(f.$('sqStart').value), .1); assert.equal(Number(f.$('sqEnd').value), .4); }
  else { unchanged(f); assert.match(f.$('sqLoopAnalysis').textContent, /未发现可信循环/); }
  released(f);
});
test('自动识别回退16点快照的精确名义时刻采样，不加入10微秒偏移', async () => {
  let samples;
  const f = await fixture({duration:4.458333,onFind(value){samples=Array.from(value.samples);}});
  f.loadSource(); await f.api.analyzeLoopInterval();
  const probeDraws=f.draws.filter(draw=>draw.media.isProbe);
  assert.equal(probeDraws.length,samples.length);
  for(const i of [0,24,25,68,82,84]) {
    assert.ok(Math.abs(samples[i].time-i/24)<1e-12,'名义采样时刻不偏移');
    assert.ok(Math.abs(probeDraws[i].time-samples[i].time)<1e-12,'分析采样恢复快照的精确时刻');
    assert.equal(probeDraws[i].time,samples[i].time,'未加入后续采样偏移');
  }
  released(f);
});
test('自动候选保留亚毫秒精度，24FPS半开区间不多抽重复终点', async () => {
  const end=25/24,f=await fixture({duration:2,result:{start:0,end,confidence:'high',fallback:false}});
  f.loadSource();await f.api.analyzeLoopInterval();
  assert.equal(Number(f.$('sqEnd').value),end);
  f.$('sqFps').value='24';await f.$('sqExtract').click();
  assert.equal(f.api.inspect().raw.length,25);
  assert.ok(f.api.inspect().raw.every(frame=>frame.time<end));
  const draws=f.draws.filter(draw=>draw.media===f.video);
  assert.ok(draws.every((draw,i)=>Math.abs(draw.time-(i/24+.00001))<1e-12));
});
test('循环到达视频末尾timeupdate先回绕时ended仍能续播且不重复seek',async()=>{
  const f=await fixture();f.loadSource();f.setInterval(.1,.5);await f.$('sqLoop').click();await flush();
  f.video.holdSeek=true;f.video._time=.5;f.video.ontimeupdate();const count=f.video.seekTimes.length;
  f.video.paused=true;f.video.onended();assert.equal(f.video.paused,false);assert.equal(f.video.seekTimes.length,count);
  f.$('sqLoop').click();
});
test('无效循环到达ended不得重新播放全片',async()=>{
  const f=await fixture();f.loadSource();f.setInterval(.1,.4);await f.$('sqLoop').click();await flush();
  f.setInterval(.4,.1);f.video.onended();assert.equal(f.video.paused,true);assert.equal(f.$('sqLoop').textContent,'循环预览');
});
test('手动时间取消等待中的分析，旧结果不得回填', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const running = f.api.analyzeLoopInterval(), probe = f.probes.at(-1);
  f.$('sqStart').value = '.18'; f.$('sqStart').oninput();
  probe.emit('loadeddata'); await running;
  unchanged(f, .18, .36); assert.equal(f.stats().findCalls, 0);
  assert.equal(f.api.inspect().videoTask.manualInterval, true); released(f);
});
test('角色切换取消旧分析且不写入新角色', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const running = f.api.analyzeLoopInterval(), probe = f.probes.at(-1);
  f.window.activeCharacterId = '角色B'; f.window.emit('cotton-character-changed');
  probe.emit('loadeddata'); await running; await flush();
  assert.equal(f.api.inspect().state.characterId, '角色B'); assert.equal(f.api.inspect().videoTask, null);
  assert.equal(f.stats().findCalls, 0); assert.notEqual(f.$('sqLoopAnalysis').textContent.includes('已自动填写'), true); released(f);
});
test('视频源切换取消旧分析且旧 probe 不回填', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource('旧.mp4'); f.setInterval(.12, .36);
  const oldSource = f.video.src, running = f.api.analyzeLoopInterval();
  f.loadSource('新.mp4'); f.setInterval(.2, .45); await running;
  unchanged(f, .2, .45); assert.notEqual(f.video.src, oldSource);
  assert.equal(f.api.inspect().state.videoName, '新.mp4'); assert.ok(f.revoked.includes(oldSource)); assert.equal(f.stats().findCalls, 0); released(f);
});
test('findLoop 返回前手动修改仍须拒绝旧结果', async () => {
  let f;
  f = await fixture({ onFind() { f.$('sqStart').value = '.19'; f.$('sqStart').oninput(); } });
  f.loadSource(); f.setInterval(.12, .36); await f.api.analyzeLoopInterval();
  unchanged(f, .19, .36); assert.equal(f.stats().findCalls, 1); released(f);
});
test('重复 loadedmetadata 不重置手动区间或重启分析', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.video.onloadedmetadata();
  assert.equal(f.probes.length, 1);
  f.$('sqStart').value = '.15'; f.$('sqStart').oninput(); f.$('sqEnd').value = '.35'; f.$('sqEnd').oninput();
  f.video.onloadedmetadata(); f.video.onloadedmetadata(); await flush();
  unchanged(f, .15, .35); assert.equal(f.probes.length, 1); assert.equal(f.api.inspect().videoTask.metadataInitialized, true); released(f);
});
test('首次 metadata 前已手动修改也不得被初始化覆盖', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.12, .36); f.$('sqStart').oninput();
  f.video.onloadedmetadata(); await flush(); unchanged(f);
  assert.equal(f.probes.length, 0); assert.equal(f.api.inspect().videoTask.manualInterval, true);
});
test('重复 metadata 在自动分析期间及完成后均只启动一次', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource();
  f.video.onloadedmetadata(); f.video.onloadedmetadata(); f.video.onloadedmetadata();
  assert.equal(f.probes.length, 1); assert.equal(f.api.inspect().analyzingLoop, true);
  f.probes[0].emit('loadeddata'); await flush();
  assert.equal(f.stats().findCalls, 1); unchanged(f, .1, .4); released(f);
  f.video.onloadedmetadata(); await flush();
  assert.equal(f.probes.length, 1); assert.equal(f.stats().findCalls, 1); unchanged(f, .1, .4);
  assert.equal(f.api.inspect().videoTask.analysisStarted, true);
});
test('已切换 source 的 metadata 不得初始化或触发自动分析', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.12, .36);
  f.video.src = 'blob:不匹配的来源'; f.video.onloadedmetadata(); await flush();
  unchanged(f); assert.equal(f.probes.length, 0);
  assert.equal(f.api.inspect().videoTask.metadataInitialized, undefined);
});
for (const [name, change, expectedStart, expectedEnd] of [
  ['结束数字输入', f => { f.$('sqEnd').value = '.33'; f.$('sqEnd').oninput(); }, .12, .33],
  ['开始滑块', f => { f.$('sqStartRange').value = '.16'; f.$('sqStartRange').oninput(); }, .16, .36],
  ['结束滑块', f => { f.$('sqEndRange').value = '.34'; f.$('sqEndRange').oninput(); }, .12, .34],
  ['当前时间设为开始', f => f.$('sqStartNow').click(), .23, .36],
  ['当前时间设为结束', f => f.$('sqEndNow').click(), .12, .23],
  ['时长预设', f => { f.$('sqDurationPreset').value = '.2'; f.$('sqDurationPreset').onchange(); }, .12, .32],
]) test(`${name}取消分析并同步保留手动区间`, async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const running = f.api.analyzeLoopInterval(); change(f); await running;
  unchanged(f, expectedStart, expectedEnd);
  assert.equal(Number(f.$('sqStartRange').value), expectedStart); assert.equal(Number(f.$('sqEndRange').value), expectedEnd);
  assert.equal(f.api.inspect().videoTask.manualInterval, true); assert.equal(f.stats().findCalls, 0);
  assert.equal(f.$('sqExtract').disabled, false); assert.equal(f.$('sqAnalyzeLoop').disabled, false);
  assert.match(f.$('sqLoopAnalysis').textContent, /手动区间/); released(f);
});
test('连续重新分析时旧任务 finally 不得清除新任务控制器', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const first = f.api.analyzeLoopInterval(), firstProbe = f.probes.at(-1);
  const second = f.api.analyzeLoopInterval(), secondProbe = f.probes.at(-1);
  const controller = f.api.inspect().loopAnalysisController;
  await first;
  assert.notEqual(firstProbe, secondProbe); assert.equal(firstProbe.src, ''); assert.equal(firstProbe.listenerCount(), 0);
  assert.equal(f.api.inspect().analyzingLoop, true); assert.equal(f.api.inspect().loopAnalysisController, controller);
  assert.equal(controller.signal.aborted, false); assert.equal(f.$('sqExtract').disabled, true);
  firstProbe.emit('loadeddata'); assert.equal(f.stats().findCalls, 0);
  secondProbe.emit('loadeddata'); await second;
  assert.equal(f.stats().findCalls, 1); unchanged(f, .1, .4);
  assert.equal(f.$('sqExtract').disabled, false); assert.equal(f.$('sqAnalyzeLoop').disabled, false); released(f, secondProbe);
});
test('历史视频等待异步 restore 期间换角色必须拒绝载入', async () => {
  const f = await fixture(); f.window.activeCharacterId = '角色B'; const deferred = f.deferGet();
  const loading = f.window.SequenceWorkflow.useVideo({ characterId: '角色B', url: 'http://localhost/history.mp4', taskId: 'history-task' });
  const rejected = assert.rejects(loading, /载入期间角色已切换/);
  await flush(); assert.ok(deferred.request, '历史视频应等待角色B草稿读取');
  f.window.activeCharacterId = '角色C'; f.window.emit('cotton-character-changed');
  deferred.request.result = { characterId: '角色B', videoName: '过期草稿' }; deferred.request.onsuccess();
  await rejected; await flush();
  assert.equal(f.api.inspect().state.characterId, '角色C'); assert.equal(f.video.src, ''); assert.equal(f.api.inspect().videoTask, null);
});
test('取消等待 seek 的分析会释放 probe、事件与计时器', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource();
  const running = f.api.analyzeLoopInterval(), probe = f.probes.at(-1); probe.holdSeek = true; probe.emit('loadeddata'); await flush();
  assert.ok(probe.listenerCount() > 0); f.api.cancelLoopAnalysis(); await running;
  assert.equal(f.stats().findCalls, 0); released(f);
});
for (const [name, config, pattern] of [
  ['分析加载异常释放', { loadError: true }, /解码失败/],
  ['分析绘图异常释放', { drawError: true }, /模拟画布失败/],
]) test(name, async () => {
  const f = await fixture(config); f.loadSource(); f.setInterval(.12, .36); await f.api.analyzeLoopInterval();
  unchanged(f); assert.match(f.$('sqLoopAnalysis').textContent, pattern); released(f);
});
test('分析超时清理事件和 probe', async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const running = f.api.analyzeLoopInterval(); f.fireTimeout(); await running;
  unchanged(f); assert.match(f.$('sqLoopAnalysis').textContent, /超时/); released(f);
});
for (const [name, finish, pattern] of [
  ['超时', f => f.fireTimeout(), /超时/],
  ['解码失败', (f, probe) => probe.emit('error'), /解码失败/],
]) test(`分析等待 seek ${name}释放 probe、监听及计时器`, async () => {
  const f = await fixture({ holdLoad: true }); f.loadSource(); f.setInterval(.12, .36);
  const running = f.api.analyzeLoopInterval(), probe = f.probes.at(-1);
  probe.holdSeek = true; probe.emit('loadeddata'); await flush();
  assert.equal(probe.seeking, true); assert.ok(probe.listenerCount() > 0);
  finish(f, probe); await running;
  unchanged(f); assert.equal(f.stats().findCalls, 0); assert.match(f.$('sqLoopAnalysis').textContent, pattern);
  assert.equal(f.$('sqExtract').disabled, false); assert.equal(f.$('sqAnalyzeLoop').disabled, false); released(f);
});
test('抽帧端点排除、帧数与原视频控件恢复', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.1, .4, 20);
  const running = f.$('sqExtract').click();
  assert.equal(f.video.controls, false); assert.equal(f.api.inspect().extracting, true);
  await running;
  const times = Array.from(f.api.inspect().raw, frame => frame.time);
  assert.equal(times.length, 6); assert.ok(times.every(time => time < .4));
  assert.deepEqual(times, Array.from({ length: 6 }, (_, i) => .1 + i / 20));
  assert.equal(f.draws.filter(draw => draw.media === f.video).length, 6);
  assert.equal(f.video.controls, true); assert.equal(f.api.inspect().extracting, false);
  assert.equal(f.api.inspect().extractController, null); assert.equal(f.$('sqCancelExtract').hidden, true);
  assert.equal(f.video.listenerCount(), 1, '只保留 playing 固定监听'); assert.equal(f.timers.size, 0);
});
test('抽帧取消保留旧帧并恢复控件与等待监听', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.1, .4); const old = { blob: {}, name: '旧帧', checked: true, time: 0 };
  f.api.seedRaw([old]); f.video.holdSeek = true; const running = f.$('sqExtract').click();
  assert.equal(f.video.controls, false); f.$('sqCancelExtract').click(); await running;
  assert.equal(f.api.inspect().raw[0], old); assert.equal(f.video.controls, true);
  assert.equal(f.api.inspect().extractController, null); assert.equal(f.$('sqCancelExtract').hidden, true);
  assert.equal(f.video.listenerCount(), 1); assert.equal(f.timers.size, 0);
});
test('抽帧编码异常保留旧帧且恢复控件', async () => {
  const f = await fixture({ blobError: true }); f.loadSource(); f.setInterval(.1, .4); const old = { blob: {}, name: '旧帧', checked: true, time: 0 }; f.api.seedRaw([old]);
  await f.$('sqExtract').click();
  assert.equal(f.api.inspect().raw[0], old); assert.match(f.$('sqVideoStatus').textContent, /PNG 编码失败/);
  assert.equal(f.video.controls, true); assert.equal(f.api.inspect().extracting, false); assert.equal(f.api.inspect().extractController, null);
  assert.equal(f.timers.size, 0);
});

for (const [name, config, prepare, finish, message] of [
  ['等待 loadeddata 超时', {}, f => { f.video.readyState = 0; }, f => f.fireTimeout(), /超时/],
  ['等待 seek 超时', {}, f => { f.video.holdSeek = true; }, f => f.fireTimeout(), /超时/],
  ['等待 seek 解码失败', {}, f => { f.video.holdSeek = true; }, f => f.video.emit('error'), /解码失败/],
  ['画布绘图失败', { drawError: true }, () => {}, () => {}, /模拟画布失败/],
]) test(`抽帧${name}保留旧帧并恢复 controls`, async () => {
  const f = await fixture(config); f.loadSource(); f.setInterval(.1, .4);
  const old = { blob: {}, name: '旧帧', checked: true, time: 0 }; f.api.seedRaw([old]); prepare(f);
  const running = f.$('sqExtract').click(); assert.equal(f.video.controls, false); finish(f); await running;
  assert.equal(f.api.inspect().raw[0], old); assert.match(f.$('sqVideoStatus').textContent, message);
  assert.equal(f.video.controls, true); assert.equal(f.api.inspect().extracting, false);
  assert.equal(f.api.inspect().extractController, null); assert.equal(f.$('sqCancelExtract').hidden, true);
  assert.equal(f.$('sqExtract').disabled, false); assert.equal(f.$('sqAnalyzeLoop').disabled, false);
  assert.equal(f.video.listenerCount(), 1); assert.equal(f.timers.size, 0);
});
test('抽帧中切换角色取消旧任务并在恢复完成后释放 controls', async () => {
  const f = await fixture(); f.loadSource(); f.setInterval(.1, .4); f.video.holdSeek = true;
  const running = f.$('sqExtract').click(); assert.equal(f.video.controls, false);
  f.window.activeCharacterId = '角色B'; f.window.emit('cotton-character-changed'); await running; await flush();
  assert.equal(f.api.inspect().state.characterId, '角色B'); assert.equal(f.api.inspect().raw.length, 0);
  assert.equal(f.api.inspect().restoreBusy, false); assert.equal(f.api.inspect().restorePending, false);
  assert.equal(f.api.inspect().videoTask, null); assert.equal(f.video.src, '');
  assert.equal(f.video.controls, true); assert.equal(f.api.inspect().extracting, false);
  assert.equal(f.api.inspect().extractController, null); assert.equal(f.$('sqCancelExtract').hidden, true);
  assert.equal(f.video.listenerCount(), 1); assert.equal(f.timers.size, 0);
});
for (const [start, end, fps, count] of [[.1, .2, 30, 3], [.2, .30000000000000004, 30, 3], [0, .31, 20, 7]]) {
  test(`真实抽帧 ${start}–${end} @ ${fps} 排除浮点终点且匹配预估`, async () => {
    const f = await fixture(); f.loadSource(); f.setInterval(start, end, fps); f.$('sqFps').oninput();
    assert.match(f.$('sqEstimate').textContent, new RegExp(`预计 ${count} 帧`));
    await f.$('sqExtract').click();
    const times = Array.from(f.api.inspect().raw, frame => frame.time);
    assert.equal(times.length, count); assert.equal(times.length, f.api.intervalFrameCount(start, end, fps));
    assert.deepEqual(times, Array.from({ length: count }, (_, i) => start + i / fps));
    assert.ok(times.every(time => time < end)); assert.equal(f.video.controls, true);
    assert.equal(f.video.listenerCount(), 1); assert.equal(f.timers.size, 0);
  });
}
test('未触发取消时源地址变动也须通过 source 校验拒绝旧结果', async () => {
  let f; f = await fixture({ onFind() { f.video.src = 'blob:已变更'; } });
  f.loadSource(); f.setInterval(.12, .36); await f.api.analyzeLoopInterval();
  unchanged(f); assert.equal(f.stats().findCalls, 1); released(f);
});
test('未触发事件时当前角色变动也须拒绝旧结果', async () => {
  let f; f = await fixture({ onFind() { f.window.activeCharacterId = '角色B'; } });
  f.loadSource(); f.setInterval(.12, .36); await f.api.analyzeLoopInterval();
  unchanged(f); assert.equal(f.stats().findCalls, 1); released(f);
});
function coloredFrame(name, color, time = 0) {
  const data = new Uint8ClampedArray(8 * 4 * 4);
  for (let i = 0; i < data.length; i += 4) data.set([...color, 255], i);
  return { name, time, checked: true, blob: { width: 8, height: 4, data } };
}
test('预览及批处理真实 processFrame 共享 keyImage、首帧缓存与处理选项', async () => {
  const f = await fixture(); f.loadSource();
  const first = coloredFrame('首帧.png', [250, 248, 245]), second = coloredFrame('次帧.png', [200, 210, 220], .05);
  f.api.seedRaw([first, second]);
  for (const [id, value] of Object.entries({ sqMatte: 'chroma', sqColorPreset: 'auto', sqTolerance: '37', sqSpill: '65', sqFeather: '7', sqEdgeClean: '3', sqSize: 'original', sqQuality: 'pixel' })) f.$(id).value = value;
  f.$('sqSmooth').checked = false;
  await f.$('sqPreviewProcessed').click();
  assert.equal(f.mattingCalls.length, 1); assert.equal(f.backgroundSamples.length, 1);
  assert.equal(f.api.inspect().processed.length, 0, '单帧试看不能冒充批量处理结果');
  assert.match(f.$('sqProcessedMode').textContent, /单帧试看/);
  await f.$('sqProcess').click();
  assert.equal(f.mattingCalls.length, 3, '预览一帧与批处理两帧均进入真实 keyImage 调用点');
  assert.equal(f.backgroundSamples.length, 1, '同一视频只取首帧背景色');
  const expected = { key: [250, 248, 245], tolerance: 37, feather: 7, smooth: false, spill: .65, edgeClean: 3, edgeChoke: 1 };
  for (const call of f.mattingCalls) {
    assert.deepEqual(call.options, expected); assert.equal(call.width, 8); assert.equal(call.height, 4);
  }
  assert.deepEqual(f.mattingCalls[2].input.slice(0, 3), [200, 210, 220]);
  assert.equal(f.api.inspect().processed.length, 2); assert.equal(f.api.inspect().processing, false);
  assert.match(f.$('sqProcessStatus').textContent, /完成 2 帧/);
});
test('直接调用真实 processFrame 支持自定义色、原始尺寸及来源索引', async () => {
  const f = await fixture(); f.loadSource(); const frame = coloredFrame('帧.png', [9, 10, 11]); f.api.seedRaw([frame]);
  const options = { ...f.api.settings(), mode: 'chroma', key: 'custom', color: '#123456', tolerance: 20, spill: .2, feather: 8, smooth: true, edgeClean: 2, size: 'original', corners: [] };
  const processed = await f.api.processFrame(frame, options);
  assert.equal(f.mattingCalls.length, 1); assert.equal(f.backgroundSamples.length, 0);
  assert.deepEqual(f.mattingCalls[0].options, { key: [18, 52, 86], tolerance: 20, spill: .2, feather: 8, smooth: true, edgeClean: 2, edgeChoke: .5 });
  assert.equal(processed.sourceIndex, 0); assert.equal(processed.blob.width, 8); assert.equal(processed.blob.height, 4); assert.equal(processed.url, undefined);
});
test('局部修整控件及预览canvas指针事件均已移除', async () => {
  const f = await fixture(); f.loadSource(); f.api.seedRaw([coloredFrame('帧.png', [90, 80, 70])]);
  await f.$('sqProcess').click();
  assert.equal(/sqRepair/.test(source), false, '生产源码不再包含局部修整控件引用');
  for (const id of ['sqRepairMode', 'sqRepairSize', 'sqRepairFeather', 'sqRepairTolerance', 'sqRepairLimit', 'sqRepairUndo', 'sqRepairStatus']) {
    assert.equal(f.$(id), undefined, id + ' 不应渲染');
  }
  for (const id of ['sqFrameCanvas', 'sqProcessedCanvas', 'sqAnimationCanvas']) {
    const canvas = f.$(id);
    for (const event of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel']) {
      assert.equal(canvas.listeners.get(event)?.size || 0, 0, id + ' 不应注册 ' + event);
      assert.equal(typeof canvas['on' + event], 'undefined', id + ' 不应绑定 on' + event);
    }
  }
});
test('点击和拖动预览不改变批处理Blob、缩略图或导出ZIP', async () => {
  const config = {}, f = await fixture(config); f.loadSource();
  f.api.seedRaw([coloredFrame('一.png', [90, 80, 70]), coloredFrame('二.png', [70, 80, 90], .05)]);
  f.$('sqSize').value = 'original'; await f.$('sqProcess').click(); await flush();
  const frames = f.api.inspect().processed, blobs = frames.map(frame => frame.blob), urls = frames.map(frame => frame.url);
  const payloads = await Promise.all(blobs.map(async blob => Array.from(new Uint8Array(await blob.arrayBuffer()))));
  const canvas = f.$('sqProcessedCanvas'), pixels = Array.from(canvas.getContext().getImageData().data);
  await f.$('sqProcessedZip').click();
  const beforeZip = Array.from(new Uint8Array(await f.downloads[0].blob.arrayBuffer())), putsBefore = f.dbPuts.length;
  config.holdBlob = true;
  for (const id of ['sqFrameCanvas', 'sqProcessedCanvas']) {
    const preview = f.$(id);
    preview.click(); preview.emit('click', { button: 0, clientX: 12, clientY: 22 });
    preview.emit('pointerdown', { button: 0, pointerId: 1, clientX: 12, clientY: 22 });
    preview.emit('pointermove', { buttons: 1, pointerId: 1, clientX: 22, clientY: 24 });
    preview.emit('pointerup', { button: 0, pointerId: 1, clientX: 22, clientY: 24 });
    preview.emit('pointerdown', { button: 0, pointerId: 2, clientX: 14, clientY: 22 });
    preview.emit('pointercancel', { pointerId: 2 });
  }
  await flush();
  assert.equal(f.api.inspect().processed, frames);
  assert.equal(f.api.inspect().processing, false); assert.equal(f.pendingBlobs.length, 0, '预览交互不应触发PNG编码');
  assert.equal(f.dbPuts.length, putsBefore, '预览交互不应触发草稿保存');
  for (let i = 0; i < frames.length; i++) {
    assert.equal(frames[i].blob, blobs[i]); assert.equal(frames[i].url, urls[i]);
    assert.equal(frames[i].repairOriginalBlob, undefined);
    assert.deepEqual(Array.from(new Uint8Array(await frames[i].blob.arrayBuffer())), payloads[i]);
    assert.equal(f.objectUrls.get(f.$('sqProcessedFrames').querySelectorAll('img')[i].src), blobs[i]);
  }
  assert.deepEqual(Array.from(canvas.getContext().getImageData().data), pixels);
  await f.$('sqProcessedZip').click();
  assert.equal(f.downloads.length, 2); assert.equal(f.downloads[1].name, 'processed_frames.zip');
  assert.deepEqual(Array.from(new Uint8Array(await f.downloads[1].blob.arrayBuffer())), beforeZip);
});
test('已有批处理时单帧试看仍不覆盖批处理及导出，返回后恢复批处理画面', async () => {
  const f = await fixture(); f.loadSource();
  const input = coloredFrame('帧.png', [90, 80, 70]); f.api.seedRaw([input]);
  f.$('sqSize').value = 'original'; await f.$('sqProcess').click(); await flush();
  const frames = f.api.inspect().processed, blob = frames[0].blob;
  const batchPixels = Array.from(f.$('sqProcessedCanvas').getContext().getImageData().data), putsBefore = f.dbPuts.length;
  input.blob.data.set([10, 20, 30, 255], 0);
  await f.$('sqPreviewProcessed').click();
  assert.match(f.$('sqProcessedMode').textContent, /单帧试看/);
  assert.notEqual(f.$('sqProcessedCanvas').getContext().getImageData().data[0], batchPixels[0], '试看确实绘制了不同于批处理的画面');
  assert.equal(f.api.inspect().processed, frames); assert.equal(frames[0].blob, blob);
  assert.equal(f.dbPuts.length, putsBefore, '单帧试看不保存或替换批处理');
  assert.equal(f.$('sqProcessedZip').disabled, false); assert.equal(f.$('sqToSpine').disabled, false);
  await f.$('sqProcessedZip').click();
  const bytes = new Uint8Array(await f.downloads[0].blob.arrayBuffer()), view = new DataView(bytes.buffer);
  const start = 30 + view.getUint16(26, true) + view.getUint16(28, true), payload = new Uint8Array(await blob.arrayBuffer());
  assert.deepEqual(Array.from(bytes.slice(start, start + payload.length)), Array.from(payload));
  f.$('sqShowProcessed').click(); await flush();
  assert.match(f.$('sqProcessedMode').textContent, /批处理结果/);
  assert.deepEqual(Array.from(f.$('sqProcessedCanvas').getContext().getImageData().data), batchPixels);
  assert.equal(frames[0].blob, blob); assert.equal(f.api.inspect().processing, false);
});
test('带repairOriginalBlob的旧草稿可恢复且不自动回滚PNG、删除字段或回写', async () => {
  const f = await fixture(), original = coloredFrame('原图.png', [90, 80, 70]);
  const repairedData = original.blob.data.slice(); repairedData[3] = 0;
  const repaired = Object.assign(new Blob([repairedData], { type: 'image/png' }), { width: 8, height: 4, data: repairedData });
  const repairOriginalBlob = Object.assign(new Blob([original.blob.data], { type: 'image/png' }), original.blob);
  const savedFrame = { name: '旧修整.png', time: 0, sourceIndex: 0, checked: true, blob: repaired, repairOriginalBlob };
  const saved = { characterId: '角色A', videoName: '旧草稿.mp4', raw: [original], processed: [savedFrame], groups: [] };
  const putsBefore = f.dbPuts.length, deferred = f.deferGet(), restoring = f.api.restore('角色A');
  await flush(); assert.ok(deferred.request, '恢复必须读取内存夹具提供的旧草稿');
  deferred.request.result = saved; deferred.request.onsuccess(); await restoring; await flush();
  const frame = f.api.inspect().processed[0];
  assert.equal(f.api.inspect().restoreBusy, false); assert.equal(f.api.inspect().processed.length, 1);
  assert.equal(f.api.inspect().state.videoName, '旧草稿.mp4'); assert.match(f.$('sqVideoName').textContent, /已恢复帧/);
  assert.equal(frame.blob, repaired); assert.equal(frame.repairOriginalBlob, repairOriginalBlob);
  assert.equal(savedFrame.blob, repaired); assert.equal(savedFrame.repairOriginalBlob, repairOriginalBlob);
  assert.equal(f.objectUrls.get(frame.url), repaired); assert.equal(f.$('sqProcessedCanvas').getContext().getImageData().data[3], 0);
  assert.deepEqual(Array.from(new Uint8Array(await frame.blob.arrayBuffer())), Array.from(repairedData));
  assert.equal(new Uint8Array(await frame.repairOriginalBlob.arrayBuffer())[3], 255, '旧备份PNG保持不变');
  assert.equal(f.dbPuts.length, putsBefore, '恢复不应自动迁移或保存旧草稿');
  await f.$('sqProcessedZip').click();
  const bytes = new Uint8Array(await f.downloads[0].blob.arrayBuffer()), view = new DataView(bytes.buffer);
  const start = 30 + view.getUint16(26, true) + view.getUint16(28, true);
  assert.deepEqual(Array.from(bytes.slice(start, start + repairedData.length)), Array.from(repairedData), '导出仍使用旧草稿现有PNG，而非修整前备份');
  assert.equal(frame.repairOriginalBlob, repairOriginalBlob); assert.equal(f.dbPuts.length, putsBefore);
});
test('切换视频后自动背景缓存重建', async () => {
  const f = await fixture(); f.loadSource('一.mp4'); const options = { ...f.api.settings(), mode: 'chroma', key: 'auto', size: 'original', corners: [] };
  await f.api.processFrame(coloredFrame('一.png', [250, 248, 245]), options);
  f.loadSource('二.mp4'); await f.api.processFrame(coloredFrame('二.png', [12, 34, 56]), options);
  assert.equal(f.backgroundSamples.length, 2); assert.deepEqual(f.mattingCalls[1].options.key, [12, 34, 56]);
});

test('先试看第二帧仍从原始第一帧锁定自动背景色', async () => {
  const f = await fixture(); f.loadSource();
  const first = coloredFrame('首帧.png', [249, 247, 245]), second = coloredFrame('次帧.png', [30, 60, 90], .05);
  f.api.seedRaw([first, second]);
  await f.api.processFrame(second, { ...f.api.settings(), mode:'chroma',key:'auto',size:'original',corners:[] });
  assert.deepEqual(f.mattingCalls[0].options.key, [249, 247, 245]);
  assert.deepEqual(f.mattingCalls[0].input.slice(0,3), [30,60,90]);
  assert.equal(f.backgroundSamples.length, 1);
});
test('检查底色只影响CSS且不清理批处理或写入像素', async () => {
  const f = await fixture(); f.loadSource(); f.api.seedRaw([coloredFrame('帧.png',[90,80,70])]);
  await f.$('sqProcess').click(); const frames = f.api.inspect().processed, blob = frames[0].blob;
  f.$('sqMattePreviewBg').value = '#ff00ff'; f.$('sqMattePreviewBg').onchange();
  assert.equal(f.$('sqProcessedCanvas').style.backgroundColor, '#ff00ff');
  assert.equal(f.$('sqProcessedCanvas').style.backgroundImage, 'none');
  assert.equal(f.api.inspect().processed, frames); assert.equal(frames[0].blob, blob);
  f.$('sqMattePreviewBg').value = 'checker'; f.$('sqMattePreviewBg').onchange();
  assert.equal(f.$('sqProcessedCanvas').style.backgroundColor, '');
  assert.equal(f.$('sqProcessedCanvas').style.backgroundImage, '');
});
test('边缘净化输入更新显示并使旧处理帧失效', async () => {
  const f = await fixture(); f.loadSource(); f.api.seedRaw([coloredFrame('帧.png',[90,80,70])]);
  await f.$('sqProcess').click(); assert.equal(f.api.inspect().processed.length, 1);
  f.$('sqEdgeClean').value='2'; f.$('sqEdgeClean').emit('input');
  assert.equal(f.$('sqEdgeCleanValue').textContent, '2 / 3');
  assert.equal(f.api.inspect().processed.length, 0);
  assert.equal(f.api.settings().edgeClean, 2);
});

test('下载ZIP逐字节使用当前处理Blob且检查底色不写入文件', async () => {
  const f = await fixture(); f.loadSource();
  f.api.seedRaw([coloredFrame('原始.png',[90,80,70])]); await f.$('sqProcess').click();
  const payload = new Uint8Array([137,80,78,71,13,10,26,10,0,255,31]);
  f.api.inspect().processed[0].blob = new Blob([payload],{type:'image/png'});
  f.$('sqMattePreviewBg').value='#000000'; f.$('sqMattePreviewBg').onchange();
  await f.$('sqProcessedZip').click();
  assert.equal(f.downloads.length, 1); assert.equal(f.downloads[0].name,'processed_frames.zip');
  const bytes = new Uint8Array(await f.downloads[0].blob.arrayBuffer()), view = new DataView(bytes.buffer);
  assert.equal(view.getUint32(0,true),0x04034b50); assert.equal(view.getUint32(18,true),payload.length);
  const nameLength=view.getUint16(26,true), extraLength=view.getUint16(28,true), start=30+nameLength+extraLength;
  assert.equal(new TextDecoder().decode(bytes.slice(30,30+nameLength)),'frame_0001.png');
  assert.deepEqual(Array.from(bytes.slice(start,start+payload.length)),Array.from(payload));
});

test('地址导入运行真实useVideo并在metadata后自动分析', async () => {
  const f = await fixture({holdLoad:true});
  f.$('sqVideoUrl').value = 'http://localhost/source.mp4';
  await f.$('sqImportUrl').click();
  assert.equal(f.video.src, 'http://localhost/source.mp4');
  assert.equal(f.api.inspect().state.videoName, '地址导入视频');
  assert.equal(f.api.inspect().state.taskId, '');
  f.video.emit('loadedmetadata');
  assert.equal(f.api.inspect().analyzingLoop, true);
  f.probes[0].emit('loadeddata'); await flush();
  assert.equal(f.stats().findCalls, 1);
  assert.equal(Number(f.$('sqStart').value), .1);
  assert.equal(Number(f.$('sqEnd').value), .4);
});
for (const address of ['', 'file:///C:/video.mp4', 'javascript:alert(1)', 'https://user:secret@example.com/video.mp4']) {
  test('地址导入拒绝无效或含凭据地址：' + address.split(':')[0], async () => {
    const f = await fixture(); f.loadSource();
    const source = f.video.src, state = f.api.inspect().state;
    f.$('sqVideoUrl').value = address; await f.$('sqImportUrl').click();
    assert.equal(f.video.src, source); assert.equal(f.api.inspect().state, state);
    assert.match(f.$('sqVideoStatus').textContent, /地址导入失败/);
  });
}

(async () => {
  let failures = 0;
  for (const { name, run } of cases) {
    const before = assertions;
    try { await run(); console.log(`通过 ${name}（${assertions - before} 条断言）`); }
    catch (error) { failures++; console.error(`失败 ${name}\n${error.stack}`); }
  }
  const workflowSha256 = createHash('sha256').update(source).digest('hex');
  const sourceUnchanged = fs.readFileSync(workflowPath, 'utf8') === source;
  console.log(JSON.stringify({ testFile: path.basename(__filename), workflowSha256, sourceUnchanged, cases: cases.length, assertions, passed: cases.length - failures, failed: failures }));
  process.exitCode = failures ? 1 : 0;
})();
