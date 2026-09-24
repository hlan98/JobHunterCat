"""Boss直聘聊天监听 + 自动发送简历模块。

在已登录的 BOSS 直聘聊天页上轮询会话：
- 检测对方"要简历"的两种形态：
  ① 系统"请求简历"（对方点了请求简历按钮，聊天内出现系统卡片/提示）
  ② 普通对话里文本问"能发一份简历吗"（文本意图识别）
- 命中且满足发送条件时，自动进入会话 -> 点「发简历」-> 在"请选择要发送的简历"弹窗中选中已上传附件简历 -> 点「发送」（无需重新上传本地文件）
- 兜底：若弹窗中没有已上传附件，才走"上传本地 PDF"旧路径
- 对方拒绝时，若配置了 reject_reply，发送礼貌致谢话术（提升活跃度）
- 防误发：每会话只发一次；跳过已拒绝会话；跳过已发送过简历的会话；只处理有明确要简历信号的会话

安全原则：默认 rehearsal（只检测、记录"将发送"，不真实点击发送）；apply 才真正发送。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from agent.shared import (
    build_llm_client,
    clamp_text,
    find_clickable_by_text,
    find_first,
    get_logger,
    pace_sleep,
    llm_quota_exhausted,
    load_config,
    normalize_text,
    normalize_run_mode,
    open_tab,
    resolve_skill_dir,
    safe_attr,
    safe_click,
    safe_text,
)

PLATFORM = "boss"
PLATFORM_NAME = "Boss直聘"
CHAT_URL = "https://www.zhipin.com/web/geek/chat"

# ---------- 会话列表 DOM ----------
FRIEND_ITEMS = ["css:li[role=listitem] .friend-content", "css:li[role=listitem]"]
NAME_LOCATORS = ["css:.name-text", "css:[class*=name-text]"]
LAST_MSG_LOCATORS = ["css:.last-msg-text", "css:[class*=last-msg-text]"]
UNREAD_LOCATORS = ["css:.notice-badge", "css:[class*=notice-badge]"]

# ---------- 消息区 DOM ----------
MESSAGE_ITEMS = ["css:.im-list .message-item", "css:li.message-item"]
FRIEND_MSG_CLASS = "item-friend"
MSG_TEXT_LOCATORS = ["css:.text-content", "css:p", "css:.text"]
SEND_RESUME_BTN = ["css:[d-c='62009']", "css:[aria-label*='求简历']", "css:[class*='toolbar']"]
# 选择已上传附件简历弹窗（点「发简历」后弹出，无需重新上传）
CHOOSE_DIALOG = ["css:.choose-resume-dialog", "css:[class*='choose-resume-dialog']"]
CHOOSE_LIST_ITEM = ["css:.resume-list .list-item", "css:[class*='resume-list'] [class*='list-item']"]
CHOOSE_RESUME_NAME = ["css:.resume-name", "css:[class*='resume-name']"]
CHOOSE_CONFIRM = ["css:.btn-confirm", "css:.footer button", "css:button.btn-sure-v2"]
# 旧版上传简历弹窗（备用：本地文件上传）
SELECT_DIALOG = ["css:.upload-select-dialog"]
SELECT_ONE = ["css:.upload-select-dialog .select-one"]
UPLOAD_DIALOG = ["css:.upload-resume-dialog"]
UPLOAD_FILE_INPUT = ["css:.upload-resume-dialog input[type=file]", "css:input[ka='user-resume-upload-file']"]
SEND_BUTTON_LOCATORS = ["css:.btn-send", "css:button[type=send]"]

# ---------- 要简历：文本意图（形态②：普通对话问简历） ----------
RESUME_REQUEST_PHRASES = [
    "简历发我", "发份简历", "发一份简历", "发我一份简历", "把简历发", "简历发过来",
    "发个简历", "发一下简历", "简历方便发", "能发份简历", "可以发份简历", "投一份简历",
    "发你的简历", "发来简历", "要一份简历", "给我一份简历", "简历给我", "简历能发",
    "方便发一下简历", "发一份你的简历", "请发简历", "发送简历", "简历发一", "发简历",
    "发份你的简历", "简历可以发", "简历发一份", "把您的简历发", "把你们的简历发",
    "send resume", "send your resume", "share resume", "resume please",
    # 2026-09-21 CARD1：日志里抓到的卡片首段文字是「看下简历」（用户指出这不是卡片正文，
    # 说明抓取只拿到了第一个节点 —— 见 CARD2）。
    # ⚠️ 这里**只加短、无歧义的短语**，刻意**不加**「看一下你的简历」「看简历」：
    #    「我**看了一下**你的简历，不太合适」（拒绝消息）会因此被误判成请求
    #    → **给拒绝你的人发简历**。现有单测 test_not_request_viewing 也断言
    #    「我看一下你的简历」不算请求。
    "看下简历", "看一下简历", "看看简历", "看份简历",
    "看下你的简历", "看下您的简历", "看看你的简历", "看看您的简历",
]

# 组合式：出现"简历/resume" 且 出现请求动词
RESUME_TOKEN_RE = re.compile(r"(简历|resume|cv)", re.IGNORECASE)
REQUEST_VERB_RE = re.compile(r"(发我|发过来|发份|发一份|发个|发一下|发下|方便发|可以发|能发|请发|发给我|给我发|投一份|投递|发送|发来|发你的|share|send)", re.IGNORECASE)

# ---------- 系统"请求简历"（形态①：系统卡片） ----------
SYSTEM_RESUME_REQUEST_PHRASES = [
    "请求你发送简历", "请求您的简历", "请求你的简历", "想要一份你的简历",
    "想要一份您的简历", "请发送你的简历", "请发送您的简历", "需要一份简历",
    "向您索要简历", "向你要一份简历", "请求发送简历", "request resume",
    "请求你发一份简历", "想要你的简历", "需要你的简历", "麻烦发一份简历",
    "方便发送一下简历", "方便发一下您的简历", "请发一份您的简历",
    "想要一份您的附件简历", "想要一份你的附件简历", "一份您的附件简历",
    "一份你的附件简历", "您的附件简历，您是否同意", "你的附件简历，您是否同意",
    "附件简历，您是否同意", "附件简历，是否同意",
]

# ---------- BOSS 系统自动回复模板（HR 未真正说话，仅平台模板） ----------
# 这是 BOSS 在「对方点击聊一聊/打招呼」后自动发出的系统话术，不代表 HR 真实意图。
# 检测必须足够严格：需同时满足多个特征，避免把 HR 真实消息（如"你好，在吗"）误判成模板。
BOSS_SYSTEM_TEMPLATE_PHRASES = [
    "您好，可以聊聊吗",
    "您这个职位我很有兴趣",
    "希望进一步了解",
]

# BOSS 系统 UI 卡片/通知（非 HR 对话），单独命中任意一条即视为系统消息，不应自动回复。
BOSS_SYSTEM_UI_PHRASES = [
    "你与该职位竞争者PK情况",
    "共人投递，你超过",
    "共 人投递，你超过",
    "优秀竞争者会",
    "查看详细分析",
    "该职位已被收藏",
    "你已收藏该职位",
    "对方已同意",
    "附件简历已发送",
    "已发送给Boss",
    "点击查看附件",
    "该职位已下线",
    "职位已停止招聘",
]

# ---------- 拒绝信号（对方不感兴趣） ----------
REJECTION_PHRASES = [
    # 2026-09-17 收紧：原表含大量「礼貌性泛词」。"感谢您" 几乎命中任何客套话，
    # 实测把「感谢您的投递。我们将在完成内部综合评估后…」判成拒绝 —— 这是中性回执，
    # 说明简历已送达、正在评估，却被自动回了「没关系，祝你生活愉快」，主动关掉机会。
    # 已删除：感谢关注 / 感谢您的关注 / 感谢投递 / 感谢您 / 抱歉 / 综合需求 / 暂不 / 已关闭
    #   「抱歉」多为「抱歉回复晚了」等非拒绝语境，真拒绝会由「不太合适」「已招满」命中；
    #   「已关闭」由更具体的「岗位已关闭」覆盖，避免「岗位未关闭」误命中。
    "不合适", "不匹配", "不打算", "不能共事", "很遗憾",
    "暂时不考虑", "不太合适", "其他候选人",
    "不符合", "未通过", "无法合作", "不考虑",
    "已经招满", "岗位已关闭", "停止招聘", "名额已满", "不再需要",
]

# ---------- 已发送成功信号 ----------
RESUME_SENT_CONFIRM_PHRASES = [
    "已发送给对方", "已发送给Boss", "附件简历 已发送", "简历已发送", "已发送简历",
    # 2026-09-09 实测：BOSS 在「发简历」流程后产生的系统确认文案为「附件简历请求已发送」，
    # 旧短语未覆盖导致发送成功被误判为失败（雾非雾事件根因之一）。
    "附件简历请求已发送", "简历请求已发送", "附件简历已发送给对方",
]

# ---------- 面试邀请信号 ----------
INTERVIEW_INVITE_PHRASES = [
    "约面试", "安排面试", "面试时间", "来面试", "面试一下", "约个时间面试",
    "方便来面试", "面试邀请", "可以面试", "约谈", "面试沟通", "进行面试",
]


def detect_resume_request_text(text: str) -> tuple[bool, str]:
    """检测单条文本是否是"要简历"请求。返回 (命中, 命中说明)。"""
    normalized = normalize_text(text)
    if not normalized:
        return False, ""
    lowered = normalized.lower()

    # 否定式拦截（最高优先）：明确表示"不要简历/不用发"时绝不触发，
    # 避免「你不需要发简历给我」「不用了谢谢」被「简历给我/发简历」等短语误判
    for neg in ("不需要", "不用", "无需", "不必", "别发", "不要发", "不用发",
                "不用了", "不发了", "免了", "别给我", "不用给我", "不需要给我"):
        if neg in normalized:
            return False, ""

    # 形态①：系统请求简历
    for phrase in SYSTEM_RESUME_REQUEST_PHRASES:
        if phrase.lower() in lowered:
            return True, f"系统请求简历：{phrase}"

    # 形态②：文本意图（普通对话）
    for phrase in RESUME_REQUEST_PHRASES:
        if phrase.lower() in lowered:
            return True, f"文本请求简历：{phrase}"

    # 组合式：简历 + 请求动词（排除"看简历/查看简历"这类非请求）
    if RESUME_TOKEN_RE.search(lowered) and REQUEST_VERB_RE.search(lowered):
        # 负向：纯展示型表达不触发
        for non_request in ("我看一下你的简历", "我看看你的简历", "请先完善简历", "先更新简历", "请更新简历"):
            if non_request in normalized:
                return False, ""
        return True, "简历+请求动词组合命中"

    return False, ""


def detect_rejection_text(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(phrase.lower() in lowered for phrase in REJECTION_PHRASES)


def detect_resume_sent_confirmation(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(phrase.lower() in lowered for phrase in RESUME_SENT_CONFIRM_PHRASES)


def detect_interview_invite(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(phrase.lower() in lowered for phrase in INTERVIEW_INVITE_PHRASES)


def classify_message(text: str) -> dict[str, bool]:
    """综合分类一条消息。"""
    return {
        "resume_request": detect_resume_request_text(text)[0],
        "rejection": detect_rejection_text(text),
        "resume_sent": detect_resume_sent_confirmation(text),
        "interview_invite": detect_interview_invite(text),
    }


def scan_conversations(tab: Any) -> list[dict[str, Any]]:
    """扫描会话列表，返回每个会话的元信息。"""
    results: list[dict[str, Any]] = []
    items = tab.eles("css:li[role=listitem]", timeout=2.0)
    for item in items:
        try:
            name = safe_text(find_first(item, NAME_LOCATORS, timeout=0.3))
            last_msg = safe_text(find_first(item, LAST_MSG_LOCATORS, timeout=0.3))
            unread_el = find_first(item, UNREAD_LOCATORS, timeout=0.2)
            unread = ""
            if unread_el is not None:
                unread = safe_text(unread_el)
            company = ""
            raw = normalize_text(safe_text(item))
            results.append(
                {
                    "name": name,
                    "company": company,
                    "last_msg": last_msg,
                    "unread": unread,
                    "raw": raw,
                    "element": item,
                }
            )
        except Exception:
            continue
    return results


def open_conversation(tab: Any, item: Any) -> bool:
    """点击进入某个会话。用物理点击（跟附件简历检测一致），不用JS点击。"""
    import sys as _sys
    if item is None:
        print("[打开会话] item 为 None，失败", file=_sys.stderr)
        return False
    try:
        item.scroll.to_see()
        import time as _t, random as _r
        _t.sleep(_r.uniform(0.2, 0.5))
        item.click()  # 物理点击，跟附件简历检测一致
        print("[打开会话] 物理点击成功", file=_sys.stderr)
        return True
    except Exception as e:
        print("[打开会话] 异常：%s" % e, file=_sys.stderr)
        return False


def read_friend_messages(tab: Any, limit: int = 20) -> list[str]:
    """读取当前会话中对方（item-friend）最近的消息文本。"""
    messages: list[str] = []
    try:
        items = tab.eles("css:.message-item", timeout=1.5)
    except Exception:
        return messages
    for item in items:
        try:
            class_attr = safe_attr(item, "class") or ""
            if FRIEND_MSG_CLASS not in class_attr:
                # 2026-09-21 CARD4：BOSS 的「请求简历卡片」是**系统卡片**，
                # 可能不带 item-friend → 原判定直接跳过它，卡片永远读不到。
                # 放宽：非对方消息，只要正文像请求简历卡片，也读进来。
                _ft0 = safe_text(item) or ""
                if not (("是否同意" in _ft0) and ("简历" in _ft0 or "附件" in _ft0)):
                    continue
            text = safe_text(find_first(item, MSG_TEXT_LOCATORS, timeout=0.2))
            # 2026-09-21 CARD2：卡片是「标题+说明+按钮」多段结构，
            # find_first 只取第一段 → 会漏掉「是否同意」这类关键信息
            # （实测：请求简历卡片只抓到标题「看下简历」，说明整段丢失）。
            # 兜底：整条消息的可见文字更长时，用它。
            _full = safe_text(item)
            if _full and (not text or len(_full) > len(text)):
                text = _full
            if text:
                messages.append(text)
        except Exception:
            continue
    return messages[-limit:]


def read_friend_messages_classified(tab: Any, limit: int = 20) -> list[dict[str, Any]]:
    """读取对方最近消息，并区分「系统自动回复模板」与「真实消息」。

    返回按时间升序的列表，每项 {"text": str, "is_system_template": bool}。
    BOSS 平台的系统模板话术（如「您好，可以聊聊吗？您这个职位我很有兴趣，希望进一步了解」）
    是 HR 侧自动回复，不代表对方真实意图，处理时应与真实消息区分对待。
    """
    entries: list[dict[str, Any]] = []
    try:
        items = tab.eles("css:.message-item", timeout=1.5)
    except Exception:
        return entries
    for item in items:
        try:
            class_attr = safe_attr(item, "class") or ""
            if FRIEND_MSG_CLASS not in class_attr:
                # 2026-09-21 CARD4：BOSS 的「请求简历卡片」是**系统卡片**，
                # 可能不带 item-friend → 原判定直接跳过它，卡片永远读不到。
                # 放宽：非对方消息，只要正文像请求简历卡片，也读进来。
                _ft0 = safe_text(item) or ""
                if not (("是否同意" in _ft0) and ("简历" in _ft0 or "附件" in _ft0)):
                    continue
            text = safe_text(find_first(item, MSG_TEXT_LOCATORS, timeout=0.2))
            # 2026-09-21 CARD2：同上 —— 卡片多段文字，只取第一段会漏「是否同意」
            _full = safe_text(item)
            if _full and (not text or len(_full) > len(text)):
                text = _full
            if text:
                entries.append(
                    {
                        "text": text,
                        "is_system_template": _is_boss_system_template(text),
                    }
                )
        except Exception:
            continue
    return entries[-limit:]


def _read_all_message_texts(tab: Any, limit: int = 40) -> list[str]:
    """读取当前会话所有消息文本（含 item-system 系统消息，如简历发送确认）。"""
    texts: list[str] = []
    try:
        items = tab.eles("css:.message-item", timeout=1.5)
    except Exception:
        return texts
    for item in items:
        try:
            text = safe_text(find_first(item, MSG_TEXT_LOCATORS, timeout=0.2))
            if text:
                texts.append(text)
        except Exception:
            continue
    return texts[-limit:]


def chat_has_resume_sent(tab: Any) -> bool:
    """当前会话是否已经发送过简历（防重复发送）。

    覆盖两类来源：
    1) 系统确认消息（item-system）：系统自动发送或用户手动发送后 BOSS 生成
       的「对方已同意，您的附件简历已发送给对方」等确认；
    2) 对方消息中的发送确认。
    """
    for text in _read_all_message_texts(tab, limit=40):
        if detect_resume_sent_confirmation(text):
            return True
    return False


def read_my_messages(tab: Any, limit: int = 20) -> list[str]:
    """读取当前会话中自己（item-myself）最近的消息文本。"""
    messages: list[str] = []
    try:
        items = tab.eles("css:.message-item", timeout=1.5)
    except Exception:
        return messages
    for item in items:
        try:
            class_attr = safe_attr(item, "class") or ""
            if "item-myself" not in class_attr:
                continue
            text = safe_text(find_first(item, MSG_TEXT_LOCATORS, timeout=0.2))
            if text:
                messages.append(text)
        except Exception:
            continue
    return messages[-limit:]


def chat_has_replied_thanks(tab: Any, replies: list[str] | None = None) -> bool:
    """当前会话是否已发过拒绝致谢（防重复发送）。

    直接检查聊天记录里是否有我们发出的致谢话术，不依赖易变的会话 key。

    2026-09-17 修复：原实现把待查文案**写死**为「谢谢您抽空沟通」，而实际发送的是
    config.reject_reply（本项目为「没关系，祝你生活愉快」），两者永不匹配 →
    本函数恒返回 False，防重复只剩「按会话名」一条腿，同一会话会被重复发致谢。
    现在优先用调用方传入的候选文案（来自配置），并保留旧写死文案做历史兼容。
    """
    candidates = [c for c in (replies or []) if c]
    _legacy = "谢谢您抽空沟通"
    if _legacy not in candidates:
        candidates.append(_legacy)
    for text in read_my_messages(tab, limit=30):
        _t = text or ""
        if any(c in _t for c in candidates):
            return True
    return False


def click_resume_card_agree(tab: Any) -> bool:
    """点击请求简历卡片上的「同意」按钮。

    场景：HR 通过 BOSS 系统卡片「我想要一份您的附件简历，您是否同意 拒绝 同意」请求简历。
    卡片带「同意/拒绝」按钮，点「同意」后 BOSS 会弹出选择简历弹窗（与工具栏「发简历」同流程）。
    若检测到卡片存在，优先点「同意」而非工具栏「发简历」，保证走正常同意流程。
    """
    try:
        # 检测卡片是否存在：消息里含"是否同意" + "附件简历"
        found_card = False
        try:
            items = tab.eles("css:.message-item", timeout=1.0)
            for it in items:
                cls_attr = (safe_attr(it, "class") or "")
                if "item-friend" not in cls_attr:
                    # 2026-09-21 CARD4：同上 —— 系统卡片可能不带 item-friend，
                    # 只要正文像请求简历卡片就继续判（下面还会再校验文字）。
                    _ft0 = safe_text(it) or ""
                    if not (("是否同意" in _ft0) and ("简历" in _ft0 or "附件" in _ft0)):
                        continue
                t = safe_text(find_first(it, MSG_TEXT_LOCATORS, timeout=0.2)) or ""
                # 2026-09-21 CARD2：卡片正文（「我想要一份您的附件简历，您是否同意」）
                # 不在 .text-content/p/.text 里 → 上面取不到 → 卡片永远判不出来。
                # 用户实测卡片内容就是这两行：
                #     我想要一份您的附件简历，您是否同意
                #     拒绝  同意
                # 所以这里也要用整条消息文字兜底。
                _ft = safe_text(it) or ""
                if len(_ft) > len(t):
                    t = _ft
                # 2026-09-21 CARD1：BOSS 换了卡片文案 —— 老版含「是否同意」，
                # 新版直接显示「看下简历」（实测日志里「是否同意」一次都没出现过）。
                # 只要"提到简历/附件"且带"请求语义"就认为是卡片。
                if ("简历" in t or "附件" in t) and (
                        "是否同意" in t or "看下简历" in t or "看一下简历" in t
                        or "看看简历" in t or "看份简历" in t or "请求" in t):
                    found_card = True
                    break
        except Exception:
            pass
        if not found_card:
            return False
        # 找「同意」按钮（卡片上的明确按钮，避免误点其他）
        for locator in (
            "css:button",
            "css:.btn",
            "css:[class*=agree]",
            "css:[class*=btn]",
        ):
            try:
                els = tab.eles(locator, timeout=0.5)
            except Exception:
                continue
            for el in els:
                try:
                    t = (safe_text(el) or "").strip()
                except Exception:
                    continue
                if t in ("同意", "同意发送", "确认同意"):
                    if safe_click(el, by_js=None) or safe_click(el, by_js=True):
                        pace_sleep(2.0, 3.0)
                        return True
        # 兜底：find_clickable_by_text 精确找"同意"
        btn = find_clickable_by_text(tab, ["同意"])
        if btn is not None:
            if safe_click(btn, by_js=None) or safe_click(btn, by_js=True):
                pace_sleep(2.0, 3.0)
                return True
        return False
    except Exception:
        return False


def click_send_resume_button(tab: Any) -> bool:
    """点击聊天工具栏的「发简历」按钮。

    实测（2026-09-02）：按钮 `div[d-c='62009']` 需先滚动到可视再 click(by_js=True) 才能触发弹窗。
    """
    btn = None
    for locator in ("css:[d-c='62009']", "css:div.toolbar-btn"):
        try:
            el = tab.ele(locator, timeout=0.6)
            label = " ".join(filter(None, (
                safe_text(el),
                safe_attr(el, "aria-label"),
                safe_attr(el, "title"),
            )))
            if el is not None and "发简历" in label:
                btn = el
                break
        except Exception:
            continue
    if btn is None:
        btn = find_clickable_by_text(tab, ["发简历"])
    if btn is None:
        return False
    # 检查是否禁用（双方未回复时 disabled，对方要简历时必已回复，按钮必可用）
    class_attr = (safe_attr(btn, "class") or "").lower()
    if "unable" in class_attr or "disabled" in class_attr:
        return False
    if not safe_click(btn, by_js=None):
        if not safe_click(btn, by_js=True):
            return False
    pace_sleep(1.5, 2.5)
    return True


def select_existing_resume(tab: Any, resume_name: str = "") -> bool:
    """在「请选择要发送的简历」弹窗中，选中已上传的附件简历（无需重新上传）。

    resume_name 为空时按弹窗内第一份简历兜底（不写死任何用户真实简历名）。

    弹窗结构（chat_dialog2.html 实测）：
      div.choose-resume-dialog > ul.resume-list > li.list-item
        每个 li 内有 .resume-name（文件名）、.item-desc（更新时间/大小）、.preview（预览）
      底部 footer > button.btn-confirm（初始 disabled=disabled，选中后激活）
    选中后返回 True。
    """
    dialog = find_first(tab, CHOOSE_DIALOG, timeout=3.0)
    if dialog is None:
        # 弹窗可能仍在渲染，再等一次
        pace_sleep(1.0, 2.0)
        dialog = find_first(tab, CHOOSE_DIALOG, timeout=2.0)
    if dialog is None:
        return False
    items = dialog.eles("css:.resume-list .list-item", timeout=1.0)
    if not items:
        items = dialog.eles("css:li.list-item", timeout=1.0)
    for item in items:
        name_el = find_first(item, ["css:.resume-name"], timeout=0.5)
        if name_el is None:
            continue
        name = safe_text(name_el).strip()
        if not name:
            continue
        # 精确命中目标文件名（含容错：忽略空白/大小写）
        if name.replace(" ", "") == resume_name.replace(" ", ""):
            if safe_click(item, by_js=None) or safe_click(item, by_js=True):
                pace_sleep(1.0, 2.0)
                return True
    return False


def select_upload_resume_option(tab: Any) -> bool:
    """（旧版兜底）在「上传简历 / 发送在线简历」选择弹窗中选择「上传简历」（附件简历）。"""
    dialog = find_first(tab, SELECT_DIALOG, timeout=1.5)
    if dialog is None:
        return False
    select_ones = dialog.eles("css:.select-one", timeout=0.8)
    if not select_ones:
        select_ones = tab.eles("css:.upload-select-dialog .select-one", timeout=0.8)
    if not select_ones:
        return False
    # 第一个 select-one 是「上传简历」
    if not safe_click(select_ones[0], by_js=None):
        if not safe_click(select_ones[0], by_js=True):
            return False
    pace_sleep(1.0, 2.0)
    return True


def upload_resume_file(tab: Any, resume_pdf: str | Path) -> bool:
    """（旧版兜底）若出现上传弹窗，则通过 file input 上传本地 PDF 简历。"""
    dialog = find_first(tab, UPLOAD_DIALOG, timeout=1.5)
    if dialog is None:
        return False
    file_input = find_first(dialog, UPLOAD_FILE_INPUT, timeout=1.0)
    if file_input is None:
        file_input = find_first(tab, UPLOAD_FILE_INPUT, timeout=0.8)
    if file_input is None:
        return False
    try:
        file_input.input(str(resume_pdf))
        pace_sleep(2.0, 3.5)
        return True
    except Exception:
        return False


def confirm_and_send(tab: Any) -> bool:
    """发送简历：找到确认/发送按钮并点击。

    优先点击「请选择要发送的简历」弹窗底部的 .btn-confirm（选中附件后由 disabled 变可用）。
    找不到时回退旧版弹窗/输入区发送按钮。
    """
    # 首选：choose-resume-dialog 弹窗内的「发送」按钮
    dialog = find_first(tab, CHOOSE_DIALOG, timeout=1.5)
    if dialog is not None:
        for locator in ("css:.btn-confirm", "css:footer button", "css:button.btn-sure-v2"):
            try:
                el = dialog.ele(locator, timeout=0.6)
            except Exception:
                continue
            if el is None:
                continue
            class_attr = safe_attr(el, "class") or ""
            if "disabled" in class_attr.lower() or "unable" in class_attr.lower():
                continue
            if safe_click(el, by_js=None) or safe_click(el, by_js=True):
                pace_sleep(1.5, 2.5)
                return True
    # 兜底：旧版弹窗内的确认按钮（发送/确定/确认/同意）
    candidates = [
        "css:.dialog-container .btn-sure-v2",
        "css:.dialog-container button",
        "css:.dialog-container [class*=sure]",
        "css:.btn-send",
        "css:button[type=send]",
    ]
    for locator in candidates:
        try:
            els = tab.eles(locator, timeout=0.5)
        except Exception:
            continue
        for el in els:
            text = safe_text(el)
            class_attr = safe_attr(el, "class") or ""
            if "disabled" in class_attr.lower() or "unable" in class_attr.lower():
                continue
            if any(k in text for k in ("发送", "确定", "确认", "同意")):
                if safe_click(el, by_js=None) or safe_click(el, by_js=True):
                    pace_sleep(1.0, 2.0)
                    return True
    # 再兜底：点输入区发送按钮
    send_btn = find_first(tab, SEND_BUTTON_LOCATORS, timeout=0.5)
    if send_btn is not None:
        class_attr = safe_attr(send_btn, "class") or ""
        if "disabled" not in class_attr.lower():
            if safe_click(send_btn, by_js=None) or safe_click(send_btn, by_js=True):
                pace_sleep(1.0, 2.0)
                return True
    return False


def send_reject_reply(tab: Any, reply: str) -> bool:
    """对方拒绝时发送礼貌致谢话术（提升活跃度，不催不问）。"""
    if not reply:
        return False
    try:
        input_box = tab.ele("css:#chat-input", timeout=1.0)
        if input_box is None:
            input_box = find_first(tab, ["css:[contenteditable='true']"], timeout=0.8)
        if input_box is None:
            return False
        input_box.click()
        input_box.input(reply, clear=True)
        pace_sleep(0.8, 1.5)
        send_btn = find_first(tab, SEND_BUTTON_LOCATORS, timeout=0.8)
        if send_btn is not None and "disabled" not in (safe_attr(send_btn, "class") or ""):
            if safe_click(send_btn, by_js=None) or safe_click(send_btn, by_js=True):
                pace_sleep(1.0, 2.0)
                return True
    except Exception:
        pass
    return False


# ---------- 普通对话自动回复（用用户语气回答对方问题） ----------
# 拿不准、涉及具体承诺/数字/隐私的问题，必须停下提醒用户接管
ESCALATE_KEYWORDS = [
    "薪资", "工资", "薪酬", "待遇", "薪水", "多少钱", "k薪", "月薪", "年薪",
    "到岗", "入职时间", "什么时候能入职", "何时入职", "什么时候入职", "报道时间", "入职日期",
    "期望薪资", "薪资要求", "薪资预期", "最低多少",
    "手机号", "电话", "微信", "联系方式", "加个微信",
    "目前在职", "是否在职", "离职状态", "离职证明",
    "什么时候到岗", "能接受加班", "加班", "996",
    "base", "package", "offer", "公积金", "社保",
]

# 薪资单位「数字+k」写法（如 20k / 15-25k / 2w 等），单独命中即需用户确认
SALARY_K_RE = re.compile(r"\d+\s*[-~—–]?\s*\d*\s*[kKwW]")

# 普通寒暄/信息类，可安全自动回复
SAFE_REPLY_HINTS = [
    "你好", "您好", "在吗", "在么", "方便聊聊", "可以聊聊", "有兴趣", "简单介绍",
    "自我介绍", "介绍一下", "工作经验", "做过", "负责过", "了解岗位", "看过岗位",
]


def should_escalate_to_user(message: str) -> tuple[bool, str]:
    """规则兜底：消息涉及具体承诺/数字/隐私/时间等拿不准的问题 → 交给用户。"""
    normalized = normalize_text(message)
    if not normalized:
        return False, ""
    lowered = normalized.lower()
    # 先查薪资单位「数字+k」模式（如 20k / 15-25k），避免把「ok」「look」中的字母 k 误判
    if SALARY_K_RE.search(lowered):
        return True, "涉及薪资数字（如 XX K）"
    for kw in ESCALATE_KEYWORDS:
        if kw.lower() in lowered:
            return True, f"涉及敏感信息：{kw}"
    return False, ""


def _is_boss_system_template(message: str) -> bool:
    """对方消息是否为 BOSS 系统自动回复模板（HR 未真正说话）。

    两类判定：
    1. 系统 UI 卡片/通知（如 PK 卡片、简历发送确认、职位下线）—— 单独命中任意一条即 True。
    2. 打招呼模板 —— 要求至少命中 2 个模板特征短语，避免把 HR 真实短消息（如"你好，在吗"）误判成模板。
    """
    m = (message or "").strip()
    if not m:
        return False
    normalized = normalize_text(m)
    if any(p in normalized for p in BOSS_SYSTEM_UI_PHRASES):
        return True
    hits = sum(1 for p in BOSS_SYSTEM_TEMPLATE_PHRASES if p in normalized)
    return hits >= 2


def generate_conversation_reply(
    llm: Any,
    resume_text: str,
    position_hint: str,
    message: str,
    is_template: bool = False,
    applicant_name: str = "",
) -> tuple[bool, str]:
    """用 LLM 以候选人语气生成对普通消息的回复。

    返回 (是否应回复, 回复文本)。拿不准/敏感问题由 should_escalate_to_user 先拦截。

    applicant_name：候选人姓名（从配置读取，可选）。不传则用中性身份
    （「本简历的求职者本人」），避免写死任何真实姓名，防隐私泄漏。

    is_template=True 表示对方消息是平台自动回复模板（HR 未真正说话）：
    此时不客套，直接自我介绍匹配点并抛一个岗位相关问题，主动推进对话。
    """
    if llm is None or not getattr(llm, "is_configured", lambda: False)():
        return False, ""
    _name = (applicant_name or "").strip()
    _who = ("你是求职者%s，正在BOSS直聘上与招聘方沟通。" % _name) if _name else \
        "你是本简历的求职者本人，正在BOSS直聘上与招聘方沟通。"
    if is_template:
        system_prompt = (
            _who +
            "对方只发来平台自动回复模板「您好，可以聊聊吗？您这个职位我很有兴趣，希望进一步了解」，"
            "对方并没有真正说话或表示认可，因此："
            "①绝对不要以「感谢认可/谢谢认可/感谢您的关注/谢谢」等客套话开头；"
            "②直接自然切入：用一两句话简短介绍自己与岗位的匹配点（只谈职业方向、技能、经验领域，不出现任何数字）；"
            "③结尾抛一个与岗位相关的具体问题（如团队规模、业务现状、核心目标等），主动推进对话；"
            "④总长不超过120字；⑤不得出现任何具体薪资数字、到岗日期承诺；"
            "⑥若岗位信息不足以支撑提问，输出 ONLY_ESCALATE。"
            "只输出回复内容本身，不要任何前缀或解释。"
        )
    else:
        system_prompt = (
            _who +
            "请以本人的语气、用第一人称「我」自然回复对方消息。要求："
            "①只谈职业发展方向、技能匹配度、经验领域与协作能力；"
            "②回答要简洁自然、口语化，不超过120字；"
            "③若对方询问的细节你在简历中不掌握，或涉及薪资、到岗时间、具体数字承诺、隐私等拿不准的内容，"
            "统一输出 ONLY_ESCALATE 表示无法回答需要用户接管；"
            "④不得编造简历之外的具体业绩数字；"
            "⑤不得出现任何具体薪资数字、到岗日期承诺。"
            "只输出回复内容本身，不要任何前缀或解释。"
        )
    user_prompt = (
        f"【我的简历摘要】\n{clamp_text(resume_text, 1500)}\n\n"
        f"【当前沟通的岗位】\n{position_hint}\n\n"
        f"【对方最新消息】\n{message}\n\n"
        "请给出回复（或 ONLY_ESCALATE）："
    )
    try:
        # 2026-09-24 MAXTOK：300 会被推理预算吃光（实测同类调用 900 都会空），抬到 1200
        reply = llm.chat_text(system_prompt, user_prompt, max_tokens=1200, temperature=0.4)
    except Exception:
        return False, ""
    reply = reply.strip()
    if not reply:
        return False, ""
    if "ONLY_ESCALATE" in reply.upper():
        return False, ""
    # 保险：回复里若出现具体数字承诺/薪资，仍拦截
    esc, _ = should_escalate_to_user(reply)
    if esc:
        return False, ""
    # 模板场景（对方未真正说话）的回复不得出现任何数字/数据（与打招呼规则一致）
    if is_template and re.search(r"\d", reply):
        return False, ""
    return True, reply


def send_chat_reply(tab: Any, reply: str) -> bool:
    """向当前会话发送一条普通文本回复（复用拒绝话术的发送链路）。"""
    if not reply:
        return False
    try:
        input_box = tab.ele("css:#chat-input", timeout=1.0)
        if input_box is None:
            input_box = find_first(tab, ["css:[contenteditable='true']"], timeout=0.8)
        if input_box is None:
            return False
        input_box.click()
        input_box.input(reply, clear=True)
        pace_sleep(0.8, 1.5)
        send_btn = find_first(tab, SEND_BUTTON_LOCATORS, timeout=0.8)
        if send_btn is not None and "disabled" not in (safe_attr(send_btn, "class") or ""):
            if safe_click(send_btn, by_js=None) or safe_click(send_btn, by_js=True):
                pace_sleep(1.0, 2.0)
                return True
    except Exception:
        pass
    return False
def _normalize_processed_entries(state: dict[str, Any]) -> dict[str, Any]:
    """把 processed 中的旧格式条目（整条 raw，如「14:51 樊女士…」）归一化为 HR 姓名。

    旧实现用整条 raw 做会话 key，每次扫描 raw 都变导致同一 HR 反复被处理；
    新实现用 HR 姓名做稳定 key。此函数负责迁移历史条目，避免旧 key 永不匹配。
    """
    import re as _re

    def _to_name(entry: str) -> str:
        entry = normalize_text(entry)
        # 形如「14:51 樊女士广州奥丝科技…」→ 取时间后的第一个词
        m = _re.match(r"^\d{1,2}:\d{2}\s*(\S+)", entry)
        token = m.group(1) if m else (entry.split()[0] if entry.split() else entry)
        # 称谓标记：先生/女士/HR/招聘/总监/经理/主管/专员/主任/总裁/负责人/助理 等
        title_pat = _re.compile(
            r"(女士|先生|小姐|老师|HRBP|HR|招聘|总监|经理|主管|专员|主任|总裁|负责人|助理)"
        )
        tm = title_pat.search(token)
        if tm:
            # 取称谓之前的中文名（1~6 字）+ 称谓本身
            pre = tm.start()
            name_part = token[:pre]
            # name_part 可能是「樊女士」中的樊 或「石茹翎度数字」整段；只保留末尾 2~4 个中文字
            zh = _re.findall(r"[\u4e00-\u9fa5]+", name_part)
            if zh:
                last_zh = zh[-1]
                return last_zh[-4:] + tm.group(1)
            return token[:8]
        # 无称谓标记：取前 2~4 个中文字作为标识（如「周治成飞书深诺」→「周治成」）
        m3 = _re.match(r"^([\u4e00-\u9fa5]{2,4})", token)
        if m3:
            return m3.group(1)
        return token[:8]

    processed = state.get("processed")
    if isinstance(processed, list):
        # 兼容旧版 list 格式：转成 dict（key=HR名, value=最后消息摘要）
        names: set[str] = set()
        for entry in processed:
            if not isinstance(entry, str):
                continue
            nm = _to_name(entry)
            if nm and len(nm) <= 8:
                names.add(nm)
        state["processed"] = {n: "" for n in names}
    elif not isinstance(processed, dict):
        state["processed"] = {}
    return state


def load_chat_state(skill_dir: Path) -> dict[str, Any]:
    state_file = skill_dir / "chat-state.json"
    defaults = {"processed": {}, "resume_sent": [], "reject_replied": [], "chat_replied": []}
    if state_file.exists():
        try:
            raw = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in defaults.items():
                    raw.setdefault(key, list(value))
                return _normalize_processed_entries(raw)
        except Exception:
            pass
    return defaults


def save_chat_state(state: dict[str, Any], skill_dir: Path) -> None:
    state_file = skill_dir / "chat-state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _conversation_key(raw: str) -> str:
    return normalize_text(raw)


def _stable_conversation_key(conv: dict[str, Any]) -> str:
    """生成稳定的会话标识：HR 姓名。

    会话列表项 raw 每次扫描都会变（时间戳、最新消息、送达状态、消息内容都在变），
    若用它做 key，同一会话每轮都会生成不同 key → 重复发送。HR 姓名字段是稳定的。
    不同公司同姓 HR 的 key 可能冲突，但重复发送由
    chat_has_replied_thanks / chat_has_resume_sent 的「聊天记录」检查兜底，故可接受。
    """
    return normalize_text(conv.get("name") or "")


def resolve_company_from_text(text: str, known: list[str]) -> str:
    """从一段会话文本里认出公司名（**最长匹配**，避免短名误命中）。

    2026-09-22 CONV1：`scan_conversations` 的 company 字段恒为空字符串
    （会话列表项只有一整坨文本，形如「15:51 郭女士克洛斯人事经理 [送达] 你好…」，
    公司名夹在 HR 姓名和职位之间、没有稳定分隔符，选择器拆不出来）。

    于是改用已知公司名去文本里匹配，并取**最长**的命中 ——
    否则「广州」会吃掉「广州华越服饰有限公司」这类包含关系。
    """
    hay = normalize_text(text or "")
    if not hay:
        return ""
    best = ""
    for name in known or []:
        nm = normalize_text(str(name or ""))
        if len(nm) < 2:
            continue
        if nm in hay and len(nm) > len(best):
            best = nm
    return best


def load_greeted_companies(skill_dir: Path, *, include_preview: bool = False) -> list[str]:
    """从投递日志中读取已打招呼（apply 真实投递）的公司名白名单。

    只有我们主动打过招呼的公司，聊天监听才处理其 HR 会话。
    """
    return sorted({x["company"] for x in load_greeted_targets(skill_dir, include_preview=include_preview) if x.get("company")})


def load_greeted_targets(skill_dir: Path, *, include_preview: bool = False) -> list[dict[str, str]]:
    """读取打招呼白名单目标，优先使用 company + hr_name 组合。

    旧记录没有 hr_name 时保留空值，监听端按公司回退兼容；新记录一旦带 HR 姓名，
    则必须公司和姓名同时命中。BOSS 岗位页有时拿不到 HR 姓名，因此空姓名是可预期的。
    """
    targets: set[tuple[str, str]] = set()
    log_paths = []
    for pattern in ("boss-*-log.json",):
        log_paths.extend(skill_dir.glob(pattern))
    # 桌面演练使用独立日志；仅 rehearsal 可将其作为预览白名单。
    if include_preview:
        demo_log = skill_dir / "boss-demo-log.json"
        if demo_log.exists():
            log_paths.append(demo_log)
    for log_file in log_paths:
        try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                records = list(data.get("records", {}).get("applied") or [])
                # preview 只在演练监听中显式纳入；正式模式绝不能把历史演练
                # 当成真实投递，否则会错误放行/屏蔽 HR 会话。
                if include_preview:
                    records.extend(data.get("records", {}).get("preview") or [])
                for rec in records:
                    company = normalize_text(str(rec.get("company") or "").strip())
                    hr_name = normalize_text(str(rec.get("hr_name") or rec.get("recruiter") or "").strip())
                    if company:
                        targets.add((company, hr_name))
        except Exception:
            continue
    return [{"company": c, "hr_name": h} for c, h in sorted(targets)]


def _user_stop_requested(skill_dir) -> bool:
    """是否已存在用户「停止」标记（manual_stop.flag）。读取失败按「未停止」处理。

    2026-09-17 新增：run_chat_monitor 原先只检查 LLM 配额、不检查停止标记，
    导致用户按「停止」后监听仍继续跑（实测 22:31:11 停 → 22:32:28 才结束，77 秒），
    期间持续访问 BOSS 页面。
    """
    try:
        return (Path(skill_dir) / "manual_stop.flag").exists()
    except Exception:
        return False


def run_chat_monitor(
    *,
    config: dict[str, Any] | None = None,
    browser: Any = None,
    skill_dir: Path | None = None,
    debug_port: int = 9222,
    mode: str = "rehearsal",
    rounds: int = 5,
    interval: float = 30.0,
    resume_pdf: str | Path | None = None,
    baseline_companies: list[str] | None = None,
) -> dict[str, Any]:
    """轮询 BOSS 聊天页，处理要简历/拒绝场景。

    mode=rehearsal：只检测并记录"将发送"，不真实点击发送。
    mode=apply：真实发送简历/拒绝话术。

    baseline_companies：本轮投递开始前已打招呼的公司集合。传入后，
    仅监听「本轮新增打招呼」的公司（当前累计 − baseline），避免处理历史轮次的 HR。
    """
    skill_dir = resolve_skill_dir(skill_dir)
    cfg = load_config(skill_dir) if config is None else config
    mode = normalize_run_mode(mode, cfg)
    logger = get_logger("job-hunter.boss-chat", skill_dir=skill_dir)

    if browser is None:
        from agent.shared import connect_browser

        browser = connect_browser(debug_port=debug_port)

    resume_path = resume_pdf or cfg.get("resume_pdf_path") or cfg.get("resume_path", "")
    if resume_path:
        _rp = Path(str(resume_path)).expanduser()
        if not _rp.is_absolute():
            _rp = skill_dir / _rp
        resume_path = str(_rp.resolve())
    llm = build_llm_client(cfg, skill_dir=skill_dir)
    llm_enabled = llm.is_configured()

    state = load_chat_state(skill_dir)
    # 只监听本轮新增打招呼的 HR 会话（当前累计 − 本轮开始前基线）
    only_greeted = bool(cfg.get("only_greeted_hr", False))  # 改为默认 False：全部会话都检查，不按白名单过滤
    all_targets = load_greeted_targets(
        skill_dir, include_preview=(mode == "rehearsal")
    ) if only_greeted else []
    baseline = set(baseline_companies or [])
    greeted_targets = [x for x in all_targets if x.get("company") not in baseline] if only_greeted else []
    greeted_companies = sorted({x.get("company") for x in greeted_targets if x.get("company")})
    if only_greeted:
        logger.info("仅监听本轮新增打招呼的公司：%s", greeted_companies or "（本轮暂无新增）")
    summary = {
        "platform": PLATFORM,
        "mode": mode,
        "rounds_scanned": 0,
        "conversations_seen": 0,
        "resume_requests_detected": 0,
        "resume_sent": 0,
        "rejections_detected": 0,
        "reject_replies_sent": 0,
        "interview_invites_detected": 0,
        "chat_replies_sent": 0,
        "chat_escalated_to_user": 0,
        "quota_exhausted": False,
        "stopped_by_user": False,
        "skipped": 0,
        "actions": [],
    }

    # 修复 tab bug：打开 tab 前记录 tab 数量，结束时只关自己新开的 tab
    # （如果 open_tab 退回到主 tab，关闭它会把投递主线程的 tab 也关了）
    _tab_count_before = 0
    try:
        _tab_count_before = len(browser.tab_list())
    except Exception:
        pass

    tab = open_tab(browser, CHAT_URL)
    pace_sleep(3.0, 4.0)

    # 判断这个 tab 是不是我们新开的
    _is_new_tab = False
    try:
        _tab_count_after = len(browser.tab_list())
        _is_new_tab = (_tab_count_after > _tab_count_before)
    except Exception:
        pass

    try:
        for round_index in range(1, rounds + 1):
            # 2026-09-17 修复：用户按「停止」后立即收尾，不再继续扫下一轮。
            if _user_stop_requested(skill_dir):
                summary["stopped_by_user"] = True
                logger.info("检测到用户停止标记，聊天监听提前结束。")
                break
            # 修复：每轮重新读取打招呼白名单，新打招呼的公司下一轮就能被监听到
            if only_greeted:
                all_targets = load_greeted_targets(
                    skill_dir, include_preview=(mode == "rehearsal")
                )
                greeted_targets = [x for x in all_targets if x.get("company") not in baseline]
                greeted_companies = sorted({x.get("company") for x in greeted_targets if x.get("company")})
                logger.info("第 %s 轮白名单：%s", round_index, greeted_companies or "（本轮暂无新增）")
            # LLM 配额/余额耗尽：立即停止监听（LLM 已不可用，继续处理无意义且可能误操作）
            if llm_enabled and llm_quota_exhausted(skill_dir):
                summary["quota_exhausted"] = True
                logger.error("LLM 配额已耗尽，停止聊天监听。")
                summary["actions"].append(
                    {
                        "type": "llm_quota_exhausted",
                        "message": "LLM 配额/余额已用完，投递与监听已自动停止。",
                    }
                )
                break
            summary["rounds_scanned"] = round_index
            conversations = scan_conversations(tab)
            summary["conversations_seen"] = max(summary["conversations_seen"], len(conversations))
            logger.info("第 %s 轮：发现 %s 个会话（只处理前 15 个）。", round_index, len(conversations))

            # 只处理前 15 个会话（用户要求：全部监控太浪费时间）
            conversations = conversations[:15]

            for conv in conversations:
                # 2026-09-17 修复：逐个会话前检查停止标记，按停止后最多再跑完当前一个会话。
                if _user_stop_requested(skill_dir):
                    summary["stopped_by_user"] = True
                    logger.info("检测到用户停止标记，聊天监听提前结束。")
                    break
                conv_name = normalize_text(conv.get("name") or "")
                # 只处理本轮新增打招呼公司的会话（仅当启用了 only_greeted_hr）
                # 注意：only_greeted=True 时，白名单为空表示「本轮没有新增打招呼」，
                # 此时不应处理任何会话（避免误处理历史轮次的 HR）。
                if only_greeted:
                    if not greeted_companies:
                        summary["skipped"] += 1
                        continue
                    conv_text = normalize_text(f"{conv.get('name') or ''} {conv.get('company') or ''} {conv.get('raw') or ''}")
                    if not any(
                        target.get("company") in conv_text
                        and (not target.get("hr_name") or target.get("hr_name") == conv_name)
                        for target in greeted_targets
                    ):
                        summary["skipped"] += 1
                        continue

                key = _stable_conversation_key(conv)
                logger.info("[监听] 会话：%s | 公司：%s | 摘要：%s", key, conv.get("company",""), (conv.get("raw") or "")[:40])
                # 修复：不按最后一条消息去重，改成按"是否已发过简历"去重
                if key in state.get("resume_sent", []):
                    logger.info("[监听] 跳过（已发过简历）：%s", key)
                    continue
                # P1 修复：rehearsal 模式不持久化 processed，避免正式运行漏处理
                if mode == "apply":
                    state["processed"][key] = normalize_text(conv.get("raw") or "")[:80]
                if not open_conversation(tab, conv.get("element")):
                    state["processed"].pop(key, None)
                    save_chat_state(state, skill_dir)
                    continue
                pace_sleep(0.8, 1.5)
                # 修复：点击会话后多等一会，确保右边聊天面板加载完
                pace_sleep(2.0, 3.0)

                friend_entries = read_friend_messages_classified(tab, limit=15)
                if not friend_entries:
                    # 首读为空（消息懒加载/页面未切换完成）：重读一次再放弃
                    pace_sleep(2.0, 3.0)
                    friend_entries = read_friend_messages_classified(tab, limit=15)
                if not friend_entries:
                    # BUG 修复：读取失败时回滚 processed 标记，避免永久跳过该会话的后续新消息
                    state["processed"].pop(key, None)
                    save_chat_state(state, skill_dir)
                    continue

                latest_entry = friend_entries[-1]
                latest = latest_entry["text"]
                is_template_msg = latest_entry["is_system_template"]
                verdict = classify_message(latest)

                # 修复 bug：不只看最后一条消息，遍历所有消息（含系统卡片），只要有一条是要简历的就触发
                # （场景：HR 先发系统卡片要简历，然后又发了介绍业务的话术，最后一条不是要简历）
                _has_resume_request_in_history = False
                _resume_request_text = ""
                # 先遍历 HR 发的消息
                for entry in friend_entries:
                    v = classify_message(entry["text"])
                    if v["resume_request"]:
                        _has_resume_request_in_history = True
                        _resume_request_text = entry["text"]
                        break  # 找到第一条要简历的就够了
                # 再遍历系统消息（系统卡片要简历是 item-system）
                if not _has_resume_request_in_history:
                    all_texts = _read_all_message_texts(tab, limit=20)
                    for text in all_texts:
                        v = classify_message(text)
                        if v["resume_request"]:
                            _has_resume_request_in_history = True
                            _resume_request_text = text
                            break

                # 如果历史消息里有要简历，但最后一条不是，也要处理
                if _has_resume_request_in_history and not verdict["resume_request"]:
                    logger.info("[要简历·历史消息] %s | 最后一条不是要简历，但历史消息里有：%s", key, _resume_request_text[:60])
                    # 把 verdict 改成要简历，走下面的发简历逻辑
                    # 2026-09-17 裁决（显式化，不改行为）：此处**有意不清除**
                    # verdict["rejection"]。下方三个分支的判定顺序为
                    # 「面试邀请 → 拒绝 → 要简历」，因此「历史里要过简历 +
                    # 最后一条判为拒绝」会先命中拒绝分支并 continue，简历不发。
                    # 这是期望行为：主流路径是「先发简历、后被拒绝」，此时回致谢正确；
                    # 仅「HR 误点要简历、紧接着一句拒绝」属小概率，不回/忽略亦可接受。
                    # 故保留「拒绝优先于要简历」，不做清除。
                    verdict["resume_request"] = True
                    latest = _resume_request_text  # 用历史消息的内容做日志

                # 面试邀请：不做任何自动回复，仅记录提醒用户接管
                if verdict["interview_invite"]:
                    summary["interview_invites_detected"] += 1
                    summary["actions"].append(
                        {
                            "conversation": key,
                            "type": "interview_invite",
                            "message": latest,
                            "hint": "对方约面试：请用户接管，未自动回复。",
                        }
                    )
                    logger.info("[面试邀请] %s | %s", key, latest)
                    continue

                # 拒绝：发礼貌致谢（防重复：会话内已发过致谢则跳过）
                if verdict["rejection"]:
                    summary["rejections_detected"] += 1
                    reply = cfg.get("reject_reply", "")
                    already_thanked = chat_has_replied_thanks(tab, [reply]) or key in state["reject_replied"]
                    should_send = (
                        mode == "apply" and reply and not already_thanked
                    )
                    if should_send:
                        if send_reject_reply(tab, reply):
                            state["reject_replied"].append(key)
                            summary["reject_replies_sent"] += 1
                            summary["actions"].append(
                                # 2026-09-19 N：带上触发原话，供日志排查
                                # （曾经因为只记 reply 不记 message，
                                #   误发致谢时完全无法定位是哪句话命中）
                                {"conversation": key, "type": "reject_reply",
                                 "reply": reply, "message": latest}
                            )
                            logger.info("[拒绝话术] 已发送给 %s", key)
                        else:
                            summary["skipped"] += 1
                            # P1 修复：致谢发送失败回滚 processed
                            state["processed"].pop(key, None)
                            save_chat_state(state, skill_dir)
                    else:
                        summary["actions"].append(
                            {
                                "conversation": key,
                                "type": "reject_detected",
                                "will_reply": reply if mode == "apply" else "(rehearsal 不发送)",
                            }
                        )
                        logger.info("[拒绝] %s | %s", key, latest)
                    continue

                # 要简历：自动发附件简历
                if verdict["resume_request"]:
                    summary["resume_requests_detected"] += 1
                    already_sent = chat_has_resume_sent(tab) or key in state["resume_sent"]
                    if already_sent:
                        # 会话内已有发送确认（含用户手动发送产生的系统确认）：同步状态防重复
                        if key not in state["resume_sent"]:
                            state["resume_sent"].append(key)
                            save_chat_state(state, skill_dir)
                        summary["skipped"] += 1
                        logger.info("[要简历] %s 已发送过简历（含手动/系统确认），跳过。", key)
                        continue
                    # 修复：删掉"检查本地简历文件是否存在"的判断，直接走选择在线附件简历的流程
                    # （用户要求：只发一开始选好的在线附件简历，不要兜底上传本地 PDF）

                    if mode != "apply":
                        summary["actions"].append(
                            {
                                "conversation": key,
                                "type": "resume_request",
                                "message": latest,
                                "would_send": "rehearsal 模式，未真实发送",
                            }
                        )
                        logger.info("[要简历·演练] %s | %s", key, latest)
                        continue

                    # 真实发送流程
                    sent_ok = False
                    try:
                        # 优先：请求简历卡片上的「同意」按钮（HR 通过系统卡片请求）
                        # 点「同意」后 BOSS 会弹出选简历弹窗；若卡片不存在则回退到工具栏「发简历」
                        # 2026-09-21 CARD3：分步诊断日志 —— 原链路一行日志都没有，
                        # "没发出去"时完全无法定位卡在哪一步。
                        _card_ok = click_resume_card_agree(tab)
                        logger.info("[要简历·步骤1] %s 点卡片「同意」→ %s", key,
                                    "成功" if _card_ok else "未找到卡片或按钮")
                        send_triggered = _card_ok
                        if not send_triggered:
                            send_triggered = click_send_resume_button(tab)
                            logger.info("[要简历·步骤2] %s 回退工具栏「发简历」→ %s", key,
                                        "成功" if send_triggered else "失败")
                        if send_triggered:
                            # 首选：选择已上传的附件简历（无需重新上传本地文件）
                            # 附件名优先用 config.resume_send_name（demo 附件简历选择写入），无则按弹窗第一份兜底
                            _rname = str(cfg.get("resume_send_name") or "")
                            _sel = select_existing_resume(tab, resume_name=_rname)
                            logger.info("[要简历·步骤3] %s 选附件简历「%s」→ %s", key,
                                        _rname or "(第一份)", "成功" if _sel else "失败")
                            if _sel:
                                sent_ok = confirm_and_send(tab)
                                logger.info("[要简历·步骤4] %s 确认发送 → %s", key,
                                            "成功" if sent_ok else "失败")
                            else:
                                logger.warning("[要简历] %s 弹窗中没有找到在线附件简历", key)
                        else:
                            logger.warning("[要简历] %s 卡片和工具栏都没点动，未能发送", key)
                        if sent_ok:
                            state["resume_sent"].append(key)
                            summary["resume_sent"] += 1
                            try:
                                from agent.ledger import record_action
                                record_action("resume_send", "sent", {"conversation": str(key)[:40]},
                                              skill_dir=skill_dir)
                            except Exception:
                                pass
                            summary["actions"].append(
                                {
                                    "conversation": key,
                                    "type": "resume_sent",
                                    "resume": str(resume_path),
                                }
                            )
                            logger.info("[已发送简历] %s | %s", key, resume_path)
                        else:
                            summary["skipped"] += 1
                            summary["actions"].append(
                                {
                                    "conversation": key,
                                    "type": "resume_send_failed",
                                    "message": latest,
                                }
                            )
                            logger.warning("[发送失败] %s | %s", key, latest)
                            # P1 修复：失败回滚 processed
                            state["processed"].pop(key, None)
                            save_chat_state(state, skill_dir)
                    except Exception as exc:
                        summary["skipped"] += 1
                        summary["actions"].append(
                            {"conversation": key, "type": "resume_send_error", "error": str(exc)}
                        )
                        logger.exception("[发送异常] %s", key)
                        # P1 修复：异常回滚 processed
                        state["processed"].pop(key, None)
                        save_chat_state(state, skill_dir)
                    continue

                # 对方没真正回复（仅系统模板自动回复）：不回复
                # 规则：对方只是发来平台自动回复模板（如「您好，可以聊聊吗？您这个职位我很有兴趣」），
                # 说明对方没有真正说话，此时不回复，避免对模板话术做无意义的自动回复。
                if is_template_msg:
                    summary["skipped"] += 1
                    summary["actions"].append(
                        {
                            "conversation": key,
                            "type": "system_template_skip",
                            "message": latest,
                            "note": "对方仅系统模板自动回复（未真正说话），不回复。",
                        }
                    )
                    logger.info("[系统模板·不回复] %s | %s", key, latest)
                    continue

                # 其他普通消息：不自动回复，只记录提醒用户（用户要求：普通对话只提醒不回复）
                summary["chat_new_alert"] = summary.get("chat_new_alert", 0) + 1
                summary["actions"].append(
                    {
                        "conversation": key,
                        "type": "chat_alert",
                        "hr_name": conv_name,
                        "company": normalize_text(conv.get("company") or ""),
                        "message": latest,
                        "time": time.strftime("%H:%M", time.localtime()),
                        "hint": "HR 发来新消息（普通对话），未自动回复，请用户查看。",
                    }
                )
                logger.info("[HR新消息·未回复] %s | %s", key, latest)
                continue

            save_chat_state(state, skill_dir)
            if round_index < rounds:
                time.sleep(interval)
    finally:
        save_chat_state(state, skill_dir)
        # 监听结束后，只关自己新开的 tab（open_tab 退回主 tab 时不关，避免把投递搜索页关了）
        try:
            if tab and _is_new_tab:
                tab.close()
                logger.info("监听 tab 已关闭。")
            else:
                logger.info("监听 tab 非新开，跳过关闭（保留投递主线程页面）。")
        except Exception as e:
            logger.warning("关闭监听 tab 失败：%s", e)

    summary["message"] = (
        f"聊天监听完成：扫描 {summary['rounds_scanned']} 轮，共 {summary['conversations_seen']} 个会话，"
        f"检测到要简历 {summary['resume_requests_detected']} 次"
        f"（发送 {summary['resume_sent']} 份），"
        f"拒绝 {summary['rejections_detected']} 次（回谢 {summary['reject_replies_sent']} 条），"
        f"面试邀请 {summary['interview_invites_detected']} 次，"
        f"自动回复 {summary['chat_replies_sent']} 条，"
        f"需用户接管 {summary['chat_escalated_to_user']} 次。"
    )
    logger.info("%s", summary["message"])
    # 2026-09-22 CONV1：把「会话 → 公司名」回填进 actions。
    # 结果统计按公司名做键（outcomes.json / job_memory / 复盘报告三方 join），
    # 而会话 key 是 HR 姓名，两者对不上 → HR 回复被判成
    # 「不是我们方案打的招呼」，只进 hr_inbound，进不了结果统计。
    # 这里拿已打招呼的公司名去会话 raw 里做最长匹配，认出公司名。
    try:
        _known = sorted({str(t.get("company") or "").strip()
                         for t in load_greeted_targets(skill_dir,
                                                       include_preview=False)}
                        - {""})
        if _known:
            _proc = load_chat_state(skill_dir).get("processed") or {}
            for _act in summary.get("actions") or []:
                if not isinstance(_act, dict) or _act.get("company"):
                    continue
                _key = str(_act.get("conversation") or "").strip()
                if not _key:
                    continue
                _co = resolve_company_from_text(_proc.get(_key) or "", _known)
                if _co:
                    _act["company"] = _co
                    logger.info("[会话→公司] %s → %s", _key, _co)
                else:
                    logger.info("[会话→公司] %s → 未认出公司（仍按 HR 姓名入账）", _key)
    except Exception as _exc:
        logger.debug("会话→公司回填失败（已忽略）：%s", _exc)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{PLATFORM_NAME} 聊天监听 + 自动发简历")
    parser.add_argument("--mode", choices=("rehearsal", "apply"), default="rehearsal", help="运行模式")
    parser.add_argument("--port", type=int, default=9222, help="浏览器调试端口")
    parser.add_argument("--rounds", type=int, default=5, help="轮询轮数")
    parser.add_argument("--interval", type=float, default=30.0, help="每轮间隔秒数")
    parser.add_argument("--resume-pdf", default="", help="要发送的简历 PDF 路径（默认用 config 配置）")
    parser.add_argument("--skill-dir", default=str(resolve_skill_dir()), help="运行目录")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill_dir = resolve_skill_dir(args.skill_dir)
    config = load_config(skill_dir)
    result = run_chat_monitor(
        config=config,
        skill_dir=skill_dir,
        debug_port=args.port,
        mode=args.mode,
        rounds=args.rounds,
        interval=args.interval,
        resume_pdf=args.resume_pdf or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
