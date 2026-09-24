<p align="center">
  <img src="assets/cat.png" width="240" alt="JobHunter Cat mascot">
</p>

# 🐱 JobHunter Cat

> **A desktop AI agent that searches, evaluates and applies for jobs — then learns from the results.**
>
> **Not just auto-apply. A personal job-search agent that remembers what worked.**

<p align="center">
  🇬🇧 <b>English</b> (current) · 🇨🇳 <a href="README.md"><b>中文</b></a>
</p>

<div align="center">
  <img src="assets/demo.gif" width="700" alt="JobHunter Cat demo">
  <br>
  <sub>▶ Full demo video (25s): <a href="assets/demo.mp4">demo.mp4</a></sub>
</div>

<br>

**Resume → Strategy → Search → AI Match → Apply → HR Monitoring → Result Analysis → Next-Round Optimisation**

> ⚠️ **Platform scope**: JobHunter Cat currently automates **BOSS Zhipin** only — a Chinese job
> platform. If you are not job hunting in China, this project will not be usable for you yet;
> support for other platforms is on the roadmap. The underlying ideas (AI job agent, personal job
> memory, result-driven strategy) are not platform-specific.

> 📐 **Note on diagrams**: the illustrations below are rendered from the original Chinese assets,
> so labels inside the images are in Chinese. Captions and surrounding text are in English.

---

## ⚠️ Read This First: It Sends Real Messages to Recruiters

This is not a simulation. **Greetings, resume sends and replies are real actions — once sent, they cannot be taken back.**

The agent **only replies on its own in two situations**: when a recruiter asks for your resume (it sends it), and when a recruiter declines (it sends a thank-you). **Anything that needs your judgment — interview scheduling, salary negotiation — is only surfaced to you, never answered for you.** See **HR Message Monitoring** below.

Please make sure to:

1. **Confirm your resume, keywords, salary range and city are what you actually want before applying**
   > ⚠️ There is **no dry-run mode and no read-only trial**. Clicking "Start Applying" performs a
   > real application. There is no "just try it" option.
2. Use your own account and accept the platform's rules and risks yourself.

**On account bans**: as of 2026-09-24, five consecutive days of heavy use (5+ hours a day) produced **no bans**. Rate limiting is built in — a random share of qualifying jobs is skipped (about 26% of all skips are of this kind) — but **this is not a guarantee of any kind**. Platform rules change; evaluate and accept the risk yourself.

The project **never handles your password** — it attaches to a browser you have **already logged into yourself**.

---

## 🤔 Why It Exists

Most AI job-search tools solve this:

> Help you find jobs, then help you apply.

JobHunter Cat tries to solve a different one:

> **What happens after you apply?**

Many auto-apply tools report how many applications you sent. Far fewer feed those outcomes back into your next round of decisions.

Here is one real run — **2026-09-18 to 09-24, seven consecutive days**. All figures come from the program's own action ledger:

<p align="center">
  <img src="assets/flow-7day-funnel.svg" width="820"
       alt="7-day funnel: 3,135 job scan actions → 141 greetings → 14 resumes sent → 13 recruiters responded (10 replies / 3 rejections)">
</p>

### 7-day real-world run

| Metric | Count |
|---|---|
| Job scan actions processed | **3,135** |
| Greetings sent (real clicks on "Contact now") | **141** |
| Resumes sent (after recruiters asked) | **14** |
| Recruiters who responded | **13** |
| — of which replies / rejections | 10 replies / 3 rejections (~9.2% response rate) |

> **On counting**: 3,135 is a count of **actions**, not of distinct jobs. The same job is scanned
> repeatedly under different keywords and across rounds, so the count exceeds the number of unique
> jobs — de-duplicated by "job title + company", the skipped set covers about 985 jobs. The 141
> greetings / 14 resumes / 13 responses are likewise **action counts, not job counts**.

Of those 3,135 actions, **2,980 were deliberate skips (95.1%)**:

| Skip reason | Count | Share |
|---|---|---|
| Match score too low | 1,475 | 49.5% |
| Rate-limit random skip | 776 | 26.0% |
| Salary out of range | 391 | 13.1% |
| Matched an exclusion word (JD / job title) | 338 | 11.3% |

**95% of scans get filtered out.** The filters clearly keep volume under control — but whether they actually raise the *effective* application rate (rather than killing good jobs along with the bad) needs more real data. That is one of the hypotheses this project is validating in public.

None of those skips are wasted. They accumulate into **keyword effectiveness** (below: the keyword dimension of Job Memory, de-duplicated by keyword — a different counting basis from the action counts above):

