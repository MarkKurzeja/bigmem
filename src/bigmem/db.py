import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5.0)
    # WAL mode: concurrent readers, non-blocking writes
    conn.execute("PRAGMA journal_mode=WAL")
    # NORMAL sync is safe with WAL and avoids fsync on every commit
    conn.execute("PRAGMA synchronous=NORMAL")
    # Wait up to 5s for locks instead of failing immediately
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    # Performance: 64MB page cache, 256MB mmap, temp tables in memory
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")
    # Cap WAL file at 64MB to prevent unbounded growth
    conn.execute("PRAGMA journal_size_limit=67108864")
    # Analyze all tables for query planner on open (not just queried ones)
    conn.execute("PRAGMA optimize=0x10002")
    return conn


def close_connection(conn: sqlite3.Connection) -> None:
    """Close connection with optimize pass for query planner stats."""
    try:
        conn.execute("PRAGMA optimize")
    except sqlite3.OperationalError:
        pass  # best-effort; may fail under heavy concurrent load
    conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            key TEXT NOT NULL,
            namespace TEXT NOT NULL DEFAULT 'default',
            value TEXT NOT NULL DEFAULT 'null',
            tags TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            session TEXT NOT NULL DEFAULT '',
            ephemeral INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            PRIMARY KEY (key, namespace)
        );

        CREATE INDEX IF NOT EXISTS idx_facts_tags ON facts(tags);
        CREATE INDEX IF NOT EXISTS idx_facts_namespace ON facts(namespace);
        CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session) WHERE ephemeral = 1;

        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            key, value, tags,
            content='facts',
            content_rowid='rowid'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
            INSERT INTO facts_fts(rowid, key, value, tags)
            VALUES (new.rowid, new.key, new.value, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
            INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
            VALUES ('delete', old.rowid, old.key, old.value, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
            INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
            VALUES ('delete', old.rowid, old.key, old.value, old.tags);
            INSERT INTO facts_fts(rowid, key, value, tags)
            VALUES (new.rowid, new.key, new.value, new.tags);
        END;
    """)
