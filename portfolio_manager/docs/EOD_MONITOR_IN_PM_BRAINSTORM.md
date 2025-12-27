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

## Option E: Cloud Signal Generator (RECOMMENDED)

**Status:** SELECTED - User has paid KiteConnect subscription

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLOUD (AWS/GCP/DigitalOcean)                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    Signal Generator Service                            │  │
│  │                                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  │ KiteConnect  │  │  Indicator   │  │  Condition   │  │  Webhook  │  │  │
│  │  │  Data Feed   │─▶│  Calculator  │─▶│  Evaluator   │─▶│  Sender   │──┼──┼─┐
│  │  │              │  │              │  │              │  │           │  │  │ │
│  │  │ - Historical │  │ - RSI        │  │ - 7 conds    │  │ - JSON    │  │  │ │
│  │  │ - WebSocket  │  │ - EMA        │  │ - Entry/Exit │  │ - Retry   │  │  │ │
│  │  │ - 75m/1h TF  │  │ - SuperTrend │  │ - Pyramid    │  │ - Logging │  │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘  │  │ │
│  └───────────────────────────────────────────────────────────────────────┘  │ │
└─────────────────────────────────────────────────────────────────────────────┘ │
                                                                                │
     ┌──────────────────────────────────────────────────────────────────────────┘
     │  webhook (same format as TradingView)
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LOCAL (Your Machine)                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      Portfolio Manager (Existing)                      │  │
│  │                                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  │   Webhook    │  │  Position    │  │    Order     │  │  OpenAlgo │  │  │
│  │  │   Handler    │─▶│    Sizer     │─▶│   Executor   │─▶│   Client  │  │  │
│  │  │  (existing)  │  │  (existing)  │  │  (existing)  │  │ (existing)│  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

1. **Zero changes to PM** - Uses existing webhook format
2. **Cloud reliability** - 99.9% uptime vs local machine
3. **Redundancy** - Can run alongside TradingView
4. **Single source of truth** - Indicators calculated once
5. **Easier debugging** - Cloud logs, monitoring, alerts

### Signal Generator Service Components

```
signal_generator/
├── main.py                  # FastAPI app, health checks
├── config.py                # Instrument configs, thresholds
├── core/
│   ├── kite_client.py       # KiteConnect wrapper
│   ├── data_manager.py      # Historical + real-time OHLC
│   ├── indicators.py        # RSI, EMA, SuperTrend, etc.
│   ├── condition_checker.py # 7-condition evaluator
│   └── webhook_sender.py    # HTTP POST to PM
├── strategies/
│   ├── bank_nifty.py        # BN-specific params
│   └── gold_mini.py         # Gold-specific params
└── tests/
    ├── test_indicators.py   # Parity tests vs Pine
    └── test_conditions.py   # Condition logic tests
```

### Data Source Options: KiteConnect vs Dhan

**User has both KiteConnect and Dhan subscriptions!**

| Feature | KiteConnect | Dhan |
|---------|-------------|------|
| **Historical Data** | ✅ chart_data API | ✅ historical API |
| **WebSocket** | ✅ KiteTicker | ✅ DhanFeed |
| **75-min candles** | ❌ (need to aggregate) | ❌ (need to aggregate) |
| **60-min candles** | ✅ Native | ✅ Native |
| **Rate Limits** | 3 req/sec historical | 5 req/sec historical |
| **Python SDK** | `kiteconnect` | `dhanhq` |
| **MCX Support** | ✅ | ✅ |
| **Daily Login** | Required | Required |
| **Documentation** | Excellent | Good |

**Recommendation:** Use **Dhan** for data (slightly higher rate limits, modern API) or use both for redundancy.

### Dhan Integration

```python
from dhanhq import dhanhq

class DhanDataManager:
    """Manages historical and real-time data from Dhan"""

    def __init__(self, client_id: str, access_token: str):
        self.dhan = dhanhq(client_id, access_token)

    def get_historical_data(self, symbol: str, exchange: str,
                            from_date: str, to_date: str, interval: str = "60"):
        """
        Fetch historical OHLC data

        Args:
            symbol: Security ID (e.g., "25" for Bank Nifty FUT)
            exchange: "NSE_FNO" or "MCX"
            from_date: "2025-01-01" format
            to_date: "2025-12-27" format
            interval: "1", "5", "15", "25", "60" (minutes)
        """
        data = self.dhan.historical_minute_charts(
            security_id=symbol,
            exchange_segment=exchange,
            instrument_type="FUT",
            from_date=from_date,
            to_date=to_date
        )
        return pd.DataFrame(data['data'])

    def subscribe_realtime(self, instruments: list, callback):
        """Subscribe to real-time data via DhanFeed WebSocket"""
        # DhanFeed for real-time streaming
        from dhanhq import marketfeed
        feed = marketfeed.DhanFeed(
            client_id=self.client_id,
            access_token=self.access_token,
            instruments=instruments,
            on_message=callback
        )
        feed.connect()
```

