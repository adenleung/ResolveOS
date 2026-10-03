from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


class DatabaseManager:
    def __init__(self, database_url: str, echo: bool = False):
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=echo, future=True)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_all(self) -> None:
        import app.classification.models  # noqa: F401
        import app.correlation.models  # noqa: F401
        import app.ingestion.models  # noqa: F401
        import app.orchestration.models  # noqa: F401
        import app.investigation.models  # noqa: F401
        import app.supervisor.models  # noqa: F401
        import app.controls.models  # noqa: F401
        import app.execution.models  # noqa: F401
        import app.simulator.models  # noqa: F401
        import app.memory.models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.session_factory()

    def check_connection(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def drop_all(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
