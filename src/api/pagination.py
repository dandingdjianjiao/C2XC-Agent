from __future__ import annotations

import base64
import json
from dataclasses import dataclass


class CursorError(ValueError):
    pass


@dataclass(frozen=True)
class Cursor:
    created_at: float
    item_id: str


def encode_cursor(cursor: Cursor) -> str:
    raw = json.dumps({"created_at": cursor.created_at, "id": cursor.item_id}, separators=(",", ":")).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> Cursor:
    s = (value or "").strip()
    if not s:
        raise CursorError("Empty cursor")

    # Add padding for base64 decoding.
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    try:
        raw = base64.urlsafe_b64decode((s + pad).encode("ascii")).decode("utf-8")
        obj = json.loads(raw)
        return Cursor(created_at=float(obj["created_at"]), item_id=str(obj["id"]))
    except Exception as e:
        raise CursorError("Invalid cursor") from e
