"""
Auto-Hedge System - Margin Calculator Service

Calculates margin requirements and projections for hedge decisions.
Determines when hedges are needed based on projected utilization.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.models.hedge_constants import (
    MarginConstants, HedgeConfig, LotSizes,
    IndexName, ExpiryType,
    MARGIN_CONSTANTS, HEDGE_CONFIG, LOT_SIZES
)

logger = logging.getLogger(__name__)


@dataclass
class MarginProjection:
    """Result of a margin projection calculation."""
    current_intraday_margin: float
    total_budget: float
    margin_for_next_entry: float
    projected_intraday_margin: float
    current_utilization: float
    projected_utilization: float
    hedge_required: bool
    margin_reduction_needed: float


@dataclass
class HedgeRequirement:
    """Details of hedge requirement for an upcoming entry."""
    is_required: bool
    current_utilization: float
    projected_utilization: float
    margin_reduction_needed: float
    target_utilization: float
    portfolio_name: str
    reason: str


class MarginCalculatorService:
    """
    Calculates margin requirements and projections.

    Core responsibilities:
    - Calculate margin per straddle for different index/expiry combinations
    - Project utilization after adding a new entry
    - Determine if hedge is required
    - Calculate margin reduction needed from hedges
    - Estimate hedge margin benefit
    """

    def __init__(
        self,
        constants: MarginConstants = None,
        config: HedgeConfig = None,
        lot_sizes: LotSizes = None
    ):
        """
        Initialize the margin calculator.

        Args:
            constants: MarginConstants (uses global default if not provided)
            config: HedgeConfig (uses global default if not provided)
            lot_sizes: LotSizes (uses global default if not provided)
        """
        self.constants = constants or MARGIN_CONSTANTS
        self.config = config or HEDGE_CONFIG
        self.lot_sizes = lot_sizes or LOT_SIZES

    def get_margin_per_straddle(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        has_hedge: bool,
        num_baskets: int = 1
    ) -> float:
        """
        Get margin requirement for one straddle.

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            has_hedge: Whether hedges are in place
            num_baskets: Number of baskets

        Returns:
            Total margin requirement in INR
        """
        return self.constants.get_margin(
            index=index,
            expiry_type=expiry_type,
            has_hedge=has_hedge,
            num_baskets=num_baskets
        )

    def calculate_current_utilization(
        self,
        intraday_margin: float,
        total_budget: float
    ) -> float:
        """
        Calculate current utilization percentage.

        Args:
            intraday_margin: Current intraday margin used
            total_budget: Total available budget

        Returns:
            Utilization percentage (0-100+)
        """
        if total_budget <= 0:
            return 0.0
        return (intraday_margin / total_budget) * 100

    def calculate_projected_utilization(
        self,
        current_intraday_margin: float,
        total_budget: float,
        margin_for_next_entry: float
    ) -> float:
        """
        Calculate projected utilization after next entry.

        Args:
            current_intraday_margin: Current intraday margin
            total_budget: Total available budget
            margin_for_next_entry: Margin required for next entry

        Returns:
            Projected utilization percentage
        """
        projected_margin = current_intraday_margin + margin_for_next_entry
        return self.calculate_current_utilization(projected_margin, total_budget)

    def is_hedge_required(
        self,
        projected_utilization: float,
        trigger_pct: float = None
    ) -> bool:
        """
        Determine if hedge is required based on projected utilization.

        Args:
            projected_utilization: Projected utilization after entry
            trigger_pct: Threshold to trigger hedge (default: config value)

        Returns:
            True if hedge is required
        """
        if trigger_pct is None:
            trigger_pct = self.config.entry_trigger_pct

        return projected_utilization > trigger_pct

    def calculate_margin_reduction_needed(
        self,
        current_intraday_margin: float,
        total_budget: float,
        margin_for_next_entry: float,
        target_pct: float = None
    ) -> float:
        """
        Calculate how much margin reduction is needed from hedges.

        Args:
            current_intraday_margin: Current intraday margin
            total_budget: Total available budget
            margin_for_next_entry: Margin required for next entry
            target_pct: Target utilization after hedge (default: config value)

        Returns:
            Margin reduction needed in INR (0 if no reduction needed)
        """
        if target_pct is None:
            target_pct = self.config.entry_target_pct

        projected_margin = current_intraday_margin + margin_for_next_entry
        target_margin = total_budget * (target_pct / 100)

        reduction_needed = projected_margin - target_margin
        return max(0, reduction_needed)

    def estimate_hedge_margin_benefit(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        num_baskets: int = 1
    ) -> float:
        """
        Estimate margin reduction from adding one hedge pair (CE + PE).

        Args:
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            num_baskets: Number of baskets

        Returns:
            Estimated margin reduction in INR
        """
        return self.constants.get_hedge_benefit(
            index=index,
            expiry_type=expiry_type,
            num_baskets=num_baskets
        )

    def calculate_full_projection(
        self,
        current_intraday_margin: float,
        total_budget: float,
        index: IndexName,
        expiry_type: ExpiryType,
        num_baskets: int,
        has_existing_hedge: bool = False
    ) -> MarginProjection:
        """
        Calculate full margin projection for next entry.

        Args:
            current_intraday_margin: Current intraday margin
            total_budget: Total available budget
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            num_baskets: Number of baskets for the entry
            has_existing_hedge: Whether hedges are already in place

        Returns:
            MarginProjection with all details
        """
        # Get margin for next entry
        margin_for_entry = self.get_margin_per_straddle(
            index=index,
            expiry_type=expiry_type,
            has_hedge=has_existing_hedge,
            num_baskets=num_baskets
        )

        # Calculate utilizations
        current_util = self.calculate_current_utilization(
            current_intraday_margin, total_budget
        )
        projected_util = self.calculate_projected_utilization(
            current_intraday_margin, total_budget, margin_for_entry
        )

        # Check if hedge required
        hedge_required = self.is_hedge_required(projected_util)

        # Calculate reduction needed
        reduction_needed = 0.0
        if hedge_required:
            reduction_needed = self.calculate_margin_reduction_needed(
                current_intraday_margin, total_budget, margin_for_entry
            )

        return MarginProjection(
            current_intraday_margin=current_intraday_margin,
            total_budget=total_budget,
            margin_for_next_entry=margin_for_entry,
            projected_intraday_margin=current_intraday_margin + margin_for_entry,
            current_utilization=current_util,
            projected_utilization=projected_util,
            hedge_required=hedge_required,
            margin_reduction_needed=reduction_needed
        )

    def evaluate_hedge_requirement(
        self,
        current_intraday_margin: float,
        total_budget: float,
        index: IndexName,
        expiry_type: ExpiryType,
        num_baskets: int,
        portfolio_name: str
    ) -> HedgeRequirement:
        """
        Evaluate if hedge is required for an upcoming entry.

        This is the main method used by the orchestrator to determine
        if hedge action is needed.

        Args:
            current_intraday_margin: Current intraday margin
            total_budget: Total available budget
            index: NIFTY or SENSEX
            expiry_type: 0DTE, 1DTE, or 2DTE
            num_baskets: Number of baskets
            portfolio_name: Name of the portfolio for logging

        Returns:
            HedgeRequirement with decision details
        """
        projection = self.calculate_full_projection(
            current_intraday_margin=current_intraday_margin,
            total_budget=total_budget,
            index=index,
            expiry_type=expiry_type,
            num_baskets=num_baskets,
            has_existing_hedge=False
        )

        # Build reason string
        if projection.hedge_required:
            reason = (
                f"Projected util {projection.projected_utilization:.1f}% "
                f"> trigger {self.config.entry_trigger_pct}%"
            )
        else:
            reason = (
                f"Projected util {projection.projected_utilization:.1f}% "
                f"within safe range"
            )

        logger.info(
            f"[MARGIN_CALC] {portfolio_name}: "
            f"current={projection.current_utilization:.1f}%, "
            f"projected={projection.projected_utilization:.1f}%, "
            f"hedge_required={projection.hedge_required}"
        )

        return HedgeRequirement(
            is_required=projection.hedge_required,
            current_utilization=projection.current_utilization,
            projected_utilization=projection.projected_utilization,
            margin_reduction_needed=projection.margin_reduction_needed,
            target_utilization=self.config.entry_target_pct,
            portfolio_name=portfolio_name,
            reason=reason
        )

    def should_exit_hedge(
        self,
        current_utilization: float,
        trigger_pct: float = None
    ) -> bool:
        """
        Check if utilization is low enough to exit hedges.

        Args:
            current_utilization: Current utilization percentage
            trigger_pct: Threshold below which to exit (default: config value)

        Returns:
            True if hedge should be considered for exit
        """
        if trigger_pct is None:
            trigger_pct = self.config.exit_trigger_pct

        return current_utilization < trigger_pct
