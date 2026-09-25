# -*- coding: utf-8 -*-
"""找工作喵 v8（爬爬版 · 卡片式界面 · Q版形象）

- 回到一开始的形态：卡片窗口 + 圆形头像 + 指令按钮 + 日志区
- 形象：爬爬 Q 版（橘白英短），四帧动作（坐姿/挥手/思考/开心）
- 本版本只有真实投递一种模式（real 参数恒为 True，无演练分支）
- 默认 real=True：点「开始投递」/说「开始找工作」都会**真实投递**（达标岗位真实点「立即沟通」）
运行：双击 run_demo.bat，或 python main.py
"""
import random
import os
import sys
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

# 2026-09-24 OSROOTFIX：开源副本目录结构是 agent/ + boss/ + desktop/（与工作副本的
# v8-core/ + pet-shell/ 不同）→ 必须把**仓库根**放进 sys.path（`import agent.shared` /
# `import boss.boss_apply` 才解析得到），SKILL_DIR / RUN_DIR / ASSETS 也都要以仓库根为基准。
DEMO_DIR = Path(__file__).resolve().parent          # .../<repo>/agent
REPO_ROOT = DEMO_DIR.parent                          # 仓库根
SKILL_DIR = Path(os.environ.get(
    "JOB_HUNTER_PACKAGE_DIR", str(REPO_ROOT)
)).expanduser().resolve()
RUN_DIR = Path(os.environ.get(
    "JOB_HUNTER_HOME", str(REPO_ROOT / "run")
)).expanduser().resolve()
ASSETS = REPO_ROOT / "assets"
LOG_FILE = DEMO_DIR / "demo.log"


# ---------------- 运行期产物体积控制（2026-09-17 修复） ----------------
# 原实现 demo.log 用裸 open(..., "a") 追加、无任何体积判断，长期使用会持续膨胀；
# 浏览器缓存清理只覆盖 Default/ 下的 5 个目录，漏掉 profile 根目录下同样会增长的
# BrowserMetrics / GPUPersistentCache / GrShaderCache / Crashpad 等。
LOG_MAX_BYTES = 5 * 1024 * 1024


# ---------------- 投递前的 HR 监听预跑（用户调试开关，2026-09-18） ----------------
# 用户此前要求保留「投递开始前先跑一轮 HR 监听」的验证代码，用于确认监听能跑通。
# 2026-09-18 用户裁决：调试完成 → 改为**默认关闭**，让投递主循环立即开始，
# 避免每次投递都要等一轮监听。需要再次验证监听时改成 True 即可恢复。
# 注意：关键词循环内的正式监听（每扫完一个关键词跑一轮）不受此开关影响。
_DEBUG_PRECHAT_ROUND = False


def _append_bounded(path, text: str) -> None:
    """向 path 追加 text；文件已超过 LOG_MAX_BYTES 时先清空再写。

    选择「超限整体清空」而不是滚动多份备份：不额外产生文件，也不会让用户
    误以为 .1/.2 备份是需要保留的重要数据。
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            if p.exists() and p.stat().st_size > LOG_MAX_BYTES:
                p.write_text("", encoding="utf-8")
        except OSError:
            pass
        with open(p, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def cleanup_browser_cache(log=None) -> int:
    """清理 9222 专用 Chrome profile 的缓存目录，保留登录 Cookie。

    同时覆盖 Default/ 内部与 profile 根目录两级。删除失败一律忽略：
    缓存目录缺失或被 Chrome 占用都不应影响主流程。
    """
    import shutil

    profile = RUN_DIR / ".job_hunter" / "browser" / "boss"
    targets = [profile / "Default" / sub for sub in (
        "Cache", "Code Cache", "GPUCache", "Service Worker",
        "CacheStorage", "DawnGraphiteCache", "DawnWebGPUCache", "Media Cache",
    )]
    targets += [profile / sub for sub in (
        "BrowserMetrics", "GPUPersistentCache", "GrShaderCache",
        "Crashpad", "ShaderCache",
    )]
    targets += [
        profile / "BrowserMetrics-spare.pma",
        profile / "CrashpadMetrics-active.pma",
    ]

    cleaned = 0
    for p in targets:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                cleaned += 1
            elif p.is_file():
                p.unlink()
                cleaned += 1
        except Exception:
            pass
    if log:
        try:
            log("浏览器缓存已清理（%d 项，保留登录状态）" % cleaned)
        except Exception:
            pass
    return cleaned

BG = "#FFF9F0"

sys.path.insert(0, str(SKILL_DIR))
from agent import shared  # noqa: E402

# BOSS 城市代码（和 boss_apply.py 的 CITY_CODES 保持一致）
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

def get_city_code(city_name: str) -> str:
    """把城市名转成 BOSS 城市代码。
    2026-09-21：表外城市返回**空串**，调用方必须处理并提示用户。
    （原来是 `CITY_CODES.get(name, CITY_CODES["广州"])` —— 会**静默搜广州**，
      用户填了长沙却以为在投长沙，实际搜的是广州。）"""
    return CITY_CODES.get(str(city_name or "").strip(), "")

# ---------- 演练岗位（模拟 JD，仅用于演示评分链路） ----------
DEMO_JOBS = [
    ("海外直播运营经理", "负责海外直播业务从0到1搭建与规模化复制，制定直播运营策略，管理直播团队，优化GMV与转化率，熟悉TikTok直播生态与欧美市场。"),
    ("TikTok 内容运营", "策划并运营TikTok账号内容，短视频脚本与剪辑跟进，内容数据复盘，提升粉丝增长与互动率，熟悉海外社媒玩法。"),
    ("海外社媒运营", "运营Facebook/Instagram/YouTube等海外社媒矩阵，策划品牌内容与活动，海外用户增长与私域沉淀。"),
    ("跨境电商运营", "负责跨境店铺日常运营与活动策划，海外市场选品与投放，优化转化率与ROI，有供应链资源者优先。"),
    ("海外用户增长负责人", "制定海外用户增长策略，搭建增长模型，负责投放与内容获客，带领增长团队，具备欧美市场成功案例。"),
    ("产品运营", "负责产品运营体系建设，用户调研与需求分析，数据驱动优化留存与转化，跨部门协作推进项目。"),
    ("行政助理（日结）", "日常行政事务，按天结算工资，无需经验，包吃住。"),
    ("电话销售客服", "电话销售客户开发，底薪加提成，可接受应届生。"),
]

STATE_COLORS = {"闲置": "#B9B2A6", "分析中": "#E8834A", "投递中": "#5B7C99", "沟通中": "#4E9E7A"}

# 请求节奏（来自 job-hunter-skill 真实参数）
PACING = {
    "jd_read": (1.8, 4.5),        # 读取职位详情 JD
    "next_job": (3.8, 9.0),       # 翻到下一个职位（+6% 概率加 9~15s）
    "task_break": (4.5, 10.5),    # 任务间休息（+4% 概率加 10.5~18s）
    "after_greet": (1.5, 3.0),    # 点「立即沟通」/打招呼后
    "after_apply": (1.5, 3.0),    # 发简历/投递后
    "skip_job": (1.2, 2.25),      # 跳过不匹配职位
    "scroll": (0.45, 1.35),        # 翻页/滚动
    "page_load": (2.25, 3.75),     # 打开搜索页加载
    "long_rest": (225.0, 360.0),  # 每 3 个关键词强制休息（3.75~6 分钟）
}
LONG_REST_DEMO_SCALE = 6.0  # 演示加速：150~240s → 25~40s

# 投递浏览器（9222 调试端口 + BOSS 登录态目录）
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DIR = str(RUN_DIR / ".job_hunter" / "browser" / "boss")

# 对话框可接收的简历文件格式
RESUME_EXTS = (".pdf", ".docx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".bmp", ".webp")


def looks_like_stop_request(text: str) -> bool:
    """识别明确停止投递的表达；与方案修改、闲聊严格分开。"""
    value = str(text or "").strip()
    if not value:
        return False
    # 2026-09-18 第 44 轮修复：纯子串匹配会把否定式与观察式也判成停止指令。
    #   · 否定式：「别停止」「不要停手」→ 语义相反，绝不能停
    #   · 观察式：「还没停止啊，我还以为已经停了呢」→ 是陈述/抱怨，不是指令；
    #     让它落到 LLM 判断通道由猫回应，避免随口一句话就被原子停止。
    _STOP_NEG = ("别停止", "不要停止", "不用停止", "别停下", "不要停下",
                  "别停手", "不要停手", "别中断", "不要中断", "先别停", "别停")
    _STOP_OBS = ("还没停", "还没有停", "还不停止", "尚未停止", "怎么还没停")
    if any(n in value for n in _STOP_NEG):
        return False
    if any(n in value for n in _STOP_OBS):
        return False
    # 2026-09-23 STOPBTN：停止改由「停止投递」按钮触发；聊天只保留这几个**兜底词**
    #（按钮点不到时还能喊停）。其余「停止类」说法不再触发停止（落到 LLM 由猫回应）。
    return any(k in value for k in ("停止投递", "停止找工作", "紧急停止"))


def looks_like_plan_change(text: str) -> bool:
    """识别运行中修改投放方案的明确意图，避免把普通进度询问误切换到方案门禁。"""
    value = str(text or "").strip()
    if not value:
        return False
    # 方案字段覆盖 UI/LLM 可能展示的所有可变约束；字段和动作同时命中，
    # 避免把“现在投得怎么样”这类进度询问误判为方案修改。
    fields = (
        "方案", "关键词", "搜索词", "岗位", "职位", "求职方向", "城市", "地区", "地点",
        "薪资", "工资", "薪资范围", "阈值", "匹配分", "匹配度", "排除词", "屏蔽词",
        # 2026-09-19 W：文案改称「岗位匹配值」，词表必须同步（保留"阈值"兼容老说法）
        "岗位匹配值",
        "关键词数量", "关键词个数", "投递数量", "运行模式", "正式投递", "演练", "兼职", "实习",
        # 2026-09-19 G1：补「我想找正式工作 / 我想找实习」这类说法。
        # 原词表只认「方案/关键词/…」+ 改类动词，导致「我想找正式工作」
        # 既无 field 也无 verb → 被当成闲聊丢给 Agent（日志里实测卡住过）。
        "正式工作", "全职", "实习工作", "找工作", "求职",
    )
    verbs = (
        "改", "调整", "增加", "添加", "补充", "加", "减少", "删除", "去掉", "换", "提高", "降低",
        "屏蔽", "取消", "优化", "设置", "设为", "改到", "调到", "改成", "改为",
        "不投", "不要", "不想",
        # 2026-09-19 G1：补「我想找…」的动词
        "找", "要",
    )
    has_field = any(field in value for field in fields)
    # 数字通常代表直接给出薪资/阈值/数量，即使省略“改为”也属于方案变更。
    has_numeric_value = any(ch.isdigit() for ch in value)
    # "把XX提上第一位/排到第一"这类排序调整
    reorder_hint = any(k in value for k in ("第一位", "排第一", "排到第一", "提上", "提到最前", "排到最前", "第一个"))
    return (has_field and (any(verb in value for verb in verbs) or has_numeric_value)) or reorder_hint


# 2026-09-25 LLMRECOVER：LLM 就绪状态用模块级锁保护（「判断 + 改标记」原子化，防并发重复提示）。
_LLM_STATE_LOCK = threading.Lock()


class PetApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = shared.load_config(RUN_DIR)
        self.state = "闲置"
        self.act = "sit"
        self.results = []
        self.session = {"start": time.time(), "scan_jobs": 0, "sim_analyze": 0,
                        "llm_calls": 0, "resume_analyzed": False, "resume_file": "",
                        "hr_msgs": 0}
        self._monitor_on = False
        self._monitor_job = None
        self._seen_msgs = {}
        self._paused = False
        self._stop_requested = False  # 用户输入「停止」→ 立即中断当前任务
        self._last_kw_stats = []  # 本轮各关键词有效性统计（供停止总结）
        self._last_run_rec = None  # 本轮运行记录（供停止总结）
        # 2026-09-18 复盘报告：本轮已评分岗位明细（只收 LLM 真评分成功的）
        self._run_jobs = []
        self._real_pace = True  # 请求节奏：默认真实间隔（非演示加速）
        # LLM 可用性门禁（2026-09-18 运行审计修复）：
        #   _llm_preflight_* —— 启动前极短连通性探测（失败则不进入投递流程）
        #   _llm_runtime_warned —— 运行中 LLM 异常只提醒一次，不替用户停止
        self._llm_preflight_pending = False
        self._llm_preflight_ok_until = 0.0
        self._llm_runtime_warned = False
        # 离线重放模式（分流）：True=岗位从本地缓存读取，零 BOSS 请求；False=真实浏览器链路
        self._offline = False
        self._offline_label = None  # 标题行模式提示 Label（动态更新）
        # 轮次状态机（三态持久化）与稳定性自检计数（交接补充）
        self._by_watchdog = "--pet-watchdog" in sys.argv  # 守护拉起 vs 用户手动启动入口区分
        self._st = {"dedup_hits": 0, "block_hits": 0, "retry_count": 0,
                    "empty_search_streak": 0, "apply_fail_streak": 0,
                    "greet_streak": 0,  # 连续打招呼次数
                    "last_2h_rest": 0}  # 上次 2 小时大休息时间戳
        # 浏览器操作锁：投递主线程和监听线程不同时操作浏览器（方案3）
        self._browser_lock = threading.Lock()
        self._run_started = 0.0  # 本轮投递开始时间（30 分钟稳定性自检触发基准）
        # LLM 主控接管（新需求：方案确认后 LLM 介入决策，喵执行）
        # 硬约束：接管只发生在「附件简历确认通过」之后；附件简历门禁不可跳过（哪怕 LLM 接手）
        self._llm_agent_enabled = True   # 默认启用（对话可关闭）
        self._llm_agent = False          # 当前是否已接管
        self._llm_agent_pending = False  # 兼容字段（接管已前置到简历上传，保留供状态检查）
        self._llm_agent_ctx = {"kw_stats": [], "decisions": []}
        self._last_choice_bubble = ""    # 附件简历选择面板当前气泡（LLM 辅助建议追加于此）
        self._llm_stage = ""             # 当前环节名（环节简报用）
        self._llm_ctx_log = []           # 环节轨迹（LLM 快速判断现状用，最多 20 条）
        # 门禁B 登录等待：未登录 → 打开登录页 → 用户对话框告知 → LLM 判断 → 重检登录
        self._login_waiting = False
        self._login_confirmed = False
        # 后台运行默认关闭；开启后仅最小化 Chrome，登录/风控/人工门禁时恢复窗口。
        self._background_mode = bool(self.cfg.get("background_mode", False))
        self._login_checking = False
        # 新增情况2：BOSS 无附件简历 → LLM 引导上传 → 用户回复传好 → 重检 → 门禁C
        self._resume_upload_waiting = False
        self._resume_upload_confirmed = False
        # 环境门禁：未装 Chrome → LLM 教安装 → 用户告知装好了 → LLM 判断 → 拉起 Chrome 为硬门槛
        self._install_waiting = False
        # 投递进行中的实时进度（供 LLM 中途报告读取）
        self._live_rec = {}
        # 对话记忆（「懂人性」改造层3，2026-09-18）：Python 端自持。
        # 前端 pet-shell/src/main.js 的 chatHistory 只用于 UI 回放、从不回传 Python，
        # 所以记忆必须由本进程维护 —— 好处是**不需要改 pet_bridge 协议、不需要改 main.js**。
        # 落盘位置 RUN_DIR/chat-memory.json，只保留最近 CHAT_MEMORY_MAX 条。
        self._chat_memory = []          # [{"role":"user"/"assistant","content":str}]
        # ⚠️ 读盘**必须延后到 _build_ui() 之后**（见下方 set_state("闲置") 处那一行）：
        #    _chat_memory_load() 的异常分支会调 self.add_log()，而 add_log 需要
        #    self.log_box —— 那是 _build_ui() 里才创建的。若在这里调用，一旦记忆文件
        #    损坏，except 块会**二次抛 AttributeError**（except 块内的异常不会被同一个
        #    try 捕获）→ 直接崩在启动阶段。与 L280-283 的 _load_plan_state() 是同一类陷阱。
        # 每次启动都要重新确认一次方案（硬门槛）：本轮已确认过则跳过预览，新轮/传新简历重置
        self._plan_reviewed_this_run = False
        # 投递中用户说"附件简历选错了/重选"→ LLM 判断后置位，下个关键词前重走环节④
        self._resume_reselect_requested = False
        self._plan_change_pending = False
        self._night_confirmation_pending = False
        self._night_confirmed_for_run = False
        # 内置 BOSS 上传附件简历攻略（LLM 引导失败时兜底，按官网路径核实）
        self._upload_guide_static = (
            "【BOSS 直聘网页版上传附件简历步骤（已核实官网路径）】\n"
            "1. 用投递浏览器（9222 窗口）打开 BOSS 直聘官网 https://www.zhipin.com 并登录；\n"
            "2. 鼠标移到右上角头像 → 点「我的简历」；\n"
            "3. 在打开的页面右侧找到「附件简历 / 附件管理」区 → 点「上传简历/作品集」；\n"
            "4. 选本地 PDF 上传（建议 PDF、文件名清晰，如：姓名-目标岗位-2026，最多 3 份）；\n"
            "5. 另一条路：打开「聊一聊」任一 HR 会话 → 点「发简历」→「上传」，按提示完成；\n"
            "6. 上传后稍等 1~2 分钟生效，然后回来告诉我「传好了」，我会重新检测并让你选发送哪一份。")
        # 附件简历选择（流程内等待用户点击选择）
        self._resume_choice_waiting = False
        self._resume_choice_list = []
        self._resume_choice_selected = None
        self._choice_panel = None
        # 投放方案流程（关键词提炼 + LLM 判定求职方向 + 对话框多轮审核）
        self._plan = {"keywords": [], "exclude_pt": False, "pt_asked": False,
                      "confirmed": False, "source": "",
                      "min_score": None, "salary_low": None, "salary_high": None,
                      "exclude_add": []}
        self._plan_state = None  # None=未在审核 | "review"=方案审核中（等用户修改意见/确认）
        self._action_panel = None
        # 启动即从磁盘恢复上次方案，避免重启后「看看方案」说没方案
        try:
            self._load_plan_state()
        except Exception:
            pass

        # 四帧动作（Q 版透明图，圆形裁切展示）
        self.frames = {
            "sit": self._load_cat(ASSETS / "papai_sit_t.png"),
            "wave": self._load_cat(ASSETS / "papai_wave_t.png"),
            "think": self._load_cat(ASSETS / "papai_think_t.png"),
            "happy": self._load_cat(ASSETS / "papai_happy_t.png"),
        }

        # 无边框置顶卡片窗口（不透明）
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry("+%d+%d" % self._bottom_right(360, 462))
        root.resizable(False, False)  # 禁止用户拉伸窗口大小

        self._fonts()
        self._build_ui()
        self._bind_drag()
        self._setup_dnd()
        self.set_state("闲置")
        # 对话记忆读盘（「懂人性」层3）：必须在 _build_ui() 之后 ——
        # 它的异常分支要调 add_log()，而 log_box 由 _build_ui() 创建。
        # 详见 __init__ 中 self._chat_memory = [] 处的说明。
        self._chat_memory_load()
        # 启动时检测是否有历史简历
        _has_old_resume = False
        try:
            p = RUN_DIR / "resume.md"
            if p.exists() and len(p.read_text(encoding="utf-8", errors="ignore").strip()) >= 30:
                _has_old_resume = True
        except Exception:
            pass
        if _has_old_resume:
            if self._plan.get("keywords"):
                self.set_bubble("你好，我是爬爬。📋 上次的投递方案还在，说「看看方案」，或点下面的「投递方案」按钮")
            else:
                self.set_bubble("你好，我是爬爬。📄 检测到你之前上传过简历，但还没生成投放方案。\n说「看看方案」让我重新生成，或说「开始找工作」走流程。")
        else:
            self.set_bubble("喵~我是爬爬，我是你投递简历的小猫助理，你把简历拖给我，我来帮你想想投递方案，包你满意的呀，PDF和图片我都看得懂")
        self.add_log("找工作喵 v8 启动（完整闭环 · 简历解析 · HR消息 · 监听 · 真实投递）")
        # 2026-09-24 PLANNOLLM：新用户引导 —— LLM 未配置时关键词提炼根本跑不了（提炼块被跳过）。
        # 这里在启动问候之后**主动提示**，把「配置 LLM」补进新用户流程；
        # 否则用户拖完简历只会拿到一个 0 关键词的空方案（2026-09-24 实测踩过）。
        try:
            self._llm_degraded = False   # 2026-09-25 LLMRECOVER：LLM 未就绪标记（供评分恢复提示用）
            self._llm_fail_streak = 0    # LLMRECOVER：连续「本应调 LLM 却失败」次数（防抖）
            _llm0 = shared.build_llm_client(self.cfg)
            if not getattr(_llm0, "is_configured", lambda: False)():
                self.add_log("启动检查：LLM 未配置（新用户需先配置，否则无法从简历提炼关键词）")
                self.set_bubble(
                    "喵~我是爬爬！先跟你说一件事：我还没配置 LLM，没法从简历提炼关键词。\n\n"
                    "① 右键点我 →「📊 分析报告」打开看板 → 切到「设置 · LLM」，填好 base_url / 密钥 / 模型 并保存；\n"
                    "② 然后把简历拖给我，我就给你出方案啦～\n\n"
                    "也可以点下面的链接直接打开设置：")
                # 2026-09-25 CFGLINK：未配置分支也给出可点链接（原来只有文字引导，无入口）
                self._emit_link("打开 LLM 设置", self.cmd_llm_settings)
                # 2026-09-25 LLMRECOVER：标记「LLM 未就绪」→ 岗位评分首次成功调 LLM 时提示恢复
                self._llm_degraded = True
            else:
                # 2026-09-24 RESUMELLM：已配置 → **后台**探一次连通性（不阻塞启动）。
                # 用户实测：新机器上没配 / 连不上 LLM 时，拖简历会静默降级成「没有关键信息的回复」。
                def _llm_ping_startup():
                    _ok = False   # 2026-09-25 LLMRECOVER：本次探测是否通过（未通过则后台复探）
                    try:
                        # 2026-09-24 LLMFIX：原写法 chat_text("ping", max_tokens=, temperature=)
                        # 只传了 system_prompt，漏掉必填的 user_prompt → 抛
                        # "missing 1 required positional argument: 'user_prompt'"，被 except 误判为
                        # "LLM 连不上"，导致已正确配置的用户也看到这条告警。补上 user_prompt 即可。
                        _txt = _llm0.chat_text(
                            "你是连通性自检助手，仅用于确认 LLM 接口是否可用。",
                            "请只回复两个字：pong",
                            max_tokens=50, temperature=0.0) or ""
                        if str(_txt).strip():
                            _ok = True
                        else:
                            self.add_log("启动检查：LLM 连通性异常（返回为空）")
                            self.root.after(0, lambda: self.set_bubble(
                                "⚠️ LLM 配置看着是好的，但**探测返回为空** ——\n"
                                "多半是推理模型把输出预算耗在思考上（不是网络/密钥问题），重试通常即可。"))
                    except Exception as _e0:
                        _msg = str(_e0)[:120]
                        self.add_log("启动检查：LLM 连不上（%s）" % _msg)
                        self.root.after(0, lambda m=_msg: (
                            self.set_bubble(
                                "⚠️ LLM 连不上：%s\n\n"
                                "简历诊断 / 投递关键词 / 岗位评分都会受影响。\n"
                                "多半是密钥 / 网络 / 代理问题，可点下方「打开 LLM 设置」核对：\n"
                                "① base_url 是否填对 ② 密钥是否有效 ③ 是否开了系统代理却没真正连上。" % m),
                            self._emit_link("打开 LLM 设置", self.cmd_llm_settings)))
                    # 2026-09-25 LLMRECOVER：本次未通过 → 标记未就绪；岗位评分成功调 LLM 时提示恢复
                    if not _ok:
                        self._llm_degraded = True
                try:
                    threading.Thread(target=_llm_ping_startup, daemon=True).start()
                except Exception:
                    pass
        except Exception:
            pass
        # 2026-09-24 CHROMECHK：新用户引导 —— 没装 Chrome，投递浏览器（9222）就起不来。
        # 启动时提前提示（原来只在「开始投递」的 0/5 环境才检查，用户走到那一步才被打断）。
        # 注意：这里**不设 _install_waiting**，不拦流程，只是提前告知。
        try:
            if not self._chrome_ok():
                self.add_log("启动检查：未检测到 Chrome（投递依赖它，需先安装）")
                self._llm_guide_install_chrome()
        except Exception:
            pass
        # 2026-09-20 CAT：夜间启动 → 桌宠切「睡觉」素材（替代看鼠标）
        try:
            import os as _os_night
            _force_night = bool(_os_night.environ.get("MIAO_FORCE_NIGHT"))
            if _force_night or shared.is_night_window():
                self._emit_pet_state("sleep")
                self.add_log("夜间启动：桌宠切换为睡觉状态"
                              + ("（调试强制）" if _force_night else ""))
        except Exception:
            pass
        # 入口区分（交接补充）：守护拉起时遇到手动停止标记 → 保持停止状态，不消费标记
        if self._by_watchdog and (RUN_DIR / "manual_stop.flag").exists():
            self.add_log("守护拉起（--pet-watchdog）：检测到手动停止标记，保持停止状态，不自动恢复投递")
        # 启动清理：残留守护与投递状态标记不得脱离投递生命周期存活（投递停→守护停）
        self._guard_tasks("disable")
        self._set_applying(False)

    # ---------- 基础 ----------
    def _fonts(self):
        self.f_title = tkfont.Font(family="Microsoft YaHei", size=12, weight="bold")
        self.f_body = tkfont.Font(family="Microsoft YaHei", size=10)
        self.f_small = tkfont.Font(family="Microsoft YaHei", size=9)
        self.f_chip = tkfont.Font(family="Microsoft YaHei", size=9, weight="bold")

    def _bottom_right(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return (sw - w - 24, sh - h - 90)

    def _load_cat(self, path: Path, size: int = 104):
        im = Image.open(path).convert("RGBA")
        im = im.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        out = Image.new("RGBA", (size, size), (255, 249, 240, 0))
        out.paste(im, (0, 0), mask)
        return ImageTk.PhotoImage(out)

    def _bind_drag(self):
        self._drag = None
        for w in (self.root, self.outer, self.head, self.avatar_lbl, self.bubble_lbl, self.log_box):
            w.bind("<Button-1>", self._on_down)
            w.bind("<B1-Motion>", self._on_move)

    def _on_down(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._drag_start = (e.x_root, e.y_root)

    def _on_move(self, e):
        if not self._drag:
            return
        # 位移 <8px 视为点击而非拖拽，避免点击按钮时误拖动窗口
        if abs(e.x_root - self._drag_start[0]) + abs(e.y_root - self._drag_start[1]) < 8:
            return
        self.root.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def add_log(self, msg: str):
        # 2026-09-17 修复：原为裸 open(..., "a") 追加，无体积判断，会无限增长。
        _append_bounded(LOG_FILE, msg + "\n")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", "· " + msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ---------- UI ----------
    def _build_ui(self):
        self.outer = tk.Frame(self.root, bg=BG, bd=1, relief="solid",
                              highlightbackground="#E4DDD0", highlightthickness=1)
        self.outer.pack(fill="both", expand=True)

        # 头部：圆形头像 + 名字 + 状态灯
        self.head = tk.Frame(self.outer, bg=BG)
        self.head.pack(fill="x", padx=14, pady=(12, 6))
        self.avatar_lbl = tk.Label(self.head, image=self.frames["sit"], bg=BG)
        self.avatar_lbl.pack(side="left", padx=(0, 12))
        info = tk.Frame(self.head, bg=BG)
        info.pack(side="left", fill="y")
        tk.Label(info, text="爬爬 · 找工作喵", font=self.f_title, bg=BG, fg="#2B2622").pack(anchor="w")
        state_row = tk.Frame(info, bg=BG)
        state_row.pack(anchor="w", pady=(6, 0))
        self.state_dot = tk.Label(state_row, text="●", font=self.f_small, fg="#B9B2A6", bg=BG)
        self.state_dot.pack(side="left")
        self.state_lbl = tk.Label(state_row, text="闲置", font=self.f_small, fg="#6B6359", bg=BG)
        self.state_lbl.pack(side="left", padx=(4, 0))
        self._offline_label = tk.Label(info, text="在线模式 · 达标岗位真实投递", font=self.f_small, fg="#C96A35", bg=BG)
        self._offline_label.pack(anchor="w", pady=(4, 0))

        # 气泡
        self.bubble_lbl = tk.Label(self.outer, text="", font=self.f_body, fg="#2B2622", bg="#FFFFFF",
                                   wraplength=300, justify="left", anchor="nw", padx=12, pady=10,
                                   highlightbackground="#E4DDD0", highlightthickness=1)
        self.bubble_lbl.pack(fill="x", padx=14, pady=(0, 8))

        # 指令按钮
        chip_row = tk.Frame(self.outer, bg=BG)
        self._chip_row = chip_row
        chip_row.pack(fill="x", padx=14)
        chip_cmds = [("分析岗位", self.cmd_analyze), ("开始投递", self.cmd_test_run),
                     ("简历匹配", self.cmd_resume), ("求职配置", self.cmd_config),
                     ("附件简历", self.cmd_boss_resumes), ("冒烟", self.cmd_smoke),
                     ("模拟HR消息", self.cmd_chat), ("今日简报", self.cmd_report),
                     ("暂停投递", self.cmd_pause), ("LLM设置", self.cmd_llm_settings)]
        for i in range(0, len(chip_cmds), 3):
            row = tk.Frame(chip_row, bg=BG)
            row.pack(fill="x", pady=(0, 6))
            for text, fn in chip_cmds[i:i + 3]:
                tk.Button(row, text=text, font=self.f_chip, bg="#FFFFFF", fg="#2B2622",
                          activebackground="#FBEBDD", activeforeground="#C96A35",
                          relief="flat", bd=0, highlightbackground="#E4DDD0", highlightthickness=1,
                          cursor="hand2", command=fn).pack(side="left", fill="x", expand=True, padx=(0, 6))

        # 输入行
        input_row = tk.Frame(self.outer, bg=BG)
        input_row.pack(fill="x", padx=14, pady=(2, 8))
        self.entry = tk.Entry(input_row, font=self.f_body, bg="#FFFFFF", fg="#2B2622",
                              relief="flat", highlightbackground="#E4DDD0", highlightthickness=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.send())
        tk.Button(input_row, text="简历", font=self.f_chip, bg="#F4B393", fg="#FFFFFF",
                  activebackground="#D99A77", activeforeground="#FFFFFF", relief="flat", bd=0,
                  cursor="hand2", command=self.cmd_resume).pack(side="left", padx=(6, 0), ipadx=8, ipady=2)
        tk.Button(input_row, text="发送", font=self.f_chip, bg="#E8834A", fg="#FFFFFF",
                  activebackground="#C96A35", activeforeground="#FFFFFF", relief="flat", bd=0,
                  cursor="hand2", command=self.send).pack(side="left", padx=(6, 0), ipadx=10, ipady=2)
        # 最高权限停止按钮：停喵一切动作（投递/监听/watchdog），不退出程序
        tk.Button(input_row, text="停", font=self.f_chip, bg="#EA6668", fg="#FFFFFF",
                  activebackground="#C2575A", activeforeground="#FFFFFF", relief="flat", bd=0,
                  cursor="hand2", command=self.cmd_stop).pack(side="left", padx=(6, 0), ipadx=8, ipady=2)

        # 日志（带滚动条）
        log_frame = tk.Frame(self.outer, bg="#F7F2E9")
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.log_box = tk.Text(log_frame, height=6, font=self.f_small, bg="#F7F2E9", fg="#6B6359",
                               relief="flat", highlightthickness=0,
                               state="disabled", wrap="word")
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

        # 右键菜单
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="置顶 / 取消置顶", command=self.toggle_top)
        self.menu.add_command(label="开启/暂停消息监听", command=self._toggle_monitor)
        self.menu.add_command(label="请求节奏：演示加速 / 真实", command=self._toggle_pace)
        self.menu.add_command(label="退出桌宠", command=self._close_app)
        for w in (self.outer, self.bubble_lbl, self.log_box, self.avatar_lbl):
            w.bind("<Button-3>", self._on_menu)
        self.root.protocol("WM_DELETE_WINDOW", self._close_app)

    def _close_app(self) -> None:
        """窗口退出也走手动停止语义，避免 watchdog 把用户退出误判成崩溃重启。"""
        self._stop_requested = True
        self._paused = False
        try:
            (RUN_DIR / "manual_stop.flag").write_text("user-close", encoding="utf-8")
        except Exception:
            pass
        self._round_state_write("MANUAL_STOPPED")
        self._guard_tasks("disable")
        self._set_applying(False)
        self.add_log("用户关闭桌宠：已写 MANUAL_STOPPED，禁用投递与守护")
        try:
            self.root.destroy()
        except Exception:
            pass

    def toggle_top(self):
        cur = bool(self.root.attributes("-topmost"))
        self.root.attributes("-topmost", not cur)

    def _on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    # ---------- 状态与动作 ----------
    def set_state(self, state: str):
        _old = self.state
        self.state = state
        self.state_dot.configure(fg=STATE_COLORS.get(state, "#B9B2A6"))
        self.state_lbl.configure(text=state)
        _btn = "红色停止投递" if state in ("投递中", "沟通中") else "橙色开始投递"
        self.add_log("【验证5-按钮】状态：%s→%s | 按钮：%s" % (_old, state, _btn))

    def set_act(self, act: str):
        self.act = act
        self.avatar_lbl.configure(image=self.frames.get(act, self.frames["sit"]))

    def set_bubble(self, text: str):
        self.bubble_lbl.configure(text=text)

    # ---------- 指令 ----------
    def cmd_analyze(self):
        if self.state == "分析中":
            return
        self.set_state("分析中")
        self.set_act("think")
        self._stop_requested = False
        self.set_bubble("正在用「LLM + 评分引擎」深度分析 8 个示例岗位：真实调用你配置的 LLM（简历 + JD 匹配补分 40 分），不会真的投递。约 1~2 分钟…")
        self.add_log("开始 LLM 分析：8 个示例岗位（只分析，不投递）")

        def _work():
            results, shown, skipped = [], [], 0
            self.session["sim_analyze"] += 1
            for title, jd in DEMO_JOBS:
                if self._stop_requested:
                    break
                while self._paused:  # 支持暂停
                    time.sleep(0.3)
                try:
                    # 不传 resume_text：自动读 run/resume.md，走真实 LLM 补分；LLM 失败自动回退启发式
                    res = self._score_jd(title, jd, self.cfg, skill_dir=RUN_DIR)
                    self.session["llm_calls"] += 1
                except Exception as exc:
                    self.root.after(0, lambda e=exc: self.add_log("评分异常：%s" % e))
                    continue
                while self._paused:  # LLM 返回后若已暂停，立即停住
                    time.sleep(0.3)
                results.append((title, res))
                if res.decision == "skip":
                    skipped += 1
                else:
                    shown.append("%s %d分(LLM+%d)" % (title, res.total_score, res.llm_score))
                    self.root.after(0, lambda t=title, s=res.total_score, l=res.llm_score:
                                    self.add_log("命中：%s %d分（LLM 补分 +%d）" % (t, s, l)))
            if self._stop_requested:
                self.root.after(0, lambda: (self.set_bubble("🛑 已停止分析。"), self.set_state("闲置")))
                self.add_log("分析已停止（用户请求）")
                return
            self.results = results

            def _done():
                if shown:
                    self.set_bubble("LLM 分析完成，达标岗位：\n" + "\n".join(shown[:5]) +
                                    "\n\n评分=岗位30+技能30+LLM40，含真实 LLM 匹配。\n（仅分析，未投递）")
                else:
                    self.set_bubble("LLM 分析完成，本轮 8 个示例岗位均未达标。真实扫描会换更多关键词。")
                self.set_state("闲置")
            self.root.after(0, _done)

        threading.Thread(target=_work, daemon=True).start()

    def cmd_resume(self):
        """2026-09-23 NOPICKER：不再弹「选择简历文件」系统对话框。

        收文件只保留两条通路：① 把文件拖到猫身上（windnd `_on_drop`）；
        ② 对话框直接发文件路径（`cmd_resume_file`）。Electron 模式聊天框没有
        「选文件」按钮，弹系统文件框会莫名打断用户 → 隐藏掉。
        · 已有简历 → 直接分析 run/resume.md；
        · 没有简历 → 提示拖文件 / 发路径，不弹框。
        """
        # 投递中 / 沟通中：不打断当前轮次（动简历会影响方案与轮次基线）
        if self.state in ("投递中", "沟通中"):
            self.set_bubble("正在投递中，换简历会打断这一轮。\n想换简历请先点「停止投递」，再把新简历拖给我～")
            return
        self.set_state("分析中")
        self.set_act("think")
        _p = RUN_DIR / "resume.md"
        try:
            _has = bool(_p.exists() and _p.read_text(encoding="utf-8").strip())
        except Exception:
            _has = False
        if not _has:
            self.set_bubble("我还没收到简历。\n把简历文件（PDF / Word / 图片 / 文字）**拖到我身上**，\n"
                            "或直接把文件路径发到对话框，我就能分析～")
            self.set_state("闲置")
            return
        self.set_bubble("正在解析并分析你已有的简历（含 LLM 诊断，约 30 秒）…")
        self.add_log("分析已有简历：run/resume.md")
        self._run_resume_analysis(str(_p))

    def _setup_dnd(self):
        """启用拖拽：把简历文件拖到窗口上自动分析。"""
        try:
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop, force_unicode=True)
            self._dnd_enabled = True
            self.add_log("拖拽已启用：把简历文件拖到窗口即可分析")
        except Exception as exc:
            self._dnd_enabled = False
            self.add_log("拖拽支持未启用：%s" % exc)

    def _on_drop(self, files):
        paths = []
        for f in (files or []):
            try:
                f = f.decode("utf-8") if isinstance(f, bytes) else str(f)
            except Exception:
                continue
            p = Path(f)
            if p.suffix.lower() in RESUME_EXTS and p.exists():
                paths.append(p)
        if not paths:
            names = "、".join(str(f) for f in (files or [])[:3])
            self.set_bubble("收到文件（%s），但不是简历格式。\n支持：PDF / JPG / PNG / BMP / WebP / Word / TXT" % names)
            return
        if len(paths) > 1:
            # 一次只允许一份；多份先后上传时评分自动用最新
            self.set_bubble("一次只能上传一份简历哦。\n请单独拖入一份；多份简历可先后分别上传，评分会自动用最新的一份。")
            self.add_log("拖入 %d 份简历：拒绝，一次仅限一份" % len(paths))
            return
        self.cmd_resume_file(str(paths[0]))

    def cmd_resume_file(self, path: str):
        """对话框直接接收简历文件（PDF/图片/Word/文字），分析理解。
        新规则：用户任何时候上传简历 = 等同手动停止当前一切动作，从环节3 重新走流程，
        不保留旧简历方案，只保留最新上传的这份。"""
        busy = (self.state == "分析中" or self._plan_state == "review"
                or self._resume_choice_waiting or self._login_waiting
                or self._resume_upload_waiting or self._install_waiting)
        if busy:
            # 上传新简历 = 手动停止：先停掉当前投递/等待流程，再走新简历分析
            self.set_bubble("📥 收到新简历，先停掉当前流程，以最新简历为准重新走…")
            self._stop_requested = True
            self._paused = False
            try:
                (RUN_DIR / "manual_stop.flag").write_text("user-manual-stop", encoding="utf-8")
            except Exception:
                pass
            self._round_state_write("MANUAL_STOPPED")
            self._plan_state = None
            self._login_waiting = False
            self._resume_upload_waiting = False
            self._install_waiting = False
            self._resume_choice_waiting = False
            self._plan_reviewed_this_run = False  # 新简历=新轮，方案重新确认
            self._hide_action_panel()
            self._hide_resume_choice_panel()
            self._set_applying(False)
            threading.Thread(target=self._atomic_stop_work, daemon=True).start()
        self.set_state("分析中")
        self.set_act("think")
        self.add_log("接收简历文件：%s（上传=手动停止+重走流程）" % path)
        self.set_bubble("📥 收到简历文件「%s」，正在解析…" % Path(path).name)
        self._run_resume_analysis(path)

    def _run_resume_analysis(self, path: str):
        """统一简历分析入口：按类型读取 → 技能提取 → LLM 诊断 → 更新 resume.md → 展示。"""

        def _work():
            try:
                ext = Path(path).suffix.lower()
                if ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    self.root.after(0, lambda: self.set_bubble(
                        "🔍 图片简历：正在本地识别文字（长图约需 1 分钟）…"))
                    text = self._read_image_resume(path)
                elif ext == ".pdf":
                    text = self._read_pdf_resume(path)
                else:
                    text = self._extract_resume_text(path)
            except Exception as exc:
                self.root.after(0, lambda e=exc: (self.set_bubble("简历读取失败：%s" % e), self.set_state("闲置")))
                return
            if not text or not text.strip():
                self.root.after(0, lambda: (self.set_bubble(
                    "未能从该文件中读到内容。\n图片不清晰或 PDF 为复杂扫描件时，建议换更清晰的版本。"),
                    self.set_state("闲置")))
                return
            # 2026-09-21：识别结果必须**像一份简历**。
            # 视觉/模型落空时会回一句「我没有收到图片…」—— 非空但根本不是简历，
            # 以前会一路放行，把拒绝话术当正文提炼技能、写进 config。这里拦死。
            _bad = any(k in text for k in (
                "没有收到", "未收到", "无法查看", "无法看到", "看不到图片",
                "请上传", "重新上传", "不是简历", "无法读取图片"))
            if len(text.strip()) < 80 or _bad:
                self.add_log("简历识别结果无效（%d 字），已终止；未写入 config / resume.md"
                              % len(text.strip()))
                # 2026-09-21：别把「本地识别组件没装/超时」说成「图片不清晰」——
                # 那是误导（与 09-19 G3 同一类）。有 OCR 诊断信息就直说原因。
                _diag = str(getattr(self, "_ocr_diag", "") or "")
                if _diag:
                    _msg = ("没能把这张图片识别成简历（%d 字）。\n"
                            "本地识别：%s\n"
                            "请在运行环境中执行 pip install rapidocr-onnxruntime（装完重启喵），"
                            "或改用 PDF / Word / 纯文本简历。" % (len(text.strip()), _diag[:80]))
                else:
                    _msg = ("没能把这个文件识别成简历（%d 字）。\n"
                            "请换更清晰、完整包含文字的版本，或改用 PDF / Word / 纯文本简历。"
                            % len(text.strip()))
                self.root.after(0, lambda: (self.set_bubble(_msg), self.set_state("闲置")))
                return
            # 2026-09-25 NOTRESUME：传错文件（如「公司关系」「合同」「报表」）时，
            # 旧逻辑会把它当简历，提炼出「天眼查、孔旭芳」等假技能写进 config，
            # 还回一句「简历分析完成」—— 误导用户（用户实测误传 公司关系.pdf）。
            # 这里加一道「像不像简历」判定：命中简历特征词才放行。
            _resume_markers = (
                "简历", "求职", "应聘", "教育经历", "教育背景", "学历", "毕业", "主修",
                "工作经历", "工作经验", "项目经历", "项目经验", "实习经历", "校园经历",
                "自我评价", "个人优势", "求职意向", "期望职位", "期望薪资", "技能特长",
                "获奖", "resume", "curriculum vitae", "education", "experience",
                "objective", "work history", "skills",
            )
            _low = text.lower()
            _hit = sum(1 for _k in _resume_markers if _k.lower() in _low)
            if _hit == 0:
                self.add_log("文件不像简历（0 个简历特征词），已终止；未写入 config / resume.md")
                self.root.after(0, lambda: (self.set_bubble(
                    "⚠️ 这个文件看起来**不是简历** —— 我没找到「教育 / 工作 / 项目经历、求职意向」这类内容。\n"
                    "请确认后把**简历**重新拖给我（支持 PDF / Word / 图片 / 纯文本）。"),
                    self.set_state("闲置")))
                return
            self._finish_resume_analysis(text, Path(path).name, path)

        threading.Thread(target=_work, daemon=True).start()

    def _finish_resume_analysis(self, text: str, source_name: str, path=None):
        """技能提取 + LLM 诊断 + 写 resume.md（原文件备份） + 气泡展示。"""
        n = len(text.strip())
        skills = shared.heuristic_extract_skills(text, limit=12)

        # ---- 修复 T（2026-09-17）：把简历提取到的技能写回配置 ----
        # 原实现只把技能写进 run/resume.md 和气泡，从不写 config["skills"]；
        # 而评分引擎 shared.score_jd 只读 config["skills"]（全包唯一写入点在 CLI 路径
        # skill_entry.py:328），导致桌宠路径下技能分恒为 0。技能分上限 30 分，
        # 占阈值 60 分的一半，缺了它即使 LLM 正常也可能全部 skip。
        # 只回写命中 COMMON_SKILL_KEYWORDS 词表的条目：英文分词兜底会把公司名/产品名
        # （Joymate、Flat、App、Mini、Cam 等）也当技能，这些词在 JD 里极易误命中而虚高评分。
        try:
            _curated = {str(k).strip().lower() for k in shared.COMMON_SKILL_KEYWORDS}
            # 2026-09-19 A3/B1：① 词表命中（高置信）优先
            _persist: list = []
            _seen: set = set()
            for s in skills or []:
                _k = str(s).strip().lower()
                if _k and _k in _curated and _k not in _seen:
                    _persist.append(str(s).strip())
                    _seen.add(_k)
            # ② 简历提取经规则清洗（中置信）补充 —— 不再整批丢弃。
            #    传入词表是为了挡住英文专名（Joymate/Flat/App/Cam 等，见 _clean_resume_skills）
            for s in self._clean_resume_skills(skills, allow_ascii=_curated):
                if s.lower() not in _seen:
                    _persist.append(s)
                    _seen.add(s.lower())
            _persist = _persist[:12]
            if _persist:
                self.cfg["skills"] = _persist
                shared.save_config(self.cfg, RUN_DIR)
                self.add_log("技能已写入配置（%d 项）：%s" % (len(_persist), "、".join(_persist)))
        except Exception as _sf_e:
            # 2026-09-21：技能写 config 失败也要留痕
            try:
                self.add_log("技能写入 config 失败：%s" % str(_sf_e)[:120])
            except Exception:
                pass
        diag = ""
        _llm_ok = False   # 2026-09-24 RESUMELLM：LLM 是否真的给出了正文（供气泡提示用）
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                diag = (llm.chat_text(
                    "你是资深 HR 与求职顾问。用 3~4 句话点评这份简历的求职竞争力：先说 2 个亮点，再说 1~2 个短板，最后给 1 条改进建议。不要客套，直接输出。",
                    "【简历内容】\n" + text[:2500], max_tokens=4000, temperature=0.4) or "").strip()
                # 调了但拿不到正文（推理预算耗尽 / 网络异常）→ 同样算「不可用」
                _llm_ok = bool(diag)
        except Exception:
            diag = ""
        self.session["resume_analyzed"] = True
        if path:
            self.session["resume_file"] = Path(path).name
        # 更新评分引擎数据源 run/resume.md（原文件备份为 resume.md.bak）
        try:
            p = RUN_DIR / "resume.md"
            if p.exists():
                bak = RUN_DIR / "resume.md.bak"
                bak.write_text(p.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            p.write_text(text, encoding="utf-8")
        except Exception as _sf_e:
            # 2026-09-21：resume.md 是评分引擎数据源，写失败会导致后续拿旧简历评分
            try:
                self.add_log("简历写入 run/resume.md 失败（后续可能仍按旧简历评分）：%s"
                              % str(_sf_e)[:120])
            except Exception:
                pass
        # LLM 主控接管（修改后需求）：起点 = 用户上传简历后，LLM 全程介入
        # （推荐关键词/方案建议/确认协助/投递决策）；方案确认与在线简历确认为用户硬门禁，
        # LLM 仅协助、无权跳过；确认期间 LLM 可辅助完成。
        self._llm_stage_enter("简历解析")
        if self._llm_agent_enabled and not self._llm_agent:
            self._llm_agent_start(text)

        def _done():
            self.set_act("sit")
            body = "✅ 简历分析完成（%s · %d 字）：\n提取技能：%s" % (
                source_name, n, "、".join(skills[:8]) if skills else "未识别到")
            if diag:
                body += "\n\nLLM 诊断：\n" + diag[:260]
            if not _llm_ok:
                # 2026-09-24 RESUMELLM：LLM 不可用**不能静默降级** ——
                # 否则新用户只收到一份「没有关键信息」的分析，完全不知道是没连上 LLM（用户实测踩过）。
                body += ("\n\n⚠️ 但我**没连上 LLM**，所以上面只有本地技能提取 ——\n"
                         "「简历诊断 / 投递关键词 / 投放方案」都做不了，岗位评分也只能走本地启发式"
                         "（分数偏低、容易全被过滤）。\n\n"
                         "请右键点我 →「📊 分析报告」→「设置 · LLM」，填好 base_url / 密钥 / 模型 并保存，\n"
                         "然后把简历**重新拖一次**，我就能给你完整分析。")
            body += "\n\n已更新 run/resume.md（当前生效简历：%s，后续评分/开始投递按这份）。" % source_name
            self.set_bubble(body)
            self.add_log("简历分析完成：%s（%d 字，%d 技能）" % (source_name, n, len(skills)))
            self.set_state("闲置")
            # 新简历就绪：强制重置旧方案 + 清除附件简历选择，重新走两轮确认
            self._plan = {"keywords": [], "exclude_pt": False, "pt_asked": False,
                          "confirmed": False, "source": "",
                          "min_score": None, "salary_low": None, "salary_high": None,
                          "exclude_add": []}
            self._plan_state = None
            try:
                (RUN_DIR / "plan.json").unlink(missing_ok=True)
            except Exception:
                pass
            # 清除已保存的附件简历选择（新简历 → 需在 BOSS 重新选择发送哪一份）
            try:
                import json as _json
                cp = RUN_DIR / "config.json"
                cfg = _json.loads(cp.read_text(encoding="utf-8"))
                cfg.pop("resume_send_name", None)
                cfg.pop("resume_pdf_path", None)
                cp.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                self.cfg = shared.load_config(RUN_DIR)
            except Exception:
                pass
            self.add_log("新简历生效：投放方案与附件简历选择已重置")
            self._ensure_plan_flow()

        self.root.after(0, _done)

    def _read_image_resume(self, path: str) -> str:
        """图片简历：优先本地 OCR；OCR 不可用再回落到视觉 LLM。

        2026-09-21：原实现**只走视觉 LLM**。多数中转站给的是纯文本模型，
        收不到 image_url，只会回一句「我没有收到图片」；上层又只看「文字是否为空」，
        于是把这句拒绝话术当成简历正文 → 提炼出假技能写进 config。
        改为本地 OCR 优先（不挑模型），并对结果做长度校验。
        """
        # ① 本地 OCR（推荐路径，不依赖模型是否支持视觉）
        #    ⚠️ 必须放**子进程**并加硬超时。2026-09-21 事故：在部分环境
        #       （解释器由 GUI 进程派生时）onnxruntime 会直接阻塞，
        #       主进程永远卡在「分析中」，用户没有任何出路。
        _OCR_IMAGE_PY = (
            "import sys\n"
            "from rapidocr_onnxruntime import RapidOCR\n"
            "from PIL import Image\n"
            "import numpy as np\n"
            "img = Image.open(sys.argv[1]).convert('RGB')\n"
            "w, h = img.size\n"
            "px = w * h\n"
            "if px > 40000000:\n"
            "    sc = (40000000.0 / px) ** 0.5\n"
            "    img = img.resize((int(w * sc), int(h * sc)), Image.LANCZOS)\n"
            "res, _ = RapidOCR()(np.array(img))\n"
            "for item in (res or []):\n"
            "    if len(item) > 1:\n"
            "        t = str(item[1]).strip()\n"
            "        if t:\n"
            "            print(t)\n"
        )
        try:
            import subprocess as _sp
            import sys as _sys
            # 注意：不能按「长边」压图（那是视觉 LLM 上传才需要的）。
            # 实测 1788x12630 长图缩到长边 2200 → 只剩 954 字且错字连篇；
            # 不压图 → 5442 字几乎无误。只在总像素过大时才等比缩小。
            _r = _sp.run([_sys.executable, "-c", _OCR_IMAGE_PY, path],
                         capture_output=True, timeout=150)
            _ocr_txt = (_r.stdout or b"").decode("utf-8", "ignore").strip()
            if len(_ocr_txt) >= 80:
                self.add_log("图片简历本地 OCR 完成：%d 字" % len(_ocr_txt))
                self._ocr_diag = ""
                return _ocr_txt
            # 记下子进程的 stderr：真机上若失败，这是唯一的线索
            _err = (_r.stderr or b"").decode("utf-8", "ignore").strip()
            self.add_log("本地 OCR 内容过少（%d 字），回落视觉 LLM%s"
                         % (len(_ocr_txt), ("；stderr：" + _err[:160]) if _err else ""))
            self._ocr_diag = "识别内容过少（%d 字）" % len(_ocr_txt)
        except Exception as _ocr_exc:
            if type(_ocr_exc).__name__ == "TimeoutExpired":
                self.add_log("本地 OCR 超时（150 秒），回落视觉 LLM")
                self._ocr_diag = "超时（150 秒）"
            else:
                self.add_log("本地 OCR 不可用：%s" % str(_ocr_exc)[:200])
                self._ocr_diag = "不可用（%s）" % str(_ocr_exc)[:80]
        # ② 回落视觉 LLM（需显式开启）
        if not bool((self.cfg.get("llm") or {}).get("allow_resume_upload", False)):
            raise RuntimeError(
                "图片简历未能识别。请安装本地 OCR（pip install rapidocr-onnxruntime），"
                "或改用 PDF / Word / 纯文本简历。")
        import base64, io, json, urllib.request
        from PIL import Image
        img = Image.open(path)
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, 1600.0 / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        b64 = base64.b64encode(buf.getvalue()).decode()
        llm_cfg = self.cfg.get("llm") or {}
        body = {
            "model": llm_cfg.get("model"),
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "这是一张简历图片。请完整、逐项提取文字内容：姓名、求职意向、联系方式、教育经历、工作经历、项目经历、技能、自我评价等，按原始顺序输出，不要遗漏，不要添加不存在的内容。如果图片不是简历，请直接说明。"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}
            ]}],
            "max_tokens": 1500, "temperature": 0.2
        }
        req = urllib.request.Request(
            # 2026-09-21：改走 shared 的统一拼接（唯一来源）。
            # 原写法只认裸域名，base_url 已带 /v1 时会拼成 .../v1/v1/... → 404。
            shared.build_llm_client(self.cfg)._chat_url(),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + llm_cfg.get("api_key", "")})
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.loads(r.read().decode())
        self.session["llm_calls"] += 1
        return (out["choices"][0]["message"]["content"] or "").strip()

    def _read_pdf_resume(self, path: str) -> str:
        """PDF 简历：文本型本地提取；扫描件（无文本层）渲染页面交给视觉 LLM。"""
        import base64, io, json, urllib.request
        from PIL import Image
        # 1) 文本型：PyMuPDF 优先，回退 pypdf
        text = ""
        try:
            import pymupdf
            with pymupdf.open(path) as doc:
                text = "\n\n".join(pg.get_text("text", sort=True) for pg in doc)
        except Exception:
            pass
        if not text or len(text.strip()) < 30:
            try:
                from pypdf import PdfReader
                text = "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
            except Exception:
                text = ""
        if text and len(text.strip()) >= 30:
            return text.strip()
        # 2) 扫描件：渲染页面 → 视觉 LLM 逐页读取
        pages_b64 = []
        try:
            import pymupdf
            with pymupdf.open(path) as doc:
                n_pages = min(doc.page_count, 6)
                for i in range(n_pages):
                    pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                    b2 = io.BytesIO()
                    img.save(b2, "JPEG", quality=85)
                    pages_b64.append(base64.b64encode(b2.getvalue()).decode())
        except Exception:
            pass
        if not pages_b64:
            return ""
        llm_cfg = self.cfg.get("llm") or {}
        if not bool(llm_cfg.get("allow_resume_upload", False)):
            raise RuntimeError("扫描型 PDF 解析需要先在 LLM 设置中显式开启 allow_resume_upload")
        # 2026-09-21：同上，统一走 shared 的拼接逻辑
        base = shared.build_llm_client(self.cfg)._chat_url()
        key = llm_cfg.get("api_key", "")
        parts = []
        for i, b64 in enumerate(pages_b64, 1):
            body = {
                "model": llm_cfg.get("model"),
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "这是简历 PDF 的第 %d/%d 页图片。请完整提取该页文字，按原始顺序输出，不要遗漏；无实质内容则输出（空）。" % (i, len(pages_b64))},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}
                ]}],
                "max_tokens": 1200, "temperature": 0.2
            }
            req = urllib.request.Request(base, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.loads(r.read().decode())
            self.session["llm_calls"] += 1
            parts.append((out["choices"][0]["message"]["content"] or "").strip())
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _extract_resume_text(path: str) -> str:
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".pdf":
            try:
                import pymupdf
                with pymupdf.open(str(p)) as doc:
                    return "\n".join(pg.get_text("text", sort=True) for pg in doc)
            except Exception:
                from pypdf import PdfReader
                r = PdfReader(str(p))
                return "\n".join((pg.extract_text() or "") for pg in r.pages)
        if ext == ".docx":
            import docx
            from docx.table import Table as _DocxTable
            from docx.text.paragraph import Paragraph as _DocxPara
            d = docx.Document(str(p))
            # 2026-09-21：必须连表格一起读 —— 中文简历常用表格排版，
            # 只取 paragraphs 会丢掉经历/教育/联系方式等最关键的内容。
            # 先按正文顺序收集候选文本（段落 / 表格单元格），再去重 —— 合并单元格
            # 会重复出现同一段文字，不去重会让简历正文里塞满重复内容。
            _cands = []
            for _child in d.element.body.iterchildren():
                _tag = _child.tag.rsplit("}", 1)[-1]
                if _tag == "p":
                    _cands.append((_DocxPara(_child, d).text or "").strip())
                elif _tag == "tbl":
                    for _row in _DocxTable(_child, d).rows:
                        for _cell in _row.cells:
                            _cands.append((_cell.text or "").strip())
            _out, _seen = [], set()
            for _s in _cands:
                if _s and _s not in _seen:
                    _seen.add(_s)
                    _out.append(_s)
            return "\n".join(_out)
        if ext == ".doc":
            # 2026-09-21：老版 Word 是二进制格式，按文本读只会得到乱码，
            # 且 errors="ignore" 会静默丢字节 → 可能把乱码当简历写进 config。
            # 明确拒绝，并告诉用户怎么办。
            raise ValueError(
                "暂不支持老版 Word（.doc）。请在 Word 中另存为 .docx，或导出 PDF 后再试。")
        if ext in (".txt", ".md"):
            # 2026-09-21：中文 Windows 记事本默认存 GBK/GB18030，写死 utf-8 会整篇乱码，
            # 而 errors="ignore" 会静默丢字节 → 可能把乱码当简历写进 config（同 .doc）。
            _raw = p.read_bytes()
            for _enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1"):
                try:
                    return _raw.decode(_enc)
                except Exception:
                    continue
            return _raw.decode("utf-8", errors="ignore")
        raise ValueError("暂不支持的文件类型：%s" % ext)

    # ---------- 2026-09-23 EXPORT：一键导出全部投递数据（含 LLM 匹配文字） ----------
    def cmd_export_delivery_data(self):
        """汇总 job_memory / outcomes / boss-demo-log / reports 为一份 JSON（附 CSV），
        保存到 run/exports/，返回路径给看板。只读、不改主流程、不影响投递。"""
        try:
            import json as _j, pathlib as _p, csv as _csv
            out_dir = RUN_DIR / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d-%H%M%S")
            mem = self._load_job_memory()
            oc = self._load_outcomes()
            demo = {}
            _dp = RUN_DIR / "boss-demo-log.json"
            if _dp.exists():
                try:
                    demo = _j.loads(_dp.read_text(encoding="utf-8")) or {}
                except Exception:
                    demo = {}
            reports = []
            try:
                for _rp in sorted(self._reports_dir().glob("report-*.json"), reverse=True):
                    try:
                        reports.append(_j.loads(_rp.read_text(encoding="utf-8")))
                    except Exception:
                        pass
            except Exception:
                pass
            payload = {
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "job_memory": mem,
                "outcomes": oc,
                "boss_demo_log": demo,
                "reports": reports,
            }
            json_path = out_dir / ("delivery_export_%s.json" % ts)
            json_path.write_text(_j.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            csv_path = out_dir / ("delivery_export_%s.csv" % ts)
            try:
                _rows = mem.get("jobs") or []
                with open(csv_path, "w", encoding="utf-8-sig", newline="") as _f:
                    _w = _csv.writer(_f)
                    _w.writerow(["岗位", "公司", "搜索词", "匹配分", "决策", "是否真投",
                                 "HR结果", "匹配理由", "匹配证据", "不匹配点", "匹配角色", "命中技能"])
                    for _r in _rows:
                        _w.writerow([
                            _r.get("job", ""), _r.get("company", ""), _r.get("kw", ""),
                            _r.get("score", ""), _r.get("decision", ""),
                            "是" if _r.get("applied") else "否",
                            _r.get("outcome", ""),
                            (_r.get("why") or "")[:240],
                            "；".join(_r.get("evidence") or []),
                            "；".join(_r.get("gaps") or []),
                            (_r.get("role") or ""),
                            "；".join(_r.get("hits") or []),
                        ])
            except Exception as _ce:
                self.add_log("导出 CSV 失败（已忽略）：%s" % str(_ce)[:80])
            self.add_log("投递数据已导出：%s" % json_path)
            return {"ok": True, "json": str(json_path), "csv": str(csv_path),
                    "jobs": len(mem.get("jobs") or []), "reports": len(reports)}
        except Exception as _e:
            self.add_log("投递数据导出失败：%s" % str(_e)[:120])
            return {"ok": False, "error": str(_e)[:200]}

    def cmd_report(self):
        self.set_act("happy")
        # 2026-09-23 REPORTFB：会话没跑过投递时，简报全是 0、很空 ——
        # 这时优先给**历史真实数据**（复用历史报告 → 否则用真实数字拼一段）。
        # 会话真跑过（scan_jobs / sim_analyze / hr_msgs 任一非 0）仍走原来的本次会话简报。
        # ⚠️ 判断里**故意不含 llm_calls**：历史报告自己会 +1，算进去就永远判不出空闲了。
        try:
            _s = self.session
            if (not _s.get("scan_jobs")) and (not _s.get("sim_analyze")) and (not _s.get("hr_msgs")):
                _hist = self._historical_summary_text()
                if _hist:
                    self.add_log("生成投递简报（历史数据）")
                    self.set_bubble(_hist)
                    self.set_state("闲置")
                    return
        except Exception:
            pass
        self.add_log("生成投递简报")
        s = self.session
        mins = max(1, int((time.time() - s["start"]) // 60))
        h, m = divmod(mins, 60)
        dur = "%d小时%d分" % (h, m) if h else "%d分钟" % m
        self.set_bubble("【投递简报 · 爬爬】\n"
                        "运行时长：%s\n"
                        "真实岗位扫描：%d 个\n"
                        "示例岗位分析：%d 轮\n"
                        "LLM 调用：%d 次\n"
                        "简历：%s\n"
                        "HR 消息处理：%d 条\n"
                        "真实投递：以看板「累计打招呼」为准" % (
                            dur, s["scan_jobs"], s["sim_analyze"], s["llm_calls"],
                            s["resume_file"] or "未导入（可点「简历匹配」导入）", s["hr_msgs"]))
        self.set_state("闲置")

    # ---------- 2026-09-22 STARTUP-DIAG：打开即诊断（只读，不影响主流程） ----------
    def _hist_data_fingerprint(self) -> str:
        """当前「跑词数据」指纹：判断自上次报告以来是否有新数据。
        组合 打招呼公司数 / job_memory 岗位数 / outcomes 数 / job_memory 最大岗位 ts。"""
        try:
            _ng = len(self._load_greeted_all())
        except Exception:
            _ng = 0
        try:
            _mem = self._load_job_memory() or {}
            _jobs = _mem.get("jobs") or []
            _nm = len(_jobs)
            _ts = ""
            for _j in _jobs:
                _t = _j.get("ts") or ""
                if _t > _ts:
                    _ts = _t
        except Exception:
            _nm, _ts = 0, ""
        try:
            _no = len(self._load_outcomes())
        except Exception:
            _no = 0
        return "%d|%d|%s|%d" % (_ng, _nm, _ts, _no)

    def _hist_report_decision(self) -> str:
        """历史报告怎么出：skip / refresh / cache。
        - skip：完全没有历史数据（与旧逻辑一致）。
        - refresh：有历史数据，且指纹与上次生成报告时不同 → 调 LLM 重出。
        - cache：有历史数据但指纹没变 → 沿用上次报告，不再调 LLM。"""
        try:
            _ng = len(self._load_greeted_all())
        except Exception:
            _ng = 0
        try:
            _nm = len((self._load_job_memory() or {}).get("jobs") or [])
        except Exception:
            _nm = 0
        try:
            _no = len(self._load_outcomes())
        except Exception:
            _no = 0
        if _ng == 0 and _nm == 0 and _no == 0:
            return "skip"
        import json as _j
        _f = RUN_DIR / "startup_diag_fp.json"
        _fp_now = self._hist_data_fingerprint()
        if not _f.exists():
            return "refresh"
        try:
            _d = _j.loads(_f.read_text(encoding="utf-8")) or {}
        except Exception:
            return "refresh"
        _fp_old = _d.get("fp")
        if not _fp_old:
            return "refresh"
        return "cache" if _fp_old == _fp_now else "refresh"

    def _load_cached_diagnosis(self) -> str:
        """读取已落盘的历史报告正文（纯只读）；无则返回空串。"""
        try:
            import json as _j
            _f = RUN_DIR / "startup_diagnosis.json"
            if _f.exists():
                _d = _j.loads(_f.read_text(encoding="utf-8")) or {}
                _dg = (_d.get("diagnosis") or "").strip()
                if _dg and _d.get("status") in ("ok", "sparse"):
                    return _dg
        except Exception:
            pass
        return ""

    def _save_hist_fingerprint(self) -> None:
        """把当前「跑词数据」指纹落盘，标记「这次报告对应的数据版本」。"""
        try:
            import json as _j
            (RUN_DIR / "startup_diag_fp.json").write_text(
                _j.dumps({"fp": self._hist_data_fingerprint(),
                          "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                         ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _startup_diagnosis(self) -> str:
        """基于历史投放数据生成完整诊断 + 方案建议（仅当 LLM 已连接）。

        纯只读 + 落盘 run/startup_diagnosis.json + 推气泡；不改 config、不投递。
        ⚠️ 不再「静默吞错」：无论跳过 / 出错都把 status+reason 落盘，
           由 cmd_startup_diagnosis 推一条可见气泡，避免「打开什么都没发生」难排查。
        """
        import json as _j
        _res = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis": "",
            "stats": {},
            "status": "ok",
            "reason": "",
        }
        try:
            llm_cfg = (self.cfg.get("llm") or {})
            if not llm_cfg.get("api_key"):
                _res["status"] = "skipped"
                _res["reason"] = "未配置 LLM api_key（在设置里填好 Key 后重启即可）"
                return ""
            # 历史记忆（RECALL1 已拼好：累计规模 + 每词真实反馈 + 指导语）
            brief = self._plan_memory_brief()
            plan = getattr(self, "_plan", None) or {}
            roles = plan.get("keywords") or self.cfg.get("target_roles") or []
            city = self.cfg.get("target_city") or plan.get("city") or "—"
            min_score = self.cfg.get("min_score", "—")
            try:
                n_mem = len(self._load_job_memory().get("jobs") or [])
            except Exception:
                n_mem = 0
            try:
                n_greet = len(self._load_greeted_all())
            except Exception:
                n_greet = 0
            try:
                n_oc = len(self._load_outcomes())
            except Exception:
                n_oc = 0
            # 没有任何历史数据就不诊断（避免空谈）
            if not brief and n_greet == 0 and n_mem == 0:
                _res["status"] = "skipped"
                _res["reason"] = "暂无历史投放数据，跳过打开诊断"
                return ""
            stats = {
                "evaluated_jobs": n_mem,
                "greeted_companies": n_greet,
                "companies_with_hr_result": n_oc,
                "keywords": list(roles),
                "target_city": city,
                "min_score": min_score,
            }
            _res["stats"] = stats
            # 2026-09-23 SPARSE：数据太薄 → 出「数据还太少」简版。
            # 判据：打招呼 < 10 家，**或**所有关键词都样本不足（每词至少投 5 家才算数）。
            # 此时**不调 LLM**（省一次调用），也不展示贝叶斯收缩后的百分比 ——
            # 收缩值在小样本下几乎等于先验（投放1回复0 会显示 40%），容易当成真实回复率误读。
            try:
                _fb = self._kw_feedback_stats() or []
            except Exception:
                _fb = []
            _has_enough = any(bool(a.get("enough")) for a in _fb)
            if n_greet < 10 or not _has_enough:
                _rows = []
                for _a in _fb[:8]:
                    _rows.append("  %s：投放 %d · 有效回复 %d · 拒绝 %d" % (
                        _a.get("kw", ""), _a.get("applied", 0),
                        _a.get("positive", 0), _a.get("rejected", 0)))
                _sparse = ("📊 数据还太少，先别急着下结论喵\n"
                           "· 已评估 %d 个岗位 · 跟 %d 家公司打过招呼 · 有 HR 结果 %d 家\n"
                           % (n_mem, n_greet, n_oc))
                if _rows:
                    _sparse += ("· 关键词样本都还不足（每个词至少投 5 家才算数）：\n"
                                + "\n".join(_rows) + "\n")
                else:
                    _sparse += "· 还没有任何关键词的真实反馈记录\n"
                _sparse += ("\n再跑几轮、每个词攒够 5 家以上，我就能给你靠谱的诊断和建议啦。"
                            "现在下结论大概率不准，所以我先不乱说～")
                _res["diagnosis"] = _sparse
                _res["sparse"] = True
                return _sparse
            prompt = (
                "你是「爬爬」，一只帮主人找工作的猫。下面是主人的【历史投递数据摘要】。\n"
                "说话要像跟朋友唠嗑（口语、不说官腔），但**结构必须清楚**，"
                "严格按下面这个模板来（段落可以少，不要多）：\n\n"
                "📌 一句话现状\n"
                "（一两句话讲完：投了多少、HR 大概什么反应）\n\n"
                "📊 数据速览\n"
                "· 评估 N 个岗位 · 打招呼 N 家 · 有 HR 结果 N 家\n"
                "· 最能打的：<关键词>　最该换的：<关键词>\n\n"
                "🔍 三个值得注意的点\n"
                "1) …\n"
                "2) …\n"
                "3) …\n\n"
                "💡 建议（分三类，每类 1~2 条，每条写清「具体怎么做」）\n"
                "· 关键词：留着 XX（因为…）；换掉 XX（因为…）\n"
                "· 打招呼：…\n"
                "· 节奏 / 优先级：…\n"
                "（某一类暂时没得说，就写「暂时没特别的」）\n\n"
                "⚠️ 样本还少，先别当结论\n"
                "（列出样本不足的关键词；没有就写「暂时没有」）\n\n"
                "排版硬要求（很重要）：\n"
                "· 用 emoji 小标题 + 短行 + 两个空格缩进分层，段落之间空一行；\n"
                "· **绝对不要**用 Markdown 星号（**）或表格竖线（|）—— 界面不解析，"
                "会直接显示成符号；要强调就靠换行和 emoji；\n"
                "· 绝对不要出现「阈值 / 字段 / 参数 / 配置」这类词，提门槛统一说「匹配度」；\n"
                "· 总长不超过 400 字；「匹配度」只是 AI 预估，重点看 HR 真实回没回。\n\n"
                "【当前方案配置】关键词=%s；目标城市=%s；匹配度门槛=%s\n\n"
                "【历史投放记忆】\n%s"
                % (("、".join(str(r) for r in roles) or "—"), city, min_score, brief)
            )
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                _res["status"] = "skipped"
                _res["reason"] = "LLM 未配置完整（base_url / model / api_key 任一缺失；填好后重启即可）"
                return ""
            self.session["llm_calls"] += 1
            # 诊断专用请求：直接构造 payload（等价 chat_text(persona=False)），
            # 目的 ① 原始响应留档（content 为空时排查「reasoning-only / 截断 / 网关空包」）
            #      ② max_tokens 放宽，给「推理型模型」先思考再作答留足预算。
            _sys = (getattr(llm, "_WORKFLOW_PREFIX", "") +
                    "你是严谨的求职策略顾问，只基于给定数据给诊断与建议，不编造数据。")
            _payload = {
                "model": llm.model,
                "messages": [{"role": "system", "content": _sys},
                             {"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 3000,
            }
            diag = ""
            _last_err = None
            # 退避重试 3 次：**异常**（429/超时）与**空响应**都重试（网关偶发空包/并发被顶）。
            # ⚠️ 只作用于「打开诊断」这一条调用，**不改** shared.chat_text 的全局重试策略。
            for _attempt in range(3):
                try:
                    _raw = llm._post_json(_payload)
                    try:
                        (RUN_DIR / "startup_diag_raw.json").write_text(
                            _j.dumps(_raw, ensure_ascii=False)[:20000], encoding="utf-8")
                    except Exception:
                        pass
                    diag = (llm._message_content(_raw) or "").strip()
                    if not diag:
                        # 兜底：少数推理模型把正文放在 reasoning_content
                        try:
                            _m = ((_raw.get("choices") or [{}])[0].get("message") or {})
                            _rc = _m.get("reasoning_content") or _m.get("reasoning") or ""
                            if isinstance(_rc, str):
                                diag = _rc.strip()
                        except Exception:
                            diag = ""
                    if diag:
                        _last_err = None
                        break
                    _last_err = None
                except Exception as _ce:
                    _last_err = _ce
                if _attempt < 2:
                    time.sleep(4 + _attempt * 8)   # 退避 4s / 12s
            if _last_err is not None:
                raise _last_err          # 交给外层 except 统一落盘 status=error + 完整 traceback
            if not diag:
                _res["status"] = "error"
                _res["reason"] = "LLM 未返回任何内容（原始响应已存 run/startup_diag_raw.json）"
                return ""
            _res["diagnosis"] = diag
            return diag
        except Exception as _e:
            _res["status"] = "error"
            _res["reason"] = "exception: %s" % _e
            # 完整堆栈落盘，便于排查（不在界面暴露）
            try:
                (RUN_DIR / "startup_diag_err.log").write_text(
                    "=== %s ===\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                          traceback.format_exc()),
                    encoding="utf-8")
            except Exception:
                pass
            return ""
        finally:
            # 无论成功 / 跳过 / 出错，都落盘一份状态，保证「打开即诊断」在界面可见（哪怕是原因）
            try:
                (RUN_DIR / "startup_diagnosis.json").write_text(
                    _j.dumps(_res, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def cmd_startup_diagnosis(self):
        """生成并推送「历史投递报告」（用户唤出投递方案时触发）。"""
        try:
            diag = self._startup_diagnosis()
            if diag:
                # 2026-09-23：**不再 set_act** —— 夜间猫应保持睡觉，报告只走对话气泡。
                self.set_bubble(diag)
                self.add_log("历史投递报告已生成（%d 字）" % len(diag))
                return
            # 没产出正文：读落盘状态，给用户一条可见的原因（不再静默）
            try:
                import json as _j
                _f = RUN_DIR / "startup_diagnosis.json"
                _d = (_j.loads(_f.read_text(encoding="utf-8")) if _f.exists() else {})
                _st = _d.get("status", "")
                _rs = _d.get("reason", "")
                if _st == "skipped":
                    self.set_bubble("📋 历史报告跳过：%s" % _rs)
                elif _st == "error":
                    self.set_bubble("⚠️ 历史报告生成失败：%s" % _rs)
                else:
                    self.set_bubble("📋 历史报告：暂无可分析的历史数据")
            except Exception:
                pass
        except Exception:
            pass

    def _historical_summary_text(self) -> str:
        """历史汇总文案（**纯只读**）：会话没跑过投递时，简报不该全是 0。

        优先复用刚生成的历史投递报告；没有就用 job_memory / greeted_all /
        outcomes / kw_feedback 的真实数字拼一段。都没有则返回空串（交给原简报）。
        """
        try:
            import json as _j
            _f = RUN_DIR / "startup_diagnosis.json"
            if _f.exists():
                _d = _j.loads(_f.read_text(encoding="utf-8")) or {}
                _dg = (_d.get("diagnosis") or "").strip()
                if _dg and _d.get("status") == "ok":
                    return "📋 历史投递报告（%s）\n\n%s" % (_d.get("ts") or "", _dg)
        except Exception:
            pass
        try:
            n_mem = len(self._load_job_memory().get("jobs") or [])
        except Exception:
            n_mem = 0
        try:
            n_greet = len(self._load_greeted_all())
        except Exception:
            n_greet = 0
        try:
            n_oc = len(self._load_outcomes())
        except Exception:
            n_oc = 0
        if not (n_mem or n_greet or n_oc):
            return ""
        lines = ["📊 累计投递情况（历史真实数据）",
                 "· 评估过 %d 个岗位" % n_mem,
                 "· 已打招呼 %d 家公司" % n_greet,
                 "· 有 HR 结果 %d 家" % n_oc]
        try:
            fb = self._kw_feedback_stats() or []
            if fb:
                fb = sorted(fb, key=lambda a: (not a.get("enough"), -a["rate_shrunk"]))
                lines.append("· 关键词真实反馈（HR 真的回没回）：")
                for a in fb[:5]:
                    lines.append("  %s：投放 %d · 有效回复 %d · 拒绝 %d → 回复率 %.0f%%%s" % (
                        a["kw"], a["applied"], a["positive"], a["rejected"],
                        a["rate_shrunk"] * 100, "" if a["enough"] else "（样本不足）"))
        except Exception:
            pass
        lines.append("（这是累计数据；本次会话还没跑投递，所以没有「本次」进度。）")
        return "\n".join(lines)
    
    def cmd_chat(self):
        self.set_state("沟通中")
        self.set_act("wave")
        try:
            from agent.shared import is_cdp_port_ready, connect_browser
            from boss import boss_chat
        except Exception as exc:
            self._sim_hr_msg("模块不可用：%s" % exc)
            return
        if not is_cdp_port_ready(9222):
            self._sim_hr_msg("9222 投递浏览器不在线")
            return
        self.set_bubble("正在读取 BOSS 聊天页的 HR 消息（只读）…")

        def _work():
            try:
                browser = connect_browser(9222)
                tab = browser.latest_tab
                msgs = boss_chat.read_friend_messages_classified(tab, limit=6)
                real = [m for m in msgs if (m.get("content") or "").strip()]
                if not real:
                    self.root.after(0, lambda: (self.set_bubble("聊天页没读到 HR 消息（可能需要先点进某个会话）。已给模拟消息。"),
                                                self._sim_hr_msg("无真实消息")))
                    return
                last = real[-1]
                content = (last.get("content") or "")[:200]
                position = last.get("company") or last.get("job") or "该岗位"
                self.session["hr_msgs"] += 1
                draft = ""
                try:
                    llm = shared.build_llm_client(self.cfg)
                    resume_for_llm = self._current_resume() if bool((self.cfg.get("llm") or {}).get("allow_resume_upload", False)) else ""
                    ok, draft = boss_chat.generate_conversation_reply(
                        llm, resume_for_llm, position, content)
                except Exception:
                    ok, draft = False, ""

                def _done():
                    if draft:
                        self.set_bubble("【草稿 · 未发送】\n对方（%s）：%s\n\n回复草稿：%s\n\n（需你确认后才会发送）" % (
                            position, content, draft[:180]))
                    else:
                        self.set_bubble("【草稿 · 只读】对方（%s）：%s\n\n（自动草稿未生成，会转人工回复）" % (
                            position, content))
                    self.set_state("闲置")

                self.root.after(0, _done)
            except Exception as exc:
                self.root.after(0, lambda e=exc: (self.set_bubble("读取聊天失败：%s" % e),
                                                  self._sim_hr_msg("读取失败"), self.set_state("闲置")))

        threading.Thread(target=_work, daemon=True).start()

    def _current_resume(self) -> str:
        try:
            p = RUN_DIR / "resume.md"
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            return ""

    def _push_hr_alert(self, act: dict) -> None:
        """HR 新消息提醒（基类默认实现：气泡 + 日志）。

        2026-09-17 补：原先本方法只在 pet_bridge.py 的 HeadlessPet 中定义，
        而 cmd_test_run 的 HR 监听会调用 self._push_hr_alert(...)。
        结果：Electron/无头路径正常（HeadlessPet 覆写），但**独立 Tk 运行**
        （`python main.py` / run_demo.bat）一旦收到 HR chat_alert 就抛
        AttributeError: 'PetApp' object has no attribute '_push_hr_alert'。
        这里补一个基类实现兜底；HeadlessPet 仍覆写为推送看板「待处理」列表。
        """
        try:
            hr = act.get("hr_name") or "HR"
            company = act.get("company") or act.get("conversation") or "该岗位"
            msg = (act.get("message") or act.get("hint") or "")[:120]
            self.add_log("【HR消息】%s · %s：%s" % (hr, company, msg))
            self.set_bubble("💬 HR 来消息（%s · %s）：\n%s\n\n喵没有自动回复，需要你查看。"
                            % (hr, company, msg))
        except Exception:
            pass

    def _sim_hr_msg(self, why: str):
        try:
            self.root.bell()
        except Exception:
            pass
        self.set_bubble("「叮」模拟 HR：看到您投递的海外直播运营经理岗位，方便约个时间聊聊吗？\n（%s；会监听真实聊天并生成回复）" % why)
        self.add_log("模拟事件：HR 来消息（%s）" % why)
        self.session["hr_msgs"] += 1
        self.root.after(2500, lambda: self.set_state("闲置"))

    # ---------- 求职配置（阶段2：展示当前求职配置） ----------
    def cmd_config(self):
        self.set_act("think")
        c = self.cfg
        roles = c.get("target_roles") or []
        ex = c.get("title_exclude_keywords") or []
        self.set_bubble("【求职配置 · 当前】\n"
                        "目标岗位：%d 个关键词（%s 等）\n"
                        "岗位匹配值：%s 分\n"
                        "薪资范围：%sK - %sK\n"
                        "排除词：%d 个（%s 等）\n"
                        "LLM：%s / %s\n\n"
                        "可在这里多轮迭代调整；本轮投递沿用当前配置。" % (
                            len(roles), "、".join(roles[:20]),
                            c.get("min_score"),
                            c.get("min_salary_low_k", "?"), c.get("min_salary_high_k", "?"),
                            len(ex), "、".join(ex[:3]),
                            (c.get("llm") or {}).get("base_url", "?"),
                            (c.get("llm") or {}).get("model", "?")))
        self.add_log("查看求职配置")
        self.set_state("闲置")

    def _launch_browser(self) -> bool:
        """拉起 9222 投递浏览器（带 BOSS 登录态目录），等待端口就绪（最多 40 秒）。"""
        import subprocess
        from agent.shared import is_cdp_port_ready
        try:
            subprocess.Popen([CHROME_PATH,
                              "--remote-debugging-port=9222",
                              "--user-data-dir=" + CHROME_USER_DIR,
                              "--no-first-run", "--no-default-browser-check",
                              "--restore-last-session",
                              ])
        except Exception as exc:
            self.add_log("拉起浏览器失败：%s" % exc)
            return False
        for _ in range(20):
            time.sleep(2)
            if is_cdp_port_ready(9222):
                return True
        return False

    def _set_browser_visibility(self, visible: bool) -> None:
        """后台模式只隐藏窗口，不使用 headless；人工门禁时必须恢复可见。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            targets = []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def _visit(hwnd, _):
                size = user32.GetWindowTextLengthW(hwnd)
                if size and user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(size + 1)
                    user32.GetWindowTextW(hwnd, buf, size + 1)
                    title = buf.value.lower()
                    if "boss直聘" in title or "zhipin" in title:
                        targets.append(hwnd)
                return True

            user32.EnumWindows(callback_type(_visit), 0)
            SW_RESTORE = 9
            SW_MINIMIZE = 6
            for hwnd in targets:
                user32.ShowWindow(hwnd, SW_RESTORE if visible else SW_MINIMIZE)
                if visible:
                    user32.SetForegroundWindow(hwnd)
            if not targets:
                self.add_log("未找到 BOSS Chrome 窗口，未调整窗口状态")
        except Exception as exc:
            self.add_log("浏览器窗口状态调整失败：%s" % exc)

    def _set_background_mode(self, enabled: bool) -> None:
        self._background_mode = bool(enabled)
        try:
            cfg = dict(self.cfg)
            cfg["background_mode"] = self._background_mode
            shared.save_config(cfg, RUN_DIR)
            self.cfg = cfg
        except Exception as exc:
            self.add_log("后台模式配置保存失败：%s" % exc)
        if enabled:
            self.set_bubble("✅ 后台最小化模式已开启：Chrome 会最小化运行；登录、验证码、风控和人工确认时会自动恢复窗口。")
            self.add_log("后台最小化模式：开启")
            if self.state in ("投递中", "沟通中") and not self._login_waiting:
                self._set_browser_visibility(False)
        else:
            self._set_browser_visibility(True)
            self.set_bubble("后台最小化模式已关闭，Chrome 恢复可见。")
            self.add_log("后台最小化模式：关闭")

    # ---------- 防待机 + 防熄屏（投递期间电脑不休眠、屏幕不熄） ----------
    def _prevent_sleep(self, enable: bool) -> None:
        """SetThreadExecutionState：投递期间阻止系统待机/睡眠及屏幕关闭。
        enable=True 在投递进程存活期间持续生效；enable=False 恢复系统默认。"""
        try:
            import ctypes
            from ctypes import wintypes
            _ES_CONTINUOUS = 0x80000000        # 持续生效，直到清除
            _ES_SYSTEM_REQUIRED = 0x00000001   # 阻止系统睡眠/待机
            _ES_DISPLAY_REQUIRED = 0x00000002  # 阻止屏幕关闭
            fn = ctypes.windll.kernel32.SetThreadExecutionState
            fn.argtypes = [wintypes.DWORD]
            fn.restype = wintypes.DWORD
            if enable:
                fn(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
                self.add_log("防待机已启用：投递期间电脑不休眠、屏幕不熄")
            else:
                fn(_ES_CONTINUOUS)
        except Exception:
            pass

    # ---------- 请求节奏 ----------
    def _pace(self, name: str) -> float:
        lo, hi = PACING[name]
        # 偏态延迟：截断指数分布 + 非线性映射（间隔策略与 skill 的 pace_sleep 一致）
        # 多数停顿落在区间低中段（间隔短），小概率出现接近上限的长停顿（偶发长间隔）
        raw = random.expovariate(1.4)
        t01 = min(raw, 1.2) / 1.2
        t01 = t01 ** 0.85
        t = lo + t01 * (hi - lo)
        if name == "long_rest" and not self._real_pace:
            t = t / LONG_REST_DEMO_SCALE
        return t

    # ---------- 守护统一开关：投递启→守护启，投递停→守护停 ----------
    def _guard_tasks(self, action: str) -> None:
        """[已停用] 系统计划任务开关。

        2026-09-17 移除：原实现用 `schtasks /Change` 动态启停
        JobHunterWatchdog5min / JobHunterLoginRestore 两个系统计划任务。
        该机制是 9/8、9/9 两次封号的根因路径——主程序被强杀或崩溃时
        disable 分支不会执行，计划任务会保持"已启用"状态，导致孤儿
        watchdog 反复唤醒并探测平台。

        现改为纯 no-op：不再创建、启用或禁用任何系统计划任务。
        调用点（共 9 处）保留以避免大范围改动，但不再产生副作用。

        请手工确认以下计划任务已从系统中删除：
            schtasks /Delete /TN "JobHunterWatchdog5min" /F
            schtasks /Delete /TN "JobHunterLoginRestore" /F
        """
        return

    def _emit_pet_state(self, state: str) -> None:
        """给桌宠外壳发素材状态：往 stdout 打一行 JSON，由 main.js 的
        forwardToWindows 自动转发给 renderer（所以 main.js 无需改动）。"""
        # 2026-09-20 CAT3：同时也写日志，方便在 demo.log 里看到调用
        try:
            self.add_log("🐾 桌宠切素材：%s" % (str(state or "")))
        except Exception:
            pass
        try:
            _payload = {"type": "petState", "state": str(state or "")}
            # 2026-09-23 修复：原先裸 print 与并发 emit 在共享 stdout 上字节交错 →
            # JSON 损坏被 main.js 丢弃 → 猫不切工作态素材（09:42 那次只发 log 没发 petState）。
            # 改走 pet_bridge.emit（带锁、与日志同一出口）；非桥接上下文回退裸 print。
            try:
                from pet_bridge import emit as _emit_pet
                _emit_pet(_payload)
            except Exception:
                import json as _json_pet
                print(_json_pet.dumps(_payload, ensure_ascii=False))
                sys.stdout.flush()
        except Exception as _e:
            try: self.add_log("⚠️ 桌宠切素材 stdout 失败：%s" % str(_e)[:120])
            except Exception: pass

    def _emit_progress(self, rec: dict, collected=None, in_collect=False) -> None:
        """投递进度 → 看板。往 stdout 打一行 JSON，由 main.js 转发（无需改 main.js）。

        ⚠️ 2026-09-21 修正（用户报「进度条没动」）：
        每个关键词其实是**两阶段**：① 收集（最多 35 个，耗时最长）② 评分/投递。
        原本只在 `rec["scan"]`（阶段②）发事件 → **阶段① 全程不发，条子看着纹丝不动**；
        且 scan 只统计"评分过"的岗位（实测 ~23），分母却是 9×35=315 → 百分比永远走不满。
        现在：收集阶段也发，百分比 = (已完成关键词×35 + 当前已收集) / (总关键词×35)。
        """
        try:
            import json as _jp
            rec = rec or {}
            kws = (getattr(self, "_plan", None) or {}).get("keywords") or []
            kw_total = max(1, len(kws))
            per = 35
            total = kw_total * per
            if collected is not None:
                self._pg_collected = int(collected)
            cur = int(getattr(self, "_pg_collected", 0) or 0)
            # ⚠️ rec["kw"] 的递增时机**两阶段不同**，别写死成 kw-1：
            #   收集阶段（_fetch_boss_jobs 内，产物 L3071）：kw 还没为当前词 +1
            #     → 已完成数 = kw
            #   评分/投递阶段（产物 L2402 之后才 +1）：kw 已含当前词
            #     → 已完成数 = kw-1
            _kw = int(rec.get("kw", 0) or 0)
            done_before = _kw if in_collect else max(0, _kw - 1)
            pct = int(min(100, (done_before * per + cur) * 100.0 / max(1, total)))
            scanned = int(rec.get("scan", 0) or 0)
            applied = int(rec.get("greet", 0) or 0)
            skipped = max(0, scanned - applied)   # 扫了但没投出 = 跳过
            print(_jp.dumps({"type": "progress", "kw_total": kw_total,
                             "kw_done": done_before, "scanned": scanned,
                             "skipped": skipped, "applied": applied, "collected": cur,
                             "total": total, "pct": pct}, ensure_ascii=False))
            sys.stdout.flush()
        except Exception:
            pass

    def _set_applying(self, flag: bool) -> None:
        # 2026-09-20 CAT：投递结束（完成或用户停止）→ 切「完成工作」素材，播完回闲置
        try:
            _was_applying = (RUN_DIR / "pet-applying.flag").exists()
        except Exception:
            _was_applying = False
        if _was_applying and not flag:
            self._emit_pet_state("work_done")
        """投递运行状态标记：run/pet-applying.flag 存在=喵正在投递（守护可拉 Chrome）；
        不存在=喵空闲（守护不得自动拉起 Chrome）。"""
        try:
            p = RUN_DIR / "pet-applying.flag"
            if flag:
                p.write_text("1", encoding="utf-8")
            else:
                p.unlink(missing_ok=True)
        except Exception:
            pass

    # ---------- 轮次状态机（三态持久化，交接补充：不依赖单标志文件） ----------
    def _round_state(self) -> str:
        """启动时三态判定：MANUAL_STOPPED（手动停止→清基线开新轮）/
        CRASHED（上次 RUNNING 未正常收尾→沿用基线续跑）/ NEW（无记录或正常完成→全新一轮）。
        读不到/损坏按 NEW 处理（安全侧：宁可清基线，不误沿用导致继续监听旧轮 HR）。"""
        import json as _json
        try:
            p = RUN_DIR / "round-state.json"
            if not p.exists():
                return "NEW"
            d = _json.loads(p.read_text(encoding="utf-8"))
            st = d.get("state")
            if st == "MANUAL_STOPPED":
                return "MANUAL_STOPPED"
            if st in ("RUNNING", "CRASHED"):
                return "CRASHED"  # RUNNING=上次未正常收尾（异常/崩溃/被杀）
            return "NEW"  # COMPLETED / 未知
        except Exception:
            return "NEW"

    def _round_state_write(self, state: str) -> None:
        import json as _json
        try:
            p = RUN_DIR / "round-state.json"
            p.write_text(_json.dumps(
                {"state": state, "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _clear_round_baseline(self) -> None:
        """全新一轮：清空打招呼白名单基线，重新计数。"""
        try:
            import json as _j
            p = RUN_DIR / "boss-demo-log.json"
            d = {}
            if p.exists():
                d = _j.loads(p.read_text(encoding="utf-8"))
            d.setdefault("records", {})["applied"] = []
            p.write_text(_j.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- 30 分钟稳定性自检（交接补充：逐项输出日志） ----------
    def _stability_report(self) -> None:
        self._llm_stage_enter("稳定性自检")
        try:
            from agent.shared import is_cdp_port_ready, connect_browser
        except Exception:
            connect_browser = None
        lines = ["【稳定性自检 · %s】" % time.strftime("%H:%M:%S")]
        # ① 去重拦截是否生效
        lines.append("① 去重拦截：命中 %d 次（两周去重生效，拦截重复评估）" % self._st["dedup_hits"])
        # ② 监听循环是否存活
        mon_alive = self._monitor_job is not None
        # 2026-09-19 O：监听有**两条腿**，原来只报腿 A，导致明明在听却显示「未开启」。
        #   腿 A：独立的 90 秒轮询定时器（用户手动开关，默认关）
        #   腿 B：投递轮次内的监听（每个关键词扫完自动跑一轮）—— 本自检就发生在投递中
        lines.append("② 消息监听：%s" % (
            "✅ 90 秒定时器运行中" if mon_alive
            else "✅ 随投递监听（关键词之间自动跑一轮；90 秒定时器未开）"))
        # ③ 登录态是否保持
        login_ok = "⚠️ 未检测（浏览器离线）"
        try:
            if connect_browser is not None and is_cdp_port_ready(9222):
                login_ok = ("✅ 保持" if self._quick_login_check(connect_browser(9222).latest_tab)
                            else "❌ 已失效")
        except Exception:
            login_ok = "⚠️ 检测失败"
        lines.append("③ BOSS 登录态：%s" % login_ok)
        # ④ 掉线/重试次数（含 429/断线自动恢复）
        lines.append("④ 掉线/重试次数：%d（断线自动恢复次数，过高说明网络/风控不稳）" % self._st["retry_count"])
        # ⑤ LLM 配额是否耗尽
        quota = (RUN_DIR / "llm-quota-state.json").exists()
        lines.append("⑤ LLM 配额：%s" % ("❌ 已耗尽（llm-quota-state.json 存在，请更换配置）" if quota else "✅ 未耗尽"))
        # ⑥ 屏蔽词预过滤是否有误杀（命中次数 + 当前排除词，供人工判断误杀）
        kws = (self.cfg.get("title_exclude_keywords") or [])[:8]
        lines.append("⑥ 屏蔽词预过滤：命中 %d 次；排除词：%s" % (
            self._st["block_hits"], "、".join(kws) if kws else "无"))
        for ln in lines:
            self.add_log(ln)

    # ---------- 环节简报（新需求：喵在每个环节自动给 LLM 生成提示词，协助 LLM 快速判断现状） ----------
    def _llm_stage_enter(self, stage: str) -> None:
        """记录环节切换（LLM 可据此追溯流程走到哪一步）。"""
        self._llm_stage = stage
        self._llm_ctx_log.append(stage)
        if len(self._llm_ctx_log) > 20:
            self._llm_ctx_log = self._llm_ctx_log[-20:]

    def _llm_stage_brief(self, stage: str, extra: dict = None) -> str:
        """喵自动为 LLM 生成「环节简报」：当前环节名 + 现状关键数据 + 最近决策轨迹 + 环节历史。
        每次 LLM 被调用时自动作为上下文前缀注入，LLM 无需自行探查即可快速判断现状。"""
        self._llm_stage_enter(stage)
        lines = ["【喵·环节简报】环节=%s，时间=%s" % (stage, time.strftime("%H:%M:%S"))]
        if extra:
            for k, v in extra.items():
                lines.append("%s=%s" % (k, v))
        if self._llm_agent_ctx.get("decisions"):
            last = self._llm_agent_ctx["decisions"][-3:]
            lines.append("最近LLM决策=" + "；".join(
                "%s:%s" % (d.get("scene"), d.get("action")) for d in last))
        if self._llm_ctx_log:
            lines.append("环节轨迹=" + " → ".join(self._llm_ctx_log[-6:]))
        return "\n".join(lines)

    # ---------- LLM 主控接管（修改后需求：上传简历即接管，全程协助；两个确认为用户硬门禁） ----------
    def _llm_agent_start(self, resume_text: str = "") -> None:
        """用户上传简历后启动 LLM 接管。接管范围：推荐关键词/方案建议/确认协助/投递决策（换词/岗位匹配值/停止）。
        硬约束：方案确认与在线简历确认是【用户硬门禁】——LLM 仅协助、无权跳过；
        确认期间 LLM 可辅助（方案生成/修改、简历选择建议）。"""
        self._llm_agent = True
        self._llm_agent_pending = False
        self._llm_agent_ctx = {"kw_stats": [], "decisions": [], "resume": resume_text[:800]}
        self._llm_stage_enter("LLM接管启动")
        self.add_log("LLM 主控接管已启动（简历上传后全程协助：推荐关键词/方案/确认协助/投递决策；"
                     "方案确认与在线简历确认仍为用户硬门禁，LLM 无权跳过）")

    def _llm_agent_decide(self, scene: str, payload: dict) -> dict:
        """LLM 主控决策（与岗位分析同一 aiaaa.cc API）。返回决策 dict：
        {"action": "continue"|"switch"|"adjust"|"stop", "min_score": int?, "reason": str}
        任何失败/未配置/超时 → 默认 continue（安全侧：不阻塞、不误停投递）。"""
        if not self._llm_agent:
            return {"action": "continue", "reason": "LLM 接管未开启"}
        try:
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                self.add_log("LLM 接管：LLM 未配置，本次决策按 continue（不阻塞投递）")
                return {"action": "continue", "reason": "LLM 未配置"}
            self.session["llm_calls"] += 1
            rows = "\n".join(
                "· %s：扫描 %d · 达标 %d · 平均 %.1f 分 · 最高 %d 分" % (
                    s["kw"], s["scanned"], s["applied"], s["avg"], s["top"])
                for s in self._llm_agent_ctx["kw_stats"])
            threshold = self.cfg.get("min_score", 70)
            prompt = (
                self._llm_stage_brief("投递决策·换词", {
                    "当前关键词": payload.get("kw"), "扫描数": payload.get("scanned"),
                    "达标数": payload.get("applied"), "平均分": payload.get("avg"),
                    "最高分": payload.get("top"), "岗位匹配值": self.cfg.get("min_score", 70)})
                + "\n\n你是求职投递主控 Agent。当前场景：%s。岗位匹配值 %s 分（满分 100）。\n"
                "本轮关键词表现：\n%s\n\n"
                "当前关键词「%s」：扫描 %d · 达标 %d · 平均 %.1f 分 · 最高 %d 分。\n\n"
                "请决策下一步：\n"
                "- continue：继续用当前关键词/策略投递；\n"
                "- switch：当前词无效，切换到下一个关键词（通常平均分明显低于岗位匹配值或达标 0）；\n"
                "- adjust：整体岗位匹配值不合适，返回新的 min_score（50~85 整数）；\n"
                "- stop：本轮应提前停止（如质量全面不达标或风控风险）。\n"
                "只输出 JSON：{\"action\": \"continue|switch|adjust|stop\", "
                "\"min_score\": 可选整数, \"reason\": \"一句话理由\"}" % (
                    scene, threshold, rows or "（暂无）",
                    payload.get("kw", "?"), payload.get("scanned", 0),
                    payload.get("applied", 0), payload.get("avg", 0), payload.get("top", 0)))
            out = (llm.chat_text(prompt, "当前方案关键词：" + "、".join(
                (self._plan.get("keywords") or self.cfg.get("target_roles") or [])[:20]),
                max_tokens=300, temperature=0.2) or "").strip()
            out = out.strip("`").strip()
            if out.startswith("json"):
                out = out[4:].strip()
            import json as _json
            start, end = out.find("{"), out.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM 输出非 JSON")
            obj = _json.loads(out[start:end + 1])
            action = str(obj.get("action") or "continue").strip().lower()
            if action not in ("continue", "switch", "adjust", "stop"):
                action = "continue"
            dec = {
                "action": action,
                "reason": str(obj.get("reason") or "").strip(),
                "scene": scene,
            }
            try:
                dec["min_score"] = int(obj["min_score"]) if "min_score" in obj else None
            except Exception:
                dec["min_score"] = None
            self._llm_agent_ctx["decisions"].append(dec)
            self.add_log("LLM 主控决策 [%s]：%s（%s）" % (scene, action, dec["reason"]))
            return dec
        except Exception as exc:
            self.add_log("LLM 主控决策异常（按 continue 处理）：%s" % exc)
            return {"action": "continue", "reason": "决策异常"}

    # ---------- 门禁B：登录等待 · LLM 判断用户「已登录」意图 ----------
    def _llm_judge_login_msg(self, text: str) -> bool:
        """LLM 判断用户回复是否表达「BOSS 已登录完成」。失败/未配置 → 强关键词兜底
        （先排除求助类否定词，避免「不会登录/怎么登录」误判）。"""
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                out = (llm.chat_text(
                    self._llm_stage_brief("登录确认意图", {"用户回复": text[:120]})
                    + "\n\n用户正在等待 BOSS 登录确认。判断这条用户消息是否表达「我已经登录完成了」的意图"
                      "（如：我登录了 / 登好了 / 好了 / OK / 可以了 / 登进去了 / 已经扫码了 / 登录成功）。"
                      "求助、疑问、闲聊、其他内容都算否。只输出 true 或 false。",
                    "", max_tokens=200, temperature=0.0) or "").strip().lower()
                return "true" in out
        except Exception:
            pass
        t = (text or "").lower()
        if any(k in t for k in ("不会", "怎么", "如何", "教", "打不开", "失败", "没反应")):
            return False
        return any(k in t for k in (
            "我登录了", "登录好了", "登好了", "登完了", "登录成功", "登录完成",
            "好了", "ok", "可以了", "进去了", "扫完", "扫好了", "已经扫码", "登录上了"))

    def _wait_login_confirm(self, tab, steps: str) -> bool:
        """门禁B（修改后）：未登录 → 打开登录页 → 用户登录后对话框说一声 →
        LLM 判断 → 重检登录。返回 True=登录确认通过；False=用户停止/取消。"""
        self._login_waiting = True
        self._login_confirmed = False
        self.root.after(0, lambda: self.set_state("分析中"))  # 未等登录时按钮显示"开始投递"（=我登录好了继续）
        # 登录需要人工操作，后台模式也必须显示 Chrome。
        self._set_browser_visibility(True)
        try:
            tab.get("https://login.zhipin.com/?ka=header-login")
        except Exception:
            pass
        self.root.after(0, lambda: self.set_bubble(
            "🔐 需要先登录 BOSS：已在投递浏览器为你打开登录页，请扫码/密码登录。\n"
            "登录好后，在对话框跟我说「我登录了 / 好了 / OK」即可——喵会请 LLM 判断并重新检查登录。\n"
            "（随时说「停止」可取消）"))
        self.add_log("门禁B：等待用户登录，对话框回复后 LLM 判断并重检")
        while self._login_waiting and not self._stop_requested:
            if self._paused:
                while self._paused and not self._stop_requested:
                    time.sleep(0.5)
            time.sleep(0.5)
        self._login_waiting = False
        if self._stop_requested:
            return False
        return bool(self._login_confirmed)

    def _handle_login_msg(self, text: str) -> None:
        """对话框在登录等待中：LLM 判断 → 是则重检登录，否则回应。"""
        if self._login_checking:
            return
        self._login_checking = True
        try:
            judged = self._llm_judge_login_msg(text)
        except Exception as exc:
            judged = False
            self.add_log("登录意图判断异常：%s" % exc)
        if judged:
            ok = False
            try:
                from agent.shared import connect_browser
                tab = connect_browser(9222).latest_tab
                ok = self._boss_login_check(tab)
            except Exception:
                ok = False
            if ok:
                self._login_confirmed = True
                self._login_waiting = False
                self.root.after(0, lambda: (self.set_bubble("✅ 登录确认通过，继续投递流程…"),
                                            self.add_log("LLM 判断「已登录」，登录重检通过")))
                if self._background_mode:
                    self.root.after(500, lambda: self._set_browser_visibility(False))
            else:
                self.root.after(0, lambda: self.set_bubble(
                    "我检查了一下，BOSS 好像还没登录成功？\n请确认已在投递浏览器窗口完成扫码/密码登录，登录好后再跟我说一声～"))
        else:
            self.root.after(0, lambda t=text: self.set_bubble(
                "收到～等你登录完成后跟我说「我登录了 / 好了」就行。（你刚才说：%s）" % t))
        self._login_checking = False

    # ---------- 新增情况2：BOSS 无附件简历 → LLM 引导上传 → 用户回复传好 → 重检 ----------
    def _llm_judge_upload_msg(self, text: str) -> str:
        """LLM 判断用户回复意图：done=已上传完成 / help=询问怎么上传 / other=其他。"""
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                out = (llm.chat_text(
                    self._llm_stage_brief("上传附件简历意图", {"用户回复": text[:120]})
                    + "\n\n用户正在给 BOSS 上传附件简历。判断意图：\n"
                      "- done：表达「已经上传完了」（如：传好了/上传完了/传完了/弄好了/好了/OK）；\n"
                      "- help：询问怎么上传/不会上传（如：怎么传/怎么上传/不会/教我/步骤）；\n"
                      "- other：其他。\n只输出 done 或 help 或 other。",
                    "", max_tokens=200, temperature=0.0) or "").strip().lower()
                if "done" in out:
                    return "done"
                if "help" in out:
                    return "help"
                return "other"
        except Exception:
            pass
        t = (text or "").lower()
        if any(k in t for k in ("怎么", "如何", "不会", "教", "步骤", "操作")):
            return "help"
        if any(k in t for k in ("传好了", "传完了", "上传完", "上传好了", "弄好了", "好了", "ok", "完成", "传上去了")):
            return "done"
        return "other"

    def _llm_guide_resume_upload(self, ask: str = "") -> None:
        """LLM 生成「上传附件简历」引导提示词（含内置攻略），失败用攻略兜底。"""
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                guide = (llm.chat_text(
                    self._llm_stage_brief("上传附件简历引导", {"用户问题": (ask or "")[:120]})
                    + "\n\n你是求职助手。用户需要在 BOSS 直聘网页版上传附件简历（PDF，最多 3 份），"
                      "官方路径如下（已核实）：\n" + self._upload_guide_static
                    + "\n\n请用清晰分步的方式教用户：先给官网路径（www.zhipin.com → 右上角头像「我的简历」"
                      "→ 右侧「附件简历/附件管理」→「上传简历/作品集」），再提示「聊一聊」里发简历→上传这条备用路。"
                      "语气友好，控制在 200 字内；用户问题里有具体困惑先针对性解答。",
                    # 2026-09-24 MAXTOK-GUIDE：同上；抬到 2000 后 ask（针对性解答）才走得到
                    "", max_tokens=2000, temperature=0.3) or "").strip()
                if guide:
                    self.root.after(0, lambda g=guide: self.set_bubble("📤 " + g))
                    return
        except Exception:
            pass
        self.root.after(0, lambda: self.set_bubble("📤 " + self._upload_guide_static))

    def _wait_resume_upload(self, tab) -> bool:
        """新增情况2：账号无附件简历 → LLM 引导上传 → 用户回复传好 → 重检简历。
        返回 True=检测到附件简历（落入门禁C 选择）；False=用户停止/仍未检测到。"""
        self._resume_upload_waiting = True
        self._resume_upload_confirmed = False
        self.root.after(0, lambda: self.set_bubble(
            "❌ BOSS 账号还没有附件简历：投递前必须确认要发送的附件简历，需要先上传。\n"
            "上传好后在对话框跟我说「传好了 / 上传完了」；不知道怎么传，直接问我「怎么上传」，我会教你。\n"
            "（随时说「停止」可取消）"))
        self._llm_guide_resume_upload()
        while self._resume_upload_waiting and not self._stop_requested:
            if self._paused:
                while self._paused and not self._stop_requested:
                    time.sleep(0.5)
            time.sleep(0.5)
        self._resume_upload_waiting = False
        if self._stop_requested:
            return False
        # 用户说传好了 → 重检附件简历
        again = self._list_boss_resumes(tab)
        if again == "blocked":
            self.root.after(0, lambda: self.set_bubble(
                "❌ 重新检测时遇到 BOSS 访问受限（403 风控），请稍后再试。"))
            return False
        if not again:
            self.root.after(0, lambda: self.set_bubble(
                "我重新检查了，还是没看到附件简历？\n请确认已在 BOSS「我的简历→附件简历」上传完成（可再问我「怎么上传」），传好后再跟我说一声～"))
            return False
        return True

    def _handle_upload_msg(self, text: str) -> None:
        """对话框在上传等待中：LLM 判断意图 → 完成则重检 / 求助则教 / 其他回应。"""
        intent = self._llm_judge_upload_msg(text)
        if intent == "done":
            self._resume_upload_confirmed = True
            self._resume_upload_waiting = False
            self.root.after(0, lambda: self.set_bubble("收到，正在重新检测你的附件简历…"))
        elif intent == "help":
            self._llm_guide_resume_upload(text)
        else:
            self.root.after(0, lambda t=text: self.set_bubble(
                "收到～上传完成后跟我说「传好了」；不会传可以问我「怎么上传」。（你刚才说：%s）" % t))

    # ---------- 新增情况1：未检测到 Chrome → LLM 教会用户安装 ----------
    def _chrome_ok(self) -> bool:
        """检测 Chrome 是否已安装（用于投递浏览器）。"""
        try:
            import os as _os
            return _os.path.exists(CHROME_PATH)
        except Exception:
            return False

    def _llm_judge_install_msg(self, text: str) -> bool:
        """Chrome 安装等待：LLM 判断用户是否表达「安装好了」（不绑固定回复词）。"""
        try:
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                return any(k in text for k in ("装好了", "安装好了", "装完了", "好了", "OK", "ok", "可以了"))
            self.session["llm_calls"] += 1
            sys_p = ("你在帮用户安装 Chrome 浏览器。用户刚说了一句话。"
                     "只输出 JSON：{\"installed\": true/false, \"reply\": \"一句中文\"}。"
                     "installed=true 仅当用户明确表示 Chrome 已安装完成/已打开/可以继续；"
                     "求助、还在装、问怎么装 一律 false。")
            raw = (llm.chat_text(sys_p, text, max_tokens=200, temperature=0.2) or "").strip()
            import json as _j, re as _re
            m = _re.search(r"\{.*\}", raw, _re.S)
            if m:
                try:
                    return bool(_j.loads(m.group(0)).get("installed", False))
                except Exception:
                    pass
        except Exception:
            pass
        return any(k in text for k in ("装好了", "安装好了", "装完了"))

    def _handle_install_msg(self, text: str) -> None:
        """Chrome 安装等待：用户告知装好了 → LLM 判断 → 以拉起 Chrome 成功为硬门槛。"""
        if not self._llm_judge_install_msg(text):
            self.set_bubble("喵还在等 Chrome 装好哦。确认安装完成后告诉我「装好了」；不会装可以问我「怎么装」。")
            return
        self.set_bubble("正在拉起投递浏览器验证…")
        self.add_log("用户表示 Chrome 已装好，尝试拉起验证")
        ok = False
        for _ in range(3):
            try:
                from agent.shared import is_cdp_port_ready
                if self._chrome_ok() and is_cdp_port_ready(9222):
                    ok = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if ok:
            self._install_waiting = False
            self.set_bubble("✅ Chrome 已成功拉起（9222 就绪），继续跑流程…")
            self.add_log("Chrome 拉起成功，解除安装等待")
        else:
            self.set_bubble("还没检测到 Chrome（9222 未就绪）。确认安装完成后再告诉我「装好了」；不想继续说「停止」。")

    def _llm_guide_install_chrome(self) -> None:
        """未检测到 Chrome：LLM 生成安装引导提示词，失败用静态兜底。"""
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                guide = (llm.chat_text(
                    self._llm_stage_brief("安装Chrome引导", {})
                    + "\n\n你是求职助手。用户的电脑没有安装 Google Chrome 浏览器，"
                      "但产品（桌面宠物求职 Agent）必须依赖 Chrome（远程调试端口 9222 投递浏览器）才能工作。\n"
                      "请给出安装步骤：①官网下载地址（google.cn/chrome 或 google.com/chrome）；"
                      "②安装要点（默认选项即可）；③装好后回到对话框告诉喵。控制在 150 字内。",
                    # 2026-09-24 MAXTOK-GUIDE：200 会被推理预算吃光 → content 空 → 永远走静态兜底
                    "", max_tokens=2000, temperature=0.3) or "").strip()
                if guide:
                    self.root.after(0, lambda g=guide: self.set_bubble("🌐 未检测到 Chrome：\n" + g))
                    return
        except Exception:
            pass
        self.root.after(0, lambda: self.set_bubble(
            "🌐 未检测到 Chrome 浏览器。产品依赖 Chrome（投递浏览器 9222）才能自动投递。\n"
            "安装步骤：①打开官网 https://www.google.cn/chrome/ 下载安装包；"
            "②双击安装，保持默认选项；③装好后重新点「开始投递」。"))

    def _toggle_pace(self):
        self._real_pace = not self._real_pace
        mode = ("真实节奏：完整等待，每 3 个关键词休息 2.5~4 分钟"
                if self._real_pace else "演示加速：短节奏保持真实，长休息压缩为 25~40 秒")
        self.add_log("请求节奏切换：" + mode)
        self.set_bubble("请求节奏：%s" % mode)

    # ---------- 暂停 / 继续投递 ----------
    def cmd_pause(self):
        busy = self.state == "分析中" or self._plan_state == "review" or self._resume_choice_waiting
        if not busy and not self._paused:
            self.set_bubble("当前没有正在运行的投递。\n可以先点「分析岗位」或「开始投递」跑起来，再点这里暂停。")
            self.add_log("暂停按钮被点击：当前无运行中的投递")
            return
        self._paused = not self._paused
        if self._paused:
            self.set_act("sit")
            self.set_bubble("⏸️ 投递已暂停，爬爬会停在当前位置（等当前 LLM 评分/页面操作完成即停住）。\n再点一次「暂停投递」继续。")
            self.add_log("投递已暂停")
            # 2026-09-20：暂停 → 桌宠切「看鼠标」，不能再播「工作中」
            self._emit_pet_state("idle")
        else:
            self.set_bubble("▶️ 继续投递…")
            self.add_log("投递继续")
            # 2026-09-20：恢复 → 桌宠切回「工作中」
            self._emit_pet_state("working")

    # ---------- 停止：对话框输入「停止」立即中断（原子停止） ----------
    def cmd_stop(self):
        # 喵内投递线程立即响应停止（此前只杀 skill 进程，喵自己跑的线程停不掉 → 「还在跑」）
        self._stop_requested = True
        self._paused = False
        try:
            (RUN_DIR / "manual_stop.flag").write_text("user-manual-stop", encoding="utf-8")
        except Exception:
            pass
        self._round_state_write("MANUAL_STOPPED")  # 三态主记录：手动停止（不依赖单标志）
        self._plan_reviewed_this_run = False  # 喊停后不自动回方案；等用户说开启→重新展示方案+LLM建议等 OK
        if self._plan_state == "review":
            self._plan_state = None
            self._hide_action_panel()
            self._hide_resume_choice_panel()
        self.set_bubble("🛑 收到，正在停止…\n浏览器会保持打开，但不会再自动投递。")
        self.add_log("用户请求停止（原子停止流程启动）")
        self._set_applying(False)
        threading.Thread(target=self._atomic_stop_work, daemon=True).start()

    def _atomic_stop_work(self):
        """原子停止后台执行：杀 skill 投递进程 + 杀 watchdog 守护 + 禁用计划任务 → 四合一确认。"""
        import subprocess as _sp

        def _kill(match: str, extra: str = ""):
            try:
                _sp.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                    '\\"Name=\'python.exe\'\\" | Where-Object { $_.CommandLine -like \\"*%s*\\" %s } | '
                    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"' % (match, extra),
                    capture_output=True, timeout=30, shell=True)
            except Exception:
                pass

        def _count(match: str, extra: str = "") -> int:
            try:
                out = _sp.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                    '\\"Name=\'python.exe\'\\" | Where-Object { $_.CommandLine -like \\"*%s*\\" %s } | '
                    'Measure-Object | Select-Object -ExpandProperty Count"' % (match, extra),
                    capture_output=True, text=True, timeout=30, shell=True)
                return int((out.stdout or "").strip() or 0)
            except Exception:
                return -1

        # ① 杀 skill 投递主进程（launch_apply.py）
        _kill("launch_apply.py")
        # ② 杀 skill 守护进程 watchdog.py（排除 watchdog_pet.py）
        _kill("watchdog.py", '-and $_.CommandLine -notlike \\"*watchdog_pet.py*\\"')
        # ③ 禁用计划任务（投递停 → 守护停，统一开关）
        for _tn in ("JobHunterWatchdog5min", "JobHunterLoginRestore"):
            try:
                _sp.run('schtasks /Change /TN "\\%s" /Disable' % _tn,
                        capture_output=True, timeout=15, shell=True)
            except Exception:
                pass
        # ④ 四合一确认
        _n_app = _count("launch_apply.py")
        _n_wd = _count("watchdog.py", '-and $_.CommandLine -notlike \\"*watchdog_pet.py*\\"')
        _flag = (RUN_DIR / "manual_stop.flag").exists()
        lines = [
            "🛑 任务已停止（手动停止）。",
            "浏览器保持打开，但不会再自动投递。",
            "重新投递请点「开始投递」。",
        ]
        self.root.after(0, lambda: (self.set_bubble("\n".join(lines)),
                                    self.add_log("原子停止完成（投递进程 %d / 守护 %d / 标记 %s）" % (_n_app, _n_wd, _flag))))
        # 修正：喊停后不自动回方案——等用户说「开启/启动」（LLM 判断真实意图）→
        # cmd_test_run 会因 _plan_reviewed_this_run=False 重新展示方案+LLM历史建议，用户回 OK 才进投递。

    def _back_to_plan_review_after_stop(self):
        """喊停后的去向：回到环节①方案预览（含 LLM 历史表现建议），等用户确认/改方案。"""
        if not self._has_resume():
            self.root.after(0, lambda: self.set_bubble(
                "已停止。还没有简历，把简历拖给我，我帮你做方案。"))
            return
        self.root.after(0, lambda: (self.set_bubble("📋 已停止。回到方案，结合历史投递表现看看要不要调整："),
            self._start_plan_review_each_run()))

    # ---------- 四合一状态查询：我到底停没停 ----------
    def cmd_stop_status(self):
        """查询 投递进程 + 守护进程 + 计划任务 + 停止标记 四合一状态。"""
        import subprocess as _sp

        def _count(match: str, extra: str = "") -> int:
            try:
                out = _sp.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                    '\\"Name=\'python.exe\'\\" | Where-Object { $_.CommandLine -like \\"*%s*\\" %s } | '
                    'Measure-Object | Select-Object -ExpandProperty Count"' % (match, extra),
                    capture_output=True, text=True, timeout=30, shell=True)
                return int((out.stdout or "").strip() or 0)
            except Exception:
                return -1

        def _task_state(tn: str) -> str:
            try:
                out = _sp.run('schtasks /Query /TN "\\%s"' % tn,
                              capture_output=True, text=True, timeout=15, shell=True)
                txt = (out.stdout or "") + (out.stderr or "")
                if "Disable" in txt:
                    return "禁用"
                if "ERROR" in txt.upper() or "找不到" in txt:
                    return "不存在"
                return "启用"
            except Exception:
                return "未知"

        def _work():
            n_app = _count("launch_apply.py")
            n_wd = _count("watchdog.py", '-and $_.CommandLine -notlike \\"*watchdog_pet.py*\\"')
            n_pet = _count("watchdog_pet.py")
            flag = (RUN_DIR / "manual_stop.flag").exists()
            t1, t2 = _task_state("JobHunterWatchdog5min"), _task_state("JobHunterLoginRestore")
            busy = self.state in ("分析中", "投递中", "沟通中") or self._paused
            stopped = flag and n_app == 0
            lines = [
                "【停止状态 · 四合一】",
                "· 投递进程(launch_apply)：%s" % ("✅ 无（已停）" if n_app == 0 else "🔴 运行中 %d 个" % n_app),
                "· 守护进程(watchdog)：%s" % ("✅ 无（已停）" if n_wd == 0 else "🟡 运行中 %d 个" % n_wd),
                "· 桌宠守护(watchdog_pet)：%s" % ("✅ 未运行" if n_pet == 0 else "🟡 运行中 %d 个" % n_pet),
                "· 计划任务：Watchdog5min=%s · LoginRestore=%s" % (t1, t2),
                "· 停止标记：%s" % ("✅ 存在（停止态）" if flag else "（无——投递态/全新轮）"),
                "· 喵当前任务：%s" % ("⏸️ 暂停中" if self._paused else ("运行中（%s）" % self.state if busy else "空闲")),
                "\n结论：" + ("🛑 已停止（标记在、投递进程无）" if stopped else "▶️ 未停止/运行中"),
            ]
            self.root.after(0, lambda: (self.set_bubble("\n".join(lines)), self.add_log("停止状态查询")))

        threading.Thread(target=_work, daemon=True).start()

    def _pausable_sleep(self, secs: float) -> None:
        """可被暂停打断的 sleep：暂停时挂起等待，恢复后继续计时；停止时立即返回。"""
        import time as _t
        end = _t.time() + max(0.0, float(secs))
        while _t.time() < end:
            if self._stop_requested:
                return
            if self._paused:
                while self._paused and not self._stop_requested:
                    _t.sleep(0.2)
            _t.sleep(0.25)

    def _record_ledger_action(self, action: str, status: str, details: dict | None = None) -> None:
        try:
            from agent.ledger import record_action
            record_action(action, status, details or {}, skill_dir=RUN_DIR)
        except Exception:
            pass

    def _warn_llm_runtime(self, reason: str) -> None:
        if self._llm_runtime_warned:
            return
        self._llm_runtime_warned = True
        msg = ("⚠️ LLM 模型连接出现问题：%s\n当前投递不会自动停止，但不建议继续让它按旧规则跑。需要的话请点「暂停投递」；要结束请明确回复「停止」。" % str(reason)[:120])
        self.root.after(0, lambda: self.set_bubble(msg))
        self.add_log("LLM 运行中异常：%s（未自动停止，已提示用户暂停）" % str(reason)[:120])

    def _llm_preflight_start(self, real: bool) -> bool:
        import time as _t
        if _t.time() < self._llm_preflight_ok_until:
            return True
        if self._llm_preflight_pending:
            return False
        self._llm_preflight_pending = True
        self.set_bubble("🔎 正在检查 LLM 模型连通性，确认可用后才开始投递…")
        def _work():
            error = ""
            try:
                llm = shared.build_llm_client(self.cfg, skill_dir=RUN_DIR)
                if not getattr(llm, "is_configured", lambda: False)():
                    raise RuntimeError("LLM 未配置或缺少 API Key")
                out = (llm.chat_text(
                    "只做连通性检查，只回复 OK，不执行任何操作。"
                    # 2026-09-20：与 09-19 G2 同一类坑 —— 推理模型会把 max_tokens 预算
                    # 全烧在 reasoning 上，content 恒空（_message_content 只读 content，
                    # 不看 reasoning_content）。预检原只给 5 个 token，必然空
                    # → 误报「LLM 没连通」，而同时对话通道（预算 900）是正常的。
                    "\n\n【重要】直接输出 OK，不要推理过程、不要思考步骤。",
                    "ping", max_tokens=200, temperature=0.0) or "").strip()
                if not out:
                    raise RuntimeError("LLM 返回为空")
            except Exception as exc:
                error = str(exc)
            def _done():
                self._llm_preflight_pending = False
                if error:
                    self._llm_preflight_ok_until = 0.0
                    self.set_state("闲置")
                    self.add_log("启动前 LLM 检查失败：%s" % error[:160])
                    # 2026-09-20：原文案甩锅「网络/API 配置」是误导（与 09-19 G3 同一类问题）——
                    # 实测根因多是推理模型把输出预算耗在思考过程上，重试一次通常即可。
                    self.set_bubble("❌ LLM 模型当前不可用，暂不进入投递流程。\n原因：%s\n"
                                    "若提示「返回为空」，多为推理模型把输出预算耗在思考过程上"
                                    "（不是网络/密钥问题），重试一次通常即可；"
                                    "这次没有自动停止任何正在运行的任务。" % error[:160])
                    return
                self._llm_preflight_ok_until = time.time() + 120
                self.add_log("启动前 LLM 连通性检查通过")
                self.cmd_test_run(real=real)
            self.root.after(0, _done)
        threading.Thread(target=_work, daemon=True).start()
        return False

    # ---------- 开始投递：按完整投递业务流程全流程模拟（投递不真实发出） ----------
    def _has_resume(self) -> bool:
        """是否已有简历信息：会话内分析过 或 run/resume.md 有实质内容。"""
        if self.session.get("resume_analyzed"):
            return True
        try:
            p = RUN_DIR / "resume.md"
            if p.exists() and len(p.read_text(encoding="utf-8", errors="ignore").strip()) >= 30:
                return True
        except Exception:
            pass
        return False

    # ---------- 浏览器统一门禁：方案未确认（未回复 OK）前，禁止任何入口拉起浏览器进 BOSS ----------
    def _browser_gate(self) -> bool:
        """返回 True=放行；False=已拦截（已提示并引导）。"""
        if not self._has_resume():
            self.set_bubble("爬爬还没收到你的简历：先拖入/导入简历，生成投放方案并回复 OK 后，才能打开 BOSS 页面。")
            self.add_log("浏览器门禁拦截：无简历信息")
            return False
        if not self._plan_confirmed():
            self.set_bubble("📋 投放方案还没确认：需要先回复 OK 确认方案，才能打开 BOSS 页面。\n正在生成方案…")
            self.add_log("浏览器门禁拦截：方案未确认")
            self._ensure_plan_flow()
            return False
        return True

    def cmd_test_run(self, real: bool = True):
        """完整投递业务流程。real=True：真实投递（达标岗位真实点击「立即沟通」，BOSS 默认话术）；
        real=False：仅记录、不真实发送（**本版本恒为 True**，参数保留以兼容旧调用）。"""
        self._pending_real = real  # P1 修复：记住 real 参数，方案异步确认后不丢失
        if getattr(self, "_is_applying", False):
            self.set_bubble("爬爬正在忙上一个任务，等它做完再点哦～")
            return
        if not self._llm_preflight_start(real):
            return
        # 夜间 22:00-09:00 先要求用户确认风控后果，不再静默硬拒绝。
        # 时段判定统一走 shared.is_night_window()（2026-09-17 统一策略）
        if shared.is_night_window():
            if not self._night_confirmed_for_run:
                self._night_confirmation_pending = True
                self.set_bubble(
                    "🌙 当前是夜间时段（22:00-09:00），BOSS 夜间操作更容易触发风控/封号。\n"
                    "仍要继续请回复 OK；否则回复停止。请确认账号风险由你自行承担。")
                self.add_log("夜间启动：等待用户风险确认 OK")
                return
        else:
            self._night_confirmed_for_run = False
        # 风控标记：启动时自动清除（上次检测到风控停下，下次手动启动就自动恢复）
        if (RUN_DIR / "risk_blocked.flag").exists():
            (RUN_DIR / "risk_blocked.flag").unlink()
            self.add_log("已自动清除上次的风控停止标记")
        if not self._has_resume():
            self.set_bubble("爬爬还没收到你的简历，暂时不能开始投递。\n把简历文件拖到窗口上，或点「简历」按钮导入，然后再点「开始投递」。")
            self.add_log("开始投递被拦截：未收到简历信息")
            return
        # 2026-09-23 STARTBTN：方案确认改由「点开始投递按钮」完成（聊天不再能启动投递）。
        #  · 还没有方案 → 先走方案生成流程（让用户先看方案）；
        #  · 已有方案 → 视为用户已看过（按钮仅在看过方案后才出现）→ 应用并确认后开投。
        if not self._plan_reviewed_this_run:
            if not self._plan_confirmed():
                self._start_plan_review_each_run()
                return
            self._apply_plan(self._plan.get("keywords") or [])
            return
        self.set_state("分析中")
        self.set_act("think")
        self._paused = False
        self._stop_requested = False
        self._plan_state = None
        self._plan_change_pending = False
        self._llm_runtime_warned = False
        self._run_jobs = []  # 2026-09-18 复盘报告：新的一轮，清空上轮明细
        self._last_kw_stats = []  # 2026-09-23：本轮关键词统计也随新轮清空（原跨轮累加会污染报告）
        steps = ("【开始投递】\n"
                 "检查登录状态 → 检查在线简历 → 进入投递流程")
        self.set_bubble(steps + "\n⚠️ 达标岗位会真实打招呼（BOSS 默认话术）；输入「停止」可随时停。")
        self.add_log("真实投递启动：真实岗位 + 真实打招呼" if real else "开始投递：真实岗位全流程")

        def _wait_if_paused():
            while self._paused and not self._stop_requested:
                time.sleep(0.5)

        def _work():
            import time
            from agent.shared import is_cdp_port_ready, connect_browser  # noqa: F401
            from boss import boss_apply  # noqa: F401
            from boss.boss_chat import load_greeted_companies  # noqa: F401
            rec = {"kw": 0, "scan": 0, "greet": 0, "llm": 0}
            self._live_rec = rec  # 挂到 self 供投递中 LLM 中途报告读取（修改5）
            try:
                # 防待机防熄屏：投递期间电脑不休眠（结束/停止/异常时释放）
                self._prevent_sleep(True)
                self._run_started = time.time()  # 30 分钟稳定性自检基准
                # 离线重放模式（分流）：岗位读本地缓存，零 BOSS 请求——直接跑重放流程
                # 注意：离线模式不触碰轮次状态机（不写 RUNNING/不清基线）
                if self._offline:
                    self._run_offline_flow(rec, real)
                    return
                # 三态轮次语义（交接补充：状态持久化到 round-state.json，不依赖单标志文件）
                # - MANUAL_STOPPED → 全新一轮：清基线重新计数
                # - CRASHED（上次 RUNNING 未正常收尾）→ 沿用上一轮白名单续跑
                # - NEW（无记录/正常完成）→ 全新一轮
                _round = self._round_state()
                if _round == "MANUAL_STOPPED":
                    self._clear_round_baseline()
                    self.add_log("轮次判定：上次手动停止 → 清基线，本轮为全新一轮")
                elif _round == "CRASHED":
                    self.add_log("轮次判定：上次异常终止（CRASHED）→ 沿用上一轮白名单续跑")
                else:
                    self._clear_round_baseline()
                    self.add_log("轮次判定：全新一轮（无记录/正常完成）→ 清基线")
                self._round_state_write("RUNNING")
                # 兼容旧标志：手动启动消费 manual_stop.flag（skill watchdog 仍以此判断停止）
                try:
                    (RUN_DIR / "manual_stop.flag").unlink(missing_ok=True)
                except Exception:
                    pass
                # 登录确认通过前不启用守护：未登录/登录丢失 = 投递未真正开始（等同自然关闭，守护不开）
                # （守护激活统一放在登录检测通过之后，见下方 1/5 登录确认处）
                # 0/5 环境：确保投递浏览器在线（不在线自动拉起；未装 Chrome → LLM 教会安装）
                self.root.after(0, lambda: self.set_state("投递中"))
                self.root.after(0, lambda: self.set_bubble(steps + "\n检查投递环境：正在连接投递浏览器…"))
                if not is_cdp_port_ready(9222):
                    if not self._chrome_ok():
                        # 未检测到 Chrome → LLM 生成安装引导 → 等待用户装好（不直接退出）
                        self._llm_guide_install_chrome()
                        self._install_waiting = True
                        self.root.after(0, lambda: (self.set_bubble(
                            steps + "\n检查投递环境：未检测到 Chrome，已给出安装指引。\n"
                                    "装好后在对话框告诉我「装好了」，喵会自动拉起验证并继续；不想继续说「停止」。"),
                            self.add_log("等待用户安装 Chrome（_install_waiting）")))
                        while self._install_waiting and not self._stop_requested:
                            if self._paused:
                                while self._paused and not self._stop_requested:
                                    time.sleep(0.5)
                            time.sleep(0.5)
                        self._install_waiting = False
                        if self._stop_requested:
                            self._round_state_write("MANUAL_STOPPED")
                            return
                        self.root.after(0, lambda: self.set_bubble(steps + "\n检查投递环境：Chrome 已就绪，继续…"))
                    self.root.after(0, lambda: self.set_bubble(
                        steps + "\n检查投递环境：投递浏览器不在线，正在自动拉起（带 BOSS 登录态）…"))
                    self.add_log("自动拉起 9222 投递浏览器")
                    # 修改2：浏览器必须自动拉起（不自动拉起 watchdog 无意义）——失败自动重试 3 次
                    _launched = False
                    for _attempt in range(3):
                        if self._launch_browser():
                            _launched = True
                            break
                        time.sleep(2)
                    if not _launched:
                        self.root.after(0, lambda: (self.set_bubble(
                            "自动拉起投递浏览器失败（已自动重试 3 次）。\n请检查 Chrome 安装后重新点「开始投递」。"),
                            self.set_state("闲置")))
                        self._round_state_write("MANUAL_STOPPED")
                        return
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 投递环境就绪"))
                time.sleep(1.2)
                _wait_if_paused()
                # 1/5 简历准备
                resume_text = self._current_resume()
                if resume_text:
                    self.root.after(0, lambda: self.set_bubble(
                        steps + "\n✅ 检查在线简历：已就绪（%d 字）" % len(resume_text)))
                else:
                    self.root.after(0, lambda: self.set_bubble(
                        steps + "\n⚠️ 检查在线简历：未找到（可点「简历匹配」导入）"))
                time.sleep(1.2)
                _wait_if_paused()
                # 2/5 求职配置
                c = self.cfg
                roles = c.get("target_roles") or []
                self.root.after(0, lambda: self.set_bubble(
                    steps + "\n✅ 投递配置：%d 个关键词 · 匹配值 %s 分 · 薪资 %s-%sK · 排除 %d 词" % (
                        len(roles), c.get("min_score"), c.get("min_salary_low_k", "?"),
                        c.get("min_salary_high_k", "?"), len(c.get("title_exclude_keywords") or []))))
                time.sleep(1.2)
                _wait_if_paused()
                # 2.5/5 登录确认：打开 BOSS 检测登录；未登录 → 打开登录页 → 用户对话框告知 → LLM 判断 → 重检
                self.root.after(0, lambda: self.set_bubble(steps + "\n检查登录状态…"))
                browser = connect_browser(9222)
                tab = browser.latest_tab
                if not self._ensure_boss_login(tab):
                    # 未登录：回到方案确认环节，让用户重新走流程（可改方案/改简历）
                    self._guard_tasks("disable")
                    self._set_applying(False)
                    self._round_state_write("MANUAL_STOPPED")
                    self._plan_reviewed_this_run = False
                    self.root.after(0, lambda: (self.set_bubble(
                        "🔐 BOSS 还没登录哦～\n请先在浏览器里登录 BOSS，然后重新点「开始投递」。"),
                        self.set_state("闲置")))
                    return
                # 登录确认通过 → 投递真正开始 → 守护启（统一开关：投递启→守护启，投递停→守护停）
                self._llm_stage_enter("登录检测通过")
                self._guard_tasks("enable")
                self._set_applying(True)
                if self._background_mode:
                    self.root.after(500, lambda: self._set_browser_visibility(False))
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 登录状态正常，检查在线简历…"))
                self._llm_stage_enter("在线简历确认")
                # 2.6/5 附件简历选择：BOSS 要简历时发送哪一份
                _wait_if_paused()
                if not self._ensure_resume_send_choice(tab):
                    self._guard_tasks("disable")
                    self._set_applying(False)
                    self.root.after(0, lambda: (self.set_bubble(
                        "附件简历确认未完成，开始投递已暂停。\n请按上方提示处理（选择简历 / 上传附件 / 检查弹窗）后重新点「开始投递」。"),
                        self.set_state("闲置")))
                    self._round_state_write("MANUAL_STOPPED")
                    # 附件简历是用户硬门禁：LLM 仅协助、无权跳过；未通过则流程暂停
                    return
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 在线简历确认，正式进入投递流程…"))
                self.set_state("投递中")
                self._llm_stage_enter("投递主循环")
                # LLM 主控接管已在「上传简历后」启动；此处仅确认硬门禁顺序不变：
                # 附件简历确认必须已通过（未通过上方已 return），LLM 无权跳过。
                # 3/5 投递主循环（真实岗位，含请求节奏控制）
                # 监听白名单基线：本轮投递开始前已打招呼的公司集合（历史轮次）
                baseline = load_greeted_companies(RUN_DIR)
                keywords = roles or ["海外运营", "海外社媒", "TikTok"]
                greeted = []

                # 串行监听：投递主线程每扫完一个关键词后，暂停投递同步跑一轮 HR 监听
                # 不再开后台线程，避免并发操作同一个浏览器导致 tab 竞态
                self._chat_monitor_stop = False
                self.add_log("投递中监听已启动：每扫完一个关键词同步跑一轮 HR 消息")

                def _run_one_chat_round():
                    """同步跑一轮 HR 监听（主线程调用，不并发）。"""
                    try:
                        from boss.boss_chat import run_chat_monitor
                        self.add_log("【验证2-HR监听】开始扫描HR消息（前15个会话）…")
                        demo_cfg = dict(self.cfg)
                        demo_cfg["auto_chat_reply"] = False
                        demo_cfg["only_greeted_hr"] = False  # 强制关闭白名单，处理所有前15个会话
                        summary = run_chat_monitor(
                            config=demo_cfg, skill_dir=RUN_DIR, debug_port=9222,
                            mode="apply" if real else "rehearsal",
                            rounds=1, interval=30.0, baseline_companies=baseline,
                            resume_pdf=self.cfg.get("resume_pdf_path") or None)
                        _acts = (summary or {}).get("actions", [])
                        _seen = (summary or {}).get("conversations_seen", 0)
                        self.add_log("【验证2-HR监听】扫描完成：发现 %d 个会话，处理了 %d 个动作" % (_seen, len(_acts)))
                        for act in _acts:
                            _type = act.get("type", "?")
                            # 2026-09-22 CONV2：结果统计按**公司名**做键
                            # （outcomes.json / job_memory / 复盘报告三方都靠公司名 join），
                            # 而会话 key 是 HR 姓名，两者对不上 → HR 结果永远进不了报告。
                            # 优先用 monitor 回填的公司名，拿不到才回退 HR 姓名。
                            _conv = (str(act.get("company") or "").strip()
                                     or str(act.get("conversation") or "").strip()
                                     or str(act.get("hr_name") or "").strip()
                                     or "?")
                            _msg = (act.get("message") or act.get("reply") or act.get("hint") or "")[:80]
                            # 2026-09-19 C3：每个 HR 动作落成结果回填状态。
                            # 判定不看「谁触发的」—— 用户自己手动聊出来的结果同样入账。
                            self._record_outcome(
                                _conv, _type, hr_name=str(act.get("hr_name") or ""),
                                snippet=str(_msg or ""))
                            if _type == "chat_alert":
                                # 2026-09-19 O：命中方案排除词（日结/押金/先交费…）的
                                # HR 消息打上标记，便于一眼识别垃圾招聘。
                                # ⚠️ 只打标记，不做过滤（过滤属行为变更，未做）。
                                _junk = [w for w in (
                                    self.cfg.get("exclude_keywords") or [])
                                    if w and w in _msg]
                                self.add_log("【验证2-消息提醒】%sHR:%s | %s" % (
                                    "⚠️命中排除词(%s) " % "/".join(_junk[:3]) if _junk else "",
                                    _conv, _msg))
                                self.root.after(0, lambda a=act: self._push_hr_alert(a))
                            elif _type == "send_resume":
                                self.add_log("【验证2-发简历】✅ HR要简历，已自动发送：%s" % _conv)
                            elif _type == "interview_invite":
                                self.add_log("【验证2-面试邀请】HR:%s | %s（未自动回复，需你接管）" % (_conv, _msg))
                            elif _type == "reject_reply":
                                # 2026-09-19 N：把触发原话打出来 ——
                                # 否则误发致谢时无法定位（用户已实测遇到一次）
                                self.add_log("【验证2-拒绝致谢】HR:%s | 已发礼貌回复 | 触发原话：%s" % (_conv, _msg))
                            elif _type == "reject_detected":
                                self.add_log("【验证2-被拒绝】HR:%s | %s" % (_conv, _msg))
                            elif _type == "llm_quota_exhausted":
                                self.add_log("【验证2-LLM配额】⚠️ LLM额度耗尽！")
                            else:
                                self.add_log("【验证2-其他】%s | %s | %s" % (_type, _conv, _msg))
                        self.add_log("【验证4-tab关闭】监听结束，关闭消息页tab")
                    except Exception as e:
                        self.add_log("【验证2-HR监听】异常：%s" % e)

                # 临时验证：投递开始前先跑一轮HR监听
                # 开关见模块顶部 _DEBUG_PRECHAT_ROUND（默认 False = 不预跑）。
                if _DEBUG_PRECHAT_ROUND:
                    self.add_log("【临时验证】投递开始前先跑一轮HR监听…")
                    _run_one_chat_round()

                for i, kw in enumerate(keywords, 1):
                    _wait_if_paused()
                    if self._stop_requested:
                        break
                    # 问题4：用户说"选错简历/重选附件"→ 重走环节④（重检+重选），选完继续本轮
                    if self._resume_reselect_requested:
                        self._resume_reselect_requested = False
                        self.root.after(0, lambda: self.set_bubble("🔄 回到附件简历环节，重新检测并让你选择…"))
                        if not self._ensure_resume_send_choice(browser.latest_tab):
                            self.root.after(0, lambda: (self.set_bubble(
                                "重选附件简历未完成，本轮停止。可改完后重新点「开始投递」。"),
                                self.set_state("闲置")))
                            self._round_state_write("MANUAL_STOPPED")
                            return
                    # 跨入夜间：暂停并再次询问风险，不自动结束或静默继续。
                    # 时段判定统一走 shared.is_night_window()（2026-09-17 统一策略）
                    if shared.is_night_window() and not self._night_confirmed_for_run:
                        self._night_confirmation_pending = True
                        self._paused = True
                        self.root.after(0, lambda: self.set_bubble(
                            steps + "\n🌙 已进入夜间时段（22:00-09:00），当前已暂停。BOSS 夜间操作有封号风险；回复 OK 继续，回复停止结束。"))
                        self.add_log("运行中跨入夜间：暂停并等待风险确认 OK")
                        _wait_if_paused()
                        if self._stop_requested:
                            break
                    # 每个关键词搜索前复核登录态：未登录立即停，不搜索（不依赖"扫不到才怀疑"）
                    try:
                        if not self._quick_login_check(browser.latest_tab):
                            self._alert_login_lost()
                            self.root.after(0, lambda kw=kw: (self.set_bubble(
                                "开始投递中断：检测到 BOSS 未登录（关键词「%s」搜索前）。\n请扫码登录后重新点「开始投递」。" % kw),
                                self.set_state("闲置")))
                            return
                    except Exception:
                        pass
                    # 打开搜索页加载节奏
                    self._pausable_sleep(self._pace("page_load"))
                    try:
                        # 2026-09-18：60 → 35。用户裁决「60 个容易被封号」，
                        # 属风控改动。单轮请求量 1140 → 665 次（降约 42%）。
                        jobs = self._fetch_boss_jobs(kw, limit=35)
                    except Exception as exc:
                        self.root.after(0, lambda e=exc, kw=kw: self.add_log(
                            "关键词「%s」读取失败：%s" % (kw, e)))
                        jobs = []
                    if not jobs:
                        self._st["empty_search_streak"] += 1
                        risk_cfg = self.cfg.get("risk_detection") or {}
                        if self._st["empty_search_streak"] >= int(risk_cfg.get("empty_search_streak", 3) or 3):
                            self._trigger_risk_block("连续 3 个关键词无岗位/结果异常，疑似被限流或风控")
                            break
                        # 扫不到岗位：先怀疑登录失效
                        try:
                            if not self._quick_login_check(connect_browser(9222).latest_tab):
                                self._alert_login_lost()
                                self._guard_tasks("disable")
                                self._set_applying(False)
                                self.root.after(0, lambda: (self.set_bubble(
                                    "开始投递中断：检测到 BOSS 登录已失效，请扫码后重新点「开始投递」。"),
                                    self.set_state("闲置")))
                                return
                        except Exception:
                            pass
                        self.root.after(0, lambda kw=kw: self.add_log("关键词「%s」未读到岗位，跳过" % kw))
                        continue
                    self._st["empty_search_streak"] = 0
                    self.root.after(0, lambda i=i, kw=kw, n=len(jobs): self.set_bubble(
                        steps + "\n✅ 投递中：关键词 %d/%d「%s」扫到 %d 个岗位，评分中…" % (
                            i, len(keywords), kw, n)))
                    rec["kw"] += 1
                    self._emit_progress(rec)
                    kw_scanned = 0
                    kw_applied = 0
                    kw_scores = []
                    for title, jd, company, _href in jobs:
                        _wait_if_paused()
                        if self._stop_requested:
                            break
                        # 2026-09-18 新增：公司名屏蔽（company_exclude_keywords）。
                        # 独立于标题/JD 排除词；默认空数组时不产生任何影响。
                        _co_kw = shared.company_blocked(company, self.cfg)
                        if _co_kw:
                            self.add_log("公司名屏蔽跳过：%s | %s（命中：%s）" % (
                                company, title, _co_kw))
                            self._record_ledger_action("skip", "company_filter", {"job": title, "company": company, "reason": _co_kw})
                            self._st["block_hits"] += 1
                            continue
                        # 两周去重：同一岗位两周内只评估一次（仅 LLM 真评分成功才计入）
                        _job_key = shared.normalize_text((title or "") + (company or ""))
                        if self._job_seen_recently(_job_key):
                            self.add_log("【验证3-两周去重】两周内已评估过，直接用缓存评分：%s" % title)
                            self._st["dedup_hits"] += 1
                            # 直接用之前的评分结果，不用再调用 LLM
                            res = self._get_cached_score(_job_key)
                            if res is None:
                                # 缓存里没有详细评分，还是跳过
                                continue
                            self._log_demo_result(kw, title, company, res)
                        else:
                            # 读职位详情节奏
                            self._pausable_sleep(self._pace("jd_read"))
                            rec["scan"] += 1
                            self._emit_progress(rec)
                            kw_scanned += 1
                            try:
                                res = self._score_jd(title, jd, self.cfg, skill_dir=RUN_DIR,
                                                     resume_text=self._current_resume(),
                                                     use_llm=real)
                                rec["llm"] += int(bool(getattr(res, "llm_ok", False)))
                                _llm_used = "LLM真评分" if getattr(res, "llm_ok", False) else "启发式兜底"
                                self.add_log("【验证1-LLM评分】%s | %s | llm_score=%d" % (
                                    _llm_used, title, getattr(res, "llm_score", 0)))
                                # 记录 key + 完整评分结果
                                self._mark_job_seen(_job_key, res)
                                self._log_demo_result(kw, title, company, res)
                            except Exception as e:
                                self.add_log("评分异常跳过：%s（%s）" % (title, str(e)[:100]))
                                self._record_ledger_action("fail", "score_error", {"job": title, "company": company, "reason": str(e)[:100]})
                                continue
                            if real and not getattr(res, "llm_ok", False):
                                # 2026-09-24 RESUMEOPT：区分「开关没开」与「LLM 真出问题」——
                                # 前者是**必然**走启发式（简历被清空、压根没调 LLM），
                                # 原来只报「回退到了启发式」，用户会误以为 LLM 挂了。
                                if not bool((self.cfg.get("llm") or {}).get("allow_resume_upload", False)):
                                    self._warn_llm_runtime(
                                        "岗位评分走的是本地启发式 —— 因为「允许上传简历」没开"
                                        "（看板 → 设置 · LLM 里勾上；否则分数偏低、容易全被过滤）")
                                else:
                                    self._warn_llm_runtime("岗位评分回退到了启发式结果")
                        _wait_if_paused()  # LLM 返回后若已暂停，立即停住
                        kw_scores.append(res.total_score)
                        # 不用缓存的 decision，用 total_score 和当前阈值重新判断
                        # （用户可能调整了阈值，缓存的 decision 是旧阈值下的）
                        _current_threshold = shared.match_threshold(title, self.cfg)
                        _score_source = "缓存" if getattr(res, "llm_ok", None) is False and "CachedScore" in str(type(res)) else "新评"
                        # 2026-09-19 M：分母不再写死 40 —— A2 权重重构后
                        # LLM 上限已是 60，写死会出现「50/40」这种自相矛盾的数字。
                        _llm_cap = shared.scoring_config(self.cfg).get("llm_score_max", 60)
                        self.add_log("评分明细：%s | %s | 规则分=%d | LLM补分=%d/%s | 总分=%d | 实际阈值=%d" % (_score_source, title, getattr(res, "rule_score", 0), getattr(res, "llm_score", 0), _llm_cap, res.total_score, _current_threshold))
                        if res.total_score >= _current_threshold:
                            if real:
                                # 真实投递：打开详情页真实点击「立即沟通」（BOSS 默认话术）
                                _greeted = False
                                if _href:
                                    try:
                                        _dt = browser.new_tab(_href)
                                        time.sleep(3)
                                        _status, _msg = boss_apply.click_apply_button(_dt, "", browser, skill_dir=RUN_DIR, company=company, job=title)
                                        _dt.close()
                                        _greeted = (_status == "applied")
                                        if _status != "applied":
                                            self._st["apply_fail_streak"] += 1
                                            self.root.after(0, lambda t=title, s=_status, m=_msg: self.add_log(
                                                "真实投递跳过：%s（%s：%s）" % (t, s, m)))
                                            risk_cfg = self.cfg.get("risk_detection") or {}
                                            if self._st["apply_fail_streak"] >= int(risk_cfg.get("apply_fail_streak", 2) or 2):
                                                self._trigger_risk_block("连续 2 次立即沟通失败，疑似按钮异常、限流或风控")
                                        else:
                                            self._st["apply_fail_streak"] = 0
                                    except Exception as _exc:
                                        self.root.after(0, lambda e=_exc, t=title: self.add_log(
                                            "真实投递异常：%s %s" % (t, e)))
                                if _greeted:
                                    rec["greet"] += 1
                                    self._emit_progress(rec)
                                    kw_applied += 1
                                    greeted.append(title)
                                    self._log_demo_greet(company, title, real=real)  # 真实已投 → 记入正式白名单（监听范围）
                                    # 2026-09-22 OUTCOME1：标出「这条真的投出去了」，
                                    # 供「关键词 → 投过的岗位 → HR 结果」归因用。
                                    self._mark_job_applied(kw, title, company)
                                    self.root.after(0, lambda t=title, s=res.total_score: self.add_log(
                                        "【真实打招呼】%s（%d分）— 已真实点击立即沟通" % (t, s)))
                                else:
                                    self.root.after(0, lambda t=title: self.add_log(
                                        "未真实投出：%s（按钮不可用/打开失败）" % t))
                            else:
                                rec["greet"] += 1
                                self._emit_progress(rec)
                                kw_applied += 1
                                greeted.append(title)
                                self._log_demo_greet(company, title, real=real)  # 写入白名单日志（模拟）
                                self.root.after(0, lambda t=title, s=res.total_score: self.add_log(
                                    "【模拟打招呼】%s（%d分）— 未真实发送，已记入白名单日志" % (t, s)))
                            # 打招呼后节奏
                            self._pausable_sleep(self._pace("after_greet"))
                            # 新规则 1：连续打 3 个招呼，停 2 分钟
                            self._st["greet_streak"] += 1
                            if self._st["greet_streak"] >= 3:
                                self.add_log("连续 3 个打招呼，停 2 分钟")
                                self.root.after(0, lambda: self.set_bubble(
                                    steps + "\n⏸️ 连续 3 个打招呼，停 2 分钟…"))
                                self._pausable_sleep(120.0)
                                self._st["greet_streak"] = 0
                            # 新规则 2：连续运行 2 小时，停 15 分钟
                            now = time.time()
                            if not self._st["last_2h_rest"]:
                                self._st["last_2h_rest"] = now
                            elif now - self._st["last_2h_rest"] >= 7200:  # 2 小时 = 7200 秒
                                self.add_log("连续运行 2 小时，停 15 分钟")
                                self.root.after(0, lambda: self.set_bubble(
                                    steps + "\n⏸️ 连续运行 2 小时，停 15 分钟…"))
                                self._pausable_sleep(900.0)
                                self._st["last_2h_rest"] = now
                        else:
                            self._record_ledger_action("skip", "score_filter", {"job": title, "company": company, "score": getattr(res, "total_score", 0), "rule_score": getattr(res, "rule_score", 0), "llm_score": getattr(res, "llm_score", 0), "threshold": _current_threshold})
                            self.root.after(0, lambda t=title: self.add_log("过滤跳过：%s" % t))
                            # 跳过不匹配职位节奏
                            self._pausable_sleep(self._pace("skip_job"))
                    # 换关键词：有效性分析（按匹配分）
                    avg = sum(kw_scores) / len(kw_scores) if kw_scores else 0
                    top = max(kw_scores) if kw_scores else 0
                    self._last_kw_stats.append({
                        "kw": kw, "scanned": kw_scanned, "applied": kw_applied,
                        "avg": round(avg, 1), "top": top})
                    self.root.after(0, lambda kw=kw, s=kw_scanned, a=kw_applied, avg=avg, top=top: (
                        self.add_log("关键词「%s」有效性：扫描 %d · 达标 %d · 平均 %.0f 分 · 最高 %d 分" % (kw, s, a, avg, top)),
                        self.set_bubble(steps + "\n🔎 换词分析「%s」：\n扫描 %d · 达标 %d · 平均 %.0f 分 · 最高 %d 分\n%s" % (
                            kw, s, a, avg, top,
                            "✅ 该关键词有效，继续按此词投递" if a > 0 else "⚠️ 无一达标（<%s 分），下一个关键词" % self.cfg.get("min_score")))))
                    # LLM 主控接管：换关键词决策由 LLM 给出（喵执行）
                    if self._llm_agent and i < len(keywords):
                        _dec = self._llm_agent_decide("switch_keyword", {
                            "kw": kw, "scanned": kw_scanned, "applied": kw_applied,
                            "avg": avg, "top": top})
                        if _dec.get("action") == "stop":
                            self._stop_requested = True
                            self.add_log("LLM 主控指令：停止本轮（%s）" % _dec.get("reason"))
                            break
                        if _dec.get("action") == "adjust" and _dec.get("min_score"):
                            try:
                                old_ms = self.cfg.get("min_score", 70)
                                self.cfg["min_score"] = int(_dec["min_score"])
                                self.add_log("LLM 主控指令：调整岗位匹配值 %s→%s（%s）" % (
                                    old_ms, _dec["min_score"], _dec.get("reason")))
                            except Exception:
                                pass
                    # Tab 清理：保留聊天页（监听用），清掉历史详情/搜索页
                    try:
                        from agent.shared import cleanup_tabs
                        cleanup_tabs(connect_browser(9222),
                                     keep_urls=("https://www.zhipin.com/web/geek/chat",),
                                     max_tabs=5)
                    except Exception:
                        pass
                    # 30 分钟稳定性自检：投递运行中每 30 分钟逐项输出日志
                    if self._run_started and time.time() - self._run_started >= 1800:
                        self._stability_report()
                        self._run_started = time.time()
                    # 任务间休息（+4% 概率加长）
                    if i < len(keywords):
                        _wait_if_paused()
                        t = self._pace("task_break")
                        if random.random() < 0.04:
                            t += random.uniform(7.0, 12.0)
                        self.root.after(0, lambda t=t, kw=kw: self.add_log(
                            "任务间停顿：%s 后等待 %.0f 秒（控制请求频率）" % (kw, t)))
                        self._pausable_sleep(t)
                    # 每 3 个关键词强制长休息（控制单位时间内的请求总量）
                    if i % 3 == 0:
                        _wait_if_paused()
                        if self._stop_requested:
                            break
                        t = self._pace("long_rest")
                        real_txt = ("（2.5~4 分钟）" if self._real_pace else "（演示加速 25~40 秒，正式 2.5~4 分钟）")
                        self.root.after(0, lambda t=t, real_txt=real_txt: (
                            self.set_bubble(steps + "\n⏸️ 长休息：已完成 %d 个关键词，暂停 %.0f 秒 %s\n控制请求频率，避免短时间连续大量请求" % (i, t, real_txt)),
                            self.add_log("风控长休息：%.0f 秒（每 3 关键词）" % t)))
                        self._pausable_sleep(t)
                    # 每扫完一个关键词，同步跑一轮 HR 监听（串行，不并发）
                    _wait_if_paused()
                    if self._stop_requested:
                        break
                    self.root.after(0, lambda kw=kw: self.add_log("关键词「%s」扫完，跑一轮 HR 监听…" % kw))
                    _run_one_chat_round()
                # 停止收尾：用户输入「停止」→ 直接结束，不进入监听/简报
                if self._stop_requested:
                    self._last_run_rec = rec
                    self._prevent_sleep(False)
                    self._guard_tasks("disable")
                    self._set_applying(False)
                    self.root.after(0, lambda: (self.set_bubble(
                        "🛑 已停止，本次投递到此结束。\n点「开始投递」按钮可重新开始。"),
                        self.set_state("闲置")))
                    self.add_log("投递已停止（用户请求）")
                    self._stop_summary_llm(rec, list(self._last_kw_stats), True)
                    return
                self.session["test_run"] = rec
                self._last_run_rec = rec
                # 4/5 真实监听：独立线程运行，主线程可被暂停/停止打断地等待结果
                _wait_if_paused()
                self.root.after(0, lambda: self.set_bubble(
                    steps + "\n✅ 监听 HR 回复：已启动（%d 家公司）…" % (
                        len([c for c in load_greeted_companies(RUN_DIR) if c not in set(baseline)]))))
                _msum = {}

                def _mon_run():
                    try:
                        from boss.boss_chat import run_chat_monitor
                        demo_cfg = dict(self.cfg)
                        demo_cfg["auto_chat_reply"] = False  # 普通对话不自动回复，仅提醒用户
                        _msum.update(run_chat_monitor(
                            config=demo_cfg, skill_dir=RUN_DIR, debug_port=9222,
                            mode="apply" if real else "rehearsal",
                            rounds=1, interval=30.0, baseline_companies=baseline,
                            resume_pdf=self.cfg.get("resume_pdf_path") or None) or {})
                    except Exception as exc:
                        _msum["error"] = str(exc)

                _mt = threading.Thread(target=_mon_run, daemon=True)
                _mt.start()
                while _mt.is_alive():
                    if self._stop_requested:
                        break
                    if self._paused:
                        while self._paused and not self._stop_requested:
                            time.sleep(0.5)
                    else:
                        time.sleep(0.5)
                # 停止投递中监听（现在是串行，不需要停后台线程）
                self._chat_monitor_stop = True
                self.add_log("投递结束，串行监听已随主循环退出")
                # 自动清理浏览器缓存（只清缓存，保留登录 Cookie）
                # 2026-09-17 修复：原只清 Default/ 下 5 个目录，漏掉 profile 根目录下的
                # BrowserMetrics / GPUPersistentCache / GrShaderCache / Crashpad 等。
                try:
                    cleanup_browser_cache(self.add_log)
                except Exception as e:
                    self.add_log("缓存清理跳过：%s" % str(e)[:80])
                # 最后做一轮结束监听
                try:
                    from boss.boss_chat import run_chat_monitor
                    demo_cfg = dict(self.cfg)
                    demo_cfg["auto_chat_reply"] = False
                    _final_sum = run_chat_monitor(
                        config=demo_cfg, skill_dir=RUN_DIR, debug_port=9222,
                        mode="apply" if real else "rehearsal",
                        rounds=1, interval=30.0, baseline_companies=baseline,
                        resume_pdf=self.cfg.get("resume_pdf_path") or None) or {}
                    self.root.after(0, lambda s=dict(_final_sum): self._monitor_summary(s))
                except Exception as e:
                    self.add_log("结束监听异常：%s" % e)

                # 5/5 收尾简报
                _wait_if_paused()
                self._prevent_sleep(False)
                self.root.after(0, lambda: self._test_summary(rec, True, real))
            except Exception as exc:
                self._prevent_sleep(False)
                self._guard_tasks("disable")
                self._set_applying(False)
                self.root.after(0, lambda e=exc: (self.set_bubble("开始投递异常：%s" % e), self.set_state("闲置")))

        threading.Thread(target=_work, daemon=True).start()

    # ---------- 离线重放模式（分流：冒烟存缓存 → 流程用缓存重放，零 BOSS 请求） ----------
    def _set_offline(self, flag: bool) -> None:
        self._offline = flag
        try:
            if self._offline_label is not None:
                self._offline_label.config(
                    text="离线重放 · 零真实请求" if flag else "在线模式 · 达标岗位真实投递",
                    fg="#4E9E7A" if flag else "#C96A35")
            self.add_log("已切换为离线重放模式（岗位读本地缓存，不访问 BOSS）" if flag
                         else "已切换为在线模式（岗位读真实 BOSS）")
        except Exception:
            pass

    def _cached_jobs_path(self):
        return RUN_DIR / "cached_jobs.json"

    def _save_cached_jobs(self, jobs: list) -> None:
        try:
            import json as _json
            data = {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "jobs": jobs}
            self._cached_jobs_path().write_text(
                _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_cached_jobs(self, limit: int = 3) -> list:
        """离线重放：从本地缓存读岗位（冒烟/上次真实抓取的快照）。无缓存时返回内置示例。"""
        import json as _json
        try:
            p = self._cached_jobs_path()
            if p.exists():
                data = _json.loads(p.read_text(encoding="utf-8"))
                jobs = data.get("jobs") or []
                if jobs:
                    return jobs[:limit]
        except Exception:
            pass
        # 内置示例岗位（首次使用离线模式的兜底数据，便于开箱即测）
        # 2026-09-18 修复：格式必须是**四元组**，与 _collect() 的产出
        # （out.append((title, jd, company, href))）以及 _save_cached_jobs 的落盘格式一致。
        # 原先是 dict 列表，而消费方（_run_offline_flow / 投递演练）按四元组解包 ——
        # dict 恰好 4 个键会「解包成功但取到键名」：title="title"、jd="jd"、company="company"，
        # 评分恒 0 且**不抛任何异常**，表现为日志满屏「过滤跳过：title」。
        # 公司名统一加「【示例】」前缀：这些岗位达标后会经 _log_demo_result 落进
        # boss-demo-log.json 的 evaluated 桶。该桶目前**没有消费者** —— 唯一读取它的
        # _load_historical_result_rows 已无任何调用点（方案复核改为不读历史、省 LLM 调用）。
        # 加前缀属于防御性标注：一旦将来接入历史分析或看板展示，可一眼识别非真实数据。
        return [
            ("海外运营经理（TikTok）",
             "负责TikTok海外市场运营策略制定与落地，统筹内容与投放，3年以上出海运营经验，英语流利。",
             "【示例】科技", ""),
            ("海外用户增长负责人",
             "负责欧美市场用户增长，搭建增长团队，熟悉ASO/社媒投放/达人营销，有0到1经验优先。",
             "【示例】出海", ""),
            ("直播运营总监",
             "统筹海外直播业务，搭建直播运营体系，熟悉TikTok直播生态，5年以上直播运营管理经验。",
             "【示例】电商", ""),
        ][:limit]

    def _run_offline_flow(self, rec: dict, real: bool) -> None:
        """离线重放完整投递流程：缓存岗位 → LLM 评分 → 过滤 → 模拟打招呼 → 简报。
        零 BOSS 请求（不拉起浏览器/不登录/不附件简历/不监听）。"""
        import time as _t
        steps = ("【开始投递 · 离线重放】\n⚡ 岗位读本地缓存，零 BOSS 请求"
                 + (" · 真实投递标记忽略" if real else ""))
        self._prevent_sleep(True)
        # 2026-09-18 第 44 轮修复（pyflakes 静态检查发现）：
        # 本方法此前直接用了 load_greeted_companies / _wait_if_paused，
        # 但这两个名字只存在于 cmd_test_run 的局部作用域里
        # （L1885 嵌套函数 / L1893 局部 import）→ 一进入就 NameError。
        from boss.boss_chat import load_greeted_companies

        def _wait_if_paused():
            while self._paused and not self._stop_requested:
                time.sleep(0.5)

        baseline = load_greeted_companies(RUN_DIR)
        keywords = self._plan.get("keywords") or ["海外运营", "海外社媒", "TikTok"]
        greeted = []
        try:
            for i, kw in enumerate(keywords, 1):
                _wait_if_paused()
                if self._stop_requested:
                    break
                jobs = self._fetch_boss_jobs(kw, limit=30)
                if not jobs:
                    self.root.after(0, lambda kw=kw: self.add_log("离线重放：关键词「%s」无缓存岗位，跳过" % kw))
                    continue
                rec["kw"] += 1
                kw_scanned = 0
                kw_applied = 0
                kw_scores = []
                for title, jd, company, _href in jobs:
                    _wait_if_paused()
                    if self._stop_requested:
                        break
                    rec["scan"] += 1
                    kw_scanned += 1
                    try:
                        res = self._score_jd(title, jd, self.cfg, skill_dir=RUN_DIR, use_llm=True)
                    except Exception:
                        continue
                    kw_scores.append(res.total_score)
                    if res.decision == "apply":
                        rec["greet"] += 1
                        kw_applied += 1
                        greeted.append(title)
                        self._log_demo_greet(company, title)  # 白名单（模拟，未真实发送）
                        self.root.after(0, lambda t=title, s=res.total_score: self.add_log(
                            "【离线模拟打招呼】%s（%d分）— 缓存岗位，未真实发送" % (t, s)))
                    else:
                        self.root.after(0, lambda t=title: self.add_log("过滤跳过：%s" % t))
                    self._pausable_sleep(self._pace("after_greet") if res.decision == "apply" else self._pace("skip_job"))
                avg = sum(kw_scores) / len(kw_scores) if kw_scores else 0
                top = max(kw_scores) if kw_scores else 0
                self._last_kw_stats.append(
                    {"kw": kw, "scanned": kw_scanned, "applied": kw_applied,
                     "avg": round(avg, 1), "top": top})
                self.root.after(0, lambda kw=kw, s=kw_scanned, a=kw_applied, avg=avg, top=top: (
                    self.add_log("关键词「%s」有效性（离线重放）：扫描 %d · 达标 %d · 平均 %.0f 分 · 最高 %d 分" % (kw, s, a, avg, top)),
                    self.set_bubble(steps + "\n🔎 换词分析「%s」：\n扫描 %d · 达标 %d · 平均 %.0f 分 · 最高 %d 分" % (kw, s, a, avg, top))))
                if i < len(keywords):
                    self._pausable_sleep(min(self._pace("task_break"), 3.0))  # 离线快跑：任务间休息压到 ≤3s
            if self._stop_requested:
                self._prevent_sleep(False)
                self.root.after(0, lambda: (self.set_bubble("🛑 已停止（离线重放）。"), self.set_state("闲置")))
                self._stop_summary_llm(rec, list(self._last_kw_stats), True)
                return
            rec["summary"] = "offline_replay"
            self.session["test_run"] = rec
            self._last_run_rec = rec
            self._prevent_sleep(False)
            self.root.after(0, lambda r=rec, s=steps: self.set_bubble(
                s + "\n✅ 离线重放完成：扫描 %d 岗位 · LLM %d 次 · 模拟打招呼 %d（未真实发送）\n"
                    "监听已跳过（离线无真实聊天）。说「今日简报」看汇总。" % (r["scan"], r["llm"], r["greet"])))
            self.add_log("离线重放完成：扫描 %d，模拟打招呼 %d（未发送）" % (rec["scan"], rec["greet"]))
        except Exception as exc:
            self._prevent_sleep(False)
            self.root.after(0, lambda e=exc: (self.set_bubble("离线重放异常：%s" % e), self.set_state("闲置")))
        finally:
            self.set_state("闲置")

    def _busy(self) -> bool:
        return self.state in ("分析中", "投递中", "沟通中")

    def cmd_llm_settings(self):
        """LLM API 配置窗口：base_url / api_key / model，保存到 config.json。支持在线拉取模型列表。"""
        import tkinter.ttk as ttk
        import urllib.request, json as _json
        llm = self.cfg.get("llm") or {}
        win = tk.Toplevel(self.root)
        win.title("LLM 设置")
        win.geometry("480x340")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Base URL", font=self.f_body, bg=BG, fg="#2B2622").pack(anchor="w", padx=20, pady=(18, 2))
        e_url = tk.Entry(win, font=self.f_body, width=54, bg="#FFF", fg="#2B2622")
        e_url.pack(padx=20, fill="x")
        e_url.insert(0, llm.get("base_url", ""))

        tk.Label(win, text="API Key", font=self.f_body, bg=BG, fg="#2B2622").pack(anchor="w", padx=20, pady=(10, 2))
        e_key = tk.Entry(win, font=self.f_body, width=54, show="*", bg="#FFF", fg="#2B2622")
        e_key.pack(padx=20, fill="x")
        e_key.insert(0, llm.get("api_key", ""))

        # Model 行：下拉框 + 获取列表按钮
        row_model = tk.Frame(win, bg=BG)
        row_model.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(row_model, text="Model", font=self.f_body, bg=BG, fg="#2B2622").pack(side="left")
        cbo_model = ttk.Combobox(row_model, font=self.f_body, width=38, values=[])
        cbo_model.pack(side="left", padx=(8, 6), fill="x", expand=True)
        cbo_model.set(llm.get("model", ""))

        def fetch_models():
            url = e_url.get().strip().rstrip("/")
            key = e_key.get().strip()
            if not url or not key:
                self.set_bubble("⚠️ 先填 Base URL 和 API Key，再拉模型列表。")
                return
            cbo_model.set("拉取中…")
            try:
                req = urllib.request.Request(
                    url + "/v1/models",
                    headers={"Authorization": "Bearer " + key})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                ids = sorted([m.get("id", "") for m in data.get("data", []) if m.get("id")])
                cbo_model["values"] = ids
                if ids:
                    cbo_model.set(ids[0])
                    self.add_log("LLM 设置：拉到 %d 个模型" % len(ids))
                else:
                    cbo_model.set("（未返回模型列表，可手动填）")
            except Exception as exc:
                cbo_model.set("")
                self.set_bubble("⚠️ 拉取模型列表失败：%s\n可手动填 Model 名。" % str(exc)[:120])

        tk.Button(row_model, text="拉取", font=self.f_chip, bg="#8BC8EA", fg="#0D2A3A",
                  relief="flat", bd=0, cursor="hand2", command=fetch_models).pack(side="right")

        def save():
            url = e_url.get().strip().rstrip("/")
            key = e_key.get().strip()
            model = cbo_model.get().strip()
            if not url or not key:
                self.set_bubble("⚠️ Base URL 和 API Key 必填，Model 可留空。")
                return
            self.cfg.setdefault("llm", {})
            self.cfg["llm"]["base_url"] = url
            self.cfg["llm"]["api_key"] = key
            self.cfg["llm"]["model"] = model
            try:
                (RUN_DIR / "config.json").write_text(_json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            self.set_bubble("✅ LLM 配置已保存：\nURL=%s\nModel=%s\n（Key 已隐藏）" % (url, model or "默认"))
            win.destroy()

        tk.Button(win, text="保存", font=self.f_chip, bg="#94D8C3", fg="#1A3A2A",
                  relief="flat", bd=0, cursor="hand2", command=save).pack(pady=20)

    def cmd_smoke(self):
        """冒烟验证：真实浏览器链路一次性验证（登录→附件简历→抓1关键词3条→存缓存）。
        覆盖全部浏览器链路，每天最多 1 次；其余用缓存重放，零 BOSS 请求。"""
        if self._offline:
            self.set_bubble("当前是离线重放模式，冒烟需要真实浏览器。\n回复「在线模式」切换后再点「冒烟」。")
            return
        if self._busy():
            self.set_bubble("正在忙其他任务，稍后再点「冒烟」。")
            return
        self.set_state("分析中")
        self.set_act("think")
        self.add_log("冒烟验证启动：登录 → 附件简历 → 抓取 1 关键词 3 条 → 存缓存")
        self.root.after(0, lambda: self.set_bubble(
            "🧪 冒烟验证开始（约 30~60 秒）：\n① 拉起浏览器 → ② 登录检测 → ③ 附件简历弹窗 → ④ 抓取岗位存缓存"))
        threading.Thread(target=self._smoke_work, daemon=True).start()

    def _smoke_work(self):
        import time as _t
        from agent.shared import is_cdp_port_ready, connect_browser
        try:
            if not is_cdp_port_ready(9222):
                self.add_log("自动拉起 9222 投递浏览器")
                if not self._launch_browser():
                    self.root.after(0, lambda: (self.set_bubble("投递浏览器启动失败，冒烟中止。"), self.set_state("闲置")))
                    return
            tab = connect_browser(9222).latest_tab
            if not self._ensure_boss_login(tab):
                self.root.after(0, lambda: (self.set_bubble("冒烟中止：BOSS 未登录，请扫码登录后重试。"), self.set_state("闲置")))
                return
            resumes = self._list_boss_resumes(tab)
            if resumes == "blocked":
                self.root.after(0, lambda: (self.set_bubble("冒烟中止：BOSS 访问受限（403 风控），请稍后再试。"), self.set_state("闲置")))
                return
            if resumes is None:
                self.root.after(0, lambda: (self.set_bubble("冒烟中止：附件简历弹窗不可用，请检查浏览器聊天页。"), self.set_state("闲置")))
                return
            jobs = self._fetch_boss_jobs("海外运营", limit=3)
            if not jobs:
                self.root.after(0, lambda: (self.set_bubble("冒烟完成但未抓到岗位（可能页面结构/网络），其余链路已通过。"), self.set_state("闲置")))
                return
            self._save_cached_jobs(jobs)
            n = len(jobs)
            names = "、".join(j[0] for j in jobs[:3])
            self.root.after(0, lambda names=names, n=n, rn=len(resumes): (
                self.set_bubble("✅ 冒烟通过！全链路正常：登录✓ 附件简历(%d份)✓ 抓取 %d 条✓\n已存缓存，回复「离线模式」即可用缓存重放（零 BOSS 请求）。\n岗位：%s" % (rn, n, names)),
                self.add_log("冒烟通过：登录✓ 附件简历%d份✓ 抓取%d条✓ 已存缓存" % (rn, n))))
        except Exception as exc:
            self.root.after(0, lambda e=exc: (self.set_bubble("冒烟异常：%s" % e), self.set_state("闲置")))
        finally:
            self.set_state("闲置")

    def _fetch_boss_jobs(self, keyword: str, limit: int = 3) -> list:
        """从 9222 浏览器读取 BOSS 真实岗位，返回 [(title, jd_text, company, href)]。
        离线重放模式：读本地缓存岗位（零 BOSS 请求）。

        内置两个加固：
        1) 卡片级标题预过滤：命中 title_exclude_keywords 直接跳过（不开详情、不调 LLM）
        2) Chrome 掉线自动恢复：9222 未监听 → 拉起 Chrome → 重连 → 登录校验 → 清理 tab → 重试一次
        """
        import time
        if self._offline:
            jobs = self._load_cached_jobs(limit)
            self.add_log("离线重放：读缓存岗位 %d 条（关键词「%s」，零 BOSS 请求）" % (len(jobs), keyword))
            return jobs
        from agent.shared import (connect_browser, find_all, build_boss_search_url,
                                             normalize_text, keyword_in_text, is_cdp_port_ready,
                                             cleanup_tabs)
        from boss import boss_apply

        def _once():
            from agent.shared import smooth_scroll
            browser = connect_browser(9222)
            tab = browser.latest_tab
            city_name = self.cfg.get("target_city", "广州")
            city_code = get_city_code(city_name)
            if not city_code:
                self.add_log("城市「%s」不在支持列表，已中止本次搜索（支持：%s）"
                             % (city_name, "、".join(CITY_CODES)))
                self.root.after(0, lambda c=city_name: (self.set_bubble(
                    "⚠️ 城市「%s」不在支持列表里，我没去搜（不会偷偷换成别的城市）。\n"
                    "请在看板「设置」里改成一个支持的城市。" % c), self.set_state("闲置")))
                return []
            salary_max = self.cfg.get("min_salary_high_k") or self._plan.get("salary_high") or 0
            search_url = build_boss_search_url(keyword, city_code, salary_max)
            self.add_log("打开搜索页：关键词「%s」→ %s" % (keyword, search_url))
            tab.get(search_url)
            time.sleep(5)
            out = []
            _seen = set()
            random_skip_remaining = 0
            block_kws = [k for k in [*(self.cfg.get("title_exclude_keywords") or []),
                                      *(self.cfg.get("exclude_keywords") or [])] if k]

            def _collect(cards):
                nonlocal random_skip_remaining
                for card in cards:
                    if len(out) >= limit or self._stop_requested:
                        return
                    while self._paused and not self._stop_requested:
                        time.sleep(0.4)
                    if self._stop_requested:
                        return
                    try:
                        # 2026-09-24 SLOWTRACE：读卡片计时（只在慢时打日志）
                        _t_st = time.time()
                        info = boss_apply.extract_card_info(card)
                        if time.time() - _t_st > 5:
                            self.add_log("⏱ 读卡片耗时 %.1fs" % (time.time() - _t_st))
                        title = info["title"]
                        if not title:
                            continue
                        _key = normalize_text((title or "") + (info.get("company") or ""))
                        if _key in _seen:
                            continue
                        _seen.add(_key)
                        # 卡片级标题预过滤：命中排除词（TikTok/电商/日结等）直接跳过，
                        # 不点详情、不调 LLM。只匹配岗位标题，不匹配 JD 正文。
                        _title_clean = normalize_text(title)
                        _blocked = None
                        for _kw in block_kws:
                            if keyword_in_text(_kw, _title_clean):
                                _blocked = _kw
                                break
                        if _blocked:
                            self.add_log("标题预过滤跳过：%s（命中排除词：%s，未点开详情）" % (title, _blocked))
                            self._record_ledger_action("skip", "title_filter", {"job": title, "company": info.get("company") or "", "reason": _blocked})
                            self._st["block_hits"] += 1
                            continue
                        jd = info["raw_text"]
                        salary_text = info.get("salary") or ""
                        company = info.get("company") or "未知公司"
                        # 2026-09-18 新增：公司名屏蔽，与投递主循环保持同一套规则
                        _co_kw = shared.company_blocked(company, self.cfg)
                        if _co_kw:
                            self.add_log("公司名屏蔽跳过：%s | %s（命中：%s）" % (
                                company, title, _co_kw))
                            self._record_ledger_action("skip", "company_filter", {"job": title, "company": company, "reason": _co_kw})
                            self._st["block_hits"] += 1
                            continue
                        # 2026-09-19 T：**随机跳过提前** —— 在打开详情页之前决定。
                        # 原实现放在读 JD 之后，等于「先花钱再决定不买」，
                        # 实测 110 个详情页里 34 个是这么白打开的。
                        if random_skip_remaining > 0 or random.random() < 0.10:
                            if random_skip_remaining <= 0:
                                random_skip_remaining = random.randint(1, 4)
                            random_skip_remaining -= 1
                            self.add_log("随机跳过岗位：%s" % title)
                            self._record_ledger_action("skip", "random", {"job": title, "company": company})
                            continue
                        if info["href"]:
                            try:
                                # 加锁：和监听线程不同时操作浏览器
                                # 2026-09-24 SLOWTRACE：这条链路逐步计时，定位静默空档
                                _t_st = time.time()
                                self._browser_lock.acquire()
                                if time.time() - _t_st > 3:
                                    self.add_log("⏱ 等浏览器锁 %.1fs" % (time.time() - _t_st))
                                try:
                                    self.add_log("打开详情页：%s → %s" % (title, info["href"]))
                                    _t_st = time.time()
                                    dt = browser.new_tab(info["href"])
                                    if time.time() - _t_st > 8:
                                        self.add_log("⏱ 打开详情页耗时 %.1fs" % (time.time() - _t_st))
                                    time.sleep(3)
                                    self.add_log("  → 读 JD 文本 + 薪资信息")
                                    _t_st = time.time()
                                    jd = boss_apply.extract_detail_text(dt) or jd
                                    if time.time() - _t_st > 8:
                                        self.add_log("⏱ 读 JD 耗时 %.1fs" % (time.time() - _t_st))
                                    sal_el = shared.find_first(dt, ["css:.salary", "css:.job-salary"], timeout=0.8)
                                    salary_text = shared.safe_text(sal_el) or salary_text
                                    self.add_log("  → 详情页读完，关闭 tab（薪资：%s）" % salary_text)
                                    _t_st = time.time()
                                    dt.close()
                                    if time.time() - _t_st > 5:
                                        self.add_log("⏱ 关闭 tab 耗时 %.1fs" % (time.time() - _t_st))
                                finally:
                                    self._browser_lock.release()
                            except Exception:
                                pass
                        content_blocked = shared.excluded_keyword_for_job(title, jd, self.cfg)
                        if content_blocked:
                            self.add_log("岗位预过滤跳过：%s（命中排除词：%s，未调用 LLM）" % (title, content_blocked))
                            self._record_ledger_action("skip", "content_filter", {"job": title, "company": company, "reason": content_blocked})
                            self._st["block_hits"] += 1
                            continue
                        salary_reason = boss_apply.salary_policy_reason(salary_text, self.cfg)
                        if salary_reason:
                            self.add_log("薪资预过滤跳过：%s（%s，未调用 LLM）" % (title, salary_reason))
                            self._record_ledger_action("skip", "salary_filter", {"job": title, "company": company, "reason": salary_reason})
                            continue
                        out.append((title, jd or title, company, info["href"] or ""))
                        # 2026-09-18 第 44 轮：入选进度反馈（每 5 个一次）
                        if len(out) % 5 == 0:
                            self.add_log("收集进度：已入选 %d/%d 个（收集完成后统一评分）" % (len(out), limit))
                            self._emit_progress(self._live_rec or {}, len(out), True)
                    except Exception as e:
                        self.add_log("卡片解析异常跳过：%s" % str(e)[:80])
                        continue

            # 2026-09-18 第 44 轮：收集期很长且此前无任何进度反馈，
            # 用户只看到浏览器翻详情页，会以为卡住 / 以为已经停了。先说明阶段。
            self.add_log("关键词「%s」开始收集岗位（目标 %d 个）：先读岗位详情，收集完成后才统一评分与投递" % (keyword, limit))
            # 第一抓：当前视口卡片
            cards = find_all(tab, boss_apply.CARD_LOCATORS, timeout=3.0)
            if not cards:
                cards = find_all(tab, ["css:[class*=job-card]"], timeout=2.0)
            _collect(cards)
            # 滚动模拟：分步滚动（每步随机像素、步间随机停顿），
            # 边看边往下翻再抓取，直到抓满 limit 或停止/暂停
            for _s in range(30):
                if len(out) >= limit or self._stop_requested:
                    break
                try:
                    smooth_scroll(tab, steps=3, min_pixel=420, max_pixel=860)
                except Exception:
                    pass
                time.sleep(self._pace("scroll"))
                cards = find_all(tab, boss_apply.CARD_LOCATORS, timeout=3.0)
                if not cards:
                    cards = find_all(tab, ["css:[class*=job-card]"], timeout=2.0)
                _collect(cards)
            self.add_log("关键词「%s」岗位收集完毕：共 %d 个（目标 %d）" % (keyword, len(out), limit))
            return out

        try:
            return _once()
        except Exception as exc:
            # Chrome 掉线自动恢复（投递内）：PageDisconnected / 连接被拒等
            if not is_cdp_port_ready(9222):
                self.add_log("检测到投递浏览器掉线，正在自动恢复…")
                self.root.after(0, lambda: self.set_bubble(
                    "⚠️ 投递浏览器掉线，自动恢复中（拉起 Chrome → 重连 → 登录校验 → 清理标签页）…"))
                if not self._launch_browser():
                    self.root.after(0, lambda: self.set_bubble(
                        "浏览器自动恢复失败：9222 仍不在线。请手动打开投递浏览器后重试。"))
                    return []
                try:
                    tab = connect_browser(9222).latest_tab
                    if not self._quick_login_check(tab):
                        self._alert_login_lost()
                        self.root.after(0, lambda: self.set_bubble(
                            "浏览器已恢复，但 BOSS 登录已失效，请扫码登录后重新点「开始投递」。"))
                        return []
                    try:
                        cleanup_tabs(connect_browser(9222),
                                     keep_urls=("https://www.zhipin.com/web/geek/chat",),
                                     max_tabs=5)
                    except Exception:
                        pass
                except Exception:
                    pass
                self.add_log("浏览器已恢复，重试关键词「%s」…" % keyword)
                self._st["retry_count"] += 1
                try:
                    return _once()
                except Exception as exc2:
                    self.add_log("恢复后重试仍失败：%s" % exc2)
                    return []
            self.add_log("读取岗位失败（非掉线）：%s" % exc)
            return []

    def _log_demo_greet(self, company: str, title: str, real: bool = False) -> None:
        """记录一次打招呼（写进公司名白名单，供 HR 监听判定「是不是我们投的」）。

        2026-09-22 GREET1：原实现**无条件**写 preview + mode="rehearsal"，
        连真实投递（`if real:` 分支的那次调用）也被记成演练 ——
        于是 `records.applied` 永远是空的，`load_greeted_companies()` 返回 0 条，
        HR 消息被判成「不是我们方案打的招呼」→ 只进 hr_inbound（不进结果统计），
        outcomes.json 永不生成 → 分析报告里永远看不到 HR 回复结果。

        现在按 real 分流：真实投递 → applied（正式白名单）；
        离线重放 / 演练 → preview（行为不变）。
        """
        try:
            import json as _json
            p = RUN_DIR / "boss-demo-log.json"
            data = {}
            if p.exists():
                data = _json.loads(p.read_text(encoding="utf-8"))
            bucket = "applied" if real else "preview"
            rows = data.setdefault("records", {}).setdefault(bucket, [])
            rows.append({"company": company or "未知公司", "title": title,
                         "mode": "apply" if real else "rehearsal"})
            p.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            # 2026-09-22 GREETALL：同时写一份**永不被清**的持久白名单，
            # 否则本轮结束（applied 被清）后，隔天到达的 HR 回复就认不出来源。
            if real:
                self._add_greeted_all(company)
        except Exception:
            pass

    def _mark_job_applied(self, keyword: str, title: str, company: str) -> None:
        """把「这条岗位真的投出去了」标到本轮报告明细上（2026-09-22 OUTCOME1）。

        只标记，不改任何判断。用途：让「关键词 → 投过的岗位 → HR 结果」
        这条归因链能对上；否则只能按公司名 join，同公司的其他岗位会被一起算上。
        """
        try:
            for row in reversed(self._run_jobs or []):
                if (str(row.get("job") or "") == str(title or "")
                        and str(row.get("company") or "") == str(company or "")):
                    row["applied"] = True
                    return
        except Exception:
            pass

    def _log_demo_result(self, keyword: str, title: str, company: str, result) -> None:
        """记录桌面流程每个已评分岗位，供下一轮方案优化读取。"""
        try:
            import json as _json
            p = RUN_DIR / "boss-demo-log.json"
            data = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            records = data.setdefault("records", {})
            evaluated = records.setdefault("evaluated", [])
            _llm_ok = bool(getattr(result, "llm_ok", False))
            evaluated.append({
                "keyword": keyword, "job": title, "company": company or "未知公司",
                "score": int(getattr(result, "total_score", 0) or 0),
                "decision": getattr(result, "decision", ""),
                "reason": str(getattr(result, "reason", "") or "")[:120],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                # 2026-09-18 复盘报告：补结构化字段
                # （旧记录没有这些键，读取方必须用 .get 兜底）
                "rule": int(getattr(result, "rule_score", 0) or 0),
                "llm": int(getattr(result, "llm_score", 0) or 0),
                "llm_reason": str(getattr(result, "llm_reason", "") or "")[:80],
                "hits": list(getattr(result, "skill_hits", []) or []),
                "role": getattr(result, "role_hit", None),
                "llm_ok": _llm_ok,
                # 2026-09-19 A3：LLM 证据与不足（旧记录没有这两个键）
                "evidence": list(getattr(result, "llm_evidence", []) or [])[:3],
                "gaps": list(getattr(result, "llm_gaps", []) or [])[:2],
            })
            # 2026-09-22 KEEPALL：超上限**归档**，不再丢弃最老的
            if len(evaluated) > 1000:
                self._archive_append("evaluated", evaluated[:-1000])
            records["evaluated"] = evaluated[-1000:]
            # 复盘报告只收「LLM 真评分成功」的岗位（用户 2026-09-18 裁决）：
            # LLM 没评上 / 走启发式兜底 / 被规则预过滤挡下的，都不进报告明细。
            # 报告明细**只存总分与「为什么」**（用户 2026-09-18 裁决）：
            # 权重拆分（规则分 / LLM 补分 / 阈值 / +N 加分项）是内部实现，
            # 不给主人看 —— 他要的是「这岗多少分、为什么」，不是计分公式。
            # 保留 role/hits 是因为它们描述「哪里匹配上了」，属解释而非权重。
            # 收录条件：LLM 真评分成功 **或** 命中两周缓存。
            #   · 缓存命中 → 分数是之前 LLM 真评过的，只是复用 → 应当收录
            #   · 启发式兜底（LLM 没评上）→ 不收录（用户 2026-09-18 裁决）
            if _llm_ok or bool(getattr(result, "from_cache", False)):
                self._run_jobs.append({
                    "job": str(title)[:60],
                    "company": str(company or "未知公司")[:40],
                    "kw": str(keyword)[:30],
                    "score": int(getattr(result, "total_score", 0) or 0),
                    "decision": getattr(result, "decision", ""),
                    "why": str(getattr(result, "llm_reason", "") or "")[:80],
                    "hits": list(getattr(result, "skill_hits", []) or []),
                    "role": getattr(result, "role_hit", None),
                    # 2026-09-19 A3：证据与不足 —— 报告里展示「为什么」
                    "evidence": list(getattr(result, "llm_evidence", []) or [])[:3],
                    "gaps": list(getattr(result, "llm_gaps", []) or [])[:2],
                    # 2026-09-22 OUTCOME1：这条岗位**真的投出去了**吗
                    # （投递成功时由 _mark_job_applied 置 True）。
                    # 报告行是「评分过」就算，不等于投过 —— 两者必须分开。
                    "applied": False,
                    "t": time.strftime("%H:%M:%S"),
                })
            p.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- 两周岗位去重（演练侧，对齐 9-08 #5：仅 LLM 真评分成功才计入） ----------
    def _job_seen_recently(self, key: str) -> bool:
        try:
            import json as _json
            p = RUN_DIR / "boss-demo-seen.json"
            if not p.exists():
                return False
            data = _json.loads(p.read_text(encoding="utf-8"))
            now = time.time()
            for item in data.get("jobs", []):
                if item.get("key") == key and now - item.get("ts", 0) < 14 * 86400:
                    return True
        except Exception:
            pass
        return False

    def _get_cached_score(self, key: str):
        """如果这个岗位在两周内已评估过，直接返回之前的评分结果，不用再调用 LLM"""
        try:
            import json as _json
            p = RUN_DIR / "boss-demo-seen.json"
            if not p.exists():
                return None
            data = _json.loads(p.read_text(encoding="utf-8"))
            now = time.time()
            for item in data.get("jobs", []):
                if item.get("key") == key and now - item.get("ts", 0) < 14 * 86400:
                    if "score" in item:
                        # 构造一个类似 ScoreResult 的对象
                        class CachedScore:
                            def __init__(self, s):
                                self.total_score = s.get("total_score", 0)
                                self.rule_score = s.get("rule_score", 0)
                                self.llm_score = s.get("llm_score", 0)
                                self.decision = s.get("decision", "")
                                self.reason = s.get("reason", "")
                                self.llm_reason = s.get("llm_reason", "")
                                self.llm_ok = False  # 缓存的不算真实调用 LLM
                                # 但它的分数是**之前 LLM 真评过的**，只是复用。
                                # 复盘报告据此与「启发式兜底」区分开（2026-09-18）。
                                self.from_cache = True
                        return CachedScore(item["score"])
        except Exception:
            pass
        return None

    def _mark_job_seen(self, key: str, score_result=None) -> None:
        # 启发式兜底（LLM没真调用）不进缓存，下次重新调LLM评分
        if score_result is not None and not getattr(score_result, "llm_ok", False):
            return
        try:
            import json as _json
            p = RUN_DIR / "boss-demo-seen.json"
            data = {"jobs": []}
            if p.exists():
                data = _json.loads(p.read_text(encoding="utf-8"))
            now = time.time()
            jobs = [x for x in data.get("jobs", [])
                    if x.get("key") != key and now - x.get("ts", 0) < 14 * 86400]
            # 记录 key + 时间 + 完整评分结果
            entry = {"key": key, "ts": now}
            if score_result is not None:
                entry["score"] = {
                    "total_score": getattr(score_result, "total_score", 0),
                    "rule_score": getattr(score_result, "rule_score", 0),
                    "llm_score": getattr(score_result, "llm_score", 0),
                    "decision": getattr(score_result, "decision", ""),
                    "reason": getattr(score_result, "reason", ""),
                    "llm_reason": getattr(score_result, "llm_reason", ""),
                }
            jobs.append(entry)
            data["jobs"] = jobs[-500:]
            p.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _list_boss_resumes(self, tab) -> list:
        """读取 BOSS 账号已上传的附件简历列表（聊天页→发简历弹窗→解析→ESC 关闭）。
        返回 [{"name":..., "desc":...}]；未登录返回 []；弹窗打不开返回 None。"""
        import time as _t
        from boss import boss_chat
        try:
            # 优化：已在 chat 页就不重复 get（减少刷新次数，避免频繁刷新）
            cur_url = (tab.url or "").lower()
            if "/web/geek/chat" not in cur_url:
                tab.get("https://www.zhipin.com/web/geek/chat")
                _t.sleep(5)
            else:
                _t.sleep(2)  # 已在 chat 页，短等待让 SPA 稳定
            low = (tab.url or "").lower()
            if "login" in low or "zhipin.com/login" in low:
                return []
            # 风控 403：IP/账号被 BOSS 临时限制访问（如「访问受限」「403」页面）
            if "403" in low or "passport/zp" in low:
                try:
                    _body = (shared.safe_text(tab.ele("css:body", timeout=2.0)) or "")
                except Exception:
                    _body = ""
                if "访问受限" in _body or "异常行为" in _body:
                    self.add_log("BOSS 访问受限（403 风控）：「%s」" % (_body[:80].replace("\n", " ") or low))
                    return "blocked"
            # 不固定第一个会话：部分会话的「发简历」按钮会因职位状态而 disabled，
            # 逐个探测当前已加载的会话，找到任一可用入口后再打开简历弹窗。
            try:
                items = tab.eles("css:li[role=listitem]", timeout=2.0) or []
            except Exception:
                items = []
            opened = False
            probe_items = items[:50]
            for item in probe_items:
                try:
                    item.click()
                    _t.sleep(1.2)
                    probe_url = (tab.url or "").lower()
                    probe_body = shared.safe_text(tab.ele("css:body", timeout=1.0)) or ""
                    if ("403" in probe_url or "passport/zp" in probe_url
                            or "访问受限" in probe_body or "异常行为" in probe_body
                            or "安全验证" in probe_body):
                        self.add_log("切换聊天会话时检测到 BOSS 风控，停止附件简历探测")
                        return "blocked"
                    if boss_chat.click_send_resume_button(tab):
                        opened = True
                        break
                except Exception:
                    continue
            if not opened:
                self.add_log("附件简历弹窗不可用：已探测 %d 个会话仍未找到可用「发简历」按钮" % len(probe_items))
                return None
            _t.sleep(2)
            dialog = boss_chat.find_first(tab, boss_chat.CHOOSE_DIALOG, timeout=3.0)
            if dialog is None:
                _t.sleep(1.5)  # 弹窗渲染慢：多等一次再查，避免误判
                dialog = boss_chat.find_first(tab, boss_chat.CHOOSE_DIALOG, timeout=2.5)
            if dialog is None:
                try:
                    tab.actions.key_down("ESCAPE")
                    tab.actions.key_up("ESCAPE")
                except Exception:
                    pass
                self.add_log("附件简历弹窗不可用：已点「发简历」但弹窗未出现（等待超时，可能加载慢或 BOSS 结构变更）")
                return None
            items = dialog.eles("css:.resume-list .list-item", timeout=1.5)
            if not items:
                items = dialog.eles("css:li.list-item", timeout=1.5)
            out = []
            for it in items:
                name = (boss_chat.safe_text(boss_chat.find_first(it, ["css:.resume-name"], timeout=0.5)) or "").strip()
                desc = (boss_chat.safe_text(boss_chat.find_first(it, ["css:.item-desc"], timeout=0.5)) or "").strip()
                if name:
                    out.append({"name": name, "desc": desc})
            try:
                tab.actions.key_down("ESCAPE")
                tab.actions.key_up("ESCAPE")
            except Exception:
                pass
            return out
        except Exception:
            return None

    def _find_local_resume(self, name: str) -> str:
        """在 run 目录附近查找与 BOSS 附件同名的本地简历文件，用于上传兜底。"""
        for d in (RUN_DIR, RUN_DIR.parent, RUN_DIR.parent / "run"):
            try:
                cand = Path(d) / name
                if cand.exists():
                    return str(cand)
            except Exception:
                continue
        return ""

    def _save_resume_send_config(self, name: str, pdf_path: str) -> bool:
        """把「要发送的附件简历」写入 skill 的 config.json，真实投递脚本同步生效。"""
        import json as _json
        try:
            p = RUN_DIR / "config.json"
            cfg = _json.loads(p.read_text(encoding="utf-8"))
            cfg["resume_send_name"] = name
            if pdf_path:
                cfg["resume_pdf_path"] = pdf_path
            p.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self.cfg = shared.load_config(RUN_DIR)
            return True
        except Exception:
            return False

    def _show_resume_choice_panel(self, resumes: list) -> None:
        """主对话框气泡正下方显示可点击的简历选择列表。"""
        self._hide_resume_choice_panel()
        p = tk.Frame(self.outer, bg="#FBEBDD", highlightbackground="#E4DDD0", highlightthickness=1)
        tk.Label(p, text="🐱 请选择 BOSS 要简历时发送哪一份：", font=self.f_chip,
                 bg="#FBEBDD", fg="#2B2622").pack(anchor="w", padx=10, pady=(6, 2))
        for i, r in enumerate(resumes):
            desc = (r.get("desc") or "").replace("更新于", "更新于 ")
            txt = "%d. %s（%s）" % (i + 1, r["name"], desc)
            tk.Button(p, text=txt, font=self.f_body, bg="#FFFFFF", fg="#2B2622",
                      activebackground="#F4B393", activeforeground="#FFFFFF",
                      relief="flat", bd=0, highlightbackground="#E4DDD0", highlightthickness=1,
                      cursor="hand2", justify="left", anchor="w", wraplength=320,
                      command=lambda s=r: self._on_resume_choice_click(s)
                      ).pack(fill="x", padx=10, pady=3, ipady=4)
        # 修改3：附件简历硬门槛——没有"跳过/默认"，必须用户选一份（哪怕只有一份）
        tk.Label(p, text="⚠ 必须点选一份（无默认、不可跳过）", font=self.f_small, bg="#FBEBDD",
                 fg="#C2575A").pack(anchor="w", padx=10, pady=(2, 8))
        p.pack(fill="x", padx=14, pady=(0, 8), before=self._chip_row)
        self._choice_panel = p
        # 窗口大小固定，不随选项面板变化
        # try:
        #     self.log_box.configure(height=2)
        # except Exception:
        #     pass
        # try:
        #     x, y = self._bottom_right(360, 580)
        #     self.root.geometry("360x580+%d+%d" % (x, y))
        # except Exception:
        #     pass

    def _hide_resume_choice_panel(self) -> None:
        if self._choice_panel is not None:
            try:
                self._choice_panel.destroy()
            except Exception:
                pass
            self._choice_panel = None
        # 窗口大小固定，不随选项面板变化
        # try:
        #     self.log_box.configure(height=5)
        # except Exception:
        #     pass
        # try:
        #     x, y = self._bottom_right(360, 462)
        #     self.root.geometry("360x462+%d+%d" % (x, y))
        # except Exception:
        #     pass

    def _on_resume_choice_click(self, sel: dict) -> None:
        self._resume_choice_waiting = False
        self._resume_choice_selected = sel["name"]
        pdf = self._find_local_resume(sel["name"])
        self._save_resume_send_config(sel["name"], pdf)
        self._hide_resume_choice_panel()
        self.set_bubble("✅ 已选择：BOSS 要简历时发送「%s」%s\n继续跑投递流程…" % (
            sel["name"], "（本地文件已匹配）" if pdf else ""))
        self.add_log("已选择附件简历：%s" % sel["name"])

        # 2026-09-20 CAT：登录已确认 + 简历已选好 → 桌宠切「开始工作」素材
        self._emit_pet_state("work_start")
    def _on_resume_choice_skip(self) -> None:
        self._resume_choice_waiting = False
        self._resume_choice_selected = "__skip__"
        self._hide_resume_choice_panel()
        self.set_bubble("已跳过简历选择，发送时用默认。")
        self.add_log("用户跳过附件简历选择")

    def _ensure_resume_send_choice(self, tab) -> bool:
        """登录后检测 BOSS 附件简历，让用户选择发送哪一份（存 config）。
        每次启动都真实检测弹窗；上次选择仍在列表中→自动沿用（已核实）；
        无附件/弹窗不可用→跳过；选择超时→返回 False。"""
        import time as _t
        c = self.cfg
        resumes = self._list_boss_resumes(tab)
        if resumes == "blocked":
            # 9-10 整改③：风控硬停止 → 写 risk_blocked.flag，停止一切自动动作（不再反复探测）
            try:
                (RUN_DIR / "risk_blocked.flag").write_text("risk-blocked", encoding="utf-8")
            except Exception:
                pass
            # BOSS 风控 403：IP/账号临时受限，非代码故障——明确提示并暂停，等恢复
            self.root.after(0, lambda: (self.set_bubble(
                "❌ BOSS 当前访问受限（风控临时限制，403 页面）。\n"
                "已自动写入风控停止标记（run/risk_blocked.flag），一切动作暂停。\n"
                "一般次日自动恢复正常；确认账号恢复后，删除该文件再重新点「开始投递」。"),
                self.add_log("BOSS 403 风控限制：已写 risk_blocked.flag，附件简历环节暂停（不跳过）")))
            return False
        if resumes is None:
            # 弹窗不可用 = 故障：附件简历是投递前必过环节，流程暂停，不允许进程决定跳过
            self.root.after(0, lambda: (self.set_bubble(
                "❌ 附件简历弹窗不可用（未找到「发简历」按钮或弹窗未弹出）。\n"
                "附件简历是投递前的必要确认环节，流程已暂停。\n"
                "请在浏览器手动确认聊天页可点「发简历」，然后重新点「开始投递」。"),
                self.add_log("附件简历弹窗不可用，流程暂停（不跳过）")))
            return False
        if not resumes:
            # 新增情况2：账号无附件简历 → LLM 引导上传 → 用户回复传好 → 重检 → 落入门禁C
            if not self._wait_resume_upload(tab):
                return False
            resumes = self._list_boss_resumes(tab)
            if not resumes or resumes in (None, "blocked"):
                self.root.after(0, lambda: (self.set_bubble(
                    "❌ 重检后仍未检测到附件简历，流程暂停。\n请按上面指引上传后重新点「开始投递」。"),
                    self.add_log("附件简历重检未通过，流程暂停（不跳过）")))
                return False
            self.root.after(0, lambda: (self.set_bubble(
                "✅ 已检测到你的附件简历（%d 份），请选择发送哪一份：" % len(resumes)),
                self.add_log("附件简历重检通过：检测到 %d 份" % len(resumes))))
        # 真正检测完成：上次选择仍在账号中 → 自动沿用并提示已核实
        last = (c.get("resume_send_name") or "").strip()
        if last:
            for r in resumes:
                if r["name"] == last:
                    self.root.after(0, lambda n=last: (
                        self.set_bubble("✅ 本次已真实检测附件简历：账号中仍存在「%s」，沿用上次选择。" % n),
                        self.add_log("附件简历已重新检测并沿用：%s" % n)))
                    # 2026-09-20 CAT4：补「沿用」路径的钩子（原 hook 只挂了手动选择）
                    # ⚠️ 缩进 20 空格（`)))` 已闭合 lambda，回到 for 循环体层级）
                    self._emit_pet_state("work_start")
                    return True
        lines = "\n".join("%d. %s（%s）" % (i + 1, r["name"], r["desc"]) for i, r in enumerate(resumes))
        self._resume_choice_list = resumes
        self._resume_choice_selected = None
        self._resume_choice_waiting = True
        _bubble = "检测到 %d 份附件简历，点击下方选择 BOSS 要简历时发送哪一份：%s" % (
            len(resumes), ("\n（上次选择「%s」已不在账号中，请重新选择）" % last) if last else "")
        self._last_choice_bubble = _bubble
        self.root.after(0, lambda: (self.set_state("投递中"),
            self.set_bubble(_bubble),
            self.add_log("等待用户选择附件简历"),
            self._show_resume_choice_panel(resumes)))
        # 环节④停留规则：没选简历就一直停在这个环节，直到三分支——
        # ①用户喊停（_stop_requested）②重新上传简历（cmd_resume_file 会置 _stop_requested 跳出）③用户上传并告知→重选完进下一步
        waited = 0.0
        while self._resume_choice_waiting:
            if self._stop_requested:  # 用户停止 / 重传简历 → 立即退出等待
                self._resume_choice_waiting = False
                self._resume_choice_selected = None
                break
            if self._paused:  # 暂停期间不消耗等待时间
                _t.sleep(0.5)
                continue
            waited += 0.5
            _t.sleep(0.5)
        self._resume_choice_waiting = False
        self.root.after(0, self._hide_resume_choice_panel)
        return self._resume_choice_selected is not None

    def cmd_boss_resumes(self):
        """检测 BOSS 账号已上传的附件简历。"""
        if self.state == "分析中":
            self.set_bubble("爬爬正在忙上一个任务，等它做完再点哦～")
            return
        # 浏览器统一门禁：方案未确认（未回复 OK）→ 不进入 BOSS 页面
        if not self._browser_gate():
            return
        self.set_state("分析中")
        self.set_act("think")
        self.set_bubble("正在读取你 BOSS 账号里的附件简历…")
        self.add_log("开始检测 BOSS 附件简历")

        def _work():
            from agent.shared import is_cdp_port_ready, connect_browser
            if not is_cdp_port_ready(9222):
                self.add_log("自动拉起 9222 投递浏览器")
                if not self._launch_browser():
                    self.root.after(0, lambda: (self.set_bubble("投递浏览器启动失败，请稍后重试。"), self.set_state("闲置")))
                    return
            try:
                tab = connect_browser(9222).latest_tab
                resumes = self._list_boss_resumes(tab)
            except Exception as exc:
                self.root.after(0, lambda e=exc: (self.set_bubble("读取失败：%s" % e), self.set_state("闲置")))
                return

            def _done():
                self.set_act("sit")
                if resumes == "blocked":
                    self.set_bubble("BOSS 当前访问受限（风控临时限制，403 页面）。\n一般次日自动恢复正常，请稍后再试。")
                elif resumes is None:
                    self.set_bubble("未能打开 BOSS 选简历弹窗（可能没有进行中的会话，或页面结构变化）。\n请先进入一个 BOSS 会话再试。")
                elif not resumes:
                    self.set_bubble("已登录 BOSS，但账号里还没有附件简历。\n可以在 BOSS 聊天里上传一份简历后再来检测。")
                else:
                    self._resume_choice_list = resumes
                    self._resume_choice_selected = None
                    self._resume_choice_waiting = True
                    self.set_bubble("检测到 %d 份附件简历，请在弹出的窗口里点击选择发送哪一份：" % len(resumes))
                    self._last_choice_bubble = "检测到 %d 份附件简历，请在弹出的窗口里点击选择发送哪一份：" % len(resumes)
                    self.add_log("等待用户选择附件简历")
                    self._show_resume_choice_panel(resumes)
                self.set_state("闲置")

            self.root.after(0, _done)

        threading.Thread(target=_work, daemon=True).start()

    def _show_action_panel(self, title: str, options: list, callback) -> None:
        """主对话框内通用可点击面板（多行按钮，选后回调 value 并收起）。"""
        self._hide_action_panel()
        p = tk.Frame(self.outer, bg="#FBEBDD", highlightbackground="#E4DDD0", highlightthickness=1)
        tk.Label(p, text=title, font=self.f_chip, bg="#FBEBDD", fg="#2B2622",
                 justify="left", wraplength=320).pack(anchor="w", padx=10, pady=(6, 2))
        for label, value in options:
            tk.Button(p, text=label, font=self.f_body, bg="#FFFFFF", fg="#2B2622",
                      activebackground="#F4B393", activeforeground="#FFFFFF",
                      relief="flat", bd=0, highlightbackground="#E4DDD0", highlightthickness=1,
                      cursor="hand2", justify="left", anchor="w", wraplength=320,
                      command=lambda v=value: (callback(v), self._hide_action_panel())
                      ).pack(fill="x", padx=10, pady=3, ipady=4)
        p.pack(fill="x", padx=14, pady=(0, 8), before=self._chip_row)
        self._action_panel = p
        # 窗口大小固定，不随操作面板变化
        # try:
        #     self.log_box.configure(height=2)
        # except Exception:
        #     pass
        # try:
        #     x, y = self._bottom_right(360, 580)
        #     self.root.geometry("360x580+%d+%d" % (x, y))
        # except Exception:
        #     pass

    def _emit_link(self, text: str, callback=None) -> None:
        """超链接式 LLM 设置入口：Tkinter 模式下直接打开设置窗；Electron 下由 pet_bridge 覆盖为聊天框链接。"""
        try:
            cb = callback or self.cmd_llm_settings
            self.root.after(0, cb)
        except Exception:
            pass

    _LLM_DEGRADED_AFTER = 2   # LLMRECOVER：连续 N 次「本应调 LLM 却失败」才判失效（防抖）

    def _score_jd(self, *args, **kwargs):
        """2026-09-25 LLMRECOVER：包装 shared.score_jd，做「LLM 失效 / 恢复正常」的状态轮转。

        · 评分**成功调用 LLM**（`res.llm_ok`）且此前处于降级态 → 提示「已恢复正常」并清标记；
        · 评分**本应调 LLM 却失败**（`llm_ok=False` 且确实该调）**连续** `_LLM_DEGRADED_AFTER` 次
          → 判失效：提示一次并置标记（防抖：偶发一次失败不算，避免反复弹）。
        · 「确实该调」= `use_llm` 且 `allow_resume_upload` 且 LLM 已配置 ——
          否则 `llm_ok=False` 只是「按设计没调 LLM」，**不能**当失效。
        · 「判断 + 改标记」用 `_LLM_STATE_LOCK` 原子化，杜绝并发下重复弹。

        用户要求：坏了要提示，**好了也要提示**；检查点放在「岗位评分」这条链路，不写轮询。
        """
        _orig = shared.score_jd
        res = _orig(*args, **kwargs)
        try:
            _ok = bool(getattr(res, "llm_ok", False))
            _should = False   # 本轮 LLM 是否「本应被调用」
            try:
                _cli = shared.build_llm_client(self.cfg)
                _should = (bool(kwargs.get("use_llm", True))
                           and bool((self.cfg.get("llm") or {}).get("allow_resume_upload", False))
                           and bool(getattr(_cli, "is_configured", lambda: False)()))
            except Exception:
                _should = False
            _recovered = False
            _degraded_now = False
            with _LLM_STATE_LOCK:
                if _ok:
                    self._llm_fail_streak = 0
                    if getattr(self, "_llm_degraded", False):
                        self._llm_degraded = False
                        _recovered = True
                elif _should:
                    self._llm_fail_streak = getattr(self, "_llm_fail_streak", 0) + 1
                    if (self._llm_fail_streak >= self._LLM_DEGRADED_AFTER
                            and not getattr(self, "_llm_degraded", False)):
                        self._llm_degraded = True
                        _degraded_now = True
            if _recovered:
                self.add_log("LLM 已恢复正常（岗位评分已成功调用 LLM）")
                self.root.after(0, lambda: self.set_bubble(
                    "✅ LLM 已恢复正常 —— 岗位评分已能正常调用 LLM，"
                    "简历诊断 / 投递关键词也都可用了。"))
            elif _degraded_now:
                self.add_log("LLM 连不上（岗位评分已连续 %d 次退回本地启发式）"
                             % self._LLM_DEGRADED_AFTER)
                self.root.after(0, lambda: self.set_bubble(
                    "⚠️ LLM 连不上了 —— 岗位评分已退回本地启发式（分数偏低、容易全被过滤）。\n"
                    "多半是密钥 / 网络 / 代理问题；修好后我会自动提示你已恢复。"))
        except Exception:
            pass
        return res

    def _hide_action_panel(self) -> None:
        if self._action_panel is not None:
            try:
                self._action_panel.destroy()
            except Exception:
                pass
            self._action_panel = None
        # 窗口大小固定，不随操作面板变化
        # try:
        #     self.log_box.configure(height=5)
        # except Exception:
        #     pass
        # try:
        #     x, y = self._bottom_right(360, 462)
        #     self.root.geometry("360x462+%d+%d" % (x, y))
        # except Exception:
        #     pass

    # ---------- 投放方案流程（简历分析后 → 兼职实习询问 → 方案确认） ----------
    def _plan_confirmed(self) -> bool:
        try:
            p = RUN_DIR / "plan.json"
            if not p.exists():
                return False
            import json as _json
            d = _json.loads(p.read_text(encoding="utf-8"))
            return bool(d.get("confirmed")) and bool(d.get("keywords"))
        except Exception:
            return False

    def _load_plan_state(self) -> None:
        try:
            p = RUN_DIR / "plan.json"
            if p.exists():
                import json as _json
                d = _json.loads(p.read_text(encoding="utf-8"))
                self._plan.update(d)
        except Exception:
            pass

    def _save_plan_state(self) -> None:
        try:
            import json as _json
            p = RUN_DIR / "plan.json"
            p.write_text(_json.dumps(self._plan, ensure_ascii=False, indent=2), encoding="utf-8")
            # 自动同步 config.json：保证 plan 和 config 永远一致
            cfg_path = RUN_DIR / "config.json"
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            new_kws = self._plan.get("keywords") or []
            if new_kws:
                cfg["target_roles"] = new_kws[:30]
            if self._plan.get("min_score") is not None:
                cfg["min_score"] = int(self._plan["min_score"])
            if self._plan.get("salary_low") is not None:
                cfg["min_salary_low_k"] = int(self._plan["salary_low"])
            if self._plan.get("salary_high") is not None:
                cfg["min_salary_high_k"] = int(self._plan["salary_high"])
            if self._plan.get("city"):
                cfg["target_city"] = self._plan["city"]
            cfg_path.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self.cfg = shared.load_config(RUN_DIR)
        except Exception as _sf_e:
            # 2026-09-21：方案持久化失败必须留痕，否则用户以为改成功了
            try:
                self.add_log("方案保存失败（未写入 config）：%s" % str(_sf_e)[:120])
            except Exception:
                pass

    def _start_plan_review_each_run(self) -> None:
        """每次启动都硬确认一次方案：未确认→生成方案进 review；已确认→展示预览+LLM 基于
        历史关键词/投放表现的优化建议，再等用户回 OK 才进投递。"""
        if not self._plan_confirmed():
            self.set_bubble("📋 还没有确认过投放方案：正在制定并请你确认…")
            self.add_log("新轮：无已确认方案，走方案生成流程")
            self._ensure_plan_flow()
            return
        # 方案已确认：展示预览 + 后台拉历史优化建议 → 进 review 等 OK
        self.set_bubble("📋 开始前先跟你过一遍方案（每次启动都确认一次）…\n正在结合历史投递表现给建议…")
        threading.Thread(target=self._preview_plan_with_advice, daemon=True).start()

    def _preview_plan_with_advice(self) -> None:
        """展示当前方案预览（方案 B：不调用 LLM 生成优化建议，省一次 LLM 调用）。"""
        kws = self._plan.get("keywords") or self.cfg.get("target_roles") or []
        ms = self._plan.get("min_score") or self.cfg.get("min_score")
        sl = self._plan.get("salary_low") or self.cfg.get("min_salary_low_k")
        sh = self._plan.get("salary_high") or self.cfg.get("min_salary_high_k")
        city = self._plan.get("city") or self.cfg.get("target_city") or "广州"
        # 方案 B：不调用 LLM 生成优化建议，省一次 LLM 调用
        advice_txt = ""
        body = ("📋 本轮投放方案（启动前确认）：\n\n"
                "🎯 关键词 %d 个：%s\n"
                "📍 城市：%s\n"
                "📊 岗位匹配值：%s 分（满分 100）  💰 薪资：%s-%sK\n"
                # 2026-09-19：把阈值的含义写出来，用户才知道调什么。
                # 单一阈值（用户可随时改），不再有海外/市场分档。
                "　　（≥%s 分才打招呼；规则分满分 40 + LLM 满分 60）\n\n" % (  # 2026-09-23 PREVIEWFMT：补回缺失的阈值参数
                    len(kws), "、".join(kws) if kws else "（默认）", city, ms, sl, sh, ms))
        _preview_excludes = list(dict.fromkeys(
            [*(self.cfg.get("exclude_keywords") or []), *(self._plan.get("exclude_add") or [])]))
        body += "🚫 排除词（命中岗位/JD/薪资即关闭）：%s\n\n" % (
            "、".join(_preview_excludes[:24]) or "无")
        # 不确定字段提醒：薪资/阈值/城市缺失时提醒用户确认
        uncertain = []
        if not sl or not sh:
            uncertain.append("喵喵没从简历里瞅准薪资范围，现在默认按 20-25K 帮你找，怕和你心里想的不一样喵～")
        if not ms:
            uncertain.append("岗位匹配值喵也没数，先用 70 分兜底啦")
        if uncertain:
            body += "😿 等一下哦，有几样东西喵喵拿不准：\n"
            for u in uncertain:
                body += "  · " + u + "\n"
            body += "  你可以直接跟我说（比如「薪资改成15-25K」），或者去看板「编辑方案」里改好再开冲喵～\n\n"
        if advice_txt:
            body += "🤖 历史表现优化建议：\n" + advice_txt + "\n\n"
        else:
            body += "（暂无历史投递数据，首轮无优化建议）\n\n"
        body += "点「开始投递」按钮开投；要改就直接说（如：去掉XX/岗位匹配值80/把XX提前搜）。"
        self.root.after(0, lambda: (self.set_bubble(body), setattr(self, "_plan_state", "review"),
            self.add_log("本轮方案预览+历史优化建议已展示，等用户确认")))

    def _load_historical_result_rows(self) -> list[dict]:
        """读取并聚合全部已落盘岗位结果，供每轮启动时的 LLM 方案优化使用。"""
        rows = []
        try:
            import json as _json
            files = list(RUN_DIR.glob("boss-*-log.json"))
            demo = RUN_DIR / "boss-demo-log.json"
            if demo.exists():
                files.append(demo)
            for path in files:
                data = _json.loads(path.read_text(encoding="utf-8"))
                records = data.get("records") or {}
                for bucket in ("applied", "skipped", "failed", "preview", "evaluated"):
                    for rec in records.get(bucket) or []:
                        if not isinstance(rec, dict):
                            continue
                        rows.append({
                            "bucket": bucket,
                            "keyword": rec.get("keyword") or rec.get("target_job") or "",
                            "job": rec.get("job") or rec.get("title") or "",
                            "company": rec.get("company") or "",
                            "salary": rec.get("salary") or "",
                            "score": rec.get("score", 0),
                            "reason": str(rec.get("reason") or rec.get("skip_reason") or "")[:80],
                        })
        except Exception:
            return rows
        grouped = {}
        for row in rows:
            key = row.get("keyword") or "（未知关键词）"
            item = grouped.setdefault(key, {
                "keyword": key, "total": 0, "applied": 0, "skipped": 0,
                "failed": 0, "preview": 0, "evaluated": 0, "scores": [],
                "salary_rejected": 0, "exclude_rejected": 0, "samples": [],
            })
            item["total"] += 1
            bucket = row.get("bucket")
            if bucket in item:
                item[bucket] += 1
            score = row.get("score")
            if isinstance(score, (int, float)) and score:
                item["scores"].append(score)
            reason = str(row.get("reason") or "")
            if "薪资" in reason:
                item["salary_rejected"] += 1
            if "排除" in reason:
                item["exclude_rejected"] += 1
            if len(item["samples"]) < 5:
                item["samples"].append({"job": row.get("job"), "score": score, "reason": reason})
        result = []
        for item in grouped.values():
            scores = item.pop("scores")
            item["average_score"] = round(sum(scores) / len(scores), 1) if scores else 0
            item["max_score"] = max(scores) if scores else 0
            result.append(item)
        return sorted(result, key=lambda x: (-x["applied"], -x["average_score"], x["keyword"]))

    def _ensure_plan_flow(self) -> None:
        """确保投放方案已确认：未确认 → 提炼关键词 + LLM 判定求职方向 + 对话框审核。"""
        self._load_plan_state()
        if self._plan.get("confirmed"):
            return
        if self._plan.get("keywords"):
            self.root.after(0, self._enter_plan_review)
        else:
            # 不覆盖分析报告气泡，只写日志
            self.add_log("正在从简历提炼投递关键词，制定投放方案…")
            threading.Thread(target=self._build_plan_from_resume, daemon=True).start()

    def _enter_plan_review(self) -> None:
        """气泡展示完整方案，进入对话框多轮审核（用户回复修改意见，直到确认开投）。"""
        kws = self._plan.get("keywords") or []
        pt = self._plan.get("exclude_pt", False)
        ms = self._plan.get("min_score") or self.cfg.get("min_score")
        sl = self._plan.get("salary_low") or self.cfg.get("min_salary_low_k")
        sh = self._plan.get("salary_high") or self.cfg.get("min_salary_high_k")
        salary_note = "（简历期望薪资）" if self._plan.get("salary_low") else ""
        city = self._plan.get("city") or self.cfg.get("target_city", "未设置")
        # 2026-09-19 W：与「看看方案」共用同一套格式，不再各写一份
        body = self._plan_body("投放方案（已按你的简历生成）", for_review=True)
        self.set_bubble(body)
        self._plan_state = "review"
        # 2026-09-19 R：要素不齐 → 除了展示方案，还要**问用户**（不给选项）
        _miss = self._plan_missing_fields()
        if _miss:
            self.add_log("方案要素不齐备，待用户补充：%s" % "、".join(_miss))
            self.set_bubble(
                "📋 方案先放这儿，但有件事得先问你：\n\n" + self._ask_missing_field(_miss[0]))
        self.add_log("投放方案已生成，等待用户审核（回复修改意见或确认开投）")

        # 2026-09-23 HISTREPORT2：上传/重传简历自动展示方案时，也顺带生成历史报告
        # （与 _show_current_plan 的钩子同源，受 _hist_report_done 同会话一次约束）。
        # 先提示一句，再后台线程生成 —— 用户注意力在方案上，报告稍后补上可一并参考。
        # 注：cmd_startup_diagnosis 自身已吞掉所有异常，用 lambda 起线程即可（不新增方法）。
        # 2026-09-23 前置判断：零历史数据不弹「整理中」提示（避免「帮你整理→跳过：暂无数据」
        # 自相矛盾）；也不置 _hist_report_done，等以后有真实数据再触发。
        try:
            _dec = self._hist_report_decision()
            if _dec == "skip":
                pass
            elif _dec == "refresh":
                # 2026-09-23 HISTCACHE：数据有更新才重新调 LLM 出报告
                self._save_hist_fingerprint()
                self.root.after(0, lambda: self.set_bubble(
                    "📋 我顺便帮你整理一份历史投递报告，稍等一下，可以和方案一起参考～"))
                threading.Thread(
                    target=lambda: self.cmd_startup_diagnosis(), daemon=True).start()
            elif _dec == "cache":
                # 无新数据：沿用上次报告，不再调 LLM（本会话只提示一次，避免刷屏）
                if not getattr(self, "_hist_report_cache_shown", False):
                    self._hist_report_cache_shown = True
                    _cached = self._load_cached_diagnosis()
                    if _cached:
                        self.root.after(0, lambda: self.set_bubble(
                            "📋 数据没更新，沿用上次的投递报告：\n\n" + _cached))
        except Exception:
            pass

    def _build_plan_from_resume(self) -> None:
        """后台：LLM 从 resume.md 提炼投放关键词 + 判定求职方向（正式工作/兼职实习）。"""
        kws = []
        self._plan_llm_missing = False   # 2026-09-24 PLANNOLLM：每次重算先复位
        work_type = "full"  # 默认正式工作（实习岗会被排除；兼职永远排除）
        try:
            rp = RUN_DIR / "resume.md"
            text = rp.read_text(encoding="utf-8", errors="ignore") if rp.exists() else ""
            if text:
                llm = shared.build_llm_client(self.cfg)
                _llm_ok = getattr(llm, "is_configured", lambda: False)()
                if not _llm_ok:
                    # 2026-09-24 PLANNOLLM：LLM 未配置 → 无法提炼关键词；
                    # 标记出来，让调用方给用户**明确提示**（而不是静默产出 0 关键词的空方案）。
                    self._plan_llm_missing = True
                    self.add_log("方案生成：LLM 未配置（无 api_key / base_url），无法从简历提炼关键词")
                if _llm_ok:
                    self.session["llm_calls"] += 1
                    out = (llm.chat_text(
                        self._llm_stage_brief("方案生成", {"简历字数": len(text), "期望薪资读取": "见下方JSON"})
                        + "\n\n你是招聘投放策略师。基于这份简历做三件事：\n"
                        # 2026-09-19 X：明确下限 —— 首个方案关键词不少于 8 个
                        "① 提炼 8~15 个最适合在 BOSS 直聘投递的职位关键词（岗位名/方向词，中文，2~6 字），"
                        "**数量不得少于 8 个**；"
                        "贴近简历核心经验与目标岗位，不得出现兼职/实习/初级/助理/客服等词；\n"
                        "② 判断求职类型 work_type：若简历显示的是正式职业经历（全职岗位、多年经验、管理层级、"
                        "完整职业发展线）则为 \"full\"（找正式工作，屏蔽兼职/实习）；若简历显示在校学生/应届/"
                        "经验不足半年/明显兼职实习倾向（如多段短期实习、寒暑假兼职）则为 \"intern\"（实习）；\n"
                        "③ 提取简历中的期望薪资（千元/月，如 15-20K → {\"salary_low\":15,\"salary_high\":20}）；"
                        "简历明确写了期望薪资就按它填数字；没写或写的是模糊描述（如\"面议\"）则 salary_low/salary_high 都填 null。\n"
                        "④ 提取简历中的求职城市（如\"广州\"\"上海\"\"北京\"），只填一个最主要的城市；\n   **简历没写城市则 city 填 null**（不要填\"全国\"——它不是有效城市，实测会把用户已设的具体城市冲掉）。\n"
                        "只输出 JSON 对象：{\"keywords\": [\"海外运营\",\"TikTok运营\"], \"work_type\": \"full\", "
                        "\"salary_low\": 15, \"salary_high\": 20, \"city\": \"广州\"}",
                        "【简历内容】\n" + text[:2500] + self._plan_memory_brief(), max_tokens=4000, temperature=0.3) or "").strip()
                    out = out.strip("`").strip()
                    if out.startswith("json"):
                        out = out[4:].strip()
                    # 调试：把 LLM 原始返回落盘
                    try:
                        (RUN_DIR / "llm-revise-debug.txt").write_text(
                            "=== 来源 ===\n简历方案生成\n\n=== 原始返回 ===\n%s" % out,
                            encoding="utf-8")
                    except Exception:
                        pass
                    import json as _json
                    start, end = out.find("{"), out.rfind("}")
                    if start >= 0 and end > start:
                        obj = _json.loads(out[start:end + 1])
                        arr = obj.get("keywords") or []
                        # 调试：看解析出来的内容
                        self.add_log("LLM 方案解析：keywords=%d个, work_type=%s, city=%s, salary=%s-%sK" % (
                            len(arr), obj.get("work_type"), obj.get("city"), obj.get("salary_low"), obj.get("salary_high")))
                        kws = [str(x).strip() for x in arr if str(x).strip()][:15]
                        # 2026-09-19 X：兜底 —— 首个方案关键词**不少于 8 个**。
                        # 不足时用 config 里已有的 target_roles 补齐（那些是先前用过、验证过的词），
                        # 不凭空编造；补齐会打日志说明。
                        if len(kws) < 8:
                            _old_kws = list(kws)
                            for _cand in (self.cfg.get("target_roles") or []):
                                _cand = str(_cand).strip()
                                if _cand and _cand not in kws:
                                    kws.append(_cand)
                                if len(kws) >= 8:
                                    break
                            if len(kws) > len(_old_kws):
                                self.add_log("关键词不足 8 个（%d），已用已有配置补齐至 %d 个"
                                             % (len(_old_kws), len(kws)))
                        wt = str(obj.get("work_type") or "").strip().lower()
                        if wt in ("pt", "part", "兼职", "实习"):
                            work_type = "intern"
                        elif wt in ("full", "全职", "正式"):
                            work_type = "full"
                        # 期望薪资：简历有明确数值才采用，否则保留 config 默认
                        try:
                            sl = float(obj.get("salary_low"))
                            sh = float(obj.get("salary_high"))
                            if sl and sh and 5 <= sl <= sh <= 200:
                                self._plan["salary_low"] = int(sl)
                                self._plan["salary_high"] = int(sh)
                        except Exception:
                            pass
                        # 求职城市：从简历提取
                        # 2026-09-19 Q：**「全国」不是有效城市**，是「简历没写」的兜底值，
                        # 绝不能拿它覆盖用户已明确设置的城市（实测把广州冲成了全国）。
                        try:
                            city = str(obj.get("city") or "").strip()
                            _cur = str(self.cfg.get("target_city") or "").strip()
                            if city and len(city) <= 6 and city != "全国":
                                self._plan["city"] = city
                                self.cfg["target_city"] = city
                            elif _cur:
                                # 简历没给出有效城市 → 沿用用户现值
                                self._plan["city"] = _cur
                            elif city and len(city) <= 6:
                                # 连现值都没有，才接受「全国」
                                self._plan["city"] = city
                        except Exception:
                            pass
                    else:
                        # JSON 解析失败：把 LLM 原始返回写到日志里
                        self.add_log("LLM 返回解析失败，原始内容前 200 字：%s" % out[:200])
        except Exception as e:
            kws = []
            self.add_log("LLM 调用异常：%s" % str(e)[:200])
        if not kws:
            kws = list((self.cfg.get("target_roles") or [])[:10])
        self._plan["keywords"] = kws
        self._plan["exclude_pt"] = (work_type == "full")
        self._plan["pt_asked"] = True  # LLM 已判定，无需用户再选
        self._plan["source"] = "resume" if kws else "default"
        # 同步 min_score：新方案不主动改阈值，沿用 config 现值（用户可在看板改）
        if self._plan.get("min_score") is None:
            self._plan["min_score"] = self.cfg.get("min_score", 70)
        self._save_plan_state()
        # 同步写 config.json：salary/city 已从简历提取，min_score 沿用现值，避免 plan.json 和 config.json 不一致
        try:
            import json as _json_sync
            _cfg_path = RUN_DIR / "config.json"
            _cfg_now = _json_sync.loads(_cfg_path.read_text(encoding="utf-8"))
            _cfg_now["min_score"] = int(self._plan["min_score"])
            if self._plan.get("salary_low") is not None:
                _cfg_now["min_salary_low_k"] = int(self._plan["salary_low"])
            if self._plan.get("salary_high") is not None:
                _cfg_now["min_salary_high_k"] = int(self._plan["salary_high"])
            if self._plan.get("city"):
                _cfg_now["target_city"] = self._plan["city"]
            _cfg_path.write_text(_json_sync.dumps(_cfg_now, ensure_ascii=False, indent=2), encoding="utf-8")
            self.cfg = shared.load_config(RUN_DIR)
        except Exception as e:
            self.add_log("同步 config.json 失败：%s" % str(e)[:100])
        # 2026-09-24 PLANNOLLM：LLM 未配置 + 没有任何关键词 → 方案是空的。
        # 不能把「0 关键词的空方案」当正常结果推进审核，必须明确告诉用户去配置 LLM。
        if getattr(self, "_plan_llm_missing", False) and not kws:
            self.root.after(0, lambda: (
                self.set_bubble(
                    "⚠️ 我还没配置 LLM，所以没法从简历提炼关键词 —— 方案里是空的。\n\n"
                    "请右键点我 →「📊 分析报告」打开看板 →「设置 · LLM」填好 base_url / 密钥 / 模型，\n"
                    "保存后把简历**重新拖给我**（或说「重新生成方案」），我就能出方案～"),
                self.add_log("方案生成中止：LLM 未配置且无可用关键词（已提示用户去配置）")))
            return
        self.root.after(0, lambda: (self.set_bubble(
            "📋 已从简历提炼 %d 个投递关键词。\nLLM 判定求职方向：%s。" % (
                len(kws), "正式工作" if work_type == "full" else "实习")),
            self.add_log("投放方案：提炼关键词 %d 个，求职方向 %s" % (len(kws), work_type)),
            self._enter_plan_review()))

    def _revise_plan(self, feedback: str) -> None:
        """按用户修改意见，LLM 调整方案（后台）。"""
        self.set_bubble("🔧 正在按你的意见调整方案…")
        threading.Thread(target=self._revise_plan_work, args=(feedback,), daemon=True).start()

    def _revise_plan_work(self, feedback: str) -> None:
        # 2026-09-21 KWG1：修订前先备份 plan.json，改坏了能回滚
        try:
            import shutil as _shutil
            _pp = RUN_DIR / "plan.json"
            if _pp.exists():
                _shutil.copy2(str(_pp), str(RUN_DIR / "plan.json.bak"))
        except Exception:
            pass
        new_plan = None
        try:
            llm = shared.build_llm_client(self.cfg)
            if getattr(llm, "is_configured", lambda: False)():
                self.session["llm_calls"] += 1
                kws = self._plan.get("keywords") or []
                pt = self._plan.get("exclude_pt", False)
                ms = self._plan.get("min_score") or self.cfg.get("min_score")
                sl = self._plan.get("salary_low") or self.cfg.get("min_salary_low_k")
                sh = self._plan.get("salary_high") or self.cfg.get("min_salary_high_k")
                city_now = self._plan.get("city") or self.cfg.get("target_city", "全国")
                out = (llm.chat_text(
                    "你是招聘投放方案调整器。根据用户意见调整方案，只输出一个JSON对象，不要输出任何解释、markdown或代码块标记。\n\n"
                    "【输出格式】必须严格如下，字段不能少，不能加多余字段：\n"
                    # 2026-09-19 F：加 work_type —— 否则「我想找实习工作」这种请求
                    # LLM 无法真正改方向，只能在 summary 里嘴上说改了。
                    '{"keywords":["词1","词2"],"work_type":"full",'
                    '"min_score":75,"min_salary_low_k":15,"min_salary_high_k":25,'
                    '"city":"广州","exclude_add":[],'
                    '"summary":"一句话说明改了什么"}\n\n'
                    "【字段规则】\n"
                    "- keywords：职位关键词数组，中文2~6字，用户要求多少个就给多少个，不要加标点\n"
                    "- work_type：求职方向。用户要找正式工作就填 full；要找实习就填 intern；用户没提就保持原值\n"
                    "- min_score：1~100的整数，用户没提就保持原值\n"
                    "- min_salary_low_k/min_salary_high_k：数字，单位K，用户说15-25K就填15和25\n"
                    "- city：投递城市，用户提到哪个城市就填哪个（如广州/上海/北京/深圳），用户没提就保持原值\n"
                    "- exclude_add：新增排除词数组，没有就空数组[]\n"
                    "   · 屏蔽词同时作用于**岗位标题 / JD / 公司名**\n"
                    "   · **公司名维度只认 ≥3 个中文字的词**（如「蚍蜉网络」）；\n"
                    "     2 字词（电商/网络/科技）不会屏蔽公司，避免误杀一整片。\n"
                    "     用户问「能不能屏蔽某公司」时，请这样解释：\n"
                    "     把公司名（≥3 个中文字）加进屏蔽词即可屏蔽整家公司。\n"
                    "- summary：一句话说明改了什么\n\n"
                    "只输出JSON，不要输出其他任何文字。",
                    "【当前方案】\n"
                    "关键词：%s\n"
                    "求职方向：%s\n"
                    "岗位匹配值：%s\n"
                    "薪资范围：%s-%sK\n"
                    "城市：%s\n\n"
                    # 2026-09-18：注入「投递记忆」（只含摘要层，约 350 tokens）
                    "%s"
                    "【用户意见】\n%s" % (
                        "、".join(kws), "正式工作" if pt else "实习",
                        ms, sl, sh, city_now,
                        # 2026-09-22 RECALL1：换成完整回忆（含 HR 真实反馈），
                        # 它内部已包含 _recent_runs_brief，不会重复。
                        self._plan_memory_brief(), feedback),
                    max_tokens=4000, temperature=0.3) or "").strip()
                out = out.strip("`").strip()
                if out.startswith("json"):
                    out = out[4:].strip()
                import json as _json
                start, end = out.find("{"), out.rfind("}")
                if start >= 0 and end > start:
                    new_plan = _json.loads(out[start:end + 1])
        except Exception as e:
            new_plan = None
            # 调试：把异常信息落盘
            try:
                (RUN_DIR / "llm-revise-debug.txt").write_text(
                    "=== 用户意见 ===\n%s\n\n=== 异常 ===\n%s" % (feedback, str(e)),
                    encoding="utf-8")
            except Exception:
                pass
        if not isinstance(new_plan, dict) or not isinstance(new_plan.get("keywords"), list):
            self._plan_change_pending = False  # 修复：LLM 失败时解除门禁，让用户能继续发消息
            self.root.after(0, lambda: (self.set_bubble(
                "😿 LLM 没返回有效方案，可能是 LLM 服务异常或网络问题。\n"
                "请检查 API 配置后重试，或手动告诉我要改什么。"),
                self.set_state("错误")))
            self.add_log("LLM 方案修改失败：返回空或解析失败")
            return
        kws2 = [str(x).strip() for x in new_plan.get("keywords") if str(x).strip()][:20]
        # 2026-09-21 KWG1：**关键词不得静默减少**。
        # 原逻辑只要 LLM 返回非空列表就整体替换 —— 用户只要求排序时，
        # LLM 可能只回 3 个词，其余被无声丢掉（用户实测：12 → 3）。
        _old_kws = [str(x).strip() for x in (self._plan.get("keywords") or []) if str(x).strip()]
        _del_intent = any(w in str(feedback or "") for w in
                          ("删", "去掉", "移除", "不要", "剔除", "拿掉", "清除"))
        if kws2 and len(kws2) < len(_old_kws) and not _del_intent:
            # 不应用关键词变更；其余字段（薪资/城市/匹配值…）照常应用
            _lost = len(_old_kws) - len(kws2)
            self.add_log("方案修订：关键词被 LLM 从 %d 个压到 %d 个，但用户没说要删 → 已拒绝，保留原 %d 个"
                         % (len(_old_kws), len(kws2), len(_old_kws)))
            self.root.after(0, lambda n=_lost: (self.set_bubble(
                "⚠️ 我没改关键词。\n"
                "LLM 这次只回了 %d 个词，比现在的少 %d 个，但你没说要删。\n"
                "我先把原来的词留着了。\n\n"
                "如果确实想删，请明说，例如：\n"
                "「删掉抖音运营、直播运营」" % (len(_old_kws) - n, n)),
                self.set_state("闲置")))
        elif kws2:
            self._plan["keywords"] = kws2
        try:
            if new_plan.get("min_score") is not None:
                self._plan["min_score"] = int(new_plan["min_score"])
        except Exception:
            pass
        try:
            if new_plan.get("min_salary_low_k") is not None:
                self._plan["salary_low"] = int(new_plan["min_salary_low_k"])
            if new_plan.get("min_salary_high_k") is not None:
                self._plan["salary_high"] = int(new_plan["min_salary_high_k"])
        except Exception:
            pass
        try:
            if new_plan.get("city"):
                self._plan["city"] = str(new_plan["city"]).strip()
        except Exception:
            pass
        ex_add = [str(x).strip() for x in (new_plan.get("exclude_add") or []) if str(x).strip()]
        if ex_add:
            cur = self._plan.get("exclude_add") or []
            self._plan["exclude_add"] = list(dict.fromkeys(cur + ex_add))
        summary = str(new_plan.get("summary") or "已按意见调整").strip()
        # 2026-09-19 F：应用求职方向（正式/实习二选一；兼职不在此列）
        _wt = str(new_plan.get("work_type") or "").strip().lower()
        if _wt in ("full", "intern"):
            self._plan["exclude_pt"] = (_wt == "full")
        self._plan["pt_asked"] = True
        self._save_plan_state()
        # 同步写 config.json：避免 plan.json 和 config.json 不一致
        try:
            import json as _json_sync2
            _cfg_path2 = RUN_DIR / "config.json"
            _cfg_now2 = _json_sync2.loads(_cfg_path2.read_text(encoding="utf-8"))
            # 关键词列表直接替换（按 plan 顺序），不是合并
            _new_kws = self._plan.get("keywords") or []
            if _new_kws:
                _cfg_now2["target_roles"] = _new_kws[:30]
            if self._plan.get("min_score") is not None:
                _cfg_now2["min_score"] = int(self._plan["min_score"])
            if self._plan.get("salary_low") is not None:
                _cfg_now2["min_salary_low_k"] = int(self._plan["salary_low"])
            if self._plan.get("salary_high") is not None:
                _cfg_now2["min_salary_high_k"] = int(self._plan["salary_high"])
            if self._plan.get("city"):
                _cfg_now2["target_city"] = self._plan["city"]
            # 2026-09-19 F：改方案也要同步排除词 —— 原实现只有「方案确认」
            # 那条路写，改方案路径从不写 → 方向改了但排除词没跟着变。
            self._sync_title_excludes(_cfg_now2)
            _cfg_path2.write_text(_json_sync2.dumps(_cfg_now2, ensure_ascii=False, indent=2), encoding="utf-8")
            self.cfg = shared.load_config(RUN_DIR)
        except Exception as e:
            self.add_log("修改方案后同步 config.json 失败：%s" % str(e)[:100])
        self.add_log("方案已调整（%s）" % summary[:40])

        def _show():
            kws3 = self._plan.get("keywords") or []
            pt = self._plan.get("exclude_pt", False)
            ms = self._plan.get("min_score") or self.cfg.get("min_score")
            sl = self._plan.get("salary_low") or self.cfg.get("min_salary_low_k")
            sh = self._plan.get("salary_high") or self.cfg.get("min_salary_high_k")
            city = self._plan.get("city") or self.cfg.get("target_city", "广州")
            salary_note = "（简历期望薪资）" if self._plan.get("salary_low") else ""
            # 2026-09-19 W3：与另外两处方案展示共用 `_plan_body()`。
            # 原实现自己拼格式串，W2 改文案时漏改参数 → TypeError → 气泡不出来。
            body = ("✅ 已按你的意见调整：%s\n\n" % (summary or "")) + \
                   self._plan_body("新方案", for_review=True)
            self.set_bubble(body)
            self._plan_state = "review"

        self.root.after(0, _show)

    def _apply_plan(self, kws: list) -> None:
        """应用方案：更新 config 关键词/阈值/薪资/排除词 + 写 plan.json confirmed。"""
        try:
            import json as _json
            p = RUN_DIR / "config.json"
            cfg = _json.loads(p.read_text(encoding="utf-8"))
            if kws:
                merged = list(dict.fromkeys(kws + (cfg.get("target_roles") or [])))
                cfg["target_roles"] = merged[:30]
            if self._plan.get("min_score") is not None:
                cfg["min_score"] = int(self._plan["min_score"])
            if self._plan.get("salary_low") is not None:
                cfg["min_salary_low_k"] = int(self._plan["salary_low"])
            if self._plan.get("salary_high") is not None:
                cfg["min_salary_high_k"] = int(self._plan["salary_high"])
            # 2026-09-19 F：改为双向同步（原实现只 append、从不 remove，
            # 导致切到「实习」方向后实习岗仍被硬排除）。
            self._sync_title_excludes(cfg)
            for w in (self._plan.get("exclude_add") or []):
                ex = list(cfg.get("exclude_keywords") or [])
                if w not in ex:
                    ex.append(w)
                cfg["exclude_keywords"] = ex
            p.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self.cfg = shared.load_config(RUN_DIR)
        except Exception:
            pass
        self._plan["confirmed"] = True
        self._plan_change_pending = False
        self._plan["keywords"] = kws or (self.cfg.get("target_roles") or [])
        self._plan_state = None
        self._save_plan_state()
        self.add_log("投放方案已确认并保存（关键词 %d 个）" % len(self._plan["keywords"]))
        # LLM 已在简历上传后接管；方案确认是用户硬门禁（LLM 仅协助生成/修改，无权代替确认）
        self.set_bubble(
            "✅ 方案通过！已应用：%d 个关键词 · 岗位匹配值 %s 分 · 薪资 %s-%sK · %s\n\n"
            "正在直接进入投递流程…" % (
                len(self._plan["keywords"]), self.cfg.get("min_score"),
                self.cfg.get("min_salary_low_k"), self.cfg.get("min_salary_high_k"),
                "正式工作" if self._plan.get("exclude_pt") else "实习"))
        self.add_log("方案通过，自动进入投递流程")
        self._plan_reviewed_this_run = True  # 本轮已硬确认，重入 cmd_test_run 直接进投递
        # P1 修复：记住 real 参数，异步确认后不丢失
        _real = getattr(self, "_pending_real", True)  # 默认真实投递
        self.root.after(800, lambda: self.cmd_test_run(real=_real))

    def _sim_listen_event(self, tag: str, msg: str, kind: str):
        try:
            self.root.bell()
        except Exception:
            pass
        self.session["hr_msgs"] += 1
        if kind == "auto_send":
            # 简历名从配置/当前选择读取，不写死（防隐私泄漏）
            _resume_name = (self.cfg.get("resume_send_name")
                            or self._resume_choice_selected or "附件简历")
            self.set_bubble("【监听 · 模拟】HR 要简历：\n%s\n\n✅ 自动处理：发送「%s」\n（未真实发送）" % (msg, _resume_name))
            self.add_log("模拟监听：HR 要简历 → 自动发简历（未发送）")
        elif kind == "thank":
            self.set_bubble("【监听 · 模拟】HR 拒绝：\n%s\n\n✅ 自动处理：固定致谢「感谢回复，祝您生活愉快！」" % msg)
            self.add_log("模拟监听：HR 拒绝 → 固定致谢")
        elif kind == "escalate":
            self.set_act("wave")
            self.set_bubble("【监听 · 模拟】HR 约面试：\n%s\n\n⚠️ 需你接管：爬爬不自动回复面试邀请，请人工确认时间。" % msg)
            self.add_log("模拟监听：HR 约面试 → 提醒用户接管")
        else:
            self.set_act("think")
            self.set_bubble("【监听 · 模拟】HR 对话：\n%s\n\n正在生成回复草稿…" % msg)

            def _gen():
                draft = ""
                try:
                    from boss import boss_chat
                    llm = shared.build_llm_client(self.cfg)
                    resume_for_llm = self._current_resume() if bool((self.cfg.get("llm") or {}).get("allow_resume_upload", False)) else ""
                    ok, draft = boss_chat.generate_conversation_reply(
                        llm, resume_for_llm, "该岗位", msg)
                except Exception:
                    ok, draft = False, ""
                self.root.after(0, lambda d=draft: (self.set_act("sit"),
                    self.set_bubble("【监听 · 模拟】HR：\n%s\n\n回复草稿：%s\n（未发送）" % (
                        msg, d[:160] if d else "未能生成，转人工"))))

            threading.Thread(target=_gen, daemon=True).start()

    def _test_summary(self, rec: dict, online: bool, real: bool = False):
        self.set_act("happy")
        # 投递自然结束 → 守护停（统一开关闭环）
        self._guard_tasks("disable")
        self._set_applying(False)
        self._round_state_write("COMPLETED")  # 三态主记录：正常完成
        mins = max(1, int((time.time() - self.session["start"]) // 60))
        resume_note = self.session.get("resume_file") or "run/resume.md"
        if real:
            self.set_bubble("【真实投递 · 收尾简报】\n"
                            "运行：%d 分钟\n"
                            "简历：%s（最新）\n"
                            "关键词：%d 个（%s）\n"
                            "扫描岗位：%d 个\n"
                            "真实打招呼：%d 次（已真实点击立即沟通）\n"
                            "LLM 调用：%d 次\n"
                            "监听：真实监听本轮 HR（要简历自动发 / 拒绝回谢 / 面试提醒）\n"
                            "⚠️ 已真实发出，HR 回复会进入监听" % (
                                mins, resume_note, rec["kw"], "真实 BOSS" if online else "模拟岗位",
                                rec["scan"], rec["greet"], rec["llm"]))
            self.add_log("真实投递完成：扫描 %d 岗位，真实打招呼 %d 次" % (rec["scan"], rec["greet"]))
        else:
            self.set_bubble("【开始投递 · 收尾简报】\n"
                            "运行：%d 分钟\n"
                            "简历：%s（最新）\n"
                            "关键词：%d 个（%s）\n"
                            "扫描岗位：%d 个\n"
                            "模拟打招呼：%d 次（未真实发送）\n"
                            "LLM 调用：%d 次\n"
                            "监听事件：4 类已处理\n"
                            "真实投递：0 —— 全流程模拟，可放心点" % (
                                mins, resume_note, rec["kw"], "真实 BOSS" if online else "模拟岗位",
                                rec["scan"], rec["greet"], rec["llm"]))
            self.add_log("开始投递完成：扫描 %d 岗位，模拟打招呼 %d（未发送）" % (rec["scan"], rec["greet"]))
        self.set_state("闲置")
        # 自然跑完也做一次 LLM 总结 + 关键词调整判断
        self._stop_summary_llm(rec, list(self._last_kw_stats), False)

    # ---------- 停止总结：LLM 总结本轮 + 按关键词打分判断是否调整关键词 ----------
    # =============== 复盘报告（2026-09-18 新增） ===============
    # 目标：让主人能复盘「哪个词有效、为什么这个岗位没达标」；
    #       也让喵能把历史表现当记忆用，做方案时不再空泛。
    # 保留策略：最近 REPORTS_KEEP_FULL 次留完整明细，更早的降级为摘要。
    REPORTS_KEEP_FULL = 30

    # ---------- 数据归档（2026-09-22 KEEPALL）----------
    # ⚠️ 只做「多存一份」，不改任何判断逻辑。
    def _archive_dir(self):
        d = RUN_DIR / "archive"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _archive_append(self, name: str, records: list) -> None:
        """把即将被截断的记录**追加**到 run/archive/<name>-<日期>.jsonl。

        用 append-only 的 JSONL，而不是全量重写 JSON ——
        boss-demo-log.json 每次评分都整文件读+写，放大它会让投递主循环变慢。
        失败一律忽略，绝不影响主流程。
        """
        if not records:
            return
        try:
            import json as _j
            p = self._archive_dir() / ("%s-%s.jsonl"
                                       % (name, time.strftime("%Y%m%d")))
            with p.open("a", encoding="utf-8") as fh:
                for r in records:
                    fh.write(_j.dumps(r, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _reports_dir(self):
        d = RUN_DIR / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _write_run_report(self, rec: dict, kw_stats: list, stopped_by_user: bool) -> None:
        """把本轮结果写成一份复盘报告（总结 + 岗位打分明细）。失败不影响主流程。"""
        try:
            import json as _j
            jobs = list(getattr(self, "_run_jobs", []) or [])
            # 2026-09-18 用户裁决：当轮**没有任何岗位拿到 LLM 评分**就停止的
            # （无论什么原因：用户提前停止、登录失效、浏览器掉线、崩溃…），
            # 都不计入总结 —— 那种轮次只有关键词统计，没有可复盘的内容，
            # 写出来只会污染「结果复盘」列表。
            if not jobs:
                self._last_report_id = ""
                return
            rid = time.strftime("%Y%m%d-%H%M%S")
            # 只对**真正扫到过岗位**的词求平均。
            # 否则 scanned=0 的词会把均值拉低（实测 40.6 被算成 20.3）。
            _scanned_kws = [s for s in kw_stats
                            if int(s.get("scanned", 0) or 0) > 0]
            report = {
                "v": 1,
                "run_id": rid,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": "user_stop" if stopped_by_user else "natural",
                "cfg": {
                    "threshold": self.cfg.get("min_score", 70),
                    "city": self.cfg.get("target_city", ""),
                    "salary": [self.cfg.get("min_salary_low_k"),
                               self.cfg.get("min_salary_high_k")],
                },
                "summary": {
                    "scanned": sum(int(s.get("scanned", 0)) for s in kw_stats),
                    "applied": sum(int(s.get("applied", 0)) for s in kw_stats),
                    "avg": (round(sum(float(s.get("avg", 0)) for s in _scanned_kws)
                                  / len(_scanned_kws), 1) if _scanned_kws else 0),
                    "top": max([int(s.get("top", 0)) for s in kw_stats] or [0]),
                    "by_keyword": kw_stats,
                    "advice": None,  # 由 _patch_report_advice 回填
                },
                "jobs": jobs,
            }
            self._last_report_id = rid
            (self._reports_dir() / ("report-%s.json" % rid)).write_text(
                _j.dumps(report, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
            self._prune_reports()
            self.add_log("复盘报告已生成：%s（岗位明细 %d 条）" % (rid, len(jobs)))
            # 2026-09-19 V：折进「个人求职记忆」（独立数据层，跨轮次积累）
            self._fold_report_into_job_memory(report)
        except Exception as exc:
            self.add_log("复盘报告生成失败（已忽略）：%s" % str(exc)[:120])

    def _patch_report_advice(self, advice: dict) -> None:
        """把 LLM 停止总结的建议回填进本轮已落盘的报告。"""
        try:
            import json as _j
            rid = getattr(self, "_last_report_id", "")
            if not rid:
                return
            p = self._reports_dir() / ("report-%s.json" % rid)
            if not p.exists():
                return
            d = _j.loads(p.read_text(encoding="utf-8"))
            d.setdefault("summary", {})["advice"] = advice
            p.write_text(_j.dumps(d, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
        except Exception:
            pass

    def _prune_reports(self) -> None:
        """最近 REPORTS_KEEP_FULL 次保留完整明细；更早的丢掉 jobs 只留摘要。

        这样「长留 + 尽量压缩」与「近 30 次行为可读懂」同时成立。
        """
        try:
            import json as _j
            files = sorted(self._reports_dir().glob("report-*.json"), reverse=True)
            for p in files[self.REPORTS_KEEP_FULL:]:
                try:
                    d = _j.loads(p.read_text(encoding="utf-8"))
                    # 2026-09-22 KEEPALL：裁剪前先把完整明细归档，否则真丢了。
                    # ⚠️ 归档单独 try —— 它是「锦上添花」，
                    #    失败也**不能**连带跳过裁剪（否则报告永远不降级）。
                    try:
                        _old_jobs = d.get("jobs")
                        if _old_jobs is not None:
                            self._archive_append(
                                "report_%s" % str(d.get("run_id") or p.stem),
                                _old_jobs)
                    except Exception:
                        pass
                    if d.pop("jobs", None) is not None:
                        d["jobs_trimmed"] = True
                        p.write_text(
                            _j.dumps(d, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
                except Exception:
                    continue
        except Exception:
            pass

    def list_reports(self, limit: int = 60) -> list:
        """列出复盘报告（轻量索引，不含岗位明细）。供看板「结果复盘」用。"""
        out = []
        try:
            import json as _j
            for p in sorted(self._reports_dir().glob("report-*.json"),
                            reverse=True)[:limit]:
                try:
                    d = _j.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                s = d.get("summary") or {}
                out.append({
                    "run_id": d.get("run_id", p.stem),
                    "ts": d.get("ts", ""),
                    "reason": d.get("reason", ""),
                    "scanned": s.get("scanned", 0),
                    "applied": s.get("applied", 0),
                    "avg": s.get("avg", 0),
                    "top": s.get("top", 0),
                    "jobs": len(d.get("jobs") or []),
                    "trimmed": bool(d.get("jobs_trimmed")),
                })
        except Exception:
            pass
        return out

    def load_report(self, run_id: str):
        """读取单份报告全文（含岗位明细）。run_id 已做白名单过滤，防路径穿越。"""
        try:
            import json as _j
            safe = "".join(ch for ch in str(run_id) if ch.isdigit() or ch == "-")
            if not safe:
                return None
            p = self._reports_dir() / ("report-%s.json" % safe)
            if not p.exists():
                return None
            d = _j.loads(p.read_text(encoding="utf-8"))
            # 2026-09-19 C3：join 结果回填（按公司名）。
            # outcome 独立于轮次存储，所以跨轮次/跨天到达的 HR 回复
            # 也能挂到这份历史报告上 —— 这正是它不存报告里的原因。
            _oc = self._load_outcomes()
            for _jb in (d.get("jobs") or []):
                _co = str(_jb.get("company") or "").strip()
                _hit = _oc.get(_co)
                if _hit:
                    _st = str(_hit.get("state") or "")
                    _jb["outcome"] = _st
                    _jb["outcome_label"] = self.OUTCOME_LABELS.get(_st, _st)
                    _jb["outcome_ts"] = _hit.get("ts", "")
            return d
        except Exception:
            return None

    def _sync_title_excludes(self, cfg: dict) -> None:
        """按求职方向同步标题排除词（2026-09-19 用户裁决）。

        三条路不混为一谈：
          · 正式工作 / 实习 = 真正的二选一方向 —— 选「正式」才排除「实习」
          · 兼职 = 忽略不计，**永远**排除，不随方向变化

        原实现是**单向**的（只在 exclude_pt=True 时 append、从不 remove），
        导致用户从「正式」切到「实习」后「实习」永远留在排除词里 ——
        实习岗在预过滤阶段被 0 分杀掉，连 LLM 都不进，关键词加了也没用。
        """
        ex = [x for x in (cfg.get("title_exclude_keywords") or []) if x != "实习"]
        if self._plan.get("exclude_pt"):
            ex.append("实习")
        if "兼职" not in ex:
            ex.append("兼职")
        cfg["title_exclude_keywords"] = ex

    def _push_outcome_update(self, company: str, state: str) -> None:
        """结果状态变化时通知前端（基类默认只记日志；HeadlessPet 覆写为推事件）。

        2026-09-19 Q1 方案 A：让看板在 HR 回复到达时**立刻**反映，
        而不是等用户重新打开报告。
        """
        try:
            self.add_log("结果状态更新：%s → %s" % (
                company, self.OUTCOME_LABELS.get(state, state)))
        except Exception:
            pass

    # 2026-09-19 A3：技能清洗的停用词（这些词在 JD 里高频但与技能无关）
    SKILL_STOPWORDS = {
        "公司", "科技", "有限", "集团", "中心", "部门", "团队", "工作", "经验",
        "负责", "项目", "产品", "以上", "优先", "熟悉", "熟练", "具备", "能力",
        "相关", "岗位", "职责", "要求", "任职", "资格", "学历", "本科", "大专",
        "专业", "年龄", "性别", "待遇", "薪资", "福利", "地点", "城市", "沟通",
    }

    def _clean_resume_skills(self, cands, allow_ascii=None) -> list:
        """B1 折中：从简历提取的技能里剔除噪音，保留真正可用的技能词。

        规则：
          · 长度 2~10（单字与长句都不要）
          · 不在停用词表（公司/科技/经验/负责…）
          · 不含公司机构后缀（公司/科技/有限/集团/中心/部门）
          · ⭐ **纯 ASCII 词必须命中已知技能词表** —— 这条最关键。

        为什么最后一条不能省（2026-09-19 实测回归）：
          英文分词会把**公司名/产品名**当技能提取。用户简历实测收进了
          Joymate / Flat / Incubator / Mini / App / Lovense / Cam ——
          全是产品名，进了 JD 就会误命中、把技能分虚高到上限。
        → 中文技能词不受限（中文产品名较少且可控），英文必须过词表。
        """
        out: list = []
        _ok = {str(x).strip().lower() for x in (allow_ascii or [])}
        try:
            for s in cands or []:
                s = str(s or "").strip()
                if not (2 <= len(s) <= 10):
                    continue
                if s.lower() in self.SKILL_STOPWORDS:
                    continue
                if any(bad in s for bad in ("公司", "科技", "有限", "集团",
                                            "中心", "部门")):
                    continue
                # 纯 ASCII（英文/数字）：必须命中已知技能词表，否则视为专名丢弃
                if s.isascii() and s.lower() not in _ok:
                    continue
                out.append(s)
        except Exception:
            return []
        seen = set()
        res = []
        for s in out:
            if s.lower() not in seen:
                seen.add(s.lower())
                res.append(s)
        return res[:10]

    # 2026-09-19 R：方案的**必要要素**（读不出来就必须问，不给默认值、不给选项）
    def _plan_missing_fields(self) -> list:
        """返回还不齐备的要素，按提问顺序排列。"""
        miss: list = []
        city = str(self._plan.get("city") or "").strip()
        # 「全国」不是有效城市 —— 那是「不知道」的占位，等于没填
        if (not city) or city in ("全国", "未设置"):
            miss.append("city")
        sl, sh = self._plan.get("salary_low"), self._plan.get("salary_high")
        try:
            sl = float(sl) if sl is not None else 0.0
            sh = float(sh) if sh is not None else 0.0
        except Exception:
            sl = sh = 0.0
        if not (sl and sh and 5 <= sl <= sh <= 200):
            miss.append("salary")
        return miss

    def _ask_missing_field(self, field: str) -> str:
        """开放式提问 —— 不给选项，让用户自己说。"""
        if field == "city":
            return ("📍 简历里没写求职城市，这个我没法替你猜。\n"
                    "你想在哪个城市找工作？直接告诉我城市名就行。")
        return ("💰 简历里没写期望薪资，这个我也不能替你定。\n"
                "你的期望月薪是多少？比如说「15-20K」。")

    def _parse_city_answer(self, text: str) -> str:
        """从用户回答里认城市（只认已知城市表，避免把"全国"当答案）。"""
        t = str(text or "")
        try:
            for name in CITY_CODES:
                if name != "全国" and name in t:
                    return name
        except Exception:
            pass
        return ""

    def _parse_salary_answer(self, text: str):
        """从用户回答里认薪资区间，返回 (low, high) 或 None。"""
        import re as _re
        t = str(text or "")
        m = _re.search(r"(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)", t)
        if m:
            return float(m.group(1)), float(m.group(2))
        m = _re.search(r"(\d+(?:\.\d+)?)\s*[kK千]", t)
        if m:
            v = float(m.group(1))
            return v, v
        return None

    # =============== 个人求职记忆（2026-09-19 V）===============
    # ⭐ 战略级差异点：记录「这个用户在真实招聘市场里什么有效」。
    # 独立于报告 —— 报告是按轮次的快照，记忆是跨轮次的流。
    def _job_memory_path(self):
        return RUN_DIR / "job_memory.json"

    def _load_job_memory(self) -> dict:
        try:
            import json as _j
            p = self._job_memory_path()
            if not p.exists():
                return {"v": 1, "jobs": [], "keyword_stats": {}}
            d = _j.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.setdefault("jobs", [])
                d.setdefault("keyword_stats", {})
                return d
        except Exception:
            pass
        return {"v": 1, "jobs": [], "keyword_stats": {}}

    def _save_job_memory(self, data: dict) -> None:
        try:
            import json as _j
            p = self._job_memory_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_j.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except Exception:
            pass

    def _fold_report_into_job_memory(self, report: dict) -> None:
        """把本轮报告折进求职记忆。失败不影响主流程。

        V1 只积累、不分析 —— 分析等有几十轮数据后做（那时才有统计意义）。
        """
        try:
            mem = self._load_job_memory()
            jobs = list(mem.get("jobs") or [])
            rid = str(report.get("run_id") or "")
            city = str(self.cfg.get("target_city") or "")
            for j in (report.get("jobs") or []):
                jobs.append({
                    "job": str(j.get("job") or ""),
                    "company": str(j.get("company") or ""),
                    "kw": str(j.get("kw") or ""),          # 搜索词（后续分析的分组维度）
                    "score": int(j.get("score") or 0),
                    "city": city,
                    "round": rid,
                    "t": str(j.get("t") or ""),
                    "outcome": "",                          # 由 HR 结果回填
                    # 2026-09-22 OUTCOME1：只有 applied=True 的行才是
                    # 「我们真的投过的那条」，统计回复率时必须只看这些行 ——
                    # 否则同公司的其他岗位会被一起算进去（实测已污染）。
                    "decision": str(j.get("decision") or ""),
                    # 2026-09-23 MATCHTEXT：LLM 逐岗匹配文字也折进累计库，
                    # 让历史报告/看板能引用「为什么匹配/不匹配」。旧条目无这些键，.get 兜底。
                    "why": str(j.get("why") or "")[:240],
                    "evidence": list(j.get("evidence") or [])[:3],
                    "gaps": list(j.get("gaps") or [])[:2],
                    "role": (j.get("role") or None),
                    "hits": list(j.get("hits") or []),
                    "applied": bool(j.get("applied")),
                })
            # 2026-09-22 KEEPALL：超上限**归档**，不再丢弃最老的
            if len(jobs) > 2000:
                self._archive_append("job_memory", jobs[:-2000])
            mem["jobs"] = jobs[-2000:]                      # 只留最近 2000 条
            # 关键词累计（供将来的"证据强度"计算）
            ks = dict(mem.get("keyword_stats") or {})
            for k in ((report.get("summary") or {}).get("by_keyword") or []):
                name = str(k.get("kw") or "").strip()
                if not name:
                    continue
                cur = dict(ks.get(name) or {"scanned": 0, "applied": 0,
                                             "rounds": 0, "sum_avg": 0.0})
                cur["scanned"] = int(cur.get("scanned") or 0) + int(k.get("scanned") or 0)
                cur["applied"] = int(cur.get("applied") or 0) + int(k.get("applied") or 0)
                cur["rounds"] = int(cur.get("rounds") or 0) + 1
                cur["sum_avg"] = float(cur.get("sum_avg") or 0.0) + float(k.get("avg") or 0)
                ks[name] = cur
            mem["keyword_stats"] = ks
            mem["v"] = 1
            mem["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._save_job_memory(mem)
            self.add_log("个人求职记忆已更新（累计 %d 条岗位 / %d 个关键词）"
                         % (len(mem["jobs"]), len(ks)))
        except Exception as e:
            self.add_log("个人求职记忆更新失败：%s" % str(e)[:80])

    # ---------- 关键词「HR 真实反馈」聚合（2026-09-22 KWFB1）----------
    # ⚠️ 只统计、不决策：不改关键词、不改阈值、不写 config。
    #    消费方是看板展示（桥接 fn="kw_feedback"）与影子对比（KWFB2）。
    def _kw_feedback_stats(self) -> list:
        """按关键词统计「HR 真实反馈」。求职记忆的第一个消费方。

        两种证据要分开看：
          · 匹配分（_stop_summary_llm 用的）= AI 预估这岗适不适合你；
          · 本表 = HR 真的回没回你。
        """
        try:
            mem = self._load_job_memory()
            oc = self._load_outcomes()
            agg = {}
            seen = set()
            for r in (mem.get("jobs") or []):
                kw = str(r.get("kw") or "").strip()
                co = str(r.get("company") or "").strip()
                jb = str(r.get("job") or "").strip()
                if not kw:
                    continue
                key = (kw, co, jb)
                if key in seen:      # 同一岗位跨轮次会重复出现，去重
                    continue
                seen.add(key)
                raw_applied = r.get("applied")
                legacy = raw_applied is None
                if legacy:
                    # 老数据没有 applied 字段 → 回退用决策值，并标记出来
                    applied = (str(r.get("decision") or "") == "apply")
                else:
                    applied = bool(raw_applied)
                if not applied:
                    continue
                st = str(r.get("outcome") or "").strip()
                if not st:
                    st = str((oc.get(co) or {}).get("state") or "")
                a = agg.get(kw)
                if a is None:
                    a = agg[kw] = {"kw": kw, "applied": 0, "replied": 0,
                                   "resume_sent": 0, "interview": 0,
                                   "rejected": 0, "pending": 0, "legacy": 0}
                a["applied"] += 1
                if legacy:
                    a["legacy"] += 1
                if st in ("replied", "resume_sent", "interview"):
                    a[st] += 1
                elif st == "rejected":
                    a["rejected"] += 1
                else:
                    a["pending"] += 1
            out = []
            for a in agg.values():
                pos = a["replied"] + a["resume_sent"] + a["interview"]
                n = a["applied"]
                a["positive"] = pos
                a["rate_raw"] = round(pos / n, 3) if n else 0.0
                # 贝叶斯收缩：小样本不会因为一次回复就冲到 50%
                a["rate_shrunk"] = round((pos + 2.0) / (n + 4.0), 3)
                a["enough"] = n >= 5
                out.append(a)
            out.sort(key=lambda x: (-x["rate_shrunk"], -x["applied"]))
            return out
        except Exception:
            return []

    def _write_kw_feedback(self) -> None:
        """落盘 run/kw_feedback.json（只读统计结果，失败不影响主流程）。"""
        try:
            import json as _j
            stats = self._kw_feedback_stats()
            p = RUN_DIR / "kw_feedback.json"
            p.write_text(_j.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "note": "按关键词的 HR 真实反馈（只读统计，不影响关键词与阈值）",
                "stats": stats,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _kw_shadow_compare(self, prompt: str, plan_kws: list,
                           base_obj: dict) -> str:
        """影子模式：带「HR 真实反馈」再问一次 LLM，**只记录不应用**（KWFB2）。

        ⚠️ 本方法**不写 plan、不写 config**，与现有自动应用逻辑完全隔离。
        目的：把「只看匹配分」与「带上真实反馈」两种口径的建议并排存下来，
        供判断真实反馈到底有没有用 —— 准不准要靠真实用户数据检验。

        返回可拼进气泡的说明文本；没有反馈数据时返回空串（不花 token）。
        """
        try:
            fb = self._kw_feedback_stats()
            if not fb:
                return ""            # 没有真实反馈 → 不发起额外调用
            import json as _j
            fb_rows = "\n".join(
                "· %s：投放 %d · 有效回复 %d · 拒绝 %d · 待定 %d%s" % (
                    a["kw"], a["applied"], a["positive"], a["rejected"], a["pending"],
                    "" if a["enough"] else "（样本不足，仅供参考）")
                for a in fb)
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                return ""
            self.session["llm_calls"] += 1
            extra = ("\n\n【各关键词的 HR 真实反馈】与上面的匹配分是**两种证据**：\n"
                     "匹配分 = AI 预估这岗适不适合你；下面是 HR 真的回没回你。\n"
                     "%s\n\n"
                     "请据此**再给一次**关键词调整建议：\n"
                     "· 预估分高但真实回复率极低的词 → 可考虑替换；\n"
                     "· 预估分一般但真实回复率高的词 → 建议保留；\n"
                     "· 样本不足的词不要据此下结论。" % fb_rows)
            obj2 = llm.chat_json(
                "你是求职投放策略师。直接输出 JSON，不要推理过程、不要 markdown、不要代码块。",
                prompt + extra + "\n\n【本轮关键词】\n" + "、".join(plan_kws[:20]),
                max_tokens=900, temperature=0.3) or {}
            rec = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "base": {"adjust": bool(base_obj.get("adjust")),
                         "keep": base_obj.get("keep") or [],
                         "replace": base_obj.get("replace") or [],
                         "add": base_obj.get("add") or []},
                "shadow": {"adjust": bool(obj2.get("adjust")),
                           "keep": obj2.get("keep") or [],
                           "replace": obj2.get("replace") or [],
                           "add": obj2.get("add") or [],
                           "summary": str(obj2.get("summary") or "")[:200]},
                "feedback": fb,
                "note": "影子对比：shadow 的建议**未应用**，仅用于判断真实反馈是否有用",
            }
            p = RUN_DIR / "kw_shadow.json"
            old = []
            if p.exists():
                old = _j.loads(p.read_text(encoding="utf-8")) or []
            old.append(rec)
            p.write_text(_j.dumps(old[-50:], ensure_ascii=False, indent=2),
                         encoding="utf-8")
            b, s = rec["base"], rec["shadow"]
            line = ("\n\n👥 HR 真实反馈（影子对比 · **未应用**）：\n"
                    "· 只看匹配分会：删[%s] 加[%s]\n"
                    "· 带上真实反馈会：删[%s] 加[%s]\n"
                    "（仅记录在 run/kw_shadow.json，未改动关键词与阈值）" % (
                        "/".join(b["replace"]) or "无", "/".join(b["add"]) or "无",
                        "/".join(s["replace"]) or "无", "/".join(s["add"]) or "无"))
            try:
                self.root.after(0, lambda m=line: self.add_log(
                    "影子对比已记录（未应用）：" + m.replace("\n", " ")[:110]))
            except Exception:
                pass
            return line
        except Exception as e:
            try:
                self.root.after(0, lambda s=str(e)[:80]: self.add_log(
                    "影子对比失败（已忽略）：%s" % s))
            except Exception:
                pass
            return ""

    # =============== 结果回填（2026-09-19 C3 / S）===============
    # ---------- 持久白名单（2026-09-22 GREETALL）----------
    # ⚠️ 只服务于「这条 HR 回复是不是我们投的」判定，**不参与投递主流程**。
    #    主流程走 boss_chat.load_greeted_companies()，未改动。
    def _greeted_all_path(self):
        return RUN_DIR / "greeted_all.json"

    def _load_greeted_all(self) -> dict:
        """持久白名单：我们真的打过招呼的公司 → 最近一次打招呼时间。

        `records.applied` 是**本轮基线**，`_clear_round_baseline()` 在全新一轮时
        会把它清空；而 HR 回复常常隔几小时甚至几天才来 —— 那时已进新一轮，
        applied 已被清，于是跨轮的 HR 回复认不出来源，永远进不了结果统计。
        这份文件**只增不减、永不被清**，专门解决跨轮问题。
        """
        try:
            import json as _j
            p = self._greeted_all_path()
            if not p.exists():
                return {}
            d = _j.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_greeted_all(self, data: dict) -> None:
        try:
            import json as _j
            p = self._greeted_all_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_j.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except Exception:
            pass

    def _add_greeted_all(self, company: str) -> None:
        """把一个公司记进持久白名单（幂等：重复只更新时间）。"""
        co = str(company or "").strip()
        if not co:
            return
        try:
            d = self._load_greeted_all()
            d[co] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._save_greeted_all(d)
            # 2026-09-23 GREETCACHE：同步刷新进程内缓存 —— 否则同一进程内
            # 本轮新打招呼的公司会被 _our_greeted_companies() 的旧缓存漏掉，
            # 其 HR 结果被判为「非本方案会话」→ 只进 hr_inbound、进不了 outcomes。
            _c = getattr(self, "_greeted_cache", None)
            if isinstance(_c, set):
                _c.add(co)
        except Exception:
            pass

    def _our_greeted_companies(self) -> set:
        """我们（喵）真实打过招呼的公司集合 —— 用来判断会话的**源头**。

        读投递账本的 greet + applied 记录。缓存到 self._greeted_cache，
        避免每条 HR 消息都去扫一遍日志文件。
        """
        try:
            cache = getattr(self, "_greeted_cache", None)
            if isinstance(cache, set):
                return cache
        except Exception:
            pass
        names: set = set()
        try:
            from boss import boss_chat
            for c in boss_chat.load_greeted_companies(RUN_DIR) or []:
                c = str(c or "").strip()
                if c:
                    names.add(c)
        except Exception:
            pass
        # 2026-09-22 GREETALL：并入**持久白名单**（永不被清）。
        # applied 是「本轮基线」，全新一轮会被清空 → 跨轮的 HR 回复
        # 本来认不出来源，这里补上。只影响结果统计，不影响投递。
        try:
            for c in self._load_greeted_all():
                c = str(c or "").strip()
                if c:
                    names.add(c)
        except Exception:
            pass
        try:
            self._greeted_cache = names
        except Exception:
            pass
        return names

    def _is_our_plan_conversation(self, company: str) -> bool:
        """这个会话是不是**我们方案**产生的（= 喵打过招呼）？

        场景 1（用户自己打招呼）→ False → 不进结果统计，只提醒
        场景 2（喵打招呼，中途用户接着聊）→ True → 落盘
        """
        co = str(company or "").strip()
        if not co:
            return False
        try:
            return co in self._our_greeted_companies()
        except Exception:
            return False

    def _inbound_path(self):
        """非方案来源（用户自己 / HR 主动）的来话记录 —— 只用于提醒展示。"""
        return RUN_DIR / "hr_inbound.json"

    def _load_inbound(self) -> list:
        try:
            import json as _j
            p = self._inbound_path()
            if not p.exists():
                return []
            d = _j.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _save_inbound(self, items: list) -> None:
        try:
            import json as _j
            p = self._inbound_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_j.dumps(items, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except Exception:
            pass

    def _record_inbound(self, company: str, act_type: str, *,
                        hr_name: str = "", snippet: str = "") -> None:
        """记录**非方案来源**的来话（用户自己打招呼 / HR 主动）。

        只做提醒展示，**不进结果统计**（它们没有分数）。
        """
        co = str(company or "").strip()
        if not co:
            return
        state = self.ACT_TO_OUTCOME.get(str(act_type or ""))
        if not state:
            return
        try:
            items = self._load_inbound()
            items = [x for x in items
                     if str(x.get("company") or "").strip() != co]
            items.append({"company": co, "hr_name": str(hr_name or ""),
                          "state": state,
                          "state_label": self.OUTCOME_LABELS.get(state, state),
                          "job": "",
                          "last_msg": str(snippet or "")[:80],
                          "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "source": "inbound"})
            # 只留最近 50 条，避免无限增长
            items.sort(key=lambda x: x.get("ts") or "", reverse=True)
            self._save_inbound(items[:50])
        except Exception:
            pass

    # =============== 结果回填（2026-09-19 C3）===============
    # ⭐ outcome **独立于报告**存储、按公司名做键 ——
    #    HR 回复是异步、跨轮次、跨天的，塞进「按轮次快照」的报告里必然丢。
    OUTCOME_ORDER = {"replied": 1, "resume_sent": 2, "interview": 3,
                     "rejected": 9}
    OUTCOME_LABELS = {"replied": "HR 回复", "resume_sent": "已发简历",
                      "interview": "有面试邀约", "rejected": "HR 拒绝"}
    # run_chat_monitor 已经分好类了，这里只做映射，不重复判定。
    ACT_TO_OUTCOME = {
        "chat_alert": "replied",
        # 2026-09-23 OUTMAP：补齐监听**真实发出**的信号名。
        #   boss_chat 发简历成功吐 "resume_sent"（不是 "send_resume"），
        #   检测到拒绝吐 "reject_detected"（不是 "rejection"）。
        #   原两个 key 对不上 → _record_outcome 在 `if not state` 处静默 return，
        #   导致 outcomes.json 从来没有 monitor 来源（12 条全是人工 backfill）。
        "resume_sent": "resume_sent",
        "send_resume": "resume_sent",
        "resume_request": "resume_sent",
        "interview_invite": "interview",
        "reject_detected": "rejected",
        "reject_reply": "rejected",
        "rejection": "rejected",
    }

    def _outcomes_path(self):
        return RUN_DIR / "outcomes.json"

    def _load_outcomes(self) -> dict:
        try:
            import json as _j
            p = self._outcomes_path()
            if not p.exists():
                return {}
            d = _j.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_outcomes(self, data: dict) -> None:
        try:
            import json as _j
            p = self._outcomes_path()
            # 显式建父目录：否则目录不存在时 write_text 会抛异常，
            # 而外层是宽 except → **静默丢数据**（写验证脚本时真踩到过）。
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                _j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _record_outcome(self, company: str, act_type: str, *,
                        hr_name: str = "", snippet: str = "",
                        src: str = "monitor") -> None:
        """把一条 HR 动作落成结果状态。**按公司名做键，与轮次解耦。**

        状态只升不降（replied < resume_sent < interview；rejected 终态），
        且保留 events 全历史 —— 信息不丢，将来可回溯状态演进。
        """
        co = str(company or "").strip()
        if not co:
            return
        state = self.ACT_TO_OUTCOME.get(str(act_type or ""))
        if not state:
            return  # 与结果无关的动作（如配额告警）不入账
        # 2026-09-19 S：先判**源头**。不是我们方案打的招呼
        # （用户自己打的 / HR 主动）→ 只记提醒，不进结果统计。
        if not self._is_our_plan_conversation(co):
            self._record_inbound(co, act_type, hr_name=hr_name,
                                 snippet=snippet)
            self._push_outcome_update(co, state)
            return
        try:
            data = self._load_outcomes()
            rec = data.get(co) or {"company": co, "state": "", "events": [],
                                  "source": "our_apply"}
            rec["source"] = "our_apply"
            old = str(rec.get("state") or "")
            # 只升不降；rejected 一旦写入即为终态
            if (old != "rejected"
                    and self.OUTCOME_ORDER.get(state, 0)
                    > self.OUTCOME_ORDER.get(old, 0)):
                rec["state"] = state
            if not old:
                rec["state"] = state
            ev = {"state": state, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "hr": str(hr_name or ""), "snippet": str(snippet or "")[:80],
                  "src": src}
            evs = list(rec.get("events") or [])
            # 同一状态只留最后一次，避免刷屏
            evs = [x for x in evs if x.get("state") != state]
            evs.append(ev)
            rec["events"] = evs[-20:]
            rec["ts"] = ev["ts"]
            data[co] = rec
            self._save_outcomes(data)
            if rec.get("state") != old:
                self.add_log("结果回填：%s → %s" % (
                    co, self.OUTCOME_LABELS.get(rec.get("state"), rec.get("state"))))
                # 2026-09-19 Q1 方案 A：主动通知看板（详情开着也能立刻更新）
                self._push_outcome_update(co, rec.get("state") or "")
                # 2026-09-19 V：把结果回填进求职记忆（岗位 → 结果的对应关系，
                # 这是将来算「分数段 ↔ 回复率」的原始素材）
                try:
                    _mem = self._load_job_memory()
                    _hit = 0
                    for _jb in (_mem.get("jobs") or []):
                        if str(_jb.get("company") or "").strip() == co:
                            _jb["outcome"] = rec.get("state") or ""
                            _hit += 1
                    if _hit:
                        self._save_job_memory(_mem)
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- 缓存清理（2026-09-18 新增）----------
    # ⚠️ 刻意**只清投递报告**，不提供清「去重缓存 / 账本 / 关键词历史」的入口
    #    （用户 2026-09-18 裁决）：
    #    · 两周去重缓存 boss-demo-seen.json 是**省 LLM tokens 的关键**，
    #      清掉会让同一岗位重新调 LLM 评分；将来商业化它还是重要功能；
    #    · 账本被清会丢失已投记录 → 可能重复投递同一岗位。
    #    所以这里**物理上不给别的口子**，而不是靠 UI 上不勾选来防。
    def clear_reports(self) -> dict:
        """只清投递报告（run/reports/*.json），返回清掉的份数。"""
        n = 0
        try:
            for p in self._reports_dir().glob("report-*.json"):
                try:
                    p.unlink()
                    n += 1
                except Exception:
                    pass
        except Exception as exc:
            self.add_log("报告清理失败：%s" % str(exc)[:120])
            return {"reports": n, "error": str(exc)[:120]}
        self.add_log("已清除投递报告 %d 份（去重缓存与账本未动）" % n)
        return {"reports": n}

    # ---------- 让喵读得懂历史（2026-09-18 新增）----------
    def _plan_memory_brief(self) -> str:
        """给 LLM 做方案时看的「完整回忆」：历史投放数据（2026-09-22 RECALL1）。

        与 `_recent_runs_brief`（只看最近 5 轮匹配分）互补 ——
        这里加上**跨全部历史的 HR 真实反馈**与**累计规模**。

        ⚠️ 只用于拼 prompt，**不改任何配置、不写文件**；
        没有数据时返回空串（prompt 结构与改造前一致）。
        """
        try:
            parts = []
            mem = self._load_job_memory()
            n_jobs = len(mem.get("jobs") or [])
            try:
                n_greet = len(self._load_greeted_all())
            except Exception:
                n_greet = 0
            n_oc = len(self._load_outcomes())
            if n_jobs or n_greet:
                parts.append("· 历史累计：评估过 %d 个岗位 · 已打招呼 %d 家公司 · 有 HR 结果 %d 家"
                             % (n_jobs, n_greet, n_oc))
            fb = self._kw_feedback_stats()
            if fb:
                # ⚠️ 先排「样本够」的 —— 按回复率排会把只有 1 次投放的词顶到最前，
                #    那种 60% 是噪音，会误导 LLM。可靠信号优先。
                fb = sorted(fb, key=lambda a: (not a.get("enough"), -a["rate_shrunk"]))
                rows = []
                for a in fb[:10]:
                    rows.append("  %s：投放 %d · 有效回复 %d · 拒绝 %d → 回复率 %.0f%%%s" % (
                        a["kw"], a["applied"], a["positive"], a["rejected"],
                        a["rate_shrunk"] * 100,
                        "" if a["enough"] else "（样本不足）"))
                parts.append("· 关键词真实反馈（HR 真的回没回）：\n" + "\n".join(rows))
            recent = self._recent_runs_brief()
            if recent:
                parts.append(recent)
            # 2026-09-23 MATCHTEXT：把「为什么匹配/不匹配」也带给诊断 LLM，
            # 让历史报告能引用（仅取最近有理由的 ~15 条，避免 prompt 过长）。
            try:
                _whys = []
                for _jr in (mem.get("jobs") or []):
                    _w = (_jr.get("why") or "").strip()
                    if _w:
                        _whys.append("  · %s @ %s：%s" % (
                            str(_jr.get("job") or "")[:24],
                            str(_jr.get("company") or "")[:16], _w[:120]))
                    if len(_whys) >= 15:
                        break
                if _whys:
                    parts.append("· 部分岗位的匹配理由（AI 怎么看）：\n" + "\n".join(_whys))
            except Exception:
                pass
            if not parts:
                return ""
            return ("\n\n【你的历史投放记忆】\n"
                    "⚠️ 两种证据分开看：**匹配分**是 AI 预估这岗适不适合你；"
                    "**真实反馈**是 HR 真的回没回。\n"
                    + "\n".join(parts)
                    + "\n（据此：预估分高但真实回复率极低的词优先考虑替换；"
                    "预估分一般但真实回复率高的词建议保留；"
                    "样本不足的词不要据此下结论。）\n")
        except Exception:
            return ""

    def _recent_runs_brief(self, limit: int = 5) -> str:
        """把最近几次复盘报告压成一段给 LLM 看的「投递记忆」。

        只喂**摘要层**（每轮每词的表现），**绝不喂岗位明细** ——
        明细 60 岗约 4800 tokens，那才是真正的成本；摘要只要约 350 tokens。
        没有历史时返回空串，提示词结构与改造前一致。
        """
        try:
            items = self.list_reports(limit=limit)
            if not items:
                return ""
            th = self.cfg.get("min_score", 70)
            lines = []
            agg = {}
            for it in items:
                lines.append("· %s 扫 %s · 达 %s · 均 %s · 最高 %s（岗位匹配值 %s）" % (
                    str(it.get("ts", ""))[5:16], it.get("scanned", 0),
                    it.get("applied", 0), it.get("avg", 0), it.get("top", 0), th))
                d = self.load_report(it.get("run_id", ""))
                for s in ((d or {}).get("summary") or {}).get("by_keyword") or []:
                    kw = str(s.get("kw", "")).strip()
                    if not kw:
                        continue
                    a = agg.setdefault(kw, {"n": 0, "top": 0})
                    a["n"] += 1
                    a["top"] = max(a["top"], int(s.get("top", 0) or 0))
            trend = []
            for kw, a in sorted(agg.items(), key=lambda x: -x[1]["top"])[:8]:
                if a["top"] >= th:
                    verdict = "有效"
                elif a["top"] >= th - 5:
                    verdict = "差一点，值得保留或考虑把匹配度门槛降一点"
                else:
                    verdict = "基本没跑出来"
                trend.append("· %s：跑 %d 次，最高 %d 分（%s）" % (kw, a["n"], a["top"], verdict))
            out = "【你近期的投递记忆】\n最近 %d 次：\n%s" % (len(lines), "\n".join(lines))
            if trend:
                out += "\n\n关键词表现汇总：\n%s" % "\n".join(trend)
            out += ("\n（据此判断：跑不出来的词该换；差一点的优先考虑调匹配度门槛；"
                    "有有效的就保留。别让主人反复试同一批无效词。）\n")
            return out
        except Exception:
            return ""

    def _stop_summary_llm(self, rec: dict, kw_stats: list, stopped_by_user: bool) -> None:
        # 2026-09-18 复盘报告：先落盘。
        self._write_run_report(rec, kw_stats, stopped_by_user)
        if not kw_stats:
            return
        if self._plan_change_pending:
            return
        # 2026-09-22 KWFB1：落盘「关键词 · HR 真实反馈」（只读统计，不进决策）
        self._write_kw_feedback()
        # 持久化本轮关键词表现到历史（供下次启动 LLM 优化建议用），只留最近 200 条
        try:
            import json as _j2, time as _t2
            hp = RUN_DIR / "kw_history.json"
            old = []
            if hp.exists():
                old = _j2.loads(hp.read_text(encoding="utf-8")) or []
            rec_item = {"ts": int(_t2.time()), "reason": "user_stop" if stopped_by_user else "natural",
                        "stats": kw_stats}
            old.append(rec_item)
            hp.write_text(_j2.dumps(old[-200:], ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        # 2026-09-23 SUMMARY-LITE：结束总结只展示「扫描/投递」计数，
        # 不再调用 LLM 给建议、不再自动修改用户投递方案。
        def _work():
            try:
                _n_kw = len(kw_stats)
                _scanned = sum(int(s.get("scanned") or 0) for s in kw_stats)
                _applied = sum(int(s.get("applied") or 0) for s in kw_stats)
                _head = "🛑 任务停止（手动停止）" if stopped_by_user else "✅ 任务结束"
                _body = ("""%s
📋 本轮简报
· 扫描了 %d 个关键词，共 %d 个岗位
· 实际投递 %d 个""") % (_head, _n_kw, _scanned, _applied)
                self.root.after(0, lambda: self.set_bubble(_body))
                self.add_log("停止总结（精简版）：扫描 %d / 投递 %d" % (_scanned, _applied))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self.add_log("停止总结失败：%s" % e))
        threading.Thread(target=_work, daemon=True).start()

    def _monitor_summary(self, s: dict) -> None:
        """展示真实监听（run_chat_monitor）返回的统计。"""
        actions = s.get("actions") or []
        lines = []
        for a in actions[:6]:
            t = a.get("type")
            if t == "resume_request":
                lines.append("📄 要简历：%s" % (a.get("would_send") or a.get("error") or ""))
            elif t == "resume_sent":
                lines.append("✅ 已发简历：%s" % (a.get("resume") or ""))
            elif t == "reject_detected":
                lines.append("🙅 拒绝：%s" % (a.get("will_reply") or ""))
            elif t == "reject_reply":
                lines.append("✅ 致谢已发")
            elif t == "interview_invite":
                lines.append("🎯 约面试：%s" % ((a.get("message") or "")[:40]))
            elif t == "chat_reply":
                lines.append("💬 自动回复：%s" % ((a.get("reply") or "")[:30]))
            elif t == "chat_escalate":
                lines.append("🤝 需你接管：%s" % ((a.get("message") or "")[:40]))
            elif t == "other":
                lines.append("💬 普通对话（未自动回复）：%s" % ((a.get("message") or "")[:40]))
            elif t == "system_template_skip":
                lines.append("⏭️ 跳过系统模板")
            else:
                lines.append("· %s" % t)
        body = "【HR 监听结果】\n" + (s.get("message") or "")
        if lines:
            body += "\n\n" + "\n".join(lines)
        if s.get("quota_exhausted"):
            body += "\n\n⚠️ LLM 配额已耗尽，监听自动停止。"
        self.set_bubble(body)
        self.add_log("真实监听完成：%s" % (s.get("message") or ""))

    # ---------- 消息监听（只读，后台轮询 BOSS 聊天） ----------
    def _toggle_monitor(self):
        self._monitor_on = not self._monitor_on
        if self._monitor_on:
            self._monitor_job = self.root.after(3000, self._monitor_tick)
            self.add_log("消息监听已开启（每 90 秒扫描 BOSS 聊天）")
            self.set_bubble("消息监听已开启：每 90 秒自动检查 HR 新消息，有动静会提醒你（只读不回复）。")
        else:
            if self._monitor_job:
                self.root.after_cancel(self._monitor_job)
                self._monitor_job = None
            self.add_log("消息监听已暂停")
            self.set_bubble("消息监听已暂停。")

    def _monitor_tick(self):
        if not self._monitor_on:
            return
        self._monitor_job = self.root.after(90000, self._monitor_tick)

        def _work():
            try:
                from agent.shared import is_cdp_port_ready, connect_browser
                from boss import boss_chat
                if not is_cdp_port_ready(9222):
                    return
                browser = connect_browser(9222)
                tab = browser.latest_tab
                # 登录守护：BOSS 登录退出/失效时提醒并打开登录页
                if not self._quick_login_check(tab):
                    self._alert_login_lost()
                    return
                msgs = boss_chat.read_friend_messages_classified(tab, limit=10)
                fresh = []
                for m in msgs:
                    key = (m.get("friend", ""), (m.get("content") or "")[:60])
                    if key[1] and self._seen_msgs.get(key) != 1:
                        fresh.append(m)
                if not fresh:
                    return
                for m in fresh:
                    key = (m.get("friend", ""), (m.get("content") or "")[:60])
                    self._seen_msgs[key] = 1
                m0 = fresh[-1]

                def _alert():
                    try:
                        self.root.bell()
                    except Exception:
                        pass
                    self.add_log("HR 新消息：%s" % (m0.get("content") or "")[:50])
                    self.set_bubble("「叮」收到 HR 新消息（%s）：\n%s\n会自动生成回复草稿。" % (
                        m0.get("friend", "BOSS"), (m0.get("content") or "")[:120]))

                self.root.after(0, _alert)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    # ---------- Agent 任务链：投递演练 = 唤起浏览器 → 扫描岗位 → LLM 分析 → 简报（全程不投递） ----------
    def cmd_scan_jobs(self, keyword: str = "海外运营", chain_report: bool = False):
        if self.state == "分析中":
            self.set_bubble("爬爬正在忙上一个任务，等它做完再点哦～")
            return
        # 浏览器统一门禁：无简历 / 方案未确认（未回复 OK）→ 不进入 BOSS 页面
        if not self._browser_gate():
            return
        self.set_state("分析中")
        self.set_act("think")
        try:
            from boss import boss_apply
            from agent.shared import (is_cdp_port_ready, connect_browser, find_all,
                                                 build_boss_search_url)
        except Exception as exc:
            self.set_bubble("岗位扫描模块不可用：%s" % exc)
            self.set_state("闲置")
            return
        steps = ("【扫描分析】0/3 启动浏览器 → 1/3 确认登录 → 2/3 扫描+LLM分析 → 3/3 生成简报"
                 if chain_report else "【岗位扫描】0/2 启动浏览器 → 1/2 确认登录 → 2/2 扫描+LLM分析")
        self.set_bubble(steps + "\n正在启动投递浏览器，读取「%s」真实岗位…" % keyword)
        self.add_log("开始扫描分析：%s（只读，不会发送任何消息）" % keyword)

        def _work():
            import time
            try:
                # 防待机防熄屏：分析期间电脑不休眠
                self._prevent_sleep(True)
                # 离线重放：投递演练用缓存岗位分析（零 BOSS 请求，不拉浏览器/不登录）
                if self._offline:
                    jobs = self._load_cached_jobs(5)
                    if not jobs:
                        self.root.after(0, lambda: (self.set_bubble("离线缓存无岗位，请先点「冒烟」抓取或回复「在线模式」。"),
                                                    self.set_state("闲置")))
                        return
                    lines, hits, ok = [], [], 0
                    for title, jd_text, company, _href in jobs:
                        if self._stop_requested:
                            break
                        while self._paused and not self._stop_requested:
                            time.sleep(0.4)
                        if self._stop_requested:
                            break
                        res = self._score_jd(title, jd_text or title, self.cfg, skill_dir=RUN_DIR, use_llm=True)
                        ok += 1
                        self.session["scan_jobs"] += 1
                        lines.append("%s %d分(规则) %s" % (title, res.total_score, company))
                        if res.decision == "apply":
                            hits.append("%s ｜ %s ｜ %d分" % (title, company, res.total_score))

                    def _off_done():
                        self._prevent_sleep(False)
                        if lines:
                            body = ("⚡ 离线重放：读了 %d 个缓存岗位：\n" % ok + "\n".join(lines) +
                                    ("\n\n达标可投：\n" + "\n".join(hits) if hits else "\n\n本轮无达标岗位") +
                                    "\n（缓存岗位分析，未投递，零 BOSS 请求）")
                        else:
                            body = "离线缓存无岗位可分析。"
                        if chain_report:
                            self.set_bubble(body + "\n\n【第 3 步】正在生成投递简报…")
                            self.root.after(1500, self.cmd_report)
                        else:
                            self.set_bubble(body)
                            self.set_state("闲置")

                    self.root.after(0, _off_done)
                    return
                # 第 0 步：自动启动投递浏览器（不在线时拉起，不用手动）
                self.root.after(0, lambda: self.set_bubble(steps + "\n第 0 步：启动投递浏览器…"))
                if not is_cdp_port_ready(9222):
                    self.add_log("自动拉起 9222 投递浏览器")
                    if not self._launch_browser():
                        self.root.after(0, lambda: (self.set_bubble(
                            "自动拉起投递浏览器失败，请手动启动（按交接文档）后重试。"),
                            self.set_state("闲置")))
                        return
                browser = connect_browser(9222)
                tab = browser.latest_tab
                # 第 1 步：完成登录（未登录打开登录页，登录后再继续）
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 第 0 步：浏览器已启动\n第 1 步：检查 BOSS 登录态…"))
                if not self._ensure_boss_login(tab):
                    self.root.after(0, lambda: (self.set_bubble(
                        "BOSS 未登录，扫描分析已暂停。请扫码登录后重新点「扫描分析」。"),
                        self.set_state("闲置")))
                    return
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 第 1 步：登录态 OK，正在打开 BOSS 岗位页…"))
                city_name = self.cfg.get("target_city", "广州")
                city_code = get_city_code(city_name)
                if not city_code:
                    self.add_log("城市「%s」不在支持列表，已中止扫描（支持：%s）"
                                 % (city_name, "、".join(CITY_CODES)))
                    self.root.after(0, lambda c=city_name: (self.set_bubble(
                        "⚠️ 城市「%s」不在支持列表里，我没去搜（不会偷偷换成别的城市）。\n"
                        "请在看板「设置」里改成一个支持的城市。" % c), self.set_state("闲置")))
                    return
                salary_min = self._plan.get("salary_low") or self.cfg.get("min_salary_low_k") or 0
                tab.get(build_boss_search_url(keyword, city_code, salary_min))
                time.sleep(5)
                cards = find_all(tab, boss_apply.CARD_LOCATORS, timeout=3.0)
                if not cards:
                    cards = find_all(tab, ["css:[class*=job-card]"], timeout=2.0)
                if not cards:
                    self.root.after(0, lambda: (self.set_bubble(
                        "在 BOSS 页面没读到岗位卡片。可能是需要登录、弹验证码或页面结构变了。你可以手动确认浏览器里的页面。"),
                        self.set_state("闲置")))
                    return
                lines, hits, ok = [], [], 0
                n_cards = min(len(cards), 5)
                self.root.after(0, lambda: self.set_bubble(steps + "\n✅ 第 2 步：读到 %d 个岗位，逐个 LLM 分析中（约 1 分钟）…" % n_cards))
                for card in cards[:5]:
                    # 暂停/停止检查：LLM 分析循环内也响应
                    if self._stop_requested:
                        break
                    while self._paused and not self._stop_requested:
                        time.sleep(0.4)
                    if self._stop_requested:
                        break
                    try:
                        info = boss_apply.extract_card_info(card)
                        title = info["title"]
                        if not title:
                            continue
                        # 卡片级标题预过滤：命中排除词直接跳过（不开详情、不调 LLM）
                        _title_clean = shared.normalize_text(title)
                        _blocked = None
                        for _kw in (self.cfg.get("title_exclude_keywords") or []):
                            if shared.keyword_in_text(_kw, _title_clean):
                                _blocked = _kw
                                break
                        if _blocked:
                            self.add_log("标题预过滤跳过：%s（命中排除词：%s，未点开详情）" % (title, _blocked))
                            continue
                        href, jd_text = info["href"], info["raw_text"]
                        if href:
                            try:
                                dt = browser.new_tab(href)
                                time.sleep(3)
                                jd_text = boss_apply.extract_detail_text(dt) or jd_text
                                dt.close()
                            except Exception:
                                pass
                        res = self._score_jd(title, jd_text or title, self.cfg, skill_dir=RUN_DIR, use_llm=True)
                        ok += 1
                        self.session["scan_jobs"] += 1
                        lines.append("%s %d分(规则) %s" % (title, res.total_score, info["salary"] or ""))
                        if res.decision == "apply":
                            hits.append("%s ｜ %s ｜ %s ｜ %d分" % (
                                title, info["company"] or "?", info["salary"] or "?", res.total_score))
                    except Exception as exc:
                        self.root.after(0, lambda e=exc: self.add_log("单岗位失败：%s" % e))

                def _done():
                    self._prevent_sleep(False)
                    if lines:
                        body = ("✅ 第 2 步完成：读了 %d 个真实岗位：\n" % ok + "\n".join(lines) +
                                ("\n\n达标可投：\n" + "\n".join(hits) if hits else "\n\n本轮无达标岗位") +
                                "\n（只读分析，未投递）")
                    else:
                        body = "读到岗位卡片但未提取到标题，可能页面需要登录。"
                    if chain_report:
                        self.set_bubble(body + "\n\n【第 3 步】正在生成投递简报…")
                        self.root.after(1500, self.cmd_report)
                    else:
                        self.set_bubble(body)
                        self.set_state("闲置")

                self.root.after(0, _done)
            except Exception as exc:
                self._prevent_sleep(False)
                self.root.after(0, lambda e=exc: (self.set_bubble("扫描异常：%s" % e), self.set_state("闲置")))

        threading.Thread(target=_work, daemon=True).start()

    def _boss_login_check(self, tab) -> bool:
        """强验证 BOSS 登录态：探测聊天页（未登录必跳登录页）+ 页面信号复核。
        轮询等待 SPA 跳转稳定：未登录会在 2~6 秒内跳 login，单次采样可能误判，故多次轮询。"""
        import time as _t
        logged_out = False  # 标记：一旦判断未登录，finally 不跳走
        try:
            # 1) URL 级强验证：BOSS 聊天页未登录必跳 login
            tab.get("https://www.zhipin.com/web/geek/chat")
            _confirmed = False
            for _attempt in range(4):
                _t.sleep(2.5)
                low = (tab.url or "").lower()
                if "login" in low or "/user/" in low or "zhipin.com/login" in low:
                    logged_out = True
                    return False
                # 2) 页面信号复核（防 SPA 不跳 URL、只弹登录框）
                html = ""
                try:
                    html = tab.html or ""
                except Exception:
                    pass
                if html and any(k in html for k in ("扫码登录", "立即登录", "请先登录", "手机号登录", "登录/注册")):
                    logged_out = True
                    return False
                if html and "chat" in low:
                    _confirmed = True
                    break  # 已在聊天页且无登录特征 → 已登录
            # P1 修复：4 次轮询都没确认在 chat 页 → 按未登录处理（fail-closed）
            return _confirmed
        except Exception:
            # 探测失败按未登录处理，走扫码引导（安全侧）
            logged_out = True
            return False
        finally:
            try:
                # 未登录（URL 在 login 或 HTML 有登录特征）→ 不跳走，让用户在登录页扫码
                if not logged_out:
                    low = (tab.url or "").lower()
                    # 已在 BOSS 岗位/聊天页则不重复导航
                    if "zhipin.com/web/geek" not in low:
                        tab.get("https://www.zhipin.com/web/geek/jobs?query=海外运营")
                    _t.sleep(2)
            except Exception:
                pass

    def _quick_login_check(self, tab) -> bool:
        """轻量检测当前 BOSS 页面登录态（不导航，全量页面信号）。
        P1 修复：全链路 fail-closed——非 BOSS 页面/读不到信号/检测异常都返回 False。"""
        try:
            low = (tab.url or "").lower()
            if "zhipin.com" not in low:
                return False  # 非 BOSS 页面：不确定登录态，按未登录处理
            if "login" in low or "/user/" in low or "zhipin.com/login" in low:
                return False
            html = ""
            try:
                html = tab.html or ""
            except Exception:
                pass
            if not html:
                # 读不到 HTML：不确定登录态，按未登录处理（fail-closed）
                return False
            # 已登录强特征：出现即认为已登录（优先）
            if any(k in html for k in ("退出登录", "我的简历", "收到的简历", "已投递", "个人中心", "在线简历")):
                return True
            # 未登录特征：登录框/登录引导
            if any(k in html for k in ("扫码登录", "立即登录", "请先登录", "手机号登录",
                                       "登录/注册", "密码登录", "登录后查看", "点击登录", "登录后可见")):
                return False
            # P1 修复：HTML 里既没已登录特征也没未登录特征 → 不确定，按未登录处理
            return False
        except Exception:
            # P1 修复：异常按未登录处理（fail-closed）
            return False

    def _ensure_boss_login(self, tab) -> bool:
        """打开 BOSS 检测登录态；未登录提示扫码（不重复跳登录页）。"""
        import time as _t
        if self._boss_login_check(tab):
            return True
        # _boss_login_check 已判断未登录：要么 URL 在 login/passport，要么页面有登录框
        # 不再主动 get login 页，避免重复跳转；用户扫码后说一声即可
        self.add_log("BOSS 未登录，等待用户在浏览器完成扫码后对话框告知")
        return False

    def _alert_login_lost(self):
        """检测到 BOSS 登录退出/失效：提醒用户 + 打开登录页 + 停守护（登录丢失=投递中断，等同自然关闭）。"""
        def _a():
            try:
                self.root.bell()
            except Exception:
                pass
            self.add_log("检测到 BOSS 登录已退出/失效")
            self.set_bubble("⚠️ 检测到 BOSS 登录已退出/失效。\n爬爬正在为你打开登录页，请扫码重新登录…")
        self.root.after(0, _a)
        # 登录丢失 = 投递中断：立即停守护、清投递状态（不开启 watchdog 进程）
        self._guard_tasks("disable")
        self._set_applying(False)
        try:
            from agent.shared import connect_browser
            browser = connect_browser(9222)
            browser.latest_tab.get("https://login.zhipin.com/?ka=header-login")
        except Exception:
            pass

    def _trigger_risk_block(self, reason: str) -> None:
        """行为异常达到阈值时硬停止；不依赖页面是否显示明确风控文案。"""
        try:
            (RUN_DIR / "risk_blocked.flag").write_text(
                "risk-suspected: " + str(reason), encoding="utf-8")
        except Exception:
            pass
        self._stop_requested = True
        self._paused = False
        self._guard_tasks("disable")
        self._set_applying(False)
        self.add_log("疑似 BOSS 风控，已硬停止：%s" % reason)
        self.root.after(0, lambda r=reason: self.set_bubble(
            "🛡️ 检测到疑似 BOSS 风控，已立即停止。\n%s\n请人工确认账号状态，删除 run/risk_blocked.flag 后再运行。" % r))

    # ---------- 唤起浏览器（正式投递浏览器 9222，离线则回退系统浏览器） ----------
    def _open_default(self, url: str = "https://www.zhipin.com/web/geek/jobs?query=海外运营"):
        import webbrowser
        webbrowser.open(url)

    def cmd_browser(self):
        # 浏览器统一门禁：方案未确认（未回复 OK）→ 不进入 BOSS 页面
        if not self._browser_gate():
            return
        self.set_state("投递中")
        self.set_act("wave")
        self.add_log("唤起浏览器…")
        try:
            from agent.shared import is_cdp_port_ready, connect_browser
        except Exception as exc:
            self.set_bubble("浏览器模块不可用（%s），已用系统默认浏览器打开 BOSS 岗位页。" % exc)
            self._open_default()
            self.set_state("闲置")
            return
        if not is_cdp_port_ready(9222):
            self.set_bubble("9222 投递浏览器不在线。\n已用系统默认浏览器打开 BOSS 岗位页（会自动拉起带登录态的投递浏览器）。")
            self._open_default()
            self.set_state("闲置")
            return
        self.set_bubble("检测到 9222 投递浏览器在线，正在唤起并检查 BOSS 登录态…")

        def _work():
            try:
                browser = connect_browser(9222)
                tab = browser.latest_tab
                self.root.after(0, lambda: self.set_bubble("已唤起投递浏览器，正在检查 BOSS 登录态…"))
                if not self._ensure_boss_login(tab):
                    self.root.after(0, lambda: self.set_bubble("未完成 BOSS 登录，浏览器已停在登录页，登录后可以再点「打开浏览器」。"))
                    return
                self.root.after(0, lambda: (self.set_bubble(
                    "✅ 登录态正常，已打开 BOSS「海外运营」岗位搜索页。\n只读浏览：不会发送任何消息。"),
                    self.add_log("BOSS 登录确认，已打开搜索页")))
            except Exception as exc:
                # 2026-09-18 第 44 轮修复（pyflakes 静态检查发现）：
                # except 块一结束 exc 就被删除，而这里把 exc 用在延迟回调里
                # → 回调触发时 NameError，提示反而显示不出来。
                # 用默认参数在创建 lambda 时把值绑进去。
                self.root.after(0, lambda _e=exc: (self.set_bubble(
                    "连接 9222 失败：%s\n已改用系统默认浏览器打开。" % _e),
                    self._open_default()))
            finally:
                self.root.after(0, lambda: self.set_state("闲置"))

        threading.Thread(target=_work, daemon=True).start()

    # ---------- 独立守护进程 watchdog（Chrome 掉线/喵被杀自动恢复） ----------
    def cmd_watchdog(self, action: str = "status"):
        import subprocess as _sp
        wd = DEMO_DIR / "watchdog_pet.py"
        wd_log = DEMO_DIR / "watchdog.log"

        def _running(name: str) -> bool:
            try:
                out = _sp.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                    '\\"Name=\'python.exe\'\\" | Where-Object { $_.CommandLine -like \\"*%s*\\" } | '
                    'Measure-Object | Select-Object -ExpandProperty Count"' % name,
                    capture_output=True, text=True, timeout=30, shell=True)
                return (out.stdout or "").strip().isdigit() and int((out.stdout or "").strip()) > 0
            except Exception:
                return False

        if action == "start":
            if _running("watchdog_pet.py"):
                self.set_bubble("🟢 守护进程已在运行（每 10 分钟检测 Chrome 与喵进程）。")
                return
            try:
                _sp.Popen([sys.executable, str(wd)], cwd=str(DEMO_DIR),
                          creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
                self.set_bubble("✅ 守护进程已启动：每 10 分钟检测一次。\n"
                                "Chrome(9222) 掉线 → 自动拉起；喵被杀 → 自动重启。\n"
                                "日志：watchdog.log（对话框说「守护状态」查看）")
                self.add_log("守护进程已启动")
            except Exception as exc:
                self.set_bubble("守护进程启动失败：%s" % exc)
            return
        if action == "stop":
            try:
                _sp.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                    '\\"Name=\'python.exe\'\\" | Where-Object { $_.CommandLine -like \\"*watchdog_pet.py*\\" } | '
                    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
                    capture_output=True, text=True, timeout=30, shell=True)
                self.set_bubble("🛑 守护进程已停止。")
                self.add_log("守护进程已停止")
            except Exception as exc:
                self.set_bubble("停止守护失败：%s" % exc)
            return

        # 状态
        lines = []
        lines.append("🟢 守护进程运行中" if _running("watchdog_pet.py") else "🔴 守护进程未运行（说「守护启动」开启）")
        try:
            from agent.shared import is_cdp_port_ready
            lines.append("Chrome(9222)：%s" % ("✅ 在线" if is_cdp_port_ready(9222) else "❌ 掉线（守护会自动拉起）"))
        except Exception:
            lines.append("Chrome(9222)：检测失败")
        lines.append("喵进程：%s" % ("✅ 运行中" if _running("job-pet-demo\\\\main.py") else "❌ 未运行（守护会自动重启）"))
        tail = ""
        try:
            if wd_log.exists():
                tail = "\n".join(wd_log.read_text(encoding="utf-8").strip().splitlines()[-8:])
        except Exception:
            pass
        self.set_bubble("\n".join(lines) + (("\n\n最近日志：\n" + tail) if tail else ""))
        self.add_log("守护状态查询")

    # ---------- 对话入口 ----------
    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.add_log("你说：%s" % text)
        # 本地兜底：看看方案 → 任何状态都直接展示
        if any(k in text for k in ("看看方案", "看方案", "方案是什么", "当前方案", "简历方案", "投放方案", "怎么投的", "策略是什么")):
            self._show_current_plan("好的，这是当前方案：")
            return
        if any(k in text for k in ("开启后台", "后台模式开启", "最小化运行", "后台运行")):
            self._set_background_mode(True)
            return
        if any(k in text for k in ("关闭后台", "后台模式关闭", "取消最小化", "显示浏览器")):
            self._set_background_mode(False)
            return
        # 停止状态查询：最高优先级（必须在「停止」之前，否则被停止命令截获）
        if any(k in text for k in ("停止状态", "查状态", "我停没停", "停没停", "停了吗", "状态查询")):
            self.cmd_stop_status()
            return
        # 2026-09-23 STOPBTN：停止改由「停止投递」按钮触发；这里只处理**兜底词**
        #（looks_like_stop_request 已收窄到 停止投递 / 停止找工作 / 紧急停止）。
        if looks_like_stop_request(text):
            self.cmd_stop()
            return
        # 对话框直接收文件：输入 PDF/图片/Word 路径 → 简历分析
        cand = text.strip().strip('"').strip("'")
        if Path(cand).exists() and Path(cand).suffix.lower() in RESUME_EXTS:
            self.cmd_resume_file(cand)
            return
        # 2026-09-24 ROUTESLIM：提问 / 求支招**最先**接住 → 交 LLM 问答。
        # 位置：硬命令门禁（看方案 / 后台 / 停止状态 / 停止 / 文件路径）之后，
        #      其余状态门禁与关键词路由之前 —— 既不抢硬命令，
        #      又让「随便说」的提问不再撞进某个动作分支。
        # 例外：简报 / 日报类说法仍走汇报分支（见排除表）。
        if (any(q in text for q in (
                "文案", "话术", "模板", "开场白", "支招", "教我", "帮我写", "帮我想",
                "帮我分析", "帮我看看", "帮我推荐", "帮我改",
                "怎么", "怎样", "如何", "为什么", "是不是", "能不能", "可不可以",
                "介绍一下", "讲讲", "说一下", "建议", "意见", "看法", "推荐", "觉得",
                "多少", "几个", "哪", "啥", "吗", "？", "?"))
                and not any(w in text for w in ("今天怎么样", "简报", "日报", "总结", "汇总"))):
            self.set_bubble("爬爬正在用 LLM 理解你的话，稍等…")
            threading.Thread(target=self._llm_agent_handle, args=(text,), daemon=True).start()
            return
        # 方案修改正在后台重算时，保持停机门禁；不能让“OK”或其他指令
        # 通过旧方案状态抢跑。待新方案展示后再由下方 review 分支接收确认。
        if self._plan_change_pending and self._plan_state != "review":
            self.set_bubble("🔧 新方案正在调整中，当前流程已停止。方案展示后请回复 OK 才能继续。")
            return
        # 夜间风险确认门禁：启动或跨时段暂停后，只接受 OK/停止。
        if self._night_confirmation_pending:
            if text.strip().lower() in shared.NIGHT_CONFIRM_WORDS:
                self._night_confirmation_pending = False
                self._night_confirmed_for_run = True
                # 2026-09-20 CAT：确认夜间风险 → 桌宠「起床」，切回白天素材
                self._emit_pet_state("wake")
                self._paused = False
                self.set_bubble("✅ 已确认夜间风险，继续当前流程。")
                self.add_log("用户确认夜间运行风险，继续投递")
                # 修复：如果是启动时遇到夜间风险（还没真正开始），重新触发投递
                if self.state in ("闲置", "待命中") or not self._st.get("started"):
                    self.root.after(500, lambda: self.cmd_test_run(real=getattr(self, '_pending_real', True)))
            else:
                # 用户说改方案 → 取消夜间确认，回到方案审核环节让他改
                if looks_like_plan_change(text):
                    self._night_confirmation_pending = False
                    self.add_log("夜间确认中用户要求改方案，回到方案审核")
                    self._revise_plan(text)
                    return
                # 2026-09-24 NIGHTSTOP：夜间门禁里说「停止/算了/不投…」= **放弃本次启动**
                #（不是停正在跑的投递；此时还没进入投递）。上一轮收窄停止词后
                # 提示里的「回复停止」失效了，这里补回来。
                if any(w in text for w in ("停止", "算了", "不投", "取消", "结束",
                                            "不用", "先不", "别投", "不搞", "不跑了",
                                            "不开始", "退出")):
                    self._night_confirmation_pending = False
                    self._night_confirmed_for_run = False
                    self._paused = False
                    self.set_bubble("🛑 好的，本次夜间投递已取消、没有启动。\n白天（09:00 之后）想跑再点「开始投递」就行～")
                    self.add_log("夜间确认：用户选择不继续 → 取消本次启动（未进入投递）")
                    return
                self.set_bubble("当前仍在夜间风险门禁，请回复 OK 继续，或回复停止结束。")
            return
        # 环境门禁（修改1b）：Chrome 安装等待 → LLM 判断是否装好 → 拉起 Chrome 为硬门槛
        if self._install_waiting:
            self.set_bubble("正在检查 Chrome 环境…")
            threading.Thread(target=self._handle_install_msg, args=(text,), daemon=True).start()
            return
        # 投递进行中（不在各类等待态时）：未命中固定停止词 → LLM 统一判断意图
        # （修改4：非固定停止词由 LLM 把关是否真停止；修改5：中途问情况→LLM 生成报告）
        _in_wait = (self._login_waiting or self._resume_upload_waiting
                    or self._resume_choice_waiting or self._plan_change_pending)
        # 【硬命令】最高优先级：不走 LLM，直接执行（方案1：命令放 LLM 之前）
        if any(k in text for k in ("取消两周去重", "清除缓存", "清除去重", "重新打分", "去掉去重", "清空去重")):
            seen_file = RUN_DIR / "boss-demo-seen.json"
            try:
                if seen_file.exists():
                    seen_file.unlink()
                    self.set_bubble("✅ 已清除两周去重缓存！\n之前打过的岗位，下一轮会重新调 LLM 打分。")
                    self.add_log("用户硬命令清除两周去重缓存（boss-demo-seen.json 已删除）")
                else:
                    self.set_bubble("ℹ️ 去重缓存本来就是空的，没有需要清除的。")
            except Exception as e:
                self.set_bubble("❌ 清除去重缓存失败：%s" % str(e)[:80])
            return
        if (not _in_wait and not self._stop_requested
                and self.state in ("分析中", "投递中", "沟通中")):
            # 正在投递（含暂停）：LLM 判断 stop / report / other
            threading.Thread(target=self._llm_judge_during_run, args=(text,), daemon=True).start()
            return
        # 门禁B 登录等待（修改3）：用户告知登录完成 → LLM 判断 → 重检登录
        if self._login_waiting:
            if self._login_checking:
                self.set_bubble("正在确认登录状态，请稍候…")
                return
            self.set_bubble("正在确认登录状态…")
            threading.Thread(target=self._handle_login_msg, args=(text,), daemon=True).start()
            return
        # 新增情况2 上传等待：用户告知传好 / 询问怎么传 → LLM 判断引导
        if self._resume_upload_waiting:
            self.set_bubble("正在检查附件简历…")
            threading.Thread(target=self._handle_upload_msg, args=(text,), daemon=True).start()
            return
        # 附件简历选择等待：回复序号（硬门槛：必须选 1~N，无 0 跳过、无默认）
        if self._resume_choice_waiting:
            if text.isdigit():
                idx = int(text)
                if 1 <= idx <= len(self._resume_choice_list):
                    sel = self._resume_choice_list[idx - 1]
                    self._resume_choice_selected = sel["name"]
                    pdf = self._find_local_resume(sel["name"])
                    self._save_resume_send_config(sel["name"], pdf)
                    self.set_bubble("✅ 已选择：BOSS 要简历时发送「%s」%s\n继续跑投递流程…" % (
                        sel["name"], "（本地文件已匹配）" if pdf else ""))
                    self.add_log("已选择附件简历：%s" % sel["name"])
                else:
                    self.set_bubble("序号不对，必须回复 1~%d 选一份（没有默认、不能跳过）。" % len(self._resume_choice_list))
                    return
            else:
                self.set_bubble("爬爬正在等你选附件简历，请回复序号（1~%d）或直接点列表。必须选一份才能开始投递。" % len(self._resume_choice_list))
                return
            self._resume_choice_waiting = False
            return
        # 2026-09-24 ROUTESLIM：提问 / 求支招的直通已上移到 send() 前段（见上文），
        # 这里不再重复判定。
        # 投放方案审核：回复修改意见 / 确认开投
        if self._plan_state == "review":
            _txt = text.lower()  # OK/ok/O K 统一小写比较，避免大小写不匹配被误判为修改
            # 2026-09-19 R：**要素不齐时优先当要素答案** —— 否则用户回答「广州」
            # 既可能被当成改方案、又可能因为含"ok"之类被误判成确认开投。
            _miss = self._plan_missing_fields()
            if _miss:
                _f = _miss[0]
                _got = False
                if _f == "city":
                    _c = self._parse_city_answer(text)
                    if _c:
                        self._plan["city"] = _c
                        self.cfg["target_city"] = _c
                        _got = True
                        self.add_log("用户补充求职城市：%s" % _c)
                else:
                    _s = self._parse_salary_answer(text)
                    if _s:
                        self._plan["salary_low"] = int(_s[0])
                        self._plan["salary_high"] = int(_s[1])
                        _got = True
                        self.add_log("用户补充期望薪资：%s-%sK" % (int(_s[0]), int(_s[1])))
                try:
                    import json as _json_r
                    _cp = RUN_DIR / "config.json"
                    _cc = _json_r.loads(_cp.read_text(encoding="utf-8"))
                    if self._plan.get("city"):
                        _cc["target_city"] = self._plan["city"]
                    if self._plan.get("salary_low") and self._plan.get("salary_high"):
                        _cc["min_salary_low_k"] = int(self._plan["salary_low"])
                        _cc["min_salary_high_k"] = int(self._plan["salary_high"])
                    _cp.write_text(_json_r.dumps(_cc, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
                except Exception:
                    pass
                if not _got:
                    self.set_bubble("没太看懂，能再说一次吗？\n\n" + self._ask_missing_field(_f))
                    return
                self._save_plan_state()
                self._show_current_plan()
                _rest = self._plan_missing_fields()
                if _rest:
                    self.set_bubble(self._ask_missing_field(_rest[0]))
                return
            # 2026-09-19 P②：补上此前漏掉的修改信号。
            # 「增加运营经理」「放在排除词中」「往后挪」「第X位」都不在原表里，
            # 于是落到确认分支被误判（配合①的 ok 子串 bug，直接开投）。
            revise_hint = any(k in text for k in (
                "修改", "调整", "优化", "换成", "去掉", "删掉", "加上", "加入", "添加",
                "增加", "排除", "屏蔽词", "往后", "往後", "挪", "顺序", "次序",
                "第一位", "第二位", "第三位", "第四位", "放第一", "排第一",
                "阈值", "薪资", "工资", "降到", "升到", "提到", "提高到", "降低到",
                # 2026-09-19 W：新文案「岗位匹配值」也要能触发修改（"阈值"保留兼容）
                "岗位匹配值",
                "改成", "改为", "加个", "不要", "屏蔽", "换个", "换词"))
            # 2026-09-19 P①：确认短语照旧，但 **"ok" 必须独立成词**。
            # 原实现用子串匹配 → "TikTok" 含 "ok" → 用户想排除 TikTok 反而被判成确认开投。
            _confirm_phrase = any(k in _txt for k in (
                "确认", "通过", "没问题", "就这个", "可以了",
                "同意", "方案可以", "就这样", "好了"))
            # 把非字母数字（含中文）都视为分隔符，再判断 " ok " 是否独立出现
            _norm = "".join(
                ch if (ch.isalnum() or "\u4e00" <= ch <= "\u9fff") else " " for ch in _txt)
            _ok_word = (" ok " in (" " + _norm + " ")) or _norm.strip() == "ok"
            if revise_hint:
                self._revise_plan(text)
            elif _confirm_phrase or _ok_word:
                # 2026-09-23 STARTBTN：确认开投改由「点开始投递按钮」完成（聊天不再启动投递）
                self.set_bubble("▶ 方案已就绪。开投请点对话框的「开始投递」按钮（聊天不能启动投递）。")
            else:
                self._revise_plan(text)
            return
        if any(k in text for k in ("真实投递", "真投", "正式投递", "真的投", "开始真投", "真实打招呼", "真打招")):
            # 2026-09-23 STARTBTN：聊天不再启动投递 → 提示点按钮
            self.set_bubble("▶ 投递请点对话框的「开始投递」按钮（聊天不能启动投递）。")
        elif any(k in text for k in ("冒烟", "冒烟验证", "链路检查", "链路检测")):
            self.cmd_smoke()
        elif any(k in text for k in ("LLM接管", "LLM接手", "Agent接管", "智能接管", "AI接管", "开接管")):
            self._llm_agent_enabled = True
            self.set_bubble("已开启【LLM 主控接管】：下次方案确认后，投递决策（换词/岗位匹配值/停止）由 LLM 接手，喵执行。\n附件简历确认仍是必过门禁，LLM 不跳过。")
        elif any(k in text for k in ("关闭LLM接管", "关接管", "普通模式", "不接管", "LLM不管")):
            self._llm_agent_enabled = False
            self._llm_agent = False
            self._llm_agent_pending = False
            self.set_bubble("已关闭【LLM 主控接管】：投递决策回到固定规则（按岗位匹配值打分）。")
        elif any(k in text for k in ("离线模式", "缓存模式", "离线重放", "缓存重放", "用缓存")):
            self._set_offline(True)
            self.set_bubble("已切换为【离线重放模式】：岗位读本地缓存，零 BOSS 请求。\n「开始投递」「投递演练」全部离线跑；想验证真实浏览器链路时点「冒烟」。")
        elif any(k in text for k in ("在线模式", "真实模式", "切回真实", "恢复真实")):
            self._set_offline(False)
            self.set_bubble("已切换为【在线模式】：岗位读真实 BOSS（注意控制频次，建议每天最多 1 次冒烟）。")
        # 2026-09-21 DEAD2：此处原有「取消两周去重」等关键词的 elif 分支，
        # 但 send() 开头的硬命令块（同一组关键词、带 return）已经先截获，
        # 本支 100% 不可达 → 删除，避免"改了却不生效"。
        elif any(k in text for k in ("开始投递", "测试", "全流程", "完整流程", "搞定", "一条龙", "跑一遍",
                                   "开始找工作", "开始投递", "开始求职")):
            # 2026-09-23 STARTBTN：聊天不再启动投递 → 提示点按钮
            self.set_bubble("▶ 投递请点对话框的「开始投递」按钮（聊天不能启动投递）。")
        # 2026-09-21 ROUTE1：删掉扫描分支后，这些「投递类」词恢复为**真实投递**
        elif any(k in text for k in ("打招呼", "应聘", "去投")):
            # 2026-09-23 STARTBTN：聊天不再启动投递 → 提示点按钮
            self.set_bubble("▶ 投递请点对话框的「开始投递」按钮（聊天不能启动投递）。")
        elif ("投递" in text
              and not any(w in text for w in ("方案", "情况", "简报", "记录", "统计",
                                              "数量", "多少", "进度", "结果", "投递中", "投递率"))):
            # 裸「投递」→ 真实投递。排除查看类说法（投递方案/投递情况/投递中…），
            # 否则「投递方案」会被当成开始投递 —— 那会真的给 HR 发消息。
            # 2026-09-23 STARTBTN：聊天不再启动投递 → 提示点按钮
            self.set_bubble("▶ 投递请点对话框的「开始投递」按钮（聊天不能启动投递）。")
        elif any(k in text for k in ("求职配置", "看看配置", "配置是什么")):
            self.cmd_config()
        # 2026-09-24 ROUTESLIM2：收窄通用词（去掉「看岗位」「真实岗位」这类）
        elif any(k in text for k in ("选岗位", "扫岗位", "扫描岗位", "岗位分析",
                                     "浏览器分析", "看看岗位")):
            self.cmd_scan_jobs()
        # 2026-09-24 ROUTESLIM2：收窄通用词（原「浏览器/BOSS」太宽，含「BOSS」的句子都会开浏览器）
        elif any(k in text for k in ("打开浏览器", "打开BOSS", "打开 BOSS", "开浏览器",
                                     "启动浏览器", "打开网页", "打开招聘网站")):
            self.cmd_browser()
        elif any(k in text for k in ("守护启动", "守护开", "启动守护", "开守护", "保活开")):
            self.cmd_watchdog("start")
        elif any(k in text for k in ("守护停止", "守护关", "停止守护", "关守护", "关保活")):
            self.cmd_watchdog("stop")
        elif any(k in text for k in ("守护状态",)):
            self.cmd_stop_status()
        elif any(k in text for k in ("守护", "watchdog", "保活", "掉线自动")):
            self.cmd_watchdog("status")
        # 2026-09-24 ROUTESLIM2：收窄通用词（去掉「发简历」——含它的句子都会去查附件）
        elif any(k in text for k in ("附件简历", "账号简历", "我的附件",
                                     "查看附件", "有哪些附件", "看附件简历")):
            self.cmd_boss_resumes()
        # 2026-09-23 NOPICKER：收文件只走「拖到猫身上 / 对话框发路径」；
        # 「我的简历 / 简历内容 / 我的情况 / 背景」等关键词不再触发简历分支（原来会弹选文件框）。
        elif any(k in text for k in ("简报", "日报", "总结", "汇总", "今天怎么样")):
            self.cmd_report()
        # 2026-09-17 移除死分支：原此处为
        #     elif any(k in text for k in ("投递", "打招呼", "发简历", "应聘", "去投")):
        #         self.cmd_apply()
        # 该分支 100% 不可达 —— 这 5 个关键词已全部被更靠前的「投递演练」分支
        # （其关键词表含 "投递","打招呼","发简历","应聘","去投"）截获；
        # 且 PetApp 中并不存在 cmd_apply 方法（127 个方法内无此名），
        # 一旦可达即抛 AttributeError。故删除，避免留下"看似可用实则必崩"的死分支。
        # 现状：输入「投递」实际路由到 cmd_scan_jobs（投递演练，真实岗位但不真实投递）。
        # 2026-09-24 ROUTESLIM：收窄通用词（原「消息/HR/回复/提醒/面试/叮」太宽，
        # 任何含「回复」的句子都会去模拟 HR 消息）→ 只认明确说法。
        elif any(k in text for k in ("模拟HR", "模拟 HR", "模拟消息", "模拟面试",
                                     "模拟提醒", "面试提醒", "叮一下")):
            self.cmd_chat()
        # 2026-09-24 ROUTESLIM：收窄通用词（原「分析/岗位/看看/扫描/有什么」太宽，
        # 任何含这些词的句子都会被抢去分析）→ 只认明确说法。
        elif any(k in text for k in ("分析岗位", "岗位分析", "给我分析", "帮我分析",
                                     "岗位评分", "评分一下", "分析一下")):
            self.cmd_analyze()
        else:
            # 本地拦截：修改方案 → 直接走 _revise_plan，不丢给 LLM Agent
            if looks_like_plan_change(text):
                if self.state in ("投递中", "沟通中") or self._paused:
                    self.set_bubble(
                        "⚠️ 正在投递中，不能修改方案。\n请先点「停止投递」按钮停掉当前任务，\n停止后再跟我说你要改什么，我会重新生成方案给你确认。")
                    self.add_log("投递中收到方案修改请求，已拦截（提示先停止）")
                    return
                self._revise_plan(text)
                return
            # LLM Agent：交给 aiaaa.cc LLM（分析岗位同一个）理解意图并执行/回复
            self.set_bubble("爬爬正在用 LLM 理解你的话，稍等…")
            threading.Thread(target=self._llm_agent_handle, args=(text,), daemon=True).start()

    def _llm_judge_during_run(self, text: str):
        """投递进行中判断 stop / report / view_plan / plan_change / reselect_resume / other。"""
        import json as _j, re as _re
        try:
            # 本地兜底：看看方案 → 直接展示，不走 LLM
            if any(k in text for k in ("看看方案", "看方案", "方案是什么", "当前方案", "简历方案", "投放方案", "怎么投的", "策略是什么")):
                self._show_current_plan("好的，这是当前方案：")
                return
            # 本地兜底：问进展 → 直接生成报告，不走 LLM
            if any(k in text for k in ("投了多少", "进展如何", "怎么样了", "报告呢", "投了几个", "今天投了")):
                rec = getattr(self, "_live_rec", None) or {}
                self._llm_live_report(rec)
                return
            if looks_like_stop_request(text):
                self.root.after(0, lambda: self.cmd_stop())
                return
            # 方案修改是安全门禁，不依赖 LLM 是否在线；先用本地规则拦截并回到确认态。
            if looks_like_plan_change(text):
                self._request_plan_change_during_run(text, "检测到你要修改投放方案")
                return
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                self._warn_llm_runtime("LLM 未配置或 API Key 不可用")
                return
            self.session["llm_calls"] += 1
            rec = getattr(self, "_live_rec", None) or {}
            plan = self._plan or {}
            sys_p = (
                "你是「找工作喵」求职 Agent（猫名：爬爬）。投递正在进行中，用户发来一句话。\n"
                "当前进度：%s\n"
                "当前关键词池前 8 个：%s\n"
                "岗位匹配值：%s\n"
                "判断用户意图，只输出 JSON：{\"intent\": \"...\", \"reply\": \"...\"}\n"
                "intent 取值：\n"
                "- view_plan：用户想看看当前投放方案/简历方案/当前策略（如：看看方案/方案是什么/当前方案/简历方案/投放方案/现在怎么投的）。这是查看信息，不是修改。\n"
                "- stop：用户要求停止——但**聊天不能停止投递**，只能提示用户点「停止投递」按钮。\n"
                "- report：用户想了解投递进展和结果（如：投得怎样/进展如何/报告呢/现在投了多少/怎么样了/今天投了几个）。这是问投递结果，不是问方案。\n"
                "- plan_change：用户明确要求改变投放参数（岗位/关键词/薪资/岗位匹配值/排除词/求职方向等），例如“薪资改到15K”“增加后端关键词”“屏蔽兼职”。投递中只能提示先停止，不能自动修改。\n"
                "- reselect_resume：用户想重新选择要发送的附件简历（如：简历选错了/重选简历/换一份简历发/发错简历了）。\n"
                "- clear_dedup：用户要清除两周去重缓存/重新打分（如：取消两周去重/清除缓存/清除去重/重新打分/去掉去重/清空去重）。\n"
                "\n【回答用户提问时须知】\n"
                "- 用户问「能不能屏蔽某家公司 / 不想看到某家公司」时回答：可以，\n"
                "  把公司名加进屏蔽词即可，屏蔽词同时作用于岗位标题/JD/公司名，\n"
                "  加进去之后这家公司的岗位就不再投了。\n"
                "  注意：公司名维度只认 3 个中文字及以上的词（如「某某网络」）；\n"
                "  2 个字（电商/网络/科技）不会用来屏蔽公司，避免误杀一整片公司。\n"
                "  BOSS 直聘 App 本身也有屏蔽公司的功能，可提示用户也可在那里设置。\n"
                "- other：其他指令或闲聊（如“你是什么猫”“可以和我聊天吗”“怎么操作”，都不能判为 plan_change）。\n"
                "reply 用一句中文复述判断（给用户看）。\n"
                "重要区分：「看看方案」「方案是什么」→ view_plan；「投了多少」「进展如何」→ report。"
            ) % (_j.dumps(rec, ensure_ascii=False),
                 "、".join((plan.get("keywords") or [])[:8]),
                 plan.get("min_score", 75))
            raw = (llm.chat_text(sys_p, text, max_tokens=200, temperature=0.2) or "").strip()
            m = _re.search(r"\{.*\}", raw, _re.S)
            intent, reply = "other", raw
            if m:
                try:
                    obj = _j.loads(m.group(0))
                    intent = obj.get("intent", "other")
                    reply = obj.get("reply") or raw
                except Exception:
                    pass
            # LLM 误判或服务不可用时，明确的方案修改词仍必须回到确认门禁。
            if intent == "other" and looks_like_plan_change(text):
                intent = "plan_change"
            if intent == "stop":
                # 2026-09-23 STOPBTN：聊天不再停止投递 → 提示点按钮（兜底词已在上游处理）
                self.root.after(0, lambda: self.set_bubble(
                    "⏹ 停止投递请点对话框的「停止投递」按钮（聊天不能停止）。"))
            elif intent == "plan_change":
                self._request_plan_change_during_run(text, reply)
            elif intent == "reselect_resume":
                self._resume_reselect_requested = True
                self.root.after(0, lambda r=reply: self.set_bubble(
                    "🔄 %s\n→ 已记下：下个关键词开始前，回到附件简历环节让你重选。" % r))
                self.add_log("用户要求重选附件简历（下个关键词前执行）")
            elif intent == "clear_dedup":
                # 方案2：LLM 工具调用——清除两周去重缓存
                seen_file = RUN_DIR / "boss-demo-seen.json"
                try:
                    if seen_file.exists():
                        seen_file.unlink()
                        self.root.after(0, lambda r=reply: self.set_bubble(
                            "🧹 %s\n→ 已清除两周去重缓存，之前打过的岗位下一轮会重新调 LLM 打分。" % r))
                        self.add_log("LLM 调用清除两周去重缓存（boss-demo-seen.json 已删除）")
                    else:
                        self.root.after(0, lambda r=reply: self.set_bubble(
                            "ℹ️ %s\n→ 去重缓存本来就是空的。" % r))
                except Exception as e:
                    self.root.after(0, lambda r=reply, e=e: self.set_bubble(
                        "❌ %s\n→ 清除失败：%s" % (r, str(e)[:60])))
            elif intent == "report":
                self._llm_live_report(rec)
            elif intent == "view_plan":
                self._show_current_plan(reply)
            else:
                # 说话通道（改造层1，保守版）：intent=other（闲聊/其他）不再复述判断，
                # 改走爬爬人格通道。**intent 的判定本身未改动** —— 上面那次调用的
                # system prompt / temperature 一字未改，所以 stop / report /
                # plan_change 等分类结果与改造前完全一致。
                # 保守版刻意保留本函数里「reply 用一句中文复述判断（给用户看）」那行：
                # 它与 intent 分类在同一次 LLM 调用里，改措辞有极小概率影响分类稳定性。
                pet_reply = self._reply_as_pet(text, llm)
                shown = (pet_reply or reply)[:400]
                self.root.after(0, lambda r=shown: self.set_bubble("爬爬：%s" % r))
        except Exception as exc:
            self._warn_llm_runtime(str(exc))

    def _request_plan_change_during_run(self, text: str, reply: str = "") -> None:
        """运行中修改方案：不自动改，提示用户先手动停止任务。"""
        self.root.after(0, lambda r=reply: self.set_bubble(
            "🔧 %s\n⚠️ 正在投递中，不能修改方案。请先点「停止投递」按钮停掉当前任务，\n"
            "停止后再跟我说你要改什么（如：薪资改15K / 去掉XX词），我会重新生成方案给你确认。" % (r or "收到方案修改")))
        self.add_log("投递中收到方案修改请求，已提示先停止任务（未自动改）")

    def _plan_body(self, title: str, for_review: bool = False) -> str:
        """方案展示文本的**唯一来源**（2026-09-19 W）。

        原先两处各写一套：`_enter_plan_review`（简历生成后）与
        `_show_current_plan`（用户喊「看看方案」），格式不一致。
        现在都走这里 —— 只有「审核中」才额外附「投放规则 + 开投引导」。

        优化：关键词单独成段放最前；关键项「标签 + 值」；排除词只列前 6 个并显示总数。
        文案：「匹配阈值」→「岗位匹配值」，并附一句含义（≥N 才打招呼）。
        """
        plan = self._plan or {}
        kws = plan.get("keywords") or []
        pt = plan.get("exclude_pt", False)
        ms = plan.get("min_score") or self.cfg.get("min_score", 70)
        sl = plan.get("salary_low") or self.cfg.get("min_salary_low_k", "")
        sh = plan.get("salary_high") or self.cfg.get("min_salary_high_k", "")
        city = plan.get("city") or self.cfg.get("target_city", "未设置")
        ex_all = list(dict.fromkeys([
            *(self.cfg.get("exclude_keywords") or []),
            *(plan.get("exclude_add") or []),
        ]))
        # 2026-09-19 X：用户要求**不为了美观隐藏内容** —— 全部列出。
        # （原实现只列前 6 个，是我自己加的截断，撤回）
        ex_show = "、".join(ex_all) or "无"
        ex_more = ("（共 %d 个）" % len(ex_all)) if ex_all else ""
        body = (
            "📋 %s\n\n"
            "🎯 关键词（%d）：\n%s\n\n"
            "📍 城市：%s\n"
            "👔 方向：%s\n"
            "📊 岗位匹配值（100 满分）：%s 分（≥%s 才打招呼）\n"
            "💰 期望薪资：%s-%sK\n"
            "🚫 排除词：%s %s\n"
            % (title, len(kws), "、".join(kws) or "（无）",
               city, "正式工作" if pt else "实习", ms, ms, sl, sh,
               ex_show, ex_more))
        if for_review:
            body += (
                "\n──────────\n"
                "🚀 投放规则：\n"
                "· 打招呼满 50 或发出简历 20 份 → 停止\n"
                "· 单关键词扫 30 条无一达标 → 换关键词\n\n"
                "🔧 要改直接说（如「去掉直播运营」「岗位匹配值调到 80」），\n"
                "   或点「开始投递」按钮开投。"
            )
        else:
            body += "\n\n要修改就直接说，比如「薪资改到 20K」。"
        return body

    def _show_current_plan(self, reply: str = ""):
        """展示当前投放方案（投递中用户问方案时调用）。"""
        plan = self._plan or {}
        kws = plan.get("keywords") or []
        # 还没生成方案
        if not kws:
            self.root.after(0, lambda: self.set_bubble(
                "还没生成投放方案呢。先把简历文件拖到窗口上，我分析完简历就会生成方案给你看。"))
            return
        pt = plan.get("exclude_pt", False)
        ms = plan.get("min_score") or self.cfg.get("min_score", 70)
        sl = plan.get("salary_low") or self.cfg.get("min_salary_low_k", "")
        sh = plan.get("salary_high") or self.cfg.get("min_salary_high_k", "")
        city = plan.get("city") or self.cfg.get("target_city", "广州")
        body = self._plan_body(reply or "当前投放方案", for_review=False)
        self.root.after(0, lambda: self.set_bubble(body))

        # 2026-09-23 HISTREPORT：首次唤出「投递方案」时顺带生成历史报告（本会话仅一次）。
        # 先给一句提示，再后台生成 —— 用户注意力在方案上，报告稍后补上可一并参考。
        # 注：cmd_startup_diagnosis 自身已吞掉所有异常，这里用 lambda 起线程即可（不新增方法）。
        # 2026-09-23 前置判断：零历史数据不弹「整理中」提示（避免「帮你整理→跳过：暂无数据」
        # 自相矛盾）；也不置 _hist_report_done，等以后有真实数据再触发。
        try:
            _dec = self._hist_report_decision()
            if _dec == "skip":
                pass
            elif _dec == "refresh":
                # 2026-09-23 HISTCACHE：数据有更新才重新调 LLM 出报告
                self._save_hist_fingerprint()
                self.root.after(0, lambda: self.set_bubble(
                    "📋 我顺便帮你整理一份历史投递报告，稍等一下，可以和方案一起参考～"))
                threading.Thread(
                    target=lambda: self.cmd_startup_diagnosis(), daemon=True).start()
            elif _dec == "cache":
                # 无新数据：沿用上次报告，不再调 LLM（本会话只提示一次，避免刷屏）
                if not getattr(self, "_hist_report_cache_shown", False):
                    self._hist_report_cache_shown = True
                    _cached = self._load_cached_diagnosis()
                    if _cached:
                        self.root.after(0, lambda: self.set_bubble(
                            "📋 数据没更新，沿用上次的投递报告：\n\n" + _cached))
        except Exception:
            pass

    def _llm_live_report(self, rec: dict):
        """修改5：投递中途用户问情况 → LLM 生成中途情况报告（提示词 v1，用户后改）。"""
        try:
            # 2026-09-18 修复：下面拼 prompt 要用到 _j.dumps，
            # 而 _j 在本方法里从未 import → NameError，被 except 吞成一句人话错误。
            import json as _j
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                self.root.after(0, lambda: self.set_bubble(
                    "当前进度：扫词 %d · 岗位 %d · 打招呼 %d · LLM评 %d" % (
                        rec.get("kw", 0), rec.get("scan", 0), rec.get("greet", 0), rec.get("llm", 0))))
                return
            self.session["llm_calls"] += 1
            plan = self._plan or {}
            prompt = (
                "你是找工作喵的求职 Agent「爬爬」，正在帮用户自动投递 BOSS。用户中途想了解情况。\n"
                "进度数据：%s\n"
                "关键词池前 8 个：%s；岗位匹配值：%s；已屏蔽兼职/日结/诈骗类词。\n"
                "请生成一份口语化的「中途情况简报」：①一句话说进度（打了多少招呼、距离 50 目标还差多少）；"
                "②当前在哪个方向/关键词；③有没有卡点（连续空转/HR 回复情况）；④下一步打算（继续跑/换词/该停了）。"
                "控制在 200 字内，像猫聊天，不要罗列表格。"
            ) % (_j.dumps(rec, ensure_ascii=False),
                 "、".join((plan.get("keywords") or [])[:8]), plan.get("min_score", 75))
            # 2026-09-24 MAXTOK：同上，抬到 2000
            rep = (llm.chat_text("你是找工作喵的求职 Agent「爬爬」。", prompt, max_tokens=2000, temperature=0.5) or "").strip()
            self.root.after(0, lambda r=rep: self.set_bubble("📊 中途情况：\n" + (r or "暂无数据")[:500]))
            self.add_log("投递中：LLM 生成中途情况报告")
        except Exception as exc:
            self.root.after(0, lambda e=exc: self.set_bubble("生成情况报告失败：%s" % e))

    # ================= 「懂人性」改造：说话通道（层1/2/3，2026-09-18） =================
    # 设计主轴：把「判断」和「说话」拆开。
    #   · 判断通道（_llm_judge_during_run / _llm_agent_handle 的第一次调用）
    #     —— system prompt、temperature、输出格式**一字不改** → 动作判定结果与改造前
    #        完全一致，主流程零影响。
    #   · 说话通道（本区块的 _reply_as_pet）
    #     —— 只在「判断通道已得出『不执行任何动作』」之后被调用，决定气泡里写什么字。
    #        它不修改任何决策状态，因此 prompt / 温度 / 长度可以放心调优。
    # 若 LLM 未配置、调用异常或返回空 → 回退到改造前的原文案，保证不退化。

    # 对话记忆上限：20 条 = 最近 10 轮（user + assistant 各算 1 条）
    CHAT_MEMORY_MAX = 20

    def _chat_memory_file(self):
        """对话记忆落盘路径（RUN_DIR 见本文件 L26-28）。"""
        return RUN_DIR / "chat-memory.json"

    def _chat_memory_load(self):
        """启动时读回对话记忆。文件不存在/损坏 → 静默跳过，绝不影响启动。"""
        import json          # ⚠️ main.py 顶层**没有** import json（各函数内按需导入，
        #                        如 L4597 `import json as _j`），新增方法必须遵守同一约定。
        try:
            p = self._chat_memory_file()
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._chat_memory = [
                    x for x in data
                    if isinstance(x, dict)
                    and x.get("role") in ("user", "assistant")
                    and isinstance(x.get("content"), str)
                ][-self.CHAT_MEMORY_MAX:]
        except Exception as exc:
            self.add_log("对话记忆读取失败（已忽略）：%s" % str(exc)[:80])

    def _chat_memory_tail(self, n: int = 6):
        """取最近 n 条供 LLM 上下文（n<=0 → 返回空列表）。"""
        return list(self._chat_memory[-n:]) if n and n > 0 else []

    def _chat_memory_append(self, user_text: str, assistant_text: str):
        """追加一轮对话并裁剪、落盘。任何异常都吞掉 —— 记忆是锦上添花，不能影响主流程。"""
        import json
        try:
            self._chat_memory.append({"role": "user", "content": user_text[:500]})
            self._chat_memory.append({"role": "assistant", "content": assistant_text[:500]})
            if len(self._chat_memory) > self.CHAT_MEMORY_MAX:
                self._chat_memory = self._chat_memory[-self.CHAT_MEMORY_MAX:]
            self._chat_memory_file().write_text(
                json.dumps(self._chat_memory, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception as exc:
            self.add_log("对话记忆写入失败（已忽略）：%s" % str(exc)[:80])

    def _pet_context_brief(self) -> str:
        """给「爬爬」的状态摘要（改造层2）—— **只喂给说话通道，不参与任何决策**。

        改造前 _llm_agent_handle 的 sys_prompt 完全没有状态信息，模型不知道
        「现在是不是在投递」「有没有方案」「主人给没给简历」，只能凭一句话猜，
        所以回复必然空泛。这里把 __init__ 已有的状态字段摊开给它看。

        字段来源（均已核实存在于 __init__，本文件 L198-L280）：
        self.state / self._paused / self._plan / self._plan_state /
        self._resume_choice_waiting / self._night_confirmation_pending /
        self.session / self._live_rec / self._st / self._offline / self._llm_agent
        """
        plan = self._plan or {}
        kws = plan.get("keywords") or []
        rec = getattr(self, "_live_rec", None) or {}
        st = self._st or {}
        sess = self.session or {}
        bits = []

        bits.append("现在是 %s%s" % (
            time.strftime("%H:%M"),
            "（夜间，主人可能想休息了）" if shared.is_night_window() else ""))
        bits.append("你的状态：%s%s" % (
            self.state, "，任务处于暂停" if self._paused else ""))

        if self._night_confirmation_pending:
            bits.append("你正在等主人确认夜间运行风险（只有他说 OK 才能继续）")
        if self._plan_state == "review":
            bits.append("你刚把投放方案给主人看，正在等他确认或提修改意见")
        if self._resume_choice_waiting:
            bits.append("你在等主人选要发给 HR 的附件简历（必须他选，你不能代选）")

        if kws:
            bits.append("投放方案已就绪：关键词 %d 个（%s），岗位匹配值 %s 分" % (
                len(kws), "、".join(kws[:5]),
                plan.get("min_score") or self.cfg.get("min_score", 70)))
        else:
            bits.append("还没有投放方案（要先有主人的简历）")

        # 2026-09-18 第 44 轮修复：self.session 是运行时字典，重启后
        # resume_analyzed 必为 False，会误报「主人还没给」——而磁盘上
        # run/resume.md 一直存在、启动时也已载入评分引擎。故回落到磁盘判断。
        _resume_md = RUN_DIR / "resume.md"
        if sess.get("resume_analyzed"):
            bits.append("简历：已分析过（%s）" % sess.get("resume_file", ""))
        elif _resume_md.exists() and _resume_md.stat().st_size > 0:
            bits.append("简历：已有（沿用上次解析的内容，主人这次没给新的）")
        else:
            bits.append("简历：主人还没给")

        if rec:
            bits.append("本轮投递进度：扫词 %s · 看岗 %s · 打招呼 %s" % (
                rec.get("kw", 0), rec.get("scan", 0), rec.get("greet", 0)))
        elif st.get("greet_streak"):
            bits.append("本轮已连续打招呼 %d 次" % st.get("greet_streak"))

        bits.append("模式：%s；LLM 主控接管：%s" % (
            "离线重放（不碰 BOSS）" if self._offline else "在线（真连 BOSS）",
            "已开启" if self._llm_agent else "关闭"))
        return "\n".join("- " + b for b in bits)

    def _reply_as_pet(self, text: str, llm=None, *,
                      max_tokens: int = 400, temperature: float = 0.8) -> str:
        """用「爬爬」人格生成一句自然回复（说话通道）。

        返回生成的文本；LLM 未配置 / 调用异常 / 返回空 → 返回 ""，
        由调用方回退到改造前的原文案（保证不退化）。

        ⚠️ 本方法**不参与任何决策**：调用方必须已判定「不执行动作」才可调用它。
        """
        try:
            if llm is None:
                llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                return ""
            self.session["llm_calls"] += 1
            hist = self._chat_memory_tail(6)
            out = (llm.chat_text(
                "主人刚对你说了一句话，用你的性格回他：1~3 句，不超过 120 字。"
                "别复述他的话，别解释你在做什么判断，别用客服腔。\n"
                "你此刻的情况：\n" + self._pet_context_brief(),
                text,
                max_tokens=max_tokens,
                temperature=temperature,
                history=hist,
                persona=True,
            ) or "").strip()
            if not out:
                return ""
            self._chat_memory_append(text, out)
            return out
        except Exception as exc:
            self.add_log("人格回复失败（已回退原文案）：%s" % str(exc)[:120])
            return ""

    # ==============================================================================

    def _looks_like_keyword_edit(self, text: str) -> bool:
        """判断用户是否在改「投放方案的关键词」（而非在传/选简历文件）。
        用于 _exec_agent_action 的 resume 分支拦截 LLM 误判：
        「去掉/增加某关键词」被误判成 resume 会触发 cmd_resume 弹文件选择框。"""
        t = (text or "").strip()
        if not t:
            return False
        edit_verb = any(v in t for v in ("去掉", "删除", "移除", "删掉", "增加", "加上",
                                          "添加", "换", "改", "调", "屏蔽", "取消"))
        if not edit_verb:
            return False
        # 明确在说简历/附件文件 → 这是 resume 动作，不是改方案
        if any(r in t for r in ("简历", "附件", "文件")):
            return False
        # 命中方案字段词 → 是改方案
        if any(f in t for f in ("关键词", "方案", "薪资", "岗位", "职位", "方向",
                                 "排除", "屏蔽", "匹配值", "阈值", "城市")):
            return True
        # 或：动词后跟的词命中当前方案里的某个关键词
        kws = [str(k) for k in ((getattr(self, "_plan", None) or {}).get("keywords") or []) if k]
        for kw in kws:
            if kw and kw in t:
                return True
        return False

    def _llm_agent_handle(self, text: str):
        """LLM Agent 兜底：解析意图 → 执行对应动作，或直接聊天回复。"""
        import json
        import re as _re
        try:
            llm = shared.build_llm_client(self.cfg)
            if not getattr(llm, "is_configured", lambda: False)():
                self.root.after(0, lambda: (self.set_bubble(
                    "LLM 未配置：需要分析岗位用的那个 LLM（aiaaa.cc）的 key。\n配置好后我就能听懂任意指令、像 Agent 一样干活。"),
                    self.set_state("闲置")))
                return
            self.session["llm_calls"] += 1
            sys_prompt = (
                "你是「找工作喵」，一个求职 Agent 桌面宠物（名字：爬爬）。用户的话可能是闲聊，也可能是操作指令。\n"
                "可执行动作：\n"
                "- analyze：分析岗位（内置岗位快速演示评分）\n"
                "- scan：扫描分析（打开 BOSS 读真实岗位并分析，不发送任何消息）\n"
                # 2026-09-23 STARTBTN：投递只能点按钮，聊天不得启动 → 不把 test 交给 LLM
                "- （投递只能由用户点「开始投递」按钮启动；聊天里不要输出投递动作，只做问答）\n"
                "- browser：唤起浏览器打开 BOSS 岗位页\n"
                "- resume：简历分析/匹配\n"
                "- plan_change：修改/调整投放方案（关键词/薪资/岗位匹配值/方向/排除词等），例如「去掉XX关键词」「薪资改到15K」「增加后端关键词」。改方案请走这个动作，不要走 resume。\n"
                # 2026-09-24 TALKPLAN：「打招呼话术 / 开场白 / 打招呼语 / 文案」= 帮用户写几句
                # 参考话术，属**闲聊问答**；投放方案里没有这些字段，不要输出 plan_change。
                "- （打招呼话术 / 开场白 / 打招呼语 / 文案 = 帮用户写几句参考，属闲聊问答；方案里没有这些字段，不要输出 plan_change）\n"
                "- report：会话简报/日报\n"
                "- config：查看求职配置\n"
                "- chat：模拟 HR 消息/面试提醒\n"
                "- pause：暂停当前任务；unpause（或 continue）：继续/恢复被暂停的任务\n"
                "如果用户明显要执行某个动作，只输出 JSON：{\"action\": \"动作名\", \"reply\": \"一句话说明你准备干什么\"}\n"
                "否则（闲聊、提问）只输出一句自然的中文回复，不要 JSON，不要多余符号。"
                # 2026-09-19 G2：原 max_tokens=300 对**推理模型**太小 ——
                # 预算全烧在 reasoning 上 → content 恒为空（日志实测）。
                # 这里加大预算并明确禁止推理过程。
                "\n\n【重要】直接输出最终结果，不要推理过程、不要思考步骤。"
            )
            # 2026-09-24 MAXTOK：900 会被推理预算吃光 → content 空（实测）→ 抬到 2000
            raw = (llm.chat_text(sys_prompt, text, max_tokens=2000, temperature=0.3) or "").strip()
            if not raw:
                self.root.after(0, lambda: (self.set_bubble(
                    # 2026-09-19 G3：原文案甩锅「密钥 / 网络」是**误导** ——
                    # 实测根因是推理模型把预算烧在 reasoning 上导致 content 为空，
                    # 与密钥、网络都无关（用户会白折腾配置）。
                    "😿 我刚才没想明白（模型返回了空内容，通常是推理占用了全部输出额度）。\n"
                    "麻烦**再说一次**；如果连续这样，可以把话再说具体一点，比如「帮我把方案改成找实习」。"),
                    self.set_state("闲置")))
                self.add_log("LLM Agent 返回空内容（多为推理模型输出被 reasoning 占满，非密钥或网络问题）")
                return
            m = _re.search(r"\{.*\}", raw, _re.S)
            action, reply = None, raw
            if m:
                try:
                    obj = json.loads(m.group(0))
                    action = obj.get("action")
                    reply = obj.get("reply") or raw
                except Exception:
                    action, reply = None, raw
            # 2026-09-24 TALKPLAN（防误判）：话术 / 开场白 / 打招呼语 属聊天问答
            #（投放方案里没有这些字段）。LLM 若判成 plan_change → 清空动作，
            # 落到下面的「闲聊 / 提问」回复，避免「去改方案 → 又说没这字段」的空转。
            if action in ("plan_change", "plan", "adjust_plan", "change_plan") and any(
                    q in text for q in ("话术", "开场白", "打招呼语", "打招呼的话", "文案")):
                action = None
            if action:
                self.root.after(0, lambda r=reply: (self.set_bubble("爬爬：%s" % r), self.set_state("闲置")))
                self.add_log("LLM 判定动作：%s" % action)
                self._exec_agent_action(action, text)
            else:
                # 说话通道（改造层1）：动作判定已完成且为空，此时才生成展示文本。
                # 原实现直接贴出 LLM 那句「自然回复」—— 受工具腔 system prompt、
                # max_tokens=300 与 reply[:300] 三重收紧，必然短促模板化。
                # 注意：pet_reply 的生成发生在 action 解析**之后**，且它不修改任何
                # 决策状态 → 动作判定结果与改造前完全一致。
                pet_reply = self._reply_as_pet(text, llm)
                shown = (pet_reply or reply)[:400]
                self.root.after(0, lambda r=shown: (
                    self.set_bubble("爬爬：%s" % r), self.set_state("闲置")))
        except Exception as exc:
            self.root.after(0, lambda e=exc: (self.set_bubble(
                "😿 LLM 调用失败：%s\n请检查 API 配置或网络。" % str(e)[:200]),
                self.set_state("错误")))
            self.add_log("LLM Agent 异常：%s" % str(exc)[:200])

    def _exec_agent_action(self, action: str, text: str):
        if action in ("analyze", "analysis"):
            self.cmd_analyze()
        elif action in ("scan",):
            self.cmd_scan_jobs(chain_report=True)
        elif action in ("test",):
            # 2026-09-23 STARTBTN：聊天不再启动投递 → 提示点按钮
            self.set_bubble("▶ 投递请点对话框的「开始投递」按钮（聊天不能启动投递）。")
        elif action in ("browser", "open"):
            self.cmd_browser()
        elif action in ("plan_change", "plan", "adjust_plan", "change_plan"):
            # 2026-09-20：用户要改方案/关键词 → 走方案修订，不再误判成 resume
            self._revise_plan(text)
        elif action in ("resume", "cv", "resume_analyze"):
            # 2026-09-17 修复：LLM 系统提示里 resume 同时表示「简历分析」与
            # 「继续当前任务」，导致后面的 elif action in ("resume","continue")
            # 永远不可达（被本分支先截获）；且暂停后说「继续」会误触发简历分析。
            # 改为按上下文区分：暂停中 → 恢复任务；否则 → 简历分析。
            if self._paused:
                self._paused = False
                self.set_bubble("已继续。")
            else:
                # 2026-09-23 修复：LLM 把「去掉/增加某关键词」误判成 resume 会触发
                # cmd_resume → filedialog 弹文件选择框。若本意是改方案关键词，改走 _revise_plan。
                if self._looks_like_keyword_edit(text):
                    self._revise_plan(text)
                else:
                    self.cmd_resume()
        elif action in ("report", "summary"):
            self.cmd_report()
        elif action in ("config",):
            self.cmd_config()
        elif action in ("chat", "message"):
            self.cmd_chat()
        elif action in ("pause",):
            self._paused = True
            self.set_bubble("已暂停当前任务，说「继续」恢复。")
        elif action in ("unpause", "continue", "resume_task"):
            self._paused = False
            self.set_bubble("已继续。")


def main():
    try:
        # 2026-09-17 修复：启动时补做一次缓存清理。
        # 原实现只在「投递正常结束」时清理；手动停止 / 中途异常 / 崩溃都会
        # 整段跳过，且启动时不补做，导致缓存长期无人回收。
        try:
            cleanup_browser_cache()
        except Exception:
            pass
        root = tk.Tk()
        PetApp(root)
        root.mainloop()
    except Exception:
        _append_bounded(LOG_FILE, traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
