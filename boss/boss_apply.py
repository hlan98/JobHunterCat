"""Boss直聘自动投递脚本，强制使用 DrissionPage 接管本地 9222 端口浏览器。"""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from agent.shared import (
    JobTask,
    ScoreResult,
    append_log,
    build_boss_search_url,
    clamp_text,
    company_blocked,
    current_timestamp,
    find_all,
    find_clickable_by_text,
    find_first,
    get_logger,
    pace_sleep,
    keyword_in_text,
    normalize_text,
    read_job_sleep,
    between_jobs_sleep,
    check_boss_login,
    load_config,
    load_log,
    log_bucket_items,
    log_contains,
    make_job_key,
    normalize_run_mode,
    open_tab,
    cleanup_tabs,
    platform_label,
    prepare_runtime,
    resolve_skill_dir,
    run_mode_label,
    safe_attr,
    safe_click,
    safe_input,
    safe_text,
    save_log,
    score_jd,
    start_log_run,
    smooth_scroll,
    finish_log_run,
    wait_for_manual_login,
)


PLATFORM = "boss"
PLATFORM_NAME = platform_label(PLATFORM)

CITY_CODES = {
    "全国": "100010000",
    # 直辖市
    "北京": "101010100", "上海": "101020100", "天津": "101030100", "重庆": "101040100",
    # 东北
    "哈尔滨": "101050100", "长春": "101060100", "沈阳": "101070100", "大连": "101070200",
    # 华北
    "呼和浩特": "101080100", "石家庄": "101090100", "唐山": "101090500", "太原": "101100100",
    # 西北
    "西安": "101110100", "乌鲁木齐": "101130100", "拉萨": "101140100", "西宁": "101150100",
    "兰州": "101160100", "银川": "101170100",
    # 华东
    "济南": "101120100", "青岛": "101120200", "烟台": "101120500", "郑州": "101180100",
    "洛阳": "101180900", "南京": "101190100", "无锡": "101190200", "苏州": "101190400",
    "南通": "101190500", "徐州": "101190800", "常州": "101191100",
    "杭州": "101210100", "宁波": "101210400", "温州": "101210700", "嘉兴": "101210300",
    "金华": "101210900", "合肥": "101220100", "芜湖": "101220300",
    "福州": "101230100", "厦门": "101230200", "泉州": "101230500", "南昌": "101240100",
    # 华中
    "武汉": "101200100", "襄阳": "101200200", "宜昌": "101200900",
    "长沙": "101250100", "湘潭": "101250200", "株洲": "101250300",
    # 华南
    "广州": "101280100", "深圳": "101280600", "珠海": "101280700", "佛山": "101280800",
    "惠州": "101280300", "汕头": "101280500", "东莞": "101281600", "中山": "101281700",
    "南宁": "101300100", "桂林": "101300500", "海口": "101310100", "三亚": "101310200",
    # 西南
    "贵阳": "101260100", "成都": "101270100", "绵阳": "101270400", "昆明": "101290100",
}

CARD_LOCATORS = [
    "css:.job-card-wrap",
    "css:.job-card-wrapper",
    "css:[class*=job-card-wrap]",
    "css:[class*=job-card-wrapper]",
]

TITLE_LOCATORS = [
    "css:.job-name",
    "css:.job-title",
    "css:[class*=job-name]",
    "css:[class*=job-title]",
    "css:h3",
]

COMPANY_LOCATORS = [
    "css:.company-name",
    "css:.brand-name",
    "css:[class*=company-name]",
    "css:[class*=brand-name]",
]

SALARY_LOCATORS = [
    "css:.salary",
    "css:.job-salary",
    "css:[class*=salary]",
]

DETAIL_LOCATORS = [
    "css:.job-detail-body",
    "css:.job-detail-box",
    "css:.job-detail-section",
    "css:.job-sec-text",
    "css:[class*=job-detail]",
    "css:[class*=job-sec]",
]

GREETING_INPUT_LOCATORS = [
    "css:textarea",
    "css:input[placeholder*='打招呼']",
    "css:textarea[placeholder*='打招呼']",
    "css:[contenteditable='true']",
]


def parse_args(default_count: int, default_min_score: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=PLATFORM_NAME)
    parser.add_argument("--job", required=True, help="搜索岗位名")
    parser.add_argument("--city", default="全国", help="目标城市")
    parser.add_argument("--count", type=int, default=default_count, help="投递数量")
    parser.add_argument("--min-score", type=int, default=default_min_score, help="最低分")
    parser.add_argument("--mode", choices=("rehearsal", "apply"), help="运行模式")
    parser.add_argument("--port", type=int, default=9222, help="浏览器调试端口")
    parser.add_argument("--skill-dir", default=str(resolve_skill_dir()), help="运行目录")
    parser.add_argument("--skip-login-prompt", action="store_true", help="跳过手动登录确认提示")
    return parser.parse_args()


