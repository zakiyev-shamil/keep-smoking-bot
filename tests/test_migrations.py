from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=Path(__file__).parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _tables(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def test_migration_20260718_03_upgrade_downgrade_and_schema_check(tmp_path):
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

    _alembic(database_url, "upgrade", "head")
    assert {"event_poll_options", "event_poll_votes"} <= _tables(database_path)
    _alembic(database_url, "check")

    _alembic(database_url, "downgrade", "20260718_02")
    assert "events" in _tables(database_path)
    assert "event_poll_options" not in _tables(database_path)
    assert "event_poll_votes" not in _tables(database_path)

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "downgrade", "base")
    assert "users" not in _tables(database_path)
