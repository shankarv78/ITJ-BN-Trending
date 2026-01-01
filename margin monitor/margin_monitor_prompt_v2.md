# Margin Monitor System - Development Prompt

## Project Overview

Build a **Python backend service** with **REST API endpoints** to monitor margin utilization and hedge costs for intraday index option strategies. The system is **strategy-agnostic** - it observes positions from Zerodha and tracks margin usage without needing to know strategy details.

**Platform:** Mac (development) with existing React/Vue frontend and OpenAlgo integration

---

## Business Context

### What the User Does

- Trades intraday options on **Nifty** and **Sensex** indices
- Uses **Stoxxo Intelligent Trading Bridge** for order execution
- Runs multiple strategies (straddles, ITM, delta-based, wait-and-trade, etc.)
- All trades use **NRML** product type (not MIS), even for intraday
- Trades **current week expiry** only for intraday positions

### Trading Schedule

| Day | Index | Expiry Type | Trading Active |
|-----|-------|-------------|----------------|
| Monday | Nifty | 1DTE (Tuesday expiry) | ✅ Yes |
| Tuesday | Nifty | 0DTE (Expiry day) | ✅ Yes |
| Wednesday | - | - | ❌ No trades |
| Thursday | Sensex | 0DTE (Expiry day) | ✅ Yes |
| Friday | Nifty | 2DTE (Next Tuesday expiry) | ✅ Yes |

### Budget Model

```
1 basket  = ₹10 Lakhs margin budget
N baskets = N × ₹10L budget

Example:
- User runs 15 baskets on Tuesday
- Total budget = 15 × ₹10L = ₹1.5 Crore
- All intraday positions must stay within ₹1.5Cr margin
```

**Lot Sizes:**
- Nifty: 75 qty per lot
- Sensex: 10 qty per lot

### Existing Positions to Exclude

The user has **long-term Nifty positions** (e.g., Dec 2026 synthetic long) that should NOT be counted in intraday margin tracking. These are identified by their far-out expiry dates.

Example Dec 2026 position:
```
├── Long 450 qty  NIFTY 25000 CE (Dec 2026)
├── Short 450 qty NIFTY 25000 PE (Dec 2026)
└── Long 450 qty  NIFTY 26000 PE (Dec 2026)

Current margin: ~₹5.92L (this becomes BASELINE)
```

---

## Core Concept: Baseline Subtraction

**Problem:** Zerodha API provides only account-level margin totals, not per-position or per-index breakdown.

**Solution:** Capture baseline margin before intraday trades begin.

