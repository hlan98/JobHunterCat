// 量两套素材的「猫的重心 / 包围盒」，判断位置差多少
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

// 2026-09-22：这里原先硬编码了工作副本的绝对路径，发布后会公开本机目录结构与用户名。
// 改为可传参，默认用本仓库的 desktop/assets（实测帧目录都在这里，可直接跑）。
const A = process.argv[2] || path.resolve(__dirname, '..', 'assets');

async function stat(file) {
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
  return {
    cx: sx / wsum, cy: sy / wsum,
    minX, minY, maxX, maxY,
    bw: maxX - minX, bh: maxY - minY,
    W, H,
  };
}

(async () => {
  const targets = [
    ['闲置(看鼠标)', path.join(A, 'extracted_frames/frame-000.webp')],
    ['work_start  ', path.join(A, 'frames_work_start/frame-000.webp')],
    ['working     ', path.join(A, 'frames_working/frame-000.webp')],
    ['work_done   ', path.join(A, 'frames_work_done/frame-000.webp')],
  ];
  const res = {};
  for (const [name, f] of targets) {
    if (!fs.existsSync(f)) { console.log('  跳过（不存在）: ' + name); continue; }
    const s = await stat(f);
    res[name.trim()] = s;
    console.log(
      '  ' + name +
      ' 重心(' + s.cx.toFixed(0) + ',' + s.cy.toFixed(0) + ')' +
      '  包围盒 x[' + s.minX + '~' + s.maxX + '] y[' + s.minY + '~' + s.maxY + ']' +
      '  尺寸 ' + s.bw + 'x' + s.bh
    );
  }
  const base = res['闲置(看鼠标)'];
  if (!base) { console.log('  没有基准，无法比较'); return; }
  console.log('\n  相对「闲置」的偏差（正数=工作态更靠右/下）：');
  for (const k of ['work_start', 'working', 'work_done']) {
    const s = res[k];
    if (!s) continue;
    const dx = s.cx - base.cx, dy = s.cy - base.cy;
    console.log(
      '  ' + k.padEnd(11) +
      ' Δ重心 x=' + dx.toFixed(1) + 'px (' + (dx / base.W * 100).toFixed(1) + '%)' +
      '  y=' + dy.toFixed(1) + 'px (' + (dy / base.H * 100).toFixed(1) + '%)'
    );
  }
})();
