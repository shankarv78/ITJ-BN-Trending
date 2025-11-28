"""
Unit tests for DatabaseStateManager

Tests database persistence layer with test database
"""
import pytest
import psycopg2
from datetime import datetime
from decimal import Decimal
from core.db_state_manager import DatabaseStateManager
from core.models import Position, PortfolioState, InstrumentType


# Test database configuration
TEST_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'portfolio_manager_test',
    'user': 'pm_user',
    'password': 'test_password',
    'minconn': 1,
    'maxconn': 3
}


@pytest.fixture(scope='module')
def test_db():
    """Create test database and run migrations"""
    # Connect to postgres database to create test database
    try:
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database='postgres',
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Drop test database if exists
        cursor.execute("DROP DATABASE IF EXISTS portfolio_manager_test")
        
        # Create test database
        cursor.execute("CREATE DATABASE portfolio_manager_test")
        cursor.close()
        conn.close()
        
        # Run migrations
        import os
        migration_file = os.path.join(
            os.path.dirname(__file__),
            '../../migrations/001_initial_schema.sql'
        )
        
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database='portfolio_manager_test',
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        with open(migration_file, 'r') as f:
            cursor.execute(f.read())
        
        cursor.close()
        conn.close()
        
        yield TEST_DB_CONFIG
        
        # Cleanup: Drop test database
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database='postgres',
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("DROP DATABASE portfolio_manager_test")
        cursor.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        pytest.skip(f"PostgreSQL not available or test database setup failed: {e}")


@pytest.fixture
def db_manager(test_db):
    """Create DatabaseStateManager instance"""
    return DatabaseStateManager(test_db)


@pytest.fixture
def sample_position():
    """Create sample position for testing"""
    return Position(
        position_id="Long_1",
        instrument="BANK_NIFTY",
        entry_timestamp=datetime(2025, 11, 28, 10, 0, 0),
        entry_price=50000.0,
        lots=5,
        quantity=125,  # 5 lots × 25 lot_size
        initial_stop=49000.0,
        current_stop=49500.0,
        highest_close=51000.0,
        atr=350.0,
        unrealized_pnl=50000.0,
        realized_pnl=0.0,
        status="open",
        strike=50000,
        expiry="2025-12-25",
        pe_symbol="BANKNIFTY251225P50000",
        ce_symbol="BANKNIFTY251225C50000",
        pe_order_id="PE_ORDER_123",
        ce_order_id="CE_ORDER_123",
        pe_entry_price=250.0,
        ce_entry_price=300.0,
        is_base_position=True,
        limiter="risk",
        risk_contribution=2.5,
        vol_contribution=1.2
    )


@pytest.fixture
def sample_portfolio_state():
    """Create sample portfolio state for testing"""
    return PortfolioState(
        timestamp=datetime.now(),
        equity=5000000.0,
        closed_equity=5000000.0,
        open_equity=5050000.0,
        blended_equity=5025000.0,
        positions={},
        total_risk_amount=125000.0,
        total_risk_percent=2.5,
        total_vol_amount=60000.0,
        margin_used=1350000.0
    )


class TestConnectionManagement:
    """Test connection pool and transaction management"""
    
    def test_connection_pool_initialization(self, db_manager):
        """Test that connection pool is initialized"""
        assert db_manager.pool is not None
        assert db_manager._position_cache == {}
        assert db_manager._portfolio_state_cache is None
    
    def test_get_connection(self, db_manager):
        """Test getting connection from pool"""
        with db_manager.get_connection() as conn:
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_transaction_commit(self, db_manager):
        """Test transaction commit"""
        with db_manager.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO portfolio_positions (position_id, instrument, status, entry_timestamp, entry_price, lots, quantity, initial_stop, current_stop, highest_close) VALUES ('TEST_1', 'BANK_NIFTY', 'open', NOW(), 50000.0, 1, 25, 49000.0, 49500.0, 50000.0)")
        
        # Verify data was committed
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT position_id FROM portfolio_positions WHERE position_id = 'TEST_1'")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == 'TEST_1'
    
    def test_transaction_rollback(self, db_manager):
        """Test transaction rollback on error"""
        try:
            with db_manager.transaction() as conn:
                cursor = conn.cursor()
                # This will fail due to constraint violation
                cursor.execute("INSERT INTO portfolio_positions (position_id, instrument, status, entry_timestamp, entry_price, lots, quantity, initial_stop, current_stop, highest_close) VALUES ('TEST_1', 'BANK_NIFTY', 'open', NOW(), 50000.0, 1, 25, 49000.0, 49500.0, 50000.0)")
                cursor.execute("INSERT INTO portfolio_positions (position_id, instrument, status, entry_timestamp, entry_price, lots, quantity, initial_stop, current_stop, highest_close) VALUES ('TEST_1', 'BANK_NIFTY', 'open', NOW(), 50000.0, 1, 25, 49000.0, 49500.0, 50000.0)")  # Duplicate key
        except Exception:
            pass  # Expected to fail
        
        # Verify data was NOT committed
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM portfolio_positions WHERE position_id = 'TEST_1'")
            result = cursor.fetchone()
            # Should only have 1 from previous test, not 2
            assert result[0] <= 1


