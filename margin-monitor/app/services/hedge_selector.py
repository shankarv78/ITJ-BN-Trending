"""
Auto-Hedge System - Hedge Strike Selector Service

Selects optimal hedge strikes based on Margin Benefit Per Rupee (MBPR).
Finds the most cost-effective hedges that provide required margin reduction.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from app.models.hedge_constants import (
    IndexName, ExpiryType,
    HEDGE_CONFIG, LOT_SIZES, MARGIN_CONSTANTS
)
from app.services.margin_calculator import MarginCalculatorService
from app.services.openalgo_service import OpenAlgoService

logger = logging.getLogger(__name__)


@dataclass
class HedgeCandidate:
    """A potential hedge strike with cost-benefit analysis."""
    strike: int
    option_type: str  # CE or PE
    ltp: float
    otm_distance: int  # Points from ATM
    estimated_margin_benefit: float
    cost_per_lot: float
    total_cost: float
    total_lots: int
    mbpr: float  # Margin Benefit Per Rupee - higher is better

    def __repr__(self) -> str:
        return (
            f"HedgeCandidate({self.strike}{self.option_type}, "
            f"ltp={self.ltp}, otm={self.otm_distance}, "
            f"mbpr={self.mbpr:.2f})"
        )


@dataclass
class HedgeSelection:
    """Result of hedge selection process."""
    candidates: List[HedgeCandidate]
    selected: List[HedgeCandidate]
    total_cost: float
    total_margin_benefit: float
    margin_reduction_needed: float
    fully_covered: bool  # True if selected hedges cover the reduction needed


class HedgeStrikeSelectorService:
    """
    Selects optimal hedge strikes based on Margin Benefit Per Rupee.

    The goal is to minimize hedge cost while achieving required margin reduction.
    Uses a greedy algorithm to select hedges with best MBPR first.

    Core responsibilities:
    - Get spot price for index
    - Find valid hedge candidates (premium and OTM distance in range)
    - Calculate MBPR for each candidate
    - Select optimal hedges to achieve required margin reduction
    """

    def __init__(
        self,
        openalgo: OpenAlgoService = None,
        margin_calculator: MarginCalculatorService = None,
        config = None,
        lot_sizes = None
    ):
        """
        Initialize the hedge selector.

        Args:
            openalgo: OpenAlgo service for market data
            margin_calculator: Margin calculator service
            config: HedgeConfig (uses global default if not provided)
            lot_sizes: LotSizes (uses global default if not provided)
        """
        self.openalgo = openalgo or OpenAlgoService()
        self.margin_calc = margin_calculator or MarginCalculatorService()
        self.config = config or HEDGE_CONFIG
        self.lot_sizes = lot_sizes or LOT_SIZES

    async def get_spot_price(self, index: IndexName) -> float:
        """
        Get current spot price for index.

        Args:
            index: NIFTY or SENSEX

        Returns:
            Current spot price
        """
        # Map index to spot symbol
        symbol_map = {
            IndexName.NIFTY: "NIFTY 50",
            IndexName.SENSEX: "SENSEX"
        }
        symbol = symbol_map.get(index, "NIFTY 50")

        # For now, we'll use the positions to infer spot from ATM strikes
        # In production, this should use the quotes API
        # TODO: Add direct quote API call when available

        positions = await self.openalgo.get_positions()

        if not positions:
            logger.warning(f"[HEDGE_SELECTOR] No positions found, using fallback spot")
            # Fallback values
            return 25000 if index == IndexName.NIFTY else 80000

        # Find ATM strike from existing positions
        index_positions = [
            p for p in positions
            if index.value in p['symbol'].upper()
        ]

        if not index_positions:
            return 25000 if index == IndexName.NIFTY else 80000

        # Parse strike from symbol (e.g., NIFTY30DEC2525000PE -> 25000)
        from app.utils.symbol_parser import parse_option_symbol

        strikes = []
        for pos in index_positions:
            parsed = parse_option_symbol(pos['symbol'])
            if parsed and 'strike_price' in parsed:
                strikes.append(parsed['strike_price'])

        if strikes:
            # Use average of strikes as approximate spot
            return sum(strikes) / len(strikes)

        return 25000 if index == IndexName.NIFTY else 80000

    async def find_hedge_candidates(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        option_types: List[str],  # ['CE', 'PE'] or ['CE'] or ['PE']
        num_baskets: int,
        spot_price: float = None
    ) -> List[HedgeCandidate]:
        """
        Find all valid hedge strike candidates.

        Filters candidates based on:
        - Premium range (min_premium to max_premium)
        - OTM distance (min_otm_distance to max_otm_distance)

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            option_types: List of option types to consider
            num_baskets: Number of baskets
            spot_price: Optional spot price (fetched if not provided)

        Returns:
            List of HedgeCandidate sorted by MBPR (highest first)
        """
        if spot_price is None:
            spot_price = await self.get_spot_price(index)

        logger.info(
            f"[HEDGE_SELECTOR] Finding candidates for {index.value} "
            f"{expiry_type.value}, spot={spot_price:.0f}, "
            f"options={option_types}, baskets={num_baskets}"
        )

        # Get OTM distance limits
        min_otm = self.config.min_otm_distance.get(index.value, 200)
        max_otm = self.config.max_otm_distance.get(index.value, 1000)

        # Calculate lot sizes
        lot_size = self.lot_sizes.get_lot_size(index)
        lots_per_basket = self.lot_sizes.get_lots_per_basket(index)
        total_lots = lots_per_basket * num_baskets
        total_quantity = lot_size * total_lots

        # Estimate margin benefit per side (CE or PE)
        # Total hedge benefit is split between CE and PE
        total_benefit = self.margin_calc.estimate_hedge_margin_benefit(
            index, expiry_type, num_baskets
        )
        per_side_benefit = total_benefit / 2  # CE and PE each contribute half

        candidates: List[HedgeCandidate] = []

        # Generate strike range to check
        strike_step = 50 if index == IndexName.NIFTY else 100

        for opt_type in option_types:
            # Determine strike range based on option type
            if opt_type == 'CE':
                # CE hedges are above spot
                start_strike = int(spot_price + min_otm)
                end_strike = int(spot_price + max_otm)
            else:  # PE
                # PE hedges are below spot
                start_strike = int(spot_price - max_otm)
                end_strike = int(spot_price - min_otm)

            # Round to strike step
            start_strike = (start_strike // strike_step) * strike_step
            end_strike = ((end_strike // strike_step) + 1) * strike_step

            # Check each strike (in production, use option chain API)
            for strike in range(start_strike, end_strike, strike_step):
                # Calculate OTM distance
                if opt_type == 'CE':
                    otm_distance = strike - int(spot_price)
                else:
                    otm_distance = int(spot_price) - strike

                # Skip if outside OTM range
                if otm_distance < min_otm or otm_distance > max_otm:
                    continue

                # Estimate LTP based on OTM distance (simplified model)
                # In production, use actual option chain data
                ltp = self._estimate_ltp(otm_distance, index, expiry_type)

                # Skip if outside premium range
                if not (self.config.min_premium <= ltp <= self.config.max_premium):
                    continue

                # Calculate costs
                cost_per_lot = ltp * lot_size
                total_cost = cost_per_lot * total_lots

                # Calculate MBPR (Margin Benefit Per Rupee)
                mbpr = per_side_benefit / total_cost if total_cost > 0 else 0

                candidates.append(HedgeCandidate(
                    strike=strike,
                    option_type=opt_type,
                    ltp=ltp,
                    otm_distance=otm_distance,
                    estimated_margin_benefit=per_side_benefit,
                    cost_per_lot=cost_per_lot,
                    total_cost=total_cost,
                    total_lots=total_lots,
                    mbpr=mbpr
                ))

        # Sort by MBPR (highest first)
        candidates.sort(key=lambda x: x.mbpr, reverse=True)

        logger.info(f"[HEDGE_SELECTOR] Found {len(candidates)} candidates")

        return candidates

    def _estimate_ltp(
        self,
        otm_distance: int,
        index: IndexName,
        expiry_type: ExpiryType
    ) -> float:
        """
        Estimate LTP based on OTM distance (simplified model).

        In production, this should be replaced with actual option chain data.

        Args:
            otm_distance: Points from ATM
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE

        Returns:
            Estimated LTP
        """
        # Simplified decay model based on OTM distance
        # More OTM = lower premium

        base_premium = 10.0  # ATM approximate

        # Decay rate based on expiry
        decay_rate = {
            ExpiryType.ZERO_DTE: 0.015,  # Faster decay for 0DTE
            ExpiryType.ONE_DTE: 0.012,
            ExpiryType.TWO_DTE: 0.010,
        }.get(expiry_type, 0.012)

        # Scale by index volatility
        if index == IndexName.SENSEX:
            decay_rate *= 0.8  # SENSEX less volatile

        estimated_ltp = base_premium * (1 - decay_rate * otm_distance / 10)

        return max(0.05, min(estimated_ltp, 20.0))  # Clamp to realistic range

    async def select_optimal_hedges(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        margin_reduction_needed: float,
        short_positions: List[Dict[str, Any]],
        num_baskets: int
    ) -> HedgeSelection:
        """
        Select optimal hedges to achieve required margin reduction with minimum cost.

        Uses a greedy algorithm:
        1. Find all valid candidates
        2. Sort by MBPR (highest first)
        3. Select hedges until reduction target is met

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            margin_reduction_needed: Target margin reduction in INR
            short_positions: Current short positions (to determine which sides need hedging)
            num_baskets: Number of baskets

        Returns:
            HedgeSelection with selected candidates
        """
        # Determine which sides need hedging based on short positions
        ce_shorts = sum(1 for p in short_positions if 'CE' in p.get('symbol', '').upper())
        pe_shorts = sum(1 for p in short_positions if 'PE' in p.get('symbol', '').upper())

        option_types = []
        if ce_shorts > 0:
            option_types.append('CE')
        if pe_shorts > 0:
            option_types.append('PE')

        if not option_types:
            logger.warning("[HEDGE_SELECTOR] No short positions found, cannot determine hedge side")
            return HedgeSelection(
                candidates=[],
                selected=[],
                total_cost=0,
                total_margin_benefit=0,
                margin_reduction_needed=margin_reduction_needed,
                fully_covered=False
            )

        # Find candidates
        candidates = await self.find_hedge_candidates(
            index=index,
            expiry_type=expiry_type,
            option_types=option_types,
            num_baskets=num_baskets
        )

        if not candidates:
            logger.warning("[HEDGE_SELECTOR] No valid candidates found")
            return HedgeSelection(
                candidates=[],
                selected=[],
                total_cost=0,
                total_margin_benefit=0,
                margin_reduction_needed=margin_reduction_needed,
                fully_covered=False
            )

        # Greedy selection: pick best MBPR until reduction achieved
        selected: List[HedgeCandidate] = []
        total_benefit = 0.0
        total_cost = 0.0
        selected_types: set = set()

        for candidate in candidates:
            if total_benefit >= margin_reduction_needed:
                break

            # Only one hedge per side (CE or PE)
            if candidate.option_type in selected_types:
                continue

            selected.append(candidate)
            selected_types.add(candidate.option_type)
            total_benefit += candidate.estimated_margin_benefit
            total_cost += candidate.total_cost

        fully_covered = total_benefit >= margin_reduction_needed

        logger.info(
            f"[HEDGE_SELECTOR] Selected {len(selected)} hedges, "
            f"cost=₹{total_cost:,.0f}, benefit=₹{total_benefit:,.0f}, "
            f"needed=₹{margin_reduction_needed:,.0f}, covered={fully_covered}"
        )

        return HedgeSelection(
            candidates=candidates,
            selected=selected,
            total_cost=total_cost,
            total_margin_benefit=total_benefit,
            margin_reduction_needed=margin_reduction_needed,
            fully_covered=fully_covered
        )

    async def find_best_single_hedge(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        option_type: str,
        num_baskets: int
    ) -> Optional[HedgeCandidate]:
        """
        Find the best single hedge for a given option type.

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            option_type: 'CE' or 'PE'
            num_baskets: Number of baskets

        Returns:
            Best HedgeCandidate or None if no valid candidates
        """
        candidates = await self.find_hedge_candidates(
            index=index,
            expiry_type=expiry_type,
            option_types=[option_type],
            num_baskets=num_baskets
        )

        if candidates:
            return candidates[0]  # Already sorted by MBPR

        return None
