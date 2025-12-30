from __future__ import annotations

import pytest

from src.api.pagination import Cursor, CursorError, decode_cursor, encode_cursor


def test_cursor_roundtrip() -> None:
    c = Cursor(created_at=123.456, item_id="evt_abc")
    encoded = encode_cursor(c)
    decoded = decode_cursor(encoded)
    assert decoded.created_at == pytest.approx(c.created_at)
    assert decoded.item_id == c.item_id


def test_cursor_invalid() -> None:
    with pytest.raises(CursorError):
        decode_cursor("not-a-valid-cursor")

