"""
Integration tests for database persistence

Tests full signal → database → recovery flow
"""
import pytest
import psycopg2
import os
from datetime import datetime
from core.db_state_manager import DatabaseStateManager
from core.models import Signal, SignalType, Position
from live.engine import LiveTradingEngine
from core.config import PortfolioConfig


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
    try:
        # Connect to postgres database to create test database
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
def mock_openalgo():
    """Mock OpenAlgo client"""
    class MockOpenAlgoClient:
        def get_funds(self):
            return {'availablecash': 5000000.0}
        
        def get_quote(self, symbol):
            return {'ltp': 50000, 'bid': 49990, 'ask': 50010}
        
        def place_order(self, symbol, action, quantity, order_type="MARKET", price=0.0):
            return {'status': 'success', 'orderid': f'MOCK_{symbol}_{action}'}
        
        def get_order_status(self, order_id):
            return {'status': 'COMPLETE', 'price': 50000}
    
    return MockOpenAlgoClient()


@pytest.fixture
def engine(test_db, mock_openalgo):
    """Create LiveTradingEngine with database manager"""
    db_manager = DatabaseStateManager(test_db)
    config = PortfolioConfig()
    
    return LiveTradingEngine(
        initial_capital=5000000.0,
        openalgo_client=mock_openalgo,
        config=config,
        db_manager=db_manager
    )


class TestSignalToDatabaseFlow:
    """Test signal processing → database persistence"""
    
    def test_base_entry_signal_persisted(self, engine, db_manager):
        """Test that BASE_ENTRY signal creates position in database"""
        signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49000.0,
            suggested_lots=5,
            atr=350.0,
            er=0.85,
            supertrend=49500.0
        )
        
        # Process signal
        result = engine.process_signal(signal)
        assert result['status'] == 'executed'
        
        # Verify position in database
        position = db_manager.get_position("BANK_NIFTY_Long_1")
        assert position is not None
        assert position.instrument == "BANK_NIFTY"
        assert position.lots == 5
        assert position.is_base_position is True
        
        # Verify pyramiding state
        pyr_state = db_manager.get_pyramiding_state()
        assert "BANK_NIFTY" in pyr_state
        assert pyr_state["BANK_NIFTY"]["base_position_id"] == "BANK_NIFTY_Long_1"
    
    def test_pyramid_signal_persisted(self, engine, db_manager):
        """Test that PYRAMID signal creates position in database"""
        # First create base entry
        base_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49000.0,
            suggested_lots=5,
            atr=350.0,
            er=0.85,
            supertrend=49500.0
        )
        engine.process_signal(base_signal)
        
        # Now process pyramid
        pyramid_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=51000.0,
            stop=50000.0,
            suggested_lots=3,
            atr=350.0,
            er=0.90,
            supertrend=50500.0
        )
        
        result = engine.process_signal(pyramid_signal)
        assert result['status'] == 'executed'
        
        # Verify pyramid position in database
        position = db_manager.get_position("BANK_NIFTY_Long_2")
        assert position is not None
        assert position.is_base_position is False
        
        # Verify pyramiding state updated
        pyr_state = db_manager.get_pyramiding_state()
        assert float(pyr_state["BANK_NIFTY"]["last_pyramid_price"]) == 51000.0
    
    def test_exit_signal_persisted(self, engine, db_manager):
        """Test that EXIT signal closes position in database"""
        # Create base entry
        base_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49000.0,
            suggested_lots=5,
            atr=350.0,
            er=0.85,
            supertrend=49500.0
        )
        engine.process_signal(base_signal)
        
        # Process exit
        exit_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.EXIT,
            position="Long_1",
            price=52000.0,
            stop=0.0,  # Not used for exit
            suggested_lots=0,
            atr=350.0,
            er=0.90,
            supertrend=51500.0,
            reason="stop_hit"
        )
        
        result = engine.process_signal(exit_signal)
        assert result['status'] == 'executed'
        
        # Verify position closed in database
        position = db_manager.get_position("BANK_NIFTY_Long_1")
        assert position.status == "closed"
        
        # Verify portfolio state updated
        portfolio_state = db_manager.get_portfolio_state()
        assert portfolio_state is not None
        # Closed equity should be updated (initial + P&L)


