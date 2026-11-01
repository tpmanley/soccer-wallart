from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class JsonCache:
    """Tiny on-disk cache for API responses so device polls don't hammer ESPN."""

    def __init__(self, directory: str | Path, ttl_seconds: float):
        self.dir = Path(directory)
        self.ttl = ttl_seconds
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def get(self, key: str, allow_stale: bool = False) -> Any | None:
        p = self._path(key)
        if not p.exists():
            return None
        if not allow_stale and time.time() - p.stat().st_mtime > self.ttl:
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value))
        tmp.replace(p)