### KiteConnect Integration

```python
from kiteconnect import KiteConnect, KiteTicker

class KiteDataManager:
    """Manages historical and real-time data from KiteConnect"""

    def __init__(self, api_key: str, access_token: str):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self.ticker = KiteTicker(api_key, access_token)

    def get_historical_data(self, instrument: str, timeframe: str, days: int = 30):
        """
        Fetch historical OHLC data

        Args:
            instrument: "BANKNIFTY" or "GOLDM"
            timeframe: "75minute" (BN) or "60minute" (MCX)
            days: Number of days of history (need ~15 for 250 bars of 75min)
        """
        # KiteConnect historical data API
        # Returns: [{'date': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}]
        instrument_token = self.get_instrument_token(instrument)
        from_date = datetime.now() - timedelta(days=days)
        to_date = datetime.now()

        data = self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=timeframe
        )
        return pd.DataFrame(data)

    def subscribe_realtime(self, instruments: list, callback):
        """Subscribe to real-time ticks via WebSocket"""
        tokens = [self.get_instrument_token(i) for i in instruments]
        self.ticker.on_ticks = callback
        self.ticker.subscribe(tokens)
        self.ticker.set_mode(self.ticker.MODE_FULL, tokens)
        self.ticker.connect(threaded=True)
```

### Webhook Format (Compatible with Existing PM)

```json
{
  "type": "EOD_MONITOR",
  "instrument": "BANK_NIFTY",
  "source": "kite_signal_generator",
  "timestamp": "2025-12-27T15:28:00+05:30",
  "price": 52150.50,
  "conditions": {
    "rsi_condition": true,
    "ema_condition": true,
    "dc_condition": true,
    "adx_condition": true,
    "er_condition": true,
    "st_condition": true,
    "not_doji": true
  },
  "indicators": {
    "rsi": 72.5,
    "ema": 51800.0,
    "dc_upper": 52000.0,
    "adx": 22.3,
    "er": 0.85,
    "supertrend": 51500.0,
    "atr": 350.0,
    "roc": 1.2
  },
  "position_status": {
    "in_position": true,
    "pyramid_count": 2
  }
}
```

### Cloud Deployment Options

| Platform | Cost/Month | Pros | Cons |
|----------|------------|------|------|
| **AWS EC2 t3.micro** | ~₹800 | Free tier eligible, reliable | Complex setup |
| **DigitalOcean Droplet** | ~₹400 | Simple, good docs | Less features |
| **Google Cloud e2-micro** | Free | Always free tier | Limited to 1 instance |
| **Railway.app** | ~₹400 | Easy deploy, auto-SSL | Less control |
| **Render.com** | Free (750h) | GitHub integration | Sleep on inactivity |

**Recommendation:** Start with DigitalOcean or Railway for simplicity.

### Authentication Flow

```
Daily Flow:
1. Morning: Login to Zerodha Kite (generates access_token)
2. Access token valid for 1 day
3. Signal generator uses token for data access
4. No execution happens in cloud - just data + signals

Options for token management:
A) Manual: Copy token to cloud config daily (simple)
B) Semi-auto: Use Zerodha's login URL, paste token via API
C) Full-auto: Selenium/Playwright for auto-login (complex, fragile)
```

### Redundancy: Run Both TradingView + Kite

```
┌──────────────────┐     ┌──────────────────┐
│    TradingView   │     │  Kite Signal Gen │
│  (Primary now)   │     │    (Cloud)       │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         │  webhook               │  webhook
         ▼                        ▼
     ┌───────────────────────────────────────┐
     │         Portfolio Manager              │
     │                                        │
     │  Signal Deduplication (existing):      │
     │  - Memory LRU cache                    │
     │  - Redis distributed lock              │
     │  - DB fingerprint unique constraint    │
     │                                        │
     │  First signal wins, duplicates ignored │
     └───────────────────────────────────────┘
```

**Benefit:** If TradingView fails, Kite signal generator provides backup.

### Implementation Plan

#### Phase 1: Core Signal Generator (3-4 days)
- [ ] KiteConnect client wrapper
- [ ] Historical data fetcher
- [ ] OHLC candle aggregation (build 75m/60m from ticks)
- [ ] pandas-ta indicator calculations
- [ ] Unit tests for indicator parity

#### Phase 2: Condition Evaluation (2 days)
- [ ] 7-condition checker matching Pine Script
- [ ] Entry/Exit/Pyramid signal generation
- [ ] EOD window detection

