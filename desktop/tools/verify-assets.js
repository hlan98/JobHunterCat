const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const root = path.resolve(__dirname, '..');
const assetRoot = path.join(root, 'assets');
const meta = JSON.parse(fs.readFileSync(path.join(assetRoot, 'angles.json'), 'utf8'));
  const frames = fs.readdirSync(path.join(assetRoot, 'extracted_frames')).filter(f => f.endsWith('.webp')).sort();

async function main() {
  if (!fs.existsSync(path.join(assetRoot, 'contact_sheet.png'))) throw new Error('contact_sheet.png missing');
  if (fs.existsSync(path.join(assetRoot, 'source_frames'))) throw new Error('source_frames intermediate directory should be removed');
  if (frames.length !== meta.frameCount) throw new Error(`Expected ${meta.frameCount} transparent frames, found ${frames.length}`);
  const first = await sharp(path.join(assetRoot, 'extracted_frames', frames[0])).metadata();
  if (!first.hasAlpha) throw new Error('Frames do not contain alpha');
  const probe = await sharp(path.join(assetRoot, 'extracted_frames', frames[Math.floor(frames.length / 2)])).raw().toBuffer({ resolveWithObject: true });
  let transparent = 0, opaque = 0;
  for (let i = 3; i < probe.data.length; i += probe.info.channels) {
    if (probe.data[i] === 0) transparent++; else if (probe.data[i] > 240) opaque++;
  }
  if (!transparent || !opaque) throw new Error('Alpha matte probe is invalid');
  const keys = meta.ANGLE_KEYS || meta.angleKeys;
  const validAngles = keys.every((key, i, a) =>
    key.angle >= -180 && key.angle <= 180 && key.frame >= 0 && key.frame < meta.frameCount &&
    (i === 0 || key.angle > a[i - 1].angle));
  if (!validAngles) throw new Error('ANGLE_KEYS angles/frames are invalid');
  console.log(JSON.stringify({
    ok: true, contactSheet: path.join(assetRoot, 'contact_sheet.png'), frames: frames.length,
    dimensions: `${first.width}x${first.height}`, alphaPixelsInProbe: transparent,
    opaquePixelsInProbe: opaque, angleKeys: keys
  }, null, 2));
}
main().catch((err) => { console.error(err.message); process.exit(1); });
