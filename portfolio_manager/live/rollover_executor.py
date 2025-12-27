"""
Rollover Executor - Executes position rollovers with tight limit orders

Handles:
- Bank Nifty synthetic futures rollover (PE+CE legs)
- Gold Mini futures rollover
- Tight limit order execution (0.25% start, +0.05% per retry, 15s total)
- Position-by-position rollover (no aggregation)
"""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

from core.models import Position, RolloverStatus
from core.config import PortfolioConfig
from core.portfolio_state import PortfolioStateManager
from live.rollover_scanner import RolloverCandidate, RolloverScanResult
from live.expiry_utils import (
    get_rollover_strike,
    format_banknifty_option_symbol,
    format_gold_mini_futures_symbol,
    format_copper_futures_symbol,
    format_silver_mini_futures_symbol,
    is_market_hours
)

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of a single order execution"""
    success: bool
    order_id: Optional[str] = None
    fill_price: float = 0.0
    attempts: int = 0
    final_order_type: str = "LIMIT"  # LIMIT or MARKET (fallback)
    error: Optional[str] = None
    details: Dict = field(default_factory=dict)


@dataclass
class LegResult:
    """Result of closing/opening a single leg (PE, CE, or Futures)"""
    leg_type: str  # "PE", "CE", "FUTURES"
    action: str    # "BUY" or "SELL"
    symbol: str
    quantity: int
    order_result: OrderResult


@dataclass
class RolloverResult:
    """Result of rolling over a single position"""
    position_id: str
    instrument: str
    success: bool
    old_expiry: str
    new_expiry: str
    old_strike: Optional[int] = None
    new_strike: Optional[int] = None
    old_pe_symbol: Optional[str] = None  # For reconciliation
    old_ce_symbol: Optional[str] = None  # For reconciliation

    # Close leg results
    close_results: List[LegResult] = field(default_factory=list)

    # Open leg results
    open_results: List[LegResult] = field(default_factory=list)

    # P&L tracking
    close_pnl: float = 0.0  # P&L from closing old position
    spread_cost: float = 0.0  # Cost of bid-ask spread during rollover
    total_rollover_cost: float = 0.0

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0

    error: Optional[str] = None


@dataclass
class BatchRolloverResult:
    """Result of rolling over multiple positions"""
    total_positions: int
    successful: int
    failed: int
    results: List[RolloverResult] = field(default_factory=list)
    total_rollover_cost: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class RolloverExecutor:
    """
    Executes position rollovers with tight limit orders

    Strategy:
    - Close first, then open (per position)
    - Start with LIMIT at LTP ± 0.25%
    - Increase by 0.05% per retry
    - 5 retries × 3 seconds = 15 seconds total
    - Fallback to MARKET after timeout
    """

    def __init__(
        self,
        openalgo_client,
        portfolio: PortfolioStateManager,
        config: PortfolioConfig = None,
        broker: str = "zerodha"
    ):
        """
        Initialize executor

        Args:
            openalgo_client: OpenAlgo API client for order execution
            portfolio: Portfolio state manager
            config: Portfolio configuration
            broker: Broker name for symbol formatting
        """
        self.openalgo = openalgo_client
        self.portfolio = portfolio
        self.config = config or PortfolioConfig()
        self.broker = broker

        # Execution parameters from config
        self.initial_buffer_pct = self.config.rollover_initial_buffer_pct
        self.increment_pct = self.config.rollover_increment_pct
        self.max_retries = self.config.rollover_max_retries
        self.retry_interval = self.config.rollover_retry_interval_sec

    def execute_rollovers(
        self,
        scan_result: RolloverScanResult,
        dry_run: bool = False
    ) -> BatchRolloverResult:
        """
        Execute rollovers for all candidates from scan

        Args:
            scan_result: Result from RolloverScanner
            dry_run: If True, simulate without placing orders

        Returns:
            BatchRolloverResult with all results
        """
        batch_result = BatchRolloverResult(
            total_positions=len(scan_result.candidates),
            successful=0,
            failed=0,
            start_time=datetime.now()
        )

        if not scan_result.has_candidates():
            logger.info("No positions to roll over")
            batch_result.end_time = datetime.now()
            return batch_result

        logger.info(f"Starting rollover of {batch_result.total_positions} positions")

        for candidate in scan_result.candidates:
            try:
                # Check market hours before each rollover
                if not is_market_hours(candidate.instrument):
                    logger.warning(
                        f"Skipping {candidate.position.position_id}: "
                        f"Outside market hours for {candidate.instrument}"
                    )
                    batch_result.failed += 1
                    batch_result.results.append(RolloverResult(
                        position_id=candidate.position.position_id,
                        instrument=candidate.instrument,
                        success=False,
                        old_expiry=candidate.current_expiry,
                        new_expiry=candidate.next_expiry,
                        error="Outside market hours"
                    ))
                    continue

                # Execute rollover for this position
                if candidate.instrument == "BANK_NIFTY":
                    result = self._rollover_banknifty_position(candidate, dry_run)
                elif candidate.instrument == "GOLD_MINI":
                    result = self._rollover_gold_mini_position(candidate, dry_run)
                elif candidate.instrument == "COPPER":
                    result = self._rollover_copper_position(candidate, dry_run)
                elif candidate.instrument == "SILVER_MINI":
                    result = self._rollover_silver_mini_position(candidate, dry_run)
                else:
                    result = RolloverResult(
                        position_id=candidate.position.position_id,
                        instrument=candidate.instrument,
                        success=False,
                        old_expiry=candidate.current_expiry,
                        new_expiry=candidate.next_expiry,
                        error=f"Unknown instrument: {candidate.instrument}"
                    )

                batch_result.results.append(result)

                if result.success:
                    batch_result.successful += 1
                    batch_result.total_rollover_cost += result.total_rollover_cost
                    logger.info(
                        f"✓ Rolled {candidate.position.position_id}: "
                        f"{candidate.current_expiry} -> {candidate.next_expiry}"
                    )
                else:
                    batch_result.failed += 1
                    logger.error(
                        f"✗ Failed to roll {candidate.position.position_id}: {result.error}"
                    )

            except Exception as e:
                logger.error(f"Exception rolling {candidate.position.position_id}: {e}")
                batch_result.failed += 1
                batch_result.results.append(RolloverResult(
                    position_id=candidate.position.position_id,
                    instrument=candidate.instrument,
                    success=False,
                    old_expiry=candidate.current_expiry,
                    new_expiry=candidate.next_expiry,
                    error=str(e)
                ))

        batch_result.end_time = datetime.now()
        logger.info(
            f"Rollover complete: {batch_result.successful}/{batch_result.total_positions} "
            f"successful, cost=₹{batch_result.total_rollover_cost:,.2f}"
        )

        return batch_result

    def _rollover_banknifty_position(
        self,
        candidate: RolloverCandidate,
        dry_run: bool = False
    ) -> RolloverResult:
        """
        Rollover a Bank Nifty synthetic futures position

        Steps:
        1. Get current Bank Nifty futures LTP
        2. Calculate new strike (ATM -> nearest 500, prefer 1000s)
        3. Close old synthetic (BUY PE + SELL CE)
        4. Open new synthetic (SELL PE + BUY CE)
        5. Update position state

        Args:
            candidate: Position to roll
            dry_run: Simulate without orders

        Returns:
            RolloverResult
        """
        position = candidate.position
        result = RolloverResult(
            position_id=position.position_id,
            instrument="BANK_NIFTY",
            success=False,
            old_expiry=candidate.current_expiry,
            new_expiry=candidate.next_expiry,
            old_strike=position.strike,
            start_time=datetime.now()
        )

        try:
            # Step 1: Get current Bank Nifty price for new strike calculation
            bn_futures_symbol = self.config.banknifty_futures_symbol
            quote = self.openalgo.get_quote(bn_futures_symbol)
            current_price = quote.get('ltp', 0)

            if current_price <= 0:
                # Try alternative symbol format
                alt_symbols = ["BANKNIFTY", "BANKNIFTY-I", "BANKNIFTY25DEC25FUT"]
                for alt_symbol in alt_symbols:
                    quote = self.openalgo.get_quote(alt_symbol)
                    current_price = quote.get('ltp', 0)
                    if current_price > 0:
                        logger.info(f"Using alternative symbol: {alt_symbol}")
                        break

                if current_price <= 0:
                    result.error = f"Could not get Bank Nifty futures price (tried: {bn_futures_symbol}, {', '.join(alt_symbols)})"
                    return result

            # Step 2: Calculate new strike
            new_strike = get_rollover_strike(
                current_price,
                self.config.rollover_strike_interval,
                self.config.rollover_prefer_1000s
            )
            result.new_strike = new_strike

            logger.info(
                f"Rolling {position.position_id}: "
                f"strike {position.strike} -> {new_strike}, "
                f"expiry {candidate.current_expiry} -> {candidate.next_expiry}"
            )

            # Old symbols (store before updating)
            old_pe_symbol = position.pe_symbol
            old_ce_symbol = position.ce_symbol
            quantity = position.quantity

            # Store old symbols in result for reconciliation
            result.old_pe_symbol = old_pe_symbol
            result.old_ce_symbol = old_ce_symbol

            # New symbols
            new_pe_symbol = format_banknifty_option_symbol(
                candidate.next_expiry, new_strike, "PE", self.broker
            )
            new_ce_symbol = format_banknifty_option_symbol(
                candidate.next_expiry, new_strike, "CE", self.broker
            )

            if dry_run:
                logger.info(f"[DRY RUN] Would close: {old_pe_symbol}, {old_ce_symbol}")
                logger.info(f"[DRY RUN] Would open: {new_pe_symbol}, {new_ce_symbol}")
                result.success = True
                result.end_time = datetime.now()
                return result

            # Step 3: Close old position (BUY PE + SELL CE)
            # Mark position as in-progress
            position.rollover_status = RolloverStatus.IN_PROGRESS.value

            # Close PE (BUY to cover short)
            pe_close = self._execute_order_with_retry(
                old_pe_symbol, "BUY", quantity, "PE close"
            )
            result.close_results.append(LegResult(
                leg_type="PE", action="BUY", symbol=old_pe_symbol,
                quantity=quantity, order_result=pe_close
            ))

            if not pe_close.success:
                result.error = f"Failed to close PE: {pe_close.error}"
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            # Close CE (SELL to close long)
            ce_close = self._execute_order_with_retry(
                old_ce_symbol, "SELL", quantity, "CE close"
            )
            result.close_results.append(LegResult(
                leg_type="CE", action="SELL", symbol=old_ce_symbol,
                quantity=quantity, order_result=ce_close
            ))

            if not ce_close.success:
                result.error = f"Failed to close CE: {ce_close.error}"
                # PE is already closed - critical situation
                logger.critical(
                    f"CRITICAL: PE closed but CE close failed for {position.position_id}! "
                    f"Manual intervention required."
                )
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"Old position closed: PE@{pe_close.fill_price}, CE@{ce_close.fill_price}")

            # Step 4: Open new position (SELL PE + BUY CE)
            # Open PE (SELL)
            pe_open = self._execute_order_with_retry(
                new_pe_symbol, "SELL", quantity, "PE open"
            )
            result.open_results.append(LegResult(
                leg_type="PE", action="SELL", symbol=new_pe_symbol,
                quantity=quantity, order_result=pe_open
            ))

            if not pe_open.success:
                result.error = f"Failed to open new PE: {pe_open.error}"
                # Old position is closed, new PE failed - need manual intervention
                logger.critical(
                    f"CRITICAL: Old position closed but new PE failed for {position.position_id}! "
                    f"Position is now FLAT. Manual re-entry required."
                )
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            # Open CE (BUY)
            ce_open = self._execute_order_with_retry(
                new_ce_symbol, "BUY", quantity, "CE open"
            )
            result.open_results.append(LegResult(
                leg_type="CE", action="BUY", symbol=new_ce_symbol,
                quantity=quantity, order_result=ce_open
            ))

            if not ce_open.success:
                result.error = f"Failed to open new CE: {ce_open.error}"
                # PE is open, CE failed - need to cover PE
                logger.critical(
                    f"CRITICAL: New PE opened but CE failed for {position.position_id}! "
                    f"Attempting to cover PE..."
                )
                # Try to cover the PE
                pe_cover = self._execute_order_with_retry(
                    new_pe_symbol, "BUY", quantity, "PE emergency cover"
                )
                if pe_cover.success:
                    logger.info(f"Emergency PE cover successful")
                else:
                    logger.critical(f"Emergency PE cover FAILED! Manual intervention required!")
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"New position opened: PE@{pe_open.fill_price}, CE@{ce_open.fill_price}")

            # Step 5: Update position state
            # Store original values before updating
            position.original_expiry = candidate.current_expiry
            position.original_strike = position.strike
            position.original_entry_price = position.entry_price

            # Store original PE/CE entry prices if not already stored (for first rollover)
            # Note: In a real system, these should be stored at initial entry from execution_result
            # For now, we approximate using current market prices (will be accurate for first rollover)
            if position.pe_entry_price is None:
                # Get quotes for old symbols to estimate original entry prices
                # This is an approximation - ideally should come from initial entry execution
                old_pe_quote = self.openalgo.get_quote(old_pe_symbol)
                old_ce_quote = self.openalgo.get_quote(old_ce_symbol)
                position.pe_entry_price = old_pe_quote.get('ltp', pe_close.fill_price)
                position.ce_entry_price = old_ce_quote.get('ltp', ce_close.fill_price)
                logger.debug(f"Stored estimated entry prices: PE={position.pe_entry_price}, CE={position.ce_entry_price}")

            # Update position with new contract details
            position.expiry = candidate.next_expiry
            position.strike = new_strike
            # Calculate synthetic futures entry price: Strike + CE - PE
            # For ENTRY: SELL PE (receive premium), BUY CE (pay premium)
            synthetic_entry_price = float(new_strike) + ce_open.fill_price - pe_open.fill_price
            position.entry_price = synthetic_entry_price
            position.pe_symbol = new_pe_symbol
            position.ce_symbol = new_ce_symbol
            position.pe_order_id = pe_open.order_id
            position.ce_order_id = ce_open.order_id
            # Update PE/CE entry prices for the new position (needed for next rollover P&L)
            position.pe_entry_price = pe_open.fill_price
            position.ce_entry_price = ce_open.fill_price
            position.rollover_status = RolloverStatus.ROLLED.value
            position.rollover_timestamp = datetime.now()
            position.rollover_count += 1

            logger.info(
                f"[ROLLOVER] Updated position entry price: ₹{synthetic_entry_price:,.2f} "
                f"(strike={new_strike}, PE={pe_open.fill_price}, CE={ce_open.fill_price})"
            )

            # Update highest_close if new entry is higher
            if position.entry_price > position.highest_close:
                position.highest_close = position.entry_price

            # Calculate rollover cost (actual P&L from closing old position)
            # For Bank Nifty (options or futures):
            # P&L = price_diff × quantity, where quantity = lots × lot_size
            # This is consistent with: P&L = price_diff × lots × point_value (where point_value = lot_size for BN)
            #
            # For synthetic futures (options):
            # - PE: SELL at entry (short), BUY at close (cover) -> profit if close < entry
            # - CE: BUY at entry (long), SELL at close -> profit if close > entry

            # Calculate P&L from closing old position
            # PE: Was sold at entry, bought back at close -> profit if close < entry (price went down)
            pe_close_pnl = (position.pe_entry_price - pe_close.fill_price) * quantity
            # CE: Was bought at entry, sold at close -> profit if close > entry (price went up)
            ce_close_pnl = (ce_close.fill_price - position.ce_entry_price) * quantity
            close_pnl = pe_close_pnl + ce_close_pnl

            # Cost of opening new position (spread + slippage)
            # For synthetic futures: SELL PE (receive premium), BUY CE (pay premium)
            # Net premium at entry: PE_price - CE_price (positive = we receive net, negative = we pay net)
            # The spread cost is the difference in net premiums between old and new positions
            # This represents the cost of switching from old to new contract
            net_premium_old = (position.pe_entry_price - position.ce_entry_price) * quantity  # Old: what we received/paid
            net_premium_new = (pe_open.fill_price - ce_open.fill_price) * quantity  # New: what we'll receive/pay
            # Spread cost = difference (positive = costs more to enter new, negative = cheaper)
            spread_cost = net_premium_new - net_premium_old

            # Total rollover cost = P&L from closing old + spread cost of opening new
            # close_pnl is the realized P&L from closing the old position
            result.close_pnl = close_pnl
            result.spread_cost = spread_cost
            result.total_rollover_cost = close_pnl + spread_cost
            position.rollover_pnl += result.total_rollover_cost

            # Update portfolio closed equity with rollover P&L
            # Note: close_pnl is the realized P&L from closing the old position
            if close_pnl != 0:
                self.portfolio.closed_equity += close_pnl
                logger.info(f"Rollover P&L: Close P&L=₹{close_pnl:,.2f}, Spread cost=₹{spread_cost:,.2f}, Total=₹{result.total_rollover_cost:,.2f}")

            # Reconcile position with broker
            reconciliation = self.reconcile_position_after_rollover(position, result)
            if reconciliation['status'] != 'success':
                logger.warning(f"Rollover reconciliation issues: {reconciliation.get('mismatches', [])}")

            result.success = True
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()

            return result

        except Exception as e:
            result.error = str(e)
            result.end_time = datetime.now()
            position.rollover_status = RolloverStatus.FAILED.value
            return result

    def _rollover_gold_mini_position(
        self,
        candidate: RolloverCandidate,
        dry_run: bool = False
    ) -> RolloverResult:
        """
        Rollover a Gold Mini futures position

        Steps:
        1. Close current month futures
        2. Open next month futures
        3. Update position state

        Args:
            candidate: Position to roll
            dry_run: Simulate without orders

        Returns:
            RolloverResult
        """
        position = candidate.position
        result = RolloverResult(
            position_id=position.position_id,
            instrument="GOLD_MINI",
            success=False,
            old_expiry=candidate.current_expiry,
            new_expiry=candidate.next_expiry,
            start_time=datetime.now()
        )

        try:
            # Old and new symbols
            old_symbol = position.futures_symbol or format_gold_mini_futures_symbol(
                candidate.current_expiry, self.broker
            )
            new_symbol = format_gold_mini_futures_symbol(
                candidate.next_expiry, self.broker
            )
            quantity = position.quantity

            logger.info(
                f"Rolling {position.position_id}: "
                f"{old_symbol} -> {new_symbol}"
            )

            if dry_run:
                logger.info(f"[DRY RUN] Would close: {old_symbol}")
                logger.info(f"[DRY RUN] Would open: {new_symbol}")
                result.success = True
                result.end_time = datetime.now()
                return result

            # Mark position as in-progress
            position.rollover_status = RolloverStatus.IN_PROGRESS.value

            # Step 1: Close old futures (SELL)
            close_result = self._execute_order_with_retry(
                old_symbol, "SELL", quantity, "Futures close"
            )
            result.close_results.append(LegResult(
                leg_type="FUTURES", action="SELL", symbol=old_symbol,
                quantity=quantity, order_result=close_result
            ))

            if not close_result.success:
                result.error = f"Failed to close futures: {close_result.error}"
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"Old futures closed @ {close_result.fill_price}")

            # Step 2: Open new futures (BUY)
            open_result = self._execute_order_with_retry(
                new_symbol, "BUY", quantity, "Futures open"
            )
            result.open_results.append(LegResult(
                leg_type="FUTURES", action="BUY", symbol=new_symbol,
                quantity=quantity, order_result=open_result
            ))

            if not open_result.success:
                result.error = f"Failed to open new futures: {open_result.error}"
                logger.critical(
                    f"CRITICAL: Old futures closed but new open failed for {position.position_id}! "
                    f"Position is now FLAT. Manual re-entry required."
                )
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"New futures opened @ {open_result.fill_price}")

            # Step 3: Update position state
            # Store original values before updating
            position.original_expiry = candidate.current_expiry
            position.original_entry_price = position.entry_price

            # Update position with new contract details
            position.expiry = candidate.next_expiry
            position.contract_month = candidate.next_expiry[2:5] + candidate.next_expiry[:2]  # DEC25
            position.futures_symbol = new_symbol
            position.futures_order_id = open_result.order_id
            position.entry_price = open_result.fill_price  # Update entry price to new futures price
            position.rollover_status = RolloverStatus.ROLLED.value
            position.rollover_timestamp = datetime.now()
            position.rollover_count += 1

            # Update highest_close if new entry is higher
            if position.entry_price > position.highest_close:
                position.highest_close = position.entry_price

            # Calculate rollover cost (actual P&L from closing old position + spread cost)
            from core.config import get_instrument_config
            from core.models import InstrumentType
            inst_config = get_instrument_config(InstrumentType.GOLD_MINI)
            point_value = inst_config.point_value  # Rs 10 per point per lot

            # P&L from closing old futures position
            # For futures: BUY at entry, SELL at close -> profit if close > entry
            # Gold Mini: P&L = price_diff × lots × 10 (since quoted per 10g, contract is 100g)
            lots = position.lots
            close_pnl = (close_result.fill_price - position.original_entry_price) * lots * point_value

            # Cost of opening new position (spread + slippage)
            # This is the cost difference between closing old and opening new
            spread_cost = abs(open_result.fill_price - close_result.fill_price) * lots * point_value

            result.close_pnl = close_pnl
            result.spread_cost = spread_cost
            result.total_rollover_cost = close_pnl + spread_cost
            position.rollover_pnl += result.total_rollover_cost

            # Update portfolio closed equity with rollover P&L
            if close_pnl != 0:
                self.portfolio.closed_equity += close_pnl
                logger.info(f"Rollover P&L: Close P&L=₹{close_pnl:,.2f}, Spread cost=₹{spread_cost:,.2f}, Total=₹{result.total_rollover_cost:,.2f}")

            # Reconcile position with broker
            reconciliation = self.reconcile_position_after_rollover(position, result)
            if reconciliation['status'] != 'success':
                logger.warning(f"Rollover reconciliation issues: {reconciliation.get('mismatches', [])}")

            result.success = True
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()

            return result

        except Exception as e:
            result.error = str(e)
            result.end_time = datetime.now()
            position.rollover_status = RolloverStatus.FAILED.value
            return result

    def _rollover_copper_position(
        self,
        candidate: RolloverCandidate,
        dry_run: bool = False
    ) -> RolloverResult:
        """
        Rollover a Copper futures position

        Steps:
        1. Close current month futures
        2. Open next month futures
        3. Update position state

        Args:
            candidate: Position to roll
            dry_run: Simulate without orders

        Returns:
            RolloverResult
        """
        position = candidate.position
        result = RolloverResult(
            position_id=position.position_id,
            instrument="COPPER",
            success=False,
            old_expiry=candidate.current_expiry,
            new_expiry=candidate.next_expiry,
            start_time=datetime.now()
        )

        try:
            # Old and new symbols
            old_symbol = position.futures_symbol or format_copper_futures_symbol(
                candidate.current_expiry, self.broker
            )
            new_symbol = format_copper_futures_symbol(
                candidate.next_expiry, self.broker
            )
            quantity = position.quantity

            logger.info(
                f"Rolling {position.position_id}: "
                f"{old_symbol} -> {new_symbol}"
            )

            if dry_run:
                logger.info(f"[DRY RUN] Would close: {old_symbol}")
                logger.info(f"[DRY RUN] Would open: {new_symbol}")
                result.success = True
                result.end_time = datetime.now()
                return result

            # Mark position as in-progress
            position.rollover_status = RolloverStatus.IN_PROGRESS.value

            # Step 1: Close old futures (SELL)
            close_result = self._execute_order_with_retry(
                old_symbol, "SELL", quantity, "Futures close"
            )
            result.close_results.append(LegResult(
                leg_type="FUTURES", action="SELL", symbol=old_symbol,
                quantity=quantity, order_result=close_result
            ))

            if not close_result.success:
                result.error = f"Failed to close futures: {close_result.error}"
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"Old futures closed @ {close_result.fill_price}")

            # Step 2: Open new futures (BUY)
            open_result = self._execute_order_with_retry(
                new_symbol, "BUY", quantity, "Futures open"
            )
            result.open_results.append(LegResult(
                leg_type="FUTURES", action="BUY", symbol=new_symbol,
                quantity=quantity, order_result=open_result
            ))

            if not open_result.success:
                result.error = f"Failed to open new futures: {open_result.error}"
                logger.critical(
                    f"CRITICAL: Old futures closed but new open failed for {position.position_id}! "
                    f"Position is now FLAT. Manual re-entry required."
                )
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"New futures opened @ {open_result.fill_price}")

            # Step 3: Update position state
            # Store original values before updating
            position.original_expiry = candidate.current_expiry
            position.original_entry_price = position.entry_price

            # Update position with new contract details
            position.expiry = candidate.next_expiry
            position.contract_month = candidate.next_expiry[2:5] + candidate.next_expiry[:2]  # DEC25
            position.futures_symbol = new_symbol
            position.futures_order_id = open_result.order_id
            position.entry_price = open_result.fill_price  # Update entry price to new futures price
            position.rollover_status = RolloverStatus.ROLLED.value
            position.rollover_timestamp = datetime.now()
            position.rollover_count += 1

            # Update highest_close if new entry is higher
            if position.entry_price > position.highest_close:
                position.highest_close = position.entry_price

            # Calculate rollover cost (actual P&L from closing old position + spread cost)
            from core.config import get_instrument_config
            from core.models import InstrumentType
            inst_config = get_instrument_config(InstrumentType.COPPER)
            point_value = inst_config.point_value  # Rs 2500 per Re 1 move per lot

            # P&L from closing old futures position
            # For futures: BUY at entry, SELL at close -> profit if close > entry
            lots = position.lots
            close_pnl = (close_result.fill_price - position.original_entry_price) * lots * point_value

            # Cost of opening new position (spread + slippage)
            spread_cost = abs(open_result.fill_price - close_result.fill_price) * lots * point_value

            result.close_pnl = close_pnl
            result.spread_cost = spread_cost
            result.total_rollover_cost = close_pnl + spread_cost
            position.rollover_pnl += result.total_rollover_cost

            # Update portfolio closed equity with rollover P&L
            if close_pnl != 0:
                self.portfolio.closed_equity += close_pnl
                logger.info(f"Rollover P&L: Close P&L=₹{close_pnl:,.2f}, Spread cost=₹{spread_cost:,.2f}, Total=₹{result.total_rollover_cost:,.2f}")

            # Reconcile position with broker
            reconciliation = self.reconcile_position_after_rollover(position, result)
            if reconciliation['status'] != 'success':
                logger.warning(f"Rollover reconciliation issues: {reconciliation.get('mismatches', [])}")

            result.success = True
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()

            return result

        except Exception as e:
            result.error = str(e)
            result.end_time = datetime.now()
            position.rollover_status = RolloverStatus.FAILED.value
            return result

    def _rollover_silver_mini_position(
        self,
        candidate: RolloverCandidate,
        dry_run: bool = False
    ) -> RolloverResult:
        """
        Roll Silver Mini futures position to next contract.

        Silver Mini has bimonthly contracts (Feb, Apr, Jun, Aug, Nov).

        Args:
            candidate: Rollover candidate
            dry_run: If True, don't execute actual orders

        Returns:
            RolloverResult
        """
        position = candidate.position
        result = RolloverResult(
            position_id=position.position_id,
            instrument="SILVER_MINI",
            success=False,
            old_expiry=candidate.current_expiry,
            new_expiry=candidate.next_expiry,
            start_time=datetime.now()
        )

        try:
            # Old and new symbols
            old_symbol = position.futures_symbol or format_silver_mini_futures_symbol(
                candidate.current_expiry, self.broker
            )
            new_symbol = format_silver_mini_futures_symbol(
                candidate.next_expiry, self.broker
            )
            quantity = position.quantity

            logger.info(
                f"Rolling {position.position_id}: "
                f"{old_symbol} -> {new_symbol}"
            )

            if dry_run:
                logger.info(f"[DRY RUN] Would close: {old_symbol}")
                logger.info(f"[DRY RUN] Would open: {new_symbol}")
                result.success = True
                result.end_time = datetime.now()
                return result

            # Mark position as in-progress
            position.rollover_status = RolloverStatus.IN_PROGRESS.value

            # Step 1: Close old futures (SELL)
            close_result = self._execute_order_with_retry(
                old_symbol, "SELL", quantity, "Futures close"
            )
            result.close_results.append(LegResult(
                leg_type="FUTURES", action="SELL", symbol=old_symbol,
                quantity=quantity, order_result=close_result
            ))

            if not close_result.success:
                result.error = f"Failed to close futures: {close_result.error}"
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"Old futures closed @ {close_result.fill_price}")

            # Step 2: Open new futures (BUY)
            open_result = self._execute_order_with_retry(
                new_symbol, "BUY", quantity, "Futures open"
            )
            result.open_results.append(LegResult(
                leg_type="FUTURES", action="BUY", symbol=new_symbol,
                quantity=quantity, order_result=open_result
            ))

            if not open_result.success:
                result.error = f"Failed to open new futures: {open_result.error}"
                logger.critical(
                    f"CRITICAL: Old futures closed but new open failed for {position.position_id}! "
                    f"Position is now FLAT. Manual re-entry required."
                )
                position.rollover_status = RolloverStatus.FAILED.value
                return result

            logger.info(f"New futures opened @ {open_result.fill_price}")

            # Step 3: Update position state
            # Store original values before updating
            position.original_expiry = candidate.current_expiry
            position.original_entry_price = position.entry_price

            # Update position with new contract details
            position.expiry = candidate.next_expiry
            position.contract_month = candidate.next_expiry[2:5] + candidate.next_expiry[:2]  # FEB26
            position.futures_symbol = new_symbol
            position.futures_order_id = open_result.order_id
            position.entry_price = open_result.fill_price  # Update entry price to new futures price
            position.rollover_status = RolloverStatus.ROLLED.value
            position.rollover_timestamp = datetime.now()
            position.rollover_count += 1

            # Update highest_close if new entry is higher
            if position.entry_price > position.highest_close:
                position.highest_close = position.entry_price

            # Calculate rollover cost (actual P&L from closing old position + spread cost)
            from core.config import get_instrument_config
            from core.models import InstrumentType
            inst_config = get_instrument_config(InstrumentType.SILVER_MINI)
            point_value = inst_config.point_value  # Rs 5 per Rs 1/kg move per lot

            # P&L from closing old futures position
            # For futures: BUY at entry, SELL at close -> profit if close > entry
            lots = position.lots
            close_pnl = (close_result.fill_price - position.original_entry_price) * lots * point_value

            # Cost of opening new position (spread + slippage)
            spread_cost = abs(open_result.fill_price - close_result.fill_price) * lots * point_value

            result.close_pnl = close_pnl
            result.spread_cost = spread_cost
            result.total_rollover_cost = close_pnl + spread_cost
            position.rollover_pnl += result.total_rollover_cost

            # Update portfolio closed equity with rollover P&L
            if close_pnl != 0:
                self.portfolio.closed_equity += close_pnl
                logger.info(f"Rollover P&L: Close P&L=₹{close_pnl:,.2f}, Spread cost=₹{spread_cost:,.2f}, Total=₹{result.total_rollover_cost:,.2f}")

            # Reconcile position with broker
            reconciliation = self.reconcile_position_after_rollover(position, result)
            if reconciliation['status'] != 'success':
                logger.warning(f"Rollover reconciliation issues: {reconciliation.get('mismatches', [])}")

            result.success = True
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()

            return result

        except Exception as e:
            result.error = str(e)
            result.end_time = datetime.now()
            position.rollover_status = RolloverStatus.FAILED.value
            return result

    def _execute_order_with_retry(
        self,
        symbol: str,
        action: str,
        quantity: int,
        description: str
    ) -> OrderResult:
        """
        Execute order with tight limit order strategy

        Strategy:
        - Start with LIMIT at LTP ± 0.25%
        - Increase buffer by 0.05% per retry
        - 5 retries × 3 seconds = 15 seconds
        - Fallback to MARKET

        Args:
            symbol: Trading symbol
            action: "BUY" or "SELL"
            quantity: Order quantity
            description: For logging

        Returns:
            OrderResult
        """
        result = OrderResult(success=False)

        try:
            # Get current quote
            quote = self.openalgo.get_quote(symbol)
            ltp = quote.get('ltp', 0)
            bid = quote.get('bid', ltp)
            ask = quote.get('ask', ltp)

            if ltp <= 0:
                result.error = f"Could not get LTP for {symbol}"
                return result

            logger.info(f"[{description}] {symbol}: LTP={ltp}, Bid={bid}, Ask={ask}")

            # Calculate initial limit price
            buffer_pct = self.initial_buffer_pct / 100
            if action == "BUY":
                limit_price = round(ltp * (1 + buffer_pct), 2)
            else:  # SELL
                limit_price = round(ltp * (1 - buffer_pct), 2)

            # Place initial LIMIT order
            order_response = self.openalgo.place_order(
                symbol=symbol,
                action=action,
                quantity=quantity,
                order_type="LIMIT",
                price=limit_price
            )

            if order_response.get('status') != 'success':
                result.error = f"Order placement failed: {order_response}"
                return result

            order_id = order_response.get('orderid')
            result.order_id = order_id
            result.attempts = 1

            logger.info(f"[{description}] LIMIT order placed @ {limit_price}, ID={order_id}")

            # Retry loop
            for attempt in range(1, self.max_retries + 1):
                time.sleep(self.retry_interval)

                # Check order status
                order_status = self.openalgo.get_order_status(order_id)
                status = order_status.get('status', '').upper() if order_status else ''

                if status in ['COMPLETE', 'FILLED']:
                    result.success = True
                    result.fill_price = float(order_status.get('price', limit_price))
                    result.final_order_type = "LIMIT"
                    logger.info(
                        f"[{description}] FILLED @ {result.fill_price} "
                        f"(attempt {attempt})"
                    )
                    return result

                if status in ['REJECTED', 'CANCELLED']:
                    result.error = f"Order {status}: {order_status}"
                    return result

                # Still pending - modify price
                result.attempts = attempt + 1
                buffer_pct += self.increment_pct / 100

                # Get fresh quote for mid-price
                fresh_quote = self.openalgo.get_quote(symbol)
                fresh_bid = fresh_quote.get('bid', bid)
                fresh_ask = fresh_quote.get('ask', ask)
                mid_price = round((fresh_bid + fresh_ask) / 2, 2)

                # New limit price - use mid-price or buffer, whichever is more aggressive
                if action == "BUY":
                    new_limit = max(mid_price, round(ltp * (1 + buffer_pct), 2))
                else:
                    new_limit = min(mid_price, round(ltp * (1 - buffer_pct), 2))

                # Determine exchange from symbol (MCX for Gold/Copper/Silver, NFO for others)
                symbol_upper = symbol.upper()
                exchange = "MCX" if ("GOLD" in symbol_upper or "COPPER" in symbol_upper or "SILVER" in symbol_upper) else "NFO"

                # Modify order with full params required by OpenAlgo
                modify_response = self.openalgo.modify_order(
                    order_id=order_id,
                    new_price=new_limit,
                    symbol=symbol,
                    action=action,
                    exchange=exchange,
                    quantity=quantity,
                    product="NRML"
                )
                logger.info(
                    f"[{description}] Retry {attempt}: modified to {new_limit} "
                    f"(mid={mid_price}, buffer={buffer_pct*100:.2f}%)"
                )

            # All retries exhausted - fallback to MARKET
            logger.warning(f"[{description}] LIMIT failed after {self.max_retries} retries, using MARKET")

            # Cancel pending LIMIT order
            self.openalgo.cancel_order(order_id)

            # Place MARKET order
            market_response = self.openalgo.place_order(
                symbol=symbol,
                action=action,
                quantity=quantity,
                order_type="MARKET"
            )

            if market_response.get('status') != 'success':
                result.error = f"MARKET fallback failed: {market_response}"
                return result

            market_order_id = market_response.get('orderid')
            result.order_id = market_order_id
            result.final_order_type = "MARKET"

            # Wait for MARKET fill
            time.sleep(2)
            market_status = self.openalgo.get_order_status(market_order_id)

            if market_status and market_status.get('status', '').upper() in ['COMPLETE', 'FILLED']:
                result.success = True
                result.fill_price = float(market_status.get('price', ltp))
                logger.info(f"[{description}] MARKET filled @ {result.fill_price}")
            else:
                result.error = f"MARKET order did not fill: {market_status}"

            return result

        except Exception as e:
            result.error = str(e)
            logger.error(f"[{description}] Exception: {e}")
            return result

    def reconcile_position_after_rollover(
        self,
        position: Position,
        rollover_result: RolloverResult
    ) -> Dict[str, Any]:
        """
        Reconcile position state with broker after rollover

        Verifies that:
        - Old position legs are closed in broker
        - New position legs are open in broker
        - Portfolio state matches broker state

        Args:
            position: Position that was rolled
            rollover_result: Result from rollover execution

        Returns:
            Dict with reconciliation status and any mismatches
        """
        reconciliation = {
            'position_id': position.position_id,
            'status': 'success',
            'mismatches': [],
            'warnings': []
        }

        try:
            # Get broker positions
            broker_positions = self.openalgo.get_positions()

            if position.instrument == "BANK_NIFTY":
                # Check that old PE/CE are closed (use old symbols from rollover result)
                old_pe_symbol = rollover_result.old_pe_symbol
                old_ce_symbol = rollover_result.old_ce_symbol

                for bp in broker_positions:
                    bp_symbol = bp.get('symbol', '')
                    # Check if old symbols still exist in broker
                    if old_pe_symbol and bp_symbol == old_pe_symbol:
                        reconciliation['mismatches'].append(f"Old PE {old_pe_symbol} still open in broker (qty: {bp.get('quantity')})")
                    if old_ce_symbol and bp_symbol == old_ce_symbol:
                        reconciliation['mismatches'].append(f"Old CE {old_ce_symbol} still open in broker (qty: {bp.get('quantity')})")

                # Check that new PE/CE are open
                new_pe_open = False
                new_ce_open = False

                for bp in broker_positions:
                    if bp.get('symbol') == position.pe_symbol:
                        new_pe_open = True
                        # Verify quantity matches
                        if abs(bp.get('quantity', 0)) != position.quantity:
                            reconciliation['warnings'].append(
                                f"PE quantity mismatch: portfolio={position.quantity}, broker={bp.get('quantity')}"
                            )
                    if bp.get('symbol') == position.ce_symbol:
                        new_ce_open = True
                        if abs(bp.get('quantity', 0)) != position.quantity:
                            reconciliation['warnings'].append(
                                f"CE quantity mismatch: portfolio={position.quantity}, broker={bp.get('quantity')}"
                            )

                if not new_pe_open:
                    reconciliation['mismatches'].append(f"New PE {position.pe_symbol} not found in broker")
                if not new_ce_open:
                    reconciliation['mismatches'].append(f"New CE {position.ce_symbol} not found in broker")

            elif position.instrument in ("GOLD_MINI", "COPPER", "SILVER_MINI"):
                # Check that old futures is closed
                # Reconstruct old symbol from original expiry
                old_futures_symbol = None
                if position.original_expiry:
                    try:
                        if position.instrument == "GOLD_MINI":
                            old_futures_symbol = format_gold_mini_futures_symbol(position.original_expiry, self.broker)
                        elif position.instrument == "COPPER":
                            old_futures_symbol = format_copper_futures_symbol(position.original_expiry, self.broker)
                        else:  # SILVER_MINI
                            old_futures_symbol = format_silver_mini_futures_symbol(position.original_expiry, self.broker)
                    except Exception as e:
                        logger.debug(f"Could not reconstruct old futures symbol: {e}")
                        pass

                if old_futures_symbol:
                    for bp in broker_positions:
                        if bp.get('symbol') == old_futures_symbol:
                            reconciliation['mismatches'].append(f"Old futures {old_futures_symbol} still open in broker (qty: {bp.get('quantity')})")

                # Check that new futures is open
                new_futures_open = False
                for bp in broker_positions:
                    if bp.get('symbol') == position.futures_symbol:
                        new_futures_open = True
                        if abs(bp.get('quantity', 0)) != position.quantity:
                            reconciliation['warnings'].append(
                                f"Futures quantity mismatch: portfolio={position.quantity}, broker={bp.get('quantity')}"
                            )

                if not new_futures_open:
                    reconciliation['mismatches'].append(f"New futures {position.futures_symbol} not found in broker")

            if reconciliation['mismatches']:
                reconciliation['status'] = 'mismatch'
                logger.warning(f"Position reconciliation found mismatches: {reconciliation['mismatches']}")
            elif reconciliation['warnings']:
                reconciliation['status'] = 'warning'
                logger.info(f"Position reconciliation warnings: {reconciliation['warnings']}")
            else:
                logger.info(f"Position {position.position_id} reconciled successfully")

            return reconciliation

        except Exception as e:
            reconciliation['status'] = 'error'
            reconciliation['error'] = str(e)
            logger.error(f"Reconciliation error for {position.position_id}: {e}")
            return reconciliation