#### Phase 3: Webhook & Deployment (2-3 days)
- [ ] Webhook sender with retry logic
- [ ] FastAPI health endpoints
- [ ] Docker container
- [ ] Cloud deployment (DigitalOcean/Railway)
- [ ] Monitoring & alerts

#### Phase 4: Testing & Go-Live (2-3 days)
- [ ] Paper trading mode (log signals, don't send)
- [ ] Parallel run with TradingView
- [ ] Compare signals for discrepancies
- [ ] Gradual cutover

**Total: 9-12 days**

### Key Technical Challenges

1. **75-minute timeframe for Bank Nifty**
   - KiteConnect doesn't support 75-min directly
   - Solution: Fetch 15-min data, aggregate to 75-min
   - Must align with market hours (9:15 AM - 3:30 PM)

2. **MCX session handling**
   - MCX has day + evening sessions
   - Summer/Winter timing changes
   - Must handle session breaks correctly

3. **SuperTrend state persistence**
   - SuperTrend is stateful (direction persists)
   - Need Redis/file cache to survive restarts
   - Or recalculate from sufficient history

4. **KiteConnect rate limits**
   - Historical API: 3 requests/second
   - Real-time: Unlimited via WebSocket
   - Strategy: Fetch history once, then use WebSocket

### Dual-Source Architecture (Maximum Reliability)

Since you have both KiteConnect and Dhan, we can implement failover:

```
┌────────────────────────────────────────────────────────────┐
│                Signal Generator Service                     │
│                                                             │
│  ┌─────────────┐     ┌─────────────┐                       │
│  │    Dhan     │     │ KiteConnect │                       │
│  │  (Primary)  │     │  (Backup)   │                       │
│  └──────┬──────┘     └──────┬──────┘                       │
│         │                   │                              │
│         ▼                   ▼                              │
│  ┌──────────────────────────────────────────────────┐     │
│  │           Data Manager (Failover Logic)          │     │
│  │                                                  │     │
│  │  1. Try Dhan first (higher rate limits)          │     │
│  │  2. If Dhan fails → fallback to KiteConnect      │     │
│  │  3. Cross-validate on startup (both sources)     │     │
│  │  4. Alert if sources diverge > 0.1%              │     │
│  └──────────────────────────────────────────────────┘     │
│                           │                                │
│                           ▼                                │
│               ┌─────────────────────┐                      │
│               │ Indicator Calculator │                      │
│               └─────────────────────┘                      │
└────────────────────────────────────────────────────────────┘
```

**Benefits:**
- Zero downtime if one broker API is down
- Cross-validation catches data errors
- Can switch primary based on performance

### Cost Analysis

| Item | Monthly Cost | Notes |
|------|-------------|-------|
| KiteConnect API | ₹2000 | Already paid |
| Dhan API | ₹0-500 | Check your plan |
| Cloud hosting | ₹400-800 | DigitalOcean/Railway |
| **Total** | ₹2400-3300 | |

**ROI:** For ₹50L capital, this is ~0.06% - trivial cost for reliability.

### Why Cloud + Webhook is Better Than Embedded

| Aspect | Cloud Signal Gen + Webhook | Embedded in PM |
|--------|---------------------------|----------------|
| **PM Changes** | Zero | Significant |
| **Deployment** | Independent | Coupled |
| **Testing** | Isolated | Complex |
| **Failure isolation** | Separate | Cascading |
| **Scaling** | Easy (multiple instances) | Hard |
| **Monitoring** | Cloud tools | Custom |

**Verdict:** Cloud with webhook is the cleaner architecture.

---

## Updated Recommendation

### Immediate (This Week)
1. ~~Fix Pine Script `calc_on_every_tick=true`~~ (still useful as backup)
2. **Start building Cloud Signal Generator** (Option E)

### Week 1-2
- Complete Phase 1 + 2 (Core + Conditions)
- Deploy to cloud in paper mode

### Week 3
- Parallel run with TradingView
- Validate signal parity
- Go live with redundant setup

### Long Term
- Phase out TradingView dependency
- Keep TradingView for charting only
- All signals from Kite Signal Generator

---

---

## Mission-Critical EOD System Requirements

**Added: 2025-12-27**
**Priority: HIGHEST - ₹50L capital at risk**

### Core Requirements

1. **Multi-Asset Parallel Monitoring** - All 4 instruments simultaneously
2. **PM Position Sync** - Signal generator must know open positions
3. **Parallel Order Execution** - Handle multiple signals at once
4. **30-Second Hard Deadline** - All orders placed + tracked before close
5. **Fail-Safe Design** - Mission-critical, zero tolerance for failures

---

## Revised Architecture: Mission-Critical EOD System

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CLOUD - EOD Signal Generator (Mission Critical)               │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PARALLEL INSTRUMENT MONITORS                             │ │
│  │                                                                             │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │ │
│  │  │ Bank Nifty  │ │ Gold Mini   │ │   Copper    │ │ Silver Mini │          │ │
│  │  │  Monitor    │ │  Monitor    │ │  Monitor    │ │  Monitor    │          │ │
│  │  │  Thread     │ │  Thread     │ │  Thread     │ │  Thread     │          │ │
│  │  │             │ │             │ │             │ │             │          │ │
│  │  │ - WebSocket │ │ - WebSocket │ │ - WebSocket │ │ - WebSocket │          │ │
│  │  │ - Indicators│ │ - Indicators│ │ - Indicators│ │ - Indicators│          │ │
│  │  │ - Conditions│ │ - Conditions│ │ - Conditions│ │ - Conditions│          │ │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘          │ │
│  │         │               │               │               │                  │ │
│  │         └───────────────┴───────┬───────┴───────────────┘                  │ │
│  │                                 │                                           │ │
│  │                                 ▼                                           │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    SIGNAL COORDINATOR                                 │  │ │
│  │  │                                                                       │  │ │
│  │  │  • Aggregates signals from all monitors                              │  │ │
│  │  │  • Queries PM for current positions (REST API)                       │  │ │
│  │  │  • Determines signal type: ENTRY / PYRAMID / EXIT                    │  │ │
│  │  │  • Batches multiple signals into single webhook                      │  │ │
│  │  │  • Handles priority (EXIT > PYRAMID > ENTRY)                         │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                             │
│                                    │ BATCH WEBHOOK (all instruments)             │
│                                    ▼                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │  POST /webhook/eod_batch
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  LOCAL - Portfolio Manager (Parallel Execution)                  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    EOD BATCH EXECUTOR (NEW)                                 │ │
│  │                                                                             │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │                   PARALLEL ORDER THREADS                             │   │ │
│  │  │                                                                      │   │ │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │ │
│  │  │  │ BN Order │  │Gold Order│  │ Cu Order │  │ Ag Order │            │   │ │
│  │  │  │ Executor │  │ Executor │  │ Executor │  │ Executor │            │   │ │
│  │  │  │          │  │          │  │          │  │          │            │   │ │
│  │  │  │ Place    │  │ Place    │  │ Place    │  │ Place    │            │   │ │
│  │  │  │ Track    │  │ Track    │  │ Track    │  │ Track    │            │   │ │
│  │  │  │ Fallback │  │ Fallback │  │ Fallback │  │ Fallback │            │   │ │
│  │  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │   │ │
│  │  │       │             │             │             │                   │   │ │
│  │  │       └─────────────┴──────┬──────┴─────────────┘                   │   │ │
│  │  │                            │                                        │   │ │
│  │  │                            ▼                                        │   │ │
│  │  │  ┌─────────────────────────────────────────────────────────────┐   │   │ │
│  │  │  │              EXECUTION RESULT AGGREGATOR                    │   │   │ │
│  │  │  │  • Wait for all threads (with timeout)                      │   │   │ │
│  │  │  │  • Report success/failure per instrument                    │   │   │ │
│  │  │  │  • Trigger emergency fallback if any fail                   │   │   │ │
│  │  │  └─────────────────────────────────────────────────────────────┘   │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Signal Generator: Parallel Monitoring Design

### Thread Architecture

```python
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, time
import httpx

@dataclass
class InstrumentConfig:
    name: str                    # "BANK_NIFTY", "GOLD_MINI", etc.
    exchange: str                # "NFO", "MCX"
    timeframe_minutes: int       # 75 for BN, 60 for MCX
    market_close: time           # 15:30 for BN, 23:30/23:55 for MCX
    eod_window_minutes: int      # 5 minutes before close
    indicator_params: dict       # RSI period, ADX threshold, etc.

@dataclass
class InstrumentState:
    """Real-time state for each instrument"""
    name: str
    last_price: float
    indicators: dict             # RSI, EMA, SuperTrend, etc.
    conditions: dict             # 7 conditions (bool)
    position_from_pm: Optional[dict]  # Synced from PM
    last_update: datetime
    is_eod_window: bool
    signal_pending: Optional[str]  # "ENTRY", "PYRAMID", "EXIT", None


class ParallelInstrumentMonitor:
    """
    Monitors all instruments in parallel threads.
    Each instrument has its own:
    - WebSocket connection for real-time data
    - Indicator calculator
    - Condition evaluator
    - State tracker
    """

    def __init__(self, pm_url: str, instruments: list[InstrumentConfig]):
        self.pm_url = pm_url
        self.instruments = {i.name: i for i in instruments}
        self.states: Dict[str, InstrumentState] = {}
        self.executor = ThreadPoolExecutor(max_workers=len(instruments))
        self.lock = threading.Lock()

    async def start_monitoring(self):
        """Start parallel monitoring for all instruments"""
        tasks = []
        for name, config in self.instruments.items():
            task = asyncio.create_task(self._monitor_instrument(config))
            tasks.append(task)

        # Also start position sync task
        tasks.append(asyncio.create_task(self._sync_positions_loop()))

        # Also start signal coordinator
        tasks.append(asyncio.create_task(self._signal_coordinator_loop()))

        await asyncio.gather(*tasks)

    async def _monitor_instrument(self, config: InstrumentConfig):
        """Monitor single instrument - runs in its own coroutine"""
        while True:
            try:
                # 1. Receive tick from WebSocket
                tick = await self._get_next_tick(config.name)

                # 2. Update OHLC candle
                candle = self._update_candle(config.name, tick)

                # 3. Recalculate indicators on candle close or during EOD
                if candle.is_closed or self._is_eod_window(config):
                    indicators = self._calculate_indicators(config.name)
                    conditions = self._evaluate_conditions(config.name, indicators)

                    # 4. Update state (thread-safe)
                    with self.lock:
                        self.states[config.name] = InstrumentState(
                            name=config.name,
                            last_price=tick.ltp,
                            indicators=indicators,
                            conditions=conditions,
                            position_from_pm=self.states.get(config.name, {}).get('position_from_pm'),
                            last_update=datetime.now(),
                            is_eod_window=self._is_eod_window(config),
                            signal_pending=self._determine_signal(config.name, conditions)
                        )

            except Exception as e:
                logger.error(f"Error monitoring {config.name}: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

    async def _sync_positions_loop(self):
        """Sync positions from PM every 5 seconds"""
        while True:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.pm_url}/api/positions",
                        timeout=5.0
                    )
                    positions = response.json()

                    with self.lock:
                        for pos in positions:
                            instrument = pos['instrument']
                            if instrument in self.states:
                                self.states[instrument].position_from_pm = pos

            except Exception as e:
                logger.error(f"Failed to sync positions from PM: {e}")

            await asyncio.sleep(5)

    async def _signal_coordinator_loop(self):
        """
        Coordinates signals across all instruments.
        Runs every second during EOD window.
        """
        while True:
            signals_to_send = []

            with self.lock:
                for name, state in self.states.items():
                    if state.is_eod_window and state.signal_pending:
                        signals_to_send.append({
                            'instrument': name,
                            'type': state.signal_pending,
                            'price': state.last_price,
                            'conditions': state.conditions,
                            'indicators': state.indicators,
                            'position': state.position_from_pm
                        })

            if signals_to_send:
                await self._send_batch_webhook(signals_to_send)

            await asyncio.sleep(1)  # Check every second during EOD

    async def _send_batch_webhook(self, signals: list):
        """Send batch of signals to PM in single request"""
        payload = {
            'type': 'EOD_BATCH',
            'timestamp': datetime.now().isoformat(),
            'source': 'kite_signal_generator',
            'signals': signals
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.pm_url}/webhook/eod_batch",
                json=payload,
                timeout=10.0
            )
            if response.status_code != 200:
                logger.error(f"Batch webhook failed: {response.text}")
                # Trigger alert!
```

### PM Position Sync API (New Endpoint Needed)

```python
# portfolio_manager/live/engine.py - ADD THIS ENDPOINT

@app.get("/api/positions")
async def get_positions_for_eod():
    """
    Returns current positions for EOD Signal Generator sync.
    Called every 5 seconds during EOD window.
    """
    positions = []
    for instrument, state in portfolio_state.positions.items():
        positions.append({
            'instrument': instrument,
            'in_position': state.quantity > 0,
            'quantity': state.quantity,
            'pyramid_count': state.pyramid_count,
            'entry_price': state.entry_price,
            'current_stop': state.stop_price,
            'unrealized_pnl': state.unrealized_pnl,
            'last_pyramid_price': state.last_pyramid_price
        })
    return positions
```

---

## Portfolio Manager: Parallel Execution Design

### Current Problem

Current EOD executor handles ONE instrument at a time:
```python
# Current: Sequential (SLOW)
for signal in signals:
    place_order(signal)      # 2-3 seconds
    track_order(signal)      # 5-10 seconds
    # Total: 7-13 seconds per instrument
    # 4 instruments = 28-52 seconds = TOO SLOW!
```

### New Design: Parallel Execution

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict
import threading

@dataclass
class EODOrderResult:
    instrument: str
    success: bool
    order_id: Optional[str]
    fill_price: Optional[float]
    error: Optional[str]
    execution_time_ms: int


class ParallelEODExecutor:
    """
    Executes multiple EOD orders in parallel.
    Each instrument gets its own thread.
    30-second hard deadline enforced.
    """

    HARD_DEADLINE_SECONDS = 25  # Leave 5s buffer before close

    def __init__(self, broker_client, max_workers: int = 4):
        self.broker = broker_client
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.results: Dict[str, EODOrderResult] = {}
        self.lock = threading.Lock()

    def execute_batch(self, signals: List[dict]) -> Dict[str, EODOrderResult]:
        """
        Execute all signals in parallel with hard deadline.

        Args:
            signals: List of signal dicts from EOD Signal Generator

        Returns:
            Dict mapping instrument -> execution result
        """
        start_time = time.time()
        futures = {}

        # Submit all orders in parallel
        for signal in signals:
            future = self.executor.submit(
                self._execute_single_order,
                signal,
                start_time
            )
            futures[future] = signal['instrument']

        # Wait for all with timeout
        remaining_time = self.HARD_DEADLINE_SECONDS
        for future in as_completed(futures, timeout=remaining_time):
            instrument = futures[future]
            try:
                result = future.result()
                with self.lock:
                    self.results[instrument] = result
            except Exception as e:
                with self.lock:
                    self.results[instrument] = EODOrderResult(
                        instrument=instrument,
                        success=False,
                        order_id=None,
                        fill_price=None,
                        error=str(e),
                        execution_time_ms=int((time.time() - start_time) * 1000)
                    )

        # Check for any that didn't complete
        for future, instrument in futures.items():
            if instrument not in self.results:
                logger.critical(f"TIMEOUT: {instrument} order did not complete!")
                with self.lock:
                    self.results[instrument] = EODOrderResult(
                        instrument=instrument,
                        success=False,
                        order_id=None,
                        fill_price=None,
                        error="TIMEOUT - Hard deadline exceeded",
                        execution_time_ms=self.HARD_DEADLINE_SECONDS * 1000
                    )

        return self.results

    def _execute_single_order(self, signal: dict, batch_start: float) -> EODOrderResult:
        """
        Execute single order with aggressive timing.

        Timeline:
        - T+0s:   Calculate position size
        - T+1s:   Place limit order (LTP + buffer)
        - T+2-8s: Track order, modify price if needed
        - T+10s:  If not filled, convert to MARKET
        - T+12s:  Confirm fill
        """
        instrument = signal['instrument']
        start = time.time()

        try:
            # Phase 1: Position sizing (< 1 second)
            lots = self._calculate_lots(signal)
            if lots == 0:
                return EODOrderResult(
                    instrument=instrument,
                    success=True,
                    order_id=None,
                    fill_price=None,
                    error="Zero lots calculated",
                    execution_time_ms=int((time.time() - start) * 1000)
                )

            # Phase 2: Place limit order (< 2 seconds)
            ltp = signal['price']
            limit_price = ltp * 1.002 if signal['type'] != 'EXIT' else ltp * 0.998
            order_id = self.broker.place_order(
                instrument=instrument,
                action='BUY' if signal['type'] != 'EXIT' else 'SELL',
                quantity=lots,
                order_type='LIMIT',
                price=limit_price
            )

            # Phase 3: Track and modify (up to 8 seconds)
            filled = False
            for _ in range(8):  # 8 iterations, 1 second each
                time.sleep(1)
                status = self.broker.get_order_status(order_id)

                if status['status'] == 'COMPLETE':
                    filled = True
                    break
                elif status['status'] == 'REJECTED':
                    raise Exception(f"Order rejected: {status.get('message')}")

                # Modify price if not filling
                elapsed = time.time() - batch_start
                if elapsed > 10 and not filled:
                    # Getting close to deadline - be more aggressive
                    new_price = ltp * 1.005 if signal['type'] != 'EXIT' else ltp * 0.995
                    self.broker.modify_order(order_id, new_price)

            # Phase 4: Market fallback if needed
            if not filled:
                elapsed = time.time() - batch_start
                if elapsed < self.HARD_DEADLINE_SECONDS - 5:
                    # Cancel limit, place market
                    self.broker.cancel_order(order_id)
                    order_id = self.broker.place_order(
                        instrument=instrument,
                        action='BUY' if signal['type'] != 'EXIT' else 'SELL',
                        quantity=lots,
                        order_type='MARKET'
                    )
                    time.sleep(2)
                    status = self.broker.get_order_status(order_id)
                    filled = status['status'] == 'COMPLETE'

            # Get fill price
            fill_price = None
            if filled:
                fill_price = self.broker.get_trade_fill_price(order_id)

            return EODOrderResult(
                instrument=instrument,
                success=filled,
                order_id=order_id,
                fill_price=fill_price,
                error=None if filled else "Order not filled",
                execution_time_ms=int((time.time() - start) * 1000)
            )

        except Exception as e:
            logger.error(f"Error executing {instrument}: {e}")
            return EODOrderResult(
                instrument=instrument,
                success=False,
                order_id=None,
                fill_price=None,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000)
            )
