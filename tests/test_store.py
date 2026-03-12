import json
import pytest

from bigmem.store import put, get, list_facts, search, delete, session_end, stats, cleanup, append, exists


# --- put / get basics ---

def test_put_and_get(conn):
    put(conn, "greeting", json.dumps("hello world"))
    fact = get(conn, "greeting")
    assert fact is not None
    assert fact.key == "greeting"
    assert json.loads(fact.value) == "hello world"


def test_put_auto_wraps_plain_string(conn):
    """If value is not valid JSON, store it as a JSON string."""
    put(conn, "name", "Alice")
    fact = get(conn, "name")
    assert json.loads(fact.value) == "Alice"


def test_put_preserves_valid_json(conn):
    put(conn, "config", '{"retries": 3}')
    fact = get(conn, "config")
    assert json.loads(fact.value) == {"retries": 3}


def test_put_preserves_json_number(conn):
    put(conn, "count", "42")
    fact = get(conn, "count")
    assert json.loads(fact.value) == 42


def test_put_preserves_json_array(conn):
    put(conn, "items", '[1, 2, 3]')
    fact = get(conn, "items")
    assert json.loads(fact.value) == [1, 2, 3]


def test_upsert_overwrites(conn):
    put(conn, "k", '"v1"')
    put(conn, "k", '"v2"')
    fact = get(conn, "k")
    assert json.loads(fact.value) == "v2"


def test_upsert_updates_updated_at(conn):
    put(conn, "k", '"v1"')
    first = get(conn, "k")
    put(conn, "k", '"v2"')
    second = get(conn, "k")
    assert second.updated_at >= first.updated_at


def test_get_not_found(conn):
    assert get(conn, "nonexistent") is None


# --- namespace isolation ---

def test_namespace_isolation(conn):
    put(conn, "k", '"a"', namespace="ns1")
    put(conn, "k", '"b"', namespace="ns2")
    assert json.loads(get(conn, "k", namespace="ns1").value) == "a"
    assert json.loads(get(conn, "k", namespace="ns2").value) == "b"


def test_get_default_namespace(conn):
    put(conn, "k", '"v"')
    assert get(conn, "k") is not None
    assert get(conn, "k", namespace="other") is None


# --- tags ---

def test_put_with_tags(conn):
    put(conn, "k", '"v"', tags="a,b,c")
    fact = get(conn, "k")
    assert fact.tags == "a,b,c"


# --- metadata fields ---

def test_put_with_source_and_session(conn):
    put(conn, "k", '"v"', source="agent-1", session="sess-1")
    fact = get(conn, "k")
    assert fact.source == "agent-1"
    assert fact.session == "sess-1"


def test_put_ephemeral(conn):
    put(conn, "k", '"v"', ephemeral=True, session="s1")
    fact = get(conn, "k")
    assert fact.ephemeral is True


# --- list ---

def test_list_all(conn):
    put(conn, "a", '"1"')
    put(conn, "b", '"2"')
    facts = list_facts(conn)
    assert len(facts) == 2


def test_list_filter_by_tags(conn):
    put(conn, "a", '"1"', tags="x,y")
    put(conn, "b", '"2"', tags="y,z")
    put(conn, "c", '"3"', tags="z")
    facts = list_facts(conn, tags="y")
    keys = {f.key for f in facts}
    assert keys == {"a", "b"}


def test_list_filter_by_session(conn):
    put(conn, "a", '"1"', session="s1")
    put(conn, "b", '"2"', session="s2")
    facts = list_facts(conn, session="s1")
    assert len(facts) == 1
    assert facts[0].key == "a"


def test_list_ephemeral_only(conn):
    put(conn, "a", '"1"', ephemeral=True, session="s1")
    put(conn, "b", '"2"')
    facts = list_facts(conn, ephemeral_only=True)
    assert len(facts) == 1
    assert facts[0].key == "a"


def test_list_persistent_only(conn):
    put(conn, "a", '"1"', ephemeral=True, session="s1")
    put(conn, "b", '"2"')
    facts = list_facts(conn, persistent_only=True)
    assert len(facts) == 1
    assert facts[0].key == "b"


def test_list_limit_offset(conn):
    for i in range(5):
        put(conn, f"k{i}", f'"{i}"')
    facts = list_facts(conn, limit=2, offset=1)
    assert len(facts) == 2


def test_list_by_namespace(conn):
    put(conn, "a", '"1"', namespace="ns1")
    put(conn, "b", '"2"', namespace="ns2")
    facts = list_facts(conn, namespace="ns1")
    assert len(facts) == 1


# --- time filters ---

def test_list_since(conn):
    put(conn, "old", '"v"')
    # Manually backdate one fact
    conn.execute(
        "UPDATE facts SET created_at = '2020-01-01T00:00:00.000Z', "
        "updated_at = '2020-01-01T00:00:00.000Z' WHERE key = 'old'"
    )
    conn.commit()
    put(conn, "new", '"v"')
    facts = list_facts(conn, since="2025-01-01T00:00:00Z")
    assert len(facts) == 1
    assert facts[0].key == "new"


