"""
Portfolio State Manager

Tracks all positions, calculates portfolio-level metrics:
- Total portfolio risk (sum of all position risks)
- Total portfolio volatility
- Margin utilization
- Equity calculations (closed, open, blended)
"""
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from core.models import Position, PortfolioState, InstrumentType
from core.config import PortfolioConfig, get_instrument_config

logger = logging.getLogger(__name__)

class PortfolioStateManager:
    """Manages portfolio state and calculates metrics"""

    def __init__(self, initial_capital: float, portfolio_config: PortfolioConfig = None,
                 db_manager = None, strategy_manager = None):
        """
        Initialize portfolio state manager

        Args:
            initial_capital: Starting capital in Rs
            portfolio_config: Portfolio configuration
            db_manager: Optional DatabaseStateManager for persistence
            strategy_manager: Optional StrategyManager for trade history logging
        """
        self.initial_capital = initial_capital
        self.config = portfolio_config or PortfolioConfig()
        self.db_manager = db_manager
        self.strategy_manager = strategy_manager

        # Load closed_equity and equity_high from database if available
        if self.db_manager:
            db_state = self.db_manager.get_portfolio_state()
            if db_state:
                self.closed_equity = float(db_state['closed_equity'])
                # Load equity_high (Tom Basso high watermark for position sizing)
                self.equity_high = float(db_state.get('equity_high') or self.closed_equity)
                logger.info(f"Loaded from database: closed_equity=₹{self.closed_equity:,.0f}, equity_high=₹{self.equity_high:,.0f}")
            else:
                self.closed_equity = initial_capital
                self.equity_high = initial_capital
                logger.info("No portfolio state in database, using initial_capital")
        else:
            self.closed_equity = initial_capital
            self.equity_high = initial_capital

        # Current state
        self.positions: Dict[str, Position] = {}

        logger.info(f"Portfolio initialized: Capital=₹{initial_capital:,.0f}, Closed Equity=₹{self.closed_equity:,.0f}, Equity High=₹{self.equity_high:,.0f}")

    def get_current_state(self, current_time: datetime = None) -> PortfolioState:
        """
        Get current portfolio state snapshot

        Args:
            current_time: Current timestamp

        Returns:
            PortfolioState with all metrics calculated
        """
        if current_time is None:
            current_time = datetime.now()

        # Calculate unrealized P&L
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values()
                                    if p.status == "open")

        # Calculate equity values
        open_equity = self.closed_equity + total_unrealized_pnl
        blended_equity = self.config.get_equity(self.closed_equity, total_unrealized_pnl)

        # Create state object
        state = PortfolioState(
            timestamp=current_time,
            equity=blended_equity,  # Primary equity for decisions
            closed_equity=self.closed_equity,
            open_equity=open_equity,
            blended_equity=blended_equity,
            positions=dict(self.positions)
        )

        # Calculate portfolio metrics
        self._calculate_risk_metrics(state)
        self._calculate_volatility_metrics(state)
        self._calculate_margin_metrics(state)

        return state

    def _calculate_risk_metrics(self, state: PortfolioState):
        """Calculate portfolio risk metrics"""
        total_risk = 0.0
        gold_risk = 0.0
        bn_risk = 0.0
        silver_risk = 0.0
        copper_risk = 0.0

        for pos in state.get_open_positions().values():
            # Get instrument config for point value
            instrument = pos.instrument
            if instrument == "BANK_NIFTY":
                inst_type = InstrumentType.BANK_NIFTY
            elif instrument == "GOLD_MINI":
                inst_type = InstrumentType.GOLD_MINI
            elif instrument == "COPPER":
                inst_type = InstrumentType.COPPER
            elif instrument == "SILVER_MINI":
                inst_type = InstrumentType.SILVER_MINI
            else:
                logger.warning(f"Unknown instrument: {instrument}")
                continue

            config = get_instrument_config(inst_type)
            pos_risk = pos.calculate_risk(config.point_value)

            total_risk += pos_risk
            if instrument == "GOLD_MINI":
                gold_risk += pos_risk
            elif instrument == "BANK_NIFTY":
                bn_risk += pos_risk
            elif instrument == "SILVER_MINI":
                silver_risk += pos_risk
            elif instrument == "COPPER":
                copper_risk += pos_risk

        state.total_risk_amount = total_risk
        state.total_risk_percent = (total_risk / state.equity * 100) if state.equity > 0 else 0
        state.gold_risk_percent = (gold_risk / state.equity * 100) if state.equity > 0 else 0
        state.banknifty_risk_percent = (bn_risk / state.equity * 100) if state.equity > 0 else 0
        state.silver_risk_percent = (silver_risk / state.equity * 100) if state.equity > 0 else 0
        state.copper_risk_percent = (copper_risk / state.equity * 100) if state.equity > 0 else 0

    def _calculate_volatility_metrics(self, state: PortfolioState):
        """Calculate portfolio volatility metrics"""
        total_vol = 0.0
        gold_vol = 0.0
        bn_vol = 0.0
        silver_vol = 0.0
        copper_vol = 0.0

        for pos in state.get_open_positions().values():
            # Volatility contribution = ATR × Quantity × Point_Value
            instrument = pos.instrument

            # Use actual ATR from position, fallback to typical values if not set
            if pos.atr > 0:
                atr = pos.atr
            else:
                # Fallback to typical ATR if not stored (backwards compatibility)
                if instrument == "GOLD_MINI":
                    atr = 450
                elif instrument == "COPPER":
                    atr = 3.0  # Typical ATR for Copper (in Rs/kg)
                elif instrument == "SILVER_MINI":
                    atr = 1500  # Typical ATR for Silver Mini (in Rs/kg)
                else:
                    atr = 350  # Bank Nifty

            if instrument == "GOLD_MINI":
                point_val = 10  # Rs 10 per point per lot
                vol = atr * pos.lots * point_val
                gold_vol += vol
            elif instrument == "COPPER":
                point_val = 2500  # Rs 2500 per Re 1 move per lot
                vol = atr * pos.lots * point_val
                copper_vol += vol
            elif instrument == "SILVER_MINI":
                point_val = 5  # Rs 5 per Rs 1/kg move per lot (5kg contract)
                vol = atr * pos.lots * point_val
                silver_vol += vol
            else:  # BANK_NIFTY
                point_val = 30  # Rs 30 per point per lot (Dec 2025 onwards)
                vol = atr * pos.lots * point_val
                bn_vol += vol

            total_vol += vol

        state.total_vol_amount = total_vol
        state.total_vol_percent = (total_vol / state.equity * 100) if state.equity > 0 else 0
        state.gold_vol_percent = (gold_vol / state.equity * 100) if state.equity > 0 else 0
        state.banknifty_vol_percent = (bn_vol / state.equity * 100) if state.equity > 0 else 0
        state.silver_vol_percent = (silver_vol / state.equity * 100) if state.equity > 0 else 0
        state.copper_vol_percent = (copper_vol / state.equity * 100) if state.equity > 0 else 0

    def _calculate_margin_metrics(self, state: PortfolioState):
        """Calculate margin utilization metrics"""
        total_margin_used = 0.0

        for pos in state.get_open_positions().values():
            instrument = pos.instrument

            if instrument == "GOLD_MINI":
                margin_per_lot = 105000.0  # ₹1.05L per lot (conservative)
            elif instrument == "COPPER":
                margin_per_lot = 300000.0  # ₹3L per lot
            elif instrument == "SILVER_MINI":
                margin_per_lot = 200000.0  # ₹2L per lot
            else:  # BANK_NIFTY
                margin_per_lot = 270000.0  # ₹2.7L per lot

            total_margin_used += pos.lots * margin_per_lot

        state.margin_used = total_margin_used
        state.margin_available = max(0, state.equity - total_margin_used)
        state.margin_utilization_percent = (
            (total_margin_used / state.equity * 100) if state.equity > 0 else 0
        )

    def reload_equity_from_db(self) -> float:
        """
        Reload closed_equity from database after capital injection

        This should be called after a capital transaction to ensure
        PortfolioStateManager has the latest equity value.

        Returns:
            New closed_equity value

        Raises:
            RuntimeError: If no database manager configured
        """
        if not self.db_manager:
            raise RuntimeError("No database manager configured - cannot reload equity")

        db_state = self.db_manager.get_portfolio_state()
        if db_state:
            old_equity = self.closed_equity
            old_high = self.equity_high
            self.closed_equity = float(db_state['closed_equity'])
            self.equity_high = float(db_state.get('equity_high') or self.closed_equity)
            logger.info(f"Equity reloaded from DB: closed=₹{old_equity:,.0f}->₹{self.closed_equity:,.0f}, high=₹{old_high:,.0f}->₹{self.equity_high:,.0f}")
        else:
            logger.warning("No portfolio state found in database during reload")

        return self.closed_equity

    def add_position(self, position: Position):
        """Add new position to portfolio"""
        self.positions[position.position_id] = position
        logger.info(f"Position added: {position.position_id}, {position.lots} lots @ ₹{position.entry_price}")

        # Save portfolio state to database if db_manager available
        # This ensures risk/margin are persisted for crash recovery
        if self.db_manager:
            state = self.get_current_state()
            self.db_manager.save_portfolio_state(state, self.initial_capital, self.equity_high)
            logger.debug(f"Portfolio state saved after position add")

    def close_position(self, position_id: str, exit_price: float, exit_time: datetime) -> float:
        """
        Close position and update closed equity

        Args:
            position_id: Position to close
            exit_price: Exit price
            exit_time: Exit timestamp

        Returns:
            Realized P&L from this position
        """
        if position_id not in self.positions:
            logger.error(f"Position not found: {position_id}")
            return 0.0

        pos = self.positions[position_id]

        # Get point value
        if pos.instrument == "GOLD_MINI":
            point_value = 10.0
        elif pos.instrument == "COPPER":
            point_value = 2500.0
        elif pos.instrument == "SILVER_MINI":
            point_value = 5.0  # 5kg × Rs 1/kg
        else:  # BANK_NIFTY
            point_value = 30.0  # Dec 2025 onwards

        # Calculate realized P&L
        pnl = pos.calculate_pnl(exit_price, point_value)
        pos.realized_pnl = pnl
        pos.status = "closed"

        # Set exit data
        pos.exit_timestamp = exit_time
        pos.exit_price = exit_price

        # Update closed equity
        self.closed_equity += pnl

        # Update equity_high (Tom Basso high watermark) - only ratchets up
        if self.closed_equity > self.equity_high:
            old_high = self.equity_high
            self.equity_high = self.closed_equity
            logger.info(f"Equity high watermark updated: ₹{old_high:,.0f} -> ₹{self.equity_high:,.0f}")

        # Record P&L in equity ledger (single source of truth for equity)
        if self.db_manager:
            try:
                self.db_manager.record_trading_pnl(
                    position_id=position_id,
                    instrument=pos.instrument,
                    pnl=pnl
                )
            except Exception as e:
                logger.error(f"Failed to record trading P&L in ledger: {e}")
                # Continue even if ledger recording fails - don't break the trade

        # Save portfolio state to database if db_manager available
        if self.db_manager:
            state = self.get_current_state(exit_time)
            self.db_manager.save_portfolio_state(state, self.initial_capital, self.equity_high)
            logger.debug(f"Portfolio state saved to database")

        # Log trade to strategy trade history for cumulative P&L tracking
        if self.strategy_manager:
            try:
                self.strategy_manager.log_closed_position(pos, exit_price, exit_time)
                logger.debug(f"Trade history logged for position {position_id}")
            except Exception as e:
                logger.error(f"Failed to log trade history: {e}")

        logger.info(f"Position closed: {position_id}, P&L=₹{pnl:,.0f}, "
                   f"New closed equity=₹{self.closed_equity:,.0f}")

        return pnl

    def update_position_unrealized_pnl(self, position_id: str, current_price: float):
        """Update unrealized P&L for open position"""
        if position_id not in self.positions:
            return

        pos = self.positions[position_id]
        if pos.status != "open":
            return

        # Get point value
        if pos.instrument == "GOLD_MINI":
            point_value = 10.0
        elif pos.instrument == "COPPER":
            point_value = 2500.0
        elif pos.instrument == "SILVER_MINI":
            point_value = 5.0  # 5kg × Rs 1/kg
        else:  # BANK_NIFTY
            point_value = 30.0  # Dec 2025 onwards

        pos.unrealized_pnl = pos.calculate_pnl(current_price, point_value)

    def check_portfolio_gate(
        self,
        new_position_risk: float,
        new_position_vol: float
    ) -> Tuple[bool, str]:
        """
        Check if new position would exceed portfolio limits

        Args:
            new_position_risk: Risk of proposed position in Rs
            new_position_vol: Volatility of proposed position in Rs

        Returns:
            (allowed, reason)
        """
        state = self.get_current_state()

        # Check risk limit
        projected_risk = state.total_risk_amount + new_position_risk
        projected_risk_pct = (projected_risk / state.equity * 100) if state.equity > 0 else 0

        if projected_risk_pct > self.config.max_portfolio_risk_percent:
            reason = f"Portfolio risk would be {projected_risk_pct:.1f}% (limit: {self.config.max_portfolio_risk_percent}%)"
            logger.warning(f"Portfolio gate BLOCKED: {reason}")
            return False, reason

        # Check volatility limit
        projected_vol = state.total_vol_amount + new_position_vol
        projected_vol_pct = (projected_vol / state.equity * 100) if state.equity > 0 else 0

        if projected_vol_pct > self.config.max_portfolio_vol_percent:
            reason = f"Portfolio volatility would be {projected_vol_pct:.1f}% (limit: {self.config.max_portfolio_vol_percent}%)"
            logger.warning(f"Portfolio gate BLOCKED: {reason}")
            return False, reason

        logger.debug(f"Portfolio gate OPEN: Risk={projected_risk_pct:.1f}%, Vol={projected_vol_pct:.1f}%")
        return True, "Portfolio gates passed"