```

### New Batch Webhook Endpoint

```python
# portfolio_manager/live/engine.py - ADD THIS ENDPOINT

@app.post("/webhook/eod_batch")
async def handle_eod_batch(request: Request):
    """
    Handle batch EOD signals from Signal Generator.
    Executes all orders in parallel.
    """
    try:
        payload = await request.json()

        if payload.get('type') != 'EOD_BATCH':
            return {"status": "error", "message": "Invalid batch type"}

        signals = payload.get('signals', [])
        if not signals:
            return {"status": "ok", "message": "No signals to process"}

        logger.info(f"Received EOD batch with {len(signals)} signals")

        # Execute in parallel
        executor = ParallelEODExecutor(broker_client)
        results = executor.execute_batch(signals)

        # Log results
        success_count = sum(1 for r in results.values() if r.success)
        logger.info(f"EOD batch complete: {success_count}/{len(signals)} successful")

        # Alert on failures
        for instrument, result in results.items():
            if not result.success:
                send_alert(f"EOD FAILURE: {instrument} - {result.error}")

        return {
            "status": "ok",
            "results": {k: asdict(v) for k, v in results.items()}
        }

    except Exception as e:
        logger.critical(f"EOD batch failed: {e}")
        send_alert(f"CRITICAL: EOD batch processing failed: {e}")
        return {"status": "error", "message": str(e)}
