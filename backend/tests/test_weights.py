"""Weight log CRUD and the trend endpoint.

Dates are relative to today rather than hard-coded: the POST validator rejects
future dates and the trend endpoint has a lookback window, so a fixed calendar
date would start failing on its own once enough time passed.
"""
from datetime import date, timedelta

from conftest import post_raw_json


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def log(client, day: str, weight: float):
    return client.post("/api/weights", json={"date": day, "weight_kg": weight})


def test_log_list_and_delete(client):
    created = log(client, days_ago(2), 82.4)
    assert created.status_code == 200
    body = created.json()
    assert body["weight_kg"] == 82.4
    assert body["date"] == days_ago(2)

    log(client, days_ago(1), 82.1)
    entries = client.get("/api/weights").json()
    # Oldest first, so the list reads as a series.
    assert [e["date"] for e in entries] == [days_ago(2), days_ago(1)]

    assert client.delete(f"/api/weights/{body['id']}").status_code == 204
    assert [e["date"] for e in client.get("/api/weights").json()] == [days_ago(1)]
    assert client.delete(f"/api/weights/{body['id']}").status_code == 404


def test_non_finite_weight_is_refused_by_the_existing_bound(client):
    """WeightEntryCreate is the one macro-ish schema with no allow_inf_nan=False.

    It does not need one: MAX_WEIGHT_KG already rejects `inf`, and `nan` fails
    every comparison it is given. This test exists so that stays true — if the
    upper bound were ever loosened, the hole would open silently and this is the
    only thing that would notice.
    """
    for bad in (float("inf"), float("-inf"), float("nan")):
        response = post_raw_json(
            client, "/api/weights", {"date": days_ago(1), "weight_kg": bad}
        )
        assert response.status_code == 422, f"weight_kg={bad} was accepted"


def test_relogging_a_date_replaces_rather_than_duplicates(client):
    first = log(client, days_ago(1), 80.0).json()
    second = log(client, days_ago(1), 79.5)

    assert second.status_code == 200  # upsert: never flips to 201
    assert second.json()["id"] == first["id"]
    entries = client.get("/api/weights").json()
    assert len(entries) == 1
    assert entries[0]["weight_kg"] == 79.5


def test_range_filter_and_inverted_range(client):
    log(client, days_ago(10), 80.0)
    log(client, days_ago(5), 79.0)
    log(client, days_ago(1), 78.0)

    ranged = client.get(
        "/api/weights", params={"start": days_ago(6), "end": days_ago(2)}
    ).json()
    assert [e["date"] for e in ranged] == [days_ago(5)]

    inverted = client.get(
        "/api/weights", params={"start": days_ago(1), "end": days_ago(10)}
    )
    assert inverted.status_code == 422


def test_future_date_is_rejected(client):
    future = (date.today() + timedelta(days=30)).isoformat()
    assert log(client, future, 80.0).status_code == 422


def test_implausible_weights_are_rejected(client):
    for bad in (0, -5, 700, 8000):
        assert log(client, days_ago(1), bad).status_code == 422, f"{bad} accepted"
    # The bound is above the heaviest recorded human, not below real people.
    assert log(client, days_ago(1), 250).status_code == 200


def test_trend_smooths_and_reports_a_weekly_rate(client):
    # Fourteen days of steady loss with a noisy final reading.
    for offset in range(13, -1, -1):
        log(client, days_ago(offset), 85.0 - 0.1 * (13 - offset))
    log(client, days_ago(0), 86.5)  # one heavy day

    trend = client.get("/api/weights/trend").json()
    assert trend["point_count"] == 14
    assert len(trend["points"]) == 14

    latest = trend["points"][-1]
    assert latest["weight_kg"] == 86.5
    # The trend absorbs the spike instead of following it.
    assert latest["trend_kg"] < 85.0
    assert trend["latest_trend_kg"] == latest["trend_kg"]
    # Losing weight over the window reads as a negative rate.
    assert trend["weekly_rate_kg"] is not None
    assert trend["weekly_rate_kg"] < 0


def test_trend_withholds_a_rate_until_there_is_enough_data(client):
    for offset in (3, 2, 1):
        log(client, days_ago(offset), 80.0)

    trend = client.get("/api/weights/trend").json()
    assert trend["point_count"] == 3
    assert trend["weekly_rate_kg"] is None
    assert trend["latest_trend_kg"] is not None


def test_trend_is_empty_without_entries(client):
    trend = client.get("/api/weights/trend").json()
    assert trend == {
        "points": [],
        "latest_trend_kg": None,
        "weekly_rate_kg": None,
        "point_count": 0,
    }


def test_trend_window_excludes_older_entries(client):
    log(client, days_ago(200), 95.0)
    log(client, days_ago(1), 80.0)

    trend = client.get("/api/weights/trend", params={"days": 90}).json()
    assert [p["date"] for p in trend["points"]] == [days_ago(1)]


def test_weights_require_authentication(anon_client):
    assert anon_client.get("/api/weights").status_code == 401
    assert anon_client.get("/api/weights/trend").status_code == 401
    assert anon_client.post(
        "/api/weights", json={"date": days_ago(1), "weight_kg": 80}
    ).status_code == 401
