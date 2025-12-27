from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator


def advect_particles(
    *,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    z_coords: np.ndarray,
    ux: np.ndarray,
    uy: np.ndarray,
    uz: np.ndarray,
    solid: np.ndarray,
    source_point_mm: np.ndarray,
    gravity_dir: np.ndarray,
    n_particles: int,
    n_frames: int,
):
    # Interpolators expect axes increasing.
    interp_ux = RegularGridInterpolator((x_coords, y_coords, z_coords), ux, bounds_error=False, fill_value=0.0)
    interp_uy = RegularGridInterpolator((x_coords, y_coords, z_coords), uy, bounds_error=False, fill_value=0.0)
    interp_uz = RegularGridInterpolator((x_coords, y_coords, z_coords), uz, bounds_error=False, fill_value=0.0)

    rng = np.random.default_rng(0)

    # Seed particles in a small sphere around the source.
    r0 = 3.5  # mm
    dirs = rng.normal(size=(n_particles, 3)).astype(np.float32)
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-9
    rad = (rng.random((n_particles, 1)).astype(np.float32) ** (1.0 / 3.0)) * r0
    pos = source_point_mm.astype(np.float32)[None, :] + dirs * rad

    # Use a small dt in mm-space; clamp step length.
    dt = 0.6
    frames = np.empty((n_frames, n_particles, 3), dtype=np.float32)

    for t in range(n_frames):
        frames[t] = pos
        v = np.stack([interp_ux(pos), interp_uy(pos), interp_uz(pos)], axis=1).astype(np.float32)

        # If velocity is near-zero, apply a gentle gravity drift so the animation still progresses.
        v_mag = np.linalg.norm(v, axis=1, keepdims=True)
        drift = gravity_dir.astype(np.float32)[None, :] * 0.02
        v = np.where(v_mag < 1e-5, drift, v)

        step = v * dt
        step_len = np.linalg.norm(step, axis=1, keepdims=True)
        step = step * np.clip(2.0 / (step_len + 1e-9), 0.0, 1.0)

        pos = pos + step

    return frames
