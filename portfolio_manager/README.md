# Tom Basso Multi-Instrument Portfolio Manager

**Unified system for backtesting and live trading with portfolio-level risk management**

## Features

- ✅ **Tom Basso 3-Constraint Position Sizing** (Risk, Volatility, Margin)
- ✅ **Portfolio-level Risk Cap** (15% hard limit)
- ✅ **Cross-Instrument Management** (Gold Mini + Bank Nifty with shared capital)
- ✅ **Independent ATR Trailing Stops** (each position trails separately)
- ✅ **Pyramid Gate Control** (instrument + portfolio + profit gates)
- ✅ **Peel-Off Mechanism** (automatic position reduction)
- ✅ **Dual Mode Operation** (Same code for backtest and live trading)
- ✅ **Comprehensive Testing** (Unit + Integration + E2E tests)
- ✅ **Test Coverage Reports** (pytest-cov)

## Architecture

```
Portfolio Manager
├── core/                    # Shared logic (backtest + live)
│   ├── models.py           # Data models
│   ├── config.py           # Configuration
│   ├── position_sizer.py   # Tom Basso 3-constraint sizing
│   ├── portfolio_state.py  # Portfolio metrics tracking
│   ├── pyramid_gate.py     # Pyramid control logic
│   └── stop_manager.py     # ATR trailing stops
├── backtest/               # Backtest-specific
│   ├── signal_loader.py    # Parse TradingView CSVs
│   └── engine.py           # Backtest simulation
├── live/                   # Live trading-specific
│   └── engine.py           # Live execution via OpenAlgo
└── tests/                  # Test suite
    ├── unit/               # Unit tests
    ├── integration/        # Integration tests
    ├── fixtures/           # Test data
    └── test_end_to_end.py  # E2E tests
```

## Installation

### 1. Install Python Dependencies

```bash
cd portfolio_manager
pip install -r requirements.txt
```

### 2. Database Setup (Optional - for HA/Persistence)

For state persistence and high availability, PostgreSQL is required:

```bash
# Install PostgreSQL (see DATABASE_SETUP.md for details)
# Then run migrations:
psql -U pm_user -d portfolio_manager -f migrations/001_initial_schema.sql

# Create database config:
cp database_config.json.example database_config.json
# Edit database_config.json with your database credentials
```

See [DATABASE_SETUP.md](DATABASE_SETUP.md) for detailed setup instructions.

## Testing

### Run All Tests

```bash
./run_tests.sh
```

### Run Specific Test Suites

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_position_sizer.py -v

# With coverage
pytest tests/ --cov=core --cov-report=html
```

### View Coverage Report

```bash
open htmlcov/index.html
```

## Usage

### Backtest Mode

```bash
python portfolio_manager.py backtest \
  --gold signals/gold_mini.csv \
  --bn signals/bank_nifty.csv \
  --capital 5000000
```

### Live Trading Mode

**Without Database (In-Memory Only):**
```bash
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_OPENALGO_API_KEY \
  --capital 5000000
```

**With Database Persistence (Recommended for Production):**
```bash
python portfolio_manager.py live \
  --broker zerodha \
  --api-key YOUR_OPENALGO_API_KEY \
  --capital 5000000 \
  --db-config database_config.json \
  --db-env local
```

**Database Configuration:**
- `--db-config`: Path to database configuration JSON file
- `--db-env`: Environment to use (`local` or `production`)
- See [DATABASE_SETUP.md](DATABASE_SETUP.md) for setup instructions

#### Webhook Setup (TradingView Integration)

The portfolio manager receives signals via webhooks from TradingView. Since TradingView sends webhooks from their cloud servers, you need to expose your local server to the internet using a tunnel.

**Quick Setup:**

1. **Start portfolio manager** (Terminal 1):
   ```bash
   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
   ```

2. **Start tunnel** (Terminal 2):

   **Option A: Simple (No domain needed)** - Quick start:
   ```bash
   ./setup_tunnel_no_domain.sh
   ```
   Copy the URL shown - it stays the same as long as tunnel runs.

   **Option B: Permanent (Free domain)** - Recommended:
   ```bash
   ./setup_tunnel_with_free_domain.sh
   ```
   Follow the prompts to get a free domain and permanent URL.

3. **Get your webhook URL** from the tunnel output

4. **Configure TradingView alert**:
   - Webhook URL: `https://YOUR_URL/webhook`
   - Message: Leave as default (Pine Script sends JSON)

**Note:** If you see "No domains found" during setup, use Option A or see `NO_DOMAIN_SOLUTION.md`

**Detailed Guide:** See [`CLOUDFLARE_TUNNEL_GUIDE.md`](CLOUDFLARE_TUNNEL_GUIDE.md) for:
- Background tunnel setup
- Named tunnels (permanent URLs)
- Security (webhook secrets)
- Troubleshooting

## Testing Strategy

### 1. Unit Tests (✅ Implemented)

Test individual components in isolation:
- `test_position_sizer.py` - Tom Basso 3-constraint calculations
- `test_portfolio_state.py` - Portfolio metrics and equity tracking
- `test_stop_manager.py` - ATR trailing stop logic

### 2. Integration Tests (✅ Implemented)

Test components working together:
- `test_backtest_engine.py` - Complete backtest workflow
- `test_signal_loader.py` - CSV parsing and signal generation

### 3. End-to-End Tests (✅ Implemented)

Test complete system:
- `test_end_to_end.py` - Full backtest scenarios
- Portfolio risk cap enforcement
- Cross-instrument coordination

### 4. Test Fixtures (✅ Implemented)

Reusable test data:
- `mock_signals.py` - Sample signals and positions
- Mock CSV data
- Predefined signal sequences

## Test Coverage

Target coverage: >80% for all core modules

Run coverage report:
```bash
pytest tests/ --cov=core --cov=backtest --cov-report=term-missing
```

## Key Design Decisions

### 1. Same Logic for Backtest and Live

The core position sizing, risk management, and stop logic is **identical** in both modes.

Only difference:
- **Backtest:** Simulates trades in memory
- **Live:** Executes trades via OpenAlgo API

### 2. Test-Driven Development

Every module has corresponding unit tests written **first**, ensuring:
- Logic is correct before use
- Edge cases are handled
- Regressions are caught

### 3. Modular Design

Each component is independent and testable:
- Position sizer doesn't know about portfolio state
- Stop manager doesn't know about order execution
- Easy to modify one component without breaking others

## Validation Checklist

- [x] Unit tests for position sizer (13 tests)
- [x] Unit tests for portfolio state (10 tests)
- [x] Unit tests for stop manager (8 tests)
- [x] Integration tests for backtest engine (8 tests)
- [x] End-to-end workflow tests (3 tests)
- [x] Performance test (1000+ signals)
- [x] Test runner script
- [x] Coverage reporting setup

## Next Steps

1. **Run Tests:** `./run_tests.sh`
2. **Fix Any Failures:** Address issues found
3. **Enhance Comments in Pine Scripts:** Add ATR, ER, STOP to comments
4. **Re-export from TradingView:** Get enhanced CSV data
5. **Run Real Backtest:** Test with actual historical signals
6. **Deploy Live:** Connect to OpenAlgo and go live

## Documentation

- `README.md` - This file
- `TESTING_GUIDE.md` - Detailed testing procedures
- Code docstrings - Every function documented
- Test docstrings - Every test explained

## Support

For issues or questions, check:
- Test logs in `portfolio_manager.log`
- Test coverage report in `htmlcov/`
- Individual test failures with `pytest -v -s`

