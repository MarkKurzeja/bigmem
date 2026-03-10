import sqlite3

from bigmem.db import get_connection, init_db


def test_get_connection_returns_sqlite_connection(db_path):
    conn = get_connection(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_wal_mode_enabled(db_path):
    conn = get_connection(db_path)
    init_db(conn)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_facts_table_exists(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
    ).fetchall()
    assert len(tables) == 1


def test_fts_table_exists(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts_fts'"
    ).fetchall()
    assert len(tables) == 1


def test_init_db_is_idempotent(conn):
    # calling init_db again should not raise
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
    ).fetchall()
    assert len(tables) == 1


def test_facts_table_has_correct_columns(conn):
    cursor = conn.execute("PRAGMA table_info(facts)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        "key", "namespace", "value", "tags", "source",
        "session", "ephemeral", "created_at", "updated_at",
    }
    assert expected == columns


def test_composite_primary_key(conn):
    # Insert same key in different namespaces — should work
    conn.execute(
        "INSERT INTO facts (key, namespace, value) VALUES (?, ?, ?)",
        ("k1", "ns1", '"v1"'),
    )
    conn.execute(
        "INSERT INTO facts (key, namespace, value) VALUES (?, ?, ?)",
        ("k1", "ns2", '"v2"'),
    )
    conn.commit()
    rows = conn.execute("SELECT * FROM facts WHERE key='k1'").fetchall()
    assert len(rows) == 2

    # Duplicate (key, namespace) should fail
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO facts (key, namespace, value) VALUES (?, ?, ?)",
            ("k1", "ns1", '"v3"'),
        )
