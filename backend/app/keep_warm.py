"""Is the keep-warm pinger actually landing? In-memory, and deliberately so.

Render's free plan stops this service after 15 minutes with no inbound traffic,
and the next visitor pays for a full boot -- 52.30 s median, measured over ten
consecutive cold starts on 2026-09-03. A scheduler at cron-job.org sends one
request every 10 minutes across a daytime window to stop that timer expiring.

Its dashboard can say a request was made. It cannot say whether the server was
already awake, which is the only thing anyone actually wants to know. That is
what this module answers, and **uptime is the signal**: /admin reporting *up 10
hours* at 3 PM proves the pings are landing; *up 40 seconds* proves they are
not, because the page load was itself the cold start.

⚠ NOTHING HERE IS PERSISTED, AND WRITING IT TO POSTGRES IS THE CHANGE THAT
BREAKS THE APP. Recording pings to the database is the obvious implementation.
It would also make /api/health touch Neon on every ping, holding the database
awake ~16 hours a day: ~486 hours a month, ~122 CU-hours against a 100 CU-hour
free allowance, and Neon suspends the compute when they run out -- open
connections dropped, new ones refused, until the next billing period. A
multi-day outage caused entirely by the monitoring, with zero users. Accept that
every counter below is wiped at spin-down; uptime still answers the question.

Durations come from time.monotonic() and only the display timestamps come from
the wall clock. A container's clock can step -- an NTP correction just after
boot is exactly when it does -- and an uptime that jumped backwards would
mislead in precisely the situation this panel exists for.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schemas import KeepWarmStatus

logger = logging.getLogger(__name__)

# The window cron-job.org actually runs: 05:03 to 20:53 Asia/Dubai, every 10
# minutes. THAT dashboard is the source of truth; these three are the record of
# it, and the panel labels them as such. Constants rather than environment
# variables on purpose -- they govern a label, not behaviour, and a setting that
# looks live while governing nothing is worse than a value you have to commit.
# Changing the real schedule means editing the cron-job.org job.
WINDOW_START_HOUR = 5
WINDOW_END_HOUR = 21
WINDOW_TZ = "Asia/Dubai"

# Asia/Dubai is UTC+4 and does not observe DST, which is what makes a fixed
# offset a correct fallback rather than an approximation. Used only if the
# runtime has no tzdata: ZoneInfo would raise, and letting the zone silently
# become UTC would run the window four hours early -- the same failure
# keep-warm.yml's own zone check exists to prevent.
WINDOW_TZ_FALLBACK_OFFSET_HOURS = 4

# Render stops a free service after 15 minutes without inbound traffic. Surviving
# longer than that means *something* kept it alive.
SPIN_DOWN_S = 15 * 60

# Below this, the request that rendered the page is almost certainly the one
# that woke the server -- 52.3 s of boot plus the page's own fetches.
COLD_START_SUSPECT_S = 120

_lock = threading.Lock()
_booted_at: datetime | None = None
_booted_monotonic: float | None = None
_checks = 0
_last_check_at: datetime | None = None
_last_check_monotonic: float | None = None
_longest_gap_s: float | None = None


def _display_now() -> datetime:
    """A wall-clock stamp for the panel, to the second.

    Truncated because these two timestamps are read by a person, and
    microseconds on "when did this process boot" are noise dressed as
    precision. Nothing here is used for arithmetic -- every duration in this
    module comes from the monotonic clock.
    """
    return datetime.now(timezone.utc).replace(microsecond=0)


def mark_boot() -> None:
    """Start the clock. Called from the lifespan handler, not at import.

    Import time would count the seconds spent creating tables and reading
    settings as uptime. The number wanted here is "how long has this process
    been able to serve requests", because that is what a ping keeps alive.
    """
    global _booted_at, _booted_monotonic, _checks
    global _last_check_at, _last_check_monotonic, _longest_gap_s
    with _lock:
        _booted_at = _display_now()
        _booted_monotonic = time.monotonic()
        _checks = 0
        _last_check_at = None
        _last_check_monotonic = None
        _longest_gap_s = None


def record_health_check() -> None:
    """One more /api/health request. The whole write path of this module.

    Under a lock because FastAPI runs sync endpoints in a threadpool, so two
    pings can land at once, and `+= 1` is a read, an add and a store -- not one
    atomic step. The lock costs nothing at this rate and removes the argument.
    """
    global _checks, _last_check_at, _last_check_monotonic, _longest_gap_s
    now = time.monotonic()
    with _lock:
        if _last_check_monotonic is not None:
            gap = now - _last_check_monotonic
            if _longest_gap_s is None or gap > _longest_gap_s:
                _longest_gap_s = gap
        _checks += 1
        _last_check_at = _display_now()
        _last_check_monotonic = now


def window_tz() -> timezone | ZoneInfo:
    """The window's zone, or an equivalent fixed offset if tzdata is missing."""
    try:
        return ZoneInfo(WINDOW_TZ)
    except ZoneInfoNotFoundError:
        logger.warning(
            "No tzdata for %s; falling back to a fixed UTC+%s, which is exact "
            "for this zone because it does not observe DST.",
            WINDOW_TZ,
            WINDOW_TZ_FALLBACK_OFFSET_HOURS,
        )
        return timezone(timedelta(hours=WINDOW_TZ_FALLBACK_OFFSET_HOURS))


