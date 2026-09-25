# Contributing · 如何参与

感谢你愿意参与。**在动手之前，请先读完这份文件** —— 尤其是「⛔ 红线」那节，
因为本项目会**真的给 HR 发消息**，有些错误的代价是不可逆的。

---

## 这个项目是什么

Python 内核（业务逻辑）+ Electron 外壳（界面）的双进程应用，通过 stdio JSON 通信。
界面是一只常驻桌面的猫，但**猫只是交互入口** —— 核心是背后的 Agent 与求职记忆。

不了解整体结构？先看：

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —— 分层与事件协议
- [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) —— 现在能跑什么
- [`docs/DECISIONS.md`](docs/DECISIONS.md) —— 12 条关键设计决策（**改架构前必读**）
- [`AGENTS.md`](AGENTS.md) —— 代码约定（AI 助手也读这一份）

---

## 开始之前

### 环境

| 项 | 要求 |
|---|---|
| 系统 | Windows 10/11 |
| Python | 3.10–3.13（**必须带 tkinter**） |
| Node.js | 20+ |
| 浏览器 | Chrome（需手动登录 BOSS 直聘，程序接管 9222 端口） |

```bash
git clone https://github.com/hlan98/JobHunterCat.git jobhuntercat
cd jobhuntercat
pip install -r requirements.txt
cd desktop && npm install && cd ..
```

### ⚠️ 第一次跑，别急着投递

程序**默认就是真实投递**，没有「先试一下」的模式，**也没有只读试跑**。

- 「开始投递」= 真的给 HR 发消息，发出去收不回来
- 改动投递相关代码时，不要拿你的**主力求职账号**做试验

---

## 常用命令

```bash
# 单元测试（49 项基线，改动前后都必须全绿）
python -m unittest discover -s tests -t .

# Python 语法自检
python -m compileall -q agent boss

# 前端语法检查
node --check desktop/src/main.js

# 代码来源差异分析（改动混合文件后重跑）
python scripts/provenance_diff.py --markdown
```

---

## ⛔ 红线（不可协商）

这 5 条是从真实事故里总结出来的，不是形式主义：

1. **不提交隐私**
   `run/`、`*.log`、`node_modules/`、`*.pre-*.bak` 一律不提交。
   `run/` 里含 BOSS 登录态、简历正文、LLM API Key。
   → 提交前跑 `git status`，详见 [`docs/PRIVACY.md`](docs/PRIVACY.md)。

2. **不重写现有 BOSS 自动化流程**
   结构调整走「分析依赖 → 保留行为 → 小改 → 测试 → 确认」。
   这条链路是在真实账号上反复试出来的，很多看似冗余的分支是踩坑后的产物。

3. **不对 MIT 部分追加许可限制**
   `boss/` 及 `agent/shared.py`、`ledger.py`、`doctor.py`、`skill_entry.py`、`tests/` 是混合文件，
   目前采取保守处置整体按 MIT 分发。**不要给它们加任何附加条款。**

4. **不静默替换用户意图**
   取不到值就**明确报错**，不要兜底成别的值。
   本项目已因此出过多次事故（城市静默回退广州、LLM 返回的关键词白名单漏列即删除）。

5. **不自动回复面试邀请**
   必须提示用户接管。这是产品原则，不是实现细节。

---

## 代码风格

- **Python**：`from __future__ import annotations`；类型标注优先；无第三方依赖优先
- **JavaScript**：无框架无构建；`contextIsolation: true`；只经 `window.bridge` 通信
- **注释**：写**为什么**，不写**是什么**。历史决策和踩过的坑值得留在注释里
- **提交信息**：说明「改了什么 + 为什么」

---

## 改完之后的自检清单

提交 PR 前，请逐项确认：

- [ ] `python -m unittest discover -s tests -t .` 全绿（49 项）
- [ ] 新增/改动的事件 `type:` 与命令 `cmd:` **两端成对**（前端发了后端要有处理，反之亦然）
- [ ] 新增依赖已写进 `requirements.txt`
- [ ] 涉及 **DOM 读取**的改动 → 做过**假 DOM 双版本对照**验证（修复前必须失败、修复后必须全过）
- [ ] 涉及 **CSS 类名**的改动 → 反查过 `querySelector` / `closest` / `classList`（JS 按类名查询不经过 class 属性，很容易漏）
- [ ] 涉及 **LLM 返回的结构化数据** → 校验过「是否越权改动用户配置」
- [ ] 新增的重型第三方依赖调用 → 放在子进程 + 硬超时（主线程阻塞会让用户永远卡住）
- [ ] 没有提交 `run/` 或任何含隐私/密钥的文件

---

## Good First Issues

以下是**真实存在、可以直接认领**的改进点（不是凑数的泛型清单）：

| # | 任务 | 为什么有价值 | 难度 |
|---|---|---|---|
| 1 | 补全并校验城市码表（现 63 个） | 广东部分地级市编码是按规律推的，**需人工抽查**；表外城市目前会明确报错 | 低 |
| 2 | 支持老版 Word `.doc` | 目前显式拒绝。要么接真解析（antiword / LibreOffice），要么把提示写得更清楚 | 中 |
| 3 | 英文 README | 项目名是 JobHunter Cat，国际开发者看不懂中文 README | 低 |
| 4 | 英文界面文案抽取 | 目前文案硬编码在 Python 字符串里，做 i18n 前需要先抽出来 | 中 |
| 5 | 处理 `real` 参数名存实亡的问题 | `cmd_test_run` 的 `real=False` 分支本版本恒为 `True`，参数保留只为兼容。**要么恢复演练模式，要么删掉这个假参数** | 中 |
| 6 | 匹配分校准 | 现在的分数是启发式的，不等于真实成功率。需要用真实投递结果做统计校准 | 高 |
| 7 | 浏览器错误恢复 | 页面结构变化 / 弹窗 / 验证码会让流程中断，需要更健壮的恢复 | 高 |
| 8 | 补充简历格式测试 | 目前测试集中在核心逻辑，简历解析（PDF/docx/txt/md/图片）覆盖不足 | 中 |
| 9 | 新的猫动画素材 | `assets/papai_*.png` 现有 sit / happy / think / wave 四种，欢迎补充 | 低 |

认领方式：开一个 issue 说明你要做哪个，避免重复劳动。

---

## 许可相关

- 你贡献的代码，若属于**原创部分**，将采用 PolyForm Noncommercial 1.0.0
- 若改动的是**混合文件**（`boss/` 等），那部分整体按 MIT 分发，不追加限制
- 具体边界见 [`docs/CODE_PROVENANCE.md`](docs/CODE_PROVENANCE.md) 与 [`NOTICE`](NOTICE)

---

## 联系

- 商用授权：Leo He（邮箱 hlan98@hotmail.com · QQ `104495956`）
- 技术问题：请开 issue
