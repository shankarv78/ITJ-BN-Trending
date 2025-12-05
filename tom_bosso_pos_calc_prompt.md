# Prompt: Create Tom Basso Position Sizing Calculator

## Objective

Create a locally running web app that calculates position sizing for **base entry trades** using Tom Basso's **3-Constraint Position Sizing Method** for two instruments: **Bank Nifty** and **Gold Mini**.

---

## Background: Tom Basso's 3-Constraint Method

Tom Basso, featured in Van Tharp's "The Definitive Guide to Position Sizing", uses a methodology that applies **three independent constraints** to determine position size. The final position is the **minimum** of all three constraints, ensuring risk is controlled from multiple angles.

### The Three Constraints for Base Entry

1. **Lot-R (Risk-based Constraint):** Limits the maximum loss per trade as a percentage of equity
2. **Lot-V (Volatility-based Constraint):** Limits daily portfolio volatility exposure
3. **Lot-M (Margin-based Constraint):** Ensures sufficient margin is available

**Final Position Size = FLOOR(MIN(Lot-R, Lot-V, Lot-M))**

The FLOOR function ensures we can only trade whole lots (no fractional positions).

---

## Formulas

### Constraint 1: Risk-Based Lots (Lot-R)

```
Lot-R = (Equity × Risk%) / ((Entry Price - Stop Price) × Point Value) × ER
```

Where:
- **Equity:** Current portfolio value in Rupees
- **Risk%:** Maximum risk per trade (default: 0.5%)
- **Entry Price:** Price at which you enter the trade
- **Stop Price:** SuperTrend stop loss level
- **Point Value:** Rupees per point movement per lot (instrument-specific)
- **ER:** Efficiency Ratio (trend strength multiplier, 0 to 1)

**Purpose:** Ensures you never risk more than X% of your equity on any single trade.

### Constraint 2: Volatility-Based Lots (Lot-V)

```
Lot-V = (Equity × Volatility%) / (ATR × Point Value)
```

Where:
- **Equity:** Current portfolio value in Rupees
- **Volatility%:** Maximum daily volatility exposure (default: 0.2%)
- **ATR:** Average True Range (14-period) - measures market volatility
- **Point Value:** Rupees per point movement per lot

**Purpose:** Limits how much your portfolio can swing on a daily basis due to market volatility.

### Constraint 3: Margin-Based Lots (Lot-M)

```
Lot-M = Available Margin / Margin Per Lot
```

Where:
- **Available Margin:** Free cash/margin available for new positions (in Rupees)
- **Margin Per Lot:** Required margin per lot for the instrument

**Purpose:** Prevents over-leveraging by ensuring you have sufficient margin.

### Final Position Size

```
Final Lots = FLOOR(MIN(Lot-R, Lot-V, Lot-M))
Final Lots = MAX(0, Final Lots)  // Ensure non-negative
```

The **limiting factor** is whichever constraint produced the smallest value:
- If MIN = Lot-R → Limited by **RISK**
- If MIN = Lot-V → Limited by **VOLATILITY**
- If MIN = Lot-M → Limited by **MARGIN**

---

## Instrument Parameters

### Bank Nifty (Index Futures)

| Parameter | Value | Description |
|-----------|-------|-------------|
| Lot Size | 30 units | Units per contract (as of 2025) |
| Point Value | ₹30 per point per lot | Rupees earned/lost per 1-point move per lot |
| Margin Per Lot | ₹2,70,000 | Required margin per lot (~15% of notional) |

**Note:** Bank Nifty lot size changed from 15→25→30→35 over the years. Current lot size as of late 2024/2025 is 30.

### Gold Mini (Commodity Futures)

| Parameter | Value | Description |
|-----------|-------|-------------|
| Lot Size | 100 grams | Grams per contract |
| Point Value | ₹10 per point per lot | Rupees earned/lost per ₹1 move per lot |
| Margin Per Lot | ₹1,05,000 | Required margin per lot (conservative estimate) |

**Note:** Gold Mini is quoted per 10 grams, but the contract is for 100 grams, hence ₹10 per ₹1 move.

---

## Default Risk Parameters

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| Initial Risk % | 0.5% | Maximum risk on new base entries |
| Initial Volatility % | 0.2% | Maximum volatility exposure on new entries |
| Ongoing Risk % | 1.0% | Risk threshold for existing positions |
| Ongoing Volatility % | 0.5% | Volatility threshold for existing positions |

---

## Spreadsheet Structure

### Sheet 1: Calculator

#### Section A: Portfolio Inputs (User Editable)

| Row | Label | Cell | Description |
|-----|-------|------|-------------|
| 1 | **PORTFOLIO PARAMETERS** | | Section header |
| 2 | Current Equity (₹) | B2 | Total portfolio value |
| 3 | Available Margin (₹) | B3 | Free margin for new trades |
| 4 | Initial Risk % | B4 | Default: 0.5 |
| 5 | Initial Volatility % | B5 | Default: 0.2 |

