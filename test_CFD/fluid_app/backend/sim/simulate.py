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
    """
    Quality parameters DRAMATICALLY INCREASED for RTX 5090!
    
    RTX 5090 has 32GB VRAM and massive compute - let's use it!
    - Low: Still fast (~10-15 sec) but much better than before
    - Medium: Good balance (~20-30 sec)  
    - High: Maximum detail - UNLEASH THE GPU (~45-60 sec)
    """
    if quality == "low":
        return {
            "base_res": 128,      # Was 64 - doubled!
            "iterations": 800,    # Was 220 - 4x more!
            "frames": 300,        # Was 140 - more animation
            "particles": 15000,   # Was 2500 - 6x more particles!
            "nu_lbm": 0.08,       # Viscosity
        }
    if quality == "high":
        return {
            "base_res": 256,      # Was 128 - doubled for serious detail!
            "iterations": 3000,   # Was 750 - 4x more for proper flow development
            "frames": 600,        # Was 360 - longer animation
            "particles": 80000,   # Was 12000 - massive particle count!
            "nu_lbm": 0.05,       # Lower viscosity = more turbulent
        }
    # Medium
    return {
        "base_res": 192,          # Was 96 - doubled!
        "iterations": 1500,       # Was 420 - 3.5x more!
        "frames": 450,            # Was 240 - more animation
        "particles": 40000,       # Was 6000 - 6x more!
        "nu_lbm": 0.06,           # Balanced viscosity
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
    """
    Run a complete CFD simulation:
    1. Build domain from STL (voxelize, setup inlet/outlet)
    2. Run LBM solver with gravity body force
    3. Advect particles through velocity field
    4. Save results
    """
    try:
        store.write_status(run_id, state="running", progress=0.01, message="Loading STL mesh...")

        params = _quality_params(quality)
        nu_lbm = params.get("nu_lbm", 0.06)
        
        domain = build_domain_from_stl(
            stl_path=stl_path,
            base_resolution=int(params["base_res"]),
            gravity=gravity,
            source_point_mm=source_point_mm,
            nu_lbm=nu_lbm,  # Pass viscosity for gravity scaling
        )

        store.write_status(run_id, state="running", progress=0.10, message="Initializing GPU LBM solver...")

        # Create LBM solver WITH GRAVITY BODY FORCE
        lbm = LbmD3Q19Torch(
            nx=domain.nx,
            ny=domain.ny,
            nz=domain.nz,
            nu_lbm=nu_lbm,
            solid=domain.solid,
            inlet=domain.inlet,
            outlet=domain.outlet,
            gravity_lbm=domain.gravity_lbm,  # NEW: Pass gravity for body force!
        )

        inlet_speed_lbm = domain.inlet_speed_lbm(flow_gph=flow_gph, nu_lbm=lbm.nu)
        lbm.set_inlet_direction(domain.gravity_dir)
        
        print(f"[Simulate] Inlet speed (LBM): {inlet_speed_lbm:.6f}")
        print(f"[Simulate] Running {params['iterations']} LBM iterations...")

        n_iter = int(params["iterations"])
        for i in range(n_iter):
            lbm.step(inlet_speed=float(inlet_speed_lbm))
            if (i + 1) % max(1, n_iter // 20) == 0:
                pct = 0.10 + 0.55 * (i + 1) / n_iter
                store.write_status(
                    run_id,
                    state="running",
                    progress=pct,
                    message=f"LBM solver: {i+1}/{n_iter} iterations",
                )

        store.write_status(run_id, state="running", progress=0.68, message="Extracting velocity field...")
        ux, uy, uz = lbm.velocity_cpu()
        fill_level = lbm.fill_level_cpu()

        store.write_status(run_id, state="running", progress=0.72, message="Advecting particles...")
        
        # Use the CLAMPED source point from domain, not the original user click!
        # This ensures particles spawn inside the fluid region
        clamped_source = domain.source_point_mm
        print(f"[Simulate] Using clamped source for advection: {clamped_source}")
        
        frames = advect_particles(
            x_coords=domain.x_coords,
            y_coords=domain.y_coords,
            z_coords=domain.z_coords,
            ux=ux,
            uy=uy,
            uz=uz,
            solid=domain.solid,
            source_point_mm=clamped_source,  # Use clamped source!
            gravity_dir=domain.gravity_dir,
            n_particles=int(params["particles"]),
            n_frames=int(params["frames"]),
            fill_level=fill_level,
        )

        store.write_status(run_id, state="running", progress=0.92, message="Saving results...")

        out_path = store.result_path(run_id)
        np.savez_compressed(
            out_path,
            x_coords=domain.x_coords.astype(np.float32),
            y_coords=domain.y_coords.astype(np.float32),
            z_coords=domain.z_coords.astype(np.float32),
            frames=frames.astype(np.float32),
            solid=domain.solid.astype(np.uint8),
            fill_level=fill_level.astype(np.float32),
        )

        store.write_status(run_id, state="done", progress=1.0, message="Simulation complete!")

    except Exception as ex:
        error_msg = f"{type(ex).__name__}: {ex}"
        tb = traceback.format_exc()
        
        # VERBOSE ERROR LOGGING - print to console so we can see it!
        print(f"\n{'='*60}")
        print(f"[SIMULATION ERROR] {error_msg}")
        print(f"{'='*60}")
        print(tb)
        print(f"{'='*60}\n")
        
        store.write_status(
            run_id,
            state="error",
            progress=1.0,
            message=error_msg,
            extra={"traceback": tb},
        )
