import asyncio
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
# Importing the provider's errors is fine *here*: these tests exist to prove
# meal_ai.py translates them, so nothing else has to know they exist.
from google.genai import errors as genai_errors
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import AIAnalysis
from app.routers import ai as ai_router
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
async def fake_analyze(images, text, prior_analysis=None, **kwargs):
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

    async def capture(images, text, prior_analysis=None, **kwargs):
        captured.update(images=images, text=text, prior=prior_analysis, **kwargs)
        return SAMPLE

    configure(monkeypatch, capture)
    response = client.post(
        "/api/ai/analyze",
        data={"text": "I only ate half", "prior_analysis": SAMPLE.model_dump_json()},
        files={"image": ("meal.jpg", io.BytesIO(b"fake-jpeg-bytes"), "image/jpeg")},
    )
    assert response.status_code == 200
    # One `image` part still arrives as a one-item list: the field name did not
    # change when this grew to accept several, so a client written against the
    # single-image API keeps working.
    assert captured["images"] == [(b"fake-jpeg-bytes", "image/jpeg")]
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

    async def capture(images, text, prior_analysis=None, **kwargs):
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


class _RecordingUpload:
    """An UploadFile stand-in that reports what `read()` was asked for.

    The 413 alone cannot tell the fix from the bug -- reading the whole body and
    measuring it afterwards refuses the same upload with the same status. What
    changed is how much was held to reach that answer, and only the argument
    passed to read() shows it.
    """

    def __init__(self, size, content_type="image/jpeg"):
        self._data = b"x" * size
        self.content_type = content_type
        self.read_args = []

    async def read(self, size=-1):
        self.read_args.append(size)
        return self._data if size is None or size < 0 else self._data[:size]


def test_read_media_never_reads_more_than_the_limit_plus_one():
    """A 512 MB upload must not become 512 MB of memory before it is refused."""
    upload = _RecordingUpload(512 * 1024 * 1024)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            ai_router._read_media(
                upload, "image", ai_router.MAX_IMAGE_BYTES, "an image", "Image"
            )
        )

    assert excinfo.value.status_code == 413
    assert upload.read_args == [ai_router.MAX_IMAGE_BYTES + 1]


def test_read_media_returns_a_file_that_exactly_fills_the_limit():
    """The +1 is a probe, not a smaller budget: max_bytes itself still passes."""
    upload = _RecordingUpload(ai_router.MAX_IMAGE_BYTES)

    data, mime = asyncio.run(
        ai_router._read_media(
            upload, "image", ai_router.MAX_IMAGE_BYTES, "an image", "Image"
        )
    )

    assert len(data) == ai_router.MAX_IMAGE_BYTES
    assert mime == "image/jpeg"


def test_read_media_rejects_a_wrong_type_without_reading_it_at_all():
    """The cheapest refusal should also be the earliest one."""
    upload = _RecordingUpload(1024, content_type="text/plain")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            ai_router._read_media(
                upload, "image", ai_router.MAX_IMAGE_BYTES, "an image", "Image"
            )
        )

    assert excinfo.value.status_code == 415
    assert upload.read_args == []


def image_parts(count, size=16, mime="image/jpeg"):
    """`count` repeated `image` parts, as httpx wants them for a repeated field.

    A dict can only carry one value per key, so multi-image requests have to be
    built as a list of (field_name, file) pairs.
    """
    return [
        ("image", (f"meal{index}.jpg", io.BytesIO(b"x" * size), mime))
        for index in range(count)
    ]


def test_analyze_accepts_several_photos(client, monkeypatch):
    captured = {}

    async def capture(images, text, prior_analysis=None, **kwargs):
        captured["images"] = images
        return SAMPLE

    configure(monkeypatch, capture)
    response = client.post("/api/ai/analyze", files=image_parts(ai_router.MAX_IMAGES))
    assert response.status_code == 200, response.json()
    # All of them reach the provider, in the order they were sent.
    assert len(captured["images"]) == ai_router.MAX_IMAGES
    assert {mime for _, mime in captured["images"]} == {"image/jpeg"}


def test_analyze_rejects_more_photos_than_the_cap(client, monkeypatch):
    """The cap is what bounds the token bill: one call, but N images of input."""
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze", files=image_parts(ai_router.MAX_IMAGES + 1)
    )
    assert response.status_code == 422


def test_analyze_rejects_photos_oversized_in_total(client, monkeypatch):
    """Each photo can be under the per-image limit and still be too much together."""
    configure(monkeypatch)
    # Four 4 MB images: none hits MAX_IMAGE_BYTES (5 MB), together they pass
    # MAX_TOTAL_IMAGE_BYTES (12 MB).
    response = client.post(
        "/api/ai/analyze", files=image_parts(4, size=4 * 1024 * 1024)
    )
    assert response.status_code == 413