#### Section B: Instrument Selection (Dropdown)

| Row | Label | Cell | Description |
|-----|-------|------|-------------|
| 7 | **INSTRUMENT** | | Section header |
| 8 | Select Instrument | B8 | Dropdown: "Bank Nifty" or "Gold Mini" |

#### Section C: Signal Inputs (From TradingView)

| Row | Label | Cell | Description |
|-----|-------|------|-------------|
| 10 | **TRADINGVIEW SIGNAL DATA** | | Section header |
| 11 | Entry Price | B11 | Current close price |
| 12 | Stop Price (SuperTrend) | B12 | SuperTrend value |
| 13 | ATR (Average True Range) | B13 | 14-period ATR |
| 14 | ER (Efficiency Ratio) | B14 | Value between 0 and 1 |

#### Section D: Instrument Parameters (Auto-Populated)

| Row | Label | Cell | Formula |
|-----|-------|------|---------|
| 16 | **INSTRUMENT PARAMETERS** | | Section header |
| 17 | Lot Size | B17 | `=IF(B8="Bank Nifty", 30, 100)` |
| 18 | Point Value (₹) | B18 | `=IF(B8="Bank Nifty", 30, 10)` |
| 19 | Margin Per Lot (₹) | B19 | `=IF(B8="Bank Nifty", 270000, 105000)` |

#### Section E: Calculations

| Row | Label | Cell | Formula |
|-----|-------|------|---------|
| 21 | **CONSTRAINT CALCULATIONS** | | Section header |
| 22 | Risk Amount (₹) | B22 | `=B2 * (B4/100)` |
| 23 | Risk Per Point | B23 | `=B11 - B12` |
| 24 | Risk Per Lot (₹) | B24 | `=B23 * B18` |
| 25 | **Lot-R (Risk-based)** | B25 | `=IF(B24>0, (B22/B24)*B14, 0)` |
| 26 | | | |
| 27 | Volatility Budget (₹) | B27 | `=B2 * (B5/100)` |
| 28 | Volatility Per Lot (₹) | B28 | `=B13 * B18` |
| 29 | **Lot-V (Volatility-based)** | B29 | `=IF(B28>0, B27/B28, 0)` |
| 30 | | | |
| 31 | **Lot-M (Margin-based)** | B31 | `=IF(B19>0, B3/B19, 0)` |

#### Section F: Results

| Row | Label | Cell | Formula |
|-----|-------|------|---------|
| 33 | **FINAL POSITION SIZE** | | Section header |
| 34 | Minimum Constraint | B34 | `=MIN(B25, B29, B31)` |
| 35 | **FINAL LOTS** | B35 | `=MAX(0, FLOOR(B34, 1))` |
| 36 | Limiting Factor | B36 | `=IF(B35=0, "INVALID", IF(B34=B25, "RISK", IF(B34=B29, "VOLATILITY", "MARGIN")))` |

#### Section G: Risk Metrics

| Row | Label | Cell | Formula |
|-----|-------|------|---------|
| 38 | **RISK METRICS** | | Section header |
| 39 | Actual Risk (₹) | B39 | `=B35 * B24` |
| 40 | Risk % of Equity | B40 | `=IF(B2>0, (B39/B2)*100, 0)` |
| 41 | Actual Volatility (₹) | B41 | `=B35 * B28` |
| 42 | Volatility % of Equity | B42 | `=IF(B2>0, (B41/B2)*100, 0)` |
| 43 | Margin Required (₹) | B43 | `=B35 * B19` |
| 44 | Margin % Used | B44 | `=IF(B3>0, (B43/B3)*100, 0)` |

---

## Example Calculations

### Example 1: Bank Nifty Entry

**Inputs:**
- Equity: ₹50,00,000 (50 Lakhs)
- Available Margin: ₹30,00,000 (30 Lakhs)
- Entry Price: 52,000
- Stop Price: 51,650
- ATR: 350 points
- ER: 0.82
- Risk %: 0.5%
- Volatility %: 0.2%

**Calculations:**

1. **Lot-R (Risk-based):**
   - Risk Amount = 50,00,000 × 0.5% = ₹25,000
   - Risk Per Point = 52,000 - 51,650 = 350 points
   - Risk Per Lot = 350 × 30 = ₹10,500
   - Lot-R = (25,000 / 10,500) × 0.82 = **1.95 lots**

2. **Lot-V (Volatility-based):**
   - Vol Budget = 50,00,000 × 0.2% = ₹10,000
   - Vol Per Lot = 350 × 30 = ₹10,500
   - Lot-V = 10,000 / 10,500 = **0.95 lots**

3. **Lot-M (Margin-based):**
   - Lot-M = 30,00,000 / 2,70,000 = **11.11 lots**

