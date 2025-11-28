# Tom Basso Multi-Instrument Portfolio Management System
## Specification Document v1.0

**Author:** Claude (with Shankar)  
**Date:** 27 November 2025  
**Instruments:** MCX Gold Mini, NSE Banknifty Futures  
**Methodology:** Tom Basso Volatility-Based Position Sizing + Trend Following

---

## 1. Executive Summary

This specification defines a portfolio management system for trend-following strategies across multiple instruments (Gold Mini and Banknifty) using a shared capital pool. The system implements Tom Basso's three-pillar position sizing methodology: **Risk Control**, **Volatility Control**, and **Margin Control**, with a portfolio-level risk cap of 15%.

### Core Principles

1. **Capital is shared** - Both instruments draw from the same equity pool
2. **Risk budget is shared** - Total portfolio risk capped at 15% of equity
3. **Position size follows stop** - Never size first, then set stop (Tom Basso's cardinal rule)
4. **Volatility equalizes contribution** - Higher volatility = smaller position
5. **Peel off winners** - Reduce size when risk/volatility exceeds ongoing limits

---

## 2. Instrument Specifications

### 2.1 MCX Gold Mini

| Parameter | Value | Notes |
|-----------|-------|-------|
| Symbol | GOLDM | MCX Gold Mini |
| Lot Size | 100 grams | 1 lot = 100g |
| Tick Size | Re 1 | Minimum price movement |
| Point Value | Rs 10 per tick | 100g × Re 1 = Rs 100? Verify |
| Margin per Lot | Rs 1,05,000 | ~Rs 1.05 Lakhs |
| Trading Hours | 9:00 AM - 11:30 PM | MCX timings |
| ATR Period | 21 days | For volatility calculation |
| Typical ATR% | 0.6% - 1.2% | Daily volatility range |

### 2.2 NSE Banknifty Futures

| Parameter | Value | Notes |
|-----------|-------|-------|
| Symbol | BANKNIFTY | NSE F&O |
| Lot Size | 15 units | 1 lot = 15 × Index value |
| Tick Size | 0.05 | Minimum price movement |
| Point Value | Rs 15 per point | 15 units × Rs 1 |
| Margin per Lot | ~Rs 1,00,000 | Varies, ~Rs 1L approx |
| Trading Hours | 9:15 AM - 3:30 PM | NSE timings |
| ATR Period | 21 days | For volatility calculation |
| Typical ATR% | 1.0% - 2.5% | Daily volatility range |

### 2.3 Correlation Consideration

Gold and Banknifty are generally **low-correlated** assets:
- Gold: Safe haven, inversely correlated with risk appetite
- Banknifty: Risk asset, correlated with equity markets

This provides natural diversification benefit, but during market stress, correlations can spike. The portfolio risk cap handles this.

---

## 3. Position Sizing Framework

### 3.1 The Three Controls (Tom Basso Method)

Every position must satisfy ALL THREE constraints. Final position size = MIN(Risk-Based, Volatility-Based, Margin-Based).

```
┌─────────────────────────────────────────────────────────────────┐
│                    POSITION SIZING FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. SET STOP FIRST (Based on ATR or technical level)          │
│              ↓                                                  │
│   2. CALCULATE THREE LOT SIZES                                  │
│      ├── Lot-R: Risk-Based (stop distance)                     │
│      ├── Lot-V: Volatility-Based (ATR)                         │
│      └── Lot-M: Margin-Based (available margin)                │
│              ↓                                                  │
│   3. FINAL LOTS = MIN(Lot-R, Lot-V, Lot-M)                     │
│              ↓                                                  │
│   4. CHECK PORTFOLIO CONSTRAINTS                                │
│      ├── Total Risk < 15%?                                     │
│      └── Total Volatility < 5%?                                │
│              ↓                                                  │
│   5. EXECUTE OR REDUCE                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Risk-Based Position Sizing (Lot-R)

**Purpose:** Limit maximum loss per trade to X% of equity.

**Formula:**
```
Risk_Per_Lot = (Entry_Price - Stop_Price) × Point_Value
Lot_R = (Equity × Risk_Percent) / Risk_Per_Lot
```

**Parameters:**

| Position Type | Risk % (Initial) | Risk % (Ongoing) |
|---------------|------------------|------------------|
| Base Entry | 0.5% | 1.0% |
| Pyramid 1 | 0.25% | 0.5% |
| Pyramid 2+ | 0.15% | 0.3% |

**Example - Gold Mini:**
```
Equity = Rs 50,00,000 (50 Lakhs)
Entry = 78,500
Stop = 77,800 (700 points away)
Point_Value = Rs 10

Risk_Per_Lot = 700 × 10 = Rs 7,000
Risk_Budget = 50,00,000 × 0.5% = Rs 25,000
Lot_R = 25,000 / 7,000 = 3.57 → 3 lots
```

### 3.3 Volatility-Based Position Sizing (Lot-V)

**Purpose:** Limit daily P&L swings to Y% of equity.

**Formula:**
```
Volatility_Per_Lot = ATR(21) × Point_Value
Lot_V = (Equity × Volatility_Percent) / Volatility_Per_Lot
```

**Parameters:**

| Position Type | Volatility % (Initial) | Volatility % (Ongoing) |
|---------------|------------------------|------------------------|
| Base Entry | 0.20% | 0.30% |
| Pyramid 1 | 0.10% | 0.15% |
| Pyramid 2+ | 0.05% | 0.10% |

**Example - Gold Mini:**
```
Equity = Rs 50,00,000
ATR(21) = 450 points
Point_Value = Rs 10

Volatility_Per_Lot = 450 × 10 = Rs 4,500
Volatility_Budget = 50,00,000 × 0.20% = Rs 10,000
Lot_V = 10,000 / 4,500 = 2.22 → 2 lots
```

### 3.4 Margin-Based Position Sizing (Lot-M)

**Purpose:** Prevent over-leverage and maintain margin safety.

**Formula:**
```
Available_Margin = Equity × Margin_Utilization_Limit - Current_Margin_Used
Lot_M = Available_Margin / Margin_Per_Lot
```

**Parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Margin Utilization | 60% | Never use more than 60% of equity as margin |
| Warning Level | 50% | Alert when approaching limit |
| Emergency Level | 70% | Force reduce positions |

**Example:**
```
Equity = Rs 50,00,000
Max_Margin = 50,00,000 × 60% = Rs 30,00,000
Current_Margin = Rs 8,40,000 (4 lots Gold × 1.05L + 3 lots BN × 1.0L)
Available_Margin = 30,00,000 - 8,40,000 = Rs 21,60,000

Lot_M (Gold) = 21,60,000 / 1,05,000 = 20.5 → 20 lots
Lot_M (Banknifty) = 21,60,000 / 1,00,000 = 21.6 → 21 lots
```

### 3.5 Final Position Size

```
Final_Lots = MIN(Lot_R, Lot_V, Lot_M)
Final_Lots = MAX(Final_Lots, 0)  // Non-negative
Final_Lots = FLOOR(Final_Lots)   // Whole lots only
```

**Tracking the Limiter:**
Always log which constraint is the binding one:
- If Lot_R is smallest → "Risk Limited"
- If Lot_V is smallest → "Volatility Limited"  
- If Lot_M is smallest → "Margin Limited"

---

## 4. Portfolio-Level Risk Management

### 4.1 Portfolio Risk Budget

The combined risk across ALL instruments must not exceed 15% of total equity.

**Formula:**
```
Portfolio_Risk = Σ (Position_Risk for each open position)

Position_Risk = (Entry_Price - Current_Stop) × Lots × Point_Value

Portfolio_Risk_Percent = Portfolio_Risk / Equity × 100
```

**Thresholds:**

| Level | Portfolio Risk % | Action |
|-------|------------------|--------|
| Green | 0% - 10% | Normal operations, pyramiding allowed |
| Yellow | 10% - 12% | Caution, reduce pyramid sizes |
| Orange | 12% - 15% | Warning, no new pyramids |
| Red | > 15% | BLOCKED - Must reduce positions |

### 4.2 Portfolio Volatility Budget

Combined daily volatility exposure across all instruments.

**Formula:**
```
Portfolio_Volatility = Σ (ATR × Lots × Point_Value for each position)

Portfolio_Volatility_Percent = Portfolio_Volatility / Equity × 100
```

**Thresholds:**

| Level | Portfolio Vol % | Action |
|-------|-----------------|--------|
| Green | 0% - 3% | Normal operations |
| Yellow | 3% - 4% | Reduce new position sizes |
| Orange | 4% - 5% | No new positions |
| Red | > 5% | PEEL OFF required |

### 4.3 Instrument Allocation

Rather than fixed 50/50 allocation, use **inverse volatility weighting**:

**Formula:**
```
Weight_i = (1 / ATR%_i) / Σ(1 / ATR%_j for all instruments)
```

**Example:**
```
Gold ATR% = 0.8%
Banknifty ATR% = 1.6%

Gold_Weight = (1/0.8) / (1/0.8 + 1/1.6) = 1.25 / 1.875 = 66.7%
Banknifty_Weight = (1/1.6) / (1/0.8 + 1/1.6) = 0.625 / 1.875 = 33.3%
```

This means Gold gets 2× the capital allocation of Banknifty to equalize risk contribution.

**Implementation:**
```
Allocated_Capital_Gold = Total_Equity × Weight_Gold
Allocated_Capital_Banknifty = Total_Equity × Weight_Banknifty
```

---

## 5. Pyramiding Rules (Cross-Instrument)

### 5.1 Pyramid Prerequisites

Before ANY pyramid (in either instrument), check:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PYRAMID GATE CHECKS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   CHECK 1: Instrument-Level Gate                                │
│   ├── Price > 1R from entry? (optional, can disable)           │
│   └── Price > 0.5 ATR from last pyramid?                       │
│                                                                 │
│   CHECK 2: Portfolio-Level Gate                                 │
│   ├── Total Portfolio Risk < 12%?                              │
│   ├── Total Portfolio Volatility < 4%?                         │
│   └── Margin Utilization < 50%?                                │
│                                                                 │
│   CHECK 3: Profit Gate                                          │
│   ├── Combined unrealized P&L > 0?                             │
│   └── This instrument's P&L > base risk?                       │
│                                                                 │
│   ALL CHECKS PASS → Pyramid allowed                            │
│   ANY CHECK FAILS → Pyramid blocked                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Pyramid Sizing (Triple Constraint)

When pyramiding is allowed, size using the tightest of:

```
Pyramid_Lots = MIN(
    Lot_A,  // Margin constraint (free margin available)
    Lot_B,  // Discipline constraint (50% of previous layer)
    Lot_C   // Risk budget constraint (remaining portfolio risk budget)
)
```

**Lot-A (Margin):**
```
Free_Margin = Max_Margin - Current_Margin_Used
Lot_A = Free_Margin / Margin_Per_Lot
```

**Lot-B (Discipline - 50% Rule):**
```
Lot_B = Previous_Layer_Lots × 0.5
```

**Lot-C (Portfolio Risk Budget):**
```
Remaining_Risk_Budget = (15% - Current_Portfolio_Risk%) × Equity
Risk_Per_Lot = (Entry - Stop) × Point_Value
Lot_C = Remaining_Risk_Budget / Risk_Per_Lot
```

### 5.3 Maximum Pyramids per Instrument

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max Pyramids (Gold) | 3 | 4 total positions (base + 3) |
| Max Pyramids (Banknifty) | 2 | 3 total positions (base + 2) |
| Max Combined Positions | 7 | Across both instruments |

### 5.4 Cross-Instrument Pyramid Priority

When both instruments are trending and eligible for pyramids:

**Priority Logic:**
```
IF both_eligible:
    // Pyramid the one with MORE room in risk budget
    Gold_Risk_Headroom = Allocated_Risk_Gold - Current_Risk_Gold
    BN_Risk_Headroom = Allocated_Risk_BN - Current_Risk_BN
    
    IF Gold_Risk_Headroom > BN_Risk_Headroom:
        Pyramid Gold first
    ELSE:
        Pyramid Banknifty first
```

---

## 6. Ongoing Position Management

### 6.1 The "Peel Off" Mechanism

When a winning position grows too large (risk or volatility exceeds ongoing limits), reduce size.

**Trigger Conditions:**
```
Position_Risk% = (Entry - Current_Stop) × Lots × Point_Value / Equity × 100
Position_Vol% = ATR × Lots × Point_Value / Equity × 100

IF Position_Risk% > Ongoing_Risk_Limit (1.0%):
    Peel_Off_Required = TRUE
    
IF Position_Vol% > Ongoing_Vol_Limit (0.3%):
    Peel_Off_Required = TRUE
```

**Peel Off Calculation:**
```
// For Risk-based peel off:
Target_Risk = Equity × Ongoing_Risk_Limit
Current_Risk = (Entry - Stop) × Lots × Point_Value
Excess_Risk = Current_Risk - Target_Risk
Lots_To_Peel = CEIL(Excess_Risk / Risk_Per_Lot)

// For Volatility-based peel off:
Target_Vol = Equity × Ongoing_Vol_Limit
Current_Vol = ATR × Lots × Point_Value
Excess_Vol = Current_Vol - Target_Vol
Lots_To_Peel = CEIL(Excess_Vol / Vol_Per_Lot)

// Final peel off = MAX of both
Final_Peel = MAX(Risk_Peel, Vol_Peel)
```

### 6.2 Stop Management (Tom Basso ATR Trailing)

Each position has an independent trailing stop:

**On Entry:**
```
Initial_Stop = Entry_Price - (Initial_ATR_Mult × ATR)
Highest_Close = Entry_Price
```

**On Each Bar:**
```
Highest_Close = MAX(Highest_Close, Close)
Trailing_Stop = Highest_Close - (Trailing_ATR_Mult × ATR)
Current_Stop = MAX(Current_Stop, Trailing_Stop)  // Only ratchets UP
```

**Parameters:**

| Instrument | Initial ATR Mult | Trailing ATR Mult |
|------------|------------------|-------------------|
| Gold Mini | 1.0× | 2.0× |
| Banknifty | 1.5× | 2.5× |

### 6.3 Recalculation Frequency

| Calculation | Frequency | Trigger |
|-------------|-----------|---------|
| Position Risk | Every bar | Price change |
| Portfolio Risk | Every bar | Any position change |
| ATR | Daily close | EOD |
| Peel Off Check | Every bar | Risk/Vol threshold breach |
| Rebalance Check | Weekly | Sunday/Monday |

---

## 7. Entry and Exit Rules

### 7.1 Entry Conditions (Trend Following)

**Gold Mini (existing strategy):**
```
Long Entry:
  - Close > EMA(200)
  - Close > Donchian Upper (20)
  - RSI(6) > 70 (momentum confirmation)
  - ADX > 15 (trend strength)
  - Efficiency Ratio > 0.8 (trend quality)
  - Not a Doji candle
  - Date >= Start Date filter
```

**Banknifty (to be defined):**
```
Long Entry:
  - Close > EMA(50) [faster EMA for more volatile instrument]
  - Close > Donchian Upper (20)
  - RSI(6) > 65 [slightly lower threshold]
  - ADX > 20
  - VIX < 20 [volatility filter - optional]
```

### 7.2 Exit Conditions

**Primary Exit (Stop Hit):**
```
IF Close < Current_Stop:
    Exit position (all lots for that layer)
```

**Secondary Exit (Trend Reversal):**
```
IF Close < EMA(200) for 3 consecutive days:
    Exit all positions in that instrument
```

**Emergency Exit (Portfolio Risk Breach):**
```
IF Portfolio_Risk > 18%:
    Exit smallest profitable position first
    Repeat until Portfolio_Risk < 15%
```

---

## 8. Equity Tracking

### 8.1 Equity Types

| Equity Type | Definition | Used For |
|-------------|------------|----------|
| Closed Equity | Cash + Realized P&L | Conservative sizing |
| Open Equity | Closed + Unrealized P&L | Aggressive sizing |
| Blended Equity | Closed + 50% of Unrealized | Recommended (Tom Basso) |

**Recommendation:** Use Blended Equity for position sizing to balance between:
- Not giving back all gains (pure Open Equity risk)
- Not being too conservative (pure Closed Equity limitation)

### 8.2 Equity Update Frequency

```
// On each trade close:
Closed_Equity += Realized_P&L

// On each bar:
Open_Equity = Closed_Equity + Σ(Unrealized_P&L for all positions)
Blended_Equity = Closed_Equity + 0.5 × Σ(Unrealized_P&L)
```

### 8.3 Drawdown Monitoring

| Drawdown Level | Action |
|----------------|--------|
| 0% - 5% | Normal operations |
| 5% - 10% | Reduce initial risk% by 25% |
| 10% - 15% | Reduce initial risk% by 50%, no new positions |
| > 15% | Trading halt, review required |

---

## 9. Data Requirements

### 9.1 Real-Time Data

| Data Point | Source | Frequency |
|------------|--------|-----------|
| Gold Mini Price | MCX | Real-time |
| Banknifty Price | NSE | Real-time |
| Gold ATR(21) | Calculated | Daily |
| Banknifty ATR(21) | Calculated | Daily |

### 9.2 Position Tracking

For each open position, track:

```
Position = {
    instrument: "GOLDM" | "BANKNIFTY",
    layer: "BASE" | "PYR1" | "PYR2" | "PYR3",
    entry_price: float,
    entry_date: datetime,
    lots: int,
    initial_stop: float,
    current_stop: float,
    highest_close: float,
    unrealized_pnl: float,
    risk_contribution: float,    // % of equity
    vol_contribution: float      // % of equity
}
```

### 9.3 Portfolio State

```
Portfolio = {
    equity: {
        closed: float,
        open: float,
        blended: float
    },
    risk: {
        gold_risk_pct: float,
        banknifty_risk_pct: float,
        total_risk_pct: float
    },
    volatility: {
        gold_vol_pct: float,
        banknifty_vol_pct: float,
        total_vol_pct: float
    },
    margin: {
        used: float,
        available: float,
        utilization_pct: float
    },
    positions: [Position, ...],
    pyramid_gate: {
        gold_eligible: bool,
        banknifty_eligible: bool,
        portfolio_allows: bool
    }
}
```

---

## 10. Alerts and Notifications

### 10.1 Alert Types

| Alert | Condition | Priority |
|-------|-----------|----------|
| Entry Signal | Entry conditions met | High |
| Pyramid Available | All pyramid gates pass | Medium |
| Peel Off Required | Risk/Vol exceeds ongoing limit | High |
| Stop Approaching | Price within 0.5 ATR of stop | Medium |
| Stop Hit | Position exited | High |
| Portfolio Risk Warning | > 12% | High |
| Portfolio Risk Critical | > 15% | Critical |
| Margin Warning | Utilization > 50% | Medium |
| Margin Critical | Utilization > 60% | High |

### 10.2 Daily Summary Report

Generate EOD report with:

```
=== PORTFOLIO SUMMARY ===
Date: {date}
Blended Equity: Rs {equity}
Daily P&L: Rs {daily_pnl} ({daily_pnl_pct}%)

=== RISK METRICS ===
Total Portfolio Risk: {risk_pct}% (Limit: 15%)
Total Portfolio Volatility: {vol_pct}% (Limit: 5%)
Margin Utilization: {margin_pct}% (Limit: 60%)

=== POSITIONS ===
GOLD MINI:
  Base: {lots} lots @ {entry}, Stop: {stop}, P&L: Rs {pnl}
  PYR1: {lots} lots @ {entry}, Stop: {stop}, P&L: Rs {pnl}
  Risk Contribution: {gold_risk_pct}%
  
BANKNIFTY:
  Base: {lots} lots @ {entry}, Stop: {stop}, P&L: Rs {pnl}
  Risk Contribution: {bn_risk_pct}%

=== SIGNALS ===
Gold Pyramid: {eligible/blocked} - {reason}
Banknifty Pyramid: {eligible/blocked} - {reason}

=== ACTIONS REQUIRED ===
- {any peel off required}
- {any stop adjustments}
```

---

## 11. Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Update Gold Mini strategy with portfolio-level risk tracking
- [ ] Add volatility-based position sizing (Lot-V)
- [ ] Implement blended equity calculation
- [ ] Create portfolio state tracking variables

### Phase 2: Banknifty Integration (Week 3-4)
- [ ] Develop Banknifty trend-following strategy
- [ ] Implement shared equity pool logic
- [ ] Add cross-instrument pyramid gate
- [ ] Test with paper trading

### Phase 3: Advanced Features (Week 5-6)
- [ ] Implement peel-off mechanism
- [ ] Add inverse volatility allocation
- [ ] Create daily summary report
- [ ] Add all alert types

### Phase 4: Live Testing (Week 7-8)
- [ ] Deploy with minimal capital
- [ ] Monitor all metrics daily
- [ ] Fine-tune parameters based on real behavior
- [ ] Document learnings

---

## 12. Parameter Summary

### 12.1 Position Sizing Parameters

| Parameter | Gold Mini | Banknifty | Notes |
|-----------|-----------|-----------|-------|
| Initial Risk % | 0.5% | 0.5% | Per position |
| Ongoing Risk % | 1.0% | 1.0% | After trail begins |
| Initial Vol % | 0.2% | 0.2% | Per position |
| Ongoing Vol % | 0.3% | 0.3% | Maximum allowed |
| ATR Period | 21 | 21 | For volatility calc |

### 12.2 Portfolio Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Portfolio Risk | 15% | Tom Basso's limit |
| Max Portfolio Volatility | 5% | Daily swing limit |
| Max Margin Utilization | 60% | Safety buffer |
| Equity Type | Blended | 50% of unrealized |

### 12.3 Pyramid Parameters

| Parameter | Gold Mini | Banknifty | Notes |
|-----------|-----------|-----------|-------|
| Max Pyramids | 3 | 2 | Per instrument |
| Use 1R Gate | Optional | Optional | Can disable |
| ATR Spacing | 0.5 ATR | 0.5 ATR | Between pyramids |
| Size Ratio | 50% | 50% | Of previous layer |

### 12.4 Stop Loss Parameters

| Parameter | Gold Mini | Banknifty | Notes |
|-----------|-----------|-----------|-------|
| Initial ATR Mult | 1.0× | 1.5× | Wider for BN |
| Trailing ATR Mult | 2.0× | 2.5× | Wider for BN |
| ATR Period | 10 | 10 | For stop calc |

---

## 13. Appendix

### A. Formulas Quick Reference

```
// Risk-Based Lots
Lot_R = (Equity × Risk%) / ((Entry - Stop) × Point_Value)

// Volatility-Based Lots
Lot_V = (Equity × Vol%) / (ATR × Point_Value)

// Margin-Based Lots
Lot_M = (Max_Margin - Used_Margin) / Margin_Per_Lot

// Final Lots
Lots = FLOOR(MIN(Lot_R, Lot_V, Lot_M))

// Portfolio Risk
Portfolio_Risk% = Σ((Entry - Stop) × Lots × Point_Value) / Equity × 100

// Inverse Volatility Weight
Weight_i = (1/ATR%_i) / Σ(1/ATR%_j)

// Peel Off Lots
Peel_Lots = CEIL((Current_Risk - Target_Risk) / Risk_Per_Lot)
```

### B. Example Scenarios

**Scenario 1: Fresh Entry in Both Instruments**
```
Equity: Rs 50 Lakhs
Gold Entry: 78,500, Stop: 77,800, ATR: 450
Banknifty Entry: 52,000, Stop: 51,200, ATR: 700

Gold Lot_R = (50L × 0.5%) / (700 × 10) = 25,000 / 7,000 = 3.5 → 3 lots
Gold Lot_V = (50L × 0.2%) / (450 × 10) = 10,000 / 4,500 = 2.2 → 2 lots
Gold Final = MIN(3, 2, ...) = 2 lots

BN Lot_R = (50L × 0.5%) / (800 × 15) = 25,000 / 12,000 = 2.08 → 2 lots
BN Lot_V = (50L × 0.2%) / (700 × 15) = 10,000 / 10,500 = 0.95 → 0 lots!
BN needs lower vol% or wait for lower ATR
```

**Scenario 2: Portfolio Risk Check Before Pyramid**
```
Current Positions:
- Gold: 3 lots, risk = 700 × 3 × 10 = Rs 21,000 = 0.42%
- Banknifty: 2 lots, risk = 600 × 2 × 15 = Rs 18,000 = 0.36%

Total Portfolio Risk = 0.78% (well under 15%, pyramid OK)
```

### C. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 27 Nov 2025 | Initial specification |

---

*End of Specification*
