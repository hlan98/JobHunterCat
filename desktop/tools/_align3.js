// 用「上半身重心」估算对齐偏移：只取每个主体包围盒的上半部分，
// 避免 working 帧里宽而靠下的笔记本把重心拖低。
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const A = path.resolve(__dirname, '..', 'assets');
const pad3 = (n) => String(n).padStart(3, '0');

async function stat(file) {
  if (!fs.existsSync(file)) return null;
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const W = info.width, H = info.height;
  let minY = H, maxY = -1, minX = W, maxX = -1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (data[(y * W + x) * 4 + 3] < 128) continue;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
    }
  }
  if (maxY < 0) return null;
  // 上半身区域 = bbox 的上 50%
  const yEnd = Math.round(minY + (maxY - minY) * 0.5);
  let sx = 0, sy = 0, wsum = 0;
  for (let y = minY; y <= yEnd; y++) {
    for (let x = 0; x < W; x++) {
      const a = data[(y * W + x) * 4 + 3];
      if (a < 128) continue;
      sx += x * a; sy += y * a; wsum += a;
    }
  }
  return {
    minY, maxY, minX, maxX,
    upCx: wsum ? sx / wsum : 0,
    upCy: wsum ? sy / wsum : 0,
    W, H,
  };
}

(async () => {
  const sets = [
    ['闲置', 'extracted_frames', 84, 0],
    ['work_start', 'frames_work_start', 57, 0],
    ['working', 'frames_working', 73, 0],
    ['work_done', 'frames_work_done', 60, 59],   // 末帧（坐姿，回到 idle 前的形态）
  ];
  const res = {};
  for (const [name, dir, n, idx] of sets) {
    const s = await stat(path.join(A, dir, 'frame-' + pad3(idx) + '.webp'));
    if (!s) { console.log('  跳过 ' + name); continue; }
    res[name] = s;
    console.log(
      '  ' + name.padEnd(11) +
      ' 头顶y=' + String(s.minY).padStart(3) +
      '  底y=' + String(s.maxY).padStart(3) +
      '  上半身重心(' + s.upCx.toFixed(0) + ',' + s.upCy.toFixed(0) + ')'
    );
  }
  const b = res['闲置'];
  if (!b) return;
  console.log('\n  相对「闲置」的建议偏移（%，正=右/下）：');
  for (const k of ['work_start', 'working', 'work_done']) {
    const s = res[k];
    if (!s) continue;
    const ox = (b.upCx - s.upCx) / b.W * 100;
    const oy = (b.upCy - s.upCy) / b.H * 100;
    console.log('  ' + k.padEnd(11) + ' ox=' + ox.toFixed(1) + '  oy=' + oy.toFixed(1) +
      '   (头顶对齐需 oy=' + ((b.minY - s.minY) / b.H * 100).toFixed(1) + ')');
  }
})();
