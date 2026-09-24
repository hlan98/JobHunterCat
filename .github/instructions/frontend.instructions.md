---
applyTo: "desktop/**"
---

# Electron 前端规范

适用：`desktop/src/**`

> 本层全部为**原创**代码，适用 PolyForm Noncommercial 1.0.0。
> 详见 [`docs/CODE_PROVENANCE.md`](../../docs/CODE_PROVENANCE.md)。

---

## 一、进程与安全边界

```js
webPreferences: {
  preload: path.join(SRC_DIR, 'xxx-preload.js'),
  contextIsolation: true,
  nodeIntegration: false,
}
```

- 渲染进程**只能**通过 `window.bridge` 收发，拿不到 Node 能力
- 每个窗口用**自己的** preload：`preload.js` / `chat-preload.js` / `dash-preload.js`
- **不要**在渲染进程里 `require` 任何 Node 模块

---

## 二、⭐ 事件契约必须两端成对

新增事件时，**必须**同时在两端落地：

| 端 | 位置 | 动作 |
|---|---|---|
| 发出 | `agent/main.py` | `emit({"type": "xxx", ...})` |
| 转发 | `desktop/src/main.js` | 已自动转发全部事件，无需改 |
| 处理 | `desktop/src/*.js` / `*.html` | `if (msg.type === 'xxx') {...}` |

**漏掉任一端 → 事件静默丢失**，不报错、难排查。

命令方向同理：前端 `window.bridge.send({cmd:'xxx'})`
↔ 后端 `pet_bridge.py` 的 `_dispatch`。

---

## 三、⭐ 推送式状态必须支持「打开时回放」

**窗口可以随时开关 —— 只靠推送，打开时就是空的。**

```js
// main.js：缓存 + 加载完成后补发
if (msg.type === 'progress') lastProgress = msg;
...
dashWin.webContents.once('did-finish-load', () => {
  if (lastProgress) dashWin.webContents.send('pet-event', lastProgress);
});
```

**为什么**：`progress` 只在投递中推送。用户中途打开看板时，
要等下一次事件（收集阶段 1~3 分钟一次）；若接近尾声就再也等不到
→ 表现为"进度条不动"。

**新增任何推送式状态时，都要问：窗口晚打开会怎样？**

已有回放机制的状态：
- `progress` → `lastProgress`
- `state` / `snapshot` → 看板加载时发 `get_state`，后端推完整快照

---

## 四、事件处理的位置

`dash.html` / `chat.js` 的 `window.bridge.onEvent(msg => {...})` 是**唯一入口**。

- 新分支**加在开头附近**，避免被前面的逻辑拦住
- 分支内取 DOM 用 `getElementById` + 判空，不要假设元素一定存在：

```js
const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
```

---

## 五、主题与可读性

- 遵循当前 IDE / 系统主题（浅色主题下不要用深色面板）
- **颜色类（如 `c-purple`）尚未实现** —— SVG / canvas 里必须**显式写 fill**，
  否则回落到黑色
- 图表里的硬编码颜色也要跟随主题

---

## 六、调试验证

```bash
# 语法检查（改完必跑）
node --check desktop/src/main.js

# 真跑产物 JS 的逻辑校验
node tests/verify_ui_logic.js
```

### 前端逻辑的验证方式

DOM 处理逻辑单测覆盖不到、静态检查也测不出。用**假 DOM + 双版本对照**：

- 造一个能触发 bug 的假 DOM
- 同一套断言跑**修复前**和**修复后**：前者必须失败、后者必须全过
- **打印被测文件路径**确认测的是哪份代码（曾出现路径替换没生效、白测一轮）

---

## 七、窗口生命周期

```js
chatWin.on('closed', () => { chatWin = null; });   // 必须置空
```

- 关窗后**必须**把变量置空，否则转发时会向已销毁的窗口发事件
- 转发前判活：`if (dashWin && !dashWin.isDestroyed())`

---

## 八、不要引入构建步骤

本项目**无框架、无打包**：直接写 `.js` / `.html` / `.css`，Electron 直接加载。

不要为了"现代化"引入 React / Vue / Vite 构建链 —— 会破坏"改完即生效"的开发体验。