```
Timeline:
─────────────────────────────────────────────────────────────────
09:15 AM │ Market opens
09:16 AM │ CAPTURE BASELINE (only long-term positions exist)
09:16+   │ Stoxxo starts entering intraday trades
...      │ Monitor: Intraday Margin = Total - Baseline
03:30 PM │ Market closes, generate EOD summary
─────────────────────────────────────────────────────────────────

Calculation:
├── Baseline Margin     = Total margin at 9:16 AM (before intraday trades)
├── Total Margin Used   = Current margin from kite.margins()
├── Intraday Margin     = Total Margin Used - Baseline Margin
├── Budget              = Number of Baskets × ₹10,00,000
└── Utilization %       = (Intraday Margin / Budget) × 100
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXISTING FRONTEND                             │
│              (React/Vue - already built)                         │
│                                                                  │
│  New Components Needed:                                          │
│  • Daily config panel (index, expiry, baskets)                  │
│  • Baseline capture button + status                             │
│  • Real-time utilization gauge                                   │
│  • Margin timeline chart (5-min intervals)                      │
│  • Positions table (shorts vs longs)                            │
│  • Hedge cost display                                            │
│  • Historical analysis by day-of-week                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              NEW PYTHON BACKEND SERVICE                          │
│                  (Separate from existing PM)                     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  API Layer (FastAPI)                                     │    │
│  │  • POST /api/margin/config        - Set day's config    │    │
│  │  • POST /api/margin/baseline      - Capture baseline    │    │
│  │  • GET  /api/margin/current       - Current status      │    │
│  │  • GET  /api/margin/positions     - Filtered positions  │    │
│  │  • GET  /api/margin/history       - Day's snapshots     │    │
│  │  • GET  /api/margin/summary       - Daily summaries     │    │
│  │  • GET  /api/margin/analytics     - Day-of-week stats   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Core Services                                           │    │
│  │  • MarginService    - Fetch & calculate margins         │    │
│  │  • PositionService  - Filter & categorize positions     │    │
│  │  • SchedulerService - 5-min polling during market hours │    │
│  │  • DatabaseService  - Persist snapshots & summaries     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Database (SQLite)                                       │    │
│  │  • daily_config      - Daily parameters                 │    │
│  │  • margin_snapshots  - 5-min snapshots                  │    │
│  │  • position_snapshots - Position details per snapshot   │    │
│  │  • daily_summary     - EOD aggregates                   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Reuse existing token
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OPENALGO (Existing)                           │
│         Already integrated with Kite Connect API                 │
│         Provides access token for Zerodha                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ZERODHA KITE API                              │
│  • kite.margins()   - Account-level margin info                 │
│  • kite.positions() - All positions with P&L                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

```sql
-- Daily configuration (one row per trading day)
CREATE TABLE daily_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    day_of_week INTEGER NOT NULL,           -- 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    day_name TEXT NOT NULL,                 -- 'Monday', 'Tuesday', etc.
    index_name TEXT NOT NULL,               -- 'NIFTY' or 'SENSEX'
    expiry_date DATE NOT NULL,              -- Actual expiry being traded
    num_baskets INTEGER NOT NULL,           -- Quantity multiplier
    budget_per_basket REAL DEFAULT 1000000, -- ₹10L default
    total_budget REAL NOT NULL,             -- num_baskets × budget_per_basket
    baseline_margin REAL,                   -- Captured at 9:16 AM
    baseline_captured_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,            -- 0 if no trading (e.g., Wednesday)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5-minute margin snapshots
CREATE TABLE margin_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    -- Raw margin data from Zerodha
    total_margin_used REAL NOT NULL,
    available_margin REAL NOT NULL,
    span_margin REAL,
    exposure_margin REAL,
    
    -- Calculated values
    baseline_margin REAL NOT NULL,
    intraday_margin REAL NOT NULL,          -- total - baseline
    utilization_pct REAL NOT NULL,          -- (intraday / budget) × 100
    
    -- Position summary
    short_positions_count INTEGER,          -- Number of short legs
    short_positions_qty INTEGER,            -- Total short quantity
    long_positions_count INTEGER,           -- Number of long legs (hedges)
    long_positions_qty INTEGER,             -- Total long quantity
    
    -- Cost tracking
    total_hedge_cost REAL,                  -- Premium paid for long positions
    
    FOREIGN KEY (config_id) REFERENCES daily_config(id)
);

-- Position details at each snapshot (for drill-down)
CREATE TABLE position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    tradingsymbol TEXT NOT NULL,
    exchange TEXT NOT NULL,                 -- 'NFO' or 'BFO'
    product TEXT NOT NULL,                  -- 'NRML'
    quantity INTEGER NOT NULL,              -- +ve=long, -ve=short
    average_price REAL NOT NULL,
    last_price REAL NOT NULL,
    pnl REAL NOT NULL,
    position_type TEXT NOT NULL,            -- 'SHORT' or 'LONG'
    option_type TEXT NOT NULL,              -- 'CE' or 'PE'
    strike_price REAL NOT NULL,
    
    FOREIGN KEY (snapshot_id) REFERENCES margin_snapshots(id)
);

-- Daily summary (generated at EOD)
CREATE TABLE daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL UNIQUE,
    date DATE NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    index_name TEXT NOT NULL,
    num_baskets INTEGER NOT NULL,
    total_budget REAL NOT NULL,
    
    -- Margin metrics
    baseline_margin REAL NOT NULL,
    max_intraday_margin REAL NOT NULL,
    max_utilization_pct REAL NOT NULL,
    avg_utilization_pct REAL,
    
    -- Hedge metrics
    total_hedge_cost REAL NOT NULL,
    max_hedge_positions INTEGER,
    
    -- Position metrics
    max_short_qty INTEGER,
    max_long_qty INTEGER,
    
    -- Timestamps
    first_position_time TIMESTAMP,
    last_position_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (config_id) REFERENCES daily_config(id)
);

