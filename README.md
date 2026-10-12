# JobPilot — Ranjit’s personal job-search assistant

A runnable, local-first MVP: FastAPI + SQLite + a responsive HTML/CSS/JavaScript dashboard. No Node service, hosted database, subscription, or LLM is required. It uses Ranjit’s supplied profile and actual CV project facts. It **never submits an application**.

## Quick start (Mac mini / Linux, Python 3.11+)

```bash
cd jobpilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/run.sh
```

Open **http://127.0.0.1:8000**. The launcher creates `.env` with a random `APP_TOKEN` on first run. Open that local file and paste its token into the dashboard. The browser holds it only in memory. Keep the terminal running; Ctrl+C stops the service. Do not use the example placeholder as your real token.

The supplied private database snapshot contains 75 real feed listings fetched during validation and 2 previously recorded applications (Periwin and Envision). It contains no sample jobs. These are historical snapshots, not a promise that roles remain open. Refresh when source cooldowns permit, and always check the original listing. To start empty, stop the app and move `data/` to a backup location before restarting. For a fresh database, import the known prior applications with:

```bash
python -m app.cli history
```

The project contains two existing CV PDFs. **They say “3+ years,” while your current instruction says approximately two years.** Matching and new letters use two years. Review or replace the CV before approving a packet. Education and employer dates are not invented or rewritten. This archive contains personal information; keep it private.

## Everyday workflow

1. **Discover jobs** reads enabled official feeds. Repeated clicks honor persistent cooldowns and conditional HTTP caching.
2. Import permitted listing details from Upwork, LinkedIn, or another source. Leave unknown fields blank. Importing an eligibility override is a factual assertion: use it only when the source explicitly confirms Nepal eligibility.
3. Inspect score evidence, missing information, salary, source, date, Connects, and warnings. High normalized scores with inadequate evidence do not qualify for automated preparation.
4. Eligible shortlisted jobs receive free drafts automatically (maximum five per discovery run). You can also use **Prepare free draft**. No AI credits are spent.
5. Edit letters and screening answers; download the selected CV. Replace inaccurate PDFs using the selected-CV upload control. A changed CV requires refreshing and reviewing the draft again.
6. Optional **AI polish** sends only the letter and bounded job text to your configured provider after an explicit click. The response appears separately as an **unverified suggestion**. It is never silently substituted into an application.
7. Check the review box, save, and inspect the exact approval packet: employer, title, destination, profile fields, CV hash, letters and screening answers.
8. Approve that specific packet. Approval expires after 24 hours and is invalidated by document, profile, CV or listing changes. Approval itself sends nothing.
9. Complete and submit on the employer’s site yourself. After the platform confirms success, paste the success text or receipt reference to record Applied. The UI and database label this **user-reported confirmation**, not independent platform verification. Interviewing is available after an application receipt.

No purchase, Connect spend, application message, or Telegram notification was performed during development.

## Implemented / boundaries

| Capability | MVP behavior |
|---|---|
| Automatic discovery | Himalayas, Remotive; Greenhouse boards configurable |
| Other boards | Manual structured import, direct source links; no scraper or unauthorized browser login |
| Ranking | Deterministic, configurable, evidence-normalized 0–100 with completeness and criterion-level explanations |
| Deduplication | HTTPS canonical URL without tracking parameters; normalized exact title + company fallback; prior receipts block reapplication |
| Persistence | SQLite WAL, indexed identifiers, JSON listing evidence, approval snapshots, receipts, audit, cache and usage tables |
| Documents | Truthful free text letters/proposals, match summary, project selection, actual CV selection, verified-answer lookup |
| AI | Optional HTTPS OpenAI-compatible provider adapter; conservative daily reservations and cached suggestions |
| Dashboard | Responsive layout, search, status/source filters, priority filter, sorting, pagination, details, editor, CV upload/download, approval UI, statistics and audit |
| Notifications | Optional Telegram alerts; eligibility/completeness gating; at-most-once attempts per job |
| Form assistance | Optional local headed Playwright helper for ordinary labeled text inputs, CV upload and cover-letter textareas on explicitly permitted hosts |
| Final submission | Manual only; no automatic submit/click/email endpoint exists |
| Deployment | Local Mac/Linux; cron examples below. No paid hosting is provisioned |
| PostgreSQL / Next.js | Not implemented in MVP. The simpler single-process stack avoids a second service/build chain. SQLite access is centralized for a later migration |

