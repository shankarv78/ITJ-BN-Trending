# Margin Monitor

Real-time intraday margin utilization monitoring for Nifty/Sensex options trading.

## Overview

This service tracks margin usage throughout the trading day by:
- Capturing a baseline margin at 09:15:15 IST (before first strategy entry)
- Polling OpenAlgo API every 5 minutes to capture margin snapshots
- Calculating intraday margin utilization against a configurable budget
- Filtering and categorizing positions by index and expiry
- Generating end-of-day summaries and day-of-week analytics

## Quick Start

### 1. Install Dependencies

```bash
cd margin-monitor
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the environment template and fill in your values:

```bash
# Create .env file
cat > .env << EOF
# Margin Monitor Backend
MM_PORT=5010
MM_HOST=0.0.0.0

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/portfolio_manager
MM_SCHEMA=margin_monitor

# OpenAlgo
OPENALGO_BASE_URL=http://127.0.0.1:5000
OPENALGO_API_KEY=your_api_key_here

# Trading Defaults
DEFAULT_BUDGET_PER_BASKET=1000000

# Frontend
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
EOF
```

### 3. Initialize Database

```bash
# Create schema and tables
alembic upgrade head
```

Or manually create the schema:
```sql
CREATE SCHEMA IF NOT EXISTS margin_monitor;
```

### 4. Run the Service

```bash
python run.py
```

The service will start on http://localhost:5010

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/margin/config` | POST/GET | Set/get daily configuration |
| `/api/margin/baseline` | POST | Capture baseline margin |
| `/api/margin/baseline/manual` | POST | Manually set baseline |
| `/api/margin/current` | GET | Get current margin status |
| `/api/margin/positions` | GET | Get filtered positions |
| `/api/margin/history` | GET | Get day's snapshots |
| `/api/margin/summary` | GET | Get daily summaries |
| `/api/margin/analytics` | GET | Get day-of-week analytics |
| `/api/margin/snapshot` | POST | Manually trigger snapshot |
| `/health` | GET | Health check |

## Scheduled Jobs

| Job | Time | Description |
|-----|------|-------------|
| Baseline Capture | 09:15:15 IST | Auto-capture baseline margin |
| Margin Polling | Every 5 min (09:20-15:30) | Capture margin snapshots |
| EOD Summary | 15:35 IST | Generate daily summary |

## Configuration Options

### Daily Config (via API)

```json
{
  "index_name": "NIFTY",
  "expiry_date": "2025-12-30",
  "num_baskets": 15,
  "budget_per_basket": 1000000
}
```

- `index_name`: NIFTY or SENSEX
- `expiry_date`: Trading expiry (YYYY-MM-DD)
- `num_baskets`: Number of baskets (determines total budget)
- `budget_per_basket`: Budget per basket (default ₹10L)

## Symbol Format

Nifty/Sensex option symbols follow this format:

```
NIFTY30DEC2525800PE
│    │ │  ││     └── Option type (CE/PE)
│    │ │  │└─────── Strike price (25800)
│    │ │  └──────── Year (25 = 2025)
│    │ └─────────── Month (DEC)
│    └───────────── Day (30)
└────────────────── Index name
```

## Position Categories

| Quantity | Category | Description |
|----------|----------|-------------|
| `< 0` | Short | Options sold (consume margin) |
| `> 0` | Long | Options bought (hedges) |
| `= 0` | Closed | Position exited (SL hit) |

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_symbol_parser.py -v
```

## Frontend Integration

The Margin Monitor is integrated into the existing React frontend:
- Route: `/margin-monitor`
- API Client: `frontend/src/lib/margin-api-client.ts`
- Page: `frontend/src/pages/MarginMonitor.tsx`

## Utilization Thresholds

| Range | Status | Color |
|-------|--------|-------|
| 0-70% | Safe | Green |
| 70-90% | Warning | Yellow |
| 90-100% | Critical | Red |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                              │
│                    /margin-monitor page                          │
└─────────────────────────────────────────────────────────────────┘
                              │ REST API (port 5010)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 MARGIN MONITOR BACKEND (FastAPI)                 │
│  Services: OpenAlgo, Margin, Position, Scheduler, Analytics     │
└─────────────────────────────────────────────────────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   OpenAlgo API (:5000)  │     │  PostgreSQL Database    │
│   /api/v1/funds         │     │  Schema: margin_monitor │
│   /api/v1/positionbook  │     └─────────────────────────┘
└─────────────────────────┘
```
