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

            # Create margin adapter that uses EXISTING margin monitor data
            # This ensures auto-hedge sees the SAME utilization as main margin monitor
            class HedgeMarginAdapter:
                """
                Adapter to provide margin data for hedge orchestrator.

                CRITICAL: Uses the actual DailyConfig (baseline, budget) from the database
                to ensure consistency with main margin monitor display.
                """
                def __init__(self, session_maker, openalgo_svc):
                    self.session_maker = session_maker  # async_session_maker
                    self.openalgo = openalgo_svc
                    self._cached_config = None

                async def _get_today_config(self):
                    """Get today's config with baseline and budget."""
                    from app.models import DailyConfig
                    from app.utils.date_utils import today_ist
                    from sqlalchemy import select

                    async with self.session_maker() as db:
                        result = await db.execute(
                            select(DailyConfig)
                            .where(DailyConfig.date == today_ist())
                            .where(DailyConfig.is_active == 1)
                        )
                        config = result.scalar_one_or_none()
                        if config:
                            self._cached_config = {
                                'id': config.id,
                                'baseline': config.baseline_margin or 0.0,
                                'budget': config.total_budget or 15000000.0,
                                'index': config.index_name,
                                'expiry_date': config.expiry_date.isoformat() if config.expiry_date else None
                            }
                        return self._cached_config

                async def get_current_status(self) -> dict:
                    """
                    Get current margin status using the ACTUAL margin service.
                    This ensures auto-hedge sees IDENTICAL utilization % as main UI.

                    Uses margin_service.get_current_margin() which includes:
                    - Baseline subtraction
                    - Excluded margin subtraction (PM + long-term positions)
                    """
                    from app.services.margin_service import margin_service

                    try:
                        # Use the SAME margin service as the main endpoint
                        # This ensures identical calculation including excluded margin
                        margin_data = await margin_service.get_current_margin()

                        if margin_data and margin_data.get('success'):
                            margin = margin_data.get('margin', {})
                            config = margin_data.get('config', {})

                            return {
                                'utilization_pct': margin.get('utilization_pct', 0),
                                'used_margin': margin.get('total_used', 0),
                                'available': margin.get('available_cash', 0),
                                'intraday_margin': margin.get('intraday_used', 0),
                                'total_budget': config.get('total_budget', 15000000.0),
                                'baseline': margin.get('baseline', 0),
                                'excluded': margin.get('excluded', 0)
                            }
                    except Exception as e:
                        logger.warning(f"[HEDGE_ADAPTER] Error using margin service: {e}")

                    # Fallback to basic calculation if margin service fails
                    config = await self._get_today_config()
                    if not config:
                        funds = await self.openalgo.get_funds()
                        used_margin = funds.get('used_margin', 0) or funds.get('marginused', 0) or 0
                        return {
                            'utilization_pct': 0,
                            'used_margin': used_margin,
                            'available': funds.get('available_margin', 0),
                            'intraday_margin': 0,
                            'total_budget': 15000000.0
                        }

                    # Basic fallback (no excluded margin)
                    funds = await self.openalgo.get_funds()
                    used_margin = funds.get('used_margin', 0) or funds.get('marginused', 0) or 0
                    baseline = config['baseline']
                    budget = config['budget']
                    intraday = max(0, used_margin - baseline)
                    utilization = (intraday / budget) * 100 if budget > 0 else 0

                    return {
                        'utilization_pct': utilization,
                        'used_margin': used_margin,
                        'available': funds.get('available_margin', 0) or funds.get('availablecash', 0),
                        'intraday_margin': intraday,
                        'total_budget': budget,
                        'baseline': baseline,
                        'excluded': 0
                    }

                async def get_filtered_positions(self) -> list:
                    """Get current positions."""
                    try:
                        return await self.openalgo.get_positions()
                    except Exception:
                        return []

                async def get_position_summary(self) -> dict:
                    """
                    Get position summary with CE/PE breakdown.
                    Uses same filtering as main margin monitor.
                    """
                    from app.services.position_service import position_service

                    config = await self._get_today_config()
                    if not config or not config.get('expiry_date'):
                        return {
                            'short_ce_qty': 0,
                            'short_pe_qty': 0,
                            'long_ce_qty': 0,
                            'long_pe_qty': 0,
                            'short_qty': 0,
                            'long_qty': 0
                        }

                    positions = await self.get_filtered_positions()
                    filtered = position_service.filter_positions(
                        positions,
                        config['index'],
                        config['expiry_date']
                    )
                    return position_service.get_summary(filtered)

                def get_cached_config(self):
                    """Return cached config for position filtering."""
                    return self._cached_config

            margin_adapter = HedgeMarginAdapter(async_session_maker, openalgo_service)

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
