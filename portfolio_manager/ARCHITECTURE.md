# Tom Basso Portfolio Manager - Architecture

## System Overview: Dumb Scout / Smart General (V9.0)

The system uses a **two-tier architecture** separating signal generation from execution authority:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TRADINGVIEW (The Scout)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────┐         ┌─────────────────────────┐            │
│  │   EOD Scout Indicator   │         │   Strategy V9           │            │
│  │   (Dumb - no state)     │         │   (Executor)            │            │
│  ├─────────────────────────┤         ├─────────────────────────┤            │
│  │ • Sends raw conditions  │         │ • Fires only on trade   │            │
│  │   every 15 seconds      │         │   execution             │            │
│  │ • NO position state     │         │ • BASE_ENTRY            │            │
│  │ • Throttled (varip)     │         │ • PYRAMID               │            │
│  │ • EOD window only       │         │ • EXIT                  │            │
│  └─────────────────────────┘         └─────────────────────────┘            │
│           │                                    │                             │
│           │ EOD_MONITOR                        │ Order Alerts                │
│           ▼                                    ▼                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               PYTHON PORTFOLIO MANAGER (The General - Smart)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────┐    ┌─────────────────────────┐                 │
│  │   PostgreSQL Database   │◄───│   EOD Monitor           │                 │
│  │   (Source of Truth)     │    │   + Executor            │                 │
│  ├─────────────────────────┤    ├─────────────────────────┤                 │
│  │ • Position TRUTH        │    │ • Receives signals      │                 │
│  │ • Pyramid count         │    │ • Overrides TradingView │                 │
│  │ • Entry prices          │    │ • Makes decisions       │                 │
│  │ • P&L tracking          │    │ • Places orders         │                 │
│  └─────────────────────────┘    └─────────────────────────┘                 │
│                                                                              │
│  KEY PRINCIPLE: PM is the AUTHORITY on position state                       │
│  TradingView is BLIND - it only sends raw indicator data                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture? (PR #4)

| Problem (V8) | Solution (V9) |
|--------------|---------------|
| TradingView position state can become stale | PM uses DATABASE as source of truth |
| EOD_MONITOR fired on every tick → rate limiting | Scout throttles to every 15 seconds |
| Single script handled both monitoring + execution | Separated into Indicator + Strategy |
| PM trusted TradingView's position_status | PM overrides with its own database |

### Component Roles

| Component | Type | Role | State Awareness |
|-----------|------|------|-----------------|
| EOD Scout | TradingView Indicator | Send raw conditions during EOD window | ❌ None (dumb) |
| Strategy V9 | TradingView Strategy | Fire alerts on trade execution | Own trades only |
| PM | Python Application | Make all decisions, execute orders | ✅ Full (database) |

---

## Legacy Overview (Pre-V9)

```
┌─────────────────────────────────────────────────────────────────┐
│                  TRADINGVIEW SIGNALS                            │
│  • Bank Nifty v6 (75-min chart)                                │
│  • Gold Mini v5.2 (60-min chart)                               │
└────────────────────┬────────────────────────────────────────────┘
                     │ CSV Export / Webhooks
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│           PORTFOLIO MANAGER (Unified Core)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Tom Basso Position Sizer                         │          │
│  │  • Lot-R (Risk-based)                            │          │
│  │  • Lot-V (Volatility-based)                      │          │
│  │  • Lot-M (Margin-based)                          │          │
│  │  • Final = FLOOR(MIN(R,V,M))                     │          │
│  └──────────────────────────────────────────────────┘          │
│                     ↓                                            │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Portfolio State Manager                          │          │
│  │  • Track all positions (Gold + BN)               │          │
│  │  • Calculate portfolio risk (15% cap)            │          │
│  │  • Calculate portfolio volatility (5% cap)       │          │
│  │  • Monitor margin utilization (60% max)          │          │
│  └──────────────────────────────────────────────────┘          │
│                     ↓                                            │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Pyramid Gate Controller                          │          │
│  │  • Instrument gate (1R + ATR spacing)            │          │
│  │  • Portfolio gate (15% risk, 5% vol)             │          │
│  │  • Profit gate (positive P&L)                    │          │
│  └──────────────────────────────────────────────────┘          │
│                     ↓                                            │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Tom Basso Stop Manager                           │          │
│  │  • Independent stops per position                │          │
│  │  • ATR trailing (ratchet up only)               │          │
│  │  • Stop hit detection                            │          │
│  └──────────────────────────────────────────────────┘          │
│                                                                 │
└───────────────┬─────────────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │                │
   BACKTEST         LIVE TRADING
        │                │
        ↓                ↓
┌────────────────┐  ┌────────────────┐
│ Simulate       │  │ Execute via    │
│ • Load CSV     │  │ • Webhooks     │
│ • Process      │  │ • OpenAlgo API │
│ • Generate     │  │ • Real orders  │
│   reports      │  │ • Track fills  │
└────────────────┘  └────────────────┘
```

## TradingView Scripts (V9.0)

### EOD Scout Indicators
| File | Instrument | EOD Window |
|------|------------|------------|
| `BankNifty_EOD_Scout_V1.0.pine` | Bank Nifty | 15:15-15:30 IST |
| `GoldMini_EOD_Scout_V1.0.pine` | Gold Mini | 23:15-23:30 IST |
| `SilverMini_EOD_Scout_V1.0.pine` | Silver Mini | 23:15-23:30 IST |

**Features:**
- Uses `indicator()` not `strategy()`
- `varip` throttling → fires every 15 seconds (prevents rate limiting)
- NO position_status field → PM is authority
- Sends raw conditions + indicators only

### V9 Strategies
| File | Instrument |
|------|------------|
| `BankNifty_TF_V9.0.pine` | Bank Nifty |
| `GoldMini_TF_V9.0.pine` | Gold Mini |
| `SilverMini_TF_V9.0.pine` | Silver Mini |

**V9 Changes from V8:**
- ❌ Removed EOD_MONITOR logic entirely (moved to Scout)
- ✅ Only fires ORDER FILL alerts (BASE_ENTRY/PYRAMID/EXIT)
- ✅ `barstate.isconfirmed` on entries (prevents duplicates)
- ✅ Fixed 50% lot_b for signal triggering (PM does geometric sizing)

---

## Core Components

### 1. Data Models (`core/models.py`)

**Purpose:** Type-safe data structures

**Key Classes:**
- `Signal` - TradingView signal with metadata
- `Position` - Active/closed position tracking
- `PortfolioState` - Complete portfolio snapshot
- `TomBassoConstraints` - 3-constraint sizing results
- `PyramidGateCheck` - Pyramid decision results

**Design:** Using `@dataclass` for immutability and type safety

---

### 2. Position Sizer (`core/position_sizer.py`)

**Purpose:** Calculate position size using Tom Basso's 3 constraints

**Methods:**
- `calculate_base_entry_size()` - For initial entries
- `calculate_pyramid_size()` - For pyramids (A, B, C constraints)
- `calculate_peel_off_size()` - Determine peel-off amount

**Formula:**
```
Lot-R = (Equity × Risk%) / (Entry - Stop) / Point_Value × ER
Lot-V = (Equity × Vol%) / (ATR × Point_Value)
Lot-M = Available_Margin / Margin_Per_Lot

Final_Lots = FLOOR(MIN(Lot-R, Lot-V, Lot-M))
```

**Test Coverage:** 15 unit tests, 90%+ coverage

---

### 3. Portfolio State Manager (`core/portfolio_state.py`)

**Purpose:** Track all positions and calculate portfolio metrics

**Responsibilities:**
- Maintain position inventory
- Calculate total risk across all positions
- Calculate total volatility exposure
- Track margin utilization
- Calculate equity (closed, open, blended)

**Key Method:**
```python
state = portfolio.get_current_state()
# Returns complete portfolio snapshot with all metrics
```

**Test Coverage:** 12 unit tests, 85%+ coverage

---

### 4. Pyramid Gate Controller (`core/pyramid_gate.py`)

**Purpose:** Decide if pyramiding is allowed

**3-Level Gate Check:**
1. **Instrument Gate:** Price > 1R AND ATR spacing met
2. **Portfolio Gate:** Risk < 12%, Volatility < 4%
3. **Profit Gate:** Instrument P&L > 0

**Returns:** `PyramidGateCheck` with detailed reasoning

**Test Coverage:** Integrated in backtest engine tests

---

### 5. Stop Manager (`core/stop_manager.py`)

**Purpose:** Manage independent ATR trailing stops

**Stop Formula:**
```
Initial_Stop = Entry - (Initial_ATR_Mult × ATR)
Trailing_Stop = Highest_Close - (Trailing_ATR_Mult × ATR)
Current_Stop = MAX(Current_Stop, Trailing_Stop)  // Ratchet up only
```

**Key Feature:** Each position trails independently

**Test Coverage:** 8 unit tests, 85%+ coverage

---

### 6. Backtest Engine (`backtest/engine.py`)

**Purpose:** Simulate portfolio trading with historical signals

**Process:**
1. Load signals from TradingView CSVs
2. Process chronologically
3. Apply Tom Basso sizing
4. Check portfolio gates
5. Track all metrics
6. Generate reports

**Output:** Complete backtest results with statistics

**Test Coverage:** 8 integration tests

---

### 7. Live Engine (`live/engine.py`)

**Purpose:** Execute real trades using SAME logic as backtest

**Key Difference:**
- Backtest: `_simulate_trade()`
- Live: `_execute_via_openalgo()`

**Everything else identical!**

**Test Coverage:** Integration tests with mock OpenAlgo client

---

### 8. Crash Recovery System (`live/recovery.py`)

**Purpose:** Restore portfolio state from PostgreSQL after crashes/restarts

**Recovery Flow:**
```
Startup → Fetch DB State → Reconstruct Objects → Validate → Ready
```

**Key Methods:**
- `recover_from_database()` - Main recovery entry point
- `_validate_recovered_state()` - Consistency checks (risk/margin)

**Error Codes:**
- `DB_UNAVAILABLE` - Database connection failed
- `DATA_CORRUPT` - Invalid position data
- `VALIDATION_FAILED` - Risk/margin mismatch (epsilon: 0.01₹)

**Validation Logic:**
```python
# Ensures saved state matches recalculated values
risk_diff = abs(db_risk - calculated_risk)
if risk_diff > 0.01:  # 1 paisa tolerance
    return VALIDATION_FAILED
```

**HA Integration:** Updates coordinator status during recovery phases

**Test Coverage:** Performance tests show 3-7ms recovery for 10-50 positions

---

## Data Flow

### Backtest Mode

```
CSV Files
    ↓
Signal Loader (parse enhanced comments)
    ↓
Merged Signal List (chronological)
    ↓
FOR EACH Signal:
    ├─→ Calculate Position Size (Tom Basso 3-constraint)
    ├─→ Check Portfolio Gates (15% risk cap)
    ├─→ Simulate Trade (update portfolio state)
    ├─→ Update Stops (ATR trailing)
    └─→ Check Stop Hits (exit if triggered)
    ↓
Final Results + Reports
```

### Live Mode

```
TradingView Webhook
    ↓
Flask Endpoint (/webhook)
    ↓
Parse Signal JSON
    ↓
FOR EACH Signal:
    ├─→ Calculate Position Size (SAME logic as backtest)
    ├─→ Check Portfolio Gates (SAME logic as backtest)
    ├─→ Execute via OpenAlgo (DIFFERENT: real orders)
    ├─→ Update Stops (SAME logic as backtest)
    └─→ Monitor & Exit (SAME logic as backtest)
```

## Testing Architecture

```
Test Suite (42 tests)
├── Unit Tests (31 tests)
│   ├── test_position_sizer.py (15 tests)
│   │   • Test each constraint independently
│   │   • Test MIN logic
│   │   • Test edge cases (zero equity, invalid stops)
│   │   • Test pyramid constraints
│   │   • Test peel-off calculations
│   │
│   ├── test_portfolio_state.py (12 tests)
│   │   • Test risk aggregation
│   │   • Test equity calculations
│   │   • Test margin tracking
│   │   • Test portfolio gates
│   │
│   └── test_stop_manager.py (8 tests)
│       • Test initial stop calc
│       • Test trailing logic
│       • Test ratchet effect
│       • Test stop hit detection
│
├── Integration Tests (8 tests)
│   └── test_backtest_engine.py
│       • Test signal processing
│       • Test portfolio gates in action
│       • Test complete workflows
│
└── End-to-End Tests (3 tests)
    └── test_end_to_end.py
        • Full backtest scenarios
        • Risk cap enforcement
        • Multi-instrument coordination
```

## Code Quality Measures

### 1. Type Safety
- All models use `@dataclass`
- Type hints on all function signatures
- Enum for constants (InstrumentType, SignalType)

### 2. Error Handling
- Input validation in Signal creation
- Graceful handling of invalid data
- Comprehensive logging at all levels

### 3. Testability
- Dependency injection (pass configs, clients)
- Mock-friendly interfaces
- No global state
- Pure functions where possible

### 4. Documentation
- Module-level docstrings
- Class docstrings
- Method docstrings with Args/Returns
- Inline comments for complex logic

### 5. Logging
- DEBUG: Detailed calculations
- INFO: Important events (entries, exits)
- WARNING: Blocked trades, issues
- ERROR: Failures

## Key Design Principles

### 1. Single Responsibility
Each module has ONE clear purpose:
- Position sizer → Calculate lots
- Portfolio state → Track metrics
- Stop manager → Manage stops
- Engines → Orchestrate workflow

### 2. Open/Closed Principle
Easy to extend without modifying:
- Add new instrument: Just add config
- Add new constraint: Extend sizer
- Add new gate: Extend gate controller

### 3. Dependency Injection
Components don't create dependencies:
```python
# Good
engine = BacktestEngine(portfolio_manager, stop_manager)

# Bad
class BacktestEngine:
    def __init__(self):
        self.portfolio = PortfolioManager()  # Hard-coded!
```

### 4. Test-Driven Development
Tests written BEFORE implementation:
- Defines expected behavior
- Ensures testability
- Catches regressions

## Performance Considerations

### Backtest Performance
- **Expected:** 1000 signals in <10 seconds
- **Bottleneck:** CSV parsing (use pandas)
- **Optimization:** Vectorize where possible

### Live Performance
- **Expected:** Process webhook in <100ms
- **Bottleneck:** OpenAlgo API calls
- **Optimization:** Async execution (future)

## Extensibility

### Adding New Instrument

```python
# 1. Add to models.py
class InstrumentType(Enum):
    GOLD_MINI = "GOLD_MINI"
    BANK_NIFTY = "BANK_NIFTY"
    NIFTY_50 = "NIFTY_50"  # NEW

# 2. Add config in config.py
INSTRUMENT_CONFIGS[InstrumentType.NIFTY_50] = InstrumentConfig(...)

# 3. That's it! Rest is automatic
```

### Adding New Constraint

```python
# In position_sizer.py
def calculate_base_entry_size(...):
    lot_r = ...
    lot_v = ...
    lot_m = ...
    lot_d = ...  # NEW: Drawdown-based constraint

    final = min(lot_r, lot_v, lot_m, lot_d)  # Add to MIN
```

## Deployment

### Development Environment
```bash
cd portfolio_manager
pip install -r requirements.txt
python verify_setup.py
./run_tests.sh
```

### Backtest Environment
```bash
python portfolio_manager.py backtest \
  --gold ../data/gold.csv \
  --bn ../data/bn.csv \
  --capital 5000000
```

### Live Environment
```bash
python portfolio_manager.py live \
  --broker zerodha \
  --api-key $OPENALGO_KEY \
  --capital 5000000
```

## Monitoring

### Backtest Metrics
- Initial/Final equity
- Total P&L and return %
- Entries/Pyramids executed vs blocked
- Max portfolio risk reached
- Max positions held simultaneously

### Live Metrics
- Real-time portfolio risk %
- Current positions
- Open P&L
- Orders placed vs failed
- API response times

## Security Considerations

### Backtest Mode
- Read-only file access
- No network calls
- Safe to run on any machine

### Live Mode
- API keys in environment variables
- HTTPS for OpenAlgo communication
- Order validation before execution
- Emergency stop mechanism

## Future Enhancements

1. **Advanced Reporting**
   - Equity curve charts
   - Drawdown analysis
   - Sharpe ratio calculation
   - Monte Carlo simulation

2. **Optimization Engine**
   - Parameter optimization
   - Walk-forward analysis
   - Genetic algorithms

3. **Real-Time Dashboard**
   - Web UI for monitoring
   - Real-time position updates
   - Alert notifications

4. **Multi-Strategy Support**
   - Multiple strategies per instrument
   - Strategy allocation logic
   - Strategy correlation analysis