class TestRecoveryFlow:
    """Test state recovery on engine restart"""
    
    def test_recovery_loads_positions(self, test_db, mock_openalgo):
        """Test that engine recovers positions from database on startup"""
        # Create first engine and process signal
        db_manager1 = DatabaseStateManager(test_db)
        config = PortfolioConfig()
        
        engine1 = LiveTradingEngine(
            initial_capital=5000000.0,
            openalgo_client=mock_openalgo,
            config=config,
            db_manager=db_manager1
        )
        
        signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49000.0,
            suggested_lots=5,
            atr=350.0,
            er=0.85,
            supertrend=49500.0
        )
        
        engine1.process_signal(signal)
        
        # Simulate crash - create new engine
        db_manager2 = DatabaseStateManager(test_db)
        engine2 = LiveTradingEngine(
            initial_capital=5000000.0,
            openalgo_client=mock_openalgo,
            config=config,
            db_manager=db_manager2
        )
        
        # Verify position recovered
        assert "BANK_NIFTY_Long_1" in engine2.portfolio.positions
        recovered_pos = engine2.portfolio.positions["BANK_NIFTY_Long_1"]
        assert recovered_pos.lots == 5
        assert recovered_pos.entry_price == 50000.0
        assert recovered_pos.is_base_position is True
        
        # Verify pyramiding state recovered
        assert "BANK_NIFTY" in engine2.base_positions
        assert engine2.last_pyramid_price["BANK_NIFTY"] == 50000.0
    
    def test_recovery_allows_continued_trading(self, test_db, mock_openalgo):
        """Test that recovered engine can process new signals"""
        # Create engine, process signal, simulate crash
        db_manager1 = DatabaseStateManager(test_db)
        config = PortfolioConfig()
        
        engine1 = LiveTradingEngine(
            initial_capital=5000000.0,
            openalgo_client=mock_openalgo,
            config=config,
            db_manager=db_manager1
        )
        
        base_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49000.0,
            suggested_lots=5,
            atr=350.0,
            er=0.85,
            supertrend=49500.0
        )
        engine1.process_signal(base_signal)
        
        # Recover engine
        db_manager2 = DatabaseStateManager(test_db)
        engine2 = LiveTradingEngine(
            initial_capital=5000000.0,
            openalgo_client=mock_openalgo,
            config=config,
            db_manager=db_manager2
        )
        
        # Process new signal with recovered engine
        pyramid_signal = Signal(
            timestamp=datetime.now(),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=51000.0,
            stop=50000.0,
            suggested_lots=3,
            atr=350.0,
            er=0.90,
            supertrend=50500.0
        )
        
        result = engine2.process_signal(pyramid_signal)
        assert result['status'] == 'executed'
        
        # Verify both positions exist
        assert "BANK_NIFTY_Long_1" in engine2.portfolio.positions
        assert "BANK_NIFTY_Long_2" in engine2.portfolio.positions


class TestConcurrentUpdates:
    """Test concurrent position updates with optimistic locking"""
    
    def test_concurrent_stop_updates(self, db_manager):
        """Test that concurrent stop updates work with optimistic locking"""
        # Create position
        position = Position(
            position_id="Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=50000.0,
            lots=5,
            quantity=125,
            initial_stop=49000.0,
            current_stop=49500.0,
            highest_close=50000.0,
            status="open",
            is_base_position=True
        )
        db_manager.save_position(position)
        
        # Simulate concurrent updates
        import threading
        
        def update_stop(stop_price):
            pos = db_manager.get_position("Long_1")
            pos.current_stop = stop_price
            db_manager.save_position(pos)
        
        # Update from two threads
        thread1 = threading.Thread(target=update_stop, args=(49600.0,))
        thread2 = threading.Thread(target=update_stop, args=(49700.0,))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Verify final state (one of the updates should succeed)
        final_pos = db_manager.get_position("Long_1")
        assert final_pos.current_stop in [49600.0, 49700.0]
        
        # Verify version incremented
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM portfolio_positions WHERE position_id = 'Long_1'")
            version = cursor.fetchone()[0]
            assert version >= 2  # At least 2 updates

