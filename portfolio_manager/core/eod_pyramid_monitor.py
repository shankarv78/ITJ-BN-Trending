"""
EOD Pyramid Monitor - Price-Based Pyramid Detection During EOD Window

This module monitors price during the EOD (End-of-Day) window and determines
if a pyramid entry should be executed, using PM's own position data instead
of relying on TradingView's position_status.

Why this exists:
- TradingView sends EOD_MONITOR signals with position_status, but it doesn't
  know PM's actual positions (only its own strategy.position_size)
- Pyramid signals from TradingView fire at bar close (00:00), but MCX closes at 23:55
- PM needs to independently check pyramid conditions using its own database

Pyramid Conditions (from Pine Script logic):
1. 1R Gate: price > entry_price + initial_risk (entry - stop)
2. ATR Spacing: price >= last_pyramid_price + (ATR * threshold)
3. Profit Gate: Total P&L on instrument > 0
4. Max Pyramids: pyramid_count < max_pyramids (5 for BN, 3 for Gold)

Usage:
    monitor = EODPyramidMonitor(portfolio_state, config)

    # During EOD window, call with current price
    result = monitor.check_pyramid_eligibility(instrument, current_price, atr)

    if result.should_pyramid:
        # Execute pyramid via engine
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List

from core.config import PortfolioConfig, get_instrument_config
from core.portfolio_state import PortfolioStateManager
from core.models import InstrumentType

logger = logging.getLogger(__name__)


@dataclass
class PyramidCheckResult:
    """Result of pyramid eligibility check"""
    should_pyramid: bool
    instrument: str
    current_price: float

    # Gate statuses
    has_position: bool = False
    position_count: int = 0
    max_pyramids: int = 5

    # 1R Gate
    one_r_gate_passed: bool = False
    entry_price: float = 0.0
    initial_risk: float = 0.0
    price_move_from_entry: float = 0.0
    price_move_in_r: float = 0.0

    # ATR Spacing
    atr_spacing_passed: bool = False
    last_pyramid_price: float = 0.0
    price_move_from_last: float = 0.0
    atr_moves: float = 0.0
    atr_threshold: float = 1.0

    # Profit Gate
    profit_gate_passed: bool = False
    total_pnl: float = 0.0

    # Rejection reason
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/API"""
        return {
            'should_pyramid': self.should_pyramid,
            'instrument': self.instrument,
            'current_price': self.current_price,
            'has_position': self.has_position,
            'position_count': self.position_count,
            'max_pyramids': self.max_pyramids,
            'one_r_gate': {
                'passed': self.one_r_gate_passed,
                'entry_price': self.entry_price,
                'initial_risk': self.initial_risk,
                'price_move': self.price_move_from_entry,
                'r_multiple': self.price_move_in_r
            },
            'atr_spacing': {
                'passed': self.atr_spacing_passed,
                'last_pyramid_price': self.last_pyramid_price,
                'price_move': self.price_move_from_last,
                'atr_moves': self.atr_moves,
                'threshold': self.atr_threshold
            },
            'profit_gate': {
                'passed': self.profit_gate_passed,
                'total_pnl': self.total_pnl
            },
            'rejection_reason': self.rejection_reason
        }


