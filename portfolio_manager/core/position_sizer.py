"""
Tom Basso Position Sizing

BASE ENTRY uses 2 constraints (matching Pine Script):
1. Risk Control (Lot-R)
2. Margin Control (Lot-M)
Final = FLOOR(MIN(Lot-R, Lot-M))

PYRAMID uses 3 constraints:
A. Margin Safety
B. Discipline (50% of base)
C. Risk Budget (50% of excess profit)
Final = FLOOR(MIN(A, B, C))

Note: Volatility constraint (Lot-V) is calculated for reference/logging
but NOT used in base entry sizing to match Pine Script behavior.
"""
import logging
import math
from typing import Tuple
from core.models import (
    Signal, InstrumentConfig, TomBassoConstraints,
    SignalType, InstrumentType
)

logger = logging.getLogger(__name__)

class TomBassoPositionSizer:
    """Calculates position size using Tom Basso's 3-constraint method"""

    def __init__(self, instrument_config: InstrumentConfig, test_mode: bool = False):
        """
        Initialize position sizer for specific instrument

        Args:
            instrument_config: Configuration for the instrument
            test_mode: If True, enforce minimum 1 lot for pyramids (for testing with small positions)
        """
        self.config = instrument_config
        self.lot_size = instrument_config.lot_size
        self.point_value = instrument_config.point_value
        self.margin_per_lot = instrument_config.margin_per_lot
        self.test_mode = test_mode

    def calculate_base_entry_size(
        self,
        signal: Signal,
        equity: float,
        available_margin: float
    ) -> TomBassoConstraints:
        """
        Calculate position size for base entry using 3 constraints

        Args:
            signal: Entry signal with price, stop, ATR, etc.
            equity: Current portfolio equity
            available_margin: Available margin in Rs

        Returns:
            TomBassoConstraints with all three lot calculations
        """
        if signal.signal_type != SignalType.BASE_ENTRY:
            raise ValueError(f"Expected BASE_ENTRY signal, got {signal.signal_type}")

        entry_price = signal.price
        stop_price = signal.stop
        atr = signal.atr
        er = signal.er

        # CONSTRAINT 1: Risk-based lots (Lot-R)
        # Formula: (Equity × Risk%) / (Entry - Stop) / Point_Value
        # Multiplied by ER for efficiency scaling
        risk_percent = self.config.initial_risk_percent
        risk_amount = equity * (risk_percent / 100.0)

        risk_per_point = entry_price - stop_price
        if risk_per_point <= 0:
            logger.warning(f"Invalid risk: entry={entry_price}, stop={stop_price}")
            return TomBassoConstraints(0, 0, 0, 0, "invalid_risk")

        risk_per_lot = risk_per_point * self.point_value
        lot_r = (risk_amount / risk_per_lot) * er

        logger.debug(f"Lot-R: Risk={risk_amount:.0f}, RiskPerLot={risk_per_lot:.0f}, "
                    f"ER={er:.2f} → {lot_r:.2f} lots")

        # VOLATILITY (Lot-V) - Calculated for reference only, NOT used in base entry
        # This matches Pine Script which only uses Risk + Margin for base entries
        vol_percent = self.config.initial_vol_percent
        vol_budget = equity * (vol_percent / 100.0)

        vol_per_lot = atr * self.point_value
        if vol_per_lot <= 0:
            logger.warning(f"Invalid volatility: ATR={atr}")
            lot_v = 0
        else:
            lot_v = vol_budget / vol_per_lot

        logger.debug(f"Lot-V (reference only): VolBudget={vol_budget:.0f}, ATR={atr:.2f}, "
                    f"VolPerLot={vol_per_lot:.0f} → {lot_v:.2f} lots")

        # CONSTRAINT 3: Margin-based lots (Lot-M)
        # Formula: Available_Margin / Margin_Per_Lot
        lot_m = available_margin / self.margin_per_lot if self.margin_per_lot > 0 else 0

        logger.debug(f"Lot-M: AvailMargin={available_margin:.0f}, "
                    f"MarginPerLot={self.margin_per_lot:.0f} → {lot_m:.2f} lots")

        # FINAL: Minimum of Risk and Margin only (matching Pine Script)
        # Volatility constraint NOT used for base entries
        final_lots = math.floor(min(lot_r, lot_m))
        final_lots = max(0, final_lots)  # Ensure non-negative

        # Determine limiting factor (only risk or margin for base entry)
        if lot_r <= lot_m:
            limiter = "risk"
        else:
            limiter = "margin"

        logger.info(f"Position size: {final_lots} lots (limited by {limiter})")

        return TomBassoConstraints(
            lot_r=lot_r,
            lot_v=lot_v,
            lot_m=lot_m,
            final_lots=final_lots,
            limiter=limiter
        )

    def calculate_pyramid_size(
        self,
        signal: Signal,
        equity: float,
        available_margin: float,
        base_position_size: int,
        profit_after_base_risk: float
    ) -> TomBassoConstraints:
        """
        Calculate pyramid size using triple constraint

        Args:
            signal: Pyramid signal
            equity: Current equity
            available_margin: Available margin
            base_position_size: Size of initial entry (lots)
            profit_after_base_risk: Profit beyond base risk coverage

        Returns:
            TomBassoConstraints for pyramid
        """
        if signal.signal_type != SignalType.PYRAMID:
            raise ValueError(f"Expected PYRAMID signal, got {signal.signal_type}")

        entry_price = signal.price
        stop_price = signal.stop

        # CONSTRAINT A: Margin safety
        lot_a = math.floor(available_margin / self.margin_per_lot)

        # CONSTRAINT B: Discipline (50% of base)
        lot_b = math.floor(base_position_size * 0.5)

        # CONSTRAINT C: Risk budget (50% of excess profit)
        available_risk_budget = profit_after_base_risk * 0.5
        risk_per_point = entry_price - stop_price

        if risk_per_point <= 0:
            logger.warning(f"Invalid pyramid risk: entry={entry_price}, stop={stop_price}")
            return TomBassoConstraints(lot_a, lot_b, 0, 0, "invalid_risk")

        risk_per_lot = risk_per_point * self.point_value
        lot_c = math.floor(available_risk_budget / risk_per_lot) if risk_per_lot > 0 else 0

        logger.debug(f"Pyramid constraints: A={lot_a}, B={lot_b}, C={lot_c}")

        # Final: minimum of all three
        final_lots = math.floor(min(lot_a, lot_b, lot_c))
        final_lots = max(0, final_lots)

        # Determine limiter
        min_constraint = min(lot_a, lot_b, lot_c)
        if min_constraint == lot_a:
            limiter = "margin"
        elif min_constraint == lot_b:
            limiter = "50%_rule"
        else:
            limiter = "risk_budget"

        # Test mode: Enforce minimum 1 lot for pyramid testing (when margin allows)
        if self.test_mode and final_lots == 0 and lot_a >= 1:
            final_lots = 1
            limiter = "test_mode_min"
            logger.info(f"[TEST MODE] Enforcing minimum 1 lot for pyramid (was 0 due to {limiter})")

        logger.info(f"Pyramid size: {final_lots} lots (limited by {limiter})")

        return TomBassoConstraints(
            lot_r=lot_a,  # Reusing fields for A,B,C
            lot_v=lot_b,
            lot_m=lot_c,
            final_lots=final_lots,
            limiter=limiter
        )

    def calculate_peel_off_size(
        self,
        position_risk: float,
        position_vol: float,
        equity: float,
        current_lots: int
    ) -> Tuple[int, str]:
        """
        Calculate how many lots to peel off if position too large

        Args:
            position_risk: Current position risk in Rs
            position_vol: Current position volatility in Rs
            equity: Current equity
            current_lots: Current position size in lots

        Returns:
            (lots_to_peel, reason)
        """
        ongoing_risk_pct = self.config.ongoing_risk_percent
        ongoing_vol_pct = self.config.ongoing_vol_percent

        # Check if position exceeds ongoing limits
        risk_pct = (position_risk / equity) * 100
        vol_pct = (position_vol / equity) * 100

        lots_to_peel = 0
        reason = None

        # Calculate peel for risk
        if risk_pct > ongoing_risk_pct:
            target_risk = equity * (ongoing_risk_pct / 100)
            excess_risk = position_risk - target_risk
            risk_per_lot = position_risk / current_lots
            risk_peel = math.ceil(excess_risk / risk_per_lot)
            lots_to_peel = max(lots_to_peel, risk_peel)
            reason = f"risk_{risk_pct:.1f}%_exceeds_{ongoing_risk_pct}%"

        # Calculate peel for volatility
        if vol_pct > ongoing_vol_pct:
            target_vol = equity * (ongoing_vol_pct / 100)
            excess_vol = position_vol - target_vol
            vol_per_lot = position_vol / current_lots
            vol_peel = math.ceil(excess_vol / vol_per_lot)
            lots_to_peel = max(lots_to_peel, vol_peel)
            if reason:
                reason += f"_and_vol_{vol_pct:.1f}%"
            else:
                reason = f"vol_{vol_pct:.1f}%_exceeds_{ongoing_vol_pct}%"

        # Ensure we don't peel more than we have
        lots_to_peel = min(lots_to_peel, current_lots)

        if lots_to_peel > 0:
            logger.info(f"Peel-off required: {lots_to_peel} lots ({reason})")

        return lots_to_peel, reason or ""
