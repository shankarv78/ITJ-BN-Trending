# Signal-PnL Coupling Analysis - Bank Nifty v6 Strategy

**Date:** November 16, 2025
**Context:** Production trading system design
**Status:** Analysis complete, awaiting architecture design

---

## EXECUTIVE SUMMARY

The Bank Nifty Trend Following v6 strategy contains **CRITICAL coupling** between signal generation and actual execution results. Base entry signals are clean and equity-independent, but pyramid signals depend on actual fill prices, creating non-deterministic behavior in production.

---

## CRITICAL FINDINGS

### ✅ BASE ENTRY SIGNALS: CLEAN (No Issues)

**Location:** Lines 138-151 in `trend_following_strategy_v6.pine`

All 7 entry conditions are purely price/indicator-based with NO equity dependencies:
- RSI > 70
- Close > EMA(200)
- Close > Donchian Upper
- ADX < 30
- ER(3) > 0.8
- Close > SuperTrend
- NOT Doji

**Verdict:** Signal timing is deterministic and equity-independent ✅

### 🚨 PYRAMID SIGNALS: CRITICAL COUPLING (Major Issues)

#### Issue 1: Profitability Check (Line 257)
```pine
position_is_profitable = unrealized_pnl > 0
```
- Depends on `strategy.openprofit` (actual fills)
- Backtest assumes perfect fills at bar close
- Production slippage causes signal divergence

#### Issue 2: ATR Distance Calculation (Lines 253-254)
```pine
price_move_from_last = close - last_pyramid_price
atr_moves = price_move_from_last / atr_pyramid
```
- Uses actual entry price (`last_pyramid_price`)
- If previous entry had slippage, next pyramid timing shifts

#### Issue 3: Pyramid Sizing (Line 263)
```pine
previous_size = pyramid_count == 0 ? initial_position_size :
    initial_position_size * math.pow(pyramid_size_ratio, pyramid_count)
```
- Uses actual executed position size
- Cascading errors if any pyramid fails to execute

#### Issue 4: Margin Check (Line 269)
```pine
margin_available = total_margin_after_pyramid <= max_margin_available
```
- Depends on `strategy.position_size` (actual fills)

---

## DEPENDENCY CLASSIFICATION

### Type A: CRITICAL - Signal timing depends on execution
1. **Line 257:** Profitability check using `unrealized_pnl`
2. **Lines 253-254:** Pyramid distance from actual fill price
3. **Line 263:** Pyramid sizing from actual position
4. **Line 269:** Margin check from actual position size
5. **Lines 280-281:** Pyramid count affects future signals

### Type B: ACCEPTABLE - Quantity only
1. **Line 218:** Base entry lot sizing uses `equity_high`
2. **Line 229:** ER multiplier scales position

### Type C: EXPECTED - Exit logic
1. **Lines 344-440:** Van Tharp trailing to entry prices
2. **Lines 441-536:** Tom Basso ATR stops
3. **Lines 233-236:** Entry price storage

---

## PRODUCTION IMPACT SCENARIOS

### Scenario 1: Pyramid Timing Drift
```
Backtest: Entry 50,000 → Pyramid at 50,750 (0.75 ATR)
Live: Entry 50,100 (slippage) → Need 50,850 for same 0.75 ATR
Result: Pyramid delayed by 100 points
```

### Scenario 2: Profitability Check Failure
```
Backtest: Entry 50,000, price 50,200 → +200 profit ✅
Live: Entry 50,100, price 50,200 → +100 profit ❌
Result: Pyramid signal doesn't fire if threshold >150 points
```

### Scenario 3: Pyramid Count Desync
```
Backtest: All 5 pyramids execute successfully
Live: Pyramid 3 rejected (margin), pyramid_count = 2
Result: Signal logic expects count=5, actual=2 (divergence)
```

---

## PROPOSED SOLUTION: 3-LAYER ARCHITECTURE

### Layer 1: Signal Engine (Pure, Deterministic)
- Generate entry/pyramid signals from price data only
- Track theoretical positions at signal prices
- Calculate theoretical P&L for profitability checks
- **Output:** Clean signal stream (JSON/CSV)

### Layer 2: Execution Tracker (Monitor Divergence)
- Compare theoretical vs actual fills
- Measure slippage impact on signals
- Alert if divergence exceeds thresholds
- **Output:** Quality metrics dashboard

### Layer 3: Risk Manager (Actual Trading)
- Use actual fills for stop-loss calculations
- Apply real equity for position sizing
- Execute orders based on Layer 1 signals
- **Output:** Real trades via broker API

---

## REQUIRED CODE CHANGES (Option B: Full Decoupling)

### 1. Add Theoretical Tracking Variables
```pine
// After line 179
var float theoretical_entry_price = na
var float theoretical_pyr1_price = na
var float theoretical_pyr2_price = na
var float theoretical_pyr3_price = na
var float theoretical_pyr4_price = na
var float theoretical_pyr5_price = na
var float theoretical_last_pyramid = na
var int theoretical_pyramid_count = 0
var float theoretical_position_size = 0
var float theoretical_initial_size = 0
```

### 2. Fix Profitability Check
```pine
// Replace line 257
theoretical_profit = (close - theoretical_entry_price) *
                     theoretical_position_size * lot_size
position_is_profitable = theoretical_profit > 0
```

### 3. Fix ATR Distance Calculation
```pine
// Replace lines 253-254
price_move_from_last = close - theoretical_last_pyramid
atr_moves = price_move_from_last / atr_pyramid
```

