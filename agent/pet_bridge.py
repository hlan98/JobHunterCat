# -*- coding: utf-8 -*-
"""找工作喵 · 无头桥接层（给 Electron 壳用）

设计目标：
- 完全复用 main.py 的 PetApp 业务逻辑（零改动投递主流程）；
- 用 FakeWidget 吞掉所有 Tk 界面依赖，不弹窗、不显示；
- 把 UI 出口（气泡/状态/日志/选项面板）转成 NDJSON 行写到 stdout；
- 从 stdin 逐行读 JSON 命令，注入用户文本/触发功能/回传选项。

通信（每消息一行 JSON，UTF-8）：
  Python -> 壳:
    {"type":"ready"}
    {"type":"bubble","text":"..."}
    {"type":"log","text":"..."}
    {"type":"state","state":"闲置","act":"sit"}
    {"type":"panel","kind":"resume_choice","items":[{name,desc}]}
    {"type":"panel","kind":"action","title":"...","options":[{"label","index"}]}
    {"type":"error","text":"..."}
  壳 -> Python:
    {"cmd":"user_text","text":"..."}
    {"cmd":"start"} | {"cmd":"pause"} | {"cmd":"resume"} | {"cmd":"stop"}
    {"cmd":"resume_file","path":"..."}
    {"cmd":"choice","index":1}            # 回传当前等待的面板选择
    {"cmd":"call","action":"report|config|llm_settings|browser|stop_status|resume"}
"""
import sys
import os
import json
import queue
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# 2026-09-18 第 44 轮修复：
# ① RUN_DIR 在本文件里此前只有使用、从未定义 →
#    read_recent(..., skill_dir=RUN_DIR) 抛 NameError，被下面的
#    except Exception: pass 吞掉 → 看板统计恒为 0、sessions 恒为 []。
# ② `import job_hunter_skill` 必须落到工作副本内的那一份（与 main.py 同一份），
#    否则会解析到沙箱里残留的旧副本。故把 SKILL_DIR 插到 sys.path 最前。
SKILL_DIR = Path(os.environ.get(
    # 2026-09-24 OSROOTFIX：开源副本的「包目录」就是仓库根（HERE 的上一层）
    "JOB_HUNTER_PACKAGE_DIR", str(HERE.parent))).expanduser().resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))
RUN_DIR = Path(os.environ.get(
    "JOB_HUNTER_HOME", str(SKILL_DIR / "run"))).expanduser().resolve()
# 2026-09-18 第 44 轮修复：
# ① RUN_DIR 在本文件里此前只有使用、从未定义 →
#    read_recent(..., skill_dir=RUN_DIR) 抛 NameError，被下面的
#    except Exception: pass 吞掉 → 看板统计恒为 0、sessions 恒为 []。
# ② `import job_hunter_skill` 必须落到工作副本内的那一份（与 main.py 同一份），
#    否则会解析到沙箱里残留的旧副本。故把 SKILL_DIR 插到 sys.path 最前。
SKILL_DIR = Path(os.environ.get(
    # 2026-09-24 OSROOTFIX：开源副本的「包目录」就是仓库根（HERE 的上一层）
    "JOB_HUNTER_PACKAGE_DIR", str(HERE.parent))).expanduser().resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))
RUN_DIR = Path(os.environ.get(
    "JOB_HUNTER_HOME", str(SKILL_DIR / "run"))).expanduser().resolve()

import tkinter as tk  # noqa: E402  仅用于类型/占位，不创建可见窗口

# ---------------------------------------------------------------------------
# Fake UI：吞掉所有 Tk 控件调用，避免线程安全与真实窗口
# ---------------------------------------------------------------------------
class _FakeWidget:
    """万能假控件：任何方法调用/属性访问都安全 no-op。"""
    def __init__(self, *a, **k):
        self._buf = ""
        # 部分业务代码会读这些属性
        self.text = ""

    # entry 行为
    def get(self):
        return self._buf

    def delete(self, a, b=None):
        self._buf = ""

    def insert(self, a, text=""):
        self._buf = (self._buf or "") + str(text)

    # Text 控件行为
    def see(self, *a):
        pass

    # 通用 no-op
    def configure(self, *a, **k):
        pass

    config = configure
    def pack(self, *a, **k):
        pass
    def grid(self, *a, **k):
        pass
    def place(self, *a, **k):
        pass
    def destroy(self):
        pass
    def bind(self, *a, **k):
        pass
    def unbind(self, *a, **k):
        pass
    def winfo(self, *a, **k):
        return 0
    def tk_popup(self, *a, **k):
        pass
    def __getattr__(self, name):
        # 任何其它属性 -> 一个 no-op 可调用（也当普通空对象用）
        if name.startswith("_"):
            raise AttributeError(name)
        def _noop(*a, **k):
            return None
        return _noop


