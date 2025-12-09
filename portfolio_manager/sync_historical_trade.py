#!/usr/bin/env python3
"""
Sync historical trades into Portfolio Manager database

This script imports closed trades that were executed outside of PM
(e.g., manual trades, trades from position calculator)

Usage:
  python sync_historical_trade.py --show       # Show what would be synced
  python sync_historical_trade.py --execute    # Actually sync to database
"""

import os
import sys
import csv
import argparse
from datetime import datetime
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection settings (same as PM)
DB_CONFIG = {
    'host': os.environ.get('PM_DB_HOST', 'localhost'),
    'port': int(os.environ.get('PM_DB_PORT', 5432)),
    'dbname': os.environ.get('PM_DB_NAME', 'portfolio_manager'),
    'user': os.environ.get('PM_DB_USER', 'pm_user'),
    'password': os.environ.get('PM_DB_PASSWORD', 'pm_password')
}

# Trade data from position-calculator.csv (Dec 5, 2025)
HISTORICAL_TRADE = {
    'position_id': 'manual_gold_20251205_1540',
    'instrument': 'GOLD_MINI',
    'status': 'closed',
    'entry_timestamp': '2025-12-05 15:40:00',
    'entry_price': 130051.67,
    'lots': 3,
    'quantity': 300,  # 3 lots × 100 grams/lot
    'initial_stop': 128511.24,
    'current_stop': 128511.24,
    'highest_close': 130051.67,  # Never went higher
    'unrealized_pnl': 0.0,  # Closed
    'realized_pnl': -27200.10,
    'atr': 1540.43,  # Calculated: (130051.67 - 128511.24) / 1.0 ATR mult
    'is_base_position': True,
    'exit_timestamp': '2025-12-05 16:30:00',
    'exit_price': 129145.00,
    'exit_reason': 'STOP_LOSS',
    'futures_symbol': 'GOLDM25FEBFUT',  # Feb 2025 contract
    'contract_month': '2025-02'
}

# Updated portfolio state
PORTFOLIO_STATE = {
    'equity': 5084296.0,
    'closed_equity': 5084296.0,  # Starting 5,111,496 - 27,200 loss
    'starting_equity': 5111496.0  # Before this trade
}


def get_db_connection():
    """Get database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Config: {DB_CONFIG}")
        return None


def show_current_state(conn):
    """Display current database state"""
    print("\n📊 Current Database State:")
    print("=" * 60)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Portfolio state
        cur.execute("SELECT * FROM portfolio_state WHERE id = 1")
        state = cur.fetchone()
        if state:
            print(f"\n💰 Portfolio State:")
            print(f"   Initial Capital: ₹{state['initial_capital']:,.2f}")
            print(f"   Closed Equity:   ₹{state['closed_equity']:,.2f}")
            print(f"   Risk Amount:     ₹{state['total_risk_amount']:,.2f}")
            print(f"   Risk Percent:    {state['total_risk_percent']:.2f}%")
        else:
            print("   ❌ No portfolio state found")

        # Positions
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) as open, SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as closed FROM portfolio_positions")
        counts = cur.fetchone()
        print(f"\n📈 Positions:")
        print(f"   Total:  {counts['total'] or 0}")
        print(f"   Open:   {counts['open'] or 0}")
        print(f"   Closed: {counts['closed'] or 0}")

        # Recent trades
        cur.execute("""
            SELECT position_id, instrument, status, entry_timestamp, entry_price, lots, realized_pnl
            FROM portfolio_positions
            ORDER BY entry_timestamp DESC
            LIMIT 5
        """)
        recent = cur.fetchall()
        if recent:
            print(f"\n📜 Recent Positions:")
            for pos in recent:
                pnl_str = f"₹{pos['realized_pnl']:,.2f}" if pos['realized_pnl'] else "N/A"
                print(f"   {pos['position_id'][:30]:30} | {pos['instrument']:12} | {pos['status']:8} | P&L: {pnl_str}")


def show_pending_sync():
    """Show what would be synced"""
    print("\n📋 Pending Sync - Trade Data:")
    print("=" * 60)

    t = HISTORICAL_TRADE
    print(f"""
Trade Details:
  Position ID:    {t['position_id']}
  Instrument:     {t['instrument']}
  Status:         {t['status']}

  Entry:
    Timestamp:    {t['entry_timestamp']}
    Price:        ₹{t['entry_price']:,.2f}
    Lots:         {t['lots']}
    Quantity:     {t['quantity']} grams

  Stop Loss:
    Initial:      ₹{t['initial_stop']:,.2f}
    ATR:          ₹{t['atr']:,.2f}

  Exit:
    Timestamp:    {t['exit_timestamp']}
    Price:        ₹{t['exit_price']:,.2f}
    Reason:       {t['exit_reason']}

  P&L:            ₹{t['realized_pnl']:,.2f}
