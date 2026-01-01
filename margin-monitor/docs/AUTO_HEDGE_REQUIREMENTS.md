# Auto-Hedge System - Implementation Guide

## Project Overview

### Objective
Build an intelligent auto-hedge system that **minimizes hedge cost** while ensuring sufficient margin availability for scheduled intraday options strategies. The system observes real-time margin utilization and proactively buys/sells hedges only when absolutely necessary.

### Core Principle
```
GOAL: Spend ₹0 on hedges if possible
REALITY: Only buy hedges when margin would actually breach budget
NEVER: Buy hedges "just in case" or based on static rules
```

### Why Not Stoxxo's Dynamic Hedge?
Stoxxo's "Dynamic Hedge" is actually **static** - pre-configured per portfolio, not margin-aware. It buys hedges even when budget has headroom, wasting money.

**Our system is truly dynamic:**
- Checks ACTUAL margin utilization before each strategy entry
- Calculates PROJECTED utilization after entry
- Only buys hedges when projected > threshold
- Exits hedges when no longer needed

---

## System Architecture

### Integration Points

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
│  │     API      │     │   Database   │     │     Bot      │            │
│  └──────────────┘     └──────────────┘     └──────────────┘            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL (schema: `auto_hedge`)
- **Scheduler:** APScheduler
- **Broker API:** OpenAlgo (existing integration)
- **Alerts:** Telegram Bot API
- **Frontend:** React component in existing Margin Monitor dashboard

---

## Core Data Models

### 1. Strategy Schedule

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import time, date
from enum import Enum

