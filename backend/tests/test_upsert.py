"""The race a pre-flight SELECT cannot close.

Four endpoints look a row up, create it if it is missing, and commit. Send two
of those at once -- a double-tapped save, a retried request, two open tabs --
and both SELECTs miss, both INSERT, and the unique index refuses the second.
Before this, the loser's IntegrityError left the handler as a 500.

The suite is per-test SQLite on a temp file, which serialises writes, so a
thread-based test would prove nothing except that threads are slow. The
interleaving is forced instead: a second Session commits the winning row from
inside `build`, at precisely the point a concurrent request would have. The
IntegrityError that follows is raised by the real unique index, not a stub.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Food, MealTemplate, StepEntry, User
from app.routers import steps as steps_router
from app.upsert import upsert


def _only_user(session):
    return session.scalars(select(User)).one()


def _find_food(session, user_id, name):
    return session.scalars(
        select(Food).where(
            Food.user_id == user_id, func.lower(Food.name) == name.lower()
        )
    ).first()


def test_upsert_absorbs_a_concurrent_insert_and_applies_its_update(client):
    """The loser re-reads and writes on top, as if the two had arrived apart."""
    with Session(get_engine()) as session:
        user_id = _only_user(session).id

    attempts = []

    with Session(get_engine()) as session:

        def build():
            attempts.append(len(attempts) + 1)
            row = _find_food(session, user_id, "Chicken")
            if row is None:
                row = Food(user_id=user_id, name="Chicken", serving_size=100)
                session.add(row)
            row.calories = 165.0
            row.protein = 31.0
            # On the first pass only, let a concurrent request win the race in
            # the window between the SELECT above and the commit upsert is
            # about to attempt.
            if len(attempts) == 1:
                with Session(get_engine()) as other:
                    other.add(
                        Food(
                            user_id=user_id,
                            name="chicken",
                            serving_size=100,
                            calories=1.0,
                            protein=1.0,
                        )
                    )
                    other.commit()
            return row

        row = upsert(session, build)
        assert row.calories == 165.0

    # Built twice: once optimistically, once after the loser re-read.
    assert attempts == [1, 2]

    with Session(get_engine()) as session:
        rows = session.scalars(select(Food).where(Food.user_id == user_id)).all()
        assert len(rows) == 1, "the unique index still holds"
        # Last writer wins, which is what two sequential saves already did.
        assert rows[0].calories == 165.0


def test_upsert_does_not_swallow_a_second_failure(client):
    """One retry, not a loop. A constraint failing twice is a real error."""
    with Session(get_engine()) as session:
        user_id = _only_user(session).id

    with Session(get_engine()) as session:

        def build():
            # Two rows differing only by case: the index refuses this every
            # time, so the retry cannot help and must not hide it.
            session.add(Food(user_id=user_id, name="Rice", serving_size=100))
            session.add(Food(user_id=user_id, name="rice", serving_size=100))
            return None

        with pytest.raises(IntegrityError):
            upsert(session, build)


def test_saving_a_food_survives_losing_the_race(client, monkeypatch):
    """End to end: 201, not 500, and one row."""
    with Session(get_engine()) as session:
        user_id = _only_user(session).id
        session.add(
            Food(
                user_id=user_id,
                name="oats",
                serving_size=100,
                calories=1.0,
                protein=1.0,
            )
        )
        session.commit()

    # The row above already exists, so the router's own SELECT would find it.
    # Blinding that SELECT once reproduces exactly what a concurrent insert
    # does: the handler believes it is creating, and the index disagrees.
    real_scalars = Session.scalars
    blinded = {"done": False}

    def scalars_missing_once(self, statement, *args, **kwargs):
        result = real_scalars(self, statement, *args, **kwargs)
        if not blinded["done"] and "foods" in str(statement).lower():
            blinded["done"] = True

            class _Empty:
                def first(self_inner):
                    return None

            return _Empty()
        return result

    monkeypatch.setattr(Session, "scalars", scalars_missing_once)

    response = client.post(
        "/api/foods",
        json={
            "name": "Oats",
            "serving_size": 100,
            "calories": 389,
            "protein": 16.9,
        },
    )
    monkeypatch.undo()

    assert response.status_code == 201, response.text
    assert blinded["done"], "the SELECT was never blinded; the test proved nothing"

    with Session(get_engine()) as session:
        rows = session.scalars(select(Food).where(Food.user_id == user_id)).all()
        assert len(rows) == 1
        assert rows[0].calories == 389


def test_logging_steps_survives_losing_the_race(client, monkeypatch):
    """The same shape on a (user_id, date) index rather than a name."""
    first = client.post("/api/steps", json={"date": "2026-07-01", "steps": 4000})
    assert first.status_code == 200, first.text

    calls = {"n": 0}
    real_row = steps_router._row

    def row_missing_once(db, user_id, day):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_row(db, user_id, day)

    monkeypatch.setattr(steps_router, "_row", row_missing_once)

    response = client.post("/api/steps", json={"date": "2026-07-01", "steps": 9000})

    assert response.status_code == 200, response.text
    assert response.json()["steps"] == 9000
    assert calls["n"] == 2, "the retry never ran"

    with Session(get_engine()) as session:
        rows = session.scalars(select(StepEntry)).all()
        assert len(rows) == 1
        assert rows[0].steps == 9000


def test_a_template_that_lost_the_race_reports_replaced_not_created(client, monkeypatch):
    """`created` is recomputed per attempt, and the distinction is not cosmetic.

    Overwriting a template destroys an ingredient list and there is no undo, so
    the client words that differently from a first save. Captured once before
    the retry, the loser would claim it created a template it in fact replaced.
    """
    first = client.post(
        "/api/meal-templates",
        json={"name": "Breakfast", "calories": 500, "protein": 30, "items": []},
    )
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True

    real_scalars = Session.scalars
    blinded = {"done": False}

    def scalars_missing_once(self, statement, *args, **kwargs):
        result = real_scalars(self, statement, *args, **kwargs)
        if not blinded["done"] and "meal_templates" in str(statement).lower():
            blinded["done"] = True

            class _Empty:
                def first(self_inner):
                    return None

            return _Empty()
        return result

    monkeypatch.setattr(Session, "scalars", scalars_missing_once)
    response = client.post(
        "/api/meal-templates",
        json={"name": "Breakfast", "calories": 700, "protein": 55, "items": []},
    )
    monkeypatch.undo()

    assert response.status_code == 201, response.text
    assert blinded["done"], "the SELECT was never blinded; the test proved nothing"
    assert response.json()["created"] is False, "it replaced a template, and must say so"

    with Session(get_engine()) as session:
        rows = session.scalars(select(MealTemplate)).all()
        assert len(rows) == 1
        assert rows[0].calories == 700


def test_a_steps_import_keeps_the_rows_it_already_wrote(client, monkeypatch):
    """One transaction over many rows, so a collision must not undo the file.

    A bare rollback here would discard every row imported before the clash. The
    savepoint unwinds only the failed insert.
    """
    real_scalars = Session.scalars
    # Blind the *second* per-row lookup, which is the one for 2026-07-02 -- the
    # only date already stored. Blinding the first would change nothing, since
    # 2026-07-01 is genuinely absent and the query correctly returns None: the
    # test would then pass without the collision ever happening.
    seen = {"n": 0, "blinded": False}

    def scalars_missing_once(self, statement, *args, **kwargs):
        result = real_scalars(self, statement, *args, **kwargs)
        if "steps.id" in str(statement).lower():
            seen["n"] += 1
            if seen["n"] == 2:
                seen["blinded"] = True

                class _Empty:
                    def first(self_inner):
                        return None

                return _Empty()
        return result

    client.post("/api/steps", json={"date": "2026-07-02", "steps": 1111})
    monkeypatch.setattr(Session, "scalars", scalars_missing_once)

    csv_content = "date,steps\n2026-07-01,8000\n2026-07-02,9000\n2026-07-03,7000\n"
    result = client.post(
        "/api/data/import/steps",
        files={"file": ("steps.csv", csv_content, "text/csv")},
    )
    monkeypatch.undo()

    assert result.status_code == 200, result.text
    body = result.json()
    assert seen["blinded"], "the duplicate's lookup was never blinded"
    assert body["skipped_duplicates"] == 1
    assert body["inserted"] == 2, "the rows either side of the clash must survive"

    with Session(get_engine()) as session:
        rows = {r.date.isoformat(): r.steps for r in session.scalars(select(StepEntry)).all()}
    assert rows == {"2026-07-01": 8000, "2026-07-02": 1111, "2026-07-03": 7000}
