"""Guard the Alembic chain against drifting from the models.

Local development creates tables straight from ``Base.metadata``, so nothing in
the normal test path would notice a broken or incomplete migration until a
PostgreSQL deploy ran ``alembic upgrade head`` and failed. These tests run the
real chain and diff the result against the declared schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.config import get_settings
from app.database import Base

API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def _schema(path: Path) -> dict[str, set[str]]:
    connection = sqlite3.connect(path)
    try:
        tables = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        return {
            table: {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")}
            for table in tables
        }
    finally:
        connection.close()


def test_migration_chain_has_a_single_head():
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert heads == ["004"], f"expected one head, found {heads}"


def test_migrations_build_the_schema_the_models_declare(tmp_path, monkeypatch):
    """Run the chain on SQLite and diff it against ``Base.metadata``.

    Running on SQLite also keeps the migrations portable: an earlier revision
    used PostgreSQL's ``now()`` as a server default, which no other backend
    accepts. Every default has to render on both engines for this to pass.
    """

    migrated = tmp_path / "migrated.db"
    # env.py takes its URL from the cached settings object, so point that at the
    # temporary file rather than the in-memory database the suite normally uses.
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite+aiosqlite:///{migrated.as_posix()}")
    command.upgrade(_alembic_config(), "head")

    declared = tmp_path / "declared.db"
    engine = create_engine(f"sqlite:///{declared.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    from_migrations = _schema(migrated)
    from_models = _schema(declared)
    assert from_migrations.pop("alembic_version", None) is not None, "alembic did not stamp a version"

    assert set(from_migrations) == set(from_models)
    for table, columns in from_models.items():
        assert from_migrations[table] == columns, f"{table} columns differ"
