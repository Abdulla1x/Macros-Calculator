from app.announcements import ANNOUNCEMENTS


def test_announcements_are_public(anon_client):
    """No auth: the status banner has to render on the login page, which is
    where someone lands when the app looks broken to them."""
    response = anon_client.get("/api/announcements")
    assert response.status_code == 200
    body = response.json()
    assert body["banner"] is None
    assert len(body["items"]) == len(ANNOUNCEMENTS)


def test_status_banner_comes_from_the_environment(anon_client, monkeypatch):
    """Read per request, so an outage notice needs no deploy."""
    monkeypatch.setenv("STATUS_BANNER", "AI analysis is down — macros still save.")
    body = anon_client.get("/api/announcements").json()
    assert body["banner"] == "AI analysis is down — macros still save."

    monkeypatch.setenv("STATUS_BANNER", "")
    assert anon_client.get("/api/announcements").json()["banner"] is None


def test_blank_status_banner_is_not_a_banner(anon_client, monkeypatch):
    """A dashboard field cleared to whitespace must not show an empty bar."""
    monkeypatch.setenv("STATUS_BANNER", "   \n")
    assert anon_client.get("/api/announcements").json()["banner"] is None


def test_announcements_are_newest_first(anon_client):
    dates = [item["date"] for item in anon_client.get("/api/announcements").json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_announcement_ids_are_unique():
    """Ids are the frontend's localStorage dismissal keys; a duplicate would
    make dismissing one note silently hide another."""
    ids = [item.id for item in ANNOUNCEMENTS]
    assert len(ids) == len(set(ids))
