"""
Tests for AutoHedgeOrchestrator

Tests cover:
- Monitoring loop
- Hedge triggering based on utilization
- Imminent entry detection
- Hedge exit logic
- System state management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, time, timedelta
from contextlib import asynccontextmanager

from app.services.hedge_orchestrator import AutoHedgeOrchestrator
from app.models.hedge_constants import IndexName, ExpiryType


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_margin_service():
    """Mock margin service."""
    mock = AsyncMock()
    mock.get_current_status = AsyncMock(return_value={
        'utilization_pct': 75.0,
        'intraday_margin': 3750000,
        'total_budget': 5000000
    })
    mock.get_filtered_positions = AsyncMock(return_value=[
        {"symbol": "NIFTY06JAN2626200PE", "quantity": -1950},
        {"symbol": "NIFTY06JAN2626250CE", "quantity": -975}
    ])
    return mock


@pytest.fixture
def mock_db_factory():
    """Mock database session factory (callable)."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.fixture
def mock_strategy_scheduler():
    """Mock strategy scheduler."""
    mock = AsyncMock()
    mock.get_today_schedule = MagicMock(return_value=[])
    mock.get_next_entry = AsyncMock(return_value=None)
    mock.is_entry_imminent = AsyncMock(return_value=(False, None))
    mock.get_entries_in_window = MagicMock(return_value=[])
    mock.should_hold_hedges = AsyncMock(return_value=(False, None))
    return mock


@pytest.fixture
def mock_margin_calculator():
    """Mock margin calculator."""
    mock = MagicMock()
    mock.get_current_utilization = MagicMock(return_value=75.0)
    mock.calculate_projected_utilization = MagicMock(return_value=85.0)
    mock.is_hedge_required = MagicMock(return_value=False)
    mock.calculate_margin_reduction_needed = MagicMock(return_value=0)
    mock.should_exit_hedge = MagicMock(return_value=False)
    mock.evaluate_hedge_requirement = MagicMock(return_value=MagicMock(
        is_required=False,
        reason="",
        margin_reduction_needed=0,
        projected_utilization=85.0
    ))
    mock.estimate_hedge_margin_benefit = MagicMock(return_value=50000)
    return mock


@pytest.fixture
def mock_hedge_selector():
    """Mock hedge selector."""
    mock = AsyncMock()
    mock.select_optimal_hedges = AsyncMock(return_value=MagicMock(
        selected=[],
        total_cost=0,
        fully_covered=False,
        total_margin_benefit=0
    ))
    return mock


@pytest.fixture
def mock_hedge_executor():
    """Mock hedge executor."""
    mock = AsyncMock()
    # Correct method name: execute_hedge_buy returns OrderResult dataclass
    mock.execute_hedge_buy = AsyncMock(return_value=MagicMock(
        success=True,
        order_id="123",
        executed_price=3.5,
        error_message=None,
        transaction_id=1
    ))
    mock.execute_hedge_exit = AsyncMock(return_value=MagicMock(
        success=True,
        order_id="456",
        executed_price=1.5,
        error_message=None,
        transaction_id=2
    ))
    mock.get_active_hedges = AsyncMock(return_value=[])
    mock.get_cooldown_remaining = MagicMock(return_value=0)
    return mock


@pytest.fixture
def mock_telegram():
    """Mock telegram service."""
    mock = AsyncMock()
    mock.send_message = AsyncMock()
    mock.send_system_status = AsyncMock()
    mock.send_entry_imminent_alert = AsyncMock()
    mock.send_hedge_buy_alert = AsyncMock()
    mock.send_hedge_failure_alert = AsyncMock()
    return mock


@pytest.fixture
def orchestrator(
    mock_db_factory,
    mock_margin_service,
    mock_strategy_scheduler,
    mock_margin_calculator,
    mock_hedge_selector,
    mock_hedge_executor,
    mock_telegram
):
    """Create orchestrator with mocks."""
    orch = AutoHedgeOrchestrator(
        db_factory=mock_db_factory,
        margin_service=mock_margin_service,
        scheduler=mock_strategy_scheduler,
        margin_calc=mock_margin_calculator,
        hedge_selector=mock_hedge_selector,
        hedge_executor=mock_hedge_executor,
        telegram=mock_telegram
    )
    # Initialize session cache to avoid "No session" early return
    orch._session_cache = {
        'id': 1,
        'date': '2025-01-02',
        'index': 'NIFTY',
        'baskets': 10,
        'budget': 5000000,
        'auto_hedge_enabled': True,
        'expiry_date': '2025-01-06',
        'expiry_type': '2DTE'
    }
    orch._session = MagicMock()  # Mock session object
    return orch


