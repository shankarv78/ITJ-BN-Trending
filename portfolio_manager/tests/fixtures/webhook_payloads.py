"""
Test fixtures for webhook payloads

Reusable JSON payloads for testing webhook endpoint
"""
VALID_BASE_ENTRY_BN = {
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000.0,
    "stop": 51650.0,
    "lots": 5,
    "atr": 350.0,
    "er": 0.82,
    "supertrend": 51650.0,
    "roc": 2.5,
    "timestamp": "2025-11-28T10:30:00Z"
}

VALID_PYRAMID_GOLD = {
    "type": "PYRAMID",
    "instrument": "GOLD_MINI",
    "position": "Long_2",
    "price": 72500.0,
    "stop": 72000.0,
    "lots": 2,
    "atr": 450.0,
    "er": 0.8,
    "supertrend": 72000.0,
    "roc": 1.2,
    "timestamp": "2025-11-28T14:15:00Z"
}

VALID_EXIT_WITH_REASON = {
    "type": "EXIT",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 51800.0,
    "stop": 51800.0,
    "lots": 5,
    "atr": 500.0,
    "er": 0.75,
    "supertrend": 51500.0,
    "roc": 2.5,
    "reason": "TOM_BASSO_STOP",
    "timestamp": "2025-11-28T15:00:00Z"
}

INVALID_MISSING_POSITION = {
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    # "position": "Long_1",  # Missing
    "price": 52000.0,
    "stop": 51650.0,
    "lots": 5,
    "atr": 350.0,
    "er": 0.82,
    "supertrend": 51650.0,
    "timestamp": "2025-11-28T10:30:00Z"
}

INVALID_POSITION_LONG_7 = {
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_7",  # Invalid
    "price": 52000.0,
    "stop": 51650.0,
    "lots": 5,
    "atr": 350.0,
    "er": 0.82,
    "supertrend": 51650.0,
    "timestamp": "2025-11-28T10:30:00Z"
}

INVALID_EXIT_NO_REASON = {
    "type": "EXIT",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 51800.0,
    "stop": 51800.0,
    "lots": 5,
    "atr": 500.0,
    "er": 0.75,
    "supertrend": 51500.0,
    "roc": 2.5,
    # "reason": "TOM_BASSO_STOP",  # Missing
    "timestamp": "2025-11-28T15:00:00Z"
}

INVALID_MISSING_TYPE = {
    # "type": "BASE_ENTRY",  # Missing
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000.0,
    "stop": 51650.0,
    "lots": 5,
    "atr": 350.0,
    "er": 0.82,
    "supertrend": 51650.0,
    "timestamp": "2025-11-28T10:30:00Z"
}

INVALID_INSTRUMENT = {
    "type": "BASE_ENTRY",
    "instrument": "INVALID_INSTRUMENT",
    "position": "Long_1",
    "price": 52000.0,
    "stop": 51650.0,
    "lots": 5,
    "atr": 350.0,
    "er": 0.82,
    "supertrend": 51650.0,
    "timestamp": "2025-11-28T10:30:00Z"
}

# Silver Mini payloads
VALID_BASE_ENTRY_SILVER_MINI = {
    "type": "BASE_ENTRY",
    "instrument": "SILVER_MINI",
    "position": "Long_1",
    "price": 90500.0,
    "stop": 88700.0,  # 2 × ATR stop
    "lots": 3,
    "atr": 900.0,
    "er": 0.78,
    "supertrend": 88700.0,
    "roc": 1.5,
    "timestamp": "2025-12-15T15:30:00Z"
}

VALID_PYRAMID_SILVER_MINI = {
    "type": "PYRAMID",
    "instrument": "SILVER_MINI",
    "position": "Long_2",
    "price": 92000.0,
    "stop": 90200.0,
    "lots": 2,
    "atr": 900.0,
    "er": 0.80,
    "supertrend": 90200.0,
    "roc": 1.8,
    "timestamp": "2025-12-16T16:00:00Z"
}

VALID_EXIT_SILVER_MINI = {
    "type": "EXIT",
    "instrument": "SILVER_MINI",
    "position": "ALL",
    "price": 93500.0,
    "stop": 93500.0,
    "lots": 5,
    "atr": 850.0,
    "er": 0.72,
    "supertrend": 92500.0,
    "roc": 2.0,
    "reason": "TOM_BASSO_STOP",
    "timestamp": "2025-12-17T22:30:00Z"
}
