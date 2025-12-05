"""
Unit tests for CrashRecoveryManager

Tests crash recovery state loading from PostgreSQL
"""
import pytest
import psycopg2
import os
from datetime import datetime, timedelta
from decimal import Decimal
from live.recovery import CrashRecoveryManager, StateInconsistencyError
from core.db_state_manager import DatabaseStateManager
from core.models import Position, PortfolioState
from core.portfolio_state import PortfolioStateManager
from live.engine import LiveTradingEngine
from core.config import PortfolioConfig


# Test database configuration
TEST_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'portfolio_manager',
    'user': 'pm_user',
    'password': 'test_password',
    'minconn': 1,
    'maxconn': 3
}


@pytest.fixture(scope='function')
def test_db():
    """Setup test database and run migrations"""
    db_config = TEST_DB_CONFIG.copy()

    try:
        # Connect to database
        conn = psycopg2.connect(**{k: v for k, v in db_config.items() if k not in ['minconn', 'maxconn']})
        conn.autocommit = True
        cursor = conn.cursor()

        # Run migrations
        migration_dir = os.path.join(os.path.dirname(__file__), '../../migrations')
        migration_files = [
            '001_initial_schema.sql',
            '002_add_heartbeat_index.sql',
            '003_add_leadership_history.sql'
        ]

        for migration_file in migration_files:
            migration_path = os.path.join(migration_dir, migration_file)
            if os.path.exists(migration_path):
                with open(migration_path, 'r') as f:
                    sql = f.read()
                    try:
                        cursor.execute(sql)
                    except (psycopg2.errors.DuplicateTable, psycopg2.errors.DuplicateObject):
                        pass

        # Clean up test data
        cursor.execute("DELETE FROM leadership_history")
        cursor.execute("""
            DELETE FROM instance_metadata
            WHERE instance_id LIKE 'TEST_%'
               OR instance_id LIKE 'recovery_%'
        """)
        cursor.execute("""
            DELETE FROM portfolio_positions
            WHERE position_id LIKE 'TEST_%'
               OR position_id LIKE 'Long_%'
        """)
        cursor.execute("DELETE FROM portfolio_state")
        cursor.execute("DELETE FROM signal_log WHERE signal_hash LIKE 'TEST_%'")
        cursor.execute("""
            DELETE FROM pyramiding_state
            WHERE instrument LIKE 'TEST_%'
               OR instrument = 'BANK_NIFTY'
        """)

        cursor.close()
        conn.close()

        yield db_config

        # Cleanup after test
        try:
            conn = psycopg2.connect(**{k: v for k, v in db_config.items() if k not in ['minconn', 'maxconn']})
            conn.autocommit = True
            cursor = conn.cursor()

            cursor.execute("DELETE FROM leadership_history")
            cursor.execute("""
                DELETE FROM instance_metadata
                WHERE instance_id LIKE 'TEST_%'
                   OR instance_id LIKE 'recovery_%'
            """)
            cursor.execute("""
                DELETE FROM portfolio_positions
                WHERE position_id LIKE 'TEST_%'
                   OR position_id LIKE 'Long_%'
            """)
            cursor.execute("DELETE FROM portfolio_state")
            cursor.execute("DELETE FROM signal_log WHERE signal_hash LIKE 'TEST_%'")
            cursor.execute("""
                DELETE FROM pyramiding_state
                WHERE instrument LIKE 'TEST_%'
                   OR instrument = 'BANK_NIFTY'
            """)

            cursor.close()
            conn.close()
        except Exception:
            pass

    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.fixture
def db_manager(test_db):
    """Create DatabaseStateManager instance"""
    return DatabaseStateManager(test_db)


@pytest.fixture
def recovery_manager(db_manager):
    """Create CrashRecoveryManager instance"""
    return CrashRecoveryManager(db_manager)


@pytest.fixture
def mock_openalgo():
    """Mock OpenAlgo client"""
    class MockOpenAlgoClient:
        def get_funds(self):
            return {'availablecash': 5000000.0}

        def get_quote(self, symbol):
            return {'ltp': 50000, 'bid': 49990, 'ask': 50010}

    return MockOpenAlgoClient()


