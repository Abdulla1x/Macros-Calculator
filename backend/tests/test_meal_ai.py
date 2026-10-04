import asyncio
import gc
import io
import json
import weakref
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
# Importing the provider's errors is fine *here*: these tests exist to prove
# meal_ai.py translates them, so nothing else has to know they exist.
from google.genai import errors as genai_errors
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import AIAnalysis
from app.routers import ai as ai_router
from app.schemas import AnalyzedItem, Food, MacroRange, MealAnalysis
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


def test_analyze_logs_how_many_photo_bytes_arrived(client, monkeypatch, caplog):
    """The prod check that photos arrive shrunk: count and total bytes per call."""
    configure(monkeypatch)
    with caplog.at_level("INFO", logger="app.routers.ai"):
        response = client.post(
            "/api/ai/analyze", files=image_parts(2, size=300_000)
        )
    assert response.status_code == 200, response.json()
    assert "analysis input: images=2 image_bytes=600000" in caplog.text


def test_analyze_logs_no_photo_line_for_a_text_only_call(client, monkeypatch, caplog):
    configure(monkeypatch)
    with caplog.at_level("INFO", logger="app.routers.ai"):
        response = client.post("/api/ai/analyze", data={"text": "rice"})
    assert response.status_code == 200, response.json()
    assert "analysis input" not in caplog.text


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


# --- attaching saved foods to an analysis ------------------------------------

FOOD = {
    "name": "Chicken breast, raw", "serving_size": 100,
    "calories": 165, "protein": 31, "carbs": 0, "fat": 3.6,
}


def _capture(monkeypatch):
    """Configure the AI with a fake that records what the router handed it."""
    seen: dict = {}

    async def fake(images, text, prior_analysis=None, **kwargs):
        seen.update(kwargs, images=images, text=text)
        return SAMPLE

    configure(monkeypatch, fake)
    return seen


def _analysis_count() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(AIAnalysis))


def test_analyze_hands_the_provider_the_stored_macros(client, monkeypatch):
    """The client sends ids; the numbers are read from the caller's own library.

    Asserting the *values* rather than just the count is the point: a request
    cannot claim a food has different macros than the row it names.
    """
    seen = _capture(monkeypatch)
    food = client.post("/api/foods", json=FOOD).json()

    response = client.post(
        "/api/ai/analyze", data={"text": "lunch", "food_id": [food["id"]]}
    )

    assert response.status_code == 200
    attached = seen["library_foods"]
    assert [f.name for f in attached] == ["Chicken breast, raw"]
    assert (attached[0].calories, attached[0].protein) == (165, 31)


def test_analyze_dedupes_repeated_ids(client, monkeypatch):
    seen = _capture(monkeypatch)
    food = client.post("/api/foods", json=FOOD).json()
    food_id = food["id"]

    client.post(
        "/api/ai/analyze", data={"text": "lunch", "food_id": [food_id, food_id]}
    )

    # One fact, not two -- a duplicate would be billed again on every retry.
    assert len(seen["library_foods"]) == 1


def test_analyze_without_attachments_sends_none(client, monkeypatch):
    seen = _capture(monkeypatch)
    client.post("/api/ai/analyze", data={"text": "lunch"})
    assert seen["library_foods"] == []


def test_analyze_refuses_more_attached_foods_than_the_cap(client, monkeypatch):
    configure(monkeypatch)
    # Ids that do not exist: the cap is checked before the lookup, so an absurd
    # request is refused without touching the database at all.
    too_many = list(range(1, ai_router.MAX_ATTACHED_FOODS + 2))

    response = client.post("/api/ai/analyze", data={"text": "lunch", "food_id": too_many})

    assert response.status_code == 422
    assert "Too many saved foods" in response.json()["detail"]
    assert _analysis_count() == 0


