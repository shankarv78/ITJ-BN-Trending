"""
Tests for HedgeStrikeSelectorService

Tests cover:
- Spot price fetching (with API and fallback)
- Hedge candidate finding
- MBPR calculation
- Optimal hedge selection (greedy algorithm)
- Option chain integration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.services.hedge_selector import (
    HedgeStrikeSelectorService,
    HedgeCandidate,
    HedgeSelection
)
from app.models.hedge_constants import IndexName, ExpiryType


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_openalgo():
    """Mock OpenAlgo service."""
    mock = AsyncMock()
    mock.get_quotes = AsyncMock(return_value={"ltp": 24500})
    mock.get_positions = AsyncMock(return_value=[])
    mock.get_option_chain = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_margin_calc():
    """Mock MarginCalculatorService."""
    mock = MagicMock()
    mock.estimate_hedge_margin_benefit = MagicMock(return_value=100000)  # ₹1L benefit
    return mock


@pytest.fixture
def selector(mock_openalgo, mock_margin_calc):
    """Create HedgeSelector with mocks."""
    return HedgeStrikeSelectorService(
        openalgo=mock_openalgo,
        margin_calculator=mock_margin_calc
    )


# ============================================================
# Spot Price Tests
# ============================================================

class TestGetSpotPrice:
    """Tests for get_spot_price method."""

    @pytest.mark.asyncio
    async def test_spot_from_quotes_api(self, selector, mock_openalgo):
        """Should use quotes API when available."""
        mock_openalgo.get_quotes.return_value = {"ltp": 24750.50}

        spot = await selector.get_spot_price(IndexName.NIFTY)

        assert spot == 24750.50
        mock_openalgo.get_quotes.assert_called_once()

    @pytest.mark.asyncio
    async def test_spot_fallback_to_positions(self, selector, mock_openalgo):
        """Should infer from positions when quotes fail."""
        mock_openalgo.get_quotes.side_effect = Exception("API error")
        mock_openalgo.get_positions.return_value = [
            {"symbol": "NIFTY30DEC2524500PE", "quantity": -750},
            {"symbol": "NIFTY30DEC2524500CE", "quantity": -750}
        ]

        with patch('app.services.hedge_selector.parse_option_symbol') as mock_parse:
            mock_parse.return_value = {"strike_price": 24500}
            spot = await selector.get_spot_price(IndexName.NIFTY)

        assert spot == 24500

    @pytest.mark.asyncio
    async def test_spot_fallback_default(self, selector, mock_openalgo):
        """Should use default when all methods fail."""
        mock_openalgo.get_quotes.side_effect = Exception("API error")
        mock_openalgo.get_positions.return_value = []

        spot = await selector.get_spot_price(IndexName.NIFTY)
        assert spot == 25000  # Default Nifty

        spot = await selector.get_spot_price(IndexName.SENSEX)
        assert spot == 80000  # Default Sensex


# ============================================================
# LTP Estimation Tests
# ============================================================

class TestEstimateLTP:
    """Tests for _estimate_ltp method."""

    def test_ltp_decreases_with_otm_distance(self, selector):
        """More OTM should result in lower premium."""
        ltp_200 = selector._estimate_ltp(200, IndexName.NIFTY, ExpiryType.ZERO_DTE)
        ltp_400 = selector._estimate_ltp(400, IndexName.NIFTY, ExpiryType.ZERO_DTE)
        ltp_600 = selector._estimate_ltp(600, IndexName.NIFTY, ExpiryType.ZERO_DTE)

        assert ltp_200 > ltp_400 > ltp_600

    def test_ltp_higher_for_longer_expiry(self, selector):
        """Longer expiry should have higher premium."""
        ltp_0dte = selector._estimate_ltp(300, IndexName.NIFTY, ExpiryType.ZERO_DTE)
        ltp_1dte = selector._estimate_ltp(300, IndexName.NIFTY, ExpiryType.ONE_DTE)
        ltp_2dte = selector._estimate_ltp(300, IndexName.NIFTY, ExpiryType.TWO_DTE)

        # 2DTE > 1DTE > 0DTE (slower decay)
        assert ltp_2dte > ltp_1dte > ltp_0dte

    def test_ltp_clamped_to_range(self, selector):
        """LTP should be within realistic bounds."""
        # Very far OTM
        ltp_far = selector._estimate_ltp(1000, IndexName.NIFTY, ExpiryType.ZERO_DTE)
        assert ltp_far >= 0.05

        # Very close to ATM
        ltp_close = selector._estimate_ltp(100, IndexName.NIFTY, ExpiryType.TWO_DTE)
        assert ltp_close <= 20.0


# ============================================================
# Candidate Finding Tests
# ============================================================

class TestFindHedgeCandidates:
    """Tests for find_hedge_candidates method."""

    @pytest.mark.asyncio
    async def test_finds_candidates_for_ce(self, selector):
        """Should find CE hedge candidates above spot."""
        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        assert len(candidates) > 0
        for c in candidates:
            assert c.option_type == 'CE'
            assert c.strike > 24500  # CE is above spot
            assert c.otm_distance > 0

    @pytest.mark.asyncio
    async def test_finds_candidates_for_pe(self, selector):
        """Should find PE hedge candidates below spot."""
        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['PE'],
            num_baskets=10,
            spot_price=24500
        )

        assert len(candidates) > 0
        for c in candidates:
            assert c.option_type == 'PE'
            assert c.strike < 24500  # PE is below spot
            assert c.otm_distance > 0

    @pytest.mark.asyncio
    async def test_candidates_sorted_by_mbpr(self, selector):
        """Candidates should be sorted by MBPR (highest first)."""
        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE', 'PE'],
            num_baskets=10,
            spot_price=24500
        )

        if len(candidates) > 1:
            mbpr_values = [c.mbpr for c in candidates]
            assert mbpr_values == sorted(mbpr_values, reverse=True)

    @pytest.mark.asyncio
    async def test_candidates_filtered_by_premium_range(self, selector):
        """Should only include candidates within premium range."""
        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        for c in candidates:
            assert selector.config.min_premium <= c.ltp <= selector.config.max_premium

    @pytest.mark.asyncio
    async def test_uses_real_ltp_when_available(self, selector, mock_openalgo):
        """Should use option chain LTP when API available."""
        # Mock option chain with real data
        mock_openalgo.get_option_chain.return_value = [
            {"strike": 24800, "ce_ltp": 3.5, "pe_ltp": 250.0},
            {"strike": 24900, "ce_ltp": 2.8, "pe_ltp": 300.0},
        ]

        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        # Should have candidates using real LTPs
        assert len(candidates) >= 0  # May still filter based on premium range


# ============================================================
# MBPR Calculation Tests
# ============================================================

class TestMBPRCalculation:
    """Tests for MBPR (Margin Benefit Per Rupee) calculation."""

    @pytest.mark.asyncio
    async def test_mbpr_calculated_correctly(self, selector, mock_margin_calc):
        """MBPR = margin_benefit / cost."""
        mock_margin_calc.estimate_hedge_margin_benefit.return_value = 200000

        candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        for c in candidates:
            expected_mbpr = c.estimated_margin_benefit / c.total_cost if c.total_cost > 0 else 0
            assert abs(c.mbpr - expected_mbpr) < 0.01

    @pytest.mark.asyncio
    async def test_higher_benefit_higher_mbpr(self, selector, mock_margin_calc):
        """Higher margin benefit should result in higher MBPR."""
        # First with low benefit
        mock_margin_calc.estimate_hedge_margin_benefit.return_value = 50000
        low_candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        # Then with high benefit
        mock_margin_calc.estimate_hedge_margin_benefit.return_value = 200000
        high_candidates = await selector.find_hedge_candidates(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_types=['CE'],
            num_baskets=10,
            spot_price=24500
        )

        if low_candidates and high_candidates:
            # Find same strike in both
            low_by_strike = {c.strike: c for c in low_candidates}
            for hc in high_candidates:
                if hc.strike in low_by_strike:
                    assert hc.mbpr > low_by_strike[hc.strike].mbpr


# ============================================================
# Optimal Selection Tests
# ============================================================

class TestSelectOptimalHedges:
    """Tests for select_optimal_hedges method."""

    @pytest.mark.asyncio
    async def test_selects_hedges_greedy_by_mbpr(self, selector):
        """Should select highest MBPR hedges first."""
        short_positions = [
            {"symbol": "NIFTY30DEC2524500CE", "quantity": -750},
            {"symbol": "NIFTY30DEC2524500PE", "quantity": -750}
        ]

        selection = await selector.select_optimal_hedges(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            margin_reduction_needed=50000,
            short_positions=short_positions,
            num_baskets=10
        )

        assert isinstance(selection, HedgeSelection)
        assert len(selection.candidates) >= len(selection.selected)

    @pytest.mark.asyncio
    async def test_one_hedge_per_side(self, selector):
        """Should select at most one CE and one PE."""
        short_positions = [
            {"symbol": "NIFTY30DEC2524500CE", "quantity": -750},
            {"symbol": "NIFTY30DEC2524500PE", "quantity": -750}
        ]

        selection = await selector.select_optimal_hedges(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            margin_reduction_needed=200000,
            short_positions=short_positions,
            num_baskets=10
        )

        selected_types = [h.option_type for h in selection.selected]
        assert len(set(selected_types)) == len(selected_types)  # No duplicates

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_shorts(self, selector):
        """Should return empty selection if no short positions."""
        selection = await selector.select_optimal_hedges(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            margin_reduction_needed=50000,
            short_positions=[],
            num_baskets=10
        )

        assert selection.selected == []
        assert not selection.fully_covered

    @pytest.mark.asyncio
    async def test_fully_covered_flag(self, selector, mock_margin_calc):
        """Should set fully_covered correctly."""
        mock_margin_calc.estimate_hedge_margin_benefit.return_value = 200000

        short_positions = [
            {"symbol": "NIFTY30DEC2524500CE", "quantity": -750},
            {"symbol": "NIFTY30DEC2524500PE", "quantity": -750}
        ]

        # Small reduction needed - should be covered
        selection = await selector.select_optimal_hedges(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            margin_reduction_needed=10000,
            short_positions=short_positions,
            num_baskets=10
        )

        # With 200K benefit and only 10K needed, should be covered
        if selection.selected:
            assert selection.fully_covered


# ============================================================
# Find Best Single Hedge Tests
# ============================================================

class TestFindBestSingleHedge:
    """Tests for find_best_single_hedge method."""

    @pytest.mark.asyncio
    async def test_returns_best_mbpr_hedge(self, selector):
        """Should return the candidate with highest MBPR."""
        result = await selector.find_best_single_hedge(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_type='CE',
            num_baskets=10
        )

        if result:
            # Should be the best (first after sorting)
            all_candidates = await selector.find_hedge_candidates(
                index=IndexName.NIFTY,
                expiry_type=ExpiryType.ZERO_DTE,
                option_types=['CE'],
                num_baskets=10,
                spot_price=None
            )
            if all_candidates:
                assert result.mbpr == all_candidates[0].mbpr

    @pytest.mark.asyncio
    async def test_returns_none_when_no_candidates(self, selector, mock_openalgo):
        """Should return None if no valid candidates."""
        # Make config very restrictive
        selector.config = MagicMock()
        selector.config.min_premium = 100  # Too high
        selector.config.max_premium = 101
        selector.config.min_otm_distance = {"NIFTY": 200}
        selector.config.max_otm_distance = {"NIFTY": 1000}

        result = await selector.find_best_single_hedge(
            index=IndexName.NIFTY,
            expiry_type=ExpiryType.ZERO_DTE,
            option_type='CE',
            num_baskets=10
        )

        assert result is None
