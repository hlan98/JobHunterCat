# Copilot Instructions — JobHunter Cat

本文件是本仓库的**总纲**。分领域的细则见 `instructions/` 目录：

- [`instructions/boss.instructions.md`](instructions/boss.instructions.md) — BOSS 平台适配层
- [`instructions/python.instructions.md`](instructions/python.instructions.md) — Python 侧
- [`instructions/frontend.instructions.md`](instructions/frontend.instructions.md) — Electron 侧

---

## 项目一句话

桌面宠物形态的求职自动化工具：Python 内核（业务）+ Electron 外壳（界面），
经 stdio JSON 通信，通过 DrissionPage 接管用户已登录的浏览器操作 BOSS 直聘。

---

## ⛔ 三条红线（违反必拒）

### 1. 不要提交隐私数据

`run/` 目录、任何 `*.log`、`node_modules/`、`*.bak` / `*.pre-*.bak` / `*.syncbak` **一律不得提交**。

其中 `run/` 含：
- `.job_hunter/` —— 浏览器登录态 Cookie
- `resume.md` —— 简历正文
- `config.json` —— **LLM API Key**

详见 [`docs/PRIVACY.md`](../docs/PRIVACY.md)。提交前务必 `git status` 核对。

### 2. 不要重写现有 BOSS 自动化流程

不要因为"结构不够漂亮"而主动重构。任何结构调整必须：

1. 先分析依赖
2. 保留现有行为
3. 小范围修改
4. 运行测试
5. 确认通过后再继续

### 3. 不要对 MIT 部分追加许可限制

`boss/`、`agent/shared.py`、`agent/ledger.py`、`agent/doctor.py`、
`agent/skill_entry.py`、`tests/` 属 MIT 衍生（**混合文件**），
不得改按 PolyForm Noncommercial 或其它限制性许可。

详见 [`docs/CODE_PROVENANCE.md`](../docs/CODE_PROVENANCE.md)。

---

## 目录约定

| 目录 | 放什么 | 不放什么 |
|---|---|---|
| `agent/` | Python 编排层与共享内核 | 平台特有逻辑 |
| `boss/` | BOSS 直聘平台适配 | 通用工具（放 `agent/shared.py`） |
| `desktop/` | Electron 全部前端 | Python 代码 |
| `docs/` | 文档 | 代码 |
| `tests/` | 测试 | 生产代码 |
| `scripts/` | 启动 / 维护脚本 | 业务逻辑 |
| `run/` | **运行时数据（不提交）** | 任何要进仓库的东西 |

---

## 代码风格

- **Python**：类型标注优先（`from __future__ import annotations`）；
  无第三方依赖优先；新增文件需能通过 `ast.parse`
- **JavaScript**：无框架、无构建步骤；`contextIsolation: true` 下只通过 `window.bridge` 通信
- **注释**：解释**为什么**，不是**是什么**。历史决策与踩过的坑值得写进注释
- **提交信息**：说明"改了什么 + 为什么"，不要只写"fix"

---

## 测试与验证

```bash
python -m unittest discover -s tests -t .
```

**当前基线：49 项全部通过。** 改动后必须保持全绿。

### 三类改动各自的验证要求

| 改动类型 | 验证方式 |
|---|---|
| 业务逻辑（Python） | 单元测试 |
| **DOM 读取逻辑** | **假 DOM + 双版本对照**（原版必须失败、新版必须全过） |
| 前端 JS / 事件契约 | `node --check` + 确认 `type:` / `cmd:` 两端成对 |

### 一条硬性纪律

**验证前先确认"我测的确实是那份代码"** —— 打印被测模块路径：

```python
print(mod.__file__)   # 曾出现"测了半天其实是另一份代码"
```

---

## 改动许可边界时

若新增/删除/重命名了源文件，或改动了混合文件：

1. 重跑 `python scripts/provenance_diff.py --baseline <基线包.zip>`
2. 更新 `docs/CODE_PROVENANCE.md`（表格数字 + 顶部「文件状态」日期）
3. 同步 `NOTICE` 与 `README.md` 的许可表格
