import logging
import math
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .auth import router as auth_router
from .auth.security import get_jwt_secret, token_lifetime
from .db import get_engine
from .models import Base
from .rate_limit import limiter
from .routers import (
    admin,
    ai,
    analytics,
    announcements,
    data,
    foods,
    meal_templates,
    meals,
    settings,
    steps,
    supplements,
    water,
    weights,
)

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

# Without this the root logger has no handler under uvicorn, and app logs fall
# through to logging's unformatted lastResort stream. Provider failures in
# services/meal_ai.py are only diagnosable if they actually reach the logs.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_jwt_secret()  # fail fast in production if JWT_SECRET is missing
    # Read the token lifetime once at boot so a bad ACCESS_TOKEN_DAYS logs its
    # warning here, next to the deploy that introduced it, rather than on some
    # user's login hours later. Deliberately not fatal, unlike JWT_SECRET above:
    # that has no safe default, this one has a good one, and refusing to serve
    # anything over a mistyped token lifetime is a worse outage than the bug.
    token_lifetime()
    # SQLite (dev/tests) gets its schema from the models directly; Postgres
    # schema is owned by Alembic (`alembic upgrade head` in the start command).
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Macros Calculator API", version="3.0.0", lifespan=lifespan)

app.state.limiter = limiter


def _json_safe(value):
    """Replace values that are valid Python floats but not valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 body echoes the rejected value back under `input`.

    That is fine until the rejected value is exactly what JSON cannot express.
    `json.loads` accepts the bare token `Infinity`, so a hand-written request
    can put inf into a field; Pydantic then rejects it correctly (see
    TemplateItem's allow_inf_nan), and rendering the rejection crashes, because
    Starlette's JSONResponse serializes with allow_nan=False. The caller gets a
    500 for a request the server had already understood and refused.

    Sanitizing the echo keeps the 422. The frontend is unaffected either way --
    api/client.ts only reads `detail` when it is a string.
    """
    return JSONResponse(
        status_code=422, content={"detail": _json_safe(jsonable_encoder(exc.errors()))}
    )


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # A `detail` body so the frontend surfaces this like any other API error.
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait a minute and try again."},
    )


app.add_middleware(
    CORSMiddleware,
    # strip() tolerates "a, b" spacing in the env var; a stray space would
    # otherwise silently break origin matching. Auth is Bearer-header based,
    # not cookies, so allow_credentials stays off.
    allow_origins=[
        origin.strip()
        for origin in (os.environ.get("CORS_ORIGINS") or DEFAULT_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(meals.router)
app.include_router(meal_templates.router)
app.include_router(foods.router)
app.include_router(weights.router)
app.include_router(analytics.router)
app.include_router(settings.router)
app.include_router(data.router)
app.include_router(ai.router)
app.include_router(water.router)
app.include_router(steps.router)
app.include_router(supplements.router)
app.include_router(announcements.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