-- Indexes for performance
CREATE INDEX idx_snapshots_timestamp ON margin_snapshots(timestamp);
CREATE INDEX idx_snapshots_config ON margin_snapshots(config_id);
CREATE INDEX idx_position_snapshot ON position_snapshots(snapshot_id);
CREATE INDEX idx_summary_date ON daily_summary(date);
CREATE INDEX idx_summary_day_of_week ON daily_summary(day_of_week);
CREATE INDEX idx_config_day_of_week ON daily_config(day_of_week);
```

---

## API Specifications

### 1. Set Daily Configuration

```
POST /api/margin/config
```

**Request:**
```json
{
    "index_name": "NIFTY",
    "expiry_date": "2025-01-02",
    "num_baskets": 15
}
```

**Response:**
```json
{
    "success": true,
    "config": {
        "id": 1,
        "date": "2024-12-31",
        "day_of_week": 1,
        "day_name": "Tuesday",
        "index_name": "NIFTY",
        "expiry_date": "2025-01-02",
        "num_baskets": 15,
        "budget_per_basket": 1000000,
        "total_budget": 15000000,
        "baseline_margin": null,
        "baseline_captured_at": null
    }
}
```

### 2. Capture Baseline Margin

```
POST /api/margin/baseline
```

**Request:** (optional)
```json
{
    "config_id": 1
}
```

**Response:**
```json
{
    "success": true,
    "baseline_margin": 592057.13,
    "captured_at": "2024-12-31T09:16:00+05:30",
    "message": "Baseline captured successfully"
}
```

### 3. Get Current Margin Status

```
GET /api/margin/current
```

**Response:**
```json
{
    "success": true,
    "timestamp": "2024-12-31T10:30:00+05:30",
    "config": {
        "date": "2024-12-31",
        "day_name": "Tuesday",
        "index_name": "NIFTY",
        "expiry_date": "2025-01-02",
        "num_baskets": 15,
        "total_budget": 15000000
    },
    "margin": {
        "total_used": 8592057.13,
        "baseline": 592057.13,
        "intraday_used": 8000000.00,
        "available": 43408850.73,
        "utilization_pct": 53.33,
        "budget_remaining": 7000000.00
    },
    "positions": {
        "short_count": 6,
        "short_qty": 3375,
        "long_count": 4,
        "long_qty": 2250,
        "hedge_cost": 45000.00
    }
}
```

### 4. Get Filtered Positions

```
GET /api/margin/positions
```

**Response:**
```json
{
    "success": true,
    "timestamp": "2024-12-31T10:30:00+05:30",
    "filter": {
        "index": "NIFTY",
        "expiry": "2025-01-02"
    },
    "short_positions": [
        {
            "tradingsymbol": "NIFTY2510223800CE",
            "quantity": -1125,
            "average_price": 285.50,
            "last_price": 278.30,
            "pnl": 8100.00,
            "strike": 23800,
            "option_type": "CE"
        },
        {
            "tradingsymbol": "NIFTY2510223800PE",
            "quantity": -1125,
            "average_price": 312.75,
            "last_price": 298.40,
            "pnl": 16143.75,
            "strike": 23800,
            "option_type": "PE"
        }
    ],
    "long_positions": [
        {
            "tradingsymbol": "NIFTY2510223400PE",
            "quantity": 1125,
            "average_price": 5.20,
            "last_price": 4.80,
            "cost": 5850.00,
            "strike": 23400,
            "option_type": "PE"
        }
    ],
    "excluded_positions": [
        {
            "tradingsymbol": "NIFTY25DEC25000CE",
            "quantity": 450,
            "reason": "Expiry mismatch (Dec 2025)"
        }
    ]
}
```

### 5. Get Historical Snapshots

```
GET /api/margin/history?date=2024-12-31
```

**Response:**
```json
{
    "success": true,
    "date": "2024-12-31",
    "config": {
        "day_name": "Tuesday",
        "index_name": "NIFTY",
        "num_baskets": 15,
        "total_budget": 15000000
    },
    "snapshots": [
        {
            "timestamp": "2024-12-31T09:20:00+05:30",
            "intraday_margin": 2500000,
            "utilization_pct": 16.67,
            "hedge_cost": 0,
            "short_qty": 1125,
            "long_qty": 0
        },
        {
            "timestamp": "2024-12-31T09:25:00+05:30",
            "intraday_margin": 4800000,
            "utilization_pct": 32.00,
            "hedge_cost": 0,
            "short_qty": 2250,
            "long_qty": 0
        }
    ]
}
```

### 6. Get Daily Summaries

```
GET /api/margin/summary?start_date=2024-12-01&end_date=2024-12-31
```

**Response:**
```json
{
    "success": true,
    "summaries": [
        {
            "date": "2024-12-30",
            "day_name": "Monday",
            "index_name": "NIFTY",
            "num_baskets": 15,
            "max_utilization_pct": 72.5,
            "total_hedge_cost": 45000
        },
        {
            "date": "2024-12-31",
            "day_name": "Tuesday",
            "index_name": "NIFTY",
            "num_baskets": 15,
            "max_utilization_pct": 85.3,
            "total_hedge_cost": 67500
        }
    ]
}
```

### 7. Get Day-of-Week Analytics

```
GET /api/margin/analytics?period=30
```

**Response:**
```json
{
    "success": true,
    "period_days": 30,
    "by_day_of_week": [
        {
            "day_name": "Monday",
            "index_name": "NIFTY",
            "trading_days": 4,
            "avg_max_utilization": 72.3,
            "avg_hedge_cost": 42500,
            "max_utilization_seen": 85.0,
            "min_utilization_seen": 58.0
        },
        {
            "day_name": "Tuesday",
            "index_name": "NIFTY",
            "trading_days": 4,
            "avg_max_utilization": 88.5,
            "avg_hedge_cost": 65000,
            "max_utilization_seen": 95.0,
            "min_utilization_seen": 78.0
        },
        {
            "day_name": "Thursday",
            "index_name": "SENSEX",
            "trading_days": 4,
            "avg_max_utilization": 62.8,
            "avg_hedge_cost": 28000,
            "max_utilization_seen": 72.0,
            "min_utilization_seen": 55.0
        },
        {
            "day_name": "Friday",
            "index_name": "NIFTY",
            "trading_days": 4,
            "avg_max_utilization": 55.2,
            "avg_hedge_cost": 22000,
            "max_utilization_seen": 65.0,
            "min_utilization_seen": 48.0
        }
    ],
    "insights": [
        "Tuesday (Nifty 0DTE) has highest average utilization at 88.5%",
        "Friday (Nifty 2DTE) has lowest hedge costs at ₹22,000 average",
        "Consider increasing baskets on Friday - utilization headroom available"
    ]
}
```

---

## Position Filtering Logic

### Trading Symbol Format

```
Nifty (NFO):
NIFTY + YY + MMM + DD + STRIKE + CE/PE (weekly)
NIFTY + YY + MMM + STRIKE + CE/PE (monthly)

