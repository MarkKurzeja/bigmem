from __future__ import annotations

import argparse
import json
import os
import sys

from bigmem import __version__
from bigmem.db import get_connection, init_db, close_connection
from bigmem.store import put, get, list_facts, search, delete, session_end, stats, cleanup, append, exists


def _default_db() -> str:
    return os.path.join(os.path.expanduser("~"), ".bigmem.db")


_pretty = False


def _output(data) -> None:
    if isinstance(data, str):
        sys.stdout.write(data + "\n")
    else:
        indent = 2 if _pretty else None
        sys.stdout.write(json.dumps(data, indent=indent, separators=(",", ":") if not _pretty else None) + "\n")


def cmd_put(args, conn) -> int:
    if args.stdin:
        value = sys.stdin.read().rstrip("\n")
    else:
        if args.value is None:
            print("error: value is required (or use --stdin)", file=sys.stderr)
            return 2
        value = args.value
    fact = put(
        conn,
        args.key,
        value,
        namespace=args.namespace,
        tags=args.tags or "",
        source=args.source or "",
        session=args.session or "",
        ephemeral=args.ephemeral,
    )
    if not args.quiet:
        _output(fact.to_dict())
    return 0


def cmd_get(args, conn) -> int:
    keys = args.keys
    if len(keys) == 1:
        fact = get(conn, keys[0], namespace=args.namespace)
        if fact is None:
            print(json.dumps({"error": "not found", "key": keys[0]}), file=sys.stderr)
            return 1
        if args.raw:
            sys.stdout.write(fact.value + "\n")
        else:
            _output(fact.to_dict())
        return 0
    # Multi-key: return array, include nulls for missing keys
    results = []
    any_found = False
    for key in keys:
        fact = get(conn, key, namespace=args.namespace)
        if fact:
            any_found = True
            results.append(fact.to_dict())
        else:
            results.append(None)
    if args.raw:
        for result in results:
            if result:
                sys.stdout.write(json.dumps(result["value"]) + "\n")
            else:
                sys.stdout.write("\n")
    else:
        _output(results)
    return 0 if any_found else 1


def cmd_list(args, conn) -> int:
    facts = list_facts(
        conn,
        namespace=args.namespace,
        tags=args.tags or "",
        session=args.session or "",
        ephemeral_only=args.ephemeral,
        persistent_only=args.persistent,
        since=args.since or "",
        before=args.before or "",
        limit=args.limit,
        offset=args.offset,
    )
    if args.keys_only:
        _output([f.key for f in facts])
    else:
        _output([f.to_dict() for f in facts])
    return 0


def cmd_search(args, conn) -> int:
    results = search(
        conn,
        args.query,
        namespace=args.namespace,
        tags=args.tags or "",
        limit=args.limit,
        offset=args.offset,
        exact=args.exact,
    )
    _output([f.to_dict() for f in results])
    return 0


def cmd_delete(args, conn) -> int:
    deleted = delete(conn, args.key, namespace=args.namespace)
    if not deleted:
        print(json.dumps({"error": "not found", "key": args.key}), file=sys.stderr)
        return 1
    _output({"deleted": True, "key": args.key})
    return 0


def cmd_session_end(args, conn) -> int:
    count = session_end(conn, args.session_id)
    _output({"deleted": count, "session": args.session_id})
    return 0


def cmd_stats(args, conn) -> int:
    _output(stats(conn))
    return 0


def cmd_exists(args, conn) -> int:
    found = exists(conn, args.key, namespace=args.namespace)
    _output({"exists": found, "key": args.key})
    return 0 if found else 1


def cmd_append(args, conn) -> int:
    if args.stdin:
        value = sys.stdin.read().rstrip("\n")
    else:
        if args.value is None:
            print("error: value is required (or use --stdin)", file=sys.stderr)
            return 2
        value = args.value
    fact = append(
        conn,
        args.key,
        value,
        namespace=args.namespace,
        tags=args.tags or "",
        source=args.source or "",
        session=args.session or "",
    )
    if not args.quiet:
        _output(fact.to_dict())
    return 0


def cmd_cleanup(args, conn) -> int:
    if not args.before and not args.tags:
        print("error: --before or --tags required", file=sys.stderr)
        return 2
    count = cleanup(
        conn,
        namespace=args.namespace,
        before=args.before or "",
        tags=args.tags or "",
    )
    _output({"deleted": count})
    return 0


def cmd_version(args, conn) -> int:
    _output({"version": __version__})
    return 0


def cmd_export(args, conn) -> int:
    facts = list_facts(
        conn,
        namespace=args.namespace,
        tags=args.tags or "",
    )
    if args.file:
        with open(args.file, "w") as f:
            for fact in facts:
                f.write(json.dumps(fact.to_dict()) + "\n")
        _output({"exported": len(facts), "file": args.file})
    else:
        for fact in facts:
            sys.stdout.write(json.dumps(fact.to_dict()) + "\n")
    return 0


