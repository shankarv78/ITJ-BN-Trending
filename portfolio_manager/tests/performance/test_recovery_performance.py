"""
Performance Test: Recovery with 10+ Positions

Task 1.8: Test recovery performance with larger position counts
- Tests recovery time with 10, 20, 30, 50 positions
- Verifies performance targets (< 2s for 10, < 3s for 20, < 5s for 50)
- Generates performance plot
"""
import os
import sys
import time
import psycopg2
from datetime import datetime
from typing import List, Tuple, Dict

# Optional matplotlib for plotting
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("⚠️  matplotlib not available - plotting will be skipped")

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.db_state_manager import DatabaseStateManager
from core.models import Signal, SignalType, Position
from live.engine import LiveTradingEngine
from live.recovery import CrashRecoveryManager
from core.config import PortfolioConfig


# Test database configuration
TEST_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'portfolio_manager',
    'user': 'pm_user',
    'password': 'test_password',
    'minconn': 1,
    'maxconn': 10
}


class MockOpenAlgoClient:
    """Mock OpenAlgo client for testing"""
    def get_funds(self):
        return {'availablecash': 5000000.0}

    def get_quote(self, symbol):
        # Return realistic prices
        if symbol == "BANK_NIFTY":
            return {'ltp': 50000, 'bid': 49990, 'ask': 50010}
        elif symbol == "GOLD_MINI":
            return {'ltp': 70000, 'bid': 69990, 'ask': 70010}
        return {'ltp': 50000, 'bid': 49990, 'ask': 50010}

    def place_order(self, symbol, action, quantity, order_type="MARKET", price=0.0):
        return {'status': 'success', 'orderid': f'MOCK_{symbol}_{action}'}

    def get_order_status(self, order_id):
        return {'status': 'COMPLETE', 'price': 50000}


def setup_test_database():
    """Setup test database and ensure tables exist"""
    try:
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database=TEST_DB_CONFIG['database'],
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Ensure tables exist
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
                    except (psycopg2.errors.DuplicateTable, psycopg2.errors.DuplicateObject, psycopg2.errors.ProgrammingError):
                        pass

        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False


def cleanup_test_data():
    """Clean up test data from database"""
    try:
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database=TEST_DB_CONFIG['database'],
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Cleanup test data - only delete PERF_TEST positions (safe)
        cursor.execute("DELETE FROM leadership_history")
        cursor.execute("DELETE FROM instance_metadata WHERE instance_id LIKE 'perf-test-%'")
        cursor.execute("DELETE FROM pyramiding_state WHERE base_position_id LIKE 'PERF_TEST_%'")
        cursor.execute("DELETE FROM portfolio_positions WHERE position_id LIKE 'PERF_TEST_%'")
        cursor.execute("DELETE FROM portfolio_state WHERE id = 1")
        # Note: signal_log table may not have signal_hash column, skip if it fails
        try:
            cursor.execute("DELETE FROM signal_log WHERE signal_hash LIKE 'perf-test-%'")
        except Exception:
            pass

        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
        return False


def check_for_non_test_positions() -> bool:
    """
    Check if there are non-test positions in the database.

    Returns:
        True if safe to proceed (no non-test positions), False otherwise
    """
    try:
        conn = psycopg2.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            database=TEST_DB_CONFIG['database'],
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password']
        )
        cursor = conn.cursor()

        # Check for open positions that are NOT test positions
        cursor.execute("""
            SELECT position_id, instrument, lots, status
            FROM portfolio_positions
            WHERE status = 'open'
            AND position_id NOT LIKE 'PERF_TEST_%'
        """)
        non_test_positions = cursor.fetchall()
        conn.close()

        if non_test_positions:
            print("\n" + "=" * 70)
            print("⚠️  WARNING: Non-test positions found in database!")
            print("=" * 70)
            print("\nThe following positions exist and would affect test results:\n")
            for pos in non_test_positions:
                print(f"  - {pos[0]}: {pos[1]} {pos[2]} lots (status: {pos[3]})")
            print("\nThese positions will cause recovery to load more data than expected,")
            print("resulting in validation failures.")
            print("\nOptions:")
            print("  1. Manually delete these positions if they are stale test data")
            print("  2. Use a separate test database")
            print("  3. Close these positions if they are from actual trading")
            print("\nTo delete stale positions, run:")
            print("  DELETE FROM portfolio_positions WHERE position_id IN (")
            for i, pos in enumerate(non_test_positions):
                comma = "," if i < len(non_test_positions) - 1 else ""
                print(f"    '{pos[0]}'{comma}")
            print("  );")
            print("\n" + "=" * 70)
            print("❌ ABORTING: Please resolve non-test positions before running test.")
            print("=" * 70 + "\n")
            return False

        return True

    except Exception as e:
        print(f"⚠️  Warning: Could not check for non-test positions: {e}")
        return True  # Proceed but warn


