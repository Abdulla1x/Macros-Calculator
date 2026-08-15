import json

from app.db import get_engine
from app.models import MealTemplate
from sqlalchemy import select
from sqlalchemy.orm import Session


def _item(**overrides):
    item = {
        "name": "Chicken Breast",
        "weight_grams": 150,
        "serving_size": 100,
        "calories": 165,
        "protein": 31,
        "carbs": 0,
        "fat": 3.6,
    }
    item.update(overrides)
    return item


def _template(**overrides):
    template = {
        "name": "Chicken & Rice",
        "calories": 620,
        "protein": 48,
        "carbs": 71,
        "fat": 12,
        "items": [_item(), _item(name="White Rice", weight_grams=200, calories=130,
                        protein=2.7, carbs=28, fat=0.3)],
    }
    template.update(overrides)
    return template


def test_saving_a_template_keeps_its_ingredient_rows(client):
    """The regression that matters most.

    The ORM row stores `items_json`, not `items`. If the response model were
    built with from_attributes, Pydantic would find no `items` attribute, fall
    back to the default, and hand back an empty list without raising — every
    template silently losing exactly the thing it exists to remember.
    """
    saved = client.post("/api/meal-templates", json=_template()).json()
    assert [item["name"] for item in saved["items"]] == ["Chicken Breast", "White Rice"]

    listed = client.get("/api/meal-templates").json()
    assert len(listed) == 1
    assert [item["name"] for item in listed[0]["items"]] == [
        "Chicken Breast", "White Rice"
    ]
    assert listed[0]["items"][1]["weight_grams"] == 200
    assert listed[0]["calories"] == 620


def test_a_template_can_have_no_items(client):
    """Saving from the edit-an-existing-meal path yields totals and nothing else."""
    saved = client.post("/api/meal-templates", json=_template(items=[])).json()
    assert saved["items"] == []

    with Session(get_engine()) as session:
        assert session.scalars(select(MealTemplate)).one().items_json is None

    assert client.get("/api/meal-templates").json()[0]["items"] == []


def test_unreadable_items_do_not_break_the_list(client):
    """One corrupt row must not take the whole Quick log panel down with it."""
    client.post("/api/meal-templates", json=_template())
    with Session(get_engine()) as session:
        session.scalars(select(MealTemplate)).one().items_json = "{not json"
        session.commit()

    listed = client.get("/api/meal-templates").json()
    assert listed[0]["items"] == []
    assert listed[0]["calories"] == 620


def test_saving_the_same_name_replaces_rather_than_duplicates(client):
    first = client.post("/api/meal-templates", json=_template()).json()
    assert first["created"] is True

    second = client.post(
        "/api/meal-templates",
        json=_template(name="chicken & rice", calories=700, items=[_item()]),
    ).json()

    # Overwriting a food is a correction; overwriting a template destroys an
    # ingredient list. The flag is what lets the client say so.
    assert second["created"] is False
    listed = client.get("/api/meal-templates").json()
    assert len(listed) == 1
    assert listed[0]["calories"] == 700
    assert len(listed[0]["items"]) == 1


def test_two_users_may_use_the_same_template_name(client, client_b):
    assert client.post("/api/meal-templates", json=_template()).status_code == 201
    assert client_b.post("/api/meal-templates", json=_template()).status_code == 201

    assert len(client.get("/api/meal-templates").json()) == 1
    assert len(client_b.get("/api/meal-templates").json()) == 1


def test_templates_are_listed_newest_first(client):
    for name in ("First", "Second", "Third"):
        client.post("/api/meal-templates", json=_template(name=name))

    listed = client.get("/api/meal-templates").json()
    assert [t["name"] for t in listed] == ["Third", "Second", "First"]


def test_delete_template(client):
    template_id = client.post("/api/meal-templates", json=_template()).json()["id"]
    assert client.delete(f"/api/meal-templates/{template_id}").status_code == 204
    assert client.delete(f"/api/meal-templates/{template_id}").status_code == 404
    assert client.get("/api/meal-templates").json() == []


def test_another_users_template_is_not_deletable(client, client_b):
    template_id = client_b.post("/api/meal-templates", json=_template()).json()["id"]

    assert client.delete(f"/api/meal-templates/{template_id}").status_code == 404
    assert len(client_b.get("/api/meal-templates").json()) == 1


def test_too_many_items_is_rejected(client):
    body = _template(items=[_item(name=f"Item {n}") for n in range(31)])
    assert client.post("/api/meal-templates", json=body).status_code == 422


def test_item_bounds_are_enforced(client):
    """These values end up serialized in a Text column and read back out through
    the full export, so a bad one has a wider blast radius than a bad meal."""
    over_long = client.post(
        "/api/meal-templates", json=_template(items=[_item(name="x" * 201)])
    )
    assert over_long.status_code == 422

    # Sent as raw content because httpx refuses to serialize `inf` at all --
    # but Python's json.loads happily *accepts* the bare token `Infinity`, so
    # this is reachable by any hand-written request. Without allow_inf_nan it
    # would be stored, and json.dumps would write it straight back out as
    # `Infinity`, corrupting the account's entire export.
    infinite = client.post(
        "/api/meal-templates",
        content=json.dumps(_template(items=[_item(calories=float("inf"))])),
        headers={"Content-Type": "application/json"},
    )
    assert infinite.status_code == 422

    negative = client.post(
        "/api/meal-templates", json=_template(items=[_item(weight_grams=0)])
    )
    assert negative.status_code == 422


def test_template_name_is_required(client):
    assert client.post("/api/meal-templates", json=_template(name="")).status_code == 422
