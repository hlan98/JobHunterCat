from __future__ import annotations

import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

from agent.skill_entry import prompt_review_skills
from boss.boss_apply import salary_policy_reason
from agent.shared import (
    JobTask,
    append_log,
    initialize_config_from_resume,
    heuristic_extract_skills,
    keyword_in_text,
    load_log,
    log_bucket_items,
    merge_config,
    normalize_platforms,
    normalize_run_mode,
    platform_user_data_dir,
    resolve_skill_dir,
    save_log,
    sanitize_json_text,
    score_jd,
    cleanup_tabs,
    check_boss_login,
    split_keywords,
    start_log_run,
    finish_log_run,
)


class PolicyGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # 2026-09-17 修复：项目目录曾由 job-pet-demo 更名为 v8-core，
        # 原硬编码路径失效导致 PolicyGuardTests 整体 ERROR。改为顺序探测。
        # 2026-09-24：改成**按层级探测、两种布局通用**，不要再写死 parents[N]。
        #   开源副本：tests/ 在仓库根，main.py 在 agent/   → _base.parent / "agent" / "main.py"
        #   工作副本：tests/ 在 v8-core/job-hunter-skill/  → _base.parents[1] / "main.py"
        # 为什么这么做：迁移脚本是**全量复制**，写死层级的版本一旦被复制过去就会
        # 在另一份布局里失效（09-24 那次同步就把这里打回了 parents[2]，PolicyGuardTests 整组 ERROR）。
        # 两种布局都认，迁移就可以安全覆盖，不会再复发。
        _base = Path(__file__).resolve().parent
        _candidates = [
            _base.parent / "agent" / "main.py",      # 开源副本
            _base.parents[1] / "main.py",            # 工作副本（v8-core/main.py）
            _base.parent / "main.py",                # 平铺结构
            _base.parent / "v8-core" / "main.py",    # 旧结构
            _base.parent / "job-pet-demo" / "main.py",
        ]
        demo_path = next((p for p in _candidates if p.exists()), None)
        if demo_path is None:
            raise RuntimeError(
                "找不到 main.py，已尝试：" + ", ".join(str(p) for p in _candidates)
            )
        spec = importlib.util.spec_from_file_location("job_pet_demo_main", demo_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load %s" % demo_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.looks_like_plan_change = staticmethod(module.looks_like_plan_change)

    def test_runtime_plan_change_detection_covers_all_plan_fields(self) -> None:
        for text in (
            "把薪资改成20-30K", "匹配分调到70", "增加海外社媒关键词",
            "城市换成上海", "排除词加上兼职", "改成正式投递模式",
            "薪资15-25K", "匹配分70", "不投兼职",
        ):
            self.assertTrue(self.looks_like_plan_change(text), text)
        self.assertFalse(self.looks_like_plan_change("现在投得怎么样"))
        self.assertFalse(self.looks_like_plan_change("岗位有哪些"))

    def test_salary_policy_rejects_range_below_both_thresholds(self) -> None:
        reason = salary_policy_reason("12-20K", {
            "min_salary_low_k": 15,
            "min_salary_high_k": 25,
        })
        self.assertIn("下限", reason)
        self.assertIn("上限", reason)

    def test_salary_policy_rejects_unparseable_salary_when_configured(self) -> None:
        self.assertEqual(
            salary_policy_reason("薪资面议", {
                "min_salary_low_k": 15,
                "min_salary_high_k": 25,
            }),
            "薪资无法解析",
        )

    def test_salary_policy_rejects_daily_salary(self) -> None:
        self.assertEqual(
            salary_policy_reason("300元/天", {"min_salary_low_k": 15}),
            "按天/日结薪资格式",
        )

    def test_exclude_keyword_scans_jd_before_llm(self) -> None:
        class ExplodingClient:
            def is_configured(self):
                raise AssertionError("excluded jobs must not touch LLM")

        result = score_jd(
            "海外运营", "公司包吃住，可带行李", {
                "target_roles": ["海外运营"], "skills": ["运营"], "min_score": 0,
            }, llm_client=ExplodingClient(), use_llm=True,
        )
        self.assertEqual(result.decision, "skip")
        self.assertIn(result.exclude_hit, {"包吃住", "可带行李"})
        self.assertEqual(result.llm_score, 0)

    def test_merge_config_keeps_default_exclusions_and_adds_custom(self) -> None:
        cfg = merge_config({"exclude_keywords": ["用户自定义词"]})
        self.assertIn("包吃住", cfg["exclude_keywords"])
        self.assertIn("兼职", cfg["exclude_keywords"])
        self.assertIn("用户自定义词", cfg["exclude_keywords"])


class SharedTests(unittest.TestCase):
    def test_security_check_query_does_not_mark_logged_in_page_blocked(self) -> None:
        class Tab:
            url = "https://www.zhipin.com/web/geek/jobs?_security_check=1_123"
            html = "消息 简历 退出登录 岗位列表"
        class Browser:
            latest_tab = Tab()
        with patch("agent.shared.time.sleep"):
            self.assertEqual(check_boss_login(Browser()), "ok")

    def test_score_jd_without_llm_does_not_call_client(self) -> None:
        class ExplodingClient:
            def is_configured(self):
                raise AssertionError("LLM client must not be touched")
        result = score_jd("海外运营", "负责海外社媒运营", {
            "target_roles": ["运营"], "skills": ["社媒"], "min_score": 0,
        }, llm_client=ExplodingClient(), use_llm=False)
        self.assertEqual(result.llm_score, 0)

    def test_cleanup_tabs_keeps_chat_query_url(self) -> None:
        class Tab:
            def __init__(self, tab_id, url):
                self.tab_id, self.url, self.title, self.closed = tab_id, url, "", False
            def close(self):
                self.closed = True
        class Browser:
            def __init__(self):
                self.tabs = [Tab("chat", "https://www.zhipin.com/web/geek/chat?uid=1"),
                             Tab("jobs", "https://www.zhipin.com/web/geek/jobs?query=x")]
            def get_tabs(self):
                return [t for t in self.tabs if not t.closed]
        browser = Browser()
        self.assertEqual(cleanup_tabs(browser, keep_urls=["https://www.zhipin.com/web/geek/chat"]), 0)
        self.assertFalse(browser.tabs[0].closed)
    def test_resolve_skill_dir_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(resolve_skill_dir(tmpdir), Path(tmpdir).resolve())

    def test_split_keywords(self) -> None:
        self.assertEqual(
            split_keywords("Java开发实习生, AI产品实习生，Java开发实习生"),
            ["Java开发实习生", "AI产品实习生"],
        )

    def test_keyword_match_tolerates_spacing(self) -> None:
        self.assertTrue(keyword_in_text("Java开发实习生", "Java 开发实习生"))
        self.assertTrue(keyword_in_text("Spring Boot", "SpringBoot 项目经验"))

    def test_normalize_platforms(self) -> None:
        # 2026-09-18：实习僧（sxs）已随「删死代码」移除，只剩 Boss。
        self.assertEqual(normalize_platforms("Boss"), ["boss"])
        self.assertEqual(normalize_platforms("boss直聘"), ["boss"])
        # 已移除的平台应当明确报错，而不是静默接受
        with self.assertRaises(ValueError):
            normalize_platforms("实习僧")

    def test_normalize_run_mode(self) -> None:
        self.assertEqual(normalize_run_mode("安全演练"), "rehearsal")
        self.assertEqual(normalize_run_mode("apply"), "apply")

    def test_platform_user_data_dir_resolves_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = platform_user_data_dir(
                "boss",
                {"user_data_dirs": {"boss": ".job_hunter/browser/boss"}},
                skill_dir=tmpdir,
            )
            self.assertTrue(path.startswith(str(Path(tmpdir).resolve())))

    def test_log_round_trip_with_runs_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "boss-北京-log.json"
            task = JobTask(
                job_name="Java开发实习生",
                city="北京",
                count=1,
                platforms=["boss"],
                mode="rehearsal",
                debug_port=9222,
            )

            log_data = load_log(log_path)
            run_id = start_log_run(log_data, platform="boss", task=task, min_score=80)
            append_log(
                log_data,
                "skipped",
                {
                    "run_id": run_id,
                    "job_key": "boss|java开发实习生|测试公司",
                    "job": "Java开发实习生",
                    "company": "测试公司",
                    "score": 72,
                },
            )
            finish_log_run(
                log_data,
                run_id,
                {
                    "mode": "rehearsal",
                    "applied": 0,
                    "reviewed": 1,
                    "skipped": 1,
                    "failed": 0,
                    "count": 1,
                    "min_score": 80,
                    "message": "done",
                },
            )
            save_log(log_data, log_path)

            reloaded = load_log(log_path)
            self.assertEqual(reloaded["schema_version"], 2)
            self.assertEqual(reloaded["meta"]["platform"], "boss")
            self.assertEqual(len(reloaded["runs"]), 1)
            self.assertEqual(len(log_bucket_items(reloaded, "skipped")), 1)
            self.assertEqual(reloaded["analytics"]["counts"]["skipped"], 1)

    def test_score_jd_matches_target_role_with_spacing_difference(self) -> None:
        result = score_jd(
            "Java 开发实习生",
            "岗位要求：熟悉 Java、MySQL、SQL。",
            {
                "target_roles": ["Java开发实习生"],
                "skills": ["Java", "MySQL", "SQL"],
                "min_score": 80,
            },
            resume_text="",
        )

        self.assertEqual(result.role_hit, "Java开发实习生")
        # 2026-09-19 A2：默认权重重构后 职位名 30→20，
        # 20 + 3 个技能 × 5 = 35（原为 30 + 15 = 45）
        self.assertEqual(result.rule_score, 35)

    def test_score_jd_uses_configurable_scoring(self) -> None:
        result = score_jd(
            "Java 开发实习生",
            "岗位要求：熟悉 Java、MySQL、SQL。",
            {
                "target_roles": ["Java开发实习生"],
                "skills": ["Java", "MySQL", "SQL"],
                "min_score": 80,
                "scoring": {
                    "role_title_score": 40,
                    "skill_score_each": 6,
                    "skill_score_cap": 12,
                    "heuristic_base_score": 0,
                    "heuristic_skill_score_each": 0,
                    "heuristic_skill_score_cap": 0,
                    "heuristic_role_score": 0,
                    "heuristic_bonus_keywords": [],
                    "heuristic_bonus_score": 0,
                },
            },
            resume_text="",
        )

        self.assertEqual(result.rule_score, 52)
        self.assertIn("岗位加分: Java开发实习生(+40)", result.reason)
        self.assertIn("技能命中: Java/MySQL/SQL(+12)", result.reason)

    def test_merge_config_keeps_default_scoring_keys(self) -> None:
        cfg = merge_config({"scoring": {"role_title_score": 42}})

        self.assertEqual(cfg["scoring"]["role_title_score"], 42)
        self.assertIn("skill_score_each", cfg["scoring"])

    def test_sanitize_json_text_removes_surrogates(self) -> None:
        cleaned = sanitize_json_text({"skills": ["Java\udc80"]})

        self.assertEqual(cleaned, {"skills": ["Java "]})

    def test_initialize_config_keeps_user_greeting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            resume = Path(tmpdir) / "resume.md"
            resume.write_text("Java MySQL Redis Spring Boot Git Linux Docker SQL", encoding="utf-8")

            config, _profile = initialize_config_from_resume(
                resume,
                target_roles=["Java开发实习生"],
                exclude_keywords=["销售"],
                base_config={"greeting": "用户自己填写的话术"},
                skill_dir=tmpdir,
            )

            self.assertEqual(config["greeting"], "用户自己填写的话术")

    def test_prompt_review_skills_requires_user_confirmation(self) -> None:
        inputs = iter(
            [
                "编辑",
                "Java,Spring Boot,MySQL,Redis,Git,Linux,Docker,SQL",
                "接受",
            ]
        )

        with patch("builtins.input", lambda _prompt: next(inputs)), patch(
            "agent.skill_entry.print_line",
            lambda _message="": None,
        ):
            skills = prompt_review_skills(["Java", "MySQL"])

        self.assertEqual(
            skills,
            ["Java", "Spring Boot", "MySQL", "Redis", "Git", "Linux", "Docker", "SQL"],
        )

    def test_heuristic_extract_skills_filters_contact_noise(self) -> None:
        skills = heuristic_extract_skills(
            "邮箱 candidate123@example.com mailto:test https://github.com/example-user "
            "熟悉 Java Spring Boot MySQL Redis Git Docker SQL。"
        )

        lowered = {item.lower() for item in skills}
        self.assertIn("java", lowered)
        self.assertIn("mysql", lowered)
        self.assertNotIn("candidate123", lowered)
        self.assertNotIn("example.com", lowered)
        self.assertNotIn("mailto", lowered)
        self.assertNotIn("https", lowered)


if __name__ == "__main__":
    unittest.main()