Examples:
NIFTY2510223800CE  → Nifty, 2025, Jan 02, 23800 CE (weekly)
NIFTY25JAN23800CE  → Nifty, 2025, Jan (monthly), 23800 CE
NIFTY25DEC25000CE  → Nifty, 2025, Dec (monthly), 25000 CE

Sensex (BFO):
SENSEX + YY + MMM + DD + STRIKE + CE/PE (weekly)
SENSEX + YY + M + DD + STRIKE + CE/PE (weekly alternate format)

Examples:
SENSEX2510378000PE → Sensex, 2025, Jan 03, 78000 PE
```

### Filter Pseudocode

```python
def filter_positions(all_positions, index_name, expiry_date):
    """
    Filter positions by index and expiry date.
    Strategy-agnostic: doesn't care about strategy type.
    """
    included = []
    excluded = []
    
    for pos in all_positions:
        symbol = pos['tradingsymbol']
        
        # Check index match
        if index_name == 'NIFTY' and not symbol.startswith('NIFTY'):
            excluded.append({**pos, 'reason': 'Wrong index'})
            continue
            
        if index_name == 'SENSEX' and not symbol.startswith('SENSEX'):
            excluded.append({**pos, 'reason': 'Wrong index'})
            continue
        
        # Check product type (should be NRML for this user)
        if pos['product'] != 'NRML':
            excluded.append({**pos, 'reason': f"Product is {pos['product']}, not NRML"})
            continue
        
        # Parse and check expiry
        parsed_expiry = parse_expiry_from_symbol(symbol)
        if parsed_expiry != expiry_date:
            excluded.append({**pos, 'reason': f'Expiry mismatch ({parsed_expiry})'})
            continue
        
        # Position matches - include it
        included.append(pos)
    
    return included, excluded


