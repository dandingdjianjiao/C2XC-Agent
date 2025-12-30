from __future__ import annotations


class CancelledError(RuntimeError):
    """Raised when a cancellation request should abort the current run."""


class CancellationToken:
    def __init__(self) -> None:
        self._cancel_requested = False

    @property
    def cancelled(self) -> bool:
        return self._cancel_requested

    def request_cancel(self) -> None:
        self._cancel_requested = True