def test_list_before(conn):
    put(conn, "old", '"v"')
    conn.execute(
        "UPDATE facts SET created_at = '2020-01-01T00:00:00.000Z', "
        "updated_at = '2020-01-01T00:00:00.000Z' WHERE key = 'old'"
    )
    conn.commit()
    put(conn, "new", '"v"')
    facts = list_facts(conn, before="2021-01-01T00:00:00Z")
    assert len(facts) == 1
    assert facts[0].key == "old"


def test_list_since_and_before(conn):
    for i, year in enumerate([2019, 2021, 2024]):
        put(conn, f"k{i}", f'"{i}"')
        conn.execute(
            f"UPDATE facts SET created_at = '{year}-06-01T00:00:00.000Z', "
            f"updated_at = '{year}-06-01T00:00:00.000Z' WHERE key = 'k{i}'"
        )
    conn.commit()
    facts = list_facts(conn, since="2020-01-01T00:00:00Z", before="2023-01-01T00:00:00Z")
    assert len(facts) == 1
    assert facts[0].key == "k1"


# --- search (FTS) ---

def test_search_by_value(conn):
    put(conn, "greeting", json.dumps("hello world"))
    put(conn, "farewell", json.dumps("goodbye"))
    results = search(conn, "hello")
    assert len(results) == 1
    assert results[0].key == "greeting"


def test_search_by_key(conn):
    put(conn, "user_preference", '"dark mode"')
    results = search(conn, "preference")
    assert len(results) == 1


def test_search_by_tag(conn):
    put(conn, "k1", '"v"', tags="important,urgent")
    put(conn, "k2", '"v"', tags="trivial")
    results = search(conn, "important")
    assert len(results) == 1
    assert results[0].key == "k1"


def test_search_with_tag_filter(conn):
    put(conn, "k1", json.dumps("hello"), tags="a")
    put(conn, "k2", json.dumps("hello"), tags="b")
    results = search(conn, "hello", tags="a")
    assert len(results) == 1
    assert results[0].key == "k1"


def test_search_limit(conn):
    for i in range(5):
        put(conn, f"k{i}", json.dumps(f"hello {i}"))
    results = search(conn, "hello", limit=2)
    assert len(results) == 2


def test_search_no_results(conn):
    put(conn, "k", '"v"')
    results = search(conn, "nonexistent_term_xyz")
    assert len(results) == 0


def test_search_smart_or_for_long_queries(conn):
    """Long queries (4+ words) auto-convert to OR-joined for better recall."""
    put(conn, "preterm-risk", json.dumps("prior preterm birth is the strongest risk factor"))
    put(conn, "cervical-length", json.dumps("short cervical length predicts preterm delivery"))
    put(conn, "unrelated", json.dumps("the weather is nice today"))
    # 4+ words → OR-joined: "preterm" OR "birth" OR "risk" OR "factor" OR "cervical"
    results = search(conn, "preterm birth risk factor cervical length screening")
    assert len(results) >= 2  # should find both preterm facts
    keys = {r.key for r in results}
    assert "preterm-risk" in keys
    assert "cervical-length" in keys


def test_search_short_query_stays_and(conn):
    """Short queries (≤3 words) keep implicit AND behavior."""
    put(conn, "k1", json.dumps("alpha beta"))
    put(conn, "k2", json.dumps("alpha gamma"))
    # "alpha beta" = 2 words, stays AND
    results = search(conn, "alpha beta")
    assert len(results) == 1
    assert results[0].key == "k1"


def test_search_exact_flag(conn):
    """exact=True bypasses smart OR-join."""
    put(conn, "k1", json.dumps("hello world foo bar baz"))
    # 5 words, but exact=True → AND (all words must match)
    results = search(conn, "hello world foo bar baz", exact=True)
    assert len(results) == 1
    # Query with word not in doc → 0 results with exact
    results = search(conn, "hello world foo bar nonexistent", exact=True)
    assert len(results) == 0


def test_search_fts5_operators_passthrough(conn):
    """Queries with explicit FTS5 operators pass through unchanged."""
    put(conn, "k1", json.dumps("apple banana"))
    put(conn, "k2", json.dumps("apple cherry"))
    # Explicit OR — should pass through even though it's 4+ words
    results = search(conn, "apple AND banana AND cherry AND orange")
    # Only k1 has banana, only k2 has cherry; AND means no single doc matches all
    assert len(results) == 0


# --- delete ---

def test_delete(conn):
    put(conn, "k", '"v"')
    deleted = delete(conn, "k")
    assert deleted is True
    assert get(conn, "k") is None


def test_delete_not_found(conn):
    deleted = delete(conn, "nonexistent")
    assert deleted is False


