"""Fresh disposable PostgreSQL migrations and regression, without live inference."""
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
    parser.add_argument("--targeted", action="store_true")
    parser.add_argument("--phase", type=int, default=9, choices=list(range(7, 15)))
    parser.add_argument("--test-files", nargs="+", help="Run selected test files in the supplied order")
    parser.add_argument("--report", help="JUnit report path for an ordered regression run")
    args = parser.parse_args()
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    name = "resolveos_backend_verify_" + uuid.uuid4().hex[:10]
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
    os.environ["RESOLVEOS_TEST_DATABASE"] = name
    os.environ["INVESTIGATOR_LIVE_ENABLED"] = "false"
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "20261002_0006")
    command.upgrade(config, "head")
    print("Fresh migration chain and backend downgrade/upgrade verified.")
    import pytest
    options = ["-q", "--junitxml=" + (args.report or (f"phase{args.phase}-test-results.xml" if args.targeted else "backend-test-results.xml"))]
    if args.targeted:
        options.append(f"tests/test_phase{args.phase}_postgres.py")
    if args.test_files:
        options.extend(args.test_files)
    result = pytest.main(options)
    if result == 0:
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
    else:
        Path(".backend_failed_test_db").write_text(name)
    admin.dispose()
    return result

if __name__ == "__main__":
    raise SystemExit(main())
