import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .auth import router as auth_router
from .auth.security import get_jwt_secret
from .db import get_engine
from .models import Base
from .rate_limit import limiter
from .routers import ai, analytics, data, foods, meals, settings

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_jwt_secret()  # fail fast in production if JWT_SECRET is missing
    # SQLite (dev/tests) gets its schema from the models directly; Postgres
    # schema is owned by Alembic (`alembic upgrade head` in the start command).
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Macros Calculator API", version="3.0.0", lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # A `detail` body so the frontend surfaces this like any other API error.
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait a minute and try again."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(meals.router)
app.include_router(foods.router)
app.include_router(analytics.router)
app.include_router(settings.router)
app.include_router(data.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