def test_analyze_refuses_a_food_id_that_no_longer_exists(client, monkeypatch):
    configure(monkeypatch)
    response = client.post("/api/ai/analyze", data={"text": "lunch", "food_id": [9999]})

    assert response.status_code == 422
    assert "no longer in your library" in response.json()["detail"]
    # Refused before _reserve_call, so it costs the user nothing.
    assert _analysis_count() == 0


def test_analyze_cannot_attach_another_accounts_food(client, client_b, monkeypatch):
    """B may not quote A's library into B's estimate, and pays no slot to find out."""
    configure(monkeypatch)
    a_food = client.post("/api/foods", json=FOOD).json()

    response = client_b.post(
        "/api/ai/analyze", data={"text": "lunch", "food_id": [a_food["id"]]}
    )

    # Identical to an id that never existed: B learns nothing about A's library.
    assert response.status_code == 422
    assert "no longer in your library" in response.json()["detail"]
    assert _analysis_count() == 0


def test_attached_foods_are_refused_before_the_provider_is_checked(client):
    """A bad id answers the same way whether or not a key is configured.

    Deliberately no configure() here: the ordering in the router is what lets
    the isolation suite and the live smoke script prove the ownership rule
    without spending a provider call.
    """
    response = client.post("/api/ai/analyze", data={"text": "lunch", "food_id": [9999]})
    assert response.status_code == 422
    assert "no longer in your library" in response.json()["detail"]


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


# --- attached library foods in the prompt -----------------------------------

# created_at is required on the response schema and carries no meaning for the
# prompt -- _library_block reads names and macros and nothing else -- so it is a
# fixed stamp here rather than utcnow(), which would make these fixtures differ
# between runs for no reason.
STAMP = datetime(2026, 1, 1, 12, 0, 0)

CHICKEN = Food(
    id=1, name="Chicken breast, raw", serving_size=100,
    calories=165, protein=31, carbs=0, fat=3.6, source="user",
    created_at=STAMP,
)
SKYR = Food(
    id=2, name="Skyr", serving_size=100,
    calories=63, protein=11, carbs=None, fat=None, source="user",
    created_at=STAMP,
)


def test_build_contents_quotes_attached_foods_before_the_description():
    parts = _build_contents([], "chicken and rice", None, library_foods=[CHICKEN])
    text = parts[0]
    assert '"Chicken breast, raw" -- per 100 g: 165 kcal, 31 g protein' in text
    assert "these numbers are exact" in text
    # Facts are reference material and the user's words are ground truth, so the
    # words go last -- closest to the answer.
    assert text.index("Chicken breast, raw") < text.index("chicken and rice")


def test_build_contents_says_which_macros_were_never_recorded():
    # carbs and fat are nullable on a foods row. A blank in a list of exact
    # figures reads as zero, which would claim Skyr has no fat.
    parts = _build_contents([], "skyr", None, library_foods=[SKYR])
    assert "63 kcal, 11 g protein (carbs and fat not recorded)" in parts[0]


def test_attached_foods_do_not_replace_the_default_instruction():
    """A photo with foods attached and no typed words still gets an instruction.

    The regression this pins: if the library block were appended to the same
    list the `if not instructions` check reads, it would satisfy that check and
    the model would receive a photo, a table of macros, and nothing telling it
    what to do with either.
    """
    parts = _build_contents(
        [(b"img", "image/png")], None, None, library_foods=[CHICKEN]
    )
    assert len(parts) == 2
    assert "Analyze the meal in the photo." in parts[1]
    assert "Chicken breast, raw" in parts[1]


def test_build_contents_omits_the_block_when_nothing_is_attached():
    parts = _build_contents([], "chicken and rice", None)
    assert "saved food library" not in parts[0]


# --- analyze_meal's response handling (fake genai client, no network) -------

class _FakeAio:
    """The `client.aio` surface meal_ai uses: an async context manager with models."""

    def __init__(self, generate_content, closed):
        self.models = SimpleNamespace(generate_content=generate_content)
        self._closed = closed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self._closed.append(True)


