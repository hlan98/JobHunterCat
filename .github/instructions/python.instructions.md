---
applyTo: "agent/**/*.py"
---

# Python 侧规范

适用：`agent/*.py`

> ⚠️ `shared.py`、`ledger.py`、`doctor.py`、`skill_entry.py` 是 **MIT 衍生（混合文件）**；
> `main.py`、`pet_bridge.py` 是**原创**（PolyForm Noncommercial）。
> 详见 [`docs/CODE_PROVENANCE.md`](../../docs/CODE_PROVENANCE.md)。

---

## 一、模块职责边界

| 模块 | 只负责 |
|---|---|
| `main.py` | 流程编排、状态机、UI 事件发出 |
| `pet_bridge.py` | stdin 命令分发 → 调能力 → stdout 事件 |
| `shared.py` | 配置、日志、评分、LLM、浏览器接管、DOM 工具 |
| `ledger.py` | 动作账本（纯追加） |
| `doctor.py` | 环境自检 |

**平台特有逻辑不要写进 `shared.py`** —— 那是 `boss/` 的事。

---

## 二、路径解析

```python
DEMO_DIR  = Path(__file__).resolve().parent    # agent/
REPO_ROOT = DEMO_DIR.parent                     # 仓库根
RUN_DIR   = Path(os.environ.get("JOB_HUNTER_HOME", str(REPO_ROOT / "run")))
```

- 支持 `JOB_HUNTER_PACKAGE_DIR` / `JOB_HUNTER_HOME` 环境变量覆盖
- **不要**硬编码绝对路径
- 测试里的路径探测用**多候选**，兼容结构变化：

```python
_root = Path(__file__).resolve().parents[1]
_candidates = [_root / "agent" / "main.py", _root / "main.py", ...]
```

---

## 三、依赖

- **无第三方依赖优先**（标准库能解决就不引库）
- 新增依赖必须**同时**写进 `requirements.txt`，并说明用途
  - 历史教训：`pymupdf` / `python-docx` 一直在用却**从未声明**，
    照 `requirements.txt` 建环境会导致 PDF / docx 简历解析直接 `ImportError`
- 可选依赖要**优雅降级**：缺失时给出明确提示，不要静默失败

---

## 四、类型与风格

- 文件头 `from __future__ import annotations`
- 公开函数加类型标注
- 异常**不要**裸 `except:`；至少 `except Exception:`
- 静默吞异常要写清**为什么可以吞**：

```python
try:
    ...
except Exception:
    pass   # 账本写失败不影响主流程，故意忽略
```

---

## 五、⛔ 禁止静默替换用户意图

**这是本项目的核心纪律。**

```python
# ❌ 表外城市静默回退广州 —— 用户以为在投长沙，实际投广州
return CITY_CODES.get(name, CITY_CODES["广州"])

# ✅ 明确返回空 + 由调用方提示用户并中止
return CITY_CODES.get(str(name or "").strip(), "")
```

凡"取不到值就给个默认"的地方，先问自己：
**这个默认值会不会掩盖用户的真实意图？** 会 → 明确报错，不要兜底。

同类问题清单见 [`docs/DECISIONS.md`](../../docs/DECISIONS.md)（ADR-8 / ADR-9 / ADR-10）。

---

## 六、日志

- 走 `add_log()`（写入有体积上限），**不要**直接 `open(...).write()`
- 日志要能**定位问题**：带上下文（哪个会话 / 哪个关键词 / 第几步）
- 关键决策点（跳过 / 中止 / 回退）**必须**留日志

---

## 七、验证

```bash
# 语法自检（改完先跑这个）
python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.py')]"

# 单测
python -m unittest discover -s tests -t .
```

- **49 项基线必须保持全绿**
- 改了函数签名 → 同步检查 `tests/` 里的断言（含 `_changed` 列表这类清单断言）
- 涉及 DOM 读取的改动 → 用**假 DOM 双版本对照**验证