class FakeRoot:
    """假 Tk root：after() 进队列由 pump 线程执行；其它调用 no-op。"""
    def __init__(self):
        self._q = queue.Queue()
        self._screen_w = 1920
        self._screen_h = 1080

    def after(self, ms, func=None, *args):
        if func is None:
            return
        def _run():
            try:
                func(*args)
            except Exception:
                sys.stderr.write("[after-error]\n" + traceback.format_exc() + "\n")
                sys.stderr.flush()
        delay = max(0, (ms or 0) / 1000.0)
        if delay <= 0:
            self._q.put(_run)
        else:
            threading.Timer(delay, lambda: self._q.put(_run)).start()

    def pump_loop(self):
        while True:
            fn = self._q.get()
            try:
                fn()
            except Exception:
                sys.stderr.write("[pump-error]\n" + traceback.format_exc() + "\n")
                sys.stderr.flush()

    # 其余 root 调用 no-op
    def overrideredirect(self, *a):
        pass
    def attributes(self, *a, **k):
        pass
    def geometry(self, *a):
        pass
    def resizable(self, *a):
        pass
    def withdraw(self):
        pass
    def protocol(self, *a):
        pass
    def destroy(self):
        pass
    def mainloop(self):
        # 无头不进入 Tk mainloop
        pass
    def winfo_screenwidth(self):
        return self._screen_w
    def winfo_screenheight(self):
        return self._screen_h
    def update(self):
        pass
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        def _noop(*a, **k):
            return None
        return _noop


# ---------------------------------------------------------------------------
# 事件出口
# ---------------------------------------------------------------------------
_sink_lock = threading.Lock()
_pending_panel = {"kind": None, "callback": None, "items": []}


def emit(obj):
    """向 stdout 写一行 JSON（线程安全）。"""
    line = json.dumps(obj, ensure_ascii=False)
    with _sink_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# HeadlessPet