def _fake_client_factory(generate_content, closed=None):
    """Stands in for genai.Client; `closed` gets one entry per client closed."""
    closed = [] if closed is None else closed
    return lambda api_key=None: SimpleNamespace(aio=_FakeAio(generate_content, closed))


def _install_fake_provider(monkeypatch, response):
    async def generate_content(**_kwargs):
        return response

    monkeypatch.setattr(meal_ai.genai, "Client", _fake_client_factory(generate_content))


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

    monkeypatch.setattr(meal_ai.genai, "Client", _fake_client_factory(generate_content))


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
    calls = {"n": 0, "models": [], "configs": [], "closed": []}

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
        _fake_client_factory(generate_content, calls["closed"]),
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


def test_a_sustained_outage_spreads_its_attempts_out(monkeypatch, virtual_clock):
    """Retries wait between attempts rather than firing them back to back.

    The original fixed count gave up ~1.5s in, with 98% of the budget unused —
    indistinguishable from no retry at all. The count is capped again now
    (ANALYZE_MAX_ATTEMPTS, because failed attempts spend the per-day quota), but
    the backoff still spreads those few attempts across the outage.

    ⚠️ This used to assert "at least 8 attempts". That was the behaviour which
    let one analysis spend most of the free tier's 20-a-day; see
    test_attempts_per_action_are_capped.
    """
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    assert calls["n"] == meal_ai.ANALYZE_MAX_ATTEMPTS
    # A sleep between every pair of attempts, none after the last...
    assert len(virtual_clock) == calls["n"] - 1
    # ...and never past the deadline.
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
        # Already sending too much: asking the same model again inside its
        # window makes the thing we're being limited for worse. (With a fallback
        # configured the call moves on to the other model instead; see
        # test_a_per_minute_limit_moves_to_the_other_model_once.)
        genai_errors.ClientError(429, {"error": {"message": "slow down"}}),
        # A rejected key or retired model id fails identically every time.
        genai_errors.ClientError(400, {"error": {"message": "bad key"}}),
        # A drifted dependency raises the same TypeError every time.
        RuntimeError("boom"),
    ],
)
def test_failures_a_retry_cannot_fix_are_not_retried(monkeypatch, exc):
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", "")
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


def test_every_attempt_closes_its_client_including_the_failed_ones(monkeypatch):
    calls = _install_scripted_provider(
        monkeypatch,
        [_server_error(), _server_error(), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert len(calls["closed"]) == calls["n"] == 3


class _Payload:
    """Stands in for an attempt's encoded request body. Weak-referenceable."""


def test_an_attempts_cyclic_garbage_is_freed_before_the_next_attempt(monkeypatch):
    """The 2026-09-29 outage, pinned at the seam that caused it.

    Each real attempt leaves an httpx Response in a cycle with its stream, with
    the whole encoded request hanging off it. Refcounting never frees a cycle,
    and the automatic collector counts objects rather than bytes, so in
    production it never ran and the payloads piled up until the instance was
    killed. The automatic collector is switched off here so the only thing that
    can free the cycle is the collection meal_ai does itself.
    """
    alive_at_next_attempt: list[bool] = []
    previous: list = []

    async def generate_content(**_kwargs):
        if previous:
            alive_at_next_attempt.append(previous[-1]() is not None)
        payload = _Payload()
        payload.cycle = payload  # unreachable once this returns: cycle only
        previous.append(weakref.ref(payload))
        del payload
        if len(previous) < 3:
            raise _server_error()
        return SimpleNamespace(parsed=SAMPLE, text=None)

    monkeypatch.setattr(meal_ai.genai, "Client", _fake_client_factory(generate_content))
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    finally:
        if was_enabled:
            gc.enable()
    assert alive_at_next_attempt == [False, False]


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


# --- 429s: a per-day quota is not a per-minute one ----------------------------
# Google's free tier is 20 requests a day PER MODEL, counted from midnight
# Pacific, failed attempts included. Measured 2026-10-03/04; see
# docs/ai-capacity-2026-10.md.

DAILY_QUOTA_ID = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE_QUOTA_ID = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


def _quota_error(quota_id=None, message="You exceeded your current quota."):
    """A 429 in the shape Google really sends: prose plus a structured QuotaFailure.

    quota_id=None leaves the structured part out entirely, the shape of a 429
    from anything that is not the quota system.
    """
    details = []
    if quota_id is not None:
        details = [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "generativelanguage.googleapis.com/"
                        "generate_content_free_tier_requests",
                        "quotaId": quota_id,
                        "quotaDimensions": {"model": "gemini-3.5-flash"},
                        "quotaValue": "20",
                    }
                ],
            },
            # Google's own retry hint. It points at 00:00 UTC, which is wrong
            # for a per-day quota, so nothing may read it.
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "16800s"},
        ]
    return genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": message,
                "status": "RESOURCE_EXHAUSTED",
                "details": details,
            }
        },
    )


