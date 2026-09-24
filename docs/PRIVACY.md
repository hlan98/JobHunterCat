# PRIVACY — 数据读写与提交红线

> 本文件回答三个问题：**它会读什么**、**它会写什么**、**哪些绝不能提交**。

---

## 一、它会读什么

| 对象 | 说明 |
|---|---|
| **你的简历文件** | PDF / Word / 图片（可选 OCR）。用于生成投放方案与评分 |
| **BOSS 直聘页面** | 岗位列表、JD、薪资、HR 消息。**通过你已登录的浏览器读取** |
| **浏览器登录态** | 接管 9222 端口的 Chrome profile（`.job_hunter/`） |
| **你的对话输入** | 发给 LLM 判断意图（可用本地/自建端点，取决于你的配置） |

**它不读**：
- ❌ 你的账号密码（不接管登录，见 [`DECISIONS.md`](DECISIONS.md) ADR-2）
- ❌ 浏览器里除 BOSS 之外的其它页面内容

---

## 二、它会写什么

所有运行时数据写在仓库根的 **`run/`**（已在 `.gitignore` 中）：

| 文件 | 内容 | 敏感级别 |
|---|---|---|
| `.job_hunter/` | 浏览器用户目录 —— **含登录态 Cookie** | 🔴 极高 |
| `resume.md` | **你的简历正文** | 🔴 极高 |
| `config.json` | 配置 —— **含 LLM API Key** | 🔴 极高 |
| `plan.json` | 投放方案（关键词、薪资、城市…） | 🟡 中 |
| `job_memory.json` | 已评估岗位（497 条）+ 关键词统计 | 🟡 中 |
| `ledger/` | 动作账本（打招呼 / 发简历 / 跳过 / 失败） | 🟡 中 |
| `reports/` | 分析报告 | 🟡 中 |
| `chat-state.json` / `chat-memory.json` | 会话状态与记忆 | 🟡 中 |
| `boss-demo-seen.json` / `boss-demo-log.json` | 投递过的岗位记录 | 🟡 中 |
| `job-hunter.log` | 运行日志（含 HR 姓名、公司名、岗位链接） | 🟡 中 |

另有：
| 文件 | 位置 | 敏感级别 |
|---|---|---|
| `demo.log` | `agent/` | 🟡 中（含 HR 姓名、公司名） |
| `bridge-debug.log` / `main-debug.log` | `desktop/` | 🟡 中（含岗位链接、HR 名字） |

---

## 三、⛔ 绝不能提交的文件

**以下一旦提交，等于把账号和个人信息公开：**

| 文件 | 泄露后果 |
|---|---|
| `run/.job_hunter/`（128 MB） | **BOSS 登录态 / Cookie** → 账号被接管 |
| `run/resume.md`、任意 `*.pdf`/`*简历*` | 姓名、电话、工作经历全公开 |
| `run/config.json` | **LLM API Key**（实测 67 字符）→ 额度被白嫖 |

**连带清理**（个人求职记录，同样不该公开）：

- `run/boss-demo-log.json`、`run/boss-demo-seen.json`
- `run/ledger/`、`run/reports/`、`run/job_memory.json`、`run/kw_history.json`
- `run/chat-memory.json`、`run/chat-state.json`、`run/hr_inbound.json`
- 所有 `*.log`

---

## 四、提交前自检

`.gitignore` 已覆盖上述内容，但**推送前请人工再核一遍**：

```bash
# 1. 看 git 会纳入哪些文件（应无 run/、无 *.log、无 node_modules）
git status --short | head -40

# 2. 确认没有隐私文件被纳入
git status --short | grep -Ei "run/|\.log$|resume|config\.json|\.pdf" || echo "✅ 无隐私文件"

# 3. 确认没有密钥被纳入
git grep -In "api_key" -- ':(exclude)docs/*' ':(exclude)memory/templates/*' || echo "✅ 无密钥"
```

**首次推送建议**：先建 **Private** 仓库 → 推送 → 在 GitHub 网页上**再浏览一遍文件树**
→ 确认无误后改为 Public。

---

## 五、如果你已经误提交过

1. **立刻轮换密钥**：LLM API Key、任何出现在仓库里的凭证
2. **退出 BOSS 登录**（让已泄露的 Cookie 失效）
3. **清洗 git 历史**：`git filter-repo`（或 BFG）移除敏感文件，
   然后**强制推送**
4. 注意：GitHub 上已 fork / 已 clone 的副本**无法回收** ——
   所以**第一步永远是别提交**

---

## 六、给使用者的话

本工具在你的**本机**运行，数据默认不出本机，
**除非**你配置了云端 LLM —— 此时简历与岗位文本会发往你配置的那端点。

请自行判断：
- 你的简历文本是否适合发给该 LLM 服务
- 你所在地区对个人信息处理的合规要求
