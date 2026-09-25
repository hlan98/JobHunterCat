const { app, BrowserWindow, Tray, Menu, screen, ipcMain, dialog } = require('electron');

// 2026-09-20 O：单实例锁 —— 防止多次启动导致桌面上出现多个猫窗口
// （用户实测：不锁的话每次启动都多一只猫，旧窗口继续跑旧代码，看起来像叠加）
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    try {
      if (win && !win.isDestroyed()) {
        if (win.isMinimized()) win.restore();
        win.show();
        win.focus();
      }
    } catch {}
  });
}

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// ---------- 路径 ----------
const SRC_DIR = __dirname;
const SHELL_ROOT = path.join(SRC_DIR, '..');
// 2026-09-22 目录重整修复（P0）：
// 原写法 `path.resolve(SHELL_ROOT, '..', 'v8-core')` 指向的是**已不存在的目录** ——
// 迁移时 v8-core/ 被拆为 agent/ + boss/，但这里没同步，
// 导致 spawn 的文件不存在、cwd 也不存在 → **Python 桥接根本起不来，应用完全无法工作**。
// Python 端（main.py / pet_bridge.py）会自己把仓库根算进 sys.path，
// 所以 cwd 用仓库根最稳，与它们保持一致。
const REPO_ROOT = path.resolve(SHELL_ROOT, '..');   // 仓库根
const CORE_DIR = path.join(REPO_ROOT, 'agent');     // 桥接脚本所在目录
const BRIDGE = path.join(CORE_DIR, 'pet_bridge.py');

// 2026-09-22 ICON1：爬爬的猫脸图标
// （由 Desktop\work\make_cat_icon.py 从原图裁出，构建时打进 assets/）
// 托盘 / 聊天框 / 看板三处统一用它 —— 原来 chatWin、dashWin 都没设 icon，
// Windows 上会显示 Electron 默认图标。
const CAT_ICON = path.join(SRC_DIR, '..', 'assets', 'cat-face.png');

// 2026-09-22 DASHFIX1：**模块级**日志助手
// ⚠️ 事故复盘：`_log` 原本只在 openChatWindow / app.whenReady 内部定义为局部 const。
//    在 openDashboardWindow 里直接用它 → ReferenceError: _log is not defined
//    → 点「📊 打开看板」直接抛异常，**看板窗口永远创建不出来**。
//    模块级函数才能被所有窗口创建函数共用；内部 try/catch 保证日志失败不影响功能。
const _logMain = (m) => {
  try {
    fs.appendFileSync(path.join(SHELL_ROOT, 'main-debug.log'),
      new Date().toISOString() + ' ' + m + '\n');
  } catch {}
};

let win = null;        // 猫窗
let chatWin = null;    // 对话框窗
let dashWin = null;    // 看板窗
// 2026-09-21 DASH2：缓存最近一次 progress —— 看板打开时补发，
// 否则"投递中途才打开看板"会看不到任何进度（推送式事件不重放）。
let lastProgress = null;
let lastPetState = null;   // 2026-09-23：最近一次桌宠素材状态，供窗口加载后补发
let tray = null;
let py = null;         // Python 桥接子进程
let locked = false;
let WIN_SIZE = 256;
const chatHistory = [];  // [{role:'cat'|'me'|'log', text:'...'}]，关闭重开时回放
const HISTORY_LIMIT = 200;
let chatCloseBubbleShown = false;  // "对话框关掉啦"气泡每次启动只弹一次