```

---

## Timing & Deadline Management

### EOD Timeline (All Instruments)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EOD EXECUTION TIMELINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BANK NIFTY (Close: 15:30 IST)                                              │
│  ├── 15:25:00  EOD window starts, Signal Gen monitors every tick            │
│  ├── 15:29:00  T-60s: Final condition check                                 │
│  ├── 15:29:30  T-30s: Signal Gen sends batch webhook                        │
│  ├── 15:29:32  PM receives, starts parallel execution                       │
│  ├── 15:29:35  All LIMIT orders placed (parallel)                           │
│  ├── 15:29:45  Track orders, modify prices if needed                        │
│  ├── 15:29:55  T-5s: MARKET fallback for unfilled                           │
│  └── 15:30:00  Market close - all orders must be complete                   │
│                                                                              │
│  MCX COMMODITIES (Close: 23:30 summer / 23:55 winter)                       │
│  ├── 23:25/23:50  EOD window starts                                         │
│  ├── 23:29/23:54  T-60s: Final condition check                              │
│  ├── 23:29:30/23:54:30  T-30s: Batch webhook                                │
│  └── 23:30/23:55  Market close                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Hard Deadline Enforcement

```python
class DeadlineEnforcer:
    """
    Ensures all operations complete before market close.
    Implements escalating urgency levels.
    """

    def __init__(self, market_close: datetime):
        self.market_close = market_close
        self.hard_deadline = market_close - timedelta(seconds=5)

    def time_remaining(self) -> float:
        """Seconds until hard deadline"""
        return (self.hard_deadline - datetime.now()).total_seconds()

    def urgency_level(self) -> str:
        """
        Returns urgency level for decision making:
        - NORMAL: > 60s remaining, use limit orders
        - ELEVATED: 30-60s remaining, aggressive limit prices
        - CRITICAL: 10-30s remaining, consider market orders
        - EMERGENCY: < 10s remaining, market orders only
        """
        remaining = self.time_remaining()
        if remaining > 60:
            return "NORMAL"
        elif remaining > 30:
            return "ELEVATED"
        elif remaining > 10:
            return "CRITICAL"
        else:
            return "EMERGENCY"

    def should_use_market_order(self) -> bool:
        return self.urgency_level() == "EMERGENCY"

    def should_skip_tracking(self) -> bool:
        """Skip detailed tracking if time critical"""
        return self.time_remaining() < 5
