"""动作账本（第一阶段优化 · 观测性增强）。

每次关键投递动作（打招呼/发简历/跳过/失败）写一条 JSONL 到 run/ledger/。
纯追加、纯新增；写失败静默，绝不影响主投递流程。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def _resolve_run_dir(skill_dir: str | Path | None = None) -> Path:
    """解析账本运行目录，兼容传入 skill 根目录或已经是 run/ 的目录。"""
    if skill_dir:
        p = Path(skill_dir).expanduser().resolve()
        return p if p.name.lower() == "run" else p / "run"
    return Path(__file__).resolve().parent.parent / "run"


def _ledger_dir(skill_dir: str | Path | None = None) -> Path:
    d = _resolve_run_dir(skill_dir) / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _daily_file(skill_dir: str | Path | None = None) -> Path:
    return _ledger_dir(skill_dir) / f"ledger-{time.strftime('%Y%m%d')}.jsonl"


def record_action(action: str, status: str, details: dict[str, Any] | None = None,
                  skill_dir: str | Path | None = None) -> None:
    """追加一条动作记录。action: greet/resume_send/skip/fail/round_start/round_stop。"""
    try:
        entry = {
            "event_id": uuid.uuid4().hex[:12],
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": int(time.time()),
            "pid": os.getpid(),
            "action": action,
            "status": status,
            "details": details or {},
        }
        with _daily_file(skill_dir).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        # 账本写失败绝不影响主流程
        pass


def sha256_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return ""


def binding_snapshot(resume_path: str | Path | None, skill_dir: str | Path | None = None) -> dict[str, Any]:
    """计算简历文件指纹快照（第一阶段只观测，不做硬阻断）。"""
    snap: dict[str, Any] = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "resume_path": str(resume_path) if resume_path else "",
        "resume_sha256": "",
    }
    try:
        if resume_path:
            p = Path(resume_path)
            if p.is_file():
                snap["resume_sha256"] = sha256_file(p)
    except Exception:
        pass
    try:
        (_resolve_run_dir(skill_dir) / "binding.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    return snap


def read_recent(limit: int = 200, skill_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """读最近 N 条动作记录（给 LLM 报告/排查用）。"""
    out: list[dict[str, Any]] = []
    try:
        files = sorted(_ledger_dir(skill_dir).glob("ledger-*.jsonl"), reverse=True)
        for fp in files:
            for line in fp.read_text(encoding="utf-8").splitlines()[::-1]:
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
                if len(out) >= limit:
                    return out
    except Exception:
        return []
    return out
