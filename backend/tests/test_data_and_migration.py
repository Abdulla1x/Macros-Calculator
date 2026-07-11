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
