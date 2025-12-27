# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🚀 Quick Session Start

**Last Updated:** December 2024

### Current State
- ✅ Portfolio Manager: Production ready with live trading
- ✅ Frontend: React dashboard at `localhost:8080`
- ✅ HA System: PostgreSQL + Redis for persistence
- ⚠️ Daily: Must login to Zerodha via OpenAlgo before market opens

### Start Everything
```bash
cd ~/claude-code/ITJ-BN-Trending/portfolio_manager
./start_all.sh start              # Starts: PostgreSQL → OpenAlgo → Tunnel → PM → Frontend
./start_all.sh status             # Check all services
./start_all.sh logs               # Tail all logs
```

### Recent Session Notes
<!-- Update this section after each session -->
- Fixed: start_all.sh now auto-starts PostgreSQL and clears stale lock files
- Fixed: Frontend port is 8080 (not 5173)
- Fixed: OpenAlgo auth cache issue (restart OpenAlgo after Zerodha login)

### Active Issues / TODOs
- None currently

---

## Repository Overview

A multi-component trading system for Bank Nifty and Gold Mini trend following:

1. **Pine Script Strategies** (`*.pine`) - TradingView signal generators
2. **Portfolio Manager** (`portfolio_manager/`) - Python live trading engine with Tom Basso position sizing
3. **Frontend** (`frontend/`) - React/TypeScript dashboard (local dev, formerly Lovable AI)

**Capital at Risk:** ₹1 crore (~$120K USD). This is a production trading system.

---

## System Architecture

```
┌─────────────────────────────────┐     ┌─────────────────────────────────────────┐
│  TradingView (Pine Script)      │     │  Portfolio Manager (Python)              │
│  ════════════════════════════   │     │  ════════════════════════════════════    │
│  SIGNAL GENERATOR ONLY          │────▶│  TOM BASSO POSITION SIZING ENGINE        │
│                                 │     │                                          │
│  Sends via webhook:             │     │  Calculates:                             │
│  • 7 condition states (bool)    │     │  • Position size (lots) using REAL equity│
│  • Indicator values (RSI, ST)   │     │  • Risk per trade (shared capital)       │
│  • Current price                │     │  • Margin availability (both instruments)│
│  • Position status              │     │  • Stop distance from SuperTrend         │
│                                 │     │                                          │
│  Does NOT calculate:            │     │  Executes via OpenAlgo:                  │
│  • Position sizing              │     │  • Synthetic futures (ATM options)       │
│  • Lots to trade                │     │  • Pyramiding decisions                  │
│  • Available margin             │     │  • Stop-loss management                  │
└─────────────────────────────────┘     └─────────────────────────────────────────┘
         │                                            │
         │                                            ▼
         │                              ┌─────────────────────────────┐
         │                              │  PostgreSQL + Redis (HA)    │
         │                              │  • State persistence        │
         │                              │  • Leader election          │
         │                              │  • Signal deduplication     │
         │                              │  • Crash recovery           │
         │                              └─────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Frontend (React/TypeScript)    │
│  • Dashboard with positions     │
│  • Equity curve, P&L metrics    │
│  • Emergency controls           │
│  • Holiday calendar             │
└─────────────────────────────────┘
```

**Key insight:** Pine Script's `strategy.equity` is per-chart only. Portfolio Manager knows actual portfolio equity across both Bank Nifty and Gold Mini positions.

---

## Current Development Status

### Active Branch: `feature/ha-phase1-database-persistence`

**Phase 1 Complete:** Database persistence with PostgreSQL
- All positions persisted to `portfolio_positions` table
- State recovery on startup (crash recovery)
- Signal deduplication via `signal_log` table

**Phase 2 In Progress:** Redis coordination (see TaskMaster tasks 21-32)
- Leader election for background tasks (rollover, cleanup)
- Distributed signal locking (prevent duplicates across instances)
- Active-Active architecture (all instances process webhooks)

### TaskMaster Project

This project uses TaskMaster for task management. **Project root: `./portfolio_manager`**

