"""Job Hunter Skill 入口脚本。"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Callable

from agent.shared import (
    DEFAULT_GREETING,
    JobTask,
    PROJECT_NAME,
    PROJECT_VERSION,
    connect_browser,
    dedupe_keep_order,
    default_config,
    get_logger,
    initialize_config_from_resume,
    load_config,
    normalize_platforms,
    normalize_run_mode,
    platform_debug_port,
    platform_label,
    print_browser_login_instructions,
    read_resume_text,
    resolve_skill_dir,
    run_mode_label,
    sanitize_json_text,
    save_config,
    split_keywords,
)


CODE_DIR = Path(__file__).resolve().parent
SCRIPT_REGISTRY = {
    "boss": {"module": "boss_apply", "functions": ("apply_jobs", "run", "main")},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job Hunter Skill 入口")
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROJECT_NAME} {PROJECT_VERSION}",
    )
    parser.add_argument("--platform", help="本次执行的平台，目前仅支持 boss")
    parser.add_argument("--job", help="本次搜索岗位名")
    parser.add_argument("--city", help="目标城市")
    parser.add_argument("--count", type=int, help="投递数量")
    parser.add_argument("--mode", help="运行模式：rehearsal 或 apply")
    parser.add_argument("--min-score", type=int, help="本次运行覆盖最低分阈值")
    parser.add_argument("--skill-dir", help="运行目录，用于存放 config.json、resume.md 和日志")
    parser.add_argument("--yes", action="store_true", help="自动确认已完成浏览器登录")
    return parser.parse_args()


def print_line(message: str = "") -> None:
    print(str(sanitize_json_text(message)), flush=True)


def prompt_text(label: str, default: str | None = None, *, required: bool = True) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = str(sanitize_json_text(input(f"{label}{suffix}: ").strip()))
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print_line("该项不能为空，请重新输入。")


def prompt_yes_no(label: str, *, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{suffix}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "是", "确认", "ok"}:
            return True
        if raw in {"n", "no", "否", "不", "取消"}:
            return False
        print_line("请输入 yes 或 no。")


def prompt_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print_line("请输入大于 0 的整数。")


def prompt_nonnegative_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit():
            return int(raw)
        print_line("请输入大于等于 0 的整数。")


def prompt_keywords(label: str, default: str | None = None) -> list[str]:
    text = prompt_text(label, default=default, required=False)
    return split_keywords(text)


def prompt_required_keywords(label: str) -> list[str]:
    while True:
        values = prompt_keywords(label)
        if values:
            return values
        print_line("该项不能为空，请至少填写 1 个关键词。")


def prompt_review_skills(skills: list[str]) -> list[str]:
    reviewed = dedupe_keep_order(skills)[:15]
    while True:
        print_line("\n请复查根据简历自动抽取的 skills：")
        for index, skill in enumerate(reviewed, start=1):
            print_line(f"{index}. {skill}")
        print_line("你可以接受这组 skills，也可以改成自己认可的 8-15 个关键词。")
        action = prompt_text("接受 / 编辑 / 取消", default="接受").strip().lower()
        if action in {"接受", "accept", "a", "yes", "y", "ok", "确认"}:
            if 8 <= len(reviewed) <= 15:
                return reviewed
            print_line("skills 数量需要在 8-15 个之间，请选择编辑。")
            continue
        if action in {"编辑", "edit", "e"}:
            edited = prompt_required_keywords("请输入最终 skills（8-15 个，用逗号分隔）")
            if 8 <= len(edited) <= 15:
                reviewed = edited
                continue
            print_line(f"当前填写了 {len(edited)} 个，skills 数量需要在 8-15 个之间。")
            continue
        if action in {"取消", "quit", "exit", "q"}:
            raise RuntimeError("用户取消首次引导。")
        print_line("请输入 接受、编辑 或 取消。")


def config_preview(config: dict[str, Any]) -> dict[str, Any]:
    llm = dict(config.get("llm", {}))
    return {
        "resume_path": config.get("resume_path", ""),
        "greeting": config.get("greeting", ""),
        "target_roles": config.get("target_roles", []),
        "exclude_keywords": config.get("exclude_keywords", []),
        "skills": config.get("skills", []),
        "min_score": config.get("min_score", 80),
        "default_count": config.get("default_count", 20),
        "default_mode": config.get("default_mode", "rehearsal"),
        "platform_ports": config.get("platform_ports", {}),
        "user_data_dirs": config.get("user_data_dirs", {}),
        "scoring": config.get("scoring", {}),
        "llm": {
            "base_url": llm.get("base_url", ""),
            "api_key": "***" if llm.get("api_key") else "",
            "model": llm.get("model", ""),
            "timeout": llm.get("timeout", 60),
            "temperature": llm.get("temperature", 0.2),
        },
    }


def prompt_scoring(defaults: dict[str, Any]) -> dict[str, Any]:
    print_line("\n评分标准会写入 config.json，你后续可以按自己的情况修改。")
    return {
        "role_title_score": prompt_nonnegative_int("岗位标题命中 target_roles 加分", int(defaults.get("role_title_score", 30))),
        "skill_score_each": prompt_nonnegative_int("每命中一个 skills 关键词加分", int(defaults.get("skill_score_each", 5))),
        "skill_score_cap": prompt_nonnegative_int("skills 关键词总加分上限", int(defaults.get("skill_score_cap", 30))),
        "llm_score_min": prompt_nonnegative_int("LLM/启发式补分最低分", int(defaults.get("llm_score_min", 1))),
        "llm_score_max": prompt_nonnegative_int("LLM/启发式补分最高分", int(defaults.get("llm_score_max", 40))),
        "heuristic_base_score": prompt_nonnegative_int("未配置 LLM 时的基础补分", int(defaults.get("heuristic_base_score", 6))),
        "heuristic_skill_score_each": prompt_nonnegative_int(
            "未配置 LLM 时每个技能命中的补分",
            int(defaults.get("heuristic_skill_score_each", 4)),
        ),
        "heuristic_skill_score_cap": prompt_nonnegative_int(
            "未配置 LLM 时技能补分上限",
            int(defaults.get("heuristic_skill_score_cap", 20)),
        ),
        "heuristic_role_score": prompt_nonnegative_int(
            "未配置 LLM 时岗位命中的补分",
            int(defaults.get("heuristic_role_score", 8)),
        ),
        "heuristic_bonus_keywords": prompt_keywords(
            "未配置 LLM 时的额外补分关键词",
            ",".join(str(item) for item in defaults.get("heuristic_bonus_keywords", [])),
        ),
        "heuristic_bonus_score": prompt_nonnegative_int(
            "命中额外补分关键词时加分",
            int(defaults.get("heuristic_bonus_score", 4)),
        ),
    }


def normalize_single_platform(raw: str) -> str:
    platforms = normalize_platforms(raw)
    if len(platforms) != 1:
        raise ValueError("当前入口一次只执行一个平台，请输入 Boss。")
    return platforms[0]


def prompt_platform() -> str:
    default_value = "Boss"
    while True:
        raw = prompt_text(
            "本次目标平台（Boss）",
            default=default_value,
            required=True,
        )
        try:
            return normalize_single_platform(raw)
        except ValueError as exc:
            print_line(str(exc))


def prompt_mode(config: dict[str, Any]) -> str:
    default_value = run_mode_label(normalize_run_mode(None, config))
    while True:
        raw = prompt_text(
            "本次运行模式（安全演练 或 正式投递）",
            default=default_value,
            required=True,
        )
        try:
            return normalize_run_mode(raw, config)
        except ValueError as exc:
            print_line(str(exc))


def ensure_resume_ready(config: dict[str, Any], *, skill_dir: Path) -> dict[str, Any]:
    config_file = skill_dir / "config.json"
    if not config_file.exists():
        return first_run_setup(skill_dir=skill_dir)

    if not config.get("resume_path"):
        print_line("检测到已有 config.json，但缺少 resume_path，重新进入首次引导。")
        return first_run_setup(skill_dir=skill_dir)

    try:
        read_resume_text(config["resume_path"], skill_dir=skill_dir)
        return config
    except Exception as exc:
        print_line(f"现有简历配置不可用：{exc}")
        print_line("将重新进入首次引导。")
        return first_run_setup(skill_dir=skill_dir)


def first_run_setup(*, skill_dir: Path) -> dict[str, Any]:
    print_line("\n[Step 1] 首次引导：准备 resume.md 并生成 config.json")
    default_resume = skill_dir / "resume.md"
    defaults = default_config()
    resume_default = str(default_resume)

    print_line(f"请先把你的简历保存为 resume.md，放到运行目录：{default_resume}")
    print_line("如果简历放在其他位置，也可以在下面输入完整路径。")
    print_line("接下来除 skills 外，其他配置项都由你填写；skills 会根据简历自动抽取 8-15 个关键点。")

    while True:
        resume_path = prompt_text("请输入 resume.md / resume.txt 路径", default=resume_default)
        try:
            read_resume_text(resume_path, skill_dir=skill_dir)
        except Exception as exc:
            print_line(f"简历文件暂时不可用：{exc}")
            print_line("请先把 resume.md 放到指定位置，或输入正确路径。\n")
            continue

        greeting = prompt_text("请输入打招呼话术", default=DEFAULT_GREETING)
        target_roles = prompt_required_keywords("请输入期望岗位关键词（多个用逗号分隔，例如 Java开发实习生,后端开发实习生）")
        exclude_keywords = prompt_keywords("请输入排除关键词（多个用逗号分隔，例如 销售,客服,培训）")
        min_score = prompt_int("最低匹配分阈值", int(defaults.get("min_score", 80)))
        default_count = prompt_int("默认检查/投递数量", int(defaults.get("default_count", 20)))
        default_mode = prompt_mode({**defaults, "default_mode": defaults.get("default_mode", "rehearsal")})
        boss_port = prompt_int("Boss直聘浏览器 CDP 端口", int(defaults["platform_ports"]["boss"]))
        boss_user_data_dir = prompt_text(
            "Boss直聘浏览器用户目录",
            default=str(defaults["user_data_dirs"]["boss"]),
        )
        llm_base_url = prompt_text("LLM base_url（可留空）", default="", required=False)
        llm_api_key = prompt_text("LLM api_key（可留空，也可改用环境变量）", default="", required=False)
        llm_model = prompt_text("LLM model（可留空）", default=str(defaults["llm"]["model"]), required=False)
        scoring = prompt_scoring(defaults.get("scoring", {}))
        manual_config = {
            "greeting": greeting,
            "target_roles": target_roles,
            "exclude_keywords": exclude_keywords,
            "min_score": min_score,
            "default_count": default_count,
            "default_mode": default_mode,
            "platform_ports": {"boss": boss_port},
            "user_data_dirs": {"boss": boss_user_data_dir},
            "scoring": scoring,
            "llm": {
                "base_url": llm_base_url,
                "api_key": llm_api_key,
                "model": llm_model or defaults["llm"]["model"],
                "timeout": int(defaults["llm"]["timeout"]),
                "temperature": float(defaults["llm"]["temperature"]),
            },
        }

        try:
            config, profile = initialize_config_from_resume(
                resume_path,
                target_roles=target_roles,
                exclude_keywords=exclude_keywords,
                base_config=manual_config,
                skill_dir=skill_dir,
            )
            config["greeting"] = greeting
            config["skills"] = prompt_review_skills(config["skills"])
            print_line("\n请复查即将写入 config.json 的配置摘要：")
            print_line(json.dumps(sanitize_json_text(config_preview(config)), ensure_ascii=False, indent=2))
            if not prompt_yes_no("确认写入 config.json", default=True):
                print_line("已取消写入。将重新进入首次引导。\n")
                continue
            config_path = save_config(config, skill_dir=skill_dir)
            print_line(f"\n已生成配置文件：{config_path}")
            print_line(
                "已写入本地私有配置："
                f"目标岗位 {len(config['target_roles'])} 个，"
                f"排除关键词 {len(config['exclude_keywords'])} 个，"
                f"自动抽取 skills {len(config['skills'])} 个，"
                f"最低分阈值 {config['min_score']}。"
            )
            print_line(f"初始化方式：{profile['source']} | {profile['note']}")
            return config
        except Exception as exc:
            print_line(f"首次引导失败：{exc}")
            print_line("请修正输入后重试。\n")


def collect_task(config: dict[str, Any], args: argparse.Namespace) -> JobTask:
    print_line("\n[Step 2] 收集本次投递任务信息")
    if args.platform:
        platform = normalize_single_platform(args.platform)
    else:
        platform = prompt_platform()
    target_roles = list(config.get("target_roles") or [])
    default_job = target_roles[0] if target_roles else None
    job_name = args.job or prompt_text("本次搜索岗位名", default=default_job)
    if job_name:
        config["target_roles"] = dedupe_keep_order([job_name, *target_roles])
    city = args.city or prompt_text("目标城市")
    count = args.count if args.count and args.count > 0 else prompt_int("投递数量", int(config.get("default_count", 20) or 20))
    mode = normalize_run_mode(args.mode, config) if args.mode else prompt_mode(config)
    return JobTask(job_name=job_name, city=city, count=count, platforms=[platform], mode=mode)


def print_browser_instructions(task: JobTask, config: dict[str, Any], *, skill_dir: Path) -> None:
    print_line("\n[Step 3] 请手动启动浏览器并完成登录")
    print_browser_login_instructions(
        platforms=task.platforms,
        config=config,
        skill_dir=skill_dir,
        print_func=print_line,
    )
    print_line("入口脚本会按平台分别接管各自端口，不再混用同一个浏览器会话。")


def wait_for_confirmation(*, auto_confirm: bool = False) -> bool:
    if auto_confirm:
        return True
    while True:
        answer = input("请输入 yes 继续，或输入 quit 退出: ").strip().lower()
        if answer == "yes":
            return True
        if answer in {"quit", "exit", "q", "no"}:
            return False
        print_line("未识别输入，请输入 yes 或 quit。")


def load_platform_runner(platform: str) -> tuple[Callable[..., Any] | None, Path]:
    script_info = SCRIPT_REGISTRY[platform]
    script_path = CODE_DIR / f"{script_info['module']}.py"
    if not script_path.exists():
        return None, script_path

    module_name = f"boss.{script_info['module']}"
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载平台脚本：{script_path}")

    module = importlib.import_module(module_name)

    for func_name in script_info["functions"]:
        runner = getattr(module, func_name, None)
        if callable(runner):
            return runner, script_path

    raise RuntimeError(
        f"{script_path.name} 中未找到可调用入口，请实现以下任一函数："
        f"{', '.join(script_info['functions'])}"
    )


def invoke_runner(
    runner: Callable[..., Any],
    *,
    task: JobTask,
    config: dict[str, Any],
    browser: Any,
    skill_dir: Path,
) -> Any:
    signature = inspect.signature(runner)
    call_kwargs: dict[str, Any] = {}
    for parameter in signature.parameters:
        if parameter == "task":
            call_kwargs["task"] = task
        elif parameter == "config":
            call_kwargs["config"] = config
        elif parameter == "browser":
            call_kwargs["browser"] = browser
        elif parameter == "skill_dir":
            call_kwargs["skill_dir"] = skill_dir

    return runner(**call_kwargs)


def print_platform_result(platform: str, result: Any) -> None:
    label = platform_label(platform)
    if result is None:
        print_line(f"{label} 执行完成。")
        return

    if isinstance(result, dict):
        compact = {
            key: value
            for key, value in result.items()
            if key in {"mode", "run_id", "applied", "reviewed", "skipped", "failed", "count", "min_score", "message"}
        }
        if compact:
            print_line(f"{label} 结果：{json.dumps(compact, ensure_ascii=False)}")
            return

    print_line(f"{label} 执行完成，返回：{result}")


def dispatch_platforms(task: JobTask, config: dict[str, Any], *, skill_dir: Path) -> int:
    logger = get_logger(skill_dir=skill_dir)
    executed = 0

    print_line("\n[Step 4] 执行平台投递脚本")
    print_line("说明：当前入口只执行你本次指定的平台，并连接它自己的独立浏览器端口。")

    for platform in task.platforms:
        label = platform_label(platform)
        debug_port = platform_debug_port(platform, config)
        print_line(f"\n开始执行：{label}")
        try:
            runner, script_path = load_platform_runner(platform)
            if runner is None:
                print_line(
                    f"{label} 对应脚本尚未创建：{script_path.name}。"
                    " 入口调度已预留，后续补完适配器即可直接接上。"
                )
                continue

            print_line(f"{label} 将接管你已手动打开的浏览器端口 {debug_port}。")
            browser = connect_browser(debug_port=debug_port)
            platform_task = JobTask(
                job_name=task.job_name,
                city=task.city,
                count=task.count,
                platforms=[platform],
                mode=task.mode,
                debug_port=debug_port,
            )
            print_line(f"{label} 搜索词：{platform_task.job_name}")
            result = invoke_runner(
                runner,
                task=platform_task,
                config=config,
                browser=browser,
                skill_dir=skill_dir,
            )
            print_platform_result(platform, result)
            executed += 1
        except Exception as exc:
            logger.exception("%s 执行失败", label)
            print_line(f"{label} 执行失败：{exc}")

    return executed


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    runtime_dir = resolve_skill_dir(args.skill_dir)
    logger = get_logger(skill_dir=runtime_dir)
    print_line("Job Hunter 启动中。")
    print_line("流程：配置检查 -> 首次引导/读取配置 -> 收集任务 -> 手动登录浏览器 -> 自动调度平台脚本。\n")
    print_line(f"代码目录：{CODE_DIR}")
    print_line(f"运行目录：{runtime_dir}")

    try:
        config = ensure_resume_ready(load_config(skill_dir=runtime_dir), skill_dir=runtime_dir)
        runtime_config = dict(config)
        if args.min_score is not None:
            runtime_config["min_score"] = int(args.min_score)
        print_line(
            f"当前配置：目标岗位 {len(config.get('target_roles') or [])} 个，"
            f"skills {len(config.get('skills') or [])} 个，"
            f"最低投递分={runtime_config.get('min_score', 80)}，"
            f"默认模式={run_mode_label(normalize_run_mode(None, runtime_config))}。"
        )

        task = collect_task(runtime_config, args)
        print_line(
            f"本次任务：平台={platform_label(task.platforms[0])}，模式={run_mode_label(task.mode)}，"
            f"岗位={task.job_name}，城市={task.city}，数量={task.count}。"
        )
        print_browser_instructions(task, runtime_config, skill_dir=runtime_dir)
        if not wait_for_confirmation(auto_confirm=args.yes):
            print_line("用户取消执行，本次任务结束。")
            return 0

        for platform in task.platforms:
            print_line(
                f"{platform_label(platform)} 预期端口：{platform_debug_port(platform, runtime_config)}"
            )

        executed = dispatch_platforms(task, runtime_config, skill_dir=runtime_dir)
        if executed == 0:
            print_line(
                "\n本次没有成功执行任何平台脚本。请检查浏览器登录状态、平台适配器文件和日志。"
            )
        else:
            print_line(f"\n本次共执行了 {executed} 个平台脚本。当前模式为单平台调度。")
        return 0
    except KeyboardInterrupt:
        print_line("\n用户中断执行。")
        return 130
    except Exception as exc:
        logger.exception("Job Hunter 运行失败")
        print_line(f"\n运行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
