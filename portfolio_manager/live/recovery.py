"""
Crash Recovery Manager

Implements state recovery from PostgreSQL on application startup.
Restores PortfolioStateManager and LiveTradingEngine to their last known state
before a crash or restart.

Key Features:
- Fetches all open positions from database
- Restores portfolio financial state (cash, equity, risk)
- Rehydrates LiveTradingEngine position tracking
- Validates data consistency before resuming operations
- Retry logic with exponential backoff for database operations
- Integration with HA system (RedisCoordinator) for recovery status
"""
import logging
import time
from typing import Dict, Optional, Tuple

from core.models import Position
from core.portfolio_state import PortfolioStateManager
from live.engine import LiveTradingEngine

logger = logging.getLogger(__name__)


class StateInconsistencyError(Exception):
    """Raised when loaded state fails consistency validation"""
    pass


class CrashRecoveryManager:
    """
    Manages crash recovery by loading application state from PostgreSQL

    This class is responsible for:
    1. Fetching all state data from database (positions, portfolio state, pyramiding state)
    2. Reconstructing PortfolioStateManager internal state
    3. Re-populating LiveTradingEngine active positions
    4. Validating data consistency
    5. Coordinating with HA system during recovery
    """

    # Error codes for recovery failures
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    DATA_CORRUPT = "DATA_CORRUPT"
    VALIDATION_FAILED = "VALIDATION_FAILED"

    def __init__(self, db_manager):
        """
        Initialize crash recovery manager

        Args:
            db_manager: DatabaseStateManager instance for database access
        """
        self.db_manager = db_manager
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s
        # Note: consistency_epsilon removed - we now refresh cache instead of comparing

    def load_state(
        self,
        portfolio_manager: PortfolioStateManager,
        trading_engine: LiveTradingEngine,
        coordinator=None
    ) -> Tuple[bool, Optional[str]]:
        """
        Load application state from database and rehydrate in-memory objects

        This is the main entry point for crash recovery. It:
        1. Sets instance status to 'recovering' in HA system
        2. Fetches all state data from database with retry logic
        3. Reconstructs PortfolioStateManager state
        4. Re-populates LiveTradingEngine positions
        5. Validates consistency
        6. Sets instance status back to 'active' on success
        7. Returns success status and error code if failed

        Args:
            portfolio_manager: PortfolioStateManager to rehydrate
            trading_engine: LiveTradingEngine to rehydrate
            coordinator: Optional RedisCoordinator for HA system integration

        Returns:
            Tuple of (success: bool, error_code: Optional[str])
            - (True, None) on success
            - (False, error_code) on failure
        """
        logger.info("=" * 60)
        logger.info("CRASH RECOVERY: Starting state restoration from database")
        logger.info("=" * 60)

        # Step 0: Set instance status to 'recovering' in HA system
        if coordinator and coordinator.db_manager:
            try:
                coordinator.db_manager.upsert_instance_metadata(
                    instance_id=coordinator.instance_id,
                    is_leader=False,  # Not leader during recovery
                    status='recovering',
                    hostname=coordinator._get_hostname_safe() if hasattr(coordinator, '_get_hostname_safe') else None
                )
                logger.info("Instance status set to 'recovering' in HA system")
            except Exception as e:
                logger.warning(f"Failed to set recovery status in HA system: {e}")
                # Continue with recovery even if status update fails

        try:
            # Step 1: Fetch all state data from database (with retry)
            state_data = self._fetch_state_data()
            if state_data is None:
                logger.error("Failed to fetch state data from database")
                return False, self.DB_UNAVAILABLE

            # Step 2: Reconstruct PortfolioStateManager internal state
            self._reconstruct_portfolio_state(portfolio_manager, state_data)

            # Step 3: Re-populate LiveTradingEngine active positions
            self._reconstruct_trading_engine(trading_engine, state_data)

            # Step 4: Validate data consistency
            validation_result = self._validate_state_consistency(
                portfolio_manager,
                trading_engine,
                state_data
            )

            if not validation_result[0]:
                logger.error(f"State consistency validation failed: {validation_result[1]}")
                return False, self.VALIDATION_FAILED

            # Get calculated state (not stale database values)
            calculated_state = portfolio_manager.get_current_state()

            logger.info("=" * 60)
            logger.info("CRASH RECOVERY: State restoration completed successfully")
            logger.info(f"  - Loaded {len(state_data['positions'])} open positions")
            logger.info(f"  - Portfolio closed equity: ₹{portfolio_manager.closed_equity:,.0f}")
            logger.info(f"  - Total risk (calculated): ₹{calculated_state.total_risk_amount:,.0f} ({calculated_state.total_risk_percent:.2%})")
            logger.info(f"  - Margin used: ₹{calculated_state.margin_used:,.0f}")
            logger.info(f"  - Total unrealized P&L: ₹{sum(p.unrealized_pnl for p in state_data['positions'].values()):,.0f}")
            logger.info("=" * 60)

            # Set instance status back to 'active' in HA system
            if coordinator and coordinator.db_manager:
                try:
                    coordinator.db_manager.upsert_instance_metadata(
                        instance_id=coordinator.instance_id,
                        is_leader=False,  # Will be set by leader election
                        status='active',
                        hostname=coordinator._get_hostname_safe() if hasattr(coordinator, '_get_hostname_safe') else None
                    )
                    logger.info("Instance status set to 'active' in HA system - ready for leader election")
                except Exception as e:
                    logger.warning(f"Failed to set active status in HA system: {e}")
                    # Recovery succeeded, but status update failed - log warning

            return True, None

        except StateInconsistencyError as e:
            logger.error(f"State consistency error: {e}")
            # Set status to indicate recovery failure
            if coordinator and coordinator.db_manager:
                try:
                    coordinator.db_manager.upsert_instance_metadata(
                        instance_id=coordinator.instance_id,
                        is_leader=False,
                        status='crashed',  # Mark as crashed due to validation failure
                        hostname=coordinator._get_hostname_safe() if hasattr(coordinator, '_get_hostname_safe') else None
                    )
                except Exception:
                    pass  # Ignore errors when setting failed status
            return False, self.VALIDATION_FAILED
        except Exception as e:
            logger.exception(f"Unexpected error during recovery: {e}")
            # Set status to indicate recovery failure
            if coordinator and coordinator.db_manager:
                try:
                    coordinator.db_manager.upsert_instance_metadata(
                        instance_id=coordinator.instance_id,
                        is_leader=False,
                        status='crashed',  # Mark as crashed due to unexpected error
                        hostname=coordinator._get_hostname_safe() if hasattr(coordinator, '_get_hostname_safe') else None
                    )
                except Exception:
                    pass  # Ignore errors when setting failed status
            return False, self.DATA_CORRUPT

    def _fetch_state_data(self) -> Optional[Dict]:
        """
        Fetch all application state from database with retry logic

        Returns:
            Dictionary with keys:
            - 'positions': Dict[str, Position] - All open positions
            - 'portfolio_state': dict - Portfolio state from database
            - 'pyramiding_state': Dict[str, dict] - Pyramiding state per instrument
            None if all retries fail
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching state data from database (attempt {attempt + 1}/{self.max_retries})")

                # Fetch all open positions
                positions = self.db_manager.get_all_open_positions()
                logger.info(f"Fetched {len(positions)} open positions")

                # Validate positions data
                for pos_id, position in positions.items():
                    if not isinstance(position, Position):
                        raise ValueError(f"Invalid position type for {pos_id}: {type(position)}")
                    # Check critical fields
                    if not position.position_id or not position.instrument:
                        raise ValueError(f"Position {pos_id} missing critical fields")

                # Fetch portfolio state
                portfolio_state = self.db_manager.get_portfolio_state()
                if portfolio_state is None:
                    logger.warning("No portfolio state found in database - using defaults")
                    portfolio_state = {}
                else:
                    logger.info("Fetched portfolio state from database")
                    # Validate portfolio state has expected structure
                    if 'closed_equity' in portfolio_state:
                        try:
                            float(portfolio_state['closed_equity'])
                        except (ValueError, TypeError) as e:
                            raise ValueError(f"Invalid closed_equity value: {e}")

                # Fetch pyramiding state
                pyramiding_state = self.db_manager.get_pyramiding_state()
                logger.info(f"Fetched pyramiding state for {len(pyramiding_state)} instruments")

                # Validate pyramiding state structure
                for instrument, state in pyramiding_state.items():
                    if not isinstance(state, dict):
                        raise ValueError(f"Invalid pyramiding state type for {instrument}: {type(state)}")
                    if 'last_pyramid_price' in state and state['last_pyramid_price'] is not None:
                        try:
                            float(state['last_pyramid_price'])
                        except (ValueError, TypeError) as e:
                            raise ValueError(f"Invalid last_pyramid_price for {instrument}: {e}")

                return {
                    'positions': positions,
                    'portfolio_state': portfolio_state,
                    'pyramiding_state': pyramiding_state
                }

            except (ValueError, TypeError) as e:
                # Data corruption detected - don't retry
                logger.error(f"Data corruption detected in database: {e}")
                raise StateInconsistencyError(f"Data corruption: {e}")
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delays[attempt]
                    logger.warning(
                        f"Failed to fetch state data (attempt {attempt + 1}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch state data after {self.max_retries} attempts: {e}")
                    return None

        return None

    def _reconstruct_portfolio_state(
        self,
        portfolio_manager: PortfolioStateManager,
        state_data: Dict
    ):
        """
        Reconstruct PortfolioStateManager internal state from database records

        Maps database columns to PortfolioStateManager attributes:
        - closed_equity: From portfolio_state.closed_equity
        - positions: From portfolio_positions (already loaded)

        Args:
            portfolio_manager: PortfolioStateManager to rehydrate
            state_data: State data dictionary from _fetch_state_data()
        """
        logger.info("Reconstructing PortfolioStateManager state...")

        portfolio_state = state_data['portfolio_state']
        positions = state_data['positions']

        # Restore closed_equity (CRITICAL - this is the cash + realized P&L)
        if 'closed_equity' in portfolio_state:
            # Convert Decimal to float
            closed_equity = float(portfolio_state['closed_equity'])
            portfolio_manager.closed_equity = closed_equity
            logger.info(f"Restored closed_equity: ₹{closed_equity:,.0f}")
        else:
            logger.warning("No closed_equity in database, using initial_capital")
            # closed_equity already set in __init__, no need to change

        # Restore positions (already loaded as Position objects)
        portfolio_manager.positions = positions
        logger.info(f"Restored {len(positions)} positions to PortfolioStateManager")

        logger.info("PortfolioStateManager state reconstruction complete")

    def _reconstruct_trading_engine(
        self,
        trading_engine: LiveTradingEngine,
        state_data: Dict
    ):
        """
        Re-populate LiveTradingEngine active positions and pyramiding state

        Restores:
        - active_positions map (via portfolio.positions)
        - last_pyramid_price dict
        - base_positions dict

        Args:
            trading_engine: LiveTradingEngine to rehydrate
            state_data: State data dictionary from _fetch_state_data()
        """
        logger.info("Reconstructing LiveTradingEngine state...")

        positions = state_data['positions']
        pyramiding_state = state_data['pyramiding_state']

        # Positions are already loaded into portfolio.positions by PortfolioStateManager
        # The trading engine shares the same portfolio instance, so positions are already there
        logger.info(f"Trading engine has access to {len(positions)} positions via portfolio")

        # Restore pyramiding state
        # Ensure attributes exist (they may not be initialized if db_manager was None)
        if not hasattr(trading_engine, 'last_pyramid_price'):
            trading_engine.last_pyramid_price = {}
        if not hasattr(trading_engine, 'base_positions'):
            trading_engine.base_positions = {}

        # Clear existing state before restoring
        trading_engine.last_pyramid_price.clear()
        trading_engine.base_positions.clear()

        for instrument, pyr_state in pyramiding_state.items():
            # Restore last_pyramid_price
            last_pyr_price = pyr_state.get('last_pyramid_price')
            if last_pyr_price is not None:
                trading_engine.last_pyramid_price[instrument] = float(last_pyr_price)
                logger.info(f"Restored last_pyramid_price for {instrument}: ₹{last_pyr_price:,.2f}")

            # Restore base_position reference
            base_pos_id = pyr_state.get('base_position_id')
            if base_pos_id:
                base_pos = positions.get(base_pos_id)
                if base_pos:
                    trading_engine.base_positions[instrument] = base_pos
                    logger.info(f"Restored base_position for {instrument}: {base_pos_id}")
                else:
                    logger.warning(
                        f"Base position {base_pos_id} not found in loaded positions "
                        f"for instrument {instrument}"
                    )

        # Update unrealized P&L using current market prices (if available)
        # This ensures P&L is accurate after recovery, not stale from database
        logger.info("Updating unrealized P&L for recovered positions...")

        for pos_id, position in positions.items():
            if position.status == "open":
                try:
                    # Fetch current market price from broker
                    if hasattr(trading_engine, 'openalgo_client') and trading_engine.openalgo_client:
                        quote = trading_engine.openalgo_client.get_quote(position.instrument)
                        current_price = quote.get('ltp', position.entry_price)

                        # Recalculate P&L with current market price
                        if position.instrument == "BANK_NIFTY":
                            point_value = 30.0  # Dec 2025 onwards
                        elif position.instrument == "COPPER":
                            point_value = 2500.0
                        elif position.instrument == "SILVER_MINI":
                            point_value = 5.0  # 5kg × Rs 1/kg
                        else:  # GOLD_MINI
                            point_value = 10.0
                        position.unrealized_pnl = position.calculate_pnl(current_price, point_value)
                        logger.info(f"Updated P&L for {pos_id}: ₹{position.unrealized_pnl:,.0f} (price: ₹{current_price:,.0f})")
                    else:
                        # No broker client available (testing/simulation mode)
                        # Preserve database P&L as fallback
                        logger.info(f"Preserved database P&L for {pos_id}: ₹{position.unrealized_pnl:,.0f} (simulation mode)")

                except Exception as e:
                    # If market price fetch fails, keep database P&L
                    logger.warning(f"Failed to fetch market price for {pos_id}, using database P&L: {e}")

        logger.info("LiveTradingEngine state reconstruction complete")

    def _validate_state_consistency(
        self,
        portfolio_manager: PortfolioStateManager,
        trading_engine: LiveTradingEngine,
        state_data: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate position integrity and refresh cached aggregates.

        Phase 1: Validate positions (source of truth)
        - Check lots > 0
        - Check entry_price > 0
        - Check valid instrument
        - Check initial_stop exists
        - Warn on orphaned pyramids

        Phase 2: Refresh cached state (fix any drift)
        - Recalculate from positions
        - Update portfolio_state in DB

        Args:
            portfolio_manager: Reconstructed PortfolioStateManager
            trading_engine: Reconstructed LiveTradingEngine
            state_data: Original state data from database

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        logger.info("Validating position integrity...")

        # positions is a dict: {position_id: Position}
        positions_dict = state_data['positions']
        positions = list(positions_dict.values())  # Get Position objects
        valid_instruments = {'GOLD_MINI', 'BANK_NIFTY', 'COPPER', 'SILVER_MINI'}

        # === PHASE 1: Validate Position Integrity ===
        position_ids = {pos.position_id for pos in positions}

        for pos in positions:
            # Check lots
            if pos.lots <= 0:
                return False, f"Invalid lots ({pos.lots}) for {pos.position_id}"

            # Check entry price
            if pos.entry_price <= 0:
                return False, f"Invalid entry_price for {pos.position_id}"

            # Check instrument
            if pos.instrument not in valid_instruments:
                return False, f"Unknown instrument: {pos.instrument}"

            # Check initial stop exists
            if pos.initial_stop is None:
                return False, f"Missing initial_stop for {pos.position_id}"

            # Check pyramid has valid base reference (warning only, not a hard fail)
            if not pos.is_base_position and hasattr(pos, 'base_position_id') and pos.base_position_id:
                if pos.base_position_id not in position_ids:
                    logger.warning(f"Orphaned pyramid {pos.position_id} → missing base {pos.base_position_id}")

        # === PHASE 2: Refresh Cached State ===
        old_state = state_data.get('portfolio_state', {})
        old_risk = float(old_state.get('total_risk_amount', 0) or 0)
        old_margin = float(old_state.get('margin_used', 0) or 0)

        current_state = portfolio_manager.get_current_state()

        if self.db_manager:
            self.db_manager.save_portfolio_state(current_state, portfolio_manager.initial_capital)
            logger.info(
                f"Cache refreshed: risk ₹{old_risk:,.2f} → ₹{current_state.total_risk_amount:,.2f}, "
                f"margin ₹{old_margin:,.2f} → ₹{current_state.margin_used:,.2f}"
            )

        logger.info(f"Position integrity validated ({len(positions)} positions), cache refreshed")
        return True, None
