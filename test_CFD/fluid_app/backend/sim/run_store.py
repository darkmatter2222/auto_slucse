from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class RunStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def create_run(self, meta: dict[str, Any]) -> str:
        run_id = f"run_{int(time.time() * 1000)}"
        d = self._run_dir(run_id)
        d.mkdir(parents=True, exist_ok=False)
        (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (d / "status.json").write_text(
            json.dumps({"state": "queued", "progress": 0.0, "message": "queued"}, indent=2),
            encoding="utf-8",
        )
        return run_id

    def write_status(self, run_id: str, state: str, progress: float, message: str, extra: dict[str, Any] | None = None):
        d = self._run_dir(run_id)
        status = {
            "state": state,
            "progress": float(max(0.0, min(1.0, progress))),
            "message": message,
        }
        if extra:
            status.update(extra)
        (d / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    def read_status(self, run_id: str) -> dict[str, Any] | None:
        d = self._run_dir(run_id)
        p = d / "status.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def result_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "result.npz"
