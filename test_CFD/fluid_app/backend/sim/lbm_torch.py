from __future__ import annotations

import numpy as np

try:
    import torch
except Exception as ex:  # pragma: no cover
    torch = None


class LbmD3Q19Torch:
    # D3Q19 velocities
    _c_np = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [-1, 0, 0],
            [0, 1, 0],
            [0, -1, 0],
            [0, 0, 1],
            [0, 0, -1],
            [1, 1, 0],
            [-1, 1, 0],
            [1, -1, 0],
            [-1, -1, 0],
            [1, 0, 1],
            [-1, 0, 1],
            [1, 0, -1],
            [-1, 0, -1],
            [0, 1, 1],
            [0, -1, 1],
            [0, 1, -1],
            [0, -1, -1],
        ],
        dtype=np.int64,
    )

    _w_np = np.array(
        [
            1 / 3,
            1 / 18,
            1 / 18,
            1 / 18,
            1 / 18,
            1 / 18,
            1 / 18,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
            1 / 36,
        ],
        dtype=np.float32,
    )

    _opp_np = np.array([0, 2, 1, 4, 3, 6, 5, 10, 9, 8, 7, 14, 13, 12, 11, 18, 17, 16, 15], dtype=np.int64)

    def __init__(self, *, nx: int, ny: int, nz: int, nu_lbm: float, solid: np.ndarray, inlet: np.ndarray, outlet: np.ndarray):
        if torch is None:
            raise RuntimeError("PyTorch is not available. Install torch with CUDA for GPU compute.")

        self.nx, self.ny, self.nz = int(nx), int(ny), int(nz)
        self.nu = float(nu_lbm)
        self.tau = 3.0 * self.nu + 0.5
        self.omega = 1.0 / self.tau

        self.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

        self.c = torch.tensor(self._c_np, device=self.device, dtype=torch.int64)
        self.w = torch.tensor(self._w_np, device=self.device, dtype=torch.float32)
        self.opposite = torch.tensor(self._opp_np, device=self.device, dtype=torch.int64)

        # Masks
        self.solid = torch.tensor(solid.astype(np.bool_), device=self.device)
        self.inlet = torch.tensor(inlet.astype(np.bool_), device=self.device)
        self.outlet = torch.tensor(outlet.astype(np.bool_), device=self.device)

        # Fields
        self.rho = torch.ones((self.nx, self.ny, self.nz), device=self.device, dtype=torch.float32)
        self.ux = torch.zeros_like(self.rho)
        self.uy = torch.zeros_like(self.rho)
        self.uz = torch.zeros_like(self.rho)

        self.inlet_dir = torch.tensor([0.0, 0.0, -1.0], device=self.device, dtype=torch.float32)

        self.f = self._equilibrium(self.rho, self.ux, self.uy, self.uz)

    def set_inlet_direction(self, direction_xyz: np.ndarray):
        v = torch.tensor(direction_xyz, device=self.device, dtype=torch.float32)
        n = torch.linalg.norm(v)
        if float(n) < 1e-12:
            raise ValueError("inlet direction is zero")
        self.inlet_dir = v / n

    def _equilibrium(self, rho, ux, uy, uz):
        # feq[q] = w[q]*rho*(1 + 3cu + 4.5cu^2 - 1.5 u^2)
        u_sq = ux * ux + uy * uy + uz * uz
        feq = torch.empty((19, self.nx, self.ny, self.nz), device=self.device, dtype=torch.float32)
        cx = self.c[:, 0].to(torch.float32).view(19, 1, 1, 1)
        cy = self.c[:, 1].to(torch.float32).view(19, 1, 1, 1)
        cz = self.c[:, 2].to(torch.float32).view(19, 1, 1, 1)

        cu = cx * ux.unsqueeze(0) + cy * uy.unsqueeze(0) + cz * uz.unsqueeze(0)
        w = self.w.view(19, 1, 1, 1)
        feq = w * rho.unsqueeze(0) * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * u_sq.unsqueeze(0))
        return feq

    def _collide(self):
        feq = self._equilibrium(self.rho, self.ux, self.uy, self.uz)
        self.f = self.f - self.omega * (self.f - feq)

    def _stream(self):
        f_new = torch.empty_like(self.f)
        for q in range(19):
            sx = int(self._c_np[q, 0])
            sy = int(self._c_np[q, 1])
            sz = int(self._c_np[q, 2])
            f_new[q] = torch.roll(self.f[q], shifts=(sx, sy, sz), dims=(0, 1, 2))
        self.f = f_new

    def _apply_boundaries(self, inlet_speed: float):
        # Bounce-back
        solid = self.solid
        for q in range(19):
            self.f[q][solid] = self.f[int(self.opposite[q])][solid]

        if bool(torch.any(self.inlet)):
            inlet_rho = 1.0
            self.rho[self.inlet] = inlet_rho
            self.ux[self.inlet] = self.inlet_dir[0] * inlet_speed
            self.uy[self.inlet] = self.inlet_dir[1] * inlet_speed
            self.uz[self.inlet] = self.inlet_dir[2] * inlet_speed

            feq_inlet = self._equilibrium(self.rho, self.ux, self.uy, self.uz)
            for q in range(19):
                self.f[q][self.inlet] = feq_inlet[q][self.inlet]

        if bool(torch.any(self.outlet)):
            self.rho[self.outlet] = 1.0

    def _compute_macroscopic(self):
        self.rho = torch.sum(self.f, dim=0)
        self.rho = torch.clamp(self.rho, min=1e-10)

        cx = self.c[:, 0].to(torch.float32).view(19, 1, 1, 1)
        cy = self.c[:, 1].to(torch.float32).view(19, 1, 1, 1)
        cz = self.c[:, 2].to(torch.float32).view(19, 1, 1, 1)

        self.ux = torch.sum(self.f * cx, dim=0) / self.rho
        self.uy = torch.sum(self.f * cy, dim=0) / self.rho
        self.uz = torch.sum(self.f * cz, dim=0) / self.rho

        self.ux[self.solid] = 0.0
        self.uy[self.solid] = 0.0
        self.uz[self.solid] = 0.0

    def step(self, *, inlet_speed: float):
        self._collide()
        self._stream()
        self._apply_boundaries(inlet_speed=float(inlet_speed))
        self._compute_macroscopic()

    def velocity_cpu(self):
        return (
            self.ux.detach().to("cpu").numpy(),
            self.uy.detach().to("cpu").numpy(),
            self.uz.detach().to("cpu").numpy(),
        )