@pytest.fixture(autouse=True)
def _forget_exhausted_models():
    """The exhausted-model memory is module state; no test may inherit another's."""
    meal_ai._exhausted.clear()
    yield
    meal_ai._exhausted.clear()


@pytest.fixture
def wall_clock(monkeypatch):
    """Pins meal_ai's wall clock, which the per-day memory and reset times read."""
    now = {"t": datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(meal_ai, "_utcnow", lambda: now["t"])
    return now


def _chain(monkeypatch, primary, fallback):
    monkeypatch.setenv("MEAL_AI_MODEL", primary)
    monkeypatch.setenv("MEAL_AI_FALLBACK_MODEL", fallback)


def test_a_per_day_quota_raises_its_own_error(monkeypatch):
    _chain(monkeypatch, "gemini-a", "")
    _install_scripted_provider(monkeypatch, [_quota_error(DAILY_QUOTA_ID)])
    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))


def test_a_per_minute_quota_is_not_mistaken_for_the_day(monkeypatch):
    _chain(monkeypatch, "gemini-a", "")
    _install_scripted_provider(monkeypatch, [_quota_error(MINUTE_QUOTA_ID)])
    with pytest.raises(meal_ai.MealAIRateLimited) as raised:
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert not isinstance(raised.value, meal_ai.MealAIDailyQuotaExhausted)


def test_the_message_text_is_never_what_decides(monkeypatch):
    """The first guard in compare_estimates.py matched "PerDay" in the prose and
    stopped a run on what was a per-minute refusal. Only the quotaId counts."""
    _chain(monkeypatch, "gemini-a", "")
    _install_scripted_provider(
        monkeypatch,
        [_quota_error(MINUTE_QUOTA_ID, message="Quota exceeded: ...PerDay... retry in 4h")],
    )
    with pytest.raises(meal_ai.MealAIRateLimited) as raised:
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert not isinstance(raised.value, meal_ai.MealAIDailyQuotaExhausted)


def test_a_429_without_structured_details_is_treated_as_per_minute(monkeypatch):
    _chain(monkeypatch, "gemini-a", "")
    _install_scripted_provider(monkeypatch, [_quota_error(None, message="PerDay")])
    with pytest.raises(meal_ai.MealAIRateLimited) as raised:
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert not isinstance(raised.value, meal_ai.MealAIDailyQuotaExhausted)