Unknown screening answers, salaries, start dates, citizenship, visas, proficiency ratings, and sensitive information require your input. The job parser is a heuristic, not an exhaustive legal/eligibility determination. Review role restrictions and employer credibility yourself.

## Source policy and cadence

Checked against official documentation on 12 October 2026. Recheck provider terms before expanding use.

| Source | Mode and cadence | Important limitation |
|---|---|---|
| [Himalayas API](https://himalayas.app/docs/remote-jobs-api) | Free no-key JSON API, Nepal-filtered recent search; three pages/day by default | Daily cache; no instant-job guarantee; country/timezone restrictions preserved; source attribution shown |
| [Remotive API](https://github.com/remotive-com/remote-jobs-api) | Free no-key software-development feed; at most once per six hours | Public postings delayed 24h; source links and attribution retained; do not syndicate to other job boards |
| [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) | Public read-only GET endpoints; once per six hours per configured board | Only board tokens you deliberately configure; update timestamps are not treated as posting dates |
| Upwork, LinkedIn, Wellfound, YC Work at a Startup | Manual import | Official/approved account integrations remain future work, not enabled capabilities |
| Remote OK, We Work Remotely, other company/Nepal boards | Manual import | RSS/API adapters can be added after confirming source-specific permissions; arbitrary website scraping is not implemented |

Source data is for your private application workflow. Do not turn this private dashboard into a public redistribution service without a separate terms review. A listing disappearing from a bounded search is not automatically labeled expired; explicit expiry dates are honored. Full-feed mirroring is intentionally avoided.

Enable Greenhouse by editing `config/rules.json`:

```json
"enabled_sources": ["himalayas", "remotive", "greenhouse"],
"greenhouse_boards": ["your-confirmed-board-token"]
```

No credentials are needed for these three read-only sources. Rate limits/failed runs are visible under Activity. 5xx responses get at most three attempts with short backoff. 429 Retry-After extends cooldown; 401/403 are not bypassed. Conditional ETag/Last-Modified headers are used when the provider supplies them. Failed fetches retain cooldown to avoid retry storms. Cached payloads and unchanged content hashes avoid repeated downstream work.

## Configuration and scoring

Edit `config/profile.json` for verified facts, projects, resume filenames, and exact screening-question answers. Add a resume PDF under `resumes/` and a mapping in the profile; selection maximizes verified skill overlap. The two included CVs were retrieved from your existing documents. Antora, Handsy/GoHandsy, DataBrakes, the mobile project, and the interview-evaluation project have explicit source notes. A named project is not proof of every listed technology.

Edit `config/rules.json`; scoring reads it on each request. Baseline:

- Minimum normalized score 70 and minimum observed weight 55/100.
- Confirmed Nepal eligibility required for auto-preparation; ambiguous remote does not mean worldwide.
- Senior/lead titles with unknown or excessive experience requirements need manual review.
- More than 10 Connects reduces points, but is not a hard rejection unless `hard_connect_limit=true`.
- Unpaid listings rejected by default. Old age is a preference unless `hard_age_limit=true`.
- USD floors: $10/hour, $12,000/year, $50 fixed. These are editable heuristics, not market valuations. Fixed project scope needs review. Other currencies and unparsed text salaries remain unknown rather than being falsely converted.
- Timezone restrictions hold automatic preparation until manually resolved; country eligibility alone does not prove working-hours compatibility.

| Category | Maximum | Evidence |
|---|---:|---|
| Skills and experience | 30 | 24 from detected/declared skill overlap; 6 from explicit minimum years |
| Location/remote eligibility | 20 | Source constraints or user-verified eligibility; explicit Nepal exclusion overrides worldwide |
| Freshness | 15 | Source publication timestamp only; future/missing dates unknown |
| Compensation | 15 | Supported currency/pay-period with numeric floor; unpaid evidence scores zero |
| Credibility | 10 | Observed Upwork payment flag or manually documented company credibility; never inferred from a board name |
| Competition and cost | 10 | 5 for actual Connect cost, 5 for reliable proposal count; unknown stays unknown |

`normalized = earned points / observed maximum weight × 100`.
`completeness = observed maximum weight / 100 × 100`.
Unknown criteria receive neither points nor denominator weight. Known unfavorable evidence receives zero/low points and remains in the denominator. Categories: 85–100 High priority, 70–84 Worth reviewing, 50–69 Low priority, below 50 Skip. Hard rejection overrides the recommendation regardless of score. Automated actions also require the shortlist gates; a 100 with only 24% evidence does not qualify.

The exact title/company fallback deliberately errs toward suppressing duplicates. It may collapse multiple geographic variants of one role. Review before expanding to fuzzy matching. Applied receipts block preparation even if status changes.

## AI and costs

Leave `LLM_ENABLED=false` for $0 AI usage. Free drafts are deterministic and are the automatic default. To enable optional polishing, set these in `.env`, then restart:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://YOUR-PROVIDER/v1
LLM_API_KEY=YOUR_PRIVATE_KEY
LLM_MODEL=YOUR_INEXPENSIVE_CHAT_MODEL
LLM_INPUT_USD_PER_MILLION=YOUR_VERIFIED_PRICE
LLM_OUTPUT_USD_PER_MILLION=YOUR_VERIFIED_PRICE
AI_DAILY_USD=0.20
AI_DAILY_REQUESTS=10
AI_MAX_OUTPUT_TOKENS=700
```

Choose current model/prices from your provider; no price/model is assumed. The adapter uses `/chat/completions`; providers with different protocols need another adapter. Endpoint must be HTTPS. Existing ChatGPT subscriptions are not assumed to include API credits. No account, credit, or paid service is purchased.

Each request reserves a conservative token-cost upper bound inside an SQLite `BEGIN IMMEDIATE` transaction. Concurrent requests cannot exceed configured request/spend reservations. UTF-8 input bytes plus message overhead are used as a conservative token bound. Actual token-based cost replaces reservation when returned; timeouts/errors keep the reservation because billing may be uncertain. Estimates depend on correctly configured prices and provider-reported tokens; provider invoices are authoritative. Separate rate tiers, reasoning charges or other billing models need a provider-specific estimator before use.

The quota day uses Asia/Kathmandu. Draft cache keys include listing content, rules, profile, CV bytes and template version. Unchanged requests reuse the draft. AI is never used for routine scoring. No automatic retry of paid requests. Telegram and public-feed use incur no service charge in this code, but your internet/device costs remain yours.

“Potential Connects avoided” is the sum of known Connect costs on explicitly rejected Upwork listings. It is a counterfactual estimate, not a verified account saving. The app cannot know your Upwork balance or actual spend without an approved integration.

## Telegram (optional)

Create your own Telegram bot and obtain the intended personal chat ID. Set `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` in `.env`. The dashboard button or CLI command then sends only new qualifying high-priority jobs. Keep credentials out of config JSON and frontend code.

```bash
python -m app.cli notify
```

Messages show title, employer, source link, score, completeness, age, compensation, Connect cost, match and concerns. Each job has a durable alert row reserved before sending. If delivery times out, the state is marked uncertain and is **not automatically retried**, preventing duplicate alerts after ambiguous delivery. Inspect Activity and your chat before considering any manual resend. Setup/tests did not contact Telegram.

## Scheduling on your Mac mini / server

Run discovery once per hour; the source-specific daily/six-hour cooldowns still apply. Cron is the lightweight scheduler, not an extra service. Install these yourself with `crontab -e`, using the actual absolute project path:

```cron
0 * * * * cd /Users/ranjit/jobpilot && /Users/ranjit/jobpilot/.venv/bin/python -m app.cli discover >> /Users/ranjit/jobpilot/data/discovery.log 2>&1
10 * * * * cd /Users/ranjit/jobpilot && /Users/ranjit/jobpilot/.venv/bin/python -m app.cli notify >> /Users/ranjit/jobpilot/data/notifications.log 2>&1
```

Do not install the notify line until Telegram configuration is intentional. Cron runs while the computer is awake; missed sleep intervals are not replayed. Rotate logs periodically. A Linux systemd or macOS launchd wrapper can run `scripts/run.sh` under your own user for restart supervision. No scheduler was installed on your device by this deliverable.

For a remote server, keep the app bound to 127.0.0.1 and use an SSH tunnel:

```bash
ssh -N -L 8000:127.0.0.1:8000 your-user@your-server
```

Open http://127.0.0.1:8000 locally. Do not bind to 0.0.0.0 or expose this personal app publicly. Public hosting requires proper TLS, authentication, rate limiting, backup management and a security review.

## Optional form helper

Install only if needed:

```bash
pip install playwright
python -m playwright install chromium
python scripts/form_assist.py JOB_ID --host exact-employer-host.example --permission-confirmed
```

Use the job ID from API responses or the audit/database. Complete the dashboard packet review first. This helper is deliberately separate from discovery and never runs automatically. `--permission-confirmed` means you checked that this specific employer allows this assistance; it is not a bypass of its terms.

The headed browser has an isolated session. The helper:

- Verifies the destination host; redirects, login/password fields, detected CAPTCHAs and sensitive fields stop filling.
- Shows recognized fields and verified values; waits for `FILL` confirmation.
- Fills ordinary labeled name/email/links/location inputs; uploads the chosen PDF to a recognized CV/resume input; fills a recognized cover-letter textarea.
- Leaves unknown/select/checkbox/radio and sensitive answers to you; saves a local progress report.
- Blocks outbound non-read HTTP methods throughout filling, including autosaves. It never clicks buttons, solves CAPTCHAs, logs in, or submits.

**Limitation:** this is a fill-and-review helper, not a production ATS integration. It does not traverse custom widgets, multi-step forms, authenticated ATS flows, or shadow DOM. Since writes remain blocked, submit from your ordinary browser manually after approval; values may need to be copied. The helper is unit-tested for field mapping but has not been tested against live employer forms. Upwork, LinkedIn, Wellfound and Google forms are manual-only in this MVP. False-negative CAPTCHA/sensitive-field detection remains possible, so run only on deliberately reviewed sites.

## Tests and validation

```bash
pip install -r requirements-dev.txt
python -m pytest -q
# Optional syntax check if Node is installed (not required to run the app):
node --check app/static/app.js
```

20 automated tests passed during delivery. They exercise HTTP routes end-to-end with a test client, unknown-data normalization, exclusions, expiry, senior-title gating, import validation, deduplication, caching, receipt prerequisites, stale approvals, CV invalidation, auth/origin checks, concurrent budget limits, failed-cost reservations, feed cooldown/ETag and notification deduplication. External AI and Telegram tests use mocks; no paid request or real notification was sent. Live discovery fetched 60 Himalayas + 15 Remotive jobs without source errors. Greenhouse is adapter-tested by code inspection only; no specific company board was configured. Browser-rendered UI and live ATS form QA were not available in the development environment; frontend syntax and API behavior were checked. See `VALIDATION.md`.

## Data and security

`app/schema.sql` is the database schema. `data/jobpilot.sqlite3` holds listings, drafts, approvals, receipts, feed cache, usage and audit events. PDFs are in `resumes/`. All API routes require a bearer token. Host/origin allowlists, no CORS, no third-party scripts, escaped UI output, restricted CV filenames, file-size checks, CSP and no-store responses reduce exposure. Secrets stay in environment variables; error events omit HTTP bodies and credentials. The file umask is private; `.env` is generated with mode 0600. Disk encryption/FileVault is still your responsibility. This is a single-user local tool, not a multi-tenant security boundary.

Application text and imported listings are untrusted. No HTML from job descriptions is executed. The optional model cannot call tools and only suggests prose; you must verify every AI statement. Manual edits can still be inaccurate, so the final review is meaningful rather than a claim of automatic factual verification.

Back up with the application stopped, or use SQLite’s backup API:

```bash
python -c "from app.core import db; import sqlite3; c=sqlite3.connect('data/jobpilot.sqlite3'); b=sqlite3.connect('data/backup.sqlite3'); c.backup(b); b.close(); c.close()"
```

Back up `.env` securely and `resumes/` separately; never commit them to a public repository. Version control is not initialized and no deployment has been published. Source attribution and your private documents must remain private when sharing code.

## Layout

```text
app/core.py           configuration, scoring, canonicalization, SQLite access
app/feeds.py          official adapters, polling limits, HTTP cache
app/applications.py   free drafts, LLM budget, review, approval, receipt logic
app/main.py           authenticated API and dashboard server
app/notifications.py  optional Telegram deduplication
app/cli.py            initialize, discover, import, notify, prior history
app/schema.sql        schema and indexes
app/static/           responsive dashboard, no build step
config/               verified profile and configurable preferences
resumes/              original CV PDFs
scripts/              launcher and optional fill-only helper
tests/                isolated pytest suite
```

## Practical next steps

Start locally, correct/confirm the experience wording in your CV, review actual listings, and configure company boards you want to follow. Keep AI disabled until free drafts prove insufficient. Add approved platform integrations, better skill/requirement extraction, and richer ATS support only when the source access and maintenance benefit justify them. Public job feeds can miss fresh openings; official job alerts plus manual import remain useful alongside this MVP.