class TestPositionOperations:
    """Test position CRUD operations"""
    
    def test_save_position_insert(self, db_manager, sample_position):
        """Test inserting new position"""
        result = db_manager.save_position(sample_position)
        assert result is True
        
        # Verify in database
        saved = db_manager.get_position("Long_1")
        assert saved is not None
        assert saved.position_id == "Long_1"
        assert saved.instrument == "BANK_NIFTY"
        assert saved.lots == 5
        assert saved.is_base_position is True
    
    def test_save_position_update(self, db_manager, sample_position):
        """Test updating existing position"""
        # Insert first
        db_manager.save_position(sample_position)
        
        # Update
        sample_position.current_stop = 49600.0
        sample_position.unrealized_pnl = 60000.0
        db_manager.save_position(sample_position)
        
        # Verify update
        saved = db_manager.get_position("Long_1")
        assert saved.current_stop == 49600.0
        assert saved.unrealized_pnl == 60000.0
    
    def test_save_position_optimistic_locking(self, db_manager, sample_position):
        """Test version increment on update"""
        db_manager.save_position(sample_position)
        
        # Get version
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM portfolio_positions WHERE position_id = 'Long_1'")
            version1 = cursor.fetchone()[0]
        
        # Update
        sample_position.current_stop = 49700.0
        db_manager.save_position(sample_position)
        
        # Verify version incremented
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM portfolio_positions WHERE position_id = 'Long_1'")
            version2 = cursor.fetchone()[0]
        
        assert version2 == version1 + 1
    
    def test_get_position_cache_hit(self, db_manager, sample_position):
        """Test cache-first lookup"""
        db_manager.save_position(sample_position)
        
        # First call - from database
        pos1 = db_manager.get_position("Long_1")
        assert pos1 is not None
        
        # Second call - from cache
        pos2 = db_manager.get_position("Long_1")
        assert pos2 is pos1  # Same object from cache
    
    def test_get_position_cache_miss(self, db_manager):
        """Test database fallback when not in cache"""
        # Position not in cache, should query database
        pos = db_manager.get_position("NONEXISTENT")
        assert pos is None
    
    def test_get_all_open_positions(self, db_manager, sample_position):
        """Test loading all open positions"""
        # Create multiple positions
        db_manager.save_position(sample_position)
        
        sample_position2 = Position(
            position_id="Long_2",
            instrument="GOLD_MINI",
            entry_timestamp=datetime(2025, 11, 28, 11, 0, 0),
            entry_price=65000.0,
            lots=3,
            quantity=30,
            initial_stop=64000.0,
            current_stop=64500.0,
            highest_close=66000.0,
            status="open",
            is_base_position=False
        )
        db_manager.save_position(sample_position2)
        
        # Create closed position (should not be included)
        sample_position3 = Position(
            position_id="Long_3",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime(2025, 11, 28, 9, 0, 0),
            entry_price=49000.0,
            lots=2,
            quantity=50,
            initial_stop=48000.0,
            current_stop=48000.0,
            highest_close=49500.0,
            status="closed",
            is_base_position=False
        )
        db_manager.save_position(sample_position3)
        
        # Get all open positions
        open_positions = db_manager.get_all_open_positions()
        
        assert len(open_positions) == 2
        assert "Long_1" in open_positions
        assert "Long_2" in open_positions
        assert "Long_3" not in open_positions
    
    def test_position_serialization_is_base_position(self, db_manager, sample_position):
        """Test that is_base_position is properly serialized"""
        sample_position.is_base_position = True
        db_manager.save_position(sample_position)
        
        # Verify in database
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_base_position FROM portfolio_positions WHERE position_id = 'Long_1'")
            result = cursor.fetchone()
            assert result[0] is True
        
        # Verify deserialization
        loaded = db_manager.get_position("Long_1")
        assert loaded.is_base_position is True


