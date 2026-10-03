"""Read-only final demo/development checks; no seeding or operational writes."""
import json
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from app.database import DatabaseManager
from app.demo import verify_journeys
from verify_phase11_migrations import snapshot


def main():
    report = json.loads(Path("phase15-development-preservation-results.json").read_text())
    engine = create_engine("postgresql+psycopg://resolve:resolve@localhost:5433/resolveos")
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == report["revision"]
        tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
        assert tables == set(report["snapshots"])
        assert snapshot(connection, tables) == report["snapshots"]
    manifest = json.loads(Path("demo-manifest.local.json").read_text())
    verify_journeys(DatabaseManager(engine.url.set(database=manifest["database"]).render_as_string(hide_password=False)), manifest)
    report["verified_after_production_browser_checks"] = True
    Path("phase15-development-preservation-results.json").write_text(json.dumps(report, indent=2)+"\n")
    print("Final read-only checks passed: three persisted journeys and every development row unchanged.")


if __name__ == "__main__": main()
