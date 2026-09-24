const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const sharp = require('sharp');
const ffmpegPath = require('ffmpeg-static');

const root = path.resolve(__dirname, '..');
// 2026-09-22：这里原先硬编码了一段**他人机器上的**绝对路径（OneDrive 下的微信临时目录），
// 发布到公开仓库等于把别人的目录信息挂出去。现改为必传参数 ——
// 取不到就明确报错，不兜底成别的值（见 AGENTS.md 红线第 4 条）。
const input = process.argv[2];
if (!input) {
  console.error('缺少输入视频。用法：npm run assets -- <视频路径>');
  console.error('示例：npm run assets -- assets/source_video.mp4');
  process.exit(1);
}
const assetRoot = path.join(root, 'assets');
const sourceDir = path.join(assetRoot, 'source_frames');
const frameDir = path.join(assetRoot, 'extracted_frames');

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

// Background removal is deliberately edge-connected: white/grey fur inside the subject is never
// considered background unless it is connected to the image border by the background colour.
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
  const candidate = (p) => {
    const i = p * 4;
    const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
    const brightnessGap = Math.abs(brightness - bgBrightness);
    return dist(i) < 68 && brightnessGap < (bgBrightness < 90 ? 48 : 54);
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
  for (let p = 0; p < width * height; p++) {
    if (!seen[p]) continue;
    const i = p * 4;
    const d = dist(i);
    data[i + 3] = d < 28 ? 0 : Math.min(255, Math.round((d - 28) * 11));
  }
  await sharp(data, { raw: { width, height, channels: 4 } })
    .webp({ quality: 88, alphaQuality: 100, effort: 6 })
    .toFile(outputPath);
}

async function makeContactSheet(files) {
  const cols = 6;
  const thumbW = 220, thumbH = 165, labelH = 26;
  const rows = Math.ceil(files.length / cols);
  const composites = [];
  for (let i = 0; i < files.length; i++) {
    const thumb = await sharp(files[i]).resize(thumbW, thumbH, { fit: 'contain', background: '#20252b' }).png().toBuffer();
    const label = Buffer.from(`<svg width="${thumbW}" height="${labelH}"><rect width="100%" height="100%" fill="#15191f"/><text x="10" y="18" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="14">frame ${String(i).padStart(3, '0')}</text></svg>`);
    composites.push({ input: thumb, left: (i % cols) * thumbW, top: Math.floor(i / cols) * (thumbH + labelH) });
    composites.push({ input: label, left: (i % cols) * thumbW, top: Math.floor(i / cols) * (thumbH + labelH) + thumbH });
  }
  await sharp({ create: { width: cols * thumbW, height: rows * (thumbH + labelH), channels: 4, background: '#20252b' } })
    .composite(composites).png().toFile(path.join(assetRoot, 'contact_sheet.png'));
}

async function makeTrayIcon() {
  const svg = Buffer.from(`<svg width="32" height="32" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#20252b"/><path d="M7 11 10 5l6 4 6-4 3 6v9c0 5-4 8-9 8s-9-3-9-8z" fill="#f6b24a"/><circle cx="13" cy="17" r="2" fill="#20252b"/><circle cx="21" cy="17" r="2" fill="#20252b"/><path d="M14 23q2 2 4 0" fill="none" stroke="#20252b" stroke-width="1.5" stroke-linecap="round"/></svg>`);
  await sharp(svg).png().toFile(path.join(assetRoot, 'tray.png'));
}

async function main() {
  if (!fs.existsSync(input)) throw new Error(`Video not found: ${input}`);
  mkdir(assetRoot); cleanGeneratedFrames(sourceDir); cleanGeneratedFrames(frameDir);
  runFfmpeg(['-y', '-i', input, '-vf', 'fps=12', '-vsync', '0', path.join(sourceDir, 'frame-%03d.png')]);
  const sourceFiles = fs.readdirSync(sourceDir).filter(f => f.endsWith('.png')).sort().map(f => path.join(sourceDir, f));
  if (!sourceFiles.length) throw new Error('No frames extracted');
  await makeContactSheet(sourceFiles);
  await makeTrayIcon();
  for (let i = 0; i < sourceFiles.length; i++) {
    await removeConnectedBackground(sourceFiles[i], path.join(frameDir, `frame-${String(i).padStart(3, '0')}.webp`));
  }
  fs.rmSync(sourceDir, { recursive: true, force: true });
  const meta = await sharp(sourceFiles[0]).metadata();
  const frameCount = sourceFiles.length;
  // Pose landmarks read from contact_sheet.png. The source is a head-sway loop, so these
  // indices intentionally are not evenly distributed frame percentages.
  const anchors = [
    { angle: -180, frame: 56, label: 'left-profile' },
    { angle: -135, frame: 68, label: 'upper-left' },
    { angle: -100, frame: 9, label: 'upper-left-to-top' },
    { angle: -94, frame: 9, label: 'top-stable-left' },
    { angle: -86, frame: 9, label: 'top-stable-right' },
    { angle: -78, frame: 9, label: 'top-to-upper-right' },
    { angle: -45, frame: 20, label: 'upper-right' },
    { angle: 0, frame: 27, label: 'right-facing' },
    { angle: 45, frame: 34, label: 'lower-right' },
    { angle: 90, frame: 42, label: 'downward' },
    { angle: 135, frame: 50, label: 'lower-left' },
    { angle: 180, frame: 56, label: 'left-profile' }
  ];
  fs.writeFileSync(path.join(assetRoot, 'angles.json'), JSON.stringify({
    source: path.basename(input), fps: 12, frameCount, width: meta.width, height: meta.height, frameFormat: 'webp',
    alpha: { method: 'edge-connected chroma matte', sourceHasAlpha: false },
    ANGLE_KEYS: anchors.map(({ angle, frame }) => ({ angle, frame })),
    ANGLE_ANCHORS: anchors,
    angleKeys: anchors.map(({ angle, frame }) => ({ angle, frame })),
    angleAnchors: anchors,
    calibration: 'Review contact_sheet.png and adjust frame indices if the source sequence is non-uniform.'
  }, null, 2));
  console.log(`Generated ${frameCount} frames (${meta.width}x${meta.height})`);
}

main().catch(err => { console.error(err.stack || err); process.exit(1); });
