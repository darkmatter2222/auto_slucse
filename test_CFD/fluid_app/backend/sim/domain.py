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
    gravity_dir: np.ndarray  # float32 (3,) - normalized
    gravity_lbm: np.ndarray  # float32 (3,) - gravity in lattice units!
    dx_m: float
    source_point_mm: np.ndarray  # float32 (3,) - CLAMPED source point for advection!

    def inlet_speed_lbm(self, *, flow_gph: float, nu_lbm: float) -> float:
        """
        Convert physical flow rate (GPH) to inlet velocity in lattice units.
        """
        # Convert flow rate to m³/s
        q_m3s = float(flow_gph) * 3.785411784e-3 / 3600.0
        
        # Inlet area: use larger source for better results
        r_m = 0.010  # 10mm nominal source radius (was 4mm - too small!)
        a_m2 = np.pi * (r_m**2)
        
        # Physical inlet velocity
        inlet_u_phys = q_m3s / max(a_m2, 1e-12)

        # Convert to lattice units using diffusive scaling
        nu_phys = 1.004e-6  # m²/s (water @ ~20°C)
        dt_s = float(nu_lbm) * (self.dx_m**2) / nu_phys
        inlet_u_lbm = inlet_u_phys * dt_s / self.dx_m

        # Clamp to stable range (Ma < 0.1 for LBM)
        return float(np.clip(inlet_u_lbm, 0.001, 0.08))


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return np.array([0.0, 0.0, -1.0], dtype=np.float32)
    return (v / n).astype(np.float32)


def _dims_from_bounds(bounds, base_resolution: int, max_cells: int = 320):
    """
    Calculate grid dimensions from mesh bounds.
    RTX 5090 can handle much larger grids - up to 320³ = 32M cells easily!
    """
    x_range = float(bounds[1] - bounds[0])
    y_range = float(bounds[3] - bounds[2])
    z_range = float(bounds[5] - bounds[4])
    max_range = max(x_range, y_range, z_range, 1e-6)

    nx = max(int(base_resolution * x_range / max_range), 32)
    ny = max(int(base_resolution * y_range / max_range), 32)
    nz = max(int(base_resolution * z_range / max_range), 32)

    # RTX 5090 has 32GB VRAM - we can do much larger grids!
    # 320³ × 19 × 4 bytes = ~2.5GB for distributions alone - very manageable
    nx = min(nx, max_cells)
    ny = min(ny, max_cells)
    nz = min(nz, max_cells)

    return nx, ny, nz


def _compute_gravity_lbm(gravity_dir: np.ndarray, dx_m: float, nu_lbm: float) -> np.ndarray:
    """
    Convert physical gravity (9.81 m/s²) to lattice units.
    
    In LBM with diffusive scaling:
    - dx_phys = dx_m
    - dt = nu_lbm * dx² / nu_phys
    - g_lbm = g_phys * dt² / dx
    
    This is CRITICAL for realistic gravity-driven flow!
    """
    g_phys = 9.81  # m/s²
    nu_phys = 1.004e-6  # m²/s (water)
    
    # Time step from viscosity matching
    dt_s = float(nu_lbm) * (dx_m ** 2) / nu_phys
    
    # Gravity in lattice units
    g_lbm_scalar = g_phys * (dt_s ** 2) / dx_m
    
    # Scale to be effective but stable (LBM gravity typically 1e-5 to 1e-3)
    # The diffusive scaling gives very small values, so we boost it for visual effect
    # while keeping it physically reasonable
    g_lbm_scalar = float(np.clip(g_lbm_scalar, 1e-6, 5e-4))
    
    # Apply to direction
    gravity_lbm = _normalize(gravity_dir) * g_lbm_scalar
    
    print(f"[Domain] Gravity conversion:")
    print(f"  Physical: {g_phys} m/s², dx={dx_m*1000:.3f}mm, dt={dt_s:.2e}s")
    print(f"  Lattice: {g_lbm_scalar:.6f} (direction: {gravity_dir})")
    
    return gravity_lbm.astype(np.float32)


