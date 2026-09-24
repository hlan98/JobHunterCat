const pet = document.getElementById('pet');
// 2026-09-20 CAT4：启动不闪 —— 首个 petState 到达并「无溶解」应用后，等 Python ready 再显形。
// 旧行为：窗口一加载就画 idle（看鼠标），Python 起来后才交叉溶解成 sleep → 用户看到「闪一下」.
let petRevealed = false;
if (pet && pet.style) pet.style.visibility = 'hidden';
function _revealPet() {
  if (petRevealed) return;
  petRevealed = true;
  if (pet && pet.style) pet.style.visibility = '';
}
setTimeout(_revealPet, 8000);   // 兜底：Python 一直没起来也要显形
const ASSET_VERSION = 'rollback-stable-1';
const stage = document.getElementById('pet-stage');
const status = document.getElementById('status');
const frameCount = 84;
const ANGLE_ANCHORS = [
  { angle: -180, frame: 56 }, { angle: -135, frame: 68 }, { angle: -100, frame: 9 },
  { angle: -94, frame: 9 }, { angle: -86, frame: 9 }, { angle: -78, frame: 9 },
  { angle: -45, frame: 20 }, { angle: 0, frame: 27 },
  { angle: 45, frame: 34 }, { angle: 90, frame: 42 }, { angle: 135, frame: 50 },
  { angle: 180, frame: 56 }
];
const ANGLE_KEYS = ANGLE_ANCHORS.map(({ angle, frame }) => ({ angle, frame }));
const frames = Array.from({ length: frameCount }, (_, i) => {
  const img = new Image();
  img.src = `../assets/extracted_frames/frame-${String(i).padStart(3, '0')}.webp?v=${ASSET_VERSION}`;
  return img;
});