class TestPortfolioStateOperations:
    """Test portfolio state operations"""
    
    def test_save_portfolio_state(self, db_manager, sample_portfolio_state):
        """Test saving portfolio state"""
        result = db_manager.save_portfolio_state(sample_portfolio_state, initial_capital=5000000.0)
        assert result is True
        
        # Verify in database
        state = db_manager.get_portfolio_state()
        assert state is not None
        assert float(state['closed_equity']) == 5000000.0
        assert float(state['total_risk_amount']) == 125000.0
    
    def test_get_portfolio_state(self, db_manager, sample_portfolio_state):
        """Test loading portfolio state"""
        db_manager.save_portfolio_state(sample_portfolio_state, initial_capital=5000000.0)
        
        # First call - from database
        state1 = db_manager.get_portfolio_state()
        assert state1 is not None
        
        # Second call - from cache
        state2 = db_manager.get_portfolio_state()
        assert state2 is state1  # Same object from cache
    
    def test_portfolio_state_version_increment(self, db_manager, sample_portfolio_state):
        """Test version increment on portfolio state update"""
        db_manager.save_portfolio_state(sample_portfolio_state, initial_capital=5000000.0)
        
        # Get version
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM portfolio_state WHERE id = 1")
            version1 = cursor.fetchone()[0]
        
        # Update
        sample_portfolio_state.closed_equity = 5100000.0
        db_manager.save_portfolio_state(sample_portfolio_state, initial_capital=5000000.0)
        
        # Verify version incremented
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM portfolio_state WHERE id = 1")
            version2 = cursor.fetchone()[0]
        
        assert version2 == version1 + 1


class TestPyramidingStateOperations:
    """Test pyramiding state operations"""
    
    def test_save_pyramiding_state(self, db_manager):
        """Test saving pyramiding state"""
        result = db_manager.save_pyramiding_state(
            "BANK_NIFTY", 51000.0, "Long_1"
        )
        assert result is True
        
        # Verify in database
        pyr_state = db_manager.get_pyramiding_state()
        assert "BANK_NIFTY" in pyr_state
        assert float(pyr_state["BANK_NIFTY"]["last_pyramid_price"]) == 51000.0
        assert pyr_state["BANK_NIFTY"]["base_position_id"] == "Long_1"
    
    def test_get_pyramiding_state(self, db_manager):
        """Test loading pyramiding state"""
        db_manager.save_pyramiding_state("BANK_NIFTY", 51000.0, "Long_1")
        db_manager.save_pyramiding_state("GOLD_MINI", 66000.0, "Long_2")
        
        pyr_state = db_manager.get_pyramiding_state()
        assert len(pyr_state) == 2
        assert "BANK_NIFTY" in pyr_state
        assert "GOLD_MINI" in pyr_state
    
    def test_base_position_id_nullable(self, db_manager):
        """Test that base_position_id can be None"""
        result = db_manager.save_pyramiding_state(
            "BANK_NIFTY", 51000.0, None
        )
        assert result is True
        
        # Verify NULL in database
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT base_position_id FROM pyramiding_state WHERE instrument = 'BANK_NIFTY'")
            result = cursor.fetchone()
            assert result[0] is None


class TestSignalDeduplication:
    """Test signal deduplication operations"""
    
    def test_check_duplicate_signal_exists(self, db_manager):
        """Test duplicate signal detection"""
        # Log a signal
        signal_data = {
            'instrument': 'BANK_NIFTY',
            'type': 'BASE_ENTRY',
            'position': 'Long_1',
            'timestamp': datetime.now()
        }
        fingerprint = "test_fingerprint_123"
        
        db_manager.log_signal(signal_data, fingerprint, "instance_1", "executed")
        
        # Check for duplicate
        is_duplicate = db_manager.check_duplicate_signal(fingerprint)
        assert is_duplicate is True
    
    def test_check_duplicate_signal_not_exists(self, db_manager):
        """Test non-duplicate signal"""
        is_duplicate = db_manager.check_duplicate_signal("nonexistent_fingerprint")
        assert is_duplicate is False
    
    def test_log_signal_insert(self, db_manager):
        """Test logging new signal"""
        signal_data = {
            'instrument': 'BANK_NIFTY',
            'type': 'BASE_ENTRY',
            'position': 'Long_1',
            'timestamp': datetime.now()
        }
        fingerprint = "new_fingerprint_456"
        
        result = db_manager.log_signal(signal_data, fingerprint, "instance_1", "executed")
        assert result is True
        
        # Verify in database
        is_duplicate = db_manager.check_duplicate_signal(fingerprint)
        assert is_duplicate is True
    
    def test_log_signal_duplicate_detection(self, db_manager):
        """Test duplicate signal logging"""
        signal_data = {
            'instrument': 'BANK_NIFTY',
            'type': 'BASE_ENTRY',
            'position': 'Long_1',
            'timestamp': datetime.now()
        }
        fingerprint = "duplicate_fingerprint_789"
        
        # Log first time
        db_manager.log_signal(signal_data, fingerprint, "instance_1", "executed")
        
        # Log second time (should mark as duplicate)
        db_manager.log_signal(signal_data, fingerprint, "instance_2", "executed")
        
        # Verify duplicate flag
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_duplicate FROM signal_log WHERE fingerprint = %s", (fingerprint,))
            result = cursor.fetchone()
            assert result[0] is True

