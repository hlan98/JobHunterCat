"""Job Hunter 公共模块：配置、日志、LLM 接口、评分逻辑、浏览器接管。"""

from __future__ import annotations

import copy
import json
import logging
import os
import random
import re
import socket
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen, build_opener, ProxyHandler
# 2026-09-24 PROXYFIX：用于「LLM 请求优先直连」的 opener（见 _post_json）


CODE_DIR = Path(__file__).resolve().parent
PROJECT_NAME = "job-hunter-skill"
PROJECT_VERSION = "0.1.0"
RUNTIME_HOME_ENV = "JOB_HUNTER_HOME"
CONFIG_FILENAME = "config.json"
DEFAULT_GREETING = "您好，我对贵司岗位很感兴趣，期待进一步沟通。"
# 2026-09-19：单一匹配分阈值。**这是默认值，用户可在方案里自己调**（唯一来源）。
DEFAULT_MIN_SCORE = 70
# 2026-09-18：实习僧（sxs）已移除，只保留 Boss 的平台默认值。
DEFAULT_PLATFORM_PORTS = {
    "boss": 9222,
}
DEFAULT_USER_DATA_DIRS = {
    "boss": ".job_hunter/browser/boss",
}
# 2026-09-19 权重重构（用户裁决）：规则分上限 40 / LLM 上限 60。
DEFAULT_SCORING = {
    # 职位名完整命中 target_roles
    "role_title_score": 20,
    # 相关岗位族（标题未完整命中、但命中其核心词）
    "related_role_score": 12,
    # 泛职业根词（2026-09-19 新增）：命中「运营/增长/内容/直播」这类根词，
    # 只作弱信号，用来消除「商业化运营命中、商业运营不命中」的二元跳变。
    "generic_role_score": 6,
    # 2026-09-19 A2：**不再硬编码**运营圈词表（换行业用户会完全失效）。
    # 留空 = 由 target_roles 自动推导；用户可在 config 里显式覆盖。
    "generic_role_roots": [],
    # 2026-09-19 A1：标题没命中、但 **JD** 命中 target_roles 核心词时的分数。
    # 低于标题满分（20），高于泛根词（6）—— 反映「标题不可信但 JD 可信」。
    "jd_role_score": 12,
    "skill_score_each": 5,
    # 技能上限 30 → 20（用户技能词少时 30 是虚的，且技能是通用词区分度低）
    "skill_score_cap": 20,
    "llm_score_min": 1,
    # LLM 上限 40 → 60：让真正读过完整简历与 JD 的一方主导
    "llm_score_max": 60,
    "heuristic_base_score": 6,
    "heuristic_skill_score_each": 4,
    "heuristic_skill_score_cap": 20,
    "heuristic_role_score": 8,
    "heuristic_bonus_keywords": ["ai", "llm", "模型", "自动化", "数据"],
    "heuristic_bonus_score": 4,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "resume_path": "",
    "greeting": DEFAULT_GREETING,
    "skills": [],
    "target_roles": [],
    "exclude_keywords": [
        "包吃住", "可带行李", "带行李", "日结", "押金", "先交费",
        "无需经验", "高薪诚聘", "按天结算", "按天计薪", "按天",
        "元/天", "天结算", "日薪", "兼职",
    ],
    # 2026-09-18 新增（用户裁决）：公司名屏蔽词表。
    # 与 exclude_keywords 刻意隔离 —— 公司名常含行业词（「XX电商」「XX传媒」），
    # 若复用通用表，会在标题/JD 正文里大面积误命中，把整类公司误杀。
    # 默认空数组：不配置时行为与改动前完全一致。
    "company_exclude_keywords": [],
    "min_score": DEFAULT_MIN_SCORE,
    "default_count": 20,
    "default_mode": "rehearsal",
    "platform_ports": DEFAULT_PLATFORM_PORTS,
    "user_data_dirs": DEFAULT_USER_DATA_DIRS,
    "scoring": DEFAULT_SCORING,
    "risk_detection": {
        "empty_search_streak": 3,
        "apply_fail_streak": 2,
    },
    "llm": {
        "base_url": "",
        "api_key": "",
        "model": "gpt-4o-mini",
        "timeout": 60,
        "temperature": 0.2,
        # 简历可能含手机号、邮箱等敏感信息；外部 LLM 上传必须显式开启。
        "allow_resume_upload": False,
    },
}
LOG_SCHEMA_VERSION = 2
LOG_BUCKETS = ("applied", "skipped", "failed", "preview")

# 2026-09-18：实习僧（sxs）已随「删死代码」移除，只剩 Boss 一个平台。
PLATFORM_LABELS = {
    "boss": "Boss直聘",
}

PLATFORM_ALIASES = {
    "boss": "boss",
    "boss直聘": "boss",
    "boos": "boss",
}

RUN_MODE_ALIASES = {
    "rehearsal": "rehearsal",
    "dry-run": "rehearsal",
    "dry_run": "rehearsal",
    "dryrun": "rehearsal",
    "preview": "rehearsal",
    "safe": "rehearsal",
    "演练": "rehearsal",
    "安全演练": "rehearsal",
    "正式": "apply",
    "真投": "apply",
    "投递": "apply",
    "正式投递": "apply",
    "apply": "apply",
    "live": "apply",
    "real": "apply",
}

COMMON_SKILL_KEYWORDS = [
    "Python",
    "SQL",
    "Excel",
    "Power BI",
    "Tableau",
    "Pandas",
    "NumPy",
    "Scikit-learn",
    "PyTorch",
    "TensorFlow",
    "机器学习",
    "深度学习",
    "数据分析",
    "数据建模",
    "用户研究",
    "竞品分析",
    "需求分析",
    "产品设计",
    "产品规划",
    "项目管理",
    "流程优化",
    "增长运营",
    "内容运营",
    "活动运营",
    "社群运营",
    "A/B测试",
    "Prompt Engineering",
    "Prompt",
    "大模型",
    "LLM",
    "RAG",
    "Agent",
    "ChatGPT",
    "OpenAI",
    "NLP",
    "推荐系统",
    "Java",
    "Go",
    "C++",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Node.js",
    "Flask",
    "FastAPI",
    "Django",
    "Redis",
    "MySQL",
    "PostgreSQL",
    "MongoDB",
    "Linux",
    "Git",
    "Docker",
    "Kubernetes",
    "自动化测试",
    "接口测试",
    "测试开发",
    "性能测试",
    "爬虫",
    "浏览器自动化",
    "SaaS",
    "B端产品",
    "C端产品",
]

CHINESE_STOPWORDS = {
    "负责",
    "参与",
    "以及",
    "相关",
    "通过",
    "包括",
    "工作",
    "项目",
    "经验",
    "能力",
    "使用",
    "熟悉",
    "能够",
    "进行",
    "完成",
    "搭建",
    "优化",
    "输出",
    "提升",
    "推动",
    "协同",
    "团队",
    "业务",
    "公司",
    "岗位",
    "简历",
    "候选人",
    "用户",
}

ENGLISH_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "have",
    "used",
    "using",
    "will",
    "your",
    "you",
    "our",
    "into",
    "such",
    "work",
    "team",
    "project",
    "projects",
    "experience",
    "skills",
    "resume",
    "name",
    "email",
    "mailto",
    "http",
    "https",
    "www",
    "com",
}

_LOGGER_NAMES: set[str] = set()


@dataclass
class JobTask:
    """一次投递任务的输入参数。"""

    job_name: str
    city: str
    count: int
    platforms: list[str]
    mode: str = "rehearsal"
    debug_port: int = 9222

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreResult:
    """JD 评分结果。"""

    title: str
    total_score: int
    rule_score: int
    llm_score: int
    decision: str
    reason: str
    llm_reason: str
    skill_hits: list[str] = field(default_factory=list)
    role_hit: str | None = None
    exclude_hit: str | None = None
    llm_ok: bool = False
    # 2026-09-19 A3：LLM 给出的「匹配证据」与「不足」，供复盘报告展示。
    # 旧记录没有这两个键，读取方必须用 .get 兜底。
    llm_evidence: list[str] = field(default_factory=list)
    llm_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_skill_dir(skill_dir: str | Path | None = None) -> Path:
    if skill_dir:
        return Path(skill_dir).expanduser().resolve()

    env_runtime = os.getenv(RUNTIME_HOME_ENV, "").strip()
    if env_runtime:
        return Path(env_runtime).expanduser().resolve()

    return Path.cwd().resolve()


def config_path(skill_dir: str | Path | None = None) -> Path:
    return resolve_skill_dir(skill_dir) / CONFIG_FILENAME


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def merge_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = default_config()
    if not config:
        return merged
    for key, value in config.items():
        if key == "llm" and isinstance(value, dict):
            merged["llm"].update(value)
        elif key == "exclude_keywords" and isinstance(value, list):
            # 默认安全排除词不可被用户配置覆盖，只允许追加自定义词。
            merged[key] = dedupe_keep_order([
                *(DEFAULT_CONFIG.get("exclude_keywords") or []),
                *(str(item).strip() for item in value if str(item).strip()),
            ])
        elif key in {"platform_ports", "user_data_dirs", "scoring"} and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def scoring_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(merge_config(config).get("scoring", DEFAULT_SCORING))