// ---------- 2026-09-20：工作态素材（开始 / 工作中 / 结束）----------
// 素材由 tools/build-state-assets.js 生成：640x640、12fps、黑背景已抠透明。
// work_start / work_done 播一次；working 循环。播完自动衔接（见 renderLoop）。
const STATE_SETS = {
  // v2 素材（2026-09-20）：20fps、内容 80%、抠图加强 —— 帧数比 v1 多一倍，播放更顺
  // ox/oy = 该段素材相对「闲置猫」的位置补偿（%，正=右/下）。
  // 数值来自实测重心（tools/_align2.js）。想微调改这里的 ox/oy 即可，三段互不影响。
  work_start: { dir: 'frames_work_start', count: 57, mode: 'once', next: 'working', ox: 4.6, oy: 5.7 },
  // working 用 **乒乓循环**：正放 → 倒放 → 正放…（用户要求）
  // 素材首尾帧不完全一致，直接 loop 会在接缝处「跳一下」；
  // 乒乓让最后一帧原地折返，视觉上永远连续。
  working:    { dir: 'frames_working',    count: 73, mode: 'pingpong', next: null , ox: 4.6, oy: 5.7 },
  work_done:  { dir: 'frames_work_done',  count: 60, mode: 'once', next: 'idle' , ox: 4.6, oy: 5.7 },
  sleep:      { dir: 'frames_sleep',      count: 46, mode: 'pingpong', next: null, ox: 4.6, oy: 5.7 },
  wake:       { dir: 'frames_wake',       count: 97, mode: 'once',     next: 'idle', ox: 4.6, oy: 5.7 },
};
const STATE_FPS = 20;
// 2026-09-20：工作态素材与「看鼠标」素材的**构图位置对不齐**，切换时猫会跳一下。
// 这里给工作态加一个整体偏移（百分比），让两者叠得上。
// 用户实测反馈「往右下挪一点点」→ 正数 = 右/下。
// 2026-09-20：实测各状态重心相对「闲置」的偏移（见 tools/_align2.js），ox/oy 单位 %，正=右/下。
// 注意 working 的构图是「猫在笔记本后」，整体比闲置**低**，所以 oy 是负的（要往上提）。
// 优先读外部配置 pet_offsets.js（用户可直接改数值，不必改代码），读不到再退回内置默认值
function _offsetTransform(state) {
  const ext = (typeof window !== 'undefined' && window.PET_OFFSETS) ? window.PET_OFFSETS[state] : null;
  const cfg = ext || STATE_SETS[state];
  if (!cfg || cfg.ox === undefined || cfg.oy === undefined) return 'translate(0px, 0px)';
  return 'translate(' + cfg.ox + '%, ' + cfg.oy + '%)';
}
const stateFrames = {};
function loadState(name) {
  const cfg = STATE_SETS[name];
  if (!cfg || stateFrames[name]) return stateFrames[name];
  stateFrames[name] = Array.from({ length: cfg.count }, (_, i) => {
    const img = new Image();
    img.src = `../assets/${cfg.dir}/frame-${String(i).padStart(3, '0')}.webp?v=${ASSET_VERSION}`;
    return img;
  });
  return stateFrames[name];
}
let petState = 'idle';        // idle | work_start | working | work_done
let stateIndex = 0;
let stateLastTick = 0;
// 2026-09-21：删掉了一行孤儿注释——原文写着「进 idle 时若为 true，自动转 sleep」，
// 但它描述的那个变量早已被删除、并没有实现，留着只会误导后来的人。
// （夜间回睡的真实规则见 main.py：sleep 只在启动时发一次，起床后不再自动回睡。）
// 2026-09-20 CAT5：状态切换加淡入淡出 —— 原来的硬切看起来像「啪地换了只猫」
const FADE_MS = 180;
let petFading = false;
function _firstFrameSrc(state) {
  if (state === 'idle') return frames[IDLE_FRAME] ? frames[IDLE_FRAME].src : '';
  const s = stateFrames[state];
  return (s && s[0]) ? s[0].src : '';
}
function _applyState(next) {
  // 进入任何状态（含 idle）都先同步位置偏移，保证与素材构图对齐
  if (pet && pet.style) pet.style.transform = _offsetTransform(next);
  if (next === 'idle') {
    petState = 'idle'; stateIndex = 0; stateDir = 1; return;
  }
  if (!STATE_SETS[next]) return;
  loadState(next);
  petState = next;
  stateIndex = 0;
  stateDir = 1;          // 每次进入新状态都从正放开始
  stateLastTick = performance.now();
}
// 2026-09-20 v3：**真正的交叉溶解（crossfade）**
// v2 用的是「同一个 img 先淡出→换图→淡入」，中间会有一瞬间**猫是空的** ——
// 用户反馈「淡入淡出本身就是在闪」，指的就是这个空档。
// v3 改成两层叠着：旧图一直可见，新图在上层淡入，全程**无空白帧**。
let petGhost = null;
function _ensureGhost() {
  if (petGhost) return petGhost;
  petGhost = document.createElement('img');
  petGhost.id = 'pet-ghost';
  petGhost.alt = '';
  petGhost.draggable = false;
  petGhost.style.position = 'absolute';
  petGhost.style.left = '0';
  petGhost.style.top = '0';
  petGhost.style.width = '100%';
  petGhost.style.height = '100%';
  petGhost.style.objectFit = 'contain';
  petGhost.style.opacity = '0';
  petGhost.style.pointerEvents = 'none';
  petGhost.style.transition = 'opacity ' + FADE_MS + 'ms ease';
  if (pet && pet.parentNode) {
    if (getComputedStyle(pet.parentNode).position === 'static') {
      pet.parentNode.style.position = 'relative';
    }
    pet.parentNode.insertBefore(petGhost, pet.nextSibling);
  }
  return petGhost;
}
function _firstFrameSrcFor(state) {
  if (state === 'idle') return frames[IDLE_FRAME] ? frames[IDLE_FRAME].src : '';
  const s = stateFrames[state];
  return (s && s[0]) ? s[0].src : '';
}
function setPetState(next) {
  // 夜间：起过床就不再睡（直到重启猫）—— 用户规则：只要没关闭猫，起床后一直白天素材
  // 夜间：起过床就不再睡（直到重启猫）。
  // 规则来自用户：只要没关闭猫，起床后一直维持白天素材。
  if (next === petState) return;          // 同状态不重播
  if (next !== 'idle' && !STATE_SETS[next]) return;
  if (!pet || !pet.style) { _applyState(next); return; }
  const begin = () => {
    const g = _ensureGhost();
    const first = _firstFrameSrcFor(next);
    if (!g || !first) { _applyState(next); return; }
    petFading = true;
    g.src = first;
    g.style.transform = _offsetTransform(next);   // 过渡图层也要用同一偏移，否则交叉溶解时会错位
    // 新图从 0 淡到 1 —— 旧图始终在下面可见，所以不会出现空白
    requestAnimationFrame(() => { g.style.opacity = '1'; });
    setTimeout(() => {
      _applyState(next);
      const f2 = _firstFrameSrc(petState);
      if (f2) pet.src = f2;      // 主图直接跳到新状态首帧（与 ghost 同图，看不出变化）
      g.style.opacity = '0';     // ghost 隐去
      petFading = false;
    }, FADE_MS);
  };
  // 预加载目标首帧，加载完再开始溶解
  const probe = (next === 'idle') ? frames[IDLE_FRAME] : (loadState(next) || [])[0];
  if (probe && !probe.complete) {
    let done = false;
    const once = () => { if (!done) { done = true; begin(); } };
    probe.addEventListener('load', once, { once: true });
    probe.addEventListener('error', once, { once: true });
    setTimeout(once, 400);
  } else {
    begin();
  }
}
const IDLE_FRAME = 0;
let currentFrame = IDLE_FRAME;
let targetFrame = IDLE_FRAME;
let locked = false;
let lastCursor = null;
let dragging = false;
let pressState = null;
const idleRadius = 18;
const headAnchor = { x: 0.50, y: 0.31 };

