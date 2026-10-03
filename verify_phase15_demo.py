"""Create and verify isolated demos while proving development remains unchanged."""
import json
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, inspect, text
from app.config import get_settings
from verify_phase11_migrations import snapshot


def main():
    engine = create_engine(get_settings().database_url)
    assert engine.url.database == "resolveos" and engine.url.host in {"localhost", "127.0.0.1"} and engine.url.port == 5433
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "20261004_0013"
        tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
        before = snapshot(connection, tables)
    subprocess.run([sys.executable, "-m", "app.demo", "--create"], check=True)
    subprocess.run([sys.executable, "-m", "app.demo"], check=True)
    with engine.connect() as connection:
        assert snapshot(connection, tables) == before
    Path("phase15-development-preservation-results.json").write_text(json.dumps({"database": "resolveos", "revision": revision,
        "existing_application_tables": len(tables), "existing_rows": sum(item["count"] for item in before.values()),
        "all_existing_rows_unchanged": True, "snapshots": before, "demonstration_database": json.loads(Path("demo-manifest.local.json").read_text())["database"]}, indent=2)+"\n")
    print("Three actual journeys verified; all development tables retained identical hashes.")


if __name__ == "__main__": main()
