/**
 * 把「笔记本图层」补回干净帧（2026-09-20 v15）
 *
 * 背景：v14 为了清干净绿色，抠得比较狠，笔记本出现破损/半透明。
 *       用户建议：拿一版「有笔记本图层」的图，把笔记本补回去。
 *
 * 思路：
 *   A = 干净帧（sweep 阈值低，绿全清，但笔记本有破损）
 *   B = 保留帧（sweep 阈值高，笔记本完整，但仍带绿）
 *
 *   合成规则：**只在 A 透明、B 不透明、且 B 该像素"不绿"** 时才补 B。
 *   → 补回的是笔记本（灰，greenness≈-1），不会把绿边/绿块也补回来。
 *
 * 用法：node tools/compose-laptop.js <state>
 *   需要 assets/frames_<state>          （A，干净帧）
 *   需要 assets/_B_<state>/             （B，保留帧）
 */
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const root = path.resolve(__dirname, '..');
const state = process.argv[2];
if (!state) { console.error('用法: node tools/compose-laptop.js <state>'); process.exit(1); }

const dirA = path.join(root, 'assets', 'frames_' + state);
const dirB = path.join(root, 'assets', '_B_' + state);
if (!fs.existsSync(dirA) || !fs.existsSync(dirB)) {
  console.error('缺少 A 或 B 目录：' + dirA + ' / ' + dirB);
  process.exit(1);
}

// 只补「明显不绿」的像素：笔记本 gray greenness≈-1，绿块 >30
const GREEN_GUARD = 25;
const A_TRANSPARENT = 8;    // A 透明判定
const B_OPAQUE = 200;       // B 不透明判定

async function compose(file) {
  const pa = path.join(dirA, file);
  const pb = path.join(dirB, file);
  if (!fs.existsSync(pb)) return 0;

  const ia = await sharp(pa).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const ib = await sharp(pb).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const a = ia.data, b = ib.data;
  const n = ia.info.width * ia.info.height;
  let filled = 0;

  for (let p = 0; p < n; p++) {
    const i = p * 4;
    if (a[i + 3] > A_TRANSPARENT) continue;      // A 已经有内容，不动
    if (b[i + 3] < B_OPAQUE) continue;           // B 这里是透明的，没啥可补
    const g = b[i + 1] - Math.max(b[i], b[i + 2]);
    if (g > GREEN_GUARD) continue;               // B 这里是绿的，不补（避免把绿边加回来）
    a[i] = b[i]; a[i + 1] = b[i + 1]; a[i + 2] = b[i + 2]; a[i + 3] = b[i + 3];
    filled++;
  }

  if (filled) {
    await sharp(a, { raw: { width: ia.info.width, height: ia.info.height, channels: 4 } })
      .webp({ quality: 88, alphaQuality: 100, effort: 6 })
      .toFile(pa);
  }
  return filled;
}

(async () => {
  const files = fs.readdirSync(dirA).filter(f => f.endsWith('.webp')).sort();
  let total = 0;
  for (const f of files) total += await compose(f);
  console.log('✅ ' + state + '：补回 ' + total + ' 像素（共 ' + files.length + ' 帧）');
})();