// ---------- Python 桥接 ----------
// 2026-09-20 N3：Python 解释器多候选探测（不写死任何机器专属路径）
function pickPythonExe() {
  if (process.env.MIAO_PYTHON) return process.env.MIAO_PYTHON;
  const found = [];
  // ① PATH
  try {
    const cmd = process.platform === 'win32' ? 'where' : 'which';
    const r = spawnSync(cmd, ['python'], { windowsHide: true });
    if (r && r.status === 0) {
      const p = String(r.stdout || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0];
      if (p) found.push(p);
    }
  } catch {}
  // ② 常见安装目录（通配用 readdir 展开，避免出现机器专属 ID）
  const la = process.env.LOCALAPPDATA || '';
  const bases = [];
  if (la) {
    bases.push({ dir: path.join(la, 'Programs', 'Python'), tail: ['python.exe'] });
    bases.push({ dir: path.join(la, 'Doubao', 'User Data', 'sandbox_runtime', 'bases'),
                 tail: ['python', 'python.exe'] });
  }
  for (const b of bases) {
    try {
      if (!fs.existsSync(b.dir)) continue;
      for (const sub of fs.readdirSync(b.dir)) {
        const cand = path.join(b.dir, sub, ...b.tail);
        if (fs.existsSync(cand)) found.push(cand);
      }
    } catch {}
  }
  found.push('python');   // ④ 最后兜底
  try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'),
    '[pickPython] candidates=' + found.length + ' first=' + found[0] + '\n'); } catch {}
  return found[0];
}

function startBridge() {
  if (py) return;
  const pyExe = pickPythonExe();
  try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), '[spawn] using py=' + pyExe + '\n'); } catch {}
  // 2026-09-20 N2 守卫：pyExe 为空时 spawn 会抛 ERR_INVALID_ARG_VALUE，这里提前拦掉
  if (!pyExe || !String(pyExe).trim()) {
    try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'),
      '[spawn-skip] pyExe 为空，未启动 Python 桥接（请设置环境变量 MIAO_PYTHON 或确保 python 在 PATH 里）\n'); } catch {}
    return;
  }
  const child = spawn(pyExe, ['-u', BRIDGE], {
    cwd: REPO_ROOT,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    windowsHide: true,
  });
  py = child;
  child.on('error', (err) => {
    try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), '[spawn-error] ' + err.message + '\n'); } catch {}
  });

  let buf = '';
  child.stdout.on('data', (d) => {
    buf += d.toString('utf-8');
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (line) forwardToWindows(line);
    }
  });
  child.stderr.on('data', (d) => {
    // 2026-09-25 HANGFIX：**不能无条件 process.stdout.write** ——
    // Node 在 Windows 上「管道」的 stdout 写入是**同步**的；主进程 stdout 无人消费时
    // 缓冲区满会**阻塞 Electron 主进程事件循环** → 整个 app 未响应
    // （用户实测：HR 监听让 Python 狂写 stderr，主进程 ~15:56:16 卡死，Python 却还在跑）。
    // 只在真有控制台（TTY，写入异步、不阻塞）时才镜像到控制台；其余情况只落日志文件。
    try {
      if (process.stdout && process.stdout.isTTY) {
        process.stdout.write('[py-stderr] ' + d.toString('utf-8'));
      }
    } catch (_) {}
    try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), '[stderr] ' + d.toString('utf-8')); } catch {}
  });
  child.on('close', (code) => {
    console.log('[bridge] exited code=' + code);
    try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), '[bridge] exited code=' + code + '\n'); } catch {}
    py = null;
    // 自动重启 Python 桥接
    if (!app.isQuiting) {
      setTimeout(() => { try { startBridge(); } catch (e) {} }, 1500);
    }
  });
}