def create_test_positions(num_positions: int) -> List[str]:
    """
    Create test positions directly in database (bypassing signal processing)

    Args:
        num_positions: Number of positions to create

    Returns:
        List of position IDs created
    """
    print(f"\n📦 Creating {num_positions} test positions...")

    db_manager = DatabaseStateManager(TEST_DB_CONFIG)
    config = PortfolioConfig()

    # Create engine to calculate portfolio state
    engine = LiveTradingEngine(
        initial_capital=5000000.0,
        openalgo_client=MockOpenAlgoClient(),
        config=config,
        db_manager=db_manager
    )

    position_ids = []
    instruments = ["BANK_NIFTY", "GOLD_MINI"]
    lot_sizes = {"BANK_NIFTY": 30, "GOLD_MINI": 100}
    point_values = {"BANK_NIFTY": 30.0, "GOLD_MINI": 10.0}

    for i in range(num_positions):
        instrument = instruments[i % len(instruments)]
        position_layer = f"Long_{((i // len(instruments)) % 5) + 1}"  # Cycle through Long_1 to Long_5

        # Create unique position ID
        position_id = f"PERF_TEST_{instrument}_{position_layer}_{i}"

        # Create position directly
        base_price = 50000.0 if instrument == "BANK_NIFTY" else 70000.0
        entry_price = base_price + (i * 50)  # Vary prices slightly
        lots = 2 + (i % 3)  # Vary lots: 2, 3, or 4
        quantity = lots * lot_sizes[instrument]
        initial_stop = entry_price - 500.0

        position = Position(
            position_id=position_id,
            instrument=instrument,
            entry_timestamp=datetime.now(),
            entry_price=entry_price,
            lots=lots,
            quantity=quantity,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            highest_close=entry_price,
            atr=350.0 if instrument == "BANK_NIFTY" else 500.0,
            unrealized_pnl=0.0,  # Start with zero P&L
            realized_pnl=0.0,
            status="open",
            is_base_position=(position_layer == "Long_1"),
            limiter="risk",
            risk_contribution=0.5,  # 0.5% risk per position
            vol_contribution=0.2
        )

        # Save position directly to database
        db_manager.save_position(position)
        position_ids.append(position_id)

        # Add to portfolio for state calculation
        engine.portfolio.add_position(position)

    # Recalculate portfolio state after all positions are added
    # This ensures risk and margin calculations are accurate
    state = engine.portfolio.get_current_state()

    # Save complete portfolio state with calculated risk/margin values
    # This allows validation to pass by ensuring saved values match calculated values
    db_manager.save_portfolio_state(state, 5000000.0)

    # Verify the saved state matches calculated state
    saved_state = db_manager.get_portfolio_state()
    if saved_state:
        print(f"   - Saved risk: ₹{saved_state.get('total_risk_amount', 0):,.2f}")
        print(f"   - Calculated risk: ₹{state.total_risk_amount:,.2f}")
        print(f"   - Saved margin: ₹{saved_state.get('margin_used', 0):,.2f}")
        print(f"   - Calculated margin: ₹{state.margin_used:,.2f}")

    print(f"✅ Created {len(position_ids)} positions")
    return position_ids


def measure_recovery_time(num_positions: int) -> Tuple[float, bool, str]:
    """
    Measure recovery time for given number of positions

    Args:
        num_positions: Number of positions to recover

    Returns:
        Tuple of (duration_seconds, success, error_code)
    """
    print(f"\n⏱️  Measuring recovery time for {num_positions} positions...")

    db_manager = DatabaseStateManager(TEST_DB_CONFIG)
    config = PortfolioConfig()

    engine = LiveTradingEngine(
        initial_capital=5000000.0,
        openalgo_client=MockOpenAlgoClient(),
        config=config,
        db_manager=db_manager
    )

    recovery_manager = CrashRecoveryManager(db_manager)

    # Measure recovery time
    start_time = time.time()
    success, error_code = recovery_manager.load_state(
        portfolio_manager=engine.portfolio,
        trading_engine=engine
    )
    duration = time.time() - start_time

    if success:
        print(f"✅ Recovery completed in {duration:.3f} seconds")
        print(f"   - Recovered {len(engine.portfolio.positions)} positions")
    else:
        print(f"❌ Recovery failed: {error_code}")

    return duration, success, error_code


