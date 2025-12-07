# Files to Share with Lovable AI

This document lists all files from the `portfolio_manager` codebase that should be shared with Lovable AI for context when generating the frontend portal.

## Priority Levels

- **ESSENTIAL**: Must share - core logic and data models
- **RECOMMENDED**: Should share - additional context and patterns
- **OPTIONAL**: Nice to have - documentation and examples

---

## ESSENTIAL Files (Share These First)

### Core Data Models and Configuration

| File | Lines | Purpose |
|------|-------|---------|
| `core/models.py` | ~560 | **CRITICAL** - All data models: Signal, Position, PortfolioState, InstrumentConfig, EODMonitorSignal, TomBassoConstraints, PyramidGateCheck |
| `core/config.py` | ~250 | Portfolio configuration, instrument settings, market hours, EOD settings |

### Database Schema

| File | Lines | Purpose |
|------|-------|---------|
| `migrations/001_initial_schema.sql` | ~200 | **CRITICAL** - PostgreSQL schema: portfolio_positions, portfolio_state, pyramiding_state, signal_log, instance_metadata |

### Broker Integration (Reference for Zerodha)

| File | Lines | Purpose |
|------|-------|---------|
| `brokers/openalgo_client.py` | ~280 | Current broker API interface - use as **reference pattern** for ZerodhaClient |
| `brokers/factory.py` | ~200 | Broker client factory pattern, AnalyzerBrokerWrapper |

### Main Application

| File | Lines | Purpose |
|------|-------|---------|
| `portfolio_manager.py` | ~935 | Main entry point, Flask webhook server, all REST endpoints |

### Dependencies

| File | Lines | Purpose |
|------|-------|---------|
| `requirements.txt` | ~30 | Python dependencies |

---

## RECOMMENDED Files (Additional Context)

### Core Trading Logic

| File | Lines | Purpose |
|------|-------|---------|
| `core/portfolio_state.py` | ~400 | Portfolio state management, equity tracking |
| `core/position_sizer.py` | ~200 | Tom Basso 3-constraint position sizing (Lot-R, Lot-V, Lot-M) |
| `core/pyramid_gate.py` | ~300 | Pyramid control logic (1R gate, portfolio gate, profit gate) |
| `core/stop_manager.py` | ~150 | ATR trailing stop management |
| `core/signal_validator.py` | ~400 | Signal validation logic |
| `core/webhook_parser.py` | ~250 | Webhook JSON parsing, duplicate detection |
| `core/db_state_manager.py` | ~760 | Database operations (PostgreSQL), connection pooling |
| `core/order_executor.py` | ~400 | Order execution strategies (simple limit, progressive) |

### Live Trading Engine

| File | Lines | Purpose |
|------|-------|---------|
| `live/engine.py` | ~1400 | Live trading engine - processes signals, executes trades |
| `live/rollover_scanner.py` | ~200 | Scans positions for rollover candidates |
| `live/rollover_executor.py` | ~300 | Executes position rollovers |
| `live/expiry_utils.py` | ~150 | Expiry date calculations |
| `live/recovery.py` | ~300 | Crash recovery manager |

### Configuration Examples

| File | Purpose |
|------|---------|
| `database_config.json.example` | Database connection config template |
| `openalgo_config.json.example` | Broker config template |
| `redis_config.json.example` | Redis HA config template |

---

## OPTIONAL Files (Documentation & Examples)

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | System overview and usage |
| `DATABASE_SETUP.md` | PostgreSQL setup instructions |
| `WEBHOOK_TESTING_GUIDE.md` | Testing webhook integration |
| `RUNBOOK.md` | Operations runbook |
| `PYRAMID_GATE_SYSTEM.md` | Detailed trading logic explanation |
| `QUICK_START.md` | Quick start guide |

### Test Fixtures (Example Data)

| File | Purpose |
|------|---------|
| `tests/fixtures/webhook_payloads.py` | Example webhook JSON payloads |
| `tests/fixtures/mock_signals.py` | Example signals for testing |
| `sample_webhook_payloads.json` | Sample webhook payloads |

---

## File Contents Quick Reference

### Key Exports from `core/models.py`:

```python
# Enums
class InstrumentType(Enum):
    GOLD_MINI = "GOLD_MINI"
    BANK_NIFTY = "BANK_NIFTY"

class SignalType(Enum):
    BASE_ENTRY = "BASE_ENTRY"
    PYRAMID = "PYRAMID"
    EXIT = "EXIT"
    EOD_MONITOR = "EOD_MONITOR"

class PositionLayer(Enum):
    BASE = "Long_1"
    PYR1 = "Long_2"
    # ... through Long_6

# Dataclasses
@dataclass
class InstrumentConfig: ...
@dataclass
class Signal: ...
@dataclass
class Position: ...
@dataclass
class PortfolioState: ...
@dataclass
class TomBassoConstraints: ...
@dataclass
class PyramidGateCheck: ...
@dataclass
class EODMonitorSignal: ...
```

