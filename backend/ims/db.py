"""Engine and session setup. The database file lives under data/ (git-ignored)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import UNASSIGNED_LOCATION_ID, UNASSIGNED_LOCATION_LABEL, Base, Location

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "ims.sqlite3"


def make_engine(db_path: Path | str | None = None) -> Engine:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
    else:
        url = "sqlite://"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):  # pragma: no cover - trivial
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _add_missing_columns(engine: Engine) -> None:
    """Small in-place migrations for databases created before a column existed.

    create_all() creates new tables but never adds columns to existing ones.
    Replace this with Alembic before the schema changes more.
    """
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(location)").all()}
        if cols and "name" not in cols:
            conn.exec_driver_sql("ALTER TABLE location ADD COLUMN name VARCHAR(120)")


def init_db(engine: Engine) -> None:
    """Create tables and the reserved 'Sem localização' location. Idempotent."""
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    with Session(engine) as session:
        if session.get(Location, UNASSIGNED_LOCATION_ID) is None:
            session.add(Location(id=UNASSIGNED_LOCATION_ID, estante=None, prateleira=None))
            session.commit()


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


__all__ = ["make_engine", "init_db", "session_factory", "UNASSIGNED_LOCATION_LABEL"]