```bash
# View tasks (use portfolio_manager as projectRoot)
mcp__taskmaster-ai__get_tasks --projectRoot ./portfolio_manager

# Get next task
mcp__taskmaster-ai__next_task --projectRoot ./portfolio_manager
```

**Current focus areas:**
- Task 22: Redis Leader Election (mostly done)
- Task 23: Distributed Signal Locking (pending)
- Task 25: 3-Layer Signal Deduplication (pending)
- Task 27: Crash Recovery Manager (done)

---

## Development Commands

### Portfolio Manager (Python Backend)

```bash
cd portfolio_manager

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
./run_tests.sh                    # Full test suite with coverage
pytest tests/unit/ -v             # Unit tests only
pytest tests/integration/ -v      # Integration tests only
pytest tests/unit/test_position_sizer.py -v  # Single test file
pytest -k "test_pyramid" -v       # Tests matching pattern

# Type checking
./scripts/typecheck.sh            # Gradual mypy (default)
./scripts/typecheck.sh --strict   # Strict mypy

# Pre-commit hooks
pre-commit install                # Install hooks
pre-commit run --all-files        # Run manually

# Start services (production)
./start_all.sh                    # Start OpenAlgo + Tunnel + PM
./start_all.sh --test-mode        # 1 lot only, logs calculated lots
./start_all.sh --silent           # No voice announcements
./start_all.sh status             # Check service status
./start_all.sh stop               # Stop all services

# Daily operations
./daily_startup.sh                # Standard daily start
./daily_startup.sh --sync         # Start + sync positions from broker
```

### Frontend (React Dashboard)

```bash
cd frontend

# Development
bun install                       # Install dependencies
bun run dev                       # Start dev server (Vite)
bun run build                     # Production build
bun run lint                      # ESLint
```

**Note:** Frontend was originally built with Lovable AI but is now running locally. The `Lovable/` folder contains historical prompts and documentation used to generate the initial frontend.

### Database Setup

```bash
cd portfolio_manager

# PostgreSQL setup (see DATABASE_SETUP.md)
psql -U pm_user -d portfolio_manager -f migrations/001_initial_schema.sql
psql -U pm_user -d portfolio_manager -f migrations/002_add_heartbeat_index.sql
psql -U pm_user -d portfolio_manager -f migrations/003_add_leadership_history.sql
# ... run all migrations in order

# Configure
cp database_config.json.example database_config.json
# Edit with your credentials
```

---

## Portfolio Manager Architecture

### Directory Structure

```
portfolio_manager/
├── core/                    # Business logic
│   ├── models.py           # Signal, Position, EODMonitorSignal dataclasses
│   ├── portfolio_state.py  # PortfolioStateManager - equity, positions
│   ├── position_sizer.py   # TomBassoPositionSizer - risk-based sizing
│   ├── pyramid_gate.py     # PyramidGateController - entry constraints
│   ├── stop_manager.py     # TomBassoStopManager - trailing stops
│   ├── webhook_parser.py   # Parse TradingView webhooks, duplicate detection
│   ├── order_executor.py   # SimpleLimitExecutor, SyntheticFuturesExecutor
│   ├── signal_validator.py # Validate signals before execution
│   ├── db_state_manager.py # PostgreSQL persistence (DatabaseStateManager)
│   ├── redis_coordinator.py # Leader election, distributed locks
│   ├── config.py           # PortfolioConfig, instrument configs
│   └── eod_*.py            # End-of-day execution
├── live/                    # Live trading components
│   ├── engine.py           # LiveTradingEngine - main orchestrator
│   ├── recovery.py         # CrashRecoveryManager
│   ├── rollover_*.py       # Contract rollover logic
│   └── expiry_utils.py     # Expiry date calculations
├── brokers/                 # Broker integrations
│   ├── factory.py          # Broker client factory
│   └── openalgo_client.py  # OpenAlgo API wrapper
├── backtest/                # Backtesting
│   ├── engine.py           # BacktestEngine
│   └── signal_loader.py    # Load signals from CSV
├── tests/
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── fixtures/           # Test data
├── migrations/              # PostgreSQL migrations (001-007)
└── portfolio_manager.py     # CLI entrypoint
```

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `LiveTradingEngine` | live/engine.py | Orchestrates live trading, processes webhooks |
| `PortfolioStateManager` | core/portfolio_state.py | Tracks positions, equity, margin |
| `TomBassoPositionSizer` | core/position_sizer.py | Risk-based position sizing |
| `PyramidGateController` | core/pyramid_gate.py | Validates pyramid entries |
| `DatabaseStateManager` | core/db_state_manager.py | PostgreSQL persistence |
| `RedisCoordinator` | core/redis_coordinator.py | Leader election, distributed locks |
| `CrashRecoveryManager` | live/recovery.py | State recovery on startup |

