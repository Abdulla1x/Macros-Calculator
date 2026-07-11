import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import AIAnalysis
from app.schemas import AnalyzedItem, MacroRange, MealAnalysis
from app.services import meal_ai
from app.services.meal_ai import _build_contents

SAMPLE = MealAnalysis(
    meal_name="Chicken & Rice",
    items=[
        AnalyzedItem(
            name="Chicken Breast", portion_grams=180, calories=297,
            protein=55.8, carbs=0, fat=6.5, confidence="high",
        ),
        AnalyzedItem(
            name="White Rice (cooked)", portion_grams=220, calories=286,
            protein=5.9, carbs=61.6, fat=0.7, confidence="medium",
        ),
    ],
    assumptions=["grilled, no added oil", "rice portion ~220 g"],
    calories=MacroRange(low=500, estimate=583, high=680),
    protein=MacroRange(low=55, estimate=62, high=68),
    carbs=MacroRange(low=52, estimate=62, high=72),
    fat=MacroRange(low=5, estimate=7, high=12),
    confidence="medium",
    explanation="Confident about the chicken; the rice portion is approximate.",
)


async def fake_analyze(image_bytes, image_mime, text, prior_analysis=None):
    return SAMPLE


def configure(monkeypatch, fake=fake_analyze):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(meal_ai, "analyze_meal", fake)


def test_analyze_requires_photo_or_text(client, monkeypatch):
    configure(monkeypatch)
    response = client.post("/api/ai/analyze", data={"text": "   "})
    assert response.status_code == 422


def test_analyze_returns_503_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/api/ai/analyze", data={"text": "chicken and rice"})
    assert response.status_code == 503


def test_analyze_success_returns_analysis_and_persists(client, monkeypatch):
    configure(monkeypatch)
    response = client.post("/api/ai/analyze", data={"text": "chicken and rice"})
    assert response.status_code == 200
    body = response.json()
    assert body["meal_name"] == "Chicken & Rice"
    assert body["calories"]["estimate"] == 583
    assert len(body["items"]) == 2
    assert isinstance(body["analysis_id"], int)

    with Session(get_engine()) as session:
        row = session.get(AIAnalysis, body["analysis_id"])
        assert row.user_text == "chicken and rice"
        assert json.loads(row.analysis_json)["meal_name"] == "Chicken & Rice"
        assert row.meal_id is None


def test_analyze_passes_image_and_prior_to_service(client, monkeypatch):
    captured = {}

    async def capture(image_bytes, image_mime, text, prior_analysis=None):
        captured.update(
            image_bytes=image_bytes, image_mime=image_mime,
            text=text, prior=prior_analysis,
        )
        return SAMPLE

    configure(monkeypatch, capture)
    response = client.post(
        "/api/ai/analyze",
        data={"text": "I only ate half", "prior_analysis": SAMPLE.model_dump_json()},
        files={"image": ("meal.jpg", io.BytesIO(b"fake-jpeg-bytes"), "image/jpeg")},
    )
    assert response.status_code == 200
    assert captured["image_bytes"] == b"fake-jpeg-bytes"
    assert captured["image_mime"] == "image/jpeg"
    assert captured["text"] == "I only ate half"
    assert captured["prior"].meal_name == "Chicken & Rice"


def test_analyze_rejects_invalid_prior(client, monkeypatch):
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze", data={"text": "pizza", "prior_analysis": "not json"}
    )
    assert response.status_code == 422


def test_analyze_rejects_non_image_upload(client, monkeypatch):
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze",
        files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415


def test_analyze_rejects_oversized_image(client, monkeypatch):
    configure(monkeypatch)
    big = io.BytesIO(b"x" * (5 * 1024 * 1024 + 1))
    response = client.post(
        "/api/ai/analyze", files={"image": ("meal.jpg", big, "image/jpeg")}
    )
    assert response.status_code == 413


def test_analyze_maps_provider_errors_to_502(client, monkeypatch):
    async def boom(image_bytes, image_mime, text, prior_analysis=None):
        raise RuntimeError("provider down")

    configure(monkeypatch, boom)
    response = client.post("/api/ai/analyze", data={"text": "pizza"})
    assert response.status_code == 502


def test_analyze_rejects_overlong_text(client, monkeypatch):
    configure(monkeypatch)
    response = client.post("/api/ai/analyze", data={"text": "x" * 2_001})
    assert response.status_code == 422


def test_provider_failure_refunds_the_quota_slot(client, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")

    async def boom(image_bytes, image_mime, text, prior_analysis=None):
        raise RuntimeError("provider down")

    configure(monkeypatch, boom)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 502

    # The failed call must not count against the daily limit...
    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200
    # ...but the successful one does.
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 429


def test_link_analysis_sets_meal_id(client, monkeypatch):
    configure(monkeypatch)
    analysis_id = client.post(
        "/api/ai/analyze", data={"text": "pizza"}
    ).json()["analysis_id"]

    meal = client.post(
        "/api/meals",
        json={"date": "2026-07-06", "name": "Pizza", "calories": 740, "protein": 31},
    ).json()

    response = client.patch(
        f"/api/ai/analyses/{analysis_id}", json={"meal_id": meal["id"]}
    )
    assert response.status_code == 204

    with Session(get_engine()) as session:
        row = session.get(AIAnalysis, analysis_id)
        assert row.meal_id == meal["id"]


def test_link_analysis_404_for_unknown_id(client):
    response = client.patch("/api/ai/analyses/9999", json={"meal_id": 1})
    assert response.status_code == 404


def test_build_contents_text_only():
    parts = _build_contents(None, None, "grilled chicken", None)
    assert len(parts) == 1
    assert "grilled chicken" in parts[0]


def test_build_contents_defaults_to_photo_instruction():
    parts = _build_contents(b"img", "image/png", None, None)
    assert len(parts) == 2
    assert parts[1] == "Analyze the meal in the photo."


def test_build_contents_includes_prior_for_refinement():
    parts = _build_contents(None, None, "I only ate half", SAMPLE)
    assert "Previous analysis to refine" in parts[0]
    assert "I only ate half" in parts[0]


# --- analyze_meal's response handling (fake genai client, no network) -------

def _install_fake_provider(monkeypatch, response):
    async def generate_content(**_kwargs):
        return response

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr(meal_ai.genai, "Client", lambda api_key=None: fake_client)


def test_analyze_meal_uses_sdk_parsed_object(monkeypatch):
    _install_fake_provider(monkeypatch, SimpleNamespace(parsed=SAMPLE, text=None))
    result = asyncio.run(meal_ai.analyze_meal(None, None, "chicken and rice"))
    assert result is SAMPLE


def test_analyze_meal_falls_back_to_raw_json_text(monkeypatch):
    # Some SDK versions leave .parsed unset and only give raw JSON text.
    response = SimpleNamespace(parsed=None, text=SAMPLE.model_dump_json())
    _install_fake_provider(monkeypatch, response)
    result = asyncio.run(meal_ai.analyze_meal(None, None, "chicken and rice"))
    assert result.meal_name == "Chicken & Rice"
    assert result.calories.estimate == 583


def test_analyze_meal_raises_on_empty_provider_response(monkeypatch):
    _install_fake_provider(monkeypatch, SimpleNamespace(parsed=None, text=None))
    with pytest.raises(ValidationError):
        asyncio.run(meal_ai.analyze_meal(None, None, "chicken and rice"))
