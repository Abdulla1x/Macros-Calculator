# 🍽️ Macros Calculator

[![CI](https://github.com/Abdulla1x/Macros-Calculator/actions/workflows/ci.yml/badge.svg)](https://github.com/Abdulla1x/Macros-Calculator/actions/workflows/ci.yml)
![React](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178c6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)
![Postgres](https://img.shields.io/badge/Database-PostgreSQL-4169e1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-725%20pytest-brightgreen)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

**🔗 Live app: [macros-calculator-mu.vercel.app](https://macros-calculator-mu.vercel.app)** — sign up and start logging. (Free-tier hosting: the first request after idle can take ~30–60 s.)

A full-stack, **multi-user** nutrition tracking app: a **React + TypeScript** dashboard UI (installable as a PWA) backed by a **FastAPI + SQLAlchemy** REST API on **PostgreSQL**.

Sign up with an email and password and get your own private meal log, food library, goals, and AI analyses — every API endpoint is scoped to the authenticated user.

Log meals by typing an ingredient name — macros auto-fill from your personal **food library**, with an **Open Food Facts** lookup as fallback for foods you haven't logged before. Or skip the form entirely: **describe your meal, record a voice note, or photograph it** — any one is enough — and let **AI estimate the macros** — with honest uncertainty ranges and editable assumptions — before you review and save. Track calories and protein (plus carbs and fat if you enable them), set daily goals, weigh in, and watch progress rings, trend charts and a computed weekly review update as you log.

> **v2 rewrite:** this project started as a Streamlit app and was rebuilt with a decoupled frontend/backend architecture. The original app lives in [`legacy/`](legacy/).

---

## ✨ Features

### 🔐 Accounts & privacy
- **Email + password auth**: Argon2id password hashing, JWT bearer tokens (7-day expiry), per-IP rate limiting on login, signup and password reset
- **Per-user everything**: meals, food library, saved meal templates, weight entries, water logs, step counts, supplements and their check-offs, calorie plans, goals/settings, and AI analyses are isolated per account — enforced on every query, verified by a dedicated cross-tenant test suite
- **Layered AI quotas**: 20 analyses + 40 voice notes + 3 review summaries per user per day, under a **global ceiling** of 500 calls/day across every account — the per-user caps stop one person over-using the shared Gemini quota, the global one stops mass signups draining it (or running up a bill on a paid key). All of them are env-tunable
- **Own your data**: change your password (revokes all previously issued tokens), download everything as JSON, or permanently delete your account from Settings
- **Password reset by email — built, deployed, and switched off.** The endpoints, the single-use link (hashed at rest, valid an hour, revoking every session when used) and 38 tests are all here and running in production. They answer **503 to every address**, because no email provider is configured — three free providers were tried and all three refused a domainless free account, which is the profile their fraud screening targets. Until one is wired up **a forgotten password means a lost account**, and the signup page says so rather than letting you find out later. Nothing about the feature needs a deploy to switch on; it activates on credentials alone

### 📊 Dashboard
- Daily **progress rings** for each tracked macro vs. your goals
- **Quick log** — your saved meals as one-tap tiles, most recently used first, folded to six with the rest a tap away
- **Water tracker** with configurable quick-add buttons and a goal derived from your trend weight — shown with the arithmetic, not just the answer
- **Steps tracker**, typed in by hand or imported from a `date,steps` CSV — no phone or watch sync is possible in a web app, and the UI says so rather than implying one. Set a goal or don't; with none set the card shows the count alone
- **Supplement tracker** — a list with a dose and the times of day you take it, ticked off from the dashboard. Reminders are in-app only, deliberately: push on Android needs Google Play Services and scheduled local notifications need a browser API nobody shipped, so the card says a dose is overdue while you have it open and never pretends it will reach your phone. Pausing keeps the history; deleting does not
- **Calorie planning** — move calories between days without moving the week. Plan a bigger day and fund it from the days around it, or spread a day that already ran over across the days ahead (and the mirror when bulking and under). Three things are deliberate: it is **not a debt** — measured expenditure already absorbs one large day as a slightly slower week, so this only decides where it lands; **nothing prompts you** — one standing link under the calorie ring, present whether the day went well or badly, because an app that asks after every overshoot is a different kind of app; and **you pick the days**, with the server only refusing a spread that would take one below a safe calorie floor, naming the day rather than quietly shaving less than you asked. Protein never moves — carbohydrate and fat absorb the difference
- Today's meal list with inline edit and delete
- 7-day calorie trend sparkline

### 🤖 AI meal analysis
- **Describe it, speak it, or shoot it**: type a description, record a voice note, or snap a photo — either a description or a photo produces an estimate on its own, and combining them sharpens it
- **Voice notes become editable text**: a recording is transcribed by Gemini straight into the description box *before* anything is estimated, so a misheard ingredient is a typo you fix rather than a wrong number you have to catch afterwards
- **Honest uncertainty**: results show a calorie/macro **range** (low–estimate–high), an overall confidence badge, and per-ingredient confidence dots — not a false-precision single number
- **Editable assumptions**: the AI lists every assumption it made ("1 cup cooked rice ≈ 158 g"); tap one to correct it in the note and **refine** the estimate without starting over
- **It can use your saved foods instead of guessing them.** Attach foods from your library before analysing and their macros are sent as facts. It splits the work along the line each side is good at: a photo is poor evidence for how many calories are in chicken breast — you already know that exactly, because you saved it — and good evidence for how much of it is on the plate, which your library cannot know. **The AI estimates the portion; your library supplies the macros.** If it names a food you have saved but did not attach, the ingredient row *offers* to use your numbers rather than quietly rewriting them
- **You stay in control**: detected ingredients prefill the normal meal editor, so you review and adjust everything before saving
- **Estimate accuracy, measured against you.** Every analysis is logged to an `ai_analyses` table (photo and audio discarded) and compared with what you actually saved: how often the true value fell inside the stated range, and whether the estimates lean high or low. Where there is not enough evidence to answer honestly it **refuses** rather than printing a reassuring number
- Powered by **Gemini 3.5 Flash** (free tier) — the provider is isolated in a single backend module, so swapping to another model later is a one-file change. Google retires models on a schedule, so the id is overridable at runtime via `MEAL_AI_MODEL` (no deploy needed) and provider failures are logged with the reason
- **Survives provider outages**: Gemini's "model is overloaded" 503 is retried with jittered backoff and then re-tried against a fallback model — overload is per serving pool, so an older generation is usually still answering. Every call carries an explicit deadline, and `GET /api/ai/status?probe=true` names the cause when it doesn't

### 🍽️ Smart meal logging
- **Type-ahead food search**: ingredients you've logged before auto-fill their macros from your personal food library
- **Open Food Facts fallback**: unknown foods can be looked up in the public OFF database (per-serving macros normalized automatically) and are cached locally for next time
- **A food library you can edit**, not just accumulate — rename, correct or delete saved foods from Settings. Correcting one that came from Open Food Facts makes it yours, so a later lookup can't overwrite your own numbers
- **Saved meals**: store a meal you eat often and re-log it in one tap from the dashboard
- **Share a meal by code**: turn a meal or a saved template into a short code, hand it to someone, and they get an **editable copy in their own account**. The code is a self-contained encoded payload — there is no shared row, no invite, nothing to revoke, and no account id inside it, so per-user isolation is untouched by the feature existing
- Single- or multi-ingredient meals with live-updating totals as you type

### ⚖️ Weight & trends
- Log a weigh-in and read the **trend**, not the daily noise — an exponentially weighted line over the raw points, with the weekly rate fitted over the last 28 days
- Kilograms or pounds, switchable at any time; the stored value never changes, only how it's shown
- Your weigh-ins are not just a chart: they are what the measured daily burn and — if you enable them — the automatic daily targets are worked out from
- **An optional weigh-in nudge.** Set a time and how many days you want between weigh-ins, and on a day one is due a card appears with a link straight to the weight log. Dismiss it and it stays gone until the next day it is due. It never appears on the weight page itself — you are already where it would send you. Leave the time empty, which is how every account starts, and none of it happens

### ⚙️ Configurable tracking
- Calories + protein always on; **carbs and fat are opt-in**
- Per-macro daily goals drive the dashboard rings, log form, and analytics
- Optional **body profile** (height, date of birth, sex, activity level, goal
  rate) turns into BMI, a daily burn, and calorie/macro targets — every figure
  shown next to the input it came from
- **Your daily burn is measured, not guessed**, once you have logged enough:
  roughly two weeks of weigh-ins and meals turns into a real energy-balance
  figure from your own data, shown beside what the formula would have said.
  Until then it says exactly what it is still waiting for
- Let the app **keep those goals in step with your weight**: with auto-targets
  on, the daily goals are recalculated on every weigh-in instead of staying
  wherever you first set them
- Settings is five addressable tabs — Goals, Body, Trackers, Library, Account — each with its own URL, and a save bar that follows you between them rather than scrolling away

### 🗓️ Weekly review
- **Everything the app already knew, added up in one place**: how much you logged, calories and protein against target, whether your weight is moving the way you asked, where your daily burn figure came from, water, steps, and one line on estimate accuracy
- **Every sentence is arithmetic, not opinion.** Each section shows the number, what it is compared with, and how many days it was worked out from — and where there isn't enough to answer, it says what is missing instead of guessing
- **Today is left out on purpose.** The week ends yesterday, because averaging in a day that still has dinner to come makes every week look better than it was
- **Not every section is about the same seven days, and each one says which.** The weight rate is fitted over four weeks, not one, because a seven-day weight slope is mostly water. Calling that "this week" would have been a tidier page and a less honest one
- **Sections appear only for things you already track** — no step goal, no steps section. Nothing new to switch on
- And an optional **plain-English reading** of it. That one button asks the AI; it is handed the figures and nothing else, and is not allowed to work anything out, introduce a number, or tell you what to eat. It isn't stored — come back tomorrow and you get the figures, not yesterday's wording

### 📈 Analytics
- Any date range: totals, daily averages, per-macro trend charts, daily table
- Averages are **per day you logged**, not per day in the range — a day with nothing recorded is missing data, not a day of zero intake
- **CSV export/import** with duplicate detection and date normalization

---

## 📸 Screenshots

Every screen at both widths. Each image is one long capture of the **entire page**, top to bottom — not the part that happens to fit above the fold.

> 🔍 **Click any screenshot to open it full size.**
> Because each one is a whole page, it is scaled down to fit here and runs past the bottom of your screen. What you can see without scrolling is not the end of it.

### Dashboard

Rings against your goals, one-tap quick log, the three daily trackers, today's meals, and the seven-day trend.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/dashboard.png"><img src="screenshots/desktop/dashboard.png" alt="Dashboard in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/dashboard.png"><img src="screenshots/mobile/dashboard.png" alt="Dashboard on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### AI meal analysis

Describe it, speak it or photograph it. The estimate comes back as a range with a confidence badge, per-ingredient confidence dots, and every assumption listed and editable.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/ai-analysis.png"><img src="screenshots/desktop/ai-analysis.png" alt="AI meal analysis in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/ai-analysis.png"><img src="screenshots/mobile/ai-analysis.png" alt="AI meal analysis on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### The estimate fills the meal editor

Nothing is saved until you have looked at it. Ingredients arrive as ordinary rows you can correct first.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/ai-applied.png"><img src="screenshots/desktop/ai-applied.png" alt="The estimate fills the meal editor in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/ai-applied.png"><img src="screenshots/mobile/ai-applied.png" alt="The estimate fills the meal editor on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### Log a meal

Type an ingredient and your food library fills in the macros, with an Open Food Facts lookup behind it for anything you have not logged before.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/log-meal.png"><img src="screenshots/desktop/log-meal.png" alt="Log a meal in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/log-meal.png"><img src="screenshots/mobile/log-meal.png" alt="Log a meal on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### Weight

The trend line rather than the daily noise, with the weekly rate fitted over 28 days.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/weight.png"><img src="screenshots/desktop/weight.png" alt="Weight in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/weight.png"><img src="screenshots/mobile/weight.png" alt="Weight on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### Weekly review

Eight computed checks. Each one names the number, what it is compared with, and how many days it was worked out from.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/review.png"><img src="screenshots/desktop/review.png" alt="Weekly review in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/review.png"><img src="screenshots/mobile/review.png" alt="Weekly review on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### Analytics

Any date range: totals, per-day averages over the days you actually logged, and a chart per macro.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/analytics.png"><img src="screenshots/desktop/analytics.png" alt="Analytics in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/analytics.png"><img src="screenshots/mobile/analytics.png" alt="Analytics on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

### Settings

Five tabs, each with its own address, and a save bar that follows you between them.

<table>
<tr><th align="center">Desktop</th><th align="center">Phone</th></tr>
<tr>
<td valign="top" align="center"><a href="screenshots/desktop/settings.png"><img src="screenshots/desktop/settings.png" alt="Settings in a desktop browser" width="620"></a></td>
<td valign="top" align="center"><a href="screenshots/mobile/settings.png"><img src="screenshots/mobile/settings.png" alt="Settings on a phone" width="190"></a></td>
</tr>
</table>

<sub>Whole page, scaled down — click either image to view it full size.</sub>

---

## 📲 Install it on your phone

The app is a **PWA**, so it can be added to your home screen and opened like a
native app — its own icon, its own window, no address bar. There is nothing to
download and no app store involved: it is the same
[live app](https://macros-calculator-mu.vercel.app), saved as a shortcut that
the browser then treats as an app.

**On Android** (Chrome, Edge, Samsung Internet)

1. Open the app in your browser.
2. Open the browser menu — the **⋮** in the corner.
3. Tap **Install app**, or **Add to Home screen** if that is the wording you see.
4. Confirm. The icon appears with your other apps.

**On iPhone or iPad** (Safari)

1. Open the app in Safari.
2. Tap **Share** — the square with the arrow pointing up.
3. Scroll down the list and tap **Add to Home Screen**.
4. Tap **Add**.

On iOS 16.4 and later, Chrome, Edge and Firefox can add to the home screen from
their own share menus too; before that, it has to be Safari.

**On a desktop** (Chrome, Edge) — an install icon appears at the right-hand end
of the address bar; the browser menu has the same option if it doesn't.

**What you get:** the app opens full-screen with no browser chrome, on its own
icon, with a dark splash screen while it starts.

⚠️ **What you do not get, said rather than left for you to discover:**

- **It does not work offline.** The service worker caches the app shell only,
  and API responses are deliberately never cached — a shared browser cache
  holding one account's data is exactly what per-user isolation exists to
  prevent. With no connection the app opens and has nothing to show.
- **It cannot notify you.** Installing changes nothing about reminders: the
  supplement and weigh-in nudges still speak only while the app is open, for
  the reasons given above.

---

## 🏗️ Architecture

```
┌─────────────────────┐         ┌──────────────────────┐        ┌─────────────────┐
│  React SPA / PWA    │  HTTP   │  FastAPI REST API    │        │ Open Food Facts │
│  Tailwind, Recharts ├────────►│  /api/auth /meals    ├───────►│  public API     │
│  React Router       │ Bearer  │  /foods /ai ...      │  httpx │  (fallback)     │
└─────────────────────┘  JWT    └──────┬────────┬──────┘        └─────────────────┘
                                       │SQLAlchemy  google-genai ┌─────────────────┐
                                ┌──────▼──────┐ └───────────────►│ Gemini 3.5 Flash│
                                │  PostgreSQL │ users · meals    │ (meal analysis) │
                                │ (Neon)/SQLite│ foods · settings└─────────────────┘
                                └─────────────┘ ai_analyses     ┌─────────────────┐
                                        password_resets  httpx  │ Brevo (off)     │
                                                 └─────────────►│ (password reset)│
                                                                └─────────────────┘
```

```
Macros-Calculator
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan (fails fast on a missing JWT_SECRET)
│   │   ├── db.py                # SQLAlchemy engine + session dependency
│   │   ├── env.py               # env_int / env_float — one idiom for ~23 environment variables
│   │   ├── models.py            # ORM models: users, password_resets, meals, meal_templates, foods,
│   │   │                        #   weights, water_logs, steps, supplements, supplement_logs,
│   │   │                        #   calorie_plan_days, settings, ai_analyses
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── auth/                # signup/login/me, Argon2 + JWT, current-user dependency
│   │   ├── rate_limit.py        # per-IP limits on the public auth routes
│   │   ├── upsert.py            # the check-then-insert race, handled once instead of at five sites
│   │   ├── calculations.py      # macro scaling, weight trend, BMR/TDEE/target math
│   │   ├── targets.py           # body profile → daily targets, and measured TDEE
│   │   ├── banking.py           # moving calories between days: the split, the floors, the sum rules
│   │   ├── calibration.py       # how far you move the AI's numbers — coverage, bias, sample sizes
│   │   ├── review.py            # the weekly review's arithmetic: eight checks, each with its own window
│   │   ├── share.py             # the meal-code codec (a self-contained payload; no table)
│   │   ├── announcements.py     # committed release notes + an env-var status banner
│   │   ├── routers/             # auth, meals, meal_templates, share, foods, weights, analytics,
│   │   │                        #   settings, data (CSV/JSON), ai, water, steps, plan,
│   │   │                        #   supplements, review, announcements, admin
│   │   └── services/
│   │       ├── off_client.py    # Open Food Facts client
│   │       ├── meal_ai.py       # AI meal analysis (the only AI-provider-aware module)
│   │       └── email.py         # password-reset email (the only Brevo-aware module; switched off)
│   ├── alembic/                 # database migrations (Postgres)
│   ├── scripts/                 # smoke_multiuser.py — the live two-account isolation check
│   ├── tests/                   # pytest suite incl. auth + cross-tenant isolation
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/client.ts        # typed API client
│       ├── auth/                # AuthContext + token storage (guarded against blocked localStorage)
│       ├── settings/            # SettingsContext — one settings fetch for the whole app
│       ├── components/
│       │   ├── ui/              # the six shared primitives: Modal, Card, TextInput,
│       │   │                    #   OptionChip, Field, Button
│       │   ├── settings/        # the Settings panels' sections
│       │   └── ...              # Layout, MacroRing, DailyTrackerCard, MealAnalyzer,
│       │                        #   FoodAutocomplete, WeighInNudge, ShareCodePanel
│       ├── hooks/               # useAudioRecorder (MediaRecorder voice notes), useWarmup, ...
│       ├── lib/                 # dates, parse, limits (mirrors the server's bounds), units,
│       │                        #   chartTheme (one place for every recharts colour), libraryMatch
│       └── pages/               # Dashboard, LogMeal, Weight, Analytics, Review, Admin,
│                                #   WhatsNew, settings/ (five tab panels), and the four auth pages
├── docs/                        # AI provider runbook + the Gemini EEA-region incident write-up
├── scripts/                     # check.sh (all five gates), dev.sh, review-changes.sh,
│                                #   dom-snapshot.mjs (the refactor DOM-diff harness)
├── screenshots/                 # desktop/ and mobile/ captures used by this README
├── .github/workflows/           # ci.yml (the same five gates), backup.yml (daily export)
├── legacy/                      # original Streamlit app (v1)
├── LICENSE                      # MIT
└── render.yaml                  # Render blueprint — documentation of intent, NOT synced with
                                 #   the dashboard, which is the source of truth for every value
```

---

## 🚀 Running locally

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**AI meal analysis (optional):** set `GEMINI_API_KEY` before starting the backend
(get a free key at [Google AI Studio](https://aistudio.google.com/apikey)):

```bash
GEMINI_API_KEY=your-key uvicorn app.main:app --reload --port 8000
```

Without a key the rest of the app works normally and the analyze endpoint returns
a clear 503. `MEAL_AI_MODEL` overrides the default model (`gemini-3.5-flash`).
Keep the key in your environment or an untracked `.env` — never commit it.

When AI analysis misbehaves, `GET /api/ai/status?probe=true` (authenticated) names
the cause — upstream outage, unreachable, misconfigured key, or quota — instead of
leaving you to read logs. See [`docs/runbook-ai-provider.md`](docs/runbook-ai-provider.md).

Local development needs no database setup: with `DATABASE_URL` unset the backend
uses a repo-root SQLite file and creates the schema itself. Point `DATABASE_URL`
at Postgres (and set `JWT_SECRET`) for a production-like run — the schema is then
managed by Alembic (`alembic upgrade head`). All 23 env vars are documented in
[`backend/.env.example`](backend/.env.example).

**Migrating from the single-user version:** the old `macros.db` isn't read by
the multi-user schema. Export your meals as CSV from the old app (or keep the
file), create an account, and use **Analytics → Import meals (CSV)**.

### 2. Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (the dev server proxies `/api` to the backend).

Or start both at once, with a throwaway database:

```bash
./scripts/dev.sh --fresh
```

### Tests and gates

`scripts/check.sh` runs every pre-commit gate in one pass — the same five CI runs:

```bash
./scripts/check.sh              # all five
./scripts/check.sh --backend    # pytest + ruff only
./scripts/check.sh --frontend   # tsc + oxlint + build only
```

| Gate | Command |
|---|---|
| backend tests | `venv/bin/python -m pytest -q` — 725 tests |
| backend lint | `ruff check app tests scripts` |
| frontend typecheck | `npx tsc --noEmit -p tsconfig.app.json` — `strict` **and** `noUncheckedIndexedAccess` |
| frontend lint | `npm run lint` (oxlint) |
| frontend build | `npm run build` |

It deliberately does not stop at the first failure. `a && b && c` hides whether the
frontend is also broken once the backend fails, turning one fix-and-rerun cycle into
three; every gate runs, then a summary says which failed.

**Cross-tenant isolation is tested twice, deliberately.** `tests/test_isolation.py`
asserts it in-process (49 tests). `backend/scripts/smoke_multiuser.py` asserts it
against a *running* server — over a hundred live checks that sign up two accounts and
fire every verb at the other account's concrete row ids, which is the only version
that also covers routing, auth middleware and the deployed database:

```bash
cd backend
BASE_URL=http://localhost:8000 DATABASE_URL=... venv/bin/python scripts/smoke_multiuser.py
```

⚠️ **Set `DATABASE_URL` or the row-ownership half silently skips** and you get a
smaller, quieter pass. It also runs against the deployed URL — note that it leaves
its two throwaway accounts behind, so it is the wrong tool for probing production.

**Proving a refactor changed nothing.** `scripts/dom-snapshot.mjs` renders every
route with a signed-in, seeded account and dumps `document.body.innerHTML` with
every `class` attribute stripped. Run it on each branch and diff:

```bash
node scripts/dom-snapshot.mjs /tmp/snap-before   # on main
node scripts/dom-snapshot.mjs /tmp/snap-after    # on your branch
diff -ru /tmp/snap-before /tmp/snap-after
```

Stripping `class` is what makes it useful: a styling change passes, while a stray
wrapper `<div>`, a dropped attribute, a reordered sibling or a section that quietly
stopped rendering still fails. It needs a browser, so it is **not** part of
`check.sh`, and `playwright-core` is deliberately absent from `package.json` — it is
a local verification tool, not something the app ships, and CI has no reason to
download a browser to run `npm ci`. The one-time setup, including the no-root path
for the missing system libraries on Linux, is in the script's own header.

Browser-level checks beyond that diff are manual; backend tests do not catch
interaction bugs.

**Why ~5% of the suite covers a switched-off feature.** `tests/test_password_reset.py`
is 38 tests over `services/email.py`, which answers 503 to everything today. They are
kept rather than deleted because the feature is *code-complete and unconfigured*, not
abandoned — it activates on credentials alone, with no code change and no deploy.
Deleting the tests would mean writing them again to turn it on. Roughly 13 of them are
Brevo-specific (they pin the `api-key` header and the 201 status) and would need
rewriting for a different provider; the other ~25 test the endpoints and would not.

---

## ☁️ Deployment

**Database → [Neon](https://neon.tech)** (free tier) — create a project, copy the
connection string, and rewrite its scheme for SQLAlchemy:
`postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require`. That's the value for
`DATABASE_URL`. (Plain Postgres — a `pg_dump` moves you anywhere later.)

**Backend → [Render](https://render.com)** — the included [`render.yaml`](render.yaml) deploys
`backend/` as a web service; the start command runs `alembic upgrade head` before the
server boots, so the schema is created/updated on deploy. In the Render dashboard set:
- `DATABASE_URL` — the Neon string above
- `GEMINI_API_KEY` — optional, enables AI meal analysis
- `MEAL_AI_MODEL` — optional, overrides the default Gemini model without a redeploy
- `MEAL_AI_FALLBACK_MODEL` — optional, model tried when the primary returns 5xx
  (default `gemini-2.5-flash`; set empty to disable)
- `MEAL_AI_DEADLINE_S` — optional, seconds one analysis may keep retrying a busy
  provider (default `60`; the frontend timeout must stay above it)
- `AI_DAILY_LIMIT` / `AI_TRANSCRIBE_DAILY_LIMIT` / `AI_REVIEW_DAILY_LIMIT` /
  `AI_GLOBAL_DAILY_LIMIT` — optional, the per-user and app-wide AI quotas
  (defaults 20 / 40 / 3 / 500)
- `AI_PROBE_DAILY_LIMIT` / `MEAL_AI_STATUS_DETAIL` — optional, govern
  [`GET /api/ai/status`](docs/runbook-ai-provider.md)
- `CORS_ORIGINS` — your exact frontend origin (scheme included, no trailing slash)
- `ADMIN_EMAILS` — optional, comma-separated addresses allowed to read
  `/api/admin` (usage metrics: signups, active accounts, per-account counts and
  AI consumption). Case- and whitespace-insensitive, re-read on every request.
  **Unset means nobody is an admin** — there is no role column and no promotion
  endpoint, so this variable is the only way to grant it. Admins see counts and
  timestamps only, never meal, food or weight content
- `STATUS_BANNER` — optional, a site-wide notice read on every request, so an
  outage can be announced without a deploy
- `BREVO_API_KEY` + `EMAIL_SENDER_ADDRESS` — enable password reset (it returns 503
  for every address until both are set). The sender must be verified in the Brevo
  dashboard first: add the address, then enter the 6-digit code it emails you.
  ⚠️ **This deployment has never got past that step**, and neither did two
  alternatives — Brevo's phone verification never delivers a code, and Mailjet
  auto-blocks the account on its first API call. Both are the same underlying
  cause: a new free account with no domain and a gmail.com sender is the profile
  free-ESP fraud screening exists to stop. A provider with **an HTTP API (never
  SMTP — Render blocks outbound 25/465/587 on free web services) and a real
  domain** is what unblocks it
- `EMAIL_SENDER_NAME` / `APP_BASE_URL` / `PASSWORD_RESET_TTL_MINUTES` /
  `PASSWORD_RESET_GLOBAL_DAILY_LIMIT` — optional; all default in code. `APP_BASE_URL`
  builds the emailed link and is **never** taken from the request's Host header

`JWT_SECRET` is auto-generated by the blueprint. Rotating it logs every user out —
that's also the emergency kill switch for leaked tokens.

> **Pick a non-EEA region.** Google's terms allow only *paid* services for users in
> the EEA, UK and Switzerland — and your server's IP is what counts as the user's
> location. So a backend in Render's Frankfurt region fails every analysis with
> `400 FAILED_PRECONDITION` — *"User location is not supported for the API use"* —
> while the same key works fine from a machine outside those countries. Note that
> Google's [available-regions](https://ai.google.dev/gemini-api/docs/available-regions)
> page lists every EEA country as supported and doesn't mention this, so the docs
> will not warn you. `render.yaml` pins `region: ohio`; put the Neon project in the
> matching region (`AWS US East 2`) so database round-trips stay local.
> This one took three days to diagnose — the write-up is in
> [`docs/incident-2026-07-gemini-eea-region.md`](docs/incident-2026-07-gemini-eea-region.md).

**Frontend → [Vercel](https://vercel.com)** — import the repo, set the root directory to
`frontend/`, and add an environment variable `VITE_API_URL=https://<your-render-service>.onrender.com`.
Also update `connect-src` in [`frontend/vercel.json`](frontend/vercel.json) to your own API
origin — the CSP there names an exact host, and the browser silently refuses every request
to anything else. That failure looks like a network error and never reaches the server, so
`curl` against the API will happily report everything healthy.

> Free-tier note: Render stops the service after 15 minutes without traffic, and the next
> request pays for the boot — a 52.3 s median over ten consecutive cold starts, and about
> 62 s on the slow one run in five. Neon autosuspends too, but resumes in about a second.
> The login page says so, so first-time users don't bounce.
>
> That wait is removed across a daily window — 05:03 to 20:53 `Asia/Dubai`, one ping every
> 10 minutes — by a scheduler at [cron-job.org](https://cron-job.org), not by GitHub
> Actions. GitHub's cron cannot hold a 15-minute deadline on a free public repository: it
> delivered 3 of the 114 runs a day this needs, and `backup.yml` has started 4.5 to 12
> hours late on eight consecutive days.
> [`.github/workflows/keep-warm.yml`](.github/workflows/keep-warm.yml) carries the whole
> record of why, and remains a one-click button for waking the server by hand.
> **Outside the window the cold start is still there** — the window exists because Render
> allows 750 instance-hours per workspace per month and a 24/7 ping would spend all but six
> of them.
>
> **While a cold start is happening you get a progress bar, not just a spinner.** It is
> calibrated on those measurements — a straight line to 90% across the 52.3 s that eight
> of ten boots take, then a creep toward 99% covering the ~10 s extra step the other two
> pay. It never fills on a timer; only the request completing ends the wait. `/admin`
> shows the same thing from the operator's side: uptime, how many health pings have
> arrived since boot, and whether that adds up to the scheduler actually landing.
>
> The scheduled job calls `/api/health?src=keepwarm`, and the marker matters: Render's own
> platform monitor hits the bare route every few seconds, so without a way to tell the two
> apart the "are the pings landing" answer on `/admin` counts the platform's traffic as the
> scheduler's and can never report a problem.
>
> The ping targets `/api/health` and must keep doing so: it is the one route that never
> touches Postgres. Pointing it at anything that queries the database would hold Neon awake
> ~16 hours a day, over its 100 CU-hour monthly allowance, and suspend the database until
> the next billing period.

---

## 🔌 API overview

51 paths. All of them require an `Authorization: Bearer <token>` header and operate
only on the caller's data, except these public ones: `/api/health`,
`/api/announcements`, `/api/auth/signup|login`, and
`/api/auth/forgot-password|reset-password`.

### Accounts

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup` | Create an account → JWT + user |
| POST | `/api/auth/login` | Log in → JWT + user |
| GET | `/api/auth/me` | Current user (token check) |
| POST | `/api/auth/change-password` | Rotate password; revokes older tokens, returns a fresh one |
| POST | `/api/auth/forgot-password` | Email a reset link. Always 200, whether or not the address exists — but **503 today**, see above |
| POST | `/api/auth/reset-password` | Consume a link and set a new password; revokes every session. Reachable, but no link can be issued while the above 503s |
| DELETE | `/api/auth/account` | Permanently delete the account and all its data |

### Meals, foods and sharing

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/meals` | List (optionally by `?date=`) / create meals |
| PUT/DELETE | `/api/meals/{id}` | Edit or delete a meal |
| GET/POST | `/api/meal-templates` | List saved meals / save one (upsert by name) |
| DELETE | `/api/meal-templates/{id}` | Delete a saved meal template |
| GET/POST | `/api/foods` | The food library / save or update a food |
| PUT/DELETE | `/api/foods/{id}` | Rename and correct a saved food / remove it |
| GET | `/api/foods/search?q=` | Autocomplete over the local food library |
| GET | `/api/foods/lookup?q=` | Open Food Facts search (normalized per serving) |
| GET | `/api/share/meal/{id}` | Encode one of your meals as a shareable code |
| GET | `/api/share/template/{id}` | Encode a saved meal as a shareable code |
| POST | `/api/share/decode` | Read a code back into an editable draft — no row is shared |

### AI

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ai/analyze` | AI meal analysis from any of photo, audio, text (multipart) |
| POST | `/api/ai/transcribe` | Voice note (multipart audio) → editable text |
| PATCH | `/api/ai/analyses/{id}` | Link an analysis to the meal it was saved as |
| GET | `/api/ai/calibration` | How your corrections compare with the estimates — coverage, bias, sample size |
| GET | `/api/ai/status` | Provider health; `?probe=true` makes one live call and classifies the failure |

### Weight, trackers and planning

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/weights` | Weigh-in history / log one (upsert by date) |
| GET | `/api/weights/trend` | Smoothed trend line, latest trend weight and weekly rate |
| DELETE | `/api/weights/{id}` | Delete a weigh-in |
| GET/POST | `/api/water` | One day's water (entries, total, derived goal) / log a drink |
| DELETE | `/api/water/{id}` | Remove one water entry (what the card's undo calls) |
| GET/POST/DELETE | `/api/steps` | One day's steps (count, goal, walking estimate) / save it / clear it |
| POST | `/api/data/import/steps` | Import a step history from a two-column `date,steps` CSV; days already logged are kept |
| GET | `/api/supplements/day` | One day's doses: every scheduled slot and whether it was ticked |
| POST/DELETE | `/api/supplements/log` | Tick / un-tick one dose; both idempotent, both return the updated day |
| GET/POST | `/api/supplements` | The supplement list (paused ones included) / add one |
| PUT/DELETE | `/api/supplements/{id}` | Edit, pause or resume one / delete it and its check-offs |
| GET | `/api/plan/day` | One day's **effective** targets — the four numbers its rings are drawn against, after any plan |
| GET/POST | `/api/plan` | Upcoming plans / create one (validated as a set; refusals name every offending day) |
| DELETE | `/api/plan/{event_date}` | Cancel a plan, removing only the days it has not spent yet |
| GET | `/api/plan/surplus` | How far a finished day ran from its target, with what it was measured against |

### Review, settings and data

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/review` | The computed weekly review — eight checks, each with its own window and sample size |
| POST | `/api/review/summary` | An AI reading of those figures; nothing is stored |
| GET | `/api/analytics/daily` | Per-day totals + averages for a date range |
| GET/PUT | `/api/settings` | Daily goals, tracked-macro toggles, body profile, tracker goals, weigh-in reminder |
| GET | `/api/settings/targets` | BMI, BMR, measured-or-estimated TDEE, calorie + macro targets |
| GET | `/api/data/export` | CSV backup of every meal |
| POST | `/api/data/import` | Restore meals from CSV, with duplicate detection |
| GET | `/api/data/export/all` | Full JSON export of everything the account owns |
| GET | `/api/announcements` | Committed release notes + the status banner (public) |
| GET | `/api/health` | Liveness check (public). `?src=keepwarm` marks a request as the keep-warm scheduler's |
| GET | `/api/admin/stats` | Usage metrics, behind the `ADMIN_EMAILS` allowlist |
| GET | `/api/admin/users` | Per-account counts and AI consumption; never meal or weight content |
| GET | `/api/admin/keep-warm` | Uptime, scheduler-ping counts and the ping window; in-memory, wiped at spin-down |

---

## 📈 Future improvements

- Learn from your corrections to AI analyses — the accuracy figures are measured
  today, but nothing feeds them back into the next estimate
- Upgrade the analysis model (provider is isolated in `services/meal_ai.py`)
- Email verification at signup (would also close the account-enumeration gap the signup 409 leaves open)
- A sending domain of our own, so reset emails stop being rewritten to `brevosend.com`
- Barcode scanning via the Open Food Facts barcode API — examined and parked
  rather than unstarted: it needs a hit-rate measurement against real shelves
  first, because a scanner that misses most products is worse than no scanner
- Frontend component tests (Vitest + Testing Library)

---

## 🔍 Engineering notes

- [**AI meal analysis down for three days**](docs/incident-2026-07-gemini-eea-region.md) — a
  post-mortem. The feature failed for every input; the API key was valid, the model existed,
  and the deployed code worked fine from a laptop. Six hypotheses were eliminated before the
  real one: Gemini's free tier is geo-blocked in the EEA, and the backend was hosted in
  Frankfurt. Covers the diagnosis, the region migration, what remains unproven, and the two
  further failures the migration caused.

---

## 👨‍💻 Author

**Abdulla** — [github.com/Abdulla1x](https://github.com/Abdulla1x)