### Signal Flow

1. **TradingView** → Webhook to `/webhook` endpoint
2. **webhook_parser.py** → Parse JSON, check duplicates (memory cache)
3. **RedisCoordinator** → Acquire distributed lock (prevents cross-instance duplicates)
4. **signal_validator.py** → Validate signal sanity
5. **LiveTradingEngine** → Process signal type (ENTRY/PYRAMID/EXIT)
6. **position_sizer.py** → Calculate lot size based on risk %
7. **pyramid_gate.py** → Check if pyramid allowed (triple-constraint)
8. **order_executor.py** → Place order via OpenAlgo
9. **db_state_manager.py** → Persist state to PostgreSQL

### Database Schema

PostgreSQL with migrations in `portfolio_manager/migrations/`:
- `portfolio_positions` - Active and historical positions (36 columns)
- `portfolio_state` - Single-row portfolio metrics
- `pyramiding_state` - Per-instrument pyramiding metadata
- `signal_log` - Signal audit trail with fingerprint deduplication
- `instance_metadata` - HA instance tracking, heartbeat
- `leadership_history` - Leader election audit trail
- `strategies` - Strategy-level P&L tracking

---

## High Availability (HA) System

### Architecture: Active-Active

**Signal Processing:** ALL instances process webhooks concurrently
- Load balancer distributes webhooks across all instances
- Redis distributed locks prevent duplicate processing
- No leader election needed for signals

**Leader Election:** ONLY for background tasks
- Rollover scheduler (hourly/daily)
- Signal log cleanup
- Statistics aggregation

**Failover:** <3 seconds
- If leader dies, another instance becomes leader automatically
- Signal processing continues uninterrupted

### Key HA Components

1. **RedisCoordinator** (`core/redis_coordinator.py`)
   - Leader election via `SET NX EX` (10s TTL)
   - Heartbeat renewal every 5s
   - Split-brain detection (compares Redis vs DB)
   - Auto-demote on conflict

2. **DatabaseStateManager** (`core/db_state_manager.py`)
   - Connection pooling with retry logic
   - Optimistic locking (version field)
   - L1 cache for hot data

3. **CrashRecoveryManager** (`live/recovery.py`)
   - Load open positions on startup
   - Restore pyramiding state
   - Validate consistency

---

## Pine Script Strategy Reference

### Production Strategies

| File | Version | Instrument |
|------|---------|------------|
| `BankNifty_TF_V8.0.pine` | v8.0 | Bank Nifty | **Current production** |
| `GoldMini_TF_V8.0.pine` | v8.0 | Gold Mini | **Current production** |

### 7-Condition Entry System

ALL conditions must be TRUE simultaneously:
1. RSI(6) > 70 - Momentum confirmation
2. Close > EMA(200) - Long-term uptrend
3. Close > Donchian Channel Upper(20) - Breakout
4. ADX(30) < threshold - Low trend strength (allows new trend formation)
5. Efficiency Ratio > threshold - Clean price action
6. Close > SuperTrend(10, 1.5) - Bullish trend
7. NOT a Doji - Body > 10% of candle range

### Critical TradingView Settings

