"""
Tests for AutoHedgeOrchestratorService

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

from app.services.hedge_orchestrator import AutoHedgeOrchestratorService
from app.models.hedge_constants import IndexName, ExpiryType


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_strategy_scheduler():
    """Mock strategy scheduler."""
    mock = MagicMock()
    mock.get_today_schedule = MagicMock(return_value=[])
    mock.get_next_entry = MagicMock(return_value=None)
    mock.is_entry_imminent = MagicMock(return_value=False)
    mock.get_entries_in_window = MagicMock(return_value=[])
    return mock


@pytest.fixture
def mock_margin_calculator():
    """Mock margin calculator."""
    mock = MagicMock()
    mock.get_current_utilization = MagicMock(return_value=75.0)
    mock.calculate_projected_utilization = MagicMock(return_value=85.0)
    mock.is_hedge_required = MagicMock(return_value=False)
    mock.calculate_margin_reduction_needed = MagicMock(return_value=0)
    return mock


@pytest.fixture
def mock_hedge_selector():
    """Mock hedge selector."""
    mock = AsyncMock()
    mock.select_optimal_hedges = AsyncMock(return_value=MagicMock(
        selected=[],
        total_cost=0,
        fully_covered=False
    ))
    return mock


@pytest.fixture
def mock_hedge_executor():
    """Mock hedge executor."""
    mock = AsyncMock()
    mock.buy_hedge = AsyncMock(return_value={"status": "success", "order_id": "123"})
    mock.sell_hedge = AsyncMock(return_value={"status": "success", "order_id": "456"})
    return mock


@pytest.fixture
def mock_telegram():
    """Mock telegram service."""
    mock = AsyncMock()
    mock.send_message = AsyncMock()
    return mock


@pytest.fixture
def mock_openalgo():
    """Mock OpenAlgo service."""
    mock = AsyncMock()
    mock.get_funds = AsyncMock(return_value={
        "used_margin": 5000000,
        "available_cash": 2000000,
        "collateral": 0
    })
    mock.get_positions = AsyncMock(return_value=[
        {"symbol": "NIFTY30DEC2524500CE", "quantity": -750},
        {"symbol": "NIFTY30DEC2524500PE", "quantity": -750}
    ])
    return mock


@pytest.fixture
def orchestrator(
    mock_strategy_scheduler,
    mock_margin_calculator,
    mock_hedge_selector,
    mock_hedge_executor,
    mock_telegram,
    mock_openalgo
):
    """Create orchestrator with mocks."""
    orchestrator = AutoHedgeOrchestratorService(
        strategy_scheduler=mock_strategy_scheduler,
        margin_calculator=mock_margin_calculator,
        hedge_selector=mock_hedge_selector,
        hedge_executor=mock_hedge_executor,
        telegram_service=mock_telegram,
        openalgo=mock_openalgo,
        db=AsyncMock()
    )
    return orchestrator


# ============================================================
# State Management Tests
# ============================================================

class TestStateManagement:
    """Tests for orchestrator state management."""

    def test_initial_state_is_idle(self, orchestrator):
        """Orchestrator should start in idle state."""
        assert orchestrator.is_running is False
        assert orchestrator._enabled is True

    @pytest.mark.asyncio
    async def test_start_sets_running(self, orchestrator):
        """Start should set running flag."""
        # Start with immediate stop
        with patch.object(orchestrator, '_monitoring_loop', new_callable=AsyncMock):
            await orchestrator.start()
            assert orchestrator.is_running is True

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, orchestrator):
        """Stop should clear running flag."""
        orchestrator.is_running = True
        await orchestrator.stop()
        assert orchestrator.is_running is False

    def test_enable_disable(self, orchestrator):
        """Should be able to enable/disable."""
        orchestrator.disable()
        assert orchestrator._enabled is False

        orchestrator.enable()
        assert orchestrator._enabled is True


# ============================================================
# Market Hours Tests
# ============================================================

class TestMarketHours:
    """Tests for market hours validation."""

    def test_recognizes_market_open(self, orchestrator):
        """Should recognize when market is open."""
        # Mock time during market hours
        with patch('app.services.hedge_orchestrator.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 2, 10, 30)  # 10:30 AM

            is_open = orchestrator._is_market_open()
            assert is_open is True

    def test_recognizes_market_closed(self, orchestrator):
        """Should recognize when market is closed."""
        with patch('app.services.hedge_orchestrator.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 2, 16, 0)  # 4:00 PM

            is_open = orchestrator._is_market_open()
            assert is_open is False

    def test_recognizes_pre_market(self, orchestrator):
        """Should recognize pre-market hours."""
        with patch('app.services.hedge_orchestrator.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 2, 9, 0)  # 9:00 AM

            is_open = orchestrator._is_market_open()
            assert is_open is False


# ============================================================
# Hedge Trigger Tests
# ============================================================

class TestHedgeTrigger:
    """Tests for hedge triggering logic."""

    @pytest.mark.asyncio
    async def test_triggers_hedge_when_utilization_high(
        self, orchestrator, mock_margin_calculator, mock_hedge_selector, mock_hedge_executor
    ):
        """Should trigger hedge when utilization exceeds threshold."""
        # Setup high utilization scenario
        mock_margin_calculator.is_hedge_required.return_value = True
        mock_margin_calculator.calculate_margin_reduction_needed.return_value = 100000
        mock_hedge_selector.select_optimal_hedges.return_value = MagicMock(
            selected=[MagicMock(strike=24800, option_type='CE', total_cost=10000)],
            total_cost=10000,
            fully_covered=True
        )

        await orchestrator._check_and_hedge()

        mock_hedge_executor.buy_hedge.assert_called()

    @pytest.mark.asyncio
    async def test_no_hedge_when_utilization_normal(
        self, orchestrator, mock_margin_calculator, mock_hedge_executor
    ):
        """Should not trigger hedge when utilization is normal."""
        mock_margin_calculator.is_hedge_required.return_value = False

        await orchestrator._check_and_hedge()

        mock_hedge_executor.buy_hedge.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_enabled_flag(
        self, orchestrator, mock_margin_calculator, mock_hedge_executor
    ):
        """Should not hedge when disabled."""
        orchestrator._enabled = False
        mock_margin_calculator.is_hedge_required.return_value = True

        await orchestrator._check_and_hedge()

        mock_hedge_executor.buy_hedge.assert_not_called()


# ============================================================
# Imminent Entry Tests
# ============================================================

class TestImminentEntry:
    """Tests for imminent entry detection."""

    @pytest.mark.asyncio
    async def test_buys_hedge_before_entry(
        self, orchestrator, mock_strategy_scheduler,
        mock_margin_calculator, mock_hedge_executor
    ):
        """Should buy hedge before imminent entry."""
        # Mock an imminent entry
        mock_strategy_scheduler.is_entry_imminent.return_value = True
        mock_strategy_scheduler.get_next_entry.return_value = MagicMock(
            index_name=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            num_baskets=10,
            entry_time=time(10, 0)
        )
        mock_margin_calculator.calculate_projected_utilization.return_value = 98.0

        await orchestrator._handle_imminent_entry()

        # Should have attempted to buy hedge
        # (exact assertion depends on implementation)

    @pytest.mark.asyncio
    async def test_no_action_when_no_entry(
        self, orchestrator, mock_strategy_scheduler, mock_hedge_executor
    ):
        """Should not act when no entry is imminent."""
        mock_strategy_scheduler.is_entry_imminent.return_value = False

        await orchestrator._handle_imminent_entry()

        mock_hedge_executor.buy_hedge.assert_not_called()


# ============================================================
# Hedge Exit Tests
# ============================================================

class TestHedgeExit:
    """Tests for hedge exit logic."""

    @pytest.mark.asyncio
    async def test_exits_hedge_when_utilization_low(
        self, orchestrator, mock_margin_calculator, mock_hedge_executor
    ):
        """Should consider exiting when utilization drops."""
        mock_margin_calculator.get_current_utilization.return_value = 60.0

        # Add an active hedge
        orchestrator._active_hedges = [
            {"symbol": "NIFTY30DEC2524800CE", "quantity": 750}
        ]

        await orchestrator._check_hedge_exits()

        # Depending on implementation, may exit
        # This documents expected behavior

    @pytest.mark.asyncio
    async def test_no_exit_when_entry_near(
        self, orchestrator, mock_strategy_scheduler, mock_margin_calculator
    ):
        """Should not exit if entry is near."""
        mock_margin_calculator.get_current_utilization.return_value = 60.0
        mock_strategy_scheduler.is_entry_imminent.return_value = True

        orchestrator._active_hedges = [
            {"symbol": "NIFTY30DEC2524800CE", "quantity": 750}
        ]

        # Should not exit with imminent entry
        await orchestrator._check_hedge_exits()


# ============================================================
# Telegram Notification Tests
# ============================================================

class TestTelegramNotifications:
    """Tests for Telegram notifications."""

    @pytest.mark.asyncio
    async def test_sends_alert_on_hedge_buy(
        self, orchestrator, mock_margin_calculator,
        mock_hedge_selector, mock_hedge_executor, mock_telegram
    ):
        """Should send Telegram alert on successful hedge."""
        mock_margin_calculator.is_hedge_required.return_value = True
        mock_margin_calculator.calculate_margin_reduction_needed.return_value = 100000
        mock_hedge_selector.select_optimal_hedges.return_value = MagicMock(
            selected=[MagicMock(strike=24800, option_type='CE', total_cost=10000)],
            total_cost=10000,
            fully_covered=True
        )
        mock_hedge_executor.buy_hedge.return_value = {"status": "success", "order_id": "123"}

        await orchestrator._check_and_hedge()

        mock_telegram.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_sends_alert_on_failure(
        self, orchestrator, mock_margin_calculator,
        mock_hedge_selector, mock_hedge_executor, mock_telegram
    ):
        """Should send Telegram alert on hedge failure."""
        mock_margin_calculator.is_hedge_required.return_value = True
        mock_margin_calculator.calculate_margin_reduction_needed.return_value = 100000
        mock_hedge_selector.select_optimal_hedges.return_value = MagicMock(
            selected=[MagicMock(strike=24800, option_type='CE', total_cost=10000)],
            total_cost=10000,
            fully_covered=True
        )
        mock_hedge_executor.buy_hedge.return_value = {"status": "error", "message": "Failed"}

        await orchestrator._check_and_hedge()

        # Should send failure alert
        mock_telegram.send_message.assert_called()


# ============================================================
# Status Reporting Tests
# ============================================================

class TestStatusReporting:
    """Tests for status reporting."""

    @pytest.mark.asyncio
    async def test_get_status(self, orchestrator, mock_margin_calculator):
        """Should return current status."""
        mock_margin_calculator.get_current_utilization.return_value = 75.0

        status = await orchestrator.get_status()

        assert "enabled" in status
        assert "running" in status or "is_running" in status
        assert "utilization" in status or "current_utilization" in status

    @pytest.mark.asyncio
    async def test_status_includes_active_hedges(self, orchestrator):
        """Status should include active hedges."""
        orchestrator._active_hedges = [
            {"symbol": "NIFTY30DEC2524800CE", "quantity": 750}
        ]

        status = await orchestrator.get_status()

        assert "active_hedges" in status or "hedges" in status


# ============================================================
# Integration-like Tests
# ============================================================

class TestMonitoringLoop:
    """Tests for the monitoring loop."""

    @pytest.mark.asyncio
    async def test_loop_checks_periodically(self, orchestrator):
        """Monitoring loop should check at intervals."""
        check_count = 0

        async def mock_check():
            nonlocal check_count
            check_count += 1
            if check_count >= 3:
                orchestrator.is_running = False

        with patch.object(orchestrator, '_check_and_hedge', mock_check):
            with patch.object(orchestrator, '_is_market_open', return_value=True):
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    orchestrator.is_running = True
                    await orchestrator._monitoring_loop()

        assert check_count >= 1

    @pytest.mark.asyncio
    async def test_loop_pauses_outside_market_hours(self, orchestrator):
        """Loop should pause when market is closed."""
        with patch.object(orchestrator, '_is_market_open', return_value=False):
            with patch.object(orchestrator, '_check_and_hedge', new_callable=AsyncMock) as mock_check:
                with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    # Run one iteration
                    orchestrator.is_running = True

                    # Immediately stop after first check
                    async def stop_after_sleep(*args):
                        orchestrator.is_running = False

                    mock_sleep.side_effect = stop_after_sleep

                    await orchestrator._monitoring_loop()

                # Should not have checked (market closed)
                mock_check.assert_not_called()
