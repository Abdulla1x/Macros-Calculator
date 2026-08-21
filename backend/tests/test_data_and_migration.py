def test_export_round_trips_through_import(client):
    client.post("/api/meals", json={
        "date": "2026-07-01", "name": "Bowl", "calories": 500, "protein": 40,
        "carbs": 55, "fat": 12,
    })

    export = client.get("/api/data/export")
    assert export.headers["content-type"].startswith("text/csv")
    assert "date,name,calories,protein,carbs,fat" in export.text

    # Re-importing the same file only skips duplicates.
    result = client.post(
        "/api/data/import", files={"file": ("backup.csv", export.text, "text/csv")}
    ).json()
    assert result == {"inserted": 0, "skipped_duplicates": 1, "skipped_invalid": 0}


def test_import_handles_invalid_rows_and_date_formats(client):
    csv_content = (
        "Date,Name,Calories,Protein\n"
        "2026-07-01,ISO Meal,400,30\n"
        "02/07/2026,Slash Meal,350,25\n"
        "not-a-date,Bad Meal,100,5\n"
        ",,,\n"
    )
    result = client.post(
        "/api/data/import", files={"file": ("data.csv", csv_content, "text/csv")}
    ).json()
    assert result["inserted"] == 2
    assert result["skipped_invalid"] == 2

    meals = client.get("/api/meals").json()
    assert {meal["date"] for meal in meals} == {"2026-07-01", "2026-07-02"}


def test_import_skips_non_finite_macros(client):
    """The importer is the only path that writes a Meal without MealCreate.

    `float()` parses all three of these, and `inf >= 0` is True, so before the
    isfinite check they imported as valid rows. The cost was not theoretical:
    one stored `inf` makes GET /api/data/export/all raise
    "Out of range float values are not JSON compliant" for the rest of that
    account's life, with no way for the user to tell which row did it.

    Reachable without any hand-written request — pandas writes `inf` when it
    serializes an infinite value, so an export-edit-reimport round trip is
    enough.
    """
    csv_content = (
        "date,name,calories,protein\n"
        "2026-07-01,Good Meal,400,30\n"
        "2026-07-01,Infinity Word,Infinity,30\n"
        "2026-07-01,Lowercase Inf,inf,30\n"
        "2026-07-01,Overflowing Exponent,1e999,30\n"
        "2026-07-01,Not A Number,nan,30\n"
    )
    result = client.post(
        "/api/data/import", files={"file": ("data.csv", csv_content, "text/csv")}
    ).json()
    assert result["inserted"] == 1
    assert result["skipped_invalid"] == 4

    # And the export the bad rows would have broken still works.
    assert client.get("/api/data/export/all").status_code == 200


def test_import_rejects_missing_columns(client):
    response = client.post(
        "/api/data/import", files={"file": ("bad.csv", "foo,bar\n1,2\n", "text/csv")}
    )
    assert response.status_code == 400


def test_import_rejects_oversized_file(client):
    huge = "date,name,calories,protein\n" + ("x" * (1024 * 1024))
    response = client.post(
        "/api/data/import", files={"file": ("huge.csv", huge, "text/csv")}
    )
    assert response.status_code == 413


def test_import_dedupe_considers_carbs_and_fat(client):
    csv_content = (
        "date,name,calories,protein,carbs,fat\n"
        "2026-07-01,Bowl,400,30,50,10\n"
        "2026-07-01,Bowl,400,30,20,25\n"  # same cal/protein, different carbs/fat
        "2026-07-01,Bowl,400,30,50,10\n"  # true duplicate of row 1
    )
    result = client.post(
        "/api/data/import", files={"file": ("data.csv", csv_content, "text/csv")}
    ).json()
    assert result["inserted"] == 2
    assert result["skipped_duplicates"] == 1


# -- Steps import ---------------------------------------------------------
#
# Dates are relative because the importer refuses future ones, the same way the
# manual path does -- a fixed calendar date would eventually start failing.

def steps_csv(client, content):
    return client.post(
        "/api/data/import/steps",
        files={"file": ("steps.csv", content, "text/csv")},
    ).json()