def parse_salary_range(salary_text: str) -> tuple[float, float, bool]:
    """解析 BOSS 直聘薪资格式（如 20-30K / 20K以上 / 15-20K·13薪 / 2-3万 / 薪资面议），
    返回 (下限K, 上限K, 是否可解析)。单值/以上格式上限取 999 表示不封顶；
    不可解析（面议等）返回 (0.0, 0.0, False)。"""
    import re

    text = (salary_text or "").replace(" ", "").replace("·", "-").replace("＊", "*").upper()
    if not text or "面议" in text:
        return 0.0, 0.0, False
    # 去掉 "X薪"（月薪数，如 13薪/14薪），避免干扰薪资范围
    text = re.sub(r"\d+\s*薪", "", text)
    # 范围格式：20-30K / 20~30K / 20到30K
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~到]\s*(\d+(?:\.\d+)?)\s*K", text)
    if m:
        return float(m.group(1)), float(m.group(2)), True
    # 单个 K 以上：20K以上
    m = re.search(r"(\d+(?:\.\d+)?)\s*K\s*以上", text)
    if m:
        return float(m.group(1)), 999.0, True
    # 单个 K：20K
    m = re.search(r"(\d+(?:\.\d+)?)\s*K", text)
    if m:
        k = float(m.group(1))
        return k, k, True
    # 万 单位：2-3万 / 2万以上
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~到]\s*(\d+(?:\.\d+)?)\s*万", text)
    if m:
        return float(m.group(1)) * 10.0, float(m.group(2)) * 10.0, True
    m = re.search(r"(\d+(?:\.\d+)?)\s*万\s*以上", text)
    if m:
        return float(m.group(1)) * 10.0, 999.0, True
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if m:
        k = float(m.group(1)) * 10.0
        return k, k, True
    return 0.0, 0.0, False


def salary_policy_reason(salary_text: str, config: dict[str, Any] | None = None) -> str | None:
    """返回不符合薪资方案的原因；配置了薪资门槛时，无法解析也视为不符合。"""
    cfg = config or {}
    low_req = float(cfg.get("min_salary_low_k", 0) or 0)
    high_req = float(cfg.get("min_salary_high_k", 0) or 0)
    if not (low_req > 0 or high_req > 0):
        return None
    text = str(salary_text or "")
    if any(p in text for p in ("元/天", "日结", "日薪", "按天", "天结算", "/天")):
        return "按天/日结薪资格式"
    low, high, parsed = parse_salary_range(text)
    if not parsed:
        return "薪资无法解析"
    reasons = []
    if low_req and low < low_req:
        reasons.append("下限{}<{}K".format(low, low_req))
    if high_req and high < high_req:
        reasons.append("上限{}<{}K".format(high, high_req))
    return "且".join(reasons) or None


def extract_card_info(card: Any) -> dict[str, str]:
    title = safe_text(find_first(card, TITLE_LOCATORS, timeout=0.5))
    company = safe_text(find_first(card, COMPANY_LOCATORS, timeout=0.5))
    salary = safe_text(find_first(card, SALARY_LOCATORS, timeout=0.5))

    links = find_all(card, ["css:a"], timeout=0.2)
    href = ""
    for link in links:
        text = safe_text(link)
        link_href = safe_attr(link, "href")
        if not href and "/job_detail/" in link_href:
            href = urljoin("https://www.zhipin.com", link_href)
        if not company and text and text != title and "/gongsi/" in link_href:
            company = text
    if not href:
        link = find_first(card, ["css:a"], timeout=0.2)
        href = urljoin("https://www.zhipin.com", safe_attr(link, "href"))

    if not title:
        lines = [line.strip() for line in safe_text(card).splitlines() if line.strip()]
        title = lines[0] if lines else ""
        company = company or (lines[1] if len(lines) > 1 else "")

    return {
        "title": title,
        "company": company,
        "salary": salary,
        "href": href,
        "raw_text": safe_text(card),
    }


def extract_detail_text(tab: Any) -> str:
    detail_root = find_first(tab, DETAIL_LOCATORS, timeout=1.5)
    if detail_root is not None:
        try:
            detail_root.scroll.to_see()
        except Exception:
            pass
        smooth_scroll(detail_root, steps=4, min_pixel=240, max_pixel=520)
        text = safe_text(detail_root)
        if text:
            return text

    smooth_scroll(tab, steps=4, min_pixel=260, max_pixel=580)
    for locator in DETAIL_LOCATORS:
        root = find_first(tab, [locator], timeout=0.8)
        text = safe_text(root)
        if text:
            return text
    return safe_text(tab)


