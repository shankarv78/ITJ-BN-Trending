# PM Signal Audit Trail & Telegram Bot - Product Requirements Document

**Version:** 1.0
**Date:** January 2026
**Author:** Claude Code
**Status:** Draft for Review

---

## 1. Executive Summary

### Problem Statement

The Portfolio Manager (PM) currently logs signals for deduplication but lacks:
1. **Comprehensive audit trail** - No record of WHY signals were processed/rejected
2. **Decision transparency** - Position sizing calculations not persisted
3. **Order execution tracking** - Success/failure of broker operations not linked to signals
4. **Operational visibility** - No way to query system state via Telegram

### Proposed Solution

Enhance PM with:
1. **Enhanced Signal Audit** - Full decision trail from webhook to execution
2. **Telegram Bot Integration** - Query system state, receive alerts, heartbeat monitoring

### Business Value

- **Debugging:** Quickly diagnose why trades did/didn't happen
- **Compliance:** Full audit trail for trading decisions
- **Operations:** Monitor PM health via mobile
- **Post-trade analysis:** Understand position sizing decisions

---

## 2. Current State Analysis

### Existing signal_log Schema

```sql
CREATE TABLE signal_log (
    id BIGSERIAL PRIMARY KEY,
    instrument VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    position VARCHAR(20) NOT NULL,
    signal_timestamp TIMESTAMP NOT NULL,
    fingerprint VARCHAR(64) UNIQUE NOT NULL,
    is_duplicate BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_by_instance VARCHAR(50),
    processing_status VARCHAR(20),  -- accepted, rejected, blocked, executed
    payload JSONB
);
```

### Gaps Identified

| Gap | Impact |
|-----|--------|
| No rejection reason | Can't debug why signals were rejected |
| No position sizing data | Can't verify lot calculation was correct |
| No risk calculation | Can't audit risk decisions |
| No order execution result | Can't correlate signal → order → fill |
| 7-day retention | Lose historical audit data |
| No Telegram integration | No mobile monitoring |

---

## 3. Requirements

### 3.1 Enhanced Signal Audit Trail

#### 3.1.1 Signal Outcome Tracking

**Requirement:** Record the final outcome of every signal received.

| Outcome | Description |
|---------|-------------|
| `PROCESSED` | Signal accepted and order placed |
| `REJECTED_VALIDATION` | Failed signal validation (stale, future timestamp, etc.) |
| `REJECTED_RISK` | Failed risk checks (margin, position limit) |
| `REJECTED_DUPLICATE` | Duplicate signal (already processed) |
| `REJECTED_MARKET_CLOSED` | Received outside market hours |
| `REJECTED_MANUAL_OVERRIDE` | User chose to reject via voice prompt |
| `FAILED_ORDER` | Signal valid but order placement failed |
| `PARTIAL_FILL` | Order partially filled |

#### 3.1.2 Rejection Reason with Context

**Requirement:** For each rejection, store structured reason with decision data.

```json
{
  "rejection_code": "SIGNAL_STALE",
  "rejection_reason": "Signal age 45s exceeds threshold 30s",
  "decision_data": {
    "signal_timestamp": "2026-01-06T10:15:30+05:30",
    "received_at": "2026-01-06T10:16:15+05:30",
    "signal_age_seconds": 45,
    "threshold_seconds": 30,
    "severity": "REJECTED"
  }
}
```

#### 3.1.3 Position Sizing Calculation Audit

**Requirement:** Record full position sizing calculation for accepted signals.

```json
{
  "sizing_method": "TOM_BASSO",
  "inputs": {
    "equity_high": 5200000,
    "risk_percent": 1.0,
    "stop_distance": 245.50,
    "lot_size": 15,
    "point_value": 30,
    "efficiency_ratio": 0.72,
    "atr": 312.45
  },
  "calculation": {
    "risk_amount": 52000,
    "raw_lots": 4.72,
    "er_adjusted_lots": 3.40,
    "final_lots": 3
  },
  "constraints_applied": [
    {"constraint": "FLOOR", "before": 3.40, "after": 3},
    {"constraint": "MAX_LOTS_PER_TRADE", "limit": 10, "applied": false}
  ],
  "limiter": "RISK"  -- What limited the position: RISK, VOLATILITY, MARGIN
}
```

#### 3.1.4 Order Execution Tracking

**Requirement:** Link signal to order execution result.

