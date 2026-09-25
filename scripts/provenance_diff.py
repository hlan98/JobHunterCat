#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""代码来源差异分析 —— 支撑 docs/CODE_PROVENANCE.md 的实测数据

用途
----
`docs/CODE_PROVENANCE.md` 第三节的数字（未变行 / 新增 / 删除）由本脚本生成。
**每次改动混合文件后**，请重跑本脚本并更新文档中的数字。

用法
----
    python scripts/provenance_diff.py --baseline <基线包.zip>
    python scripts/provenance_diff.py --baseline <zip> --markdown   # 直接输出可粘贴的表格

基线
----
2026-09-25 起，基线改为**上游原始包** `job-hunter-skill.zip`
（目录结构：`job_hunter_skill/*.py` + `tests/` + `examples/`）。

此前用的是「找工作喵 2026-09-12 完整包」当基线 —— **那是错的**：
它本身已包含找工作喵自己早期的代码（main.py / pet_bridge.py / desktop/），
会把自有早期代码误算成"来源于原项目"，从而**低估**新增代码比例。

⚠️ 重要差异（相对旧基线）：
原始包里**没有** `boss_chat.py`、`ledger.py`，也没有 `main.py` /
`pet_bridge.py` / `desktop/` —— 这些都是后续新增，本脚本会单独统计为「新增文件」。
"""
from __future__ import annotations

import argparse
import difflib
import pathlib
import sys
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 基线包内的模块名 → 本仓库当前位置；None = 该文件已被删除
MODULE_MAP: dict[str, str | None] = {
    "boss_apply.py": "boss/boss_apply.py",
    "boss_chat.py": "boss/boss_chat.py",
    "shared.py": "agent/shared.py",
    "ledger.py": "agent/ledger.py",
    "doctor.py": "agent/doctor.py",
    "skill_entry.py": "agent/skill_entry.py",
    "sxs_apply.py": None,          # 实习僧适配，已整体删除
    "__init__.py": None,
}

# 测试与非代码资源（原始包里也有，同样要做比对）
EXTRA_MAP: dict[str, str] = {
    "tests/test_core.py": "tests/test_core.py",
    "examples/config.example.json": "examples/config.example.json",
    "examples/resume.example.md": "examples/resume.example.md",
}


def detect_prefix(z: zipfile.ZipFile) -> str:
    """自动识别基线包里 job_hunter_skill/ 的位置（不同打包方式前缀不同）。"""
    names = z.namelist()
    for n in names:
        if n.endswith("job_hunter_skill/shared.py"):
            return n[: -len("shared.py")]
    for n in names:
        if n.endswith("/shared.py") or n == "shared.py":
            return n[: -len("shared.py")]
    return "job_hunter_skill/"


def count_lines(path: pathlib.Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return 0


def scan_new_files(mapped: set) -> list[tuple[str, int]]:
    """扫描仓库里『基线中不存在』的代码文件（= 后续新增）。

    `mapped` = **基线里真实存在**、已被逐行比对过的目标文件集合。
    注意：MODULE_MAP 里登记了但**基线中查不到**的模块（如 boss_chat.py / ledger.py）
    不属于 mapped，必须计入新增文件 —— 否则会被漏统计。
    只统计主要代码目录，跳过 .git / node_modules / 素材二进制。
    """
    SKIP_DIRS = {".git", "node_modules", "assets", "__pycache__", "run", "docs", "scripts", "memory"}
    out: list[tuple[str, int]] = []
    for p in sorted(REPO_ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        parts = rel.split("/")
        if parts[0] in SKIP_DIRS:
            continue
        if p.suffix.lower() not in (".py", ".js", ".html", ".css", ".md"):
            continue
        if rel == "README.md":
            continue
        out.append((rel, count_lines(p)))
    return [(r, n) for r, n in out if r not in mapped]


def _diff(base_lines: list[str], cur_lines: list[str]) -> tuple[int, int, int]:
    sm = difflib.SequenceMatcher(None, base_lines, cur_lines, autojunk=False)
    same = sum(bl.size for bl in sm.get_matching_blocks())
    return same, len(cur_lines) - same, len(base_lines) - same


def measure(baseline: pathlib.Path) -> tuple[list[dict], dict, list[tuple[str, int]]]:
    z = zipfile.ZipFile(baseline)
    prefix = detect_prefix(z)
    rows: list[dict] = []

    def read_base(rel: str) -> list[str] | None:
        for cand in (prefix + rel, rel):
            try:
                return z.read(cand).decode("utf-8", "ignore").splitlines()
            except KeyError:
                continue
        return None

    # ① 有基线对应的模块
    pairs = list(MODULE_MAP.items()) + [(k, v) for k, v in EXTRA_MAP.items()]
    mapped: set = set()
    for base_name, cur_rel in pairs:
        base_lines = read_base(base_name)
        if base_lines is None:
            # 基线里没有 → 属「后续新增文件」，由 scan_new_files() 统一统计
            continue
        if cur_rel:
            mapped.add(cur_rel)
        if cur_rel is None:
            rows.append({"name": base_name, "base": len(base_lines), "cur": None,
                         "same": None, "add": None, "del": len(base_lines)})
            continue
        cur_path = REPO_ROOT / cur_rel
        if not cur_path.exists():
            rows.append({"name": base_name, "base": len(base_lines), "cur": "缺失",
                         "same": None, "add": None, "del": None})
            continue

        cur_lines = cur_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        same, add, dele = _diff(base_lines, cur_lines)
        rows.append({"name": base_name, "base": len(base_lines), "cur": len(cur_lines),
                     "same": same, "add": add, "del": dele})

    new_files = scan_new_files(mapped)

    total = {
        "base": sum(r["base"] for r in rows),
        "cur": sum(r["cur"] for r in rows if isinstance(r["cur"], int)),
        "same": sum(r["same"] for r in rows if isinstance(r["same"], int)),
        "add": sum(r["add"] for r in rows if isinstance(r["add"], int)),
        "del": sum(r["del"] for r in rows if isinstance(r["del"], int)),
        "new_files": sum(n for _, n in new_files),
    }
    return rows, total, new_files


def print_plain(rows: list[dict], total: dict, new_files: list[tuple[str, int]]) -> None:
    print("%-24s %8s %8s %8s %8s %8s %9s" %
          ("模块", "基线行", "现在行", "未变行", "新增行", "删除行", "未变占比"))
    print("-" * 80)
    for r in rows:
        if r["cur"] is None:
            print("%-24s %8d %8s %8s %8s %8d %9s" %
                  (r["name"], r["base"], "—", "—", "—", r["del"], "全部删除"))
            continue
        if not isinstance(r["cur"], int):
            print("%-24s %8d %8s   %s" % (r["name"], r["base"], r["cur"], r["cur"]))
            continue
        pct = r["same"] * 100.0 / r["cur"] if r["cur"] else 0
        print("%-24s %8d %8d %8d %8d %8d %8.0f%%" %
              (r["name"], r["base"], r["cur"], r["same"], r["add"], r["del"], pct))
    print("-" * 80)
    if total["cur"]:
        print("%-24s %8d %8d %8d %8d %8d %8.1f%%" %
              ("合计（有对应）", total["base"], total["cur"], total["same"],
               total["add"], total["del"], total["same"] * 100.0 / total["cur"]))

    print("\n=== 基线中不存在 → 后续新增文件 ===")
    for rel, n in new_files:
        print("   %-36s %6d 行" % (rel, n))
    print("   %-36s %6d 行" % ("新增文件合计", total["new_files"]))

    print("\n=== 总体（用于「原创占比」） ===")
    own = total["add"] + total["new_files"]
    inherited = total["same"]
    allcur = total["cur"] + total["new_files"]
    if allcur:
        print("   继承自原项目（逐行未变）: %d 行  %.1f%%" % (inherited, inherited * 100.0 / allcur))
        print("   后续新增 / 重写          : %d 行  %.1f%%" % (own, own * 100.0 / allcur))
        print("   （现有可比代码总行 %d）" % allcur)


def print_markdown(rows: list[dict], total: dict, new_files: list[tuple[str, int]]) -> None:
    print("| 模块 | 基线行数 | 现有行数 | **未变行** | 新增行 | 删除行 | 未变占比 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        if r["cur"] is None:
            print("| `%s`（已删除） | %d | — | — | — | 全部删除 | — |" % (r["name"], r["base"]))
            continue
        if not isinstance(r["cur"], int):
            continue
        pct = r["same"] * 100.0 / r["cur"] if r["cur"] else 0
        print("| `%s` | %d | %d | **%d** | %d | %d | **%.0f%%** |" %
              (r["name"], r["base"], r["cur"], r["same"], r["add"], r["del"], pct))
    if total["cur"]:
        print("| **合计（有对应）** | **%d** | **%d** | **%d** | **%d** | **%d** | **%.1f%%** |" %
              (total["base"], total["cur"], total["same"],
               total["add"], total["del"], total["same"] * 100.0 / total["cur"]))
    print()
    print("### 基线中不存在 → 后续新增文件")
    print()
    print("| 文件 | 行数 |")
    print("|---|---|")
    for rel, n in new_files:
        print("| `%s` | %d |" % (rel, n))
    print("| **新增文件合计** | **%d** |" % total["new_files"])


def main() -> int:
    ap = argparse.ArgumentParser(description="代码来源差异分析（支撑 CODE_PROVENANCE.md）")
    ap.add_argument("--baseline", required=True, help="基线包（.zip）路径")
    ap.add_argument("--markdown", action="store_true", help="输出 Markdown 表格（可直接粘贴进文档）")
    args = ap.parse_args()

    baseline = pathlib.Path(args.baseline)
    if not baseline.exists():
        print("❌ 基线包不存在：%s" % baseline, file=sys.stderr)
        return 1

    rows, total, new_files = measure(baseline)
    print("基线：%s" % baseline)
    print("仓库：%s" % REPO_ROOT)
    print()
    (print_markdown if args.markdown else print_plain)(rows, total, new_files)

    print()
    print("提示：更新 docs/CODE_PROVENANCE.md 时，请同时更新「文件状态」中的日期。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
