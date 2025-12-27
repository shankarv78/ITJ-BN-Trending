# EOD Monitor Implementation in Portfolio Manager - Brainstorm

**Date:** 2025-12-27
**Status:** Brainstorm / Architecture Review
**Context:** Investigating whether EOD monitoring can be moved entirely to PM, removing TradingView dependency

---

## Current Architecture

```
TradingView (Pine Script)              Portfolio Manager (Python)
┌────────────────────────────┐         ┌────────────────────────────┐
│  Calculates ALL indicators │         │  Receives signals via      │
│  - RSI(6)                  │         │  webhook JSON              │
│  - EMA(200)                │  ─────▶ │                            │
│  - Donchian(20)            │  webhook│  Currently NO indicator    │
│  - ADX(30)                 │         │  calculation capability    │
│  - ER(3)                   │         │                            │
│  - SuperTrend(10, 1.5)     │         │  Only gets:                │
│  - ATR(10)                 │         │  - LTP quotes (OpenAlgo)   │
│  - ROC(15)                 │         │  - Position sizing         │
│  - Doji detection          │         │  - Order execution         │
└────────────────────────────┘         └────────────────────────────┘
```

**The Problem:**
- EOD_MONITOR alerts only fire at bar close (23:55) due to `calc_on_every_tick=false`
- Even with fix, depends on TradingView webhook reliability
- PM has no fallback if TradingView fails during critical EOD window

---

## What Would PM Need to Calculate Indicators Itself?

### 1. Required Indicators (Bank Nifty / Gold Mini)

| Indicator | Parameters | Lookback Required |
|-----------|------------|-------------------|
| RSI | Period: 6 | 7 bars minimum |
| EMA | Period: 200 | 200+ bars for stability |
| Donchian Channel | Period: 20 | 21 bars (uses [1] offset) |
| ADX | Period: 30 | 60+ bars for DMI smoothing |
| Efficiency Ratio | Period: 3 | 4 bars |
| SuperTrend | Period: 10, Mult: 1.5 | 10+ bars |
| ATR | Period: 10 | 10 bars |
| ROC | Period: 15 | 16 bars |
| Doji Detection | Body/Range < 0.1 | 1 bar (OHLC) |

**Minimum data requirement:** ~250 candles of OHLC data for EMA(200) + buffer

### 2. Required Market Data

For each instrument (Bank Nifty, Gold Mini, Copper, Silver Mini):
- **OHLC data:** Open, High, Low, Close for each candle
- **Timeframe:** 75-min (Bank Nifty) or 1-hour (MCX commodities)
- **Refresh rate:** Real-time during EOD window (every 1-5 seconds)

### 3. Current Data Sources Analysis

#### OpenAlgo API (Current)
```python
# What OpenAlgo provides:
client.get_quote(symbol)  # Returns: ltp, bid, ask, volume, etc.

# What OpenAlgo does NOT provide:
# - Historical OHLC data
# - Candle data (75-min, 1-hour, etc.)
# - No historical endpoint in API docs
```

**Verdict:** OpenAlgo is insufficient for indicator calculation - only provides current quotes.

#### Alternative Data Sources

| Source | Historical OHLC | Real-time | Cost | Notes |
|--------|-----------------|-----------|------|-------|
| **Zerodha KiteConnect** | Yes (chart_data API) | Yes | ₹2000/month | Already have Zerodha account |
| **Shoonya API (Finvasia)** | Yes | Yes | Free | Would need second account |
| **NSE/MCX Direct** | Yes (bhavcopy) | No | Free | End-of-day only |
| **TradingView Data Export** | Yes | No | Manual | Could pre-cache on startup |
| **Yahoo Finance** | Limited | Limited | Free | May have delays, no MCX |
| **Alpha Vantage** | Yes | 5-min delay | Free tier | Limited Indian coverage |

---

## Option A: Full PM-Based EOD Monitor

