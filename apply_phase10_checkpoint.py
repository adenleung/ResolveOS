"""Apply accepted 0011 to development without running disposable-test cleanup."""
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def main():
    for filename, expected in [("phase10-test-results.xml", 29), ("backend-test-results.xml", 222)]:
        suite = ET.parse(filename).getroot().find("testsuite")
        assert int(suite.attrib["tests"]) == expected, suite.attrib
        assert all(int(suite.attrib[key]) == 0 for key in ["errors", "failures", "skipped"]), suite.attrib
    backup = Path("resolveos-pre-0011.dump")
    assert backup.stat().st_size > 0
    engine = create_engine(os.environ["DATABASE_URL"])
    assert engine.url.database == "resolveos", "Explicit development database required"

    def snapshot():
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version' ORDER BY tablename")).scalars().all()
            records = {}
            for table in tables:
                quoted = engine.dialect.identifier_preparer.quote_identifier(table)
                rows = sorted(connection.execute(text(f"SELECT row_to_json(t)::text FROM {quoted} t")).scalars())
                records[table] = {"count": len(rows), "sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
            return revision, records

    before_revision, before = snapshot()
    assert before_revision == "20261002_0010", before_revision
    assert "counterfactual_simulations" not in before
    command.upgrade(Config("alembic.ini"), "20261002_0011")
    after_revision, after = snapshot()
    assert after_revision == "20261002_0011"
    assert all(after[table] == values for table, values in before.items()), "Existing records changed"
    assert after["counterfactual_simulations"]["count"] == 0
    report = {"database": "resolveos", "before_revision": before_revision, "after_revision": after_revision,
              "backup": str(backup), "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
              "existing_tables_preserved": len(before), "before": before, "after": after,
              "disposable_migration_round_trip": "0001 -> 0011 -> 0006 -> 0011 passed in targeted and full runs"}
    Path("phase10-counterfactual-migration-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Development upgraded {before_revision} -> {after_revision}; {len(before)} existing tables preserved by row count and content hash.")
    engine.dispose()


if __name__ == "__main__":
    main()
