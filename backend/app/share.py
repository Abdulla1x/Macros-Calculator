"""Meal share codes: a whole meal, encoded into a string you can send someone.

The codec only. No database, no request, no knowledge of what a meal is -- this
module moves dicts to strings and back, the way `calculations.py` moves numbers,
so every hostile-input case below is a plain unit test with no fixture.

A code is **the meal itself**, not a pointer at one. That single decision is
what keeps this feature out of the isolation suite: nothing is stored, nothing
is looked up, and decoding never touches the sender's rows. It also has
consequences that have to be said on screen rather than only here -- a code
cannot be revoked, and correcting the meal it came from does nothing to a code
already sent.

Four things this format is built around, all of them load-bearing:

  * **Decoding runs on bytes a stranger chose.** The one real hazard in this
    module is decompression: 5 MB of zeros compress to under 5 KB, so an
    unbounded `zlib.decompress` hands any authenticated caller a memory
    amplifier. Every decode is bounded twice -- once on the code's length before
    anything is decoded, once on the output length during decompression -- and
    the bounds are checked, not trusted.

  * **`validate=True` on the base64 decode is not decoration.** Without it,
    `base64.b64decode` *silently discards* every character outside its alphabet,
    so a paste of ordinary prose decodes to a handful of junk bytes and fails
    two layers further down as an incomprehensible zlib error. With it, prose is
    refused where it is pasted. Do not remove it to "simplify" the call.

  * **A truncated paste is the failure people actually hit**, because chat
    clients trim long messages and a double-click selection misses the tail.
    zlib distinguishes it for free -- a short stream ends with `eof` unset, while
    a corrupted one raises -- so it gets its own sentence instead of being
    lumped in with garbage.

  * **A code minted today has to decode forever.** There is no server-side row
    to migrate and no way to reach a code someone has already sent. The version
    prefix is the escape hatch: `MC1` payloads are frozen, and any change that
    would make an old code unreadable ships as `MC2` while `MC1` keeps decoding.

What this module refuses to do: guarantee the numbers. It has no signature and
will not be given one. A signature could only ever prove that this server
encoded the string -- never that the macros in it are right, because a person
typed them or an estimate guessed them. Shipping one would let the interface say
"verified" about a number nobody checked, which is the exact false confidence
this app exists to refuse. Integrity against a mangled paste is already covered
by zlib's Adler-32 check, which is the failure that actually happens.
"""
import base64
import json
import zlib
from collections.abc import Mapping
from typing import Any

# CONVENTION. The format tag, and the separator between it and the payload.
#
# The dot is deliberately outside the base64url alphabet (A-Z a-z 0-9 - _), so
# splitting on it can never bite into the payload the way splitting on "-" or
# "_" would. It also means an unknown version can still be *read* well enough to
# say "this came from a newer app" instead of failing as unparseable noise --
# which is only possible because the tag is separable without decoding anything.
SHARE_VERSION = "MC1"
_SEPARATOR = "."

# CONVENTION. Decimal places kept when a meal is encoded.
#
# Not a loss of precision in practice: the client already rounds every total to
# two places before it is ever stored (LogMeal's save path), and the UI shows
# whole kcal and one decimal of grams. What it buys is a *bounded* float width.
# json.dumps writes the shortest string that round-trips, so an unrounded
# 0.1 + 0.2 serializes as 19 characters, and without this the worst-case code
# length below could not be computed at all.
#
# Applied on the way out only. The decoder reports what the code says, or a
# hand-built code and a re-encoded one would disagree about identical bytes.
SHARE_DECIMALS = 2

# POLICY. The longest string this will even look at, checked before decoding.
#
# Measured, not guessed. The largest code the encoder can possibly produce is a
# 30-item meal (schemas.MAX_TEMPLATE_ITEMS) whose every name is 200 incompressible
# characters (the TemplateItem.name bound), which comes to about 6,600 characters;
# a realistic 5-item meal is about 230. 8192 leaves room above the legal ceiling
# so this can never refuse a code the encoder itself would mint -- a property
# pinned by a test rather than left as an intention.
#
# Its job is to bound the work done *before* decompression, so it is checked
# against the whitespace-stripped string and reused as the request body's
# max_length in schemas.py.
MAX_CODE_CHARS = 8192

# POLICY. The most a code is allowed to decompress to.
#
# Derived from the same ceiling: 30 items x 200-character names at up to 4 bytes
# per character in UTF-8, plus JSON key overhead and six floats each, measures
# around 31 KB for the worst payload actually constructible. 64 KiB is the next
# power of two, which leaves headroom for a format change without leaving enough
# for a decompression bomb to be interesting -- 5 MB of zeros compress to under
# 5 KB, and this is the number that stops them.
MAX_DECODED_BYTES = 65536

# Three refusals, distinguished only where the user could act differently on
# them. "Copy it again" and "copy the whole thing" lead somewhere; the exact
# reason a byte was wrong does not.
_NOT_A_CODE = "That doesn't look like a meal code. Copy it again from whoever sent it."
_INCOMPLETE = (
    "That code is cut short. Copy the whole thing -- codes are long and chat "
    "apps sometimes trim them."
)
_TOO_LONG = "That code is longer than any meal code this app makes."
_FUTURE_VERSION = (
    "That code was made by a newer version of this app. Reload the page and try "
    "again."
)


class ShareCodeError(ValueError):
    """A code that cannot be read. The message is written to be shown to a user.

    Subclasses ValueError so a caller that forgets to catch it still fails as a
    bad value rather than as something exotic -- the same reasoning behind
    pydantic's ValidationError doing it.
    """


