from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Fact:
    key: str
    namespace: str = "default"
    value: str = "null"
    tags: str = ""
    source: str = ""
    session: str = ""
    ephemeral: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Parse value back to native Python for JSON output
        try:
            d["value"] = json.loads(d["value"])
        except (json.JSONDecodeError, TypeError):
            pass
        d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()] if d["tags"] else []
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_row(cls, row: tuple, columns: list[str]) -> Fact:
        data = dict(zip(columns, row))
        data["ephemeral"] = bool(data.get("ephemeral", 0))
        return cls(**data)
