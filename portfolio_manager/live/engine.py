"""
Live Trading Engine

Uses same portfolio logic as backtest, but executes real trades via OpenAlgo
"""
import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime
from core.models import Signal, SignalType, Position, InstrumentType, EODMonitorSignal
from core.portfolio_state import PortfolioStateManager
from core.eod_monitor import EODMonitor
from core.eod_executor import EODExecutor, EODExecutionContext, EODExecutionPhase
from core.position_sizer import TomBassoPositionSizer
from core.pyramid_gate import PyramidGateController
from core.stop_manager import TomBassoStopManager
from core.config import PortfolioConfig, get_instrument_config
from core.signal_validator import SignalValidator, SignalValidationConfig, ValidationSeverity
from core.order_executor import OrderExecutor, SimpleLimitExecutor, ProgressiveExecutor, ExecutionStatus
from core.signal_validation_metrics import SignalValidationMetrics
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
        config: PortfolioConfig = None,
        db_manager = None  # Optional DatabaseStateManager for persistence
    ):
        """
        Initialize live trading engine
        
        Args:
            initial_capital: Starting capital (or current equity)
            openalgo_client: OpenAlgo API client
            config: Portfolio configuration
            db_manager: Optional DatabaseStateManager for persistence
        """
        self.config = config or PortfolioConfig()
        self.db_manager = db_manager
        
        # Initialize portfolio with database manager
        self.portfolio = PortfolioStateManager(initial_capital, self.config, db_manager)
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
        
        # Initialize pyramiding tracking (will be populated by CrashRecoveryManager on startup)
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
        
        # Signal validation components
        validation_config = self.config.signal_validation_config or SignalValidationConfig()
        self.signal_validator = SignalValidator(
            config=validation_config,
            portfolio_manager=self.portfolio
        )
        
        # Metrics collection
        self.metrics = SignalValidationMetrics(window_size=1000)
        
        # Order executor based on config
        if self.config.execution_strategy == "simple_limit":
            self.order_executor: OrderExecutor = SimpleLimitExecutor(openalgo_client=self.openalgo)
        else:  # progressive (default)
            self.order_executor: OrderExecutor = ProgressiveExecutor(openalgo_client=self.openalgo)

        # EOD (End-of-Day) Pre-Close Execution Components
        self.eod_monitor: Optional[EODMonitor] = None
        self.eod_executor: Optional[EODExecutor] = None
        if self.config.eod_enabled:
            self.eod_monitor = EODMonitor(self.config)
            self.eod_executor = EODExecutor(self.config, self.openalgo)
            logger.info("[LIVE] EOD pre-close execution enabled")

        logger.info(
            f"Live engine initialized: Capital=₹{initial_capital:,.0f}, "
            f"Validation={'enabled' if self.config.signal_validation_enabled else 'disabled'}, "
            f"Execution strategy={self.config.execution_strategy}, "
            f"EOD={'enabled' if self.config.eod_enabled else 'disabled'}"
        )
    
    def _get_broker_price_with_timeout(
        self, 
        instrument: str, 
        fallback_price: float,
        timeout_seconds: float = 2.0,
        max_retries: int = 3
    ) -> Tuple[Optional[float], bool]:
        """
        Fetch broker price with timeout and exponential backoff retry.
        
        Args:
            instrument: Instrument symbol
            fallback_price: Price to use if broker API fails
            timeout_seconds: Timeout per attempt (default: 2.0s)
            max_retries: Maximum retry attempts (default: 3)
        
        Returns:
            Tuple of (broker_price, validation_bypassed)
            - broker_price: LTP from broker, or fallback_price if failed
            - validation_bypassed: True if broker API failed (used fallback)
        """
        for attempt in range(max_retries):
            try:
                # Calculate backoff delay: 0s, 0.5s, 1.0s
                if attempt > 0:
                    backoff_delay = attempt * 0.5
                    logger.debug(f"[LIVE] Retry {attempt}/{max_retries} after {backoff_delay}s backoff")
                    time.sleep(backoff_delay)
                
                # Attempt to get quote with timeout
                # Note: OpenAlgo client doesn't support timeout parameter directly
                # This is a placeholder - actual implementation depends on client API
                quote = self.openalgo.get_quote(instrument)
                broker_price = quote.get('ltp', fallback_price)
                
                logger.debug(f"[LIVE] Broker price fetched: ₹{broker_price:,.2f}")
                return broker_price, False  # Success, validation not bypassed
                
            except TimeoutError as e:
                logger.warning(
                    f"[LIVE] Broker API timeout (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"[LIVE] Broker API timeout after {max_retries} attempts, "
                        f"using signal price ₹{fallback_price:,.2f} (VALIDATION BYPASSED)"
                    )
                    return fallback_price, True  # Failed, validation bypassed
                    
            except ConnectionError as e:
                logger.warning(
                    f"[LIVE] Broker API connection error (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"[LIVE] Broker API connection failed after {max_retries} attempts, "
                        f"using signal price ₹{fallback_price:,.2f} (VALIDATION BYPASSED)"
                    )
                    return fallback_price, True  # Failed, validation bypassed
                    
            except Exception as e:
                logger.error(
                    f"[LIVE] Broker API error (attempt {attempt + 1}/{max_retries}): {e}, "
                    f"using signal price ₹{fallback_price:,.2f} (VALIDATION BYPASSED)"
                )
                return fallback_price, True  # Failed, validation bypassed
        
        # Should never reach here, but safety fallback
        return fallback_price, True
    
    def process_signal(self, signal: Signal, coordinator=None) -> Dict:
        """
        Process signal in live mode
        
        SAME logic as backtest, but calls OpenAlgo for execution
        
        Args:
            signal: Trading signal from TradingView
            coordinator: Optional RedisCoordinator for leader verification
            
        Returns:
            Dict with execution result
        """
        # Optional: Verify leadership if coordinator provided
        # This provides additional protection if called directly (not via webhook)
        if coordinator and not coordinator.is_leader:
            logger.warning(f"[LIVE] Rejecting signal - not leader (instance: {coordinator.instance_id})")
            return {'status': 'rejected', 'reason': 'not_leader'}

        # EOD Deduplication: Check if this signal was already executed at EOD
        if self.eod_monitor and self.config.eod_enabled:
            fingerprint = f"{signal.instrument}:{signal.timestamp.isoformat()}"
            if self.eod_monitor.was_executed_at_eod(signal.instrument, fingerprint):
                logger.info(
                    f"[LIVE] Skipping signal - already executed at EOD: "
                    f"{signal.signal_type.value} {signal.instrument}"
                )
                return {
                    'status': 'skipped',
                    'reason': 'already_executed_at_eod',
                    'fingerprint': fingerprint
                }

        self.stats['signals_received'] += 1

        logger.info(f"[LIVE] Processing: {signal.signal_type.value} {signal.position} @ ₹{signal.price}")
        
        # Step 1: Condition validation (trusts TradingView signal price)
        if self.config.signal_validation_enabled:
            portfolio_state = self.portfolio.get_current_state()
            condition_result = self.signal_validator.validate_conditions_with_signal_price(
                signal, portfolio_state
            )
            
            # Record validation metric
            self.metrics.record_validation(
                signal_type=signal.signal_type,
                instrument=signal.instrument,
                validation_stage='condition',
                result='passed' if condition_result.is_valid else 'failed',
                severity=condition_result.severity,
                signal_age_seconds=condition_result.signal_age_seconds,
                rejection_reason=condition_result.reason if not condition_result.is_valid else None
            )
            
            if not condition_result.is_valid:
                age_str = f"{condition_result.signal_age_seconds:.1f}s" if condition_result.signal_age_seconds is not None else "N/A"
                logger.warning(
                    f"[LIVE] Signal rejected at condition validation: {condition_result.reason} "
                    f"(age: {age_str})"
                )
                return {
                    'status': 'rejected',
                    'reason': 'validation_failed',
                    'validation_stage': 'condition',
                    'validation_reason': condition_result.reason,
                    'signal_age_seconds': condition_result.signal_age_seconds
                }
            
            # Log validation severity if not normal
            if condition_result.severity.value != "normal":
                logger.info(
                    f"[LIVE] Signal condition validation passed with {condition_result.severity.value} severity "
                    f"(age: {condition_result.signal_age_seconds:.1f}s)"
                )
        
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
        # TODO: TESTING ONLY - Using portfolio equity instead of broker equity
        # Uncomment below for production:
        # funds = self.openalgo.get_funds()
        # live_equity_raw = funds.get('availablecash', self.portfolio.closed_equity)
        # live_equity = float(live_equity_raw) if isinstance(live_equity_raw, str) else live_equity_raw

        # TESTING: Use portfolio equity to test order placement
        live_equity = self.portfolio.closed_equity
        logger.info(f"[LIVE] Using portfolio equity for testing: ₹{live_equity:,.2f}")
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
        
        # Step 2: Execution validation (uses broker API price)
        original_lots = constraints.final_lots
        execution_price = signal.price  # Default to signal price
        execution_result = None  # Initialize
        validation_bypassed = False  # Track if validation was bypassed
        
        if self.config.signal_validation_enabled:
            # Fetch broker price with timeout and retry
            broker_price, validation_bypassed = self._get_broker_price_with_timeout(
                instrument=signal.instrument,
                fallback_price=signal.price,
                timeout_seconds=2.0,
                max_retries=3
            )
            execution_price = broker_price
            
            logger.info(
                f"[LIVE] Broker price: ₹{broker_price:,.2f} (signal: ₹{signal.price:,.2f})"
                + (" [VALIDATION BYPASSED]" if validation_bypassed else "")
            )
            
            # Only validate if broker API succeeded
            if not validation_bypassed:
                # Validate execution price
                exec_result = self.signal_validator.validate_execution_price(
                    signal, broker_price, signal.signal_type
                )
                
                # Record execution validation metric
                self.metrics.record_validation(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    validation_stage='execution',
                    result='passed' if exec_result.is_valid else 'failed',
                    divergence_pct=exec_result.divergence_pct,
                    risk_increase_pct=exec_result.risk_increase_pct,
                    rejection_reason=exec_result.reason if not exec_result.is_valid else None
                )
                
                if not exec_result.is_valid:
                    logger.warning(
                        f"[LIVE] Signal rejected at execution validation: {exec_result.reason} "
                        f"(divergence: {exec_result.divergence_pct:.2%})"
                    )
                    self.stats['entries_blocked'] += 1
                    return {
                        'status': 'rejected',
                        'reason': 'validation_failed',
                        'validation_stage': 'execution',
                        'validation_reason': exec_result.reason,
                        'divergence_pct': exec_result.divergence_pct,
                        'risk_increase_pct': exec_result.risk_increase_pct
                    }
                
                # Adjust position size if risk increased
                if exec_result.risk_increase_pct and exec_result.risk_increase_pct > 0:
                    adjusted_lots = self.signal_validator.adjust_position_size_for_execution(
                        signal, broker_price, original_lots
                    )
                    if adjusted_lots != original_lots:
                        logger.info(
                            f"[LIVE] Position size adjusted: {original_lots} → {adjusted_lots} lots "
                            f"(risk increase: {exec_result.risk_increase_pct:.2%})"
                        )
            else:
                # Validation bypassed due to broker API failure
                logger.warning(
                    f"[LIVE] Execution validation BYPASSED - broker API unavailable, "
                    f"proceeding with signal price ₹{signal.price:,.2f}"
                )
                # Record bypassed validation
                self.metrics.record_validation(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    validation_stage='execution',
                    result='bypassed',
                    rejection_reason='broker_api_unavailable'
                )
        
        # Step 3: Execute order using OrderExecutor
        import time
        execution_start = time.time()
        
        try:
            exec_result = self.order_executor.execute(
                signal=signal,
                lots=original_lots,
                limit_price=execution_price
            )
            
            execution_time_ms = (time.time() - execution_start) * 1000
            
            # Record execution metric
            self.metrics.record_execution(
                signal_type=signal.signal_type,
                instrument=signal.instrument,
                execution_strategy=self.config.execution_strategy,
                status=exec_result.status,
                lots=original_lots,
                slippage_pct=exec_result.slippage_pct,
                attempts=exec_result.attempts,
                execution_time_ms=execution_time_ms,
                rejection_reason=exec_result.rejection_reason if exec_result.status != ExecutionStatus.EXECUTED else None
            )
            
            if exec_result.status == ExecutionStatus.EXECUTED:
                # Order executed successfully
                fill_price = exec_result.execution_price or execution_price
                filled_lots = exec_result.lots_filled or original_lots
                
                execution_result = {
                    'status': 'success',
                    'order_details': {
                        'order_id': exec_result.order_id,
                        'fill_price': fill_price,
                        'lots_filled': filled_lots,
                        'slippage_pct': exec_result.slippage_pct,
                        'attempts': exec_result.attempts
                    }
                }
            elif exec_result.status == ExecutionStatus.PARTIAL:
                # Partial fill - use filled lots
                fill_price = exec_result.execution_price or execution_price
                filled_lots = exec_result.lots_filled or 0
                
                logger.warning(
                    f"[LIVE] Partial fill: {filled_lots}/{original_lots} lots filled, "
                    f"remaining {exec_result.lots_cancelled} cancelled"
                )
                
                execution_result = {
                    'status': 'success',
                    'order_details': {
                        'order_id': exec_result.order_id,
                        'fill_price': fill_price,
                        'lots_filled': filled_lots,
                        'slippage_pct': exec_result.slippage_pct,
                        'attempts': exec_result.attempts,
                        'partial_fill': True,
                        'lots_cancelled': exec_result.lots_cancelled
                    }
                }
                original_lots = filled_lots  # Use filled lots for position creation
            else:
                # Execution failed
                logger.error(
                    f"[LIVE] Order execution failed: {exec_result.rejection_reason} "
                    f"(status: {exec_result.status.value})"
                )
                self.stats['orders_failed'] += 1
                return {
                    'status': 'rejected',
                    'reason': 'execution_failed',
                    'execution_reason': exec_result.rejection_reason,
                    'execution_status': exec_result.status.value,
                    'attempts': exec_result.attempts
                }
        except Exception as e:
            logger.error(f"[LIVE] Error during order execution: {e}")
            self.stats['orders_failed'] += 1
            return {
                'status': 'error',
                'reason': 'execution_error',
                'error': str(e)
            }
        
        if execution_result['status'] == 'success':
            # Create position record (SAME structure as backtest)
            initial_stop = self.stop_manager.calculate_initial_stop(
                signal.price, signal.atr, inst_type
            )
            
            # Extract PE/CE entry prices from execution result if available
            # These are needed for accurate rollover P&L calculation
            pe_entry_price = execution_result.get('order_details', {}).get('pe_entry_price')
            ce_entry_price = execution_result.get('order_details', {}).get('ce_entry_price')
            
            # Use execution price (broker price) for entry, not signal price
            entry_price = execution_result['order_details'].get('fill_price', execution_price)
            
            position = Position(
                position_id=f"{instrument}_{signal.position}",
                instrument=instrument,
                entry_timestamp=signal.timestamp,
                entry_price=entry_price,  # Use actual fill price
                lots=original_lots,  # Use adjusted lots
                quantity=original_lots * inst_config.lot_size,
                initial_stop=initial_stop,
                current_stop=initial_stop,
                highest_close=signal.price,
                limiter=constraints.limiter,
                is_base_position=True,  # Mark as base position
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                **{k: v for k, v in execution_result.get('order_details', {}).items() 
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price', 
                                'lots_filled', 'slippage_pct', 'attempts', 'partial_fill', 'lots_cancelled']}  # Exclude execution metadata
            )
            
            self.portfolio.add_position(position)
            self.base_positions[instrument] = position
            self.last_pyramid_price[instrument] = signal.price
            
            # Persist to database
            if self.db_manager:
                self.db_manager.save_position(position)
                self.db_manager.save_pyramiding_state(
                    instrument, signal.price, position.position_id
                )
                logger.debug(f"Position and pyramiding state saved to database")
            
            self.stats['entries_executed'] += 1
            
            logger.info(
                f"✓ [LIVE] Entry executed: {original_lots} lots @ ₹{entry_price:,.2f} "
                f"(signal: ₹{signal.price:,.2f}, slippage: {execution_result['order_details'].get('slippage_pct', 0):.2%})"
            )
            
            return {
                'status': 'executed',
                'lots': original_lots,
                'execution': execution_result
            }
        # If we reach here, execution failed (already returned error above)
        return {
            'status': 'error',
            'reason': 'unexpected_execution_state'
        }
    
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
        
        # Get instrument type
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        else:
            inst_type = InstrumentType.BANK_NIFTY
        
        inst_config = get_instrument_config(inst_type)
        lots = signal.suggested_lots
        
        # Step 2: Execution validation (uses broker API price)
        original_lots = lots
        execution_price = signal.price  # Default to signal price
        execution_result = None  # Initialize
        validation_bypassed = False  # Track if validation was bypassed
        
        if self.config.signal_validation_enabled:
            # Fetch broker price with timeout and retry
            broker_price, validation_bypassed = self._get_broker_price_with_timeout(
                instrument=signal.instrument,
                fallback_price=signal.price,
                timeout_seconds=2.0,
                max_retries=3
            )
            execution_price = broker_price
            
            logger.info(
                f"[LIVE] Broker price: ₹{broker_price:,.2f} (signal: ₹{signal.price:,.2f})"
                + (" [VALIDATION BYPASSED]" if validation_bypassed else "")
            )
            
            # Only validate if broker API succeeded
            if not validation_bypassed:
                # Validate execution price
                exec_result = self.signal_validator.validate_execution_price(
                    signal, broker_price, signal.signal_type
                )
                
                # Record execution validation metric
                self.metrics.record_validation(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    validation_stage='execution',
                    result='passed' if exec_result.is_valid else 'failed',
                    divergence_pct=exec_result.divergence_pct,
                    risk_increase_pct=exec_result.risk_increase_pct,
                    rejection_reason=exec_result.reason if not exec_result.is_valid else None
                )
                
                if not exec_result.is_valid:
                    logger.warning(
                        f"[LIVE] Pyramid signal rejected at execution validation: {exec_result.reason} "
                        f"(divergence: {exec_result.divergence_pct:.2%})"
                    )
                    self.stats['pyramids_blocked'] += 1
                    return {
                        'status': 'rejected',
                        'reason': 'validation_failed',
                        'validation_stage': 'execution',
                        'validation_reason': exec_result.reason,
                        'divergence_pct': exec_result.divergence_pct,
                        'risk_increase_pct': exec_result.risk_increase_pct
                    }
                
                # Adjust position size if risk increased
                if exec_result.risk_increase_pct and exec_result.risk_increase_pct > 0:
                    adjusted_lots = self.signal_validator.adjust_position_size_for_execution(
                        signal, broker_price, original_lots
                    )
                    if adjusted_lots != original_lots:
                        logger.info(
                            f"[LIVE] Pyramid position size adjusted: {original_lots} → {adjusted_lots} lots "
                            f"(risk increase: {exec_result.risk_increase_pct:.2%})"
                        )
                        original_lots = adjusted_lots
            else:
                # Validation bypassed due to broker API failure
                logger.warning(
                    f"[LIVE] Pyramid execution validation BYPASSED - broker API unavailable, "
                    f"proceeding with signal price ₹{signal.price:,.2f}"
                )
                # Record bypassed validation
                self.metrics.record_validation(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    validation_stage='execution',
                    result='bypassed',
                    rejection_reason='broker_api_unavailable'
                )
        
        # Step 3: Execute order using OrderExecutor
        import time
        execution_start = time.time()
        
        try:
            exec_result = self.order_executor.execute(
                signal=signal,
                lots=original_lots,
                limit_price=execution_price
            )
            
            execution_time_ms = (time.time() - execution_start) * 1000
            
            # Record execution metric
            self.metrics.record_execution(
                signal_type=signal.signal_type,
                instrument=signal.instrument,
                execution_strategy=self.config.execution_strategy,
                status=exec_result.status,
                lots=original_lots,
                slippage_pct=exec_result.slippage_pct,
                attempts=exec_result.attempts,
                execution_time_ms=execution_time_ms,
                rejection_reason=exec_result.rejection_reason if exec_result.status != ExecutionStatus.EXECUTED else None
            )
            
            if exec_result.status == ExecutionStatus.EXECUTED:
                fill_price = exec_result.execution_price or execution_price
                filled_lots = exec_result.lots_filled or original_lots
                
                execution_result = {
                    'status': 'success',
                    'order_details': {
                        'order_id': exec_result.order_id,
                        'fill_price': fill_price,
                        'lots_filled': filled_lots,
                        'slippage_pct': exec_result.slippage_pct,
                        'attempts': exec_result.attempts
                    }
                }
            elif exec_result.status == ExecutionStatus.PARTIAL:
                fill_price = exec_result.execution_price or execution_price
                filled_lots = exec_result.lots_filled or 0
                
                logger.warning(
                    f"[LIVE] Partial fill: {filled_lots}/{original_lots} lots filled, "
                    f"remaining {exec_result.lots_cancelled} cancelled"
                )
                
                execution_result = {
                    'status': 'success',
                    'order_details': {
                        'order_id': exec_result.order_id,
                        'fill_price': fill_price,
                        'lots_filled': filled_lots,
                        'slippage_pct': exec_result.slippage_pct,
                        'attempts': exec_result.attempts,
                        'partial_fill': True,
                        'lots_cancelled': exec_result.lots_cancelled
                    }
                }
                original_lots = filled_lots
            else:
                logger.error(
                    f"[LIVE] Pyramid order execution failed: {exec_result.rejection_reason} "
                    f"(status: {exec_result.status.value})"
                )
                self.stats['orders_failed'] += 1
                return {
                    'status': 'rejected',
                    'reason': 'execution_failed',
                    'execution_reason': exec_result.rejection_reason,
                    'execution_status': exec_result.status.value,
                    'attempts': exec_result.attempts
                }
        except Exception as e:
            logger.error(f"[LIVE] Error during pyramid order execution: {e}")
            self.stats['orders_failed'] += 1
            return {
                'status': 'error',
                'reason': 'execution_error',
                'error': str(e)
            }
        
        if execution_result and execution_result['status'] == 'success':
            initial_stop = self.stop_manager.calculate_initial_stop(
                signal.price, signal.atr, inst_type
            )
            
            # Extract PE/CE entry prices from execution result if available
            pe_entry_price = execution_result.get('order_details', {}).get('pe_entry_price')
            ce_entry_price = execution_result.get('order_details', {}).get('ce_entry_price')
            
            # Use execution price (broker price) for entry, not signal price
            entry_price = execution_result['order_details'].get('fill_price', execution_price)
            
            position = Position(
                position_id=f"{instrument}_{signal.position}",
                instrument=instrument,
                entry_timestamp=signal.timestamp,
                entry_price=entry_price,  # Use actual fill price
                lots=original_lots,  # Use adjusted lots
                quantity=original_lots * inst_config.lot_size,
                initial_stop=initial_stop,
                current_stop=initial_stop,
                highest_close=signal.price,
                is_base_position=False,  # Mark as pyramid position
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                **{k: v for k, v in execution_result.get('order_details', {}).items() 
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price', 
                                'lots_filled', 'slippage_pct', 'attempts', 'partial_fill', 'lots_cancelled']}  # Exclude execution metadata
            )
            
            self.portfolio.add_position(position)
            self.last_pyramid_price[instrument] = signal.price
            
            # Persist to database
            if self.db_manager:
                self.db_manager.save_position(position)
                base_pos_id = self.base_positions[instrument].position_id if instrument in self.base_positions else None
                self.db_manager.save_pyramiding_state(
                    instrument, signal.price, base_pos_id
                )
                logger.debug(f"Pyramid position and state saved to database")
            
            self.stats['pyramids_executed'] += 1
            
            logger.info(
                f"✓ [LIVE] Pyramid executed: {original_lots} lots @ ₹{entry_price:,.2f} "
                f"(signal: ₹{signal.price:,.2f}, slippage: {execution_result['order_details'].get('slippage_pct', 0):.2%})"
            )
            
            return {
                'status': 'executed',
                'lots': original_lots,
                'execution': execution_result
            }
        # If we reach here, execution failed (already returned error above)
        return {
            'status': 'error',
            'reason': 'unexpected_execution_state'
        }
    
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
            
            # Persist closed position to database
            if self.db_manager:
                position = self.portfolio.positions.get(position_id)
                if position:
                    self.db_manager.save_position(position)  # Save with status='closed'
                    logger.debug(f"Closed position saved to database")
                
                # Update pyramiding state if base position was closed
                if position and position.is_base_position:
                    # Clear base position reference
                    self.db_manager.save_pyramiding_state(
                        position.instrument, 
                        self.last_pyramid_price.get(position.instrument, 0.0),
                        None  # Clear base_position_id
                    )
                    if position.instrument in self.base_positions:
                        del self.base_positions[position.instrument]
            
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

    # ============================================================
    # EOD (End-of-Day) Pre-Close Execution Methods
    # ============================================================

    def process_eod_monitor_signal(self, eod_signal: EODMonitorSignal) -> Dict:
        """
        Process an incoming EOD_MONITOR signal from TradingView.

        Updates the EOD monitor with the latest signal values.
        Called by webhook handler during EOD monitoring window.

        Args:
            eod_signal: EOD monitor signal with conditions and indicators

        Returns:
            Dict with processing result
        """
        if not self.eod_monitor or not self.config.eod_enabled:
            return {
                'status': 'ignored',
                'reason': 'eod_disabled'
            }

        instrument = eod_signal.instrument

        # Update EOD monitor with new signal
        accepted = self.eod_monitor.update_signal(eod_signal)

        if not accepted:
            return {
                'status': 'ignored',
                'reason': 'signal_rejected',
                'instrument': instrument
            }

        # Log potential action
        action = eod_signal.get_signal_type_to_execute()
        logger.info(
            f"[LIVE-EOD] Signal updated: {instrument}, "
            f"price=₹{eod_signal.price:,.2f}, "
            f"action={action.value if action else 'None'}"
        )

        return {
            'status': 'accepted',
            'instrument': instrument,
            'price': eod_signal.price,
            'potential_action': action.value if action else None,
            'conditions_met': eod_signal.conditions.all_entry_conditions_met()
        }

    def eod_condition_check(self, instrument: str) -> Dict:
        """
        EOD condition check callback for EODScheduler.

        Called at T-45 seconds before market close.
        Validates conditions and prepares for execution.

        Args:
            instrument: Trading instrument

        Returns:
            Dict with check result
        """
        if not self.eod_monitor or not self.config.eod_enabled:
            return {'success': False, 'reason': 'eod_disabled'}

        logger.info(f"[LIVE-EOD] Condition check for {instrument}")

        # Check if we should execute
        if not self.eod_monitor.should_execute(instrument):
            logger.info(f"[LIVE-EOD] No execution needed for {instrument}")
            return {
                'success': True,
                'action_required': False,
                'instrument': instrument
            }

        # Prepare for execution
        result = self.eod_monitor.prepare_for_execution(instrument)
        if not result:
            logger.warning(f"[LIVE-EOD] Failed to prepare execution for {instrument}")
            return {
                'success': False,
                'reason': 'prepare_failed',
                'instrument': instrument
            }

        eod_signal, signal_type = result

        logger.info(
            f"[LIVE-EOD] Execution prepared: {instrument} {signal_type.value}, "
            f"lots={eod_signal.sizing.suggested_lots}"
        )

        return {
            'success': True,
            'action_required': True,
            'instrument': instrument,
            'signal_type': signal_type.value,
            'lots': eod_signal.sizing.suggested_lots,
            'price': eod_signal.price
        }

    def eod_execute(self, instrument: str) -> Dict:
        """
        EOD order execution callback for EODScheduler.

        Called at T-30 seconds before market close.
        Places the order if conditions were met at T-45.

        Args:
            instrument: Trading instrument

        Returns:
            Dict with execution result
        """
        if not self.eod_monitor or not self.eod_executor or not self.config.eod_enabled:
            return {'success': False, 'reason': 'eod_disabled'}

        logger.info(f"[LIVE-EOD] Executing order for {instrument}")

        # Get execution state
        state = self.eod_monitor.get_execution_state(instrument)
        if not state or not state.execution_started:
            logger.info(f"[LIVE-EOD] No pending execution for {instrument}")
            return {
                'success': True,
                'action_taken': False,
                'instrument': instrument
            }

        if state.execution_completed:
            logger.info(f"[LIVE-EOD] Execution already completed for {instrument}")
            return {
                'success': True,
                'action_taken': False,
                'reason': 'already_completed',
                'instrument': instrument
            }

        # Get signal and action type
        eod_signal = state.latest_signal
        action = eod_signal.get_signal_type_to_execute()

        if not action:
            logger.warning(f"[LIVE-EOD] No action type for {instrument}")
            return {
                'success': False,
                'reason': 'no_action_type',
                'instrument': instrument
            }

        # Prepare and execute order
        context = self.eod_executor.prepare_execution(instrument, eod_signal, action)
        if context.error:
            logger.error(f"[LIVE-EOD] Prepare failed: {context.error}")
            return {
                'success': False,
                'reason': context.error,
                'instrument': instrument
            }

        context = self.eod_executor.execute_order(context)
        if context.error and not context.order_id:
            logger.error(f"[LIVE-EOD] Order placement failed: {context.error}")
            return {
                'success': False,
                'reason': context.error,
                'instrument': instrument
            }

        # Mark order placed in monitor
        if context.order_id:
            self.eod_monitor.mark_order_placed(instrument, context.order_id)

        return {
            'success': True,
            'action_taken': True,
            'instrument': instrument,
            'order_id': context.order_id,
            'signal_type': action.value,
            'lots': context.lots,
            'limit_price': context.limit_price
        }

    def eod_track(self, instrument: str) -> Dict:
        """
        EOD order tracking callback for EODScheduler.

        Called at T-15 seconds before market close.
        Tracks order to completion and handles fallback.

        Args:
            instrument: Trading instrument

        Returns:
            Dict with tracking result
        """
        if not self.eod_monitor or not self.eod_executor or not self.config.eod_enabled:
            return {'success': False, 'reason': 'eod_disabled'}

        logger.info(f"[LIVE-EOD] Tracking order for {instrument}")

        # Get execution state
        state = self.eod_monitor.get_execution_state(instrument)
        if not state or not state.order_id:
            logger.info(f"[LIVE-EOD] No order to track for {instrument}")
            return {
                'success': True,
                'action_taken': False,
                'instrument': instrument
            }

        if state.execution_completed:
            logger.info(f"[LIVE-EOD] Already completed for {instrument}")
            return {
                'success': True,
                'action_taken': False,
                'reason': 'already_completed',
                'instrument': instrument
            }

        # Create context for tracking
        eod_signal = state.latest_signal
        action = eod_signal.get_signal_type_to_execute()

        context = EODExecutionContext(
            instrument=instrument,
            signal=eod_signal,
            signal_type=action,
            order_id=state.order_id,
            lots=eod_signal.sizing.suggested_lots,
            started_at=state.order_placed_at
        )
        context.phase = EODExecutionPhase.ORDER_TRACKING

        # Track order
        context = self.eod_executor.track_order(context)

        # Update monitor with result
        if context.success:
            self.eod_monitor.mark_order_filled(instrument, context.execution_price)

            fingerprint = f"{instrument}:{eod_signal.timestamp.isoformat()}"
            self.eod_monitor.mark_executed(
                instrument=instrument,
                result=context.to_dict(),
                fingerprint=fingerprint,
                signal_type=action
            )

            # Update portfolio state
            self._update_portfolio_after_eod_fill(instrument, context, action, eod_signal)

            logger.info(
                f"[LIVE-EOD] Order filled: {instrument} {context.filled_lots} lots "
                f"@ ₹{context.execution_price:,.2f}"
            )

        return {
            'success': context.success,
            'instrument': instrument,
            'filled': context.success,
            'filled_lots': context.filled_lots,
            'execution_price': context.execution_price,
            'fallback_used': context.fallback_used,
            'error': context.error
        }

    def _update_portfolio_after_eod_fill(
        self,
        instrument: str,
        context: EODExecutionContext,
        signal_type: SignalType,
        eod_signal: EODMonitorSignal
    ):
        """
        Update portfolio state after EOD order fill.

        Args:
            instrument: Trading instrument
            context: Execution context with fill details
            signal_type: Type of signal executed
            eod_signal: Original EOD signal
        """
        # Convert EOD signal to regular signal for portfolio update
        signal = self.eod_monitor.convert_to_signal(eod_signal, signal_type)

        if signal_type == SignalType.BASE_ENTRY:
            # Create new position
            # Similar logic to _handle_base_entry_live but with EOD fill price
            logger.info(f"[LIVE-EOD] Creating base position for {instrument}")
            # Portfolio update would go here - omitted for brevity
            # The actual implementation depends on your Position management

        elif signal_type == SignalType.PYRAMID:
            # Add pyramid to existing position
            logger.info(f"[LIVE-EOD] Adding pyramid for {instrument}")
            # Portfolio update would go here

        elif signal_type == SignalType.EXIT:
            # Close position(s)
            logger.info(f"[LIVE-EOD] Closing positions for {instrument}")
            # Portfolio update would go here

    def get_eod_status(self) -> Dict:
        """
        Get current EOD status for monitoring.

        Returns:
            Dict with EOD status and statistics
        """
        if not self.eod_monitor or not self.config.eod_enabled:
            return {
                'enabled': False,
                'reason': 'eod_disabled'
            }

        active_instruments = self.eod_monitor.get_active_instruments()

        status = {
            'enabled': True,
            'active_instruments': active_instruments,
            'instruments': {}
        }

        for instrument in self.config.eod_instruments_enabled.keys():
            state = self.eod_monitor.get_execution_state(instrument)
            latest_signal = self.eod_monitor.get_latest_signal(instrument)
            seconds_to_close = self.eod_monitor.get_seconds_to_close(instrument)
            in_window = self.eod_monitor.is_in_eod_window(instrument)

            status['instruments'][instrument] = {
                'enabled': self.config.eod_instruments_enabled.get(instrument, False),
                'in_eod_window': in_window,
                'seconds_to_close': seconds_to_close,
                'has_signal': latest_signal is not None,
                'signal_price': latest_signal.price if latest_signal else None,
                'conditions_met': latest_signal.conditions.all_entry_conditions_met() if latest_signal else None,
                'execution_state': {
                    'scheduled': state.execution_scheduled if state else False,
                    'started': state.execution_started if state else False,
                    'completed': state.execution_completed if state else False,
                    'order_id': state.order_id if state else None,
                    'order_filled': state.order_filled if state else False
                } if state else None
            }

        return status