```json
{
  "order_id": "ZERODHA_20260106_123456",
  "order_type": "SYNTHETIC_FUTURES",  -- or DIRECT_FUTURES
  "legs": [
    {
      "leg": "CE_BUY",
      "symbol": "BANKNIFTY06JAN26C52000",
      "quantity": 45,
      "order_status": "COMPLETE",
      "fill_price": 385.50,
      "fill_time": "2026-01-06T10:16:18+05:30"
    },
    {
      "leg": "PE_SELL",
      "symbol": "BANKNIFTY06JAN26P52000",
      "quantity": 45,
      "order_status": "COMPLETE",
      "fill_price": 412.30,
      "fill_time": "2026-01-06T10:16:19+05:30"
    }
  ],
  "execution_status": "SUCCESS",
  "execution_time_ms": 1850,
  "slippage": {
    "signal_price": 52145.00,
    "execution_price": 52172.80,  -- synthetic price
    "slippage_pct": 0.053
  }
}
```

### 3.2 Telegram Bot Integration

#### 3.2.1 Bot Commands (Query Capability)

| Command | Description | Response |
|---------|-------------|----------|
| `/status` | PM system status | Running/Stopped, uptime, positions open |
| `/positions` | Current open positions | List with entry, lots, P&L |
| `/signals` | Recent signals (last 10) | Signal type, outcome, time |
| `/signal <id>` | Detailed signal info | Full audit trail |
| `/pnl` | Today's P&L summary | Realized + Unrealized |
| `/equity` | Portfolio equity | Closed equity, margin used |
| `/risk` | Current risk exposure | Risk %, volatility % |
| `/orders` | Today's orders | Order status, fills |
| `/ping` | Heartbeat check | Responds with latency |
| `/help` | List commands | Command reference |

#### 3.2.2 Proactive Alerts

| Event | Alert Message |
|-------|---------------|
| Signal Received | `📥 ENTRY signal: BN @ ₹52,145` |
| Signal Rejected | `⛔ REJECTED: Signal stale (45s > 30s)` |
| Order Placed | `📤 ORDER: BUY 3 lots BN synthetic` |
| Order Filled | `✅ FILLED: 3 lots @ ₹52,172 (slip: 0.05%)` |
| Order Failed | `❌ FAILED: Margin insufficient` |
| Stop Hit | `🛑 STOP HIT: BN @ ₹51,890 (P&L: -₹12,450)` |
| System Error | `🚨 ERROR: DB connection lost` |

#### 3.2.3 Heartbeat Monitoring

**Requirement:** PM sends periodic heartbeat to Telegram.

```
✅ PM Heartbeat
Time: 10:16:00 IST
Status: Running
Positions: 2 open
Today P&L: ₹15,450
Last Signal: 09:45:23 (ENTRY processed)
```

- Frequency: Every 5 minutes during market hours
- Missing heartbeat triggers alert on receiving bot

#### 3.2.4 Authorization

- Single authorized chat ID (configurable)
- Commands only accepted from authorized chat
- API key validation for sensitive operations

---

## 4. Database Schema Changes

### 4.1 New Table: signal_audit

```sql
CREATE TABLE signal_audit (
    id BIGSERIAL PRIMARY KEY,

    -- Link to signal_log
    signal_log_id BIGINT REFERENCES signal_log(id),
    signal_fingerprint VARCHAR(64) NOT NULL,

    -- Signal identification (denormalized for query performance)
    instrument VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    position VARCHAR(20) NOT NULL,
    signal_timestamp TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Outcome
    outcome VARCHAR(30) NOT NULL,  -- PROCESSED, REJECTED_*, FAILED_*
    outcome_reason TEXT,           -- Human-readable reason

    -- Decision data (JSONB for flexibility)
    validation_result JSONB,       -- Condition + execution validation
    sizing_calculation JSONB,      -- Position sizing inputs/outputs
    risk_assessment JSONB,         -- Risk checks performed

    -- Order execution (if applicable)
    order_execution JSONB,         -- Order placement result

    -- Metadata
    processing_duration_ms INTEGER,
    processed_by_instance VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    CONSTRAINT idx_signal_audit_fingerprint UNIQUE (signal_fingerprint)
);

-- Indexes for common queries
CREATE INDEX idx_signal_audit_instrument_time ON signal_audit(instrument, signal_timestamp);
CREATE INDEX idx_signal_audit_outcome ON signal_audit(outcome);
CREATE INDEX idx_signal_audit_created ON signal_audit(created_at);
```

### 4.2 New Table: order_execution_log

