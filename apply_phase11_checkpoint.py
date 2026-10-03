"""Guarded, backed-up development upgrade after Phase 11 PostgreSQL acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from verify_phase11_migrations import MEMORY_TABLES, snapshot


def main():
    # Keep the original Phase 10 XML evidence intact.
    for filename, expected in [("phase10-test-results.xml", 29), ("backend-test-results.xml", 222),
                               ("phase11-test-results.xml", 46), ("phase11-full-regression-results.xml", 268)]:
        suite = ET.parse(filename).getroot().find("testsuite")
        assert int(suite.attrib["tests"]) == expected, suite.attrib
        assert all(int(suite.attrib[key]) == 0 for key in ("errors", "failures", "skipped")), suite.attrib
    migration_report = json.loads(Path("phase11-migration-results.json").read_text())
    assert migration_report["populated_round_trip"] == "0012 -> 0011 -> 0012"
    engine = create_engine(os.environ["DATABASE_URL"])
    assert engine.url.database == "resolveos" and engine.url.host == "localhost" and engine.url.port == 5433
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261002_0011"
        system_id = str(connection.execute(text("SELECT system_identifier FROM pg_control_system()")).scalar_one())
        source_tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
        assert not MEMORY_TABLES.intersection(source_tables)
        before = snapshot(connection, source_tables)
    # Verify the backup container is the same PostgreSQL cluster as the explicit
    # TCP development connection. Never dump or migrate another database.
    container = "resolveos-postgres"
    container_id = subprocess.run(["docker", "exec", container, "psql", "-U", "resolve", "-d", "resolveos", "-tA",
        "-c", "SELECT system_identifier FROM pg_control_system()"], check=True, capture_output=True, text=True).stdout.strip()
    assert container_id == system_id
    backup = Path("resolveos-pre-0012.dump")
    # Exclusive creation prevents silently replacing a recovery point.
    with backup.open("xb") as output:
        subprocess.run(["docker", "exec", container, "pg_dump", "-U", "resolve", "-d", "resolveos", "-Fc"],
            stdout=output, check=True)
    assert backup.stat().st_size > 0
    # pg_restore reads the full dump through stdin without Windows text encoding.
    with backup.open("rb") as source:
        listing = subprocess.run(["docker", "exec", "-i", container, "pg_restore", "--list"],
            stdin=source, capture_output=True, check=True).stdout.decode("utf-8")
    assert "alembic_version" in listing and "verification_results" in listing
    with engine.connect() as connection:
        assert snapshot(connection, source_tables) == before, "Development changed while creating recovery point"
    command.upgrade(Config("alembic.ini"), "20261004_0012")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261004_0012"
        after = snapshot(connection, source_tables | MEMORY_TABLES)
        assert all(after[table] == contents for table, contents in before.items()), "Existing development rows changed"
        assert all(after[table]["count"] == 0 for table in MEMORY_TABLES)
    report = {"database": "resolveos", "before_revision": "20261002_0011", "after_revision": "20261004_0012",
        "backup": str(backup), "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
        "backup_format": "PostgreSQL custom archive; pg_restore --list checked",
        "existing_tables_preserved": len(source_tables), "before": before, "after": after}
    Path("phase11-development-migration-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Development upgraded 0011 -> 0012 after recovery backup; {len(source_tables)} existing tables preserved by count and hash.")
    engine.dispose()


if __name__ == "__main__":
    main()
