"""HTTP API layer (FastAPI).

This module exposes a small, versioned `/api/v1` surface that the WebUI can use to:
- create/list batches and runs
- fetch run outputs and trace events
- request cancellation

The API is intentionally thin: core behavior lives in `src/runtime` and `src/storage`.
"""

