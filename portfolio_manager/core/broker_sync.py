"""
Broker State Sync - Reconcile PM state with broker positions

Features:
1. Periodic sync with broker (every 5 minutes)
2. Manual sync on demand
3. Startup reconciliation
4. Discrepancy detection and alerting
"""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncDiscrepancy:
    """Represents a discrepancy between PM and broker state"""
    discrepancy_type: str  # 'missing_in_pm', 'missing_in_broker', 'quantity_mismatch'
    instrument: str
    pm_lots: Optional[int]
    broker_lots: Optional[int]
    details: str


@dataclass
class SyncResult:
    """Result of a sync operation"""
    success: bool
    timestamp: datetime
    pm_positions: int
    broker_positions: int
    discrepancies: List[SyncDiscrepancy]
    error: Optional[str] = None


class BrokerSyncManager:
    """
    Manages synchronization between Portfolio Manager and Broker state

    Features:
    - Periodic background sync
    - Manual sync endpoint
    - Startup reconciliation
    - Discrepancy alerting
    """

    # Default sync interval (5 minutes)
    DEFAULT_SYNC_INTERVAL_SECONDS = 300

    def __init__(
        self,
        portfolio_state_manager,
        openalgo_client,
        telegram_notifier=None,
        voice_announcer=None,
        sync_interval_seconds: int = DEFAULT_SYNC_INTERVAL_SECONDS
    ):
        """
        Initialize BrokerSyncManager

        Args:
            portfolio_state_manager: PortfolioStateManager instance
            openalgo_client: OpenAlgo client for broker API
            telegram_notifier: TelegramNotifier for alerts
            voice_announcer: VoiceAnnouncer for audio alerts
            sync_interval_seconds: Interval between automatic syncs
        """
        self.portfolio = portfolio_state_manager
        self.openalgo = openalgo_client
        self.telegram = telegram_notifier
        self.voice = voice_announcer
        self.sync_interval = sync_interval_seconds

        # Background sync thread
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Last sync result
        self._last_sync: Optional[SyncResult] = None
        self._sync_lock = threading.Lock()

        # Broker connectivity tracking
        self._consecutive_failures: int = 0
        self._last_failure_alert: Optional[datetime] = None
        self._broker_down_alerted: bool = False  # Prevent repeated "broker down" alerts

        logger.info(f"[SYNC] BrokerSyncManager initialized (interval: {sync_interval_seconds}s)")

    def start_background_sync(self):
        """Start background sync thread"""
        if self._sync_thread and self._sync_thread.is_alive():
            logger.warning("[SYNC] Background sync already running")
            return

        self._stop_event.clear()
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info("[SYNC] Background sync started")

    def stop_background_sync(self):
        """Stop background sync thread"""
        self._stop_event.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=10.0)
        logger.info("[SYNC] Background sync stopped")

    def _sync_loop(self):
        """Background sync loop"""
        while not self._stop_event.is_set():
            try:
                # Wait for interval or stop event
                if self._stop_event.wait(timeout=self.sync_interval):
                    break  # Stop event set

                # Perform sync
                result = self.sync_now()

                # Only alert discrepancies if sync was successful (broker reachable)
                if result.success:
                    self._consecutive_failures = 0
                    self._broker_down_alerted = False  # Reset for next broker-down event

                    if result.discrepancies:
                        self._alert_discrepancies(result.discrepancies)
                else:
                    # Broker unreachable - track consecutive failures
                    self._consecutive_failures += 1

                    # Alert only once when broker goes down, not on every failed sync
                    if not self._broker_down_alerted:
                        self._broker_down_alerted = True
                        logger.warning(
                            f"[SYNC] Broker connectivity issue - sync failed "
                            f"(will suppress alerts until connectivity restored)"
                        )
                        # One-time brief notification (not voice spam)
                        if self.voice and self.voice.silent_mode:
                            self.voice.show_transient_alert(
                                "Broker Sync",
                                f"Cannot reach broker: {result.error}",
                                timeout_seconds=10
                            )
                    else:
                        # Subsequent failures - just log at debug level
                        logger.debug(
                            f"[SYNC] Broker still unreachable (consecutive failures: {self._consecutive_failures})"
                        )

            except Exception as e:
                logger.error(f"[SYNC] Background sync error: {e}")

    def sync_now(self) -> SyncResult:
        """
        Perform immediate sync with broker

        Returns:
            SyncResult with comparison details
        """
        logger.info("[SYNC] Starting broker sync...")

        try:
            # Get PM positions
            pm_state = self.portfolio.get_current_state()
            pm_positions = pm_state.get_open_positions()

            # Get broker positions via OpenAlgo
            broker_positions = self._fetch_broker_positions()

            if broker_positions is None:
                logger.warning("[SYNC] Broker positions unavailable (fetch failed) - skipping discrepancy checks")
                result = SyncResult(
                    success=False,
                    timestamp=datetime.now(),
                    pm_positions=len(pm_positions),
                    broker_positions=0,
                    discrepancies=[],
                    error="Failed to fetch broker positions"
                )
                with self._sync_lock:
                    self._last_sync = result
                return result

            # Compare positions
            discrepancies = self._compare_positions(pm_positions, broker_positions)

            result = SyncResult(
                success=True,
                timestamp=datetime.now(),
                pm_positions=len(pm_positions),
                broker_positions=len(broker_positions),
                discrepancies=discrepancies
            )

            with self._sync_lock:
                self._last_sync = result

            if discrepancies:
                logger.warning(f"[SYNC] Found {len(discrepancies)} discrepancies")
                for d in discrepancies:
                    logger.warning(f"[SYNC]   - {d.discrepancy_type}: {d.instrument} - {d.details}")
            else:
                logger.info(f"[SYNC] ✅ Sync complete - PM: {len(pm_positions)}, Broker: {len(broker_positions)} - No discrepancies")

            return result

        except Exception as e:
            logger.error(f"[SYNC] Sync error: {e}")
            result = SyncResult(
                success=False,
                timestamp=datetime.now(),
                pm_positions=0,
                broker_positions=0,
                discrepancies=[],
                error=str(e)
            )
            with self._sync_lock:
                self._last_sync = result
            return result

    def _fetch_broker_positions(self) -> Optional[Dict]:
        """
        Fetch positions from broker via OpenAlgo

        Returns:
            Dict of positions or None if failed
        """
        try:
            # OpenAlgo positionbook endpoint
            response = self.openalgo.get_positions()

            if response is None:
                logger.error("[SYNC] Broker returned None for positions")
                return None

            # Log first position for debugging field names - always log at INFO level for debugging
            if response and len(response) > 0:
                sample = response[0]
                logger.info(f"[SYNC] Sample position - ALL FIELDS: {list(sample.keys())}")
                logger.info(f"[SYNC] Sample position - FULL DATA: {sample}")

            # Parse response - OpenAlgo returns list of positions
            positions = {}

            if isinstance(response, list):
                for pos in response:
                    symbol = pos.get('symbol', pos.get('tradingsymbol', ''))

                    # Try different field names for quantity
                    # OpenAlgo/Zerodha uses: netqty, quantity, buyqty-sellqty
                    quantity = pos.get('netqty')
                    qty_source = 'netqty'
                    if quantity is None:
                        quantity = pos.get('quantity')
                        qty_source = 'quantity'
                    if quantity is None:
                        buyqty = int(pos.get('buyqty', 0))
                        sellqty = int(pos.get('sellqty', 0))
                        quantity = buyqty - sellqty
                        qty_source = f'buyqty({buyqty})-sellqty({sellqty})'
                    quantity = int(quantity) if quantity else 0

                    if quantity != 0:
                        # OpenAlgo positionbook API returns: average_price, quantity, symbol, exchange, product
                        # Per docs: https://docs.openalgo.in/api-documentation/v1/accounts-api/positionbook
                        avg_price = pos.get('average_price')  # OpenAlgo standard field (with underscore!)
                        price_source = 'average_price'
                        if avg_price is None:
                            avg_price = pos.get('netavgprice')
                            price_source = 'netavgprice'
                        if avg_price is None:
                            avg_price = pos.get('averageprice')  # no underscore variant
                            price_source = 'averageprice'
                        if avg_price is None:
                            avg_price = pos.get('avgprice')
                            price_source = 'avgprice'
                        if avg_price is None and quantity > 0:
                            avg_price = pos.get('buyavgprice') or pos.get('buyavg')
                            price_source = 'buyavgprice/buyavg'
                        elif avg_price is None and quantity < 0:
                            avg_price = pos.get('sellavgprice') or pos.get('sellavg')
                            price_source = 'sellavgprice/sellavg'

                        # Convert to float, default to 0 if still None
                        try:
                            avg_price = float(avg_price) if avg_price is not None else 0.0
                        except (ValueError, TypeError):
                            avg_price = 0.0

                        # Try to get LTP (may not be in positionbook response per docs)
                        # Use 'is None' checks instead of 'or' to preserve 0 values
                        ltp = pos.get('ltp')
                        if ltp is None:
                            ltp = pos.get('lastprice')
                        if ltp is None:
                            ltp = pos.get('last_price')
                        try:
                            ltp = float(ltp) if ltp is not None else 0.0
                        except (ValueError, TypeError):
                            ltp = 0.0

                        # Get PNL (unrealized P&L for open position)
                        # Use 'is None' checks instead of 'or' to preserve 0 values
                        pnl = pos.get('pnl')
                        if pnl is None:
                            pnl = pos.get('unrealizedpnl')
                        if pnl is None:
                            pnl = pos.get('unrealized_pnl')
                        try:
                            pnl = float(pnl) if pnl is not None else 0.0
                        except (ValueError, TypeError):
                            pnl = 0.0

                        # Fallback: Calculate PNL if broker returns 0 but we have LTP and avg_price
                        # PNL = (ltp - avg_price) * quantity (works for long and short)
                        pnl_source = 'broker'
                        if pnl == 0.0 and ltp > 0 and avg_price > 0:
                            pnl = (ltp - avg_price) * quantity
                            pnl_source = 'calculated'

                        logger.info(f"[SYNC] Parsed {symbol}: qty={quantity} (from {qty_source}), avg_price={avg_price} (from {price_source}), ltp={ltp}, pnl={pnl} ({pnl_source})")

                        positions[symbol] = {
                            'symbol': symbol,
                            'quantity': quantity,
                            'product': pos.get('product', pos.get('producttype', 'NRML')),
                            'exchange': pos.get('exchange', ''),
                            'average_price': avg_price,
                            'ltp': ltp,
                            'pnl': pnl,
                            # Include raw data for debugging
                            'raw': pos
                        }
            elif isinstance(response, dict):
                # Handle dict response format
                for symbol, pos in response.items():
                    quantity = int(pos.get('netqty', pos.get('quantity', 0)))
                    if quantity != 0:
                        positions[symbol] = pos

            logger.info(f"[SYNC] Fetched {len(positions)} broker positions")
            return positions

        except Exception as e:
            logger.error(f"[SYNC] Failed to fetch broker positions: {e}")
            return None

    def _compare_positions(
        self,
        pm_positions: Dict,
        broker_positions: Dict,
        strategy_id: int = 1  # Default to ITJ Trend Follow
    ) -> List[SyncDiscrepancy]:
        """
        Compare PM positions with broker positions (strategy-aware)

        Only compares positions belonging to the specified strategy.
        Positions in broker but not in PM are logged as info (manual trades),
        not flagged as discrepancies.

        Args:
            pm_positions: Positions from PortfolioStateManager
            broker_positions: Positions from broker
            strategy_id: Strategy ID to filter PM positions (default: 1 = ITJ Trend Follow)

        Returns:
            List of discrepancies found
        """
        from core.strategy_manager import STRATEGY_ITJ_TREND_FOLLOW

        discrepancies = []

        # Build a map of instrument -> total lots from PM (filtered by strategy)
        pm_by_instrument: Dict[str, int] = {}
        for pos_id, pos in pm_positions.items():
            # Only count positions for the specified strategy
            pos_strategy_id = getattr(pos, 'strategy_id', STRATEGY_ITJ_TREND_FOLLOW)
            if pos_strategy_id != strategy_id:
                continue

            instrument = pos.instrument
            pm_by_instrument[instrument] = pm_by_instrument.get(instrument, 0) + pos.lots

        # Build a map from broker positions
        # Note: Broker uses actual trading symbols, we need to map back
        broker_by_instrument: Dict[str, int] = {}
        for symbol, pos in broker_positions.items():
            # Try to identify instrument from symbol
            quantity = pos.get('quantity', 0)
            lot_size = self._get_lot_size_from_symbol(symbol)
            lots = abs(quantity) // lot_size if lot_size > 0 else abs(quantity)

            instrument = self._symbol_to_instrument(symbol)
            if instrument:
                broker_by_instrument[instrument] = broker_by_instrument.get(instrument, 0) + lots

        # Check for positions in PM (strategy-filtered) but not in broker
        for instrument, pm_lots in pm_by_instrument.items():
            broker_lots = broker_by_instrument.get(instrument, 0)

            if broker_lots == 0:
                discrepancies.append(SyncDiscrepancy(
                    discrepancy_type='missing_in_broker',
                    instrument=instrument,
                    pm_lots=pm_lots,
                    broker_lots=0,
                    details=f"PM has {pm_lots} lots, broker has none (strategy {strategy_id})"
                ))
            elif pm_lots > broker_lots:
                # PM has more than broker - this is a real discrepancy
                discrepancies.append(SyncDiscrepancy(
                    discrepancy_type='quantity_mismatch',
                    instrument=instrument,
                    pm_lots=pm_lots,
                    broker_lots=broker_lots,
                    details=f"PM: {pm_lots} lots, Broker: {broker_lots} lots (strategy {strategy_id})"
                ))

        # NOTE: We intentionally do NOT flag "missing_in_pm" discrepancies
        # When broker has more positions than PM's ITJ strategy, these are likely:
        # - Manual trades
        # - Positions from other strategies
        # - Positions from external systems
        # These should be handled by the strategy framework (assign to 'unknown' strategy)
        # rather than flagged as sync errors.
        #
        # Only log as info for visibility:
        for instrument, broker_lots in broker_by_instrument.items():
            pm_lots = pm_by_instrument.get(instrument, 0)
            if broker_lots > pm_lots:
                extra_lots = broker_lots - pm_lots
                logger.info(
                    f"[SYNC] Broker has {extra_lots} extra {instrument} lots "
                    f"(likely manual trades or other strategies)"
                )

        return discrepancies

    def _symbol_to_instrument(self, symbol: str) -> Optional[str]:
        """Map trading symbol to instrument name"""
        symbol_upper = symbol.upper()

        # MCX Commodities - check first (COPPER before other checks)
        if 'COPPER' in symbol_upper:
            return 'COPPER'
        elif 'SILVERM' in symbol_upper:
            return 'SILVER_MINI'
        elif 'GOLD' in symbol_upper or 'GOLDM' in symbol_upper:
            return 'GOLD_MINI'
        # NSE/BFO Indices
        elif 'BANKNIFTY' in symbol_upper or 'NIFTYBANK' in symbol_upper:
            return 'BANK_NIFTY'
        elif 'SENSEX' in symbol_upper:
            return 'SENSEX'
        elif 'FINNIFTY' in symbol_upper:
            return 'FINNIFTY'
        elif 'MIDCPNIFTY' in symbol_upper:
            return 'MIDCPNIFTY'
        elif 'NIFTY' in symbol_upper:  # Must come after other NIFTY variants
            return 'NIFTY'

        return None

    def _get_lot_size_from_symbol(self, symbol: str) -> int:
        """
        Get lot size divisor from symbol for converting broker quantity to lots.

        Note: MCX futures (Gold, Copper, Silver, etc.) return quantity as number of contracts/lots
        directly, so divisor is 1. NSE/BFO options return quantity in units, so we divide
        by the lot size to get number of lots.
        """
        symbol_upper = symbol.upper()

        # MCX futures - broker returns lot count directly, not units
        if 'COPPER' in symbol_upper and 'FUT' in symbol_upper:
            return 1  # Copper futures: qty is already in lots (lot size 2500 kg)
        if 'GOLDM' in symbol_upper and 'FUT' in symbol_upper:
            return 1  # Gold Mini futures: qty is already in lots
        if 'SILVERM' in symbol_upper and 'FUT' in symbol_upper:
            return 1  # Silver Mini futures: qty is already in lots

        # NSE/BFO options - broker returns units, divide by lot size
        if 'BANKNIFTY' in symbol_upper:
            return 30  # Bank Nifty lot size (Dec 2025 onwards)
        elif 'SENSEX' in symbol_upper:
            return 10
        elif 'FINNIFTY' in symbol_upper:
            return 25
        elif 'MIDCPNIFTY' in symbol_upper:
            return 50
        elif 'NIFTY' in symbol_upper:
            return 75  # Nifty lot size

        return 1

    def _alert_discrepancies(self, discrepancies: List[SyncDiscrepancy]):
        """Alert about discrepancies via Telegram, voice, or transient notification"""
        if not discrepancies:
            return

        # Build details message
        details = []
        for d in discrepancies[:5]:
            details.append(f"• {d.instrument}: {d.details}")
        details_str = "\n".join(details)
        if len(discrepancies) > 5:
            details_str += f"\n... and {len(discrepancies) - 5} more"

        # Voice or visual alert
        if self.voice:
            if self.voice.silent_mode:
                # Silent mode: Use transient alert (auto-dismiss after 15s)
                self.voice.show_transient_alert(
                    "Broker Sync Discrepancy",
                    f"Found {len(discrepancies)} position mismatch(es):\n{details_str}",
                    timeout_seconds=15
                )
            else:
                # Normal mode: Voice alert
                self.voice._speak(
                    f"Warning! Found {len(discrepancies)} position discrepancies between portfolio manager and broker. "
                    f"Please check and reconcile.",
                    priority="critical",
                    voice="Alex"
                )

        # Telegram alert (always send if configured)
        if self.telegram:
            self.telegram.send_alert(
                f"🔄 SYNC DISCREPANCY\n"
                f"Found {len(discrepancies)} issue(s):\n{details_str}"
            )

    def startup_reconciliation(self) -> SyncResult:
        """
        Perform startup reconciliation

        Called when PM starts to ensure state matches broker

        Returns:
            SyncResult
        """
        logger.info("[SYNC] === STARTUP RECONCILIATION ===")

        result = self.sync_now()

        if not result.success:
            # Log as warning, not error - broker might just not be connected yet
            logger.warning(f"[SYNC] Startup reconciliation skipped: {result.error}")
            self._broker_down_alerted = True  # Mark as alerted to prevent background sync spam

            if self.voice:
                # Show a non-blocking notification, not a critical error dialog
                # User might not have broker connected at startup - that's OK
                if self.voice.silent_mode:
                    self.voice.show_transient_alert(
                        "Startup Sync",
                        f"Broker not reachable - position verification skipped.\n{result.error}",
                        timeout_seconds=15
                    )
                else:
                    self.voice._speak(
                        "Broker not reachable. Position verification skipped.",
                        priority="normal",
                        voice="Samantha"
                    )
        elif result.discrepancies:
            logger.warning(f"[SYNC] Startup reconciliation found {len(result.discrepancies)} discrepancies")
            self._alert_discrepancies(result.discrepancies)
        else:
            logger.info("[SYNC] ✅ Startup reconciliation complete - all positions match")
            if self.voice:
                if self.voice.silent_mode:
                    # Silent mode: Show brief notification
                    self.voice.show_notification(
                        "PM Startup",
                        "Reconciliation complete - all positions verified"
                    )
                else:
                    # Normal mode: Voice confirmation
                    self.voice._speak(
                        "Startup reconciliation complete. All positions verified.",
                        priority="normal",
                        voice="Samantha"
                    )

        return result

    def get_last_sync_result(self) -> Optional[SyncResult]:
        """Get the last sync result"""
        with self._sync_lock:
            return self._last_sync

    def get_status(self) -> Dict:
        """Get current sync status"""
        with self._sync_lock:
            last_sync = self._last_sync

        return {
            'sync_interval_seconds': self.sync_interval,
            'background_sync_running': self._sync_thread and self._sync_thread.is_alive(),
            'broker_connectivity': {
                'is_connected': self._consecutive_failures == 0,
                'consecutive_failures': self._consecutive_failures,
                'alert_suppressed': self._broker_down_alerted
            },
            'last_sync': {
                'timestamp': last_sync.timestamp.isoformat() if last_sync else None,
                'success': last_sync.success if last_sync else None,
                'pm_positions': last_sync.pm_positions if last_sync else None,
                'broker_positions': last_sync.broker_positions if last_sync else None,
                'discrepancy_count': len(last_sync.discrepancies) if last_sync else 0,
                'error': last_sync.error if last_sync else None
            } if last_sync else None
        }


# Global instance
_broker_sync_manager: Optional[BrokerSyncManager] = None


def init_broker_sync(
    portfolio_state_manager,
    openalgo_client,
    telegram_notifier=None,
    voice_announcer=None,
    sync_interval_seconds: int = 300
) -> BrokerSyncManager:
    """Initialize global BrokerSyncManager instance"""
    global _broker_sync_manager
    _broker_sync_manager = BrokerSyncManager(
        portfolio_state_manager=portfolio_state_manager,
        openalgo_client=openalgo_client,
        telegram_notifier=telegram_notifier,
        voice_announcer=voice_announcer,
        sync_interval_seconds=sync_interval_seconds
    )
    return _broker_sync_manager


def get_broker_sync() -> Optional[BrokerSyncManager]:
    """Get global BrokerSyncManager instance"""
    return _broker_sync_manager