def test_a_daily_limit_falls_back_to_the_next_model_at_once(monkeypatch, virtual_clock):
    """Each model has its own 20 a day, so the fallback still has its whole
    allowance -- and waiting first buys nothing, since the day will not end."""
    _chain(monkeypatch, "gemini-a", "gemini-b")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(DAILY_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["models"] == ["gemini-a", "gemini-b"]
    assert virtual_clock == []


def test_a_later_call_skips_a_model_already_out_for_the_day(monkeypatch):
    _chain(monkeypatch, "gemini-a", "gemini-b")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(DAILY_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    asyncio.run(meal_ai.analyze_meal([], "chicken"))
    asyncio.run(meal_ai.analyze_meal([], "chicken"))
    # Three attempts, not four: the second analysis never asked gemini-a.
    assert calls["models"] == ["gemini-a", "gemini-b", "gemini-b"]


def test_with_every_model_out_for_the_day_google_is_not_called(monkeypatch):
    """Asking would spend nothing useful, and the answer is already known."""
    _chain(monkeypatch, "gemini-a", "gemini-b")
    calls = _install_scripted_provider(monkeypatch, [_quota_error(DAILY_QUOTA_ID)])
    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 2

    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.transcribe_audio(b"audio", "audio/webm"))
    assert calls["n"] == 2


def test_the_memory_is_rechecked_within_the_hour(monkeypatch, wall_clock):
    """Billing switched on mid-day lifts the quota at once; the app must notice
    without waiting for midnight Pacific or a restart."""
    _chain(monkeypatch, "gemini-a", "")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(DAILY_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    wall_clock["t"] += timedelta(minutes=59)
    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 1

    wall_clock["t"] += timedelta(minutes=2)
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["n"] == 2


def test_the_memory_never_outlives_midnight_pacific(monkeypatch, wall_clock):
    """06:30 UTC on 2026-10-05 is 23:30 the day before in Los Angeles (PDT): the
    quota resets in half an hour, sooner than the hourly re-check."""
    wall_clock["t"] = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)
    _chain(monkeypatch, "gemini-a", "")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(DAILY_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    with pytest.raises(meal_ai.MealAIDailyQuotaExhausted):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))

    wall_clock["t"] += timedelta(minutes=31)
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["n"] == 2


@pytest.mark.parametrize(
    "now,expected",
    [
        # PDT, UTC-7: midnight in Los Angeles is 07:00 UTC.
        (datetime(2026, 10, 4, 12, 0), datetime(2026, 10, 5, 7, 0)),
        (datetime(2026, 10, 5, 6, 59), datetime(2026, 10, 5, 7, 0)),
        (datetime(2026, 10, 5, 7, 0), datetime(2026, 10, 6, 7, 0)),
        # US DST ends 2026-11-01; from then midnight is 08:00 UTC.
        (datetime(2026, 11, 1, 12, 0), datetime(2026, 11, 2, 8, 0)),
    ],
)
def test_the_daily_quota_resets_at_midnight_pacific(now, expected):
    """Google's documented reset, confirmed by measurement 2026-10-04. The 429's
    own retryDelay points at 00:00 UTC and is wrong."""
    got = meal_ai.next_quota_reset(now.replace(tzinfo=timezone.utc))
    assert got == expected.replace(tzinfo=timezone.utc)


def test_a_per_minute_limit_moves_to_the_other_model_once(monkeypatch, virtual_clock):
    """Per-minute windows are per model too. The refusing model is never asked
    again in the same call -- that would only deepen its window."""
    _chain(monkeypatch, "gemini-a", "gemini-b")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(MINUTE_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["models"] == ["gemini-a", "gemini-b"]
    assert virtual_clock == []


def test_a_per_minute_limit_is_not_remembered_past_the_call(monkeypatch):
    _chain(monkeypatch, "gemini-a", "")
    calls = _install_scripted_provider(
        monkeypatch,
        [_quota_error(MINUTE_QUOTA_ID), SimpleNamespace(parsed=SAMPLE, text=None)],
    )
    with pytest.raises(meal_ai.MealAIRateLimited):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert asyncio.run(meal_ai.analyze_meal([], "chicken")) is SAMPLE
    assert calls["models"] == ["gemini-a", "gemini-a"]


def test_attempts_per_action_are_capped(monkeypatch):
    """Failed attempts count against the per-day quota exactly like successful
    ones (measured 2026-10-04: 2 answers + ~12 overload failures, then refused
    for the day). Uncapped, one analysis in an overload could spend the whole
    app's day."""
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == meal_ai.ANALYZE_MAX_ATTEMPTS

    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.transcribe_audio(b"audio", "audio/webm"))
    assert calls["n"] == meal_ai.TRANSCRIBE_MAX_ATTEMPTS


