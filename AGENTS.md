# Repository Guidelines

## Project Structure

- `src/`: core Python package (agent logic, ReCAP engine, KB wrappers, SQLite trace).
- `config/default.toml`: single source of runtime config (roles, prompts, priors, limits).
- `docs/`: project spec and injected priors (`docs/priors/*.en.md`).
- `scripts/`: developer utilities (run batch, cancel runs, build KBs).
- `original_assets/`: research PDFs/DOCX/XLSX (source material; not runtime code).
- `data/`: local runtime state (`data/app.db`, Marker outputs, LightRAG working dirs).

## Run Locally (Development Commands)

- Dry run (no KB/LLM; writes placeholder output to SQLite):
  - `python scripts/run_batch.py --dry-run --request "test" --n-runs 1 --recipes-per-run 1`
- Real run (requires KB + OpenAI-compatible endpoints):
  - `export OPENAI_API_KEY=...`
  - `export LIGHTRAG_KB_PRINCIPLES_DIR=/abs/path/to/data/lightrag/kb_principles`
  - `export LIGHTRAG_KB_MODULATION_DIR=/abs/path/to/data/lightrag/kb_modulation`
  - `python scripts/run_batch.py --request "..." --n-runs 2 --recipes-per-run 3`
- Cancel:
  - `python scripts/cancel_run.py --run-id run_<uuid>`
  - `python scripts/cancel_batch.py --batch-id batch_<uuid>`

## Knowledge Base (Marker → LightRAG)

- Extract PDFs to markdown via Marker:
  - `python scripts/kb/run_marker_all.py --workers 1 --skip-existing`
- Build LightRAG working dirs from Marker outputs:
  - `python scripts/kb/build_lightrag_all.py --chunk-size 512`

## Coding Style & Conventions

- Python 3.11+ required (`tomllib`); keep code type-hinted and follow existing patterns (`dataclass`, small modules).
- Indentation: 4 spaces; naming: `snake_case` (functions/files), `CamelCase` (classes).
- Keep domain behavior in `config/default.toml` and priors in `docs/priors/` (avoid hard-coding prompts in code).

## Testing Guidelines

- No test suite is wired yet. Prefer adding unit tests under `tests/` with `pytest` if/when introducing non-trivial logic.
- Minimal sanity checks: `python -m compileall src` and `python scripts/run_batch.py --dry-run ...`.

## Commits & Pull Requests

- This workspace does not include a `.git/` directory, so commit conventions cannot be inferred here.
- Suggested convention: imperative subject lines (e.g., “Add KB alias resolution”), one topic per commit, include config/schema changes in the PR description.
- PRs should include: what changed, how to run, and any new env vars or data migrations (`data/app.db` schema changes).
