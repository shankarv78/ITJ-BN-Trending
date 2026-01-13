"""
Live Trading Engine

Uses same portfolio logic as backtest, but executes real trades via OpenAlgo
"""
import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime
from core.models import Signal, SignalType, Position, InstrumentType, EODMonitorSignal, EODPositionStatus, MarketDataSignal
from core.portfolio_state import PortfolioStateManager
from core.eod_monitor import EODMonitor
from core.eod_executor import EODExecutor, EODExecutionContext, EODExecutionPhase
from core.position_sizer import TomBassoPositionSizer
from core.pyramid_gate import PyramidGateController
from core.stop_manager import TomBassoStopManager
from core.config import PortfolioConfig, get_instrument_config
from core.signal_validator import SignalValidator, SignalValidationConfig, ValidationSeverity
from core.order_executor import OrderExecutor, SimpleLimitExecutor, ProgressiveExecutor, ExecutionStatus, SyntheticFuturesExecutor
from core.signal_validation_metrics import SignalValidationMetrics
from core.signal_audit_service import (
    SignalAuditService, SignalAuditRecord, SignalOutcome,
    ValidationResultData, SizingCalculationData, RiskAssessmentData, OrderExecutionData
)
from live.rollover_scanner import RolloverScanner, RolloverScanResult
from live.rollover_executor import RolloverExecutor, BatchRolloverResult

