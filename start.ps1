# NebulaML Startup Script for Windows
# This script starts both the FastAPI backend and the Next.js frontend.

Write-Host "🚀 Starting NebulaML..." -ForegroundColor Cyan

# Start Backend
Write-Host "📂 Starting Backend (FastAPI)..." -ForegroundColor Yellow
$backendProcess = Start-Process -NoNewWindow -PassThru -FilePath "powershell.exe" -ArgumentList "-Command", "cd server; .\venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

# Wait for backend to initialize
Start-Sleep -Seconds 3

# Start Frontend
Write-Host "💻 Starting Frontend (Next.js)..." -ForegroundColor Yellow
$frontendProcess = Start-Process -NoNewWindow -PassThru -FilePath "powershell.exe" -ArgumentList "-Command", "cd client; npm run dev"

Write-Host "✨ NebulaML is running!" -ForegroundColor Green
Write-Host "🔗 Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "🔗 Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "Press Ctrl+C in this terminal to stop." -ForegroundColor Gray

try {
    # Wait indefinitely until Ctrl+C
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "🛑 Stopping services..." -ForegroundColor Yellow
    if ($backendProcess -and !$backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force
    }
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force
    }
    
    # Attempt to kill lingering node/python processes if needed (optional)
    # Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force
    # Get-Process -Name "python" -ErrorAction SilentlyContinue | Stop-Process -Force
    
    Write-Host "✅ All services stopped." -ForegroundColor Green
}
