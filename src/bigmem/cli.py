from __future__ import annotations

import argparse
import json
import os
import sys

from bigmem.db import get_connection, init_db
from bigmem.store import put, get, list_facts, search, delete, session_end, stats


def _default_db() -> str:
    return os.path.join(os.path.expanduser("~"), ".bigmem.db")


def _output(data) -> None:
    if isinstance(data, str):
        sys.stdout.write(data + "\n")
    else:
        sys.stdout.write(json.dumps(data, indent=2) + "\n")


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
    _output(fact.to_dict())
    return 0


def cmd_get(args, conn) -> int:
    fact = get(conn, args.key, namespace=args.namespace)
    if fact is None:
        print(json.dumps({"error": "not found", "key": args.key}), file=sys.stderr)
        return 1
    if args.raw:
        sys.stdout.write(fact.value + "\n")
    else:
        _output(fact.to_dict())
    return 0


def cmd_list(args, conn) -> int:
    facts = list_facts(
        conn,
        namespace=args.namespace,
        tags=args.tags or "",
        session=args.session or "",
        ephemeral_only=args.ephemeral,
        persistent_only=args.persistent,
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
            else:
                print(json.dumps({"ok": False, "error": f"unknown op: {op}"}))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))

    return 0


def main():
    parser = argparse.ArgumentParser(prog="bigmem", description="SQLite-backed memory store for AI agents")
    parser.add_argument("--db", default=_default_db(), help="Path to SQLite database")
    parser.add_argument("--namespace", default="default", help="Namespace for facts")

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

    # get
    p_get = sub.add_parser("get", help="Get a fact by key")
    p_get.add_argument("key")
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

    # search
    p_search = sub.add_parser("search", help="Full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--tags", default="")
    p_search.add_argument("--limit", type=int, default=100)
    p_search.add_argument("--offset", type=int, default=0)

    # delete
    p_delete = sub.add_parser("delete", help="Delete a fact")
    p_delete.add_argument("key")

    # session-end
    p_session = sub.add_parser("session-end", help="Delete ephemeral facts for a session")
    p_session.add_argument("session_id")

    # stats
    sub.add_parser("stats", help="Show database statistics")

    # batch
    sub.add_parser("batch", help="Process NDJSON batch operations from stdin")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(2)

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
        "batch": cmd_batch,
    }

    rc = dispatch[args.command](args, conn)
    conn.close()
    sys.exit(rc)
