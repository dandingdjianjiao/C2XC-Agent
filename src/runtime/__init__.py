"""Runtime orchestration (workers, background jobs).

This layer is responsible for:
- claiming queued runs from SQLite
- executing runs using the agent engine
- updating batch/run statuses

It should remain independent from the HTTP layer (`src/api`), so both CLI and API
can reuse the same execution logic.
"""