def categorize_positions(filtered_positions):
    """
    Categorize by quantity sign.
    SHORT (qty < 0): Options sold - consume margin
    LONG (qty > 0): Options bought - hedges
    """
    shorts = []
    longs = []
    
    for pos in filtered_positions:
        if pos['quantity'] < 0:
            shorts.append(pos)
        else:
            longs.append(pos)
    
    return shorts, longs


def calculate_hedge_cost(long_positions):
    """
    Total premium paid for long (hedge) positions.
    Cost = Σ (average_price × quantity)
    """
    return sum(pos['average_price'] * pos['quantity'] for pos in long_positions)
```

---

## Scheduler Service

```python
"""
Market Hours: 9:15 AM - 3:30 PM IST

Schedule:
- 9:16 AM: Auto-capture baseline (if config exists and baseline not captured)
- 9:20 - 3:30 PM: Poll every 5 minutes
- 3:35 PM: Generate EOD summary
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

IST = pytz.timezone('Asia/Kolkata')

def setup_scheduler():
    scheduler = BackgroundScheduler(timezone=IST)
    
    # Baseline capture at 9:16 AM on weekdays
    scheduler.add_job(
        auto_capture_baseline,
        CronTrigger(day_of_week='mon-fri', hour=9, minute=16),
        id='baseline_capture',
        replace_existing=True
    )
    
    # Regular polling every 5 minutes from 9:20 to 15:30
    scheduler.add_job(
        capture_margin_snapshot,
        CronTrigger(
            day_of_week='mon-fri',
            hour='9-15',
            minute='0,5,10,15,20,25,30,35,40,45,50,55'
        ),
        id='margin_polling',
        replace_existing=True
    )
    
    # EOD summary at 3:35 PM
    scheduler.add_job(
        generate_daily_summary,
        CronTrigger(day_of_week='mon-fri', hour=15, minute=35),
        id='eod_summary',
        replace_existing=True
    )
    
    return scheduler
```

---

## Kite Connect Integration

### Reusing OpenAlgo Token

The existing OpenAlgo setup generates a Kite access token daily. This margin monitor should reuse that token.

**Developer Task:** Identify how OpenAlgo exposes the token:
- File path (e.g., `~/.openalgo/access_token`)
- Database table
- Redis key
- API endpoint (e.g., `GET http://localhost:5000/api/token`)

### Required API Calls

```python
from kiteconnect import KiteConnect

def get_kite_client():
    """Initialize Kite client with OpenAlgo's token."""
    kite = KiteConnect(api_key=KITE_API_KEY)
    access_token = get_token_from_openalgo()  # Implement based on OpenAlgo setup
    kite.set_access_token(access_token)
    return kite


def get_margin_info(kite):
    """Fetch account margin details."""
    margins = kite.margins(segment="equity")
    return {
        'available': margins['net'],
        'used': margins['utilised']['debits'],
        'span': margins['utilised'].get('span', 0),
        'exposure': margins['utilised'].get('exposure', 0)
    }


def get_positions(kite):
    """Fetch all positions."""
    positions = kite.positions()
    return positions['net']
