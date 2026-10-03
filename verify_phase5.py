"""Run regression on an isolated, freshly migrated PostgreSQL database."""
import os
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def main():
    configured = get_settings().database_url
    admin = create_engine(configured, isolation_level="AUTOCOMMIT")
    name = "resolveos_phase5_verify_" + uuid.uuid4().hex[:8]
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "20261002_0004")
    command.upgrade(config, "head")
    print("Fresh chain 0001-0005 and 0005 downgrade/upgrade verified.")
    import pytest
    result = pytest.main(["-q", "--junitxml=phase5-test-results.xml"])
    # This script creates and owns this exact temporary database.
    if result == 0:
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
    else:
        Path(".phase5_failed_test_db").write_text(name)
    admin.dispose()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