def test_the_attempt_cap_is_overridable_from_the_dashboard(monkeypatch):
    """On a paid key a refused attempt costs nothing, so the cap can go up."""
    monkeypatch.setenv("MEAL_AI_MAX_ATTEMPTS", "7")
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == 7


@pytest.mark.parametrize("bad", ["", "0", "-2", "lots"])
def test_an_unusable_attempt_cap_keeps_the_default(monkeypatch, bad):
    monkeypatch.setenv("MEAL_AI_MAX_ATTEMPTS", bad)
    calls = _install_scripted_provider(monkeypatch, [_server_error()])
    with pytest.raises(meal_ai.MealAIUnavailable):
        asyncio.run(meal_ai.analyze_meal([], "chicken"))
    assert calls["n"] == meal_ai.ANALYZE_MAX_ATTEMPTS


def test_the_fallback_can_be_a_list(monkeypatch):
    """Every model on the free tier is another 20 a day."""
    _chain(monkeypatch, "gemini-a", "gemini-b, gemini-c,,gemini-a")
    assert meal_ai._models() == ["gemini-a", "gemini-b", "gemini-c"]


def test_status_reports_every_fallback(client, monkeypatch):
    _chain(monkeypatch, "gemini-a", "gemini-b,gemini-c")
    body = client.get("/api/ai/status").json()
    assert body["model"] == "gemini-a"
    assert body["fallback_model"] == "gemini-b, gemini-c"


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


# --- what a user is told when the day's AI is gone ---------------------------


def test_a_daily_provider_limit_never_says_try_again_in_a_minute(client, monkeypatch):
    """The bug: every 429 said "Try again in a minute", which is false for
    hours when it is Google's quota for the DAY that ran out."""
    resets_at = datetime.now(timezone.utc) + timedelta(hours=5, minutes=10)

    async def out_for_the_day(*_args, **_kwargs):
        raise meal_ai.MealAIDailyQuotaExhausted("spent", resets_at)

    configure(monkeypatch, out_for_the_day)
    response = client.post("/api/ai/analyze", data={"text": "pizza"})
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert "minute" not in detail
    assert "resets in about 5 hours" in detail
    assert "enter macros manually" in detail


def test_a_per_minute_limit_still_says_a_minute(client, monkeypatch):
    async def busy(*_args, **_kwargs):
        raise meal_ai.MealAIRateLimited("slow down")

    configure(monkeypatch, busy)
    response = client.post("/api/ai/analyze", data={"text": "pizza"})
    assert response.status_code == 429
    assert "in a minute" in response.json()["detail"]


def test_a_daily_limit_refunds_the_slot(client, monkeypatch):
    """Refused before inference, so it costs the user nothing."""
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")

    async def out_for_the_day(*_args, **_kwargs):
        raise meal_ai.MealAIDailyQuotaExhausted("spent", meal_ai.next_quota_reset())

    configure(monkeypatch, out_for_the_day)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 429
    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200


def test_the_app_caps_say_when_they_reset(client, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "1")
    configure(monkeypatch)
    assert client.post("/api/ai/analyze", data={"text": "pizza"}).status_code == 200
    detail = client.post("/api/ai/analyze", data={"text": "pizza"}).json()["detail"]
    assert "resets in" in detail and "tomorrow" not in detail

    monkeypatch.setenv("AI_DAILY_LIMIT", "5")
    monkeypatch.setenv("AI_GLOBAL_DAILY_LIMIT", "1")
    detail = client.post("/api/ai/analyze", data={"text": "pizza"}).json()["detail"]
    assert "shared daily AI quota" in detail and "resets in" in detail


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (5, "in under an hour"),
        (59, "in under an hour"),
        (60, "in about 1 hour"),
        (89, "in about 1 hour"),
        (91, "in about 2 hours"),
        (23 * 60 + 50, "in about 24 hours"),
    ],
)
def test_reset_wording(minutes, expected):
    now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    assert ai_router.resets_in(now + timedelta(minutes=minutes), now) == expected