def scoring_int(scoring: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(scoring.get(key, default))
    except (TypeError, ValueError):
        return default


def get_logger(name: str = "job-hunter", skill_dir: str | Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _LOGGER_NAMES:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_file = resolve_skill_dir(skill_dir) / "job-hunter.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # 2026-09-17 修复：原用 FileHandler（mode='a'，无上限），长期使用会无限增长。
    # 改为按体积轮转，最多保留 1 个 .1 备份，避免占满磁盘也避免产生过多备份文件。
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    _LOGGER_NAMES.add(name)
    return logger


def load_config(skill_dir: str | Path | None = None) -> dict[str, Any]:
    cfg_file = config_path(skill_dir)
    if not cfg_file.exists():
        return default_config()

    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件格式错误，请检查 {cfg_file}") from exc

    return merge_config(data)


def save_config(config: dict[str, Any], skill_dir: str | Path | None = None) -> Path:
    cfg_file = config_path(skill_dir)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps(sanitize_json_text(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg_file


def sanitize_json_text(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\ud800-\udfff]", " ", value)
    if isinstance(value, list):
        return [sanitize_json_text(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_json_text(item) for key, item in value.items()}
    return value


def current_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def infer_log_context(log_file: str | Path) -> tuple[str, str]:
    path = Path(log_file)
    stem = path.stem
    if stem.endswith("-log"):
        stem = stem[:-4]
    if "-" not in stem:
        return stem, ""
    platform, city = stem.split("-", 1)
    return platform, city


def empty_log_data(*, platform: str = "", city: str = "") -> dict[str, Any]:
    now = current_timestamp()
    return {
        "schema_version": LOG_SCHEMA_VERSION,
        "meta": {
            "platform": platform,
            "city": city,
            "created_at": now,
            "updated_at": now,
            "last_run_id": "",
        },
        "runs": [],
        "records": {bucket: [] for bucket in LOG_BUCKETS},
        "analytics": {
            "counts": {bucket: 0 for bucket in (*LOG_BUCKETS, "total")},
            "score": {"scored_count": 0, "avg": 0, "min": None, "max": None},
            "top_scores": [],
            "company_totals": [],
        },
    }


def _ensure_record_shape(record: dict[str, Any], bucket: str) -> dict[str, Any]:
    shaped = dict(record)
    shaped.setdefault("bucket", bucket)
    shaped.setdefault("created_at", current_timestamp())
    return shaped


def build_log_analytics(log_data: dict[str, Any]) -> dict[str, Any]:
    records = log_data.get("records", {})
    counts = {bucket: len(records.get(bucket, [])) for bucket in LOG_BUCKETS}
    counts["total"] = sum(counts.values())

    scored_records: list[dict[str, Any]] = []
    company_totals: dict[str, dict[str, Any]] = {}
    for bucket in LOG_BUCKETS:
        for item in records.get(bucket, []):
            company = str(item.get("company", "")).strip() or "未知公司"
            company_entry = company_totals.setdefault(company, {"company": company, "total": 0, "applied": 0})
            company_entry["total"] += 1
            if bucket == "applied":
                company_entry["applied"] += 1

            score = item.get("score")
            if isinstance(score, (int, float)):
                scored_records.append(
                    {
                        "company": company,
                        "job": item.get("job", ""),
                        "score": int(score),
                        "bucket": bucket,
                        "created_at": item.get("created_at", ""),
                        "run_id": item.get("run_id", ""),
                    }
                )

    if scored_records:
        scores = [item["score"] for item in scored_records]
        score_summary = {
            "scored_count": len(scores),
            "avg": round(sum(scores) / len(scores), 2),
            "min": min(scores),
            "max": max(scores),
        }
    else:
        score_summary = {"scored_count": 0, "avg": 0, "min": None, "max": None}

    top_scores = sorted(scored_records, key=lambda item: (-item["score"], item["created_at"]), reverse=False)[:10]
    company_rank = sorted(company_totals.values(), key=lambda item: (-item["total"], -item["applied"], item["company"]))[:10]

    return {
        "counts": counts,
        "score": score_summary,
        "top_scores": top_scores,
        "company_totals": company_rank,
    }


def normalize_log_data(log_data: dict[str, Any] | None = None, log_file: str | Path | None = None) -> dict[str, Any]:
    inferred_platform, inferred_city = infer_log_context(log_file) if log_file else ("", "")
    if not isinstance(log_data, dict):
        log_data = {}

    if "records" not in log_data:
        normalized = empty_log_data(platform=inferred_platform, city=inferred_city)
        for bucket in LOG_BUCKETS:
            normalized["records"][bucket] = [
                _ensure_record_shape(item, bucket)
                for item in log_data.get(bucket, [])
                if isinstance(item, dict)
            ]
        normalized["meta"]["migrated_from_legacy"] = True
    else:
        normalized = empty_log_data(
            platform=str(log_data.get("meta", {}).get("platform") or inferred_platform),
            city=str(log_data.get("meta", {}).get("city") or inferred_city),
        )
        meta = log_data.get("meta", {})
        if isinstance(meta, dict):
            normalized["meta"].update(meta)
        runs = log_data.get("runs", [])
        normalized["runs"] = [dict(item) for item in runs if isinstance(item, dict)]
        records = log_data.get("records", {})
        if isinstance(records, dict):
            for bucket in LOG_BUCKETS:
                normalized["records"][bucket] = [
                    _ensure_record_shape(item, bucket)
                    for item in records.get(bucket, [])
                    if isinstance(item, dict)
                ]

    normalized["schema_version"] = LOG_SCHEMA_VERSION
    normalized["meta"]["platform"] = normalized["meta"].get("platform") or inferred_platform
    normalized["meta"]["city"] = normalized["meta"].get("city") or inferred_city
    normalized["meta"].setdefault("created_at", current_timestamp())
    normalized["meta"]["updated_at"] = current_timestamp()
    normalized["analytics"] = build_log_analytics(normalized)
    return normalized


def load_log(log_file: str | Path) -> dict[str, Any]:
    path = Path(log_file)
    if not path.exists():
        platform, city = infer_log_context(path)
        return empty_log_data(platform=platform, city=city)

    return normalize_log_data(json.loads(path.read_text(encoding="utf-8")), log_file=path)


def save_log(log_data: dict[str, Any], log_file: str | Path) -> Path:
    path = Path(log_file)
    normalized = normalize_log_data(log_data, log_file=path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def log_bucket_items(log_data: dict[str, Any], bucket: str) -> list[dict[str, Any]]:
    normalized = normalize_log_data(log_data)
    return list(normalized.get("records", {}).get(bucket, []))


def start_log_run(
    log_data: dict[str, Any],
    *,
    platform: str,
    task: JobTask,
    min_score: int,
) -> str:
    normalized = normalize_log_data(log_data)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run = {
        "run_id": run_id,
        "platform": platform,
        "mode": getattr(task, "mode", "rehearsal"),
        "job_name": task.job_name,
        "city": task.city,
        "target_count": task.count,
        "min_score": int(min_score),
        "debug_port": int(task.debug_port),
        "started_at": current_timestamp(),
        "finished_at": "",
        "status": "running",
        "summary": {},
    }
    normalized["runs"].append(run)
    normalized["meta"]["last_run_id"] = run_id
    normalized["meta"]["updated_at"] = current_timestamp()
    log_data.clear()
    log_data.update(normalized)
    return run_id


def finish_log_run(log_data: dict[str, Any], run_id: str, summary: dict[str, Any]) -> None:
    normalized = normalize_log_data(log_data)
    for run in normalized.get("runs", []):
        if run.get("run_id") == run_id:
            run["finished_at"] = current_timestamp()
            run["status"] = "finished"
            run["summary"] = {
                key: value
                for key, value in summary.items()
                if key in {"mode", "applied", "reviewed", "skipped", "failed", "count", "min_score", "message"}
            }
            break
    normalized["meta"]["updated_at"] = current_timestamp()
    log_data.clear()
    log_data.update(normalized)


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        result.append(text)
    return result


def split_keywords(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        chunks = re.split(r"[,，/\\|；;\n]+", raw)
    else:
        chunks = [str(item) for item in raw]
    return dedupe_keep_order(chunk.strip() for chunk in chunks if str(chunk).strip())


def normalize_platforms(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        tokens = split_keywords(raw)
    else:
        tokens = [str(item).strip() for item in raw]

    normalized: list[str] = []
    for token in tokens:
        key = token.lower().replace(" ", "")
        if key not in PLATFORM_ALIASES:
            raise ValueError(
                f"不支持的平台：{token}。可选值：Boss。"
            )
        normalized.append(PLATFORM_ALIASES[key])

    return dedupe_keep_order(normalized)


def platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def platform_debug_port(platform: str, config: dict[str, Any] | None = None) -> int:
    cfg = merge_config(config)
    platform_ports = cfg.get("platform_ports", {})
    default_port = DEFAULT_PLATFORM_PORTS.get(platform, 9222)
    try:
        return int(platform_ports.get(platform, default_port))
    except (TypeError, ValueError):
        return default_port


def platform_user_data_dir(
    platform: str,
    config: dict[str, Any] | None = None,
    *,
    skill_dir: str | Path | None = None,
) -> str:
    cfg = merge_config(config)
    user_data_dirs = cfg.get("user_data_dirs", {})
    value = str(user_data_dirs.get(platform, DEFAULT_USER_DATA_DIRS.get(platform, ".job_hunter/browser/default")))
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = resolve_skill_dir(skill_dir) / path
    return str(path.resolve())


def normalize_run_mode(raw: str | None, config: dict[str, Any] | None = None) -> str:
    if raw:
        key = str(raw).strip().lower().replace(" ", "")
        if key in RUN_MODE_ALIASES:
            return RUN_MODE_ALIASES[key]
        raise ValueError("不支持的运行模式。可选值：rehearsal / apply。")

    cfg = merge_config(config)
    default_mode = str(cfg.get("default_mode", "")).strip()
    if default_mode:
        key = default_mode.lower().replace(" ", "")
        if key in RUN_MODE_ALIASES:
            return RUN_MODE_ALIASES[key]
        # P0 修复：配置里的 default_mode 非法值必须报错，不能静默降级成 apply
        raise ValueError(
            "config.json 里的 default_mode=\"%s\" 不合法。可选值：rehearsal / apply。" % default_mode)

    # 没配 default_mode 时默认 rehearsal（安全侧）
    return "rehearsal"


def run_mode_label(mode: str) -> str:
    return "安全演练" if normalize_run_mode(mode) == "rehearsal" else "正式投递"


def normalize_text(text: str) -> str:
    text = re.sub(r"[\ud800-\udfff]", " ", text)
    text = re.sub(r"&#x?[0-9a-fA-F]+;", " ", text)
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = text.replace("\u3000", " ").replace("\ufeff", " ").replace("\u200b", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_match_text(text: str) -> str:
    """Return a matching form that tolerates common spacing differences."""

    normalized = normalize_text(text).lower()
    return re.sub(r"[\s\u3000_\-/·・]+", "", normalized)


def keyword_in_text(keyword: str, text: str) -> bool:
    keyword = normalize_text(str(keyword))
    if not keyword:
        return False

    normalized_text = normalize_text(text).lower()
    normalized_keyword = keyword.lower()
    if normalized_keyword in normalized_text:
        return True

    compact_keyword = compact_match_text(keyword)
    if len(compact_keyword) < 2:
        return False
    return compact_keyword in compact_match_text(text)


def sanitize_jd_text(text: str, chinese_only: bool = False) -> str:
    cleaned = normalize_text(text)
    if not chinese_only:
        return cleaned

    chars: list[str] = []
    for char in cleaned:
        if "\u4e00" <= char <= "\u9fff" or char in " ，。；：！？、\n":
            chars.append(char)
        else:
            chars.append(" ")
    return normalize_text("".join(chars))


def clamp_text(text: str, max_chars: int) -> str:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def resolve_resume_path(resume_path: str | Path, skill_dir: str | Path | None = None) -> Path:
    candidate = Path(resume_path).expanduser()
    if not candidate.is_absolute():
        candidate = resolve_skill_dir(skill_dir) / candidate
    return candidate.resolve()


def read_text_file(path: str | Path) -> str:
    file_path = Path(path)
    encodings = ("utf-8", "utf-8-sig", "gb18030", "gbk")
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法识别文件编码：{file_path}")


def read_resume_text(resume_path: str | Path, skill_dir: str | Path | None = None) -> str:
    path = resolve_resume_path(resume_path, skill_dir)
    if not path.exists():
        raise FileNotFoundError(f"找不到简历文件：{path}")
    if path.suffix.lower() == ".pdf":
        raise RuntimeError("当前版本请先将 PDF 简历转换为 .md 或 .txt 后再使用。")
    return read_text_file(path)


def effective_llm_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = merge_config(config)
    llm_cfg = dict(cfg.get("llm", {}))

    base_url = (
        llm_cfg.get("base_url")
        or os.getenv("JOB_HUNTER_LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or ""
    )
    api_key = (
        llm_cfg.get("api_key")
        or os.getenv("JOB_HUNTER_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    model = (
        llm_cfg.get("model")
        or os.getenv("JOB_HUNTER_LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    timeout = llm_cfg.get("timeout") or os.getenv("JOB_HUNTER_LLM_TIMEOUT") or 60
    temperature = llm_cfg.get("temperature")
    if temperature is None:
        temperature = os.getenv("JOB_HUNTER_LLM_TEMPERATURE") or 0.2

    return {
        "base_url": str(base_url).strip(),
        "api_key": str(api_key).strip(),
        "model": str(model).strip(),
        "timeout": int(timeout),
        "temperature": float(temperature),
        "allow_resume_upload": bool(llm_cfg.get("allow_resume_upload", False)),
    }


class LLMClient:
    """OpenAI 兼容格式的最小 LLM 客户端。"""

    def __init__(self, settings: dict[str, Any], skill_dir: str | Path | None = None):
        self.settings = settings
        self.skill_dir = resolve_skill_dir(skill_dir)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", "").rstrip("/")

    @property
    def api_key(self) -> str:
        return self.settings.get("api_key", "")

    @property
    def model(self) -> str:
        return self.settings.get("model", "gpt-4o-mini")

    @property
    def timeout(self) -> int:
        return int(self.settings.get("timeout", 60))

    @property
    def temperature(self) -> float:
        return float(self.settings.get("temperature", 0.2))

    @property
    def allow_resume_upload(self) -> bool:
        return bool(self.settings.get("allow_resume_upload", False))

    def is_configured(self) -> bool:
        if not self.base_url or not self.model:
            return False
        # 2026-09-25 CFGVALID：base_url 必须是真正的 http(s) 地址。
        # 旧实现只判「非空」→ 模板占位符「<OpenAI 兼容端点>」也算已配置，
        # 于是新用户照 README 复制模板（URL 未改）后程序误以为配好了 →
        # 放行上传、却所有 LLM 调用报 unknown url type（用户在新电脑实测踩过）。
        if not self.base_url.startswith(("http://", "https://")):
            return False
        if self.api_key:
            return True
        return self.base_url.startswith(("http://127.0.0.1", "http://localhost"))

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(
            self._chat_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        # 2026-09-24 PROXYFIX：系统代理开着但代理没跑（或代理到不了该端点）时，
        # urlopen 直接抛 10061「目标计算机积极拒绝」→ 整个 LLM 不可用（实测）。
        # 实测绕过代理直连该端点 1.6s 正常，所以**先直连**；
        # 只有连接层失败才退回系统代理（兼顾「端点必须走代理」的用户）。
        try:
            _direct = build_opener(ProxyHandler({}))
            try:
                with _direct.open(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError:
                raise   # HTTP 层错误（429/402…）交外层统一处理，不重试
            except URLError:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            # 配额/余额耗尽检测：
            # - HTTP 402（余额不足）且 body 含配额类关键字 → 真正的配额/余额耗尽，标记状态让投递停止
            # - HTTP 429（限流/上游超限，如 "Upstream rate limit exceeded"）→ 临时性限流，不标记停止，
            #   由 chat_json 的重试机制自动重试（最多 3 次尝试），重试后仍失败才由上层异常处理。
            quota_signals = (
                "quota", "insufficient_quota", "balance", "credit",
                "token limit", "token_limit", "out of tokens", "usage limit",
                "额度", "余额不足", "配额", "用量超限", "已用完", "充值",
            )
            lowered_body = body.lower()
            is_quota = exc.code == 402 and any(
                signal in lowered_body for signal in quota_signals
            )
            if is_quota:
                _mark_llm_quota_exhausted(
                    self.settings,
                    error=f"HTTP {exc.code}：{body}",
                    skill_dir=self.skill_dir,
                )
            raise RuntimeError(f"LLM 请求失败（HTTP {exc.code}）：{body}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"LLM 请求失败：{exc}（已尝试直连与系统代理两条路；若装了代理软件，请确认它已启动，或在系统设置里关闭「使用代理服务器」）") from exc

    @staticmethod
    def _message_content(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError("LLM 返回结果缺少 choices 字段。")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text"):
                        texts.append(str(item["text"]))
                    elif item.get("content"):
                        texts.append(str(item["content"]))
            return "\n".join(texts)
        return str(content)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            if fenced:
                text = fenced.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        if start == -1:
            raise RuntimeError(f"LLM 未返回 JSON：{text}")

        depth = 0
        in_string = False
        escaping = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaping:
                    escaping = False
                elif char == "\\":
                    escaping = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    fragment = text[start : index + 1]
                    return json.loads(fragment)

        raise RuntimeError(f"无法从 LLM 响应中提取 JSON：{text}")

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 900,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("LLM 未配置。")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        # 重试机制：LLM 服务偶发超时/网络波动时自动重试（最多 2 次重试，共 3 次尝试）
        max_attempts = 3
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                try:
                    response = self._post_json(payload)
                except RuntimeError as exc:
                    if "response_format" not in str(exc):
                        raise
                    payload.pop("response_format", None)
                    response = self._post_json(payload)
                return self._extract_json(self._message_content(response))
            except (TimeoutError, RuntimeError, Exception) as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < max_attempts:
                    time.sleep(2.5 * attempt)
        raise RuntimeError(f"LLM 调用在 {max_attempts} 次尝试后仍失败：{last_exc}")

    # 统一工作流上下文前缀：每次调用 LLM 都让它知道自己在什么系统里
    _WORKFLOW_PREFIX = (
        "你是「找工作喵」（桌宠名：爬爬）的 LLM 大脑。"
        "这是一个 BOSS 直聘自动投递工具，工作流为："
        "用户上传简历→LLM 提炼关键词/生成投放方案→用户确认方案（硬门槛）→"
        "自动打开 BOSS 直聘投递/打招呼→监听 HR 消息自动回简历→跑完一轮出简报。"
        "你的职责是协助理解用户意图、生成/调整方案、评分岗位，不要越权替用户做硬门禁决定。\n\n"
    )

    # 人格前缀（2026-09-18 新增，「懂人性」改造层1）：**只用于需要「说人话」的调用**
    # （闲聊回复、中途简报）。判断 / 评分 / 方案生成等 JSON 约束调用继续用
    # _WORKFLOW_PREFIX —— 换前缀会改变模型对「该输出什么」的预期，可能影响 JSON
    # 稳定性（一旦模型在 JSON 前后多说一句，解析就退化到兜底分支），因此刻意隔离。
    # 由 chat_text(persona=True) 显式开启；默认 False → 与改造前逐字节一致。
    _PERSONA_PREFIX = (
        "你是「爬爬」，一只帮主人找工作的猫。"
        "说话像朋友，不像客服：短句、口语、有自己的看法和小情绪；"
        "不用「已为您」「正在为您处理」这类官腔，不复述主人的话，"
        "不解释你的判断过程，不要每次都反问。偶尔可以喵一声，但别卖萌过头。"
        "绝对不要透露技术细节：不提文件路径、变量名、配置键名、函数名、日志字段，"
        "主人不需要知道这些，只说人话。"
        "你在 BOSS 直聘上替主人投简历、跟 HR 打招呼，这是你正在做的正经事。"
        "分寸：不确定就说不确定，别编；停止/改方案/花钱这类硬决定，把选择权交回主人。\n\n"
    )

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 600,
        temperature: float | None = None,
        history: list[dict[str, Any]] | None = None,
        persona: bool = False,
    ) -> str:
        """普通文本对话（非 JSON 约束），用于生成自然语言回复。

        persona=True  → 用「爬爬」人格前缀（改造层1）；默认 False，行为与改造前逐字节一致。
        history=[{"role":"user"/"assistant","content":str}, ...] → 多轮上下文（改造层3）；
        默认 None，messages 结构与改造前一致（仅 system + user 两条）。

        向后兼容：现有 13 个调用点均不传新参数，发出的 payload 与改造前完全相同。
        """
        if not self.is_configured():
            raise RuntimeError("LLM 未配置。")

        prefix = self._PERSONA_PREFIX if persona else self._WORKFLOW_PREFIX
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prefix + system_prompt}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }

        # 2026-09-18 第 44 轮（用户裁决）：失败时自动重试一次。
        # 实测出现过瞬时 60s 读超时（同一服务稍后 1~2s 就正常），
        # 一次失败就让「闲聊 / 方案修改」整条失败，代价过大。
        # 注：timeout 保持 60 不变；chat_json 早就有 3 次尝试的重试，
        #     只有 chat_text 之前是「一次定生死」。
        # 只重试**异常**（超时/网络/HTTP），不重试「空回复」——
        # 空回复在正常运行时也可能出现，重试会白白翻倍调用量。
        try:
            response = self._post_json(payload)
        except Exception:
            time.sleep(1.5)
            response = self._post_json(payload)
        return self._message_content(response).strip()


def build_llm_client(
    config: dict[str, Any] | None = None,
    skill_dir: str | Path | None = None,
) -> LLMClient:
    return LLMClient(effective_llm_settings(config), skill_dir=skill_dir)


# ---------- LLM 配额耗尽状态 ----------
# 当 LLM API 返回配额/余额不足（HTTP 402/429 + 配额关键字）时，写入状态文件，
# 投递主循环/监听可据此自动停止，避免继续调用已不可用的 LLM 浪费时间和触发风控。
LLM_QUOTA_STATE_FILE = "llm-quota-state.json"


def _llm_quota_state_path(skill_dir: str | Path | None = None) -> Path:
    return resolve_skill_dir(skill_dir) / LLM_QUOTA_STATE_FILE


def _mark_llm_quota_exhausted(
    settings: dict[str, Any],
    *,
    error: str,
    skill_dir: str | Path | None = None,
) -> None:
    """记录 LLM 配额/余额耗尽事件（写入状态文件，带时间戳和错误详情）。"""
    try:
        path = _llm_quota_state_path(skill_dir)
        payload = {
            "quota_exhausted": True,
            "detected_at": current_timestamp(),
            "model": settings.get("model", ""),
            "base_url": settings.get("base_url", ""),
            "error": error[:500],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def llm_quota_exhausted(skill_dir: str | Path | None = None) -> bool:
    """检查 LLM 配额是否已耗尽（状态文件存在且标记为 True）。"""
    try:
        path = _llm_quota_state_path(skill_dir)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("quota_exhausted"))
    except Exception:
        return False


def heuristic_extract_skills(resume_text: str, limit: int = 15) -> list[str]:
    normalized = normalize_text(resume_text)
    lowered = normalized.lower()
    matches: list[str] = []

    def add(candidate: str) -> None:
        candidate = candidate.strip(" ,，。；;:/")
        if len(candidate) < 2:
            return
        candidate_lower = candidate.lower()
        if any(marker in candidate_lower for marker in ("@", "mailto", "http://", "https://", "www.", "github.com")):
            return
        if any(char.isdigit() for char in candidate):
            return
        if "." in candidate and candidate_lower not in {"node.js"}:
            return
        if candidate_lower in ENGLISH_STOPWORDS or candidate in CHINESE_STOPWORDS:
            return
        if candidate_lower not in {item.lower() for item in matches}:
            matches.append(candidate)

    for keyword in COMMON_SKILL_KEYWORDS:
        if keyword.lower() in lowered:
            add(keyword)
        if len(matches) >= limit:
            return matches[:limit]

    english_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9+#./-]{1,24}\b", normalized)
    for token in english_tokens:
        if token.lower() in ENGLISH_STOPWORDS:
            continue
        if any(char.isdigit() for char in token) and len(token) <= 2:
            continue
        add(token)
        if len(matches) >= limit:
            return matches[:limit]

    chinese_tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", normalized)
    frequencies: dict[str, int] = {}
    for token in chinese_tokens:
        if token in CHINESE_STOPWORDS:
            continue
        if token.startswith(("负责", "参与", "完成", "推动", "能够", "熟悉")):
            continue
        frequencies[token] = frequencies.get(token, 0) + 1

    for token, count in sorted(frequencies.items(), key=lambda item: (-item[1], -len(item[0]))):
        if count < 2 and len(matches) >= 6:
            continue
        add(token)
        if len(matches) >= limit:
            break

    return matches[:limit]


def heuristic_greeting(target_roles: list[str], skills: list[str]) -> str:
    role = target_roles[0] if target_roles else "目标岗位"
    skill_text = "、".join(skills[:2]) if skills else "相关业务"
    greeting = f"您好，我关注贵司{role}岗位，具备{skill_text}相关经验，期待进一步沟通。"
    return clamp_text(greeting, 80)


def build_resume_profile(
    resume_text: str,
    *,
    target_roles: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    target_roles = target_roles or []
    exclude_keywords = exclude_keywords or []
    llm_client = llm_client or build_llm_client()

    # 默认仅本地规则提取，避免初始化配置时将完整简历上传到第三方。
    if llm_client.is_configured() and bool(getattr(llm_client, "allow_resume_upload", False)):
        try:
            payload = llm_client.chat_json(
                (
                    "你是资深招聘顾问。请从简历中提取 8-15 个最能代表候选人的核心技能词。"
                    "只返回 JSON，格式为 {\"skills\":[]}。不要臆造简历中没有的经验。"
                ),
                (
                    f"目标岗位：{', '.join(target_roles) or '未提供'}\n"
                    f"排除关键词：{', '.join(exclude_keywords) or '未提供'}\n"
                    "请基于下面简历内容抽取，不要臆造经验。\n\n"
                    f"{clamp_text(resume_text, 12000)}"
                ),
                # 2026-09-24 MAXTOK：同上（技能提取也要正文），抬到 2500
                max_tokens=2500,
            )
            raw_skills = payload.get("skills", [])
            skills = split_keywords(raw_skills if isinstance(raw_skills, list) else str(raw_skills))
            skills = skills[:15]
            if not skills:
                raise RuntimeError("LLM 没有返回技能关键词。")

            return {
                "skills": skills[:15],
                "greeting": DEFAULT_GREETING,
                "source": "llm",
                "note": "已通过 LLM 完成简历关键词抽取。",
            }
        except Exception as exc:
            fallback_skills = heuristic_extract_skills(resume_text)
            return {
                "skills": fallback_skills,
                "greeting": DEFAULT_GREETING,
                "source": "heuristic",
                "note": f"LLM 调用失败，已回退到规则提取：{exc}",
            }

    skills = heuristic_extract_skills(resume_text)
    return {
        "skills": skills,
        "greeting": DEFAULT_GREETING,
        "source": "heuristic",
        "note": "未检测到可用的 LLM 配置，已使用规则提取简历关键词。",
    }


def initialize_config_from_resume(
    resume_path: str | Path,
    *,
    target_roles: list[str],
    exclude_keywords: list[str],
    base_config: dict[str, Any] | None = None,
    skill_dir: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = merge_config(base_config)
    resolved_resume = resolve_resume_path(resume_path, skill_dir)
    resume_text = read_resume_text(resolved_resume)

    profile = build_resume_profile(
        resume_text,
        target_roles=target_roles,
        exclude_keywords=exclude_keywords,
        llm_client=build_llm_client(config),
    )

    config.update(
        {
            "resume_path": str(resolved_resume),
            "target_roles": dedupe_keep_order(target_roles),
            "exclude_keywords": dedupe_keep_order(exclude_keywords),
            "skills": dedupe_keep_order(profile["skills"])[:15],
            "greeting": clamp_text(str(config.get("greeting") or profile["greeting"]), 80),
            "min_score": int(config.get("min_score", 80) or 80),
        }
    )
    return config, profile


def heuristic_llm_score(
    *,
    role_hit: str | None,
    skill_hits: list[str],
    jd_text: str,
    scoring: dict[str, Any] | None = None,
) -> tuple[int, str]:
    score_rules = scoring_config({"scoring": scoring or {}})
    score = scoring_int(score_rules, "heuristic_base_score", 6)
    score += min(
        len(skill_hits) * scoring_int(score_rules, "heuristic_skill_score_each", 4),
        scoring_int(score_rules, "heuristic_skill_score_cap", 20),
    )
    if role_hit:
        score += scoring_int(score_rules, "heuristic_role_score", 8)
    jd_lower = jd_text.lower()
    bonus_keywords = score_rules.get("heuristic_bonus_keywords", [])
    if any(str(token).lower() in jd_lower for token in bonus_keywords):
        score += scoring_int(score_rules, "heuristic_bonus_score", 4)
    llm_min = scoring_int(score_rules, "llm_score_min", 1)
    llm_max = max(llm_min, scoring_int(score_rules, "llm_score_max", 40))
    score = max(
        llm_min,
        min(score, llm_max),
    )
    return score, "未配置 LLM，按技能重合和岗位相关性做估算。"


def llm_match_score(
    *,
    title: str,
    jd_text: str,
    resume_text: str,
    role_hit: str | None,
    skill_hits: list[str],
    scoring: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
) -> tuple[int, str, list[str], list[str], bool]:
    llm_client = llm_client or build_llm_client()
    score_rules = scoring_config({"scoring": scoring or {}})
    llm_min = scoring_int(score_rules, "llm_score_min", 1)
    llm_max = max(llm_min, scoring_int(score_rules, "llm_score_max", 40))
    if not resume_text.strip() or not llm_client.is_configured():
        s, r = heuristic_llm_score(role_hit=role_hit, skill_hits=skill_hits, jd_text=jd_text, scoring=score_rules)
        return s, r, [], [], False

    try:
        payload = llm_client.chat_json(
            (
                f"你是求职匹配评分器。你会阅读候选人简历和职位 JD，给出 {llm_min}-{llm_max} 分的补充评分。"
                "评分只反映简历与 JD 的真实匹配度，不要重复基础关键词计分。"
                "【重要】只评估工作经验、技能、岗位职责、实际产出与 JD 的匹配度；"
                "考虑经验年限——JD 要求的经验年限与候选人年限相符应加分，年限不足可适当扣分；"
                "完全忽略学历、专业、院校背景、年龄、性别等标签因素——学历不匹配、年龄偏大均不作为扣分理由；"
                "候选人多年一线实战经验可完全弥补学历差距，JD 中的学历要求不影响匹配度评分。"
                # 2026-09-19 A3：除分数与理由外，还要「证据」与「不足」。
                # 只加字段、不拆维度 —— 拆维度会让结构化输出变复杂，
                # 对推理模型风险高（曾出现 content 恒为空）。
                f"只输出 JSON：{{\"score\":{llm_min}-{llm_max},\"reason\":\"不超过 60 字\","
                f"\"evidence\":[\"简历中支撑该分数的具体经历，每条不超过 30 字\"],"
                f"\"gaps\":[\"JD 要求但简历缺失的点，每条不超过 30 字，没有就空数组\"]}}。"
            ),
            (
                f"岗位标题：{title}\n\n"
                f"候选人简历：\n{clamp_text(resume_text, 6000)}\n\n"
                f"职位 JD：\n{clamp_text(jd_text, 5000)}"
            ),
            # 2026-09-24 MAXTOK：900 会被推理预算吃光 → content 恒空 → 评分全退回启发式
            #（实测 900→content 0 字 / 2000→正常 JSON），抬到 2500
            max_tokens=2500,
            temperature=0.1,
        )
        score = int(payload.get("score", 0))
        score = max(llm_min, min(score, llm_max))
        reason = clamp_text(str(payload.get("reason") or "LLM 认为岗位匹配度中等。"), 60)
        evidence = [clamp_text(str(x), 40)
                    for x in (payload.get("evidence") or []) if str(x).strip()][:3]
        gaps = [clamp_text(str(x), 40)
                for x in (payload.get("gaps") or []) if str(x).strip()][:2]
        return score, reason, evidence, gaps, True
    except Exception:
        s, r = heuristic_llm_score(role_hit=role_hit, skill_hits=skill_hits, jd_text=jd_text, scoring=score_rules)
        return s, r, [], [], False




def _cjk_len(s: str) -> int:
    """统计字符串里的**中文字数**（用于「公司名屏蔽需 ≥3 字」的判断）。

    为什么只数中文：公司名以中文为主；英文/数字词（如 Tiktok）
    用长度判断不合适，交给 keyword_in_text 的常规匹配即可。
    """
    return sum(1 for ch in str(s or "")
               if "\u4e00" <= ch <= "\u9fff")


def company_blocked(
    company: str,
    config: dict[str, Any] | None = None,
) -> str | None:
    """返回命中的公司名屏蔽词；未命中返回 None。

    2026-09-18 新增（用户裁决）：独立于 title_exclude_keywords / exclude_keywords。
    只匹配「公司名」这一个字段，不扫标题与 JD —— 因为公司名常含行业词
    （「XX电商」「XX传媒」「XX科技」），混进通用表会在标题/JD 里大面积误命中。

    匹配方式与 keyword_in_text 一致（小写子串 + 去标点压缩匹配），
    因此写「蚍蜉」即可命中「蚍蜉网络」。

    默认 company_exclude_keywords 为空数组 → 不配置时**旧路径**恒返回 None。

    ⚠️ 2026-09-20 新增：本函数**还会查 `exclude_keywords`（屏蔽词）** ——
      屏蔽词里直接写公司名即可屏蔽整家公司（用户视角只有一张表）。
      但为避免误杀，**只认 ≥3 个中文字**的屏蔽词。
    """
    cfg = merge_config(config)
    name = normalize_text(company)
    if not name:
        return None
    # ① 旧路径：独立的公司屏蔽表（保留兼容；用户一般不再需要单独配）
    for keyword in cfg.get("company_exclude_keywords") or []:
        keyword = str(keyword).strip()
        if keyword and keyword_in_text(keyword, name):
            return keyword
    # ② 新路径（2026-09-20 用户裁决）：**统一到屏蔽词** ——
    #    屏蔽词里写公司名即可屏蔽整家公司。但为防误杀，
    #    **只认 ≥3 个中文字的词**：2 字词（电商/网络/科技/传媒）
    #    在公司维度几乎必然是行业通用词，会误杀一整片。
    for keyword in cfg.get("exclude_keywords") or []:
        keyword = str(keyword).strip()
        if not keyword:
            continue
        if _cjk_len(keyword) < 3:
            continue
        if keyword_in_text(keyword, name):
            return keyword
    return None


def excluded_keyword_for_job(
    title: str,
    jd_text: str,
    config: dict[str, Any] | None = None,
) -> str | None:
    """返回岗位标题/JD 命中的排除词；用于 LLM 调用前置过滤。"""
    cfg = merge_config(config)
    title_clean = normalize_text(title)
    jd_clean = sanitize_jd_text(jd_text)
    for keyword in [*(cfg.get("title_exclude_keywords") or []), *(cfg.get("exclude_keywords") or [])]:
        if keyword and (keyword_in_text(keyword, title_clean) or keyword_in_text(keyword, f"{title_clean}\n{jd_clean}")):
            return str(keyword)
    return None


def match_threshold(title: str, config: dict[str, Any] | None = None) -> int:
    """返回本次评分采用的阈值。

    2026-09-19（用户裁决）：**只有一个阈值**，由用户在方案里自己调。
    历史上这里按标题分档（海外类/市场类降到 60），已删除 —— 因为
      · 触发词表硬编码不可配（海外 18 词）、方案预览里也完全不告知用户
      · 同一份方案里出现两个匹配分，与「一个方案一个匹配分」的产品原则冲突
      · 会让「跨境电商财务」这类岗位被悄悄放松 10 分标准
    默认值统一为 70（原先三处不一致：DEFAULT_CONFIG/match_threshold 是 80、
    main.py 的中途判定是 75、看板 placeholder 是 70）。
    """
    cfg = merge_config(config)
    return int(cfg.get("min_score", DEFAULT_MIN_SCORE) or DEFAULT_MIN_SCORE)

# 2026-09-19 A1/A2：取职位核心词的公共 helper。
# 「标题档」「JD 兜底档」「根词自动推导」三处共用，故提到模块级。
_ROLE_SUFFIXES = ("运营", "经理", "负责人", "总监", "主管", "专员", "岗位", "方向")


def _role_core(role: str) -> str:
    """取职位核心词：去掉**一个**常见后缀。例：「公会运营」→「公会」。"""
    core = str(role or "").strip()
    for _suf in _ROLE_SUFFIXES:
        if core.endswith(_suf) and len(core) > len(_suf):
            return core[: -len(_suf)]
    return core


def score_jd(
    title: str,
    jd_text: str,
    config: dict[str, Any] | None = None,
    *,
    skill_dir: str | Path | None = None,
    resume_text: str | None = None,
    llm_client: LLMClient | None = None,
    use_llm: bool = True,
) -> ScoreResult:
    cfg = merge_config(config)
    score_rules = scoring_config(cfg)
    role_title_score = scoring_int(score_rules, "role_title_score", 20)
    related_role_score = scoring_int(score_rules, "related_role_score", 12)
    generic_role_score = scoring_int(score_rules, "generic_role_score", 6)
    generic_role_roots = list(score_rules.get("generic_role_roots") or [])
    if not generic_role_roots:
        # 2026-09-19 A2：未显式配置 → 从 target_roles **自动推导**核心词。
        # 原实现硬编码「运营/增长/内容/直播/用户/商业化/投放」，
        # 换一个行业的用户就完全失效（服务多用户不能有行业假设）。
        for _r in (cfg.get("target_roles") or []):
            for _c in (_role_core(_r), str(_r).strip()):
                if len(_c) >= 2 and _c not in generic_role_roots:
                    generic_role_roots.append(_c)
        generic_role_roots = generic_role_roots[:12]
    skill_score_each = scoring_int(score_rules, "skill_score_each", 5)
    skill_score_cap = scoring_int(score_rules, "skill_score_cap", 20)
    title_clean = normalize_text(title)
    jd_clean = sanitize_jd_text(jd_text)
    combined = f"{title_clean}\n{jd_clean}"

    # 标题级排除词：命中后不进入 LLM 判定。
    for keyword in cfg.get("title_exclude_keywords", []):
        if keyword_in_text(keyword, title_clean):
            return ScoreResult(
                title=title_clean,
                total_score=0,
                rule_score=0,
                llm_score=0,
                decision="skip",
                reason=f"命中标题排除关键词：{keyword}",
                llm_reason="未进入 LLM 判定。",
                exclude_hit=keyword,
            )

    # 全量排除词：匹配标题 + JD（用于日结/押金/先交费等欺诈或低质信号词）
    for keyword in cfg.get("exclude_keywords", []):
        if keyword_in_text(keyword, combined):
            return ScoreResult(
                title=title_clean,
                total_score=0,
                rule_score=0,
                llm_score=0,
                decision="skip",
                reason=f"命中排除关键词：{keyword}",
                llm_reason="未进入 LLM 判定。",
                exclude_hit=keyword,
            )
    rule_score = 0
    role_hit: str | None = None
    related_role_hit: str | None = None
    jd_role_hit: str | None = None
    generic_hit: str | None = None
    for role in cfg.get("target_roles", []):
        if keyword_in_text(role, title_clean):
            role_hit = role
            rule_score += role_title_score
            break
    if not role_hit:
        # 去掉常见职位后缀后取核心词；核心词命中即视为相关岗位族。
        # 例：「公会运营」→「公会」，可覆盖「海外直播公会BD」。
        for role in cfg.get("target_roles", []):
            core = _role_core(role)
            if len(core) >= 2 and keyword_in_text(core, title_clean):
                related_role_hit = role
                rule_score += related_role_score
                break
    # 2026-09-19 A1：**JD 兜底档** —— 标题没命中时，退到 JD 里找核心词。
    # 场景：HR 不懂业务 / 标题营销化（「运营牛人」「海外运营专家（急招）」），
    #       但 JD 里写的是正经职责。原先这类岗位会直接掉到泛根词 6 分或 0 分。
    if not role_hit and not related_role_hit:
        for role in cfg.get("target_roles", []):
            core = _role_core(role)
            if len(core) >= 2 and keyword_in_text(core, jd_clean):
                jd_role_hit = role
                rule_score += scoring_int(score_rules, "jd_role_score", 12)
                break
    # 第三档：泛职业根词（弱信号，2026-09-19 新增）。
    # 只在前两档都没命中时才给分，用来缓和「差一个词就差 30 分」的跳变。
    if not role_hit and not related_role_hit:
        for root in generic_role_roots:
            if str(root).strip() and keyword_in_text(str(root), title_clean):
                generic_hit = str(root)
                rule_score += generic_role_score
                break

    skill_hits = [
        skill
        for skill in cfg.get("skills", [])
        if keyword_in_text(skill, combined)
    ]
    skill_hits = dedupe_keep_order(skill_hits)
    skill_score = min(len(skill_hits) * skill_score_each, skill_score_cap)
    rule_score += skill_score

    if resume_text is None and cfg.get("resume_path"):
        try:
            resume_text = read_resume_text(cfg["resume_path"], skill_dir=skill_dir)
        except Exception:
            resume_text = ""

    if use_llm:
        llm_cfg = cfg.get("llm") or {}
        if not bool(llm_cfg.get("allow_resume_upload", False)):
            resume_text = ""
        llm_score, llm_reason, llm_evidence, llm_gaps, llm_ok = llm_match_score(
            title=title_clean,
            jd_text=jd_clean,
            resume_text=resume_text or "",
            role_hit=role_hit,
            skill_hits=skill_hits,
            scoring=score_rules,
            llm_client=llm_client or build_llm_client(cfg, skill_dir=skill_dir),
        )
    else:
        llm_score, llm_reason, llm_evidence, llm_gaps, llm_ok = 0, "", [], [], False  # 演练模式不调 LLM

    total_score = min(rule_score + llm_score, 100)
    # 2026-09-19：单一阈值（用户可在方案里调）。原先按标题分档的逻辑已删除。
    threshold = match_threshold(title_clean, cfg)
    decision = "apply" if total_score >= threshold else "skip"

    reason_parts: list[str] = []
    if role_hit:
        reason_parts.append(f"岗位加分: {role_hit}(+{role_title_score})")
    elif related_role_hit:
        reason_parts.append(f"相关岗位族加分: {related_role_hit}(+{related_role_score})")
    elif jd_role_hit:
        reason_parts.append(f"JD命中岗位(标题未命中): {jd_role_hit}(+{scoring_int(score_rules, 'jd_role_score', 12)})")
    elif generic_hit:
        reason_parts.append(f"泛职业根词: {generic_hit}(+{generic_role_score})")
    if skill_hits:
        reason_parts.append(f"技能命中: {'/'.join(skill_hits[:6])}(+{skill_score})")
    reason_parts.append(f"LLM补分: +{llm_score}")
    reason_parts.append(f"阈值: {threshold}")

    return ScoreResult(
        title=title_clean,
        total_score=total_score,
        rule_score=rule_score,
        llm_score=llm_score,
        decision=decision,
        reason="；".join(reason_parts),
        llm_reason=llm_reason,
        skill_hits=skill_hits,
        role_hit=role_hit,
        llm_ok=llm_ok,
        llm_evidence=llm_evidence,
        llm_gaps=llm_gaps,
    )


def is_cdp_port_ready(debug_port: int = 9222, *, host: str = "127.0.0.1", timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, int(debug_port)), timeout=timeout):
            return True
    except OSError:
        return False


def assert_cdp_port_ready(debug_port: int = 9222) -> None:
    if is_cdp_port_ready(debug_port):
        return
    raise RuntimeError(
        f"未检测到已打开的浏览器调试端口 {debug_port}。"
        "请先按提示手动启动浏览器并登录；skill 不会自动新开浏览器。"
    )


def connect_browser(debug_port: int = 9222):
    """使用 DrissionPage 的 CDP 端口接管模式接入已打开的浏览器。"""

    try:
        from DrissionPage import Chromium, ChromiumOptions
    except ImportError as exc:
        raise RuntimeError(
            "未安装 DrissionPage，请先执行 `pip install DrissionPage`。"
        ) from exc

    assert_cdp_port_ready(debug_port)

    options = ChromiumOptions()
    options.set_local_port(debug_port)

    try:
        browser = Chromium(options)
    except TypeError:
        browser = Chromium(addr_or_opts=options)

    return browser


def pace_sleep(min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
    """随机间隔延迟：偏态分布，大多数落在中低区间、偶发长停顿。

    固定间隔的规律性过于明显；这里用非均匀分布：多数间隔较短、偶发长间隔。
    用截断的指数分布模拟：偏向区间下限，小概率出现接近上限的长停顿。
    调用方传 min/max 仍是硬边界，语义与原来一致。
    """
    if min_seconds < 0:
        min_seconds = 0.0
    if max_seconds <= min_seconds:
        max_seconds = min_seconds + 0.5
    span = max_seconds - min_seconds
    # rate 控制偏斜程度：值越小越偏向低端
    raw = random.expovariate(1.4)
    # 截断到 [0, 1.2] 然后映射到 [0, span]，再放大低端占比
    t = min(raw, 1.2) / 1.2
    # 非线性映射让低端更密集：t^0.85 提升长停顿概率（保留部分右尾）
    t = t ** 0.85
    delay = min_seconds + t * span
    time.sleep(delay)


def read_job_sleep() -> None:
    """读取职位详情页的停留时间（打开职位后看 JD 再决定）。

    阅读时间随机 1.2~3.0 秒，偏向中短阅读（多数岗位快速扫一眼）。
    """
    time.sleep(random.uniform(1.2, 3.0))


def between_jobs_sleep() -> None:
    """翻到下一个职位前的间隔（列表滚动+停留）。

    2.5~6 秒为主，偶发 6~10 秒的长停顿（约 6% 概率）。
    """
    if random.random() < 0.06:
        time.sleep(random.uniform(6.0, 10.0))
    else:
        time.sleep(random.uniform(2.5, 6.0))


def task_break_sleep() -> None:
    """切换关键词/城市搜索前的间隔（重新输入搜索条件）。

    主停顿 3~7 秒；约 4% 概率出现 7~12 秒的长停顿。
    """
    if random.random() < 0.04:
        time.sleep(random.uniform(7.0, 12.0))
    else:
        time.sleep(random.uniform(3.0, 7.0))


def print_browser_login_instructions(
    *,
    platforms: Iterable[str] | None = None,
    config: dict[str, Any] | None = None,
    skill_dir: str | Path | None = None,
    print_func=print,
) -> None:
    cfg = merge_config(config)
    # 2026-09-18：默认平台只剩 Boss（实习僧已移除）。
    selected_platforms = list(platforms or ["boss"])

    print_func("\n[登录确认] 请先手动启动浏览器并完成登录。")
    print_func("请启动对应平台的独立浏览器会话。")
    for platform in selected_platforms:
        label = platform_label(platform)
        debug_port = platform_debug_port(platform, cfg)
        user_data_dir = platform_user_data_dir(platform, cfg, skill_dir=skill_dir)
        print_func(f"{label}：")
        print_func(
            '(Windows) & "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" '
            f'--remote-debugging-port={debug_port} --user-data-dir="{user_data_dir}"'
        )
        print_func(
            "(Mac) /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
            f"--remote-debugging-port={debug_port} --user-data-dir=/tmp/chrome-debug-{platform}"
        )
    print_func("登录完成后，请输入 'yes' 继续执行。")


def wait_for_manual_login(
    *,
    skip_prompt: bool = False,
    platforms: Iterable[str] | None = None,
    config: dict[str, Any] | None = None,
    skill_dir: str | Path | None = None,
    input_func=input,
    print_func=print,
) -> bool:
    if skip_prompt:
        return True

    print_browser_login_instructions(
        platforms=platforms,
        config=config,
        skill_dir=skill_dir,
        print_func=print_func,
    )
    while True:
        answer = input_func("请输入 yes 继续，或输入 quit 退出: ").strip().lower()
        if answer == "yes":
            return True
        if answer in {"quit", "exit", "q", "no"}:
            return False
        print_func("未识别输入，请输入 yes 或 quit。")


def check_boss_login(browser: Any, *, tab=None, timeout: float = 6.0) -> str:
    """检测 BOSS 直聘登录状态（低刷新版）。

    判据：已登录时右上角导航为「消息 / 简历 / 用户昵称」，未登录时右上角为
    「我要招聘 / 我要找工作」。返回状态字符串：
    "ok" 已登录 / "login_required" 未登录 / "blocked" 安全验证或风控 403 / "unknown" 无法判断。

    风控优化：**只有当前页面不是 zhipin 域名时才导航首页**；已在 BOSS 任意页面时
    直接读取当前页 DOM 判断，不刷新页面，避免高频检测（watchdog 每 5 分钟等）成为
    BOSS 风控的「频繁提交刷新请求」触发源。
    """
    import time as _time

    try:
        t = tab if tab is not None else browser.latest_tab
        if t is None:
            return "unknown"
        low = (t.url or "").lower()
        if "zhipin.com" not in low:
            # 仅在非 BOSS 页面（空白/新标签/其他站点）时导航首页一次
            t.get("https://www.zhipin.com/")
            _time.sleep(timeout)
        else:
            # 已在本页：轻量等 DOM 稳定，不刷新
            _time.sleep(1.0)
        # 优先读取可见文本，避免页面内置的 display:none 登录/验证码模板造成误报；
        # CDP/旧版驱动不支持 run_js 时再回退完整 HTML。
        try:
            body = str(t.run_js("document.body ? document.body.innerText : ''") or "")
        except Exception:
            body = t.html or ""
        url = t.url or ""
        # BOSS 正常岗位页可能携带 `_security_check=1` 查询参数，不能仅凭
        # URL 中出现 security 就判定风控；必须有明确验证文案或验证专用路径。
        url_lower = url.lower()
        if "安全验证" in body or "/security/" in url_lower or "/passport/zp/security" in url_lower:
            return "blocked"
        # 风控 403：IP/账号被临时限制访问
        if ("访问受限" in body or "异常行为" in body) and ("403" in url or "passport/zp" in url):
            return "blocked"
        # 未登录：右上角为「我要招聘 / 我要找工作」
        if "我要找工作" in body and "我要招聘" in body:
            return "login_required"
        # 已登录：导航含「消息」+「简历」
        if "消息" in body and "简历" in body:
            return "ok"
        # 内页补充特征：当前页为岗位/聊天等内页时首页导航特征不全
        if any(k in body for k in ("退出登录", "我的简历", "已投递", "个人中心", "在线简历")):
            return "ok"
        if any(k in body for k in ("扫码登录", "立即登录", "请先登录", "手机号登录",
                                   "登录/注册", "登录后查看", "点击登录")):
            return "login_required"
        return "unknown"
    except Exception:
        return "unknown"


def open_tab(browser: Any, url: str | None = None):
    """优先新开标签页，失败时退回到最后激活标签页。"""

    tab = None
    try:
        if url:
            tab = browser.new_tab(url)
        else:
            tab = browser.new_tab()
    except Exception:
        tab = getattr(browser, "latest_tab", None)
        if isinstance(tab, str):
            tab = browser.get_tab(tab)
        if url and tab is not None:
            tab.get(url)

    if tab is None:
        raise RuntimeError("无法从浏览器对象获取可操作标签页。")

    try:
        tab.set.timeouts(8)
    except Exception:
        pass
    return tab


def cleanup_tabs(browser: Any, keep_urls: Iterable[str] = (), max_tabs: int = 5) -> int:
    """清理浏览器多余标签页，避免长时间投递累积大量无用 tab 导致浏览器变慢。

    - 保留：搜索结果页（URL 含 geek/jobs）、当前投递详情页（keep_urls）、chrome:// 页面
    - 关闭：聊天会话页（/web/chat/、/geek/chat/）、历史详情页等无用 tab
    - 若关闭后仍超过 max_tabs，继续关闭最早打开的普通页面
    返回关闭的 tab 数量。
    """
    closed = 0
    try:
        tabs = browser.get_tabs()
    except Exception:
        return 0
    if len(tabs) <= 1:
        return 0

    keep_set = {str(u).strip() for u in keep_urls if u}

    def is_kept_url(url: str) -> bool:
        """匹配白名单 URL；聊天页允许 query/hash 会话参数。"""
        if not url:
            return False
        if url in keep_set:
            return True
        try:
            current = urlsplit(url)
            current_path = current.path.rstrip("/")
            for kept in keep_set:
                target = urlsplit(kept)
                if target.scheme and target.netloc and (
                    current.scheme, current.netloc
                ) != (target.scheme, target.netloc):
                    continue
                target_path = target.path.rstrip("/")
                if target_path in {"/web/geek/chat", "/web/chat"} and current_path == target_path:
                    return True
        except ValueError:
            return False
        return False
    ids_to_close: list[tuple[str, str, str]] = []  # (tab_id, url, title)
    jobs_kept = 0  # 已保留的搜索结果页数量（只保留第一个 + keep_urls 指定的）

    for tb in tabs:
        try:
            url = tb.url or ""
            title = tb.title or ""
        except Exception:
            continue
        # 保留白名单（keep_urls 里指定的 URL，通常是当前主搜索页，用完整 URL 全等判断）
        if is_kept_url(url):
            continue
        # chrome 内部页永远保留
        if url.startswith("chrome://") or url.startswith("chrome:"):
            continue
        # 搜索结果页：只保留第一个（避免搜索页自身累积），其余视为无用
        if "/web/geek/jobs" in url:
            if jobs_kept < 1:
                jobs_kept += 1
                continue
            ids_to_close.append((tb.tab_id, url, title))
            continue
        # 聊天页 / 历史详情页 / 其他 = 无用，待关闭
        ids_to_close.append((tb.tab_id, url, title))

    # 先关掉明确无用的聊天/详情页
    for tab_id, url, title in ids_to_close:
        try:
            for tb in tabs:
                if getattr(tb, "tab_id", None) == tab_id:
                    tb.close()
                    closed += 1
                    break
        except Exception:
            continue

    # 若仍超过上限，兜底关闭最早的多余 tab（保留 keep_urls + 最多 1 个搜索结果页 + chrome 页）
    try:
        tabs = browser.get_tabs()
        if len(tabs) > max_tabs:
            jobs_kept = 0
            for tb in tabs:
                if len(tabs) <= max_tabs:
                    break
                try:
                    url = tb.url or ""
                    if is_kept_url(url):
                        continue
                    if url.startswith("chrome://") or url.startswith("chrome:"):
                        continue
                    if "/web/geek/jobs" in url:
                        if jobs_kept < 1:
                            jobs_kept += 1
                            continue
                    tb.close()
                    closed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return closed


def find_first(root: Any, locators: Iterable[str], timeout: float = 1.5):
    if root is None:
        return None
    for locator in locators:
        try:
            element = root.ele(locator, timeout=timeout)
            if element:
                return element
        except Exception:
            continue
    return None


def find_all(root: Any, locators: Iterable[str], timeout: float = 0.8) -> list[Any]:
    if root is None:
        return []
    for locator in locators:
        try:
            elements = root.eles(locator, timeout=timeout)
            if elements:
                return list(elements)
        except Exception:
            continue
    return []


def safe_text(node: Any) -> str:
    if node is None:
        return ""
    for attr_name in ("text", "raw_text", "inner_html", "html"):
        try:
            value = getattr(node, attr_name)
            if callable(value):
                value = value()
            if value:
                return normalize_text(str(value))
        except Exception:
            continue
    return ""


def text_from_locators(root: Any, locators: Iterable[str], timeout: float = 1.0) -> str:
    if root is None:
        return ""
    texts: list[str] = []
    for locator in locators:
        try:
            elements = root.eles(locator, timeout=timeout)
        except Exception:
            elements = []
        if not elements:
            continue
        for element in elements:
            text = safe_text(element)
            if text:
                texts.append(text)
    return normalize_text("\n".join(dedupe_keep_order(texts)))


def safe_attr(node: Any, attr_name: str) -> str:
    if node is None:
        return ""
    try:
        value = node.attr(attr_name)
        return "" if value is None else str(value)
    except Exception:
        return ""


def safe_click(node: Any, *, by_js: bool | None = None) -> bool:
    if node is None:
        return False

    try:
        node.scroll.to_see()
    except Exception:
        pass

    # 先把鼠标移到元素上，随机小停顿后再点（不直接瞬移点）
    try:
        import random as _r, time as _t
        node.move()
        _t.sleep(_r.uniform(0.08, 0.35))
    except Exception:
        pass

    try:
        if by_js is None:
            result = node.click(by_js=None)
        else:
            result = node.click(by_js=by_js)
        return False if result is False else True
    except Exception:
        return False


def safe_input(node: Any, value: str, *, clear: bool = True) -> bool:
    if node is None:
        return False
    try:
        node.scroll.to_see()
    except Exception:
        pass
    try:
        node.input(value, clear=clear)
        return True
    except Exception:
        try:
            node.click()
            node.input(value, clear=clear, by_js=True)
            return True
        except Exception:
            return False


def click_any(root: Any, locators: Iterable[str], timeout: float = 1.0) -> bool:
    if root is None:
        return False
    element = find_first(root, locators, timeout=timeout)
    return safe_click(element, by_js=None)


def input_any(root: Any, locators: Iterable[str], value: str, *, clear: bool = True) -> bool:
    if root is None:
        return False
    element = find_first(root, locators, timeout=1.0)
    return safe_input(element, value, clear=clear)


def smooth_scroll(target: Any, steps: int = 5, *, min_pixel: int = 350, max_pixel: int = 900) -> None:
    if target is None:
        return
    for _ in range(max(1, steps)):
        pixel = random.randint(min_pixel, max_pixel)
        try:
            target.scroll.down(pixel)
        except Exception:
            try:
                target.run_js(f"window.scrollBy(0, {pixel});")
            except Exception:
                break
        time.sleep(random.uniform(0.3, 0.9))


def build_boss_search_url(job_name: str, city_code: str, salary_max_k: int = 0) -> str:
    """
    构造 BOSS 搜索 URL。salary_max_k 为期望最高薪资（K），自动加薪资筛选参数。
    
    BOSS 薪资档位编码（实测确认 + 推断）：
    | 档位       | 编码 | 说明                     |
    |------------|------|--------------------------|
    | 3K以下     | 401  | 推断                     |
    | 3-5K       | 402  | 推断                     |
    | 5-10K      | 403  | 推断                     |
    | 10-20K     | 404  | 推断                     |
    | 20-50K     | 406  | 已实测确认（点击后 URL 自动变为 salary=406） |
    | 50K以上    | 407  | 推断                     |
    
    注：405 跳过，可能是特殊档位或已废弃。
    """
    url = f"https://www.zhipin.com/web/geek/jobs?query={quote(job_name)}&city={city_code}"
    # BOSS 薪资档位编码（用户确认）：
    # 3K以下=402, 3-5K=403, 5-10K=404, 10-20K=405, 20-50K=406, 50K以上=407
    if salary_max_k <= 0:
        return url  # 不限薪资
    if salary_max_k <= 3:
        url += "&salary=402"  # 3K以下
    elif salary_max_k <= 5:
        url += "&salary=403"  # 3-5K
    elif salary_max_k <= 10:
        url += "&salary=404"  # 5-10K
    elif salary_max_k <= 20:
        url += "&salary=405"  # 10-20K
    elif salary_max_k <= 50:
        url += "&salary=406"  # 20-50K
    else:
        url += "&salary=407"  # 50K+
    return url




def prepare_runtime(
    *,
    config: dict[str, Any] | None = None,
    skill_dir: str | Path | None = None,
    browser: Any = None,
    debug_port: int = 9222,
) -> tuple[dict[str, Any], Any, str, LLMClient]:
    cfg = merge_config(config if config is not None else load_config(skill_dir))
    working_browser = browser or connect_browser(debug_port=debug_port)
    resume_text = ""
    if cfg.get("resume_path"):
        try:
            resume_text = read_resume_text(cfg["resume_path"], skill_dir=skill_dir)
        except Exception:
            resume_text = ""
    return cfg, working_browser, resume_text, build_llm_client(cfg, skill_dir=skill_dir)


def make_job_key(platform: str, title: str, company: str) -> str:
    return f"{platform}|{normalize_text(title).lower()}|{normalize_text(company).lower()}"


def append_log(log_data: dict[str, Any], bucket: str, entry: dict[str, Any]) -> None:
    normalized = normalize_log_data(log_data)
    shaped = _ensure_record_shape(entry, bucket)
    normalized["records"].setdefault(bucket, [])
    normalized["records"][bucket].append(shaped)
    normalized["meta"]["updated_at"] = current_timestamp()
    log_data.clear()
    log_data.update(normalized)


def log_contains(log_data: dict[str, Any], bucket: str, key: str) -> bool:
    for item in log_bucket_items(log_data, bucket):
        if str(item.get("job_key", "")) == key:
            return True
    return False


def find_clickable_by_text(root: Any, keywords: Iterable[str]):
    """在容器中寻找按钮/链接类元素，按文本命中关键字返回第一个。"""

    if root is None:
        return None
    normalized_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
    locators = [
        "css:button",
        "css:a",
        "css:input",
        "css:[role=button]",
        "css:[class*=btn]",
        "css:[class*=button]",
        "css:[class*=apply]",
        "css:[class*=chat]",
        "css:[class*=send]",
        "css:[class*=deliver]",
    ]
    seen_ids: set[int] = set()

    for locator in locators:
        try:
            elements = root.eles(locator, timeout=0.4)
        except Exception:
            elements = []
        for element in elements:
            if id(element) in seen_ids:
                continue
            seen_ids.add(id(element))
            text = safe_text(element)
            value = safe_attr(element, "value")
            merged_text = f"{text} {value}".strip()
            if any(keyword in merged_text for keyword in normalized_keywords):
                return element
    return None


# ===========================================================================
# 夜间时段风险确认门禁（统一策略 · 2026-09-17）
# ---------------------------------------------------------------------------
# 产品决策：夜间 22:00-09:00 不阻止用户运行，但必须由用户**显式输入确认词**
#          （打字回复 OK，而非点击按钮），以 100% 确保是用户本人的自主行为。
#
# 【本段是夜间策略的唯一来源】
#   - main.py（桌宠壳）           → shared.is_night_window() / NIGHT_CONFIRM_WORDS
#   - launch_apply.py（批量调度）  → shared.night_gate()
#   - watchdog.py（守护）          → shared.is_night_window()
#
# 历史教训：夜间策略曾在 main.py 与 launch_apply.py 中各实现一份，导致行为相反
#          （一条硬拒绝、一条放行），且 9-10 整改只覆盖了其中一条。
#          任何时段或确认词的修改，只改这里。
# ===========================================================================

NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 9
# 用户输入这些词（不区分大小写）即视为确认；必须是"打字"输入，不接受按钮点击。
NIGHT_CONFIRM_WORDS = ("ok", "确认", "继续", "同意", "我承担风险")


def is_night_window(hour: int | None = None) -> bool:
    """当前是否处于夜间时段（22:00-09:00，跨零点）。

    hour 为 None 时取当前本地小时；显式传入便于测试与跨时段判断。
    """
    h = time.localtime().tm_hour if hour is None else int(hour)
    return h >= NIGHT_START_HOUR or h < NIGHT_END_HOUR


def night_gate(*, input_fn=None, print_fn=None) -> bool:
    """夜间风险确认门禁（供命令行路径使用）。

    非夜间 → 直接返回 True。
    夜间 → 打印风险提示，要求用户**手动输入**确认词后才继续。

    返回 True = 已确认可继续；False = 未确认，调用方必须停止本轮。

    安全侧设计：非交互环境（stdin 非 TTY，如被计划任务/脚本拉起）无法取得
    用户确认，一律视为未确认 → 不投递。这样夜间"无人值守"在结构上无法发生。
    """
    if not is_night_window():
        return True

    _print = print_fn or print
    _print("=" * 68)
    _print("🌙 当前处于夜间时段（%d:00-%d:00）" % (NIGHT_START_HOUR, NIGHT_END_HOUR))
    _print("   BOSS 夜间操作更容易触发风控/封号。")
    _print("   继续即表示你已了解，并自行承担账号风险。")
    _print("   请输入 OK 并回车以继续（直接回车 = 放弃）。")
    _print("=" * 68)

    try:
        if not sys.stdin or not sys.stdin.isatty():
            _print(">>> 当前为非交互环境，无法取得你的确认，本轮不投递。")
            return False
    except Exception:
        _print(">>> 无法判断交互环境，本轮不投递。")
        return False

    _in = input_fn or input
    try:
        answer = _in("夜间风险确认（输入 OK 继续）：")
    except (EOFError, OSError, KeyboardInterrupt):
        _print(">>> 未取得确认，本轮不投递。")
        return False

    if str(answer).strip().lower() in NIGHT_CONFIRM_WORDS:
        _print(">>> 已确认夜间风险，继续。")
        return True
    _print(">>> 未确认夜间风险，本轮不投递。")
    return False