```

---

## Project Structure

```
margin-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Configuration settings
│   ├── database.py             # SQLite setup & connection
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # API route handlers
│   │   └── schemas.py          # Pydantic request/response models
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── margin_service.py   # Margin calculation logic
│   │   ├── position_service.py # Position filtering & categorization
│   │   ├── kite_service.py     # Zerodha API wrapper
│   │   ├── scheduler_service.py # APScheduler setup
│   │   └── analytics_service.py # Day-of-week analytics
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── db_models.py        # SQLAlchemy ORM models
│   │
│   └── utils/
│       ├── __init__.py
│       ├── symbol_parser.py    # Parse trading symbols
│       └── date_utils.py       # IST timezone helpers
│
├── data/
│   └── margin_monitor.db       # SQLite database
│
├── tests/
│   ├── __init__.py
│   ├── test_symbol_parser.py
│   ├── test_position_filter.py
│   └── test_margin_calc.py
│
├── requirements.txt
├── README.md
└── run.py                      # Start script
```

---

## Requirements

```txt
# requirements.txt

fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0
sqlalchemy>=2.0.0
apscheduler>=3.10.0
kiteconnect>=5.0.0
python-dateutil>=2.8.0
pytz>=2023.3
httpx>=0.25.0
```

---

## Configuration

```python
# app/config.py

import os
from pathlib import Path

class Settings:
    # Database
    DB_PATH: Path = Path(__file__).parent.parent / "data" / "margin_monitor.db"
    
    # Kite Connect
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    
    # OpenAlgo token source (configure based on your setup)
    OPENALGO_TOKEN_FILE: str = os.getenv("OPENALGO_TOKEN_FILE", "")
    OPENALGO_TOKEN_ENDPOINT: str = os.getenv("OPENALGO_TOKEN_ENDPOINT", "")
    
    # Trading parameters
    DEFAULT_BUDGET_PER_BASKET: int = 1000000  # ₹10L
    LOT_SIZE_NIFTY: int = 75
    LOT_SIZE_SENSEX: int = 10
    
    # Scheduler
    POLLING_INTERVAL_MINUTES: int = 5
    BASELINE_CAPTURE_TIME: str = "09:16"
    MARKET_OPEN: str = "09:15"
    MARKET_CLOSE: str = "15:30"
    
    # Timezone
    TIMEZONE: str = "Asia/Kolkata"

settings = Settings()
```

---

## Frontend Components Needed

### 1. Daily Configuration Panel
```
┌─────────────────────────────────────────────────────────────┐
│  Today's Configuration                          [Set Config] │
│                                                              │
│  Index:    [NIFTY ▼]     Expiry: [2025-01-02 📅]           │
│  Baskets:  [15    ]      Budget: ₹1.5 Cr (auto-calculated) │
│                                                              │
│  Baseline: ₹5,92,057  (captured at 09:16:00)  [Re-capture] │
└─────────────────────────────────────────────────────────────┘
```

### 2. Real-Time Utilization Display
```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│            MARGIN UTILIZATION                                │
│                                                              │
│                   ╭───────╮                                 │
│                 ╱    53%    ╲                               │
│               ╱               ╲                              │
│              │     ₹80.0L     │                             │
│              │   of ₹1.5Cr    │                             │
│               ╲               ╱                              │
│                 ╲           ╱                                │
│                   ╰───────╯                                 │
│                                                              │
│  ┌──────────┬──────────┬──────────┬──────────┐             │
│  │ Baseline │ Intraday │ Available│ Hedge    │             │
│  │ ₹5.9L    │ ₹80.0L   │ ₹4.3Cr   │ ₹45,000  │             │
│  └──────────┴──────────┴──────────┴──────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### 3. Margin Timeline Chart
```
┌─────────────────────────────────────────────────────────────┐
│  Margin Utilization - Today                                  │
│                                                              │
│  100% ┤ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ Budget Line          │
│   80% ┤                 ╭────╮                               │
│   60% ┤           ╭─────╯    ╰──╮                           │
│   40% ┤     ╭─────╯              ╰────                      │
│   20% ┤ ────╯                                               │
│    0% ┼─────┬─────┬─────┬─────┬─────┬─────┬─────           │
│      9:15 10:00 11:00 12:00 13:00 14:00 15:00               │
└─────────────────────────────────────────────────────────────┘
```

