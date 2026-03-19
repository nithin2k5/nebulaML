# NebulaML Startup Script for Windows
# This script starts both the FastAPI backend and the Next.js frontend.

Write-Host "🚀 Starting NebulaML..." -ForegroundColor Cyan

# Start Backend
Write-Host "📂 Starting Backend (FastAPI)..." -ForegroundColor Yellow
Start-Process -NoNewWindow -FilePath "powershell.exe" -ArgumentList "-Command", "cd server; .\venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

# Wait for backend to initialize
Start-Sleep -Seconds 3

# Start Frontend
Write-Host "💻 Starting Frontend (Next.js)..." -ForegroundColor Yellow
Start-Process -NoNewWindow -FilePath "powershell.exe" -ArgumentList "-Command", "cd client; npm run dev"

Write-Host "✨ NebulaML is running!" -ForegroundColor Green
Write-Host "🔗 Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "🔗 Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "Press Ctrl+C in this terminal to stop (Wait, you'll need to stop the background processes manually or use Stop-Process)" -ForegroundColor Gray
