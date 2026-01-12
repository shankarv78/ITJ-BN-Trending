# Implementation Prompt: PM Signal Audit & Telegram Bot

Use this prompt with Claude Code or TaskMaster to generate a detailed implementation plan.

---

## Context

You are implementing enhancements to a **live production trading system** (Portfolio Manager) that:
- Trades Bank Nifty (synthetic futures) and Gold/Silver Mini (MCX futures)
- Manages ₹50L+ capital
- Receives signals from TradingView webhooks
- Uses PostgreSQL for persistence
- Has voice announcements for trade confirmations

**Reference:** Read `portfolio_manager/docs/PM_SIGNAL_AUDIT_AND_TELEGRAM_BOT_PRD.md` for full requirements.

---

## Prompt

```
I need to implement two major enhancements to the Portfolio Manager (PM):

## Enhancement 1: Comprehensive Signal Audit Trail

### Current State
- PM has a `signal_log` table for deduplication
- Signals flow: webhook → parser → validator → engine → executor
- No record of WHY signals were rejected or processed
- No record of position sizing calculations
- No linkage between signal and order execution result

### Requirements
1. Create `signal_audit` table to record:
   - Signal outcome (PROCESSED, REJECTED_VALIDATION, REJECTED_RISK, etc.)
   - Rejection reason with structured context data
   - Full validation result (condition + execution validation)
   - Position sizing calculation (inputs, formulas, constraints applied)
   - Risk assessment performed

2. Create `order_execution_log` table to record:
   - Link to signal_audit
   - Order details (type, symbol, quantity, prices)
   - Execution status and timing
   - Multi-leg order support (synthetic futures have 2 legs)
   - Slippage calculation

3. Integrate audit capture at these points in LiveTradingEngine:
   - After signal validation (capture validation result)
   - After position sizing (capture sizing calculation)
   - After order placement (capture execution result)
   - On any rejection (capture rejection reason + context)

### Key Files to Modify
- core/db_state_manager.py - Add audit persistence methods
- live/engine.py - Add audit capture at decision points
- core/position_sizer.py - Return calculation details (not just final lots)
- core/signal_validator.py - Already returns structured results, ensure complete
- core/order_executor.py - Return execution details with timing

### Constraints
- Must not slow down signal processing (audit writes can be async)
- Must handle failures gracefully (audit failure shouldn't block trading)
- 90-day retention (longer than current 7-day signal_log)


## Enhancement 2: Telegram Bot Integration

### Requirements
1. Create Telegram bot with command handlers:
   - /status - System status (running, positions, P&L)
   - /positions - List open positions with details
   - /signals - Recent signals with outcomes
   - /signal <id> - Detailed signal audit trail
   - /pnl - Today's P&L summary
   - /equity - Portfolio equity and margin
   - /risk - Current risk exposure
   - /orders - Today's orders
   - /ping - Heartbeat check
   - /help - Command reference

2. Implement proactive alerts:
   - Signal received
   - Signal rejected (with reason)
   - Order placed
   - Order filled (with slippage)
   - Order failed
   - Stop hit
   - System errors

3. Implement heartbeat:
   - Send status every 5 minutes during market hours
   - Include: status, positions, P&L, last signal time

4. Authorization:
   - Single authorized chat ID
   - Commands only from authorized chat

### Technology
- Use python-telegram-bot library (v20+)
- Async handlers (compatible with asyncio)
- Long polling mode (simpler than webhooks)

### Key Files to Create
- core/telegram_bot.py - Bot application and command handlers
- core/telegram_alerts.py - Alert publisher class
- telegram_config.json - Bot configuration

### Integration Points
- LiveTradingEngine - Call alert publisher on events
- start_all.sh - Start bot as part of PM startup
- portfolio_manager.py - Add bot initialization


## Deliverables

1. Database migrations:
   - 010_signal_audit.sql
   - 011_order_execution_log.sql

2. New service classes:
   - SignalAuditService - Audit persistence
   - TelegramBotService - Bot handlers
   - TelegramAlertPublisher - Event alerts

3. Modified classes:
   - LiveTradingEngine - Audit integration
   - TomBassoPositionSizer - Return calculation details
   - OrderExecutor classes - Return execution details
   - DatabaseStateManager - Audit methods

4. Configuration:
   - telegram_config.json template
   - Environment variables for secrets

5. Tests:
   - Unit tests for SignalAuditService
   - Unit tests for bot handlers (mocked)
   - Integration test for audit flow


## Design Considerations

1. **Async Safety:** Bot runs in separate thread, audit writes are fire-and-forget
2. **Error Isolation:** Telegram/audit failures must not affect trading
3. **Data Privacy:** Don't log sensitive broker credentials
4. **Rate Limits:** Telegram has 30 msg/sec limit, batch if needed
5. **Graceful Degradation:** Bot can be disabled without affecting PM


## Reference Architecture

See the screenshot of existing Stoxxo Telegram bot for UI patterns:
- Menu-style command listing
- Heartbeat monitoring with "Ping Missing Alert"
- Status messages with structured data
- Strategy-level MTM tracking

Implement similar patterns for PM.


Please create a detailed implementation plan with:
1. Task breakdown (suitable for TaskMaster)
2. File-by-file changes
3. Migration scripts
4. Test plan
5. Rollout strategy
```

---

## TaskMaster Integration

To use with TaskMaster, run:

```bash
cd portfolio_manager
task-master parse-prd --input docs/PM_SIGNAL_AUDIT_AND_TELEGRAM_BOT_PRD.md
```

This will generate tasks from the PRD.

---

## Validation Checklist

Before implementation, verify:

- [ ] PRD reviewed and approved by Q
- [ ] Telegram bot token obtained from @BotFather
- [ ] Chat ID identified (use /myid command or getUpdates API)
- [ ] python-telegram-bot added to requirements.txt
- [ ] Database backup taken before migrations

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Audit slows trading | Async writes, fire-and-forget |
| Bot crashes PM | Separate thread, error isolation |
| Telegram down | Graceful degradation, local logging |
| Migration fails | Test on staging first, backup |
| Rate limiting | Batch alerts, queue messages |

---

*Use this prompt to kick off implementation planning.*