class DayOfWeek(str, Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"

class IndexName(str, Enum):
    NIFTY = "NIFTY"
    SENSEX = "SENSEX"

class ExpiryType(str, Enum):
    ZERO_DTE = "0DTE"
    ONE_DTE = "1DTE"
    TWO_DTE = "2DTE"

class StrategyEntry(BaseModel):
    portfolio_name: str          # e.g., "ITJ_NF_EXP 1"
    entry_time: time             # e.g., 09:16:00
    exit_time: Optional[time]    # None = expire worthless

class DaySchedule(BaseModel):
    day_of_week: DayOfWeek
    index_name: IndexName
    expiry_type: ExpiryType
    entries: List[StrategyEntry]
```

### 2. Margin Constants (Per Basket)

```python
class MarginConstants(BaseModel):
    """All values in INR, per 1 basket"""

    # Sensex (0DTE) - Thursday
    SENSEX_0DTE_WITHOUT_HEDGE: float = 366666.67    # ~₹3.67L per basket
    SENSEX_0DTE_WITH_HEDGE: float = 160000.00       # ~₹1.6L per basket
    SENSEX_HEDGE_BENEFIT_PCT: float = 0.56          # 56% reduction

    # Nifty (0DTE) - Tuesday
    NIFTY_0DTE_WITHOUT_HEDGE: float = 433333.33     # ~₹4.33L per basket
    NIFTY_0DTE_WITH_HEDGE: float = 186666.67        # ~₹1.87L per basket
    NIFTY_HEDGE_BENEFIT_PCT: float = 0.57           # 57% reduction

    # Nifty (1DTE) - Monday
    NIFTY_1DTE_WITHOUT_HEDGE: float = 320000.00     # ~₹3.2L per basket
    NIFTY_1DTE_WITH_HEDGE: float = 140000.00        # ~₹1.4L per basket

    # Nifty (2DTE) - Friday
    NIFTY_2DTE_WITHOUT_HEDGE: float = 320000.00     # ~₹3.2L per basket
    NIFTY_2DTE_WITH_HEDGE: float = 140000.00        # ~₹1.4L per basket

def get_margin_per_straddle(index: IndexName, expiry_type: ExpiryType,
                            has_hedge: bool, num_baskets: int) -> float:
    """Calculate margin for a straddle based on index, expiry type, and baskets"""
    constants = MarginConstants()

    key = f"{index.value}_{expiry_type.value}_{'WITH' if has_hedge else 'WITHOUT'}_HEDGE"
    per_basket = getattr(constants, key.replace("-", "_"))

    return per_basket * num_baskets
```

### 3. Hedge Configuration

```python
class HedgeConfig(BaseModel):
    """Configuration for hedge strike selection"""

    # Premium range for hedge selection
    min_premium: float = 2.0        # Minimum LTP for hedge strike
    max_premium: float = 6.0        # Maximum LTP for hedge strike

    # OTM distance limits (points from ATM)
    min_otm_distance: dict = {
        "NIFTY": 200,
        "SENSEX": 500
    }
    max_otm_distance: dict = {
        "NIFTY": 1000,
        "SENSEX": 2500
    }

    # Thresholds
    entry_trigger_pct: float = 95.0      # Buy hedge if projected > 95%
    entry_target_pct: float = 85.0       # Target utilization after hedge
    exit_trigger_pct: float = 70.0       # Consider exit if util < 70%

    # Timing
    lookahead_minutes: int = 5           # Check this many minutes before entry
    exit_buffer_minutes: int = 15        # Don't exit if entry within this time

    # Safety
    max_hedge_cost_per_day: float = 50000.0   # ₹50,000 max daily spend
    cooldown_seconds: int = 120               # Minimum time between actions
```

---

## Database Schema

```sql
-- Schema for auto-hedge system
CREATE SCHEMA IF NOT EXISTS auto_hedge;

-- Strategy schedule configuration
CREATE TABLE auto_hedge.strategy_schedule (
    id SERIAL PRIMARY KEY,
    day_of_week VARCHAR(10) NOT NULL,      -- Monday, Tuesday, etc.
    index_name VARCHAR(10) NOT NULL,        -- NIFTY, SENSEX
    expiry_type VARCHAR(10) NOT NULL,       -- 0DTE, 1DTE, 2DTE
    portfolio_name VARCHAR(50) NOT NULL,
    entry_time TIME NOT NULL,
    exit_time TIME,                         -- NULL = expire
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(day_of_week, portfolio_name)
);

-- Daily session configuration
CREATE TABLE auto_hedge.daily_session (
    id SERIAL PRIMARY KEY,
    session_date DATE NOT NULL UNIQUE,
    day_of_week VARCHAR(10) NOT NULL,
    index_name VARCHAR(10) NOT NULL,
    expiry_type VARCHAR(10) NOT NULL,
    expiry_date DATE NOT NULL,
    num_baskets INTEGER NOT NULL,
    budget_per_basket DECIMAL(12,2) DEFAULT 1000000.00,
    total_budget DECIMAL(14,2) GENERATED ALWAYS AS (num_baskets * budget_per_basket) STORED,
    baseline_margin DECIMAL(14,2),
    baseline_captured_at TIMESTAMPTZ,
    auto_hedge_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hedge transactions log
CREATE TABLE auto_hedge.hedge_transactions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES auto_hedge.daily_session(id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Action details
    action VARCHAR(10) NOT NULL,            -- BUY, SELL
    trigger_reason VARCHAR(100) NOT NULL,   -- PRE_STRATEGY:ITJ_NF_EXP_4, EXCESS_MARGIN, MANUAL

    -- Position details
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(10) NOT NULL,          -- NFO, BFO
    strike INTEGER NOT NULL,
    option_type VARCHAR(2) NOT NULL,        -- CE, PE
    quantity INTEGER NOT NULL,
    lots INTEGER NOT NULL,

    -- Pricing
    order_price DECIMAL(10,2) NOT NULL,
    executed_price DECIMAL(10,2),
    total_cost DECIMAL(12,2),

    -- Margin impact
    utilization_before DECIMAL(5,2) NOT NULL,
    utilization_after DECIMAL(5,2),
    margin_impact DECIMAL(14,2),            -- Positive = margin freed

    -- Execution
    order_id VARCHAR(50),
    order_status VARCHAR(20) NOT NULL,      -- PENDING, SUCCESS, FAILED, CANCELLED
    error_message TEXT,

    -- Alerts
    telegram_sent BOOLEAN DEFAULT false,
    telegram_message_id VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Strategy execution tracking
CREATE TABLE auto_hedge.strategy_executions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES auto_hedge.daily_session(id),
    portfolio_name VARCHAR(50) NOT NULL,
    scheduled_entry_time TIME NOT NULL,

    -- Pre-entry state
    utilization_before DECIMAL(5,2),
    projected_utilization DECIMAL(5,2),
    hedge_required BOOLEAN DEFAULT false,
    hedge_transaction_id INTEGER REFERENCES auto_hedge.hedge_transactions(id),

    -- Post-entry state
    actual_entry_time TIMESTAMPTZ,
    utilization_after DECIMAL(5,2),
    entry_successful BOOLEAN,

    -- Exit tracking
    scheduled_exit_time TIME,
    actual_exit_time TIMESTAMPTZ,
    exit_reason VARCHAR(20),                -- TIMED, SL_HIT, EXPIRED, MANUAL

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hedge positions (active hedges)
CREATE TABLE auto_hedge.active_hedges (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES auto_hedge.daily_session(id),
    transaction_id INTEGER REFERENCES auto_hedge.hedge_transactions(id),

    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    strike INTEGER NOT NULL,
    option_type VARCHAR(2) NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price DECIMAL(10,2) NOT NULL,
    current_price DECIMAL(10,2),

    -- Status
    is_active BOOLEAN DEFAULT true,
    exit_transaction_id INTEGER REFERENCES auto_hedge.hedge_transactions(id),

    -- Calculated fields
    otm_distance INTEGER,                   -- Points from ATM at entry
    margin_benefit DECIMAL(14,2),           -- Estimated margin reduction

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_hedge_transactions_session ON auto_hedge.hedge_transactions(session_id);
CREATE INDEX idx_hedge_transactions_timestamp ON auto_hedge.hedge_transactions(timestamp);
CREATE INDEX idx_strategy_executions_session ON auto_hedge.strategy_executions(session_id);
CREATE INDEX idx_active_hedges_session ON auto_hedge.active_hedges(session_id, is_active);
```

---

## Core Services

### 1. Strategy Scheduler Service

```python
# services/strategy_scheduler.py

from datetime import datetime, time, timedelta
from typing import Optional, List, Tuple
import pytz

IST = pytz.timezone('Asia/Kolkata')

class StrategySchedulerService:
    """Manages strategy schedule and finds upcoming entries"""

    def __init__(self, db_session, config: HedgeConfig):
        self.db = db_session
        self.config = config
        self._schedule_cache = {}

    async def get_today_schedule(self) -> List[StrategyEntry]:
        """Get all scheduled entries for today"""
        today = datetime.now(IST)
        day_name = today.strftime("%A")

        entries = await self.db.fetch_all(
            """
            SELECT portfolio_name, entry_time, exit_time
            FROM auto_hedge.strategy_schedule
            WHERE day_of_week = :day AND is_active = true
            ORDER BY entry_time
            """,
            {"day": day_name}
        )
        return [StrategyEntry(**e) for e in entries]

    async def get_next_entry(self) -> Optional[Tuple[StrategyEntry, int]]:
        """
        Get next scheduled strategy entry and seconds until entry
        Returns: (entry, seconds_until) or None if no more entries today
        """
        now = datetime.now(IST)
        current_time = now.time()

        schedule = await self.get_today_schedule()

        for entry in schedule:
            if entry.entry_time > current_time:
                # Calculate seconds until entry
                entry_datetime = datetime.combine(now.date(), entry.entry_time)
                entry_datetime = IST.localize(entry_datetime)
                seconds_until = (entry_datetime - now).total_seconds()
                return (entry, int(seconds_until))

        return None

    async def get_entries_in_window(self, minutes: int) -> List[StrategyEntry]:
        """Get all entries within the next N minutes"""
        now = datetime.now(IST)
        current_time = now.time()
        window_end = (now + timedelta(minutes=minutes)).time()

        schedule = await self.get_today_schedule()

        return [
            entry for entry in schedule
            if current_time < entry.entry_time <= window_end
        ]

    async def is_entry_imminent(self) -> Tuple[bool, Optional[StrategyEntry], int]:
        """
        Check if a strategy entry is imminent (within lookahead window)
        Returns: (is_imminent, entry, seconds_until)
        """
        result = await self.get_next_entry()
        if result is None:
            return (False, None, 0)

        entry, seconds_until = result
        is_imminent = seconds_until <= (self.config.lookahead_minutes * 60)

        return (is_imminent, entry, seconds_until)

    async def get_executed_count_today(self) -> int:
        """Get count of strategies already executed today"""
        now = datetime.now(IST)
        current_time = now.time()
        schedule = await self.get_today_schedule()

        return sum(1 for entry in schedule if entry.entry_time < current_time)

    async def get_remaining_count_today(self) -> int:
        """Get count of strategies remaining today"""
        now = datetime.now(IST)
        current_time = now.time()
        schedule = await self.get_today_schedule()

        return sum(1 for entry in schedule if entry.entry_time > current_time)
```

### 2. Margin Calculator Service

```python
# services/margin_calculator.py

from typing import Optional
from decimal import Decimal

class MarginCalculatorService:
    """Calculates margin requirements and projections"""

    def __init__(self, config: HedgeConfig):
        self.config = config
        self.constants = MarginConstants()

    def get_margin_per_straddle(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        has_hedge: bool,
        num_baskets: int
    ) -> float:
        """Get margin requirement for one straddle"""

        # Build key to lookup constant
        index_key = index.value
        expiry_key = expiry_type.value.replace("-", "_")
        hedge_key = "WITH_HEDGE" if has_hedge else "WITHOUT_HEDGE"

        attr_name = f"{index_key}_{expiry_key}_{hedge_key}"

        try:
            per_basket = getattr(self.constants, attr_name)
        except AttributeError:
            # Fallback for non-expiry days
            if "1DTE" in expiry_key or "2DTE" in expiry_key:
                per_basket = getattr(self.constants, f"{index_key}_1DTE_{hedge_key}")
            else:
                raise ValueError(f"Unknown margin constant: {attr_name}")

        return per_basket * num_baskets

    def calculate_projected_utilization(
        self,
        current_intraday_margin: float,
        total_budget: float,
        margin_for_next_entry: float
    ) -> float:
        """Calculate projected utilization after next entry"""
        projected_margin = current_intraday_margin + margin_for_next_entry
        return (projected_margin / total_budget) * 100

    def calculate_hedge_required(
        self,
        current_utilization: float,
        projected_utilization: float,
        target_utilization: float = None
    ) -> bool:
        """Determine if hedge is required"""
        if target_utilization is None:
            target_utilization = self.config.entry_trigger_pct

        return projected_utilization > target_utilization

    def calculate_margin_reduction_needed(
        self,
        current_intraday_margin: float,
        total_budget: float,
        margin_for_next_entry: float,
        target_pct: float = None
    ) -> float:
        """Calculate how much margin reduction is needed from hedges"""
        if target_pct is None:
            target_pct = self.config.entry_target_pct

        projected_margin = current_intraday_margin + margin_for_next_entry
        target_margin = total_budget * (target_pct / 100)

        reduction_needed = projected_margin - target_margin
        return max(0, reduction_needed)

    def estimate_hedge_margin_benefit(
        self,
        index: IndexName,
        expiry_type: ExpiryType,
        num_baskets: int
    ) -> float:
        """Estimate margin reduction from adding one hedge pair (CE + PE)"""

        without_hedge = self.get_margin_per_straddle(
            index, expiry_type, has_hedge=False, num_baskets=num_baskets
        )
        with_hedge = self.get_margin_per_straddle(
            index, expiry_type, has_hedge=True, num_baskets=num_baskets
        )

        return without_hedge - with_hedge
```

### 3. Hedge Strike Selector Service

```python
# services/hedge_strike_selector.py

from typing import List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class HedgeCandidate:
    strike: int
    option_type: str  # CE or PE
    ltp: float
    otm_distance: int
    estimated_margin_benefit: float
    cost_per_lot: float
    mbpr: float  # Margin Benefit Per Rupee

class HedgeStrikeSelectorService:
    """Selects optimal hedge strikes based on margin benefit per rupee spent"""

    def __init__(
        self,
        openalgo_service,
        margin_calculator: MarginCalculatorService,
        config: HedgeConfig
    ):
        self.openalgo = openalgo_service
        self.margin_calc = margin_calculator
        self.config = config

    async def get_spot_price(self, index: IndexName) -> float:
        """Get current spot price for index"""
        symbol = "NIFTY 50" if index == IndexName.NIFTY else "SENSEX"
        # Implementation depends on OpenAlgo API
        quote = await self.openalgo.get_quote(symbol)
        return quote['ltp']

    async def get_option_chain(
        self,
        index: IndexName,
        expiry_date: str
    ) -> List[dict]:
        """Fetch option chain for index and expiry"""
        # Implementation depends on OpenAlgo/Kite API
        # Returns list of {strike, ce_ltp, pe_ltp, ce_oi, pe_oi, ...}
        pass

    async def find_hedge_candidates(
        self,
        index: IndexName,
        expiry_date: str,
        option_types: List[str],  # ['CE', 'PE'] or ['CE'] or ['PE']
        num_baskets: int
    ) -> List[HedgeCandidate]:
        """Find all valid hedge strike candidates"""

        spot = await self.get_spot_price(index)
        chain = await self.get_option_chain(index, expiry_date)

        candidates = []
        min_otm = self.config.min_otm_distance[index.value]
        max_otm = self.config.max_otm_distance[index.value]

        for row in chain:
            strike = row['strike']

            for opt_type in option_types:
                ltp_key = f"{opt_type.lower()}_ltp"
                ltp = row.get(ltp_key, 0)

                # Check premium range
                if not (self.config.min_premium <= ltp <= self.config.max_premium):
                    continue

                # Calculate OTM distance
                if opt_type == 'CE':
                    otm_distance = strike - spot
                    if otm_distance < min_otm or otm_distance > max_otm:
                        continue
                else:  # PE
                    otm_distance = spot - strike
                    if otm_distance < min_otm or otm_distance > max_otm:
                        continue

                # Calculate cost and benefit
                lot_size = 75 if index == IndexName.NIFTY else 20
                lots_per_basket = 1 if index == IndexName.NIFTY else 10
                total_lots = lots_per_basket * num_baskets

                cost_per_lot = ltp * lot_size
                total_cost = cost_per_lot * total_lots

                # Estimate margin benefit (simplified - ideally use basket_margins API)
                # For now, use average benefit percentage
                expiry_type = ExpiryType.ZERO_DTE  # Assume 0DTE for hedge calculation
                margin_without = self.margin_calc.get_margin_per_straddle(
                    index, expiry_type, has_hedge=False, num_baskets=num_baskets
                )
                margin_with = self.margin_calc.get_margin_per_straddle(
                    index, expiry_type, has_hedge=True, num_baskets=num_baskets
                )
                estimated_benefit = (margin_without - margin_with) / 2  # Per leg

                # MBPR = Margin Benefit Per Rupee
                mbpr = estimated_benefit / total_cost if total_cost > 0 else 0

                candidates.append(HedgeCandidate(
                    strike=strike,
                    option_type=opt_type,
                    ltp=ltp,
                    otm_distance=int(otm_distance),
                    estimated_margin_benefit=estimated_benefit,
                    cost_per_lot=cost_per_lot,
                    mbpr=mbpr
                ))

        # Sort by MBPR (highest first)
        candidates.sort(key=lambda x: x.mbpr, reverse=True)

        return candidates

    async def select_optimal_hedges(
        self,
        index: IndexName,
        expiry_date: str,
        margin_reduction_needed: float,
        short_positions: List[dict],  # Current short positions
        num_baskets: int
    ) -> List[HedgeCandidate]:
        """
        Select optimal hedge strikes to achieve required margin reduction
        with minimum cost
        """

        # Determine which sides need hedging based on short positions
        ce_shorts = sum(1 for p in short_positions if 'CE' in p['symbol'])
        pe_shorts = sum(1 for p in short_positions if 'PE' in p['symbol'])

        option_types = []
        if ce_shorts > 0:
            option_types.append('CE')
        if pe_shorts > 0:
            option_types.append('PE')

        if not option_types:
            return []

        # Get candidates
        candidates = await self.find_hedge_candidates(
            index, expiry_date, option_types, num_baskets
        )

        if not candidates:
            return []

        # Greedy selection: pick best MBPR until reduction achieved
        selected = []
        total_benefit = 0
        total_cost = 0

        for candidate in candidates:
            if total_benefit >= margin_reduction_needed:
                break

            # Check if we already have this side covered
            selected_types = [s.option_type for s in selected]
            if candidate.option_type in selected_types:
                continue  # One hedge per side

            selected.append(candidate)
            total_benefit += candidate.estimated_margin_benefit
            total_cost += candidate.cost_per_lot * num_baskets

        return selected
```

### 4. Hedge Executor Service

```python
# services/hedge_executor.py

from typing import Optional, List
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

@dataclass
class HedgeOrder:
    symbol: str
    exchange: str
    strike: int
    option_type: str
    quantity: int
    lots: int
    action: str  # BUY or SELL
    order_type: str  # MARKET or LIMIT
    price: Optional[float]

@dataclass
class HedgeResult:
    success: bool
    order_id: Optional[str]
    executed_price: Optional[float]
    error_message: Optional[str]

class HedgeExecutorService:
    """Executes hedge orders via OpenAlgo API"""

    def __init__(
        self,
        openalgo_service,
        telegram_service,
        db_session,
        config: HedgeConfig
    ):
        self.openalgo = openalgo_service
        self.telegram = telegram_service
        self.db = db_session
        self.config = config
        self._last_action_time = None

    def _check_cooldown(self) -> bool:
        """Check if cooldown period has passed"""
        if self._last_action_time is None:
            return True

        elapsed = (datetime.now(IST) - self._last_action_time).total_seconds()
        return elapsed >= self.config.cooldown_seconds

    def _build_symbol(
        self,
        index: IndexName,
        expiry_date: str,  # YYYY-MM-DD
        strike: int,
        option_type: str
    ) -> str:
        """Build trading symbol from components"""
        # Convert date format
        from datetime import datetime
        dt = datetime.strptime(expiry_date, "%Y-%m-%d")

        # Format: NIFTY30DEC2525800PE
        date_str = dt.strftime("%d%b%y").upper()  # 30DEC25

        return f"{index.value}{date_str}{strike}{option_type}"

    async def execute_hedge_buy(
        self,
        session_id: int,
        candidate: HedgeCandidate,
        index: IndexName,
        expiry_date: str,
        num_baskets: int,
        trigger_reason: str,
        utilization_before: float
    ) -> HedgeResult:
        """Execute a hedge buy order"""

        # Check cooldown
        if not self._check_cooldown():
            return HedgeResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message="Cooldown period not elapsed"
            )

        # Build order details
        lot_size = 75 if index == IndexName.NIFTY else 20
        lots_per_basket = 1 if index == IndexName.NIFTY else 10
        total_lots = lots_per_basket * num_baskets
        quantity = total_lots * lot_size

        symbol = self._build_symbol(
            index, expiry_date, candidate.strike, candidate.option_type
        )
        exchange = "NFO" if index == IndexName.NIFTY else "BFO"

        # Use limit order with buffer
        limit_price = round(candidate.ltp + 0.10, 2)

        # Log pending transaction
        transaction_id = await self.db.execute(
            """
            INSERT INTO auto_hedge.hedge_transactions
            (session_id, action, trigger_reason, symbol, exchange, strike,
             option_type, quantity, lots, order_price, utilization_before, order_status)
            VALUES (:session_id, 'BUY', :trigger_reason, :symbol, :exchange, :strike,
                    :option_type, :quantity, :lots, :price, :util_before, 'PENDING')
            RETURNING id
            """,
            {
                "session_id": session_id,
                "trigger_reason": trigger_reason,
                "symbol": symbol,
                "exchange": exchange,
                "strike": candidate.strike,
                "option_type": candidate.option_type,
                "quantity": quantity,
                "lots": total_lots,
                "price": limit_price,
                "util_before": utilization_before
            }
        )

        # Execute order via OpenAlgo
        try:
            order_response = await self.openalgo.place_order(
                symbol=symbol,
                exchange=exchange,
                action="BUY",
                product="NRML",
                price_type="LIMIT",
                price=limit_price,
                quantity=quantity
            )

            order_id = order_response.get('orderid')

            # Update transaction
            await self.db.execute(
                """
                UPDATE auto_hedge.hedge_transactions
                SET order_id = :order_id, order_status = 'SUCCESS',
                    executed_price = :price, total_cost = :cost
                WHERE id = :id
                """,
                {
                    "id": transaction_id,
                    "order_id": order_id,
                    "price": limit_price,
                    "cost": limit_price * quantity
                }
            )

            # Record active hedge
            await self.db.execute(
                """
                INSERT INTO auto_hedge.active_hedges
                (session_id, transaction_id, symbol, exchange, strike,
                 option_type, quantity, entry_price, otm_distance, is_active)
                VALUES (:session_id, :tx_id, :symbol, :exchange, :strike,
                        :option_type, :quantity, :price, :otm_dist, true)
                """,
                {
                    "session_id": session_id,
                    "tx_id": transaction_id,
                    "symbol": symbol,
                    "exchange": exchange,
                    "strike": candidate.strike,
                    "option_type": candidate.option_type,
                    "quantity": quantity,
                    "price": limit_price,
                    "otm_dist": candidate.otm_distance
                }
            )

            self._last_action_time = datetime.now(IST)

            # Send Telegram alert
            await self._send_buy_alert(
                symbol, candidate, limit_price, quantity,
                trigger_reason, utilization_before
            )

            return HedgeResult(
                success=True,
                order_id=order_id,
                executed_price=limit_price,
                error_message=None
            )

        except Exception as e:
            # Update transaction as failed
            await self.db.execute(
                """
                UPDATE auto_hedge.hedge_transactions
                SET order_status = 'FAILED', error_message = :error
                WHERE id = :id
                """,
                {"id": transaction_id, "error": str(e)}
            )

            # Send failure alert
            await self._send_failure_alert(symbol, str(e), trigger_reason)

            return HedgeResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=str(e)
            )

    async def execute_hedge_exit(
        self,
        hedge_id: int,
        session_id: int,
        trigger_reason: str,
        utilization_before: float
    ) -> HedgeResult:
        """Exit an existing hedge position"""

        # Get hedge details
        hedge = await self.db.fetch_one(
            "SELECT * FROM auto_hedge.active_hedges WHERE id = :id AND is_active = true",
            {"id": hedge_id}
        )

        if not hedge:
            return HedgeResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message="Hedge not found or already exited"
            )

        # Get current price
        quote = await self.openalgo.get_quote(hedge['symbol'], hedge['exchange'])
        current_price = quote['ltp']

        # Don't sell if value too low
        if current_price < 0.50:
            return HedgeResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=f"Hedge value too low ({current_price}), letting expire"
            )

        # Execute sell order
        # ... similar to buy logic ...
        pass

    async def _send_buy_alert(
        self,
        symbol: str,
        candidate: HedgeCandidate,
        price: float,
        quantity: int,
        trigger_reason: str,
        util_before: float
    ):
        """Send Telegram alert for hedge buy"""
        message = f"""🛡️ *HEDGE BOUGHT*

*Symbol:* `{symbol}`
*Strike:* {candidate.strike} {candidate.option_type}
*Quantity:* {quantity}
*Price:* ₹{price}
*Total Cost:* ₹{price * quantity:,.0f}

*Trigger:* {trigger_reason}
*Utilization Before:* {util_before:.1f}%
*OTM Distance:* {candidate.otm_distance} points

*Time:* {datetime.now(IST).strftime('%H:%M:%S')}"""

        await self.telegram.send_message(message, parse_mode="Markdown")

    async def _send_failure_alert(
        self,
        symbol: str,
        error: str,
        trigger_reason: str
    ):
        """Send Telegram alert for failed order"""
        message = f"""❌ *HEDGE ORDER FAILED*

*Symbol:* `{symbol}`
*Trigger:* {trigger_reason}
*Error:* {error}

*Time:* {datetime.now(IST).strftime('%H:%M:%S')}

⚠️ Manual intervention may be required!"""

        await self.telegram.send_message(message, parse_mode="Markdown")
