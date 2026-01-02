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
        Get current spot price for index using quotes API.

        Falls back to position-based inference if quotes API unavailable.

        Args:
            index: NIFTY or SENSEX

        Returns:
            Current spot price
        """
        # Map index to spot symbol and exchange
        spot_config = {
            IndexName.NIFTY: {"symbol": "NIFTY 50", "exchange": "NSE"},
            IndexName.SENSEX: {"symbol": "SENSEX", "exchange": "BSE"}
        }
        config = spot_config.get(index, spot_config[IndexName.NIFTY])

        # Try quotes API first (preferred method)
        try:
            quotes = await self.openalgo.get_quotes(
                symbol=config["symbol"],
                exchange=config["exchange"]
            )
            if quotes and "ltp" in quotes:
                ltp = float(quotes["ltp"])
                logger.info(f"[HEDGE_SELECTOR] Got {index.value} spot from quotes API: {ltp}")
                return ltp
        except Exception as e:
            logger.warning(f"[HEDGE_SELECTOR] Quotes API failed for {index.value}: {e}")

        # Fallback: Infer from positions
        try:
            positions = await self.openalgo.get_positions()
            if positions:
                # Find positions for this index
                index_positions = [
                    p for p in positions
                    if index.value in p['symbol'].upper()
                ]

                if index_positions:
                    # Parse strike from symbol (e.g., NIFTY30DEC2525000PE -> 25000)
                    from app.utils.symbol_parser import parse_option_symbol

                    strikes = []
                    for pos in index_positions:
                        parsed = parse_option_symbol(pos['symbol'])
                        if parsed and 'strike_price' in parsed:
                            strikes.append(parsed['strike_price'])

                    if strikes:
                        spot = sum(strikes) / len(strikes)
                        logger.info(
                            f"[HEDGE_SELECTOR] Inferred {index.value} spot from positions: {spot}"
                        )
                        return spot
        except Exception as e:
            logger.warning(f"[HEDGE_SELECTOR] Position inference failed: {e}")

        # Last resort: fallback values
        fallback = 25000 if index == IndexName.NIFTY else 80000
        logger.warning(f"[HEDGE_SELECTOR] Using fallback spot for {index.value}: {fallback}")
        return fallback

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

        Uses option chain API for real LTPs when available,
        falls back to estimation model if API unavailable.

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

        # Estimate margin benefit per side (CE or PE)
        # Total hedge benefit is split between CE and PE
        total_benefit = self.margin_calc.estimate_hedge_margin_benefit(
            index, expiry_type, num_baskets
        )
        per_side_benefit = total_benefit / 2  # CE and PE each contribute half

        # Try to get real LTPs from option chain API
        option_chain_data = await self._fetch_option_chain(index, expiry_type)
        use_real_ltp = len(option_chain_data) > 0

        if use_real_ltp:
            logger.info(f"[HEDGE_SELECTOR] Using real LTPs from option chain ({len(option_chain_data)} strikes)")
        else:
            logger.warning(f"[HEDGE_SELECTOR] Using estimated LTPs (option chain unavailable)")

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

            for strike in range(start_strike, end_strike, strike_step):
                # Calculate OTM distance
                if opt_type == 'CE':
                    otm_distance = strike - int(spot_price)
                else:
                    otm_distance = int(spot_price) - strike

                # Skip if outside OTM range
                if otm_distance < min_otm or otm_distance > max_otm:
                    continue

                # Get LTP (real or estimated)
                if use_real_ltp:
                    ltp = self._get_ltp_from_chain(option_chain_data, strike, opt_type)
                    if ltp is None:
                        # Strike not in chain, skip or estimate
                        ltp = self._estimate_ltp(otm_distance, index, expiry_type)
                else:
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

    async def _fetch_option_chain(
        self,
        index: IndexName,
        expiry_type: ExpiryType
    ) -> Dict[str, Dict[str, float]]:
        """
        Fetch option chain data from API.

        Returns:
            Dict mapping strike -> {CE: ltp, PE: ltp}
        """
        try:
            # Map index to option chain symbol
            symbol_map = {
                IndexName.NIFTY: ("NIFTY", "NFO"),
                IndexName.SENSEX: ("SENSEX", "BFO")
            }
            symbol, exchange = symbol_map.get(index, ("NIFTY", "NFO"))

            # Calculate expiry date based on expiry_type
            from datetime import date, timedelta
            today = date.today()
            if expiry_type == ExpiryType.ZERO_DTE:
                expiry = today
            elif expiry_type == ExpiryType.ONE_DTE:
                expiry = today + timedelta(days=1)
            else:
                expiry = today + timedelta(days=2)

            expiry_str = expiry.strftime("%Y-%m-%d")

            # Fetch from API
            chain_data = await self.openalgo.get_option_chain(
                symbol=symbol,
                exchange=exchange,
                expiry=expiry_str
            )

            # Parse into strike -> {CE: ltp, PE: ltp} format
            result: Dict[str, Dict[str, float]] = {}

            for entry in chain_data:
                strike = entry.get("strike") or entry.get("strike_price")
                if strike is None:
                    continue

                strike = int(strike)
                if strike not in result:
                    result[strike] = {}

                # Handle different response formats
                if "ce_ltp" in entry:
                    result[strike]["CE"] = float(entry["ce_ltp"])
                if "pe_ltp" in entry:
                    result[strike]["PE"] = float(entry["pe_ltp"])
                if "ltp" in entry and "option_type" in entry:
                    result[strike][entry["option_type"]] = float(entry["ltp"])

            return result

        except Exception as e:
            logger.warning(f"[HEDGE_SELECTOR] Failed to fetch option chain: {e}")
            return {}

    def _get_ltp_from_chain(
        self,
        chain: Dict[str, Dict[str, float]],
        strike: int,
        option_type: str
    ) -> Optional[float]:
        """
        Get LTP for a specific strike and option type from chain data.

        Args:
            chain: Option chain data {strike -> {CE: ltp, PE: ltp}}
            strike: Strike price
            option_type: 'CE' or 'PE'

        Returns:
            LTP or None if not found
        """
        strike_data = chain.get(strike)
        if strike_data:
            return strike_data.get(option_type)
        return None

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
        num_baskets: int,
        hedge_capacity: Optional[Dict[str, Any]] = None,
        allocation_mode: str = 'proportional'  # 'proportional' or 'equal'
    ) -> HedgeSelection:
        """
        Select optimal hedges to achieve required margin reduction with minimum cost.

        Uses a greedy algorithm:
        1. Find all valid candidates
        2. Sort by MBPR (highest first)
        3. Select hedges until reduction target is met

        IMPORTANT: Respects hedge capacity limits - buying more hedges than sold qty
        provides NO margin benefit (just adds naked long premium cost).

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            margin_reduction_needed: Target margin reduction in INR
            short_positions: Current short positions (to determine which sides need hedging)
            num_baskets: Number of baskets
            hedge_capacity: Optional dict with remaining_ce_capacity/remaining_pe_capacity
            allocation_mode: 'proportional' (based on short qty) or 'equal' (50/50)

        Returns:
            HedgeSelection with selected candidates
        """
        # Calculate short QUANTITIES (not just position count) for proportional hedging
        ce_short_qty = sum(
            abs(p.get('quantity', 0)) for p in short_positions
            if 'CE' in p.get('symbol', '').upper()
        )
        pe_short_qty = sum(
            abs(p.get('quantity', 0)) for p in short_positions
            if 'PE' in p.get('symbol', '').upper()
        )

        total_short_qty = ce_short_qty + pe_short_qty

        # Determine allocation ratio based on mode
        if allocation_mode == 'equal' or total_short_qty == 0:
            # Equal allocation for proactive hedging (before strategy entry)
            ce_ratio = 0.5
            pe_ratio = 0.5
            logger.info(
                f"[HEDGE_SELECTOR] EQUAL allocation mode: CE={ce_short_qty}, PE={pe_short_qty}, "
                f"using 50%:50% split"
            )
        else:
            # Proportional allocation for reactive hedging (critical utilization)
            ce_ratio = ce_short_qty / total_short_qty
            pe_ratio = pe_short_qty / total_short_qty
            logger.info(
                f"[HEDGE_SELECTOR] PROPORTIONAL allocation: CE={ce_short_qty}, PE={pe_short_qty}, "
                f"ratio CE:PE = {ce_ratio:.1%}:{pe_ratio:.1%}"
            )

        option_types = []
        if ce_short_qty > 0:
            option_types.append('CE')
        if pe_short_qty > 0:
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

        # Check if we're at capacity (hedge qty already >= sold qty)
        if hedge_capacity:
            if hedge_capacity.get('is_fully_hedged'):
                logger.warning(
                    "[HEDGE_SELECTOR] Fully hedged! "
                    f"CE: {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}, "
                    f"PE: {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']} - "
                    "no additional hedge benefit possible"
                )
                return HedgeSelection(
                    candidates=[],
                    selected=[],
                    total_cost=0,
                    total_margin_benefit=0,
                    margin_reduction_needed=margin_reduction_needed,
                    fully_covered=False
                )

            # Filter out option types at capacity
            if hedge_capacity.get('remaining_ce_capacity', 0) == 0 and 'CE' in option_types:
                logger.info("[HEDGE_SELECTOR] CE at capacity, skipping CE hedges")
                option_types.remove('CE')
            if hedge_capacity.get('remaining_pe_capacity', 0) == 0 and 'PE' in option_types:
                logger.info("[HEDGE_SELECTOR] PE at capacity, skipping PE hedges")
                option_types.remove('PE')

            if not option_types:
                logger.warning("[HEDGE_SELECTOR] Both CE and PE at hedge capacity")
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

        # Proportional selection: allocate hedges based on short qty ratio
        # If CE:PE ratio is 25%:75%, allocate margin reduction budget accordingly
        selected: List[HedgeCandidate] = []
        total_benefit = 0.0
        total_cost = 0.0

        # Calculate target benefit per side (proportional to exposure)
        ce_target = margin_reduction_needed * ce_ratio if 'CE' in option_types else 0
        pe_target = margin_reduction_needed * pe_ratio if 'PE' in option_types else 0

        ce_benefit = 0.0
        pe_benefit = 0.0

        logger.info(
            f"[HEDGE_SELECTOR] Proportional targets: CE=₹{ce_target:,.0f} ({ce_ratio:.0%}), "
            f"PE=₹{pe_target:,.0f} ({pe_ratio:.0%})"
        )

        # Sort candidates by MBPR and select proportionally
        for candidate in candidates:
            if total_benefit >= margin_reduction_needed:
                break

            opt_type = candidate.option_type

            # Check if this side still needs more hedges
            if opt_type == 'CE':
                if ce_benefit >= ce_target:
                    continue  # CE already has enough
                ce_benefit += candidate.estimated_margin_benefit
            else:  # PE
                if pe_benefit >= pe_target:
                    continue  # PE already has enough
                pe_benefit += candidate.estimated_margin_benefit

            selected.append(candidate)
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
