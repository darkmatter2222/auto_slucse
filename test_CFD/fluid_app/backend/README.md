# Fluid App Backend

FastAPI service that:
- Serves the STL
- Runs a GPU-accelerated (PyTorch) D3Q19 LBM solver
- Generates particle-frame animation data (`.npz`)

## Run

From this folder:

```powershell
python -m pip install -r requirements.txt
# Install a CUDA build of torch that matches your system:
# https://pytorch.org/get-started/locally/

./run_server.ps1
```

API base: `http://127.0.0.1:8010`

- `GET /api/stl`
- `POST /api/simulate`
- `GET /api/run/{runId}/status`
- `GET /api/run/{runId}/result`
