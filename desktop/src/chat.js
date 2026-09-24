const msgs = document.getElementById('msgs');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const stateEl = document.getElementById('state');
const dot = document.getElementById('dot');

function scrollBottom(){ msgs.scrollTop = msgs.scrollHeight; }
function addMsg(text, cls, instant) {
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  // 转义 HTML 后，把"回复 OK"中的 OK 标红（每帧都在当前子串上重算）
  const render = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')   // 2026-09-23 MDBOLD：星号转粗体
    .replace(/回复\s*OK/g, '回复 <span style="color:#e74c3c;font-weight:700;">OK</span>')
    .replace(/说「?OK」?/g, '说「<span style="color:#e74c3c;font-weight:700;">OK</span>」');
  msgs.appendChild(el);
  // 2026-09-21 TYPE1：只有「猫的话」逐字呈现；
  // 自己发的 / 日志 / 历史回放 一律直接显示（回放不该慢慢敲几十条历史）。
  if (instant || cls !== 'cat') {
    el.innerHTML = render(text);
    scrollBottom();
    return el;
  }
  const step = Math.max(1, Math.ceil(text.length / 220));   // 长消息也不至于太慢
  let i = 0;
  el.innerHTML = '';
  const timer = setInterval(() => {
    i = Math.min(text.length, i + step);
    el.innerHTML = render(text.slice(0, i));
    scrollBottom();
    if (i >= text.length) clearInterval(timer);
  }, 16);
  return el;
}
// 2026-09-21 TYPE1：状态行（参考 WorkBuddy：等待提示 = 小字+动效，不进正文）
//   showThinking(txt) → 显示状态行（三个点 + 一行小字）
//   正式的猫消息到来 → 自动收起状态行，再逐字打出正文
function setThinking(on, txt) {
  const t = document.getElementById('typing');
  if (!t) return;
  const s = document.getElementById('typing-txt');
  if (s) s.textContent = (txt && String(txt).trim()) ? String(txt).trim() : '思考中';
  t.style.display = on ? 'flex' : 'none';
}
// 只认「后面必有正式回复」的**等待类**提示：
//   · 以「稍等…」结尾
//   · 或含「正在用 LLM / 正在分析 / 正在处理 / 正在生成」
// ⚠️ 刻意**不**匹配这些（它们是独立提示，必须保留为正文，否则用户会漏看）：
//   「爬爬正在忙上一个任务，等它做完再点哦～」
//   「爬爬正在等你选附件简历，请回复序号…」
//   「爬爬正在为你打开登录页，请扫码重新登录…」
function isTransient(text) {
  const s = String(text || '').trim();
  if (!s) return false;
  // 2026-09-21 放宽：早些版本用 `稍等[…]$`（要求后面紧跟省略号），
  // 漏掉了「稍等一下哦~」这种带「~」的；同时漏了「正在解析」前的提示。
  // ★ 用**动词级**白名单（用LLM / 分析 / 解析 / 生成 / 处理），不要用「正在…」
  // 通配 —— 否则会把「正在忙上一个任务」「正在等你选简历」「正在为你打开登录页」
  // 这些**必须保留正文**的提示误吞。
  // 启动横幅（找工作喵 … 启动 …）→ 也是系统通知，走状态行
  return /稍等/.test(s)
      || /^找工作喵.*启动/.test(s)
      // OCR 进度：原字符串是「正在本地识别文字」+「正在识别…」两种都覆盖
      || /正在(本地)?\s*识别/.test(s)
      // 2026-09-21 第三次修正：「用」和「LLM」之间可能夹着「LLM...」这种括号
      // 或空格，要允许任意非字母分隔符。
      || /正在用[^a-zA-Z]*LLM/.test(s)
      || /(正在分析|正在解析|正在生成|正在处理)/.test(s);
}

function addPanel(title, options, onPick) {
  const el = document.createElement('div');
  el.className = 'msg panel';
  const t = document.createElement('div');
  t.className = 'panel-title';
  t.textContent = title;
  el.appendChild(t);
  const box = document.createElement('div');
  box.className = 'panel-opts';
  const btns = [];
  options.forEach((opt, i) => {
    const b = document.createElement('button');
    b.textContent = opt.label || opt;
    // 2026-09-24 PANELCLOSE：选完**立刻禁用全部按钮**（原实现只禁被点那个 → 看着像"还能再选"）
    b.onclick = () => {
      btns.forEach(x => { x.disabled = true; });
      b.textContent = '✓ ' + b.textContent;
      el.dataset.picked = '1';
      pendingPanel = null;
      onPick(i);
    };
    btns.push(b);
    box.appendChild(b);
  });
  el.appendChild(box);
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
  // 2026-09-24 PANELCLOSE：新面板出现时，收掉上一个还挂着的面板（避免叠一堆）
  if (pendingPanel && pendingPanel.parentNode) pendingPanel.parentNode.removeChild(pendingPanel);
  pendingPanel = el;
}

let pendingChoice = null;
let pendingPanel = null;   // 2026-09-24 PANELCLOSE：当前待选面板（选完 / 收到 close 时移除）
let planViewed = false;  // 用户是否主动点过"投递方案"看过当前方案
let currentState = '闲置';  // 当前业务状态：闲置/分析中/投递中/沟通中/停止

// 根据当前状态刷新"开始投递/停止投递"按钮
function refreshStartButton() {
  const btn = document.getElementById('btn-start');
  const running = (currentState === '投递中' || currentState === '沟通中');
  if (running) {
    btn.textContent = '⏹ 停止投递';
    btn.classList.add('stop-mode');
  } else {
    btn.textContent = '▶ 开始投递';
    btn.classList.remove('stop-mode');
  }
}

