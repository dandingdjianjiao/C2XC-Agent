from __future__ import annotations

import threading

from fastapi import Request

from src.api.errors import APIError
from src.config.load_config import load_app_config
from src.storage.reasoningbank_store import (
    ReasoningBankConfigError,
    ReasoningBankDependencyError,
    ReasoningBankError,
    ReasoningBankStore,
)


_RB_INIT_LOCK = threading.Lock()


def get_reasoningbank_store(request: Request) -> ReasoningBankStore:
    """FastAPI dependency: returns a cached ReasoningBankStore (lazy init).

    Motivation:
    - Creating a Chroma PersistentClient and opening a collection has non-trivial overhead.
    - Recreating it per request increases lock contention risk and latency.

    We cache the instance in `app.state` for the lifetime of the FastAPI process.
    """
    cached = getattr(request.app.state, "reasoningbank_store", None)
    if isinstance(cached, ReasoningBankStore):
        return cached

    with _RB_INIT_LOCK:
        cached2 = getattr(request.app.state, "reasoningbank_store", None)
        if isinstance(cached2, ReasoningBankStore):
            return cached2

        try:
            cfg = load_app_config()
            rb = ReasoningBankStore.from_config(cfg)
        except ReasoningBankDependencyError as e:
            raise APIError(
                status_code=503,
                code="dependency_unavailable",
                message=str(e),
                details={"missing": e.missing},
            ) from e
        except ReasoningBankConfigError as e:
            raise APIError(
                status_code=409,
                code="conflict",
                message=str(e),
                details=e.details,
            ) from e
        except ReasoningBankError as e:
            raise APIError(status_code=500, code="internal", message=str(e)) from e

        request.app.state.reasoningbank_store = rb
        return rb