```

### 5. Auto-Hedge Orchestrator Service

```python
# services/auto_hedge_orchestrator.py

from datetime import datetime
import asyncio
import pytz

IST = pytz.timezone('Asia/Kolkata')

class AutoHedgeOrchestratorService:
    """
    Main orchestrator that monitors margin and triggers hedge actions
    Runs as background task during market hours
    """

    def __init__(
        self,
        margin_monitor_service,      # Existing margin monitor
        strategy_scheduler: StrategySchedulerService,
        margin_calculator: MarginCalculatorService,
        hedge_selector: HedgeStrikeSelectorService,
        hedge_executor: HedgeExecutorService,
        telegram_service,
        db_session,
        config: HedgeConfig
    ):
        self.margin_monitor = margin_monitor_service
        self.scheduler = strategy_scheduler
        self.margin_calc = margin_calculator
        self.hedge_selector = hedge_selector
        self.executor = hedge_executor
        self.telegram = telegram_service
        self.db = db_session
        self.config = config

        self._is_running = False
        self._session = None

    async def start(self):
        """Start the auto-hedge monitoring loop"""
        self._is_running = True

        # Load today's session
        self._session = await self._get_or_create_session()

        if not self._session:
            await self.telegram.send_message(
                "⚠️ Auto-hedge: No session configured for today"
            )
            return

        if not self._session['auto_hedge_enabled']:
            await self.telegram.send_message(
                "ℹ️ Auto-hedge is disabled for today's session"
            )
            return

        await self.telegram.send_message(
            f"🚀 *Auto-Hedge Started*\n\n"
            f"Index: {self._session['index_name']}\n"
            f"Baskets: {self._session['num_baskets']}\n"
            f"Budget: ₹{self._session['total_budget']:,.0f}"
        )

        # Start monitoring loop
        while self._is_running:
            try:
                await self._check_and_act()
            except Exception as e:
                await self.telegram.send_message(f"❌ Auto-hedge error: {str(e)}")

            await asyncio.sleep(30)  # Check every 30 seconds

    async def stop(self):
        """Stop the auto-hedge monitoring loop"""
        self._is_running = False
        await self.telegram.send_message("🛑 Auto-hedge stopped")

    async def _check_and_act(self):
        """Main check cycle - called every 30 seconds"""

        now = datetime.now(IST)

        # Only run during market hours (9:15 - 15:30)
        market_open = now.replace(hour=9, minute=15, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)

        if not (market_open <= now <= market_close):
            return

        # Get current margin status
        margin_data = await self.margin_monitor.get_current_status()
        current_util = margin_data['utilization_pct']
        current_intraday = margin_data['intraday_margin']
        total_budget = self._session['total_budget']

        # Check if entry is imminent
        is_imminent, next_entry, seconds_until = await self.scheduler.is_entry_imminent()

        if is_imminent and next_entry:
            await self._handle_imminent_entry(
                next_entry, seconds_until,
                current_util, current_intraday, total_budget
            )
        else:
            # Check if we should exit hedges
            await self._check_hedge_exit(
                current_util, current_intraday, total_budget
            )

    async def _handle_imminent_entry(
        self,
        entry: StrategyEntry,
        seconds_until: int,
        current_util: float,
        current_intraday: float,
        total_budget: float
    ):
        """Handle logic when a strategy entry is imminent"""

        index = IndexName(self._session['index_name'])
        expiry_type = ExpiryType(self._session['expiry_type'])
        num_baskets = self._session['num_baskets']

        # Calculate margin for next entry (without hedge)
        margin_for_entry = self.margin_calc.get_margin_per_straddle(
            index, expiry_type, has_hedge=False, num_baskets=num_baskets
        )

        # Calculate projected utilization
        projected_util = self.margin_calc.calculate_projected_utilization(
            current_intraday, total_budget, margin_for_entry
        )

        # Log strategy execution tracking
        await self.db.execute(
            """
            INSERT INTO auto_hedge.strategy_executions
            (session_id, portfolio_name, scheduled_entry_time,
             utilization_before, projected_utilization, hedge_required)
            VALUES (:session_id, :portfolio, :entry_time, :util_before, :util_proj, :hedge_req)
            ON CONFLICT (session_id, portfolio_name) DO UPDATE
            SET utilization_before = :util_before, projected_utilization = :util_proj,
                hedge_required = :hedge_req, updated_at = NOW()
            """,
            {
                "session_id": self._session['id'],
                "portfolio": entry.portfolio_name,
                "entry_time": entry.entry_time,
                "util_before": current_util,
                "util_proj": projected_util,
                "hedge_req": projected_util > self.config.entry_trigger_pct
            }
        )

        # Check if hedge is needed
        if projected_util > self.config.entry_trigger_pct:
            await self._execute_hedge_entry(
                entry, current_util, projected_util,
                current_intraday, total_budget, margin_for_entry
            )
        else:
            # Send info alert if close to threshold
            if projected_util > 85:
                await self.telegram.send_message(
                    f"ℹ️ *Entry in {seconds_until}s*\n\n"
                    f"Portfolio: {entry.portfolio_name}\n"
                    f"Current: {current_util:.1f}%\n"
                    f"Projected: {projected_util:.1f}%\n"
                    f"Hedge: Not required ✓",
                    parse_mode="Markdown"
                )

    async def _execute_hedge_entry(
        self,
        entry: StrategyEntry,
        current_util: float,
        projected_util: float,
        current_intraday: float,
        total_budget: float,
        margin_for_entry: float
    ):
        """Execute hedge buy before strategy entry"""

        index = IndexName(self._session['index_name'])
        expiry_type = ExpiryType(self._session['expiry_type'])
        num_baskets = self._session['num_baskets']
        expiry_date = self._session['expiry_date'].isoformat()

        # Calculate margin reduction needed
        reduction_needed = self.margin_calc.calculate_margin_reduction_needed(
            current_intraday, total_budget, margin_for_entry,
            target_pct=self.config.entry_target_pct
        )

        # Get current short positions to determine hedge side
        positions = await self.margin_monitor.get_filtered_positions()
        short_positions = positions.get('short_positions', [])

        # Select optimal hedges
        hedges = await self.hedge_selector.select_optimal_hedges(
            index, expiry_date, reduction_needed, short_positions, num_baskets
        )

        if not hedges:
            await self.telegram.send_message(
                f"⚠️ *No suitable hedge found!*\n\n"
                f"Portfolio: {entry.portfolio_name}\n"
                f"Projected util: {projected_util:.1f}%\n"
                f"Reduction needed: ₹{reduction_needed:,.0f}",
                parse_mode="Markdown"
            )
            return

        # Execute hedge orders
        for hedge in hedges:
            trigger_reason = f"PRE_STRATEGY:{entry.portfolio_name}"

            result = await self.executor.execute_hedge_buy(
                session_id=self._session['id'],
                candidate=hedge,
                index=index,
                expiry_date=expiry_date,
                num_baskets=num_baskets,
                trigger_reason=trigger_reason,
                utilization_before=current_util
            )

            if not result.success:
                await self.telegram.send_message(
                    f"⚠️ Hedge failed: {result.error_message}"
                )

    async def _check_hedge_exit(
        self,
        current_util: float,
        current_intraday: float,
        total_budget: float
    ):
        """Check if hedges should be exited"""

        # Only consider exit if utilization is low
        if current_util > self.config.exit_trigger_pct:
            return

        # Check if any entry is coming soon
        entries_soon = await self.scheduler.get_entries_in_window(
            self.config.exit_buffer_minutes
        )

        if entries_soon:
            return  # Keep hedges for upcoming entry

        # Get active hedges
        active_hedges = await self.db.fetch_all(
            """
            SELECT * FROM auto_hedge.active_hedges
            WHERE session_id = :session_id AND is_active = true
            ORDER BY otm_distance DESC  -- Exit farthest first
            """,
            {"session_id": self._session['id']}
        )

        if not active_hedges:
            return

        # Consider exiting farthest OTM hedge
        farthest_hedge = active_hedges[0]

        # Get current price
        quote = await self.margin_monitor.openalgo.get_quote(
            farthest_hedge['symbol'], farthest_hedge['exchange']
        )
        current_price = quote.get('ltp', 0)

        # Only exit if has meaningful value
        if current_price >= 0.50:
            await self.executor.execute_hedge_exit(
                hedge_id=farthest_hedge['id'],
                session_id=self._session['id'],
                trigger_reason="EXCESS_MARGIN",
                utilization_before=current_util
            )

    async def _get_or_create_session(self):
        """Get or create today's session"""
        today = datetime.now(IST).date()

        session = await self.db.fetch_one(
            "SELECT * FROM auto_hedge.daily_session WHERE session_date = :date",
            {"date": today}
        )

        return session
