# Auto-Hedge System - Implementation Plan

## Overview

The Auto-Hedge system intelligently manages margin by **only buying hedges when absolutely necessary** - when projected margin utilization would breach the budget threshold before a scheduled strategy entry.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AUTO-HEDGE SYSTEM                                │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  │   Margin     │     │   Strategy   │     │    Hedge     │            │
│  │   Monitor    │────▶│   Scheduler  │────▶│   Executor   │            │
│  │  (Existing)  │     │              │     │              │            │
│  └──────────────┘     └──────────────┘     └──────────────┘            │
│         │                    │                    │                     │
│         ▼                    ▼                    ▼                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  │   OpenAlgo   │     │  PostgreSQL  │     │   Telegram   │            │
│  │     API      │     │   (auto_hedge│     │     Bot      │            │
│  │  (Existing)  │     │    schema)   │     │              │            │
│  └──────────────┘     └──────────────┘     └──────────────┘            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Principle

```
GOAL: Spend ₹0 on hedges if possible
REALITY: Only buy hedges when margin would actually breach budget
NEVER: Buy hedges "just in case" or based on static rules
```

## Implementation Phases

### Phase 1: Database Schema & Infrastructure ✅
- Create `auto_hedge` PostgreSQL schema
- Define SQLAlchemy ORM models
- Database migrations via Alembic
- Configuration settings

### Phase 2: Core Services
- **StrategySchedulerService**: Manages entry schedules, finds upcoming entries
- **MarginCalculatorService**: Calculates projections, hedge requirements
- **HedgeStrikeSelectorService**: Finds optimal OTM strikes by MBPR
- **HedgeExecutorService**: Places orders via OpenAlgo
- **TelegramService**: Sends alerts

### Phase 3: Orchestrator & API
- **AutoHedgeOrchestrator**: Main coordination loop
- REST API endpoints (`/api/hedge/*`)
- Integration with existing margin monitor

### Phase 4: Frontend
- Hedge status panel
- Schedule management UI
- Transaction history
- Analytics dashboard

### Phase 5: Testing & Deployment
- Unit tests (95%+ coverage)
- Integration tests
- Paper trading validation
- Production deployment

## Database Schema

Schema: `auto_hedge`

### Tables
1. `strategy_schedule` - Defines when each portfolio enters
2. `daily_session` - Daily configuration (index, baskets, budget)
3. `hedge_transactions` - Audit log of all hedge actions
4. `strategy_executions` - Tracks each strategy's margin state
5. `active_hedges` - Currently held hedge positions

## Key Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| entry_trigger_pct | 95% | Buy hedge if projected > this |
| entry_target_pct | 85% | Target utilization after hedge |
| exit_trigger_pct | 70% | Consider exit if util < this |
| lookahead_minutes | 5 | Check this many mins before entry |
| max_hedge_cost_per_day | ₹50,000 | Daily spending cap |
| cooldown_seconds | 120 | Min time between actions |

## Margin Constants (Per Basket)

| Index | Expiry | Without Hedge | With Hedge | Benefit |
|-------|--------|---------------|------------|---------|
| SENSEX | 0DTE | ₹3.67L | ₹1.60L | 56% |
| NIFTY | 0DTE | ₹4.33L | ₹1.87L | 57% |
| NIFTY | 1DTE | ₹3.20L | ₹1.40L | 56% |
| NIFTY | 2DTE | ₹3.20L | ₹1.40L | 56% |

## Success Metrics

| Metric | Target |
|--------|--------|
| Hedge trigger accuracy | 100% - never miss required hedge |
| False positive rate | < 5% - don't buy unnecessary hedges |
| Execution latency | < 2 seconds from trigger to order |
| Daily hedge cost | Minimize - only spend when needed |
| Order success rate | > 99% |
| Alert delivery | < 5 seconds |

## File Structure

```
margin-monitor/
├── app/
│   ├── models/
│   │   ├── db_models.py          # Existing
│   │   └── hedge_models.py       # NEW: Auto-hedge models
│   │
│   ├── services/
│   │   ├── openalgo_service.py   # Existing - extend for orders
│   │   ├── strategy_scheduler.py # NEW
│   │   ├── margin_calculator.py  # NEW
│   │   ├── hedge_selector.py     # NEW
│   │   ├── hedge_executor.py     # NEW
│   │   ├── telegram_service.py   # NEW
│   │   └── hedge_orchestrator.py # NEW
│   │
│   ├── api/
│   │   ├── routes.py             # Existing
│   │   ├── hedge_routes.py       # NEW
│   │   └── hedge_schemas.py      # NEW
│   │
│   └── config.py                 # Extend with hedge settings
│
├── alembic/versions/
│   └── xxx_create_auto_hedge_schema.py  # NEW
│
└── tests/
    ├── test_margin_calculator.py # NEW
    ├── test_strategy_scheduler.py # NEW
    ├── test_hedge_selector.py    # NEW
    └── test_orchestrator.py      # NEW
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hedge/status` | GET | Current auto-hedge status |
| `/api/hedge/toggle` | POST | Enable/disable auto-hedge |
| `/api/hedge/manual/buy` | POST | Manual hedge trigger |
| `/api/hedge/manual/exit` | POST | Manual hedge exit |
| `/api/hedge/transactions` | GET | Transaction history |
| `/api/hedge/schedule` | GET/PUT | Strategy schedule CRUD |
| `/api/hedge/analytics` | GET | Performance analytics |
| `/api/hedge/session` | GET/POST | Daily session management |

## Testing Strategy

### Unit Tests
- MarginCalculatorService: projection accuracy
- StrategySchedulerService: schedule logic
- HedgeStrikeSelectorService: MBPR optimization

### Integration Tests
- End-to-end flow with mock broker
- Database transaction integrity
- API endpoint validation

### Paper Trading
- Run for 1 week without placing orders
- Compare decisions with manual trading
- Validate timing and calculations

---

*Last Updated: 2026-01-01*
