"""Verified local backup and additive development migration; never resets dev data."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.config import get_settings
from verify_phase11_migrations import snapshot


def main():
    for name in ("phase14-targeted-results.xml", "phase14-final-full-regression-results.xml"):
        suites = list(ElementTree.parse(name).getroot().iter("testsuite"))
        minimum = 350 if "full-regression" in name else 18
        assert suites and sum(int(s.get("tests", 0)) for s in suites) >= minimum
        assert all(int(s.get(k, 0)) == 0 for s in suites for k in ("failures", "errors", "skipped"))
    engine = create_engine(get_settings().database_url)
    assert engine.url.database == "resolveos" and engine.url.host in {"localhost", "127.0.0.1"} and engine.url.port == 5433
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == "resolveos"
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20261004_0012"
        system_id = str(conn.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        tables = set(inspect(conn).get_table_names()) - {"alembic_version"}
        before = snapshot(conn, tables)
    docker_id = subprocess.check_output(["docker", "exec", "resolveos-postgres", "psql", "-U", "resolve", "-d", "resolveos", "-tA", "-c", "SELECT system_identifier FROM pg_control_system()"], text=True).strip()
    assert docker_id == system_id, "Container is not the configured PostgreSQL cluster"
    backup = Path("resolveos-pre-0013-" + uuid4().hex[:8] + ".dump")
    with backup.open("xb") as output:
        subprocess.run(["docker", "exec", "resolveos-postgres", "pg_dump", "-U", "resolve", "-d", "resolveos", "-Fc"], stdout=output, check=True)
    with backup.open("rb") as data:
        listing = subprocess.run(["docker", "exec", "-i", "resolveos-postgres", "pg_restore", "--list"], stdin=data, capture_output=True, check=True).stdout
    assert b"TABLE public cases" in listing and backup.stat().st_size > 0
    admin = create_engine(engine.url, isolation_level="AUTOCOMMIT")
    name = "resolveos_backend_verify_" + uuid4().hex[:10]
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE "' + name + '"'))
    restored = create_engine(engine.url.set(database=name))
    try:
        with backup.open("rb") as data:
            subprocess.run(["docker", "exec", "-i", "resolveos-postgres", "pg_restore", "-U", "resolve", "-d", name, "--no-owner", "--exit-on-error"], stdin=data, check=True)
        with restored.connect() as conn:
            assert conn.scalar(text("SELECT current_database()")) == name
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20261004_0012"
            assert snapshot(conn, tables) == before, "Restored backup differs from source"
        # Populated migration round trip also runs only in this disposable restore.
        original_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = restored.url.render_as_string(hide_password=False)
        try:
            command.upgrade(Config("alembic.ini"), "head")
            command.downgrade(Config("alembic.ini"), "20261004_0012")
            command.upgrade(Config("alembic.ini"), "head")
            with restored.connect() as conn:
                assert snapshot(conn, tables) == before
                assert conn.scalar(text("SELECT count(*) FROM shadow_evaluations")) == 0
        finally:
            if original_url is None: os.environ.pop("DATABASE_URL", None)
            else: os.environ["DATABASE_URL"] = original_url
    finally:
        restored.dispose()
        assert name.startswith("resolveos_backend_verify_") and len(name.rsplit("_", 1)[1]) == 10
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
        admin.dispose()
    with engine.connect() as conn:
        assert snapshot(conn, tables) == before, "Development changed during backup verification"
    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as conn:
        after = snapshot(conn, tables)
        assert after == before
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20261004_0013"
        assert conn.scalar(text("SELECT count(*) FROM shadow_evaluations")) == 0
    result = {"database": "resolveos", "cluster_system_identifier": system_id, "previous_revision": "20261004_0012", "revision": "20261004_0013",
              "backup_file": backup.name, "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
              "backup_restore_verified": True, "populated_disposable_round_trip_verified": True,
              "existing_tables_preserved": before, "shadow_rows": 0}
    Path("phase14-development-migration-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Verified backup restoration, populated round trip and development migration; all existing rows preserved.")
    engine.dispose()


if __name__ == "__main__":
    main()