```

---

## API Endpoints

```python
# api/hedge_routes.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import date

router = APIRouter(prefix="/api/hedge", tags=["Auto-Hedge"])

@router.get("/status")
async def get_hedge_status(
    orchestrator: AutoHedgeOrchestratorService = Depends(get_orchestrator)
):
    """Get current auto-hedge status"""
    session = orchestrator._session

    if not session:
        return {"status": "no_session", "message": "No session configured"}

    active_hedges = await orchestrator.db.fetch_all(
        "SELECT * FROM auto_hedge.active_hedges WHERE session_id = :id AND is_active = true",
        {"id": session['id']}
    )

    next_entry = await orchestrator.scheduler.get_next_entry()

    return {
        "status": "running" if orchestrator._is_running else "stopped",
        "session": {
            "date": session['session_date'],
            "index": session['index_name'],
            "baskets": session['num_baskets'],
            "budget": session['total_budget'],
            "auto_hedge_enabled": session['auto_hedge_enabled']
        },
        "active_hedges": [
            {
                "symbol": h['symbol'],
                "strike": h['strike'],
                "option_type": h['option_type'],
                "quantity": h['quantity'],
                "entry_price": h['entry_price'],
                "otm_distance": h['otm_distance']
            }
            for h in active_hedges
        ],
        "next_entry": {
            "portfolio": next_entry[0].portfolio_name if next_entry else None,
            "seconds_until": next_entry[1] if next_entry else None
        } if next_entry else None
    }