def run_performance_test(position_counts: List[int]) -> Dict[int, Tuple[float, bool]]:
    """
    Run performance test for multiple position counts

    Args:
        position_counts: List of position counts to test

    Returns:
        Dictionary mapping position_count -> (duration, success)
    """
    results = {}

    print("=" * 70)
    print("PERFORMANCE TEST: Recovery with Multiple Positions")
    print("=" * 70)

    # Setup database
    if not setup_test_database():
        print("❌ Failed to setup database. Exiting.")
        return results

    # Cleanup test data before starting
    cleanup_test_data()

    # Check for non-test positions that would interfere with the test
    if not check_for_non_test_positions():
        return results

    for num_positions in position_counts:
        print(f"\n{'=' * 70}")
        print(f"TEST: {num_positions} Positions")
        print(f"{'=' * 70}")

        # Create positions
        position_ids = create_test_positions(num_positions)

        if len(position_ids) < num_positions:
            print(f"⚠️  Warning: Only created {len(position_ids)} positions (expected {num_positions})")

        # Measure recovery time (run 3 times and average)
        durations = []
        successes = []

        for run in range(3):
            print(f"\n  Run {run + 1}/3:")
            duration, success, error_code = measure_recovery_time(num_positions)
            durations.append(duration)
            successes.append(success)

            # Small delay between runs
            time.sleep(0.5)

        # Calculate average
        avg_duration = sum(durations) / len(durations)
        all_success = all(successes)

        results[num_positions] = (avg_duration, all_success)

        print(f"\n📊 Results for {num_positions} positions:")
        print(f"   - Average recovery time: {avg_duration:.3f} seconds")
        print(f"   - All runs successful: {all_success}")
        print(f"   - Individual runs: {[f'{d:.3f}s' for d in durations]}")

        # Check performance target
        if num_positions == 10:
            target = 2.0
        elif num_positions == 20:
            target = 3.0
        elif num_positions == 50:
            target = 5.0
        else:
            target = None

        if target:
            if avg_duration <= target:
                print(f"   ✅ PASS: {avg_duration:.3f}s <= {target}s target")
            else:
                print(f"   ❌ FAIL: {avg_duration:.3f}s > {target}s target")

        # Cleanup for next test
        cleanup_test_data()
        time.sleep(1)

    return results


def plot_results(results: Dict[int, Tuple[float, bool]]):
    """
    Plot recovery time vs position count

    Args:
        results: Dictionary mapping position_count -> (duration, success)
    """
    if not results:
        print("❌ No results to plot")
        return

    if not HAS_MATPLOTLIB:
        print("⚠️  matplotlib not available - skipping plot generation")
        print("\n📊 Results Summary (text format):")
        position_counts = sorted(results.keys())
        for count in position_counts:
            duration, success = results[count]
            print(f"  {count} positions: {duration:.3f}s")
        return

    position_counts = sorted(results.keys())
    durations = [results[count][0] for count in position_counts]

    # Create plot
    plt.figure(figsize=(10, 6))
    plt.plot(position_counts, durations, 'b-o', linewidth=2, markersize=8, label='Recovery Time')

    # Add performance targets
    targets = {
        10: 2.0,
        20: 3.0,
        50: 5.0
    }

    for count, target in targets.items():
        if count in position_counts:
            plt.axhline(y=target, color='r', linestyle='--', alpha=0.5, label=f'Target ({count} pos): {target}s' if count == 10 else '')
            if count != 10:
                plt.text(count, target + 0.1, f'Target: {target}s', ha='center', va='bottom', fontsize=9, color='r')

    plt.xlabel('Number of Positions', fontsize=12)
    plt.ylabel('Recovery Time (seconds)', fontsize=12)
    plt.title('Recovery Performance: Time vs Position Count', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend()

    # Add annotations
    for count, duration in zip(position_counts, durations):
        plt.annotate(f'{duration:.2f}s', (count, duration),
                    textcoords="offset points", xytext=(0,10), ha='center', fontsize=9)

    # Save plot
    plot_path = os.path.join(os.path.dirname(__file__), 'recovery_performance_plot.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n📊 Performance plot saved to: {plot_path}")

    # Show plot
    try:
        plt.show()
    except:
        print("(Plot display not available, saved to file)")


def main():
    """Main test execution"""
    print("\n" + "=" * 70)
    print("PERFORMANCE TEST: Recovery with 10+ Positions")
    print("Task 1.8 - Automated Performance Testing")
    print("=" * 70)

    # Test position counts
    position_counts = [10, 20, 30, 50]

    # Run tests
    results = run_performance_test(position_counts)

    # Print summary
    print("\n" + "=" * 70)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 70)

    for count in sorted(results.keys()):
        duration, success = results[count]
        status = "✅ PASS" if success else "❌ FAIL"

        # Check target
        if count == 10:
            target = 2.0
            target_status = "✅" if duration <= target else "❌"
        elif count == 20:
            target = 3.0
            target_status = "✅" if duration <= target else "❌"
        elif count == 50:
            target = 5.0
            target_status = "✅" if duration <= target else "❌"
        else:
            target = None
            target_status = "N/A"

        print(f"\n{count} positions:")
        print(f"  - Recovery time: {duration:.3f} seconds")
        print(f"  - Success: {status}")
        if target:
            print(f"  - Target ({target}s): {target_status}")

    # Generate plot
    print("\n" + "=" * 70)
    print("GENERATING PERFORMANCE PLOT")
    print("=" * 70)
    plot_results(results)

    # Final cleanup
    cleanup_test_data()

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