def in_window_at(local_time: datetime) -> bool:
    """Whether a local wall-clock time falls inside the ping window.

    Half-open, like the workflow's own check: the window runs from START:00 up
    to but not including END:00, so 05:00 is in and 21:00 is out. A window that
    wrapped past midnight is not supported here for the reason keep-warm.yml
    gives -- it is nearly every way the pair gets typed wrongly and nearly none
    of the ways it gets meant.
    """
    return WINDOW_START_HOUR <= local_time.hour < WINDOW_END_HOUR


def verdict_for(
    uptime_s: float,
    seconds_since_last_check: float | None,
    in_window: bool,
) -> str:
    """What the two numbers together say about the pinger.

    Pure, and separate from the state above, so every branch is reachable in a
    test without a fake clock or a monkeypatched module global.

    Uptime alone cannot distinguish the pinger from ordinary user traffic, which
    is why the health-check counter exists at all: a server up for six hours
    with no health check in the last fifteen minutes is being kept alive by
    somebody using the app, and the moment they stop it will sleep.
    """
    if not in_window:
        return "outside_window"
    if uptime_s < COLD_START_SUSPECT_S:
        return "cold"
    if uptime_s < SPIN_DOWN_S:
        return "warming"
    if seconds_since_last_check is None or seconds_since_last_check > SPIN_DOWN_S:
        return "pings_missing"
    return "warm"


def snapshot() -> KeepWarmStatus:
    """Everything the panel renders, read consistently under one lock."""
    now_monotonic = time.monotonic()
    now_utc = datetime.now(timezone.utc)
    with _lock:
        booted_at = _booted_at
        booted_monotonic = _booted_monotonic
        checks = _checks
        last_check_at = _last_check_at
        last_check_monotonic = _last_check_monotonic
        longest_gap = _longest_gap_s

    # mark_boot() runs in the lifespan handler, so this is only reachable if a
    # request somehow arrived before it did. Reporting zero uptime is honest in
    # that case, and much better than raising from the one page you would open
    # to find out what is wrong -- the same argument env.py makes about the
    # admin page being the screen that must not 500.
    uptime_s = 0.0 if booted_monotonic is None else now_monotonic - booted_monotonic
    since_last = (
        None if last_check_monotonic is None else now_monotonic - last_check_monotonic
    )

    local_now = now_utc.astimezone(window_tz())
    in_window = in_window_at(local_now)

    return KeepWarmStatus(
        booted_at=booted_at or now_utc,
        uptime_seconds=int(uptime_s),
        health_checks=checks,
        last_health_check_at=last_check_at,
        seconds_since_last_check=None if since_last is None else int(since_last),
        longest_gap_seconds=None if longest_gap is None else int(longest_gap),
        window_start_hour=WINDOW_START_HOUR,
        window_end_hour=WINDOW_END_HOUR,
        window_tz=WINDOW_TZ,
        window_local_time=local_now.strftime("%H:%M"),
        in_window=in_window,
        spin_down_seconds=SPIN_DOWN_S,
        verdict=verdict_for(uptime_s, since_last, in_window),
    )