```

---

## Fail-Safe Mechanisms

### 1. Signal Generator Redundancy

```python
class FailSafeSignalGenerator:
    """
    Multiple layers of redundancy:
    1. Primary: Dhan WebSocket
    2. Backup: KiteConnect WebSocket
    3. Fallback: REST API polling
    """

    async def get_price(self, instrument: str) -> float:
        # Try Dhan WebSocket (fastest)
        try:
            return await self.dhan_ws.get_ltp(instrument)
        except:
            pass

        # Try Kite WebSocket (backup)
        try:
            return await self.kite_ws.get_ltp(instrument)
        except:
            pass

        # REST API fallback (slowest but reliable)
        try:
            return await self.dhan_rest.get_quote(instrument)
        except:
            pass

        # Last resort: cached price with staleness warning
        logger.warning(f"Using stale price for {instrument}")
        return self.price_cache.get(instrument)
```

### 2. PM Execution Redundancy

```python
class FailSafePMExecutor:
    """
    Multiple broker connections for redundancy.
    If OpenAlgo fails, try direct broker API.
    """

    def __init__(self):
        self.openalgo = OpenAlgoClient(...)
        self.kite_direct = KiteConnect(...)  # Backup
        self.dhan_direct = dhanhq(...)        # Backup

    def place_order(self, **kwargs) -> str:
        # Try OpenAlgo first (primary)
        try:
            return self.openalgo.place_order(**kwargs)
        except Exception as e:
            logger.error(f"OpenAlgo failed: {e}, trying Kite direct")

        # Try Kite direct
        try:
            return self.kite_direct.place_order(**self._convert_to_kite(kwargs))
        except Exception as e:
            logger.error(f"Kite failed: {e}, trying Dhan direct")

        # Try Dhan direct
        return self.dhan_direct.place_order(**self._convert_to_dhan(kwargs))