function normalizeAngle(deg) { return ((deg + 180) % 360 + 360) % 360 - 180; }
function frameForAngle(angle) {
  const a = normalizeAngle(angle);
  for (let i = 0; i < ANGLE_KEYS.length - 1; i++) {
    const left = ANGLE_KEYS[i], right = ANGLE_KEYS[i + 1];
    if (a >= left.angle && a <= right.angle) {
      const t = (a - left.angle) / (right.angle - left.angle);
      let frameDelta = right.frame - left.frame;
      if (frameDelta > frameCount / 2) frameDelta -= frameCount;
      if (frameDelta < -frameCount / 2) frameDelta += frameCount;
      return (left.frame + frameDelta * t + frameCount) % frameCount;
    }
  }
  return IDLE_FRAME;
}
function updateFromCursor(screenX, screenY, localX, localY) {
  const x = localX ?? screenX;
  const y = localY ?? screenY;
  const cx = innerWidth * headAnchor.x;
  const cy = innerHeight * headAnchor.y;
  const dx = x - cx, dy = y - cy;
  const distance = Math.hypot(dx, dy);
  if (distance < idleRadius) { targetFrame = IDLE_FRAME; return; }
  targetFrame = frameForAngle(Math.atan2(dy, dx) * 180 / Math.PI);
}
function renderLoop() {
  // v3 交叉溶解：主图**继续渲染**（它在下层可见，动起来更自然）
  // v2 曾在这里 `if (petFading) return;`，导致过渡期间画面冻住 → 观感更硬。
  // 2026-09-20：工作态 —— 按 STATE_FPS 顺序播放帧序列
  if (petState !== 'idle' && STATE_SETS[petState]) {
    const cfg = STATE_SETS[petState];
    const set = stateFrames[petState];
    const now = performance.now();
    if (set && now - stateLastTick >= 1000 / STATE_FPS) {
      stateLastTick = now;
      if (cfg.mode === 'pingpong') {
        // 正放 → 倒放 → 正放…：末帧原地折返，接缝处不跳帧
        stateIndex += stateDir;
        if (stateIndex >= cfg.count) { stateIndex = cfg.count - 2; stateDir = -1; }
        else if (stateIndex < 0) { stateIndex = 1; stateDir = 1; }
      } else if (cfg.mode === 'loop') {
        stateIndex = (stateIndex + 1) % cfg.count;         // 普通循环
      } else {
        stateIndex += 1;                                    // once：播完自动衔接
        if (stateIndex >= cfg.count) {
          // 旧版本：if (petState === 'wake') petWoke = true;  (2026-09-20 移除，改自然循环)
          // 旧版本：if (petState === 'wake') petWoke = true;  (2026-09-20 移除，改自然循环)
          setPetState(cfg.next || 'idle');
        }
      }
    }
    if (set) {
      // 用实际加载到的数组长度兜底，配置 count 与实际帧数不一致时也不会越界
      const idx = Math.max(0, Math.min((set ? set.length : cfg.count) - 1, stateIndex));
      if (set[idx].complete && pet.src !== set[idx].src) pet.src = set[idx].src;
    }
    requestAnimationFrame(renderLoop);
    return;
  }
  let delta = targetFrame - currentFrame;
  if (delta > frameCount / 2) delta -= frameCount;
  if (delta < -frameCount / 2) delta += frameCount;
  // Interpolate on the cyclic frame track so crossing -180/180 remains smooth.
  currentFrame = (currentFrame + delta * 0.22 + frameCount) % frameCount;
  if (Math.abs(targetFrame - currentFrame) < 0.02) currentFrame = targetFrame;
  const index = Math.max(0, Math.min(frameCount - 1, Math.round(currentFrame) % frameCount));
  if (frames[index].complete && pet.src !== frames[index].src) pet.src = frames[index].src;
  requestAnimationFrame(renderLoop);
}
function showStatus(text, duration = 1300) {
  status.textContent = text; status.classList.add('visible');
  if (duration) setTimeout(() => { if (!dragging) status.classList.remove('visible'); }, duration);
}