### 4. Positions Table
```
┌─────────────────────────────────────────────────────────────┐
│  Positions (NIFTY, 02-Jan-2025 Expiry)                      │
│                                                              │
│  SHORT POSITIONS (Margin Consumers)                         │
│  ┌─────────────────┬────────┬─────────┬─────────┬────────┐ │
│  │ Symbol          │ Qty    │ Avg     │ LTP     │ P&L    │ │
│  ├─────────────────┼────────┼─────────┼─────────┼────────┤ │
│  │ NIFTY 23800 CE  │ -1125  │ 285.50  │ 278.30  │ +8,100 │ │
│  │ NIFTY 23800 PE  │ -1125  │ 312.75  │ 298.40  │ +16,143│ │
│  └─────────────────┴────────┴─────────┴─────────┴────────┘ │
│                                                              │
│  LONG POSITIONS (Hedges)                  Cost: ₹45,000     │
│  ┌─────────────────┬────────┬─────────┬─────────┬────────┐ │
│  │ Symbol          │ Qty    │ Avg     │ LTP     │ P&L    │ │
│  ├─────────────────┼────────┼─────────┼─────────┼────────┤ │
│  │ NIFTY 23400 PE  │ +1125  │ 5.20    │ 4.80    │ -450   │ │
│  └─────────────────┴────────┴─────────┴─────────┴────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 5. Day-of-Week Analytics
```
┌─────────────────────────────────────────────────────────────┐
│  Analytics (Last 30 Days)                                    │
│                                                              │
│  ┌─────────┬───────┬───────────┬────────────┬─────────────┐│
│  │ Day     │ Index │ Avg Util% │ Avg Hedge  │ Days Traded ││
│  ├─────────┼───────┼───────────┼────────────┼─────────────┤│
│  │ Monday  │ NIFTY │ 72.3%     │ ₹42,500    │ 4           ││
│  │ Tuesday │ NIFTY │ 88.5%     │ ₹65,000    │ 4           ││
│  │ Thursday│ SENSEX│ 62.8%     │ ₹28,000    │ 4           ││
│  │ Friday  │ NIFTY │ 55.2%     │ ₹22,000    │ 4           ││
│  └─────────┴───────┴───────────┴────────────┴─────────────┘│
│                                                              │
│  💡 Tuesday has highest utilization - consider adding hedges │
│  💡 Friday has headroom - could increase baskets             │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing Checklist

### Symbol Parser Tests
- [ ] Parse weekly Nifty symbol: `NIFTY2510223800CE`
- [ ] Parse monthly Nifty symbol: `NIFTY25JAN23800CE`
- [ ] Parse far-dated Nifty symbol: `NIFTY25DEC25000CE`
- [ ] Parse Sensex symbol: `SENSEX2510378000PE`
- [ ] Handle invalid symbols gracefully

### Position Filter Tests
- [ ] Include matching index + expiry positions
- [ ] Exclude wrong index positions
- [ ] Exclude wrong expiry (e.g., Dec 2026) positions
- [ ] Exclude non-NRML products
- [ ] Handle empty position list

### Margin Calculation Tests
- [ ] Intraday margin = Total - Baseline
- [ ] Utilization % = (Intraday / Budget) × 100
- [ ] Handle negative intraday margin (baseline changed)

### Hedge Cost Tests
- [ ] Sum of (avg_price × qty) for long positions
- [ ] Handle no hedges (cost = 0)

---

## Developer Questions

Before starting implementation, clarify:

1. **OpenAlgo Token:** How is the Kite access token stored/retrieved?
   - File path?
   - API endpoint?
   - Database?

2. **Frontend Framework:** React, Vue, or other?

3. **Backend Port:** What port for this service? (avoid conflict with existing PM)

4. **CORS:** Which origins should be allowed?

5. **Existing APIs:** Any existing API conventions (auth, error format) to follow?

---

## Summary

This margin monitor system:

1. **Tracks** margin utilization for intraday index options trading
2. **Filters** positions by user-specified index and expiry date
3. **Calculates** intraday margin using baseline subtraction
4. **Categorizes** positions as SHORT (margin) or LONG (hedge) based on quantity
5. **Stores** 5-minute snapshots for historical analysis
6. **Analyzes** patterns by day-of-week to optimize capital usage

The system is **strategy-agnostic** - it doesn't need to know if you're running straddles, ITM strategies, delta-based entries, or any other approach. It simply observes what positions exist and tracks the margin they consume.
