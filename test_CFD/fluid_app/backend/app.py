from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from sim.run_store import RunStore
from sim.simulate import simulate_run

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
TEST_CFD = REPO_ROOT / "test_CFD"
DEFAULT_STL = TEST_CFD / "SmallRiffleLotsFlume.stl"

app = FastAPI(title="Fluid App Backend", version="0.1.0")
store = RunStore(ROOT / "runs")


class SimRequest(BaseModel):
    stlPath: str | None = Field(default=None, description="Optional path override")
    gravity: list[float] = Field(default_factory=lambda: [0.0, 0.0, -1.0])
    sourcePointMm: list[float] = Field(..., min_length=3, max_length=3)
    flowGph: float = Field(default=200.0, ge=0.0)
    quality: Literal["low", "medium", "high"] = "medium"


@app.get("/api/stl")
def get_stl():
    stl_path = DEFAULT_STL
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"STL not found at {stl_path}")
    return FileResponse(str(stl_path), media_type="model/stl")


@app.post("/api/simulate")
def start_simulation(req: SimRequest, bg: BackgroundTasks):
    stl_path = Path(req.stlPath) if req.stlPath else DEFAULT_STL
    if not stl_path.is_absolute():
        stl_path = (TEST_CFD / stl_path).resolve()
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"STL not found: {stl_path}")

    run_id = store.create_run(
        meta={
            "stl": str(stl_path),
            "gravity": req.gravity,
            "sourcePointMm": req.sourcePointMm,
            "flowGph": req.flowGph,
            "quality": req.quality,
        }
    )

    bg.add_task(
        simulate_run,
        store=store,
        run_id=run_id,
        stl_path=str(stl_path),
        gravity=np.array(req.gravity, dtype=np.float32),
        source_point_mm=np.array(req.sourcePointMm, dtype=np.float32),
        flow_gph=float(req.flowGph),
        quality=req.quality,
    )

    return {"runId": run_id}


@app.get("/api/run/{run_id}/status")
def run_status(run_id: str):
    status = store.read_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown runId")
    return status


@app.get("/api/run/{run_id}/result")
def run_result(run_id: str):
    path = store.result_path(run_id)
    if not path.exists():
        status = store.read_status(run_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Unknown runId")
        raise HTTPException(status_code=409, detail=f"No result yet (state={status.get('state')})")
    return FileResponse(str(path), media_type="application/octet-stream", filename=f"{run_id}.npz")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "stlExists": DEFAULT_STL.exists(),
        "cudaVisible": os.environ.get("CUDA_VISIBLE_DEVICES", None),
    }