**Properties Tab:**
- Initial capital: 10000000 (₹1 crore)
- Pyramiding: 5 orders (6 total positions)
- Commission: 0.05%
- "On every tick": UNCHECKED

**Inputs Tab:** Refer to the strategy file's input defaults.

### Pine Script Gotchas

- `process_orders_on_close=TRUE` prevents repainting
- Donchian uses `high[1]` and `low[1]` to avoid lookahead bias
- Very few signals expected (5-15/year) - this is by design
- `strategy.equity` is per-chart only, not real portfolio equity

---

## Frontend Architecture

React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui

### Tech Stack
- **Build:** Vite
- **Styling:** TailwindCSS + shadcn/ui components
- **State:** React Query (@tanstack/react-query)
- **Charts:** Recharts
- **Forms:** React Hook Form + Zod

### Key Pages/Components

```
frontend/src/
├── pages/
│   ├── Dashboard.tsx       # Main dashboard with positions, P&L
│   ├── Operations.tsx      # Emergency controls, calendar
│   └── Index.tsx           # Landing page
├── components/
│   ├── dashboard/          # MetricCard, PositionCard, EquityChart, etc.
│   ├── operations/         # EmergencyControls, HolidayCalendar
│   └── ui/                 # shadcn/ui components
├── hooks/                  # React Query hooks for API calls
└── lib/                    # Utilities
```

### API Integration

Frontend calls Portfolio Manager's REST endpoints:
- `GET /health` - System health check
- `GET /positions` - Current positions
- `GET /signals` - Recent signals
- `POST /webhook` - Receive TradingView alerts
- `GET /db/status` - Database connection status

---

## Important Concepts

### Position Sizing Formula (Tom Basso)
```
lots = (equity_high × risk% / stop_distance / lot_size) × ER
```
- Uses equity high watermark (highest realized equity), not current equity
- Efficiency Ratio (ER) scales position by trend quality
- 3-constraint system: Risk, Volatility, Margin

### Pyramiding Safety (Triple-Constraint)
Before adding a pyramid position, ALL must pass:
1. **Margin check:** Required margin < Available margin
2. **Scaling:** Position size = Previous × 0.5 (geometric)
3. **Profitability:** Current position must be in profit
4. **ROC filter** (optional): 15-period ROC > threshold

### Synthetic Futures (Bank Nifty)
- ATM PE Sell + ATM CE Buy = Synthetic futures position
- Margin: ~₹2.7L per lot
- Executed via `SyntheticFuturesExecutor`

### Signal Deduplication (3-Layer)
1. **Memory:** Local LRU cache (fastest, single instance)
2. **Redis:** Distributed lock (cross-instance)
3. **Database:** `signal_log` with unique fingerprint constraint

---

## Quick Reference

### Ports
- OpenAlgo: 5000
- Portfolio Manager: 5002
- Frontend dev: 5173 (Vite default)

### Logs
- PM logs: `portfolio_manager/pm.log`
- OpenAlgo logs: `~/openalgo/log/openalgo.log`
- Tunnel logs: `portfolio_manager/.tunnel.log`

### Key Documentation Files
- `STRATEGY_LOGIC_SUMMARY.md` - Complete strategy requirements
- `portfolio_manager/PortfolioManager-HA-system.md` - HA architecture
- `portfolio_manager/DATABASE_SETUP.md` - PostgreSQL setup
- `portfolio_manager/PHASE1_IMPLEMENTATION_SUMMARY.md` - Phase 1 status
- `TROUBLESHOOTING_GUIDE.md` - Common issues

### Configuration Files
| File | Purpose |
|------|---------|
| `portfolio_manager/openalgo_config.json` | OpenAlgo API credentials, broker, execution mode |
| `portfolio_manager/db_config.json` | PostgreSQL connection settings |
| `portfolio_manager/redis_config.json` | Redis connection settings |
| `portfolio_manager/pytest.ini` | Pytest configuration |
| `portfolio_manager/pyproject.toml` | mypy settings, project metadata |
