# OpenAlgo Setup Quick Start

## Installation

### 1. Install OpenAlgo
```bash
git clone https://github.com/marketcalls/openalgo.git
cd openalgo
pip install uv
cp .sample.env .env
# Edit .env with broker credentials
uv run app.py
```

### 2. Install Bridge Dependencies
```bash
cd /path/to/ITJ-BN-Trending
pip install -r requirements_openalgo.txt
```

### 3. Configure Bridge
Edit `openalgo_config.json`:
- Add API key from OpenAlgo settings
- Set broker (zerodha/dhan)
- Start with execution_mode: "analyzer"

### 4. Start Bridge
```bash
python openalgo_bridge.py
```

## Files Needed

Due to file size limitations, please create these files manually:

1. **openalgo_bridge.py** - See implementation plan for full code
2. **trend_following_strategy_v6_signals.pine** - Modified version of v6 for signals only

## Key Changes from v6 Strategy

1. Pine Script generates alerts (no execution)
2. Python bridge calculates position sizing
3. OpenAlgo executes on Zerodha/Dhan
4. Synthetic futures (SELL PE + BUY CE)

## Critical Features

- Partial fill protection
- Market hours validation
- Duplicate signal rejection
- Position state persistence
- Exit uses entry strike

## Next Steps

See detailed implementation plan for complete code and architecture.


