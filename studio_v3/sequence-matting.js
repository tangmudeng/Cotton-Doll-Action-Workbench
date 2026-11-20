(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SequenceMatting = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const number = (v, fallback) => Number.isFinite(Number(v)) ? Number(v) : fallback;
  const rms = (r, g, b) => Math.sqrt((r * r + g * g + b * b) / 3);
  function validate(data, width, height) {
    if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1 ||
        !Number.isSafeInteger(width * height) || !data || data.length !== width * height * 4) {
      throw new RangeError('RGBA长度必须与正整数宽高一致');
    }
  }
  function borderPixels(data, width, height) {
    const pixels = [];
    const add = p => { if (data[p * 4 + 3] >= 200) pixels.push(p); };
    for (let x = 0; x < width; x++) { add(x); if (height > 1) add((height - 1) * width + x); }
    for (let y = 1; y < height - 1; y++) { add(y * width); if (width > 1) add(y * width + width - 1); }
    return pixels;
  }
  function sampleBackground(data, width, height) {
    validate(data, width, height);
    const pixels = borderPixels(data, width, height), histogram = new Map();
    let winner = 0, maxCount = 0;
    for (const p of pixels) {
      const i = p * 4, color = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
      const count = (histogram.get(color) || 0) + 1;
      histogram.set(color, count);
      if (count > maxCount) { winner = color; maxCount = count; }
    }
    if (pixels.length && maxCount / pixels.length < 0.2) {
      // 噪声背景的精确RGB各只出现几次时，不能让一小段平坦前景抢占主簇。
      const coarse = new Map();
      for (const p of pixels) {
        const i = p * 4, cell = [data[i] >> 4, data[i + 1] >> 4, data[i + 2] >> 4];
        const id = (cell[0] << 8) | (cell[1] << 4) | cell[2];
        const value = coarse.get(id) || { cell, count: 0 };
        value.count++; coarse.set(id, value);
      }
      let bestCount = 0, bestCell;
      for (const value of coarse.values()) {
        let count = 0;
        for (let r = -1; r <= 1; r++) for (let g = -1; g <= 1; g++) for (let b = -1; b <= 1; b++) {
          const rr = value.cell[0] + r, gg = value.cell[1] + g, bb = value.cell[2] + b;
          if (rr < 0 || rr > 15 || gg < 0 || gg > 15 || bb < 0 || bb > 15) continue;
          count += coarse.get((rr << 8) | (gg << 4) | bb)?.count || 0;
        }
        if (count > bestCount) { bestCount = count; bestCell = value.cell; }
      }
      let r = 0, g = 0, b = 0, count = 0;
      for (const p of pixels) {
        const i = p * 4;
        if (Math.abs((data[i] >> 4) - bestCell[0]) <= 1 && Math.abs((data[i + 1] >> 4) - bestCell[1]) <= 1 && Math.abs((data[i + 2] >> 4) - bestCell[2]) <= 1) {
          r += data[i]; g += data[i + 1]; b += data[i + 2]; count++;
        }
      }
      let nearest = Infinity;
      for (const color of histogram.keys()) {
        const d = rms(((color >>> 16) & 255) - r / count, ((color >>> 8) & 255) - g / count, (color & 255) - b / count);
        if (d < nearest) { nearest = d; winner = color; }
      }
    }
    const mode = [(winner >>> 16) & 255, (winner >>> 8) & 255, winner & 255];
    if (!pixels.length) return { key: [0, 255, 0], color: [0, 255, 0], mode: [0, 255, 0], samples: 0, count: 0, coverage: 0, noise: 0, p95: 0, confidence: 0 };
    // 分簇只用于选成员；最终背景色始终由原始字节求均值，不用量化色格中心。
    const members = [];
    let r = 0, g = 0, b = 0;
    for (const p of pixels) {
      const i = p * 4;
      if (rms(data[i] - mode[0], data[i + 1] - mode[1], data[i + 2] - mode[2]) <= 12) {
        members.push(p); r += data[i]; g += data[i + 1]; b += data[i + 2];
      }
    }
    const key = [r / members.length, g / members.length, b / members.length], distances = [];
    let variance = 0;
    for (const p of members) {
      const i = p * 4, d = rms(data[i] - key[0], data[i + 1] - key[1], data[i + 2] - key[2]);
      distances.push(d); variance += d * d;
    }
    distances.sort((a, b) => a - b);
    const coverage = members.length / pixels.length;
    return { key, color: key.slice(), mode, samples: pixels.length, count: members.length, coverage,
      noise: Math.sqrt(variance / members.length), p95: distances[Math.floor((distances.length - 1) * 0.95)], confidence: coverage };
  }
  function keyImage(data, width, height, options) {
    validate(data, width, height);
    options = options || {};
    const started = Date.now(), sample = sampleBackground(data, width, height);
    const key = options.key === undefined ? sample.key : options.key;
    if (!key || key.length !== 3 || !Array.from(key).every(v => Number.isFinite(v) && v >= 0 && v <= 255)) {
      throw new RangeError('背景色必须是0至255的三个有限RGB数值');
    }
    const n = width * height, tolerance = clamp(number(options.tolerance, 9), 0, 255);
    const feather = options.smooth === false ? 0 : clamp(number(options.feather, 10), 0, 30);
    const spill = clamp(number(options.spill, 0.32), 0, 1);
    const edgeClean = options.smooth === false ? 0 : clamp(number(options.edgeClean, 1), 0, 3);
    // 独立可选收边，强度1最多移动0.75像素；默认关闭以保留已知抗锯齿语义。
    const edgeChoke = options.smooth === false ? 0 : clamp(number(options.edgeChoke, 0), 0, 1);
    const keyOffset = rms(key[0] - sample.key[0], key[1] - sample.key[1], key[2] - sample.key[2]);
    const matchingBorder = sample.samples > 0 && keyOffset < 12 && sample.coverage > 0.5;
    const noise = matchingBorder ? Math.min(6, sample.noise) : 0;
    const safetyLimit = matchingBorder ? clamp(sample.p95 + 8, 12, 28) : 28;
    const effectiveTolerance = Math.min(tolerance, safetyLimit);
    const threshold = Math.max(effectiveTolerance, matchingBorder ? Math.min(12, sample.p95 + 1) : 0);
    const distance = new Float32Array(n), background = new Uint8Array(n), queue = new Int32Array(n);
    const original = new Uint8ClampedArray(data);
    let tail = 0;
    for (let p = 0; p < n; p++) {
      const i = p * 4;
      distance[p] = rms(original[i] - key[0], original[i + 1] - key[1], original[i + 2] - key[2]);
    }
    const seed = p => {
      if (!background[p] && (distance[p] <= threshold || original[p * 4 + 3] === 0)) {
        background[p] = 1; queue[tail++] = p;
      }
    };
    for (let x = 0; x < width; x++) { seed(x); seed((height - 1) * width + x); }
    for (let y = 1; y < height - 1; y++) { seed(y * width); seed(y * width + width - 1); }
    // 四连通不会经对角线越过一像素描线，队列与每个距离场均为线性复杂度。
    for (let head = 0; head < tail; head++) {
      const p = queue[head], x = p % width;
      if (x) seed(p - 1);
      if (x + 1 < width) seed(p + 1);
      if (p >= width) seed(p - width);
      if (p + width < n) seed(p + width);
    }
    const backgroundCount = tail, band = Math.min(5, 1 + Math.ceil(feather / 15) + Math.ceil(edgeClean));
    const depth = new Uint8Array(n);
    // 两侧有界轮廓带。背景主区直接清空，内部同色区域不参与按色删除。
    tail = 0;
    for (let p = 0; p < n; p++) {
      const x = p % width;
      if ((x && background[p] !== background[p - 1]) || (p >= width && background[p] !== background[p - width]) ||
          (x + 1 < width && background[p] !== background[p + 1]) || (p + width < n && background[p] !== background[p + width])) {
        depth[p] = 1; queue[tail++] = p;
      }
    }
    const extend = (p, d, side) => {
      if (!depth[p] && background[p] === side) { depth[p] = d; queue[tail++] = p; }
    };
    for (let head = 0; head < tail; head++) {
      const p = queue[head], d = depth[p] + 1, x = p % width;
      if (d > band) continue;
      if (x) extend(p - 1, d, background[p]);
      if (x + 1 < width) extend(p + 1, d, background[p]);
      if (p >= width) extend(p - width, d, background[p]);
      if (p + width < n) extend(p + width, d, background[p]);
    }
    let cleared = 0, fractional = 0, unmixed = 0, protectedInterior = 0, edgeCleaned = 0, contourUnmixed = 0;
    const cleanStrength = Math.min(1, edgeClean), cleanResidual = 2.5 + edgeClean * 2.5;
    const contourUnmixStrength = clamp((edgeClean - 1) / 2, 0, 1);
    const whiteKey = Math.min(...key) >= 235 && Math.max(...key) - Math.min(...key) <= 8;
    const directions = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]];
    const reach = Math.min(8, band + 3), zeroNoise = Math.max(0.75, noise * 0.9);
    for (let p = 0; p < n; p++) {
      const i = p * 4, oldAlpha = original[i + 3];
      if (!oldAlpha) continue;
      let alpha = background[p] ? 0 : 1;
      if (!background[p] && distance[p] <= threshold) protectedInterior++;
      if (depth[p] && distance[p] > zeroNoise && (feather || edgeClean)) {
        const x = p % width, y = Math.floor(p / width);
        const cr = original[i] - key[0], cg = original[i + 1] - key[1], cb = original[i + 2] - key[2];
        let best = Infinity, solved = 1, found = false, cleanBest = Infinity, cleanSolved = 1;
        let contourNorm = 0, contourSolved = 1;
        // 固定8条射线、最多8步，不随羽化滑块形成O(N*r*r)大核扫描。
        for (const direction of directions) {
          for (let step = 1; step <= reach; step++) {
            const xx = x + direction[0] * step, yy = y + direction[1] * step;
            if (xx < 0 || yy < 0 || xx >= width || yy >= height) break;
            const q = yy * width + xx;
            // 轮廓取色不能穿过背景，再借用另一侧头发或肢体的颜色端点。
            if (!background[p] && background[q]) break;
            if (background[q] || (depth[q] && depth[q] < 2) || original[q * 4 + 3] < 200) continue;
            const j = q * 4, fr = original[j] - key[0], fg = original[j + 1] - key[1], fb = original[j + 2] - key[2];
            const norm = fr * fr + fg * fg + fb * fb;
            if (norm < Math.max(18, threshold * 1.5) ** 2 * 3) continue;
            const a = (cr * fr + cg * fg + cb * fb) / norm;
            if (a <= 0 || a > 1.015) continue;
            const residual = rms(cr - a * fr, cg - a * fg, cb - a * fb);
            const score = residual + step * 0.16 + a * 0.12;
            if (residual <= Math.max(2.5, noise * 1.8) && score < best) {
              best = score; solved = clamp(a, 0, 1); found = true;
            }
            // 2/3档仅对白底外轮廓补充解混：深处连续稳定端点优先于浅层白污染端点。
            if (whiteKey && contourUnmixStrength && !background[p] && depth[p] <= 2 && (!depth[q] || depth[q] >= 3) && oldAlpha === 255 && original[j + 3] === 255 && a > 0.08 && a < 0.985 && residual <= Math.max(6, noise * 2.5)) {
              const xx2 = xx + direction[0], yy2 = yy + direction[1];
              if (xx2 >= 0 && yy2 >= 0 && xx2 < width && yy2 < height) {
                const q2 = yy2 * width + xx2, j2 = q2 * 4;
                if (!background[q2] && (!depth[q2] || depth[q2] >= 3) && original[j2 + 3] === 255) {
                  const stable = rms(original[j] - original[j2], original[j + 1] - original[j2 + 1], original[j + 2] - original[j2 + 2]);
                  if (stable <= 8 && norm > contourNorm) { contourNorm = norm; contourSolved = clamp(a, 0, 1); }
                }
              }
            }
            // 只从轮廓更深处取色，避免将另一层白底混色当成实色端点。
            // 相邻两层颜色稳定才可信，尖角、纹理和浅色饰边不强制向深色收缩。
            if (edgeClean && !background[p] && depth[p] <= 2 && (!depth[q] || depth[q] >= 3) &&
                a < 0.985 && residual <= Math.max(cleanResidual, noise * 1.8)) {
              const xx2 = xx + direction[0], yy2 = yy + direction[1];
              if (xx2 < 0 || yy2 < 0 || xx2 >= width || yy2 >= height) continue;
              const q2 = yy2 * width + xx2, j2 = q2 * 4;
              if (background[q2] || (depth[q2] && depth[q2] < depth[q]) || original[j2 + 3] < 200) continue;
              const stable = rms(original[j] - original[j2], original[j + 1] - original[j2 + 1], original[j + 2] - original[j2 + 2]);
              if (stable > 8) continue;
              const cleanScore = residual + stable * 0.15 + step * 0.1;
              if (cleanScore < cleanBest) { cleanBest = cleanScore; cleanSolved = clamp(a, 0, 1); }
            }
          }
        }
        if (found && solved < 0.985) {
          // 仅背景侧和轮廓最外两层解混，避免把不透明亮色内部当成半透明。
          if (background[p] || depth[p] <= Math.min(2, band)) alpha = solved;
        }
        if (cleanBest < Infinity && cleanSolved < alpha) {
          alpha += (cleanSolved - alpha) * cleanStrength;
          edgeCleaned++;
        }
        if (contourNorm && contourSolved < alpha) {
          alpha += (contourSolved - alpha) * contourUnmixStrength;
          contourUnmixed++;
        }
        if (!found && !background[p] && depth[p] <= 2 && feather && distance[p] < threshold + feather) {
          // 只柔化轮廓最外侧颜色线不稳定的像素；清边不能反而抬高已有柔化alpha。
          alpha = Math.min(alpha, clamp((distance[p] - threshold) / feather, 0, 1));
        }
      }
      // 已由边界连通确认的近背景噪点，不应因射线匹配重新长出白色毛刺。
      // 关闭清边时仍保留原先的低覆盖抗锯齿恢复，默认强度只清除此低可信背景侧。
      if (background[p] && alpha > 0 && cleanStrength) {
        alpha *= 1 - cleanStrength;
        edgeCleaned++;
      }
      data[i + 3] = Math.min(oldAlpha, Math.round(oldAlpha * alpha));
      if (!data[i + 3]) { data[i] = data[i + 1] = data[i + 2] = 0; cleared++; continue; }
      if (alpha < 1) {
        fractional++;
        for (let c = 0; c < 3; c++) data[i + c] = clamp((original[i + c] - (1 - alpha) * key[c]) / alpha, 0, 255);
        unmixed++;
        // 解混已经去掉中性白灰污染；spill只补偿有色背景的额外通道溢色。
        const max = Math.max(...key), min = Math.min(...key), dominant = key.indexOf(max);
        if (spill && max - min > 40) {
          const other = Math.max(data[i + (dominant + 1) % 3], data[i + (dominant + 2) % 3]);
          const excess = Math.max(0, data[i + dominant] - other);
          data[i + dominant] -= excess * spill * (1 - alpha);
        }
      }
    }
    let edgeChoked = 0;
    if (edgeChoke) {
      const alpha = new Uint8Array(n);
      for (let p = 0; p < n; p++) alpha[p] = data[p * 4 + 3];
      for (let p = 0; p < n; p++) {
        if (background[p] || !depth[p] || depth[p] > 2 || !alpha[p]) continue;
        const x = p % width, y = Math.floor(p / width);
        let slope = 0, supported = false;
        for (const [dx, dy] of directions) {
          const xx = x + dx, yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= width || yy >= height) continue;
          const q = yy * width + xx;
          if (!background[q] && (!depth[q] || depth[q] > depth[p]) && alpha[q] >= alpha[p]) supported = true;
          slope = Math.max(slope, (alpha[p] - alpha[q]) / Math.hypot(dx, dy));
        }
        // 从快照采样，避免级联侵蚀；只减外轮廓alpha，细孤线、内部RGB及封闭白孔保持原样。
        if (!supported || !slope) continue;
        const i = p * 4;
        data[i + 3] = Math.max(0, Math.round(alpha[p] - 0.75 * edgeChoke * slope));
        if (data[i + 3] < alpha[p]) edgeChoked++;
      }
    }
    return { key: Array.from(key), sample, tolerance, effectiveTolerance, threshold,
      toleranceLimited: tolerance > effectiveTolerance, backgroundCount, cleared, fractional, unmixed,
      protectedInterior, edgeCleaned, contourUnmixed, edgeClean, edgeChoke, edgeChoked, band, elapsedMs: Date.now() - started,
      warnings: [ ...(tolerance > effectiveTolerance ? ['容差已安全限制，避免连通背景吞噬浅色前景。'] : []),
        '与背景完全同色且相连的前景、完全封闭的同色孔洞及烘焙阴影，单帧纯色抠图无法可靠区分。' ] };
  }
  return { sampleBackground, keyImage };
});
