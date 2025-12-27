from __future__ import annotations

import traceback
from pathlib import Path
from typing import Literal

import numpy as np

from .advect import advect_particles
from .domain import build_domain_from_stl
from .lbm_torch import LbmD3Q19Torch
from .run_store import RunStore


Quality = Literal["low", "medium", "high"]


def _quality_params(quality: Quality):
    if quality == "low":
        return {
            "base_res": 64,
            "iterations": 220,
            "frames": 140,
            "particles": 2500,
        }
    if quality == "high":
        return {
            "base_res": 128,
            "iterations": 750,
            "frames": 360,
            "particles": 12000,
        }
    return {
        "base_res": 96,
        "iterations": 420,
        "frames": 240,
        "particles": 6000,
    }


def simulate_run(
    *,
    store: RunStore,
    run_id: str,
    stl_path: str,
    gravity: np.ndarray,
    source_point_mm: np.ndarray,
    flow_gph: float,
    quality: Quality,
):
    try:
        store.write_status(run_id, state="running", progress=0.01, message="loading STL")

        params = _quality_params(quality)
        domain = build_domain_from_stl(
            stl_path=stl_path,
            base_resolution=int(params["base_res"]),
            gravity=gravity,
            source_point_mm=source_point_mm,
        )

        store.write_status(run_id, state="running", progress=0.12, message="initializing GPU LBM")

        lbm = LbmD3Q19Torch(
            nx=domain.nx,
            ny=domain.ny,
            nz=domain.nz,
            nu_lbm=0.10,
            solid=domain.solid,
            inlet=domain.inlet,
            outlet=domain.outlet,
        )

        inlet_speed_lbm = domain.inlet_speed_lbm(flow_gph=flow_gph, nu_lbm=lbm.nu)
        lbm.set_inlet_direction(domain.gravity_dir)

        n_iter = int(params["iterations"])
        for i in range(n_iter):
            lbm.step(inlet_speed=float(inlet_speed_lbm))
            if (i + 1) % max(1, n_iter // 20) == 0:
                store.write_status(
                    run_id,
                    state="running",
                    progress=0.12 + 0.58 * (i + 1) / n_iter,
                    message=f"LBM iterations {i+1}/{n_iter}",
                )

        store.write_status(run_id, state="running", progress=0.72, message="extracting velocity field")
        ux, uy, uz = lbm.velocity_cpu()

        store.write_status(run_id, state="running", progress=0.78, message="advecting particles")
        frames = advect_particles(
            x_coords=domain.x_coords,
            y_coords=domain.y_coords,
            z_coords=domain.z_coords,
            ux=ux,
            uy=uy,
            uz=uz,
            solid=domain.solid,
            source_point_mm=source_point_mm,
            gravity_dir=domain.gravity_dir,
            n_particles=int(params["particles"]),
            n_frames=int(params["frames"]),
        )

        store.write_status(run_id, state="running", progress=0.95, message="saving result")

        out_path = store.result_path(run_id)
        np.savez_compressed(
            out_path,
            x_coords=domain.x_coords.astype(np.float32),
            y_coords=domain.y_coords.astype(np.float32),
            z_coords=domain.z_coords.astype(np.float32),
            frames=frames.astype(np.float32),
            solid=domain.solid.astype(np.uint8),
        )

        store.write_status(run_id, state="done", progress=1.0, message="done")

    except Exception as ex:
        store.write_status(
            run_id,
            state="error",
            progress=1.0,
            message=f"{type(ex).__name__}: {ex}",
            extra={"traceback": traceback.format_exc()},
        )