def click_apply_button(detail_tab: Any, greeting: str, browser: Any = None,
                       skill_dir: str | Path | None = None,
                       company: str = "", job: str = "") -> tuple[str, str]:
    # 2026-09-22 OUTCOME1：company/job 只用于**账本记录**（可追溯投了哪条），
    # 不参与任何判断。默认空串 → 老调用方（run_apply 内部流程）行为不变。
    from agent.ledger import record_action
    button = find_clickable_by_text(detail_tab, ["立即沟通", "继续沟通", "立即投递", "发送简历"])
    if button is None:
        record_action("greet", "failed", {"reason": "no_button"}, skill_dir=skill_dir)
        return "failed", "未找到立即沟通按钮。"

    button_text = safe_text(button)
    button_class = safe_attr(button, "class").lower()
    if any(flag in button_text for flag in ("已沟通", "继续沟通", "今日沟通上限", "停止招聘")):
        record_action("greet", "skipped", {"reason": button_text}, skill_dir=skill_dir)
        return "skipped", f"按钮状态不允许继续投递：{button_text}"
    if any(flag in button_class for flag in ("disabled", "is-disabled")):
        record_action("greet", "skipped", {"reason": "disabled"}, skill_dir=skill_dir)
        return "skipped", "立即沟通按钮处于禁用状态。"

    if not safe_click(button, by_js=None):
        if not safe_click(button, by_js=True):
            record_action("greet", "failed", {"reason": "click_failed"}, skill_dir=skill_dir)
            return "failed", "点击立即沟通失败。"

    pace_sleep(2.0, 3.5)

    # 打招呼策略：BOSS 点「立即沟通」后通常会自动发送平台默认话术（无法修改）。
    # 因此这里的 greeting 作为「补发」的定制招呼：优先在弹窗输入框填；
    # 若没有弹窗输入框（已进聊天页），则在「点沟通后激活的聊天标签页」用聊天输入框补发一句。
    # 补发失败不阻塞投递（BOSS 默认话术已发出，只是少补一句定制招呼）。
    if greeting:
        sent = False
        # 形态①：弹窗内有打招呼输入框（可填自定义招呼后发送）
        try:
            input_box = find_first(detail_tab, GREETING_INPUT_LOCATORS, timeout=1.2)
            if input_box is not None:
                safe_input(input_box, greeting, clear=True)
                send_button = find_clickable_by_text(detail_tab, ["发送", "发送消息", "打招呼"])
                if send_button is not None and safe_click(send_button, by_js=None):
                    pace_sleep(1.0, 2.0)
                    sent = True
        except Exception:
            sent = False
        # 形态②：点沟通后 BOSS 通常新开/切换聊天标签页，在聊天输入框补发定制招呼
        if not sent:
            try:
                from boss.boss_chat import send_chat_reply

                chat_tab = detail_tab
                if browser is not None:
                    try:
                        # latest_tab 是最后激活的标签页（点沟通后通常为聊天窗口）
                        chat_tab = browser.latest_tab
                    except Exception:
                        chat_tab = detail_tab
                sent = send_chat_reply(chat_tab, greeting)
            except Exception:
                sent = False
        if not sent:
            try:
                get_logger("job-hunter.boss").warning(
                    "补发定制打招呼失败（BOSS 默认话术已发出）：%s", greeting
                )
            except Exception:
                pass

    # 点击后必须确认页面状态，避免把点击无效/风控拦截误记为 applied，
    # 否则后续公司去重和停止计数都会被污染。
    success_markers = ("已沟通", "沟通成功", "已投递", "已申请", "职位申请成功", "发送成功")
    verified = False
    for _ in range(6):
        candidates = [detail_tab]
        if browser is not None:
            try:
                latest = browser.latest_tab
                if latest is not None and latest is not detail_tab:
                    candidates.append(latest)
            except Exception:
                pass
            try:
                for opened in browser.get_tabs():
                    if opened is not detail_tab and opened not in candidates:
                        candidates.append(opened)
            except Exception:
                pass
        for candidate in candidates:
            try:
                text = safe_text(candidate)
                url = str(getattr(candidate, "url", "") or "")
                if any(marker in text for marker in success_markers) or "/web/geek/chat" in url or "/web/chat" in url:
                    verified = True
                    break
            except Exception:
                continue
        if verified:
            break
        time.sleep(0.5)
    if not verified:
        record_action("greet", "failed", {"reason": "post_click_unverified", "button": button_text or "沟通"}, skill_dir=skill_dir)
        return "failed", "点击后未检测到已沟通/聊天成功状态，未记为投递成功。"

    record_action("greet", "applied",
                  {"button": button_text or "沟通",
                   "company": str(company or ""), "job": str(job or "")},
                  skill_dir=skill_dir)
    return "applied", button_text or "已点击立即沟通"




def _extract_job_url_id(url: str) -> str:
    """从岗位详情 URL 提取稳定 jobId：/job_detail/{id}.html → {id}。
    非岗位详情 URL（搜索页/公司页等）返回空串，不参与去重。"""
    if not url:
        return ""
    url = str(url).strip()
    marker = "/job_detail/"
    idx = url.find(marker)
    if idx < 0:
        return ""
    rest = url[idx + len(marker):]
    if "." in rest:
        rest = rest.split(".", 1)[0]
    return rest.strip()