def test_the_default_caps_fit_the_real_free_tier(monkeypatch):
    """Set for a free tier of 20 requests a day per model, measured 2026-10-03.
    The old defaults (500 global, 20 and 40 per user) were set for a tier ~25x
    larger and meant one account could take the whole app's day."""
    for name in ("AI_DAILY_LIMIT", "AI_TRANSCRIBE_DAILY_LIMIT", "AI_GLOBAL_DAILY_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    assert ai_router._daily_limit() == 12
    assert ai_router._transcribe_daily_limit() == 16
    assert ai_router.global_daily_limit() == 40


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


# --- calibration -------------------------------------------------------------


def _analyse_and_save(client, monkeypatch, calories, protein=None):
    """Run an analysis, save a meal from it, and link the two.

    Goes through the routes rather than inserting rows, because the link is what
    creates a calibration pair and the router owns both halves of it.
    """
    configure(monkeypatch)
    analysis = client.post("/api/ai/analyze", data={"text": "chicken and rice"}).json()
    meal = client.post(
        "/api/meals",
        json={
            "date": date.today().isoformat(),
            "name": "Chicken & Rice",
            "calories": calories,
            "protein": SAMPLE.protein.estimate if protein is None else protein,
        },
    ).json()
    client.patch(
        f"/api/ai/analyses/{analysis['analysis_id']}", json={"meal_id": meal["id"]}
    )
    return analysis, meal


def test_calibration_is_empty_before_anything_is_linked(client):
    body = client.get("/api/ai/calibration").json()

    assert body["analyses"] == 0
    assert body["linked"] == 0
    assert body["calories"]["coverage_pct"] is None
    assert body["unavailable_reason"] is not None


def test_calibration_spends_no_quota_and_writes_no_row(client, monkeypatch):
    """A read about billable calls must not itself be a billable call.

    Every ai_analyses row is one provider call by definition, which is what
    calls_today and the admin stats count. Reserving a slot here would corrupt
    the very counter this endpoint reports on.
    """
    _analyse_and_save(client, monkeypatch, calories=SAMPLE.calories.estimate)

    with Session(get_engine()) as db:
        before = db.query(AIAnalysis).count()

    for _ in range(3):
        assert client.get("/api/ai/calibration").status_code == 200

    with Session(get_engine()) as db:
        assert db.query(AIAnalysis).count() == before


def test_calibration_counts_an_untouched_estimate_as_accepted(client, monkeypatch):
    """The saved value *is* the estimate, so it cannot be evidence about range."""
    _analyse_and_save(client, monkeypatch, calories=SAMPLE.calories.estimate)

    body = client.get("/api/ai/calibration").json()
    assert body["linked"] == 1
    assert body["accepted_unchanged"] == 1
    assert body["corrected"] == 0
    assert body["calories"]["corrected"] == 0


def test_calibration_counts_a_changed_value_as_a_correction(client, monkeypatch):
    _analyse_and_save(client, monkeypatch, calories=SAMPLE.calories.estimate + 120)

    body = client.get("/api/ai/calibration").json()
    assert body["accepted_unchanged"] == 0
    assert body["corrected"] == 1
    assert body["calories"]["corrected"] == 1


def test_calibration_ignores_an_analysis_that_was_never_saved(client, monkeypatch):
    """An estimate the user looked at and abandoned says nothing about accuracy."""
    configure(monkeypatch)
    client.post("/api/ai/analyze", data={"text": "chicken and rice"})

    body = client.get("/api/ai/calibration").json()
    assert body["analyses"] == 1
    assert body["linked"] == 0


def test_calibration_ignores_transcription_rows(client, monkeypatch):
    """They carry an empty analysis_json and are not estimates at all."""
    configure_transcribe(monkeypatch)
    client.post(
        "/api/ai/transcribe", files={"audio": ("a.webm", b"xx", "audio/webm")}
    )

    body = client.get("/api/ai/calibration").json()
    assert body["analyses"] == 0
    assert body["unreadable"] == 0


# --- provider timing (migration 0015) ---
#
# Every test here drives the clock rather than reading it: a wall-clock
# assertion would be a flake waiting for a slow CI box, and the thing worth
# testing is the arithmetic and which paths keep the row, not that monotonic()
# advances.


def fixed_clock(monkeypatch, *readings):
    """Make ai_router.time_module.monotonic return `readings` in order."""
    monkeypatch.setattr(
        ai_router, "time_module", SimpleNamespace(monotonic=iter(readings).__next__)
    )


def test_analyze_records_how_long_the_provider_took(client, monkeypatch):
    configure(monkeypatch)
    fixed_clock(monkeypatch, 0.0, 4.2)

    body = client.post("/api/ai/analyze", data={"text": "chicken and rice"}).json()

    with Session(get_engine()) as session:
        row = session.get(AIAnalysis, body["analysis_id"])
        assert row.provider_ms == 4200
        assert row.server_uptime_s is not None


def test_a_timing_is_kept_when_only_the_output_was_unusable(client, monkeypatch):
    """The model ran, so the wait was real even though the answer was not.

    The row already survives this path to keep the quota slot spent; dropping
    its timing would make the p95 describe a faster service than the one people
    are actually waiting on.
    """

    async def unusable(images, text, prior_analysis=None, **kwargs):
        raise meal_ai.MealAIBadResponse("not JSON")

    configure(monkeypatch, unusable)
    fixed_clock(monkeypatch, 0.0, 7.5)

    assert client.post("/api/ai/analyze", data={"text": "rice"}).status_code == 502

    with Session(get_engine()) as session:
        row = session.execute(select(AIAnalysis)).scalars().one()
        assert row.provider_ms == 7500


def test_a_refunded_analysis_leaves_no_timing_behind(client, monkeypatch):
    """A call rejected before inference is deleted, so it cannot skew anything.

    This is why provider_ms describes calls that REACHED the model rather than
    calls that were attempted -- worth pinning, because a future "let's keep the
    row for diagnostics" would silently change what every percentile means.
    """

    async def unreachable(images, text, prior_analysis=None, **kwargs):
        raise meal_ai.MealAIUnavailable("boom")

    configure(monkeypatch, unreachable)

    assert client.post("/api/ai/analyze", data={"text": "rice"}).status_code == 503

    with Session(get_engine()) as session:
        assert session.execute(select(func.count()).select_from(AIAnalysis)).scalar() == 0


def test_transcribe_records_how_long_the_provider_took(client, monkeypatch):
    configure_transcribe(monkeypatch)
    fixed_clock(monkeypatch, 0.0, 1.25)

    assert post_voice_note(client).status_code == 200

    with Session(get_engine()) as session:
        row = session.execute(select(AIAnalysis)).scalars().one()
        assert row.kind == "transcription"
        assert row.provider_ms == 1250


def test_a_row_written_before_the_column_existed_reads_as_none(client):
    """Nullable on purpose: 0 would be a measured zero and drag medians down.

    Guards the decision against a later "just default it to 0", which would look
    tidier and quietly corrupt every figure on the admin panel.
    """
    with Session(get_engine()) as session:
        session.add(AIAnalysis(user_id=1, user_text="old", analysis_json="{}"))
        session.commit()
        row = session.execute(select(AIAnalysis)).scalars().one()
        assert row.provider_ms is None
        assert row.server_uptime_s is None
