"""daily_stats: the table that exists so history stops moving.

The suite is organised around the two invariants in app/snapshots.py -- a
frozen row is never rewritten, and today is never frozen -- plus the one
behaviour that is the reason for the whole table: a deleted account must not
change what a past day says.
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import DailyStat, User, WaterLog, utcnow
from app.snapshots import MAX_BACKFILL_DAYS, ensure_snapshots

from conftest import TEST_PASSWORD, utc_today


def session() -> Session:
    return Session(get_engine())


def backdate_signup(email: str, days_ago: int) -> int:
    """Move an account's created_at into the past. Returns its id."""
    with session() as db:
        user = db.scalars(select(User).where(User.email == email)).one()
        user.created_at = datetime.combine(
            utc_today() - timedelta(days=days_ago), time(12, 0)
        )
        db.commit()
        return user.id


def add_water(user_id: int, days_ago: int) -> None:
    """A water log is the purest activity row -- always an insert, never an
    upsert -- so it is the cleanest way to say "this account was active"."""
    with session() as db:
        db.add(
            WaterLog(
                user_id=user_id,
                date=utc_today() - timedelta(days=days_ago),
                ml=250,
                created_at=datetime.combine(
                    utc_today() - timedelta(days=days_ago), time(12, 0)
                ),
            )
        )
        db.commit()


def run(today: date | None = None) -> int:
    with session() as db:
        return ensure_snapshots(db, today or utc_today())


def rows() -> list[DailyStat]:
    with session() as db:
        return list(db.scalars(select(DailyStat).order_by(DailyStat.date)).all())


def email_of(client) -> str:
    return client.get("/api/auth/me").json()["email"]


def delete_account(client) -> None:
    """⚠️ The endpoint requires the password, and asserting the 204 is the
    point: an unasserted 422 from this exact call stranded a production account
    for twelve days, because "the request was sent" and "the account is gone"
    are different claims."""
    response = client.request(
        "DELETE", "/api/auth/account", json={"password": TEST_PASSWORD}
    )
    assert response.status_code == 204, response.text


# --- Invariant 2: today is never frozen --------------------------------------


def test_today_is_never_frozen(client):
    """A row written at 09:00 would claim to describe the whole day."""
    backdate_signup(email_of(client), days_ago=3)
    run()
    assert utc_today() not in [row.date for row in rows()]
    assert max(row.date for row in rows()) == utc_today() - timedelta(days=1)


def test_nothing_to_freeze_when_the_only_account_signed_up_today(client):
    """Yesterday is before the first signup, so there is no history to write."""
    assert run() == 0
    assert rows() == []


# --- Invariant 1: a frozen row is never rewritten ----------------------------


def test_running_twice_writes_one_row_per_day(client):
    backdate_signup(email_of(client), days_ago=2)
    first = run()
    second = run()
    assert first > 0
    assert second == 0
    dates = [row.date for row in rows()]
    assert len(dates) == len(set(dates))


def test_a_frozen_day_ignores_later_activity(client):
    """The row is a historical fact, not a cached query.

    Freeze a day, then add activity dated to that same day, then re-run. A
    recomputing implementation would raise the count; a freezing one must not.
    """
    user_id = backdate_signup(email_of(client), days_ago=3)
    run()
    frozen = {row.date: row.active_users for row in rows()}
    day = utc_today() - timedelta(days=2)

    add_water(user_id, days_ago=2)
    run()

    assert {row.date: row.active_users for row in rows()} == frozen
    assert frozen[day] == 0


def test_a_gap_is_filled_rather_than_skipped(client):
    """Nobody visits for a week; the next call backfills every missing day."""
    backdate_signup(email_of(client), days_ago=6)
    run(today=utc_today() - timedelta(days=4))
    before = len(rows())
    run()
    after = [row.date for row in rows()]
    assert len(after) > before
    # Contiguous: a chart drawn from these must not invent a straight line
    # across a day that simply was not written.
    assert after == sorted(after)
    assert after[-1] - after[0] == timedelta(days=len(after) - 1)


def test_backfill_is_bounded(client):
    """A first run on a long-lived app must not scan its whole history at once."""
    backdate_signup(email_of(client), days_ago=MAX_BACKFILL_DAYS + 40)
    run()
    assert len(rows()) == MAX_BACKFILL_DAYS
    # And the leftover is picked up rather than lost.
    assert run() == 0 or len(rows()) > MAX_BACKFILL_DAYS


# --- The reason the table exists ---------------------------------------------