```sql
CREATE TABLE order_execution_log (
    id BIGSERIAL PRIMARY KEY,

    -- Link to signal audit
    signal_audit_id BIGINT REFERENCES signal_audit(id),
    position_id VARCHAR(50),  -- Link to portfolio_positions

    -- Order identification
    order_id VARCHAR(100),
    broker_order_id VARCHAR(100),

    -- Order details
    order_type VARCHAR(30) NOT NULL,  -- SYNTHETIC_FUTURES, DIRECT_FUTURES, OPTION
    action VARCHAR(10) NOT NULL,       -- BUY, SELL
    instrument VARCHAR(20) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    lots INTEGER NOT NULL,

    -- Pricing
    signal_price DECIMAL(12,2),
    limit_price DECIMAL(12,2),
    fill_price DECIMAL(12,2),
    slippage_pct DECIMAL(6,4),

    -- Status
    order_status VARCHAR(20) NOT NULL,  -- PENDING, COMPLETE, REJECTED, CANCELLED, PARTIAL
    status_message TEXT,

    -- Timing
    order_placed_at TIMESTAMP,
    order_filled_at TIMESTAMP,
    execution_duration_ms INTEGER,

    -- Multi-leg orders
    parent_order_id BIGINT REFERENCES order_execution_log(id),
    leg_number INTEGER,

    -- Metadata
    raw_response JSONB,  -- Full broker response

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_exec_signal ON order_execution_log(signal_audit_id);
CREATE INDEX idx_order_exec_position ON order_execution_log(position_id);
CREATE INDEX idx_order_exec_status ON order_execution_log(order_status);
CREATE INDEX idx_order_exec_time ON order_execution_log(order_placed_at);
```

### 4.3 Retention Policy

- `signal_audit`: 90 days (vs 7 days for signal_log)
- `order_execution_log`: 90 days
- Automated cleanup job

---

## 5. Telegram Bot Architecture

### 5.1 Technology Stack

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Bot API                   │
└─────────────────────────────────────────────────────┘
                          ▲
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────┐
│              PM Telegram Bot Service                 │
│  ┌─────────────────────────────────────────────────┐│
│  │  python-telegram-bot (ConversationHandler)      ││
│  └─────────────────────────────────────────────────┘│
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│  │ Command      │  │ Alert        │  │ Heartbeat  ││
│  │ Handlers     │  │ Publisher    │  │ Scheduler  ││
│  └──────────────┘  └──────────────┘  └────────────┘│
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│            Portfolio Manager Core                    │
│  ┌────────────────┐  ┌────────────────────────────┐│
│  │ LiveTrading    │  │ DatabaseStateManager       ││
│  │ Engine         │  │ (signal_audit, orders)     ││
│  └────────────────┘  └────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### 5.2 Bot Handler Structure

```python
# Conversation states
class BotState(Enum):
    MAIN_MENU = 0
    POSITION_DETAIL = 1
    SIGNAL_DETAIL = 2
    ORDER_DETAIL = 3
    CONFIRM_ACTION = 4

# Handler registration
application = Application.builder().token(BOT_TOKEN).build()

# Command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("status", status))
application.add_handler(CommandHandler("positions", positions))
application.add_handler(CommandHandler("signals", signals))
application.add_handler(CommandHandler("pnl", pnl))
application.add_handler(CommandHandler("equity", equity))
application.add_handler(CommandHandler("risk", risk))
application.add_handler(CommandHandler("orders", orders))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(CommandHandler("help", help_command))

# Callback query handler for inline buttons
application.add_handler(CallbackQueryHandler(button_callback))

# Error handler
application.add_error_handler(error_handler)
```

### 5.3 Configuration

```python
# telegram_config.json
{
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID",
    "enabled": true,
    "heartbeat_interval_seconds": 300,
    "alerts": {
        "signal_received": true,
        "signal_rejected": true,
        "order_placed": true,
        "order_filled": true,
        "order_failed": true,
        "stop_hit": true,
        "system_error": true
    }
}
```

---

## 6. API Endpoints (Internal)

### 6.1 Signal Audit API

```
GET  /api/signals                    # List recent signals
GET  /api/signals/{fingerprint}      # Get signal detail with audit
GET  /api/signals/stats              # Signal statistics

GET  /api/orders                     # List recent orders
GET  /api/orders/{order_id}          # Get order detail

GET  /api/audit/sizing/{position_id} # Get sizing calculation
GET  /api/audit/risk/{signal_id}     # Get risk assessment
```

### 6.2 Telegram Webhook (Optional)

```
POST /telegram/webhook               # Telegram updates (if using webhook mode)
```

---

## 7. Implementation Plan

### Phase 1: Database Schema (Week 1)

1. Create migration `010_signal_audit.sql`
2. Create migration `011_order_execution_log.sql`
3. Update retention policy
4. Add indexes