def test_analyze_ignores_an_empty_file_part(client, monkeypatch):
    """A form field submitted with no file chosen must not count as a photo.

    Otherwise the request looks like it carried an image, and a text-only
    analysis would be refused for having neither.
    """
    configure(monkeypatch)
    response = client.post(
        "/api/ai/analyze",
        data={"text": "chicken and rice"},
        files=[("image", ("", io.BytesIO(b""), "application/octet-stream"))],
    )
    assert response.status_code == 200, response.json()


def test_analyze_maps_provider_errors_to_502(client, monkeypatch):
    async def boom(images, text, prior_analysis=None, **kwargs):
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

    async def boom(images, text, prior_analysis=None, **kwargs):
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
    parts = _build_contents([], "grilled chicken", None)
    assert len(parts) == 1
    assert "grilled chicken" in parts[0]


def test_build_contents_defaults_to_photo_instruction():
    parts = _build_contents([(b"img", "image/png")], None, None)
    assert len(parts) == 2
    assert parts[1] == "Analyze the meal in the photo."


def test_build_contents_audio_only():
    parts = _build_contents([], None, None, b"audio", "audio/webm")
    assert len(parts) == 2
    assert parts[1] == "Analyze the meal described in the audio."


def test_build_contents_image_and_audio():
    parts = _build_contents([(b"img", "image/png")], None, None, b"audio", "audio/webm")
    assert len(parts) == 3
    assert parts[2] == "Analyze the meal in the photo, using the spoken description."


def test_build_contents_includes_prior_for_refinement():
    parts = _build_contents([], "I only ate half", SAMPLE)
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
    result = asyncio.run(meal_ai.analyze_meal([], "chicken and rice"))
    assert result is SAMPLE


def test_analyze_meal_falls_back_to_raw_json_text(monkeypatch):
    # Some SDK versions leave .parsed unset and only give raw JSON text.
    response = SimpleNamespace(parsed=None, text=SAMPLE.model_dump_json())
    _install_fake_provider(monkeypatch, response)
    result = asyncio.run(meal_ai.analyze_meal([], "chicken and rice"))
    assert result.meal_name == "Chicken & Rice"
    assert result.calories.estimate == 583


def test_analyze_meal_raises_on_empty_provider_response(monkeypatch):
    _install_fake_provider(monkeypatch, SimpleNamespace(parsed=None, text=None))
    with pytest.raises(meal_ai.MealAIBadResponse):
        asyncio.run(meal_ai.analyze_meal([], "chicken and rice"))


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
        asyncio.run(meal_ai.analyze_meal([], "chicken"))


def test_server_errors_map_to_unavailable(monkeypatch):
    _install_failing_provider(
        monkeypatch, genai_errors.ServerError(503, {"error": {"message": "down"}})
    )
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))


def test_unexpected_errors_map_to_internal_error(monkeypatch):
    """The residual bucket: not the provider refusing us, not the network.

    Kept distinct from MealAIUnavailable because "the SDK raised" and "Google is
    down" need different people, and reporting both as an outage is what made
    the last incident a guess.
    """
    _install_failing_provider(monkeypatch, RuntimeError("socket exploded"))
    with pytest.raises(meal_ai.MealAIInternalError):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("dns is having a day"),
        # Our own HttpOptions deadline expiring arrives as a TimeoutException,
        # which is a TransportError — so "we gave up" classifies as unreachable
        # rather than as Google being down.
        httpx.ReadTimeout("too slow"),
    ],
)
def test_transport_failures_map_to_unreachable(monkeypatch, exc):
    _install_failing_provider(monkeypatch, exc)
    with pytest.raises(meal_ai.MealAIUnreachable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))


# --- retry, fallback model, and the request deadline ------------------------


@pytest.fixture(autouse=True)
def virtual_clock(monkeypatch):
    """Sleeping advances a fake clock instead of real time.

    The retry loop is bounded by wall-clock deadline, not an attempt count, so a
    stubbed sleep that left the clock frozen would spin until the backoff
    overflowed. Advancing a virtual clock keeps the suite instant while
    exercising the real deadline arithmetic.
    """
    now = {"t": 0.0}
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        now["t"] += seconds

    monkeypatch.setattr(meal_ai.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(meal_ai, "_now", lambda: now["t"])
    return slept


def _install_scripted_provider(monkeypatch, outcomes):
    """A provider that yields `outcomes` in order: exceptions raise, values return.

    Faked at the same seam as every other provider test — the SDK boundary —
    so the retry logic is exercised without a network call.
    """
    calls = {"n": 0, "models": [], "configs": []}

    async def generate_content(**kwargs):
        calls["models"].append(kwargs.get("model"))
        calls["configs"].append(kwargs.get("config"))
        outcome = outcomes[min(calls["n"], len(outcomes) - 1)]
        calls["n"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        meal_ai.genai,
        "Client",
        lambda api_key=None: SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content)
            )
        ),
    )
    return calls