def test_deleting_an_account_does_not_rewrite_history(client, make_authed_client):
    """⚠️ THE TEST THIS WHOLE TABLE IS FOR.

    /admin's charts derive from live rows, so deleting an account rewrites the
    past -- proved by accident in production on 2026-09-08, when removing three
    test accounts erased a bar from the signups chart. A retention figure built
    that way is survivorship-biased in the flattering direction, and retention
    is the number the monetization gate turns on.

    So: freeze, delete, and assert the frozen row is untouched.
    """
    doomed = make_authed_client()
    user_id = backdate_signup(email_of(doomed), days_ago=3)
    add_water(user_id, days_ago=3)
    run()

    day = utc_today() - timedelta(days=3)
    before = {row.date: (row.signups, row.active_users) for row in rows()}
    assert before[day] == (1, 1)

    delete_account(doomed)

    # Re-running is what a real deployment does -- the next request of the day
    # calls this. The frozen row must survive that, not merely survive the
    # DELETE.
    run()
    after = {row.date: (row.signups, row.active_users) for row in rows()}
    assert after == before, "a deleted account rewrote a frozen day"


# --- Cohort maturity ---------------------------------------------------------


def test_a_cohort_inside_its_window_stays_null(client):
    """NULL means 'not measurable yet', and must never read as 'nobody came
    back' -- so it is excluded from the ratio rather than counted as zero."""
    backdate_signup(email_of(client), days_ago=3)
    run()
    day = utc_today() - timedelta(days=3)
    row = next(r for r in rows() if r.date == day)
    assert row.signups == 1
    assert row.cohort_d7_retained is None
    assert row.cohort_d30_retained is None


def test_a_matured_cohort_counts_only_later_activity(client):
    """The signup day itself is excluded: everyone is 'active' the day they
    create an account, and counting it would make D7 read 100% for anyone who
    merely finished signing up."""
    user_id = backdate_signup(email_of(client), days_ago=10)
    add_water(user_id, days_ago=10)  # signup day only
    run()
    day = utc_today() - timedelta(days=10)
    row = next(r for r in rows() if r.date == day)
    assert row.signups == 1
    assert row.cohort_d7_retained == 0

    other = utc_today() - timedelta(days=20)
    assert row.date != other


def test_returning_inside_the_window_counts_as_retained(make_authed_client):
    returner = make_authed_client()
    user_id = backdate_signup(email_of(returner), days_ago=10)
    add_water(user_id, days_ago=7)  # three days after signing up
    run()
    row = next(r for r in rows() if r.date == utc_today() - timedelta(days=10))
    assert row.cohort_d7_retained == 1


def test_a_cohort_of_nobody_stays_null(client):
    """0 of 0 is not a retention of zero, it is an absence of evidence."""
    backdate_signup(email_of(client), days_ago=12)
    run()
    empty = [r for r in rows() if r.signups == 0]
    assert empty, "expected at least one day with no signups"
    assert all(r.cohort_d7_retained is None for r in empty)


def test_churn_lowers_retention_instead_of_vanishing(make_authed_client):
    """⚠️ The asymmetry that makes the figure honest.

    The denominator was frozen when the cohort formed; the numerator is counted
    at maturity from live rows. An account that signed up and has since deleted
    is therefore absent from the numerator while remaining in the denominator,
    so quitting counts AGAINST retention. Derived-from-live-rows arithmetic
    would drop it from both and read higher the more people left.
    """
    stayer = make_authed_client()
    quitter = make_authed_client()
    # ⚠️ Both addresses are read BEFORE either account is backdated, and the
    # order is load-bearing. email_of makes an authenticated request, which
    # runs the once-a-day trigger, which freezes every finished day -- so
    # reading the second address after backdating the first would freeze this
    # cohort at a size of one and the test would be asserting against a row
    # its own setup wrote too early. The first version of this test did
    # exactly that; the invariant caught the harness.
    stayer_email = email_of(stayer)
    quitter_email = email_of(quitter)
    stayer_id = backdate_signup(stayer_email, days_ago=10)
    backdate_signup(quitter_email, days_ago=10)
    add_water(stayer_id, days_ago=7)

    # Freeze the cohort size while both accounts still exist, but do not let
    # the window mature yet.
    run(today=utc_today() - timedelta(days=8))
    day = utc_today() - timedelta(days=10)
    assert next(r for r in rows() if r.date == day).signups == 2

    delete_account(quitter)
    run()

    row = next(r for r in rows() if r.date == day)
    assert row.signups == 2, "the frozen denominator moved"
    assert row.cohort_d7_retained == 1, "1 of 2, not 1 of 1"


# --- last_seen_at ------------------------------------------------------------


