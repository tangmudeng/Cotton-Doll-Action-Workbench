'use strict';
const assert = require('node:assert/strict');
const { describeFrame, findLoop } = require('../sequence-loop-analysis.js');

const N = 96;
function descriptor(x, y, intensity) {
  const values = new Array(N).fill(0);
  const ix = Math.max(0, Math.min(11, Math.round(x * 11)));
  const iy = Math.max(0, Math.min(7, Math.round(y * 7)));
  values[iy * 12 + ix] = intensity;
  return { values };
}
function samplesFor(fn, count = 97, noise = 0) {
  return Array.from({ length: count }, (_, i) => {
    const time = i / 24;
    const values = fn(time, i);
    if (noise) for (let k = 0; k < values.length; k++) values[k] += (Math.sin((i + 1) * 127.1 + k * 311.7) - 0.5) * noise;
    return { time, descriptor: { values } };
  });
}
function movingShape(x, y, brightness = 1) {
  const values = new Array(N).fill(0);
  const cx = Math.round(2 + x * 7), cy = Math.round(1 + y * 5);
  for (let yy = cy; yy < cy + 2; yy++) for (let xx = cx; xx < cx + 2; xx++) values[yy * 12 + xx] = brightness;
  return values;
}

const staticResult = findLoop(samplesFor(() => new Array(N).fill(0.2)));
assert.equal(staticResult.confidence, 'low');
assert.match(staticResult.reason, /静态|明显运动/);

let seed = 123456789;
function random() { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }
const noiseResult = findLoop(samplesFor(() => Array.from({ length: N }, () => 0.5 + (random() - 0.5) * 0.025)));
assert.equal(noiseResult.confidence, 'low');

const intensityCycle = findLoop(samplesFor(t => new Array(N).fill(0.5 + 0.35 * Math.sin(2 * Math.PI * t))));
assert.notEqual(intensityCycle.confidence, 'low', JSON.stringify(intensityCycle));
assert.ok(Math.abs(intensityCycle.period - 1) < 0.12, JSON.stringify(intensityCycle));

const positionCycle = findLoop(samplesFor(t => movingShape(0.5 + 0.42 * Math.sin(2 * Math.PI * t), 0.5 + 0.28 * Math.cos(2 * Math.PI * t))));
assert.notEqual(positionCycle.confidence, 'low', JSON.stringify(positionCycle));
assert.ok(Math.abs(positionCycle.period - 1) < 0.14, JSON.stringify(positionCycle));

// 同一姿态在半程处反向经过；半周期端点虽相似，但局部速度方向相反。
const reversal = findLoop(samplesFor(t => movingShape(0.5 + 0.43 * Math.sin(2 * Math.PI * t), 0.5)));
assert.notEqual(reversal.confidence, 'low', JSON.stringify(reversal));
assert.ok(reversal.period > 0.8, JSON.stringify(reversal));

const nonPeriodic = findLoop(samplesFor(t => movingShape(0.3 + 0.55 * t, 0.42 + 0.2 * Math.sin(t * 3)), 97));
assert.equal(nonPeriodic.confidence, 'low', JSON.stringify(nonPeriodic));

const rgba = new Uint8Array(8 * 6 * 4);
for (let i = 0; i < 48; i++) { rgba[i * 4] = i * 3; rgba[i * 4 + 1] = 80; rgba[i * 4 + 2] = 200; rgba[i * 4 + 3] = 255; }
const compact = describeFrame(rgba, 8, 6);
assert.equal(compact.values.length, 24 * 16 * 3);
assert.ok(Object.keys(compact).length < 5);
assert.throws(() => describeFrame(new Uint8Array(3), 2, 2), TypeError);