""")

    print("\n📋 Portfolio State Update:")
    print("=" * 60)
    p = PORTFOLIO_STATE
    print(f"""
  Starting Equity: ₹{p['starting_equity']:,.2f}
  Trade P&L:       ₹{HISTORICAL_TRADE['realized_pnl']:,.2f}
  New Equity:      ₹{p['equity']:,.2f}
""")


def execute_sync(conn):
    """Execute the sync to database"""
    print("\n🔄 Executing Sync...")
    print("=" * 60)

    try:
        with conn.cursor() as cur:
            # Check if trade already exists
            cur.execute(
                "SELECT position_id FROM portfolio_positions WHERE position_id = %s",
                (HISTORICAL_TRADE['position_id'],)
            )
            if cur.fetchone():
                print(f"⚠️  Trade {HISTORICAL_TRADE['position_id']} already exists, skipping insert")
            else:
                # Insert the closed trade with exit data
                cur.execute("""
                    INSERT INTO portfolio_positions (
                        position_id, instrument, status,
                        entry_timestamp, entry_price, lots, quantity,
                        initial_stop, current_stop, highest_close,
                        unrealized_pnl, realized_pnl,
                        atr, is_base_position,
                        futures_symbol, contract_month,
                        exit_timestamp, exit_price, exit_reason,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        NOW(), NOW()
                    )
                """, (
                    HISTORICAL_TRADE['position_id'],
                    HISTORICAL_TRADE['instrument'],
                    HISTORICAL_TRADE['status'],
                    HISTORICAL_TRADE['entry_timestamp'],
                    HISTORICAL_TRADE['entry_price'],
                    HISTORICAL_TRADE['lots'],
                    HISTORICAL_TRADE['quantity'],
                    HISTORICAL_TRADE['initial_stop'],
                    HISTORICAL_TRADE['current_stop'],
                    HISTORICAL_TRADE['highest_close'],
                    HISTORICAL_TRADE['unrealized_pnl'],
                    HISTORICAL_TRADE['realized_pnl'],
                    HISTORICAL_TRADE['atr'],
                    HISTORICAL_TRADE['is_base_position'],
                    HISTORICAL_TRADE['futures_symbol'],
                    HISTORICAL_TRADE['contract_month'],
                    HISTORICAL_TRADE['exit_timestamp'],
                    HISTORICAL_TRADE['exit_price'],
                    HISTORICAL_TRADE['exit_reason']
                ))
                print(f"✅ Inserted trade: {HISTORICAL_TRADE['position_id']}")

            # Update or insert portfolio state
            cur.execute("SELECT id FROM portfolio_state WHERE id = 1")
            if cur.fetchone():
                # Update existing
                cur.execute("""
                    UPDATE portfolio_state
                    SET closed_equity = %s,
                        updated_at = NOW(),
                        version = version + 1
                    WHERE id = 1
                """, (PORTFOLIO_STATE['closed_equity'],))
                print(f"✅ Updated portfolio equity to ₹{PORTFOLIO_STATE['equity']:,.2f}")
            else:
                # Insert new
                cur.execute("""
                    INSERT INTO portfolio_state (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent, total_vol_amount, margin_used)
                    VALUES (1, %s, %s, 0.0, 0.0, 0.0, 0.0)
                """, (PORTFOLIO_STATE['starting_equity'], PORTFOLIO_STATE['closed_equity']))
                print(f"✅ Created portfolio state with equity ₹{PORTFOLIO_STATE['equity']:,.2f}")

            conn.commit()
            print("\n✅ Sync completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Sync failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description='Sync historical trades to PM database')
    parser.add_argument('--show', action='store_true', help='Show what would be synced')
    parser.add_argument('--execute', action='store_true', help='Execute the sync')
    args = parser.parse_args()

    if not args.show and not args.execute:
        args.show = True

    print("=" * 60)
    print("📥 Historical Trade Sync Tool")
    print("=" * 60)

    # Connect to database
    conn = get_db_connection()
    if not conn:
        sys.exit(1)

    try:
        # Show current state
        show_current_state(conn)

        # Show pending sync
        show_pending_sync()

        if args.execute:
            # Confirm
            print("\n⚠️  This will modify the database!")
            response = input("Continue? [y/N]: ").strip().lower()
            if response == 'y':
                execute_sync(conn)
                # Show updated state
                print("\n📊 Updated Database State:")
                show_current_state(conn)
            else:
                print("Cancelled.")
        else:
            print("\n💡 Run with --execute to apply these changes")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
