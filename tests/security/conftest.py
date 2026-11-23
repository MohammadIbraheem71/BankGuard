import pytest

from app import db
from app.config import settings
from app.models import User


@pytest.fixture
def seeded_bank(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "bankguard.db"))
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "secret_key", "test-only-signing-key")
    db.reset_and_seed()


@pytest.fixture
def alice():
    return User(id=1, username="alice", role="customer", account_ids=[1001, 1002])


@pytest.fixture
def bob():
    return User(id=2, username="bob", role="customer", account_ids=[2001])