```

### 3. Health Monitoring & Alerts

```python
class EODHealthMonitor:
    """
    Continuous health checks during EOD window.
    Alerts on any degradation.
    """

    def __init__(self):
        self.checks = [
            self._check_signal_gen_connection,
            self._check_pm_connection,
            self._check_broker_connection,
            self._check_data_freshness,
            self._check_position_sync,
        ]

    async def run_health_checks(self) -> Dict[str, bool]:
        results = {}
        for check in self.checks:
            try:
                results[check.__name__] = await check()
            except Exception as e:
                results[check.__name__] = False
                send_alert(f"Health check failed: {check.__name__}: {e}")
        return results

    async def _check_data_freshness(self) -> bool:
        """Ensure we have fresh price data"""
        for instrument, state in signal_gen.states.items():
            age = (datetime.now() - state.last_update).total_seconds()
            if age > 5:  # More than 5 seconds stale
                send_alert(f"Stale data for {instrument}: {age}s old")
                return False
        return True
```

### 4. Pre-EOD Validation

```python
class PreEODValidator:
    """
    Run 5 minutes before EOD window to catch issues early.
    """

    async def validate(self) -> List[str]:
        issues = []

        # Check broker connection
        if not await self.broker.check_connection():
            issues.append("CRITICAL: Broker not connected")

        # Check data sources
        for source in [self.dhan, self.kite]:
            if not await source.is_connected():
                issues.append(f"WARNING: {source.name} not connected")

        # Check PM is responding
        try:
            await httpx.get(f"{PM_URL}/health", timeout=5)
        except:
            issues.append("CRITICAL: PM not responding")

        # Check positions are synced
        if self.position_sync_age > 30:
            issues.append("WARNING: Position sync is stale")

        # Check available margin
        margin = await self.broker.get_available_margin()
        if margin < MIN_MARGIN_THRESHOLD:
            issues.append(f"WARNING: Low margin: ₹{margin:,.0f}")

        # Send alerts for any issues
        if issues:
            send_alert("\n".join(issues))

        return issues
