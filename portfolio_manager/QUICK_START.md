# Quick Start Guide

## 1. Installation (2 minutes)

```bash
cd portfolio_manager
pip install -r requirements.txt
```

## 2. Verify Setup (30 seconds)

```bash
python verify_setup.py
```

Expected output:
```
✓ ALL CHECKS PASSED
```

## 3. Run Tests (1 minute)

```bash
./run_tests.sh
```

Expected: All tests pass

## 4. View Coverage (30 seconds)

```bash
open htmlcov/index.html
```

Expected: >80% coverage

## 5. Run Sample Backtest (1 minute)

```bash
# Create sample data directory
mkdir -p ../data

# Run with existing CSV (if available)
python portfolio_manager.py backtest \
  --gold ../Gold_Mini_Trend_Following.csv \
  --bn "../ITJ_BN_TrendFollowing v6.csv" \
  --capital 5000000
```

## Expected Results

```
==================================================
TOM BASSO PORTFOLIO BACKTEST
==================================================
Loaded 371 Gold signals
Loaded 925 Bank Nifty signals
Processed 1296 total signals

BACKTEST RESULTS
==================================================
Initial Capital: ₹50,00,000
Final Equity: ₹...
Total P&L: ₹...
Return: ...%

Statistics:
  signals_processed: 1296
  entries_executed: ...
  pyramids_executed: ...
==================================================
```

## Troubleshooting

### Import Errors

```bash
# Ensure you're in the right directory
cd portfolio_manager

# Check Python path
python -c "import sys; print(sys.path)"
```

### Test Failures

```bash
# Run specific failing test with details
pytest tests/unit/test_position_sizer.py::test_name -v -s

# Check logs
tail -f portfolio_manager.log
```

### Missing Dependencies

```bash
pip install -r requirements.txt --upgrade
```

## Next Steps

1. ✅ Setup complete
2. ✅ Tests passing
3. → **Enhance Pine Scripts** (add ATR, ER, STOP to comments)
4. → **Re-export from TradingView**
5. → **Run real backtest**
6. → **Deploy live**

