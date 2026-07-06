import sqlite3

from fastapi.testclient import TestClient

from app.main import app


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


def test_v1_database_is_migrated_in_place(tmp_path, monkeypatch):
    """A database created by the old Streamlit app gains carbs/fat columns
    while keeping its rows."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO meals (date, name, calories, protein) VALUES (?, ?, ?, ?)",
        [("2026-01-15", "Legacy Meal", 450, 35),
         ("2026/03/22", "Slash Date Meal", 300, 20)],
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    with TestClient(app) as client:
        meals = client.get("/api/meals").json()
        assert meals[0] == {
            "id": 1, "date": "2026-01-15", "name": "Legacy Meal",
            "calories": 450, "protein": 35, "carbs": None, "fat": None,
        }
        # Non-ISO dates from the v1 app are normalized on startup.
        assert meals[1]["date"] == "2026-03-22"
        # New tables exist and work too.
        assert client.get("/api/settings").status_code == 200
        assert client.get("/api/foods").json() == []
