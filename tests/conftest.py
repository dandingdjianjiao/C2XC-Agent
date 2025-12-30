from __future__ import annotations

import sys
from pathlib import Path


# Ensure `import src...` works when running `pytest` from repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

