"""
Portfolio Manager Client Service

Queries Portfolio Manager (PM) on port 5002 to get trend-following positions.
These positions should be excluded from intraday margin calculations.
"""

import httpx
import logging
from typing import TypedDict, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# PM endpoint configuration
PM_BASE_URL = "http://localhost:5002"
PM_TIMEOUT = 10.0  # seconds


class PMPositionData(TypedDict):
    """Position data from Portfolio Manager."""
    instrument: str
    lots: int
    entry_price: float
    current_stop: float
    expiry: Optional[str]
    strike: Optional[int]
    rollover_count: int
    rollover_status: str


@dataclass
class ExcludedMarginResult:
    """Result of excluded margin calculation."""
    total_excluded: float
    breakdown: Dict[str, float]  # instrument -> margin
    positions: Dict[str, Any]    # raw position data from PM
    error: Optional[str] = None


# Approximate margin per lot for trend-following instruments
# These are estimates based on actual SPAN margin requirements (Jan 2026)
MARGIN_PER_LOT = {
    "BANK_NIFTY": 130000,    # ~₹1.3L per lot for BN futures/synthetic
    "GOLD_MINI": 105000,     # ~₹1.05L per lot for Gold Mini futures
    "SILVER_MINI": 385000,   # ~₹3.85L per lot for Silver Mini futures (verified Jan 2026)
    "NIFTY": 100000,         # ~₹1L per lot for Nifty futures/synthetic
}


class PMClient:
    """Client for Portfolio Manager REST API."""

    def __init__(self, base_url: str = PM_BASE_URL):
        self.base_url = base_url

    async def get_positions(self) -> Dict[str, PMPositionData]:
        """
        Fetch positions from Portfolio Manager.

        Returns:
            Dictionary of position_id -> position data
        """
        try:
            async with httpx.AsyncClient(timeout=PM_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/positions")
                response.raise_for_status()
                data = response.json()
                return data.get("positions", {})
        except httpx.TimeoutException:
            logger.warning("PM request timed out")
            return {}
        except httpx.HTTPStatusError as e:
            logger.warning(f"PM returned error: {e.response.status_code}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to fetch PM positions: {e}")
            return {}

    async def is_healthy(self) -> bool:
        """Check if PM is running and healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                data = response.json()
                return data.get("status") == "healthy"
        except Exception:
            return False

    async def get_excluded_margin(self) -> ExcludedMarginResult:
        """
        Calculate total margin that should be excluded from intraday calculations.

        This queries PM for trend-following positions and estimates their margin.

        Returns:
            ExcludedMarginResult with total and breakdown by instrument.
        """
        try:
            positions = await self.get_positions()

            if not positions:
                return ExcludedMarginResult(
                    total_excluded=0.0,
                    breakdown={},
                    positions={},
                    error=None
                )

            breakdown: Dict[str, float] = {}
            total = 0.0

            for pos_id, pos_data in positions.items():
                instrument = pos_data.get("instrument", "UNKNOWN")
                lots = pos_data.get("lots", 0)

                # Get margin per lot for this instrument
                margin_per_lot = MARGIN_PER_LOT.get(instrument, 50000)  # Default 50K
                estimated_margin = lots * margin_per_lot

                breakdown[instrument] = breakdown.get(instrument, 0) + estimated_margin
                total += estimated_margin

                logger.debug(
                    f"PM position {pos_id}: {instrument} x {lots} lots = "
                    f"₹{estimated_margin:,.0f} margin"
                )

            logger.info(
                f"PM excluded margin: ₹{total:,.0f} from {len(positions)} positions"
            )

            return ExcludedMarginResult(
                total_excluded=total,
                breakdown=breakdown,
                positions=positions,
                error=None
            )

        except Exception as e:
            logger.error(f"Error calculating excluded margin: {e}")
            return ExcludedMarginResult(
                total_excluded=0.0,
                breakdown={},
                positions={},
                error=str(e)
            )


# Global instance
pm_client = PMClient()
