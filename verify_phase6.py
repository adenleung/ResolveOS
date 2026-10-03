"""Fresh PostgreSQL migration and Phase 1-6 regression verification."""
import argparse
import os
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase6-only", action="store_true")
    parser.add_argument("--workload-only", action="store_true")
    args = parser.parse_args()
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    if admin.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL is required")
    name = "resolveos_phase6_verify_" + uuid.uuid4().hex[:8]
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "20261002_0005")
    command.upgrade(config, "head")
    print("Fresh chain 0001-0006 and 0006 downgrade/upgrade verified.")
    import pytest
    options = ["-q", "--junitxml=phase6-test-results.xml"]
    if args.phase6_only:
        options.append("tests/test_phase6_postgres.py")
    if args.workload_only:
        options.extend(["-s", "tests/test_phase6_postgres.py::test_bounded_synthetic_queue_workload_and_query_plan"])
    result = pytest.main(options)
    if result == 0:
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
    else:
        Path(".phase6_failed_test_db").write_text(name)
    admin.dispose()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
