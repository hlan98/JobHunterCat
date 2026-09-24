# memory/

本目录放**记忆与状态的说明与脱敏模板**，不放真实数据。

## 运行时会生成的文件（不提交）

真实运行数据写在仓库根目录的 `run/`（已 gitignore）：

| 文件 | 内容 |
|---|---|
| `config.json` | LLM 配置、城市、薪资阈值 —— **含 API Key，绝不提交** |
| `plan.json` | 当前投放方案（关键词、匹配值…） |
| `job_memory.json` | Personal Job Memory：已评估岗位 + 关键词统计 |
| `ledger/` | 动作账本（打招呼 / 发简历 / 跳过 / 失败）JSONL |
| `resume.md` | **你的简历正文，绝不提交** |
| `.job_hunter/` | 浏览器用户目录 —— **含登录态 Cookie，绝不提交** |

## templates/

脱敏后的空壳模板，字段结构与真实文件一致，可复制到 `run/` 起步。