def _recently_scored_keys(log_data: dict[str, Any], days: int = 14) -> set[str]:
    """收集「两周内」在 skipped 桶中**真正评分过**的岗位 job_key，
    用于避免重启后反复调用 LLM 重新评估同一岗位。

    「真正评分过」= 记录有有效分数（score > 0 或 llm_score > 0），即走完
    评分链路（含 LLM 失败后回退启发式评分的场景）得出过匹配分的岗位。

    纯规则跳过（标题排除词/按天日结/薪资不符等 score=0 且 llm_score=0、
    未经过评分）**不进入**两周去重：用户调整排除词/薪资门槛后这些岗位
    应立即重新评估，不应被锁死。

    直接读原始 records.skipped（不走 log_bucket_items/normalize），
    避免 normalize 给缺失 created_at 的旧记录补上当前时间导致误判为“两周内”。

    返回：{job_key: url_id}，url_id 为空表示该记录无有效岗位 URL。
    """
    cutoff = datetime.now() - timedelta(days=days)
    keys: dict[str, str] = {}
    raw_records = log_data.get("records", {}) if isinstance(log_data, dict) else {}
    for item in raw_records.get("skipped", []):
        if not isinstance(item, dict):
            continue
        # 只看「LLM 真正评分成功」的记录：llm_ok=True 才进入两周去重。
        # LLM 失败/未配置回退启发式评分（llm_ok=False）不算已评分，
        # 这些岗位重启后应重新调用 LLM 评估。
        llm_ok = item.get("llm_ok")
        if isinstance(llm_ok, bool):
            if not llm_ok:
                continue
        else:
            # 历史记录（无 llm_ok 字段）兼容判断，需同时满足：
            # 1) 有有效分数（score > 0，排除标题排除词/薪资不符/日结等纯规则跳过）；
            # 2) llm_reason 非空且非「未配置 LLM」固定失败文案
            #    （LLM 失败/未配置时 llm_reason 固定为
            #     「未配置 LLM，按技能重合和岗位相关性做估算。」）。
            try:
                _score = float(item.get("score") or 0)
            except (TypeError, ValueError):
                _score = 0.0
            if _score <= 0:
                continue
            llm_reason = str(item.get("llm_reason") or "")
            if not llm_reason or "未配置 LLM" in llm_reason:
                continue
        created = str(item.get("created_at") or "").strip()
        if not created:
            # 无有效时间戳的旧记录：不进入两周去重（避免误杀）
            continue
        try:
            ts = datetime.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if ts >= cutoff:
            jk = str(item.get("job_key") or "").strip()
            if jk:
                keys[jk] = _extract_job_url_id(str(item.get("url") or ""))
    return keys