def test_delete_respects_namespace(conn):
    put(conn, "k", '"a"', namespace="ns1")
    put(conn, "k", '"b"', namespace="ns2")
    delete(conn, "k", namespace="ns1")
    assert get(conn, "k", namespace="ns1") is None
    assert get(conn, "k", namespace="ns2") is not None


# --- session_end ---

def test_session_end(conn):
    put(conn, "e1", '"v"', ephemeral=True, session="s1")
    put(conn, "e2", '"v"', ephemeral=True, session="s1")
    put(conn, "p1", '"v"', session="s1")  # persistent, same session
    put(conn, "e3", '"v"', ephemeral=True, session="s2")  # different session
    count = session_end(conn, "s1")
    assert count == 2
    assert get(conn, "e1") is None
    assert get(conn, "e2") is None
    assert get(conn, "p1") is not None
    assert get(conn, "e3") is not None


# --- stats ---

def test_stats_empty(conn):
    s = stats(conn)
    assert s["total_facts"] == 0
    assert s["namespaces"] == 0


def test_stats_with_data(conn):
    put(conn, "a", '"1"', namespace="ns1", tags="x")
    put(conn, "b", '"2"', namespace="ns1", tags="x,y")
    put(conn, "c", '"3"', namespace="ns2", ephemeral=True, session="s1")
    s = stats(conn)
    assert s["total_facts"] == 3
    assert s["namespaces"] == 2
    assert s["ephemeral_facts"] == 1


def test_stats_includes_tag_counts(conn):
    put(conn, "a", '"1"', tags="pin,decision")
    put(conn, "b", '"2"', tags="pin")
    put(conn, "c", '"3"', tags="debug")
    s = stats(conn)
    assert "tags" in s
    assert s["tags"]["pin"] == 2
    assert s["tags"]["decision"] == 1
    assert s["tags"]["debug"] == 1


def test_stats_includes_timestamps(conn):
    put(conn, "a", '"1"')
    s = stats(conn)
    assert "oldest" in s
    assert "newest" in s
    assert s["oldest"] is not None
    assert s["newest"] is not None


# --- cleanup ---

def test_cleanup_older_than(conn):
    put(conn, "old", '"v"')
    conn.execute(
        "UPDATE facts SET created_at = '2020-01-01T00:00:00.000Z', "
        "updated_at = '2020-01-01T00:00:00.000Z' WHERE key = 'old'"
    )
    conn.commit()
    put(conn, "new", '"v"')
    count = cleanup(conn, before="2021-01-01T00:00:00Z")
    assert count == 1
    assert get(conn, "old") is None
    assert get(conn, "new") is not None


def test_cleanup_skips_pinned(conn):
    put(conn, "old_pinned", '"v"', tags="pin,context")
    put(conn, "old_unpinned", '"v"', tags="context")
    conn.execute(
        "UPDATE facts SET created_at = '2020-01-01T00:00:00.000Z', "
        "updated_at = '2020-01-01T00:00:00.000Z' WHERE key LIKE 'old%'"
    )
    conn.commit()
    count = cleanup(conn, before="2021-01-01T00:00:00Z")
    assert count == 1
    assert get(conn, "old_pinned") is not None
    assert get(conn, "old_unpinned") is None


def test_cleanup_by_tag(conn):
    put(conn, "a", '"1"', tags="debug")
    put(conn, "b", '"2"', tags="decision")
    count = cleanup(conn, tags="debug")
    assert count == 1
    assert get(conn, "a") is None
    assert get(conn, "b") is not None


# --- append ---

def test_append_creates_list_if_key_missing(conn):
    fact = append(conn, "findings", "found bug in auth.py")
    assert json.loads(fact.value) == ["found bug in auth.py"]


def test_append_adds_to_existing_list(conn):
    append(conn, "findings", "item 1")
    append(conn, "findings", "item 2")
    fact = get(conn, "findings")
    assert json.loads(fact.value) == ["item 1", "item 2"]


def test_append_to_non_list_wraps_in_list(conn):
    put(conn, "k", '"existing scalar"')
    append(conn, "k", "new item")
    fact = get(conn, "k")
    assert json.loads(fact.value) == ["existing scalar", "new item"]


# --- exists ---

def test_exists_true(conn):
    put(conn, "k", '"v"')
    assert exists(conn, "k") is True


def test_exists_false(conn):
    assert exists(conn, "nonexistent") is False


def test_exists_respects_namespace(conn):
    put(conn, "k", '"v"', namespace="ns1")
    assert exists(conn, "k", namespace="ns1") is True
    assert exists(conn, "k", namespace="ns2") is False


def test_append_preserves_json_values(conn):
    append(conn, "k", '{"step": 1}')
    append(conn, "k", '{"step": 2}')
    fact = get(conn, "k")
    assert json.loads(fact.value) == [{"step": 1}, {"step": 2}]