# ---------------------------------------------------------------------------
def _build_headless():
    import main as m
    from PIL import Image

    class HeadlessPet(m.PetApp):
        def __init__(self):
            root = FakeRoot()
            self._fake_root = root
            # 不创建真实 Tk：直接调用父类 __init__（它内部 _build_ui 已被我们覆盖为 no-op）
            super().__init__(root)
            # 启动 UI pump 线程
            threading.Thread(target=root.pump_loop, daemon=True).start()

        # --- 覆盖 UI 构建，避免真实 Tk 控件 ---
        def _fonts(self):
            pass

        def _load_cat(self, path, size=104):
            return None  # 无头不需要真图

        def _build_ui(self):
            # 给业务会访问的 UI 属性塞假控件
            self.outer = _FakeWidget()
            self.head = _FakeWidget()
            self.avatar_lbl = _FakeWidget()
            self.bubble_lbl = _FakeWidget()
            self.state_dot = _FakeWidget()
            self.state_lbl = _FakeWidget()
            self._offline_label = _FakeWidget()
            self.chip_row = _FakeWidget()
            self.entry = _FakeWidget()
            self.log_frame = _FakeWidget()
            self.log_box = _FakeWidget()
            self.scrollbar = _FakeWidget()
            self.menu = _FakeWidget()

        def _bind_drag(self):
            pass

        def _setup_dnd(self):
            pass

        # --- 覆盖 UI 出口 -> 推事件 ---
        def set_bubble(self, text: str):
            # 对话内容走 chat 事件：只在对话框显示，不打扰猫上的小气泡
            emit({"type": "chat", "text": str(text)})

        def set_state(self, state: str):
            old = getattr(self, "state", None)
            self.state = state
            # 状态真正切换时，在猫头顶弹一句固定的小气泡（仅此5类，不把对话内容搬上来）
            if state != old:
                _state_bubble = {
                    "分析中": "🧠 我在分析情况，稍等一下哦～",
                    "投递中": "💪 开始投递啦，我在努力工作！",
                    "沟通中": "💬 在和 HR 沟通呢～",
                    "停止": "🛑 这轮停啦，想继续随时说～",
                    "待命中": "🐾 我待命中，你说开始我就冲！",
                }.get(state)
                if _state_bubble:
                    emit({"type": "bubble", "text": _state_bubble})
                # session 记录：进入投递中记开始时间，离开投递中记结束时间
                import time as _t, json as _j, pathlib as _p
                try:
                    sess_file = _p.Path(RUN_DIR) / "session_history.json"
                    history = _j.loads(sess_file.read_text("utf-8")) if sess_file.exists() else []
                    if state == "投递中":
                        self._run_start_ts = _t.time()
                        history.append({"start": _t.strftime("%Y-%m-%d %H:%M", _t.localtime()),
                                        "end": None, "status": "running"})
                    elif old == "投递中" and state in ("闲置", "停止", "待命中"):
                        if history and history[-1].get("end") is None:
                            history[-1]["end"] = _t.strftime("%Y-%m-%d %H:%M", _t.localtime())
                            history[-1]["status"] = "finished"
                    # 只留最近 20 条
                    if len(history) > 20:
                        history = history[-20:]
                    sess_file.write_text(_j.dumps(history, ensure_ascii=False, indent=2), "utf-8")
                except Exception:
                    pass
            emit({"type": "state", "state": state, "act": getattr(self, "act", "sit")})
            # 状态变化时同步推一份快照，让 dashboard 总览实时刷新
            try:
                self._push_snapshot()
            except Exception:
                pass

        def set_act(self, act: str):
            self.act = act

        def add_log(self, msg: str):
            # 父类会写 demo.log 文件（保留审计），这里额外推事件
            try:
                super().add_log(msg)
            except Exception:
                pass
            emit({"type": "log", "text": str(msg)})
            # 看板实时同步：打招呼/发简历后5秒节流推一次快照
            import time as _t
            now = _t.time()
            if not hasattr(self, "_last_snapshot_ts"):
                self._last_snapshot_ts = 0.0
            if now - self._last_snapshot_ts > 5 and any(k in str(msg) for k in ("打招呼", "发简历", "已沟通", "投递成功")):
                self._last_snapshot_ts = now
                try:
                    self._push_snapshot()
                except Exception:
                    pass

        def _push_hr_alert(self, act: dict):
            """把 HR 新消息推给看板待处理列表 + 弹气泡提醒用户。"""
            # 持久化到内存列表 + 文件
            import pathlib as _p, json as _j, time as _t
            _hr_list = getattr(self, "_hr_messages", [])
            entry = {
                "hr_name": act.get("hr_name", ""),
                "company": act.get("company", ""),
                "message": act.get("message", ""),
                "time": act.get("time", _t.strftime("%H:%M")),
                "hint": act.get("hint", "喵未自动回复，需要你查看"),
            }
            _hr_list.append(entry)
            if len(_hr_list) > 100:
                _hr_list = _hr_list[-100:]
            self._hr_messages = _hr_list
            # 2026-09-17 合规整改：HR 消息（含姓名/公司/对话内容）不再落盘。
            # 属第三方个人信息，改为仅内存态，进程退出即清除；
            # 同时清理历史遗留文件。
            try:
                (_p.Path(RUN_DIR) / "hr_messages.json").unlink(missing_ok=True)
            except Exception:
                pass
            emit({"type": "hr_alert", **entry})
            _hr = entry["hr_name"] or "HR"
            _co = entry["company"] or ""
            emit({"type": "bubble",
                  "text": "🔔 %s（%s）发来新消息喵没自动回，去看看～" % (_hr, _co)})

        # --- 覆盖两个面板 -> 推事件，等壳回传 ---
        def _show_resume_choice_panel(self, resumes: list):
            _pending_panel["kind"] = "resume_choice"
            _pending_panel["items"] = resumes
            emit({"type": "panel", "kind": "resume_choice",
                  "items": [{"name": r.get("name"), "desc": r.get("desc", "")} for r in resumes]})

        def _hide_resume_choice_panel(self):
            _pending_panel["kind"] = None
            _pending_panel["callback"] = None
            # 2026-09-24 PANELCLOSE：通知壳把面板收起来（原实现只清内部状态 → 框一直挂在聊天里）
            try:
                emit({"type": "panel", "kind": "close"})
            except Exception:
                pass

        def _show_action_panel(self, title: str, options: list, callback):
            _pending_panel["kind"] = "action"
            _pending_panel["callback"] = callback
            _pending_panel["options"] = options
            emit({"type": "panel", "kind": "action", "title": str(title),
                  "options": [{"label": lbl, "index": i} for i, (lbl, _v) in enumerate(options)]})

        def _hide_action_panel(self):
            _pending_panel["kind"] = None
            _pending_panel["callback"] = None
            # 2026-09-24 PANELCLOSE：同上，通知壳收起
            try:
                emit({"type": "panel", "kind": "close"})
            except Exception:
                pass

        # --- LLM 设置：无头不弹 Toplevel，改为推事件给 dashboard ---
        def cmd_llm_settings(self):
            llm = self.cfg.get("llm") or {}
            emit({"type": "config", "llm": {
                "base_url": llm.get("base_url", ""),
                "api_key": llm.get("api_key", ""),
                "model": llm.get("model", ""),
                # 2026-09-24 RESUMEOPT：把「允许上传简历」开关回填给看板
                "allow_resume_upload": bool(llm.get("allow_resume_upload", False)),
                # 2026-09-24 RESUMEOPT2：标记「这是拉取，不是保存」→ 看板不弹「已保存」
                "loaded": True,
            }})

        def _write_run_report(self, rec, kw_stats, stopped_by_user):
            """2026-09-18：报告落盘后主动推给看板，看板因此不需要刷新按钮。

            报告只在轮次结束时生成一次（非实时），所以
            「进页面自动拉 + 轮次结束自动推」已足够覆盖。
            """
            super()._write_run_report(rec, kw_stats, stopped_by_user)
            try:
                emit({"type": "reports", "list": self.list_reports()})
            except Exception:
                pass

        def _push_outcome_update(self, company: str, state: str) -> None:
            """2026-09-19 Q1 方案 A：结果状态变化时**推事件**给看板。

            基类只记日志；这里覆写为 emit，让看板在 HR 回复到达时
            立刻重拉报告详情 / 刷新列表，而不是等用户重新打开。
            """
            try:
                emit({"type": "outcomes_updated",
                      "company": company, "state": state})
            except Exception:
                pass

        def _write_run_report(self, rec, kw_stats, stopped_by_user):
            """2026-09-18：报告落盘后主动推给看板，看板因此不需要刷新按钮。

            报告只在轮次结束时生成一次（非实时），所以
            「进页面自动拉 + 轮次结束自动推」已足够覆盖。
            """
            super()._write_run_report(rec, kw_stats, stopped_by_user)
            try:
                emit({"type": "reports", "list": self.list_reports()})
            except Exception:
                pass

        def _push_outcome_update(self, company: str, state: str) -> None:
            """2026-09-19 Q1 方案 A：结果状态变化时**推事件**给看板。

            基类只记日志；这里覆写为 emit，让看板在 HR 回复到达时
            立刻重拉报告详情 / 刷新列表，而不是等用户重新打开。
            """
            try:
                emit({"type": "outcomes_updated",
                      "company": company, "state": state})
            except Exception:
                pass

        def cmd_config(self):
            self._push_snapshot()

        def _push_snapshot(self):
            """推一份完整快照给 dashboard。"""
            import pathlib as _p, json as _j, time as _t
            llm = self.cfg.get("llm") or {}
            plan = getattr(self, "_plan", {}) or {}
            cfg = self.cfg or {}
            # 薪资/阈值：plan 优先，没有就 fallback 到 cfg
            min_score = plan.get("min_score") or cfg.get("min_score") or 70
            sal_low = plan.get("salary_low") or cfg.get("min_salary_low_k") or 20
            sal_high = plan.get("salary_high") or cfg.get("min_salary_high_k") or 25
            city = plan.get("city") or cfg.get("target_city") or "广州"
            # 2026-09-19 Y：屏蔽词（看板可编辑）—— cfg 的排除词 + 本轮新增的
            exclude_kws = list(dict.fromkeys([
                *(cfg.get("exclude_keywords") or []),
                *(plan.get("exclude_add") or []),
            ]))
            # 2026-09-19 Y：屏蔽词（看板可编辑）—— cfg 的排除词 + 本轮新增的
            exclude_kws = list(dict.fromkeys([
                *(cfg.get("exclude_keywords") or []),
                *(plan.get("exclude_add") or []),
            ]))
            # 从 ledger 读全部历史计数（打招呼/发简历/跳过/失败）
            stats = {"greet": 0, "resume_send": 0, "skip": 0, "fail": 0, "hr_msg": 0}
            try:
                from agent import ledger as _led
                for rec in _led.read_recent(limit=5000, skill_dir=RUN_DIR):
                    act = rec.get("action")
                    if act in stats:
                        stats[act] += 1
            except Exception:
                pass
            # 读 session history
            sessions = []
            try:
                sess_file = _p.Path(RUN_DIR) / "session_history.json"
                if sess_file.exists():
                    sessions = _j.loads(sess_file.read_text("utf-8"))
            except Exception:
                pass
            # 读 HR 消息列表（持久化）
            # 2026-09-17 合规整改：不再从磁盘读取 HR 消息，仅用内存态
            hr_msgs = getattr(self, "_hr_messages", [])
            emit({"type": "snapshot", "state": getattr(self, "state", ""),
                  "act": getattr(self, "act", "sit"),
                  "stats": stats,
                  "sessions": sessions,
                  "hr_messages": hr_msgs,
                  "plan": {
                      "keywords": plan.get("keywords", []),
                      "min_score": min_score,
                      "salary_low": sal_low,
                      "exclude_keywords": exclude_kws,
                      "exclude_keywords": exclude_kws,
                      "salary_high": sal_high,
                      "city": city,
                  },
                  "llm": {"base_url": llm.get("base_url", ""), "model": llm.get("model", ""),
                          "has_key": bool(llm.get("api_key", ""))}})


    return HeadlessPet()


