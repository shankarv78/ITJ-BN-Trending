# Production Trading System - Architecture Design Request

**Date:** November 16, 2025
**Requester:** User (Production Trading System)
**Target:** Software Architect Agent
**Context Files:** `SIGNAL_PNL_COUPLING_ANALYSIS.md`, `BANKNIFTY_V6_CHANGELOG.md`

---

## PROJECT OVERVIEW

Design a **production-grade automated trading system** for Bank Nifty Trend Following v6 strategy using synthetic futures (monthly options), with complete decoupling of signal generation from execution.

---

## BUSINESS REQUIREMENTS

### Trading Strategy
- **Name:** Bank Nifty Trend Following v6.0
- **Performance:** 27.5% CAGR, -25.08% max DD (16.9 years backtest)
- **Capital Allocation:** 10% of portfolio (₹5L out of ₹50L total)
- **Instrument:** Bank Nifty synthetic futures (ATM PE Sell + ATM CE Buy)
- **Options Type:** Monthly options (require rollover logic)
- **Timeframe:** 75-minute candles
- **Max Positions:** 6 concurrent (1 base + 5 pyramids)

### Signal Characteristics
- **Base Entry:** 7 conditions (RSI, EMA, DC, ADX, ER, SuperTrend, Doji)
- **Pyramid Entry:** ATR-gated (0.75 ATR spacing), profitability check, margin check
- **ROC Filter:** Disabled in v6 (allows unrestricted pyramiding)
- **Expected Frequency:** ~55 trades/year, 52.98% win rate
- **Stop Loss:** Tom Basso mode (ATR trailing stops per position)

---

## TECHNICAL REQUIREMENTS

### 1. Signal Generation Layer (TradingView)
**Purpose:** Generate pure, deterministic signals
**Output:** Signal stream (entry/exit/pyramid signals)
**Coupling Issue:** Currently couples signal timing to actual fills (see `SIGNAL_PNL_COUPLING_ANALYSIS.md`)

**Requirements:**
- Decouple signal generation from execution results
- Track theoretical positions at signal prices
- Calculate theoretical P&L for profitability checks
- Output signals to cloud execution engine
- **NO dependency** on actual fill prices for signal timing

**Output Format:**
```json
{
  "timestamp": "2025-11-16T10:15:00Z",
  "signal_type": "BASE_ENTRY",
  "symbol": "BANKNIFTY",
  "price": 50000,
  "conditions": {
    "rsi": 72.5,
    "ema": 49500,
    "dc_upper": 49800,
    "adx": 28.5,
    "er": 0.85,
    "supertrend": 49750,
    "doji": false
  },
  "theoretical_lots": 12,
  "stop_loss": 49650
}
```

### 2. Execution Engine (Python Cloud Application)
**Purpose:** Execute trades, track actual positions, manage rollovers
**Hosting:** Cloud-based (AWS/GCP/Azure)
**Language:** Python 3.10+

**Core Responsibilities:**
1. **Signal Reception:** Receive signals from TradingView
2. **Order Execution:** Route orders via Stoxxo API
3. **Position Tracking:** Track actual fills, sizes, entry prices
4. **PnL Calculation:** Real-time P&L based on actual fills
5. **Rollover Management:** Automatic monthly options rollover
6. **Gap Management:** EOD candle logic to avoid gap slippage
7. **Divergence Monitoring:** Compare theoretical vs actual state

**Required Features:**
- Real-time position management
- Automatic stop-loss order placement
- Margin utilization tracking
- Pyramid sequencing (ensure proper ordering)
- Error handling and retry logic
- Logging and audit trail

