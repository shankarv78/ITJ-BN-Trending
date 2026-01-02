"""
Margin Monitor - Position Service

Filters and categorizes positions by index and expiry.
"""

from typing import List, TypedDict
from app.utils.symbol_parser import (
    parse_symbol, is_matching_expiry, is_matching_index, get_position_type
)


class FilteredPositions(TypedDict):
    """Result of filtering positions."""
    short_positions: List[dict]
    long_positions: List[dict]
    closed_positions: List[dict]
    excluded_positions: List[dict]


class PositionSummary(TypedDict):
    """Summary statistics for positions."""
    short_count: int
    short_qty: int
    short_pnl: float
    long_count: int
    long_qty: int
    long_pnl: float
    hedge_cost: float
    closed_count: int
    closed_pnl: float
    total_pnl: float
    # Breakdown by option type for hedge capacity checking
    short_ce_qty: int
    short_pe_qty: int
    long_ce_qty: int
    long_pe_qty: int


class PositionService:
    """Service for filtering and analyzing positions."""

    def filter_positions(
        self,
        positions: List[dict],
        index_name: str,
        expiry_date: str
    ) -> FilteredPositions:
        """
        Filter positions by index and expiry, categorize by quantity.

        Args:
            positions: List of raw positions from OpenAlgo
            index_name: Target index ('NIFTY' or 'SENSEX')
            expiry_date: Target expiry date (YYYY-MM-DD format)

        Returns:
            FilteredPositions with categorized positions:
            - short_positions: qty < 0 (options sold)
            - long_positions: qty > 0 (hedges)
            - closed_positions: qty = 0 (exited)
            - excluded_positions: wrong index or expiry
        """
        short_positions: List[dict] = []
        long_positions: List[dict] = []
        closed_positions: List[dict] = []
        excluded_positions: List[dict] = []

        for pos in positions:
            symbol = pos['symbol']
            quantity = pos['quantity']

            # Parse symbol to get details
            parsed = parse_symbol(symbol)

            # Check index match
            if not is_matching_index(symbol, index_name):
                excluded_positions.append({
                    **pos,
                    'reason': f'Index mismatch (not {index_name})'
                })
                continue

            # Check expiry match
            if not is_matching_expiry(symbol, expiry_date):
                actual_expiry = parsed.expiry_date if parsed else 'unknown'
                excluded_positions.append({
                    **pos,
                    'reason': f'Expiry mismatch ({actual_expiry})'
                })
                continue

            # Enrich position with parsed data
            enriched_pos = {
                **pos,
                'strike': parsed.strike if parsed else None,
                'option_type': parsed.option_type if parsed else None,
                'expiry_date': parsed.expiry_date if parsed else None,
                'position_type': get_position_type(quantity),
            }

            # Categorize by quantity
            if quantity < 0:
                short_positions.append(enriched_pos)
            elif quantity > 0:
                long_positions.append(enriched_pos)
            else:
                closed_positions.append(enriched_pos)

        return {
            'short_positions': short_positions,
            'long_positions': long_positions,
            'closed_positions': closed_positions,
            'excluded_positions': excluded_positions,
        }

    def calculate_hedge_cost(self, long_positions: List[dict]) -> float:
        """
        Calculate total premium paid for hedge (long) positions.

        Hedge cost = sum(average_price * quantity) for all long positions.

        Args:
            long_positions: List of long positions

        Returns:
            Total hedge cost in rupees.
        """
        return sum(
            pos['average_price'] * pos['quantity']
            for pos in long_positions
        )

    def get_summary(self, filtered: FilteredPositions) -> PositionSummary:
        """
        Generate summary statistics for filtered positions.

        Args:
            filtered: FilteredPositions from filter_positions()

        Returns:
            PositionSummary with counts, quantities, and P&L.
        """
        shorts = filtered['short_positions']
        longs = filtered['long_positions']
        closed = filtered['closed_positions']

        short_pnl = sum(p['pnl'] for p in shorts)
        long_pnl = sum(p['pnl'] for p in longs)
        closed_pnl = sum(p['pnl'] for p in closed)

        # Calculate qty by option type for hedge capacity limits
        short_ce_qty = sum(
            abs(p['quantity']) for p in shorts
            if p.get('option_type') == 'CE'
        )
        short_pe_qty = sum(
            abs(p['quantity']) for p in shorts
            if p.get('option_type') == 'PE'
        )
        long_ce_qty = sum(
            p['quantity'] for p in longs
            if p.get('option_type') == 'CE'
        )
        long_pe_qty = sum(
            p['quantity'] for p in longs
            if p.get('option_type') == 'PE'
        )

        return {
            'short_count': len(shorts),
            'short_qty': sum(abs(p['quantity']) for p in shorts),
            'short_pnl': short_pnl,
            'long_count': len(longs),
            'long_qty': sum(p['quantity'] for p in longs),
            'long_pnl': long_pnl,
            'hedge_cost': self.calculate_hedge_cost(longs),
            'closed_count': len(closed),
            'closed_pnl': closed_pnl,
            'total_pnl': short_pnl + long_pnl + closed_pnl,
            # Breakdown by option type
            'short_ce_qty': short_ce_qty,
            'short_pe_qty': short_pe_qty,
            'long_ce_qty': long_ce_qty,
            'long_pe_qty': long_pe_qty,
        }


    def get_hedge_capacity(self, summary: PositionSummary) -> dict:
        """
        Calculate remaining hedge capacity by option type.

        Hedge buying only provides margin benefit when hedge_qty <= sold_qty.
        Once you have hedges equal to your shorts, additional hedges provide NO benefit.

        Args:
            summary: PositionSummary with CE/PE breakdown

        Returns:
            Dict with remaining capacity for each option type:
            - remaining_ce_capacity: How many more CE hedges can be bought
            - remaining_pe_capacity: How many more PE hedges can be bought
            - is_fully_hedged: True if no more hedges can provide benefit
        """
        remaining_ce = max(0, summary['short_ce_qty'] - summary['long_ce_qty'])
        remaining_pe = max(0, summary['short_pe_qty'] - summary['long_pe_qty'])

        return {
            'remaining_ce_capacity': remaining_ce,
            'remaining_pe_capacity': remaining_pe,
            'short_ce_qty': summary['short_ce_qty'],
            'short_pe_qty': summary['short_pe_qty'],
            'long_ce_qty': summary['long_ce_qty'],
            'long_pe_qty': summary['long_pe_qty'],
            'is_fully_hedged': (remaining_ce == 0 and remaining_pe == 0),
        }


# Global service instance
position_service = PositionService()
