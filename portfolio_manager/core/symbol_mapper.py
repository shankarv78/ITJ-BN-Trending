"""
Symbol Mapper - Translate generic instrument names to OpenAlgo format

Supports:
- GOLD_MINI → GOLDM[DDMMMYY]FUT (simple futures)
- COPPER → COPPER[DDMMMYY]FUT (simple futures)
- SILVER_MINI → SILVERM[DDMMMYY]FUT (simple futures, bimonthly)
- BANK_NIFTY → BANKNIFTY[DDMMMYY][Strike]PE/CE (synthetic futures - 2 legs)

Features:
- Dynamic expiry calculation
- ATM strike calculation (round to 500, prefer 1000s)
- Holiday-aware expiry adjustment
- Rollover detection
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Tuple
from enum import Enum

# Import InstrumentType from models to avoid duplication
from core.models import InstrumentType

logger = logging.getLogger(__name__)


class ExchangeCode(Enum):
    """Exchange codes for OpenAlgo"""
    MCX = "MCX"
    NFO = "NFO"
    NSE = "NSE"


@dataclass
class OrderLeg:
    """
    Single order leg for execution.

    For simple futures: 1 leg (BUY/SELL FUT)
    For synthetic futures: 2 legs (PE + CE)
    """
    symbol: str           # OpenAlgo format symbol
    exchange: str         # MCX, NFO, etc.
    action: str           # BUY or SELL
    leg_type: str         # "FUT", "PE", "CE"
    lot_multiplier: int = 1  # Usually 1, can be adjusted

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'exchange': self.exchange,
            'action': self.action,
            'leg_type': self.leg_type,
            'lot_multiplier': self.lot_multiplier
        }


@dataclass
class TranslatedSymbol:
    """
    Result of symbol translation.

    Contains all information needed to place orders.
    """
    instrument: str           # Generic name (GOLD_MINI, BANK_NIFTY)
    exchange: str             # Exchange code
    symbols: List[str]        # OpenAlgo format symbols (1 for futures, 2 for synthetic)
    expiry_date: date         # Contract expiry date
    is_synthetic: bool = False  # True for Bank Nifty synthetic futures
    atm_strike: Optional[int] = None  # ATM strike (for options)
    order_legs: List[OrderLeg] = field(default_factory=list)  # Pre-built order legs

    def to_dict(self) -> dict:
        return {
            'instrument': self.instrument,
            'exchange': self.exchange,
            'symbols': self.symbols,
            'expiry_date': self.expiry_date.isoformat(),
            'is_synthetic': self.is_synthetic,
            'atm_strike': self.atm_strike,
            'order_legs': [leg.to_dict() for leg in self.order_legs]
        }


class SymbolMapper:
    """
    Translate generic instrument names to OpenAlgo format.

    Key Features:
    - GOLD_MINI → Simple futures (1 order)
    - BANK_NIFTY → Synthetic futures (2 orders: PE sell + CE buy)
    - Dynamic ATM strike calculation
    - Expiry-aware symbol generation

    Usage:
        mapper = SymbolMapper(price_provider=openalgo.get_quote)
        translated = mapper.translate("BANK_NIFTY", action="BUY", current_price=50347)
        # Returns TranslatedSymbol with 2 symbols and pre-built order legs
    """

    # Strike step sizes
    STRIKE_STEP_SIZE = {
        'BANK_NIFTY': 500,  # Round to nearest 500
    }

    # Lot sizes for quantity calculation
    LOT_SIZES = {
        'GOLD_MINI': 100,
        'BANK_NIFTY': 30,  # Current lot size (Dec 2025 onwards)
        'COPPER': 2500,    # 2500 kg per lot
        'SILVER_MINI': 5,  # 5 kg per lot (MCX Silver Mini)
    }

    def __init__(self, expiry_calendar=None, holiday_calendar=None, price_provider=None):
        """
        Initialize SymbolMapper.

        Args:
            expiry_calendar: ExpiryCalendar instance for expiry calculation
            holiday_calendar: HolidayCalendar instance for holiday checking
            price_provider: Callable to get current price (signature: (symbol: str) -> float)
        """
        self.expiry_calendar = expiry_calendar
        self.holiday_calendar = holiday_calendar
        self.price_provider = price_provider

        # Lazy import to avoid circular dependency
        if self.expiry_calendar is None:
            from core.expiry_calendar import ExpiryCalendar
            self.expiry_calendar = ExpiryCalendar(holiday_calendar=holiday_calendar)

    def translate(
        self,
        instrument: str,
        action: str = "BUY",
        current_price: Optional[float] = None,
        reference_date: Optional[date] = None
    ) -> TranslatedSymbol:
        """
        Translate generic instrument to OpenAlgo format.

        Args:
            instrument: Generic name ("GOLD_MINI" or "BANK_NIFTY")
            action: Trade direction ("BUY" for long entry, "SELL" for exit)
            current_price: Current market price (required for Bank Nifty ATM)
            reference_date: Reference date for expiry (default: today)

        Returns:
            TranslatedSymbol with OpenAlgo-formatted symbols and order legs
        """
        if instrument == "GOLD_MINI":
            return self._translate_gold_mini(action, reference_date)
        elif instrument == "COPPER":
            return self._translate_copper(action, reference_date)
        elif instrument == "SILVER_MINI":
            return self._translate_silver_mini(action, reference_date)
        elif instrument == "BANK_NIFTY":
            return self._translate_bank_nifty(action, current_price, reference_date)
        else:
            raise ValueError(f"Unknown instrument: {instrument}")

    def _translate_gold_mini(
        self,
        action: str,
        reference_date: Optional[date] = None
    ) -> TranslatedSymbol:
        """
        Translate GOLD_MINI to OpenAlgo futures format.

        Format: GOLDM[DDMMMYY]FUT
        Example: GOLDM05JAN26FUT
        """
        # Get expiry date (with rollover check)
        expiry = self.expiry_calendar.get_expiry_after_rollover("GOLD_MINI", reference_date)

        # Format: GOLDM[DDMMMYY]FUT
        date_str = expiry.strftime('%d%b%y').upper()
        symbol = f"GOLDM{date_str}FUT"

        # Build order leg
        order_leg = OrderLeg(
            symbol=symbol,
            exchange=ExchangeCode.MCX.value,
            action=action,
            leg_type="FUT"
        )

        logger.info(
            f"[SYMBOL] Gold Mini translated: expiry={expiry}, symbol={symbol}, action={action}"
        )

        return TranslatedSymbol(
            instrument="GOLD_MINI",
            exchange=ExchangeCode.MCX.value,
            symbols=[symbol],
            expiry_date=expiry,
            is_synthetic=False,
            order_legs=[order_leg]
        )

    def _translate_copper(
        self,
        action: str,
        reference_date: Optional[date] = None
    ) -> TranslatedSymbol:
        """
        Translate COPPER to OpenAlgo futures format.

        Format: COPPER[DDMMMYY]FUT
        Example: COPPER31DEC25FUT
        """
        # Get expiry date (with rollover check)
        expiry = self.expiry_calendar.get_expiry_after_rollover("COPPER", reference_date)

        # Format: COPPER[DDMMMYY]FUT
        date_str = expiry.strftime('%d%b%y').upper()
        symbol = f"COPPER{date_str}FUT"

        # Build order leg
        order_leg = OrderLeg(
            symbol=symbol,
            exchange=ExchangeCode.MCX.value,
            action=action,
            leg_type="FUT"
        )

        logger.info(
            f"[SYMBOL] Copper translated: expiry={expiry}, symbol={symbol}, action={action}"
        )

        return TranslatedSymbol(
            instrument="COPPER",
            exchange=ExchangeCode.MCX.value,
            symbols=[symbol],
            expiry_date=expiry,
            is_synthetic=False,
            order_legs=[order_leg]
        )

    def _translate_silver_mini(
        self,
        action: str,
        reference_date: Optional[date] = None
    ) -> TranslatedSymbol:
        """
        Translate SILVER_MINI to OpenAlgo futures format.

        Format: SILVERM[DDMMMYY]FUT
        Example: SILVERM27FEB26FUT

        Note: Silver Mini has bimonthly expiry (Feb, Apr, Jun, Aug, Nov)
        and expires on the last day of the contract month.
        """
        # Get expiry date (with rollover check)
        expiry = self.expiry_calendar.get_expiry_after_rollover("SILVER_MINI", reference_date)

        # Format: SILVERM[DDMMMYY]FUT (day-month-year format)
        date_str = expiry.strftime('%d%b%y').upper()
        symbol = f"SILVERM{date_str}FUT"

        # Build order leg
        order_leg = OrderLeg(
            symbol=symbol,
            exchange=ExchangeCode.MCX.value,
            action=action,
            leg_type="FUT"
        )

        logger.info(
            f"[SYMBOL] Silver Mini translated: expiry={expiry}, symbol={symbol}, action={action}"
        )

        return TranslatedSymbol(
            instrument="SILVER_MINI",
            exchange=ExchangeCode.MCX.value,
            symbols=[symbol],
            expiry_date=expiry,
            is_synthetic=False,
            order_legs=[order_leg]
        )

    def _translate_bank_nifty(
        self,
        action: str,
        current_price: Optional[float] = None,
        reference_date: Optional[date] = None
    ) -> TranslatedSymbol:
        """
        Translate BANK_NIFTY to OpenAlgo synthetic futures format.

        Synthetic Future = ATM PE Sell + ATM CE Buy
        Format: BANKNIFTY[DDMMMYY][Strike]PE/CE
        Example: BANKNIFTY26DEC2450500PE, BANKNIFTY26DEC2450500CE

        Entry Long: SELL PE, BUY CE
        Exit Long: BUY PE, SELL CE
        """
        # Get current price if not provided
        if current_price is None:
            if self.price_provider:
                try:
                    current_price = self.price_provider("BANK_NIFTY")
                    if current_price is None or current_price <= 0:
                        raise ValueError(f"Price provider returned invalid price: {current_price}")
                except Exception as e:
                    raise ValueError(f"Failed to fetch Bank Nifty price: {e}")
            else:
                raise ValueError("Current price required for Bank Nifty ATM calculation. "
                               "Provide current_price parameter or configure price_provider.")

        # Get expiry date (with rollover check)
        expiry = self.expiry_calendar.get_expiry_after_rollover("BANK_NIFTY", reference_date)

        # Calculate ATM strike (round to nearest 500, prefer 1000s)
        atm_strike = self.calculate_atm_strike(current_price, step=500)

        # Format: BANKNIFTY[DDMMMYY][Strike]PE/CE (Zerodha format)
        # Example: BANKNIFTY30DEC2560000PE for Dec 30, 2025 expiry at strike 60000
        date_str = expiry.strftime('%d%b%y').upper()
        pe_symbol = f"BANKNIFTY{date_str}{atm_strike}PE"
        ce_symbol = f"BANKNIFTY{date_str}{atm_strike}CE"

        # Build order legs based on action
        # Entry Long: SELL PE, BUY CE
        # Exit Long (SELL): BUY PE, SELL CE
        if action == "BUY":
            # Long entry: SELL PE + BUY CE
            pe_action = "SELL"
            ce_action = "BUY"
        else:
            # Exit (SELL): BUY PE + SELL CE
            pe_action = "BUY"
            ce_action = "SELL"

        pe_leg = OrderLeg(
            symbol=pe_symbol,
            exchange=ExchangeCode.NFO.value,
            action=pe_action,
            leg_type="PE"
        )

        ce_leg = OrderLeg(
            symbol=ce_symbol,
            exchange=ExchangeCode.NFO.value,
            action=ce_action,
            leg_type="CE"
        )

        logger.info(
            f"[SYMBOL] Bank Nifty translated: price={current_price:.2f}, "
            f"strike={atm_strike}, expiry={expiry}, "
            f"PE={pe_symbol}({pe_action}), CE={ce_symbol}({ce_action})"
        )

        return TranslatedSymbol(
            instrument="BANK_NIFTY",
            exchange=ExchangeCode.NFO.value,
            symbols=[pe_symbol, ce_symbol],
            expiry_date=expiry,
            is_synthetic=True,
            atm_strike=atm_strike,
            order_legs=[pe_leg, ce_leg]
        )

    def calculate_atm_strike(self, price: float, step: int = 500) -> int:
        """
        Calculate ATM strike price.

        Rules:
        - Round to nearest 'step' (500 for Bank Nifty)
        - When equidistant, prefer 1000s over 500s

        Examples (step=500):
        - 50347 → 50500 (nearest 500)
        - 50750 → 51000 (prefer 1000 over 500)
        - 50250 → 50000 (prefer 1000 when equidistant)
        - 50500 → 50500 (exact 500)
        - 51000 → 51000 (exact 1000)
        """
        if price <= 0:
            raise ValueError(f"Invalid price: {price}")

        # Round to nearest step
        lower = int(price // step) * step
        upper = lower + step

        # Calculate distances
        dist_lower = price - lower
        dist_upper = upper - price

        # If equidistant, prefer 1000s
        if abs(dist_lower - dist_upper) < 0.01:  # Essentially equal
            # Choose the one that's a multiple of 1000
            if lower % 1000 == 0:
                return lower
            else:
                return upper

        # Otherwise, pick the closest
        if dist_lower < dist_upper:
            nearest = lower
        else:
            nearest = upper

        # Final preference for 1000s: if both are equally good, prefer 1000
        # This applies when the price is exactly at a 500 level
        # e.g., price=50500 → could go to 50000 or 51000, but 50500 is exact, keep it

        return nearest

    def get_order_legs_for_exit(self, translated: TranslatedSymbol) -> List[OrderLeg]:
        """
        Get order legs for exiting a position.

        Reverses the entry actions:
        - Entry SELL PE → Exit BUY PE
        - Entry BUY CE → Exit SELL CE

        Args:
            translated: TranslatedSymbol from entry

        Returns:
            List of OrderLeg for exit
        """
        exit_legs = []

        for leg in translated.order_legs:
            exit_action = "SELL" if leg.action == "BUY" else "BUY"
            exit_leg = OrderLeg(
                symbol=leg.symbol,
                exchange=leg.exchange,
                action=exit_action,
                leg_type=leg.leg_type,
                lot_multiplier=leg.lot_multiplier
            )
            exit_legs.append(exit_leg)

        return exit_legs

    def get_lot_size(self, instrument: str) -> int:
        """Get lot size for an instrument."""
        return self.LOT_SIZES.get(instrument, 1)

    def calculate_quantity(self, instrument: str, lots: int) -> int:
        """Calculate total quantity from lots."""
        lot_size = self.get_lot_size(instrument)
        return lots * lot_size


# Global instance
_symbol_mapper: Optional[SymbolMapper] = None


def get_symbol_mapper() -> Optional[SymbolMapper]:
    """Get global SymbolMapper instance."""
    return _symbol_mapper


def init_symbol_mapper(
    expiry_calendar=None,
    holiday_calendar=None,
    price_provider=None
) -> SymbolMapper:
    """Initialize global SymbolMapper."""
    global _symbol_mapper
    _symbol_mapper = SymbolMapper(
        expiry_calendar=expiry_calendar,
        holiday_calendar=holiday_calendar,
        price_provider=price_provider
    )
    return _symbol_mapper
