(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SequenceLoopAnalysis = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  // 小网格保留位置和颜色；透明像素以白底合成，不保存原始视频帧。
  function describeFrame(rgba, width, height) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 ||
        !rgba || rgba.length < width * height * 4) throw new TypeError('需要有效的 RGBA 图像');
    var cols = 24, rows = 16, values = new Array(cols * rows * 3);
    for (var gy = 0; gy < rows; gy++) {
      var y0 = Math.floor(gy * height / rows), y1 = Math.max(y0 + 1, Math.floor((gy + 1) * height / rows));
      for (var gx = 0; gx < cols; gx++) {
        var x0 = Math.floor(gx * width / cols), x1 = Math.max(x0 + 1, Math.floor((gx + 1) * width / cols));
        var r = 0, g = 0, b = 0, count = 0;
        for (var y = y0; y < y1 && y < height; y++) {
          for (var x = x0; x < x1 && x < width; x++) {
            var p = (y * width + x) * 4, a = rgba[p + 3] / 255;
            r += rgba[p] * a + 255 * (1 - a);
            g += rgba[p + 1] * a + 255 * (1 - a);
            b += rgba[p + 2] * a + 255 * (1 - a);
            count++;
          }
        }
        var q = (gy * cols + gx) * 3;
        values[q] = r / (255 * count);
        values[q + 1] = g / (255 * count);
        values[q + 2] = b / (255 * count);
      }
    }
    return { values: values, cols: cols, rows: rows };
  }

  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
  function median(a) {
    var b = a.slice().sort(function (x, y) { return x - y; });
    return b.length ? b[Math.floor(b.length / 2)] : 0;
  }

  // samples 按时间排序并去重。end 是重复姿态的时刻，抽帧应使用 [start, end)。
  // 低可信时返回全片回退区间而非伪装成循环；bestCandidate 仅供诊断。
  function findLoop(samples, options) {
    options = options || {};
    if (!Array.isArray(samples)) return null;
    var input = samples.filter(function (s) {
      var v = s && s.descriptor && (s.descriptor.values || s.descriptor);
      return s && Number.isFinite(s.time) && s.time >= 0 && v && v.length > 0;
    }).slice().sort(function (a, b) { return a.time - b.time; });
    input = input.filter(function (s, i) { return !i || s.time !== input[i - 1].time; });
    if (input.length < 2) return null;
    var n = input.length, vectors = input.map(function (s) { return s.descriptor.values || s.descriptor; });
    var dim = vectors[0].length;
    if (vectors.some(function (v) {
      return v.length !== dim || Array.prototype.some.call(v, function (x) { return !Number.isFinite(x); });
    })) return null;
    var steps = [];
    for (var t = 1; t < n; t++) steps.push(input[t].time - input[t - 1].time);
    var dt = median(steps), rate = Number.isFinite(options.sampleRate) && options.sampleRate > 0 ? options.sampleRate : 1 / dt;
    var duration = Number.isFinite(options.duration) && options.duration >= input[n - 1].time ? options.duration : input[n - 1].time + dt;
    var fallback = function (reason, motion, candidate) {
      return { start: input[0].time, end: duration, confidence: 'low', reason: reason,
        score: candidate ? candidate.score : 0, motion: motion || 0, fallback: true,
        bestCandidate: candidate || null };
    };
    if (n < 8) return fallback('采样不足，无法验证完整周期，保留全片');
    if (Math.max.apply(null, steps) > dt * 1.8 || Math.min.apply(null, steps) < dt * 0.2) {
      return fallback('采样间隔不均匀，无法可靠比较运动方向，保留全片');
    }

    var means = new Float64Array(dim), variances = new Float64Array(dim), weights = new Float64Array(dim);
    for (var k = 0; k < dim; k++) {
      for (t = 0; t < n; t++) means[k] += vectors[t][k] / n;
      for (t = 0; t < n; t++) variances[k] += Math.pow(vectors[t][k] - means[k], 2) / n;
    }
    // 依据全片时间变化抑制大面积静止背景，不逐帧归一化亮度（亮度周期同样是信号）。
    var energy = 0, totalWeight = 0, rawEnergy = 0;
    for (k = 0; k < dim; k++) {
      weights[k] = variances[k] / (variances[k] + 0.0001);
      energy += weights[k] * variances[k];
      totalWeight += weights[k];
      rawEnergy += variances[k] / dim;
    }
    var motion = Math.sqrt(energy / Math.max(totalWeight, 1));
    if (motion < (options.minMotion == null ? 0.006 : options.minMotion) || rawEnergy < 1e-8) {
      return fallback('未检测到明显运动周期（静态或变化过小），保留全片', motion);
    }
    var grid = input[0].descriptor;
    var spatial = Number.isInteger(grid.cols) && grid.cols >= 2 && Number.isInteger(grid.rows) && grid.rows >= 2 &&
      dim === grid.cols * grid.rows * 3 && input.every(function (s) {
        return s.descriptor.cols === grid.cols && s.descriptor.rows === grid.rows;
      });
    var regionOf = spatial ? new Uint8Array(dim) : null;
    var regionEnergy = new Float64Array(4), regionSums = new Float64Array(4);
    if (spatial) {
      // 四象限分别按时间运动能量归一化，避免大面积主体掩盖小区域错相；忽略能量不足全片 1% 的区域。
      for (k = 0; k < dim; k++) {
        var pixel = Math.floor(k / 3);
        var region = (Math.floor(pixel / grid.cols) >= grid.rows / 2 ? 2 : 0) + (pixel % grid.cols >= grid.cols / 2 ? 1 : 0);
        regionOf[k] = region;
        regionEnergy[region] += weights[k] * variances[k];
      }
    }
    var distances = new Float32Array(n * n), localDistances = spatial ? new Float32Array(n * n) : null;
    for (var i = 0; i < n; i++) {
      for (var j = i + 1; j < n; j++) {
        var sum = 0;
        if (spatial) regionSums.fill(0);
        for (k = 0; k < dim; k++) {
          var residual = weights[k] * Math.pow(vectors[i][k] - vectors[j][k], 2);
          sum += residual;
          if (spatial) regionSums[regionOf[k]] += residual;
        }
        distances[i * n + j] = distances[j * n + i] = sum / energy;
        if (spatial) {
          var worst = 0;
          for (var r = 0; r < 4; r++) if (regionEnergy[r] > energy * 0.01) worst = Math.max(worst, regionSums[r] / regionEnergy[r]);
          localDistances[i * n + j] = localDistances[j * n + i] = worst;
        }
      }
    }
    function distance(a, b) { return distances[a * n + b]; }
    function localDistance(a, b) { return localDistances[a * n + b]; }
    var adjacent = [], path = new Float64Array(n), moving = new Uint32Array(n);
    for (i = 1; i < n; i++) {
      adjacent.push(distance(i - 1, i));
      path[i] = path[i - 1] + Math.sqrt(distance(i - 1, i));
      moving[i] = moving[i - 1] + (distance(i - 1, i) > 0.002 ? 1 : 0);
    }
    if (median(adjacent) > 2.5) return fallback('帧间变化缺乏连续性，可能为噪声或采样过稀，保留全片', motion);

    var minPeriod = Number.isFinite(options.minPeriod) && options.minPeriod > 0 ? options.minPeriod : 0.3;
    var maxPeriod = Number.isFinite(options.maxPeriod) && options.maxPeriod > 0 ? options.maxPeriod : duration;
    var candidates = [];
    for (i = 0; i < n - 4; i++) {
      for (j = i + 4; j < n; j++) {
        var period = input[j].time - input[i].time, lag = j - i;
        if (period < minPeriod || period > maxPeriod) continue;
        var endpoint = distance(i, j);
        if (endpoint > 0.65) continue;
        var half = Math.max(2, Math.min(Math.floor(lag * 0.45), Math.round(rate * 0.5)));
        var left = Math.min(half, i), right = Math.min(half, n - j - 1);
        var comparisons = left + right;
        if (comparisons < 3) continue;
        var windowError = 0;
        for (var off = -left; off <= right; off++) if (off) windowError += distance(i + off, j + off) / comparisons;
        if (windowError > 0.65) continue;

        // 同样偏移的前后差分同时比较方向和速度，排除往返轨迹中反向通过的同一姿态。
        var back = Math.min(2, i), ahead = Math.min(2, n - j - 1);
        if (back + ahead === 0) continue;
        var a0 = i - back, a1 = i + ahead, b0 = j - back, b1 = j + ahead;
        var speedA = distance(a0, a1), speedB = distance(b0, b1);
        var dot = (distance(a1, b0) + distance(a0, b1) - distance(a1, b1) - distance(a0, b0)) / 2;
        var direction = speedA * speedB > 1e-8 ? clamp(dot / Math.sqrt(speedA * speedB), -1, 1) : 0;
        var speedRatio = Math.max(speedA, speedB) > 1e-8 ? Math.sqrt(Math.min(speedA, speedB) / Math.max(speedA, speedB)) : 0;
        var velocityError = (1 - direction) / 2 + (1 - speedRatio) / 2;
        var excursion = 0;
        for (var p = i + 1; p < j; p++) excursion = Math.max(excursion, distance(i, p));
        var movingFraction = (moving[j] - moving[i]) / lag;
        if (excursion < 0.35 || movingFraction < 0.4 || path[j] - path[i] < 1.1) continue;
        var localEndpoint = spatial ? localDistance(i, j) : endpoint, localWindow = 0;
        if (spatial) {
          for (off = -left; off <= right; off++) if (off) localWindow += localDistance(i + off, j + off) / comparisons;
        } else localWindow = windowError;
        var coverage = comparisons / lag;
        var score = clamp(1 - (0.28 * endpoint + 0.46 * windowError + 0.26 * velocityError), 0, 1);
        var credible = endpoint < 0.3 && windowError < 0.3 && localEndpoint < 0.3 && localWindow < 0.3 && velocityError < 0.55 && coverage >= 0.3;
        candidates.push({ start: input[i].time, end: input[j].time, score: score,
          period: period, endpointError: endpoint, windowError: windowError,
          localEndpointError: localEndpoint, localWindowError: localWindow,
          direction: direction, speedRatio: speedRatio, velocityError: velocityError,
          motion: motion, excursion: excursion, movingFraction: movingFraction,
          contextCoverage: coverage, credible: credible });
      }
    }
    if (!candidates.length) return fallback('未发现可验证的重复运动，按非周期视频保留全片', motion);
    var valid = candidates.filter(function (c) { return c.credible; });
    candidates.sort(function (a, b) { return b.score - a.score; });
    if (!valid.length) return fallback('相似姿态的运动衔接或上下文不一致，未确认完整周期，保留全片', motion, candidates[0]);

    // 先保留接近最优的可信候选，再选最短周期，避免两周期/三周期谐波。
    valid.sort(function (a, b) { return b.score - a.score; });
    var bestScore = valid[0].score;
    var lagScores = {};
    valid.forEach(function (c) {
      var lag = Math.round(c.period / dt);
      lagScores[lag] = Math.max(lagScores[lag] || 0, c.score);
    });
    var finalists = valid.filter(function (c) {
      var lag = Math.round(c.period / dt);
      return c.score >= bestScore - 0.08 && c.score >= (lagScores[lag - 1] || 0) && c.score >= (lagScores[lag + 1] || 0);
    });
    if (!finalists.length) finalists = [valid[0]];
    var shortest = Math.min.apply(null, finalists.map(function (c) { return c.period; }));
    finalists = finalists.filter(function (c) { return c.period <= shortest + dt * 1.1; });
    finalists.sort(function (a, b) { return b.score - a.score || a.start - b.start; });
    var best = finalists[0];
    var support = 0, supportCount = 0;
    var bestLag = Math.round(best.period / dt);
    for (i = 0; i + bestLag < n; i++) {
      supportCount++;
      if (distance(i, i + bestLag) < 0.3) support++;
    }
    best.recurrenceSupport = support / Math.max(supportCount, 1);
    best.confidence = best.score >= 0.91 && best.windowError < 0.12 && best.velocityError < 0.28 &&
      best.contextCoverage >= 0.6 && best.recurrenceSupport >= 0.65 && n >= bestLag * 1.7 ? 'high' : 'medium';
    best.reason = best.confidence === 'high' ? '完整周期候选：姿态窗口重复且运动方向、速度连续' :
      '局部完整周期候选：已比较相邻姿态与运动衔接，仍需预览确认';
    best.fallback = false;
    delete best.credible;
    return best;
  }

  return { describeFrame: describeFrame, findLoop: findLoop };
});