**Result:**
- Minimum = MIN(1.95, 0.95, 11.11) = 0.95
- **Final Lots = FLOOR(0.95) = 0 lots**
- **Limiting Factor: VOLATILITY**

*Note: With these conservative parameters, the volatility constraint limits position size. Consider increasing equity or reducing volatility % if 0 lots is not acceptable.*

### Example 2: Gold Mini Entry

**Inputs:**
- Equity: ₹50,00,000 (50 Lakhs)
- Available Margin: ₹30,00,000 (30 Lakhs)
- Entry Price: 78,500
- Stop Price: 77,800
- ATR: 450 points
- ER: 0.85
- Risk %: 0.5%
- Volatility %: 0.2%

**Calculations:**

1. **Lot-R (Risk-based):**
   - Risk Amount = 50,00,000 × 0.5% = ₹25,000
   - Risk Per Point = 78,500 - 77,800 = 700 points
   - Risk Per Lot = 700 × 10 = ₹7,000
   - Lot-R = (25,000 / 7,000) × 0.85 = **3.04 lots**

2. **Lot-V (Volatility-based):**
   - Vol Budget = 50,00,000 × 0.2% = ₹10,000
   - Vol Per Lot = 450 × 10 = ₹4,500
   - Lot-V = 10,000 / 4,500 = **2.22 lots**

3. **Lot-M (Margin-based):**
   - Lot-M = 30,00,000 / 1,05,000 = **28.57 lots**

**Result:**
- Minimum = MIN(3.04, 2.22, 28.57) = 2.22
- **Final Lots = FLOOR(2.22) = 2 lots**
- **Limiting Factor: VOLATILITY**

---

## Validation Rules

The spreadsheet should implement these validations:

1. **Entry > Stop:** For long positions, Entry Price must be greater than Stop Price
   - If Entry ≤ Stop: Display "INVALID - Entry must be above Stop for long positions"

2. **ATR > 0:** ATR must be positive
   - If ATR ≤ 0: Display "INVALID - ATR must be positive"

3. **ER Range:** ER should be between 0 and 1
   - If ER < 0 or ER > 1: Display "WARNING - ER typically between 0 and 1"

4. **Equity > 0:** Equity must be positive

5. **Margin > 0:** Available margin must be positive

---

## Additional Features (Optional)

### Feature 1: Side-by-Side Comparison
Add columns C and D to show both Bank Nifty and Gold Mini calculations simultaneously for portfolio planning.

### Feature 2: Conditional Formatting
- Green: Final Lots > 0
- Red: Final Lots = 0 or INVALID
- Yellow: Warning conditions (near limits)

### Feature 3: Summary Dashboard
Show:
- Total portfolio risk exposure across both instruments
- Combined margin utilization
- Equity allocation recommendations

### Feature 4: Historical Input Log
Add a sheet to log past signals and position sizes for record-keeping.

---

## Data Sources

The following data comes from **TradingView alerts** (JSON format):

```json
{
  "type": "BASE_ENTRY",
  "instrument": "BANK_NIFTY",
  "price": 52000,
  "stop": 51650,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650
}
```

**Field Mapping:**
- `price` → Entry Price (B11)
- `stop` or `supertrend` → Stop Price (B12)
- `atr` → ATR (B13)
- `er` → ER (B14)
- `instrument` → Instrument Selection (B8)

---

## Important Notes

1. **Lot Size Updates:** Bank Nifty lot size changes periodically. Verify current lot size with NSE before trading.

2. **Margin Updates:** Margin requirements vary by broker and market conditions. The values provided are conservative estimates.

3. **ER (Efficiency Ratio):** This measures trend strength. Higher ER = stronger trend = larger position allowed. If ER is not available from your signal, use 0.8 as a default.

4. **Conservative by Design:** The 3-constraint method is intentionally conservative. If you consistently get 0 lots, consider:
   - Increasing equity
   - Reducing risk/volatility percentages slightly
   - Waiting for tighter stop distances (stronger setups)

5. **This is for BASE ENTRIES only:** Pyramid position sizing uses different constraints (A, B, C method) and is not covered in this calculator.

---

## Summary

This spreadsheet calculates position size using Tom Basso's triple-constraint method:

| Constraint | What It Limits | Formula |
|------------|---------------|---------|
| Lot-R | Trade Risk | (Equity × Risk%) / (Stop Distance × Point Value) × ER |
| Lot-V | Daily Volatility | (Equity × Vol%) / (ATR × Point Value) |
| Lot-M | Margin Usage | Available Margin / Margin Per Lot |
| **Final** | **Most Conservative** | **FLOOR(MIN(Lot-R, Lot-V, Lot-M))** |

The calculator works for both **Bank Nifty** and **Gold Mini** with automatic parameter switching based on instrument selection.