// Python 事件 -> 各窗口
function forwardToWindows(line) {
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), new Date().toISOString() + ' OUT[' + msg.type + ']: ' + line.slice(0,200) + '\n'); } catch {}
    // 猫窗：state / bubble（气泡）· 2026-09-20 CAT2 加 petState（桌宠工作状态）
    if (win && !win.isDestroyed() && (msg.type === 'state' || msg.type === 'bubble' || msg.type === 'petState' || msg.type === 'ready')) {
      win.webContents.send('pet-event', msg);
  }
  // 对话窗：bubble / log / state / panel / error
  if (chatWin && !chatWin.isDestroyed()) {
    chatWin.webContents.send('pet-event', msg);
  }
  // 追加到对话历史（关闭重开时回放）
  if ((msg.type === 'bubble' || msg.type === 'chat') && msg.text) {
    // 2026-09-21 HIST1：等待类提示（稍等…/正在用 LLM…）不入库，
    // 否则重开窗口会把它当成「猫说过的话」回放出来。
    const _s = String(msg.text).trim();
    const _transient = /稍等/.test(_s)
      || /^找工作喵.*启动/.test(_s)
      || /正在(本地)?\s*识别/.test(_s)
      || /正在用[^a-zA-Z]*LLM/.test(_s)
      || /(正在分析|正在解析|正在生成|正在处理)/.test(_s);
    if (!_transient) chatHistory.push({ role: 'cat', text: String(msg.text) });
  }
  // 2026-09-25 LINKHIST：超链接（如「打开 LLM 设置」）也要入历史，
  // 否则关掉对话窗再打开就没了（用户在新电脑实测踩过）。
  if (msg.type === 'link' && msg.text) {
    chatHistory.push({ role: 'link', text: String(msg.text) });
  }
  if (chatHistory.length > HISTORY_LIMIT) chatHistory.shift();
  // 看板窗：snapshot / plan / config / metrics / state
  // 2026-09-21 DASH2：缓存最近一次进度，供看板打开时回放
  if (msg.type === 'progress') lastProgress = msg;
  if (msg.type === 'petState') lastPetState = msg;   // 2026-09-23：缓存供补发
  if (dashWin && !dashWin.isDestroyed()) {
    dashWin.webContents.send('pet-event', msg);
  }
}

// 发给 Python
function toBridge(obj) {
  // 2026-09-25 HANGFIX：
  // ① 所有发送都留痕 —— 托盘菜单原来**直接调本函数**，绕过了 ipcMain 的 `IN:` 日志，
  //    导致用户点「⏹ 停止」在 bridge-debug.log 里查不到（实测踩过）；
  // ② 加守卫：stdin 不可写时不再硬写（避免 EPIPE / 无谓阻塞）。
  try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), new Date().toISOString() + ' IN: ' + JSON.stringify(obj) + '\n'); } catch {}
  if (!py || !py.stdin || py.stdin.destroyed || !py.stdin.writable) return;
  try {
    py.stdin.write(JSON.stringify(obj) + '\n');
  } catch (e) {
    try { fs.appendFileSync(path.join(SHELL_ROOT, 'bridge-debug.log'), '[toBridge-error] ' + (e && e.message) + '\n'); } catch {}
  }
}

