"""
Auto-Hedge System - Constants and Configuration

Contains:
- Margin constants per basket for each index/expiry combination
- Hedge configuration thresholds
- Lot sizes and other trading constants
"""

from dataclasses import dataclass, field
from typing import Dict
from enum import Enum


class IndexName(str, Enum):
    """Supported indices."""
    NIFTY = "NIFTY"
    SENSEX = "SENSEX"


class ExpiryType(str, Enum):
    """Option expiry types."""
    ZERO_DTE = "0DTE"
    ONE_DTE = "1DTE"
    TWO_DTE = "2DTE"


@dataclass
class MarginConstants:
    """
    Margin requirements per basket for each index/expiry combination.
    All values in INR.

    These are empirical values based on observed margin requirements.
    Updated periodically based on actual trading data.
    """

    # ================================================================
    # SENSEX (0DTE) - Thursday Expiry
    # ================================================================
    SENSEX_0DTE_WITHOUT_HEDGE: float = 366666.67    # ~₹3.67L per basket
    SENSEX_0DTE_WITH_HEDGE: float = 160000.00       # ~₹1.60L per basket
    SENSEX_0DTE_HEDGE_BENEFIT_PCT: float = 0.56     # 56% reduction

    # ================================================================
    # NIFTY (0DTE) - Tuesday Expiry
    # ================================================================
    NIFTY_0DTE_WITHOUT_HEDGE: float = 433333.33     # ~₹4.33L per basket
    NIFTY_0DTE_WITH_HEDGE: float = 186666.67        # ~₹1.87L per basket
    NIFTY_0DTE_HEDGE_BENEFIT_PCT: float = 0.57      # 57% reduction

    # ================================================================
    # NIFTY (1DTE) - Monday (for Tuesday expiry)
    # ================================================================
    NIFTY_1DTE_WITHOUT_HEDGE: float = 320000.00     # ~₹3.20L per basket
    NIFTY_1DTE_WITH_HEDGE: float = 140000.00        # ~₹1.40L per basket
    NIFTY_1DTE_HEDGE_BENEFIT_PCT: float = 0.56      # 56% reduction

    # ================================================================
    # NIFTY (2DTE) - Friday (for Tuesday expiry)
    # ================================================================
    NIFTY_2DTE_WITHOUT_HEDGE: float = 320000.00     # ~₹3.20L per basket
    NIFTY_2DTE_WITH_HEDGE: float = 140000.00        # ~₹1.40L per basket
    NIFTY_2DTE_HEDGE_BENEFIT_PCT: float = 0.56      # 56% reduction

    def get_margin(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        has_hedge: bool,
        num_baskets: int = 1
    ) -> float:
        """
        Get margin requirement for specified configuration.

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            has_hedge: Whether hedges are in place
            num_baskets: Number of baskets (default 1)

        Returns:
            Total margin requirement in INR
        """
        hedge_key = "WITH_HEDGE" if has_hedge else "WITHOUT_HEDGE"
        attr_name = f"{index.value}_{expiry_type.value}_{hedge_key}"

        try:
            per_basket = getattr(self, attr_name)
        except AttributeError:
            # Fallback for non-standard expiry types
            if "1DTE" in expiry_type.value or "2DTE" in expiry_type.value:
                fallback_name = f"{index.value}_1DTE_{hedge_key}"
                per_basket = getattr(self, fallback_name)
            else:
                raise ValueError(f"Unknown margin constant: {attr_name}")

        return per_basket * num_baskets

    def get_hedge_benefit(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        num_baskets: int = 1
    ) -> float:
        """
        Calculate margin benefit from adding hedges.

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            num_baskets: Number of baskets

        Returns:
            Margin reduction in INR
        """
        without_hedge = self.get_margin(index, expiry_type, has_hedge=False, num_baskets=num_baskets)
        with_hedge = self.get_margin(index, expiry_type, has_hedge=True, num_baskets=num_baskets)
        return without_hedge - with_hedge


