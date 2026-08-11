#!/bin/bash

echo "🚀 Starting YOLO Generator Platform..."

BACKEND_PID=""
FRONTEND_PID=""

# Setup cleanup function to kill background processes
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    if [ -n "$BACKEND_PID" ]; then
        echo "Killing Backend (PID: $BACKEND_PID)..."
        kill -TERM $BACKEND_PID 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        echo "Killing Frontend (PID: $FRONTEND_PID)..."
        kill -TERM $FRONTEND_PID 2>/dev/null || true
    fi
    
    # Also attempt to kill by port if they were pre-existing
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
        echo "Killing any remaining process on port 8000..."
        kill -9 $(lsof -Pi :8000 -sTCP:LISTEN -t) 2>/dev/null || true
    fi
    if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null ; then
        echo "Killing any remaining process on port 3000..."
        kill -9 $(lsof -Pi :3000 -sTCP:LISTEN -t) 2>/dev/null || true
    fi
    
    echo "✅ All services stopped."
    exit 0
}

# Catch termination signals
trap cleanup SIGINT SIGTERM

# Check if Python backend is running
if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "📦 Starting Python Server on port 8000..."
    cd server
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install requirements
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    
    # Start FastAPI backend
    echo "Starting FastAPI server..."
    python main.py &
    BACKEND_PID=$!
    echo "✅ Server started with PID: $BACKEND_PID"
    
    cd ..
else
    echo "✅ Server already running on port 8000"
fi

# Check if Next.js frontend is running
if ! lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null ; then
    echo "🎨 Starting Next.js Client on port 3000..."
    cd client
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm install
    fi
    
    # Start Next.js dev server
    npm run dev &
    FRONTEND_PID=$!
    echo "✅ Frontend started with PID: $FRONTEND_PID"
    
    cd ..
else
    echo "✅ Frontend already running on port 3000"
fi

echo ""
echo "🎉 YOLO Generator is ready!"
echo "📱 Frontend: http://localhost:3000"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for user interrupt
wait