def _server_error():
    return genai_errors.ServerError(503, {"error": {"message": "overloaded"}})


def test_a_server_error_is_retried_and_then_succeeds(monkeypatch):
    """The failure that took the app down: Gemini 503, cleared on the retry."""
    calls = _install_scripted_provider(
        monkeypatch, [_server_error(), SimpleNamespace(parsed=SAMPLE, text=None)]
    )
    result = asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert result is SAMPLE
    assert calls["n"] == 2


def test_the_second_attempt_uses_the_other_serving_pool(monkeypatch):
    """Overload is per pool, so alternate rather than exhausting the primary.

    Reaching the fallback on attempt two is the whole point: spending half the
    budget on a pool that is already refusing us is what the manual workaround
    (switching MEAL_AI_MODEL by hand) was compensating for.
    """
    monkeypatch.setenv("MEAL_AI_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", "gemini-2.5-flash")
    calls = _install_scripted_provider(
        monkeypatch, [_server_error(), SimpleNamespace(parsed=SAMPLE, text=None)]
    )
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["models"] == ["gemini-3.5-flash", "gemini-2.5-flash"]


def test_a_sustained_outage_keeps_trying_for_the_whole_budget(
    monkeypatch, virtual_clock
):
    """The failure this redesign exists for: many tries spread over a minute.

    A fixed attempt count gave up ~1.5s in, with 98% of the budget unused —
    indistinguishable from no retry at all when a user is pressing the button
    for a minute and eventually getting through.
    """
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    # Exact count depends on jitter; the guarantee is "many, across the budget".
    assert calls["n"] >= 8
    # And it stops at the budget rather than retrying forever.
    assert sum(virtual_clock) <= meal_ai.ANALYZE_DEADLINE_S


def test_an_empty_fallback_model_keeps_everything_on_one_pool(monkeypatch):
    monkeypatch.setenv("MEAL_AI_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", "")
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert set(calls["models"]) == {"gemini-3.5-flash"}


def test_the_fallback_is_deduped_against_the_primary(monkeypatch):
    """Same id in both slots must not silently double the worst-case latency."""
    monkeypatch.setenv("MEAL_AI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", "gemini-2.5-flash")
    assert meal_ai._models() == ["gemini-2.5-flash"]


@pytest.mark.parametrize(
    "exc",
    [
        # Already sending too much: two more requests inside the same 60s window
        # make the thing we're being limited for worse.
        genai_errors.ClientError(429, {"error": {"message": "slow down"}}),
        # A rejected key or retired model id fails identically every time.
        genai_errors.ClientError(400, {"error": {"message": "bad key"}}),
        # A drifted dependency raises the same TypeError every time.
        RuntimeError("boom"),
    ],
)
def test_failures_a_retry_cannot_fix_are_not_retried(monkeypatch, exc):
    calls = _install_scripted_provider(monkeypatch, [exc])
    with pytest.raises(meal_ai.MealAIError):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 1


def test_an_unusable_response_is_not_retried(monkeypatch):
    """It arrived and burned tokens; asking again bills twice for the same garbage."""
    calls = _install_scripted_provider(
        monkeypatch, [SimpleNamespace(parsed=None, text=None)]
    )
    with pytest.raises(meal_ai.MealAIBadResponse):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 1


def test_backoff_grows_but_is_capped_and_jittered(monkeypatch, virtual_clock):
    """Growth stops at a ceiling: an unbounded double would sleep through the
    back half of the budget, when a flapping provider needs frequent sampling."""
    _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    for i, delay in enumerate(virtual_clock):
        ceiling = min(meal_ai.RETRY_BASE_DELAY * 2**i, meal_ai.RETRY_MAX_DELAY)
        # Jitter only ever shortens, so the ceiling is a hard upper bound.
        assert ceiling / 2 <= delay <= ceiling
    assert max(virtual_clock) <= meal_ai.RETRY_MAX_DELAY
    # Jitter must actually vary, or concurrent users retry in lockstep.
    assert len(set(virtual_clock)) > 1


