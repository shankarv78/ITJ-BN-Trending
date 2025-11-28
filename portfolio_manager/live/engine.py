"""
Live Trading Engine

Uses same portfolio logic as backtest, but executes real trades via OpenAlgo
"""
import logging
from typing import Dict, Optional
from datetime import datetime
from core.models import Signal, SignalType, Position, InstrumentType
from core.portfolio_state import PortfolioStateManager
from core.position_sizer import TomBassoPositionSizer
from core.pyramid_gate import PyramidGateController
from core.stop_manager import TomBassoStopManager
from core.config import PortfolioConfig, get_instrument_config
from live.rollover_scanner import RolloverScanner, RolloverScanResult
from live.rollover_executor import RolloverExecutor, BatchRolloverResult

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    """
    Live trading engine using OpenAlgo
    
    IDENTICAL logic to backtest engine, but executes real trades
    """
    
    def __init__(
        self, 
        initial_capital: float,
        openalgo_client,  # OpenAlgo client instance
        config: PortfolioConfig = None
    ):
        """
        Initialize live trading engine
        
        Args:
            initial_capital: Starting capital (or current equity)
            openalgo_client: OpenAlgo API client
            config: Portfolio configuration
        """
        self.config = config or PortfolioConfig()
        self.portfolio = PortfolioStateManager(initial_capital, self.config)
        self.stop_manager = TomBassoStopManager()
        self.pyramid_controller = PyramidGateController(self.portfolio, self.config)
        self.openalgo = openalgo_client
        
        # Position sizers per instrument (SAME as backtest)
        self.sizers = {
            InstrumentType.GOLD_MINI: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.GOLD_MINI)
            ),
            InstrumentType.BANK_NIFTY: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.BANK_NIFTY)
            )
        }
        
        # Track for pyramiding (SAME as backtest)
        self.last_pyramid_price = {}
        self.base_positions = {}
        
        # Statistics
        self.stats = {
            'signals_received': 0,
            'entries_executed': 0,
            'entries_blocked': 0,
            'pyramids_executed': 0,
            'pyramids_blocked': 0,
            'exits_executed': 0,
            'orders_placed': 0,
            'orders_failed': 0,
            'rollovers_executed': 0,
            'rollovers_failed': 0,
            'rollover_cost_total': 0.0
        }

        # Rollover components
        self.rollover_scanner = RolloverScanner(self.config)
        self.rollover_executor: Optional[RolloverExecutor] = None
        self._last_rollover_check: Optional[datetime] = None

        logger.info(f"Live engine initialized: Capital=₹{initial_capital:,.0f}")
    
    def process_signal(self, signal: Signal) -> Dict:
        """
        Process signal in live mode
        
        SAME logic as backtest, but calls OpenAlgo for execution
        
        Args:
            signal: Trading signal from TradingView
            
        Returns:
            Dict with execution result
        """
        self.stats['signals_received'] += 1
        
        logger.info(f"[LIVE] Processing: {signal.signal_type.value} {signal.position} @ ₹{signal.price}")
        
        if signal.signal_type == SignalType.BASE_ENTRY:
            return self._handle_base_entry_live(signal)
        elif signal.signal_type == SignalType.PYRAMID:
            return self._handle_pyramid_live(signal)
        elif signal.signal_type == SignalType.EXIT:
            return self._handle_exit_live(signal)
        else:
            return {'status': 'error', 'reason': f'Unknown signal type'}
    
    def _handle_base_entry_live(self, signal: Signal) -> Dict:
        """
        Handle base entry in live mode
        
        IDENTICAL sizing logic as backtest, but executes via OpenAlgo
        """
        instrument = signal.instrument
        
        # Get instrument type
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        else:
            return {'status': 'error', 'reason': f'Unknown instrument'}
        
        inst_config = get_instrument_config(inst_type)
        sizer = self.sizers[inst_type]
        
        # Get LIVE equity from OpenAlgo
        funds = self.openalgo.get_funds()
        live_equity = funds.get('availablecash', self.portfolio.closed_equity)
        available_margin = live_equity * 0.6  # Use 60% of equity as margin
        
        # Calculate position size (SAME as backtest)
        constraints = sizer.calculate_base_entry_size(
            signal,
            equity=live_equity,
            available_margin=available_margin
        )
        
        if constraints.final_lots == 0:
            self.stats['entries_blocked'] += 1
            return {
                'status': 'blocked',
                'reason': f'Zero lots (limited by {constraints.limiter})'
            }
        
        # Check portfolio gate (SAME as backtest)
        est_risk = (signal.price - signal.stop) * constraints.final_lots * inst_config.point_value
        est_vol = signal.atr * constraints.final_lots * inst_config.point_value
        
        gate_allowed, gate_reason = self.portfolio.check_portfolio_gate(est_risk, est_vol)
        
        if not gate_allowed:
            self.stats['entries_blocked'] += 1
            return {'status': 'blocked', 'reason': gate_reason}
        
        # DIFFERENCE: Execute via OpenAlgo instead of simulating
        execution_result = self._execute_entry_openalgo(signal, constraints.final_lots, inst_type)
        
        if execution_result['status'] == 'success':
            # Create position record (SAME structure as backtest)
            initial_stop = self.stop_manager.calculate_initial_stop(
                signal.price, signal.atr, inst_type
            )
            
            # Extract PE/CE entry prices from execution result if available
            # These are needed for accurate rollover P&L calculation
            pe_entry_price = execution_result.get('order_details', {}).get('pe_entry_price')
            ce_entry_price = execution_result.get('order_details', {}).get('ce_entry_price')
            
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
                limiter=constraints.limiter,
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                **{k: v for k, v in execution_result.get('order_details', {}).items() 
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price']}  # Exclude generic fields
            )
            
            self.portfolio.add_position(position)
            self.last_pyramid_price[instrument] = signal.price
            self.base_positions[instrument] = position
            self.stats['entries_executed'] += 1
            
            logger.info(f"✓ [LIVE] Entry executed: {constraints.final_lots} lots")
            
            return {
                'status': 'executed',
                'lots': constraints.final_lots,
                'execution': execution_result
            }
        else:
            self.stats['orders_failed'] += 1
            return execution_result
    
    def _execute_entry_openalgo(
        self, 
        signal: Signal, 
        lots: int, 
        inst_type: InstrumentType
    ) -> Dict:
        """
        Execute entry via OpenAlgo API
        
        For Bank Nifty: Execute synthetic future (SELL PE + BUY CE)
        For Gold Mini: Execute futures contract
        
        Args:
            signal: Entry signal
            lots: Calculated lot size
            inst_type: Instrument type
            
        Returns:
            Execution result dict
        """
        logger.info(f"[OPENALGO] Executing {inst_type.value} entry: {lots} lots")
        
        # This will be implemented with actual OpenAlgo client
        # For now, return mock success for testing
        if inst_type == InstrumentType.BANK_NIFTY:
            # For Bank Nifty synthetic futures
            strike = int(signal.price // 100) * 100  # Round to nearest 100
            return {
                'status': 'success',
                'order_details': {
                    'pe_order_id': f'MOCK_PE_{signal.timestamp.timestamp()}',
                    'ce_order_id': f'MOCK_CE_{signal.timestamp.timestamp()}',
                    'pe_entry_price': signal.price,
                    'ce_entry_price': signal.price,
                    'strike': strike,
                    'expiry': '2025-12-25',  # Mock expiry
                    'pe_symbol': f'BANKNIFTY251225{strike}PE',
                    'ce_symbol': f'BANKNIFTY251225{strike}CE'
                }
            }
        else:
            # For Gold Mini futures
            return {
                'status': 'success',
                'order_details': {
                    'futures_order_id': f'MOCK_{signal.timestamp.timestamp()}',
                    'fill_price': signal.price,
                    'futures_symbol': 'GOLDM25DEC31FUT',
                    'contract_month': 'DEC25'
                }
            }
    
    def _handle_pyramid_live(self, signal: Signal) -> Dict:
        """Handle pyramid in live mode (SAME logic as backtest)"""
        instrument = signal.instrument
        
        if instrument not in self.base_positions:
            self.stats['pyramids_blocked'] += 1
            return {'status': 'blocked', 'reason': 'No base position'}
        
        base_pos = self.base_positions[instrument]
        last_pyr_price = self.last_pyramid_price.get(instrument, base_pos.entry_price)
        
        # Check pyramid gates (SAME as backtest)
        gate_check = self.pyramid_controller.check_pyramid_allowed(
            signal, instrument, base_pos, last_pyr_price
        )
        
        if not gate_check.allowed:
            self.stats['pyramids_blocked'] += 1
            return {'status': 'blocked', 'reason': gate_check.reason}
        
        # Execute via OpenAlgo
        lots = signal.suggested_lots
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        else:
            inst_type = InstrumentType.BANK_NIFTY
        
        execution_result = self._execute_entry_openalgo(signal, lots, inst_type)
        
        if execution_result['status'] == 'success':
            inst_config = get_instrument_config(inst_type)
            initial_stop = self.stop_manager.calculate_initial_stop(
                signal.price, signal.atr, inst_type
            )
            
            # Extract PE/CE entry prices from execution result if available
            pe_entry_price = execution_result.get('order_details', {}).get('pe_entry_price')
            ce_entry_price = execution_result.get('order_details', {}).get('ce_entry_price')
            
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
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                **{k: v for k, v in execution_result.get('order_details', {}).items() 
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price']}  # Exclude generic fields
            )
            
            self.portfolio.add_position(position)
            self.last_pyramid_price[instrument] = signal.price
            self.stats['pyramids_executed'] += 1
            
            return {'status': 'executed', 'lots': lots}
        else:
            return execution_result
    
    def _handle_exit_live(self, signal: Signal) -> Dict:
        """Handle exit in live mode"""
        position_id = f"{signal.instrument}_{signal.position}"
        
        if position_id not in self.portfolio.positions:
            return {'status': 'error', 'reason': 'Position not found'}
        
        # Execute exit via OpenAlgo
        position = self.portfolio.positions[position_id]
        execution_result = self._execute_exit_openalgo(position)
        
        if execution_result['status'] == 'success':
            # Close position (SAME as backtest)
            pnl = self.portfolio.close_position(position_id, signal.price, signal.timestamp)
            self.stats['exits_executed'] += 1
            
            return {'status': 'executed', 'pnl': pnl}
        else:
            return execution_result
    
    def _execute_exit_openalgo(self, position: Position) -> Dict:
        """Execute exit via OpenAlgo API"""
        logger.info(f"[OPENALGO] Executing exit: {position.position_id}")

        # Mock for testing
        return {
            'status': 'success',
            'order_details': {
                'order_id': f'EXIT_{position.position_id}'
            }
        }

    # =========================================================================
    # ROLLOVER METHODS
    # =========================================================================

    def check_and_rollover_positions(
        self,
        dry_run: bool = False,
        broker: str = "zerodha"
    ) -> BatchRolloverResult:
        """
        Check for positions needing rollover and execute

        Called periodically (e.g., daily at market open or hourly).

        Args:
            dry_run: If True, simulate without placing orders
            broker: Broker name for symbol formatting

        Returns:
            BatchRolloverResult with execution details
        """
        logger.info("=" * 60)
        logger.info("ROLLOVER CHECK STARTING")
        logger.info("=" * 60)

        # Initialize rollover executor if not already done
        if self.rollover_executor is None:
            self.rollover_executor = RolloverExecutor(
                openalgo_client=self.openalgo,
                portfolio=self.portfolio,
                config=self.config,
                broker=broker
            )

        # Scan for positions needing rollover
        scan_result = self.rollover_scanner.scan_positions(self.portfolio)
        self._last_rollover_check = datetime.now()

        if not scan_result.has_candidates():
            logger.info("No positions need rollover")
            return BatchRolloverResult(
                total_positions=0,
                successful=0,
                failed=0,
                start_time=datetime.now(),
                end_time=datetime.now()
            )

        logger.info(f"Found {len(scan_result.candidates)} positions to roll")

        # Execute rollovers
        result = self.rollover_executor.execute_rollovers(scan_result, dry_run=dry_run)

        # Update statistics
        self.stats['rollovers_executed'] += result.successful
        self.stats['rollovers_failed'] += result.failed
        self.stats['rollover_cost_total'] += result.total_rollover_cost

        logger.info("=" * 60)
        logger.info(f"ROLLOVER COMPLETE: {result.successful}/{result.total_positions} successful")
        logger.info(f"Total rollover cost: ₹{result.total_rollover_cost:,.2f}")
        logger.info("=" * 60)

        return result

    def scan_rollover_candidates(self) -> RolloverScanResult:
        """
        Scan positions for rollover candidates without executing

        Useful for checking what would be rolled before actual execution.

        Returns:
            RolloverScanResult with candidates
        """
        return self.rollover_scanner.scan_positions(self.portfolio)

    def get_rollover_status(self) -> Dict:
        """
        Get current rollover status for monitoring

        Returns:
            Dict with rollover statistics and status
        """
        scan_result = self.rollover_scanner.scan_positions(self.portfolio)

        return {
            'last_check': self._last_rollover_check.isoformat() if self._last_rollover_check else None,
            'auto_rollover_enabled': self.config.enable_auto_rollover,
            'banknifty_rollover_days': self.config.banknifty_rollover_days,
            'gold_mini_rollover_days': self.config.gold_mini_rollover_days,
            'positions_needing_rollover': len(scan_result.candidates),
            'candidates': [
                {
                    'position_id': c.position.position_id,
                    'instrument': c.instrument,
                    'days_to_expiry': c.days_to_expiry,
                    'current_expiry': c.current_expiry,
                    'next_expiry': c.next_expiry
                }
                for c in scan_result.candidates
            ],
            'stats': {
                'rollovers_executed': self.stats['rollovers_executed'],
                'rollovers_failed': self.stats['rollovers_failed'],
                'rollover_cost_total': self.stats['rollover_cost_total']
            }
        }