@dataclass
class HedgeConfig:
    """
    Configuration for auto-hedge system.

    Thresholds, timing, and safety parameters.
    """

    # ================================================================
    # THRESHOLDS
    # ================================================================

    # Buy hedge if projected utilization exceeds this
    entry_trigger_pct: float = 95.0

    # Target utilization after buying hedge
    entry_target_pct: float = 85.0

    # Consider exiting hedge if utilization drops below this
    exit_trigger_pct: float = 70.0

    # ================================================================
    # TIMING
    # ================================================================

    # Check for hedge requirements this many minutes before entry
    lookahead_minutes: int = 5

    # Don't exit hedges if an entry is within this many minutes
    exit_buffer_minutes: int = 15

    # ================================================================
    # HEDGE STRIKE SELECTION
    # ================================================================

    # Premium range for hedge selection (INR)
    min_premium: float = 2.0
    max_premium: float = 6.0

    # OTM distance limits (points from ATM)
    min_otm_distance: Dict[str, int] = field(default_factory=lambda: {
        "NIFTY": 200,
        "SENSEX": 500
    })
    max_otm_distance: Dict[str, int] = field(default_factory=lambda: {
        "NIFTY": 1000,
        "SENSEX": 2500
    })

    # ================================================================
    # SAFETY
    # ================================================================

    # Maximum daily spend on hedges (INR)
    max_hedge_cost_per_day: float = 50000.0

    # Minimum time between hedge actions (seconds)
    cooldown_seconds: int = 120

    # Minimum hedge value to bother selling (INR)
    min_exit_value: float = 0.50

    # ================================================================
    # ORDER EXECUTION
    # ================================================================

    # Price buffer for limit orders (added to LTP for buys)
    limit_order_buffer: float = 0.10

    # Order timeout in seconds
    order_timeout_seconds: int = 30


@dataclass
class LotSizes:
    """Lot sizes for supported indices."""
    NIFTY: int = 75
    SENSEX: int = 10

    # Baskets typically have multiple lots
    NIFTY_LOTS_PER_BASKET: int = 1
    SENSEX_LOTS_PER_BASKET: int = 10  # 10 lots × 10 = 100 qty per basket

    def get_lot_size(self, index: IndexName) -> int:
        """Get lot size for index."""
        return getattr(self, index.value)

    def get_lots_per_basket(self, index: IndexName) -> int:
        """Get lots per basket for index."""
        return getattr(self, f"{index.value}_LOTS_PER_BASKET")

    def get_quantity(self, index: IndexName, num_baskets: int) -> int:
        """Get total quantity for given baskets."""
        lot_size = self.get_lot_size(index)
        lots_per_basket = self.get_lots_per_basket(index)
        return lot_size * lots_per_basket * num_baskets

    def get_lot_size_from_symbol(self, symbol: str) -> int:
        """
        Infer lot size from trading symbol.

        Args:
            symbol: Trading symbol like 'NIFTY02JAN2524000PE' or 'SENSEX02JAN2584000CE'

        Returns:
            Lot size (75 for Nifty, 10 for Sensex)
        """
        symbol_upper = symbol.upper()
        if symbol_upper.startswith("SENSEX"):
            return self.SENSEX
        else:
            # Default to NIFTY lot size (75) for NIFTY and any unknown symbols
            return self.NIFTY


# ================================================================
# EXCHANGE MAPPINGS
# ================================================================

INDEX_TO_EXCHANGE = {
    IndexName.NIFTY: "NFO",
    IndexName.SENSEX: "BFO"
}


# ================================================================
# DAY SCHEDULE MAPPINGS
# ================================================================

DAY_TO_INDEX_EXPIRY = {
    "Monday": (IndexName.NIFTY, ExpiryType.ONE_DTE),
    "Tuesday": (IndexName.NIFTY, ExpiryType.ZERO_DTE),
    "Wednesday": None,  # No trading
    "Thursday": (IndexName.SENSEX, ExpiryType.ZERO_DTE),
    "Friday": (IndexName.NIFTY, ExpiryType.TWO_DTE),
}


# ================================================================
# GLOBAL INSTANCES
# ================================================================

MARGIN_CONSTANTS = MarginConstants()
HEDGE_CONFIG = HedgeConfig()
LOT_SIZES = LotSizes()