def apply_jobs(
    *,
    task: JobTask,
    config: dict[str, Any] | None = None,
    browser: Any = None,
    skill_dir: Path | None = None,
) -> dict[str, Any]:
    skill_dir = resolve_skill_dir(skill_dir)
    cfg, browser, resume_text, llm_client = prepare_runtime(
        config=config,
        skill_dir=skill_dir,
        browser=browser,
        debug_port=task.debug_port,
    )
    cfg["min_score"] = int(cfg.get("min_score", 80) if config is None else config.get("min_score", cfg.get("min_score", 80)))
    logger = get_logger("job-hunter.boss", skill_dir=skill_dir)

    # 岗位专属分数/投放量覆盖：
    # 「海外运营总监 / 海外运营经理」匹配分放宽到 65，并加大扫描量，多投放这些高价值岗位。
    _role_boost = {
        "海外运营总监": (65, 60),
        "海外运营经理": (65, 60),
    }
    for _k, (_ms, _maxscan) in _role_boost.items():
        if _k in str(getattr(task, "job_name", "")):
            cfg["min_score"] = _ms
            cfg["max_scan_per_keyword"] = max(int(cfg.get("max_scan_per_keyword", 30) or 30), _maxscan)
            logger.info("岗位专属配置：%s 匹配分降至 %s，扫描上限提升至 %s。", _k, _ms, _maxscan)
            break
    run_mode = normalize_run_mode(getattr(task, "mode", None), cfg)
    dry_run = run_mode == "rehearsal"

    # P1 修复：未知城市报错停止，不静默变全国搜索
    if task.city not in CITY_CODES:
        raise ValueError(
            "城市「%s」不在支持列表里。请检查 config.json 里的城市名拼写。"
            "支持的城市：%s" % (task.city, "、".join(list(CITY_CODES.keys())[:20])))
    city_code = CITY_CODES[task.city]
    search_url = build_boss_search_url(task.job_name, city_code)

    # 平台执行函数自身也必须 fail-closed，不能依赖上层调度器先做登录检查。
    # 这样 CLI、Agent 直接调用 apply_jobs，以及重试路径都不会在匿名/未知状态下继续。
    login_state = check_boss_login(browser)
    if login_state != "ok":
        messages = {
            "login_required": "BOSS 当前未登录，请先在 9222 浏览器完成登录。",
            "blocked": "BOSS 当前处于安全验证/风控状态，请先人工处理。",
            "unknown": "无法确认 BOSS 登录状态，已安全停止。",
        }
        raise RuntimeError(messages.get(login_state, f"BOSS 登录状态异常：{login_state}"))

    log_file = skill_dir / f"boss-{task.city}-log.json"
    log_data = load_log(log_file)

    # P1 修复：failed 不进永久去重（临时网络/DOM 失败下次重试）
    history_buckets = ("applied",)
    seen_keys = {
        item.get("job_key", "")
        for bucket in history_buckets
        for item in log_bucket_items(log_data, bucket)
    }
    # 两周内评分过的岗位（skipped 桶）不再重新评估：避免重启后反复调 LLM 评同一岗位
    recently_scored_keys = _recently_scored_keys(log_data, days=14)
    # 公司级去重：同一家公司本轮/历史只投一次，避免多个岗位词投到同一家公司造成重复打招呼
    seen_companies = {
        str(item.get("company") or "").strip()
        for bucket in ("applied",)
        for item in log_bucket_items(log_data, bucket)
        if item.get("company")
    }
    run_id = start_log_run(
        log_data,
        platform=PLATFORM,
        task=task,
        min_score=int(cfg.get("min_score", 80) or 80),
    )

    tab = open_tab(browser, search_url)
    pace_sleep(1.5, 2.5)

    summary = {
        "platform": PLATFORM,
        "mode": run_mode,
        "run_id": run_id,
        "applied": 0,
        "greeted": 0,
        "resume_sent": 0,
        "reviewed": 0,
        "skipped": 0,
        "failed": 0,
        "count": task.count,
        "min_score": int(cfg.get("min_score", 80) or 80),
        "log_file": str(log_file),
        "message": "",
    }

    stop_cfg = cfg.get("stop_conditions", {}) or {}
    max_greeted = int(stop_cfg.get("max_greeted", 0) or 0)
    max_resume_sent = int(stop_cfg.get("max_resume_sent", 0) or 0)

    def _apply_stop_hit() -> bool:
        """正式投递时：打招呼满 max_greeted 或发送简历满 max_resume_sent，满足任一即停。"""
        if dry_run:
            return False
        if max_greeted and summary["greeted"] >= max_greeted:
            return True
        if max_resume_sent and summary["resume_sent"] >= max_resume_sent:
            return True
        return False

    idle_rounds = 0
    round_index = 0
    random_skip_remaining = 0
    # 每个关键词最多扫描的岗位数：扫满仍无达标即换下一个关键词，避免在低产出词上浪费大量时间
    max_scan_per_keyword = int(cfg.get("max_scan_per_keyword", 30) or 30)
    MAX_SCAN_ROUNDS = 8  # 单关键词页最多扫描 8 轮，多刷出岗位
    while (
        (summary["reviewed"] < task.count if dry_run else (summary["applied"] < task.count and not _apply_stop_hit()))
        and summary["reviewed"] < max_scan_per_keyword
        and idle_rounds < 3
        and round_index < MAX_SCAN_ROUNDS
    ):
        cards = find_all(tab, CARD_LOCATORS, timeout=2.0)
        if not cards:
            smooth_scroll(tab, steps=3, min_pixel=420, max_pixel=860)
            cards = find_all(tab, CARD_LOCATORS, timeout=2.0)
            if not cards:
                idle_rounds += 1
                continue

        round_index += 1
        logger.info("%s 第 %s 轮扫描，找到 %s 张卡片。", PLATFORM_NAME, round_index, len(cards))
        progressed = False

        for index in range(len(cards)):
            if dry_run and summary["reviewed"] >= task.count:
                break
            if not dry_run and (summary["applied"] >= task.count or _apply_stop_hit()):
                break

            cards = find_all(tab, CARD_LOCATORS, timeout=1.0)
            if index >= len(cards):
                break
            card = cards[index]

            info = extract_card_info(card)
            title = info["title"] or f"未命名岗位-{round_index}-{index}"
            company = info["company"] or "未知公司"
            job_key = make_job_key(PLATFORM, title, company)
            if job_key in seen_keys or log_contains(log_data, "applied", job_key):
                continue
            # 两周内评分过的岗位：不重新评估（避免重启后反复调 LLM 评同一岗位）。
            # 命中依据：job_key 相同，或岗位 URL jobId 相同（覆盖标题/公司名微调但同一岗位的情况）
            _url_id = _extract_job_url_id(str(info.get("href") or ""))
            _recent_job = recently_scored_keys.get(job_key)
            _url_hit = bool(_url_id) and _url_id in recently_scored_keys.values()
            if _recent_job is not None or _url_hit:
                summary["skipped"] += 1
                logger.info(
                    "%s | %s | 两周内已评分过，跳过不重复评估（job_key命中=%s, url命中=%s）。",
                    company, title, _recent_job is not None, _url_hit,
                )
                continue
            # 公司级去重：该公司已投过（无论岗位）则跳过，避免重复打招呼同一家公司
            if company in seen_companies:
                summary["skipped"] += 1
                logger.info("%s | %s | 公司已投过，去重跳过。", company, title)
                continue

            # P1 修复：公司去重延后到投递成功后，不提前加入
            # （同公司第一个岗位低分/按钮失败时，其他更合适岗位不会被误跳过）
            seen_keys.add(job_key)
            progressed = True

            # 卡片级标题预过滤：命中标题屏蔽词（TikTok/电商/跨境直播等）直接跳过，
            # 不点开详情页、不调 LLM，节省时间与 token。薪资门槛仍以详情页为准在下方判断。
            _title_clean = normalize_text(title)
            _title_blocked = None
            _block_kind = "标题排除关键词"
            for _kw in [*(cfg.get("title_exclude_keywords") or []), *(cfg.get("exclude_keywords") or [])]:
                if keyword_in_text(_kw, _title_clean):
                    _title_blocked = _kw
                    break
            # 2026-09-18 新增：公司名屏蔽（独立词表 company_exclude_keywords）。
            # 默认空数组 → 不配置时行为与改动前完全一致。
            if not _title_blocked:
                _co_kw = company_blocked(company, cfg)
                if _co_kw:
                    _title_blocked = _co_kw
                    _block_kind = "公司名屏蔽"
            if _title_blocked:
                logger.info(
                    "%s | %s | %s | 0分 | 命中%s：%s（卡片预过滤，未点开详情）",
                    company, title, info.get("salary", ""), _block_kind, _title_blocked,
                )
                summary["reviewed"] += 1
                summary["skipped"] += 1
                _rec = {
                    "platform": PLATFORM,
                    "company": company,
                    "job": title,
                    "salary": info.get("salary", ""),
                    "score": 0,
                    "rule_score": 0,
                    "llm_score": 0,
                    "reason": "命中%s：" % _block_kind + _title_blocked,
                    "llm_reason": "卡片预过滤，未进入 LLM 判定。",
                    "job_key": job_key,
                    "run_id": run_id,
                    "mode": run_mode,
                    "city": task.city,
                    "target_job": task.job_name,
                    "min_score": int(cfg.get("min_score", 80) or 80),
                    "url": info.get("href", ""),
                    "skip_reason": "命中%s：" % _block_kind + _title_blocked,
                }
                append_log(log_data, "skipped", _rec)
                save_log(log_data, log_file)
                pace_sleep(0.5, 1.0)  # 扫到不合适岗位，略作停顿
                continue

            between_jobs_sleep()  # 翻到下一个职位前的间隔
            detail_tab = None
            detail_url = info["href"]
            try:
                if detail_url:
                    detail_tab = open_tab(browser, detail_url)
                    read_job_sleep()  # 读取职位详情页 JD 的停留
                else:
                    if not safe_click(card, by_js=None):
                        safe_click(card, by_js=True)
                    pace_sleep(1.2, 2.2)
                    detail_tab = tab

                jd_text = extract_detail_text(detail_tab)
            except Exception:
                if detail_tab is not None and detail_tab is not tab:
                    try:
                        detail_tab.close()
                    except Exception:
                        pass
                raise

            # 详情页薪资更可靠：列表页薪资被 BOSS 直聘字体混淆（显示为乱码），详情页为明文
            salary_text = info["salary"]
            if detail_tab is not None:
                try:
                    sal_el = find_first(detail_tab, ["css:.salary"], timeout=0.8)
                    if sal_el is not None:
                        detail_salary = safe_text(sal_el)
                        if detail_salary:
                            salary_text = detail_salary
                except Exception:
                    pass

            # 读完详情页后再随机跳过：一次触发 1~4 个唯一岗位。
            if random_skip_remaining > 0 or random.random() < 0.10:
                if random_skip_remaining <= 0:
                    random_skip_remaining = random.randint(1, 4)
                random_skip_remaining -= 1
                logger.info("%s | 随机跳过岗位：%s", PLATFORM_NAME, title)
                summary["reviewed"] += 1
                summary["skipped"] += 1
                _rec = {"platform": PLATFORM, "company": company, "job": title,
                        "salary": salary_text, "score": 0, "rule_score": 0, "llm_score": 0,
                        "reason": "随机跳过岗位", "job_key": job_key, "run_id": run_id,
                        "mode": run_mode, "city": task.city}
                append_log(log_data, "skipped", _rec)
                save_log(log_data, log_file)
                continue

            # 薪资格式与方案门槛过滤：不符合或无法解析时均不进入 LLM。
            _salary_reason = salary_policy_reason(salary_text, cfg)
            if _salary_reason and _salary_reason == "按天/日结薪资格式":
                logger.info(
                    "%s | %s | %s | 按天/日结薪资格式，跳过。",
                    company,
                    title,
                    salary_text,
                )
                summary["reviewed"] += 1
                summary["skipped"] += 1
                record = {
                    "platform": PLATFORM,
                    "company": company,
                    "job": title,
                    "salary": salary_text,
                    "score": 0,
                    "rule_score": 0,
                    "llm_score": 0,
                    "reason": "按天/日结薪资格式，跳过",
                    "job_key": job_key,
                    "created_at": current_timestamp(),
                    "mode": run_mode,
                    "run_id": run_id,
                    "city": task.city,
                    "target_job": task.job_name,
                    "min_score": int(cfg.get("min_score", 80) or 80),
                    "url": getattr(detail_tab, "url", "") if detail_tab is not None else detail_url,
                }
                append_log(log_data, "skipped", record)
                save_log(log_data, log_file)
                if detail_tab is not None and detail_tab is not tab:
                    try:
                        detail_tab.close()
                    except Exception:
                        pass
                continue

            # 薪资门槛过滤：岗位薪资需满足「下限>=min_salary_low_k 且 上限>=min_salary_high_k」
            min_salary_low_k = float(cfg.get("min_salary_low_k", 0) or 0)
            min_salary_high_k = float(cfg.get("min_salary_high_k", 0) or 0)
            if min_salary_low_k > 0 or min_salary_high_k > 0:
                if _salary_reason and _salary_reason != "按天/日结薪资格式":
                    reason = _salary_reason
                    logger.info(
                        "%s | %s | %s | 薪资不符合要求(%s)，跳过。",
                        company,
                        title,
                        salary_text,
                        reason,
                    )
                    summary["reviewed"] += 1
                    record = {
                        "platform": PLATFORM,
                        "company": company,
                        "job": title,
                        "salary": salary_text,
                        "score": 0,
                        "rule_score": 0,
                        "llm_score": 0,
                        "reason": "薪资 {} 不符合要求(需下限≥{}K且上限≥{}K)".format(
                            salary_text, min_salary_low_k, min_salary_high_k
                        ),
                        "llm_reason": "",
                        "job_key": job_key,
                        "run_id": run_id,
                        "mode": run_mode,
                        "city": task.city,
                        "target_job": task.job_name,
                        "min_score": int(cfg.get("min_score", 80) or 80),
                        "url": "",
                    }
                    summary["skipped"] += 1
                    record["skip_reason"] = record["reason"]
                    append_log(log_data, "skipped", record)
                    save_log(log_data, log_file)
                    # 薪资不合适，短暂停顿再离开
                    pace_sleep(0.8, 1.5)
                    if detail_tab is not None and detail_tab is not tab:
                        try:
                            detail_tab.close()
                        except Exception:
                            pass
                    continue

            result: ScoreResult = score_jd(
                title,
                jd_text,
                cfg,
                skill_dir=skill_dir,
                resume_text=resume_text,
                llm_client=llm_client,
            )
            logger.info(
                "%s | %s | %s | %s分 | %s",
                company,
                title,
                salary_text,
                result.total_score,
                result.reason,
            )
            summary["reviewed"] += 1

            record = {
                "platform": PLATFORM,
                "company": company,
                "job": title,
                "salary": salary_text,
                "score": result.total_score,
                "rule_score": result.rule_score,
                "llm_score": result.llm_score,
                "reason": result.reason,
                "llm_reason": result.llm_reason,
                "llm_ok": result.llm_ok,
                "job_key": job_key,
                "run_id": run_id,
                "mode": run_mode,
                "city": task.city,
                "target_job": task.job_name,
                "min_score": int(cfg.get("min_score", 80) or 80),
                "url": getattr(detail_tab, "url", "") if detail_tab is not None else detail_url,
            }

            if result.decision != "apply":
                summary["skipped"] += 1
                record["skip_reason"] = result.reason
                append_log(log_data, "skipped", record)
                save_log(log_data, log_file)
                # 判断不合适，短暂停顿再离开
                pace_sleep(0.8, 1.5)
                if detail_tab is not None and detail_tab is not tab:
                    try:
                        detail_tab.close()
                    except Exception:
                        pass
                continue

            # 打招呼：仅使用 BOSS 平台默认固定话术（点「立即沟通」后 BOSS 自动发出），
            # 不再补发任何 LLM 生成或 config 自定义话术。
            try:
                greeting = ""
                if dry_run:
                    # P0 修复：rehearsal 模式不真点投递按钮，只记录"将投递"
                    status, apply_reason = "applied", "[rehearsal] 达标，演练模式不真实点击立即沟通"
                    logger.info("[演练·不点击] %s | %s", record.get("company", ""), record.get("target_job", ""))
                else:
                    logger.info("打招呼：使用 BOSS 平台默认固定话术（不补发自定义话术）")
                    # 确认合适后，稍作停顿再点击「立即沟通」
                    pace_sleep(1.0, 2.0)
                    status, apply_reason = click_apply_button(detail_tab, greeting, browser=browser,
                                                              skill_dir=skill_dir)
            except Exception as exc:
                status, apply_reason = "failed", str(exc)

            record["action_reason"] = apply_reason
            if status == "applied":
                summary["applied"] += 1
                summary["greeted"] += 1
                seen_companies.add(company)
                if "简历" in str(apply_reason):
                    summary["resume_sent"] += 1
                # P1 修复：rehearsal 写 preview bucket，不污染正式 applied 去重
                bucket = "preview" if dry_run else "applied"
                append_log(log_data, bucket, record)
            elif status == "skipped":
                summary["skipped"] += 1
                append_log(log_data, "skipped", record)
            else:
                summary["failed"] += 1
                append_log(log_data, "failed", record)
            save_log(log_data, log_file)
            if detail_tab is not None and detail_tab is not tab:
                try:
                    detail_tab.close()
                except Exception:
                    pass

            if dry_run and summary["reviewed"] < task.count:
                pace_sleep(1.0, 2.0)
            elif not dry_run and summary["applied"] < task.count and not _apply_stop_hit():
                pace_sleep(1.0, 2.0)

            # 清理多余标签页：点「立即沟通」后 BOSS 常新开聊天页，投递后这些历史详情/聊天页会累积，
            # 长时间运行导致浏览器变慢。保留搜索结果页与当前详情页，关闭其他无用 tab。
            if not dry_run:
                try:
                    # P1 修复：保留聊天页，不关掉聊天监听正在用的 tab
                    keep = [getattr(tab, "url", "") or "", search_url,
                            "https://www.zhipin.com/web/geek/chat"]
                    n_closed = cleanup_tabs(browser, keep_urls=keep, max_tabs=5)
                    if n_closed:
                        logger.info("标签页清理：关闭 %s 个无用 tab。", n_closed)
                except Exception:
                    pass

        previous_count = len(cards)
        smooth_scroll(tab, steps=3, min_pixel=480, max_pixel=980)
        current_count = len(find_all(tab, CARD_LOCATORS, timeout=1.2))
        # 9-10 整改：空转判定只看「本轮是否有新岗位进入处理流程」（progressed）。
        # 原逻辑 current_count > previous_count 会把空转计数清零（滚动总能加载出新卡片，
        # 但新卡片全被去重拦截时并无进展），导致单页无限翻页（9/9 夜间运营总监页翻 7 轮加载 90 张）。
        idle_rounds = 0 if progressed else idle_rounds + 1

        # 兜底清理：本轮所有职位已处理完，BOSS 异步打开的聊天 tab 此时已渲染。
        # 确保聊天页/历史详情页被关闭，避免 tab 长期累积导致浏览器变慢。
        if not dry_run:
            try:
                # P1 修复：保留聊天页（/web/geek/chat），不关掉聊天监听正在用的 tab
                keep = [getattr(tab, "url", "") or "", search_url,
                        "https://www.zhipin.com/web/geek/chat"]
                n_closed = cleanup_tabs(browser, keep_urls=keep, max_tabs=4)
                if n_closed:
                    logger.info("标签页清理(轮末)：关闭 %s 个无用 tab。", n_closed)
            except Exception:
                pass

    if dry_run:
        summary["message"] = f"{PLATFORM_NAME} {run_mode_label(run_mode)}完成，共检查 {summary['reviewed']} 条岗位。"
    else:
        stop_reason = ""
        if max_greeted and summary["greeted"] >= max_greeted:
            stop_reason = f"；已达打招呼上限 {max_greeted} 个"
        elif max_resume_sent and summary["resume_sent"] >= max_resume_sent:
            stop_reason = f"；已达发送简历上限 {max_resume_sent} 份"
        summary["message"] = f"{PLATFORM_NAME} {run_mode_label(run_mode)}完成（打招呼 {summary['greeted']} 个 / 发送简历 {summary['resume_sent']} 份{stop_reason}）。"
    finish_log_run(log_data, run_id, summary)
    save_log(log_data, log_file)
    return summary


def main() -> int:
    defaults = load_config(resolve_skill_dir())
    args = parse_args(int(defaults.get("default_count", 20)), int(defaults.get("min_score", 80)))
    skill_dir = resolve_skill_dir(args.skill_dir)
    config = load_config(skill_dir)
    config["min_score"] = args.min_score
    if args.mode:
        config["default_mode"] = args.mode
    if not wait_for_manual_login(
        skip_prompt=args.skip_login_prompt,
        platforms=[PLATFORM],
        config=config,
        skill_dir=skill_dir,
    ):
        print("用户取消执行。")
        return 0
    task = JobTask(
        job_name=args.job,
        city=args.city,
        count=args.count,
        platforms=[PLATFORM],
        mode=normalize_run_mode(args.mode, config),
        debug_port=args.port,
    )
    result = apply_jobs(task=task, config=config, skill_dir=skill_dir)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