// 大面积主体每秒重复，小区域每两秒才同相；全局误差不能替代局部运动验证。
function mixedPeriodSamples(rate, duration, flipped = false) {
  return Array.from({ length: Math.round(rate * duration) + 1 }, (_, i) => {
    const time = i / rate, rgba = new Uint8Array(24 * 16 * 4);
    for (let y = 0; y < 16; y++) for (let x = 0; x < 24; x++) {
      const xx = flipped ? 23 - x : x, yy = flipped ? 15 - y : y;
      const value = yy < 8 ? 0.5 + 0.35 * Math.sin(2 * Math.PI * time) :
        xx >= 6 && xx < 18 && yy >= 10 && yy < 14 ? 0.5 + 0.18 * Math.sin(Math.PI * time) : 0.5;
      const p = (y * 24 + x) * 4;
      rgba[p] = rgba[p + 1] = rgba[p + 2] = Math.round(value * 255);
      rgba[p + 3] = 255;
    }
    return { time, descriptor: describeFrame(rgba, 24, 16) };
  });
}
const localPhaseResults = [];
for (const rate of [20, 30]) for (const flipped of [false, true]) {
  const samples = mixedPeriodSamples(rate, 1.8, flipped);
  const globalOnly = findLoop(samples.map(s => ({ time: s.time, descriptor: { values: s.descriptor.values } })), { sampleRate: rate });
  assert.equal(globalOnly.fallback, false, JSON.stringify(globalOnly));
  assert.ok(Math.abs(globalOnly.period - 1) < 0.1, JSON.stringify(globalOnly));
  const guarded = findLoop(samples, { sampleRate: rate });
  assert.equal(guarded.fallback, true, JSON.stringify(guarded));
  assert.equal(guarded.confidence, 'low');
  assert.ok(guarded.bestCandidate.localWindowError > 0.3, JSON.stringify(guarded));
  assert.ok(guarded.bestCandidate.windowError < 0.3, JSON.stringify(guarded));
  const complete = findLoop(mixedPeriodSamples(rate, 5, flipped), { sampleRate: rate });
  assert.equal(complete.fallback, false, JSON.stringify(complete));
  assert.ok(Math.abs(complete.period - 2) < 0.1, JSON.stringify(complete));
  localPhaseResults.push({ rate, flipped, globalPeriod: globalOnly.period, guardedFallback: guarded.fallback, completePeriod: complete.period });
}

// 空间描述子路径也须保留静态、噪声与非周期回退，以及单一局部周期的可检出性。
function withGrid(samples) {
  return samples.map(s => ({ time: s.time, descriptor: {
    cols: 12, rows: 8, values: s.descriptor.values.flatMap(value => [value, value, value])
  } }));
}
for (const samples of [
  samplesFor(() => new Array(N).fill(0.2)),
  samplesFor(() => Array.from({ length: N }, () => 0.5 + (random() - 0.5) * 0.025)),
  samplesFor(t => movingShape(0.3 + 0.55 * t, 0.42 + 0.2 * Math.sin(t * 3)))
]) assert.equal(findLoop(withGrid(samples)).fallback, true);
const spatialCycle = findLoop(withGrid(samplesFor(t => movingShape(0.5 + 0.42 * Math.sin(2 * Math.PI * t), 0.5 + 0.28 * Math.cos(2 * Math.PI * t)))));
assert.equal(spatialCycle.fallback, false, JSON.stringify(spatialCycle));
assert.ok(Math.abs(spatialCycle.period - 1) < 0.14, JSON.stringify(spatialCycle));

console.log(JSON.stringify({
  localPhaseResults,
  static: staticResult.confidence,
  noise: noiseResult.confidence,
  intensityCycle: { start: intensityCycle.start, end: intensityCycle.end, period: intensityCycle.period, confidence: intensityCycle.confidence },
  positionCycle: { start: positionCycle.start, end: positionCycle.end, period: positionCycle.period, confidence: positionCycle.confidence },
  reversal: { start: reversal.start, end: reversal.end, period: reversal.period, confidence: reversal.confidence },
  nonPeriodic: nonPeriodic.confidence
}, null, 2));