def _round_floats(value: Any) -> Any:
    """Round every float in a nested structure to SHARE_DECIMALS.

    Recursive and type-blind on purpose: this module does not know which keys
    are macros and which are weights, and every number a meal payload carries
    wants the same treatment. bool is checked before the numeric branch because
    bool is a subclass of int and `round(True)` is a silent 1.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, SHARE_DECIMALS)
    if isinstance(value, Mapping):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_floats(item) for item in value]
    return value


def encode_share_code(payload: Mapping[str, Any]) -> str:
    """Encode a JSON-serializable mapping as a share code.

    Deterministic: the same payload always produces the same string, because
    someone copying the same meal twice and getting two different codes would
    read as a bug even though both would work.

    Raises ShareCodeError if the payload holds a non-finite float. That is
    `allow_nan=False` doing the same job it does in the JSON export: inf and nan
    are not JSON, and writing the bare token `Infinity` here would mint a code
    that only this app's own decoder could read and that would then carry inf
    into a Float column on the way back in.
    """
    try:
        raw = json.dumps(
            _round_floats(payload),
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ).encode("utf-8")
    except ValueError as exc:  # non-finite float, or a type json cannot write
        raise ShareCodeError("That meal has a value that can't be shared.") from exc

    # Level 9 because the payload is capped at 64 KiB and this runs once per tap.
    # Maximum compression is free here in a way it never is on a stream, and the
    # difference is what keeps a 30-item meal a pasteable 330 characters rather
    # than an unpasteable 3,500.
    packed = zlib.compress(raw, 9)
    body = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return f"{SHARE_VERSION}{_SEPARATOR}{body}"


def decode_share_code(code: str) -> dict[str, Any]:
    """Decode a share code back into the mapping it was made from.

    Every failure path raises ShareCodeError carrying a sentence meant for the
    person who pasted it. This validates the *encoding* only -- that the string
    is a code this app could have produced and that it holds a JSON object. What
    the object contains is the caller's problem, and the router hands it to a
    pydantic model precisely so that a code cannot express anything a normal
    save could not.
    """
    # Chat clients wrap long strings, and a paste out of one arrives with
    # newlines, CRLFs and sometimes U+00A0 in it. All of those are str.isspace(),
    # so split/join removes them. U+200B ZERO WIDTH SPACE is NOT, deliberately
    # falls through to the base64 step below, and is refused there -- which is
    # correct, but is why that step's except clause has to catch ValueError and
    # not only binascii.Error.
    cleaned = "".join(code.split())

    if len(cleaned) > MAX_CODE_CHARS:
        raise ShareCodeError(_TOO_LONG)

    version, separator, body = cleaned.partition(_SEPARATOR)
    if not separator or not body:
        raise ShareCodeError(_NOT_A_CODE)
    if version != SHARE_VERSION:
        # Only claim "newer app" for something shaped like one of our own tags.
        # Telling someone to reload because they pasted a paragraph would send
        # them off to fix the wrong thing.
        if version.startswith("MC") and version[2:].isdigit():
            raise ShareCodeError(_FUTURE_VERSION)
        raise ShareCodeError(_NOT_A_CODE)

    # Padding is stripped on the way out because a trailing "=" is the character
    # most likely to be eaten by a URL detector, and it carries no information.
    padded = body + "=" * (-len(body) % 4)
    try:
        # NOT urlsafe_b64decode: it takes no validate parameter, and without
        # validation every out-of-alphabet character is silently dropped, so
        # pasted prose would decode to junk instead of being refused here.
        # altchars translation happens before validation, so "+" and "/" are
        # also accepted -- free tolerance for a code some system re-encoded.
        packed = base64.b64decode(padded, altchars=b"-_", validate=True)
    except ValueError as exc:  # binascii.Error, and non-ASCII like U+200B
        raise ShareCodeError(_NOT_A_CODE) from exc

    raw = _decompress(packed)

    try:
        payload = json.loads(raw)
    except ValueError as exc:  # bad JSON, and UnicodeDecodeError on bad UTF-8
        raise ShareCodeError(_NOT_A_CODE) from exc

    # A JSON array or bare string is legal JSON and would sail through into a
    # caller expecting fields, so the shape is checked here rather than there.
    if not isinstance(payload, dict):
        raise ShareCodeError(_NOT_A_CODE)
    return payload


def _decompress(packed: bytes) -> bytes:
    """Inflate at most MAX_DECODED_BYTES, and tell truncation from garbage.

    The bound is `max_length`, not a timeout: decompression stops after the
    limit is produced rather than being interrupted partway through an
    already-allocated buffer. Reading one byte past the limit is what makes
    "too long" and "exactly at the limit" distinguishable at all.
    """
    stream = zlib.decompressobj()
    try:
        out = stream.decompress(packed, MAX_DECODED_BYTES + 1)
    except zlib.error as exc:
        # NOTE zlib.error is not a ValueError, so it needs this clause of its
        # own. This is also where a single flipped byte lands: the Adler-32
        # check at the end of every zlib stream catches corruption for free,
        # which is the integrity guarantee a signature would otherwise be
        # reached for.
        raise ShareCodeError(_NOT_A_CODE) from exc

    if len(out) > MAX_DECODED_BYTES or stream.unconsumed_tail:
        raise ShareCodeError(_TOO_LONG)
    if not stream.eof:
        # The stream ended early: a complete one sets eof, and a corrupted one
        # raises above. This is the trimmed-by-a-chat-app case.
        raise ShareCodeError(_INCOMPLETE)
    if stream.unused_data:
        # A complete stream with bytes appended after it. Without this check
        # those bytes are simply ignored and the code decodes happily.
        raise ShareCodeError(_NOT_A_CODE)
    return out