# Optional voice announcer
try:
    from core.voice_announcer import get_announcer
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False
    def get_announcer():
        return None

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
        db_manager = None,  # Optional DatabaseStateManager for persistence
        test_mode: bool = False,  # Test mode: place 1 lot, log actual calculated lots
        strategy_manager = None  # Optional StrategyManager for multi-strategy P&L tracking
    ):
        """
        Initialize live trading engine

        Args:
            initial_capital: Starting capital (or current equity)
            openalgo_client: OpenAlgo API client
            config: Portfolio configuration
            db_manager: Optional DatabaseStateManager for persistence
            test_mode: If True, place only 1 lot but log what actual lot would be
            strategy_manager: Optional StrategyManager for strategy-level P&L tracking
        """
        self.config = config or PortfolioConfig()
        self.db_manager = db_manager
        self.test_mode = test_mode
        self.strategy_manager = strategy_manager

        if test_mode:
            logger.warning("🧪 TEST MODE ENABLED: Orders will place 1 lot only, actual lots logged")

        # Initialize portfolio with database manager and strategy manager
        self.portfolio = PortfolioStateManager(
            initial_capital, self.config, db_manager, strategy_manager
        )
        self.stop_manager = TomBassoStopManager()
        self.pyramid_controller = PyramidGateController(self.portfolio, self.config)
        self.openalgo = openalgo_client

        # Position sizers per instrument (SAME as backtest)
        # Pass test_mode to enable min 1 lot for pyramid testing
        self.sizers = {
            InstrumentType.GOLD_MINI: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.GOLD_MINI),
                test_mode=self.test_mode
            ),
            InstrumentType.BANK_NIFTY: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.BANK_NIFTY),
                test_mode=self.test_mode
            ),
            InstrumentType.COPPER: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.COPPER),
                test_mode=self.test_mode
            ),
            InstrumentType.SILVER_MINI: TomBassoPositionSizer(
                get_instrument_config(InstrumentType.SILVER_MINI),
                test_mode=self.test_mode
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
            'rollover_cost_total': 0.0,
            'last_signal_timestamp': None  # Track when last webhook was received
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

        # Signal audit service for comprehensive signal logging
        self.audit_service: Optional[SignalAuditService] = None
        if db_manager:
            self.audit_service = SignalAuditService(db_manager)
            logger.info("[LIVE] Signal audit service initialized")

        # Order executor based on config
        if self.config.execution_strategy == "simple_limit":
            self.order_executor: OrderExecutor = SimpleLimitExecutor(openalgo_client=self.openalgo)
        else:  # progressive (default)
            self.order_executor: OrderExecutor = ProgressiveExecutor(openalgo_client=self.openalgo)

        # Symbol mapper and synthetic futures executor for Bank Nifty
        self.symbol_mapper = None
        self.synthetic_executor = None
        try:
            from core.symbol_mapper import get_symbol_mapper
            self.symbol_mapper = get_symbol_mapper()
            if self.symbol_mapper:
                self.synthetic_executor = SyntheticFuturesExecutor(
                    openalgo_client=self.openalgo,
                    symbol_mapper=self.symbol_mapper,
                    timeout_seconds=30,  # 30 second timeout for each leg
                    poll_interval_seconds=0.5
                )
                logger.info("[LIVE] SyntheticFuturesExecutor initialized for Bank Nifty 2-leg execution")
            else:
                logger.warning("[LIVE] SymbolMapper not initialized - synthetic futures disabled")
        except Exception as e:
            logger.warning(f"[LIVE] Failed to initialize synthetic executor: {e}")

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
            - broker_price: Mid-price (avg of bid/ask) from broker, or fallback_price if failed
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

                # Use mid-price (avg of bid/ask) for fair limit price
                bid = quote.get('bid')
                ask = quote.get('ask')
                ltp = quote.get('ltp', fallback_price)

                if bid and ask:
                    broker_price = (float(bid) + float(ask)) / 2
                    logger.debug(f"[LIVE] Mid-price: ₹{broker_price:,.2f} (bid={bid}, ask={ask})")
                else:
                    # Fall back to LTP if bid/ask not available
                    broker_price = float(ltp) if ltp else fallback_price
                    logger.debug(f"[LIVE] Using LTP (bid/ask unavailable): ₹{broker_price:,.2f}")
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

    # ============================================================
    # Signal Audit Logging
    # ============================================================

    def _log_signal_audit(
        self,
        signal: Signal,
        outcome: SignalOutcome,
        outcome_reason: Optional[str] = None,
        validation_data: Optional[Dict] = None,
        sizing_data: Optional[Dict] = None,
        risk_data: Optional[Dict] = None,
        order_data: Optional[Dict] = None,
        processing_start_time: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Log signal to audit trail (non-blocking, error-safe).

        Args:
            signal: The signal being processed
            outcome: SignalOutcome enum value
            outcome_reason: Human-readable reason for outcome
            validation_data: Dict with validation result details
            sizing_data: Dict with position sizing calculation
            risk_data: Dict with risk assessment
            order_data: Dict with order execution details
            processing_start_time: When processing started (for duration calc)

        Returns:
            Audit record ID if successful, None if failed or audit disabled
        """
        if not self.audit_service:
            return None

        try:
            # Calculate processing duration
            duration_ms = None
            if processing_start_time:
                duration_ms = int((datetime.now() - processing_start_time).total_seconds() * 1000)

            # Build structured data objects
            validation_result = None
            if validation_data:
                validation_result = ValidationResultData(
                    is_valid=validation_data.get('is_valid', False),
                    severity=validation_data.get('severity', 'NORMAL'),
                    signal_age_seconds=validation_data.get('signal_age_seconds'),
                    divergence_pct=validation_data.get('divergence_pct'),
                    reason=validation_data.get('reason')
                )

            sizing_calculation = None
            if sizing_data:
                sizing_calculation = SizingCalculationData(
                    equity_high=sizing_data.get('equity_high'),
                    risk_percent=sizing_data.get('risk_percent'),
                    stop_distance=sizing_data.get('stop_distance'),
                    atr=sizing_data.get('atr'),
                    efficiency_ratio=sizing_data.get('er'),
                    final_lots=sizing_data.get('lots'),
                    limiter=sizing_data.get('limiter')
                )

            risk_assessment = None
            if risk_data:
                risk_assessment = RiskAssessmentData(
                    pre_trade_risk_pct=risk_data.get('pre_trade_risk_pct'),
                    post_trade_risk_pct=risk_data.get('post_trade_risk_pct'),
                    margin_available=risk_data.get('margin_available'),
                    margin_required=risk_data.get('margin_required')
                )

            order_execution = None
            if order_data:
                order_execution = OrderExecutionData(
                    order_id=order_data.get('order_id'),
                    order_type=order_data.get('order_type'),
                    execution_status=order_data.get('status'),
                    signal_price=order_data.get('signal_price'),
                    execution_price=order_data.get('execution_price'),
                    fill_price=order_data.get('fill_price'),
                    slippage_pct=order_data.get('slippage_pct'),
                    error_message=order_data.get('error')
                )

            # Create fingerprint from signal
            fingerprint = f"{signal.instrument}:{signal.signal_type.value}:{signal.timestamp.isoformat()}"

            # Create audit record
            record = SignalAuditRecord(
                signal_fingerprint=fingerprint,
                instrument=signal.instrument,
                signal_type=signal.signal_type.value,
                position=signal.position,
                signal_timestamp=signal.timestamp,
                received_at=datetime.now(),
                outcome=outcome,
                outcome_reason=outcome_reason,
                validation_result=validation_result,
                sizing_calculation=sizing_calculation,
                risk_assessment=risk_assessment,
                order_execution=order_execution,
                processing_duration_ms=duration_ms
            )

            audit_id = self.audit_service.create_audit_record(record)
            if audit_id:
                logger.debug(f"[AUDIT] Signal logged: {outcome.value} - {signal.instrument} {signal.signal_type.value} (id={audit_id})")
            return audit_id

        except Exception as e:
            # Non-blocking: log error but don't fail signal processing
            logger.error(f"[AUDIT] Failed to log signal audit: {e}")
            return None

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
        # Track processing time for audit
        processing_start_time = datetime.now()

        # Optional: Verify leadership if coordinator provided
        # This provides additional protection if called directly (not via webhook)
        if coordinator and not coordinator.is_leader:
            logger.warning(f"[LIVE] Rejecting signal - not leader (instance: {coordinator.instance_id})")
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.REJECTED_VALIDATION,
                outcome_reason="not_leader",
                processing_start_time=processing_start_time
            )
            return {'status': 'rejected', 'reason': 'not_leader'}

        # EOD Deduplication: Check if this signal was already executed at EOD
        # This handles the case where:
        # - EOD pyramid executed at 23:54:30 (30 sec before close)
        # - Bar-close PYRAMID signal arrives at 23:55:00
        # - We should skip the bar-close signal to avoid duplicate execution
        if self.eod_monitor and self.config.eod_enabled:
            fingerprint = f"{signal.instrument}:{signal.timestamp.isoformat()}"
            if self.eod_monitor.was_executed_at_eod(
                signal.instrument,
                fingerprint,
                signal_type=signal.signal_type  # Pass signal type for type-specific dedup
            ):
                logger.info(
                    f"[LIVE] Skipping signal - already executed at EOD: "
                    f"{signal.signal_type.value} {signal.instrument}"
                )
                self._log_signal_audit(
                    signal=signal,
                    outcome=SignalOutcome.REJECTED_DUPLICATE,
                    outcome_reason="already_executed_at_eod",
                    processing_start_time=processing_start_time
                )
                return {
                    'status': 'skipped',
                    'reason': 'already_executed_at_eod',
                    'fingerprint': fingerprint
                }

        self.stats['signals_received'] += 1
        self.stats['last_signal_timestamp'] = datetime.now().isoformat()

        logger.info(f"[LIVE] Processing: {signal.signal_type.value} {signal.position} @ ₹{signal.price}")

        # Step 1: Condition validation (trusts TradingView signal price)
        # Skip validation in test mode for easier testing
        if self.test_mode:
            logger.info(f"🧪 [TEST MODE] Bypassing signal validation")

        if self.config.signal_validation_enabled and not self.test_mode:
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
                    f"[LIVE] Signal validation failed: {condition_result.reason} "
                    f"(age: {age_str}) - requesting user confirmation"
                )

                # Request user confirmation via dialog + voice
                announcer = get_announcer()
                execute_anyway = False

                if announcer:
                    details = f"Signal age: {age_str}"
                    execute_anyway = announcer.request_validation_confirmation(
                        instrument=signal.instrument,
                        signal_type=signal.signal_type.value,
                        rejection_reason=condition_result.reason,
                        details=details
                    )
                else:
                    logger.warning("[LIVE] No voice announcer available - auto-rejecting validation failure")

                if not execute_anyway:
                    logger.info(f"[LIVE] Signal rejected after user confirmation: {condition_result.reason}")
                    self._log_signal_audit(
                        signal=signal,
                        outcome=SignalOutcome.REJECTED_VALIDATION,
                        outcome_reason=f"condition_validation_failed: {condition_result.reason}",
                        validation_data={
                            'is_valid': False,
                            'severity': condition_result.severity.value if hasattr(condition_result.severity, 'value') else str(condition_result.severity),
                            'signal_age_seconds': condition_result.signal_age_seconds,
                            'reason': condition_result.reason
                        },
                        processing_start_time=processing_start_time
                    )
                    return {
                        'status': 'rejected',
                        'reason': 'validation_failed',
                        'validation_stage': 'condition',
                        'validation_reason': condition_result.reason,
                        'signal_age_seconds': condition_result.signal_age_seconds
                    }
                else:
                    logger.info(f"[LIVE] User approved execution despite validation failure: {condition_result.reason}")

            # Log validation severity if not normal
            if condition_result.severity.value != "normal":
                age_str = f"{condition_result.signal_age_seconds:.1f}s" if condition_result.signal_age_seconds is not None else "N/A"
                logger.info(
                    f"[LIVE] Signal condition validation passed with {condition_result.severity.value} severity "
                    f"(age: {age_str})"
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
        processing_start_time = datetime.now()
        instrument = signal.instrument

        # Get instrument type
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        elif instrument == "COPPER":
            inst_type = InstrumentType.COPPER
        elif instrument == "SILVER_MINI":
            inst_type = InstrumentType.SILVER_MINI
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

        # Use equity_high (Tom Basso high watermark) for position sizing
        # This maintains consistent position sizes during drawdowns
        live_equity = self.portfolio.equity_high
        logger.info(f"[LIVE] Using equity high for sizing: ₹{live_equity:,.2f} (closed: ₹{self.portfolio.closed_equity:,.2f})")
        available_margin = live_equity * 0.6  # Use 60% of equity as margin

        # Calculate position size (SAME as backtest)
        constraints = sizer.calculate_base_entry_size(
            signal,
            equity=live_equity,
            available_margin=available_margin
        )

        if constraints.final_lots == 0:
            self.stats['entries_blocked'] += 1
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.REJECTED_RISK,
                outcome_reason=f"zero_lots_calculated: limited by {constraints.limiter}",
                sizing_data={
                    'equity_high': live_equity,
                    'stop_distance': signal.price - signal.stop if signal.stop else None,
                    'atr': signal.atr,
                    'er': signal.efficiency_ratio,
                    'lots': 0,
                    'limiter': constraints.limiter
                },
                processing_start_time=processing_start_time
            )
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
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.REJECTED_RISK,
                outcome_reason=f"portfolio_gate_blocked: {gate_reason}",
                sizing_data={
                    'equity_high': live_equity,
                    'stop_distance': signal.price - signal.stop if signal.stop else None,
                    'atr': signal.atr,
                    'er': signal.efficiency_ratio,
                    'lots': constraints.final_lots,
                    'limiter': constraints.limiter
                },
                risk_data={
                    'margin_available': available_margin,
                    'margin_required': est_risk,
                    'reason': gate_reason
                },
                processing_start_time=processing_start_time
            )
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

            # Only validate if broker API succeeded AND not in test mode
            if not validation_bypassed and not self.test_mode:
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
                        f"[LIVE] Execution validation failed: {exec_result.reason} "
                        f"(divergence: {exec_result.divergence_pct:.2%}) - requesting user confirmation"
                    )

                    # Request user confirmation via dialog + voice
                    announcer = get_announcer()
                    execute_anyway = False

                    if announcer:
                        risk_str = f"{exec_result.risk_increase_pct:.1%}" if exec_result.risk_increase_pct is not None else "N/A"
                        details = (
                            f"Price divergence: {exec_result.divergence_pct:.1%}. "
                            f"Risk increase: {risk_str}"
                        )
                        execute_anyway = announcer.request_validation_confirmation(
                            instrument=signal.instrument,
                            signal_type=signal.signal_type.value,
                            rejection_reason=exec_result.reason,
                            details=details
                        )
                    else:
                        logger.warning("[LIVE] No voice announcer available - auto-rejecting validation failure")

                    if not execute_anyway:
                        self.stats['entries_blocked'] += 1
                        logger.info(f"[LIVE] Entry rejected after user confirmation: {exec_result.reason}")
                        return {
                            'status': 'rejected',
                            'reason': 'validation_failed',
                            'validation_stage': 'execution',
                            'validation_reason': exec_result.reason,
                            'divergence_pct': exec_result.divergence_pct,
                            'risk_increase_pct': exec_result.risk_increase_pct
                        }
                    else:
                        logger.info(f"[LIVE] User approved execution despite validation failure: {exec_result.reason}")
            elif self.test_mode:
                logger.info("🧪 [TEST MODE] Bypassing execution validation")
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

        # TEST MODE: Override lots to 1, but log original calculated lots
        calculated_lots = original_lots  # Store for logging
        if self.test_mode:
            logger.warning(
                f"🧪 [TEST MODE] {signal.instrument} BASE_ENTRY: "
                f"Calculated lots={calculated_lots}, executing with 1 lot only"
            )
            original_lots = 1

        # Voice announcement: Pre-trade (BASE_ENTRY)
        announcer = get_announcer()
        if announcer:
            announcer.announce_pre_trade(
                instrument=signal.instrument,
                position=signal.position,
                signal_type=signal.signal_type.value,
                lots=original_lots,
                price=execution_price,
                stop=signal.stop,
                risk_amount=est_risk,
                risk_percent=(est_risk / live_equity * 100) if live_equity > 0 else 0
            )

        try:
            # Route to appropriate executor based on instrument type
            if inst_type == InstrumentType.BANK_NIFTY:
                # ============================
                # BANK NIFTY: Use Synthetic Futures Executor (2-leg options)
                # ============================
                execution_result = self._execute_entry_openalgo(signal, original_lots, inst_type)
                execution_time_ms = (time.time() - execution_start) * 1000

                # Record execution metric for synthetic futures
                self.metrics.record_execution(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    execution_strategy='synthetic_futures',
                    status=ExecutionStatus.EXECUTED if execution_result.get('status') == 'success' else ExecutionStatus.REJECTED,
                    lots=original_lots,
                    slippage_pct=0.0,  # Synthetic futures don't track slippage the same way
                    attempts=1,
                    execution_time_ms=execution_time_ms,
                    rejection_reason=execution_result.get('error') if execution_result.get('status') != 'success' else None
                )

                if execution_result.get('status') != 'success':
                    # Execution failed
                    error_msg = execution_result.get('error', 'unknown_error')
                    logger.error(f"[LIVE] Bank Nifty synthetic execution failed: {error_msg}")
                    self.stats['orders_failed'] += 1

                    # Voice announcement: Error (repeats until acknowledged)
                    if announcer:
                        announcer.announce_error(
                            f"{signal.instrument} synthetic order rejected. {error_msg}",
                            error_type="execution"
                        )

                    return {
                        'status': 'rejected',
                        'reason': 'execution_failed',
                        'execution_reason': error_msg,
                        'execution_status': 'rejected',
                        'attempts': 1
                    }

                # Add fill_price to order_details for position creation compatibility
                if 'order_details' in execution_result:
                    # Use PE entry price as the fill price (or signal price as fallback)
                    pe_price = execution_result['order_details'].get('pe_entry_price', execution_price)
                    ce_price = execution_result['order_details'].get('ce_entry_price', execution_price)
                    # Average of PE and CE for synthetic position entry price
                    execution_result['order_details']['fill_price'] = execution_price
                    execution_result['order_details']['lots_filled'] = original_lots

            else:
                # ============================
                # GOLD MINI: Use Standard Order Executor
                # ============================
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

                    # Voice announcement: Error (repeats until acknowledged)
                    if announcer:
                        announcer.announce_error(
                            f"{signal.instrument} order rejected. {exec_result.rejection_reason}",
                            error_type="execution"
                        )

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

            # Voice announcement: Error (repeats until acknowledged)
            if announcer:
                announcer.announce_error(
                    f"{signal.instrument} execution error. {str(e)}",
                    error_type="execution"
                )

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

            # Extract strike for Bank Nifty synthetic positions
            strike = execution_result.get('order_details', {}).get('strike')

            position = Position(
                position_id=f"{instrument}_{signal.position}",
                instrument=instrument,
                entry_timestamp=signal.timestamp,
                entry_price=entry_price,  # For BN: synthetic price (Strike + CE - PE), for Gold: futures price
                lots=original_lots,  # Use adjusted lots (or 1 in test mode)
                quantity=original_lots * inst_config.lot_size,
                initial_stop=initial_stop,
                current_stop=initial_stop,
                highest_close=signal.price,
                limiter=constraints.limiter,
                is_base_position=True,  # Mark as base position
                strike=strike,  # ATM strike for Bank Nifty synthetic (None for Gold Mini)
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                is_test=self.test_mode,  # Mark as test position if in test mode
                original_lots=calculated_lots if self.test_mode else None,  # Store original calculated lots
                **{k: v for k, v in execution_result.get('order_details', {}).items()
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price', 'strike',
                                'lots_filled', 'slippage_pct', 'attempts', 'partial_fill', 'lots_cancelled',
                                'pe_order_id', 'ce_order_id', 'futures_order_id', 'expiry']}  # Exclude execution metadata
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

            # Voice announcement: Post-trade (BASE_ENTRY)
            if announcer:
                announcer.announce_trade_executed(
                    instrument=signal.instrument,
                    position=signal.position,
                    signal_type=signal.signal_type.value,
                    lots=original_lots,
                    price=entry_price,
                    order_id=execution_result['order_details'].get('order_id')
                )

            # Log successful base entry audit
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.PROCESSED,
                outcome_reason="base_entry_executed",
                sizing_data={
                    'equity_high': live_equity,
                    'stop_distance': signal.price - signal.stop if signal.stop else None,
                    'atr': signal.atr,
                    'er': signal.efficiency_ratio,
                    'lots': original_lots,
                    'limiter': constraints.limiter
                },
                risk_data={
                    'margin_available': available_margin,
                    'margin_required': est_risk,
                    'pre_trade_risk_pct': (est_risk / live_equity * 100) if live_equity > 0 else 0
                },
                order_data={
                    'order_id': execution_result['order_details'].get('order_id'),
                    'order_type': 'BASE_ENTRY',
                    'status': 'executed',
                    'signal_price': signal.price,
                    'execution_price': entry_price,
                    'fill_price': entry_price,
                    'slippage_pct': execution_result['order_details'].get('slippage_pct', 0)
                },
                processing_start_time=processing_start_time
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

        For Bank Nifty: Execute synthetic future (SELL PE + BUY CE) with rollback
        For Gold Mini: Execute futures contract

        Args:
            signal: Entry signal
            lots: Calculated lot size
            inst_type: Instrument type

        Returns:
            Execution result dict
        """
        logger.info(f"[OPENALGO] Executing {inst_type.value} entry: {lots} lots @ ₹{signal.price:,.2f}")

        if inst_type == InstrumentType.BANK_NIFTY:
            # ============================
            # BANK NIFTY: Synthetic Futures (2-leg with rollback)
            # ============================
            if not self.synthetic_executor:
                logger.error("[OPENALGO] SyntheticFuturesExecutor not initialized!")
                return {
                    'status': 'error',
                    'error': 'synthetic_executor_not_initialized'
                }

            # Execute synthetic futures entry
            result = self.synthetic_executor.execute_entry(
                instrument="BANK_NIFTY",
                lots=lots,
                current_price=signal.price
            )

            if result.status == ExecutionStatus.EXECUTED:
                # Use actual executed symbols - they contain all info (strike, expiry in the name)
                # Calculate synthetic futures entry price: Strike + CE - PE
                synthetic_price = result.get_synthetic_price()
                fill_price = synthetic_price if synthetic_price else signal.price

                return {
                    'status': 'success',
                    'order_details': {
                        'pe_order_id': result.pe_result.order_id if result.pe_result else None,
                        'ce_order_id': result.ce_result.order_id if result.ce_result else None,
                        'pe_entry_price': result.pe_result.fill_price if result.pe_result else signal.price,
                        'ce_entry_price': result.ce_result.fill_price if result.ce_result else signal.price,
                        'pe_symbol': result.pe_symbol,  # e.g., BANKNIFTY30DEC2560000PE
                        'ce_symbol': result.ce_symbol,  # e.g., BANKNIFTY30DEC2560000CE
                        'strike': result.strike,  # ATM strike used for synthetic
                        'fill_price': fill_price  # Synthetic futures entry price (Strike + CE - PE)
                    }
                }
            else:
                # Execution failed (possibly with rollback)
                error_msg = result.rejection_reason or "execution_failed"
                if result.rollback_performed:
                    if result.rollback_success:
                        error_msg += " (rollback_successful)"
                    else:
                        error_msg += " (ROLLBACK_FAILED_CRITICAL)"
                        logger.critical(f"[OPENALGO] CRITICAL: Bank Nifty rollback failed! {result.notes}")

                return {
                    'status': 'error',
                    'error': error_msg,
                    'notes': result.notes
                }

        else:
            # ============================
            # GOLD MINI: Simple Futures
            # ============================
            if not self.symbol_mapper:
                logger.error("[OPENALGO] SymbolMapper not initialized!")
                return {
                    'status': 'error',
                    'error': 'symbol_mapper_not_initialized'
                }

            # Translate symbol
            try:
                translated = self.symbol_mapper.translate(
                    instrument="GOLD_MINI",
                    action="BUY",
                    current_price=signal.price
                )
                # Gold Mini is single-leg futures, use first symbol
                futures_symbol = translated.symbols[0] if translated.symbols else None
                if not futures_symbol:
                    raise ValueError("No symbol generated for Gold Mini")
                expiry = translated.expiry_date.strftime("%Y-%m-%d") if translated.expiry_date else None
            except Exception as e:
                logger.error(f"[OPENALGO] Symbol translation failed: {e}")
                return {
                    'status': 'error',
                    'error': f'symbol_translation_failed: {e}'
                }

            logger.info(f"[OPENALGO] Gold Mini entry: {futures_symbol}")

            # Execute using standard order executor
            exec_result = self.order_executor.execute(
                signal=signal,
                lots=lots,
                limit_price=signal.price,
                action="BUY"
            )

            if exec_result.status == ExecutionStatus.EXECUTED:
                return {
                    'status': 'success',
                    'order_details': {
                        'futures_order_id': exec_result.order_id,
                        'fill_price': exec_result.execution_price,
                        'futures_symbol': futures_symbol,
                        'expiry': expiry
                    }
                }
            else:
                return {
                    'status': 'error',
                    'error': exec_result.rejection_reason or 'execution_failed'
                }

    def _handle_pyramid_live(self, signal: Signal) -> Dict:
        """Handle pyramid in live mode (SAME logic as backtest)"""
        processing_start_time = datetime.now()
        instrument = signal.instrument

        if instrument not in self.base_positions:
            self.stats['pyramids_blocked'] += 1
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.REJECTED_VALIDATION,
                outcome_reason="no_base_position_found",
                validation_data={
                    'is_valid': False,
                    'reason': f"No base position exists for {instrument}"
                },
                processing_start_time=processing_start_time
            )
            return {'status': 'blocked', 'reason': 'No base position'}

        base_pos = self.base_positions[instrument]
        last_pyr_price = self.last_pyramid_price.get(instrument, base_pos.entry_price)

        # Check pyramid gates (SAME as backtest) - BYPASSED in test mode
        if self.test_mode:
            logger.info(f"🧪 [TEST MODE] Bypassing pyramid gate check")
        else:
            gate_check = self.pyramid_controller.check_pyramid_allowed(
                signal, instrument, base_pos, last_pyr_price
            )

            if not gate_check.allowed:
                self.stats['pyramids_blocked'] += 1
                self._log_signal_audit(
                    signal=signal,
                    outcome=SignalOutcome.REJECTED_RISK,
                    outcome_reason=f"pyramid_gate_blocked: {gate_check.reason}",
                    risk_data={
                        'pre_trade_risk_pct': None,  # Could be calculated if needed
                        'reason': gate_check.reason
                    },
                    processing_start_time=processing_start_time
                )
                return {'status': 'blocked', 'reason': gate_check.reason}

        # Get instrument type
        if instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif instrument == "COPPER":
            inst_type = InstrumentType.COPPER
        elif instrument == "SILVER_MINI":
            inst_type = InstrumentType.SILVER_MINI
        else:
            inst_type = InstrumentType.BANK_NIFTY

        inst_config = get_instrument_config(inst_type)
        sizer = self.sizers[inst_type]

        # Calculate pyramid size using Tom Basso 3-constraint method
        # (Don't trust signal.suggested_lots from TradingView - PM calculates sizing)
        # Use equity_high for consistent sizing during drawdowns
        live_equity = self.portfolio.equity_high
        available_margin = live_equity * 0.6  # Use 60% of equity as margin

        # Calculate unrealized P&L for profit constraint
        unrealized_pnl = (signal.price - base_pos.entry_price) * base_pos.lots * inst_config.point_value

        # Base risk = original risk at entry
        base_risk = (base_pos.entry_price - base_pos.initial_stop) * base_pos.lots * inst_config.point_value

        # Profit after covering base risk
        profit_after_base_risk = max(0, unrealized_pnl - base_risk)

        # Calculate pyramid_count from signal.position (e.g., "Long_2" → PYR1 → pyramid_count=0)
        # Long_2 = PYR1 (first pyramid, pyramid_count=0 before this add)
        # Long_3 = PYR2 (second pyramid, pyramid_count=1 before this add)
        try:
            position_num = int(signal.position.split('_')[-1])
            pyramid_count = position_num - 2  # Long_2 → 0, Long_3 → 1, etc.
            pyramid_count = max(0, pyramid_count)
        except (ValueError, IndexError):
            pyramid_count = 0
            logger.warning(f"Could not parse pyramid count from position '{signal.position}', defaulting to 0")

        constraints = sizer.calculate_pyramid_size(
            signal=signal,
            equity=live_equity,
            available_margin=available_margin,
            base_position_size=base_pos.lots,
            profit_after_base_risk=profit_after_base_risk,
            pyramid_count=pyramid_count
        )

        if constraints.final_lots == 0:
            self.stats['pyramids_blocked'] += 1
            logger.info(
                f"[LIVE] Pyramid blocked: 0 lots (limited by {constraints.limiter}). "
                f"Base lots={base_pos.lots}, P&L=₹{unrealized_pnl:,.0f}, "
                f"Base risk=₹{base_risk:,.0f}, Excess profit=₹{profit_after_base_risk:,.0f}"
            )
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.REJECTED_RISK,
                outcome_reason=f"zero_lots_calculated: limited by {constraints.limiter}",
                sizing_data={
                    'equity_high': live_equity,
                    'risk_percent': constraints.risk_percent if hasattr(constraints, 'risk_percent') else None,
                    'stop_distance': signal.price - signal.stop if signal.stop else None,
                    'atr': signal.atr,
                    'er': signal.efficiency_ratio,
                    'lots': 0,
                    'limiter': constraints.limiter
                },
                risk_data={
                    'pre_trade_risk_pct': None,
                    'margin_available': available_margin,
                    'reason': f"Base lots={base_pos.lots}, P&L={unrealized_pnl:.0f}, Excess profit={profit_after_base_risk:.0f}"
                },
                processing_start_time=processing_start_time
            )
            return {
                'status': 'blocked',
                'reason': f'Zero lots (limited by {constraints.limiter})'
            }

        lots = constraints.final_lots
        logger.info(
            f"[LIVE] Pyramid size calculated: {lots} lots (limited by {constraints.limiter}). "
            f"Signal suggested {signal.suggested_lots} lots. "
            f"Base={base_pos.lots}, P&L=₹{unrealized_pnl:,.0f}"
        )

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
                        f"[LIVE] Pyramid execution validation failed: {exec_result.reason} "
                        f"(divergence: {exec_result.divergence_pct:.2%}) - requesting user confirmation"
                    )

                    # Request user confirmation via dialog + voice
                    announcer = get_announcer()
                    execute_anyway = False

                    if announcer:
                        risk_str = f"{exec_result.risk_increase_pct:.1%}" if exec_result.risk_increase_pct is not None else "N/A"
                        details = (
                            f"Price divergence: {exec_result.divergence_pct:.1%}. "
                            f"Risk increase: {risk_str}"
                        )
                        execute_anyway = announcer.request_validation_confirmation(
                            instrument=signal.instrument,
                            signal_type=signal.signal_type.value,
                            rejection_reason=exec_result.reason,
                            details=details
                        )
                    else:
                        logger.warning("[LIVE] No voice announcer available - auto-rejecting validation failure")

                    if not execute_anyway:
                        self.stats['pyramids_blocked'] += 1
                        logger.info(f"[LIVE] Pyramid rejected after user confirmation: {exec_result.reason}")
                        return {
                            'status': 'rejected',
                            'reason': 'validation_failed',
                            'validation_stage': 'execution',
                            'validation_reason': exec_result.reason,
                            'divergence_pct': exec_result.divergence_pct,
                            'risk_increase_pct': exec_result.risk_increase_pct
                        }
                    else:
                        logger.info(f"[LIVE] User approved pyramid despite validation failure: {exec_result.reason}")

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

        # TEST MODE: Override lots to 1, but log original calculated lots
        calculated_lots = original_lots  # Store for logging
        if self.test_mode:
            logger.warning(
                f"🧪 [TEST MODE] {signal.instrument} PYRAMID: "
                f"Calculated lots={calculated_lots}, executing with 1 lot only"
            )
            original_lots = 1

        # Calculate risk for announcement (variables needed by announcer)
        est_risk = (execution_price - signal.stop) * original_lots * inst_config.point_value
        live_equity = self.portfolio.equity_high  # Use equity_high for consistent risk %

        # Voice announcement: Pre-trade (PYRAMID)
        announcer = get_announcer()
        if announcer:
            announcer.announce_pre_trade(
                instrument=signal.instrument,
                position=signal.position,
                signal_type=signal.signal_type.value,
                lots=original_lots,
                price=execution_price,
                stop=signal.stop,
                risk_amount=est_risk,
                risk_percent=(est_risk / live_equity * 100) if live_equity > 0 else 0
            )

        try:
            # Route to appropriate executor based on instrument type
            if inst_type == InstrumentType.BANK_NIFTY:
                # ============================
                # BANK NIFTY: Use Synthetic Futures Executor (2-leg options)
                # ============================
                execution_result = self._execute_entry_openalgo(signal, original_lots, inst_type)
                execution_time_ms = (time.time() - execution_start) * 1000

                # Record execution metric for synthetic futures
                self.metrics.record_execution(
                    signal_type=signal.signal_type,
                    instrument=signal.instrument,
                    execution_strategy='synthetic_futures',
                    status=ExecutionStatus.EXECUTED if execution_result.get('status') == 'success' else ExecutionStatus.REJECTED,
                    lots=original_lots,
                    slippage_pct=0.0,
                    attempts=1,
                    execution_time_ms=execution_time_ms,
                    rejection_reason=execution_result.get('error') if execution_result.get('status') != 'success' else None
                )

                if execution_result.get('status') != 'success':
                    error_msg = execution_result.get('error', 'unknown_error')
                    logger.error(f"[LIVE] Bank Nifty pyramid synthetic execution failed: {error_msg}")
                    self.stats['orders_failed'] += 1

                    if announcer:
                        announcer.announce_error(
                            f"{signal.instrument} pyramid synthetic order rejected. {error_msg}",
                            error_type="execution"
                        )

                    return {
                        'status': 'rejected',
                        'reason': 'execution_failed',
                        'execution_reason': error_msg,
                        'execution_status': 'rejected',
                        'attempts': 1
                    }

                # Add fill_price for position update compatibility
                if 'order_details' in execution_result:
                    execution_result['order_details']['fill_price'] = execution_price
                    execution_result['order_details']['lots_filled'] = original_lots

            else:
                # ============================
                # GOLD MINI: Use Standard Order Executor
                # ============================
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

                    # Voice announcement: Error (repeats until acknowledged)
                    if announcer:
                        announcer.announce_error(
                            f"{signal.instrument} pyramid order rejected. {exec_result.rejection_reason}",
                            error_type="execution"
                        )

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

            # Voice announcement: Error (repeats until acknowledged)
            if announcer:
                announcer.announce_error(
                    f"{signal.instrument} pyramid execution error. {str(e)}",
                    error_type="execution"
                )

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
            # For BN: This is synthetic price (Strike + CE - PE), for Gold: futures price
            entry_price = execution_result['order_details'].get('fill_price', execution_price)

            # Extract strike for Bank Nifty synthetic positions
            strike = execution_result.get('order_details', {}).get('strike')

            position = Position(
                position_id=f"{instrument}_{signal.position}",
                instrument=instrument,
                entry_timestamp=signal.timestamp,
                entry_price=entry_price,  # For BN: synthetic price (Strike + CE - PE), for Gold: futures price
                lots=original_lots,  # Use adjusted lots (or 1 in test mode)
                quantity=original_lots * inst_config.lot_size,
                initial_stop=initial_stop,
                current_stop=initial_stop,
                highest_close=signal.price,
                is_base_position=False,  # Mark as pyramid position
                strike=strike,  # ATM strike for Bank Nifty synthetic (None for Gold Mini)
                pe_entry_price=pe_entry_price,  # Store for rollover P&L calculation
                ce_entry_price=ce_entry_price,  # Store for rollover P&L calculation
                is_test=self.test_mode,  # Mark as test position if in test mode
                original_lots=calculated_lots if self.test_mode else None,  # Store original calculated lots
                **{k: v for k, v in execution_result.get('order_details', {}).items()
                   if k not in ['pe_entry_price', 'ce_entry_price', 'order_id', 'fill_price', 'strike',
                                'lots_filled', 'slippage_pct', 'attempts', 'partial_fill', 'lots_cancelled',
                                'pe_order_id', 'ce_order_id', 'futures_order_id', 'expiry']}  # Exclude execution metadata
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

            # Voice announcement: Post-trade (PYRAMID)
            if announcer:
                announcer.announce_trade_executed(
                    instrument=signal.instrument,
                    position=signal.position,
                    signal_type=signal.signal_type.value,
                    lots=original_lots,
                    price=entry_price,
                    order_id=execution_result['order_details'].get('order_id')
                )

            # Log successful pyramid audit
            self._log_signal_audit(
                signal=signal,
                outcome=SignalOutcome.PROCESSED,
                outcome_reason="pyramid_executed",
                sizing_data={
                    'equity_high': live_equity,
                    'stop_distance': signal.price - signal.stop if signal.stop else None,
                    'atr': signal.atr,
                    'er': signal.efficiency_ratio,
                    'lots': original_lots,
                    'limiter': constraints.limiter
                },
                order_data={
                    'order_id': execution_result['order_details'].get('order_id'),
                    'order_type': 'PYRAMID',
                    'status': 'executed',
                    'signal_price': signal.price,
                    'execution_price': entry_price,
                    'fill_price': entry_price,
                    'slippage_pct': execution_result['order_details'].get('slippage_pct', 0)
                },
                processing_start_time=processing_start_time
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
        # Handle "EXIT ALL" - close all positions for this instrument
        if signal.position.upper() == "ALL":
            return self._handle_exit_all_live(signal)

        position_id = f"{signal.instrument}_{signal.position}"

        if position_id not in self.portfolio.positions:
            logger.warning(
                f"[TV-EXIT] Position {position_id} not found in portfolio. "
                f"Available: {list(self.portfolio.positions.keys())}"
            )
            return {'status': 'error', 'reason': 'Position not found'}

        # Get position details for announcement
        position = self.portfolio.positions[position_id]

        # ISSUE-001 FIX: Check if position is already closing/closed (prevents double exits)
        # This matches the logic in _execute_pm_initiated_exit()
        if position.status in ['closing', 'closed']:
            logger.info(
                f"[TV-EXIT] {position_id} already {position.status}, skipping "
                f"(prevents race with PM-initiated exit)"
            )
            return {'status': 'skipped', 'reason': f'already_{position.status}'}

        # Voice announcement: Pre-trade (EXIT)
        announcer = get_announcer()
        if announcer:
            announcer.announce_pre_trade(
                instrument=signal.instrument,
                position=signal.position,
                signal_type="EXIT",
                lots=position.lots,
                price=signal.price,
                stop=0,  # No stop for exit
                risk_amount=0,
                risk_percent=0
            )

        # Execute exit via OpenAlgo
        execution_result = self._execute_exit_openalgo(position)

        if execution_result['status'] == 'success':
            # Close position using ACTUAL fill price, not signal price
            actual_exit_price = execution_result['order_details'].get('exit_price', signal.price)
            pnl = self.portfolio.close_position(position_id, actual_exit_price, signal.timestamp)

            # Persist closed position to database
            if self.db_manager:
                closed_position = self.portfolio.positions.get(position_id)
                if closed_position:
                    # Set exit reason from signal (e.g., STOP_LOSS, EOD)
                    closed_position.exit_reason = signal.reason or 'SIGNAL'
                    self.db_manager.save_position(closed_position)  # Save with status='closed'
                    logger.debug(f"Closed position saved to database")

                # Update pyramiding state if base position was closed
                if closed_position and closed_position.is_base_position:
                    # Clear base position reference
                    self.db_manager.save_pyramiding_state(
                        closed_position.instrument,
                        self.last_pyramid_price.get(closed_position.instrument, 0.0),
                        None  # Clear base_position_id
                    )
                    if closed_position.instrument in self.base_positions:
                        del self.base_positions[closed_position.instrument]

            self.stats['exits_executed'] += 1

            # Voice announcement: Post-trade (EXIT)
            if announcer:
                announcer.announce_trade_executed(
                    instrument=signal.instrument,
                    position=signal.position,
                    signal_type="EXIT",
                    lots=position.lots,
                    price=signal.price,
                    pnl=pnl
                )

            return {'status': 'executed', 'pnl': pnl}
        else:
            # Voice announcement: Error
            if announcer:
                announcer.announce_error(
                    f"{signal.instrument} exit failed. {execution_result.get('reason', 'Unknown error')}",
                    error_type="execution"
                )
            return execution_result

    def _handle_exit_all_live(self, signal: Signal) -> Dict:
        """Handle EXIT ALL - close all positions for an instrument"""
        # Find all open positions for this instrument
        positions_to_close = [
            (pos_id, pos) for pos_id, pos in self.portfolio.positions.items()
            if pos.instrument == signal.instrument and pos.status == "open"
        ]

        if not positions_to_close:
            return {'status': 'error', 'reason': f'No open positions found for {signal.instrument}'}

        logger.info(f"[LIVE] EXIT ALL: Closing {len(positions_to_close)} positions for {signal.instrument}")

        total_pnl = 0.0
        failed_exits = []

        for position_id, position in positions_to_close:
            # Execute exit via OpenAlgo
            execution_result = self._execute_exit_openalgo(position)

            if execution_result['status'] == 'success':
                # Close position using ACTUAL fill price, not signal price
                actual_exit_price = execution_result['order_details'].get('exit_price', signal.price)
                pnl = self.portfolio.close_position(position_id, actual_exit_price, signal.timestamp)
                total_pnl += pnl

                # Persist to database
                if self.db_manager:
                    closed_position = self.portfolio.positions.get(position_id)
                    if closed_position:
                        closed_position.exit_reason = signal.reason or 'EXIT_ALL'
                        self.db_manager.save_position(closed_position)

                        # Clear base_positions if this was a base position
                        if closed_position.is_base_position:
                            if closed_position.instrument in self.base_positions:
                                del self.base_positions[closed_position.instrument]
                                logger.info(f"[LIVE] EXIT ALL: Cleared base position for {closed_position.instrument}")
                            # Also clear pyramiding state in DB
                            self.db_manager.save_pyramiding_state(
                                closed_position.instrument,
                                self.last_pyramid_price.get(closed_position.instrument, 0.0),
                                None  # Clear base_position_id
                            )

                logger.info(f"[LIVE] EXIT ALL: Closed {position_id}, P&L: ₹{pnl:,.2f}")
            else:
                failed_exits.append((position_id, execution_result.get('reason', 'unknown')))

        if failed_exits:
            logger.error(f"[LIVE] EXIT ALL: {len(failed_exits)} exits failed: {failed_exits}")

        # Update stats
        self.stats['exits_executed'] += len(positions_to_close) - len(failed_exits)

        # Voice announcement
        announcer = get_announcer()
        if announcer:
            announcer.announce_trade_executed(
                instrument=signal.instrument,
                position="ALL",
                signal_type="EXIT",
                lots=sum(pos.lots for _, pos in positions_to_close),
                price=signal.price,
                pnl=total_pnl
            )

        return {
            'status': 'executed' if not failed_exits else 'partial',
            'pnl': total_pnl,
            'positions_closed': len(positions_to_close) - len(failed_exits),
            'failed': failed_exits
        }

    def _execute_exit_openalgo(self, position: Position) -> Dict:
        """
        Execute exit via OpenAlgo API

        For Bank Nifty: Close synthetic future (BUY PE + SELL CE) with rollback
        For Gold Mini: Sell futures contract

        Args:
            position: Position to exit

        Returns:
            Execution result dict
        """
        logger.info(f"[OPENALGO] Executing exit: {position.position_id}, {position.lots} lots")

        # Derive instrument type from position.instrument string
        if position.instrument == "BANK_NIFTY":
            inst_type = InstrumentType.BANK_NIFTY
        elif position.instrument == "GOLD_MINI":
            inst_type = InstrumentType.GOLD_MINI
        elif position.instrument == "COPPER":
            inst_type = InstrumentType.COPPER
        elif position.instrument == "SILVER_MINI":
            inst_type = InstrumentType.SILVER_MINI
        else:
            inst_type = InstrumentType.BANK_NIFTY  # Default fallback

        if inst_type == InstrumentType.BANK_NIFTY:
            # ============================
            # BANK NIFTY: Close Synthetic Futures (2-leg with rollback)
            # ============================
            if not self.synthetic_executor:
                logger.error("[OPENALGO] SyntheticFuturesExecutor not initialized!")
                return {
                    'status': 'error',
                    'error': 'synthetic_executor_not_initialized'
                }

            # Get stored symbols from position (direct fields on Position object)
            pe_symbol = getattr(position, 'pe_symbol', None)
            ce_symbol = getattr(position, 'ce_symbol', None)

            # CRITICAL: We MUST have stored symbols for exit
            # Without them, we cannot close the correct positions - would create naked exposure!
            if not (pe_symbol and ce_symbol):
                logger.critical(
                    f"[OPENALGO] CRITICAL: Missing stored symbols for {position.position_id}! "
                    f"PE={pe_symbol}, CE={ce_symbol}. Cannot exit safely - manual intervention required!"
                )
                return {
                    'status': 'error',
                    'error': 'missing_stored_symbols_critical',
                    'notes': f"Position {position.position_id} has no stored PE/CE symbols. Manual exit required."
                }

            logger.info(f"[OPENALGO] BN Exit: PE={pe_symbol}, CE={ce_symbol}, lots={position.lots}")

            # Execute synthetic futures exit using stored symbols
            # current_price is not used when pe_symbol/ce_symbol are provided
            result = self.synthetic_executor.execute_exit(
                instrument="BANK_NIFTY",
                lots=position.lots,
                current_price=0,  # Not used when symbols are provided
                pe_symbol=pe_symbol,
                ce_symbol=ce_symbol
            )

            if result.status == ExecutionStatus.EXECUTED:
                # Calculate synthetic exit price from actual leg fills
                synthetic_exit_price = result.get_synthetic_price()
                pe_exit = result.pe_result.fill_price if result.pe_result else None
                ce_exit = result.ce_result.fill_price if result.ce_result else None

                logger.info(
                    f"[OPENALGO] BN Exit fills - PE: ₹{pe_exit}, CE: ₹{ce_exit}, "
                    f"Synthetic: ₹{synthetic_exit_price:,.2f}" if synthetic_exit_price else
                    f"[OPENALGO] BN Exit fills - PE: ₹{pe_exit}, CE: ₹{ce_exit}"
                )

                return {
                    'status': 'success',
                    'order_details': {
                        'pe_order_id': result.pe_result.order_id if result.pe_result else None,
                        'ce_order_id': result.ce_result.order_id if result.ce_result else None,
                        'pe_exit_price': pe_exit,
                        'ce_exit_price': ce_exit,
                        'exit_price': synthetic_exit_price  # Critical: Used for P&L calculation
                    }
                }
            else:
                error_msg = result.rejection_reason or "exit_execution_failed"
                if result.rollback_performed:
                    if result.rollback_success:
                        error_msg += " (rollback_successful)"
                    else:
                        error_msg += " (ROLLBACK_FAILED_CRITICAL)"
                        logger.critical(f"[OPENALGO] CRITICAL: Bank Nifty exit rollback failed! {result.notes}")

                return {
                    'status': 'error',
                    'error': error_msg,
                    'notes': result.notes
                }

        else:
            # ============================
            # MCX FUTURES: Sell Futures (Gold Mini, Copper, etc.)
            # ============================
            if not self.symbol_mapper:
                logger.error("[OPENALGO] SymbolMapper not initialized!")
                return {
                    'status': 'error',
                    'error': 'symbol_mapper_not_initialized'
                }

            # Get current price for exit - use mid-price (avg of bid/ask) for fair limit
            exit_price = position.entry_price
            try:
                quote = self.openalgo.get_quote(position.instrument)
                bid = quote.get('bid') or quote.get('ltp')
                ask = quote.get('ask') or quote.get('ltp')
                if bid and ask:
                    exit_price = (float(bid) + float(ask)) / 2  # Mid-price
                else:
                    exit_price = quote.get('ltp', position.entry_price)
                logger.debug(f"[OPENALGO] Exit price: mid={exit_price:.2f} (bid={bid}, ask={ask})")
            except Exception as e:
                logger.warning(f"[OPENALGO] Could not fetch exit price: {e}")

            # Translate symbol
            try:
                translated = self.symbol_mapper.translate(
                    instrument=position.instrument,
                    action="SELL",
                    current_price=exit_price
                )
                # MCX futures are single-leg, use first symbol
                futures_symbol = translated.symbols[0] if translated.symbols else None
                if not futures_symbol:
                    raise ValueError(f"No symbol generated for {position.instrument}")
            except Exception as e:
                logger.error(f"[OPENALGO] Symbol translation failed: {e}")
                return {
                    'status': 'error',
                    'error': f'symbol_translation_failed: {e}'
                }

            logger.info(f"[OPENALGO] {position.instrument} exit: {futures_symbol}")

            # Create a signal for the exit (placeholder values for required fields)
            exit_signal = Signal(
                timestamp=datetime.now(),
                instrument=position.instrument,
                signal_type=SignalType.EXIT,
                position=position.position_id.split("_")[-1] if "_" in position.position_id else "Long_1",
                price=exit_price,
                stop=position.current_stop or exit_price,  # Use stored stop or exit price
                suggested_lots=position.lots,
                atr=0.0,  # Not needed for exit
                er=0.0,   # Not needed for exit
                supertrend=exit_price,  # Placeholder
                reason="EXIT_ALL"
            )

            # Execute using standard order executor with SELL action
            exec_result = self.order_executor.execute(
                signal=exit_signal,
                lots=position.lots,
                limit_price=exit_price,
                action="SELL"
            )

            if exec_result.status == ExecutionStatus.EXECUTED:
                return {
                    'status': 'success',
                    'order_details': {
                        'futures_order_id': exec_result.order_id,
                        'exit_price': exec_result.execution_price,
                        'futures_symbol': futures_symbol
                    }
                }
            else:
                return {
                    'status': 'error',
                    'error': exec_result.rejection_reason or 'exit_execution_failed'
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

        IMPORTANT (Gap 1 Fix): Uses DATABASE position state, not signal state.
        TradingView is a "dumb scout" - Python PM is the authority on position state.

        Args:
            instrument: Trading instrument

        Returns:
            Dict with check result
        """
        if not self.eod_monitor or not self.config.eod_enabled:
            return {'success': False, 'reason': 'eod_disabled'}

        logger.info(f"[LIVE-EOD] Condition check for {instrument}")

        # ============================================================
        # GAP 1 FIX: Override signal position_status with DATABASE truth
        # ============================================================
        # TradingView sends raw indicator data but may have stale/incorrect
        # position info. Python PM is the authority on position state.
        state = self.eod_monitor.get_execution_state(instrument)
        if state and state.latest_signal:
            # Get actual position state from database
            portfolio_state = self.portfolio.get_current_state()
            db_positions = portfolio_state.get_positions_for_instrument(instrument)
            db_in_position = len(db_positions) > 0
            db_pyramid_count = len(db_positions) - 1 if db_in_position else 0

            # Handle Scout mode (no position_status from TradingView)
            if state.latest_signal.position_status is None:
                # Create position_status from database (Scout mode)
                logger.info(
                    f"[LIVE-EOD] Scout mode: Creating position_status from database for {instrument}"
                )
                state.latest_signal.position_status = EODPositionStatus(
                    in_position=db_in_position,
                    pyramid_count=db_pyramid_count
                )
            else:
                # V8 compatibility: Log mismatch and override
                signal_in_position = state.latest_signal.position_status.in_position
                signal_pyramid_count = state.latest_signal.position_status.pyramid_count
                if db_in_position != signal_in_position or db_pyramid_count != signal_pyramid_count:
                    logger.warning(
                        f"[LIVE-EOD] Position state mismatch for {instrument}: "
                        f"Signal says in_position={signal_in_position}, pyramid_count={signal_pyramid_count}; "
                        f"Database says in_position={db_in_position}, pyramid_count={db_pyramid_count}. "
                        f"Using DATABASE values (PM is the authority)."
                    )
                # Override signal's position_status with database truth
                state.latest_signal.position_status.in_position = db_in_position
                state.latest_signal.position_status.pyramid_count = db_pyramid_count

            logger.info(
                f"[LIVE-EOD] Database position state for {instrument}: "
                f"in_position={db_in_position}, pyramid_count={db_pyramid_count}"
            )
        # ============================================================

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

        IMPORTANT (Gap 1 + Gap 3 Fix): Re-validates with fresh DATABASE state
        at execution time to catch any condition changes since T-45.

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

        # ============================================================
        # GAP 1 + GAP 3 FIX: Re-validate with fresh DATABASE state
        # ============================================================
        # Even though we checked at T-45, we re-check at T-30 with fresh
        # database state to catch any changes (e.g., manual intervention,
        # or if conditions changed via fresh signal updates)
        eod_signal = state.latest_signal
        if not eod_signal:
            logger.warning(f"[LIVE-EOD] No signal available for {instrument}")
            return {
                'success': False,
                'reason': 'no_signal',
                'instrument': instrument
            }

        # Get fresh position state from database
        portfolio_state = self.portfolio.get_current_state()
        db_positions = portfolio_state.get_positions_for_instrument(instrument)
        db_in_position = len(db_positions) > 0
        db_pyramid_count = len(db_positions) - 1 if db_in_position else 0

        # Log current database state at T-30
        logger.info(
            f"[LIVE-EOD] T-30 fresh DB state for {instrument}: "
            f"in_position={db_in_position}, pyramid_count={db_pyramid_count}"
        )

        # Override signal's position_status with fresh database truth (null-safe)
        if eod_signal.position_status is None:
            # Scout mode: create position_status from database
            eod_signal.position_status = EODPositionStatus(
                in_position=db_in_position,
                pyramid_count=db_pyramid_count
            )
        else:
            # V8 mode: override existing
            eod_signal.position_status.in_position = db_in_position
            eod_signal.position_status.pyramid_count = db_pyramid_count
        # ============================================================

        # Get signal and action type (now uses corrected position state)
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

    # ============================================================
    # MARKET_DATA Signal Processing (PM-Side Stop Monitoring)
    # ============================================================

    def process_market_data_signal(self, signal: MarketDataSignal) -> Dict:
        """
        Process MARKET_DATA signal from Scout indicator for PM-side stop monitoring.

        This enables PM to independently monitor and execute stops without
        relying on TradingView strategy state (which can be lost).

        Steps:
        1. Get all open positions for the instrument
        2. Update trailing stops using ATR from signal
        3. Check if price < stop for any position
        4. Execute exit directly if stop hit (with deduplication)

        Args:
            signal: MarketDataSignal with price, ATR, supertrend

        Returns:
            Dict with processing result
        """
        instrument = signal.instrument
        logger.debug(
            f"[PM-STOP] Processing MARKET_DATA for {instrument}: "
            f"price={signal.price:.2f}, atr={signal.atr:.2f}, supertrend={signal.supertrend:.2f}"
        )

        # Get all open positions for this instrument
        portfolio_state = self.portfolio.get_current_state()
        positions = portfolio_state.get_positions_for_instrument(instrument)

        if not positions:
            return {
                'status': 'no_positions',
                'instrument': instrument
            }

        exits_triggered = []
        stops_updated = []

        for position in positions.values():
            # Skip if position is already closing or closed
            if position.status in ['closing', 'closed']:
                logger.debug(f"[PM-STOP] {position.position_id} already {position.status}, skipping")
                continue

            # Update trailing stop using ATR from signal
            old_stop = position.current_stop
            new_stop = self.stop_manager.update_trailing_stop(
                position, signal.price, signal.atr
            )

            if new_stop > old_stop:
                stops_updated.append({
                    'position_id': position.position_id,
                    'old_stop': old_stop,
                    'new_stop': new_stop
                })
                # Persist updated stop to database
                if self.db_manager:
                    self.db_manager.save_position(position)

            # Check if stop is hit
            if signal.price < position.current_stop:
                logger.warning(
                    f"[PM-STOP] STOP HIT: {position.position_id} - "
                    f"price {signal.price:.2f} < stop {position.current_stop:.2f}"
                )

                # Execute PM-initiated exit
                exit_result = self._execute_pm_initiated_exit(
                    position, signal.price, "PM_STOP_HIT"
                )
                exits_triggered.append({
                    'position_id': position.position_id,
                    'stop': position.current_stop,
                    'price': signal.price,
                    'result': exit_result
                })

        return {
            'status': 'processed',
            'instrument': instrument,
            'positions_checked': len(positions),
            'stops_updated': stops_updated,
            'exits_triggered': exits_triggered
        }

    def _execute_pm_initiated_exit(
        self,
        position: Position,
        exit_price: float,
        reason: str = "PM_STOP_HIT"
    ) -> Dict:
        """
        Execute a PM-initiated exit (bypasses TradingView).

        Used when PM detects stop hit via MARKET_DATA signal.
        Includes deduplication to prevent double exits if TV also sends exit.

        Args:
            position: Position to exit
            exit_price: Price at which stop was hit
            reason: Exit reason for logging

        Returns:
            Dict with exit result
        """
        position_id = position.position_id
        instrument = position.instrument

        # Deduplication: Check if already closing/closed
        if position.status in ['closing', 'closed']:
            logger.info(f"[PM-EXIT] {position_id} already {position.status}, skipping")
            return {'status': 'skipped', 'reason': 'already_closing'}

        # Mark as closing BEFORE placing order (prevents race condition)
        position.status = 'closing'
        if self.db_manager:
            self.db_manager.save_position(position)

        # Get announcer for later use (but don't announce yet - execute first!)
        announcer = get_announcer()

        logger.info(
            f"[PM-EXIT] Executing exit for {position_id}: "
            f"{position.lots} lots @ ₹{exit_price:,.2f}, reason={reason}"
        )

        # EXECUTE ORDER FIRST - don't delay for voice announcement
        # Route to appropriate executor based on instrument
        if instrument == "BANK_NIFTY":
            # BANK_NIFTY uses synthetic futures (2-leg options)
            result = self._execute_pm_exit_synthetic(position, exit_price)
        else:
            # MCX futures (Gold, Silver, Copper) - simple exit
            result = self._execute_pm_exit_mcx(position, exit_price)

        if result.get('status') == 'success':
            # Update position as closed
            actual_exit_price = result.get('exit_price', exit_price)
            pnl = self.portfolio.close_position(position_id, actual_exit_price, datetime.now())

            position.status = 'closed'
            position.exit_reason = reason
            if self.db_manager:
                self.db_manager.save_position(position)

            # Clear base_positions if this was a base position
            if position.is_base_position and instrument in self.base_positions:
                del self.base_positions[instrument]

            # Voice announcement for successful exit (only after confirmed success)
            if announcer:
                # First announce the stop hit and order placement
                announcer.announce_error(
                    f"{instrument} PM stop hit for {position_id}. Exit order placed successfully.",
                    error_type="pm_stop"
                )
                # Then announce the trade details
                announcer.announce_trade_executed(
                    instrument=instrument,
                    position=position_id.split('_')[-1] if '_' in position_id else 'Long_1',
                    signal_type="PM_EXIT",
                    lots=position.lots,
                    price=actual_exit_price,
                    pnl=pnl
                )

            logger.info(f"[PM-EXIT] {position_id} closed with P&L: ₹{pnl:,.2f}")

            return {
                'status': 'success',
                'position_id': position_id,
                'exit_price': actual_exit_price,
                'pnl': pnl,
                'reason': reason
            }
        else:
            # Exit failed - revert status
            position.status = 'open'
            if self.db_manager:
                self.db_manager.save_position(position)

            error_msg = result.get('reason', 'unknown_error')
            logger.error(f"[PM-EXIT] Failed to exit {position_id}: {error_msg}")

            if announcer:
                announcer.announce_error(
                    f"{instrument} PM exit failed for {position_id}. {error_msg}",
                    error_type="execution"
                )

            return {
                'status': 'error',
                'position_id': position_id,
                'reason': error_msg
            }

    def _execute_pm_exit_mcx(self, position: Position, exit_price: float) -> Dict:
        """
        Execute PM-initiated exit for MCX futures (Gold, Silver, Copper).

        Simple single-leg exit using ProgressiveExecutor.

        Args:
            position: Position to exit
            exit_price: Reference price for exit

        Returns:
            Dict with execution result
        """
        return self._execute_exit_openalgo(position)

    def _execute_pm_exit_synthetic(self, position: Position, exit_price: float) -> Dict:
        """
        Execute PM-initiated exit for BANK_NIFTY synthetic futures.

        Uses SyntheticFuturesExecutor for 2-leg options exit:
        - BUY PE (close short put)
        - SELL CE (close long call)

        Args:
            position: Position to exit
            exit_price: Reference price for exit

        Returns:
            Dict with execution result
        """
        # Reuse existing synthetic exit logic
        return self._execute_exit_openalgo(position)

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
