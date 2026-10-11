"""Own only a newly created disposable database; never reset the admin database."""
from contextlib import contextmanager
import os
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.config import Settings
from app.database import DatabaseManager


@contextmanager
def disposable_database():
    settings = Settings()
    if not settings.database_url.startswith("postgresql"):
        raise ValueError("PostgreSQL administrative DATABASE_URL is required")
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    name = "resolveos_backend_verify_" + uuid4().hex[:10]
    original_url = os.environ.get("DATABASE_URL")
    original_live = os.environ.get("INVESTIGATOR_LIVE_ENABLED")
    database = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text('CREATE DATABASE "' + name + '"'))
        created = True
        os.environ["DATABASE_URL"] = admin.url.set(database=name).render_as_string(hide_password=False)
        os.environ["INVESTIGATOR_LIVE_ENABLED"] = "false"
        command.upgrade(Config("alembic.ini"), "head")
        settings = Settings(environment="test", investigator_live_enabled=False)
        database = DatabaseManager(settings.database_url)
        yield database, settings
    finally:
        if database:
            database.engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + name + '" WITH (FORCE)'))
        admin.dispose()
        for key, previous in (("DATABASE_URL", original_url), ("INVESTIGATOR_LIVE_ENABLED", original_live)):
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
