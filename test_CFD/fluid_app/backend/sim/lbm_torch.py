"""
D3Q19 Lattice Boltzmann Method solver with TRUE GRAVITY BODY FORCE.
Optimized for RTX 5090 - uses large grids, vectorized operations, and proper physics.

Key improvements over basic LBM:
- Gravity is a REAL BODY FORCE applied every timestep (Guo forcing scheme)
- Free surface support via fill_level tracking
- Higher resolution support (256-512 cells)
- Proper BGK collision with forcing term
- Velocity field that actually responds to gravity!
"""
from __future__ import annotations

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except Exception:
    torch = None
    TORCH_AVAILABLE = False


class LbmD3Q19Torch:
    """
    D3Q19 Lattice Boltzmann solver with:
    - BGK collision operator
    - Bounce-back solid boundaries
    - GRAVITY BODY FORCE (Guo forcing scheme) - this is the key for realistic flow!
    - Free surface tracking for filling simulation
    """

    # D3Q19 lattice velocities
    _c_np = np.array([
        [0, 0, 0],     # 0 - rest
        [1, 0, 0],     # 1
        [-1, 0, 0],    # 2
        [0, 1, 0],     # 3
        [0, -1, 0],    # 4
        [0, 0, 1],     # 5
        [0, 0, -1],    # 6
        [1, 1, 0],     # 7
        [-1, 1, 0],    # 8
        [1, -1, 0],    # 9
        [-1, -1, 0],   # 10
        [1, 0, 1],     # 11
        [-1, 0, 1],    # 12
        [1, 0, -1],    # 13
        [-1, 0, -1],   # 14
        [0, 1, 1],     # 15
        [0, -1, 1],    # 16
        [0, 1, -1],    # 17
        [0, -1, -1],   # 18
    ], dtype=np.int64)

    # Weights for D3Q19
    _w_np = np.array([
        1/3,    # rest
        1/18, 1/18, 1/18, 1/18, 1/18, 1/18,  # face neighbors
        1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36,  # edge neighbors
    ], dtype=np.float32)

    # Opposite direction indices for bounce-back
    _opp_np = np.array([0, 2, 1, 4, 3, 6, 5, 10, 9, 8, 7, 14, 13, 12, 11, 18, 17, 16, 15], dtype=np.int64)

    def __init__(
        self,
        *,
        nx: int,
        ny: int,
        nz: int,
        nu_lbm: float,
        solid: np.ndarray,
        inlet: np.ndarray,
        outlet: np.ndarray,
        gravity_lbm: np.ndarray | None = None,
    ):
        """
        Initialize the LBM solver.
        
        Args:
            nx, ny, nz: Grid dimensions
            nu_lbm: Kinematic viscosity in lattice units (typically 0.01-0.2)
            solid: Boolean mask of solid cells (nx, ny, nz)
            inlet: Boolean mask of inlet cells
            outlet: Boolean mask of outlet cells  
            gravity_lbm: Gravity vector in lattice units (scaled from physical)
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is not available. Install torch with CUDA for GPU compute.")

        self.nx, self.ny, self.nz = int(nx), int(ny), int(nz)
        self.nu = float(nu_lbm)
        self.tau = 3.0 * self.nu + 0.5
        self.omega = 1.0 / self.tau

        # Use CUDA if available
        self.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        print(f"[LBM] Using device: {self.device}")
        if self.device.type == "cuda":
            print(f"[LBM] GPU: {torch.cuda.get_device_name()}")
            mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"[LBM] VRAM: {mem_gb:.1f} GB")

        # Lattice vectors and weights on GPU
        self.c = torch.tensor(self._c_np, device=self.device, dtype=torch.int64)
        self.c_float = self.c.to(torch.float32)
        self.w = torch.tensor(self._w_np, device=self.device, dtype=torch.float32)
        self.opposite = torch.tensor(self._opp_np, device=self.device, dtype=torch.int64)

        # Masks
        self.solid = torch.tensor(solid.astype(np.bool_), device=self.device)
        self.inlet = torch.tensor(inlet.astype(np.bool_), device=self.device)
        self.outlet = torch.tensor(outlet.astype(np.bool_), device=self.device)
        self.fluid = ~self.solid

        # Gravity body force in lattice units - THIS IS KEY FOR REALISTIC FLOW
        if gravity_lbm is None:
            self.gravity = torch.zeros(3, device=self.device, dtype=torch.float32)
        else:
            self.gravity = torch.tensor(gravity_lbm, device=self.device, dtype=torch.float32)
        print(f"[LBM] Gravity (lattice units): {self.gravity.cpu().numpy()}")

        # Inlet direction
        self.inlet_dir = torch.tensor([0.0, 0.0, -1.0], device=self.device, dtype=torch.float32)

        # Macroscopic fields
        self.rho = torch.ones((self.nx, self.ny, self.nz), device=self.device, dtype=torch.float32)
        self.ux = torch.zeros_like(self.rho)
        self.uy = torch.zeros_like(self.rho)
        self.uz = torch.zeros_like(self.rho)

        # Free surface tracking: fill_level 0=empty, 1=full
        self.fill_level = torch.zeros_like(self.rho)
        self.fill_level[self.inlet] = 1.0

        # Pre-compute lattice direction arrays for vectorized operations
        # MUST be created BEFORE calling _equilibrium()
        self._cx = self.c_float[:, 0].view(19, 1, 1, 1)
        self._cy = self.c_float[:, 1].view(19, 1, 1, 1)
        self._cz = self.c_float[:, 2].view(19, 1, 1, 1)
        self._w = self.w.view(19, 1, 1, 1)

        # Distribution functions - initialize to equilibrium
        self.f = self._equilibrium(self.rho, self.ux, self.uy, self.uz)

        # Stats
        n_solid = int(self.solid.sum())
        n_fluid = int(self.fluid.sum())
        n_inlet = int(self.inlet.sum())
        n_outlet = int(self.outlet.sum())
        total = self.nx * self.ny * self.nz
        print(f"[LBM] Grid: {self.nx}x{self.ny}x{self.nz} = {total:,} cells")
        print(f"[LBM] Solid: {n_solid:,} ({100*n_solid/total:.1f}%)")
        print(f"[LBM] Fluid: {n_fluid:,} ({100*n_fluid/total:.1f}%)")
        print(f"[LBM] Inlet: {n_inlet:,}, Outlet: {n_outlet:,}")
        print(f"[LBM] tau={self.tau:.4f}, omega={self.omega:.4f}")

    def set_inlet_direction(self, direction_xyz: np.ndarray):
        """Set the inlet velocity direction (normalized)."""
        v = torch.tensor(direction_xyz, device=self.device, dtype=torch.float32)
        n = torch.linalg.norm(v)
        if float(n) < 1e-12:
            v = torch.tensor([0.0, 0.0, -1.0], device=self.device, dtype=torch.float32)
        else:
            v = v / n
        self.inlet_dir = v

    def set_gravity_lbm(self, gravity_lbm: np.ndarray):
        """Set gravity body force in lattice units."""
        self.gravity = torch.tensor(gravity_lbm, device=self.device, dtype=torch.float32)

    def _equilibrium(self, rho, ux, uy, uz):
        """Compute equilibrium distribution."""
        u_sq = ux * ux + uy * uy + uz * uz
        cu = self._cx * ux.unsqueeze(0) + self._cy * uy.unsqueeze(0) + self._cz * uz.unsqueeze(0)
        feq = self._w * rho.unsqueeze(0) * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * u_sq.unsqueeze(0))
        return feq

    def _collide_with_forcing(self, inlet_speed: float):
        """
        BGK collision with Guo forcing scheme for gravity.
        This applies gravity as a body force - the key to realistic falling/flowing behavior!
        """
        # Compute equilibrium
        feq = self._equilibrium(self.rho, self.ux, self.uy, self.uz)

        # Standard BGK collision
        self.f = self.f - self.omega * (self.f - feq)

        # Guo forcing scheme for gravity body force
        # F_i = (1 - omega/2) * w_i * [ 3*(c_i - u) + 9*(c_i · u)*c_i ] · g
        g_mag = torch.sqrt(torch.sum(self.gravity ** 2))
        if g_mag > 1e-12:
            gx, gy, gz = self.gravity[0], self.gravity[1], self.gravity[2]

            # (c - u) terms
            cmux = self._cx - self.ux.unsqueeze(0)
            cmuy = self._cy - self.uy.unsqueeze(0)
            cmuz = self._cz - self.uz.unsqueeze(0)

            # c · u
            cu = self._cx * self.ux.unsqueeze(0) + self._cy * self.uy.unsqueeze(0) + self._cz * self.uz.unsqueeze(0)

            # Force term
            force_term = (
                3.0 * (cmux * gx + cmuy * gy + cmuz * gz) +
                9.0 * cu * (self._cx * gx + self._cy * gy + self._cz * gz)
            )

            # Apply forcing
            forcing = (1.0 - 0.5 * self.omega) * self._w * self.rho.unsqueeze(0) * force_term
            self.f = self.f + forcing

    def _stream(self):
        """Streaming step using torch.roll."""
        f_new = torch.empty_like(self.f)
        for q in range(19):
            sx = int(self._c_np[q, 0])
            sy = int(self._c_np[q, 1])
            sz = int(self._c_np[q, 2])
            f_new[q] = torch.roll(self.f[q], shifts=(sx, sy, sz), dims=(0, 1, 2))
        self.f = f_new

    def _apply_boundaries(self, inlet_speed: float):
        """Apply boundary conditions: bounce-back, inlet, outlet."""
        # Bounce-back on solid boundaries
        solid_mask = self.solid
        for q in range(19):
            opp_q = int(self.opposite[q])
            self.f[q][solid_mask] = self.f[opp_q][solid_mask]

        # Inlet: set equilibrium with prescribed velocity
        if bool(torch.any(self.inlet)):
            inlet_rho = 1.0
            self.rho[self.inlet] = inlet_rho
            self.ux[self.inlet] = self.inlet_dir[0] * inlet_speed
            self.uy[self.inlet] = self.inlet_dir[1] * inlet_speed
            self.uz[self.inlet] = self.inlet_dir[2] * inlet_speed

            feq_inlet = self._equilibrium(self.rho, self.ux, self.uy, self.uz)
            for q in range(19):
                self.f[q][self.inlet] = feq_inlet[q][self.inlet]

            self.fill_level[self.inlet] = 1.0

        # Outlet: fixed pressure
        if bool(torch.any(self.outlet)):
            self.rho[self.outlet] = 1.0

    def _compute_macroscopic(self):
        """Compute macroscopic quantities with Guo forcing correction."""
        self.rho = torch.sum(self.f, dim=0)
        self.rho = torch.clamp(self.rho, min=1e-10)

        # Momentum
        self.ux = torch.sum(self.f * self._cx, dim=0) / self.rho
        self.uy = torch.sum(self.f * self._cy, dim=0) / self.rho
        self.uz = torch.sum(self.f * self._cz, dim=0) / self.rho

        # Guo forcing velocity correction: u = (sum f_q c_q)/rho + g*dt/2
        g_mag = torch.sqrt(torch.sum(self.gravity ** 2))
        if g_mag > 1e-12:
            self.ux = self.ux + 0.5 * self.gravity[0]
            self.uy = self.uy + 0.5 * self.gravity[1]
            self.uz = self.uz + 0.5 * self.gravity[2]

        # Zero velocity in solid
        self.ux[self.solid] = 0.0
        self.uy[self.solid] = 0.0
        self.uz[self.solid] = 0.0

    def _update_fill_level(self):
        """Update fill level - simple VOF-like transport."""
        speed = torch.sqrt(self.ux**2 + self.uy**2 + self.uz**2)
        fill_new = self.fill_level.clone()

        # Upwind-style transport
        for dim in range(3):
            u_comp = [self.ux, self.uy, self.uz][dim]
            fill_pos = torch.roll(self.fill_level, shifts=1, dims=dim)
            fill_neg = torch.roll(self.fill_level, shifts=-1, dims=dim)
            flux_in = torch.where(u_comp > 0, fill_pos * u_comp, fill_neg * (-u_comp))
            flux_out = self.fill_level * torch.abs(u_comp)
            fill_new = fill_new + 0.08 * (flux_in - flux_out)

        fill_new = torch.clamp(fill_new, 0.0, 1.0)
        fill_new[self.solid] = 0.0
        fill_new[self.inlet] = 1.0
        self.fill_level = fill_new

    def step(self, *, inlet_speed: float, update_fill: bool = True):
        """Perform one LBM timestep."""
        self._collide_with_forcing(inlet_speed=inlet_speed)
        self._stream()
        self._apply_boundaries(inlet_speed=inlet_speed)
        self._compute_macroscopic()
        if update_fill:
            self._update_fill_level()

    def velocity_cpu(self):
        """Get velocity field on CPU."""
        ux_np = self.ux.detach().cpu().numpy()
        uy_np = self.uy.detach().cpu().numpy()
        uz_np = self.uz.detach().cpu().numpy()

        speed = np.sqrt(ux_np**2 + uy_np**2 + uz_np**2)
        fluid_mask = ~self.solid.detach().cpu().numpy()
        fluid_speed = speed[fluid_mask]

        print(f"[LBM] Final velocity field (fluid cells):")
        print(f"  Speed - min: {fluid_speed.min():.6f}, max: {fluid_speed.max():.6f}, mean: {fluid_speed.mean():.6f}")
        print(f"  ux: [{ux_np[fluid_mask].min():.6f}, {ux_np[fluid_mask].max():.6f}]")
        print(f"  uy: [{uy_np[fluid_mask].min():.6f}, {uy_np[fluid_mask].max():.6f}]")
        print(f"  uz: [{uz_np[fluid_mask].min():.6f}, {uz_np[fluid_mask].max():.6f}]")

        return (ux_np, uy_np, uz_np)

    def fill_level_cpu(self):
        """Get fill level on CPU."""
        return self.fill_level.detach().cpu().numpy()