### Architecture
```
┌────────────────────────────────────────────────────────────────┐
│                     Portfolio Manager                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │   Data Fetcher   │  │  TA Calculator   │  │ EOD Monitor  │  │
│  │                  │  │                  │  │              │  │
│  │  KiteConnect or  │─▶│  pandas-ta or    │─▶│  Existing    │  │
│  │  Shoonya API     │  │  ta-lib wrapper  │  │  EOD logic   │  │
│  │                  │  │                  │  │              │  │
│  │  Fetches OHLC    │  │  RSI, EMA, ADX   │  │  Condition   │  │
│  │  every 5 sec     │  │  ER, ST, ATR...  │  │  evaluation  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

1. **Add Data Fetcher Module** (`core/market_data.py`)
   - Connect to KiteConnect or Shoonya
   - Fetch last 250 candles on startup
   - Append new candles as they form
   - Cache in memory with optional Redis persistence

2. **Add Technical Indicators Module** (`core/indicators.py`)
   - Use `pandas-ta` (pure Python, easy) or `ta-lib` (faster, C-based)
   - Implement all 9 indicators with matching parameters
   - Unit tests comparing against Pine Script values

3. **Modify EOD Monitor**
   - Remove dependency on webhook data for conditions
   - Fetch fresh OHLC + calculate indicators every 5 seconds
   - Keep webhook as backup/validation

### Pros
- **Full independence from TradingView** - No webhook delays/failures
- **Faster refresh** - Can poll every 1-5 seconds vs webhook latency
- **Better debugging** - All calculations visible in Python logs
- **Consistency** - Same codebase for live + backtest

### Cons
- **Additional API dependency** - KiteConnect costs ₹2000/month
- **Indicator parity risk** - Must exactly match Pine Script calculations
- **Complexity** - New code to maintain and test
- **Startup time** - Need to fetch 250 bars on startup
- **Second auth** - KiteConnect requires separate daily login

### Effort Estimate
- Data fetcher module: ~2-3 days
- Indicator module: ~3-4 days
- Integration + testing: ~2-3 days
- Pine Script parity tests: ~2-3 days
- **Total: ~10-15 days**

---

## Option B: Hybrid Approach (TradingView Primary, PM Fallback)

### Architecture
```
┌─────────────────────┐     ┌──────────────────────────────────────┐
│    TradingView      │     │          Portfolio Manager           │
│                     │     │  ┌─────────────────────────────────┐ │
│  EOD_MONITOR alerts │────▶│  │   Primary: Webhook Handler      │ │
│  (fix calc_on_tick) │     │  └─────────────────────────────────┘ │
│                     │     │               │                      │
└─────────────────────┘     │               ▼                      │
                            │  ┌─────────────────────────────────┐ │
                            │  │   Fallback: Simplified Monitor  │ │
                            │  │   - Uses last known conditions  │ │
                            │  │   - ST/Price crossover only     │ │
                            │  │   - Fetches LTP from OpenAlgo   │ │
                            │  └─────────────────────────────────┘ │
                            └──────────────────────────────────────┘
```

### Implementation
1. Fix Pine Script `calc_on_every_tick=true` (already investigated)
2. Add simple fallback in PM:
   - Track last known SuperTrend value from webhook
   - During EOD window, if no webhook received in 30 seconds
   - Use simple price vs SuperTrend comparison
   - Skip other conditions (already met if position exists)

### Pros
- **Minimal code change** - Just add fallback logic
- **No new dependencies** - Uses existing OpenAlgo quotes
- **Quick implementation** - 1-2 days

### Cons
- **Still depends on TradingView** for initial indicator values
- **Incomplete fallback** - Can't detect new condition changes
- **Only works for existing positions** (pyramids/exits)

---

## Option C: Pre-Market Data Cache

### Concept
TradingView exports historical data → PM caches on startup → PM calculates

### Implementation
1. **Daily pre-market export** (manual or automated):
   - Export last 250 bars from TradingView chart as CSV
   - Store in `data/historical/BANK_NIFTY.csv`

2. **PM startup**:
   - Load historical data from CSV
   - Calculate all indicators
   - During market hours, append new candles from:
     - OpenAlgo LTP → aggregate into OHLC
     - OR construct from position updates

3. **EOD Window**:
   - PM has full indicator state
   - No webhook dependency

### Pros
- **No additional API costs**
- **No second login required**
- **Full indicator calculation**

### Cons
- **Manual daily step** (unless automated)
- **Building candles from LTP** is imprecise
- **Still need real-time OHLC for accuracy**

---

## Option D: Shoonya/Finvasia as Data Provider

### Why Shoonya?
- Free API with historical data
- Supports NSE, NFO, MCX
- No monthly fees
- Can open free demat account just for data

### Implementation
1. Open Finvasia account (free)
2. Use `NorenRestApiPy` library
3. Fetch historical data on demand
4. Same indicator calculation as Option A

### Pros
- **Free data source**
- **Full historical OHLC**
- **Real-time data available**

### Cons
- **Second account to manage**
- **Second login required daily**
- **Less tested than KiteConnect**

---

## Technical Deep Dive: Indicator Calculation in Python

### Library Comparison

| Library | Speed | Installation | Pine Parity | Notes |
|---------|-------|--------------|-------------|-------|
| **pandas-ta** | Medium | `pip install pandas-ta` | Good | Pure Python, easy |
| **ta-lib** | Fast | Requires C lib | Good | Harder install |
| **custom** | Varies | None | Exact | Full control |

### Example: RSI Calculation

```python
# Pine Script (reference)
rsi = ta.rsi(close, 6)

