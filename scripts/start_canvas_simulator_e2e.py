from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import engine  # noqa: E402
from backend.app.models import models as _models  # noqa: E402,F401
from backend.app.models.base import Base  # noqa: E402


def main() -> None:
    """Start an isolated, schema-ready API for the synthetic browser matrix."""

    Base.metadata.create_all(bind=engine)
    port = int(os.getenv("CANVAS_SIMULATOR_E2E_BACKEND_PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