@router.post("/toggle")
async def toggle_auto_hedge(
    enabled: bool,
    db = Depends(get_db)
):
    """Enable or disable auto-hedge for today"""
    today = date.today()

    await db.execute(
        """
        UPDATE auto_hedge.daily_session
        SET auto_hedge_enabled = :enabled, updated_at = NOW()
        WHERE session_date = :date
        """,
        {"enabled": enabled, "date": today}
    )

    return {"success": True, "auto_hedge_enabled": enabled}

@router.post("/manual/buy")
async def manual_hedge_buy(
    strike: int,
    option_type: str,  # CE or PE
    executor: HedgeExecutorService = Depends(get_executor),
    orchestrator: AutoHedgeOrchestratorService = Depends(get_orchestrator)
):
    """Manually trigger a hedge buy"""
    session = orchestrator._session

    if not session:
        raise HTTPException(400, "No active session")

    # Get current margin status
    margin_data = await orchestrator.margin_monitor.get_current_status()

    # Create hedge candidate manually
    from services.hedge_strike_selector import HedgeCandidate

    candidate = HedgeCandidate(
        strike=strike,
        option_type=option_type,
        ltp=0,  # Will be fetched
        otm_distance=0,
        estimated_margin_benefit=0,
        cost_per_lot=0,
        mbpr=0
    )

    result = await executor.execute_hedge_buy(
        session_id=session['id'],
        candidate=candidate,
        index=IndexName(session['index_name']),
        expiry_date=session['expiry_date'].isoformat(),
        num_baskets=session['num_baskets'],
        trigger_reason="MANUAL",
        utilization_before=margin_data['utilization_pct']
    )

    return {
        "success": result.success,
        "order_id": result.order_id,
        "error": result.error_message
    }