### 4. Fix Pyramid Sizing
```pine
// Replace line 263
previous_size = theoretical_pyramid_count == 0 ?
    theoretical_initial_size :
    theoretical_initial_size * math.pow(pyramid_size_ratio, theoretical_pyramid_count)
```

### 5. Track Signal vs Execution Divergence
```pine
// After base entry execution
theoretical_entry_price := close
theoretical_position_size := final_lots
// Compare to actual fill later
actual_entry_price := strategy.opentrades.entry_price(0)
entry_slippage := actual_entry_price - theoretical_entry_price
```

---

## IMPLEMENTATION OPTIONS

### Option A: Quick Fix (1 week, Low confidence)
Add slippage tolerance buffers:
```pine
min_profit_threshold = equity_high * 0.001  // 0.1% buffer
position_is_profitable = unrealized_pnl > min_profit_threshold
```
**Not recommended** - doesn't solve fundamental coupling

### Option B: Full Decoupling (4-6 weeks, High confidence) ✅ RECOMMENDED
- Complete separation of signal generation from execution
- Theoretical position tracking
- Production-grade deterministic signals
- **Timeline:** 4-6 weeks development + testing

### Option C: Hybrid Approach (2 weeks, Medium confidence)
- Use actual fills for exits only
- Theoretical state for pyramid signals
- Partial decoupling
- **Timeline:** 2 weeks development

---

## USER PRODUCTION REQUIREMENTS

### Trading Setup
- **Instrument:** Bank Nifty synthetic futures (ATM PE Sell + ATM CE Buy)
- **Options:** Monthly options requiring rollover logic
- **Capital Allocation:** 10% of portfolio
- **Timeframe:** 75-minute candles
- **Max Positions:** 6 (1 base + 5 pyramids)

### System Requirements
1. **Signal Generation:** TradingView (decoupled from execution)
2. **Execution Engine:** Python-based cloud application
3. **Order Routing:** Stoxxo (broker-agnostic)
4. **PnL Tracking:** Based on actual fills
5. **Position Management:** Automatic rollovers for monthly options
6. **Risk Management:** EOD candle logic to avoid gap slippage

### Technical Requirements
- Agent-to-agent communication via saved MD files
- Auto-compact context preservation
- Monitoring dashboard for divergence metrics
- Alert system for threshold breaches

---

## NEXT STEPS

1. **Software Architecture Design** (NEW TASK)
   - Engage software architect agent
   - Design complete production system
   - Define technology stack
   - Integration architecture

2. **Signal Decoupling Implementation**
   - Implement theoretical tracking in v6 script
   - Validate backtest results match
   - Test signal generation frequency

3. **Execution Engine Development**
   - Python cloud application
   - Stoxxo integration
   - Rollover automation
   - PnL tracking

4. **Testing & Validation**
   - Paper trading period
   - Monitor theoretical vs actual divergence
   - Adjust parameters if needed

---

## MONITORING METRICS (Critical for Production)

### Signal Quality Metrics
- Signal generation rate vs backtest (target: ±5%)
- Pyramid trigger frequency (should be deterministic)
- Theoretical vs actual signal count divergence

### Execution Quality Metrics
- Average slippage per trade
- Pyramid success rate (theoretical vs actual)
- Position size divergence (<5% target)
- Signal timing drift from slippage

### Risk Metrics
- Actual DD vs theoretical DD
- Realized vs unrealized profit tracking
- Margin utilization (actual vs theoretical)
- Rollover execution quality

---

## FILES MODIFIED/CREATED

### Analysis Phase (Current)
- ✅ `SIGNAL_PNL_COUPLING_ANALYSIS.md` - This file
- ✅ `BANKNIFTY_V6_CHANGELOG.md` - v6 specifications
- ✅ `MONTE_CARLO_ANALYSIS_REPORT.md` - Risk analysis

### Implementation Phase (Pending)
- 🔲 `trend_following_strategy_v6.pine` - Add theoretical tracking
- 🔲 `SIGNAL_DECOUPLING_IMPLEMENTATION.md` - Implementation guide
- 🔲 `PRODUCTION_ARCHITECTURE.md` - System design (architect agent)
- 🔲 `STOXXO_INTEGRATION_SPEC.md` - Order routing specs
- 🔲 `ROLLOVER_AUTOMATION_LOGIC.md` - Monthly options rollover

---

## AGENT HANDOFF NOTES

**To: Software Architect Agent**

Please design a production trading system with the following requirements:

**Input:**
- Signals from TradingView (decoupled from execution)
- 75-minute candle data
- 7 base entry conditions + 5 pyramid conditions
- ROC filter disabled, ATR-gated pyramiding

**Processing:**
- Python cloud application
- Track actual fills, PnL, positions
- Handle monthly options rollovers
- EOD candle logic for gap management
- Theoretical vs actual state tracking

**Output:**
- Orders via Stoxxo API
- Real-time PnL dashboard
- Divergence monitoring
- Alert system

**Constraints:**
- Broker-agnostic (Stoxxo interface)
- Cloud-hosted (AWS/GCP/Azure)
- Scalable architecture
- Real-time monitoring
- Agent-to-agent communication via MD files

**Technology Stack Preferences:**
- Python for execution engine
- Cloud infrastructure (AWS preferred)
- Real-time database (Redis/PostgreSQL)
- Message queue (RabbitMQ/Kafka)
- Monitoring (Grafana/Prometheus)

---

**Document Version:** 1.0
**Author:** Claude Code Analysis
**Date:** November 16, 2025
**Status:** Analysis Complete → Architecture Design Pending
**Next Agent:** Software Architect
