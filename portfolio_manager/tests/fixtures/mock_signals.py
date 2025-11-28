"""
Mock signal data for testing

Provides sample CSV data and signal sequences for testing
"""
import pandas as pd
from datetime import datetime, timedelta
from core.models import Signal, SignalType

def generate_mock_csv_data():
    """Generate mock TradingView CSV export data"""
    data = {
        'Trade #': [1, 1, 2, 2],
        'Type': ['Entry long', 'Exit long', 'Entry long', 'Exit long'],
        'Date/Time': [
            '2025-11-15 10:30',
            '2025-11-16 14:00',
            '2025-11-18 11:00',
            '2025-11-19 15:00'
        ],
        'Signal': [
            'ENTRY-5L|ATR:350|ER:0.82|STOP:51650|ST:51650|POS:Long_1',
            'EXIT|STOP:51800|HI:52500|POS:Long_1',
            'ENTRY-6L|ATR:370|ER:0.85|STOP:52100|ST:52100|POS:Long_1',
            'EXIT|STOP:52300|HI:53200|POS:Long_1'
        ],
        'Price INR': [52000.0, 52400.0, 52650.0, 52900.0],
        'Position size (qty)': [5, 5, 6, 6],
        'Net P&L INR': [70000.0, 70000.0, 37500.0, 37500.0],
        'Cumulative P&L INR': [70000.0, 70000.0, 107500.0, 107500.0]
    }
    
    return pd.DataFrame(data)

def generate_signal_sequence():
    """Generate sequence of signals for testing"""
    base_time = datetime(2025, 11, 15, 10, 30)
    
    signals = [
        # BASE ENTRY - Gold
        Signal(
            timestamp=base_time,
            instrument="GOLD_MINI",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=78500.0,
            stop=77800.0,
            suggested_lots=3,
            atr=700.0,
            er=0.85,
            supertrend=77800.0
        ),
        # BASE ENTRY - Bank Nifty
        Signal(
            timestamp=base_time + timedelta(hours=1),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51650.0,
            suggested_lots=5,
            atr=350.0,
            er=0.82,
            supertrend=51650.0
        ),
        # PYRAMID - Gold
        Signal(
            timestamp=base_time + timedelta(days=1),
            instrument="GOLD_MINI",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=79200.0,
            stop=78500.0,
            suggested_lots=2,
            atr=720.0,
            er=0.87,
            supertrend=78500.0
        ),
        # EXIT - Bank Nifty
        Signal(
            timestamp=base_time + timedelta(days=2),
            instrument="BANK_NIFTY",
            signal_type=SignalType.EXIT,
            position="Long_1",
            price=52400.0,
            stop=51800.0,
            suggested_lots=5,
            atr=360.0,
            er=0.83,
            supertrend=51800.0,
            reason="TOM_BASSO_STOP"
        )
    ]
    
    return signals

def create_sample_positions():
    """Create sample positions for testing"""
    return {
        "Gold_Long_1": Position(
            position_id="Gold_Long_1",
            instrument="GOLD_MINI",
            entry_timestamp=datetime(2025, 11, 15, 10, 30),
            entry_price=78500.0,
            lots=3,
            quantity=300,
            initial_stop=77800.0,
            current_stop=78000.0,
            highest_close=79200.0,
            unrealized_pnl=75000.0,
            status="open"
        ),
        "BN_Long_1": Position(
            position_id="BN_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime(2025, 11, 15, 11, 0),
            entry_price=52000.0,
            lots=5,
            quantity=175,
            initial_stop=51650.0,
            current_stop=51800.0,
            highest_close=52600.0,
            unrealized_pnl=105000.0,
            status="open"
        )
    }

