"""Supplements: the list you keep, and the doses you tick off each day.

The third daily tracker, and the first with two tables. Water is event rows and
steps is one row per day; a supplement is a *list* whose items are ticked, so
`supplements` holds the schedule and `supplement_logs` holds one row per dose
taken. A generic daily_logs table would have bought a discriminator column in
every query, the export and the isolation suite and saved nothing.

**Reminders are in-app only, and that is a platform fact rather than a
shortcut.** Web Push on Android routes through FCM, which requires Google Play
Services; local scheduled notifications need the Notification Triggers API,
which no browser ever shipped. So there are no VAPID keys, no subscription
table and no server-side scheduler here -- nothing that could only be tested on
a delivery path this project cannot reach. What the card gets instead is a
due/overdue read computed against the browser's own clock.

**Nothing here may recompute calorie targets.** Both sibling trackers carry the
same warning and both are pinned by a source-level test, because
`routers/weights.py` and `routers/settings.py` do call `apply_auto_targets` and
copying one of them is the easy mistake. A supplement is not an input to any
target, and Phase 5's measurement window stops at *yesterday* precisely so that
what you log today cannot move the goal you are eating towards today.
"""
import json
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Supplement as SupplementRow
from ..models import SupplementLog as SupplementLogRow
from ..models import User
from ..schemas import (
    MAX_SUPPLEMENTS,
    Supplement,
    SupplementCreate,
    SupplementDay,
    SupplementLogCreate,
    SupplementSlot,
)

router = APIRouter(prefix="/api/supplements", tags=["supplements"])


def _supplement_out(row: SupplementRow) -> Supplement:
    """Build the response explicitly rather than reading attributes off the row.

    The API field is `times: list[str]`; the column is `times_json` (TEXT). A
    from_attributes model would be handed a JSON *string* for a list field and
    500 every read. Fourth appearance of that mismatch -- `UserOut.is_admin`
    returned a silent False, `MealTemplate.items` a silent [], `Settings`
    would have 500'd -- and it is closed the same way each time: one
    construction site, so there is no second place to forget.
    """
    return Supplement(
        id=row.id,
        name=row.name,
        dose=row.dose,
        times=json.loads(row.times_json),
        active=row.active,
        created_at=row.created_at,
    )