@pytest.fixture
def sample_position():
    """Create sample position for testing"""
    return Position(
        position_id="Long_1",
        instrument="BANK_NIFTY",
        entry_timestamp=datetime(2025, 11, 28, 10, 0, 0),
        entry_price=50000.0,
        lots=5,
        quantity=125,
        initial_stop=49000.0,
        current_stop=49500.0,
        highest_close=51000.0,
        atr=350.0,
        unrealized_pnl=50000.0,
        realized_pnl=0.0,
        status="open",
        is_base_position=True,
        risk_contribution=100000.0,
        margin_required=1350000.0
    )


class TestCrashRecoveryManagerInit:
    """Test CrashRecoveryManager initialization"""

    def test_init_with_defaults(self, db_manager):
        """Test initialization with default parameters"""
        recovery_manager = CrashRecoveryManager(db_manager)

        assert recovery_manager.db_manager == db_manager
        assert recovery_manager.max_retries == 3
        assert recovery_manager.retry_delays == [1, 2, 4]
        assert recovery_manager.consistency_epsilon == 0.01

    def test_error_codes_defined(self, recovery_manager):
        """Test that error codes are defined"""
        assert recovery_manager.DB_UNAVAILABLE == "DB_UNAVAILABLE"
        assert recovery_manager.DATA_CORRUPT == "DATA_CORRUPT"
        assert recovery_manager.VALIDATION_FAILED == "VALIDATION_FAILED"


