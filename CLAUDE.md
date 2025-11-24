# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🆕 LATEST UPDATE: v6.0 Release (November 16, 2025)

**Major Version Upgrade:** Bank Nifty v6.0 achieves exceptional performance through parameter reversion + ROC filter removal.

**Key v6 Changes:**
- **Maintained v5 Capacity**: 5 pyramids (6 total positions)
- **Reverted Parameters**: ER Period 5→3, ER Threshold 0.77→0.8, ATR 0.5→0.75, Risk 1.5%→2.0%
- **⚠️ CRITICAL: ROC Filter DISABLED** - Major change allowing unrestricted pyramiding (ATR-gated only)
- **Empirically Validated**: 27.5% CAGR, -25.08% DD, 923 trades, 52.98% win rate, 2.055 PF

**v6 Performance (Jan 1, 2009 — Nov 14, 2025):**
- CAGR: **27.5%** (vs v5 expected 19-24%, v4 22.59%)
- Max DD: **-25.08%** (vs v4 -24.87%)
- Win Rate: **52.98%** | Profit Factor: **2.055**
- Total Trades: **923** | Zero margin calls

**⚠️ CRITICAL for Users:**
- v6 requires `pyramiding=5` in Properties Tab + `use_roc_for_pyramids=FALSE`
- v6 = v5 capacity + v4 parameters + NO ROC constraint
- Always reference BANKNIFTY_V6_CHANGELOG.md when working with v6

## Repository Overview

This repository contains Pine Script trading strategies for trend-following on Bank Nifty (Indian index) and Gold Mini (MCX). The strategies implement sophisticated momentum-based systems with pyramiding, multiple stop-loss modes, and comprehensive risk management.

**Primary Instruments:**
- **Bank Nifty**: 75-minute timeframe, synthetic futures (ATM PE Sell + ATM CE Buy)
- **Gold Mini**: 60-minute timeframe, MCX Gold Mini 100g futures

**Strategy Philosophy:** Highly selective, quality-over-quantity trend following with strict entry conditions (7 conditions must align), pyramiding into winners, and adaptive position sizing.

## Key Strategy Files

### Production Strategies