# pandas-ta equivalent
import pandas_ta as ta
df['rsi'] = ta.rsi(df['close'], length=6)

# Custom (matching Pine exactly)
def rsi_pine_style(close: pd.Series, period: int = 6) -> pd.Series:
    """RSI calculation matching TradingView's ta.rsi()"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    # Pine uses Wilder's smoothing (RMA)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

### Critical: SuperTrend Implementation

SuperTrend is the most complex indicator and critical for exits:

```python
def supertrend(high, low, close, period=10, multiplier=1.5):
    """
    SuperTrend matching TradingView's ta.supertrend()

    Returns: (supertrend_value, direction)
    """
    atr = ta.atr(high, low, close, period)
    hl2 = (high + low) / 2

    # Basic bands
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    # Final bands with trend logic
    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    for i in range(1, len(close)):
        # Band clamping logic (matches Pine)
        if close.iloc[i-1] > upper_band.iloc[i-1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1  # Bullish
        elif close.iloc[i-1] < lower_band.iloc[i-1]:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1  # Bearish
        else:
            # Continue previous trend
            if direction.iloc[i-1] == 1:
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
            else:
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
            direction.iloc[i] = direction.iloc[i-1]

    return supertrend, direction
```

**WARNING:** SuperTrend is stateful - requires continuous calculation from historical data.

---

## Recommendation

### Short Term (This Week)
1. **Fix Pine Script** `calc_on_every_tick=true` - Low effort, immediate impact
2. **Add simple fallback** in PM using last known SuperTrend

### Medium Term (If TradingView proves unreliable)
1. **Option D: Shoonya for data** - Free, full capability
2. Implement indicator module with pandas-ta
3. Extensive testing against Pine Script values

### Long Term (Full Independence)
1. **Option A with KiteConnect** - Most reliable, worth the cost for ₹50L capital
2. Remove TradingView dependency entirely
3. Keep TradingView only for charting/visualization

---

## Key Questions to Resolve

1. **Is the Pine Script fix sufficient?** Test `calc_on_every_tick=true` first
2. **How often does TradingView webhook fail?** Track reliability metrics
3. **Is Shoonya data quality acceptable?** Compare against TradingView
4. **Can we tolerate ₹2000/month for KiteConnect?** Small cost vs ₹50L capital

---

## Appendix: Indicator Parameter Reference

From Pine Script analysis:

| Indicator | Parameters | Condition | Threshold |
|-----------|------------|-----------|-----------|
| RSI | Period: 6 | > threshold | 70 (BN), 70 (Gold) |
| EMA | Period: 200 | Close > EMA | - |
| Donchian | Period: 20, offset [1] | Close > DC_upper | - |
| ADX | Period: 30 | < threshold | 25 (BN), 20 (Gold) |
| ER | Period: 3, non-directional | > threshold | 0.8 |
| SuperTrend | Period: 10, Mult: 1.5 | Close > ST | - |
| ATR | Period: 10 | For sizing | - |
| ROC | Period: 15 | > threshold (optional) | 2% |
| Doji | Body/Range ratio | < threshold | 0.1 |

---

*Document created: 2025-12-27*
*Next review: After testing Pine Script fix*
