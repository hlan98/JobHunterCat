"""Job Hunter Skill 环境自检。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
from pathlib import Path
from typing import Any

from agent.shared import (
    CODE_DIR,
    PROJECT_NAME,
    PROJECT_VERSION,
    effective_llm_settings,
    load_config,
    platform_debug_port,
    platform_label,
    resolve_resume_path,
    resolve_skill_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job Hunter 环境自检")
    parser.add_argument("--skill-dir", help="运行目录，默认使用当前工作目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser.parse_args()


def make_check(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    payload = {
        "name": name,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def module_exists(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def build_report(skill_dir: str | Path | None = None) -> dict[str, Any]:
    runtime_dir = resolve_skill_dir(skill_dir)
    config_file = runtime_dir / "config.json"
    config = load_config(runtime_dir)
    llm_settings = effective_llm_settings(config)

    checks: list[dict[str, Any]] = []
    checks.append(
        make_check(
            "python_version",
            "ok" if sys.version_info >= (3, 10) else "error",
            f"当前 Python 版本为 {sys.version.split()[0]}。",
            required=">=3.10",
        )
    )

    # 2026-09-18：sxs_apply.py 已随「删死代码」移除，不再列入必检。
    for filename in ("skill_entry.py", "shared.py", "boss_apply.py"):
        path = CODE_DIR / filename
        checks.append(
            make_check(
                f"code_file:{filename}",
                "ok" if path.exists() else "error",
                f"{filename} {'存在' if path.exists() else '缺失'}。",
                path=str(path),
            )
        )

    checks.append(
        make_check(
            "config_file",
            "ok" if config_file.exists() else "warn",
            "已找到 config.json。" if config_file.exists() else "未找到 config.json；首次运行 job-hunter 会引导你根据 resume.md 生成。",
            path=str(config_file),
        )
    )

    resume_path = str(config.get("resume_path", "")).strip()
    if resume_path:
        try:
            resolved_resume = resolve_resume_path(resume_path, runtime_dir)
            resume_exists = resolved_resume.exists()
            checks.append(
                make_check(
                    "resume_file",
                    "ok" if resume_exists else "warn",
                    "已找到简历文件。" if resume_exists else "配置了 resume_path，但文件不存在。",
                    path=str(resolved_resume),
                )
            )
        except Exception as exc:
            checks.append(
                make_check(
                    "resume_file",
                    "warn",
                    f"无法解析 resume_path：{exc}",
                    raw_value=resume_path,
                )
            )
    else:
        checks.append(
            make_check(
                "resume_file",
                "warn",
                "尚未配置 resume_path；请先把 resume.md 放到运行目录，首次运行会提示确认路径。",
            )
        )

    checks.append(
        make_check(
            "drissionpage",
            "ok" if module_exists("DrissionPage") else "error",
            "DrissionPage 已安装。" if module_exists("DrissionPage") else "未检测到 DrissionPage，请先执行 `python -m pip install -e .`。",
        )
    )

    llm_ready = all(
        [
            str(llm_settings.get("base_url", "")).strip(),
            str(llm_settings.get("api_key", "")).strip(),
            str(llm_settings.get("model", "")).strip(),
        ]
    )
    checks.append(
        make_check(
            "llm_config",
            "ok" if llm_ready else "warn",
            "LLM 配置完整。" if llm_ready else "LLM 仍可用启发式补分运行；如需真实 LLM，请补齐 base_url / api_key / model。",
            model=str(llm_settings.get("model", "")),
        )
    )

    # 2026-09-18：只剩 Boss 一个平台（实习僧已移除）。
    for platform in ("boss",):
        port = platform_debug_port(platform, config)
        checks.append(
            make_check(
                f"browser_port:{platform}",
                "ok" if is_port_open(port) else "warn",
                f"{platform_label(platform)} 的浏览器调试端口 {port} {'已监听' if is_port_open(port) else '未监听'}。",
                port=port,
            )
        )

    summary = {
        "ok": sum(1 for item in checks if item["status"] == "ok"),
        "warn": sum(1 for item in checks if item["status"] == "warn"),
        "error": sum(1 for item in checks if item["status"] == "error"),
    }

    return {
        "project": PROJECT_NAME,
        "version": PROJECT_VERSION,
        "runtime_dir": str(runtime_dir),
        "code_dir": str(CODE_DIR),
        "checks": checks,
        "summary": summary,
    }


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    report = build_report(args.skill_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['project']} {report['version']}")
        print(f"运行目录: {report['runtime_dir']}")
        print(f"代码目录: {report['code_dir']}")
        for item in report["checks"]:
            print(f"[{item['status'].upper()}] {item['name']}: {item['message']}")
        print(
            f"汇总: ok={report['summary']['ok']} "
            f"warn={report['summary']['warn']} error={report['summary']['error']}"
        )
    return 0 if report["summary"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
