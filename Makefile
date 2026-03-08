# NebulaML Makefile
# Shortcuts for common development tasks

.PHONY: help install dev start-backend start-frontend test lint format clean check

# Default target
help:
	@echo "NebulaML Development Commands:"
	@echo "  make install       - Install required dependencies for both frontend and backend"
	@echo "  make dev           - Start both backend and frontend servers for development"
	@echo "  make start-backend - Start only the FastAPI backend server"
	@echo "  make start-frontend- Start only the Next.js frontend server"
	@echo "  make lint          - Run linters (ruff, eslint)"
	@echo "  make format        - Format code (black, ruff, prettier)"
	@echo "  make test          - Run Python unit tests"
	@echo "  make clean         - Remove pycache and build artifacts"
	@echo "  make check         - Run format, lint, and tests (CI prep)"

install:
	@echo "Installing Backend Dependencies..."
	cd server && pip install -r requirements.txt
	@echo "Installing Frontend Dependencies..."
	cd client && npm install

dev:
	@echo "Starting full stack..."
	./start.sh

start-backend:
	@echo "Starting FastAPI backend..."
	cd server && uvicorn main:app --reload --host 0.0.0.0 --port 8000

start-frontend:
	@echo "Starting Next.js frontend..."
	cd client && npm run dev

lint:
	@echo "Linting Python code with Ruff..."
	cd server && ruff check .
	@echo "Linting JS/TS code with ESLint..."
	cd client && npm run lint

format:
	@echo "Formatting Python code with Black and Ruff..."
	cd server && black . && ruff format .
	@echo "Formatting JS/TS code..."
	cd client && npm run format || echo "Prettier format task missing, skipping."

test:
	@echo "Running tests..."
	cd server && pytest ../tests/ -v

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf server/runs/

check: format lint test
	@echo "All checks passed! Ready to commit."
