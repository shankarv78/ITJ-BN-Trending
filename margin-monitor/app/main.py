"""
Margin Monitor - FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.database import init_db
from app.api.routes import router as api_router
from app.api.hedge_routes import router as hedge_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Margin Monitor...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Import and configure scheduler with db session maker
    from app.services.scheduler_service import scheduler_service
    from app.database import async_session_maker
    scheduler_service.set_db_session_maker(async_session_maker)
    scheduler_service.start()
    logger.info("Scheduler started")

    yield

    # Shutdown
    scheduler_service.stop()
    logger.info("Margin Monitor stopped")


# Create FastAPI application
app = FastAPI(
    title="Margin Monitor",
    description="Intraday margin utilization monitoring for Nifty/Sensex options trading",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
# Note: allow_credentials=False when using wildcard origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/margin")
app.include_router(hedge_router)  # Auto-hedge routes (already has /api/hedge prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "margin-monitor"}
