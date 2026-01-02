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
from app.api.hedge_routes import router as hedge_router, set_orchestrator

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

    # Start Auto-Hedge Orchestrator (if configured)
    orchestrator = None
    if settings.auto_hedge_enabled:
        try:
            from app.services.hedge_orchestrator import AutoHedgeOrchestrator
            from app.services.hedge_executor import HedgeExecutorService
            from app.services.hedge_selector import HedgeStrikeSelectorService
            from app.services.strategy_scheduler import StrategySchedulerService
            from app.services.margin_calculator import MarginCalculatorService
            from app.services.telegram_service import TelegramService
            from app.services.openalgo_service import OpenAlgoService, openalgo_service
            from app.database import get_db

            # Create services - use factory for long-running orchestrator
            from contextlib import asynccontextmanager as async_ctx_mgr

            @async_ctx_mgr
            async def get_db_session():
                """Create a new async session for each operation."""
                async with async_session_maker() as session:
                    yield session

            openalgo = OpenAlgoService(
                base_url=settings.openalgo_base_url,
                api_key=settings.openalgo_api_key
            )
            telegram = TelegramService(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id
            )
            margin_calc = MarginCalculatorService()
            # Initialize services with correct parameters
            scheduler = StrategySchedulerService(async_session_maker())
            selector = HedgeStrikeSelectorService(
                openalgo=openalgo,
                margin_calculator=margin_calc
            )
            executor = HedgeExecutorService(async_session_maker(), openalgo, telegram)

            # Create margin adapter for hedge orchestrator
            class HedgeMarginAdapter:
                """Adapter to provide margin data for hedge orchestrator."""
                def __init__(self, openalgo_svc, baseline: float = 0.0, total_budget: float = 15000000.0):
                    self.openalgo = openalgo_svc
                    self.baseline = baseline
                    self.total_budget = total_budget

                async def get_current_status(self) -> dict:
                    """Get current margin status in format orchestrator expects."""
                    funds = await self.openalgo.get_funds()
                    used_margin = funds.get('used_margin', 0) or funds.get('marginused', 0) or 0
                    intraday = used_margin - self.baseline
                    utilization = (intraday / self.total_budget) * 100 if self.total_budget > 0 else 0
                    return {
                        'utilization_pct': utilization,
                        'used_margin': used_margin,
                        'available': funds.get('available_margin', 0) or funds.get('availablecash', 0),
                        'intraday_margin': intraday,
                        'total_budget': self.total_budget
                    }

                async def get_filtered_positions(self) -> list:
                    """Get current positions."""
                    try:
                        return await self.openalgo.get_positions()
                    except Exception:
                        return []

            margin_adapter = HedgeMarginAdapter(openalgo_service)

            orchestrator = AutoHedgeOrchestrator(
                db_factory=get_db_session,
                margin_service=margin_adapter,
                scheduler=scheduler,
                margin_calc=margin_calc,
                hedge_selector=selector,
                hedge_executor=executor,
                telegram=telegram
            )

            # Store in app state and hedge_routes module for API access
            app.state.orchestrator = orchestrator
            set_orchestrator(orchestrator)

            # Start orchestrator in background with dry_run setting
            import asyncio
            asyncio.create_task(orchestrator.start(dry_run=settings.auto_hedge_dry_run))
            logger.info(f"Auto-Hedge Orchestrator started (dry_run={settings.auto_hedge_dry_run})")
        except Exception as e:
            logger.error(f"Failed to start Auto-Hedge Orchestrator: {e}")
            orchestrator = None
    else:
        logger.info("Auto-Hedge Orchestrator disabled (set AUTO_HEDGE_ENABLED=true to enable)")

    yield

    # Shutdown
    if orchestrator:
        await orchestrator.stop()
        logger.info("Auto-Hedge Orchestrator stopped")
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
