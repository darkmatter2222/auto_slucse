# CFD Fluid Simulation App - Start Script
# Run this single script to start both backend and frontend

Write-Host "🌊 Starting CFD Fluid Simulation App..." -ForegroundColor Cyan
Write-Host ""

$repoRoot = "C:\Users\ryans\source\repos\auto_slucse"
$appRoot = "$repoRoot\test_CFD\fluid_app"
$venvPython = "$repoRoot\.venv\Scripts\python.exe"

# Kill any existing processes
Write-Host "Cleaning up existing processes..." -ForegroundColor Yellow
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*fluid_app*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Start Backend (FastAPI + Uvicorn) in new window
Write-Host "Starting Backend API server (port 8010)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$appRoot\backend'; Write-Host 'Backend API Server' -ForegroundColor Cyan; & '$venvPython' -m uvicorn app:app --host 127.0.0.1 --port 8010"

Start-Sleep -Seconds 2

# Start Frontend (Vite dev server) in new window
Write-Host "Starting Frontend dev server (port 5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$appRoot\frontend'; Write-Host 'Frontend Dev Server' -ForegroundColor Cyan; npm run dev"

Start-Sleep -Seconds 3

# Open browser
Write-Host ""
Write-Host "Opening browser..." -ForegroundColor Magenta
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "✅ App started successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend:  http://127.0.0.1:8010" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "To stop: Close the PowerShell windows or run:" -ForegroundColor Yellow
Write-Host "  Get-Process -Name python,node | Stop-Process -Force" -ForegroundColor Gray
Write-Host ""
