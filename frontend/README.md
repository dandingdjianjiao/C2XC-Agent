# C2XC-Agent WebUI (Milestone 1)

This folder contains the Web UI for C2XC-Agent.

## Prerequisites

- Node.js 18+
- Backend API running (FastAPI) on `http://127.0.0.1:8000`

## Run (dev)

1) Start the backend (from repo root):

```bash
python scripts/serve.py
```

2) Start the frontend (from repo root):

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://127.0.0.1:5173` by default and proxies `/api/*` to the backend.

## Configuration

- `VITE_API_BASE_URL` (optional)
  - Default: `/api/v1` (works in dev via Vite proxy)
  - If you deploy frontend and backend on different origins, set it to a full URL, e.g.:
    - `http://127.0.0.1:8000/api/v1`

## Notes

- Theme + language are pre-wired (persisted in `localStorage`):
  - theme key: `c2xc_theme` (`light|dark`)
  - language key: `c2xc_lang` (`en|zh`)