```

---

## Performance Requirements

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| Signal Gen → PM webhook latency | < 100ms | < 500ms |
| PM order placement (per order) | < 2s | < 5s |
| Total batch execution (4 orders) | < 15s | < 25s |
| Data freshness | < 1s | < 5s |
| Position sync frequency | 5s | 10s |
| Health check frequency | 10s | 30s |

---

## Updated Implementation Plan

### Phase 1: Signal Generator Core (4-5 days)
- [ ] Parallel instrument monitoring (4 threads)
- [ ] Dhan + Kite data managers with failover
- [ ] Indicator calculations (pandas-ta)
- [ ] Position sync from PM via REST

### Phase 2: PM Parallel Execution (3-4 days)
- [ ] ParallelEODExecutor with ThreadPoolExecutor
- [ ] `/webhook/eod_batch` endpoint
- [ ] `/api/positions` endpoint for sync
- [ ] Deadline enforcer with urgency levels

### Phase 3: Fail-Safe Mechanisms (2-3 days)
- [ ] Multi-source data redundancy
- [ ] Multi-broker execution fallback
- [ ] Health monitoring & alerts
- [ ] Pre-EOD validation

### Phase 4: Testing & Hardening (3-4 days)
- [ ] Load testing (simulate 4 instruments)
- [ ] Failure injection (kill data source, broker)
- [ ] Timing validation (hit 30s deadline)
- [ ] Paper trading parallel run

**Total: 12-16 days**

---

*Document created: 2025-12-27*
*Updated: 2025-12-27 - Added Cloud Signal Generator architecture (Option E)*
*Updated: 2025-12-27 - Added Mission-Critical requirements: parallel monitoring, PM sync, parallel execution, fail-safe mechanisms*
*Next review: After Phase 1 implementation*
