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

⚠️ **RENDER HEALTH-CHECKS /api/health ITSELF, ROUGHLY EVERY 4 SECONDS.**
`healthCheckPath: /api/health` in render.yaml points its platform monitor at the
same route the scheduler uses. Measured in production 2026-09-04: 2,714 requests
across 3 h 12 m of uptime, a longest gap of 5 s, where cron-job.org at one ping
per 10 minutes can only account for 19 of them -- about 141x. So a bare count of
requests to this route says nothing whatever about the scheduler, and the first
version of this module reported it as though it did.

That is why the scheduler's URL carries `?src=keepwarm` and only marked requests
count as scheduler pings. A marker in the URL rather than a User-Agent guess:
Render's monitor hits the bare path, the two separate exactly, and nothing has
to be inferred from a header string that can change without notice.

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

# The query marker the cron-job.org job must carry: /api/health?src=keepwarm.
# Deliberately NOT applied to keep-warm.yml's manual wake button -- pressing that
# is a person keeping the server up, not the scheduler doing its job, and letting
# it inflate this count would mask exactly the failure the count exists to find.
SCHEDULER_MARKER = "keepwarm"

# Render stops a free service after 15 minutes without inbound traffic. Surviving
# longer than that means *something* kept it alive.
SPIN_DOWN_S = 15 * 60

# Below this, the request that rendered the page is almost certainly the one
# that woke the server -- 52.3 s of boot plus the page's own fetches.
COLD_START_SUSPECT_S = 120

_lock = threading.Lock()
_booted_at: datetime | None = None
_booted_monotonic: float | None = None
# Every request to /api/health, whoever made it. Kept only so the panel can say
# out loud that most of them are Render's monitor -- it is context, not a signal.
_checks = 0
# The subset carrying SCHEDULER_MARKER. This is the number that means something.
_scheduler_pings = 0
_last_scheduler_at: datetime | None = None
_last_scheduler_monotonic: float | None = None
_longest_scheduler_gap_s: float | None = None


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
    global _booted_at, _booted_monotonic, _checks, _scheduler_pings
    global _last_scheduler_at, _last_scheduler_monotonic, _longest_scheduler_gap_s
    with _lock:
        _booted_at = _display_now()
        _booted_monotonic = time.monotonic()
        _checks = 0
        _scheduler_pings = 0
        _last_scheduler_at = None
        _last_scheduler_monotonic = None
        _longest_scheduler_gap_s = None


def record_health_check(from_scheduler: bool = False) -> None:
    """One more /api/health request. The whole write path of this module.

    `from_scheduler` is whether the URL carried SCHEDULER_MARKER. Only those
    move the numbers the verdict is computed from; everything else -- Render's
    platform monitor every ~4 s, a logged-out page's warm-up ping, the manual
    wake button -- lands in the raw total and nothing more.

    Under a lock because FastAPI runs sync endpoints in a threadpool, so two
    requests can land at once, and `+= 1` is a read, an add and a store -- not
    one atomic step. At ~4 s intervals the lock costs nothing and removes the
    argument.
    """
    global _checks, _scheduler_pings
    global _last_scheduler_at, _last_scheduler_monotonic, _longest_scheduler_gap_s
    now = time.monotonic()
    with _lock:
        _checks += 1
        if not from_scheduler:
            return
        if _last_scheduler_monotonic is not None:
            gap = now - _last_scheduler_monotonic
            if _longest_scheduler_gap_s is None or gap > _longest_scheduler_gap_s:
                _longest_scheduler_gap_s = gap
        _scheduler_pings += 1
        _last_scheduler_at = _display_now()
        _last_scheduler_monotonic = now


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
    scheduler_pings: int,
    seconds_since_scheduler_ping: float | None,
    in_window: bool,
) -> str:
    """What the numbers together say about the scheduler.

    Pure, and separate from the state above, so every branch is reachable in a
    test without a fake clock or a monkeypatched module global.

    Uptime alone cannot distinguish the scheduler from ordinary user traffic,
    which is why marked pings are counted at all: a server up for six hours with
    no scheduler ping in the last fifteen minutes is being kept alive by somebody
    using the app, and the moment they stop it will sleep.

    Deliberately reads SCHEDULER pings, never the raw health-check total. Render
    health-checks /api/health every ~4 s, so the total can never go stale and a
    verdict computed from it could never say anything but "warm".

    `awaiting_marked_pings` exists because the marker is half-deployed by
    construction: this code ships before anyone can edit the cron-job.org job to
    add `?src=keepwarm`, and in that gap a healthy scheduler produces zero marked
    pings. Reporting that as `pings_missing` would be a guaranteed false alarm on
    the very deploy that introduces it -- the same mistake the `cold` verdict was
    already rewritten to avoid. Never seen one is not the same as stopped seeing
    them, so it gets its own state, and it clears itself.
    """
    if not in_window:
        return "outside_window"
    if uptime_s < COLD_START_SUSPECT_S:
        return "cold"
    if uptime_s < SPIN_DOWN_S:
        return "warming"
    if scheduler_pings == 0:
        return "awaiting_marked_pings"
    # scheduler_pings > 0 already implies this is not None; the check keeps the
    # function total rather than resting on a caller's invariant.
    if (
        seconds_since_scheduler_ping is None
        or seconds_since_scheduler_ping > SPIN_DOWN_S
    ):
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
        scheduler_pings = _scheduler_pings
        last_scheduler_at = _last_scheduler_at
        last_scheduler_monotonic = _last_scheduler_monotonic
        longest_gap = _longest_scheduler_gap_s

    # mark_boot() runs in the lifespan handler, so this is only reachable if a
    # request somehow arrived before it did. Reporting zero uptime is honest in
    # that case, and much better than raising from the one page you would open
    # to find out what is wrong -- the same argument env.py makes about the
    # admin page being the screen that must not 500.
    uptime_s = 0.0 if booted_monotonic is None else now_monotonic - booted_monotonic
    since_last = (
        None
        if last_scheduler_monotonic is None
        else now_monotonic - last_scheduler_monotonic
    )

    local_now = now_utc.astimezone(window_tz())
    in_window = in_window_at(local_now)

    return KeepWarmStatus(
        booted_at=booted_at or now_utc,
        uptime_seconds=int(uptime_s),
        health_checks=checks,
        scheduler_pings=scheduler_pings,
        last_scheduler_ping_at=last_scheduler_at,
        seconds_since_scheduler_ping=None if since_last is None else int(since_last),
        longest_scheduler_gap_seconds=None if longest_gap is None else int(longest_gap),
        window_start_hour=WINDOW_START_HOUR,
        window_end_hour=WINDOW_END_HOUR,
        window_tz=WINDOW_TZ,
        window_local_time=local_now.strftime("%H:%M"),
        in_window=in_window,
        spin_down_seconds=SPIN_DOWN_S,
        verdict=verdict_for(
            uptime_s, scheduler_pings, since_last, in_window
        ),
    )
