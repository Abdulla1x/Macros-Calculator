import asyncio
import io
import json
from types import SimpleNamespace

import pytest
# Importing the provider's errors is fine *here*: these tests exist to prove
# meal_ai.py translates them, so nothing else has to know they exist.
from google.genai import errors as genai_errors
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


# **kwargs absorbs audio_bytes/audio_mime, which the router passes by keyword.
async def fake_analyze(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
    return SAMPLE


def configure(monkeypatch, fake=fake_analyze):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(meal_ai, "analyze_meal", fake)


async def fake_transcribe(audio_bytes, audio_mime):
    return "I had a hundred grams of broasted chicken thighs"


def configure_transcribe(monkeypatch, fake=fake_transcribe):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(meal_ai, "transcribe_audio", fake)


def post_voice_note(client, data=b"fake-audio", mime="audio/webm"):
    return client.post(
        "/api/ai/transcribe",
        files={"audio": ("note.webm", io.BytesIO(data), mime)},
    )


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

    async def capture(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
        captured.update(
            image_bytes=image_bytes, image_mime=image_mime,
            text=text, prior=prior_analysis, **kwargs,
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


def test_analyze_accepts_audio_only(client, monkeypatch):
    """A voice note with no photo and no typed text is a complete request."""
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze",
        files={"audio": ("note.webm", io.BytesIO(b"fake-audio"), "audio/webm")},
    )
    assert response.status_code == 200


def test_analyze_passes_audio_to_service(client, monkeypatch):
    captured = {}

    async def capture(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
        captured.update(kwargs)
        return SAMPLE

    configure(monkeypatch, capture)
    response = client.post(
        "/api/ai/analyze",
        files={"audio": ("note.webm", io.BytesIO(b"fake-audio"), "audio/webm")},
    )
    assert response.status_code == 200
    assert captured["audio_bytes"] == b"fake-audio"
    assert captured["audio_mime"] == "audio/webm"


def test_analyze_rejects_parameterized_non_audio_upload(client, monkeypatch):
    """Browsers send parameterized types; the 415 must still catch them."""
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze",
        files={"audio": ("notes.txt", io.BytesIO(b"hello"), "text/plain;charset=utf-8")},
    )
    assert response.status_code == 415


def test_analyze_rejects_non_audio_upload(client, monkeypatch):
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze",
        files={"audio": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415


def test_analyze_rejects_oversized_audio(client, monkeypatch):
    configure(monkeypatch)
    big = io.BytesIO(b"x" * (10 * 1024 * 1024 + 1))
    response = client.post(
        "/api/ai/analyze", files={"audio": ("note.webm", big, "audio/webm")}
    )
    assert response.status_code == 413


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
    async def boom(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
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

    async def boom(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
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


def test_build_contents_audio_only():
    parts = _build_contents(None, None, None, None, b"audio", "audio/webm")
    assert len(parts) == 2
    assert parts[1] == "Analyze the meal described in the audio."


def test_build_contents_image_and_audio():
    parts = _build_contents(b"img", "image/png", None, None, b"audio", "audio/webm")
    assert len(parts) == 3
    assert parts[2] == "Analyze the meal in the photo, using the spoken description."


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
    with pytest.raises(meal_ai.MealAIBadResponse):
        asyncio.run(meal_ai.analyze_meal(None, None, "chicken and rice"))


# --- provider errors are translated to the neutral MealAIError hierarchy ----
# The router must never see a google.genai symbol; meal_ai.py owns that mapping.

def _install_failing_provider(monkeypatch, exc):
    async def generate_content(**_kwargs):
        raise exc

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr(meal_ai.genai, "Client", lambda api_key=None: fake_client)


@pytest.mark.parametrize(
    "code,expected",
    [
        (429, meal_ai.MealAIRateLimited),
        # A retired model id lands here — the failure that took the app down.
        (400, meal_ai.MealAIBadRequest),
        (404, meal_ai.MealAIBadRequest),
    ],
)
def test_client_errors_map_to_neutral_exceptions(monkeypatch, code, expected):
    _install_failing_provider(
        monkeypatch, genai_errors.ClientError(code, {"error": {"message": "nope"}})
    )
    with pytest.raises(expected):
        asyncio.run(meal_ai.analyze_meal(None, None, "chicken"))


def test_server_errors_map_to_unavailable(monkeypatch):
    _install_failing_provider(
        monkeypatch, genai_errors.ServerError(503, {"error": {"message": "down"}})
    )
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal(None, None, "chicken"))


def test_unexpected_errors_map_to_unavailable(monkeypatch):
    _install_failing_provider(monkeypatch, RuntimeError("socket exploded"))
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal(None, None, "chicken"))


# --- the router turns those into distinguishable statuses, refunding quota ---

@pytest.mark.parametrize(
    "exc,status",
    [
        (meal_ai.MealAIRateLimited("busy"), 429),
        (meal_ai.MealAIUnavailable("down"), 503),
        (meal_ai.MealAIBadRequest("retired model"), 502),
    ],
)
def test_failures_before_inference_refund_the_quota_slot(
    client, monkeypatch, exc, status
):
    """Provider refused or was unreachable: nothing billed, so nothing spent."""
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")

    async def boom(*_args, **_kwargs):
        raise exc

    configure(monkeypatch, boom)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == status

    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200


def test_unusable_output_still_spends_the_quota_slot(client, monkeypatch):
    """The model ran and burned tokens; only its output was unusable.

    Refunding here would make input that reliably produces garbage an uncapped
    free path to the provider, which is the one failure mode the daily caps
    exist to prevent.
    """
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")

    async def boom(*_args, **_kwargs):
        raise meal_ai.MealAIBadResponse("garbage")

    configure(monkeypatch, boom)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 502

    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 429


# --- /api/ai/transcribe: a voice note becomes editable text before analysis ---

def test_transcribe_returns_text(client, monkeypatch):
    configure_transcribe(monkeypatch)
    response = post_voice_note(client)
    assert response.status_code == 200
    assert response.json() == {
        "transcript": "I had a hundred grams of broasted chicken thighs"
    }


def test_transcribe_requires_audio(client, monkeypatch):
    configure_transcribe(monkeypatch)
    assert client.post("/api/ai/transcribe").status_code == 422


def test_transcribe_returns_503_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert post_voice_note(client).status_code == 503


def test_transcribe_rejects_non_audio_upload(client, monkeypatch):
    configure_transcribe(monkeypatch)
    assert post_voice_note(client, mime="text/plain").status_code == 415


def test_transcribe_rejects_oversized_audio(client, monkeypatch):
    configure_transcribe(monkeypatch)
    assert post_voice_note(client, data=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_transcribe_persists_what_was_heard(client, monkeypatch):
    configure_transcribe(monkeypatch)
    assert post_voice_note(client).status_code == 200
    with Session(get_engine()) as db:
        record = db.query(AIAnalysis).filter_by(kind="transcription").one()
        assert record.user_text == "I had a hundred grams of broasted chicken thighs"
        assert record.analysis_json == ""


def test_silent_recording_is_a_422_and_still_spends_the_slot(client, monkeypatch):
    """The model listened either way, so silence-on-a-loop isn't free."""
    monkeypatch.setenv("AI_TRANSCRIBE_DAILY_LIMIT", "1")

    async def no_speech(*_args, **_kwargs):
        raise meal_ai.MealAIBadResponse("nothing heard")

    configure_transcribe(monkeypatch, no_speech)
    assert post_voice_note(client).status_code == 422

    configure_transcribe(monkeypatch)
    assert post_voice_note(client).status_code == 429


def test_transcribe_refunds_the_slot_when_the_provider_is_down(client, monkeypatch):
    monkeypatch.setenv("AI_TRANSCRIBE_DAILY_LIMIT", "1")

    async def down(*_args, **_kwargs):
        raise meal_ai.MealAIUnavailable("down")

    configure_transcribe(monkeypatch, down)
    assert post_voice_note(client).status_code == 503

    configure_transcribe(monkeypatch)
    assert post_voice_note(client).status_code == 200


def test_transcriptions_have_their_own_daily_allowance(client, monkeypatch):
    """Speaking a meal shouldn't cost an analysis; the budgets are separate."""
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")
    monkeypatch.setenv("AI_TRANSCRIBE_DAILY_LIMIT", "1")
    configure(monkeypatch)
    configure_transcribe(monkeypatch)

    assert post_voice_note(client).status_code == 200
    # The transcription used its own budget, so the analysis is still available.
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200
    # ...and each is now independently exhausted.
    assert post_voice_note(client).status_code == 429
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 429


# --- the browser's mime reaches the provider untouched ----------------------
# MediaRecorder labels its output `audio/webm;codecs=opus` and Gemini accepts
# it -- that exact form is what works in production. These lock that in: a
# future "normalization" that strips the codecs parameter would substitute a
# value never tested against the live provider.

def test_analyze_forwards_the_browser_mime_unchanged(client, monkeypatch):
    captured = {}

    async def capture(image_bytes, image_mime, text, prior_analysis=None, **kwargs):
        captured.update(kwargs)
        return SAMPLE

    configure(monkeypatch, capture)
    response = client.post(
        "/api/ai/analyze",
        files={"audio": ("note.webm", io.BytesIO(b"fake-audio"), "audio/webm;codecs=opus")},
    )
    assert response.status_code == 200
    assert captured["audio_mime"] == "audio/webm;codecs=opus"


def test_transcribe_forwards_the_browser_mime_unchanged(client, monkeypatch):
    captured = {}

    async def capture(audio_bytes, audio_mime):
        captured["audio_mime"] = audio_mime
        return "two eggs on toast"

    configure_transcribe(monkeypatch, capture)
    assert post_voice_note(client, mime="audio/webm;codecs=opus").status_code == 200
    assert captured["audio_mime"] == "audio/webm;codecs=opus"


# --- the global cap: what bounds spend when per-user limits aren't enough ---

def test_global_cap_rejects_once_the_shared_budget_is_gone(client, monkeypatch):
    """Per-user limits bound one account; this bounds the whole app.

    Without it, signing up repeatedly multiplies the per-user allowance without
    limit — the free tier's quota drains, or a paid key runs up a bill.
    """
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "2")
    configure(monkeypatch)

    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200

    response = client.post("/api/ai/analyze", data={"text": "pizza"})
    assert response.status_code == 503
    assert "shared daily AI quota" in response.json()["detail"]


def test_global_cap_counts_transcriptions_too(client, monkeypatch):
    """Both endpoints hit the same provider, so both draw on the same ceiling."""
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "1")
    configure(monkeypatch)
    configure_transcribe(monkeypatch)

    assert post_voice_note(client).status_code == 200
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 503


def test_global_cap_does_not_fire_below_the_limit(client, monkeypatch):
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "500")
    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200