def cmd_import(args, conn) -> int:
    count = 0
    with open(args.file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            put(
                conn,
                data["key"],
                json.dumps(data["value"]),
                namespace=data.get("namespace", args.namespace),
                tags=",".join(data["tags"]) if isinstance(data.get("tags"), list) else data.get("tags", ""),
                source=data.get("source", ""),
                session=data.get("session", ""),
                ephemeral=data.get("ephemeral", False),
            )
            count += 1
    _output({"imported": count, "file": args.file})
    return 0


def cmd_batch(args, conn) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            continue

        op = req.get("op")
        key = req.get("key")
        ns = req.get("namespace", args.namespace)

        try:
            if op == "put":
                fact = put(
                    conn,
                    key,
                    req.get("value", "null"),
                    namespace=ns,
                    tags=req.get("tags", ""),
                    source=req.get("source", ""),
                    session=req.get("session", ""),
                    ephemeral=req.get("ephemeral", False),
                )
                print(json.dumps({"ok": True, "result": fact.to_dict()}))
            elif op == "get":
                fact = get(conn, key, namespace=ns)
                if fact:
                    print(json.dumps({"ok": True, "result": fact.to_dict()}))
                else:
                    print(json.dumps({"ok": False, "error": "not found", "key": key}))
            elif op == "delete":
                deleted = delete(conn, key, namespace=ns)
                print(json.dumps({"ok": deleted, "key": key}))
            elif op == "exists":
                found = exists(conn, key, namespace=ns)
                print(json.dumps({"ok": True, "result": {"exists": found, "key": key}}))
            elif op == "append":
                fact = append(
                    conn,
                    key,
                    req.get("value", "null"),
                    namespace=ns,
                    tags=req.get("tags", ""),
                    source=req.get("source", ""),
                    session=req.get("session", ""),
                )
                print(json.dumps({"ok": True, "result": fact.to_dict()}))
            elif op == "search":
                results = search(
                    conn,
                    req.get("query", ""),
                    namespace=ns,
                    tags=req.get("tags", ""),
                    limit=req.get("limit", 100),
                )
                print(json.dumps({"ok": True, "result": [f.to_dict() for f in results]}))
            else:
                print(json.dumps({"ok": False, "error": f"unknown op: {op}"}))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))

    return 0


def main():
    parser = argparse.ArgumentParser(prog="bigmem", description="SQLite-backed memory store for AI agents")
    parser.add_argument("--db", default=_default_db(), help="Path to SQLite database")
    parser.add_argument("--namespace", default="default", help="Namespace for facts")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    sub = parser.add_subparsers(dest="command")

    # put
    p_put = sub.add_parser("put", help="Store a fact")
    p_put.add_argument("key")
    p_put.add_argument("value", nargs="?", default=None)
    p_put.add_argument("--tags", default="")
    p_put.add_argument("--source", default="")
    p_put.add_argument("--session", default="")
    p_put.add_argument("--ephemeral", action="store_true")
    p_put.add_argument("--stdin", action="store_true", help="Read value from stdin")
    p_put.add_argument("-q", "--quiet", action="store_true", help="Suppress output on success")

    # get
    p_get = sub.add_parser("get", help="Get fact(s) by key")
    p_get.add_argument("keys", nargs="+", metavar="key")
    p_get.add_argument("--raw", action="store_true", help="Output only the raw JSON value")

    # list
    p_list = sub.add_parser("list", help="List facts")
    p_list.add_argument("--tags", default="")
    p_list.add_argument("--session", default="")
    p_list.add_argument("--ephemeral", action="store_true")
    p_list.add_argument("--persistent", action="store_true")
    p_list.add_argument("--limit", type=int, default=100)
    p_list.add_argument("--offset", type=int, default=0)
    p_list.add_argument("--keys-only", action="store_true")
    p_list.add_argument("--since", default="", help="Only facts created at or after this ISO timestamp")
    p_list.add_argument("--before", default="", help="Only facts created before this ISO timestamp")

    # search
    p_search = sub.add_parser("search", help="Full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--tags", default="")
    p_search.add_argument("--limit", type=int, default=100)
    p_search.add_argument("--offset", type=int, default=0)
    p_search.add_argument("--exact", action="store_true", help="Disable smart OR-join; use raw FTS5 AND matching")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a fact")
    p_delete.add_argument("key")

    # session-end
    p_session = sub.add_parser("session-end", help="Delete ephemeral facts for a session")
    p_session.add_argument("session_id")

    # stats
    sub.add_parser("stats", help="Show database statistics")

    # exists
    p_exists = sub.add_parser("exists", help="Check if a key exists (exit 0=yes, 1=no)")
    p_exists.add_argument("key")

    # append
    p_append = sub.add_parser("append", help="Append a value to a JSON array")
    p_append.add_argument("key")
    p_append.add_argument("value", nargs="?", default=None)
    p_append.add_argument("--tags", default="")
    p_append.add_argument("--source", default="")
    p_append.add_argument("--session", default="")
    p_append.add_argument("--stdin", action="store_true")
    p_append.add_argument("-q", "--quiet", action="store_true")

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="Delete old or tagged facts (preserves pinned)")
    p_cleanup.add_argument("--before", default="", help="Delete facts created before this ISO timestamp")
    p_cleanup.add_argument("--tags", default="", help="Delete facts with this tag")

    # export
    p_export = sub.add_parser("export", help="Export facts as NDJSON")
    p_export.add_argument("--file", default="", help="Output file (default: stdout)")
    p_export.add_argument("--tags", default="", help="Filter by tag")

    # import
    p_import = sub.add_parser("import", help="Import facts from NDJSON file")
    p_import.add_argument("--file", required=True, help="Input NDJSON file")

    # version
    sub.add_parser("version", help="Show version")

    # batch
    sub.add_parser("batch", help="Process NDJSON batch operations from stdin")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(2)

    global _pretty
    _pretty = args.pretty

    conn = get_connection(args.db)
    init_db(conn)

    dispatch = {
        "put": cmd_put,
        "get": cmd_get,
        "list": cmd_list,
        "search": cmd_search,
        "delete": cmd_delete,
        "session-end": cmd_session_end,
        "stats": cmd_stats,
        "exists": cmd_exists,
        "append": cmd_append,
        "cleanup": cmd_cleanup,
        "export": cmd_export,
        "import": cmd_import,
        "version": cmd_version,
        "batch": cmd_batch,
    }

    rc = dispatch[args.command](args, conn)
    close_connection(conn)
    sys.exit(rc)
