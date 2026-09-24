# AGENTS.md — 给 AI 编码助手的入口

> 本文件是**总入口**。分领域细则见 `.github/instructions/`。

---

## 项目定位

**JobHunter Cat（找工作喵）** —— 桌面宠物形态的求职自动化工具。

- **业务**：在 BOSS 直聘上收集岗位 → 评分 → 打招呼 → 监听 HR 消息 → 自动发简历
- **形态**：Electron 透明桌宠 + 对话窗 + 看板
- **技术**：Python 内核（业务）+ Electron 外壳（界面），stdio JSON 通信，
  DrissionPage 接管用户已登录的浏览器

---

## 先读什么

| 你的任务 | 先读 |
|---|---|
| 了解现状能跑什么 | [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) |
| 改代码前理解结构 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 想知道"为什么这样设计" | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| 涉及文件/许可问题 | [`docs/CODE_PROVENANCE.md`](docs/CODE_PROVENANCE.md) |
| 涉及数据与提交 | [`docs/PRIVACY.md`](docs/PRIVACY.md) |
| 改 `boss/` 平台层 | [`.github/instructions/boss.instructions.md`](.github/instructions/boss.instructions.md) |
| 改 Python | [`.github/instructions/python.instructions.md`](.github/instructions/python.instructions.md) |
| 改前端 | [`.github/instructions/frontend.instructions.md`](.github/instructions/frontend.instructions.md) |

---

## 常用命令

```bash
# 单元测试（49 项基线，必须全绿）
python -m unittest discover -s tests -t .

# Python 语法自检
python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.py')]"

# 前端语法检查
node --check desktop/src/main.js

# 真跑前端产物 JS 的逻辑校验
node tests/verify_ui_logic.js

# 代码来源差异分析（改动混合文件后重跑）
python scripts/provenance_diff.py --baseline <基线包.zip> --markdown

# 启动
scripts\启动找工作喵.bat
```

---

## ⛔ 红线（不可协商）

1. **不提交隐私**：`run/`、`*.log`、`node_modules/`、`*.pre-*.bak`
   —— `run/` 含登录态 Cookie、简历正文、LLM API Key
2. **不重写现有 BOSS 自动化流程**；结构调整走"分析依赖 → 保留行为 → 小改 → 测试 → 确认"
3. **不对 MIT 部分追加许可限制**（`boss/` 及 `shared.py` / `ledger.py` / `doctor.py` / `skill_entry.py` / `tests/`）
4. **不静默替换用户意图** —— 取不到值就明确报错，不要兜底成别的值
5. **不擅自回复 HR** —— 只有两类可以自动发：HR 要简历（发简历）、HR 拒绝（发致谢，每会话一次）；
   **面试邀请、系统模板、普通对话一律只提示用户接管，不自动回复**

---

## 本项目的 5 条经验教训（血泪）

写代码时请主动规避：

| # | 教训 | 具体 |
|---|---|---|
| 1 | **`find_first` 会漏信息** | 多段结构（卡片/富文本）只取第一个匹配 → 必须用整条文字兜底 |
| 2 | **推送式状态打开时是空的** | 窗口可随时开关 → 必须支持打开时回放 |
| 3 | **验证前先确认测的是哪份代码** | `print(mod.__file__)` —— 曾出现路径替换没生效、白测一轮 |
| 4 | **单测可能拦住错误修改** | 加宽检测范围时先看现有断言，避免引入误判（如给拒绝你的人发简历） |
| 5 | **写状态文档前必须核对代码** | 曾把已删除的模块写进文档，误导后来者 |

---

## 代码风格速览

- **Python**：`from __future__ import annotations`；类型标注优先；无第三方依赖优先
- **JavaScript**：无框架无构建；`contextIsolation: true`；只经 `window.bridge` 通信
- **注释**：写**为什么**，不写**是什么**；历史决策与踩过的坑值得留在注释里
- **提交**：说明"改了什么 + 为什么"

---

## 改动后的自检清单

- [ ] `python -m unittest discover -s tests -t .` 全绿（49 项）
- [ ] 新增/改动的事件 `type:` 与命令 `cmd:` 两端成对
- [ ] 新增依赖已写进 `requirements.txt`
- [ ] 涉及 DOM 读取 → 假 DOM 双版本对照验证过
- [ ] 涉及文件增删/改名 → 重跑 `provenance_diff.py` 并更新 `CODE_PROVENANCE.md`
- [ ] `git status` 里**没有** `run/`、`*.log`、隐私文件
