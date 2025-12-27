"""
Strategy Manager

Manages trading strategies with:
- Strategy CRUD operations
- Cumulative P&L tracking across position cycles
- Trade history for audit trail
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


# Strategy IDs for system strategies (seeded in migration)
STRATEGY_ITJ_TREND_FOLLOW = 1
STRATEGY_UNKNOWN = 2


@dataclass
class Strategy:
    """Trading strategy with capital allocation and P&L tracking"""
    strategy_id: int
    strategy_name: str
    description: Optional[str] = None
    allocated_capital: float = 0.0
    cumulative_realized_pnl: float = 0.0
    is_system: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'strategy_id': self.strategy_id,
            'strategy_name': self.strategy_name,
            'description': self.description,
            'allocated_capital': float(self.allocated_capital),
            'cumulative_realized_pnl': float(self.cumulative_realized_pnl),
            'is_system': self.is_system,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class TradeHistoryEntry:
    """Closed trade for audit trail and P&L history"""
    trade_id: Optional[int] = None
    strategy_id: int = STRATEGY_ITJ_TREND_FOLLOW
    position_id: str = ""
    instrument: str = ""
    symbol: Optional[str] = None
    direction: str = "LONG"  # LONG or SHORT
    lots: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    realized_pnl: float = 0.0
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'trade_id': self.trade_id,
            'strategy_id': self.strategy_id,
            'position_id': self.position_id,
            'instrument': self.instrument,
            'symbol': self.symbol,
            'direction': self.direction,
            'lots': self.lots,
            'entry_price': float(self.entry_price),
            'exit_price': float(self.exit_price),
            'realized_pnl': float(self.realized_pnl),
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None
        }


@dataclass
class StrategyPnL:
    """P&L summary for a strategy"""
    strategy_id: int
    strategy_name: str
    cumulative_realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    return_pct: Optional[float] = None  # Return % if capital is set
    open_positions_count: int = 0
    total_trades: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'strategy_id': self.strategy_id,
            'strategy_name': self.strategy_name,
            'cumulative_realized_pnl': float(self.cumulative_realized_pnl),
            'unrealized_pnl': float(self.unrealized_pnl),
            'total_pnl': float(self.total_pnl),
            'return_pct': float(self.return_pct) if self.return_pct is not None else None,
            'open_positions_count': self.open_positions_count,
            'total_trades': self.total_trades
        }


class StrategyManager:
    """
    Manages trading strategies with P&L tracking

    Features:
    - CRUD operations for strategies
    - Cumulative P&L tracking (persists across position cycles)
    - Trade history logging for audit
    - Strategy-level unrealized P&L calculation
    """

    def __init__(self, db_state_manager):
        """
        Initialize StrategyManager with database connection

        Args:
            db_state_manager: DatabaseStateManager instance with connection pool
        """
        self.db = db_state_manager
        self._strategy_cache: Dict[int, Strategy] = {}
        logger.info("StrategyManager initialized")

    # ===== STRATEGY CRUD OPERATIONS =====

    def get_all_strategies(self, include_inactive: bool = False) -> List[Strategy]:
        """
        Get all strategies

        Args:
            include_inactive: Whether to include inactive strategies

        Returns:
            List of Strategy objects
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = "SELECT * FROM trading_strategies"
            if not include_inactive:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY strategy_id"

            cursor.execute(query)

            strategies = []
            for row in cursor.fetchall():
                strategy = self._dict_to_strategy(dict(row))
                strategies.append(strategy)
                self._strategy_cache[strategy.strategy_id] = strategy

            return strategies

    def get_strategy(self, strategy_id: int) -> Optional[Strategy]:
        """
        Get strategy by ID

        Args:
            strategy_id: Strategy ID

        Returns:
            Strategy object or None if not found
        """
        # Check cache
        if strategy_id in self._strategy_cache:
            return self._strategy_cache[strategy_id]

        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM trading_strategies WHERE strategy_id = %s",
                (strategy_id,)
            )
            row = cursor.fetchone()

            if row:
                strategy = self._dict_to_strategy(dict(row))
                self._strategy_cache[strategy_id] = strategy
                return strategy

        return None

    def get_strategy_by_name(self, name: str) -> Optional[Strategy]:
        """
        Get strategy by name

        Args:
            name: Strategy name

        Returns:
            Strategy object or None if not found
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM trading_strategies WHERE strategy_name = %s",
                (name,)
            )
            row = cursor.fetchone()

            if row:
                strategy = self._dict_to_strategy(dict(row))
                self._strategy_cache[strategy.strategy_id] = strategy
                return strategy

        return None

    def create_strategy(self, name: str, description: str = None,
                       allocated_capital: float = 0.0) -> Strategy:
        """
        Create a new strategy

        Args:
            name: Strategy name (must be unique)
            description: Optional description
            allocated_capital: Capital allocated to this strategy

        Returns:
            Created Strategy object

        Raises:
            ValueError: If name already exists
        """
        with self.db.transaction() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Check for duplicate name
            cursor.execute(
                "SELECT 1 FROM trading_strategies WHERE strategy_name = %s",
                (name,)
            )
            if cursor.fetchone():
                raise ValueError(f"Strategy with name '{name}' already exists")

            # Insert new strategy
            cursor.execute("""
                INSERT INTO trading_strategies
                (strategy_name, description, allocated_capital, is_system, is_active)
                VALUES (%s, %s, %s, FALSE, TRUE)
                RETURNING *
            """, (name, description, allocated_capital))

            row = cursor.fetchone()
            strategy = self._dict_to_strategy(dict(row))
            self._strategy_cache[strategy.strategy_id] = strategy

            logger.info(f"Strategy created: {name} (ID: {strategy.strategy_id})")
            return strategy

    def update_strategy(self, strategy_id: int, name: str = None,
                       description: str = None, allocated_capital: float = None,
                       is_active: bool = None) -> Optional[Strategy]:
        """
        Update an existing strategy

        Args:
            strategy_id: Strategy ID to update
            name: New name (optional)
            description: New description (optional)
            allocated_capital: New capital allocation (optional)
            is_active: New active status (optional)

        Returns:
            Updated Strategy object or None if not found

        Raises:
            ValueError: If trying to modify system strategy name
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return None

        # Prevent modifying system strategy names
        if strategy.is_system and name and name != strategy.strategy_name:
            raise ValueError(f"Cannot rename system strategy '{strategy.strategy_name}'")

        with self.db.transaction() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Build update query dynamically
            updates = []
            params = []

            if name is not None:
                updates.append("strategy_name = %s")
                params.append(name)
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if allocated_capital is not None:
                updates.append("allocated_capital = %s")
                params.append(allocated_capital)
            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)

            if not updates:
                return strategy

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(strategy_id)

            cursor.execute(f"""
                UPDATE trading_strategies
                SET {', '.join(updates)}
                WHERE strategy_id = %s
                RETURNING *
            """, tuple(params))

            row = cursor.fetchone()
            if row:
                strategy = self._dict_to_strategy(dict(row))
                self._strategy_cache[strategy_id] = strategy
                logger.info(f"Strategy updated: {strategy.strategy_name}")
                return strategy

        return None

    def delete_strategy(self, strategy_id: int, force: bool = False) -> bool:
        """
        Delete a strategy

        Args:
            strategy_id: Strategy ID to delete
            force: If True, reassign positions to 'unknown' strategy before deleting

        Returns:
            True if deleted, False otherwise

        Raises:
            ValueError: If trying to delete system strategy or strategy has positions
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return False

        if strategy.is_system:
            raise ValueError(f"Cannot delete system strategy '{strategy.strategy_name}'")

        with self.db.transaction() as conn:
            cursor = conn.cursor()

            # Check for positions
            cursor.execute(
                "SELECT COUNT(*) FROM portfolio_positions WHERE strategy_id = %s AND status = 'open'",
                (strategy_id,)
            )
            position_count = cursor.fetchone()[0]

            if position_count > 0:
                if force:
                    # Reassign to unknown strategy
                    cursor.execute("""
                        UPDATE portfolio_positions
                        SET strategy_id = %s
                        WHERE strategy_id = %s
                    """, (STRATEGY_UNKNOWN, strategy_id))
                    logger.info(f"Reassigned {position_count} positions to 'unknown' strategy")
                else:
                    raise ValueError(
                        f"Cannot delete strategy with {position_count} open positions. "
                        "Use force=True to reassign to 'unknown' strategy."
                    )

            # Delete strategy
            cursor.execute(
                "DELETE FROM trading_strategies WHERE strategy_id = %s",
                (strategy_id,)
            )

            # Clear from cache
            if strategy_id in self._strategy_cache:
                del self._strategy_cache[strategy_id]

            logger.info(f"Strategy deleted: {strategy.strategy_name}")
            return True

    # ===== P&L TRACKING =====

    def log_closed_position(self, position, exit_price: float,
                           exit_timestamp: datetime = None) -> bool:
        """
        Log a closed position to trade history and update strategy P&L

        Called when a position is closed to:
        1. Record trade in strategy_trade_history
        2. Update strategy's cumulative_realized_pnl

        Args:
            position: Position object (with strategy_id)
            exit_price: Price at which position was closed
            exit_timestamp: When position was closed (default: now)

        Returns:
            True if successful
        """
        if exit_timestamp is None:
            exit_timestamp = datetime.now()

        # Get strategy_id from position (default to ITJ Trend Follow)
        strategy_id = getattr(position, 'strategy_id', STRATEGY_ITJ_TREND_FOLLOW)

        # Calculate realized P&L
        # For Bank Nifty: point_value = 30 (lot_size × 1) - Dec 2025 onwards
        # For Gold Mini: point_value = 10 (100g × 0.1/g)
        # For Silver Mini: point_value = 5 (5kg × 1/kg)
        # For Copper: point_value = 2500 (2500kg × 1/kg)
        if position.instrument == 'BANK_NIFTY':
            point_value = 30
        elif position.instrument == 'COPPER':
            point_value = 2500
        elif position.instrument == 'SILVER_MINI':
            point_value = 5
        else:  # GOLD_MINI
            point_value = 10
        realized_pnl = (exit_price - position.entry_price) * position.lots * point_value

        # Determine direction
        direction = "LONG"  # We only support LONG positions currently

        # Get symbol for audit trail
        symbol = None
        if position.instrument == 'BANK_NIFTY':
            symbol = f"{position.pe_symbol}/{position.ce_symbol}" if position.pe_symbol else None
        else:
            symbol = position.futures_symbol

        with self.db.transaction() as conn:
            cursor = conn.cursor()

            # 1. Insert trade history record
            cursor.execute("""
                INSERT INTO strategy_trade_history
                (strategy_id, position_id, instrument, symbol, direction, lots,
                 entry_price, exit_price, realized_pnl, opened_at, closed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                strategy_id,
                position.position_id,
                position.instrument,
                symbol,
                direction,
                position.lots,
                position.entry_price,
                exit_price,
                realized_pnl,
                position.entry_timestamp,
                exit_timestamp
            ))

            # 2. Update strategy's cumulative realized P&L
            cursor.execute("""
                UPDATE trading_strategies
                SET cumulative_realized_pnl = cumulative_realized_pnl + %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE strategy_id = %s
            """, (realized_pnl, strategy_id))

            # Clear cache
            if strategy_id in self._strategy_cache:
                del self._strategy_cache[strategy_id]

            logger.info(
                f"Trade logged: {position.position_id} closed with P&L {realized_pnl:+,.2f} "
                f"for strategy {strategy_id}"
            )
            return True

    def get_strategy_pnl(self, strategy_id: int,
                        open_positions: Dict[str, 'Position'] = None) -> Optional[StrategyPnL]:
        """
        Get P&L summary for a strategy

        Args:
            strategy_id: Strategy ID
            open_positions: Optional dict of open positions (to calculate unrealized P&L)

        Returns:
            StrategyPnL object or None if strategy not found
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return None

        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get trade count
            cursor.execute(
                "SELECT COUNT(*) as count FROM strategy_trade_history WHERE strategy_id = %s",
                (strategy_id,)
            )
            total_trades = cursor.fetchone()['count']

            # Get open position count
            cursor.execute(
                "SELECT COUNT(*) as count FROM portfolio_positions WHERE strategy_id = %s AND status = 'open'",
                (strategy_id,)
            )
            open_count = cursor.fetchone()['count']

        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0.0
        if open_positions:
            for pos in open_positions.values():
                pos_strategy_id = getattr(pos, 'strategy_id', STRATEGY_ITJ_TREND_FOLLOW)
                if pos_strategy_id == strategy_id:
                    unrealized_pnl += pos.unrealized_pnl or 0.0

        # Calculate return %
        return_pct = None
        if strategy.allocated_capital > 0:
            total_pnl = strategy.cumulative_realized_pnl + unrealized_pnl
            return_pct = (total_pnl / strategy.allocated_capital) * 100

        return StrategyPnL(
            strategy_id=strategy_id,
            strategy_name=strategy.strategy_name,
            cumulative_realized_pnl=strategy.cumulative_realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=strategy.cumulative_realized_pnl + unrealized_pnl,
            return_pct=return_pct,
            open_positions_count=open_count,
            total_trades=total_trades
        )

    def get_trade_history(self, strategy_id: int = None,
                         limit: int = 100) -> List[TradeHistoryEntry]:
        """
        Get trade history for a strategy (or all strategies)

        Args:
            strategy_id: Optional strategy ID filter
            limit: Maximum number of records to return

        Returns:
            List of TradeHistoryEntry objects
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if strategy_id:
                cursor.execute("""
                    SELECT * FROM strategy_trade_history
                    WHERE strategy_id = %s
                    ORDER BY closed_at DESC
                    LIMIT %s
                """, (strategy_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM strategy_trade_history
                    ORDER BY closed_at DESC
                    LIMIT %s
                """, (limit,))

            trades = []
            for row in cursor.fetchall():
                trades.append(self._dict_to_trade_history(dict(row)))

            return trades

    # ===== POSITION-STRATEGY MANAGEMENT =====

    def reassign_position(self, position_id: str, new_strategy_id: int) -> bool:
        """
        Reassign a position to a different strategy

        Args:
            position_id: Position ID to reassign
            new_strategy_id: Target strategy ID

        Returns:
            True if successful

        Raises:
            ValueError: If strategy doesn't exist
        """
        # Verify strategy exists
        if not self.get_strategy(new_strategy_id):
            raise ValueError(f"Strategy {new_strategy_id} not found")

        with self.db.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE portfolio_positions
                SET strategy_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE position_id = %s
            """, (new_strategy_id, position_id))

            if cursor.rowcount > 0:
                logger.info(f"Position {position_id} reassigned to strategy {new_strategy_id}")
                return True

        return False

    def get_positions_for_strategy(self, strategy_id: int,
                                   status: str = 'open') -> List[dict]:
        """
        Get all positions for a strategy

        Args:
            strategy_id: Strategy ID
            status: Position status filter ('open', 'closed', 'all')

        Returns:
            List of position dictionaries
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if status == 'all':
                cursor.execute("""
                    SELECT * FROM portfolio_positions
                    WHERE strategy_id = %s
                    ORDER BY entry_timestamp
                """, (strategy_id,))
            else:
                cursor.execute("""
                    SELECT * FROM portfolio_positions
                    WHERE strategy_id = %s AND status = %s
                    ORDER BY entry_timestamp
                """, (strategy_id, status))

            return [dict(row) for row in cursor.fetchall()]

    # ===== HELPER METHODS =====

    def _dict_to_strategy(self, row: dict) -> Strategy:
        """Convert database row to Strategy dataclass"""
        return Strategy(
            strategy_id=row['strategy_id'],
            strategy_name=row['strategy_name'],
            description=row.get('description'),
            allocated_capital=float(row.get('allocated_capital', 0) or 0),
            cumulative_realized_pnl=float(row.get('cumulative_realized_pnl', 0) or 0),
            is_system=row.get('is_system', False),
            is_active=row.get('is_active', True),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def _dict_to_trade_history(self, row: dict) -> TradeHistoryEntry:
        """Convert database row to TradeHistoryEntry dataclass"""
        return TradeHistoryEntry(
            trade_id=row.get('trade_id'),
            strategy_id=row.get('strategy_id', STRATEGY_ITJ_TREND_FOLLOW),
            position_id=row.get('position_id', ''),
            instrument=row.get('instrument', ''),
            symbol=row.get('symbol'),
            direction=row.get('direction', 'LONG'),
            lots=row.get('lots', 0),
            entry_price=float(row.get('entry_price', 0) or 0),
            exit_price=float(row.get('exit_price', 0) or 0),
            realized_pnl=float(row.get('realized_pnl', 0) or 0),
            opened_at=row.get('opened_at'),
            closed_at=row.get('closed_at')
        )

    def invalidate_cache(self):
        """Clear the strategy cache"""
        self._strategy_cache.clear()
        logger.debug("Strategy cache invalidated")
