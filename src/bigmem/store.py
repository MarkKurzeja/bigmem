from __future__ import annotations

import json
import sqlite3
from typing import Optional

from bigmem.models import Fact

COLUMNS = [
    "key", "namespace", "value", "tags", "source",
    "session", "ephemeral", "created_at", "updated_at",
]


def _normalize_value(value: str) -> str:
    """Ensure value is valid JSON. If not, wrap it as a JSON string."""
    try:
        json.loads(value)
        return value
    except (json.JSONDecodeError, TypeError):
        return json.dumps(value)


def put(
    conn: sqlite3.Connection,
    key: str,
    value: str,
    *,
    namespace: str = "default",
    tags: str = "",
    source: str = "",
    session: str = "",
    ephemeral: bool = False,
) -> Fact:
    value = _normalize_value(value)
    conn.execute(
        """
        INSERT INTO facts (key, namespace, value, tags, source, session, ephemeral)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key, namespace) DO UPDATE SET
            value = excluded.value,
            tags = excluded.tags,
            source = excluded.source,
            session = excluded.session,
            ephemeral = excluded.ephemeral,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        """,
        (key, namespace, value, tags, source, session, int(ephemeral)),
    )
    conn.commit()
    return get(conn, key, namespace=namespace)


def get(
    conn: sqlite3.Connection,
    key: str,
    *,
    namespace: str = "default",
) -> Optional[Fact]:
    row = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM facts WHERE key = ? AND namespace = ?",
        (key, namespace),
    ).fetchone()
    if row is None:
        return None
    return Fact.from_row(row, COLUMNS)


def list_facts(
    conn: sqlite3.Connection,
    *,
    namespace: str = "default",
    tags: str = "",
    session: str = "",
    ephemeral_only: bool = False,
    persistent_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Fact]:
    clauses = ["namespace = ?"]
    params: list = [namespace]

    if tags:
        clauses.append("tags LIKE ?")
        params.append(f"%{tags}%")
    if session:
        clauses.append("session = ?")
        params.append(session)
    if ephemeral_only:
        clauses.append("ephemeral = 1")
    if persistent_only:
        clauses.append("ephemeral = 0")

    where = " AND ".join(clauses)
    rows = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM facts WHERE {where} ORDER BY key LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [Fact.from_row(r, COLUMNS) for r in rows]


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    namespace: str = "default",
    tags: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[Fact]:
    if tags:
        rows = conn.execute(
            f"""
            SELECT {', '.join('f.' + c for c in COLUMNS)}
            FROM facts f
            JOIN facts_fts fts ON f.rowid = fts.rowid
            WHERE facts_fts MATCH ? AND f.namespace = ? AND f.tags LIKE ?
            ORDER BY fts.rank
            LIMIT ? OFFSET ?
            """,
            (query, namespace, f"%{tags}%", limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT {', '.join('f.' + c for c in COLUMNS)}
            FROM facts f
            JOIN facts_fts fts ON f.rowid = fts.rowid
            WHERE facts_fts MATCH ? AND f.namespace = ?
            ORDER BY fts.rank
            LIMIT ? OFFSET ?
            """,
            (query, namespace, limit, offset),
        ).fetchall()
    return [Fact.from_row(r, COLUMNS) for r in rows]


def delete(
    conn: sqlite3.Connection,
    key: str,
    *,
    namespace: str = "default",
) -> bool:
    cursor = conn.execute(
        "DELETE FROM facts WHERE key = ? AND namespace = ?",
        (key, namespace),
    )
    conn.commit()
    return cursor.rowcount > 0


def session_end(conn: sqlite3.Connection, session_id: str) -> int:
    cursor = conn.execute(
        "DELETE FROM facts WHERE session = ? AND ephemeral = 1",
        (session_id,),
    )
    conn.commit()
    return cursor.rowcount


def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    namespaces = conn.execute("SELECT COUNT(DISTINCT namespace) FROM facts").fetchone()[0]
    ephemeral = conn.execute("SELECT COUNT(*) FROM facts WHERE ephemeral = 1").fetchone()[0]
    return {
        "total_facts": total,
        "namespaces": namespaces,
        "ephemeral_facts": ephemeral,
    }
