#!/usr/bin/env python3
"""
Run before uvicorn in Docker.

DBs bootstrapped with the old ``Base.metadata.create_all()`` have tables but no
``alembic_version`` row. In that case ``alembic upgrade`` would re-apply 0001
and crash with DuplicateTable. We stamp 0001 once, then apply only pending
revisions (e.g. 0002).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

API_ROOT = Path(__file__).resolve().parent.parent


def _sync_url() -> str:
    sys.path.insert(0, str(API_ROOT))
    os.chdir(API_ROOT)
    from app.core.config import get_settings

    return get_settings().database_url.replace("+asyncpg", "+psycopg2")


def _table_exists(conn, name: str) -> bool:
    r = conn.execute(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name)"
        ),
        {"name": name},
    )
    return bool(r.scalar())


def _alembic_revision(conn) -> str | None:
    if not _table_exists(conn, "alembic_version"):
        return None
    r = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    row = r.first()
    return row[0] if row else None


def main() -> int:
    url = _sync_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        has_users = _table_exists(conn, "users")
        rev = _alembic_revision(conn)

    if has_users and rev is None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "stamp", "0001"],
            cwd=API_ROOT,
            check=True,
        )

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