@router.get("/transactions")
async def get_hedge_transactions(
    session_date: Optional[date] = None,
    db = Depends(get_db)
):
    """Get hedge transaction history"""
    if session_date is None:
        session_date = date.today()

    transactions = await db.fetch_all(
        """
        SELECT t.*, s.session_date
        FROM auto_hedge.hedge_transactions t
        JOIN auto_hedge.daily_session s ON t.session_id = s.id
        WHERE s.session_date = :date
        ORDER BY t.timestamp DESC
        """,
        {"date": session_date}
    )

    return {"transactions": transactions}

@router.get("/schedule")
async def get_strategy_schedule(
    day: Optional[str] = None,
    scheduler: StrategySchedulerService = Depends(get_scheduler)
):
    """Get strategy schedule for a day"""
    if day is None:
        entries = await scheduler.get_today_schedule()
    else:
        entries = await scheduler.db.fetch_all(
            """
            SELECT portfolio_name, entry_time, exit_time
            FROM auto_hedge.strategy_schedule
            WHERE day_of_week = :day AND is_active = true
            ORDER BY entry_time
            """,
            {"day": day}
        )

    return {"schedule": entries}

@router.put("/schedule")
async def update_strategy_schedule(
    day_of_week: str,
    entries: List[dict],
    db = Depends(get_db)
):
    """Update strategy schedule for a day"""
    # Delete existing entries for the day
    await db.execute(
        "DELETE FROM auto_hedge.strategy_schedule WHERE day_of_week = :day",
        {"day": day_of_week}
    )

    # Insert new entries
    for entry in entries:
        await db.execute(
            """
            INSERT INTO auto_hedge.strategy_schedule
            (day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time)
            VALUES (:day, :index, :expiry, :portfolio, :entry, :exit)
            """,
            {
                "day": day_of_week,
                "index": entry['index_name'],
                "expiry": entry['expiry_type'],
                "portfolio": entry['portfolio_name'],
                "entry": entry['entry_time'],
                "exit": entry.get('exit_time')
            }
        )

    return {"success": True, "entries_updated": len(entries)}

