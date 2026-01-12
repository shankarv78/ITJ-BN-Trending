"""
Service Manager - FastAPI Application

Entry point for the service manager API.
Manages ITJ Trading System services (start, stop, restart, status).
"""

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import SERVICE_MANAGER_PORT, SERVICE_MANAGER_HOST
from .routes import router as services_router
from .service_controller import controller

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"[SERVICE_MANAGER] Starting on http://{SERVICE_MANAGER_HOST}:{SERVICE_MANAGER_PORT}")
    yield
    # Cleanup
    await controller.close()
    logger.info("[SERVICE_MANAGER] Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="ITJ Service Manager",
    description="Manages ITJ Trading System services - start, stop, restart, and status checks",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware - allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",  # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(services_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for the service manager itself."""
    return {
        "status": "healthy",
        "service": "service-manager",
        "port": SERVICE_MANAGER_PORT
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "ITJ Service Manager",
        "version": "1.0.0",
        "endpoints": {
            "status": "/services/status",
            "service_status": "/services/{service_key}/status",
            "restart": "/services/{service_key}/restart",
            "stop": "/services/{service_key}/stop",
            "start": "/services/{service_key}/start",
            "health": "/health"
        },
        "services": ["frontend", "pm", "margin_monitor", "openalgo"]
    }


def main():
    """Run the service manager."""
    uvicorn.run(
        "service_manager.app:app",
        host=SERVICE_MANAGER_HOST,
        port=SERVICE_MANAGER_PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
