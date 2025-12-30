"""
Margin Monitor - OpenAlgo API Client Service
"""

import httpx
import logging
import time
from typing import List, TypedDict, Optional, Tuple, Any

from app.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache with TTL
_cache: dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 5  # 5 second cache to prevent API hammering


def _get_cached(key: str) -> Optional[Any]:
    """Get value from cache if not expired."""
    if key in _cache:
        timestamp, value = _cache[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
        del _cache[key]
    return None


def _set_cached(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (time.time(), value)


class FundsData(TypedDict):
    """Funds data from OpenAlgo API."""
    used_margin: float
    available_cash: float
    collateral: float
    m2m_realized: float
    m2m_unrealized: float


class PositionData(TypedDict):
    """Position data from OpenAlgo API."""
    symbol: str
    exchange: str
    product: str
    quantity: int
    average_price: float
    ltp: float
    pnl: float


class OpenAlgoError(Exception):
    """Exception for OpenAlgo API errors."""
    pass


class OpenAlgoService:
    """Client for OpenAlgo REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.base_url = base_url or settings.openalgo_base_url
        self.api_key = api_key or settings.openalgo_api_key

    async def get_funds(self) -> FundsData:
        """
        Fetch margin/funds data from OpenAlgo.

        Returns:
            FundsData with margin, cash, collateral, and M2M values.

        Raises:
            OpenAlgoError: If API call fails.

        Note:
            Results are cached for 5 seconds to prevent API hammering.
        """
        # Check cache first
        cached = _get_cached("funds")
        if cached is not None:
            return cached

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/v1/funds",
                    json={"apikey": self.api_key},
                    timeout=10.0
                )
                response.raise_for_status()
                result = response.json()

                if result.get("status") != "success":
                    raise OpenAlgoError(f"API returned error: {result}")

                data = result["data"]

                funds_data: FundsData = {
                    "used_margin": float(data["utiliseddebits"]),
                    "available_cash": float(data["availablecash"]),
                    "collateral": float(data["collateral"]),
                    "m2m_realized": float(data["m2mrealized"]),
                    "m2m_unrealized": float(data["m2munrealized"]),
                }
                _set_cached("funds", funds_data)
                return funds_data

            except httpx.HTTPStatusError as e:
                logger.error(f"OpenAlgo funds API HTTP error: {e}")
                raise OpenAlgoError(f"HTTP error: {e.response.status_code}")
            except httpx.RequestError as e:
                logger.error(f"OpenAlgo funds API request error: {e}")
                raise OpenAlgoError(f"Request failed: {e}")
            except (KeyError, ValueError) as e:
                logger.error(f"OpenAlgo funds API parse error: {e}")
                raise OpenAlgoError(f"Failed to parse response: {e}")

    async def get_positions(self) -> List[PositionData]:
        """
        Fetch all positions from OpenAlgo.

        Returns:
            List of PositionData dictionaries.

        Raises:
            OpenAlgoError: If API call fails.

        Note:
            Results are cached for 5 seconds to prevent API hammering.
        """
        # Check cache first
        cached = _get_cached("positions")
        if cached is not None:
            return cached

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/v1/positionbook",
                    json={"apikey": self.api_key},
                    timeout=10.0
                )
                response.raise_for_status()
                result = response.json()

                if result.get("status") != "success":
                    raise OpenAlgoError(f"API returned error: {result}")

                positions: List[PositionData] = []
                for pos in result.get("data", []):
                    positions.append({
                        "symbol": pos["symbol"],
                        "exchange": pos["exchange"],
                        "product": pos["product"],
                        "quantity": int(pos["quantity"]),
                        "average_price": float(pos["average_price"]),
                        "ltp": float(pos["ltp"]),
                        "pnl": float(pos["pnl"]),
                    })

                _set_cached("positions", positions)
                return positions

            except httpx.HTTPStatusError as e:
                logger.error(f"OpenAlgo positions API HTTP error: {e}")
                raise OpenAlgoError(f"HTTP error: {e.response.status_code}")
            except httpx.RequestError as e:
                logger.error(f"OpenAlgo positions API request error: {e}")
                raise OpenAlgoError(f"Request failed: {e}")
            except (KeyError, ValueError) as e:
                logger.error(f"OpenAlgo positions API parse error: {e}")
                raise OpenAlgoError(f"Failed to parse response: {e}")


# Global service instance
openalgo_service = OpenAlgoService()