### Key Configuration from `core/config.py`:

```python
# Bank Nifty Config
InstrumentConfig(
    lot_size=35,
    point_value=35.0,
    margin_per_lot=270000.0,
    max_pyramids=5
)

# Gold Mini Config  
InstrumentConfig(
    lot_size=100,
    point_value=10.0,
    margin_per_lot=105000.0,
    max_pyramids=3
)

# Portfolio Config
max_portfolio_risk_percent = 15.0  # Hard limit
pyramid_risk_block = 12.0  # Block pyramids at 12%
```

### Existing REST Endpoints in `portfolio_manager.py`:

```
POST /webhook          - TradingView webhook receiver
GET  /webhook/stats    - Webhook processing statistics
GET  /status           - Portfolio status
GET  /positions        - Open positions
GET  /db/status        - Database connection status
GET  /rollover/status  - Rollover status
GET  /rollover/scan    - Scan rollover candidates
POST /rollover/execute - Execute rollover
GET  /eod/status       - EOD execution status
GET  /health           - Health check
GET  /analyzer/orders  - Simulated orders (analyzer mode)
```

---

## How to Share Files with Lovable AI

### Option 1: Copy-Paste Essential Files

1. Open each ESSENTIAL file
2. Copy the entire contents
3. Paste into Lovable AI chat with filename header

Example format:
```
## File: core/models.py

[paste file contents here]

---

## File: core/config.py

[paste file contents here]
```

### Option 2: Create a Combined Context File

Run this command to create a single file with all essential code:

```bash
cd portfolio_manager

# Create combined file
cat > docs/lovable_ai/COMBINED_CONTEXT.txt << 'DELIMITER'
=== FILE: core/models.py ===
DELIMITER
cat core/models.py >> docs/lovable_ai/COMBINED_CONTEXT.txt

echo "" >> docs/lovable_ai/COMBINED_CONTEXT.txt
echo "=== FILE: core/config.py ===" >> docs/lovable_ai/COMBINED_CONTEXT.txt
cat core/config.py >> docs/lovable_ai/COMBINED_CONTEXT.txt

echo "" >> docs/lovable_ai/COMBINED_CONTEXT.txt
echo "=== FILE: migrations/001_initial_schema.sql ===" >> docs/lovable_ai/COMBINED_CONTEXT.txt
cat migrations/001_initial_schema.sql >> docs/lovable_ai/COMBINED_CONTEXT.txt

echo "" >> docs/lovable_ai/COMBINED_CONTEXT.txt
echo "=== FILE: brokers/openalgo_client.py ===" >> docs/lovable_ai/COMBINED_CONTEXT.txt
cat brokers/openalgo_client.py >> docs/lovable_ai/COMBINED_CONTEXT.txt

echo "" >> docs/lovable_ai/COMBINED_CONTEXT.txt
echo "=== FILE: requirements.txt ===" >> docs/lovable_ai/COMBINED_CONTEXT.txt
cat requirements.txt >> docs/lovable_ai/COMBINED_CONTEXT.txt
```

### Option 3: GitHub Repository Link

If your code is on GitHub, share the repository URL with Lovable AI and specify which files to read.

---

## File Locations Summary

```
portfolio_manager/
├── core/
│   ├── models.py              # ESSENTIAL
│   ├── config.py              # ESSENTIAL
│   ├── portfolio_state.py     # RECOMMENDED
│   ├── position_sizer.py      # RECOMMENDED
│   ├── pyramid_gate.py        # RECOMMENDED
│   ├── stop_manager.py        # RECOMMENDED
│   ├── signal_validator.py    # RECOMMENDED
│   ├── webhook_parser.py      # RECOMMENDED
│   ├── db_state_manager.py    # RECOMMENDED
│   └── order_executor.py      # RECOMMENDED
├── brokers/
│   ├── openalgo_client.py     # ESSENTIAL (reference)
│   └── factory.py             # RECOMMENDED
├── live/
│   ├── engine.py              # RECOMMENDED
│   ├── rollover_scanner.py    # RECOMMENDED
│   ├── rollover_executor.py   # RECOMMENDED
│   ├── expiry_utils.py        # OPTIONAL
│   └── recovery.py            # OPTIONAL
├── migrations/
│   └── 001_initial_schema.sql # ESSENTIAL
├── portfolio_manager.py       # ESSENTIAL
├── requirements.txt           # ESSENTIAL
├── README.md                  # OPTIONAL
└── *.json.example             # RECOMMENDED
```

---

## Total Lines by Priority

| Priority | Files | Total Lines |
|----------|-------|-------------|
| ESSENTIAL | 7 | ~2,500 |
| RECOMMENDED | 13 | ~4,500 |
| OPTIONAL | 10 | ~2,000 |