window.bridge.onEvent((msg) => {
  console.log('[chat-event]', msg.type, (msg.text || '').slice(0, 30));
  // 历史回放：清空当前消息后按顺序重放
  if (msg.type === 'history' && Array.isArray(msg.messages)) {
    msgs.innerHTML = '';
    msg.messages.forEach((m) => addMsg(m.text, m.role, true));   // 历史回放：直接显示
    addMsg('—— 以上是之前的对话 ——', 'log');
    return;
  }
  switch (msg.type) {
    case 'ready':
      setThinking(false);
      stateEl.textContent = '已就绪';
      dot.style.background = 'var(--green)';
      break;
    case 'bubble':
    case 'chat':
      // 等待类提示 → 走状态行，**不进正文**（否则和对话内容混在一起）
      if (isTransient(msg.text)) { setThinking(true, msg.text); break; }
      setThinking(false);   // 正式的话来了 → 收起状态行
      addMsg(msg.text, 'cat');
      // 喵真正展示方案详情（含关键词列表）时，视为用户已看过，解锁"开始投递"
      // 注意：启动欢迎语里也有"投递方案"字样，不能误触发
      if (msg.text && /🎯\s*关键词|关键词\s*\d+\s*个|📍\s*城市|📊\s*匹配度/.test(msg.text)) {
        planViewed = true;
        window.bridge.send({ cmd: 'get_state' });
      }
      break;
    case 'log':
      // 2026-09-23：日志不再进聊天框（内容太多太杂）——
      // 只留在看板「运行日志」与 job-hunter.log 文件。
      break;
    case 'state':
      stateEl.textContent = msg.state || '';
      currentState = msg.state || '闲置';
      setThinking(msg.state === '分析中');   // 思考中 → 显示三个点
      const c = { '闲置': '#7b776f', '分析中': '#477ba8', '投递中': '#d86f4e',
                  '沟通中': '#b8823c', '停止': '#bd5a58' }[msg.state] || '#7b776f';
      dot.style.background = c;
      refreshStartButton();
      break;
    case 'panel':
      // 2026-09-24 PANELCLOSE：Python 说「这个面板不用了」→ 从聊天里移除（选完就不该再看到）
      if (msg.kind === 'close') {
        if (pendingPanel && pendingPanel.parentNode) pendingPanel.parentNode.removeChild(pendingPanel);
        pendingPanel = null;
        pendingChoice = null;
        break;
      }
      if (msg.kind === 'resume_choice') {
        pendingChoice = 'resume_choice';
        addPanel(msg.title || '请选择要发送的附件简历',
          (msg.items || []).map((r, i) => ({ label: `${i + 1}. ${r.name}${r.desc ? '（' + r.desc + '）' : ''}` })),
          (i) => window.bridge.send({ cmd: 'choice', index: i + 1 }));
      } else if (msg.kind === 'action') {
        pendingChoice = 'action';
        addPanel(msg.title || '请选择',
          (msg.options || []).map(o => ({ label: o.label })),
          (i) => window.bridge.send({ cmd: 'choice', index: i + 1 }));
      }
      break;
    case 'error':
      addMsg('⚠ ' + msg.text, 'cat');
      break;
    case 'snapshot': {
      // 必须用户主动点过"投递方案"且当前有方案，才显示"开始投递"
      // 新方案由喵主动展示时，用户已经通过气泡看到，无需再点一次
      const kw = (msg.plan && msg.plan.keywords) || [];
      currentState = msg.state || currentState;
      document.getElementById('btn-start').style.display = (planViewed && kw.length) ? '' : 'none';
      refreshStartButton();
      break;
    }
  }
});

function sendText() {
  const t = input.value.trim();
  if (!t) return;
  addMsg(t, 'me');
  window.bridge.send({ cmd: 'user_text', text: t });
  input.value = '';
}
sendBtn.onclick = sendText;
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendText(); });

// 快捷按钮
document.getElementById('btn-start').onclick = () => {
  // 投递中/沟通中：按钮是"停止投递"，点它发 stop
  if (currentState === '投递中' || currentState === '沟通中') {
    addMsg('⏹ 停止投递', 'me');
    window.bridge.send({ cmd: 'stop' });
    return;
  }
  // 其他状态：确认方案并开始投递（等待登录/选简历的分支在 Python 端处理）
  addMsg('▶ 开始投递', 'me');
  window.bridge.send({ cmd: 'confirm_and_start' });
};
document.getElementById('btn-plan').onclick = () => {
  planViewed = true;  // 用户主动要看方案，看完后若有方案就解锁"开始投递"
  addMsg('📋 看看方案', 'me');
  window.bridge.send({ cmd: 'user_text', text: '看看方案' });
  // 主动拉一次快照，确保 snapshot 事件触发以刷新按钮状态
  window.bridge.send({ cmd: 'get_state' });
};

// 拖入简历
document.body.addEventListener('dragover', (e) => { e.preventDefault(); document.body.classList.add('dragover'); });
document.body.addEventListener('dragleave', (e) => { if (e.target === document.body) document.body.classList.remove('dragover'); });
document.body.addEventListener('drop', (e) => {
  e.preventDefault();
  document.body.classList.remove('dragover');
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!f) return;
  let path = f.path;
  if (!path && window.bridge && window.bridge.getPathForFile) {
    try { path = window.bridge.getPathForFile(f); } catch (_) {}
  }
  if (path) {
    addMsg('📎 收到简历：' + (f.name || path), 'me');
    window.bridge.send({ cmd: 'resume_file', path });
  }
});
