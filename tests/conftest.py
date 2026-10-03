"""Committed-state isolation, including connections used by worker processes."""
import os
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture(autouse=True)
def isolated_postgres_state():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        yield
        return
    database = make_url(url).database or ""
    if not re.fullmatch(r"resolveos_backend_verify_[0-9a-f]{10}", database) or os.environ.get("RESOLVEOS_TEST_DATABASE") != database:
        pytest.fail("PostgreSQL tests require a disposable database created by verify_backend.py")
    engine = create_engine(url)

    def reset():
        with engine.begin() as connection:
            assert connection.execute(text("SELECT current_database()")).scalar_one() == database
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version' ORDER BY tablename")).scalars().all()
            if tables:
                names = [engine.dialect.identifier_preparer.quote_identifier(name) for name in tables]
                connection.execute(text("TRUNCATE TABLE " + ", ".join(names) + " RESTART IDENTITY"))

    try:
        reset()
        yield
    finally:
        reset()
        engine.dispose()
