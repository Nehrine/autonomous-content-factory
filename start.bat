@echo off
echo ============================================
echo   Autonomous Content Factory - Startup
echo ============================================
echo.

echo [1/2] Starting Backend (FastAPI on port 8000)...
cd backend
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt --quiet
start "Backend" cmd /k "venv\Scripts\activate && uvicorn main:app --reload --port 8000"

echo.
echo [2/2] Starting Frontend (Vite on port 5173)...
cd ..\frontend
call npm install --silent
start "Frontend" cmd /k "npm run dev"

echo.
echo ============================================
echo  Both servers started!
echo  Open: http://localhost:5173
echo ============================================
pause
