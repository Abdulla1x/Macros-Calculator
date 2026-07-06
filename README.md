# 🍽️ Macros Calculator

![React](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5%2B-3178c6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

A full-stack nutrition tracking app: a **React + TypeScript** dashboard UI backed by a **FastAPI + SQLite** REST API.

Log meals by typing an ingredient name — macros auto-fill from your personal **food library**, with an **Open Food Facts** lookup as fallback for foods you haven't logged before. Track calories and protein (plus carbs and fat if you enable them), set daily goals, and watch progress rings and trend charts update as you log.

> **v2 rewrite:** this project started as a Streamlit app and was rebuilt with a decoupled frontend/backend architecture. The original app lives in [`legacy/`](legacy/).

---

## ✨ Features

### 📊 Dashboard
- Daily **progress rings** for each tracked macro vs. your goals
- Today's meal list with inline delete
- 7-day calorie trend sparkline

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
┌─────────────────────┐         ┌──────────────────────┐        ┌────────────────┐
│  React SPA (Vite)   │  HTTP   │  FastAPI REST API    │        │ Open Food Facts │
│  Tailwind, Recharts ├────────►│  /api/meals /foods   ├───────►│  public API     │
│  React Router       │  JSON   │  /analytics /settings│  httpx │  (fallback)     │
└─────────────────────┘         └──────────┬───────────┘        └────────────────┘
                                           │ sqlite3
                                     ┌─────▼─────┐
                                     │ macros.db │  meals · foods · settings
                                     └───────────┘
```

```
Macros-Calculator
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, startup migration + demo seed
│   │   ├── db.py                # Schema, v1 migration, legacy date cleanup
│   │   ├── calculations.py      # Macro scaling / totalling logic
│   │   ├── schemas.py           # Pydantic models
│   │   ├── routers/             # meals, foods, analytics, settings, data (CSV)
│   │   └── services/off_client.py  # Open Food Facts client
│   ├── tests/                   # pytest suite (25 tests)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/client.ts        # Typed API client
│       ├── components/          # Layout, MacroRing, FoodAutocomplete
│       └── pages/               # Dashboard, LogMeal, Analytics, Settings
├── legacy/                      # Original Streamlit app (v1)
└── render.yaml                  # Render deployment blueprint
```

---

## 📸 Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

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

On first start the backend migrates an existing v1 `macros.db` automatically
(adds carbs/fat columns, normalizes legacy date formats — no data is lost).

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

**Backend → [Render](https://render.com)** — the included [`render.yaml`](render.yaml) deploys
`backend/` as a web service. Set `CORS_ORIGINS` to your frontend URL. `SEED_DEMO_DATA=1`
seeds sample data because the free-tier disk is ephemeral (demo data resets on redeploys).

**Frontend → [Vercel](https://vercel.com)** — import the repo, set the root directory to
`frontend/`, and add an environment variable `VITE_API_URL=https://<your-render-service>.onrender.com`.

---

## 🔌 API overview

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/meals` | List (optionally by `?date=`) / create meals |
| DELETE | `/api/meals/{id}` | Delete a meal |
| GET | `/api/foods/search?q=` | Autocomplete over the local food library |
| GET | `/api/foods/lookup?q=` | Open Food Facts search (normalized per serving) |
| POST | `/api/foods` | Save/update a cached food |
| GET | `/api/analytics/daily` | Per-day totals + averages for a date range |
| GET/PUT | `/api/settings` | Daily goals + tracked-macro toggles |
| GET/POST | `/api/data/export` · `/api/data/import` | CSV backup / restore |

---

## 📈 Future improvements

- Meal editing
- Barcode scanning via the Open Food Facts barcode API
- Weekly/monthly goal summaries and streaks
- Multi-user support with authentication
- Frontend component tests (Vitest + Testing Library)

---

## 👨‍💻 Author

**Abdulla** — [github.com/Abdulla1x](https://github.com/Abdulla1x)