### 3. Order Routing Layer (Stoxxo Integration)
**Purpose:** Broker-agnostic order execution
**API:** Stoxxo (https://stoxxo.com)

**Requirements:**
- Place market/limit orders for options
- Track order status (pending/filled/rejected)
- Handle partial fills
- Support multiple brokers via Stoxxo
- Order modification/cancellation
- Real-time order book updates

**Order Types Needed:**
- Market orders (base entries)
- Limit orders (pyramids with price buffer)
- Stop-loss orders (Tom Basso ATR stops)
- Bracket orders (entry + SL combined)

### 4. Rollover Automation
**Challenge:** Monthly options expire, need to roll positions
**Requirement:** Automatic rollover logic

**Rollover Process:**
1. **Timing:** 3-5 days before expiry
2. **Execution:** Exit current month, enter next month
3. **Price Matching:** Maintain synthetic future price equivalence
4. **Position Continuity:** Preserve pyramid structure
5. **Cost Tracking:** Track rollover costs separately

**Rollover Logic:**
```
IF (days_to_expiry <= 5) AND (time = 15:00):
    current_month_positions = get_open_positions()
    next_month_strikes = calculate_ATM_strikes()

    FOR each position:
        EXIT current_month_option
        ENTER next_month_option (same strike offset)

    UPDATE position tracking
    LOG rollover cost
```

### 5. EOD Candle Logic (Gap Management)
**Problem:** 75-minute candles can have significant gaps (especially overnight)
**Solution:** Wait for EOD candle confirmation before executing signals

**Logic:**
```
IF signal.timestamp.hour >= 14 AND signal.timestamp.minute >= 15:
    # Near market close (3:15 PM onwards)
    execution_mode = "EOD_WAIT"
    wait_for_next_day_open()
ELSE:
    execution_mode = "IMMEDIATE"
    execute_signal()
```

**Gap Handling:**
- If gap > 1% from signal price: adjust entry logic
- If gap > 2%: skip entry, wait for next signal
- Track gap frequency and impact on performance

### 6. Monitoring & Alerts
**Dashboard Requirements:**
- Real-time position status
- Theoretical vs actual P&L comparison
- Signal execution rate (should match backtest)
- Slippage per trade
- Pyramid success rate
- Margin utilization
- Rollover history

**Alert Conditions:**
- Divergence > 5% (theoretical vs actual)
- Position size mismatch
- Failed pyramid execution
- Rollover required (3 days notice)
- Margin utilization > 80%
- Stop-loss breach
- System errors/API failures

---

## ARCHITECTURE DESIGN REQUIREMENTS

### System Components

**1. TradingView Signal Generator**
- Input: 75-min OHLC data
- Processing: Indicator calculations, condition checks
- Output: Webhook to cloud execution engine

**2. Cloud Execution Engine (Python)**
Components needed:
- Signal receiver (webhook endpoint)
- Theoretical state tracker
- Order manager (Stoxxo integration)
- Position manager
- PnL calculator
- Rollover scheduler
- Gap handler
- Database (position state, trades, logs)

**3. Message Queue**
- Handle signal bursts
- Ensure order sequencing
- Retry failed operations

**4. Database**
- Real-time positions
- Trade history
- Signal logs
- Theoretical vs actual state
- Performance metrics

**5. Monitoring Dashboard**
- Grafana/Prometheus or similar
- Real-time metrics
- Alert management

### Data Flow
```
TradingView (75-min candle close)
    ↓ Webhook
Cloud Execution Engine
    ↓ Validate signal
Theoretical State Tracker
    ↓ Calculate theoretical position
Order Manager
    ↓ Generate order
Stoxxo API
    ↓ Execute order
Broker
    ↓ Fill confirmation
Position Manager
    ↓ Update actual state
PnL Calculator
    ↓ Compare theoretical vs actual
Monitoring Dashboard
    ↓ Alert if divergence > threshold
```

### Technology Stack Recommendations

**Backend:**
- Python 3.10+ (FastAPI/Flask)
- Pandas/NumPy (calculations)
- SQLAlchemy (ORM)
- Celery (task queue)
- Redis (cache/message broker)

**Database:**
- PostgreSQL (relational data)
- TimescaleDB (time-series extension)
- Redis (real-time state)

**Infrastructure:**
- AWS EC2/Lambda (compute)
- AWS RDS (database)
- AWS SQS (message queue)
- CloudWatch (logging)

**Monitoring:**
- Grafana (dashboards)
- Prometheus (metrics)
- Sentry (error tracking)

**APIs:**
- Stoxxo API (order execution)
- TradingView Webhook (signal reception)

---

## AGENT-TO-AGENT COMMUNICATION PROTOCOL

### Communication Files (MD format)

**1. Input Files (Read by Architecture Agent):**
- `SIGNAL_PNL_COUPLING_ANALYSIS.md` - Signal coupling analysis
- `BANKNIFTY_V6_CHANGELOG.md` - Strategy specifications
- `MONTE_CARLO_ANALYSIS_REPORT.md` - Risk metrics
- `ARCHITECTURE_HANDOFF.md` - This file

**2. Output Files (Written by Architecture Agent):**
- `PRODUCTION_ARCHITECTURE.md` - Complete system design
- `TECHNOLOGY_STACK_SPECIFICATION.md` - Detailed stack choices
- `API_INTEGRATION_DESIGN.md` - Stoxxo + TradingView integration
- `ROLLOVER_AUTOMATION_DESIGN.md` - Rollover logic specification
- `DATABASE_SCHEMA.md` - Data models
- `DEPLOYMENT_ARCHITECTURE.md` - Cloud infrastructure

**3. Handoff to Development Agent (Future):**
- `IMPLEMENTATION_PLAN.md` - Phase-wise development plan
- `API_ENDPOINTS_SPEC.md` - REST API specifications
- `TESTING_STRATEGY.md` - QA plan

### Communication Format
Each MD file should have:
- **Header:** Agent name, date, status
- **Context:** Link to prerequisite files
- **Content:** Structured sections
- **Handoff Notes:** Instructions for next agent
- **Open Questions:** Items needing clarification

---

## DESIGN CONSTRAINTS

### Must-Have Features
1. Signal-execution decoupling (critical)
2. Stoxxo integration (broker-agnostic)
3. Automatic rollover (monthly options)
4. EOD gap handling
5. Real-time monitoring
6. Theoretical vs actual tracking

### Nice-to-Have Features
1. Backtesting on actual fills
2. Multi-strategy support (future)
3. Mobile alerts
4. Trade replay/simulation
5. Automated reporting

### Non-Negotiable Requirements
1. **Reliability:** 99.9% uptime during market hours
2. **Latency:** Signal to order <5 seconds
3. **Data Integrity:** No position tracking errors
4. **Security:** API keys encrypted, secure storage
5. **Auditability:** Complete trade logs
6. **Scalability:** Support 10x trade volume

---

## SUCCESS CRITERIA

**Architecture Design is complete when:**
1. ✅ Complete component diagram provided
2. ✅ Technology stack justified and selected
3. ✅ API integration design specified
4. ✅ Database schema defined
5. ✅ Deployment architecture documented
6. ✅ Rollover logic designed
7. ✅ Monitoring strategy defined
8. ✅ Error handling approach specified
9. ✅ Cost estimate provided
10. ✅ Implementation timeline proposed

**Production System is successful when:**
1. Signal generation rate matches backtest (±5%)
2. Pyramid execution rate >90%
3. Average slippage <0.1% per trade
4. Rollover execution seamless (zero missed rollovers)
5. Theoretical vs actual DD divergence <10%
6. Zero catastrophic failures
7. Complete audit trail maintained

---

## OPEN QUESTIONS FOR ARCHITECT

1. **Cloud Provider:** AWS vs GCP vs Azure?
2. **Deployment:** Containerized (Docker/K8s) or serverless (Lambda)?
3. **Database:** Single PostgreSQL or hybrid (PostgreSQL + TimescaleDB)?
4. **Message Queue:** Redis pub/sub vs RabbitMQ vs AWS SQS?
5. **TradingView Integration:** Webhook vs WebSocket?
6. **Stoxxo API:** REST vs WebSocket for real-time updates?
7. **State Management:** How to handle partial fills across pyramids?
8. **Rollover Timing:** Fixed schedule vs dynamic based on liquidity?
9. **Gap Threshold:** When to skip execution vs adjust entry?
10. **Monitoring:** Self-hosted Grafana vs cloud service (Datadog)?

---

## BUDGET & TIMELINE (Informational)

**Development Budget:** TBD (architect to estimate)
**Timeline:** 8-12 weeks preferred
**Monthly OpEx:** Target <$500/month (cloud + APIs)

---

**Status:** PENDING ARCHITECTURE DESIGN
**Next Agent:** Software Architect
**Expected Deliverable:** `PRODUCTION_ARCHITECTURE.md`
**Deadline:** ASAP (high priority)
