/**
 * 生成「状态素材」帧序列（2026-09-20，v2）
 *
 * 用法：node tools/build-state-assets.js <video-path> <state>
 *   state: work_start | working | work_done | night ...
 *
 * v2 相对 v1 的四处改进（用户实测反馈）：
 *   ① **内容缩到 80%**（512→pad 到 640）—— 原素材比「看鼠标」的猫大，缩小后更柔和
 *   ② **帧率 12 → 20** —— 原来一卡一卡，帧数不够
 *   ③ **抠图更彻底**：BFS 容差 68→88，并追加「暗色邻接清理」
 *      （反复把贴着透明区的近黑像素也吃掉，专治残留黑块）
 *   ④ 中间帧目录清理更严格
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const sharp = require('sharp');
const ffmpegPath = require('ffmpeg-static');

const root = path.resolve(__dirname, '..');
const input = process.argv[2];
const state = process.argv[3];

if (!input || !state) {
  console.error('用法: node tools/build-state-assets.js <video-path> <state>');
  process.exit(1);
}

const OUT_FPS = 20;        // ① 帧率提高，播放更顺
// 1.0 = 原始尺寸（此时 pad 偏移为 0，ffmpeg 的 pad 等同空操作）
const CONTENT_SCALE = Number(process.env.CAT_CONTENT_SCALE ?? 0.8);
const SIZE = 640;

const assetRoot = path.join(root, 'assets');
const sourceDir = path.join(assetRoot, `source_frames_${state}`);
const frameDir = path.join(assetRoot, `frames_${state}`);

function mkdir(dir) { fs.mkdirSync(dir, { recursive: true }); }
function cleanGeneratedFrames(dir) {
  mkdir(dir);
  for (const file of fs.readdirSync(dir)) {
    if (file.endsWith('.png') || file.endsWith('.webp')) fs.unlinkSync(path.join(dir, file));
  }
}
function runFfmpeg(args) {
  const result = spawnSync(ffmpegPath, args, { stdio: 'inherit', windowsHide: true });
  if (result.status !== 0) throw new Error(`ffmpeg failed with exit code ${result.status}`);
}

/**
 * 抠背景（v2）
 *  · 第一遍：从四边 BFS，容差 88（比 v1 的 68 更敢吃）
 *  · 第二遍：暗色邻接清理 —— 反复扫描，把「贴着透明区 且 很暗」的像素也吃掉，
 *            专治 BFS 没连通的残留黑块（用户反馈的「大面积黑色」）
 *  · 主体是亮橙色猫，亮度门限不会误伤；笔记本等深色内容会被一并清掉
 */