| Keyword | Scanned | Applied |
|---|---|---|
| User Operations | 52 | **20** |
| Operations Manager | 70 | 18 |
| Overseas Operations | 64 | 16 |
| Content Operations | 27 | 16 |
| Overseas Social Media Operations | 43 | **0** |

Over the same pool of jobs, `User Operations` produced 20 applications while `Overseas Social Media Operations` scanned 43 and applied to none. Next round, that keyword should probably be replaced. This is what "remembering what works" actually looks like.

In round two, the agent can surface:

- Which keywords produce jobs with a **higher reply rate**
- Which jobs score well yet **get little real feedback**
- Which directions have **seen no meaningful replies for several rounds**

So the next round is not a repeat of the same search — it **treats past results as new decision input**.

---

## 🧠 Personal Job Memory

> **The desktop cat is the entry point, but Job Memory is the core capability being explored.**

It keeps recording your search: resume and career history, target direction, city and salary preferences, job search records, match results, applications, recruiter replies, interview invitations, rejections — and **how each keyword has historically performed**.

<p align="center">
  <img src="assets/flow-job-memory.svg" width="860"
       alt="Job Memory loop: resume → career profile → strategy → search → AI match → apply → HR / interview results → Personal Job Memory → next-round strategy">
</p>

> **The goal is not simply to remember what happened,
> but to use what happened to inform the next decision.**

---

## 🔬 What We Are Researching

> If an AI remembers a person's real job-search outcomes,
> can it gradually make better decisions than fixed rules would?

This is an **open, ongoing experiment**. We do not assume that "remembering past results" necessarily improves outcomes — we want to verify it with real usage data.

Currently exploring:

- The relationship between search direction and recruiter reply rate
- The relationship between match scores and **real** recruiter feedback
- How effectiveness differs across keywords
- Which job attributes are more likely to produce interviews
- When to widen the search, and when to change direction
- **How to avoid changing strategy too early on insufficient samples**

> We prefer to document what actually works
> rather than present planned features as completed features.

---

## ✅ What Works Today

Everything below is **already implemented**.

### Resume Understanding
- Parses PDF / DOCX / TXT / Markdown resumes (Word tables included; images go through local OCR)
- LLM-based extraction of target direction, city and salary preferences
- **Validates before writing**: if the result does not look like a resume, it aborts rather than pollute your config

### Job Matching
- Reads the full job description
- Rule-based score plus an LLM semantic adjustment
- Outputs match score, matching evidence, and missing skills
- **14-day de-duplication**: already-evaluated jobs reuse their cached score instead of spending LLM tokens again

### Application Execution
- Browser automation (DrissionPage over Chrome DevTools Protocol)
- Automatic greetings and an application ledger
- **Verifies login state before applying**; if not logged in, it stops and waits for your QR scan
- **Prompts you to select an online attachment resume**; it will not start until you choose one
- Rate control: **a random share of qualifying jobs is skipped** to reduce risk-control exposure; failures roll back state
- ⚠️ **No dry-run mode**: the `real` flag is always `True`, so "Start Applying" sends for real

### 🔬 HR Message Monitoring

A monitoring pass runs automatically after each keyword sweep. **Only two signals actually send anything; everything else is handed to you:**

| Recruiter sends | What the cat does |
|---|---|
| **Asks for resume** | ✅ Agrees automatically → picks the attachment resume you selected → sends it |
| **Declines** | ✅ Sends a thank-you automatically (wording you configure, once per conversation) |
| **Interview invitation** | ⚠️ **Does not reply** — notifies you to take over |
| **General question / small talk** | ⚠️ **Does not reply** — only reminds you to look |
| **Platform auto-reply template** | ⏭️ Does not reply (the other side did not actually say anything) |

> **Anything it is not confident about, it will not answer on its own.** Interview times, salary
> negotiation and follow-up questions are only surfaced to you — **it will not agree to anything for
> you, and it will not invent content to send back to a recruiter.**

De-duplication: one resume per conversation, one thank-you per conversation.

> Detection runs in a fixed order — **interview invitation → rejection → resume request →
> platform template → general conversation (fall-through)**. Only the first two produce an outgoing message.

### Human-like Pacing

**You do not need to tune any delay parameters** — pauses at each key step are generated by the program.

A fixed interval is too obviously regular, so pauses are **not drawn from a uniform random** but from a skewed distribution: most intervals are short, with an occasional long pause — closer to how a real person reads and pages through listings.

| Step | Pause |
|---|---|
| Reading a job detail page (read the JD, then decide) | 1.2–3.0 s, biased short |
| Before paging to the next job | Mainly 2.5–6 s, ~**6%** chance of a 6–10 s long pause |
| On hitting an unsuitable job | 0.5–1.0 s, a brief hesitation |
| Each click or read during chat monitoring | 0.8–4.0 s, split into several bands by action type |

