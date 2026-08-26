"""The meal-code codec: what it produces, and what it refuses to read."""
import base64
import json
import zlib

import pytest
from app.share import (
    MAX_CODE_CHARS,
    MAX_DECODED_BYTES,
    SHARE_VERSION,
    ShareCodeError,
    decode_share_code,
    encode_share_code,
)


def item(i: int = 0, name: str | None = None) -> dict:
    """One ingredient row, shaped like schemas.TemplateItem."""
    return {
        "name": name if name is not None else f"Chicken breast {i}",
        "weight_grams": 150.0,
        "serving_size": 100.0,
        "calories": 165.0,
        "protein": 31.0,
        "carbs": 0.0,
        "fat": 3.6,
    }


def payload(items: int = 2, **overrides) -> dict:
    base = {
        "name": "Chicken & Rice",
        "calories": 620.0,
        "protein": 48.0,
        "carbs": 55.0,
        "fat": 18.0,
        "items": [item(i) for i in range(items)],
    }
    return {**base, **overrides}


def hand_built(obj, *, version: str = SHARE_VERSION) -> str:
    """A code built WITHOUT going through encode_share_code.

    Every hardening test below needs a code the encoder would never mint -- a
    bomb, a wrong version, a truncated stream, a bare `Infinity`. Building them
    by round-tripping through encode_share_code could only ever produce codes
    that decode, so it can prove nothing about the ones that must not. This also
    skips the float rounding, which is how "rounding happens on the way out
    only" is testable at all.
    """
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return wrap_bytes(zlib.compress(raw, 9), version=version)


def wrap_bytes(packed: bytes, *, version: str = SHARE_VERSION) -> str:
    """Wrap arbitrary (possibly hostile) compressed bytes as a code."""
    body = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return f"{version}.{body}"


# --- the wire format -------------------------------------------------------


def test_a_code_round_trips_to_the_payload_it_was_made_from():
    original = payload(items=3)
    assert decode_share_code(encode_share_code(original)) == original


def test_a_code_names_its_version_so_a_reader_can_tell_what_it_is():
    code = encode_share_code(payload())
    assert code.startswith(f"{SHARE_VERSION}.")


def test_a_five_item_code_fits_in_a_chat_message():
    """Pins the size claim the whole design rests on.

    If a future change to the wire format quadruples this, it should be visible
    in the diff of this number rather than discovered by a user whose chat app
    silently trimmed the code.
    """
    assert len(encode_share_code(payload(items=5))) < 400


def test_the_largest_legal_meal_still_fits_under_the_length_cap():
    """THIS TEST IS THE COUPLING between share.py and schemas.MAX_TEMPLATE_ITEMS.

    MAX_CODE_CHARS is derived in a comment from the item cap and the 200-char
    name bound; nothing in the code enforces that derivation. Raising either
    bound without raising the cap would start refusing codes this app itself
    mints, and this is what catches that.
    """
    from app.schemas import MAX_TEMPLATE_ITEMS

    # Random-looking names so zlib cannot compress them away and the worst case
    # is really the worst case.
    names = [("%030x" % (i * 7919)) * 6 for i in range(MAX_TEMPLATE_ITEMS)]
    worst = payload(items=0, name="x" * 200)
    worst["items"] = [item(i, name=names[i][:200]) for i in range(MAX_TEMPLATE_ITEMS)]
    assert len(encode_share_code(worst)) <= MAX_CODE_CHARS


def test_encoding_the_same_meal_twice_gives_the_same_code():
    """Copying the same meal twice and getting two strings would read as a bug."""
    assert encode_share_code(payload()) == encode_share_code(payload())


def test_macros_are_rounded_to_two_decimals_on_the_way_out():
    code = encode_share_code(payload(items=0, calories=0.1 + 0.2, protein=1234.5678))
    decoded = decode_share_code(code)
    assert decoded["calories"] == 0.3
    assert decoded["protein"] == 1234.57


def test_rounding_happens_on_the_way_out_only():
    """The decoder reports what the code says.

    If it re-rounded, a hand-built code and a re-encoded one would disagree
    about identical bytes, and the codec would no longer be the inverse of
    itself for anything it did not mint.
    """
    decoded = decode_share_code(hand_built(payload(items=0, calories=0.123456)))
    assert decoded["calories"] == 0.123456


