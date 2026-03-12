from __future__ import annotations

import json
import re
import sqlite3
from typing import Optional

from bigmem.models import Fact

# Common English stopwords to strip from long queries
_STOPWORDS = frozenset(
  {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "and",
    "but",
    "or",
    "nor",
    "not",
    "so",
    "yet",
    "both",
    "either",
    "neither",
    "each",
    "every",
    "all",
    "any",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "only",
    "same",
    "than",
    "too",
    "very",
    "of",
    "in",
    "to",
    "for",
    "with",
    "on",
    "at",
    "from",
    "by",
    "about",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
  }
)

# FTS5 operator tokens — if present, the user is writing a raw FTS5 query
_FTS5_OPERATORS = re.compile(r'\b(AND|OR|NOT|NEAR)\b|[*"()]')


def _prepare_query(query: str) -> str:
  """Convert a natural-language query to an effective FTS5 query.

  Short queries (≤3 words) pass through with cleanup.
  Queries with FTS5 operators pass through as-is.
  Long queries (4+ words) get stopwords stripped and OR-joined so
  partial matches are returned instead of nothing.
  """
  query = query.strip()
  if not query:
    return query

  # Pass through raw FTS5 queries (contain explicit operators)
  if _FTS5_OPERATORS.search(query):
    return query

  # Clean punctuation that confuses FTS5
  # - hyphens become spaces (FTS5 treats - as column negation)
  # - strip trailing punctuation from words
  cleaned = re.sub(r"-", " ", query)
  words = [re.sub(r"[^\w]", "", w) for w in cleaned.split()]
  words = [w for w in words if w]  # drop empty

  if not words:
    return query

  if len(words) <= 3:
    return " ".join(words)

  # Strip stopwords, keep content words
  content_words = [w for w in words if w.lower() not in _STOPWORDS]
  if not content_words:
    content_words = words  # all stopwords? keep original

  # OR-join for recall-oriented search
  return " OR ".join(content_words)


COLUMNS = [
  "key",
  "namespace",
  "value",
  "tags",
  "source",
  "session",
  "ephemeral",
  "created_at",
  "updated_at",
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
  since: str = "",
  before: str = "",
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
  if since:
    clauses.append("created_at >= ?")
    params.append(since)
  if before:
    clauses.append("created_at < ?")
    params.append(before)

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
  exact: bool = False,
) -> list[Fact]:
  fts_query = query if exact else _prepare_query(query)
  cols = ", ".join("f." + c for c in COLUMNS)
  clauses = ["facts_fts MATCH ?", "f.namespace = ?"]
  params: list = [fts_query, namespace]
  if tags:
    clauses.append("f.tags LIKE ?")
    params.append(f"%{tags}%")
  where = " AND ".join(clauses)
  rows = conn.execute(
    f"""
        SELECT {cols} FROM facts f
        JOIN facts_fts fts ON f.rowid = fts.rowid
        WHERE {where}
        ORDER BY fts.rank
        LIMIT ? OFFSET ?
        """,
    params + [limit, offset],
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
  oldest = conn.execute("SELECT MIN(created_at) FROM facts").fetchone()[0]
  newest = conn.execute("SELECT MAX(created_at) FROM facts").fetchone()[0]

  # Tag distribution
  tag_counts: dict[str, int] = {}
  rows = conn.execute("SELECT tags FROM facts WHERE tags != ''").fetchall()
  for (tags_str,) in rows:
    for tag in tags_str.split(","):
      tag = tag.strip()
      if tag:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

  return {
    "total_facts": total,
    "namespaces": namespaces,
    "ephemeral_facts": ephemeral,
    "oldest": oldest,
    "newest": newest,
    "tags": tag_counts,
  }


def exists(
  conn: sqlite3.Connection,
  key: str,
  *,
  namespace: str = "default",
) -> bool:
  row = conn.execute(
    "SELECT 1 FROM facts WHERE key = ? AND namespace = ? LIMIT 1",
    (key, namespace),
  ).fetchone()
  return row is not None


def append(
  conn: sqlite3.Connection,
  key: str,
  value: str,
  *,
  namespace: str = "default",
  tags: str = "",
  source: str = "",
  session: str = "",
) -> Fact:
  """Append a value to a JSON array. Creates the array if key doesn't exist."""
  value = _normalize_value(value)
  parsed_new = json.loads(value)

  # BEGIN IMMEDIATE acquires a write lock upfront, preventing SQLITE_BUSY
  # between the read and the subsequent write (race condition).
  conn.execute("BEGIN IMMEDIATE")
  try:
    existing = get(conn, key, namespace=namespace)
    if existing is None:
      new_list = [parsed_new]
    else:
      existing_val = json.loads(existing.value)
      if isinstance(existing_val, list):
        new_list = existing_val + [parsed_new]
      else:
        new_list = [existing_val, parsed_new]

    result = put(
      conn,
      key,
      json.dumps(new_list),
      namespace=namespace,
      tags=tags or (existing.tags if existing else ""),
      source=source or (existing.source if existing else ""),
      session=session or (existing.session if existing else ""),
    )
    return result
  except Exception:
    conn.rollback()
    raise


def cleanup(
  conn: sqlite3.Connection,
  *,
  namespace: str = "default",
  before: str = "",
  tags: str = "",
) -> int:
  """Delete facts matching criteria. Pinned facts (tag 'pin') are always preserved."""
  clauses = ["tags NOT LIKE '%pin%'"]
  params: list = []

  if before:
    clauses.append("created_at < ?")
    params.append(before)
  if tags:
    clauses.append("tags LIKE ?")
    params.append(f"%{tags}%")

  if not before and not tags:
    return 0  # safety: require at least one filter

  where = " AND ".join(clauses)
  cursor = conn.execute(f"DELETE FROM facts WHERE {where}", params)
  conn.commit()
  return cursor.rowcount
