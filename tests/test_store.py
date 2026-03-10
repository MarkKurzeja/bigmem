import json
import pytest

from bigmem.store import put, get, list_facts, search, delete, session_end, stats


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
