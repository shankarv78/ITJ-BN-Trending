"""
Portfolio Backtest Engine

Simulates portfolio trading with:
- Tom Basso 3-constraint sizing
- Portfolio-level risk management
- Cross-instrument pyramiding
- Independent stop management
"""
import logging
from typing import List, Dict
from datetime import datetime
from core.models import Signal, SignalType, Position, InstrumentType
from core.portfolio_state import PortfolioStateManager
from core.position_sizer import TomBassoPositionSizer
from core.pyramid_gate import PyramidGateController
from core.stop_manager import TomBassoStopManager
from core.config import PortfolioConfig, get_instrument_config

logger = logging.getLogger(__name__)

class PortfolioBacktestEngine:
    """Main backtest engine for portfolio simulation"""
    
    def __init__(self, initial_capital: float, config: PortfolioConfig = None):
        """
        Initialize backtest engine
        
        Args:
            initial_capital: Starting capital
            config: Portfolio configuration
        """
        self.config = config or PortfolioConfig()
        self.portfolio = PortfolioStateManager(initial_capital, self.config)
        self.stop_manager = TomBassoStopManager()
        self.pyramid_controller = PyramidGateController(self.portfolio, self.config)
        
        # Position sizers per instrument
        self.sizers = {
            InstrumentType.GOLD_MINI: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.GOLD_MINI)
            ),
            InstrumentType.BANK_NIFTY: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.BANK_NIFTY)
            )
        }
        
        # Track for pyramiding
        self.last_pyramid_price = {}  # Per instrument
        self.base_positions = {}  # Track base position per instrument
        
        # Statistics
        self.stats = {
            'signals_processed': 0,
            'entries_executed': 0,
            'entries_blocked': 0,
            'pyramids_executed': 0,
            'pyramids_blocked': 0,
            'exits_executed': 0,
            'trades_closed': 0
        }
        
        logger.info(f"Backtest engine initialized: Capital=₹{initial_capital:,.0f}")
    
    def process_signal(self, signal: Signal) -> Dict:
        """
        Process a single signal
        
        Args:
            signal: Trading signal
            
        Returns:
            Dict with execution result
        """
        self.stats['signals_processed'] += 1
        
        logger.info(f"Processing signal: {signal.signal_type.value} {signal.position} @ ₹{signal.price}")
        
        if signal.signal_type == SignalType.BASE_ENTRY:
            return self._handle_base_entry(signal)
        elif signal.signal_type == SignalType.PYRAMID:
            return self._handle_pyramid(signal)
        elif signal.signal_type == SignalType.EXIT:
            return self._handle_exit(signal)
        else:
            return {'status': 'error', 'reason': f'Unknown signal type: {signal.signal_type}'}
    
    def _handle_base_entry(self, signal: Signal) -> Dict:
        """Handle base entry signal"""
        instrument = signal.instrument
        
        # Get instrument type
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        else:
            return {'status': 'error', 'reason': f'Unknown instrument: {instrument}'}
        
        inst_config = get_instrument_config(inst_type)
        sizer = self.sizers[inst_type]
        
        # Get current state
        state = self.portfolio.get_current_state(signal.timestamp)
        
        # Calculate position size
        constraints = sizer.calculate_base_entry_size(
            signal,
            equity=state.equity,
            available_margin=state.margin_available
        )
        
        if constraints.final_lots == 0:
            self.stats['entries_blocked'] += 1
            logger.warning(f"Entry blocked: {constraints.limiter}")
            return {
                'status': 'blocked',
                'reason': f'Zero lots (limited by {constraints.limiter})',
                'constraints': str(constraints)
            }
        
        # Check portfolio gate
        est_risk = (signal.price - signal.stop) * constraints.final_lots * inst_config.point_value
        est_vol = signal.atr * constraints.final_lots * inst_config.point_value
        
        gate_allowed, gate_reason = self.portfolio.check_portfolio_gate(est_risk, est_vol)
        
        if not gate_allowed:
            self.stats['entries_blocked'] += 1
            logger.warning(f"Entry blocked by portfolio gate: {gate_reason}")
            return {'status': 'blocked', 'reason': gate_reason}
        
        # Execute entry
        initial_stop = self.stop_manager.calculate_initial_stop(
            signal.price, signal.atr, inst_type
        )
        
        position = Position(
            position_id=f"{instrument}_{signal.position}",
            instrument=instrument,
            entry_timestamp=signal.timestamp,
            entry_price=signal.price,
            lots=constraints.final_lots,
            quantity=constraints.final_lots * inst_config.lot_size,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            highest_close=signal.price,
            atr=signal.atr,  # Store actual ATR for volatility calculations
            limiter=constraints.limiter
        )
        
        self.portfolio.add_position(position)
        
        # Track for pyramiding
        self.last_pyramid_price[instrument] = signal.price
        self.base_positions[instrument] = position
        
        self.stats['entries_executed'] += 1
        
        logger.info(f"✓ Entry executed: {constraints.final_lots} lots (limited by {constraints.limiter})")
        
        return {
            'status': 'executed',
            'lots': constraints.final_lots,
            'constraints': str(constraints)
        }
    
    def _handle_pyramid(self, signal: Signal) -> Dict:
        """Handle pyramid signal"""
        instrument = signal.instrument
        
        # Check if base position exists
        if instrument not in self.base_positions:
            self.stats['pyramids_blocked'] += 1
            return {'status': 'blocked', 'reason': 'No base position'}
        
        base_pos = self.base_positions[instrument]
        last_pyr_price = self.last_pyramid_price.get(instrument, base_pos.entry_price)
        
        # Check pyramid gates
        gate_check = self.pyramid_controller.check_pyramid_allowed(
            signal, instrument, base_pos, last_pyr_price
        )
        
        if not gate_check.allowed:
            self.stats['pyramids_blocked'] += 1
            logger.warning(f"Pyramid blocked: {gate_check.reason}")
            return {'status': 'blocked', 'reason': gate_check.reason, 'gate_check': gate_check}
        
        # Use suggested lots from signal (already calculated with triple constraint)
        lots = signal.suggested_lots
        
        if lots == 0:
            self.stats['pyramids_blocked'] += 1
            return {'status': 'blocked', 'reason': 'Zero suggested lots'}
        
        # Execute pyramid
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        else:
            inst_type = InstrumentType.BANK_NIFTY
        
        inst_config = get_instrument_config(inst_type)
        
        initial_stop = self.stop_manager.calculate_initial_stop(
            signal.price, signal.atr, inst_type
        )
        
        position = Position(
            position_id=f"{instrument}_{signal.position}",
            instrument=instrument,
            entry_timestamp=signal.timestamp,
            entry_price=signal.price,
            lots=lots,
            quantity=lots * inst_config.lot_size,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            highest_close=signal.price,
            atr=signal.atr  # Store actual ATR for volatility calculations
        )
        
        self.portfolio.add_position(position)
        self.last_pyramid_price[instrument] = signal.price
        self.stats['pyramids_executed'] += 1
        
        logger.info(f"✓ Pyramid executed: {lots} lots")
        
        return {'status': 'executed', 'lots': lots}
    
    def _handle_exit(self, signal: Signal) -> Dict:
        """Handle exit signal"""
        position_id = f"{signal.instrument}_{signal.position}"
        
        if position_id not in self.portfolio.positions:
            logger.warning(f"Position not found for exit: {position_id}")
            return {'status': 'error', 'reason': 'Position not found'}
        
        # Close position
        pnl = self.portfolio.close_position(position_id, signal.price, signal.timestamp)
        
        self.stats['exits_executed'] += 1
        self.stats['trades_closed'] += 1
        
        logger.info(f"✓ Exit executed: P&L=₹{pnl:,.0f}")
        
        return {'status': 'executed', 'pnl': pnl}
    
    def run_backtest(self, signals: List[Signal]) -> Dict:
        """
        Run complete backtest with signal sequence
        
        Args:
            signals: Chronologically sorted signals
            
        Returns:
            Dict with backtest results and statistics
        """
        logger.info("=" * 60)
        logger.info(f"Starting backtest with {len(signals)} signals")
        logger.info("=" * 60)
        
        for signal in signals:
            result = self.process_signal(signal)
            # Could add more detailed logging here
        
        # Final state
        final_state = self.portfolio.get_current_state()
        
        logger.info("=" * 60)
        logger.info("Backtest complete!")
        logger.info(f"Initial capital: ₹{self.portfolio.initial_capital:,.0f}")
        logger.info(f"Final equity: ₹{final_state.closed_equity:,.0f}")
        logger.info(f"Total P&L: ₹{final_state.closed_equity - self.portfolio.initial_capital:,.0f}")
        logger.info(f"Signals processed: {self.stats['signals_processed']}")
        logger.info(f"Entries executed: {self.stats['entries_executed']}")
        logger.info(f"Entries blocked: {self.stats['entries_blocked']}")
        logger.info(f"Pyramids executed: {self.stats['pyramids_executed']}")
        logger.info(f"Pyramids blocked: {self.stats['pyramids_blocked']}")
        logger.info("=" * 60)
        
        return {
            'initial_capital': self.portfolio.initial_capital,
            'final_equity': final_state.closed_equity,
            'total_pnl': final_state.closed_equity - self.portfolio.initial_capital,
            'stats': self.stats,
            'final_state': final_state
        }