**30+** pause points in total, covering both the application pipeline and chat monitoring. All parameters are **built into the program** — there is no delay setting in the config file.

### Job Memory
- Application outcomes and recruiter reply history
- Search and application statistics
- Automatic end-of-round summary with keyword-effectiveness suggestions
- Past results feed back into the next round's plan

### Desktop Agent
- Always-on desktop pet (Electron transparent window)
- Command it in plain language: "widen the salary range to 15–25K", "drop the Douyin Operations keyword"
- Dashboard: progress bars, application details, analysis reports
- Key actions are written to a ledger, so everything is observable

---

## ⚠️ Current Limitations

An honest statement of the current boundaries:

| Limitation | Detail |
|---|---|
| BOSS Zhipin only | Adapters for other platforms are not implemented |
| One city per run | Multiple cities require multiple runs |
| You must keep the browser logged in | When the session expires, you re-scan the QR code manually |
| No CAPTCHA solving | It stops and waits for you when a CAPTCHA appears |
| 63 cities in the code table | Not all prefecture-level cities covered; an unknown city **raises an explicit error** rather than silently switching |
| Image resumes need an extra dependency | Without `rapidocr-onnxruntime`, image resumes do not work; PDF/DOCX are unaffected |
| Match scores are not statistically calibrated | The score is heuristic and does not equal real success probability |
| Strategy optimisation is still experimental | 7 days of real data (1,346 evaluation records / 141 greetings / 13 responses), but **the sample is too small for statistical conclusions** |
| Automation needs ongoing maintenance | Changes to page structure break selectors |

> **On the numbers**: figures in this document come from **two different counting bases**. The
> **3,135** above is an **action count** from the action ledger (skips + greetings + resumes); the
> **1,346** here is a count of **evaluation records** in Job Memory (the same job is recorded once
> per keyword and per round; de-duplicated by "job title + company", 524 jobs). They **cannot be
> divided by each other or compared directly**.

---

## 🏗 Architecture

> **The Agent is the core, the desktop cat is the interface, Job Memory is the long-term state, and Browser Automation is the execution layer.**

<p align="center">
  <img src="assets/architecture.svg" width="640"
       alt="Architecture layers: Desktop Pet (Electron) ↔ Agent Core (Python, with LLM Layer and Job Memory) → Strategy Loop → boss/ platform layer (DrissionPage over CDP 9222)">
</p>

Layering and the event protocol are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) *(in Chinese)*.

---

## 🗺 Roadmap

No timelines — only the directions being explored.

**Now**
- Stability of the BOSS workflow
- Personal Job Memory
- Result-driven strategy experiments
- Test coverage

**Next**
- Calibrate match scores against real outcomes
- Career profile extraction
- Better strategy recommendations
- More robust browser recovery

**Exploring**
- More job platforms
- English UI (the English README is already available)
- Community skills
- An agent evaluation framework

---

## 🚀 Quick Start

### Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10/11 |
| Python | 3.8+ (**tkinter required**) |
| Node.js | 20+ |
| Browser | Chrome — launch it yourself and **log in to BOSS Zhipin manually** |
| LLM | Any OpenAI-compatible endpoint |

### Install

```bash
git clone https://github.com/hlan98/JobHunterCat.git jobhuntercat
cd jobhuntercat

pip install -r requirements.txt      # Python dependencies
cd desktop && npm install && cd ..   # desktop shell dependencies
```

### Configure

```bash
mkdir run
cp memory/templates/config.example.json run/config.json
```

Edit `run/config.json` and fill in at least three fields:

- `llm` — API endpoint, model name, API key
- `target_city` — target city (63 supported; see `CITY_CODES` in `agent/shared.py`)
- `resume_send_name` — filename of an attachment resume you have **already uploaded** to BOSS

### Launch

```bash
# double-click
scripts\启动找工作喵.bat

# or from the command line
cd desktop && npm start
```

Before the first launch, **open Chrome yourself and log in to BOSS Zhipin** (the program attaches to debug port 9222).

### First Run: The Cat Stops You for Two Things

Not optional — **it will not start applying until both are done**:

1. **Verify login state** — if you are not logged in, it opens the login page and waits for your QR scan; it re-checks if the session drops mid-run
2. **Select an online attachment resume** — the cat does not upload a local PDF; it asks you to pick one of the attachment resumes already on BOSS. Clicking "Start Applying" before selecting one stops immediately

---

## 🧪 Tests

```bash
python -m unittest discover -s tests -t .
```

Current status: **49 tests, all passing**.

