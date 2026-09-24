// 量各状态首/中/末帧的「包围盒尺寸 + 重心」，判断大小与位置是否一致
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const A = path.resolve(__dirname, '..', 'assets');

async function stat(file) {
  if (!fs.existsSync(file)) return null;
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const W = info.width, H = info.height;
  let sx = 0, sy = 0, wsum = 0;
  let minX = W, minY = H, maxX = -1, maxY = -1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const a = data[(y * W + x) * 4 + 3];
      if (a < 128) continue;
      sx += x * a; sy += y * a; wsum += a;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  if (!wsum) return null;
  return { cx: sx / wsum, cy: sy / wsum, bw: maxX - minX, bh: maxY - minY, minX, minY, maxX, maxY, W, H };
}

const pad3 = (n) => String(n).padStart(3, '0');

(async () => {
  const sets = [
    ['闲置', 'extracted_frames', 84],
    ['work_start', 'frames_work_start', 57],
    ['working', 'frames_working', 73],
    ['work_done', 'frames_work_done', 60],
  ];
  const out = {};
  for (const [name, dir, n] of sets) {
    const idx = [0, Math.floor(n / 2), n - 1];
    const rows = [];
    for (const i of idx) {
      const s = await stat(path.join(A, dir, 'frame-' + pad3(i) + '.webp'));
      if (!s) continue;
      rows.push({ i, s });
    }
    if (!rows.length) { console.log('  跳过: ' + name); continue; }
    out[name] = rows;
    console.log('  ' + name + '  (' + n + ' 帧)');
    for (const r of rows) {
      console.log(
        '    帧' + pad3(r.i) +
        '  尺寸 ' + String(r.s.bw).padStart(3) + 'x' + String(r.s.bh).padStart(3) +
        '  重心(' + r.s.cx.toFixed(0) + ',' + r.s.cy.toFixed(0) + ')' +
        '  框 x[' + r.s.minX + '~' + r.s.maxX + '] y[' + r.s.minY + '~' + r.s.maxY + ']'
      );
    }
  }

  const idle = out['闲置'] && out['闲置'][0].s;
  if (!idle) return;
  console.log('\n  === 相对「闲置」基准 ===');
  for (const k of ['work_start', 'working', 'work_done']) {
    const rows = out[k];
    if (!rows) continue;
    const f = rows[0].s, l = rows[rows.length - 1].s;
    console.log('  ' + k);
    console.log(
      '    首帧 宽 ' + (f.bw / idle.bw * 100).toFixed(0) + '%  高 ' + (f.bh / idle.bh * 100).toFixed(0) +
      '%   重心偏移 x' + ((f.cx - idle.cx) / idle.W * 100).toFixed(1) + '% y' + ((f.cy - idle.cy) / idle.H * 100).toFixed(1) + '%'
    );
    console.log(
      '    末帧 宽 ' + (l.bw / idle.bw * 100).toFixed(0) + '%  高 ' + (l.bh / idle.bh * 100).toFixed(0) +
      '%   重心偏移 x' + ((l.cx - idle.cx) / idle.W * 100).toFixed(1) + '% y' + ((l.cy - idle.cy) / idle.H * 100).toFixed(1) + '%'
    );
    const dw = Math.abs(f.bw - l.bw) / Math.max(f.bw, l.bw) * 100;
    const dh = Math.abs(f.bh - l.bh) / Math.max(f.bh, l.bh) * 100;
    console.log('    首末帧尺寸差: 宽 ' + dw.toFixed(1) + '%  高 ' + dh.toFixed(1) + '%' + (dw < 8 && dh < 8 ? '  (基本一致)' : '  (有变化)'));
  }
})();