def _owned(db: Session, user_id: int, supplement_id: int) -> SupplementRow:
    """The caller's supplement, or 404.

    Every read and write of a supplement goes through this. `supplement_id`
    arrives from the client on the log endpoints too, which makes it the same
    shape as the `meal_id` link in ai.py: an id the caller chose, pointing at a
    row someone else may own. Scoping on user_id here is what makes a guessed id
    a 404 rather than a write into another account's history.
    """
    row = db.scalars(
        select(SupplementRow).where(
            SupplementRow.id == supplement_id, SupplementRow.user_id == user_id
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplement not found")
    return row


def _day(db: Session, user_id: int, day: date_type) -> SupplementDay:
    """One day's doses: what was scheduled, what was taken, in time order.

    The slot list is the **union** of two sources, and the union is the whole
    reason this function is more than a loop:

    1. every time on every *active* supplement that already existed on that
       date, and
    2. every time that already has a log row on that date, whatever the
       supplement's schedule or paused state says now.

    Rule 1 stops a supplement added today from making every past day read as a
    missed dose. Rule 2 stops two ordinary actions -- pausing something, or
    moving a dose from 08:00 to 09:00 -- from turning a day that was fully taken
    into "2 of 3" months after the fact. History is what happened; the schedule
    is only what was meant to.

    Two queries regardless of how many supplements exist, both bounded by
    MAX_SUPPLEMENTS.
    """
    rows = db.scalars(
        select(SupplementRow).where(SupplementRow.user_id == user_id)
    ).all()
    by_id = {row.id: row for row in rows}

    taken = {
        (log.supplement_id, log.time_of_day)
        for log in db.scalars(
            select(SupplementLogRow).where(
                SupplementLogRow.user_id == user_id,
                SupplementLogRow.date == day,
            )
        ).all()
    }

    slots: list[SupplementSlot] = []
    scheduled: set[tuple[int, str]] = set()

    for row in rows:
        if not row.active:
            continue
        # created_at is naive UTC while `day` is the user's local date, so a
        # supplement added late in the evening at a positive offset can count
        # for the day before. One day, one direction -- the same skew
        # FUTURE_DATE_GRACE_DAYS already exists for, and not worth storing a
        # timezone to close.
        if row.created_at is not None and row.created_at.date() > day:
            continue
        for time_of_day in json.loads(row.times_json):
            key = (row.id, time_of_day)
            scheduled.add(key)
            slots.append(
                SupplementSlot(
                    supplement_id=row.id,
                    name=row.name,
                    dose=row.dose,
                    time=time_of_day,
                    taken=key in taken,
                )
            )

    for supplement_id, time_of_day in sorted(taken - scheduled):
        # by_id cannot miss -- the log's FK cascades with its supplement -- but
        # a missing row here would be a slot with no name to render.
        row = by_id.get(supplement_id)
        if row is None:
            continue
        slots.append(
            SupplementSlot(
                supplement_id=row.id,
                name=row.name,
                dose=row.dose,
                time=time_of_day,
                taken=True,
                off_schedule=True,
            )
        )

    # By time, then name: the card reads as the day runs. Sorted here rather
    # than in the client for the reason the water goal is derived server-side --
    # one definition of the order, not two that can drift.
    slots.sort(key=lambda slot: (slot.time, slot.name.lower()))

    return SupplementDay(
        date=day,
        taken=sum(1 for slot in slots if slot.taken),
        scheduled=len(slots),
        slots=slots,
    )


# --- The day view and its check-offs -----------------------------------------
#
# These are declared BEFORE the /{supplement_id} routes below, and the order is
# load-bearing. `DELETE /api/supplements/log` and
# `DELETE /api/supplements/{supplement_id}` are the same shape; FastAPI matches
# in declaration order, and the id route would try to parse "log" as an int and
# answer 422 rather than falling through to this one.


@router.get("/day", response_model=SupplementDay)
def get_supplement_day(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One day of doses. Defaults to the server's today when no date is given.

    Always 200, never 404: a day with nothing scheduled is an ordinary state --
    for every account that has not added a supplement, it is the only state --
    and the empty slot list is the correct answer rather than an error.
    """
    return _day(db, user.id, date or date_type.today())


@router.post("/log", response_model=SupplementDay)
def take_dose(
    entry: SupplementLogCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tick one dose. Idempotent, and 200 rather than 201 for that reason.

    A tick is a *state* -- "the 08:00 dose is taken" -- not an event the way a
    glass of water is, so tapping the same box twice is the same fact rather
    than a second dose. The unique index enforces that, and a duplicate is
    swallowed here instead of surfacing as a 409 the client could not act on:
    the box was already ticked, which is exactly what the caller wanted.

    Deliberately returns the whole day rather than the row, unlike POST
    /api/water. The tick list *is* the day's state, and this is a card you tap
    several boxes on in a row -- re-fetching after each one would double the
    requests against a free-tier instance for no new information.

    The time is NOT checked against the supplement's current schedule. Ticking
    a dose you took at a time you have since moved is a correction, not an
    error, and `_day` already renders such a slot as off-schedule history.
    """
    _owned(db, user.id, entry.supplement_id)

    db.add(
        SupplementLogRow(
            user_id=user.id,
            supplement_id=entry.supplement_id,
            date=entry.date,
            time_of_day=entry.time,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Already ticked. The unique index is doing its job; there is nothing
        # to tell the user about.
        db.rollback()

    return _day(db, user.id, entry.date)


@router.delete("/log", response_model=SupplementDay)
def untake_dose(
    supplement_id: int,
    date: date_type,
    time: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Un-tick one dose. Query params, mirroring DELETE /api/steps?date=.

    Idempotent for the same reason the tick is: un-ticking a box that is already
    clear is the state the caller asked for. The ownership check still runs
    first, so another account's supplement id is a 404 rather than a silent
    success that leaks whether the id exists.
    """
    _owned(db, user.id, supplement_id)

    row = db.scalars(
        select(SupplementLogRow).where(
            SupplementLogRow.user_id == user.id,
            SupplementLogRow.supplement_id == supplement_id,
            SupplementLogRow.date == date,
            SupplementLogRow.time_of_day == time,
        )
    ).first()
    if row is not None:
        db.delete(row)
        db.commit()

    return _day(db, user.id, date)


# --- Managing the list -------------------------------------------------------


@router.get("", response_model=list[Supplement])
def list_supplements(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """The whole list, paused ones included.

    This feeds the Settings editor, which is the only place a paused supplement
    can be un-paused -- filtering them out here would make pausing a one-way
    door. The dashboard card reads /day instead, which applies `active`.
    """
    rows = db.scalars(
        select(SupplementRow)
        .where(SupplementRow.user_id == user.id)
        .order_by(func.lower(SupplementRow.name))
    ).all()
    return [_supplement_out(row) for row in rows]


@router.post("", response_model=Supplement, status_code=201)
def create_supplement(
    body: SupplementCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add one. 409 if the name is already taken, case-insensitively.

    Not an upsert, unlike POST /api/meal_templates. Saving a template again is
    a real workflow -- the button says "save as template" and means "replace
    it" -- where there is no such flow here: the Settings editor PUTs an
    existing row by id. Two rows both called "Magnesium" on a tick list is a
    state you cannot act on, since neither says which one you already took.
    """
    count = db.scalar(
        select(func.count())
        .select_from(SupplementRow)
        .where(SupplementRow.user_id == user.id)
    )
    # A named ceiling in the style of MAX_IMAGES, enforced here because a schema
    # cannot count rows. It carries no opinion about what anyone takes -- it
    # bounds a tick list to something a person can actually read through daily.
    if count >= MAX_SUPPLEMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"You can track up to {MAX_SUPPLEMENTS} supplements.",
        )

    row = SupplementRow(
        user_id=user.id,
        name=body.name,
        dose=body.dose,
        times_json=json.dumps(body.times),
        active=body.active,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # The expression index, not a pre-flight SELECT: a check-then-insert
        # has a race a unique constraint does not, and this is the same shape
        # signup uses for a duplicate email.
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'You already track "{body.name}".'
        )
    return _supplement_out(row)


@router.put("/{supplement_id}", response_model=Supplement)
def update_supplement(
    supplement_id: int,
    body: SupplementCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit one: rename, re-dose, reschedule, pause or resume.

    A full replace rather than a patch, and the opposite of PUT /api/settings.
    The asymmetry is not an inconsistency: settings is one shared row that old
    PWA bundles keep PUTting without newer keys, so a replace there would blank
    fields a stale client has never heard of. A supplement is a row the editor
    always holds in full, and every field on it is one the user typed.

    Rescheduling deliberately leaves existing log rows alone. They keep the time
    they were actually taken at, and `_day` still shows them -- moving them to
    the new time would be inventing a history that did not happen.
    """
    row = _owned(db, user.id, supplement_id)
    row.name = body.name
    row.dose = body.dose
    row.times_json = json.dumps(body.times)
    row.active = body.active
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'You already track "{body.name}".'
        )
    return _supplement_out(row)


@router.delete("/{supplement_id}", status_code=204)
def delete_supplement(
    supplement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove one, and every dose ever ticked for it.

    The check-offs go with it by CASCADE, which is why the client confirms with
    the count first. Pausing is the non-destructive option and is what the UI
    offers first; this is for something you are not merely off at the moment.
    """
    row = _owned(db, user.id, supplement_id)
    db.delete(row)
    db.commit()
