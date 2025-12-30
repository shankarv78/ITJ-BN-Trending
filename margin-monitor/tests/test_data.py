"""
Test Data - Verified values from live trading session (Dec 30, 2025)
"""

# Baseline (Dec 2026 positions only)
BASELINE = 592178.63

# Verified snapshots timeline
SNAPSHOTS = [
    {"time": "09:15:30", "utiliseddebits": 592178.63, "event": "baseline"},
    {"time": "09:16:00", "utiliseddebits": 5049451.12, "event": "EXP 1 entered"},
    {"time": "09:24:00", "utiliseddebits": 10033810.88, "event": "EXP 2 entered"},
    {"time": "09:29:00", "utiliseddebits": 15022200.38, "event": "EXP 3 entered"},
    {"time": "09:45:00", "utiliseddebits": 12512414.25, "event": "EXP 1 CE SL hit"},
    {"time": "09:55:00", "utiliseddebits": 11366910.00, "event": "EXP 3 CE SL hit"},
]

# Sample positions from positionbook
SAMPLE_POSITIONS = [
    {
        "symbol": "NIFTY30DEC2525800PE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": -1125,
        "average_price": "8.70",
        "ltp": 5.45,
        "pnl": 3656.25
    },
    {
        "symbol": "NIFTY30DEC2525900PE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": -1125,
        "average_price": "45.43",
        "ltp": 23.35,
        "pnl": 24843.75
    },
    {
        "symbol": "NIFTY30DEC2525950PE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": -1125,
        "average_price": "79.03",
        "ltp": 44.35,
        "pnl": 39018.75
    },
    {
        "symbol": "NIFTY29DEC2625000CE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": 450,
        "average_price": "3381.03",
        "ltp": 2995,
        "pnl": -173711.25
    },
    {
        "symbol": "NIFTY29DEC2625000PE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": -450,
        "average_price": "371.55",
        "ltp": 375,
        "pnl": -1552.5
    },
    {
        "symbol": "NIFTY29DEC2626000PE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": 450,
        "average_price": "600.26",
        "ltp": 562,
        "pnl": -17216.25
    },
    {
        "symbol": "NIFTY30DEC2525850CE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": 0,
        "average_price": "0.00",
        "ltp": 108.15,
        "pnl": -8606.25
    },
    {
        "symbol": "NIFTY30DEC2525900CE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": 0,
        "average_price": "0.00",
        "ltp": 69.75,
        "pnl": -19856.25
    },
    {
        "symbol": "NIFTY30DEC2526000CE",
        "exchange": "NFO",
        "product": "NRML",
        "quantity": 0,
        "average_price": "0.00",
        "ltp": 22.05,
        "pnl": -5737.5
    },
]

# Sample funds response
SAMPLE_FUNDS = {
    "utiliseddebits": "10033810.88",
    "availablecash": "43178244.28",
    "collateral": "52062242.60",
    "m2mrealized": "0.00",
    "m2munrealized": "-2786.25",
}

# Budget calculation
NUM_BASKETS = 15
BUDGET_PER_BASKET = 1000000
TOTAL_BUDGET = 15000000
