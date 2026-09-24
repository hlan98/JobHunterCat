from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from boss.boss_chat import (
    classify_message,
    detect_interview_invite,
    detect_rejection_text,
    detect_resume_request_text,
    detect_resume_sent_confirmation,
    load_greeted_companies,
    click_send_resume_button,
)
from unittest.mock import patch


class BossChatDetectTests(unittest.TestCase):
    """聊天监听模块：要简历检测（两种形态）/ 拒绝 / 已发送 / 面试邀请。"""

    # ---------- 形态②：普通对话问简历（文本意图） ----------
    def test_text_request_common(self) -> None:
        self.assertTrue(detect_resume_request_text("方便发一份简历过来吗？")[0])

    def test_text_request_direct(self) -> None:
        self.assertTrue(detect_resume_request_text("可以把简历发我一份吗")[0])

    def test_text_request_short(self) -> None:
        self.assertTrue(detect_resume_request_text("发份简历看看")[0])

    def test_text_request_with_resume_word(self) -> None:
        self.assertTrue(detect_resume_request_text("能发一份你的简历吗")[0])

    def test_text_request_english(self) -> None:
        self.assertTrue(detect_resume_request_text("Could you send your resume?")[0])

    def test_text_request_share(self) -> None:
        self.assertTrue(detect_resume_request_text("Please share your resume")[0])

    # ---------- 形态①：系统请求简历 ----------
    def test_system_request(self) -> None:
        self.assertTrue(detect_resume_request_text("对方请求你发送简历")[0])

    def test_system_request_variant(self) -> None:
        self.assertTrue(detect_resume_request_text("想要一份你的简历")[0])

    # ---------- 不应触发 ----------
    def test_not_request_viewing(self) -> None:
        self.assertFalse(detect_resume_request_text("我看一下你的简历")[0])

    def test_not_request_no_verb(self) -> None:
        self.assertFalse(detect_resume_request_text("你好，看到你的简历了")[0])

    def test_not_request_unrelated(self) -> None:
        self.assertFalse(detect_resume_request_text("请问你什么时候方便面试")[0])

    def test_empty_text(self) -> None:
        self.assertFalse(detect_resume_request_text("")[0])

    # ---------- 拒绝检测 ----------
    def test_rejection(self) -> None:
        self.assertTrue(detect_rejection_text("不好意思，不太合适哦"))

    def test_rejection_thanks(self) -> None:
        self.assertTrue(detect_rejection_text("感谢您的关注，很遗憾不能与您共事。"))

    def test_rejection_not_hit(self) -> None:
        self.assertFalse(detect_rejection_text("您好，想进一步了解您的经验"))

    # ---------- 已发送确认 ----------
    def test_resume_sent_confirm(self) -> None:
        self.assertTrue(detect_resume_sent_confirmation("您的附件简历 我的简历 已发送给Boss点击查看附件"))

    def test_resume_sent_agree(self) -> None:
        self.assertTrue(detect_resume_sent_confirmation("对方已同意，您的附件简历已发送给对方"))

    def test_resume_sent_not_hit(self) -> None:
        self.assertFalse(detect_resume_sent_confirmation("您好，可以聊聊吗"))

    # ---------- 面试邀请 ----------
    def test_interview_invite(self) -> None:
        self.assertTrue(detect_interview_invite("请问这周五方便来面试吗"))

    def test_interview_invite_arrange(self) -> None:
        self.assertTrue(detect_interview_invite("我帮您安排面试时间"))

    # ---------- 综合分类 ----------
    def test_classify_resume_request(self) -> None:
        verdict = classify_message("方便发一份简历给我吗")
        self.assertTrue(verdict["resume_request"])
        self.assertFalse(verdict["rejection"])

    def test_classify_rejection(self) -> None:
        verdict = classify_message("很抱歉，暂时不考虑")
        self.assertTrue(verdict["rejection"])
        self.assertFalse(verdict["resume_request"])

    def test_classify_interview(self) -> None:
        verdict = classify_message("约个时间面试沟通一下")
        self.assertTrue(verdict["interview_invite"])

    def test_classify_plain(self) -> None:
        verdict = classify_message("您好，可以聊聊吗")
        self.assertFalse(verdict["resume_request"])
        self.assertFalse(verdict["rejection"])
        self.assertFalse(verdict["interview_invite"])

    def test_preview_records_are_opt_in_for_greeted_companies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "boss-2026-log.json").write_text(json.dumps({
                "records": {
                    "applied": [{"company": "真实公司"}],
                    "preview": [{"company": "演练公司"}],
                }
            }, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_greeted_companies(root), ["真实公司"])
            self.assertEqual(load_greeted_companies(root, include_preview=True), ["演练公司", "真实公司"])

    def test_resume_button_reads_aria_label(self) -> None:
        class Element:
            def __init__(self):
                self.clicked = False
            def attr(self, name):
                return {"aria-label": "发简历（双击回复）", "class": "toolbar-btn"}.get(name, "")
            def click(self, **kwargs):
                self.clicked = True
        class Tab:
            def __init__(self):
                self.element = Element()
            def ele(self, locator, timeout=0.6):
                return self.element if locator == "css:[d-c='62009']" else None
        tab = Tab()
        with patch("boss.boss_chat.pace_sleep"):
            self.assertTrue(click_send_resume_button(tab))
        self.assertTrue(tab.element.clicked)


if __name__ == "__main__":
    unittest.main()
