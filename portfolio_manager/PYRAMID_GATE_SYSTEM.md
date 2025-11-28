# Pyramid Gate System

## Overview

The pyramid system uses a **Two-Gate** architecture where BOTH gates must pass for a pyramid entry to trigger.

```
                         PYRAMID TRIGGER
                               │
               ┌───────────────┴───────────────┐
               │                               │
         ┌─────▼─────┐                   ┌─────▼─────┐
         │  GATE 1   │        AND        │  GATE 2   │
         │  1R Gate  │                   │  ATR Gate │
         │ (one-time)│                   │ (spacing) │
         └───────────┘                   └───────────┘
```

---

## Gate 1: 1R Gate (Profitability Gate)

**Purpose:** Ensure trade is profitable enough before ANY pyramiding begins.

### Calculation
```
1R = Entry Price - Initial Stop Price

With Tom Basso stops (1.0× ATR initial):
  Initial Stop = Entry - (1.0 × ATR)
  Therefore: 1R ≈ 1.0 × ATR

Gate Opens When:
  Price Move from Entry > 1R
```

### Key Property: CAPITAL INDEPENDENT
- Uses pure price math: `(current_price - entry_price) > (entry_price - stop_price)`
- No position size or capital involved
- Both Pine Script and Portfolio Manager calculate identical values

### Example
```
Entry Price:    50,000
Initial Stop:   49,500 (using 1.0× ATR where ATR = 500)
1R:             500 points

Gate opens when price > 50,500 (moved more than 500 from entry)
```

---

## Gate 2: ATR Spacing Gate

**Purpose:** Ensure proper SPACING between consecutive pyramid entries.

### Calculation
```
Price Move from Last = Current Price - Last Pyramid Price
ATR Moves = Price Move from Last / ATR

Gate Passes When:
  ATR Moves >= atr_pyramid_spacing
```

### Instrument-Specific Spacing

| Instrument | ATR Spacing | Rationale |
|------------|-------------|-----------|
| Bank Nifty | 0.75 ATR | Wider spacing, fewer but higher-quality pyramids |
| Gold Mini | 0.5 ATR | Tighter spacing, more pyramid opportunities |

### Key Property: RESETS EACH PYRAMID
- Gate 1 opens once and stays open
- Gate 2 must pass for EACH pyramid entry
- Prevents clustering of pyramids too close together

### Example
```
Base Entry:     50,000
ATR:            500
Spacing:        0.5 ATR = 250 points

Pyramid 1 allowed when: price > 50,250 (AND Gate 1 open)
Pyramid 2 allowed when: price > Pyr1_price + 250
```

---

## Combined Gate Logic

| Pyramid | Gate 1 (1R from ENTRY) | Gate 2 (ATR from LAST) |
|---------|------------------------|------------------------|
| Pyr 1   | price > entry + 1R     | price > entry + ATR×spacing |
| Pyr 2   | ✓ (already open)       | price > pyr1 + ATR×spacing |
| Pyr 3   | ✓ (already open)       | price > pyr2 + ATR×spacing |
| Pyr 4   | ✓ (already open)       | price > pyr3 + ATR×spacing |
| Pyr 5   | ✓ (already open)       | price > pyr4 + ATR×spacing |

### Practical Effect (Tom Basso with 1.0× ATR stop)

Since 1R ≈ 1.0 ATR:
- **First pyramid:** needs ~1 ATR move (1R gate is stricter than 0.5-0.75 ATR spacing)
- **Subsequent pyramids:** need ATR×spacing from previous entry

---

## Capital Independence Analysis

### Why 1R Gate is Capital-Independent

| Component | Calculation | Uses Capital? |
|-----------|-------------|---------------|
| Entry Price | Market price at entry | No |
| Initial Stop | Entry - (1.0 × ATR) | No |
| 1R (initial risk) | Entry - Stop | No |
| Price Move | Current - Entry | No |
| **Gate Check** | **Move > 1R** | **No** |

### Alternative: Profit-Based Gate (Capital-Dependent)

```
// OLD approach (use_1r_gate = false)
accumulated_profit = current_equity - initial_capital  // Uses capital!
base_risk = (entry - stop) × position_size × lot_size  // Uses position size!

Gate Opens When: accumulated_profit > base_risk
```

**Problem:** Position size depends on capital, so:
- Pine Script with ₹25L calculates different base_risk than PM with ₹50L
- Signal timing diverges between Pine Script and Portfolio Manager

**Solution:** Use `use_1r_gate = true` for capital-independent signaling.

---

## Pine Script ↔ Portfolio Manager Alignment

### Aligned Settings (V7.0)

| Parameter | Bank Nifty Pine | Gold Mini Pine | Portfolio Manager |
|-----------|-----------------|----------------|-------------------|
| `use_1r_gate` | `true` | `true` | `true` |
| `atr_pyramid_spacing` | 0.75 | 0.5 | Instrument-specific |
| `initial_capital` | ₹50L | ₹50L | ₹50L (shared pool) |

