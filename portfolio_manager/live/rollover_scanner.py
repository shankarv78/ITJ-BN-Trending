"""
Rollover Scanner - Identifies positions needing rollover

Scans open positions and determines which need to be rolled over
based on days to expiry thresholds.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import logging

from core.models import Position, InstrumentType
from core.config import PortfolioConfig
from core.portfolio_state import PortfolioStateManager
from live.expiry_utils import (
    days_to_expiry,
    is_within_rollover_window,
    get_next_month_expiry,
    get_contract_month,
    parse_expiry_string
)

logger = logging.getLogger(__name__)


@dataclass
class RolloverCandidate:
    """A position that needs rollover"""
    position: Position
    days_to_expiry: int
    current_expiry: str
    next_expiry: str
    next_expiry_date: datetime
    instrument: str
    reason: str  # e.g., "Within 7-day rollover window"


@dataclass
class RolloverScanResult:
    """Results from rollover scan"""
    scan_timestamp: datetime
    total_positions: int
    positions_to_roll: int
    candidates: List[RolloverCandidate] = field(default_factory=list)
    skipped: List[Dict] = field(default_factory=list)  # Positions not needing rollover
    errors: List[str] = field(default_factory=list)

    def has_candidates(self) -> bool:
        return len(self.candidates) > 0

    def get_by_instrument(self, instrument: str) -> List[RolloverCandidate]:
        return [c for c in self.candidates if c.instrument == instrument]


class RolloverScanner:
    """Scans positions and identifies rollover candidates"""

    def __init__(self, config: PortfolioConfig = None):
        """
        Initialize scanner

        Args:
            config: Portfolio configuration (uses defaults if not provided)
        """
        self.config = config or PortfolioConfig()

    def scan_positions(
        self,
        portfolio: PortfolioStateManager,
        scan_date: datetime = None
    ) -> RolloverScanResult:
        """
        Scan all open positions and identify those needing rollover

        Args:
            portfolio: Portfolio state manager with positions
            scan_date: Date to scan from (default: today)

        Returns:
            RolloverScanResult with candidates and statistics
        """
        if scan_date is None:
            scan_date = datetime.now()

        result = RolloverScanResult(
            scan_timestamp=scan_date,
            total_positions=0,
            positions_to_roll=0
        )

        # Get current portfolio state
        state = portfolio.get_current_state()
        open_positions = state.get_open_positions()

        result.total_positions = len(open_positions)

        if result.total_positions == 0:
            logger.info("No open positions to scan for rollover")
            return result

        logger.info(f"Scanning {result.total_positions} open positions for rollover")

        for pos_id, position in open_positions.items():
            try:
                candidate = self._check_position_for_rollover(position, scan_date)

                if candidate is not None:
                    result.candidates.append(candidate)
                    result.positions_to_roll += 1
                    logger.info(
                        f"  {pos_id}: NEEDS ROLLOVER "
                        f"(days={candidate.days_to_expiry}, "
                        f"expiry={candidate.current_expiry} -> {candidate.next_expiry})"
                    )
                else:
                    result.skipped.append({
                        'position_id': pos_id,
                        'reason': 'Not within rollover window'
                    })
                    logger.debug(f"  {pos_id}: No rollover needed")

            except Exception as e:
                error_msg = f"Error scanning {pos_id}: {str(e)}"
                result.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"Scan complete: {result.positions_to_roll}/{result.total_positions} "
            f"positions need rollover"
        )

        return result

    def _check_position_for_rollover(
        self,
        position: Position,
        scan_date: datetime
    ) -> Optional[RolloverCandidate]:
        """
        Check if a single position needs rollover

        Args:
            position: Position to check
            scan_date: Date to check from

        Returns:
            RolloverCandidate if rollover needed, None otherwise
        """
        # Skip positions already rolled or in progress
        if position.rollover_status in ['rolled', 'in_progress']:
            logger.debug(f"  {position.position_id}: Already rolled/in-progress")
            return None

        # Get expiry from position
        expiry_str = self._get_position_expiry(position)
        if expiry_str is None:
            logger.warning(f"  {position.position_id}: No expiry information")
            return None

        # Get rollover threshold for instrument
        if position.instrument == "BANK_NIFTY":
            rollover_days = self.config.banknifty_rollover_days
        elif position.instrument == "GOLD_MINI":
            rollover_days = self.config.gold_mini_rollover_days
        elif position.instrument == "COPPER":
            rollover_days = self.config.copper_rollover_days
        elif position.instrument == "SILVER_MINI":
            rollover_days = self.config.silver_mini_rollover_days
        else:
            logger.warning(f"  {position.position_id}: Unknown instrument {position.instrument}")
            return None

        # Check if within rollover window
        days = days_to_expiry(expiry_str, scan_date)

        if days >= rollover_days:
            # Not yet time to roll
            return None

        # Need to roll - calculate next expiry
        current_expiry_date = parse_expiry_string(expiry_str)
        if current_expiry_date is None:
            logger.error(f"  {position.position_id}: Could not parse expiry {expiry_str}")
            return None

        next_expiry_date, next_expiry_str = get_next_month_expiry(
            position.instrument,
            current_expiry_date
        )

        # Check if position is ALREADY in next month (e.g., a recent pyramid)
        if self._is_already_next_month(position, next_expiry_str):
            logger.debug(f"  {position.position_id}: Already in next month contract")
            return None

        return RolloverCandidate(
            position=position,
            days_to_expiry=days,
            current_expiry=expiry_str,
            next_expiry=next_expiry_str,
            next_expiry_date=next_expiry_date,
            instrument=position.instrument,
            reason=f"Within {rollover_days}-day rollover window ({days} days to expiry)"
        )

    def _get_position_expiry(self, position: Position) -> Optional[str]:
        """
        Get expiry string from position

        Bank Nifty uses `expiry` field
        Gold Mini/Copper use `contract_month` or `expiry` field
        """
        if position.instrument == "BANK_NIFTY":
            return position.expiry
        elif position.instrument in ("GOLD_MINI", "COPPER", "SILVER_MINI"):
            # MCX futures may have expiry or contract_month
            if position.expiry:
                return position.expiry
            elif position.contract_month:
                # Convert contract_month (DEC25) to expiry format (25DEC31)
                # This is approximate - assumes last day of month
                try:
                    mon = position.contract_month[:3]
                    yy = position.contract_month[3:5]
                    # Get last day of that month
                    month_map = {
                        'JAN': 31, 'FEB': 28, 'MAR': 31, 'APR': 30,
                        'MAY': 31, 'JUN': 30, 'JUL': 31, 'AUG': 31,
                        'SEP': 30, 'OCT': 31, 'NOV': 30, 'DEC': 31
                    }
                    dd = month_map.get(mon, 31)
                    return f"{yy}{mon}{dd:02d}"
                except (IndexError, ValueError):
                    return None
        return None

    def _is_already_next_month(self, position: Position, next_expiry: str) -> bool:
        """
        Check if position is already in the next month contract

        This handles the case where a pyramid entry already chose next month
        due to the entry-time rollover logic.
        """
        current_expiry = self._get_position_expiry(position)
        if current_expiry is None:
            return False

        # Compare expiry strings
        return current_expiry == next_expiry

    def scan_single_instrument(
        self,
        portfolio: PortfolioStateManager,
        instrument: str,
        scan_date: datetime = None
    ) -> RolloverScanResult:
        """
        Scan positions for a single instrument

        Args:
            portfolio: Portfolio state manager
            instrument: "BANK_NIFTY", "GOLD_MINI", or "COPPER"
            scan_date: Date to scan from

        Returns:
            RolloverScanResult for that instrument only
        """
        if scan_date is None:
            scan_date = datetime.now()

        result = RolloverScanResult(
            scan_timestamp=scan_date,
            total_positions=0,
            positions_to_roll=0
        )

        state = portfolio.get_current_state()
        instrument_positions = state.get_positions_for_instrument(instrument)

        result.total_positions = len(instrument_positions)

        for pos_id, position in instrument_positions.items():
            try:
                candidate = self._check_position_for_rollover(position, scan_date)

                if candidate is not None:
                    result.candidates.append(candidate)
                    result.positions_to_roll += 1

            except Exception as e:
                result.errors.append(f"Error scanning {pos_id}: {str(e)}")

        return result
