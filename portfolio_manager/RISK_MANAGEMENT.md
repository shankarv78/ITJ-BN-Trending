# ITJ Risk Management & Position Sizing Reference

## Overview

This document captures the **actual implementation** of risk management and position sizing in the Portfolio Manager (PM). It serves as the authoritative reference for how the system manages risk.

---

## Part 1: Position Sizing (Tom Basso 3-Constraint Method)

### Base Entry Sizing

**Formula:** `Final_Lots = FLOOR(MIN(Lot-R, Lot-M))`

> ⚠️ **Note:** Lot-V (Volatility) is calculated for reference/logging but **NOT used** in base entry sizing to match Pine Script behavior.

| Constraint | Formula | Description |
|------------|---------|-------------|
| **Lot-R** (Risk) | `(Equity × Risk%) / (Entry - Stop) / Point_Value × ER` | Risk-based sizing with efficiency ratio scaling |
| **Lot-V** (Volatility) | `(Equity × Vol%) / (ATR × Point_Value)` | *Reference only* - Not used in final MIN |
| **Lot-M** (Margin) | `Available_Margin / Margin_Per_Lot` | Margin constraint |

**Example (Silver Mini):**
```
Equity:         ₹50,00,000
Risk%:          1.0%
Entry:          95,000
Stop:           93,100 (2× ATR where ATR = 950)
Point_Value:    5 (₹5 per Re 1/kg for 5kg contract)
ER:             0.85

Risk_Amount = 50,00,000 × 0.01 = ₹50,000
Risk_Per_Point = 95,000 - 93,100 = 1,900
Risk_Per_Lot = 1,900 × 5 = ₹9,500

Lot-R = (50,000 / 9,500) × 0.85 = 4.47 → Floor = 4 lots
Lot-M = 40,00,000 / 2,00,000 = 20 lots

Final = MIN(4, 20) = 4 lots
```

### Pyramid Sizing (A, B, C Constraints)

**Formula:** `Final_Lots = FLOOR(MIN(A, B, C))`

| Constraint | Formula | Description |
|------------|---------|-------------|
| **Lot-A** (Margin) | `Available_Margin / Margin_Per_Lot` | Margin safety |
| **Lot-B** (Discipline) | `Base_Position × 0.5^(pyramid_count + 1)` | Geometric scaling |
| **Lot-C** (Risk Budget) | `(Profit_After_Base_Risk × 0.5) / Risk_Per_Lot` | Only risk profits |

**Geometric Scaling Table (Base = 10 lots):**

| Pyramid | Formula | lot_b | Description |
|---------|---------|-------|-------------|
| PYR1 (Long_2) | 10 × 0.5¹ | 5 | 50% of base |
| PYR2 (Long_3) | 10 × 0.5² | 2 | 25% of base |
| PYR3 (Long_4) | 10 × 0.5³ | 1 | 12.5% of base |
| PYR4 (Long_5) | 10 × 0.5⁴ | 0 | 6.25% → Blocked |

> **Key:** Later pyramids get smaller positions. PYR4+ typically blocked due to rounding to 0.

---

## Part 2: Stop Loss Management (Tom Basso ATR Trailing)

### Stop Formula

```
Initial_Stop = Entry_Price - (Initial_ATR_Mult × ATR)
Trailing_Stop = Highest_Close - (Trailing_ATR_Mult × ATR)
Current_Stop = MAX(Current_Stop, Trailing_Stop)  // Ratchet up only
```

### Instrument-Specific ATR Multipliers

| Instrument | Initial ATR Mult | Trailing ATR Mult | Rationale |
|------------|------------------|-------------------|-----------|
| **Gold Mini** | 1.0 | 2.0 | Lower volatility |
| **Silver Mini** | 2.0 | 3.0 | Higher volatility than gold |
| **Bank Nifty** | 1.5 | 2.5 | Index - moderate volatility |
| **Copper** | 3.0 | 5.0 | Highest volatility |

### Example (Silver Mini)

```
Entry:          95,000
ATR:            950
Initial Mult:   2.0
Trailing Mult:  3.0

Initial_Stop = 95,000 - (2.0 × 950) = 93,100

Later, when price reaches 98,000:
Highest_Close = 98,000
Trailing_Stop = 98,000 - (3.0 × 950) = 95,150
Current_Stop = MAX(93,100, 95,150) = 95,150  ← Ratcheted up!
```

### Stop as % of Entry Price

| Instrument | Typical ATR % | Initial Stop % | Max Trailing % |
|------------|---------------|----------------|----------------|
| Gold Mini | ~0.8% | ~0.8% | ~1.6% |
| Silver Mini | ~1.0% | ~2.0% | ~3.0% |
| Bank Nifty | ~0.8% | ~1.2% | ~2.0% |
| Copper | ~1.5% | ~4.5% | ~7.5% |

---

## Part 3: Risk Parameters

