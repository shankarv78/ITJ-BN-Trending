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

                # Log available fields for debugging
                logger.debug(f"OpenAlgo funds API response fields: {list(data.keys())}")

                # Flexible field mapping - try multiple possible field names
                def get_field(d: dict, *keys: str, default: float = 0.0) -> float:
                    """Try multiple field names and return first match."""
                    for key in keys:
                        if key in d:
                            return float(d[key])
                    logger.warning(f"None of {keys} found in response. Available: {list(d.keys())}")
                    return default

                funds_data: FundsData = {
                    "used_margin": get_field(data, "utiliseddebits", "utilised_debits", "used_margin", "usedMargin", "margin_used"),
                    "available_cash": get_field(data, "availablecash", "available_cash", "availableCash", "cash"),
                    "collateral": get_field(data, "collateral", "Collateral"),
                    "m2m_realized": get_field(data, "m2mrealized", "m2m_realized", "m2mRealized", "realizedPnl"),
                    "m2m_unrealized": get_field(data, "m2munrealized", "m2m_unrealized", "m2mUnrealized", "unrealizedPnl"),
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
                logger.error(f"OpenAlgo funds API parse error: {e}. Response: {result}")
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

                # Flexible field getter for positions
                def get_pos_field(p: dict, *keys: str, default: Any = None) -> Any:
                    for key in keys:
                        if key in p:
                            return p[key]
                    return default

                for pos in result.get("data", []):
                    # Log first position's fields for debugging
                    if not positions:
                        logger.debug(f"OpenAlgo position fields: {list(pos.keys())}")

                    positions.append({
                        "symbol": get_pos_field(pos, "symbol", "tradingsymbol", "Symbol") or "",
                        "exchange": get_pos_field(pos, "exchange", "Exchange") or "NFO",
                        "product": get_pos_field(pos, "product", "producttype", "Product") or "NRML",
                        "quantity": int(get_pos_field(pos, "quantity", "netqty", "Quantity") or 0),
                        "average_price": float(get_pos_field(pos, "average_price", "averageprice", "avgprice") or 0),
                        "ltp": float(get_pos_field(pos, "ltp", "lastprice", "LTP") or 0),
                        "pnl": float(get_pos_field(pos, "pnl", "unrealizedpnl", "PnL") or 0),
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
                logger.error(f"OpenAlgo positions API parse error: {e}. Response: {result}")
                raise OpenAlgoError(f"Failed to parse response: {e}")


# Global service instance
openalgo_service = OpenAlgoService()