@router.get("/analytics")
async def get_hedge_analytics(
    days: int = 30,
    db = Depends(get_db)
):
    """Get hedge analytics for the past N days"""
    analytics = await db.fetch_all(
        """
        SELECT
            s.session_date,
            s.day_of_week,
            s.index_name,
            s.num_baskets,
            COUNT(t.id) as hedge_count,
            SUM(CASE WHEN t.action = 'BUY' THEN t.total_cost ELSE 0 END) as total_cost,
            SUM(CASE WHEN t.action = 'SELL' THEN t.total_cost ELSE 0 END) as total_recovered,
            MAX(t.utilization_before) as peak_utilization
        FROM auto_hedge.daily_session s
        LEFT JOIN auto_hedge.hedge_transactions t ON s.id = t.session_id
        WHERE s.session_date >= CURRENT_DATE - :days
        GROUP BY s.id
        ORDER BY s.session_date DESC
        """,
        {"days": days}
    )

    return {"analytics": analytics}
```

---

## Configuration

### Environment Variables

```bash
# .env

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/portfolio_manager
AUTO_HEDGE_SCHEMA=auto_hedge

# OpenAlgo
OPENALGO_BASE_URL=http://127.0.0.1:5000
OPENALGO_API_KEY=your_api_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Hedge Configuration
HEDGE_ENTRY_TRIGGER_PCT=95
HEDGE_ENTRY_TARGET_PCT=85
HEDGE_EXIT_TRIGGER_PCT=70
HEDGE_LOOKAHEAD_MINUTES=5
HEDGE_EXIT_BUFFER_MINUTES=15
HEDGE_MIN_PREMIUM=2
HEDGE_MAX_PREMIUM=6
HEDGE_MAX_COST_PER_DAY=50000
HEDGE_COOLDOWN_SECONDS=120

# Defaults
DEFAULT_BUDGET_PER_BASKET=1000000
```

### Strategy Schedule Seed Data

```sql
-- Monday - Nifty 1DTE
INSERT INTO auto_hedge.strategy_schedule (day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time) VALUES
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 1', '09:19:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 2', '09:22:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 3', '09:52:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 4', '10:58:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 5', '12:38:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 6', '13:52:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 7', '14:04:00', '15:25:00');

-- Tuesday - Nifty 0DTE (Expiry)
INSERT INTO auto_hedge.strategy_schedule (day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time) VALUES
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 1', '09:16:00', '14:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 2', '09:24:00', '14:00:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 3', '09:29:00', '14:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 4', '10:16:30', '13:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 5', '13:53:30', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 6', '14:11:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 7', '14:16:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 8', '14:25:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 9', '14:28:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 10', '14:35:00', NULL);

-- Thursday - Sensex 0DTE (Expiry)
INSERT INTO auto_hedge.strategy_schedule (day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time) VALUES
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 1', '09:16:00', '14:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 2', '09:18:00', '13:15:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 3', '09:28:00', '14:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 4', '09:55:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 5', '10:53:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 6', '11:02:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 7', '11:37:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 8', '12:09:00', '15:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 9', '12:54:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 10', '13:58:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 11', '14:04:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 12', '14:34:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 13', '14:43:00', NULL);

-- Friday - Nifty 2DTE
INSERT INTO auto_hedge.strategy_schedule (day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time) VALUES
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 1', '09:19:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 2', '09:25:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 3', '09:33:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 4', '09:40:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 5', '10:50:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 6', '11:38:10', '15:25:00');
```

---

## File Structure

```
auto-hedge/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── hedge_routes.py
│   │   └── schemas.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── strategy_scheduler.py
│   │   ├── margin_calculator.py
│   │   ├── hedge_strike_selector.py
│   │   ├── hedge_executor.py
│   │   ├── auto_hedge_orchestrator.py
│   │   └── telegram_service.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── db_models.py
│   │   └── constants.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── symbol_parser.py
│
├── alembic/
│   └── versions/
│       └── 001_create_auto_hedge_schema.py
│
├── tests/
│   ├── __init__.py
│   ├── test_margin_calculator.py
│   ├── test_strategy_scheduler.py
│   ├── test_hedge_selector.py
│   └── test_orchestrator.py
│
├── scripts/
│   └── seed_schedule.sql
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_margin_calculator.py

import pytest
from services.margin_calculator import MarginCalculatorService
from models.constants import HedgeConfig, IndexName, ExpiryType

@pytest.fixture
def calculator():
    return MarginCalculatorService(HedgeConfig())

def test_margin_per_straddle_sensex_0dte_no_hedge(calculator):
    """Test Sensex 0DTE margin without hedge - 1 basket"""
    margin = calculator.get_margin_per_straddle(
        IndexName.SENSEX, ExpiryType.ZERO_DTE,
        has_hedge=False, num_baskets=1
    )
    assert margin == pytest.approx(366666.67, rel=0.01)

