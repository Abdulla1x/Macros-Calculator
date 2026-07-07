import os
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import get_connection, init_db
from .routers import ai, analytics, data, foods, meals, settings

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def seed_demo_data() -> None:
    """Populate an empty database with sample data (for the ephemeral demo host)."""
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM meals LIMIT 1").fetchone():
            return

        foods_rows = [
            ("Chicken Breast", 100, 165, 31, 0, 3.6, "user"),
            ("White Rice (cooked)", 100, 130, 2.7, 28, 0.3, "user"),
            ("Whole Egg", 50, 72, 6.3, 0.4, 4.8, "user"),
            ("Oats", 40, 150, 5, 27, 2.5, "user"),
            ("Greek Yogurt", 170, 100, 17, 6, 0.7, "user"),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO foods
               (name, serving_size, calories, protein, carbs, fat, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            foods_rows,
        )

        today = date.today()
        meal_rows = []
        daily_meals = [
            ("Oats with Greek Yogurt", 250, 22, 33, 3.2),
            ("Chicken & Rice Bowl", 560, 45, 56, 8.5),
            ("Protein Shake", 180, 30, 8, 2.0),
            ("Salmon Dinner", 620, 42, 30, 28.0),
        ]
        for days_ago in range(7):
            meal_date = (today - timedelta(days=days_ago)).isoformat()
            for name, cal, pro, carbs, fat in daily_meals[: 3 + days_ago % 2]:
                meal_rows.append((meal_date, name, cal, pro, carbs, fat))
        conn.executemany(
            """INSERT INTO meals (date, name, calories, protein, carbs, fat)
               VALUES (?, ?, ?, ?, ?, ?)""",
            meal_rows,
        )
        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.environ.get("SEED_DEMO_DATA") == "1":
        seed_demo_data()
    yield


app = FastAPI(title="Macros Calculator API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meals.router)
app.include_router(foods.router)
app.include_router(analytics.router)
app.include_router(settings.router)
app.include_router(data.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