def build_domain_from_stl(
    *, 
    stl_path: str, 
    base_resolution: int, 
    gravity: np.ndarray, 
    source_point_mm: np.ndarray,
    nu_lbm: float = 0.06,  # Viscosity in lattice units
) -> Domain:
    """
    Build simulation domain from STL mesh.
    
    This creates:
    - Voxelized solid/fluid mask
    - Inlet region (spherical source at user-picked point)
    - Outlet region (at lowest point along gravity)
    - Proper gravity in lattice units for body force
    """
    mesh = pv.read(stl_path).clean().triangulate()
    b = mesh.bounds

    print(f"[Domain] === Building domain from STL ===")
    print(f"[Domain] STL bounds: X=[{b[0]:.1f}, {b[1]:.1f}], Y=[{b[2]:.1f}, {b[3]:.1f}], Z=[{b[4]:.1f}, {b[5]:.1f}]")
    print(f"[Domain] User source point (raw): {source_point_mm}")

    # Get mesh info
    mesh_center = np.array([(b[0]+b[1])/2, (b[2]+b[3])/2, (b[4]+b[5])/2], dtype=np.float32)
    mesh_size = np.array([b[1]-b[0], b[3]-b[2], b[5]-b[4]], dtype=np.float32)
    max_dim = float(max(mesh_size))
    
    print(f"[Domain] Mesh center: {mesh_center}")
    print(f"[Domain] Mesh size: {mesh_size}")

    # Validate source point - ALWAYS clamp to mesh bounds
    src = np.asarray(source_point_mm, dtype=np.float32)
    
    # Check if source is within bounds
    src_in_bounds = (
        b[0] <= src[0] <= b[1] and
        b[2] <= src[1] <= b[3] and
        b[4] <= src[2] <= b[5]
    )

    if not src_in_bounds:
        print(f"[Domain] WARNING: Source point outside mesh bounds!")
        
        # Check if it's a simple offset issue (Three.js centering)
        # If source is near (0,0,0) but mesh is far away, add mesh center
        src_dist_from_origin = np.linalg.norm(src)
        mesh_dist_from_origin = np.linalg.norm(mesh_center)
        
        # Check if source could be in mesh-centered coordinates
        src_centered = src + mesh_center
        src_centered_in_bounds = (
            b[0] - max_dim*0.1 <= src_centered[0] <= b[1] + max_dim*0.1 and
            b[2] - max_dim*0.1 <= src_centered[1] <= b[3] + max_dim*0.1 and
            b[4] - max_dim*0.1 <= src_centered[2] <= b[5] + max_dim*0.1
        )
        
        if src_centered_in_bounds and mesh_dist_from_origin > max_dim * 0.5:
            print(f"[Domain] Applying center offset: {mesh_center}")
            source_point_mm = np.clip(
                src_centered,
                [b[0] + 1, b[2] + 1, b[4] + 1],
                [b[1] - 1, b[3] - 1, b[5] - 1]
            )
            print(f"[Domain] Offset + clamped source: {source_point_mm}")
        else:
            # Just clamp to bounds with margin
            margin = max_dim * 0.05
            source_point_mm = np.clip(
                src,
                [b[0] + margin, b[2] + margin, b[4] + margin],
                [b[1] - margin, b[3] - margin, b[5] - margin]
            )
            print(f"[Domain] Clamped source: {source_point_mm}")
    else:
        source_point_mm = src
        print(f"[Domain] Source point OK (within bounds)")

    # Calculate grid dimensions - allow much larger for RTX 5090
    nx, ny, nz = _dims_from_bounds(b, base_resolution, max_cells=320)

    # Add padding around mesh
    padding_mm = 5.0
    x_coords = np.linspace(b[0] - padding_mm, b[1] + padding_mm, nx).astype(np.float32)
    y_coords = np.linspace(b[2] - padding_mm, b[3] + padding_mm, ny).astype(np.float32)
    z_coords = np.linspace(b[4] - padding_mm, b[5] + padding_mm, nz).astype(np.float32)

    # Create lattice points
    X, Y, Z = np.meshgrid(x_coords, y_coords, z_coords, indexing="ij")
    lattice_pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    lattice_cloud = pv.PolyData(lattice_pts)

    # Find points inside the STL mesh
    solid_sel = lattice_cloud.select_enclosed_points(mesh, tolerance=0.0, check_surface=False)
    inside = np.asarray(solid_sel.point_data["SelectedPoints"]).astype(bool)
    inside_3d = inside.reshape((nx, ny, nz), order="C")

    # Fluid flows INSIDE the mesh (flume/channel)
    solid = ~inside_3d

    print(f"[Domain] Grid: {nx}x{ny}x{nz} = {nx*ny*nz:,} cells")
    print(f"[Domain] Fluid cells (inside mesh): {np.sum(~solid):,}")
    print(f"[Domain] Solid cells (outside mesh): {np.sum(solid):,}")

    gravity_dir = _normalize(gravity)

    dx_mm = float(min(np.diff(x_coords).mean(), np.diff(y_coords).mean(), np.diff(z_coords).mean()))
    dx_m = dx_mm / 1000.0

    # Compute gravity in lattice units - THIS IS KEY FOR REALISTIC FLOW
    gravity_lbm = _compute_gravity_lbm(gravity_dir, dx_m, nu_lbm)

    # === INLET SETUP ===
    # Create a LARGE spherical source region for reliable water emission
    source_radius_mm = max(20.0, 10.0 * dx_mm)  # Large source
    
    def select_sphere(center_mm: np.ndarray, radius_mm: float):
        """Select cells within a sphere."""
        c0 = np.asarray(center_mm, dtype=np.float32)
        dp = lattice_pts.astype(np.float32) - c0[None, :]
        dist = np.linalg.norm(dp, axis=1)
        sel = dist <= radius_mm
        return sel.reshape((nx, ny, nz), order="C")

    # Try to find inlet cells - if none at exact point, search nearby
    inlet_sphere = select_sphere(source_point_mm, source_radius_mm)
    inlet = inlet_sphere & (~solid)
    
    # If no inlet cells found, try larger radius or find nearest fluid
    if np.sum(inlet) == 0:
        print(f"[Domain] WARNING: No inlet cells at source point, searching for fluid...")
        
        # Find all fluid cells and pick ones closest to source
        fluid_indices = np.argwhere(~solid)
        if len(fluid_indices) > 0:
            fluid_pts = np.column_stack([
                x_coords[fluid_indices[:, 0]],
                y_coords[fluid_indices[:, 1]],
                z_coords[fluid_indices[:, 2]]
            ])
            
            # Distance to source
            dists = np.linalg.norm(fluid_pts - source_point_mm, axis=1)
            
            # Take closest fluid cells as inlet
            n_inlet_target = max(100, int(np.sum(~solid) * 0.01))  # ~1% of fluid or at least 100
            closest_idx = np.argsort(dists)[:n_inlet_target]
            
            inlet = np.zeros_like(solid)
            for idx in closest_idx:
                fi = fluid_indices[idx]
                inlet[fi[0], fi[1], fi[2]] = True
            
            # Update source point to center of inlet
            inlet_pts = fluid_pts[closest_idx]
            source_point_mm = inlet_pts.mean(axis=0).astype(np.float32)
            print(f"[Domain] Found {np.sum(inlet)} inlet cells near fluid")
            print(f"[Domain] Adjusted source to: {source_point_mm}")

    print(f"[Domain] Source radius: {source_radius_mm:.1f}mm")
    print(f"[Domain] Inlet cells: {np.sum(inlet)}")

    # === OUTLET SETUP ===
    # Find the lowest region of the mesh along gravity direction
    mesh_pts = np.asarray(mesh.points, dtype=np.float32)
    proj = mesh_pts @ gravity_dir
    
    # Get the lowest 10% of points as outlet region
    low_threshold = np.percentile(proj, 10)
    low_pts_mask = proj <= low_threshold
    low_pts = mesh_pts[low_pts_mask]
    
    if len(low_pts) > 0:
        low_center = low_pts.mean(axis=0)
    else:
        low_center = mesh_pts[int(np.argmin(proj))]

    outlet_radius_mm = source_radius_mm * 1.5
    outlet_sphere = select_sphere(low_center, outlet_radius_mm)
    outlet = outlet_sphere & (~solid)

    print(f"[Domain] Outlet center: {low_center}")
    print(f"[Domain] Outlet cells: {np.sum(outlet)}")
    print(f"[Domain] Source point (final): {source_point_mm}")
    print(f"[Domain] Gravity direction: {gravity_dir}")
    print(f"[Domain] dx = {dx_mm:.3f} mm")

    # Ensure inlet/outlet are fluid cells
    solid[inlet] = False
    solid[outlet] = False

    # Ensure source_point_mm is a proper float32 array
    final_source = np.asarray(source_point_mm, dtype=np.float32)

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
        gravity_lbm=gravity_lbm,  # Gravity in lattice units for body force
        dx_m=dx_m,
        source_point_mm=final_source,  # CLAMPED source point for advection
    )
