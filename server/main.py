from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager
import uvicorn
import os
from pathlib import Path

from app.api.v1.endpoints import inference, training, models as model_routes, annotations, auth, annotations_analyze, smart_annotation, video, active_learning, monitoring
from app.db.session import initialize_database
from app.core.config import settings
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    logger.info("🚀 Starting YOLO Generator API...")
    initialize_database()
    yield
    # Shutdown (if needed, add cleanup code here)
    logger.info("👋 Shutting down YOLO Generator API...")


app = FastAPI(
    title="YOLO Generator API",
    description="ML Model Training and Inference Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create datasets directory if it doesn't exist
datasets_dir = Path("datasets")
datasets_dir.mkdir(exist_ok=True)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(inference.router, prefix="/api/inference", tags=["Inference"])
app.include_router(training.router, prefix="/api/training", tags=["Analysis"])
app.include_router(model_routes.router, prefix="/api/models", tags=["models"])
app.include_router(annotations.router, prefix="/api/annotations", tags=["Annotations"])
app.include_router(annotations_analyze.router, prefix="/api/annotations", tags=["Annotations"])
app.include_router(smart_annotation.router, prefix="/api/smart", tags=["Smart Tools"])
app.include_router(video.router, prefix="/api/video", tags=["Video"])
app.include_router(active_learning.router, prefix="/api/active-learning", tags=["Active Learning"])
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["Monitoring"])

@app.get("/")
async def root():
    return {
        "message": "YOLO Generator API",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