### Phase 2: Signal Audit Integration (Week 2)

1. Create `SignalAuditService` class
2. Integrate into `LiveTradingEngine.process_signal()`
3. Capture validation results
4. Capture sizing calculations
5. Capture order execution

### Phase 3: Telegram Bot - Core (Week 3)

1. Set up bot with python-telegram-bot
2. Implement authorization
3. Implement query commands (/status, /positions, etc.)
4. Test command responses

### Phase 4: Telegram Bot - Alerts (Week 4)

1. Implement alert publisher
2. Integrate into signal flow
3. Implement heartbeat scheduler
4. Test alerts

### Phase 5: Testing & Documentation (Week 5)

1. Unit tests for audit service
2. Integration tests for bot
3. Update documentation
4. User acceptance testing

---

## 8. Sample Interactions

### 8.1 Query Signal Detail

```
User: /signal abc123

Bot:
📊 *Signal Detail*

*ID:* abc123
*Type:* ENTRY (Base)
*Instrument:* BANK_NIFTY
*Timestamp:* 06-Jan-2026 10:15:30 IST

*Outcome:* ✅ PROCESSED

*Validation:*
├─ Signal Age: 3.2s ✅
├─ Divergence: 0.12% ✅
└─ Risk Increase: N/A

*Position Sizing:*
├─ Equity High: ₹52,00,000
├─ Risk %: 1.0%
├─ Stop Distance: 245.5 pts
├─ Raw Lots: 4.72
├─ ER Adjusted: 3.40
└─ *Final: 3 lots* (RISK limited)

*Order Execution:*
├─ Order ID: ZRD_123456
├─ Status: COMPLETE
├─ Fill Price: ₹52,172.80
├─ Slippage: 0.053%
└─ Duration: 1.85s
```

### 8.2 Status Command

```
User: /status

Bot:
🤖 *PM Status*

*Status:* 🟢 Running
*Uptime:* 4h 23m
*Mode:* LIVE

*Positions:*
├─ Open: 2
├─ BN: 3 lots @ 52,145
└─ GOLD: 2 lots @ 78,234

*Today:*
├─ Signals: 4 (3 processed, 1 rejected)
├─ Orders: 3 (all filled)
└─ P&L: +₹15,450

*System:*
├─ DB: Connected ✅
├─ Broker: Connected ✅
└─ Last Heartbeat: 10:15:00
```

### 8.3 Rejection Alert

```
Bot:
⛔ *SIGNAL REJECTED*

*Instrument:* BANK_NIFTY
*Type:* PYRAMID
*Time:* 10:45:23 IST

*Reason:* `SIGNAL_STALE`
Signal age 45s exceeds threshold 30s

*Details:*
├─ Signal Time: 10:44:38
├─ Received: 10:45:23
├─ Age: 45 seconds
└─ Threshold: 30 seconds

_No action taken._
```

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Audit coverage | 100% of signals have audit record |
| Query response time | < 2 seconds for Telegram commands |
| Alert delivery | < 5 seconds from event |
| Heartbeat reliability | 99.9% during market hours |
| Storage efficiency | < 100MB/month for audit data |

---

## 10. Design Decisions (Confirmed)

| Question | Decision |
|----------|----------|
| Retention period | 90 days ✅ |
| Interactive actions | Query only, no order cancellation ✅ |
| Multi-user support | Single user only ✅ |
| Alert frequency | Every signal (no digest mode) ✅ |
| Sensitive data | Mask broker credentials, order IDs visible |
| Rate limiting | Queue messages if >30/sec (unlikely in practice) |

---

## 11. Appendix

### A. Current PM Files to Modify

| File | Changes |
|------|---------|
| `core/db_state_manager.py` | Add audit save methods |
| `live/engine.py` | Integrate audit at each decision point |
| `core/position_sizer.py` | Return calculation details |
| `core/signal_validator.py` | Return structured result |
| `core/order_executor.py` | Return execution details |
| `portfolio_manager.py` | Add API endpoints |

### B. New Files to Create

| File | Purpose |
|------|---------|
| `core/signal_audit_service.py` | Audit trail service |
| `core/telegram_bot.py` | Telegram bot handlers |
| `core/telegram_alerts.py` | Alert publisher |
| `migrations/010_signal_audit.sql` | Audit table |
| `migrations/011_order_execution_log.sql` | Order log table |
| `telegram_config.json` | Bot configuration |

### C. Dependencies to Add

```
python-telegram-bot>=20.0
```

---

*End of PRD*