def test_margin_per_straddle_sensex_0dte_with_hedge(calculator):
    """Test Sensex 0DTE margin with hedge - 1 basket"""
    margin = calculator.get_margin_per_straddle(
        IndexName.SENSEX, ExpiryType.ZERO_DTE,
        has_hedge=True, num_baskets=1
    )
    assert margin == pytest.approx(160000.00, rel=0.01)

def test_margin_scaling_15_baskets(calculator):
    """Test margin scales correctly with basket count"""
    margin_1 = calculator.get_margin_per_straddle(
        IndexName.SENSEX, ExpiryType.ZERO_DTE,
        has_hedge=False, num_baskets=1
    )
    margin_15 = calculator.get_margin_per_straddle(
        IndexName.SENSEX, ExpiryType.ZERO_DTE,
        has_hedge=False, num_baskets=15
    )
    assert margin_15 == margin_1 * 15

def test_projected_utilization(calculator):
    """Test projected utilization calculation"""
    # Budget: 1.5Cr, Current: 85L, Next entry: 55L
    projected = calculator.calculate_projected_utilization(
        current_intraday_margin=8500000,
        total_budget=15000000,
        margin_for_next_entry=5500000
    )
    # (85 + 55) / 150 * 100 = 93.33%
    assert projected == pytest.approx(93.33, rel=0.01)

def test_hedge_required_below_threshold(calculator):
    """Test hedge not required when projected < threshold"""
    required = calculator.calculate_hedge_required(
        current_utilization=70.0,
        projected_utilization=90.0
    )
    assert required == False  # 90% < 95% trigger

def test_hedge_required_above_threshold(calculator):
    """Test hedge required when projected > threshold"""
    required = calculator.calculate_hedge_required(
        current_utilization=85.0,
        projected_utilization=120.0
    )
    assert required == True  # 120% > 95% trigger
```

### Integration Tests

```python
# tests/test_orchestrator.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.auto_hedge_orchestrator import AutoHedgeOrchestratorService

@pytest.fixture
def mock_services():
    return {
        'margin_monitor': AsyncMock(),
        'scheduler': AsyncMock(),
        'margin_calc': MagicMock(),
        'hedge_selector': AsyncMock(),
        'executor': AsyncMock(),
        'telegram': AsyncMock(),
        'db': AsyncMock(),
        'config': HedgeConfig()
    }

@pytest.mark.asyncio
async def test_no_hedge_when_projected_under_threshold(mock_services):
    """Test no hedge action when projected utilization is safe"""
    orchestrator = AutoHedgeOrchestratorService(**mock_services)
    orchestrator._session = {
        'id': 1,
        'index_name': 'SENSEX',
        'expiry_type': '0DTE',
        'num_baskets': 15,
        'total_budget': 15000000
    }

    # Current util 50%, projected 80%
    mock_services['margin_monitor'].get_current_status.return_value = {
        'utilization_pct': 50.0,
        'intraday_margin': 7500000
    }
    mock_services['scheduler'].is_entry_imminent.return_value = (
        True,
        StrategyEntry(portfolio_name='EXP_3', entry_time=time(9,28), exit_time=None),
        60
    )
    mock_services['margin_calc'].calculate_projected_utilization.return_value = 80.0

    await orchestrator._check_and_act()

    # Should not call hedge executor
    mock_services['executor'].execute_hedge_buy.assert_not_called()

@pytest.mark.asyncio
async def test_hedge_triggered_when_projected_over_threshold(mock_services):
    """Test hedge is triggered when projected utilization exceeds threshold"""
    orchestrator = AutoHedgeOrchestratorService(**mock_services)
    orchestrator._session = {
        'id': 1,
        'index_name': 'SENSEX',
        'expiry_type': '0DTE',
        'num_baskets': 15,
        'total_budget': 15000000,
        'expiry_date': date(2026, 1, 1)
    }

    # Current util 85%, projected 120%
    mock_services['margin_monitor'].get_current_status.return_value = {
        'utilization_pct': 85.0,
        'intraday_margin': 12750000
    }
    mock_services['margin_monitor'].get_filtered_positions.return_value = {
        'short_positions': [{'symbol': 'SENSEX01JAN2680000CE'}]
    }
    mock_services['scheduler'].is_entry_imminent.return_value = (
        True,
        StrategyEntry(portfolio_name='EXP_4', entry_time=time(9,55), exit_time=None),
        60
    )
    mock_services['margin_calc'].calculate_projected_utilization.return_value = 120.0
    mock_services['margin_calc'].calculate_margin_reduction_needed.return_value = 5000000
    mock_services['hedge_selector'].select_optimal_hedges.return_value = [
        HedgeCandidate(strike=79000, option_type='CE', ltp=4.5,
                       otm_distance=1000, estimated_margin_benefit=3000000,
                       cost_per_lot=90, mbpr=33333)
    ]
    mock_services['executor'].execute_hedge_buy.return_value = HedgeResult(
        success=True, order_id='12345', executed_price=4.5, error_message=None
    )

    await orchestrator._check_and_act()

    # Should call hedge executor
    mock_services['executor'].execute_hedge_buy.assert_called_once()
```

---

## Deployment Notes

### Starting the Service

```python
# main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    orchestrator = get_orchestrator()
    task = asyncio.create_task(orchestrator.start())

    yield

    # Shutdown
    await orchestrator.stop()
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.include_router(hedge_routes.router)
```

### Scheduler Integration

The auto-hedge system integrates with the existing margin monitor scheduler:

```python
# Add to existing scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Daily session setup at 9:00 AM
scheduler.add_job(
    setup_daily_session,
    CronTrigger(day_of_week='mon-fri', hour=9, minute=0),
    id='setup_daily_session'
)

# EOD summary at 3:35 PM
scheduler.add_job(
    generate_eod_hedge_summary,
    CronTrigger(day_of_week='mon-fri', hour=15, minute=35),
    id='eod_hedge_summary'
)
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Hedge trigger accuracy | 100% - never miss required hedge |
| False positive rate | < 5% - don't buy unnecessary hedges |
| Execution latency | < 2 seconds from trigger to order |
| Daily hedge cost | Minimize - only spend when needed |
| Order success rate | > 99% |
| Alert delivery | < 5 seconds |

---

## Future Enhancements (Phase 2)

1. **Basket Margins API Integration**
   - Use Kite's `basket_margins` API for precise margin simulation
   - Replace estimated hedge benefit with actual calculation

2. **Machine Learning Optimization**
   - Learn optimal hedge timing from historical data
   - Predict margin spikes based on market volatility

3. **Multi-Account Support**
   - Manage hedges across multiple trading accounts
   - Aggregate margin utilization

4. **Advanced Exit Logic**
   - Consider hedge P&L when deciding exits
   - Roll hedges to different strikes if beneficial

5. **Stoxxo Integration**
   - API to disable Stoxxo's static hedges when our system is active
   - Prevent duplicate hedge orders