class TestFetchStateData:
    """Test state data fetching with retry logic"""

    def test_fetch_state_data_success(self, recovery_manager, db_manager, sample_position):
        """Test successful state data fetch"""
        # Setup: Save position and state to database
        db_manager.save_position(sample_position)

        portfolio_state = PortfolioState(
            timestamp=datetime.now(),
            equity=5000000.0,
            closed_equity=5000000.0,
            open_equity=5050000.0,
            blended_equity=5025000.0,
            positions={'Long_1': sample_position},
            total_risk_amount=100000.0,
            total_risk_percent=2.0,
            total_vol_amount=50000.0,
            margin_used=1350000.0
        )
        db_manager.save_portfolio_state(portfolio_state, initial_capital=5000000.0)
        db_manager.save_pyramiding_state("BANK_NIFTY", 50000.0, "Long_1")

        # Fetch state
        state_data = recovery_manager._fetch_state_data()

        assert state_data is not None
        assert 'positions' in state_data
        assert 'portfolio_state' in state_data
        assert 'pyramiding_state' in state_data

        assert "Long_1" in state_data['positions']
        assert state_data['positions']['Long_1'].instrument == "BANK_NIFTY"

        assert float(state_data['portfolio_state']['closed_equity']) == 5000000.0
        assert "BANK_NIFTY" in state_data['pyramiding_state']

    def test_fetch_state_data_empty_database(self, recovery_manager):
        """Test fetch when database is empty"""
        state_data = recovery_manager._fetch_state_data()

        assert state_data is not None
        assert len(state_data['positions']) == 0
        assert state_data['portfolio_state'] == {} or state_data['portfolio_state'] is None
        assert len(state_data['pyramiding_state']) == 0

    def test_fetch_state_data_validates_position_type(self, recovery_manager, db_manager):
        """Test that invalid position types are detected"""
        # Manually insert invalid data
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # Insert position with invalid data that will cause deserialization to fail
            cursor.execute("""
                INSERT INTO portfolio_positions
                (position_id, instrument, status, entry_timestamp, entry_price,
                 lots, quantity, initial_stop, current_stop, highest_close)
                VALUES ('TEST_INVALID', 'BANK_NIFTY', 'open', NOW(), 50000.0,
                        NULL, 125, 49000.0, 49500.0, 50000.0)
            """)
            conn.commit()

        # Should raise StateInconsistencyError due to invalid data
        with pytest.raises(StateInconsistencyError):
            recovery_manager._fetch_state_data()

    def test_fetch_state_data_validates_closed_equity(self, recovery_manager, db_manager, sample_position):
        """Test that invalid closed_equity values are detected"""
        # Setup position
        db_manager.save_position(sample_position)

        # Manually insert invalid portfolio_state
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_state
                (id, timestamp, closed_equity, total_risk_amount, margin_used)
                VALUES (1, NOW(), 'invalid', 100000.0, 1350000.0)
                ON CONFLICT (id) DO UPDATE SET
                    closed_equity = 'invalid'
            """)
            conn.commit()

        # Should raise StateInconsistencyError
        with pytest.raises(StateInconsistencyError):
            recovery_manager._fetch_state_data()


class TestReconstructPortfolioState:
    """Test portfolio state reconstruction"""

    def test_reconstruct_portfolio_state_with_closed_equity(self, recovery_manager, test_db, sample_position):
        """Test portfolio state reconstruction with closed_equity"""
        config = PortfolioConfig()
        portfolio = PortfolioStateManager(5000000.0, config)

        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {
                'closed_equity': Decimal('5100000.00')
            },
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(portfolio, state_data)

        assert portfolio.closed_equity == 5100000.0
        assert "Long_1" in portfolio.positions

    def test_reconstruct_portfolio_state_without_closed_equity(self, recovery_manager, test_db, sample_position):
        """Test reconstruction when closed_equity is missing"""
        config = PortfolioConfig()
        initial_capital = 5000000.0
        portfolio = PortfolioStateManager(initial_capital, config)

        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {},  # No closed_equity
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(portfolio, state_data)

        # Should keep initial_capital as closed_equity
        assert portfolio.closed_equity == initial_capital
        assert "Long_1" in portfolio.positions


class TestReconstructTradingEngine:
    """Test trading engine reconstruction"""

    def test_reconstruct_trading_engine_with_pyramiding_state(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test engine reconstruction with pyramiding state"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {},
            'pyramiding_state': {
                'BANK_NIFTY': {
                    'last_pyramid_price': Decimal('51000.00'),
                    'base_position_id': 'Long_1'
                }
            }
        }

        # First reconstruct portfolio (engine needs positions in portfolio)
        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)

        # Then reconstruct engine
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        assert 'BANK_NIFTY' in engine.last_pyramid_price
        assert engine.last_pyramid_price['BANK_NIFTY'] == 51000.0
        assert 'BANK_NIFTY' in engine.base_positions
        assert engine.base_positions['BANK_NIFTY'] == sample_position

    def test_reconstruct_trading_engine_missing_base_position(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test reconstruction when base_position_id references non-existent position"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {},
            'pyramiding_state': {
                'BANK_NIFTY': {
                    'last_pyramid_price': Decimal('51000.00'),
                    'base_position_id': 'Long_99'  # Non-existent
                }
            }
        }

        # Reconstruct portfolio first
        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)

        # Should log warning but not crash
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        assert 'BANK_NIFTY' in engine.last_pyramid_price
        assert 'BANK_NIFTY' not in engine.base_positions  # Not set due to missing position

    def test_reconstruct_trading_engine_initializes_dicts(self, recovery_manager, test_db, mock_openalgo):
        """Test that engine reconstruction initializes dicts if missing"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        # Create engine without db_manager first to simulate missing attributes
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager=None)

        # Remove attributes to simulate missing state
        if hasattr(engine, 'last_pyramid_price'):
            delattr(engine, 'last_pyramid_price')
        if hasattr(engine, 'base_positions'):
            delattr(engine, 'base_positions')

        state_data = {
            'positions': {},
            'portfolio_state': {},
            'pyramiding_state': {}
        }

        # Should not crash and should initialize dicts
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        assert hasattr(engine, 'last_pyramid_price')
        assert hasattr(engine, 'base_positions')
        assert isinstance(engine.last_pyramid_price, dict)
        assert isinstance(engine.base_positions, dict)