1. **`trend_following_strategy_v6.pine`** - **LATEST** Bank Nifty implementation (v6.0) ⚡
   - **Empirically Validated**: 27.5% CAGR, -25.08% DD over 16.9 years (923 trades)
   - **Extended Pyramiding**: 5 pyramids = 6 total positions (from v5)
   - **Reverted Parameters**: ER(3)>0.8, ATR 0.75, Risk 2.0% (v4 values)
   - **⚠️ CRITICAL: ROC Filter DISABLED** - Unrestricted pyramiding (ATR-gated only)
   - **Stricter Entries**: ADX 30 (from v5, vs v4's 25)
   - Maintains: Historical lot sizing, Tom Basso default, calc_on_every_tick=FALSE, Commission 0.05%
   - 75-minute timeframe, pyramiding=5, initial capital ₹50L

2. **`trend_following_strategy_banknifty_v5.pine`** - Bank Nifty v5.0 (parameter-optimized)
   - Extended pyramiding (5 pyramids = 6 total positions)
   - Optimized entry parameters (ADX 30, ER Period 5, ER Threshold 0.77)
   - More pyramiding opportunities (ROC 2%, ATR 0.5)
   - Conservative risk (1.5% vs v4's 2.0%)
   - Lower commission (0.05% vs v4's 0.1%)
   - 75-minute timeframe, pyramiding=5, initial capital ₹50L

3. **`gold_trend_following_strategy_v5.pine`** - Latest Gold Mini implementation (v5.0)
   - Extended pyramiding (5 pyramids = 6 total positions)
   - ER Period 5, ER Threshold 0.77 (from Bank Nifty v5)
   - Preserved Gold-specific: ADX 20, ROC 5%, margin 0.75L, lot size 10
   - Achieved 20.23% CAGR over 10.6 years with -17.90% max drawdown (v4 baseline)
   - 60-minute timeframe, pyramiding=5, initial capital ₹50L

4. **`trend_following_strategy_banknifty_v4.pine`** - Bank Nifty v4.1 (baseline)
   - Baseline for v5/v6 comparison
   - 75-minute timeframe, pyramiding=3, initial capital ₹50L
   - 22.59% CAGR, -24.87% DD

5. **`trend_following_strategy_smart.pine`** - Bank Nifty v3 (smart info panel variant)
   - Context-aware UI panel (switches between entry conditions and trade management)
   - SuperTrend default stop loss mode
   - Used as baseline for v4 comparison

### Legacy/Backup Files

- `trend_following_strategy.pine` - Full info panel version (always shows all info)
- `trend_following_strategy_v6.pine` - Development version
- `trend_following_strategy_backup_2025-11-10.pine` - Pre-v4 backup

## Strategy Architecture

### Core Components

**7-Condition Entry System** (ALL must be TRUE):
1. RSI(6) > 70 - Momentum confirmation
2. Close > EMA(200) - Long-term uptrend
3. Close > Donchian Channel Upper(20) - Breakout confirmation
4. ADX(30) < 25 (Bank Nifty) / < 20 (Gold) - Low trend strength (allows new trend formation)
5. Efficiency Ratio(3) > 0.8 - Clean price action
6. Close > SuperTrend(10, 1.5) - Bullish trend
7. NOT a Doji - Body > 10% of candle range

**Position Sizing:**
- Risk-based: 2% of capital per trade (Bank Nifty), 1.5% (Gold)
- Efficiency Ratio multiplier scales position by trend quality
- Uses equity high watermark (not current equity)
- Formula: `lots = (equity_high × risk% / stop_distance / lot_size) × ER`

**Pyramiding System:**
- **v5**: Maximum 5 additional entries (6 total positions)
- **v4**: Maximum 3 additional entries (4 total positions)
- Triggers: 0.5 ATR (v5, Gold), 0.75 ATR (v4 Bank Nifty)
- Geometric sizing: 50% ratio (e.g., 12 lots → 6 → 3 → 1-2 → 0-1 → 0-1)
- Requires: profitability check + margin availability + ROC filter

**Stop Loss Modes** (3 options):
1. **SuperTrend**: All positions use single SuperTrend(10, 1.5) line
2. **Tom Basso** (v4 default): Independent ATR-based trailing stops per position
   - Initial stop: Entry - (1.0 × ATR)
   - Trailing: Highest close - (2.0 × ATR)
3. **Van Tharp**: Earlier positions trail to later entry prices (breakeven protection)

### Key Optimizations Evolution

**v5.0 Changes (Bank Nifty):**
- **Extended Pyramiding**: 3 → 5 pyramids (4 → 6 total positions)
- **Entry Selectivity**: ADX 25 → 30 (more selective, fewer base entries)
- **ER Refinement**: Period 3 → 5, Threshold 0.8 → 0.77 (smoother calculation)
- **Pyramid Opportunities**: ROC 3% → 2%, ATR 0.75 → 0.5 (more pyramids allowed)
- **Risk Reduction**: 2.0% → 1.5% risk per trade (25% smaller base positions)
- **Commission Update**: 0.1% → 0.05% (realistic futures rate)

**v5.0 Changes (Gold Mini):**
- **Extended Pyramiding**: 3 → 5 pyramids (6 total positions)
- **ER Refinement**: Period 3 → 5, Threshold 0.8 → 0.77 (from Bank Nifty v5)
- **Preserved Gold-specific**: ADX 20, ROC 5%, ATR 0.5 (unchanged)

**v4 Gold-Inspired Optimizations (Maintained in v5):**
- `calc_on_every_tick = FALSE` (reduced whipsaw)
- ROC filter ENABLED (prevents weak pyramids)
- Margin cushion: 2.7L per lot Bank Nifty, 0.75L Gold
- Tom Basso default stop mode (independent profit protection)
- Historical lot sizing (v4.1+): Dynamic lot sizes matching NSE contract changes

## Testing & Development Workflow

### TradingView Development

**Loading strategy:**
1. Open TradingView → Pine Editor
2. Copy Pine Script code
3. Paste into editor
4. Click "Add to Chart"

**⚠️ CRITICAL: Settings Verification Required**

TradingView has TWO places where settings can differ from code defaults:
1. **Inputs Tab** - User-configurable parameters (can be customized after loading)
2. **Properties Tab** - Strategy-level settings (often overlooked but CRITICAL)

**Essential settings to verify BEFORE backtesting:**

**Inputs Tab - Bank Nifty v5.0:**
- ADX Threshold: **30** (v5 update from 25)
- ER Period: **5** (v5 update from 3)
- ER Threshold: **0.77** (v5 update from 0.8)
- ROC Threshold %: **2.0** (v5 update from 3.0)
- Risk % of Capital: **1.5** (v5 update from 2.0)
- ATR Pyramid Threshold: **0.5** (v5 update from 0.75)
- Max Pyramids: **5** (v5 update from 3)

**Inputs Tab - Gold Mini v5.0:**
- ADX Threshold: **20** (Gold-specific, unchanged)
- ER Period: **5** (v5 update from 3)
- ER Threshold: **0.77** (v5 update from 0.8)
- ROC Threshold %: **5.0** (Gold-specific, unchanged)
- Risk % of Capital: **1.5** (unchanged)
- ATR Pyramid Threshold: **0.5** (unchanged)
- Max Pyramids: **5** (v5 update from 3)

**Properties Tab (CRITICAL - overrides code):**
- Initial capital: **5000000** (₹50L)
- Pyramiding: **5** orders (v5 - allows max 6 total positions)
- Commission: **0.05%** (v5 update - realistic futures rate)
- Slippage: **5 ticks** (realistic for automation)
- Recalculate:
  - "On every tick": **UNCHECKED** (calc_on_every_tick=FALSE)
  - "On bar close": **CHECKED** (process_orders_on_close=TRUE)

**Chart Settings:**
- **Bank Nifty**: 75-minute timeframe, BANKNIFTY symbol
- **Gold Mini**: 60-minute timeframe, GOLDMINI symbol

**Common Configuration Errors:**
1. Using v4 settings in v5 code (ADX 25 vs 30, pyramiding 3 vs 5, etc.)
2. Properties → Pyramiding set to 3 instead of 5 (limits v5's extended capacity)
3. Using old commission rate (0.1%) instead of v5's 0.05%
4. Mixing Bank Nifty and Gold settings (different ADX, ROC thresholds)
5. Custom ER thresholds without adjusting ER Period

**See SETTINGS_ANALYSIS.md, BANKNIFTY_V5_CHANGELOG.md, and GOLD_V5_CHANGELOG.md for detailed comparisons.**

**Common backtest settings:**
- Date range: Minimum 5 years for statistical significance
- Initial capital: ₹50,00,000 (₹50 Lakhs)
- Commission: 0.1% (Bank Nifty options), 0.05% (Gold futures)
- Slippage: 5 ticks (for realistic automation modeling)

### Performance Validation

**Bank Nifty v5.0 Expected (2009-2025):**
- CAGR: 19-24% annually (v4: 22.59%)
- Max Drawdown: -20% to -27% (v4: -24.87%)
- Win Rate: 48-54% (v4: 51%)
- Total Trades: 70-85% of v4 base entries (ADX 30 stricter)
- Pyramid Count: 130-160% of v4 pyramids (ROC 2%, ATR 0.5)
- Max Positions: 6 (v4: 4)

**Gold Mini v5.0 Expected (2015-2025):**
- CAGR: 21-22% (v4: 20.23%)
- Max Drawdown: -18% to -19% (v4: -17.90%)
- Win Rate: 47-48% (v4: 46%)
- Pyramid Utilization: ~10-15% trades reach 5-6 pyramids

**Bank Nifty v3 baseline (historical reference):**
- CAGR: 12-23% annually
- Max Drawdown: 22-30%
- Win Rate: 38-48%
- Total Trades: 300-600 over 16+ years

**Key analysis points:**
1. Use Strategy Tester → List of Trades to export CSV
2. Analyze pyramid success rates separately
3. Compare stop-loss modes on identical date ranges
4. Check ROC filter effectiveness (pyramid count reduction vs win rate improvement)

### Common Development Pitfalls

**Pine Script-specific issues:**
1. **Lookahead bias**: Donchian uses `high[1]` and `low[1]` (historical data only)
2. **Repainting prevention**: `process_orders_on_close=TRUE` ensures bar-close execution
3. **Division by zero**: Position sizing has `stop_distance > 0` checks
4. **Scope issues**: Variables in custom functions must be explicitly passed
5. **Table rendering**: Smart panel uses `table.new()` with proper deletion before recreation

**Strategy-specific gotchas:**
1. Very few signals expected (5-15/year) - extend backtest period to 5+ years
2. ADX < 25 + RSI > 70 are contradictory by design (filters for early trends)
3. Margin calculations assume synthetic futures (ATM PE Sell + CE Buy = ₹2.7L per lot)
4. Equity high watermark only updates on realized profits, not open P&L

## Documentation Structure

### Primary Documentation (Read First)

- **`BANKNIFTY_V6_CHANGELOG.md`** - ⚡ **LATEST**: v6.0 complete specification (27.5% CAGR empirically validated, ROC filter disabled)
- **`STRATEGY_LOGIC_SUMMARY.md`** - Complete requirements, all 7 conditions, position sizing formulas
- **`BANKNIFTY_V5_CHANGELOG.md`** - v5.0 complete specification (extended pyramiding, optimized parameters)
- **`GOLD_V5_CHANGELOG.md`** - Gold v5.0 specification (6 positions, ER refinements)
- **`BANKNIFTY_V4_CHANGELOG.md`** - v4 optimization rationale, Gold learnings, migration guide
- **`GOLD_STRATEGY_SPECIFICATION.md`** - Gold Mini complete specification
- **`IMPLEMENTATION_GUIDE.md`** - How to use in TradingView, troubleshooting

### Reference Documentation

- **`SETTINGS_ANALYSIS.md`** - ⚠️ Critical: Screenshots vs code defaults comparison, common configuration errors
- **`BACKTEST_SETTINGS_v4.1.md`** - Validated optimal settings, complete parameter list, performance metrics
- **`BANKNIFTY_LOT_SIZE_HISTORY.md`** - NSE lot size changes 2005-2025 (critical for v4.1+)
- **`BANKNIFTY_GOLD_COMPARISON.md`** - Cross-strategy optimization analysis
- **`V2_TRIPLE_CONSTRAINT_IMPLEMENTATION.md`** - Pyramiding safety constraints
- **`TOM_BASSO_FEATURES_IMPLEMENTED.md`** - Position sizing methodology

### Development/Debug Documentation

- **`CODE_REVIEW_FINDINGS_2025-11-14.md`** - Recent code quality audit
- **`COMPREHENSIVE_CODE_REVIEW_CHECKLIST.md`** - Quality standards
- **`TROUBLESHOOTING_GUIDE.md`** - Common issues (few signals, no entries)

### Historical Documentation (Reference Only)

Files with dates/versions like `CRITICAL_BUGFIXES_2025-11-10.md`, `COMPILATION_*.md`, `PRODUCTION_READINESS_*.md` - Historical bug fixes and certification audits.

## Development Commands

### Version Control

This is a Git repository. Common operations:

```bash
# View current changes
git status
git diff

# Commit strategy changes
git add trend_following_strategy_banknifty_v4.pine
git commit -m "Update: Bank Nifty v4.1 historical lot sizing"

# View commit history
git log --oneline
```

### File Analysis

```bash
# Find specific functionality
grep -r "calc_on_every_tick" *.pine
grep -r "getBankNiftyLotSize" *.pine

# Compare versions
diff trend_following_strategy_smart.pine trend_following_strategy_banknifty_v4.pine

# Count lines of code
wc -l *.pine
```

### CSV Data Analysis

Backtest CSVs available:
- `Bank_Nifty_Trend_Following_v4.1.csv` / `.xlsx` - Latest Bank Nifty results
- `Gold_Mini_Trend_Following.csv` - Gold validation results
- `ITJ_BN_TF_run_1.csv` - Historical Bank Nifty run

## Key Concepts to Understand

### Equity High Watermark vs Current Equity

Position sizing uses **equity high watermark** (highest realized equity), NOT current equity. This prevents:
- Oversizing positions after drawdowns (current equity would be lower)
- Position size oscillation during open P&L swings
- Only updates when profits are realized (position closed)

### Pyramiding Safety (Triple-Constraint)

Before adding pyramid, ALL must pass:
1. **Margin check**: Required margin < Available margin
2. **Scaling constraint**: Position size = Previous × pyramid_size_ratio (0.5)
3. **Profitability check**: Current position must be in profit
4. **ROC filter** (v4): 15-period ROC > 3% threshold

### ROC Filter (v4 Critical Optimization)

Most important Gold learning ported to Bank Nifty:
- Only enables pyramiding when 15-period Rate of Change > 3%
- Prevents pyramiding in weak momentum or reversals
- Expected: -20-30% fewer pyramids, but +10-15% higher pyramid win rate
- Toggle: `use_roc_for_pyramids` (TRUE in v4, FALSE in v3)

### Historical Lot Sizing (v4.1)

Bank Nifty lot size changed 10 times (2005-2025):
- 2009-2010: 50 lots
- 2018-2020: 20 lots
- 2023-2024: 15 lots
- Current: 35 lots

Function `getBankNiftyLotSize(barTime)` returns accurate lot size for each historical period. Toggle `use_historical_lot_size` to enable/disable.

### Smart Info Panel Behavior

Context-aware UI that switches display:
- **When FLAT**: Shows entry condition status (7 conditions with ✓/✗)
- **When IN TRADE**: Shows position breakdown (Long_1, Long_2, etc.), stops, P&L, margin usage
- Toggle: `smart_panel` (TRUE = context-aware, FALSE = always show all)

## Code Modification Guidelines

### When editing Pine Script strategies:

1. **Always test changes** in TradingView with 5+ year backtest before committing
2. **Preserve anti-repainting measures**:
   - Keep `process_orders_on_close=TRUE`
   - Donchian must use `high[1]` and `low[1]`
   - No `security()` with lookahead bias
3. **Update version comments** at top of file (v4.1 → v4.2, etc.)
4. **Add changelog entry** in BANKNIFTY_V4_CHANGELOG.md or equivalent
5. **Test all 3 stop-loss modes** if modifying exit logic
6. **Verify margin calculations** if changing position sizing
7. **Check division-by-zero protection** for any new calculations

### When adding new parameters:

1. Use `input.*()` functions with descriptive tooltips
2. Add to relevant documentation (STRATEGY_LOGIC_SUMMARY.md)
3. Provide conservative defaults (quality over quantity philosophy)
4. Consider cross-instrument impact (Bank Nifty vs Gold)

### When upgrading from v4 to v5:

1. **Close all open positions** in v4 before switching to v5
2. **Verify v5 settings** match documented defaults (see Settings Verification section)
3. **Run comparison backtest** on identical date range (v4 vs v5)
4. **Key migration checks**:
   - Properties → Pyramiding = 5 (was 3)
   - Inputs → Max Pyramids = 5 (was 3)
   - Inputs → ADX = 30 for Bank Nifty (was 25)
   - Inputs → ER Period = 5 (was 3), ER Threshold = 0.77 (was 0.8)
   - Properties → Commission = 0.05% (was 0.1% for Bank Nifty)
5. **Backward compatibility**: v5 code can revert to v4 behavior by changing parameters
6. See BANKNIFTY_V5_CHANGELOG.md or GOLD_V5_CHANGELOG.md → Migration Guide section

### When debugging "no entries" issues:

1. Enable debug panel: `show_debug = TRUE`
2. Extend backtest to 10+ years (signals are rare by design)
3. Check ADX and ER - most common bottlenecks (too strict)
4. Verify all 7 conditions in info table
5. See TROUBLESHOOTING_GUIDE.md for systematic approach

## Important Notes

### Strategy Selectivity

These are **highly selective** strategies - few signals is NORMAL:
- Bank Nifty: 5-15 entries per year expected
- Gold Mini: 10-20 entries per year
- Requires ALL 7 conditions simultaneously = rare event
- Philosophy: Quality over quantity, trend-following only works in trending markets

### Backtesting Realism

- Historical lot sizing (v4.1) provides accurate position sizing for entire backtest period
- Commission and slippage settings reflect actual trading costs
- Margin cushion (2.7L) handles real-world volatility spikes
- `calc_on_every_tick=FALSE` prevents unrealistic mid-bar executions

### Version Strategy

- **v6.0 = Current production (Bank Nifty only)** ⚡ Empirically validated: 27.5% CAGR
- v5.x = Current production (Gold Mini) / Previous (Bank Nifty)
- v4.x = Baseline reference (Gold-optimized, 4 positions max)
- v3.x = Legacy baseline (smart panel variant)
- v2.x = Legacy (profit lock-in mechanism)
- v1.x = Original implementation

**Always work on v6 for Bank Nifty unless:**
- Comparing with v4/v5 baseline performance
- Testing parameter sensitivity (v6 vs v5 vs v4)
- Debugging version-specific issues
- Working with Gold Mini (use v5 for Gold)

### Cross-Strategy Learnings

**Gold Mini → Bank Nifty (v4 optimizations):**
- ✅ ROC filter (HIGH confidence)
- ✅ Margin cushion (HIGH confidence)
- ✅ calc_on_every_tick=FALSE (MEDIUM confidence)
- ✅ Tom Basso default (MEDIUM confidence)
- ❌ ADX 20 (not ported - Bank Nifty noisier, uses ADX 30 in v5)
- ❌ Risk 1.5% (not ported in v4, but adopted in v5)

**Bank Nifty v5 → Gold v5 (bidirectional refinement):**
- ✅ ER Period 5 + ER Threshold 0.77 (smoother calculation)
- ✅ Extended pyramiding to 6 positions (both strategies)
- ⚪ ADX 30 (Bank Nifty v5 only, Gold stays at 20)
- ⚪ ROC 2% (Bank Nifty v5 only, Gold stays at 5%)

**Bank Nifty v6 (empirical optimization):**
- ✅ Kept v5 capacity (6 positions) - HIGH value
- ✅ Kept v5 ADX 30 - stricter entries work well
- ✅ Kept v5 commission 0.05% - realistic modeling
- ⬅️ Reverted to v4 ER(3)>0.8 - better responsiveness
- ⬅️ Reverted to v4 ATR 0.75 - wider pyramid spacing
- ⬅️ Reverted to v4 Risk 2.0% - better capital utilization
- ⚠️ **DISABLED ROC filter** - most significant change, unrestricted pyramiding
- **Result:** 27.5% CAGR (+22% vs v5 expected, +22% vs v4 actual)

See BANKNIFTY_GOLD_COMPARISON.md, BANKNIFTY_V6_CHANGELOG.md, BANKNIFTY_V5_CHANGELOG.md, and GOLD_V5_CHANGELOG.md for detailed analysis.

## Support Resources

- TradingView Pine Script v5 documentation: https://www.tradingview.com/pine-script-docs/
- Pine Script reference: https://www.tradingview.com/pine-script-reference/v5/
- Strategy tester guide: TradingView → Strategy Tester tab

For strategy-specific questions, always reference STRATEGY_LOGIC_SUMMARY.md first.