if (window.petBridge) {
  window.petBridge.onCursor((data) => {
    lastCursor = data;
    if (!dragging) updateFromCursor(data.screenX, data.screenY, data.windowX, data.windowY);
  });
  window.petBridge.onLockState((value) => { locked = value; showStatus(value ? '已锁定 · 鼠标穿透' : '已就绪'); });
} else {
  window.addEventListener('mousemove', (event) => updateFromCursor(event.clientX, event.clientY));
}
stage.addEventListener('mousedown', (event) => {
  // 拖动已禁用（transparent 窗拖动会让窗口越拖越大）。位置用右键菜单"回到右下角"。
  event.preventDefault();
});
stage.addEventListener('dragstart', (event) => event.preventDefault());
stage.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  window.petBridge?.openContextMenu();
});
window.addEventListener('mousemove', (event) => {
  if (!dragging && pressState) {
    if (Math.hypot(event.clientX - pressState.x, event.clientY - pressState.y) < 4) return;
    dragging = true; stage.classList.add('dragging'); status.classList.add('visible'); status.textContent = '拖动中';
    window.petBridge.dragStart({});
  }
  if (!dragging || !window.petBridge) return;
  window.petBridge.dragMove();
});
window.addEventListener('mouseup', () => { pressState = null; if (!dragging) return; dragging = false; stage.classList.remove('dragging'); window.petBridge?.dragEnd(); status.classList.remove('visible'); });

frames[IDLE_FRAME].addEventListener('load', () => { pet.src = frames[IDLE_FRAME].src; });
renderLoop();

// ---- 桥接事件：气泡显示 ----
const bubbleEl = document.getElementById('bubble');
let bubbleTimer = null;
function showBubble(text) {
  if (!bubbleEl || !text) return;
  bubbleEl.textContent = text.length > 24 ? text.slice(0, 24) + '…' : text;
  // 根据文字判断指示灯颜色
  let dot = '#888';
  if (text.includes('分析')) dot = '#f0a03c';
  else if (text.includes('投递') || text.includes('努力')) dot = '#52c41a';
  else if (text.includes('HR') || text.includes('沟通')) dot = '#4a90e2';
  else if (text.includes('停') || text.includes('结束') || text.includes('关掉')) dot = '#e25c5c';
  else if (text.includes('待命')) dot = '#f5d442';
  bubbleEl.style.setProperty('--dot', dot);
  bubbleEl.classList.add('visible');
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => bubbleEl.classList.remove('visible'), 4000);
}
if (window.petBridge) {
  window.petBridge.onPetEvent((msg) => {
    if (msg.type === 'bubble') showBubble(msg.text);
    if (msg.type === 'state') showStatus('状态：' + (msg.state || ''));
    // 2026-09-20：Python 发来的桌宠素材切换（sleep / wake / work_start / working / work_done / idle）
    // 2026-09-20 修复：本 fixer 原版**只插入了注释、漏掉实现行** → Python 明明发了
    //   petState，renderer 却静静丢弃（表现为夜间不睡、工作态不换素材）。
    //   教训：改 fixer 必须回读产物确认代码真的进去了，不能只看 note()。
    if (msg.type === 'petState') {
      // 显形前的首个状态：直接上帧、不做交叉溶解（否则就是「正常态→睡觉」的闪）
      if (!petRevealed) {
        _applyState(msg.state);
        const f = _firstFrameSrc(petState);
        if (f && pet) pet.src = f;
        return;
      }
      setPetState(msg.state);
    }
    // ready 由 pet_bridge.py 在 PetApp 构造完（夜间检查之后）立刻发出 → 此时才显形
    if (msg.type === 'ready') _revealPet();
  });
}

// ---- 拖简历到猫身上 ----
document.addEventListener('dragover', (e) => { e.preventDefault(); });
document.addEventListener('drop', (e) => {
  e.preventDefault();
  try {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    let path = f.path;
    if (!path && window.petBridge && window.petBridge.getPathForFile) {
      try { path = window.petBridge.getPathForFile(f); } catch (_) {}
    }
    if (path) {
      window.petBridge.dropFile(path);
      showBubble('收到简历，开始分析…');
    }
  } catch (err) {}
});
