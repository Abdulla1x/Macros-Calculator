import pytest
from fastapi.testclient import TestClient

from app.db import dispose_engine
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    dispose_engine()
    with TestClient(app) as test_client:
        yield test_client
    dispose_engine()
