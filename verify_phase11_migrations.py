"""Fresh/populated Phase 11 round trip and reflected constraints, disposable DB only."""
import hashlib
import json
import time
import os
from pathlib import Path
import sys
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.orm import Session

from app.config import get_settings, Settings

MEMORY_TABLES = {"operational_memories", "memory_versions", "memory_evidence", "memory_reviews", "memory_retrievals"}


def snapshot(connection, tables):
    records = {}
    for table in sorted(tables):
        quoted = connection.dialect.identifier_preparer.quote_identifier(table)
        rows = sorted(connection.execute(text(f"SELECT row_to_json(t)::text FROM {quoted} t")).scalars())
        records[table] = {"count": len(rows), "sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    return records


def main():
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    name = "resolveos_backend_verify_" + uuid4().hex[:10]
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
    os.environ["RESOLVEOS_TEST_DATABASE"] = name
    config = Config("alembic.ini")
    engine = create_engine(os.environ["DATABASE_URL"])
    success = False
    try:
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT current_database()")).scalar_one() == name
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261004_0012"
        # Seed through the actual execution and reviewed-memory workflows.
        sys.path.insert(0, str(Path("tests").resolve()))
        from test_phase11_postgres import publish, new_case, retrieve
        settings = Settings(environment="test", orchestration_lease_seconds=30)
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            _, _, record = publish(session, settings)
            current = new_case(session)
            statements = []
            def count_statement(*args):
                statements.append(1)
            event.listen(engine, "before_cursor_execute", count_statement)
            started = time.perf_counter()
            result = retrieve(session, settings, current)
            elapsed = time.perf_counter() - started
            event.remove(engine, "before_cursor_execute", count_statement)
            assert result["memories"]
            sample = {"eligible_candidates": 1, "returned": len(result["memories"]),
                "sql_statements_including_audit": len(statements), "elapsed_seconds": round(elapsed, 6),
                "serialized_context_bytes": len(json.dumps(result).encode()),
                "scope": "One local synthetic retrieval; not enterprise load/latency acceptance"}
        with engine.connect() as connection:
            plan = connection.execute(text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT v.id, m.case_id FROM memory_versions v
                JOIN operational_memories m ON m.id = v.memory_id
                WHERE v.category = :category AND v.status = 'ACTIVE' AND m.case_id <> :case_id
                ORDER BY v.created_at DESC, v.id DESC LIMIT 50"""),
                {"category": "PAYMENT_CONFIRMATION_MISMATCH", "case_id": current.id}).scalar_one()
        inspector = inspect(engine)
        original_tables = set(inspector.get_table_names()) - MEMORY_TABLES - {"alembic_version"}
        with engine.connect() as connection:
            before = snapshot(connection, original_tables)
        command.downgrade(config, "20261002_0011")
        assert not MEMORY_TABLES.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert snapshot(connection, original_tables) == before, "Existing Phase 1-10 rows changed during downgrade"
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert snapshot(connection, original_tables) == before, "Existing Phase 1-10 rows changed during re-upgrade"
            assert all(connection.execute(text('SELECT count(*) FROM "' + table + '"')).scalar_one() == 0 for table in MEMORY_TABLES)
        from app.models.base import Base
        inspector = inspect(engine)
        checks = {}
        for table_name in sorted(MEMORY_TABLES):
            model = Base.metadata.tables[table_name]
            columns = inspector.get_columns(table_name)
            assert {row["name"] for row in columns} == {column.name for column in model.columns}
            for row in columns:
                column = model.columns[row["name"]]
                assert row["nullable"] == column.nullable
                assert str(row["type"].compile(dialect=engine.dialect)) == str(column.type.compile(dialect=engine.dialect))
            assert inspector.get_pk_constraint(table_name)["constrained_columns"] == [column.name for column in model.primary_key]
            expected_unique = sorted((constraint.name, tuple(column.name for column in constraint.columns))
                for constraint in model.constraints if isinstance(constraint, UniqueConstraint))
            actual_unique = sorted((row["name"], tuple(row["column_names"]))
                for row in inspector.get_unique_constraints(table_name))
            assert actual_unique == expected_unique
            assert {row["name"] for row in inspector.get_check_constraints(table_name)} == {
                constraint.name for constraint in model.constraints if isinstance(constraint, CheckConstraint)}
            indexes = {row["name"]: row for row in inspector.get_indexes(table_name)}
            for index in model.indexes:
                assert index.name in indexes and indexes[index.name]["column_names"] == [column.name for column in index.columns]
                assert indexes[index.name]["unique"] == index.unique
            expected_fks = sorted((tuple(fk.parent.name for fk in constraint.elements),
                constraint.elements[0].column.table.name, tuple(fk.column.name for fk in constraint.elements))
                for constraint in model.foreign_key_constraints)
            actual_fks = sorted((tuple(row["constrained_columns"]), row["referred_table"], tuple(row["referred_columns"]))
                for row in inspector.get_foreign_keys(table_name))
            assert expected_fks == actual_fks
            checks[table_name] = {"columns": len(columns), "foreign_keys": len(actual_fks),
                "indexes": sorted(indexes), "unique_constraints": inspector.get_unique_constraints(table_name),
                "check_constraints": inspector.get_check_constraints(table_name)}
        assert {row["name"] for row in checks["memory_versions"]["check_constraints"]} == {
            "ck_memory_positive_version", "ck_memory_status", "ck_memory_summary_bound", "ck_memory_active_review"}
        active_index = next(row for row in inspector.get_indexes("memory_versions") if row["name"] == "uq_memory_active")
        assert "ACTIVE" in str(active_index["dialect_options"]["postgresql_where"])
        report = {"fresh_upgrade": "0001 -> 20261004_0012", "populated_round_trip": "0012 -> 0011 -> 0012",
            "source_tables_preserved": len(original_tables), "memory_artifacts_on_downgrade": "Dropped explicitly; source and audit history preserved",
            "constraints_and_indexes": checks, "source_snapshot": before,
            "retrieval_sample": sample, "candidate_query_plan": plan}
        Path("phase11-migration-results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        success = True
        print(f"Fresh 0012 upgrade, populated downgrade/re-upgrade and reflected constraints passed; {len(original_tables)} source tables preserved.")
    finally:
        engine.dispose()
        if success:
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
        else:
            Path(".phase11_migration_failed_test_db").write_text(name)
        admin.dispose()


if __name__ == "__main__":
    main()
