"""
Tests for HedgeExecutorService

Tests cover:
- Order placement (buy/sell hedges)
- Cooldown enforcement
- Symbol building
- Transaction logging
- Dry run mode
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

import pytz

from app.services.hedge_executor import HedgeExecutorService, OrderResult
from app.services.hedge_selector import HedgeCandidate
from app.models.hedge_constants import IndexName, ExpiryType

IST = pytz.timezone('Asia/Kolkata')


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_openalgo():
    """Mock OpenAlgo service."""
    mock = AsyncMock()
    mock.place_order = AsyncMock(return_value={
        "order_id": "12345",
        "orderid": "12345",
        "status": "success"
    })
    return mock


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.flush = AsyncMock()
    mock.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))
    return mock


@pytest.fixture
def mock_telegram():
    """Mock telegram service."""
    mock = AsyncMock()
    mock.send_message = AsyncMock()
    mock.send_hedge_buy_alert = AsyncMock(return_value=123)
    mock.send_hedge_failure_alert = AsyncMock()
    mock.send_hedge_sell_alert = AsyncMock()
    return mock


@pytest.fixture
def executor(mock_openalgo, mock_db_session, mock_telegram):
    """Create HedgeExecutor with mocks."""
    # db is the FIRST positional parameter, no dry_run in constructor
    executor = HedgeExecutorService(
        db=mock_db_session,
        openalgo=mock_openalgo,
        telegram=mock_telegram
    )
    return executor


@pytest.fixture
def sample_candidate():
    """Sample hedge candidate."""
    return HedgeCandidate(
        strike=24800,
        option_type='CE',
        ltp=3.5,
        otm_distance=300,
        estimated_margin_benefit=50000,
        cost_per_lot=262.5,  # 3.5 * 75
        total_cost=26250,    # 262.5 * 100
        total_lots=100,
        mbpr=1.9
    )


# ============================================================
# Symbol Building Tests
# ============================================================

class TestBuildSymbol:
    """Tests for _build_symbol method."""

    def test_nifty_symbol_format(self, executor):
        """Should build correct Nifty symbol."""
        # _build_symbol takes expiry_date (str) not expiry_type
        symbol = executor._build_symbol(
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            strike=24800,
            option_type='CE'
        )

        # Should contain NIFTY, strike, and CE
        assert 'NIFTY' in symbol.upper()
        assert '24800' in symbol
        assert 'CE' in symbol.upper()

    def test_sensex_symbol_format(self, executor):
        """Should build correct Sensex symbol."""
        symbol = executor._build_symbol(
            index=IndexName.SENSEX,
            expiry_date="2025-01-06",
            strike=80000,
            option_type='PE'
        )

        # Should contain SENSEX, strike, and PE
        assert 'SENSEX' in symbol.upper()
        assert '80000' in symbol
        assert 'PE' in symbol.upper()


# ============================================================
# Cooldown Tests
# ============================================================

class TestCooldown:
    """Tests for cooldown enforcement."""

    def test_respects_cooldown(self, executor):
        """Should not execute if within cooldown period."""
        # Set last action to now
        executor._last_action_time = datetime.now(IST)

        # check_cooldown returns True if cooldown is OK, False if still active
        can_execute = executor.check_cooldown()
        assert not can_execute

    def test_allows_after_cooldown(self, executor):
        """Should allow execution after cooldown expires."""
        # Set last action to past cooldown (default is 120s)
        executor._last_action_time = datetime.now(IST) - timedelta(seconds=150)

        can_execute = executor.check_cooldown()
        assert can_execute

    def test_allows_first_action(self, executor):
        """Should allow first action (no last_action_time)."""
        executor._last_action_time = None

        can_execute = executor.check_cooldown()
        assert can_execute


# ============================================================
# Buy Hedge Tests
# ============================================================

class TestBuyHedge:
    """Tests for execute_hedge_buy method."""

    @pytest.mark.asyncio
    async def test_successful_buy(self, executor, sample_candidate, mock_openalgo):
        """Should place buy order successfully."""
        # execute_hedge_buy is the correct method name
        result = await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=False
        )

        # Returns OrderResult dataclass
        assert result.success is True
        assert result.order_id is not None
        mock_openalgo.place_order.assert_called()

    @pytest.mark.asyncio
    async def test_buy_blocked_by_cooldown(self, executor, sample_candidate):
        """Should fail if cooldown active."""
        executor._last_action_time = datetime.now(IST)

        result = await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=False
        )

        assert result.success is False
        assert "cooldown" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_buy_dry_run(self, mock_openalgo, mock_db_session, mock_telegram, sample_candidate):
        """Dry run should not call OpenAlgo."""
        executor = HedgeExecutorService(
            db=mock_db_session,
            openalgo=mock_openalgo,
            telegram=mock_telegram
        )

        # dry_run is passed to the METHOD, not constructor
        result = await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=True  # Pass dry_run here
        )

        assert result.success is True
        assert result.order_id == "DRY_RUN"
        mock_openalgo.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_buy_updates_cooldown(self, executor, sample_candidate):
        """Successful buy should update last_action_time."""
        old_time = executor._last_action_time

        await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=False
        )

        assert executor._last_action_time != old_time
        assert executor._last_action_time is not None


# ============================================================
# Exit Hedge Tests
# ============================================================

class TestExitHedge:
    """Tests for execute_hedge_exit method."""

    @pytest.mark.asyncio
    async def test_exit_not_found(self, executor):
        """Should handle hedge not found."""
        # Mock execute returning None for not found
        executor.db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        result = await executor.execute_hedge_exit(
            hedge_id=999,
            session_id=1,
            trigger_reason="TEST",
            utilization_before=70.0,
            dry_run=False
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()


# ============================================================
# Transaction Logging Tests
# ============================================================

class TestTransactionLogging:
    """Tests for transaction logging."""

    @pytest.mark.asyncio
    async def test_logs_buy_transaction(self, executor, sample_candidate, mock_db_session):
        """Should log transaction to database on buy."""
        await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=False
        )

        # Should have added a transaction
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_api_error(self, executor, sample_candidate, mock_openalgo):
        """Should handle OpenAlgo API errors gracefully."""
        from app.services.openalgo_service import OpenAlgoError
        mock_openalgo.place_order.side_effect = OpenAlgoError("API connection failed")

        result = await executor.execute_hedge_buy(
            session_id=1,
            candidate=sample_candidate,
            index=IndexName.NIFTY,
            expiry_date="2025-01-06",
            num_baskets=10,
            trigger_reason="TEST",
            utilization_before=75.0,
            dry_run=False
        )

        assert result.success is False
        assert result.error_message is not None


# ============================================================
# Daily Cost Tracking Tests
# ============================================================

class TestDailyCostTracking:
    """Tests for daily cost limit enforcement."""

    @pytest.mark.asyncio
    async def test_get_daily_cost(self, executor, mock_db_session):
        """Should query daily hedge cost from database."""
        # Mock the database to return a cost
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar=MagicMock(return_value=25000.0))
        )

        cost = await executor.get_daily_hedge_cost(session_id=1)
        assert cost == 25000.0

    @pytest.mark.asyncio
    async def test_check_daily_cap(self, executor, mock_db_session):
        """Should check if proposed cost exceeds daily cap."""
        # Mock returning current spent as 40000
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar=MagicMock(return_value=40000.0))
        )

        is_allowed, spent, remaining = await executor.check_daily_cost_cap(
            session_id=1,
            proposed_cost=15000  # Would exceed 50K cap
        )

        assert is_allowed is False
        assert spent == 40000.0
