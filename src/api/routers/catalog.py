from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.api.errors import APIError
from src.api.pagination import Cursor, CursorError, decode_cursor, encode_cursor
from src.storage.sqlite_store import SQLiteStore


router = APIRouter()


class CreateProductRequest(BaseModel):
    name: str = Field(min_length=1)
    status: str = Field(default="active")
    schema_version: int = Field(default=1)
    extra: dict[str, Any] = Field(default_factory=dict)


class UpdateProductRequest(BaseModel):
    name: str | None = Field(default=None)
    status: str | None = Field(default=None)
    schema_version: int | None = Field(default=None)
    extra: dict[str, Any] | None = Field(default=None)


@router.get("/products")
def list_products(
    limit: int = Query(default=200, ge=1, le=200),
    cursor: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        cursor_obj: Cursor | None = None
        if cursor:
            try:
                cursor_obj = decode_cursor(cursor)
            except CursorError as e:
                raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e

        page = store.list_products_page(
            limit=int(limit),
            cursor=(cursor_obj.created_at, cursor_obj.item_id) if cursor_obj is not None else None,
            statuses=status or None,
        )
        next_cursor = page.get("next_cursor")
        if next_cursor is not None:
            created_at, product_id = next_cursor
            page["next_cursor"] = encode_cursor(Cursor(created_at=float(created_at), item_id=str(product_id)))
        return page
    finally:
        store.close()


@router.get("/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        row = store.get_product(product_id=product_id)
        if row is None:
            raise APIError(status_code=404, code="not_found", message="Product not found.")
        return {
            "product": {
                "product_id": row["product_id"],
                "created_at": float(row["created_at"]),
                "updated_at": float(row["updated_at"]),
                "name": row["name"],
                "status": row["status"],
                "schema_version": int(row["schema_version"]),
                "extra": json.loads(str(row["extra_json"] or "{}")),
            }
        }
    finally:
        store.close()


@router.post("/products")
def create_product(body: CreateProductRequest) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        try:
            rec = store.create_product(
                name=body.name,
                status=body.status,
                schema_version=int(body.schema_version),
                extra=body.extra,
            )
        except ValueError as e:
            raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e
        except sqlite3.IntegrityError as e:
            raise APIError(status_code=409, code="conflict", message="Product name already exists.") from e
        return {
            "product": {
                "product_id": rec.product_id,
                "created_at": float(rec.created_at),
                "updated_at": float(rec.updated_at),
                "name": rec.name,
                "status": rec.status,
                "schema_version": int(body.schema_version),
                "extra": body.extra,
            }
        }
    finally:
        store.close()


@router.put("/products/{product_id}")
def update_product(product_id: str, body: UpdateProductRequest) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        if store.get_product(product_id=product_id) is None:
            raise APIError(status_code=404, code="not_found", message="Product not found.")
        try:
            store.update_product(
                product_id=product_id,
                name=body.name,
                status=body.status,
                schema_version=body.schema_version,
                extra=body.extra,
            )
        except ValueError as e:
            raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e
        except sqlite3.IntegrityError as e:
            raise APIError(status_code=409, code="conflict", message="Product name already exists.") from e

        row = store.get_product(product_id=product_id)
        assert row is not None
        return {
            "product": {
                "product_id": row["product_id"],
                "created_at": float(row["created_at"]),
                "updated_at": float(row["updated_at"]),
                "name": row["name"],
                "status": row["status"],
                "schema_version": int(row["schema_version"]),
                "extra": json.loads(str(row["extra_json"] or "{}")),
            }
        }
    finally:
        store.close()


class CreatePresetRequest(BaseModel):
    name: str = Field(min_length=1)
    product_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="active")
    schema_version: int = Field(default=1)
    extra: dict[str, Any] = Field(default_factory=dict)


class UpdatePresetRequest(BaseModel):
    name: str | None = Field(default=None)
    product_ids: list[str] | None = Field(default=None)
    status: str | None = Field(default=None)
    schema_version: int | None = Field(default=None)
    extra: dict[str, Any] | None = Field(default=None)


@router.get("/product_presets")
def list_product_presets(
    limit: int = Query(default=200, ge=1, le=200),
    cursor: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        cursor_obj: Cursor | None = None
        if cursor:
            try:
                cursor_obj = decode_cursor(cursor)
            except CursorError as e:
                raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e

        page = store.list_product_presets_page(
            limit=int(limit),
            cursor=(cursor_obj.created_at, cursor_obj.item_id) if cursor_obj is not None else None,
            statuses=status or None,
        )
        next_cursor = page.get("next_cursor")
        if next_cursor is not None:
            created_at, preset_id = next_cursor
            page["next_cursor"] = encode_cursor(Cursor(created_at=float(created_at), item_id=str(preset_id)))
        return page
    finally:
        store.close()


@router.get("/product_presets/{preset_id}")
def get_product_preset(preset_id: str) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        item = store.get_product_preset_item(preset_id=preset_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Preset not found.")
        return {"preset": item}
    finally:
        store.close()


@router.post("/product_presets")
def create_product_preset(body: CreatePresetRequest) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        try:
            rec = store.create_product_preset(
                name=body.name,
                product_ids=body.product_ids,
                status=body.status,
                schema_version=int(body.schema_version),
                extra=body.extra,
            )
        except ValueError as e:
            raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e
        item = store.get_product_preset_item(preset_id=rec.preset_id)
        assert item is not None
        return {"preset": item}
    finally:
        store.close()


@router.put("/product_presets/{preset_id}")
def update_product_preset(preset_id: str, body: UpdatePresetRequest) -> dict[str, Any]:
    store = SQLiteStore()
    try:
        if store.get_product_preset(preset_id=preset_id) is None:
            raise APIError(status_code=404, code="not_found", message="Preset not found.")
        try:
            store.update_product_preset(
                preset_id=preset_id,
                name=body.name,
                product_ids=body.product_ids,
                status=body.status,
                schema_version=body.schema_version,
                extra=body.extra,
            )
        except ValueError as e:
            raise APIError(status_code=400, code="invalid_argument", message=str(e)) from e

        item = store.get_product_preset_item(preset_id=preset_id)
        assert item is not None
        return {"preset": item}
    finally:
        store.close()
