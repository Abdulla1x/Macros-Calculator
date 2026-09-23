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

⚠ TWO PINGERS SINCE 2026-09-23, AND THE PANEL HAS TO SAY WHICH ONE LANDED.
cron-job.org's pings used to wake a sleeping instance: measured 2026-09-04, a
request abandoned at its 30 s cap still started the boot, and a request 60 s
later answered in 0.89 s. Since 2026-09-11 the same job is refused with a ~1.3 s
503 that starts nothing -- while an ordinary browser from a home connection
still wakes it. On 2026-09-16 pings had been failing since 05:03 and the owner's
own page load woke the service at 08:05: same sleep duration, opposite outcome,
so the discriminator is the CLIENT and not the waiting. A second pinger with a
different client profile (`homecron`, a cron on an always-on home machine)
therefore runs alongside the first. Counting both against one number would make
it impossible to say which of them is keeping the service up, and that is now
the whole question -- hence PING_SOURCES and the per-source rows below.

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

from .schemas import KeepWarmStatus, PingSource

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

# The query markers a recognised pinger carries: /api/health?src=<marker>.
#
#   keepwarm   the cron-job.org job
#   homecron   a cron on the owner's always-on home machine, added 2026-09-23
#
# An ALLOWLIST rather than "count whatever src happens to say". /api/health is
# public and unauthenticated and `src` is deliberately unvalidated, so a dict
# keyed on the raw value would grow one entry per distinct string anybody sent
# it -- an unbounded map behind an open endpoint. Two names are the whole set.
#
# Deliberately NOT applied to keep-warm.yml's manual wake button -- pressing that
# is a person keeping the server up, not a scheduler doing its job, and letting
# it inflate these counts would mask exactly the failure they exist to find.
SCHEDULER_MARKER = "keepwarm"
HOME_CRON_MARKER = "homecron"
PING_SOURCES = (SCHEDULER_MARKER, HOME_CRON_MARKER)

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
# The subset carrying any marker in PING_SOURCES, counted TOGETHER. This is the
# number the verdict is computed from, and a union on purpose: the verdict
# answers "is anything keeping this awake", which does not care which pinger
# managed it. Which one is landing is the per-source detail below.
_scheduler_pings = 0
_last_scheduler_at: datetime | None = None
_last_scheduler_monotonic: float | None = None
_longest_scheduler_gap_s: float | None = None
# The same pings split by source, because two pingers answering to one counter
# are indistinguishable -- and once one of them is the suspect, "something is
# warming it" stops being the question. Keys are only ever PING_SOURCES.
_pings_by_source: dict[str, int] = {}
_last_at_by_source: dict[str, datetime] = {}
_last_monotonic_by_source: dict[str, float] = {}


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
        # Cleared rather than rebuilt with zero values: snapshot() fills a row
        # for every name in PING_SOURCES regardless, so an absent key and a
        # zero already mean the same thing to the only reader there is.
        _pings_by_source.clear()
        _last_at_by_source.clear()
        _last_monotonic_by_source.clear()


def uptime_s() -> float:
    """How long this process has been able to serve requests.

    Zero if mark_boot() has somehow not run yet -- the same choice snapshot()
    makes, and for the same reason: the callers of this are a diagnostic panel
    and a timing column, neither of which should be able to raise.

    snapshot() deliberately does NOT call this -- it reads every figure it
    reports under a single lock so they cannot disagree with each other, and it
    has a local of the same name for the value it takes there.
    """
    with _lock:
        booted = _booted_monotonic
    return 0.0 if booted is None else time.monotonic() - booted


def record_health_check(src: str | None = None) -> None:
    """One more /api/health request. The whole write path of this module.

    `src` is the request's raw query marker, counted only when it is one of
    PING_SOURCES. Everything else -- Render's platform monitor every ~4 s, a
    logged-out page's warm-up ping, the manual wake button, an arbitrary string
    from the open internet -- lands in the raw total and nothing more.

    A recognised ping moves the union counters the verdict reads AND its own
    source's, under one lock, so the two can never disagree about a ping that
    arrived while the panel was being rendered.

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
        if src is None or src not in PING_SOURCES:
            return
        if _last_scheduler_monotonic is not None:
            gap = now - _last_scheduler_monotonic
            if _longest_scheduler_gap_s is None or gap > _longest_scheduler_gap_s:
                _longest_scheduler_gap_s = gap
        stamped = _display_now()
        _scheduler_pings += 1
        _last_scheduler_at = stamped
        _last_scheduler_monotonic = now
        _pings_by_source[src] = _pings_by_source.get(src, 0) + 1
        _last_at_by_source[src] = stamped
        _last_monotonic_by_source[src] = now


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
        pings_by_source = dict(_pings_by_source)
        last_at_by_source = dict(_last_at_by_source)
        last_monotonic_by_source = dict(_last_monotonic_by_source)

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

    # A row for every name in PING_SOURCES, including one that has never been
    # seen. A zero beside a pinger's name is exactly the signal the operator
    # wants, and a row that simply vanished while that pinger was down would
    # hide the only thing this panel exists to show.
    ping_sources = []
    for name in PING_SOURCES:
        last_monotonic = last_monotonic_by_source.get(name)
        ping_sources.append(
            PingSource(
                source=name,
                pings=pings_by_source.get(name, 0),
                last_ping_at=last_at_by_source.get(name),
                seconds_since_last_ping=(
                    None
                    if last_monotonic is None
                    else int(now_monotonic - last_monotonic)
                ),
            )
        )

    local_now = now_utc.astimezone(window_tz())
    in_window = in_window_at(local_now)

    return KeepWarmStatus(
        booted_at=booted_at or now_utc,
        uptime_seconds=int(uptime_s),
        health_checks=checks,
        scheduler_pings=scheduler_pings,
        ping_sources=ping_sources,
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
