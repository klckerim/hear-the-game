"""Minimal `.env` loader (KEY=VALUE lines, existing environment wins). Avoids a dependency for four settings."""
from __future__ import annotations

import os
from pathlib import Path


def load_env(path: Path | None = None) -> None:
    path = path or Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip())
