"""Numeric settings read from the environment, parsed so a typo cannot 500.

Every one of these is set in the Render dashboard, and `render.yaml` is not
synced to it -- the dashboard is the only source of truth, which makes it
exactly where a typo lives. These readers run inside request handlers, so an
unparseable value is not a config error at boot; it is a 500 on whichever
request happens to read it next, from code that has nothing visibly to do with
the setting.

Two rules, and they are the whole module:

* **Unreadable falls back, and logs.** The shipped default is a working value.
  Refusing to start, or raising mid-request, trades a small misconfiguration for
  a total outage. A silent fallback would be worse than either, which is why
  every one of them warns.
* **A value that closes a gate is never replaced by one that opens it.** A
  negative limit already blocked everything, so it clamps to 0 rather than
  reverting to the shipped default. Reverting would take a setting that was
  shutting something off and quietly switch it back on -- the opposite of what
  whoever typed it asked for.

Policy beyond that belongs at the call site, not here. Whether 0 means "off" or
"nonsense, use the default" differs per setting -- 0 is a legitimate kill switch
for AI_GLOBAL_DAILY_LIMIT and a lockout for ACCESS_TOKEN_DAYS -- so the parsers
answer only "what number is this", and each caller decides what the number means.
"""
import logging
import math
import os

logger = logging.getLogger(__name__)


def _raw(name: str) -> str:
    """The value, tolerating how dashboards mangle pasted input.

    A trailing newline or a pair of wrapping quotes survives a copy-paste into a
    web form far more often than anyone expects, and is invisible in a masked
    field. Same treatment `services/meal_ai.py` gives its string settings.
    """
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def env_int(name: str, default: int) -> int:
    """An integer setting, defaulting on anything unusable.

    A bare int() turned a typo in the Render dashboard -- AI_DAILY_LIMIT=2O,
    letter O -- into a ValueError mid-request and a 500 on every AI call,
    instead of degrading to the shipped default. Worse, global_daily_limit() is
    also read by the admin usage page: the one screen you would open to find out
    what broke.

    Zero is honoured rather than replaced, because for a limit it is a
    legitimate kill switch and quietly substituting the default would be the
    opposite of what the operator asked for. A negative clamps to 0 for the
    reason in the module docstring.

    try/except rather than a .isdigit() guard: the superscript two passes
    .isdigit() but raises inside int(), so that idiom accepts input it then
    crashes on. Asking int() what int() will do cannot be wrong about it.
    """
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s is not an integer (%r); using %s", name, raw, default)
        return default
    if value < 0:
        logger.warning("%s is negative (%s); treating as 0", name, value)
        return 0
    return value


def env_float(name: str, default: float) -> float:
    """A float setting, defaulting on anything unusable.

    Non-finite values are rejected as well as unparseable ones, and that is not
    hypothetical tidiness: float("inf") and float("nan") both parse happily, and
    an infinite ACCESS_TOKEN_DAYS then raises OverflowError inside timedelta --
    reinstating the exact 500 this function exists to prevent, one layer further
    from the value that caused it.

    No clamping here. Where a float setting is a duration, "less than or equal
    to zero" is not a gate being closed but a value that cannot mean anything,
    and the callers say so themselves.
    """
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s is not a number (%r); using %s", name, raw, default)
        return default
    if not math.isfinite(value):
        logger.warning("%s is not finite (%r); using %s", name, raw, default)
        return default
    return value