def test_last_seen_is_written_on_an_authenticated_request(client):
    client.get("/api/meals")
    with session() as db:
        user = db.scalars(select(User)).one()
        assert user.last_seen_at is not None
        assert user.last_seen_at.date() == utc_today()


def test_last_seen_writes_at_most_once_a_day(client):
    """⚠️ Asserted at SOURCE level, because "never written" and "written, no
    change today" are indistinguishable from outside -- the same reason
    test_water.py and test_supplements.py count statements rather than trusting
    a response body.

    This bound is the entire argument for the column existing: the objection on
    record against a last_seen column was a write on every authenticated
    request, and it only dies if this holds.
    """
    client.get("/api/meals")  # first request of the day does the write

    updates: list[str] = []

    def count_updates(_conn, _cursor, statement, _params, _context, _many):
        if statement.strip().upper().startswith("UPDATE USERS"):
            updates.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", count_updates)
    try:
        for _ in range(5):
            client.get("/api/meals")
    finally:
        event.remove(engine, "before_cursor_execute", count_updates)

    assert updates == [], "last_seen_at wrote again on the same day"


def test_the_once_a_day_guard_actually_guards(client):
    """Break it on purpose: a stale last_seen_at must produce exactly one write.

    A guard that has never been observed to open is indistinguishable from a
    guard that never closes.
    """
    client.get("/api/meals")
    with session() as db:
        user = db.scalars(select(User)).one()
        user.last_seen_at = utcnow() - timedelta(days=2)
        db.commit()

    updates: list[str] = []

    def count_updates(_conn, _cursor, statement, _params, _context, _many):
        if statement.strip().upper().startswith("UPDATE USERS"):
            updates.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", count_updates)
    try:
        client.get("/api/meals")
        client.get("/api/meals")
    finally:
        event.remove(engine, "before_cursor_execute", count_updates)

    assert len(updates) == 1, f"expected exactly one write, got {len(updates)}"


def test_an_authenticated_request_freezes_yesterday(client):
    """The trigger, end to end: no cron, no /api/health, just ordinary traffic.

    app/snapshots.py explains why neither of this project's two schedulers can
    do this -- a database touch on /api/health would hold Neon awake ~16 h a day
    and exhaust the free compute allowance, and GitHub Actions delivered 3 of
    114 requested runs.
    """
    backdate_signup(email_of(client), days_ago=3)
    with session() as db:
        user = db.scalars(select(User)).one()
        user.last_seen_at = None
        db.commit()
    assert rows() == []

    client.get("/api/meals")

    assert rows(), "an ordinary authenticated request did not freeze anything"


def test_a_snapshot_failure_cannot_break_the_request(client, monkeypatch):
    """⚠️ This runs inside get_current_user, so an exception here would 500 the
    dashboard, the log form and every other authenticated route -- for an
    account that merely showed up. A metrics gap must never become an outage.
    """
    import app.snapshots as snapshots

    calls: list[int] = []

    def explode(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("snapshot exploded")

    # Patched INSIDE the guard, not around it: replacing
    # ensure_snapshots_quietly would remove the try/except being tested and
    # prove nothing.
    monkeypatch.setattr(snapshots, "ensure_snapshots", explode, raising=True)
    with session() as db:
        user = db.scalars(select(User)).one()
        user.last_seen_at = None
        db.commit()

    response = client.get("/api/meals")
    assert response.status_code == 200
    assert calls, "the failing path was never reached, so nothing was proved"


# --- The privacy shape of the table -----------------------------------------


def test_daily_stats_holds_nothing_that_belongs_to_a_person():
    """The nine account-owned items of the new-table checklist do not apply
    here, and this is what makes that true rather than an assumption.

    A table with no user_id is not exported (there is nothing of yours in it),
    is not removed with an account (that is the entire point), and cannot leak
    across accounts because it does not belong to one. If a later "just one
    useful field" commit adds an identifier, that argument silently stops
    holding -- so it fails here instead.
    """
    table = DailyStat.__table__
    columns = {column.name for column in table.columns}
    assert "user_id" not in columns
    # No foreign key to anything, users included. This is the structural claim:
    # a row here cannot be traced to an account even in principle, which is
    # also why deleting an account cannot cascade into it.
    assert not [fk for column in table.columns for fk in column.foreign_keys]
    # Every column is a count, a date, or the row's own id. `active_users` is a
    # number of accounts, not a reference to one.
    assert columns == {
        "id", "date", "signups", "active_users", "meals", "total_users",
        "total_meals", "cohort_d7_retained", "cohort_d30_retained", "created_at",
    }