def test_the_deadline_is_overridable_from_the_dashboard(monkeypatch):
    """The knob you want mid-outage is "keep trying longer", without a build."""
    monkeypatch.setenv("MEAL_AI_DEADLINE_S", "0.1")
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 1


def test_transcription_gets_a_shorter_budget_than_analysis(monkeypatch):
    """A voice note is the first step of a flow; nobody waits a minute to type."""
    analyze = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    transcribe = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.transcribe_audio(b"audio", "audio/webm"))

    assert transcribe["n"] < analyze["n"]


@pytest.mark.parametrize(
    "call,expected_ms",
    [
        (lambda: meal_ai.analyze_meal([], "chicken"), meal_ai.ANALYZE_TIMEOUT_MS),
        (lambda: meal_ai.transcribe_audio(b"audio", "audio/webm"), meal_ai.TRANSCRIBE_TIMEOUT_MS),
    ],
)
def test_every_provider_call_carries_a_request_deadline(monkeypatch, call, expected_ms):
    """Guards the unit: HttpOptions.timeout is MILLISECONDS, not seconds.

    Without a timeout the SDK inherits httpx's default of none at all, so a
    connection Google accepts and never answers pins a worker until the platform
    kills it.
    """
    calls = _install_scripted_provider(
        monkeypatch, [SimpleNamespace(parsed=SAMPLE, text="a transcript")]
    )
    asyncio.run(call())
    assert calls["configs"][0].http_options.timeout == expected_ms


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

    async def capture(images, text, prior_analysis=None, **kwargs):
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


# --- GET /api/ai/status: answers "is the AI down, and why" in one request ---
# /api/health returned 200 in under a second throughout both real outages.


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    """Module-level cache outlives a test, so reset it like conftest does limiter."""
    ai_router._probe_cache = None
    yield
    ai_router._probe_cache = None


def configure_probe(monkeypatch, outcome=None):
    """Point meal_ai.probe at a scripted result; `outcome` raises if an Exception."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def fake_probe():
        if isinstance(outcome, Exception):
            raise outcome
        return "gemini-3.5-flash"

    monkeypatch.setattr(meal_ai, "probe", fake_probe)


def test_status_reports_the_model_chain_and_sdk_version(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("MEAL_AI_MODEL", "gemini-x")
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", "gemini-y")

    body = client.get("/api/ai/status").json()
    assert body["configured"] is True
    assert body["model"] == "gemini-x"
    assert body["fallback_model"] == "gemini-y"
    assert body["sdk_version"]


def test_status_without_probe_never_touches_the_provider(client, monkeypatch):
    """The free form has to stay free, or nobody can afford to poll it."""

    async def explode():
        raise AssertionError("the un-probed form must not call the provider")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(meal_ai, "probe", explode)

    body = client.get("/api/ai/status").json()
    assert body["probe"] is None
    with Session(get_engine()) as db:
        assert db.query(AIAnalysis).count() == 0


def test_status_probe_reports_ok(client, monkeypatch):
    configure_probe(monkeypatch)
    probe = client.get("/api/ai/status?probe=true").json()["probe"]
    assert probe["status"] == "ok"
    assert isinstance(probe["latency_ms"], int)


@pytest.mark.parametrize(
    "exc,expected",
    [
        # The outage this endpoint was built during.
        (meal_ai.MealAIUnavailable("503 overloaded"), "upstream_5xx"),
        (meal_ai.MealAIUnreachable("ConnectError: dns"), "unreachable"),
        (meal_ai.MealAIInternalError("TypeError: drift"), "internal_error"),
        (meal_ai.MealAIRateLimited("429"), "rate_limited"),
        (meal_ai.MealAIBadRequest("bad key"), "rejected"),
    ],
)
def test_status_probe_classifies_each_failure(client, monkeypatch, exc, expected):
    configure_probe(monkeypatch, exc)
    assert client.get("/api/ai/status?probe=true").json()["probe"]["status"] == expected


def test_status_probe_hides_provider_text_by_default(client, monkeypatch):
    """Signup is open, so "authenticated" is a weak gate on Google's own words."""
    configure_probe(monkeypatch, meal_ai.MealAIBadRequest("API key not valid"))
    assert client.get("/api/ai/status?probe=true").json()["probe"]["message"] is None


def test_status_probe_reveals_provider_text_when_enabled(client, monkeypatch):
    configure_probe(monkeypatch, meal_ai.MealAIBadRequest("API key not valid"))
    monkeypatch.setenv("MEAL_AI_STATUS_DETAIL", "1")
    message = client.get("/api/ai/status?probe=true").json()["probe"]["message"]
    assert "API key not valid" in message