def test_a_non_finite_macro_is_refused_rather_than_written_as_Infinity():
    """inf is not JSON, and `Infinity` is what json.dumps would write for it.

    data.py carries the scar: a non-finite value in a Float column once 500'd
    the whole export, because Starlette dumps with allow_nan=False. A code
    carrying inf would be readable only by this app's own decoder and would put
    inf straight back into a Float column on the way in.
    """
    with pytest.raises(ShareCodeError):
        encode_share_code(payload(items=0, calories=float("inf")))
    with pytest.raises(ShareCodeError):
        encode_share_code(payload(items=0, protein=float("nan")))


def test_a_unicode_meal_name_survives_exactly():
    """ensure_ascii=False keeps the name as UTF-8, which is both shorter and
    what zlib compresses. base64 is byte-clean, so nothing needs escaping."""
    name = "Grandma's kottbullar \N{LATIN SMALL LETTER O WITH DIAERESIS} \U0001f1f8\U0001f1ea"
    assert decode_share_code(encode_share_code(payload(name=name)))["name"] == name


def test_an_empty_item_list_survives_the_round_trip():
    """The meal case: a logged meal has no ingredient rows to carry.

    It must arrive as [] and not as a missing key, because the client's
    fallback to a totals-only row keys off items.length === 0.
    """
    assert decode_share_code(encode_share_code(payload(items=0)))["items"] == []


# --- decoding hostile input ------------------------------------------------


def test_line_wraps_from_a_chat_app_do_not_break_a_code():
    code = encode_share_code(payload(items=4))
    mangled = f"  {code[:20]}\n{code[20:60]}\r\n{code[60:]}\N{NO-BREAK SPACE}  "
    assert decode_share_code(mangled) == decode_share_code(code)


def test_a_zero_width_space_is_refused_rather_than_crashing():
    """U+200B is NOT str.isspace(), so it survives the whitespace strip and
    reaches b64decode, which raises a bare ValueError -- not the binascii.Error
    the obvious except clause would catch."""
    code = encode_share_code(payload())
    with pytest.raises(ShareCodeError):
        decode_share_code(code[:10] + "\N{ZERO WIDTH SPACE}" + code[10:])


def test_prose_pasted_by_mistake_is_refused():
    """The everyday case: someone pastes a sentence instead of a code.

    Deliberately NOT the test that pins validate=True -- see the next one for
    why. Prose is refused either way, because whatever junk it decodes to fails
    at zlib with the same message.
    """
    with pytest.raises(ShareCodeError, match="doesn't look like"):
        decode_share_code("MC1.hello there, this is not a code!!!")


def test_out_of_alphabet_characters_are_refused_rather_than_stripped():
    """THE test that pins validate=True, and it took two wrong tries to get.

    Refusing prose does not pin it: without validation the junk still fails at
    zlib and raises the same refusal, so that test stays green with the guard
    gone. Peppering the body with "!" between every character does not pin it
    either -- it changes the body's length mod 4, so it is refused for incorrect
    *padding* rather than for validation.

    Inserting exactly four characters is what isolates the guard: the length mod
    4 is unchanged, so the padding stays correct, and without validate=True the
    four are silently dropped and the original code decodes cleanly. Removing
    the guard therefore makes this a successful round-trip and fails the test.
    A code the user mangled must not appear to work.
    """
    version, _, body = encode_share_code(payload()).partition(".")
    mid = len(body) // 2
    with pytest.raises(ShareCodeError, match="doesn't look like"):
        decode_share_code(f"{version}.{body[:mid]}!!!!{body[mid:]}")


def test_a_truncated_paste_is_named_as_incomplete_not_as_garbage():
    """The failure people actually hit: chat clients trim long messages."""
    code = encode_share_code(payload(items=6))
    with pytest.raises(ShareCodeError, match="cut short"):
        decode_share_code(code[: len(code) - 8])


def test_a_single_corrupted_character_is_refused():
    """zlib's Adler-32 check, which is the integrity guarantee a signature
    would otherwise have been reached for."""
    packed = bytearray(zlib.compress(json.dumps(payload()).encode(), 9))
    packed[6] ^= 0xFF
    with pytest.raises(ShareCodeError):
        decode_share_code(wrap_bytes(bytes(packed)))


def test_trailing_bytes_after_the_stream_are_refused():
    """Without the unused_data check these are silently ignored."""
    packed = zlib.compress(json.dumps(payload()).encode(), 9)
    with pytest.raises(ShareCodeError):
        decode_share_code(wrap_bytes(packed + b"GARBAGE"))


