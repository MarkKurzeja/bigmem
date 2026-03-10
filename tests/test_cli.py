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


class TestTimeFilters:
    def test_list_since_cli(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", "-q", db_path=db)
        # Everything was just created, so --since far past should include it
        r = run_cli("list", "--since", "2020-01-01T00:00:00Z", db_path=db)
        out = json.loads(r.stdout)
        assert len(out) == 1
        # --since far future should exclude it
        r = run_cli("list", "--since", "2099-01-01T00:00:00Z", db_path=db)
        out = json.loads(r.stdout)
        assert len(out) == 0

    def test_list_before_cli(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", "-q", db_path=db)
        # --before far future should include it
        r = run_cli("list", "--before", "2099-01-01T00:00:00Z", db_path=db)
        out = json.loads(r.stdout)
        assert len(out) == 1
        # --before far past should exclude it
        r = run_cli("list", "--before", "2020-01-01T00:00:00Z", db_path=db)
        out = json.loads(r.stdout)
        assert len(out) == 0


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

    def test_batch_search_op(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "greeting", "hello world", "-q", db_path=db)
        ndjson = json.dumps({"op": "search", "query": "hello"})
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        assert r.returncode == 0
        result = json.loads(r.stdout.strip())
        assert result["ok"] is True
        assert len(result["result"]) == 1
        assert result["result"][0]["key"] == "greeting"

    def test_batch_append_op(self, tmp_path):
        db = str(tmp_path / "test.db")
        ndjson = "\n".join([
            json.dumps({"op": "append", "key": "log", "value": "step 1"}),
            json.dumps({"op": "append", "key": "log", "value": "step 2"}),
            json.dumps({"op": "get", "key": "log"}),
        ])
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        lines = [json.loads(l) for l in r.stdout.strip().split("\n")]
        assert lines[2]["ok"] is True
        assert lines[2]["result"]["value"] == ["step 1", "step 2"]

    def test_batch_exists_op(self, tmp_path):
        db = str(tmp_path / "test.db")
        ndjson = "\n".join([
            json.dumps({"op": "put", "key": "k", "value": "v"}),
            json.dumps({"op": "exists", "key": "k"}),
            json.dumps({"op": "exists", "key": "missing"}),
        ])
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        lines = [json.loads(l) for l in r.stdout.strip().split("\n")]
        assert lines[1]["ok"] is True
        assert lines[1]["result"]["exists"] is True
        assert lines[2]["ok"] is True
        assert lines[2]["result"]["exists"] is False

    def test_batch_invalid_line(self, tmp_path):
        db = str(tmp_path / "test.db")
        ndjson = "not valid json\n" + json.dumps({"op": "put", "key": "a", "value": "1"})
        r = run_cli("batch", db_path=db, stdin_data=ndjson)
        assert r.returncode == 0
        lines = [json.loads(line) for line in r.stdout.strip().split("\n")]
        assert lines[0]["ok"] is False
        assert "error" in lines[0]
        assert lines[1]["ok"] is True


class TestExists:
    def test_exists_found(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", "-q", db_path=db)
        r = run_cli("exists", "k", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["exists"] is True

    def test_exists_not_found(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("exists", "k", db_path=db)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["exists"] is False


class TestAppend:
    def test_append_creates_and_accumulates(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("append", "findings", "bug in auth", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["value"] == ["bug in auth"]

        r = run_cli("append", "findings", "XSS in form", db_path=db)
        out = json.loads(r.stdout)
        assert out["value"] == ["bug in auth", "XSS in form"]

    def test_append_quiet(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("append", "k", "v", "-q", db_path=db)
        assert r.returncode == 0
        assert r.stdout == ""


class TestCleanup:
    def test_cleanup_by_tag(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", "--tags", "debug", "-q", db_path=db)
        run_cli("put", "b", "2", "--tags", "pin", "-q", db_path=db)
        r = run_cli("cleanup", "--tags", "debug", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["deleted"] == 1
        assert run_cli("get", "a", db_path=db).returncode == 1
        assert run_cli("get", "b", db_path=db).returncode == 0

    def test_cleanup_requires_filter(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("cleanup", db_path=db)
        assert r.returncode == 2


class TestQuiet:
    def test_put_quiet(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("put", "k", "v", "-q", db_path=db)
        assert r.returncode == 0
        assert r.stdout == ""
        # fact was still stored
        r = run_cli("get", "k", db_path=db)
        assert r.returncode == 0
        assert json.loads(r.stdout)["value"] == "v"


class TestMultiGet:
    def test_multi_key_get(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", "-q", db_path=db)
        run_cli("put", "b", "2", "-q", db_path=db)
        r = run_cli("get", "a", "b", db_path=db)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert len(out) == 2
        assert out[0]["key"] == "a"
        assert out[1]["key"] == "b"

    def test_multi_key_get_with_missing(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", "-q", db_path=db)
        r = run_cli("get", "a", "missing", db_path=db)
        assert r.returncode == 0  # at least one found
        out = json.loads(r.stdout)
        assert out[0]["key"] == "a"
        assert out[1] is None

    def test_multi_key_raw(self, tmp_path):
        """Multi-key --raw should output one value per line."""
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "hello", "-q", db_path=db)
        run_cli("put", "b", '{"x": 1}', "-q", db_path=db)
        r = run_cli("get", "a", "b", "--raw", db_path=db)
        assert r.returncode == 0
        lines = r.stdout.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == "hello"
        assert json.loads(lines[1]) == {"x": 1}

    def test_multi_key_all_missing(self, tmp_path):
        db = str(tmp_path / "test.db")
        r = run_cli("get", "x", "y", db_path=db)
        assert r.returncode == 1


class TestCompactOutput:
    def test_default_is_compact(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "v", "-q", db_path=db)
        r = run_cli("get", "k", db_path=db)
        # compact output has no newlines inside the JSON
        assert "\n" not in r.stdout.strip()

    def test_pretty_flag(self, tmp_path):
        db = str(tmp_path / "test.db")
        cmd = [sys.executable, "-m", "bigmem", "--db", db, "--pretty", "put", "k", "v"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0
        # pretty output has newlines inside the JSON
        assert "\n" in r.stdout.strip()


class TestVersion:
    def test_version(self, tmp_path):
        r = run_cli("version", db_path=str(tmp_path / "test.db"))
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert "version" in out


class TestExportImport:
    def test_export_and_import(self, tmp_path):
        db1 = str(tmp_path / "src.db")
        db2 = str(tmp_path / "dst.db")
        export_file = str(tmp_path / "dump.ndjson")

        run_cli("put", "a", "1", "--tags", "x", "-q", db_path=db1)
        run_cli("put", "b", "2", "--tags", "y", "-q", db_path=db1)

        # Export
        r = run_cli("export", "--file", export_file, db_path=db1)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["exported"] == 2

        # Import into a different db
        r = run_cli("import", "--file", export_file, db_path=db2)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["imported"] == 2

        # Verify data transferred
        r = run_cli("get", "a", db_path=db2)
        assert r.returncode == 0
        assert json.loads(r.stdout)["value"] == 1

    def test_export_with_tag_filter(self, tmp_path):
        db = str(tmp_path / "test.db")
        export_file = str(tmp_path / "dump.ndjson")
        run_cli("put", "a", "1", "--tags", "pin", "-q", db_path=db)
        run_cli("put", "b", "2", "--tags", "debug", "-q", db_path=db)

        r = run_cli("export", "--file", export_file, "--tags", "pin", db_path=db)
        out = json.loads(r.stdout)
        assert out["exported"] == 1

    def test_export_to_stdout(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "a", "1", "-q", db_path=db)
        r = run_cli("export", db_path=db)
        assert r.returncode == 0
        lines = [l for l in r.stdout.strip().split("\n") if l]
        assert len(lines) == 1
        fact = json.loads(lines[0])
        assert fact["key"] == "a"


class TestNamespaceFlag:
    def test_namespace_isolation_via_cli(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("put", "k", "a", db_path=db, namespace="ns1")
        run_cli("put", "k", "b", db_path=db, namespace="ns2")
        r1 = run_cli("get", "k", db_path=db, namespace="ns1")
        r2 = run_cli("get", "k", db_path=db, namespace="ns2")
        assert json.loads(r1.stdout)["value"] == "a"
        assert json.loads(r2.stdout)["value"] == "b"
