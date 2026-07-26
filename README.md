# 🍽️ Macros Calculator

![React](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5%2B-3178c6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Postgres](https://img.shields.io/badge/Database-PostgreSQL-4169e1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

**🔗 Live app: [macros-calculator-mu.vercel.app](https://macros-calculator-mu.vercel.app)** — sign up and start logging. (Free-tier hosting: the first request after idle can take ~30–60 s.)

A full-stack, **multi-user** nutrition tracking app: a **React + TypeScript** dashboard UI (installable as a PWA) backed by a **FastAPI + SQLAlchemy** REST API on **PostgreSQL**.

Sign up with an email and password and get your own private meal log, food library, goals, and AI analyses — every API endpoint is scoped to the authenticated user.

Log meals by typing an ingredient name — macros auto-fill from your personal **food library**, with an **Open Food Facts** lookup as fallback for foods you haven't logged before. Or skip the form entirely: **describe your meal, record a voice note, or photograph it** — any one is enough — and let **AI estimate the macros** — with honest uncertainty ranges and editable assumptions — before you review and save. Track calories and protein (plus carbs and fat if you enable them), set daily goals, and watch progress rings and trend charts update as you log.

> **v2 rewrite:** this project started as a Streamlit app and was rebuilt with a decoupled frontend/backend architecture. The original app lives in [`legacy/`](legacy/).

---

## ✨ Features

### 🔐 Accounts & privacy
- **Email + password auth**: Argon2id password hashing, JWT bearer tokens (7-day expiry), per-IP rate limiting on login/signup
- **Per-user everything**: meals, food library, goals/settings, and AI analyses are isolated per account — enforced on every query, verified by a dedicated cross-tenant test suite
- **Layered AI quotas**: 20 analyses + 40 voice notes per user per day, under a **global ceiling** of 500 calls/day across every account — the per-user caps stop one person over-using the shared Gemini quota, the global one stops mass signups draining it (or running up a bill on a paid key). All three are env-tunable
- **Own your data**: change your password (revokes all previously issued tokens), download everything as JSON, or permanently delete your account from Settings
- No password *reset* yet (forgot-password email flow) — on the roadmap

### 📊 Dashboard
- Daily **progress rings** for each tracked macro vs. your goals
- Today's meal list with inline edit and delete
- 7-day calorie trend sparkline

### 🤖 AI meal analysis
- **Describe it, speak it, or shoot it**: type a description, record a voice note, or snap a photo — either a description or a photo produces an estimate on its own, and combining them sharpens it
- **Voice notes become editable text**: a recording is transcribed by Gemini straight into the description box *before* anything is estimated, so a misheard ingredient is a typo you fix rather than a wrong number you have to catch afterwards
- **Honest uncertainty**: results show a calorie/macro **range** (low–estimate–high), an overall confidence badge, and per-ingredient confidence dots — not a false-precision single number
- **Editable assumptions**: the AI lists every assumption it made ("1 cup cooked rice ≈ 158 g"); tap one to correct it in the note and **refine** the estimate without starting over
- **You stay in control**: detected ingredients prefill the normal meal editor, so you review and adjust everything before saving
- Each analysis is logged to an `ai_analyses` table (photo and audio discarded) as groundwork for future learning from your corrections
- Powered by **Gemini 3.5 Flash** (free tier) — the provider is isolated in a single backend module, so swapping to another model later is a one-file change. Google retires models on a schedule, so the id is overridable at runtime via `MEAL_AI_MODEL` (no deploy needed) and provider failures are logged with the reason

### 🍽️ Smart meal logging
- **Type-ahead food search**: ingredients you've logged before auto-fill their macros from a local SQLite food library
- **Open Food Facts fallback**: unknown foods can be looked up in the public OFF database (per-serving macros normalized automatically) and are cached locally for next time
- **Save-to-library prompt** for manually entered foods
- Single- or multi-ingredient meals with live-updating totals as you type

### ⚙️ Configurable tracking
- Calories + protein always on; **carbs and fat are opt-in**
- Per-macro daily goals drive the dashboard rings, log form, and analytics

### 📈 Analytics
- Any date range: totals, daily averages, per-macro trend charts, daily table
- **CSV export/import** with duplicate detection and date normalization

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
                                └─────────────┘ ai_analyses
```

```
Macros-Calculator
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan
│   │   ├── db.py                # SQLAlchemy engine + session dependency
│   │   ├── models.py            # ORM models (users, meals, foods, settings, ai_analyses)
│   │   ├── auth/                # signup/login/me, Argon2 + JWT, current-user dependency
│   │   ├── calculations.py      # Macro scaling / totalling logic
│   │   ├── schemas.py           # Pydantic models
│   │   ├── routers/             # meals, foods, analytics, settings, data (CSV), ai
│   │   └── services/
│   │       ├── off_client.py    # Open Food Facts client
│   │       └── meal_ai.py       # AI meal analysis (only provider-aware module)
│   ├── alembic/                 # Database migrations (Postgres)
│   ├── tests/                   # pytest suite incl. auth + cross-tenant isolation
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/client.ts        # Typed API client
│       ├── components/          # Layout, MacroRing, FoodAutocomplete, MealAnalyzer
│       ├── hooks/               # useAudioRecorder (MediaRecorder voice notes)
│       └── pages/               # Dashboard, LogMeal, Analytics, Settings
├── legacy/                      # Original Streamlit app (v1)
└── render.yaml                  # Render deployment blueprint
```

---

## 📸 Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### AI meal analysis — photo, voice, or text → macro estimate with uncertainty
![AI meal analysis](screenshots/logmeal-ai.png)

### AI results prefill the meal editor for review before saving
![AI analysis applied to the meal editor](screenshots/logmeal-ai-applied.png)

### Log a meal — food library auto-fill
![Log Meal](screenshots/logmeal.png)

### Open Food Facts fallback for unknown foods
![OFF fallback](screenshots/logmeal-off-fallback.png)

### Analytics
![Analytics](screenshots/analytics.png)

### Settings — choose what to track
![Settings](screenshots/settings.png)

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

Local development needs no database setup: with `DATABASE_URL` unset the backend
uses a repo-root SQLite file and creates the schema itself. Point `DATABASE_URL`
at Postgres (and set `JWT_SECRET`) for a production-like run — the schema is then
managed by Alembic (`alembic upgrade head`). All env vars are documented in
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

### Tests

```bash
cd backend
python -m pytest
```

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
- `CORS_ORIGINS` — your exact frontend origin (scheme included, no trailing slash)

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

> Free-tier note: Render spins down after idle (~30 s cold start) and Neon autosuspends
> (~1 s resume). The login page mentions this so first-time users don't bounce.

---

## 🔌 API overview

All endpoints except `/api/health` and `/api/auth/signup|login` require an
`Authorization: Bearer <token>` header and operate only on the caller's data.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup` | Create an account → JWT + user |
| POST | `/api/auth/login` | Log in → JWT + user |
| GET | `/api/auth/me` | Current user (token check) |
| POST | `/api/auth/change-password` | Rotate password; revokes older tokens, returns a fresh one |
| DELETE | `/api/auth/account` | Permanently delete the account and all its data |
| GET/POST | `/api/meals` | List (optionally by `?date=`) / create meals |
| DELETE | `/api/meals/{id}` | Delete a meal |
| GET | `/api/foods/search?q=` | Autocomplete over the local food library |
| GET | `/api/foods/lookup?q=` | Open Food Facts search (normalized per serving) |
| POST | `/api/foods` | Save/update a cached food |
| POST | `/api/ai/analyze` | AI meal analysis from any of photo, audio, text (multipart) |
| POST | `/api/ai/transcribe` | Voice note (multipart audio) → editable text |
| PATCH | `/api/ai/analyses/{id}` | Link an analysis to the meal it was saved as |
| GET | `/api/analytics/daily` | Per-day totals + averages for a date range |
| GET/PUT | `/api/settings` | Daily goals + tracked-macro toggles |
| GET/POST | `/api/data/export` · `/api/data/import` | CSV backup / restore |
| GET | `/api/data/export/all` | Full JSON export of everything the account owns |

---

## 📈 Future improvements

- Learn from user corrections to AI analyses (the `ai_analyses` log is the groundwork)
- Upgrade the analysis model (provider is isolated in `services/meal_ai.py`)
- Password reset / email verification (Resend or similar + purpose-claim tokens)
- Barcode scanning via the Open Food Facts barcode API
- Weekly/monthly goal summaries and streaks
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