def test_a_decompression_bomb_is_refused_without_being_expanded():
    """The bound is max_length, not a timer.

    5 MB of zeros compress to under 5 KB. The bounded read produces
    MAX_DECODED_BYTES + 1 bytes and stops, leaving the rest unconsumed -- the
    5 MB is never allocated.
    """
    bomb = zlib.compress(b"\0" * 5_000_000, 9)
    assert len(bomb) < MAX_DECODED_BYTES
    with pytest.raises(ShareCodeError, match="longer than"):
        decode_share_code(wrap_bytes(bomb))


def test_a_code_past_the_length_cap_is_refused_before_it_is_decompressed():
    """Proves the ORDER, not just the refusal.

    The body is not valid base64, so if the length check did not run first this
    would come back as "doesn't look like a code". Getting the length message
    is what shows nothing was decoded.
    """
    with pytest.raises(ShareCodeError, match="longer than"):
        decode_share_code("MC1." + "!" * (MAX_CODE_CHARS + 1))


def test_a_code_from_a_future_version_says_so():
    with pytest.raises(ShareCodeError, match="newer version"):
        decode_share_code(hand_built(payload(), version="MC2"))


def test_a_string_that_is_not_shaped_like_a_code_is_refused_plainly():
    """A paragraph is not a future version. Telling someone to reload the page
    would send them off to fix the wrong thing."""
    for bad in ("", "hello", SHARE_VERSION, f"{SHARE_VERSION}.", ".abc", "MCX.abc"):
        with pytest.raises(ShareCodeError, match="doesn't look like"):
            decode_share_code(bad)


def test_a_payload_that_is_not_a_json_object_is_refused():
    """Legal JSON that is not a mapping would sail into a caller expecting
    fields, so the shape is checked in the codec rather than there."""
    for bad in ([1, 2, 3], "hello", None, 42):
        with pytest.raises(ShareCodeError):
            decode_share_code(hand_built(bad))


# --- the endpoints ---------------------------------------------------------


MEAL = {
    "date": "2026-07-01",
    "name": "Chicken & Rice",
    "calories": 560.0,
    "protein": 45.0,
    "carbs": 56.0,
    "fat": 8.5,
}
TEMPLATE = {
    "name": "Post-gym plate",
    "calories": 620.0,
    "protein": 48.0,
    "carbs": 55.0,
    "fat": 18.0,
    "items": [item(0), item(1)],
}


def test_a_shared_meal_can_express_exactly_what_a_template_can():
    """The drift alarm for a deliberate duplication.

    SharedMeal is field-identical to MealTemplateCreate and is defined
    separately anyway, so that a field added to template-saving is not silently
    also a field a stranger's code can carry. This fails on the day they
    diverge, which is when someone should be deciding whether they should.
    """
    from app.schemas import MealTemplateCreate, SharedMeal

    assert set(SharedMeal.model_fields) == set(MealTemplateCreate.model_fields)


def test_a_meal_becomes_a_code_that_decodes_to_the_same_numbers(client):
    meal = client.post("/api/meals", json=MEAL).json()
    code = client.get(f"/api/share/meal/{meal['id']}").json()["code"]

    decoded = client.post("/api/share/decode", json={"code": code})
    assert decoded.status_code == 200
    assert decoded.json() == {
        "name": MEAL["name"],
        "calories": MEAL["calories"],
        "protein": MEAL["protein"],
        "carbs": MEAL["carbs"],
        "fat": MEAL["fat"],
        "items": [],
    }


def test_a_meal_code_carries_no_items_so_the_client_falls_back_to_totals(client):
    """A Meal has no ingredient rows to carry -- they are discarded on save."""
    meal = client.post("/api/meals", json=MEAL).json()
    code = client.get(f"/api/share/meal/{meal['id']}").json()["code"]
    assert decode_share_code(code)["items"] == []


def test_a_template_code_carries_its_ingredient_rows(client):
    """The reason a template is the better thing to share: the recipient can
    adjust one ingredient instead of scaling the whole meal."""
    created = client.post("/api/meal-templates", json=TEMPLATE).json()
    code = client.get(f"/api/share/template/{created['id']}").json()["code"]

    decoded = client.post("/api/share/decode", json={"code": code}).json()
    assert [i["name"] for i in decoded["items"]] == [
        TEMPLATE["items"][0]["name"],
        TEMPLATE["items"][1]["name"],
    ]
    assert decoded["items"][0]["weight_grams"] == 150.0


