from app.database import DatabaseManager


def test_database_manager_creates_sqlite_engine():
    db = DatabaseManager("sqlite:///:memory:")
    assert db.engine is not None
    assert "sqlite" in str(db.engine.url)
