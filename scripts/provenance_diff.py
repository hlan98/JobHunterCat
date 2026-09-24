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

为什么需要基线包
----------------
本仓库起源于第三方 MIT 项目。要量化"改了多少"，需要一个**较早的快照**做逐行比对。
本项目使用的基线是 2026-09-12 的完整包（详见文档第五节）。

⚠️ 重要：**基线 ≠ 上游原始版本**。
本脚本测出的是"与基线的一致程度"，不是"与上游 MIT 原版的一致程度"。
要测后者，需要获取上游原始仓库。
"""
from __future__ import annotations

import argparse
import difflib
import pathlib
import sys
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 基线包内的模块路径 → 本仓库当前位置
# None 表示该模块已被删除
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

BASELINE_PREFIX = "job-hunter-skill/job_hunter_skill/"


def measure(baseline: pathlib.Path) -> tuple[list[dict], dict]:
    """返回 (每模块统计, 合计)"""
    rows: list[dict] = []
    z = zipfile.ZipFile(baseline)

    for base_name, cur_rel in MODULE_MAP.items():
        member = BASELINE_PREFIX + base_name
        try:
            base_lines = z.read(member).decode("utf-8", "ignore").splitlines()
        except KeyError:
            continue

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
        sm = difflib.SequenceMatcher(None, base_lines, cur_lines, autojunk=False)
        same = sum(bl.size for bl in sm.get_matching_blocks())
        rows.append({
            "name": base_name,
            "base": len(base_lines),
            "cur": len(cur_lines),
            "same": same,
            "add": len(cur_lines) - same,
            "del": len(base_lines) - same,
        })

    total = {
        "base": sum(r["base"] for r in rows),
        "cur": sum(r["cur"] for r in rows if isinstance(r["cur"], int)),
        "same": sum(r["same"] for r in rows if isinstance(r["same"], int)),
        "add": sum(r["add"] for r in rows if isinstance(r["add"], int)),
        "del": sum(r["del"] for r in rows if isinstance(r["del"], int)),
    }
    return rows, total


def print_plain(rows: list[dict], total: dict) -> None:
    print("%-20s %8s %8s %8s %8s %8s %9s" %
          ("模块", "基线行", "现在行", "未变行", "新增行", "删除行", "未变占比"))
    print("-" * 76)
    for r in rows:
        if r["cur"] is None:
            print("%-20s %8d %8s %8s %8s %8d %9s" %
                  (r["name"], r["base"], "—", "—", "—", r["del"], "全部删除"))
            continue
        if not isinstance(r["cur"], int):
            print("%-20s %8d %8s   %s" % (r["name"], r["base"], r["cur"], r["cur"]))
            continue
        pct = r["same"] * 100.0 / r["cur"] if r["cur"] else 0
        print("%-20s %8d %8d %8d %8d %8d %8.0f%%" %
              (r["name"], r["base"], r["cur"], r["same"], r["add"], r["del"], pct))
    print("-" * 76)
    if total["cur"]:
        print("%-20s %8d %8d %8d %8d %8d %8.1f%%" %
              ("合计", total["base"], total["cur"], total["same"],
               total["add"], total["del"], total["same"] * 100.0 / total["cur"]))
    print()
    if total["cur"]:
        print("★ 与基线保持一致的行占比：%.1f%%" % (total["same"] * 100.0 / total["cur"]))
        print("★ 后续新增/重写的行占比：  %.1f%%" % (total["add"] * 100.0 / total["cur"]))
        print()
        print("⚠️ 以上为「与基线的一致程度」，**不等于**「与上游 MIT 原始版本的一致程度」。")


def print_markdown(rows: list[dict], total: dict) -> None:
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
        print("| **合计** | **%d** | **%d** | **%d** | **%d** | **%d** | **%.1f%%** |" %
              (total["base"], total["cur"], total["same"],
               total["add"], total["del"], total["same"] * 100.0 / total["cur"]))


def main() -> int:
    ap = argparse.ArgumentParser(description="代码来源差异分析（支撑 CODE_PROVENANCE.md）")
    ap.add_argument("--baseline", required=True, help="基线包（.zip）路径")
    ap.add_argument("--markdown", action="store_true", help="输出 Markdown 表格（可直接粘贴进文档）")
    args = ap.parse_args()

    baseline = pathlib.Path(args.baseline)
    if not baseline.exists():
        print("❌ 基线包不存在：%s" % baseline, file=sys.stderr)
        return 1

    rows, total = measure(baseline)
    print("基线：%s" % baseline)
    print("仓库：%s" % REPO_ROOT)
    print()
    (print_markdown if args.markdown else print_plain)(rows, total)

    print()
    print("提示：更新 docs/CODE_PROVENANCE.md 时，请同时更新「文件状态」中的日期。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
