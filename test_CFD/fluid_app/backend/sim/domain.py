from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvista as pv


@dataclass(frozen=True)
class Domain:
    nx: int
    ny: int
    nz: int
    x_coords: np.ndarray
    y_coords: np.ndarray
    z_coords: np.ndarray
    solid: np.ndarray  # bool (nx,ny,nz)
    inlet: np.ndarray  # bool
    outlet: np.ndarray  # bool
    gravity_dir: np.ndarray  # float32 (3,)
    dx_m: float

    def inlet_speed_lbm(self, *, flow_gph: float, nu_lbm: float) -> float:
        # Very simple physical-to-lattice scaling using viscosity match (same approach as notebook).
        # Converts flow rate -> inlet velocity assuming a nominal source radius.
        q_m3s = float(flow_gph) * 3.785411784e-3 / 3600.0
        r_m = 0.004  # 4mm nominal source radius
        a_m2 = np.pi * (r_m**2)
        inlet_u_phys = q_m3s / max(a_m2, 1e-12)

        nu_phys = 1.004e-6  # m^2/s (water @ ~20C)
        dt_s = float(nu_lbm) * (self.dx_m**2) / nu_phys
        inlet_u_lbm = inlet_u_phys * dt_s / self.dx_m

        return float(np.clip(inlet_u_lbm, 0.0, 0.08))


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return np.array([0.0, 0.0, -1.0], dtype=np.float32)
    return (v / n).astype(np.float32)


def _dims_from_bounds(bounds, base_resolution: int):
    x_range = float(bounds[1] - bounds[0])
    y_range = float(bounds[3] - bounds[2])
    z_range = float(bounds[5] - bounds[4])
    max_range = max(x_range, y_range, z_range, 1e-6)

    nx = max(int(base_resolution * x_range / max_range), 24)
    ny = max(int(base_resolution * y_range / max_range), 24)
    nz = max(int(base_resolution * z_range / max_range), 24)

    # Keep memory reasonable.
    nx = min(nx, 160)
    ny = min(ny, 160)
    nz = min(nz, 160)

    return nx, ny, nz


def build_domain_from_stl(*, stl_path: str, base_resolution: int, gravity: np.ndarray, source_point_mm: np.ndarray) -> Domain:
    mesh = pv.read(stl_path).clean().triangulate()
    b = mesh.bounds

    nx, ny, nz = _dims_from_bounds(b, base_resolution)

    padding_mm = 3.0
    x_coords = np.linspace(b[0] - padding_mm, b[1] + padding_mm, nx).astype(np.float32)
    y_coords = np.linspace(b[2] - padding_mm, b[3] + padding_mm, ny).astype(np.float32)
    z_coords = np.linspace(b[4] - padding_mm, b[5] + padding_mm, nz).astype(np.float32)

    # Lattice points in mm
    X, Y, Z = np.meshgrid(x_coords, y_coords, z_coords, indexing="ij")
    lattice_pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    lattice_cloud = pv.PolyData(lattice_pts)

    # Treat STL as solid material; fluid is outside solid within box (matches notebook behavior).
    solid_sel = lattice_cloud.select_enclosed_points(mesh, tolerance=0.0, check_surface=False)
    inside = np.asarray(solid_sel.point_data["SelectedPoints"]).astype(bool)
    solid = inside.reshape((nx, ny, nz), order="C")

    gravity_dir = _normalize(gravity)

    dx_mm = float(min(np.diff(x_coords).mean(), np.diff(y_coords).mean(), np.diff(z_coords).mean()))
    dx_m = dx_mm / 1000.0

    # Inlet: a thin disk (in the plane orthogonal to gravity) centered at the user source point.
    # Outlet: disk near the lowest point of the mesh along gravity.
    thickness_mm = max(2.0 * dx_mm, 1.0)
    radius_mm = 0.9 * max(3.0, 3.0 * dx_mm)

    def select_disk(center_mm: np.ndarray, axis_dir: np.ndarray, radius_mm: float, thickness_mm: float):
        c0 = np.asarray(center_mm, dtype=np.float32)
        d0 = _normalize(axis_dir)
        dp = lattice_pts.astype(np.float32) - c0[None, :]
        axial = dp @ d0
        radial = np.linalg.norm(dp - np.outer(axial, d0), axis=1)
        sel = (np.abs(axial) <= thickness_mm) & (radial <= radius_mm)
        return sel.reshape((nx, ny, nz), order="C")

    inlet = select_disk(source_point_mm, gravity_dir, radius_mm=radius_mm, thickness_mm=thickness_mm) & (~solid)

    mesh_pts = np.asarray(mesh.points, dtype=np.float32)
    proj = mesh_pts @ gravity_dir
    low_pt = mesh_pts[int(np.argmin(proj))]

    outlet = select_disk(low_pt, gravity_dir, radius_mm=radius_mm * 1.2, thickness_mm=thickness_mm) & (~solid)

    # Ensure inlet/outlet are fluid
    solid[inlet] = False
    solid[outlet] = False

    return Domain(
        nx=nx,
        ny=ny,
        nz=nz,
        x_coords=x_coords,
        y_coords=y_coords,
        z_coords=z_coords,
        solid=solid,
        inlet=inlet,
        outlet=outlet,
        gravity_dir=gravity_dir,
        dx_m=dx_m,
    )