class TestValidateStateConsistency:
    """Test state consistency validation"""

    def test_validate_consistency_success(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test successful consistency validation"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Setup state with consistent values
        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {
                'total_risk_amount': Decimal('100000.00'),
                'margin_used': Decimal('1350000.00')
            },
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        # Validate
        is_valid, error = recovery_manager._validate_state_consistency(
            engine.portfolio,
            engine,
            state_data
        )

        assert is_valid is True
        assert error is None

    def test_validate_consistency_risk_mismatch(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test validation fails when risk amounts don't match"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Setup state with INCONSISTENT risk
        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {
                'total_risk_amount': Decimal('200000.00'),  # Wrong - position has 100000
                'margin_used': Decimal('1350000.00')
            },
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        # Validate - should fail
        is_valid, error = recovery_manager._validate_state_consistency(
            engine.portfolio,
            engine,
            state_data
        )

        assert is_valid is False
        assert "Risk amount mismatch" in error

    def test_validate_consistency_margin_mismatch(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test validation fails when margin amounts don't match"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Setup state with INCONSISTENT margin
        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {
                'total_risk_amount': Decimal('100000.00'),
                'margin_used': Decimal('2000000.00')  # Wrong - position has 1350000
            },
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        # Validate - should fail
        is_valid, error = recovery_manager._validate_state_consistency(
            engine.portfolio,
            engine,
            state_data
        )

        assert is_valid is False
        assert "Margin amount mismatch" in error

    def test_validate_consistency_with_epsilon_tolerance(self, recovery_manager, test_db, mock_openalgo, sample_position):
        """Test that validation allows small differences within epsilon"""
        config = PortfolioConfig()
        db_manager = recovery_manager.db_manager
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Setup state with difference WITHIN epsilon (0.01 rupees)
        state_data = {
            'positions': {'Long_1': sample_position},
            'portfolio_state': {
                'total_risk_amount': Decimal('100000.005'),  # 0.005 difference
                'margin_used': Decimal('1350000.008')        # 0.008 difference
            },
            'pyramiding_state': {}
        }

        recovery_manager._reconstruct_portfolio_state(engine.portfolio, state_data)
        recovery_manager._reconstruct_trading_engine(engine, state_data)

        # Validate - should pass
        is_valid, error = recovery_manager._validate_state_consistency(
            engine.portfolio,
            engine,
            state_data
        )

        assert is_valid is True
        assert error is None


class TestLoadStateEndToEnd:
    """Test full load_state flow"""

    def test_load_state_success(self, recovery_manager, db_manager, test_db, mock_openalgo, sample_position):
        """Test successful end-to-end state loading"""
        # Setup: Save complete state to database
        db_manager.save_position(sample_position)

        portfolio_state = PortfolioState(
            timestamp=datetime.now(),
            equity=5000000.0,
            closed_equity=5100000.0,
            open_equity=5150000.0,
            blended_equity=5125000.0,
            positions={'Long_1': sample_position},
            total_risk_amount=100000.0,
            total_risk_percent=2.0,
            total_vol_amount=50000.0,
            margin_used=1350000.0
        )
        db_manager.save_portfolio_state(portfolio_state, initial_capital=5000000.0)
        db_manager.save_pyramiding_state("BANK_NIFTY", 50000.0, "Long_1")

        # Create fresh instances
        config = PortfolioConfig()
        portfolio = PortfolioStateManager(5000000.0, config, db_manager)
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Load state
        success, error_code = recovery_manager.load_state(portfolio, engine)

        assert success is True
        assert error_code is None

        # Verify portfolio state
        assert portfolio.closed_equity == 5100000.0
        assert "Long_1" in portfolio.positions

        # Verify engine state
        assert "BANK_NIFTY" in engine.last_pyramid_price
        assert engine.last_pyramid_price["BANK_NIFTY"] == 50000.0
        assert "BANK_NIFTY" in engine.base_positions

    def test_load_state_db_unavailable(self, recovery_manager, test_db, mock_openalgo):
        """Test load_state when database is unavailable"""
        # Close database connection to simulate unavailability
        recovery_manager.db_manager.pool.closeall()

        config = PortfolioConfig()
        portfolio = PortfolioStateManager(5000000.0, config)
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config)

        # Should fail with DB_UNAVAILABLE
        success, error_code = recovery_manager.load_state(portfolio, engine)

        assert success is False
        assert error_code == recovery_manager.DB_UNAVAILABLE

    def test_load_state_validation_failure(self, recovery_manager, db_manager, test_db, mock_openalgo, sample_position):
        """Test load_state when validation fails"""
        # Setup with INCONSISTENT data
        db_manager.save_position(sample_position)

        portfolio_state = PortfolioState(
            timestamp=datetime.now(),
            equity=5000000.0,
            closed_equity=5100000.0,
            open_equity=5150000.0,
            blended_equity=5125000.0,
            positions={'Long_1': sample_position},
            total_risk_amount=999999.0,  # WRONG - doesn't match position
            total_risk_percent=2.0,
            total_vol_amount=50000.0,
            margin_used=1350000.0
        )
        db_manager.save_portfolio_state(portfolio_state, initial_capital=5000000.0)

        config = PortfolioConfig()
        portfolio = PortfolioStateManager(5000000.0, config, db_manager)
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Should fail with VALIDATION_FAILED
        success, error_code = recovery_manager.load_state(portfolio, engine)

        assert success is False
        assert error_code == recovery_manager.VALIDATION_FAILED

    def test_load_state_with_coordinator_sets_status(self, recovery_manager, db_manager, test_db, mock_openalgo, sample_position):
        """Test that load_state sets instance status in HA system"""
        # Setup valid state
        db_manager.save_position(sample_position)

        portfolio_state = PortfolioState(
            timestamp=datetime.now(),
            equity=5000000.0,
            closed_equity=5100000.0,
            open_equity=5150000.0,
            blended_equity=5125000.0,
            positions={'Long_1': sample_position},
            total_risk_amount=100000.0,
            total_risk_percent=2.0,
            total_vol_amount=50000.0,
            margin_used=1350000.0
        )
        db_manager.save_portfolio_state(portfolio_state, initial_capital=5000000.0)

        # Create mock coordinator
        class MockCoordinator:
            def __init__(self):
                self.instance_id = 'recovery_test_instance'
                self.db_manager = db_manager

            def _get_hostname_safe(self):
                return 'test-host'

        coordinator = MockCoordinator()

        config = PortfolioConfig()
        portfolio = PortfolioStateManager(5000000.0, config, db_manager)
        engine = LiveTradingEngine(5000000.0, mock_openalgo, config, db_manager)

        # Load state with coordinator
        success, error_code = recovery_manager.load_state(portfolio, engine, coordinator)

        assert success is True

        # Verify instance status was set to 'active'
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM instance_metadata WHERE instance_id = %s",
                (coordinator.instance_id,)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 'active'


class TestRetryLogic:
    """Test retry logic and error handling"""

    def test_retry_on_transient_error(self, recovery_manager, db_manager, monkeypatch):
        """Test that transient errors trigger retry with exponential backoff"""
        call_count = [0]

        def mock_get_all_open_positions():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Transient database error")
            return {}

        monkeypatch.setattr(db_manager, 'get_all_open_positions', mock_get_all_open_positions)

        # Should retry and eventually succeed
        state_data = recovery_manager._fetch_state_data()

        assert state_data is not None
        assert call_count[0] == 3  # Failed twice, succeeded on 3rd attempt

    def test_no_retry_on_data_corruption(self, recovery_manager, db_manager, monkeypatch):
        """Test that data corruption errors don't trigger retry"""
        call_count = [0]

        def mock_get_all_open_positions():
            call_count[0] += 1
            # Return invalid data that will fail validation
            return {"invalid": "not a Position object"}

        monkeypatch.setattr(db_manager, 'get_all_open_positions', mock_get_all_open_positions)

        # Should raise immediately without retry
        with pytest.raises(StateInconsistencyError):
            recovery_manager._fetch_state_data()

        assert call_count[0] == 1  # Only called once, no retry
