import json
import subprocess
import sys


def run_cli(*args, stdin_data=None, db_path=None, namespace=None):
    cmd = [sys.executable, "-m", "bigmem"]
    if db_path:
        cmd += ["--db", db_path]
    if namespace:
        cmd += ["--namespace", namespace]
    cmd += list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin_data,
    )
    return result


class TestPutGet:
    def test_put_and_get(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("put", "greeting", "hello world", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["key"] == "greeting"
        assert out["value"] == "hello world"

        r = run_cli("get", "greeting", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["key"] == "greeting"
        assert out["value"] == "hello world"

    def test_put_json_object(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("put", "config", '{"retries": 3}', db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["value"] == {"retries": 3}

    def test_get_raw(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "hello", db_path=db)
        r = run_cli("get", "k", "--raw", db_path=db)
        assert r.returncode == 0
        # --raw outputs just the value, not full fact JSON
        assert r.stdout.strip() == '"hello"'

    def test_get_not_found(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("get", "nonexistent", db_path=db)
        assert r.returncode == 1

    def test_put_with_tags(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("put", "k", "v", "--tags", "a,b", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["tags"] == ["a", "b"]

    def test_put_with_stdin(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("put", "k", "--stdin", db_path=db, stdin_data="hello from stdin")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["value"] == "hello from stdin"

    def test_put_with_source_session_ephemeral(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli(
            "put", "k", "v",
            "--source", "agent-1",
            "--session", "s1",
            "--ephemeral",
            db_path=db,
        )
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["source"] == "agent-1"
        assert out["session"] == "s1"
        assert out["ephemeral"] is True


class TestList:
    def test_list_all(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", db_path=db)
        run_cli("put", "b", "2", db_path=db)
        r = run_cli("list", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert len(out) == 2

    def test_list_filter_by_tags(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", "--tags", "x", db_path=db)
        run_cli("put", "b", "2", "--tags", "y", db_path=db)
        r = run_cli("list", "--tags", "x", db_path=db)
        out = json.loads(r.stdout)
        assert len(out) == 1
        assert out[0]["key"] == "a"

    def test_list_keys_only(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", db_path=db)
        run_cli("put", "b", "2", db_path=db)
        r = run_cli("list", "--keys-only", db_path=db)
        out = json.loads(r.stdout)
        assert out == ["a", "b"]


class TestSearch:
    def test_search(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "greeting", "hello world", db_path=db)
        run_cli("put", "farewell", "goodbye", db_path=db)
        r = run_cli("search", "hello", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert len(out) == 1
        assert out[0]["key"] == "greeting"

    def test_search_no_results(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", db_path=db)
        r = run_cli("search", "nonexistent_xyz", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out == []


class TestDelete:
    def test_delete(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", db_path=db)
        r = run_cli("delete", "k", db_path=db)
        assert r.returncode == 0
        r = run_cli("get", "k", db_path=db)
        assert r.returncode == 1

    def test_delete_not_found(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("delete", "nonexistent", db_path=db)
        assert r.returncode == 1


class TestSessionEnd:
    def test_session_end(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "e1", "v", "--ephemeral", "--session", "s1", db_path=db)
        run_cli("put", "p1", "v", "--session", "s1", db_path=db)
        r = run_cli("session-end", "s1", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["deleted"] == 1
        # ephemeral gone, persistent stays
        assert run_cli("get", "e1", db_path=db).returncode == 1
        assert run_cli("get", "p1", db_path=db).returncode == 0


class TestStats:
    def test_stats(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", db_path=db)
        r = run_cli("stats", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["total_facts"] == 1


class TestBatch:
    def test_batch_mixed_ops(self, tmp_path):
        db = str(tmp_path / "test.db")
        ndjson = "\n".join([
            json.dumps({"op": "put", "key": "a", "value": "1"}),
            json.dumps({"op": "put", "key": "b", "value": "2"}),
            json.dumps({"op": "get", "key": "a"}),
            json.dumps({"op": "delete", "key": "b"}),
            json.dumps({"op": "get", "key": "b"}),
        ])
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        assert r.returncode == 0
        lines = [json.loads(line) for line in r.stdout.strip().split("\n")]
        assert len(lines) == 5
        # put a
        assert lines[0]["ok"] is True
        # put b
        assert lines[1]["ok"] is True
        # get a
        assert lines[2]["ok"] is True
        assert lines[2]["result"]["value"] == 1  # "1" is valid JSON number
        # delete b
        assert lines[3]["ok"] is True
        # get b (not found)
        assert lines[4]["ok"] is False

    def test_batch_invalid_line(self, tmp_path):
        db = str(tmp_path / "test.db")
        ndjson = "not valid json\n" + json.dumps({"op": "put", "key": "a", "value": "1"})
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        assert r.returncode == 0
        lines = [json.loads(line) for line in r.stdout.strip().split("\n")]
        assert lines[0]["ok"] is False
        assert "error" in lines[0]
        assert lines[1]["ok"] is True


class TestNamespaceFlag:
    def test_namespace_isolation_via_cli(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "a", db_path=db, namespace="ns1")
        run_cli("put", "k", "b", db_path=db, namespace="ns2")
        r1 = run_cli("get", "k", db_path=db, namespace="ns1")
        r2 = run_cli("get", "k", db_path=db, namespace="ns2")
        assert json.loads(r1.stdout)["value"] == "a"
        assert json.loads(r2.stdout)["value"] == "b"