def a_day(n):
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def test_steps_import_inserts_and_reports(client):
    result = steps_csv(
        client,
        f"date,steps\n{a_day(3)},8000\n{a_day(2)},12000\n{a_day(1)},0\n",
    )
    assert result == {"inserted": 3, "skipped_duplicates": 0, "skipped_invalid": 0}
    # Zero is a real count, not a refusal -- it must land as a logged day.
    day = client.get("/api/steps", params={"date": a_day(1)}).json()
    assert day["steps"] == 0 and day["logged"] is True


def test_steps_import_accepts_mixed_case_headers_and_extra_columns(client):
    """Samsung's export carries a dozen columns beside the count."""
    result = steps_csv(
        client,
        f"Date,Steps,Calories,Distance\n{a_day(1)},9000,320,6.4\n",
    )
    assert result["inserted"] == 1


def test_steps_import_never_overwrites_a_day_already_logged(client):
    """The decision that separates this from the meals importer.

    A collision here is a date, not a whole row. A count already stored was
    typed by hand or imported earlier, and replacing it from a file cannot be
    undone -- so it is skipped, and the stored value is what must still be
    there afterwards.
    """
    client.post("/api/steps", json={"date": a_day(1), "steps": 4321})

    result = steps_csv(client, f"date,steps\n{a_day(1)},99999\n")
    assert result == {"inserted": 0, "skipped_duplicates": 1, "skipped_invalid": 0}
    assert client.get("/api/steps", params={"date": a_day(1)}).json()["steps"] == 4321


def test_steps_import_catches_a_date_repeated_inside_one_file(client):
    """The per-row flush is what makes the second row see the first."""
    result = steps_csv(client, f"date,steps\n{a_day(1)},8000\n{a_day(1)},9000\n")
    assert result["inserted"] == 1
    assert result["skipped_duplicates"] == 1
    assert client.get("/api/steps", params={"date": a_day(1)}).json()["steps"] == 8000


def test_steps_import_refuses_every_shape_of_bad_count(client):
    """One row each for the four rejections in _parse_steps, plus a bad date.

    1e999 is the non-finite trap `_parse_float` was written for; 8000.5 is the
    one specific to an integer column, where a bare int() would raise and take
    the whole file down instead of reporting one row.
    """
    result = steps_csv(
        client,
        "date,steps\n"
        f"{a_day(9)},-1\n"
        f"{a_day(8)},200001\n"
        f"{a_day(7)},1e999\n"
        f"{a_day(6)},8000.5\n"
        f"{a_day(5)},nan\n"
        f"{a_day(4)},\n"
        "not-a-date,8000\n"
        ",,\n"
        f"{a_day(3)},7500\n"
    )
    assert result["inserted"] == 1
    assert result["skipped_invalid"] == 8
    # And the good row still landed -- a bad row is reported, never fatal.
    assert client.get("/api/steps", params={"date": a_day(3)}).json()["steps"] == 7500


def test_steps_import_refuses_a_future_date(client):
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=30)).isoformat()
    result = steps_csv(client, f"date,steps\n{future},8000\n")
    assert result["skipped_invalid"] == 1
    assert result["inserted"] == 0


def test_steps_import_rejects_missing_columns(client):
    response = client.post(
        "/api/data/import/steps",
        files={"file": ("steps.csv", "date,walked\n2026-07-01,8000\n", "text/csv")},
    )
    assert response.status_code == 400


def test_steps_import_rejects_oversized_file(client):
    response = client.post(
        "/api/data/import/steps",
        files={"file": ("steps.csv", "date,steps\n" + ("x" * (1024 * 1024)), "text/csv")},
    )
    assert response.status_code == 413


def test_the_full_export_round_trips_into_the_steps_importer(client):
    """export/all already emits steps as {date, steps} -- the importer's two
    columns exactly. Worth pinning, because it makes the JSON export a usable
    backup rather than a one-way dump."""
    client.post("/api/steps", json={"date": a_day(2), "steps": 8000})
    client.post("/api/steps", json={"date": a_day(1), "steps": 9500})

    rows = client.get("/api/data/export/all").json()["steps"]
    content = "date,steps\n" + "".join(f"{r['date']},{r['steps']}\n" for r in rows)

    assert steps_csv(client, content) == {
        "inserted": 0, "skipped_duplicates": 2, "skipped_invalid": 0,
    }