def test_status_probe_is_cached_so_it_cannot_drain_the_quota(client, monkeypatch):
    calls = {"n": 0}

    async def counting_probe():
        calls["n"] += 1
        return "gemini-3.5-flash"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(meal_ai, "probe", counting_probe)

    assert client.get("/api/ai/status?probe=true").json()["probe"]["cached"] is False
    second = client.get("/api/ai/status?probe=true").json()["probe"]
    assert second["cached"] is True
    assert isinstance(second["age_seconds"], int)
    assert calls["n"] == 1


def test_status_probe_counts_against_the_global_cap(client, monkeypatch):
    """A probe really does spend the shared quota; exempting it would be a lie."""
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "1")
    configure_probe(monkeypatch)
    configure(monkeypatch)

    assert client.get("/api/ai/status?probe=true").json()["probe"]["status"] == "ok"
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 503


def test_status_probe_does_not_spend_the_analysis_allowance(client, monkeypatch):
    """Its own kind, so diagnosing an outage doesn't cost the user their meals."""
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")
    configure_probe(monkeypatch)
    configure(monkeypatch)

    assert client.get("/api/ai/status?probe=true").json()["probe"]["status"] == "ok"
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200


def test_status_probe_reports_its_own_cap_instead_of_failing(client, monkeypatch):
    """A diagnostic that 429s is useless during the incident it was built for."""
    monkeypatch.setenv("AI_PROBE_DAILY_LIMIT", "1")
    configure_probe(monkeypatch)

    assert client.get("/api/ai/status?probe=true").json()["probe"]["status"] == "ok"
    ai_router._probe_cache = None  # force a second real reservation attempt
    response = client.get("/api/ai/status?probe=true")
    assert response.status_code == 200
    assert response.json()["probe"]["status"] == "quota_exhausted"


def test_status_probe_when_the_key_is_missing(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    body = client.get("/api/ai/status?probe=true").json()
    assert body["configured"] is False
    assert body["probe"]["status"] == "not_configured"


# --- Env-var limit parsing -------------------------------------------------
# These call the readers directly rather than through a request: the bug is in
# reading the value, and a full analyze round-trip would only add ways for the
# test to fail for unrelated reasons.

def test_env_limit_falls_back_when_the_value_is_unreadable(monkeypatch):
    """A typo in the Render dashboard used to 500 every AI call.

    The readers run inside the request handler, so int("2O") raised there rather
    than at import — the app booted fine and then refused every analysis with a
    500, including the admin usage page that reads the global limit.
    """
    for bad in ("2O", "abc", "20 30", "twenty", "1.5", "²"):
        monkeypatch.setenv("AI_DAILY_LIMIT", bad)
        assert ai_router._daily_limit() == ai_router.DEFAULT_DAILY_LIMIT, bad


def test_env_limit_falls_back_when_unset_or_empty(monkeypatch):
    """An env var set to "" is how a dashboard records "I cleared this"."""
    monkeypatch.delenv("AI_GLOBAL_DAILY_LIMIT", raising=False)
    assert ai_router.global_daily_limit() == ai_router.DEFAULT_GLOBAL_DAILY_LIMIT

    for blank in ("", "   "):
        monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", blank)
        assert ai_router.global_daily_limit() == ai_router.DEFAULT_GLOBAL_DAILY_LIMIT


def test_env_limit_honours_a_deliberate_zero(monkeypatch):
    """Zero is a kill switch, not a mistake.

    Falling back to the shipped 500 here would turn "AI off" into "AI on" —
    the exact opposite of what the operator asked for, at their expense.
    """
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "0")
    assert ai_router.global_daily_limit() == 0


def test_env_limit_clamps_a_negative_to_zero(monkeypatch):
    """A negative was already blocking every call, since the test is `>=`.

    So it must not fall back to the default: that would take a value which was
    holding the gate shut and quietly open it.
    """
    monkeypatch.setenv("AI_DAILY_LIMIT", "-1")
    assert ai_router._daily_limit() == 0


def test_env_limit_reads_a_valid_value(monkeypatch):
    for name, reader in (
        ("AI_DAILY_LIMIT", ai_router._daily_limit),
        ("AI_TRANSCRIBE_DAILY_LIMIT", ai_router._transcribe_daily_limit),
        ("AI_GLOBAL_DAILY_LIMIT", ai_router.global_daily_limit),
        ("AI_PROBE_DAILY_LIMIT", ai_router._probe_daily_limit),
    ):
        monkeypatch.setenv(name, "7")
        assert reader() == 7, name
        # Surrounding whitespace is a dashboard copy-paste artefact, not a typo.
        monkeypatch.setenv(name, " 7 ")
        assert reader() == 7, name