### Per-Trade Risk (ROTE - Risk of Total Equity)

| Parameter | Value | Location |
|-----------|-------|----------|
| Initial Risk % | 1.0% | `config.initial_risk_percent` |
| Ongoing Risk % | 1.0% | `config.ongoing_risk_percent` |
| Initial Vol % | 0.2-0.5% | `config.initial_vol_percent` (varies by instrument) |
| Ongoing Vol % | 0.3-0.7% | `config.ongoing_vol_percent` (varies by instrument) |

**ROTE Calculation:**
```
ROTE = Position_Size% × Stop_Loss%

Example:
- 4 lots Silver Mini = ₹8,00,000 notional = 16% of ₹50L equity
- Stop = 2% of entry price
- ROTE = 16% × 2% = 0.32% per trade
```

### Portfolio-Level Risk Caps

| Metric | Cap | Enforcement |
|--------|-----|-------------|
| Portfolio Risk | 12-15% | Pyramid gate blocks if exceeded |
| Margin Utilization | 60% | Position sizing respects margin |
| Max Positions | 5-8 | Pyramid gate: `max_pyramids` per instrument |

---

## Part 4: Comparison with Minervini Framework

| Minervini Concept | ITJ Implementation | Status |
|-------------------|-------------------|--------|
| **ROTE 1-2.5%** | 1% initial_risk_percent | ✅ Aligned |
| **Max Stop 8%** | ATR-based (varies 0.8-7.5%) | ⚠️ May exceed for Copper |
| **2R Breakeven** | ❌ Not implemented | 🔴 **Gap** |
| **Progressive Exposure** | Geometric pyramiding 50%→25%→12.5% | ✅ Aligned |
| **Scale Down on Losses** | Not automated | 🟡 Future |
| **AWLR Tracking** | Not tracked | 🟡 Future |
| **Sell Half at 2R** | Not implemented | 🟡 Future |
| **14-Day Consecutive Loss Test** | Not tested | 🟡 Future |

### Key Minervini Gap: 2R Breakeven

**Not Implemented.** Current behavior:
- Stop trails based on ATR from highest close
- No automatic move to breakeven at any R-multiple

**Proposed Enhancement:**
```python
def update_trailing_stop(self, position, current_price, current_atr):
    # Calculate R-multiple
    initial_risk = position.entry_price - position.initial_stop
    current_profit = current_price - position.entry_price
    r_multiple = current_profit / initial_risk if initial_risk > 0 else 0

    # MINERVINI RULE: Move to breakeven at 2R
    if r_multiple >= 2.0 and position.current_stop < position.entry_price:
        position.current_stop = position.entry_price
        logger.info(f"🎯 {position.position_id} moved to BREAKEVEN at 2R")

    # Continue with ATR trailing...
```

---

## Part 5: Instrument Configuration Summary

| Parameter | Gold Mini | Silver Mini | Bank Nifty | Copper |
|-----------|-----------|-------------|------------|--------|
| **Lot Size** | 100g | 5kg | 30 units | 2500kg |
| **Point Value** | ₹10/point | ₹5/Re 1 | ₹30/point | ₹2500/Re 1 |
| **Margin/Lot** | ₹1.05L | ₹2.0L | ₹2.7L | ₹3.0L |
| **Initial Risk %** | 1.0% | 1.0% | 1.0% | 1.0% |
| **Initial ATR Mult** | 1.0 | 2.0 | 1.5 | 3.0 |
| **Trailing ATR Mult** | 2.0 | 3.0 | 2.5 | 5.0 |
| **Max Pyramids** | 3 | 5 | 5 | 3 |

---

## Part 6: Code References

| Component | File | Key Methods |
|-----------|------|-------------|
| Position Sizing | `core/position_sizer.py` | `calculate_base_entry_size()`, `calculate_pyramid_size()` |
| Stop Management | `core/stop_manager.py` | `calculate_initial_stop()`, `update_trailing_stop()` |
| Risk Config | `core/config.py` | `INSTRUMENT_CONFIGS` |
| Pyramid Gating | `core/pyramid_gate.py` | `check_gate()` |
| Live Execution | `live/engine.py` | `_handle_base_entry_live()`, `_handle_pyramid_live()` |

---

## Part 7: Future Enhancements (Minervini-Inspired)

### Priority 1: 2R Breakeven Rule
- Move stop to entry price when profit ≥ 2R
- Protects profits, eliminates risk

### Priority 2: AWLR Dashboard
- Track (Avg Gain × Win%) / (Avg Loss × Loss%)
- Target: >2:1 ratio

### Priority 3: Max Stop Cap
- Hard limit of 8% stop loss
- `initial_stop = max(atr_stop, entry * 0.92)`

### Priority 4: Scale-Down on Losses
- Reduce position size after consecutive losses
- Progressive exposure system

---

*Last Updated: December 29, 2025*
*Based on: position_sizer.py, stop_manager.py, config.py*