### Code Locations

**Pine Script (BankNifty_TF_V7.0.pine):**
```pine
// Line 488-490: 1R calculation
initial_risk_points = initial_entry_price - initial_stop_price
price_move_from_entry = close - initial_entry_price
price_move_in_r = price_move_from_entry / initial_risk_points

// Line 505: Gate check
pyramid_gate_open = use_1r_gate ?
    (price_move_from_entry > initial_risk_points) :
    (accumulated_profit > base_risk)

// Line 516: Combined check
if pyramid_gate_open and atr_moves >= atr_pyramid_threshold
```

**Portfolio Manager (pyramid_gate.py):**
```python
# Lines 127-134: 1R calculation
price_move = signal.price - base_position.entry_price
initial_risk = base_position.entry_price - base_position.initial_stop

if price_move <= initial_risk:
    return False, f"Price not > 1R"

# Lines 137-141: ATR spacing
atr_moves = price_move_from_last / signal.atr
if atr_moves < self.config.atr_pyramid_spacing:
    return False, f"ATR spacing insufficient"
```

---

## Full Example: Bank Nifty Trade

### Setup
```
Capital:        ₹50,00,000 (shared pool)
Entry Price:    50,000
ATR:            400
Initial Stop:   50,000 - (1.0 × 400) = 49,600
1R:             400 points
ATR Spacing:    0.75 ATR = 300 points (Bank Nifty)
```

### Pyramid Progression

| Event | Price | Gate 1 (>1R=400) | Gate 2 (>0.75 ATR=300) | Result |
|-------|-------|------------------|------------------------|--------|
| Entry | 50,000 | - | - | Base position |
| Bar 1 | 50,200 | ❌ (200 < 400) | ✓ | No pyramid |
| Bar 2 | 50,450 | ✓ (450 > 400) | ✓ (450 > 300) | **Pyr 1** @ 50,450 |
| Bar 3 | 50,600 | ✓ (open) | ❌ (150 < 300) | No pyramid |
| Bar 4 | 50,800 | ✓ (open) | ✓ (350 > 300) | **Pyr 2** @ 50,800 |
| Bar 5 | 51,150 | ✓ (open) | ✓ (350 > 300) | **Pyr 3** @ 51,150 |

### Why Capital Doesn't Affect Signal Timing

Both Pine Script and PM calculate:
- 1R = 50,000 - 49,600 = **400 points** ✓
- Gate opens at 50,400+ regardless of capital setting
- PM calculates its OWN position size from ₹50L pool
- Signal timing is identical between Pine and PM

---

## Additional Gates (Portfolio Manager Only)

PM enforces two extra gates not present in Pine Script:

### 1. Portfolio Risk Gate
```python
if projected_risk_pct > self.config.pyramid_risk_block:  # 12%
    return False, "Portfolio risk exceeded"
```
Prevents pyramiding if portfolio-level risk would exceed 12%.

### 2. Profit Gate
```python
total_pnl = sum(p.unrealized_pnl for p in positions)
if total_pnl <= 0:
    return False, "Instrument P&L negative"
```
Requires instrument's combined positions to be profitable before allowing pyramid.

These gates are enforced by PM even if Pine Script sends the pyramid signal.

---

## Position Sizing (Separate from Gating)

After gates pass, position size is calculated independently:

### Pine Script: Triple Constraint
```pine
lot_a = free_margin / margin_per_lot          // Margin constraint
lot_b = initial_position_size × 0.5           // Geometric scaling
lot_c = available_risk_budget / risk_per_lot  // Profit protection

pyramid_lots = MIN(lot_a, lot_b, lot_c)
```

### Portfolio Manager: Tom Basso 3-Constraint
```python
lot_r = (equity × 0.5%) / risk_per_lot × ER   // Risk-based
lot_v = (equity × 0.2%) / vol_per_lot         // Volatility-based
lot_m = available_margin / margin_per_lot     // Margin-based

final_lots = FLOOR(MIN(lot_r, lot_v, lot_m))
```

**Key Point:** PM calculates position size from its ₹50L shared pool, not from Pine Script's calculation.

---

## Summary

| Aspect | Pine Script | Portfolio Manager | Match? |
|--------|-------------|-------------------|--------|
| 1R Gate Logic | `price_move > initial_risk` | `price_move > initial_risk` | ✓ |
| ATR Spacing | Configurable per instrument | Configurable per instrument | ✓ |
| Capital for Gating | Not used (1R is price-based) | Not used (1R is price-based) | ✓ |
| Position Sizing | Own calculation | Tom Basso 3-constraint | PM overrides |
| Additional Gates | None | Risk + Profit gates | PM adds |

The 1R gate ensures **signal timing is identical** between Pine Script and PM, while PM handles position sizing and additional risk controls independently.