def _dispatch(app, cmd):
    """处理壳发来的命令。"""
    action = cmd.get("cmd")
    try:
        if action == "user_text":
            text = str(cmd.get("text", ""))
            if not text.strip():
                return
            app.entry._buf = text
            app.send()
        elif action == "start":
            app.cmd_test_run(real=True)
        elif action == "confirm_and_start":
            # 如果正在等用户登录，点按钮 = "我登录好了"，走登录确认流程
            if getattr(app, '_login_waiting', False):
                app.set_bubble("正在确认登录状态…")
                threading.Thread(target=app._handle_login_msg, args=("OK",), daemon=True).start()
                return
            # 如果正在等用户选附件简历，点按钮无效（必须选序号）
            if getattr(app, '_resume_choice_waiting', False):
                app.set_bubble("请在对话框回复序号（1~%d）选一份简历哦～" % len(getattr(app, '_resume_choice_list', [])))
                return
            # 正常流程：确认当前方案，跳过 review，直接开始投递
            try:
                app._plan["confirmed"] = True
                app._save_plan_state()
                app._plan_state = None
                app._plan_change_pending = False
                app._plan_reviewed_this_run = True
            except Exception:
                pass
            app.cmd_test_run(real=True)
        elif action == "pause":
            app._paused = True
            app.set_bubble("已暂停当前任务，输入「继续」恢复。")
        elif action == "resume":
            app._paused = False
            app.set_bubble("已继续。")
        elif action == "stop":
            app.cmd_stop()
        elif action == "resume_file":
            app.cmd_resume_file(str(cmd.get("path", "")))
        elif action == "choice":
            idx = int(cmd.get("index", 1)) - 1
            kind = _pending_panel.get("kind")
            if kind == "resume_choice":
                items = _pending_panel.get("items", [])
                if 0 <= idx < len(items):
                    app._on_resume_choice_click(items[idx])
                _pending_panel["kind"] = None
                # 2026-09-24 PANELCLOSE：选完立刻通知壳移除面板（防「还能再选一次」的错觉）
                try:
                    emit({"type": "panel", "kind": "close"})
                except Exception:
                    pass
            elif kind == "action":
                options = _pending_panel.get("options", [])
                cb = _pending_panel.get("callback")
                if cb and 0 <= idx < len(options):
                    _lbl, value = options[idx]
                    cb(value)
                _pending_panel["kind"] = None
                _pending_panel["callback"] = None
                # 2026-09-24 PANELCLOSE：action 面板选完同样通知壳收起
                try:
                    emit({"type": "panel", "kind": "close"})
                except Exception:
                    pass
        elif action == "call":
            fn = cmd.get("action")
            # 2026-09-18 复盘报告：看板「结果复盘」的两个新命令。
            # 它们需要 emit 事件（而不是像其它命令那样只调一个方法），
            # 所以单独分支处理，其余命令行为完全不变。
            if fn == "reports":
                try:
                    emit({"type": "reports", "list": app.list_reports()})
                except Exception as _e:
                    emit({"type": "reports", "list": [], "error": str(_e)[:120]})
            elif fn == "report_detail":
                _rid = str(cmd.get("run_id", ""))
                try:
                    emit({"type": "report_detail", "run_id": _rid,
                          "data": app.load_report(_rid)})
                except Exception as _e:
                    emit({"type": "report_detail", "run_id": _rid,
                          "data": None, "error": str(_e)[:120]})
            elif fn == "kw_feedback":
                # 2026-09-22 KWFB1：关键词的 HR 真实反馈（只读统计）。
                # 文件由主程序每轮结束时写；这里只读，不触发任何投递动作。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "kw_feedback.json"
                    _d = (_j.loads(_f.read_text(encoding="utf-8"))
                          if _f.exists() else {})
                    emit({"type": "kw_feedback",
                          "list": _d.get("stats") or [],
                          "ts": _d.get("ts") or ""})
                except Exception as _e:
                    emit({"type": "kw_feedback", "list": [], "error": str(_e)[:120]})
            elif fn == "startup_diagnosis":
                # 2026-09-22 STARTUP-DIAG：打开诊断结果（只读）。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "startup_diagnosis.json"
                    _d = (_j.loads(_f.read_text(encoding="utf-8")) if _f.exists() else {})
                    emit({"type": "startup_diagnosis",
                          "diagnosis": _d.get("diagnosis") or "",
                          "ts": _d.get("ts") or "",
                          "stats": _d.get("stats") or {}})
                except Exception as _e:
                    emit({"type": "startup_diagnosis", "diagnosis": "", "error": str(_e)[:120]})
            elif fn == "kw_feedback":
                # 2026-09-22 KWFB1：关键词的 HR 真实反馈（只读统计）。
                # 文件由主程序每轮结束时写；这里只读，不触发任何投递动作。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "kw_feedback.json"
                    _d = (_j.loads(_f.read_text(encoding="utf-8"))
                          if _f.exists() else {})
                    emit({"type": "kw_feedback",
                          "list": _d.get("stats") or [],
                          "ts": _d.get("ts") or ""})
                except Exception as _e:
                    emit({"type": "kw_feedback", "list": [], "error": str(_e)[:120]})
            elif fn == "startup_diagnosis":
                # 2026-09-22 STARTUP-DIAG：打开诊断结果（只读）。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "startup_diagnosis.json"
                    _d = (_j.loads(_f.read_text(encoding="utf-8")) if _f.exists() else {})
                    emit({"type": "startup_diagnosis",
                          "diagnosis": _d.get("diagnosis") or "",
                          "ts": _d.get("ts") or "",
                          "stats": _d.get("stats") or {}})
                except Exception as _e:
                    emit({"type": "startup_diagnosis", "diagnosis": "", "error": str(_e)[:120]})
            elif fn == "hr_inbound":
                # 2026-09-19 S：非方案来源的来话（用户自己打招呼 / HR 主动）。
                # 只用于提醒展示，**不进结果统计**（它们没有分数）。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "hr_inbound.json"
                    _items = (_j.loads(_f.read_text(encoding="utf-8"))
                              if _f.exists() else [])
                    emit({"type": "hr_inbound",
                          "list": _items[:50]})
                except Exception:
                    emit({"type": "hr_inbound", "list": []})
            elif fn == "hr_inbound":
                # 2026-09-19 S：非方案来源的来话（用户自己打招呼 / HR 主动）。
                # 只用于提醒展示，**不进结果统计**（它们没有分数）。
                try:
                    import pathlib as _p, json as _j
                    _f = _p.Path(RUN_DIR) / "hr_inbound.json"
                    _items = (_j.loads(_f.read_text(encoding="utf-8"))
                              if _f.exists() else [])
                    emit({"type": "hr_inbound",
                          "list": _items[:50]})
                except Exception:
                    emit({"type": "hr_inbound", "list": []})
            elif fn == "clear_reports":
                # 2026-09-18：只清投递报告。去重缓存/账本刻意不提供入口
                # （去重缓存是省 LLM tokens 的关键，清掉会重复评分）。
                try:
                    emit({"type": "reports_cleared",
                          "result": app.clear_reports()})
                except Exception as _e:
                    emit({"type": "reports_cleared",
                          "result": {"error": str(_e)[:120]}})
            elif fn == "clear_reports":
                # 2026-09-18：只清投递报告。去重缓存/账本刻意不提供入口
                # （去重缓存是省 LLM tokens 的关键，清掉会重复评分）。
                try:
                    emit({"type": "reports_cleared",
                          "result": app.clear_reports()})
                except Exception as _e:
                    emit({"type": "reports_cleared",
                          "result": {"error": str(_e)[:120]}})
            elif fn == "export_delivery":
                # 2026-09-23 EXPORT：只读汇总 job_memory/outcomes/boss-demo-log/reports
                # 为一份 JSON（附 CSV），不影响投递主流程。
                try:
                    emit({"type": "export_delivery",
                          "result": app.cmd_export_delivery_data()})
                except Exception as _e:
                    emit({"type": "export_delivery",
                          "result": {"ok": False, "error": str(_e)[:200]}})
            else:
                {
                    "report": app.cmd_report,
                    "config": app.cmd_config,
                    "llm_settings": app.cmd_llm_settings,
                    "browser": app.cmd_browser,
                    "stop_status": app.cmd_stop_status,
                    "resume": app.cmd_resume,
                    "analyze": app.cmd_analyze,
                }.get(fn, lambda: None)()
        elif action == "save_llm":
            import json as _json
            app.cfg.setdefault("llm", {})
            app.cfg["llm"]["base_url"] = str(cmd.get("url", "")).strip().rstrip("/")
            new_key = str(cmd.get("key", "")).strip()
            if new_key:  # Key 框留空时保留已有 Key，不覆盖
                app.cfg["llm"]["api_key"] = new_key
            app.cfg["llm"]["model"] = str(cmd.get("model", "")).strip()
            # 2026-09-24 RESUMEOPT：保存「允许上传简历」开关
            #（缺省不动，避免旧前端不带该字段时把开关意外关掉）
            if "allow_resume_upload" in cmd:
                app.cfg["llm"]["allow_resume_upload"] = bool(cmd.get("allow_resume_upload"))
            try:
                (Path(__file__).resolve().parent.parent / "run" / "config.json").write_text(
                    _json.dumps(app.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            # 保存提示只走 dashboard config 事件，不弹猫/对话气泡
            emit({"type": "config", "llm": {"base_url": app.cfg["llm"]["base_url"],
                                              "model": app.cfg["llm"]["model"],
                                              "has_key": bool(app.cfg["llm"]["api_key"])}})
            app._push_snapshot()
            # 立即用新配置测一次连通性
            def _ping():
                import urllib.request
                try:
                    req = urllib.request.Request(
                        app.cfg["llm"]["base_url"].rstrip("/") + "/v1/chat/completions",
                        data=_json.dumps({"model": app.cfg["llm"]["model"],
                                          "messages": [{"role": "user", "content": "ping"}],
                                          "max_tokens": 5}).encode("utf-8"),
                        headers={"Authorization": "Bearer " + app.cfg["llm"]["api_key"],
                                 "Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        _json.loads(r.read().decode("utf-8"))
                    emit({"type": "llm_test", "ok": True, "msg": "✅ LLM 连通正常"})
                except Exception as e:
                    # 2026-09-22 LLMTEST1：分类提示 —— 别让"服务商 502"看起来像"配置失效"
                    import urllib.error as _ue
                    _msg = "❌ " + str(e)[:200]
                    if isinstance(e, _ue.HTTPError):
                        _c = e.code
                        if _c in (401, 403):
                            _msg = ("❌ 密钥被拒绝（HTTP %d）—— 检查 API Key 是否正确/是否过期"
                                    % _c)
                        elif _c == 404:
                            _msg = ("❌ 端点不存在（HTTP 404）—— 检查 Base URL 是否要带 /v1")
                        elif _c == 429:
                            _msg = "❌ 请求过多或额度用尽（HTTP 429）—— 稍后重试或检查余额"
                        elif 500 <= _c < 600:
                            _msg = ("❌ 服务商侧故障（HTTP %d）—— **不是你的配置问题**，"
                                    "是接口服务不可用；稍后重试即可" % _c)
                    emit({"type": "llm_test", "ok": False, "msg": _msg})
            threading.Thread(target=_ping, daemon=True).start()
        elif action == "update_plan":
            if getattr(app, "state", "") in ("投递中", "沟通中") or getattr(app, "_is_applying", False):
                emit({"type": "config", "llm": {}, "plan_saved": False,
                      "plan_error": "投递进行中不能修改方案，请先停止投递。"})
                app.add_log("看板方案修改被拒绝：投递进行中，请先停止任务")
                return
            import json as _json
            plan = app._plan or {}
            if "keywords" in cmd:
                kws = [k.strip() for k in str(cmd["keywords"])
                       .replace("，", ",").replace("、", ",").split(",") if k.strip()]
                plan["keywords"] = kws
            if "min_score" in cmd:
                try:
                    ms = int(cmd["min_score"])
                    plan["min_score"] = ms
                    app.cfg["min_score"] = ms
                except Exception:
                    pass
            if "salary_low" in cmd:
                try:
                    sl = int(cmd["salary_low"])
                    plan["salary_low"] = sl
                    app.cfg["min_salary_low_k"] = sl
                except Exception:
                    pass
            if "salary_high" in cmd:
                try:
                    sh = int(cmd["salary_high"])
                    plan["salary_high"] = sh
                    app.cfg["min_salary_high_k"] = sh
                except Exception:
                    pass
            # 2026-09-19 Y：看板编辑屏蔽词（逗号或顿号分隔）
            if "exclude_keywords" in cmd:
                try:
                    exs = [x.strip() for x in
                           str(cmd["exclude_keywords"]).replace("，", ",")
                           .replace("、", ",").split(",") if x.strip()]
                    app.cfg["exclude_keywords"] = exs
                    # 同步写回 config.json（否则重启后丢失）
                    try:
                        import json as _json_ex
                        _cpe = RUN_DIR / "config.json"
                        _cce = _json_ex.loads(_cpe.read_text(encoding="utf-8"))
                        _cce["exclude_keywords"] = exs
                        _cpe.write_text(
                            _json_ex.dumps(_cce, ensure_ascii=False, indent=2),
                            encoding="utf-8")
                    except Exception:
                        pass
                    app.add_log("看板更新屏蔽词（%d 个）：%s" % (len(exs), "、".join(exs[:10])))
                except Exception:
                    pass
            # 2026-09-19 Y：看板编辑屏蔽词（逗号或顿号分隔）
            if "exclude_keywords" in cmd:
                try:
                    exs = [x.strip() for x in
                           str(cmd["exclude_keywords"]).replace("，", ",")
                           .replace("、", ",").split(",") if x.strip()]
                    app.cfg["exclude_keywords"] = exs
                    # 同步写回 config.json（否则重启后丢失）
                    try:
                        import json as _json_ex
                        _cpe = RUN_DIR / "config.json"
                        _cce = _json_ex.loads(_cpe.read_text(encoding="utf-8"))
                        _cce["exclude_keywords"] = exs
                        _cpe.write_text(
                            _json_ex.dumps(_cce, ensure_ascii=False, indent=2),
                            encoding="utf-8")
                    except Exception:
                        pass
                    app.add_log("看板更新屏蔽词（%d 个）：%s" % (len(exs), "、".join(exs[:10])))
                except Exception:
                    pass
            if "city" in cmd:
                plan["city"] = str(cmd["city"]).strip()
                app.cfg["target_city"] = plan["city"]
            try:
                (Path(__file__).resolve().parent.parent / "run" / "plan.json").write_text(
                    _json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
                (Path(__file__).resolve().parent.parent / "run" / "config.json").write_text(
                    _json.dumps(app.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            emit({"type": "config", "llm": {}, "plan_saved": True})
            app._push_snapshot()
        elif action == "fetch_models":
            import urllib.request
            import json as _jsonm
            url = str(cmd.get("url", "")).strip().rstrip("/")
            key = str(cmd.get("key", "")).strip()
            try:
                req = urllib.request.Request(url + "/v1/models",
                    headers={"Authorization": "Bearer " + key})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = _jsonm.loads(r.read().decode("utf-8"))
                ids = sorted([m.get("id", "") for m in data.get("data", []) if m.get("id")])
                emit({"type": "models", "ids": ids})
            except Exception as e:
                emit({"type": "models", "ids": [], "error": str(e)[:200]})
        elif action == "get_state":
            app._push_snapshot()
        else:
            emit({"type": "error", "text": "未知命令: %s" % action})
    except Exception:
        emit({"type": "error", "text": traceback.format_exc()[-800:]})


def main():
    app = _build_headless()
    emit({"type": "ready"})
    app._push_snapshot()

    # 2026-09-23 HISTREPORT：打开诊断已改为「用户唤出投递方案时」触发
    # （见 main.py 的 _show_current_plan）。启动时**不再**自动生成：
    # 既避免用户还没看方案就先弹报告，也不打扰夜间睡觉的猫。

    # 2026-09-23 HISTREPORT：打开诊断已改为「用户唤出投递方案时」触发
    # （见 main.py 的 _show_current_plan）。启动时**不再**自动生成：
    # 既避免用户还没看方案就先弹报告，也不打扰夜间睡觉的猫。
    # stdin 命令循环（逐行 JSON）
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except Exception:
            emit({"type": "error", "text": "bad json: %s" % line[:120]})
            continue
        threading.Thread(target=_dispatch, args=(app, cmd), daemon=True).start()


if __name__ == "__main__":
    main()