// ---------- 窗口 ----------
function createPetWindow() {
  const display = screen.getPrimaryDisplay();
  const reportedScale = display.scaleFactor || 1;
  const scaleFactor = Math.max(1, Math.min(3, reportedScale));
  const size = Math.round(320 / scaleFactor);
  WIN_SIZE = size;
  const wa = display.workArea;
  win = new BrowserWindow({
    width: size, height: size,
    minWidth: size, maxWidth: size, minHeight: size, maxHeight: size,
    x: wa.x + wa.width - size - 24, y: wa.y + wa.height - size - 18,
    transparent: true, frame: false, resizable: false, alwaysOnTop: true,
    skipTaskbar: true, hasShadow: false,
    webPreferences: { preload: path.join(SRC_DIR, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  win.setResizable(false);
  win.setAlwaysOnTop(true, 'floating');
  win.loadFile(path.join(SRC_DIR, 'index.html'));
  win.webContents.on('did-finish-load', () => {
    win.webContents.send('lock-state', locked);
    // 2026-09-23 PETSTATE-REPLAY：补发最近一次桌宠素材状态 ——
    // 防止「Python 先发了 sleep，但渲染进程当时还没注册监听」导致猫停在默认形态。
    if (lastPetState) win.webContents.send('pet-event', lastPetState);
  });
  win.on('closed', () => { win = null; });
}

function openChatWindow() {
  const _log = (m) => { try { fs.appendFileSync(path.join(SHELL_ROOT, 'main-debug.log'), new Date().toISOString() + ' [chat] ' + m + '\n'); } catch {} };
  try {
    if (chatWin && !chatWin.isDestroyed()) {
      if (chatWin.isMinimized()) chatWin.restore();
      chatWin.show(); chatWin.focus(); chatWin.moveTop();
      return;
    }
    _log('creating chatWin');
    chatWin = new BrowserWindow({
      width: 420, height: 640, minWidth: 360, minHeight: 480,
      x: 80, y: 80,
      title: '找工作喵 · 对话', show: true, alwaysOnTop: false, icon: CAT_ICON,
      webPreferences: { preload: path.join(SRC_DIR, 'chat-preload.js'), contextIsolation: true, nodeIntegration: false },
    });
    chatWin.loadFile(path.join(SRC_DIR, 'chat.html'));
    chatWin.webContents.on('did-finish-load', () => {
      chatWin.show(); chatWin.focus(); chatWin.moveTop();
      // 重放历史消息
      if (chatHistory.length) {
        chatWin.webContents.send('pet-event', { type: 'history', messages: chatHistory.slice() });
      }
    });
    chatWin.webContents.on('did-fail-load', (_e, code, desc) => _log('load fail ' + code + ' ' + desc));
    chatWin.webContents.on('console-message', (_e, level, message) => _log('console: ' + message));
    chatWin.on('closed', () => {
      chatWin = null;
      // 对话框关掉后，给猫弹个气泡提醒怎么再打开（每次启动只弹一次）
      if (!chatCloseBubbleShown && win && !win.isDestroyed()) {
        win.webContents.send('pet-event', { type: 'bubble', text: '📭 对话框关掉啦，右键点我就能再打开～' });
        chatCloseBubbleShown = true;
      }
    });
    _log('chatWin created ok');
  } catch (e) {
    _log('chatWin ERROR: ' + (e && e.stack));
  }
}

function openDashboardWindow(page) {
  if (dashWin && !dashWin.isDestroyed()) {
    if (dashWin.isMinimized()) dashWin.restore();
    dashWin.show(); dashWin.focus(); dashWin.moveTop();
    if (page) dashWin.webContents.send('goto-page', page);
    return;
  }
  dashWin = new BrowserWindow({
    width: 1080, height: 720, minWidth: 900, minHeight: 600,
    title: '找工作喵 · 看板', show: true, icon: CAT_ICON,
    webPreferences: { preload: path.join(SRC_DIR, 'dash-preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  // 2026-09-21 DASH1：看板窗口控制台也接到日志 —— 之前只有 chatWin 接了，
  // 看板里报错完全看不到（排查进度条问题时吃了亏）。
  try {
    dashWin.webContents.on('console-message', (_e, level, message) => _logMain('dash-console: ' + message));
  } catch {}
  _logMain('openDashboardWindow: 创建看板窗口 page=' + (page || '') + '\n');
  // 2026-09-21 DASH2：加载完成后立刻补发最近一次进度 —— 让看板一打开就有数
  dashWin.webContents.once('did-finish-load', () => {
    if (lastProgress && dashWin && !dashWin.isDestroyed()) {
      dashWin.webContents.send('pet-event', lastProgress);
    }
  });
  dashWin.loadFile(path.join(SRC_DIR, 'dash.html'));
  if (page) dashWin.webContents.once('did-finish-load', () => dashWin.webContents.send('goto-page', page));
  dashWin.on('closed', () => { _logMain('openDashboardWindow: 看板窗口已关闭\n'); dashWin = null; });
}

// ---------- 托盘 / 右键 ----------
function refreshTray() {
  if (!tray) return;
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '💬 打开对话框', click: openChatWindow },
    { label: '📊 打开看板', click: () => openDashboardWindow() },
    { type: 'separator' },
    { label: '⏹ 停止', click: () => toBridge({ cmd: 'stop' }) },
    { type: 'separator' },
    { label: '📈 投递进度', click: () => openDashboardWindow('run') },
    { label: '📊 分析报告', click: () => openDashboardWindow('insights') },
    { label: '⚙ LLM 设置', click: () => openDashboardWindow('settings') },
    { type: 'separator' },
    { label: win && win.isVisible() ? '🙈 隐藏猫窗' : '🐱 显示猫窗', click: () => {
        if (!win) return;
        if (win.isVisible()) { win.hide(); } else { win.show(); moveToCorner(); }
        refreshTray();
      } },
    { type: 'separator' },
    { label: '退出', click: () => { app.isQuiting = true; app.quit(); } },
  ]));
}

// 猫窗右键菜单
function showPetContextMenu(e) {
  refreshTray();
  if (tray) tray.popUpContextMenu();
}

function setLocked(value) {
  locked = value;
  if (win) win.setIgnoreMouseEvents(locked, { forward: true });
  if (win) win.webContents.send('lock-state', locked);
  refreshTray();
}

function moveToCorner() {
  if (!win) return;
  const wa = screen.getPrimaryDisplay().workArea;
  const [w, h] = win.getSize();
  win.setPosition(wa.x + wa.width - w - 24, wa.y + wa.height - h - 18);
}

function chooseResumeFile() {
  dialog.showOpenDialog({
    title: '选择简历文件',
    properties: ['openFile'],
    filters: [
      { name: '简历', extensions: ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'doc', 'docx'] },
    ],
  }).then((r) => {
    if (!r.canceled && r.filePaths[0]) {
      toBridge({ cmd: 'resume_file', path: r.filePaths[0] });
    }
  });
}

// ---------- IPC ----------
ipcMain.on('drag-start', () => {});
ipcMain.on('drag-move', () => {});
ipcMain.on('drag-end', () => {});

// 对话窗 / 看板窗 -> Python
ipcMain.on('to-bridge', (_e, obj) => {
  // 2026-09-25 HANGFIX：`IN:` 日志已统一移到 toBridge() 内（托盘菜单也走同一条路），此处不再重复记。
  // 用户发的话也记入历史
  if (obj && obj.cmd === 'user_text' && obj.text) {
    chatHistory.push({ role: 'me', text: String(obj.text) });
    if (chatHistory.length > HISTORY_LIMIT) chatHistory.shift();
  }
  toBridge(obj);
});

// 猫窗右键
ipcMain.on('pet-context-menu', showPetContextMenu);

// 拖简历到猫身上
ipcMain.on('resume-file', (_e, path) => toBridge({ cmd: 'resume_file', path }));

// Dashboard "重新上传简历"按钮 -> 走 Electron 原生文件选择器
ipcMain.on('open_resume_picker', () => chooseResumeFile());
// 聊天框「打开 LLM 设置」超链接 -> 打开看板 LLM 设置页
ipcMain.on('open-llm-settings', () => openDashboardWindow('settings'));

// 鼠标位置轮询（猫头跟随）
function startCursorLoop() {
  setInterval(() => {
    if (!win || win.isDestroyed() || win.webContents.isDestroyed() || win.webContents.isLoading()) return;
    const p = screen.getCursorScreenPoint();
    const [x, y] = win.getPosition();
    win.webContents.send('cursor-position', { screenX: p.x, screenY: p.y, windowX: p.x - x, windowY: p.y - y });
  }, 16);
}

// ---------- 启动 ----------
app.whenReady().then(() => {
  const _log = (m) => { try { fs.appendFileSync(path.join(SHELL_ROOT, 'main-debug.log'), new Date().toISOString() + ' ' + m + '\n'); } catch {} };
  // 2026-09-22 MENU1：去掉 Electron 默认菜单栏
  // （File / Edit / View / Window / Help）。聊天框和看板是带边框的普通窗口，
  // 不设菜单时 Electron 会自动挂上应用菜单，Windows 上很显眼。
  // 一次生效于所有窗口；托盘右键菜单走 tray.setContextMenu，不受影响。
  try { Menu.setApplicationMenu(null); } catch {}
  _log('whenReady');
  createPetWindow();
  _log('petWindow created');
  // 2026-09-22 ICON1：托盘图标换成爬爬的猫脸（原来是通用橘猫 tray.png）
  tray = new Tray(CAT_ICON);
  tray.setToolTip('找工作喵');
  refreshTray();
  startCursorLoop();
  startBridge();
  _log('bridge started');
  openChatWindow();
  _log('chatWindow requested');
});

app.on('window-all-closed', (e) => e.preventDefault());
app.on('before-quit', () => {
  if (py) { try { py.kill(); } catch {} }
  if (tray) tray.destroy();
});