class EODPyramidMonitor:
    """
    Monitors price during EOD window and checks pyramid eligibility.

    Uses PM's own position data from database, not TradingView's position_status.
    """

    def __init__(
        self,
        portfolio: PortfolioStateManager,
        config: PortfolioConfig,
        atr_threshold: float = 1.0,
        use_1r_gate: bool = True
    ):
        """
        Initialize EOD Pyramid Monitor.

        Args:
            portfolio: Portfolio state manager with position data
            config: Portfolio configuration
            atr_threshold: ATR multiplier for pyramid spacing (default 1.0 = 1 ATR)
            use_1r_gate: Whether to require 1R move from entry (default True)
        """
        self.portfolio = portfolio
        self.config = config
        self.atr_threshold = atr_threshold
        self.use_1r_gate = use_1r_gate

        # Track last check results for debugging
        self._last_checks: Dict[str, PyramidCheckResult] = {}

        logger.info(
            f"[EOD-PYRAMID] Monitor initialized: "
            f"atr_threshold={atr_threshold}, use_1r_gate={use_1r_gate}"
        )

    def check_pyramid_eligibility(
        self,
        instrument: str,
        current_price: float,
        atr: float,
        db_manager=None
    ) -> PyramidCheckResult:
        """
        Check if a pyramid entry should be executed.

        Args:
            instrument: Trading instrument (e.g., "GOLD_MINI")
            current_price: Current market price
            atr: Current ATR value (from last signal or fetched live)
            db_manager: Optional DatabaseStateManager for pyramiding_state

        Returns:
            PyramidCheckResult with eligibility status and gate details
        """
        result = PyramidCheckResult(
            should_pyramid=False,
            instrument=instrument,
            current_price=current_price,
            atr_threshold=self.atr_threshold
        )

        # Get instrument config
        try:
            inst_type = InstrumentType(instrument)
            inst_config = get_instrument_config(inst_type)
        except ValueError:
            result.rejection_reason = f"Unknown instrument: {instrument}"
            logger.warning(f"[EOD-PYRAMID] {result.rejection_reason}")
            return result

        result.max_pyramids = inst_config.max_pyramids

        # Get positions for this instrument
        state = self.portfolio.get_current_state()
        positions = state.get_positions_for_instrument(instrument)
        open_positions = {k: v for k, v in positions.items() if v.status == 'open'}

        if not open_positions:
            result.rejection_reason = "No open positions"
            logger.debug(f"[EOD-PYRAMID] {instrument}: {result.rejection_reason}")
            return result

        result.has_position = True
        result.position_count = len(open_positions)

        # Check max pyramids
        # Position count includes base, so pyramid_count = position_count - 1
        pyramid_count = result.position_count - 1
        if pyramid_count >= result.max_pyramids:
            result.rejection_reason = f"Max pyramids reached ({pyramid_count}/{result.max_pyramids})"
            logger.debug(f"[EOD-PYRAMID] {instrument}: {result.rejection_reason}")
            return result

        # Find base position (oldest/first position)
        base_position = None
        for pos in sorted(open_positions.values(), key=lambda p: p.entry_timestamp):
            if pos.is_base_position or 'Long_1' in pos.position_id:
                base_position = pos
                break

        if not base_position:
            # Use first position as base
            base_position = sorted(open_positions.values(), key=lambda p: p.entry_timestamp)[0]

        result.entry_price = float(base_position.entry_price)
        result.initial_risk = result.entry_price - float(base_position.initial_stop)

        # 1R Gate Check
        result.price_move_from_entry = current_price - result.entry_price
        result.price_move_in_r = result.price_move_from_entry / result.initial_risk if result.initial_risk > 0 else 0

        if self.use_1r_gate:
            result.one_r_gate_passed = result.price_move_from_entry > result.initial_risk
            if not result.one_r_gate_passed:
                result.rejection_reason = f"1R gate not passed (move: {result.price_move_in_r:.2f}R, need: >1R)"
                logger.debug(f"[EOD-PYRAMID] {instrument}: {result.rejection_reason}")
                return result
        else:
            result.one_r_gate_passed = True

        # Get last pyramid price from database or positions
        last_pyramid_price = None

        if db_manager:
            # Try to get from pyramiding_state table
            try:
                pyr_state = db_manager.get_pyramiding_state(instrument)
                if pyr_state and pyr_state.get('last_pyramid_price'):
                    last_pyramid_price = pyr_state['last_pyramid_price']
            except Exception as e:
                logger.warning(f"[EOD-PYRAMID] Could not get pyramiding_state: {e}")

        if last_pyramid_price is None:
            # Fall back to most recent position entry price
            sorted_positions = sorted(open_positions.values(), key=lambda p: p.entry_timestamp, reverse=True)
            last_pyramid_price = float(sorted_positions[0].entry_price)

        result.last_pyramid_price = last_pyramid_price

        # ATR Spacing Check
        result.price_move_from_last = current_price - last_pyramid_price
        result.atr_moves = result.price_move_from_last / atr if atr > 0 else 0

        result.atr_spacing_passed = result.atr_moves >= self.atr_threshold
        if not result.atr_spacing_passed:
            result.rejection_reason = f"ATR spacing not met ({result.atr_moves:.2f} ATR, need: >={self.atr_threshold})"
            logger.debug(f"[EOD-PYRAMID] {instrument}: {result.rejection_reason}")
            return result

        # Profit Gate Check
        point_value = inst_config.point_value
        total_pnl = 0.0
        for pos in open_positions.values():
            pos_pnl = (current_price - float(pos.entry_price)) * pos.lots * point_value
            total_pnl += pos_pnl

        result.total_pnl = total_pnl
        result.profit_gate_passed = total_pnl > 0

        if not result.profit_gate_passed:
            result.rejection_reason = f"Profit gate not passed (P&L: ₹{total_pnl:,.0f})"
            logger.debug(f"[EOD-PYRAMID] {instrument}: {result.rejection_reason}")
            return result

        # All gates passed!
        result.should_pyramid = True
        result.rejection_reason = None

        logger.info(
            f"[EOD-PYRAMID] {instrument}: PYRAMID ELIGIBLE @ {current_price:.2f} "
            f"(P&L: ₹{total_pnl:,.0f}, {result.atr_moves:.2f} ATR from last, {result.price_move_in_r:.2f}R from entry)"
        )

        # Cache result
        self._last_checks[instrument] = result

        return result

    def get_last_check(self, instrument: str) -> Optional[PyramidCheckResult]:
        """Get the last check result for an instrument"""
        return self._last_checks.get(instrument)

    def get_target_price(
        self,
        instrument: str,
        atr: float,
        db_manager=None
    ) -> Optional[float]:
        """
        Calculate the target price for next pyramid.

        Args:
            instrument: Trading instrument
            atr: Current ATR value
            db_manager: Optional DatabaseStateManager

        Returns:
            Target price for next pyramid, or None if no position
        """
        # Get positions
        state = self.portfolio.get_current_state()
        positions = state.get_positions_for_instrument(instrument)
        open_positions = {k: v for k, v in positions.items() if v.status == 'open'}

        if not open_positions:
            return None

        # Get last pyramid price
        last_pyramid_price = None

        if db_manager:
            try:
                pyr_state = db_manager.get_pyramiding_state(instrument)
                if pyr_state and pyr_state.get('last_pyramid_price'):
                    last_pyramid_price = pyr_state['last_pyramid_price']
            except Exception:
                pass

        if last_pyramid_price is None:
            sorted_positions = sorted(open_positions.values(), key=lambda p: p.entry_timestamp, reverse=True)
            last_pyramid_price = float(sorted_positions[0].entry_price)

        # Target = last_pyramid_price + (ATR * threshold)
        return last_pyramid_price + (atr * self.atr_threshold)

    def get_status(self, instrument: str, atr: float, db_manager=None) -> Dict:
        """
        Get current pyramid monitoring status for an instrument.

        Args:
            instrument: Trading instrument
            atr: Current ATR value
            db_manager: Optional DatabaseStateManager

        Returns:
            Status dictionary with position info and target price
        """
        state = self.portfolio.get_current_state()
        positions = state.get_positions_for_instrument(instrument)
        open_positions = {k: v for k, v in positions.items() if v.status == 'open'}

        if not open_positions:
            return {
                'instrument': instrument,
                'has_position': False,
                'position_count': 0,
                'target_price': None,
                'atr': atr
            }

        # Get instrument config
        try:
            inst_type = InstrumentType(instrument)
            inst_config = get_instrument_config(inst_type)
        except ValueError:
            inst_config = None

        # Find base position
        base_position = None
        for pos in sorted(open_positions.values(), key=lambda p: p.entry_timestamp):
            if pos.is_base_position or 'Long_1' in pos.position_id:
                base_position = pos
                break
        if not base_position:
            base_position = sorted(open_positions.values(), key=lambda p: p.entry_timestamp)[0]

        target_price = self.get_target_price(instrument, atr, db_manager)

        return {
            'instrument': instrument,
            'has_position': True,
            'position_count': len(open_positions),
            'pyramid_count': len(open_positions) - 1,
            'max_pyramids': inst_config.max_pyramids if inst_config else 5,
            'base_entry_price': float(base_position.entry_price),
            'initial_stop': float(base_position.initial_stop),
            'initial_risk': float(base_position.entry_price) - float(base_position.initial_stop),
            'target_price': target_price,
            'atr': atr,
            'atr_threshold': self.atr_threshold,
            'use_1r_gate': self.use_1r_gate,
            'last_check': self._last_checks.get(instrument, {})
        }
