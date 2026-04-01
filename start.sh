#!/bin/bash

echo "============================================"
echo "  Autonomous Content Factory - Startup"
echo "============================================"
echo ""

# Backend
echo "[1/2] Starting Backend (FastAPI on port 8000)..."
cd backend

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q

# Start backend in background
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

cd ..

# Frontend
echo ""
echo "[2/2] Starting Frontend (Vite on port 5173)..."
cd frontend
npm install -s
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "============================================"
echo " Both servers running!"
echo " Open: http://localhost:5173"
echo " Press Ctrl+C to stop both"
echo "============================================"

# Wait and handle exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Servers stopped.'" EXIT
wait