def test_the_code_carries_no_date_no_id_and_no_owner(client):
    """THE leak test. Read against the raw payload, not the response model.

    Checking the response would prove nothing -- SharedMeal would drop an extra
    field on the way out and the code would still be carrying it. The key set
    of the decoded payload is the only place this is visible.
    """
    meal = client.post("/api/meals", json=MEAL).json()
    code = client.get(f"/api/share/meal/{meal['id']}").json()["code"]

    payload = decode_share_code(code)
    assert set(payload) == {"name", "calories", "protein", "carbs", "fat", "items"}


def test_an_untracked_macro_travels_as_an_absent_key_not_a_null(client):
    meal = client.post("/api/meals", json={**MEAL, "carbs": None, "fat": None}).json()
    code = client.get(f"/api/share/meal/{meal['id']}").json()["code"]

    assert set(decode_share_code(code)) == {"name", "calories", "protein", "items"}
    # ...and the recipient still sees them, as the nulls the client expects.
    decoded = client.post("/api/share/decode", json={"code": code}).json()
    assert decoded["carbs"] is None and decoded["fat"] is None


def test_a_code_cannot_express_more_than_a_template_can(client):
    """Pins the equivalence the whole validation posture rests on.

    A code carrying 31 ingredients is refused, and the same body posted to
    /api/meal-templates is refused too -- by the same constant. If these ever
    disagree, a code has become a way around a bound this app enforces.
    """
    from app.schemas import MAX_TEMPLATE_ITEMS

    too_many = {**TEMPLATE, "items": [item(i) for i in range(MAX_TEMPLATE_ITEMS + 1)]}
    assert (
        client.post("/api/share/decode", json={"code": hand_built(too_many)}).status_code
        == 400
    )
    assert client.post("/api/meal-templates", json=too_many).status_code == 422


def test_a_code_carrying_infinity_is_refused_and_does_not_500(client):
    """The highest-value hardening case.

    `Infinity` is what json.dumps writes for float('inf') and json.loads accepts
    it happily, so without allow_inf_nan=False on SharedMeal this reaches a
    Float column -- and a single such row 500s the whole account export.
    """
    raw = json.dumps({**TEMPLATE, "items": [], "calories": float("inf")})
    code = wrap_bytes(zlib.compress(raw.encode(), 9))
    assert "Infinity" in raw

    response = client.post("/api/share/decode", json={"code": code})
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


def test_a_negative_macro_in_a_code_is_refused(client):
    bad = {**TEMPLATE, "items": [], "protein": -5.0}
    assert (
        client.post("/api/share/decode", json={"code": hand_built(bad)}).status_code
        == 400
    )


def test_an_oversized_code_is_refused_by_the_request_model(client):
    """422 from request validation, distinct from the 400s a bad code gets."""
    response = client.post(
        "/api/share/decode", json={"code": "MC1." + "a" * (MAX_CODE_CHARS + 1)}
    )
    assert response.status_code == 422


def test_a_garbled_code_comes_back_as_a_sentence(client):
    """The client renders `detail` when it is a string; a pydantic field path
    would be both useless to the reader and about someone else's payload."""
    response = client.post("/api/share/decode", json={"code": "MC1.not-a-real-code"})
    assert response.status_code == 400
    assert response.json()["detail"].endswith(".")


def test_sharing_something_that_does_not_exist_is_a_404(client):
    assert client.get("/api/share/meal/999999").status_code == 404
    assert client.get("/api/share/template/999999").status_code == 404


def test_decoding_writes_nothing(client):
    """200, not 201. Decode is a read of a string."""
    meal = client.post("/api/meals", json=MEAL).json()
    code = client.get(f"/api/share/meal/{meal['id']}").json()["code"]

    assert client.post("/api/share/decode", json={"code": code}).status_code == 200
    assert len(client.get("/api/meals").json()) == 1
    assert client.get("/api/meal-templates").json() == []


def test_every_share_route_requires_a_token(anon_client):
    assert anon_client.get("/api/share/meal/1").status_code == 401
    assert anon_client.get("/api/share/template/1").status_code == 401
    assert anon_client.post("/api/share/decode", json={"code": "x"}).status_code == 401
