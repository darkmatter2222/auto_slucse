"""
Particle advection through velocity field with REAL PHYSICS.

Key features:
- Particles spawn at source and flow with velocity field + gravity
- Real STL surface collision using signed distance field
- Particle decay when too far from STL surface  
- Surface tension approximation keeps particles near surfaces
- Proper filling behavior in low regions
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import distance_transform_edt


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
    fill_level: np.ndarray | None = None,
):
    """
    Advect particles through velocity field with realistic physics.
    
    Creates a FLOWING effect where:
    - Particles emit from source point (clamped to fluid region)
    - They flow with the velocity field
    - Gravity pulls them down
    - They slide along STL surfaces
    - They decay when too far from surfaces
    """
    print(f"[Advect] === Starting particle advection ===")
    print(f"[Advect] Particles: {n_particles:,}, Frames: {n_frames}")
    print(f"[Advect] Source (input): {source_point_mm}")
    print(f"[Advect] Gravity: {gravity_dir}")

    # Domain bounds
    x_min, x_max = float(x_coords.min()), float(x_coords.max())
    y_min, y_max = float(y_coords.min()), float(y_coords.max())
    z_min, z_max = float(z_coords.min()), float(z_coords.max())
    domain_size = max(x_max - x_min, y_max - y_min, z_max - z_min)

    print(f"[Advect] Domain: X=[{x_min:.1f}, {x_max:.1f}], Y=[{y_min:.1f}, {y_max:.1f}], Z=[{z_min:.1f}, {z_max:.1f}]")
    print(f"[Advect] Domain size: {domain_size:.1f}mm")

    # Grid spacing
    dx_mm = float(np.mean(np.diff(x_coords)))
    dy_mm = float(np.mean(np.diff(y_coords)))
    dz_mm = float(np.mean(np.diff(z_coords)))
    avg_dx = (dx_mm + dy_mm + dz_mm) / 3.0

    print(f"[Advect] dx = {avg_dx:.3f}mm")

    # ==========================================================================
    # CRITICAL: Clamp source point to be INSIDE the fluid region
    # ==========================================================================
    src_raw = np.asarray(source_point_mm, dtype=np.float32)
    
    # Clamp to grid bounds first
    src_clamped = np.array([
        np.clip(src_raw[0], x_min + avg_dx, x_max - avg_dx),
        np.clip(src_raw[1], y_min + avg_dx, y_max - avg_dx),
        np.clip(src_raw[2], z_min + avg_dx, z_max - avg_dx),
    ], dtype=np.float32)
    
    # Check if clamped source is in fluid (not solid)
    # Convert to grid indices
    src_ix = int(np.clip((src_clamped[0] - x_min) / dx_mm, 0, len(x_coords) - 1))
    src_iy = int(np.clip((src_clamped[1] - y_min) / dy_mm, 0, len(y_coords) - 1))
    src_iz = int(np.clip((src_clamped[2] - z_min) / dz_mm, 0, len(z_coords) - 1))
    
    if solid[src_ix, src_iy, src_iz]:
        print(f"[Advect] WARNING: Source point is in solid! Searching for nearest fluid...")
        
        # Find nearest fluid cell
        fluid_cells = np.argwhere(~solid)
        if len(fluid_cells) > 0:
            fluid_positions = np.column_stack([
                x_coords[fluid_cells[:, 0]],
                y_coords[fluid_cells[:, 1]],
                z_coords[fluid_cells[:, 2]]
            ])
            distances = np.linalg.norm(fluid_positions - src_clamped, axis=1)
            nearest_idx = np.argmin(distances)
            src_clamped = fluid_positions[nearest_idx].astype(np.float32)
            print(f"[Advect] Found nearest fluid cell at: {src_clamped}")
    
    src = src_clamped
    print(f"[Advect] Source (final): {src}")

    # ==========================================================================
    # Build distance field for STL surface collision
    # ==========================================================================
    # Distance from each cell to nearest solid (positive = inside fluid, negative = inside solid)
    fluid_mask = ~solid
    dist_to_solid = distance_transform_edt(fluid_mask).astype(np.float32) * avg_dx  # mm
    dist_from_solid = distance_transform_edt(solid).astype(np.float32) * avg_dx
    
    # Signed distance: positive inside fluid, negative inside solid
    signed_distance = np.where(fluid_mask, dist_to_solid, -dist_from_solid)
    
    print(f"[Advect] SDF range: [{signed_distance.min():.1f}, {signed_distance.max():.1f}] mm")

    # ==========================================================================
    # Build interpolators
    # ==========================================================================
    interp_ux = RegularGridInterpolator(
        (x_coords, y_coords, z_coords), ux, 
        bounds_error=False, fill_value=0.0, method='linear'
    )
    interp_uy = RegularGridInterpolator(
        (x_coords, y_coords, z_coords), uy,
        bounds_error=False, fill_value=0.0, method='linear'
    )
    interp_uz = RegularGridInterpolator(
        (x_coords, y_coords, z_coords), uz,
        bounds_error=False, fill_value=0.0, method='linear'
    )
    
    # Signed distance interpolator - key for surface interaction!
    interp_sdf = RegularGridInterpolator(
        (x_coords, y_coords, z_coords), signed_distance,
        bounds_error=False, fill_value=-100.0, method='linear'  # Outside = "deep in solid"
    )

    # ==========================================================================
    # Physics parameters
    # ==========================================================================
    grav = gravity_dir.astype(np.float32)
    
    # Emission parameters
    emit_radius_mm = max(8.0, 4.0 * avg_dx)  # Tighter emission sphere
    emit_speed_mm = avg_dx * 2.0  # Initial emission speed in gravity direction
    
    # Velocity scaling: LBM velocities need amplification for visible motion
    velocity_scale = avg_dx * 150.0  # Increased significantly
    
    # Gravity: strong enough for visible falling
    gravity_accel_mm = avg_dx * 5.0  # mm/frame²
    max_gravity_speed = avg_dx * 15.0  # Terminal velocity
    
    # Surface interaction
    surface_thickness_mm = 4.0 * avg_dx  # How close to surface before sliding
    surface_attraction_mm = avg_dx * 0.5  # Surface tension
    
    # Particle decay
    max_distance_from_surface = 25.0 * avg_dx  # Decay when this far from any surface
    particle_lifetime_frames = int(n_frames * 1.5)  # Max frames before forced respawn

    print(f"[Advect] Emit radius: {emit_radius_mm:.1f}mm")
    print(f"[Advect] Velocity scale: {velocity_scale:.1f}")
    print(f"[Advect] Gravity accel: {gravity_accel_mm:.3f}mm/frame²")
    print(f"[Advect] Surface thickness: {surface_thickness_mm:.2f}mm")
    print(f"[Advect] Decay distance: {max_distance_from_surface:.1f}mm")

    # ==========================================================================
    # Create emission basis vectors (perpendicular to gravity)
    # ==========================================================================
    perp1 = np.cross(grav, np.array([1, 0, 0], dtype=np.float32))
    if np.linalg.norm(perp1) < 0.1:
        perp1 = np.cross(grav, np.array([0, 1, 0], dtype=np.float32))
    perp1 = perp1 / (np.linalg.norm(perp1) + 1e-9)
    perp2 = np.cross(grav, perp1)
    perp2 = perp2 / (np.linalg.norm(perp2) + 1e-9)

    # ==========================================================================
    # Initialize particles
    # ==========================================================================
    rng = np.random.default_rng(42)

    # Stagger birth times for continuous emission
    emission_duration = max(1, n_frames * 3 // 4)  # Emit for 75% of simulation
    birth_frames = rng.integers(0, emission_duration, size=n_particles)

    # Pre-compute random emission offsets
    def random_sphere_offsets(n, radius):
        """Generate random positions in a sphere."""
        theta = rng.uniform(0, 2 * np.pi, n).astype(np.float32)
        phi = rng.uniform(0, np.pi, n).astype(np.float32)
        r = (rng.uniform(0, 1, n) ** (1/3) * radius).astype(np.float32)
        x = r * np.sin(phi) * np.cos(theta)
        y = r * np.sin(phi) * np.sin(theta)
        z = r * np.cos(phi)
        return (
            x[:, None] * perp1 + 
            y[:, None] * perp2 + 
            z[:, None] * grav
        ).astype(np.float32)

    offsets = random_sphere_offsets(n_particles, emit_radius_mm)

    # Initialize positions and velocities
    pos = np.tile(src, (n_particles, 1)).astype(np.float32)
    vel = np.tile(grav * emit_speed_mm, (n_particles, 1)).astype(np.float32)
    age = np.zeros(n_particles, dtype=np.float32)

    # Output frames
    frames = np.empty((n_frames, n_particles, 3), dtype=np.float32)

    # Statistics tracking
    n_decayed = 0
    n_collisions = 0

    # ==========================================================================
    # Main advection loop
    # ==========================================================================
    for t in range(n_frames):
        # Particles not yet born stay at source
        not_born = birth_frames > t
        pos[not_born] = src + offsets[not_born]
        vel[not_born] = grav * emit_speed_mm
        age[not_born] = 0

        # Store current positions
        frames[t] = pos.copy()

        # Only advect particles that are born
        active = ~not_born
        n_active = np.sum(active)

        if n_active > 0:
            active_idx = np.where(active)[0]
            active_pos = pos[active].copy()
            active_vel = vel[active].copy()
            active_age = age[active].copy()

            # Sample velocity field
            vx = interp_ux(active_pos).astype(np.float32)
            vy = interp_uy(active_pos).astype(np.float32)
            vz = interp_uz(active_pos).astype(np.float32)
            field_vel = np.stack([vx, vy, vz], axis=1) * velocity_scale

            # Sample signed distance field
            sdf = interp_sdf(active_pos)

            # =================================================================
            # Physics update
            # =================================================================
            
            # 1. Apply field velocity with momentum
            active_vel = active_vel * 0.85 + field_vel * 0.15
            
            # 2. Apply gravity acceleration
            active_vel += grav * gravity_accel_mm
            
            # 3. Cap gravity-induced speed (terminal velocity)
            grav_speed = np.sum(active_vel * grav, axis=1, keepdims=True)
            too_fast = grav_speed > max_gravity_speed
            if np.any(too_fast):
                excess = grav_speed - max_gravity_speed
                active_vel -= np.where(too_fast, excess * grav, 0)

            # 4. Surface interaction: if near surface, slide along it
            near_surface = (sdf > 0) & (sdf < surface_thickness_mm)
            if np.any(near_surface):
                surf_idx = np.where(near_surface)[0]
                surf_pos = active_pos[surf_idx]
                
                # Compute surface normal via SDF gradient
                eps = avg_dx * 0.5
                sdf_px = interp_sdf(surf_pos + np.array([eps, 0, 0]))
                sdf_mx = interp_sdf(surf_pos + np.array([-eps, 0, 0]))
                sdf_py = interp_sdf(surf_pos + np.array([0, eps, 0]))
                sdf_my = interp_sdf(surf_pos + np.array([0, -eps, 0]))
                sdf_pz = interp_sdf(surf_pos + np.array([0, 0, eps]))
                sdf_mz = interp_sdf(surf_pos + np.array([0, 0, -eps]))
                
                grad_x = (sdf_px - sdf_mx) / (2 * eps)
                grad_y = (sdf_py - sdf_my) / (2 * eps)
                grad_z = (sdf_pz - sdf_mz) / (2 * eps)
                
                normal = np.stack([grad_x, grad_y, grad_z], axis=1)
                normal_mag = np.linalg.norm(normal, axis=1, keepdims=True)
                # Safe division to avoid RuntimeWarning
                normal = np.divide(normal, normal_mag, out=np.tile(-grav, (len(surf_idx), 1)), where=normal_mag > 1e-6)
                
                # Project velocity onto surface (remove normal component)
                v_normal = np.sum(active_vel[surf_idx] * normal, axis=1, keepdims=True)
                active_vel[surf_idx] -= v_normal * normal * 0.7
                
                # Surface attraction
                sdf_surf = sdf[surf_idx, None]
                active_vel[surf_idx] -= normal * surface_attraction_mm

            # 5. Collision: if inside solid (sdf < 0), push out
            in_solid = sdf < 0
            if np.any(in_solid):
                n_collisions += np.sum(in_solid)
                solid_idx = np.where(in_solid)[0]
                sol_pos = active_pos[solid_idx]
                
                # Compute gradient to find direction to fluid
                eps = avg_dx * 0.5
                sdf_px = interp_sdf(sol_pos + np.array([eps, 0, 0]))
                sdf_mx = interp_sdf(sol_pos + np.array([-eps, 0, 0]))
                sdf_py = interp_sdf(sol_pos + np.array([0, eps, 0]))
                sdf_my = interp_sdf(sol_pos + np.array([0, -eps, 0]))
                sdf_pz = interp_sdf(sol_pos + np.array([0, 0, eps]))
                sdf_mz = interp_sdf(sol_pos + np.array([0, 0, -eps]))
                
                grad_x = (sdf_px - sdf_mx) / (2 * eps)
                grad_y = (sdf_py - sdf_my) / (2 * eps)
                grad_z = (sdf_pz - sdf_mz) / (2 * eps)
                
                push_dir = np.stack([grad_x, grad_y, grad_z], axis=1)
                push_mag = np.linalg.norm(push_dir, axis=1, keepdims=True)
                # Safe division to avoid RuntimeWarning
                push_dir = np.divide(push_dir, push_mag, out=np.tile(-grav, (len(solid_idx), 1)), where=push_mag > 1e-6)
                
                # Push particles out of solid
                penetration = np.abs(sdf[solid_idx, None])
                active_pos[solid_idx] += push_dir * (penetration + avg_dx)
                
                # Reflect velocity
                v_normal = np.sum(active_vel[solid_idx] * push_dir, axis=1, keepdims=True)
                active_vel[solid_idx] -= v_normal * push_dir * 1.8  # Bounce

            # 6. Overall speed cap
            speed = np.linalg.norm(active_vel, axis=1, keepdims=True)
            max_speed = avg_dx * 20.0
            active_vel = np.where(speed > max_speed, active_vel * max_speed / (speed + 1e-9), active_vel)

            # 7. Update positions
            new_pos = active_pos + active_vel

            # 8. Bounds checking - particles can fall PAST the domain (into void)
            # Only respawn if they go WAY out of bounds (10x domain size)
            far_out = (
                (new_pos[:, 0] < x_min - domain_size) | (new_pos[:, 0] > x_max + domain_size) |
                (new_pos[:, 1] < y_min - domain_size) | (new_pos[:, 1] > y_max + domain_size) |
                (new_pos[:, 2] < z_min - domain_size) | (new_pos[:, 2] > z_max + domain_size)
            )
            
            # 9. Decay check - particles too far from surface (in open air) get recycled
            # But particles that left the STL downward should keep falling!
            new_sdf = interp_sdf(new_pos)
            
            # Only decay if far from surface AND not falling (gravity direction)
            # If particle is moving in gravity direction, let it fall
            falling = np.sum(active_vel * grav, axis=1) > gravity_accel_mm * 0.5
            too_far = (new_sdf > max_distance_from_surface) & (~falling)
            
            # 10. Age check - only very old particles respawn
            too_old = active_age > particle_lifetime_frames * 2
            
            # Combine decay conditions - be more lenient
            should_respawn = far_out | too_far | too_old | (new_sdf < -avg_dx * 10)
            
            if np.any(should_respawn):
                respawn_idx = np.where(should_respawn)[0]
                n_decayed += len(respawn_idx)
                
                # Respawn at source
                new_offsets = random_sphere_offsets(len(respawn_idx), emit_radius_mm)
                new_pos[respawn_idx] = src + new_offsets
                active_vel[respawn_idx] = grav * emit_speed_mm
                active_age[respawn_idx] = 0

            # Apply updates
            pos[active] = new_pos
            vel[active] = active_vel
            age[active] = active_age + 1

        # Progress logging
        if t == 0 or t % max(1, n_frames // 4) == 0 or t == n_frames - 1:
            n_born = np.sum(~not_born)
            print(f"[Advect] Frame {t}/{n_frames}: born={n_born:,}, active={n_active:,}, decayed={n_decayed:,}")

    # ==========================================================================
    # Final statistics
    # ==========================================================================
    born_mask = birth_frames <= n_frames - 1
    if np.any(born_mask):
        movement = np.linalg.norm(frames[-1, born_mask] - frames[0, born_mask], axis=1)
        print(f"[Advect] === Final Statistics ===")
        print(f"[Advect] Movement - min: {movement.min():.1f}mm, max: {movement.max():.1f}mm, mean: {movement.mean():.1f}mm")
        print(f"[Advect] Total decays: {n_decayed:,}, collisions: {n_collisions:,}")

    return frames