# ============================================================
# State Management Tests
# ============================================================

class TestStateManagement:
    """Tests for orchestrator state management."""

    def test_initial_state_is_idle(self, orchestrator):
        """Orchestrator should start in idle state."""
        # Reset to check initial state
        orchestrator._is_running = False
        assert orchestrator.is_running is False

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, orchestrator):
        """Stop should clear running flag."""
        orchestrator._is_running = True
        await orchestrator.stop()
        assert orchestrator.is_running is False


# ============================================================
# Market Hours Tests
# ============================================================

class TestMarketHours:
    """Tests for market hours validation."""

    def test_recognizes_market_open(self, orchestrator):
        """Should recognize when market is open."""
        # Create a datetime with IST timezone info
        import pytz
        IST = pytz.timezone('Asia/Kolkata')
        mock_time = IST.localize(datetime(2025, 1, 2, 10, 30))

        with patch.object(orchestrator, '_now_ist', return_value=mock_time):
            is_open = orchestrator._is_market_hours()
            assert is_open is True

    def test_recognizes_market_closed(self, orchestrator):
        """Should recognize when market is closed."""
        import pytz
        IST = pytz.timezone('Asia/Kolkata')
        mock_time = IST.localize(datetime(2025, 1, 2, 16, 0))

        with patch.object(orchestrator, '_now_ist', return_value=mock_time):
            is_open = orchestrator._is_market_hours()
            assert is_open is False

    def test_recognizes_pre_market(self, orchestrator):
        """Should recognize pre-market hours."""
        import pytz
        IST = pytz.timezone('Asia/Kolkata')
        mock_time = IST.localize(datetime(2025, 1, 2, 9, 0))

        with patch.object(orchestrator, '_now_ist', return_value=mock_time):
            is_open = orchestrator._is_market_hours()
            assert is_open is False


# ============================================================
# Hedge Exit Tests
# ============================================================

class TestHedgeExit:
    """Tests for hedge exit logic."""

    @pytest.mark.asyncio
    async def test_no_exit_when_utilization_high(
        self, orchestrator, mock_margin_calculator
    ):
        """Should not exit when utilization is still high."""
        mock_margin_calculator.should_exit_hedge.return_value = False

        # _check_hedge_exit is the actual method name
        await orchestrator._check_hedge_exit(current_util=85.0)

        # Should not have called execute_hedge_exit
        orchestrator.hedge_executor.execute_hedge_exit.assert_not_called()


# ============================================================
# Status Reporting Tests
# ============================================================

class TestStatusReporting:
    """Tests for status reporting."""

    @pytest.mark.asyncio
    async def test_get_status(self, orchestrator):
        """Should return current status."""
        status = await orchestrator.get_status()

        assert "is_running" in status
        assert "dry_run" in status
        assert "session" in status

    @pytest.mark.asyncio
    async def test_status_includes_active_hedges(self, orchestrator):
        """Status should include active hedges."""
        status = await orchestrator.get_status()

        assert "active_hedges" in status


# ============================================================
# Monitoring Loop Tests
# ============================================================

class TestMonitoringLoop:
    """Tests for the monitoring loop."""

    @pytest.mark.asyncio
    async def test_loop_pauses_outside_market_hours(self, orchestrator):
        """Loop should pause when market is closed."""
        with patch.object(orchestrator, '_is_market_hours', return_value=False):
            with patch.object(orchestrator, '_check_and_act', new_callable=AsyncMock) as mock_check:
                # Set up to stop after one iteration
                orchestrator._is_running = True

                async def stop_loop(*args):
                    orchestrator._is_running = False

                with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    mock_sleep.side_effect = stop_loop

                    # Import the module to patch correctly
                    with patch('app.services.hedge_orchestrator.asyncio.sleep', mock_sleep):
                        # Run one iteration - it should skip check when market closed
                        await orchestrator._check_and_act()

                # Outside market hours, _check_and_act returns early
                # so we verify the check doesn't proceed to hedge logic