async function removeConnectedBackground(inputPath, outputPath) {
  const image = sharp(inputPath).ensureAlpha();
  const { data, info } = await image.raw().toBuffer({ resolveWithObject: true });
  const width = info.width, height = info.height;
  const corners = [[0, 0], [width - 1, 0], [0, height - 1], [width - 1, height - 1]];
  const sample = corners.map(([x, y]) => {
    const i = (y * width + x) * 4;
    return [data[i], data[i + 1], data[i + 2]];
  });
  const bg = sample.reduce((acc, rgb) => acc.map((v, i) => v + rgb[i]), [0, 0, 0]).map(v => v / sample.length);
  const seen = new Uint8Array(width * height);
  const queue = [];
  let head = 0, tail = 0;
  const dist = (i) => {
    const dr = data[i] - bg[0], dg = data[i + 1] - bg[1], db = data[i + 2] - bg[2];
    return Math.sqrt(dr * dr + dg * dg + db * db);
  };
  const bgBrightness = bg.reduce((a, b) => a + b, 0) / 3;
  const TOL = 88;   // v1 是 68
  // 2026-09-20 v3：**色度键（chroma key）** —— 新素材是绿幕且有亮度渐变，
  // 用「离四角颜色多近」判断会在渐变处停住，留下一大片绿。
  // 改成算「绿色度」= G - max(R,B)，与亮度无关，渐变也能吃干净。
  // 实测：绿幕 greenness≈88~94，笔记本≈-1~12（浅薄荷灰），边缘溢出≈20~80。
  // 阈值 30 太低 → 笔记本被抠穿出洞。改为「全透明 / 半透明」双阈值：
  // 可用环境变量覆盖，方便试验不同力度（如激进版 CAT_GREEN_FULL=8 CAT_GREEN_SOFT=0）
  // 38 会让「毛边（greenness 20~38）」保持**完全不透明** → 看起来就是一圈实心绿，很丑。
  // 下探到 15：毛边进入半透明区间；笔记本 greenness≈12，仍在保护线以下 ✓
  const SWEEP_T = Number(process.env.CAT_FINAL_SWEEP ?? 30);   // 最终扫荡阈值
  const GREEN_FULL = Number(process.env.CAT_GREEN_FULL ?? 70);   // ≥此值：完全透明
  const GREEN_SOFT = Number(process.env.CAT_GREEN_SOFT ?? 38);   // 此值~FULL：渐变半透明
  // <38：保留（猫 + 笔记本）
  const isGreenish = (p) => {
    const i = p * 4;
    return (data[i + 1] - Math.max(data[i], data[i + 2])) > GREEN_SOFT;
  };
  const candidate = (p) => {
    if (isGreenish(p)) return true;              // 绿幕/绿溢出
    const i = p * 4;
    const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
    const brightnessGap = Math.abs(brightness - bgBrightness);
    return dist(i) < TOL && brightnessGap < (bgBrightness < 90 ? 60 : 66);  // 黑幕兜底
  };
  const greennessOf = (p) => {
    const i = p * 4;
    return data[i + 1] - Math.max(data[i], data[i + 2]);
  };
  for (let x = 0; x < width; x++) { queue[tail++] = x; queue[tail++] = (height - 1) * width + x; }
  for (let y = 1; y < height - 1; y++) { queue[tail++] = y * width; queue[tail++] = y * width + width - 1; }
  while (head < tail) {
    const p = queue[head++];
    if (seen[p] || !candidate(p)) continue;
    seen[p] = 1;
    const x = p % width, y = Math.floor(p / width);
    if (x > 0) queue[tail++] = p - 1;
    if (x + 1 < width) queue[tail++] = p + 1;
    if (y > 0) queue[tail++] = p - width;
    if (y + 1 < height) queue[tail++] = p + width;
  }

  // ---- 第二遍：暗色邻接清理 ----
  // 反复扫描：若某像素「很暗」且四邻里有已被判为背景的，就也判为背景。最多 6 轮，避免无限扩散。
  const DARK = 62;
  for (let pass = 0; pass < 6; pass++) {
    let changed = 0;
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const p = y * width + x;
        if (seen[p]) continue;
        const i = p * 4;
        const lum = (data[i] + data[i + 1] + data[i + 2]) / 3;
        if (lum > DARK) continue;
        if (seen[p - 1] || seen[p + 1] || seen[p - width] || seen[p + width]) {
          seen[p] = 1;
          changed++;
        }
      }
    }
    if (!changed) break;
  }

  // 绿色溢出（spill）抑制：只压**明显偏绿**的边缘（>25），
  // 笔记本本身是薄荷绿（greenness≈12），不能压，否则会掉色。
  // ---- 先算出「边缘带」= 背景外扩 N 像素 ----
  // ⚠️ v7 的教训：v7 对所有 g>12 的像素压暗，结果**猫身内部的浅色毛**
  //    （被绿幕反光染上一点绿）也被压暗 → 出现暗斑/马赛克。
  //    正确做法：只处理**紧贴背景**的那一圈，猫身内部一律不碰。
  //    v8 是 3px，但用户实测看到绿色溢出比 3px 宽 → 扩到 6px。
  const NEAR = 6;
  let band = seen;
  for (let pass = 0; pass < NEAR; pass++) {
    const next = new Uint8Array(band);
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const p = y * width + x;
        if (band[p]) continue;
        if (band[p - 1] || band[p + 1] || band[p - width] || band[p + width]) next[p] = 1;
      }
    }
    band = next;
  }

  for (let p = 0; p < width * height; p++) {
    if (seen[p]) continue;
    if (!band[p]) continue;            // ★ 只处理边缘带，猫身内部不动
    const i = p * 4;
    const g = greennessOf(p);
    // 绿边 → 压暗（用户方案）：读起来像柔化边缘/阴影，而不是一圈绿光
    if (g > 12) {
      const k = Number(process.env.CAT_BAND_DIM ?? 0);   // 默认 0=关闭（v7 残留，会误伤笔记本）
      const dim = 1 - k;
      data[i] = Math.round(data[i] * dim);
      data[i + 1] = Math.round(data[i + 1] * dim);
      data[i + 2] = Math.round(data[i + 2] * dim);
    }
  }

  for (let p = 0; p < width * height; p++) {
    if (!seen[p]) continue;
    const i = p * 4;
    const gn = greennessOf(p);
    if (gn >= GREEN_FULL) { data[i + 3] = 0; continue; }              // 绿幕：全透明
    if (gn >= GREEN_SOFT) {                                            // 边缘：立方曲线快速变透明
      const t = (gn - GREEN_SOFT) / (GREEN_FULL - GREEN_SOFT);         // 0→1
      // (1-t)^3 比线性更陡 —— gn 刚过 SOFT 一点就开始大幅透明，毛边不显眼
      data[i + 3] = Math.round(255 * Math.pow(1 - t, 3));
      continue;
    }
    const d = dist(i);
    data[i + 3] = d < 34 ? 0 : Math.min(255, Math.round((d - 34) * 10));  // 黑幕兜底
  }
  // ---- 边缘颜色外扩（v10）：把主体内部颜色向外延伸，覆盖绿边 ----
  // 半透明边缘像素保留的是「被染绿的主体色」，看起来就是一圈绿。
  // 与其压暗/去饱和（都会留痕迹），不如用内部真实毛色向外覆盖 EDGE_EXT 像素。
  const EDGE_EXT = Number(process.env.CAT_EDGE_EXT ?? 7);
  let solid = new Uint8Array(width * height);
  for (let p = 0; p < width * height; p++) if (data[p * 4 + 3] >= 250) solid[p] = 1;
  let frontier = solid;
  for (let pass = 0; pass < EDGE_EXT; pass++) {
    const nextSolid = new Uint8Array(frontier);
    const sR = new Uint8Array(width * height);
    const sG = new Uint8Array(width * height);
    const sB = new Uint8Array(width * height);
    for (let p = 0; p < width * height; p++) { sR[p] = data[p*4]; sG[p] = data[p*4+1]; sB[p] = data[p*4+2]; }
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const p = y * width + x;
        if (frontier[p]) continue;
        if (data[p * 4 + 3] < 8) continue;      // 已是背景，不动
        let r = 0, g = 0, b = 0, n = 0;
        const nb = [p - 1, p + 1, p - width, p + width];
        for (let k = 0; k < 4; k++) {
          const q = nb[k];
          if (frontier[q]) { r += sR[q]; g += sG[q]; b += sB[q]; n++; }
        }
        if (n) {
          data[p * 4]     = Math.round(r / n);
          data[p * 4 + 1] = Math.round(g / n);
          data[p * 4 + 2] = Math.round(b / n);
          nextSolid[p] = 1;
        }
      }
    }
    frontier = nextSolid;
  }

  // ---- 边缘 alpha cap：明显的绿边（gn>25）直接推到 50 以下 ----
  // 颜色外扩已经把边变成中性灰，但半透明叠在浅底上仍有一丝绿感。
  // 这里对明显是绿边的像素再压一次 alpha，让它几乎不可见。
  for (let p = 0; p < width * height; p++) {
    if (seen[p] || !band[p]) continue;
    const i = p * 4;
    const gn = greennessOf(p);
    if (gn > 30 && data[i + 3] > 70) data[i + 3] = 70;
  }

  // ---- 边缘 alpha cap：明显的绿边（gn>25）直接推到 50 以下 ----
  // 颜色外扩已经把边变成中性灰，但半透明叠在浅底上仍有一丝绿感。
  // 这里对明显是绿边的像素再压一次 alpha，让它几乎不可见。
  for (let p = 0; p < width * height; p++) {
    if (seen[p] || !band[p]) continue;
    const i = p * 4;
    const gn = greennessOf(p);
    if (gn > 30 && data[i + 3] > 70) data[i + 3] = 70;
  }

  // ---- 最终扫荡：抓被猫/电脑围住的孤立绿点（v13 漏的）----
  // 之前的 band 只扩 6px，猫脚之间的小绿块可能落在带外。
  // 这里扫一遍：任何不透明且 gn>30 的像素强制透明。
  // 笔记本 gn=-1，绿幕 gn=200+，30 这个阈值对它们都安全。
  for (let p = 0; p < width * height; p++) {
    if (data[p * 4 + 3] < 8) continue;
    const i = p * 4;
    const g = data[i + 1] - Math.max(data[i], data[i + 2]);
    if (g > SWEEP_T) data[i + 3] = 0;   // alpha 通道是 i+3（i+4 是下一像素的 R，之前写错了）
  }

  // ---- 最终扫荡：抓被猫/电脑围住的孤立绿点（v13 漏的）----
  // 之前的 band 只扩 6px，猫脚之间的小绿块可能落在带外。
  // 这里扫一遍：任何不透明且 gn>30 的像素强制透明。
  // 笔记本 gn=-1，绿幕 gn=200+，30 这个阈值对它们都安全。
  for (let p = 0; p < width * height; p++) {
    if (data[p * 4 + 3] < 8) continue;
    const i = p * 4;
    const g = data[i + 1] - Math.max(data[i], data[i + 2]);
    if (g > 30) data[i + 3] = 0;   // alpha 通道是 i+3（i+4 是下一像素的 R，之前写错了）
  }

  await sharp(data, { raw: { width, height, channels: 4 } })
    .webp({ quality: 88, alphaQuality: 100, effort: 6 })
    .toFile(outputPath);
}

