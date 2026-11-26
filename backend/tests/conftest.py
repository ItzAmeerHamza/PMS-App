"""Test fixtures. Every test gets its own temporary data directory and SQLite file.

Nothing here touches backend/data/pharmacy.db. All people and medicines are synthetic.
"""

import os

import pytest
from fastapi.testclient import TestClient

from src.core import database

MANAGER = {"username": "test-manager", "password": "correct horse 42", "full_name": "Test Manager"}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    path.mkdir()
    monkeypatch.setenv("PHARMACARE_DATA_DIR", str(path))
    monkeypatch.delenv("PHARMACARE_DEMO_DATA", raising=False)
    database.init_engine(path / "pharmacy.db")
    yield path
    database.get_engine().dispose()


@pytest.fixture
def db_path(data_dir):
    return data_dir / "pharmacy.db"


def start_client() -> TestClient:
    from src.api.main import app

    return TestClient(app)


@pytest.fixture
def client(data_dir):
    with start_client() as test_client:
        yield test_client


@pytest.fixture
def demo_client(data_dir, monkeypatch):
    monkeypatch.setenv("PHARMACARE_DEMO_DATA", "1")
    with start_client() as test_client:
        yield test_client


def set_up_manager(test_client: TestClient, **extra) -> dict:
    body = {**MANAGER, **extra}
    response = test_client.post("/api/v1/auth/setup", json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['token']}", "_pharmacy_id": data["pharmacy"]["id"]}


def auth(headers: dict) -> dict:
    return {key: value for key, value in headers.items() if not key.startswith("_")}


@pytest.fixture
def manager(demo_client):
    """Demo pharmacy plus a manager created through first-run setup."""
    return set_up_manager(demo_client)


def pytest_report_header(config):
    return f"PHARMACARE_DATA_DIR per test: tmp_path (real data dir untouched); cwd={os.getcwd()}"
