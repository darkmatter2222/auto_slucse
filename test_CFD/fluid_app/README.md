# Fluid App (STL + Gravity Flow)

This is a local app that:
- Loads the STL in a 3D view (rotate/pivot in space)
- Lets you pick a gravity direction
- Lets you click the STL to pick a water source location
- Lets you set flow rate (GPH) and a quality level
- Runs a GPU-accelerated LBM-style solver (PyTorch/CUDA) and returns an animated particle playback

## 1) Start the backend (Python)

```powershell
Set-Location "C:\Users\ryans\source\repos\auto_slucse\test_CFD\fluid_app\backend"
python -m pip install -r requirements.txt

# Install a CUDA build of torch that matches your system:
# https://pytorch.org/get-started/locally/

./run_server.ps1
```

Backend: `http://127.0.0.1:8010`

## 2) Start the frontend (React)

```powershell
Set-Location "C:\Users\ryans\source\repos\auto_slucse\test_CFD\fluid_app\frontend"
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Use

- Rotate the STL with the mouse (OrbitControls).
- Click the STL to set the source point.
- Set **Gravity direction**, **Flow rate**, and **Rendering intensity**.
- Click **Build to go**.

Notes:
- The backend currently treats the STL as a *solid* and simulates flow in the surrounding box (same basic assumption as the existing notebook). For internal-channel flow, the geometry needs a fluid-volume mesh or an STL that represents the negative space.