async function main() {
  if (!fs.existsSync(input)) throw new Error(`Video not found: ${input}`);
  mkdir(assetRoot); cleanGeneratedFrames(sourceDir); cleanGeneratedFrames(frameDir);
  const inner = Math.round(SIZE * CONTENT_SCALE);
  const pad = Math.round((SIZE - inner) / 2);
  // 先缩放内容到 80%，再用黑色补齐到 640×640（黑边会被抠图吃掉，等效于「整体缩小」）
  runFfmpeg([
    '-y', '-i', input,
    '-vf', `fps=${OUT_FPS},scale=${inner}:${inner},pad=${SIZE}:${SIZE}:${pad}:${pad}:color=black`,
    '-vsync', '0',
    path.join(sourceDir, 'frame-%03d.png'),
  ]);
  const sourceFiles = fs.readdirSync(sourceDir).filter(f => f.endsWith('.png')).sort()
    .map(f => path.join(sourceDir, f));
  if (!sourceFiles.length) throw new Error('No frames extracted');
  for (let i = 0; i < sourceFiles.length; i++) {
    await removeConnectedBackground(sourceFiles[i], path.join(frameDir, `frame-${String(i).padStart(3, '0')}.webp`));
  }
  for (const f of fs.readdirSync(sourceDir)) fs.unlinkSync(path.join(sourceDir, f));
  fs.rmdirSync(sourceDir);
  const meta = {
    source: path.basename(input),
    state,
    fps: OUT_FPS,
    frameCount: sourceFiles.length,
    width: SIZE,
    height: SIZE,
    contentScale: CONTENT_SCALE,
    mode: 'loop',
    alpha: { method: 'edge-connected chroma matte + dark-adjacency cleanup', sourceHasAlpha: false },
  };
  fs.writeFileSync(path.join(assetRoot, `angles_${state}.json`), JSON.stringify(meta, null, 2));
  console.log(`✅ ${state}: ${sourceFiles.length} 帧 @${OUT_FPS}fps, 内容 ${CONTENT_SCALE * 100}%`);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