> When changing DOM-reading logic, also run a **fake-DOM two-version comparison** (it must fail
> before the fix and pass after). Otherwise you cannot confirm the fix actually works.

---

## 🤝 Contributing

You do not need to know everything. These are the areas we need most right now:

| Area | What you can improve |
|---|---|
| 🧠 **Agent / LLM** | Job matching, strategy planning, memory and evaluation |
| 🌐 **Browser Automation** | Platform adapters, stability, de-duplication, error recovery |
| 🖥 **Desktop** | Pet interaction, UI, animation, notifications |
| 📊 **Data / Research** | Outcome analysis, score calibration, strategy optimisation |
| 🌍 **Localization** | English UI and docs, other platforms, other countries and hiring processes |
| 🧪 **Testing** | Tests across different resumes, industries and strategies |

Good entry points for newcomers: add resume format support, improve job-title normalisation, add new cat animations, improve error messages, extend test coverage.

---

## 📚 Documentation

The detailed docs are currently **in Chinese**:

| Document | What it covers |
|---|---|
| [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) | What runs today, module responsibilities, work in progress |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layering, event chains, data flow |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Key design decisions and trade-offs (12 ADRs) |
| [`docs/CODE_PROVENANCE.md`](docs/CODE_PROVENANCE.md) | Code provenance per file and scope of changes |
| [`docs/PRIVACY.md`](docs/PRIVACY.md) | What it reads, what it writes, **what must never be committed** |
| [`AGENTS.md`](AGENTS.md) | Repository conventions for AI coding assistants |

---

## 📜 License

**Different files in this repository are under different licences.** This is **not** a dual-licence "MIT or PolyForm, your choice" arrangement — the split is by **file boundary**, and users have no choice in the matter. Three categories:

| Category | Paths | Licence |
|---|---|---|
| **① Original** | `agent/main.py`, `agent/pet_bridge.py`, `desktop/`, `memory/`, `assets/`, `scripts/`, `docs/` | **PolyForm Noncommercial 1.0.0** |
| **② From the upstream project** | `examples/` | MIT |
| **③ Mixed files** | `boss/`, `agent/shared.py`, `agent/ledger.py`, `agent/doctor.py`, `agent/skill_entry.py`, `tests/` | see below |

### ③ Mixed Files

These are **mixed files** that continued to be modified on top of the original MIT code — a single file contains both the original MIT code and code added later.

To preserve the rights attached to the original MIT code, **this project currently takes a conservative approach: these files are distributed in their entirety under the MIT licence, with no additional commercial restrictions.**

> This is a **project-level licensing decision**; it does not mean every line in these files can be
> traced back to the upstream MIT original.

Provenance and the scope of modifications were baseline-compared separately — see [`docs/CODE_PROVENANCE.md`](docs/CODE_PROVENANCE.md).

### Original Parts (PolyForm Noncommercial 1.0.0)

- ✅ **Personal use, study, research, self-use** — free
- ✅ **Non-profit organisations** (schools, charities, public research, government) — free
- ❌ **Commercial use** (including internal corporate use, SaaS, resale, integration into commercial products) — **requires authorisation**

For commercial licensing, contact: **Leo He**

- Email: hlan98@hotmail.com
- QQ: `104495956`
- GitHub: [@hlan98](https://github.com/hlan98)

> ⚠️ Because the MIT portions cannot have restrictions added, **this repository as a whole cannot be
> treated as "no commercial use"** — the restriction applies only to the original parts marked above.

The licence boundary statement is in [`NOTICE`](NOTICE); the full MIT text is in [`LICENSES/MIT-job-hunter-skill.txt`](LICENSES/MIT-job-hunter-skill.txt).

> **Language**: an English version of the README is available, but the authoritative repository
> documentation is in Chinese. Where the two differ, **the Chinese version governs**.

> ⚠️ The above is a **statement of fact**, not legal advice. Licensing of mixed files involves
> specific legal questions such as derivative-work determination and contributor rights — consult a
> professional if needed.

---

## 🙏 Acknowledgements

- Originated from an MIT-licensed `job-hunter-skill` project; see [`docs/CODE_PROVENANCE.md`](docs/CODE_PROVENANCE.md) for provenance and evolution
- The desktop shell is built on [Electron](https://www.electronjs.org/)
- Browser automation is built on [DrissionPage](https://github.com/g1879/DrissionPage)

---

## Disclaimer

This project is intended for **personal job searching** only. Users accept responsibility for:

- Account risks on the platform caused by automated actions
- The consequences of any message sent to a recruiter
- Compliance with the laws and regulations of your jurisdiction

The author accepts no responsibility for any consequences arising from the use of this tool.
