#!/usr/bin/env python3
"""
Import portfolio data from position-calculator CSV export.

Cleans up test data and imports real equity/trade data.
"""

import sys
import json
import csv
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extras import RealDictCursor


def load_db_config(config_path: str = "db_config.json") -> dict:
    """Load database configuration."""
    with open(config_path) as f:
        config = json.load(f)
    return config.get("local", config)


def parse_csv(csv_path: str) -> tuple[dict, list[dict]]:
    """
    Parse the position-calculator CSV format.

    Returns:
        (portfolio_data, trades_list)
    """
    portfolio = {}
    trades = []

    with open(csv_path, 'r') as f:
        content = f.read()

    # Split by sections
    sections = content.split('\n\n')

    for section in sections:
        lines = section.strip().split('\n')
        if not lines:
            continue

        if lines[0] == '[PORTFOLIO]':
            # Parse portfolio section
            reader = csv.DictReader(lines[1:])
            for row in reader:
                portfolio[row['field']] = row['value']

        elif lines[0] == '[TRADES]':
            # Parse trades section
            reader = csv.DictReader(lines[1:])
            for row in reader:
                trades.append(row)

    return portfolio, trades


def clean_database(conn):
    """Remove all test data from database."""
    print("\n🧹 Cleaning database...")

    with conn.cursor() as cur:
        # Delete in order respecting foreign keys
        cur.execute("DELETE FROM signal_log")
        print(f"   - Deleted {cur.rowcount} signal_log entries")

        cur.execute("DELETE FROM pyramiding_state")
        print(f"   - Deleted {cur.rowcount} pyramiding_state entries")

        cur.execute("DELETE FROM portfolio_positions")
        print(f"   - Deleted {cur.rowcount} portfolio_positions entries")

        cur.execute("DELETE FROM instance_metadata")
        print(f"   - Deleted {cur.rowcount} instance_metadata entries")

        # Reset portfolio_state to defaults (will be updated with real values)
        cur.execute("""
            UPDATE portfolio_state
            SET initial_capital = 0,
                closed_equity = 0,
                total_risk_amount = 0,
                total_risk_percent = 0,
                total_vol_amount = 0,
                margin_used = 0,
                version = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """)

    conn.commit()
    print("   ✅ Database cleaned")


def import_portfolio(conn, portfolio: dict):
    """Import portfolio state."""
    print("\n📊 Importing portfolio state...")

    equity = float(portfolio.get('equity', 0))
    starting_equity = float(portfolio.get('startingEquity', equity))

    print(f"   - Starting Equity: ₹{starting_equity:,.2f}")
    print(f"   - Current Equity: ₹{equity:,.2f}")

    with conn.cursor() as cur:
        # Use INSERT ... ON CONFLICT to handle both insert and update cases
        cur.execute("""
            INSERT INTO portfolio_state (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent, total_vol_amount, margin_used, version, updated_at)
            VALUES (1, %s, %s, 0, 0, 0, 0, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE SET
                initial_capital = EXCLUDED.initial_capital,
                closed_equity = EXCLUDED.closed_equity,
                total_risk_amount = 0,
                total_risk_percent = 0,
                total_vol_amount = 0,
                margin_used = 0,
                version = 1,
                updated_at = CURRENT_TIMESTAMP
        """, (starting_equity, equity))

    conn.commit()
    print("   ✅ Portfolio state imported")


def import_trades(conn, trades: list[dict]):
    """Import historical trades as closed positions."""
    print(f"\n📈 Importing {len(trades)} trade(s)...")

    for trade in trades:
        trade_id = trade['id']
        instrument = trade['instrument']
        direction = trade['direction']
        entry_price = float(trade['entryPrice'])
        quantity = int(trade['quantity'])
        stop_loss = float(trade['stopLoss'])
        status = trade['status'].lower()
        notes = trade.get('notes', '')

        # Parse dates
        entry_date = datetime.fromisoformat(trade['entryDate'].replace('Z', '+00:00'))

        exit_date = None
        exit_price = None
        realized_pnl = 0.0

        if status == 'closed':
            exit_date = datetime.fromisoformat(trade['exitDate'].replace('Z', '+00:00')) if trade.get('exitDate') else None
            exit_price = float(trade['exitPrice']) if trade.get('exitPrice') else None
            realized_pnl = float(trade.get('pnl', 0))

        # The CSV stores lots in the "quantity" field
        # Get lot size based on instrument
        if instrument == 'GOLD_MINI':
            lot_size = 100
        elif instrument == 'SILVER_MINI':
            lot_size = 5
        elif instrument == 'COPPER':
            lot_size = 2500
        else:  # BANK_NIFTY and others
            lot_size = 30
        lots = quantity  # CSV quantity IS the number of lots
        actual_quantity = lots * lot_size

        print(f"   - {trade_id}: {direction} {instrument}")
        print(f"     Entry: ₹{entry_price:,.2f} x {lots} lots @ {entry_date.strftime('%Y-%m-%d %H:%M')}")
        if status == 'closed':
            print(f"     Exit: ₹{exit_price:,.2f} @ {exit_date.strftime('%Y-%m-%d %H:%M')}")
            print(f"     P&L: ₹{realized_pnl:,.2f}")

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO portfolio_positions (
                    position_id, instrument, status,
                    entry_timestamp, entry_price, lots, quantity,
                    initial_stop, current_stop, highest_close,
                    unrealized_pnl, realized_pnl,
                    is_base_position, version,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    realized_pnl = EXCLUDED.realized_pnl,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                trade_id, instrument, status,
                entry_date, entry_price, lots, actual_quantity,
                stop_loss, stop_loss, entry_price,
                0.0, realized_pnl,
                True, 1,
                entry_date
            ))

    conn.commit()
    print(f"   ✅ {len(trades)} trade(s) imported")


def main():
    if len(sys.argv) < 2:
        print("Usage: python import_from_csv.py <csv_path> [--db-config <config.json>]")
        print("\nExample:")
        print("  python import_from_csv.py ~/OneDrive/Performance/position-calculator.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    db_config_path = "db_config.json"

    # Parse optional --db-config argument
    if "--db-config" in sys.argv:
        idx = sys.argv.index("--db-config")
        db_config_path = sys.argv[idx + 1]

    print("=" * 60)
    print("  PORTFOLIO DATA IMPORT")
    print("=" * 60)
    print(f"\n📁 CSV Path: {csv_path}")
    print(f"📁 DB Config: {db_config_path}")

    # Parse CSV
    portfolio, trades = parse_csv(csv_path)

    print(f"\n📋 Found:")
    print(f"   - Portfolio equity: ₹{float(portfolio.get('equity', 0)):,.2f}")
    print(f"   - Trades: {len(trades)}")

    # Connect to database
    db_config = load_db_config(db_config_path)
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )

    try:
        # Clean database
        clean_database(conn)

        # Import portfolio state
        import_portfolio(conn, portfolio)

        # Import trades
        if trades:
            import_trades(conn, trades)

        print("\n" + "=" * 60)
        print("  ✅ IMPORT COMPLETE")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
