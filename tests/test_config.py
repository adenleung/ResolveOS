import pytest

from app.config import Settings


def test_settings_require_database_url():
    with pytest.raises(ValueError):
        Settings.from_env({})


def test_settings_accept_postgres_url():
    settings = Settings.from_env({"DATABASE_URL": "postgresql+psycopg://resolve:resolve@localhost:5432/resolveos"})
    assert settings.database_url == "postgresql+psycopg://resolve:resolve@localhost:5432/resolveos"
