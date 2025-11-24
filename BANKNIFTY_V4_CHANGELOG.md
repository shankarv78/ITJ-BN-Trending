# BANK NIFTY TREND FOLLOWING STRATEGY - v4 CHANGELOG

**Current Version:** v4.1
**Last Updated:** 2025-11-15
**Strategy:** ITJ Bank Nifty 75-min Trend Following
**Optimization Source:** Gold Mini empirical learnings (2015-2025 backtest validation)

---

## LATEST UPDATE: v4.1 (November 15, 2025)

### ✨ HISTORICAL LOT SIZE IMPLEMENTATION

**What's New:**
Bank Nifty v4.1 adds dynamic historical lot sizing based on NSE contract changes from 2005-2025. This feature enables **historically accurate backtesting** by using the correct lot size for each period.

**Why This Matters:**
- Bank Nifty lot size has changed **10 times** from 2005-2025
- Range: 15 lots (recent minimum) to 50 lots (2009 period) to 100 lots (launch)
- Using static lot size = 35 throughout 2009-2025 creates **unrealistic position sizing**
- **78% of backtest period** had different lot sizes than current 35 lots

**Key Changes:**
1. **New Function:** `getBankNiftyLotSize(barTime)` - Returns historically accurate lot size
2. **User Toggle:** `use_historical_lot_size` (default: TRUE)
   - TRUE: Uses historically accurate lot sizes (recommended for realistic backtesting)
   - FALSE: Uses static lot size (useful for parameter isolation testing)
3. **Optional Visual Indicators:** Lot size info table and change markers (hidden by default)
4. **Complete Documentation:** BANKNIFTY_LOT_SIZE_HISTORY.md with all NSE changes

**Historical Lot Sizes (2009-2025):**
| Period | Lot Size | Impact on Position Sizing |
|--------|----------|---------------------------|
| Mar 2009 - Apr 2010 | **50** | +43% more capital vs static 35 |
| Apr 2010 - Aug 2015 | **25** | -29% less capital vs static 35 |
| Apr 2016 - Oct 2018 | **40** | +14% more capital vs static 35 |
| Oct 2018 - May 2020 | **20** | -43% less capital vs static 35 |
| Jul 2023 - Nov 2024 | **15** | -57% less capital vs static 35 |
| Apr 2025 - Dec 2025 | **35** | Accurate (current period) |

**Expected Impact:**
- More realistic backtest results matching actual trading conditions
- Accurate position sizing for each historical period
- Better comparison with live trading performance
- Foundation for handling future NSE lot size changes

**Breaking Changes:** None (backward compatible via toggle)

**Files Modified:**
- `trend_following_strategy_banknifty_v4.pine` → Updated to v4.1
- `BANKNIFTY_V4_CHANGELOG.md` → Added v4.1 section
- `BANKNIFTY_LOT_SIZE_HISTORY.md` → New comprehensive reference

**Recommendation:** Use `use_historical_lot_size = TRUE` (default) for all realistic performance validation. Only use FALSE for parameter sensitivity testing.

---

## v4 BASE VERSION (November 15, 2025)

### EXECUTIVE SUMMARY

Bank Nifty v4 incorporates 4 key optimizations from the Gold Mini strategy's empirically validated performance (20.23% CAGR over 10.6 years). These changes focus on **reducing whipsaw, improving pyramid quality, and adding safety buffers** while maintaining Bank Nifty's unique characteristics.

**Key Philosophy:** Conservative adaptation - Only high-confidence Gold learnings were ported to Bank Nifty, accounting for differences in volatility, timeframe effectiveness, and instrument behavior.

---

## v4 CHANGES SUMMARY

| Parameter | v3 (Previous) | v4 (New) | Confidence | Gold Learning |
|-----------|--------------|----------|------------|---------------|
| **calc_on_every_tick** | TRUE | **FALSE** ✨ | Medium | Reduced Gold max DD to -17.90% |
| **ROC Filter Enabled** | FALSE (disabled) | **TRUE** ✨ | **HIGH** | Most important Gold optimization |
| **ROC Threshold** | 0.0% (N/A) | **3.0%** ✨ | **HIGH** | Selective pyramiding on momentum |
| **Margin per Lot** | 2.6L | **2.7L** ✨ | **HIGH** | +4% safety cushion |
| **Stop Loss Mode Default** | SuperTrend | **Tom Basso** ✨ | Medium | Better profit protection |

**Parameters NOT Changed (Deliberately):**
- ADX Threshold: Remains 25 (Bank Nifty noisier than Gold - kept conservative)
- Risk per Trade: Remains 1.0% (Bank Nifty different volatility profile than Gold)
- Max Pyramids: Remains 3 (already optimized for Bank Nifty)
- ATR Pyramid Threshold: Remains 0.75 (Bank Nifty needs larger gaps than Gold)

---

## DETAILED CHANGE ANALYSIS

### 1. calc_on_every_tick = FALSE ✨

**Change:**
```pinescript
// v3:
strategy("Bank Nifty Trend Following", ..., calc_on_every_tick=true, ...)

// v4:
strategy("Bank Nifty Trend Following v4", ..., calc_on_every_tick=false, ...)
```

**Rationale:**
- **Gold Learning:** Changing from TRUE to FALSE reduced max drawdown from projected -25-35% to actual -17.90%
- **Bank Nifty Application:** 75-min timeframe benefits from bar-close execution to reduce whipsaw
- **Trade-off:** Slightly delayed entries, but cleaner signals and less noise-induced exits

**Expected Impact:**
- ✅ **Reduced Drawdown:** 5-15% improvement expected (based on Gold results)
- ✅ **Fewer False Signals:** Bar-close confirmation filters intra-bar volatility spikes
- ⚠️ **Slightly Delayed Entry/Exit:** Orders execute at next bar open vs mid-bar

**Confidence:** Medium (Gold used hourly, Bank Nifty uses 75-min - similar timeframe class)

---

### 2. ROC Filter ENABLED ✨

**Change:**
```pinescript
// v3:
use_roc_for_pyramids = input.bool(false, "Use ROC Filter for Pyramids", ...)
roc_threshold = input.float(3.0, "ROC Threshold %", ...)

// v4:
use_roc_for_pyramids = input.bool(true, "Use ROC Filter for Pyramids",
    tooltip="✨ v4: Enable ROC momentum check (Gold-inspired)")
roc_threshold = input.float(3.0, "ROC Threshold %",
    tooltip="✨ v4: 3% minimum momentum for pyramids")
```

**Rationale:**
- **Gold Learning:** ROC filter was THE most important optimization - prevented weak pyramids
- **Bank Nifty Application:** 3% ROC ensures pyramids only enter on strong Bank Nifty momentum (lower than Gold's 5% due to Bank Nifty's higher volatility)
- **Core Principle:** "More entries + selective pyramids" beats "fewer entries + aggressive pyramids"

**Expected Impact:**
- ✅ **Higher Quality Pyramids:** Only strong trends get 2nd/3rd/4th positions
- ✅ **Reduced Pyramid Whipsaw:** Fewer pyramids that immediately reverse
- ✅ **Better Risk-Adjusted Returns:** Fewer losing pyramids improve overall win rate
- ℹ️ **Fewer Total Pyramids:** Expected 20-30% reduction in pyramid count, but higher success rate

**Confidence:** **HIGH** (Most empirically validated Gold optimization, directly applicable to Bank Nifty)

---

### 3. Margin Cushion: 2.6L → 2.7L ✨

**Change:**
```pinescript
// v3:
margin_per_lot = input.float(2.6, "Margin per Lot (Lakhs)",
    tooltip="Rs 2.60 lakh per lot (exact SEBI spec)")

// v4:
margin_per_lot = input.float(2.7, "Margin per Lot (Lakhs)",
    tooltip="✨ v4: Rs 2.7L (+4% cushion, Gold-inspired safety)")
```

**Rationale:**
- **Gold Learning:** Added 4% margin cushion (0.72L → 0.75L) to handle volatility spikes
- **Bank Nifty Application:** SEBI spec is 2.6L, but real-world margin can spike on volatile days
- **Risk Management:** Prevents position size overruns during VIX spikes or expiry week volatility

**Expected Impact:**
- ✅ **Reduced Margin Violations:** Better handling of volatile periods
- ✅ **More Conservative Position Sizing:** Slight reduction in max position size (~4%)
- ℹ️ **Slightly Lower Returns:** ~1-2% CAGR reduction acceptable for stability

**Confidence:** **HIGH** (Standard risk management practice, empirically validated on Gold)

---

### 4. Tom Basso Stop Loss Mode as Default ✨

**Change:**
```pinescript
// v3:
stop_loss_mode = input.string("SuperTrend", "Stop Loss Mode",
    options=["SuperTrend", "Tom Basso"], ...)

// v4:
stop_loss_mode = input.string("Tom Basso", "Stop Loss Mode",
    options=["SuperTrend", "Tom Basso"],
    tooltip="✨ v4: Tom Basso default (Gold learning)")
```

**Rationale:**
- **Gold Learning:** Tom Basso mode (independent ATR stops per position) protected profits better than single SuperTrend stop
- **Bank Nifty Application:** With up to 4 positions (1 base + 3 pyramids), independent stops allow partial profit protection
- **Scenario:** If position 1 is deep in profit but position 4 is recent, Tom Basso can exit position 4 independently

**Expected Impact:**
- ✅ **Better Profit Protection:** Deep profits locked in even if new pyramids fail
- ✅ **More Granular Risk Management:** Each position has appropriate stop distance
- ⚠️ **Slightly More Complex:** 4 independent stops vs 1 SuperTrend stop
- ℹ️ **User Can Revert:** SuperTrend mode still available via input dropdown

**Confidence:** Medium (Gold showed benefits, Bank Nifty pyramid behavior may differ)

---

## PARAMETERS DELIBERATELY NOT CHANGED

### ADX Threshold: Remains 25 (NOT changed to Gold's 20)

**Why NOT Changed:**
- Bank Nifty is significantly noisier than Gold Mini
- Gold Mini has smooth, persistent trends - can afford ADX 20
- Bank Nifty has more false breakouts - needs ADX 25 filter
- **Risk:** Lowering to 20 would increase false signals on Bank Nifty

**Future Consideration:** Could test ADX 22-23 as middle ground

---

### Risk per Trade: Remains 1.0% (NOT changed to Gold's 1.5%)

**Why NOT Changed:**
- Gold Mini and Bank Nifty have different volatility profiles
- Bank Nifty requires specific 1.0% risk based on historical testing
- Gold's higher risk worked for its specific volatility characteristics
- **Risk:** Increasing to 1.5% could over-leverage on Bank Nifty volatile moves

**Future Consideration:** Could test 1.1-1.2% if v4 shows drawdowns are well-controlled

---

### Max Pyramids: Remains 3 (Same as Gold's 3)

**Why NOT Changed:**
- Both strategies now use max_pyramids = 3 (Gold updated from 2 to 3)
- Already aligned between Gold and Bank Nifty
- V2 profit lock-in mechanism prevents exponential growth in both

---

### ATR Pyramid Threshold: Remains 0.75 (NOT changed to Gold's 0.5)

**Why NOT Changed:**
- Gold's smaller ATR threshold (0.5) worked because Gold has tighter, smoother trends
- Bank Nifty needs larger gaps (0.75 ATR) to ensure pyramids have breathing room
- Bank Nifty volatility spikes could trigger 0.5 ATR too frequently
- **Risk:** Lowering to 0.5 could create overcrowded pyramids on Bank Nifty

**Future Consideration:** Could test 0.65 if ROC filter proves highly effective at controlling pyramids

---

## TESTING RECOMMENDATIONS

### Immediate Backtest Tests (TradingView)

1. **Full Historical Backtest (2015-2025):**
   - Compare v3 vs v4 on identical date range
   - Key metrics: CAGR, Max DD, Win Rate, Pyramid Success Rate
   - Expected v4 improvement: +2-5% CAGR, -3-8% Max DD

2. **ROC Filter Effectiveness:**
   - Count pyramids with/without ROC filter
   - Measure pyramid win rate with ROC filter enabled
   - Expected: 20-30% fewer pyramids, but +10-15% higher win rate on pyramids

3. **calc_on_every_tick Impact:**
   - Run backtest with TRUE vs FALSE on same data
   - Measure max drawdown difference
   - Expected: FALSE reduces max DD by 5-15%

4. **Tom Basso vs SuperTrend:**
   - Compare default Tom Basso vs SuperTrend mode
   - Measure profit retention during reversals
   - Expected: Tom Basso shows better profit lock-in on partial exits

### Paper Trading Validation (2-3 months)

1. **Signal Quality Check:**
   - Monitor ROC filter rejections - are rejected pyramids actually weak?
   - Track calc_on_every_tick=FALSE - any missed opportunities?

2. **Margin Cushion Validation:**
   - Monitor actual margin usage vs 2.7L allocation
   - Check if 4% cushion handles VIX spikes adequately

3. **Stop Loss Behavior:**
   - Observe Tom Basso multi-position exits
   - Compare with hypothetical SuperTrend single-stop behavior

---

## MIGRATION GUIDE (v3 → v4)

### For Existing Users

**If Currently Running v3:**

1. **Complete Open Trades First:**
   - Let all current v3 positions close naturally
   - Do NOT switch mid-trade (different stop logic)

2. **Backup v3 Settings:**
   - Export your current v3 TradingView settings
   - Save as "BankNifty_v3_settings_backup.txt"

3. **Load v4 Script:**
   - Open `trend_following_strategy_banknifty_v4.pine`
   - Add to TradingView chart (75-min timeframe)

4. **Verify v4 Settings:**
   - ✅ calc_on_every_tick=FALSE (Strategy Properties)
   - ✅ use_roc_for_pyramids=TRUE (Inputs)
   - ✅ roc_threshold=3.0% (Inputs)
   - ✅ margin_per_lot=2.7L (Inputs)
   - ✅ stop_loss_mode="Tom Basso" (Inputs)

5. **Run Parallel Backtest:**
   - Compare v3 vs v4 on your typical date range
   - Verify v4 improvements before going live

### For New Users

1. **Start with v4 Defaults:**
   - All optimized settings pre-configured
   - No manual tweaking needed

2. **Optional Automation Settings:**
   - calc_on_every_tick=FALSE + process_orders_on_close=TRUE
   - Add 5 ticks slippage for realistic automation modeling

3. **Recommended Testing Period:**
   - Minimum 2-3 months paper trading
   - Verify ROC filter behavior in live market conditions

---

## EXPECTED PERFORMANCE IMPACT

### Conservative Projections (Based on Gold Learnings)

| Metric | v3 Baseline | v4 Expected | Improvement |
|--------|-------------|-------------|-------------|
| **CAGR** | 12-18% | 14-20% | +2-5% |
| **Max Drawdown** | -22-30% | -18-25% | -3-8% |
| **Win Rate** | 38-42% | 40-45% | +2-3% |
| **Pyramid Success** | 35-40% | 45-55% | +10-15% |
| **Max Contracts** | 200-250 | 180-220 | -10-15% (better capital efficiency) |

### Gold Mini Actual Results (For Reference)

- Gold v1.0 Projected CAGR: 10-16%
- Gold v1.1 Actual CAGR: **20.23%** (exceeded by +27-101%)
- Gold Max DD Improvement: Projected -25-35%, Actual **-17.90%**

**Note:** Bank Nifty v4 improvements will likely be more modest than Gold's due to:
1. Bank Nifty already had some optimizations (e.g., ADX 25 vs Gold's initial 22)
2. Bank Nifty has different volatility characteristics
3. Gold optimizations were discovered through extensive trial-and-error

---

## RISK ASSESSMENT

### Low Risk Changes ✅

1. **Margin Cushion (2.6L → 2.7L):** Standard risk management, minimal downside
2. **ROC Filter Enabled:** Only affects pyramids, base entry unchanged

### Medium Risk Changes ⚠️

1. **calc_on_every_tick=FALSE:** Could miss intra-bar opportunities, but Gold showed net positive
2. **Tom Basso Default:** More complex stop management, but user can revert to SuperTrend

### Mitigation Strategies

1. **Extensive Backtesting:** Run 5+ year backtest before live deployment
2. **Paper Trading:** 2-3 month validation period
3. **Gradual Rollout:** Start with 1 lot, scale up after validation
4. **Settings Reversion:** All v3 settings remain available via inputs

---

## GOLD MINI vs BANK NIFTY OPTIMIZATION COMPARISON

### High Confidence Transfers (Implemented in v4) ✅

| Optimization | Gold Change | Bank Nifty v4 | Rationale |
|--------------|-------------|---------------|-----------|
| ROC Filter | Disabled → Enabled (5%) | Disabled → Enabled (3%) | Most important Gold learning, applicable to all trending instruments |
| Margin Cushion | 0.72L → 0.75L (+4%) | 2.6L → 2.7L (+4%) | Risk management best practice |
| calc_on_every_tick | TRUE → FALSE | TRUE → FALSE | Both use hourly-class timeframes (1h vs 75-min) |
| Stop Loss Mode | N/A (always SuperTrend) → Tom Basso | SuperTrend default → Tom Basso default | Better multi-position profit protection |

### Medium Confidence (Not Implemented - Require Testing) ⚠️

| Optimization | Gold Change | Bank Nifty Status | Why Not Implemented |
|--------------|-------------|-------------------|---------------------|
| ADX Threshold | 22 → 20 | Remains 25 | Bank Nifty noisier - needs stronger filter |
| Risk per Trade | N/A | Remains 1.0% | Different volatility profile, needs independent validation |
| ATR Pyramid | 0.75 → 0.5 | Remains 0.75 | Bank Nifty needs larger gaps between pyramids |

### Not Applicable ❌

| Parameter | Gold Setting | Bank Nifty Setting | Why Different |
|-----------|--------------|-------------------|---------------|
| Point Value | Rs 10/point | Rs 20/point | Different contract specifications |
| Lot Size | 100g → 10 lots | 15 → 1 lot | Different instruments |
| Timeframe | 60-min | 75-min | Different optimal timeframes per instrument |

---

## VERSION HISTORY

### v4 (2025-11-15) - Gold-Inspired Optimizations ✨
- Added calc_on_every_tick=FALSE for reduced whipsaw
- Enabled ROC filter (3% threshold) for selective pyramiding
- Increased margin to 2.7L (+4% safety cushion)
- Changed default stop loss mode to Tom Basso
- Comprehensive documentation of changes and rationale

### v3 (Previous Version)
- V2 profit lock-in mechanism
- Triple-constraint pyramiding (margin, scaling, risk)
- SuperTrend + Tom Basso stop loss modes
- ADX trend filter (25 threshold)
- 75-min timeframe optimization

### v2
- Added profit lock-in mechanism
- Improved position sizing

### v1
- Initial Bank Nifty trend following implementation
- Basic SuperTrend + ADX system

---

## SUPPORT & FEEDBACK

### Backtesting Issues
- Verify TradingView settings match v4 defaults
- Check Strategy Properties: calc_on_every_tick=FALSE
- Ensure 75-min timeframe is used

### Performance Questions
- Compare v3 vs v4 on identical date ranges
- Allow 5+ years of backtest data for statistical significance
- ROC filter effects only visible on pyramid trades

### Automation Setup
- Recommended: calc_on_every_tick=FALSE + process_orders_on_close=TRUE
- Add 5 ticks slippage for realistic modeling
- Test with paper trading before live deployment

---

## NEXT STEPS

1. **Load v4 script** into TradingView
2. **Run backtest** on 2015-2025 date range
3. **Compare with v3** performance metrics
4. **Paper trade** for 2-3 months to validate live behavior
5. **Document results** and refine if needed

---

## CONCLUSION

Bank Nifty v4 represents a **conservative, empirically-informed evolution** based on Gold Mini's exceptional 20.23% CAGR performance over 10.6 years. The 4 key changes focus on:

1. ✨ **Reduced Whipsaw** (calc_on_every_tick=FALSE)
2. ✨ **Selective Pyramiding** (ROC filter enabled)
3. ✨ **Risk Management** (margin cushion)
4. ✨ **Profit Protection** (Tom Basso default)

**Expected Outcome:** +2-5% CAGR improvement with -3-8% drawdown reduction, while maintaining Bank Nifty's unique optimization profile.

**Philosophy:** "Take the best learnings from Gold, but respect Bank Nifty's distinct personality."

---

**Document Version:** 1.0
**Author:** ITJ Strategy Optimization Project
**Related Files:**
- `trend_following_strategy_banknifty_v4.pine`
- `BANKNIFTY_GOLD_COMPARISON.md`
- `GOLD_OPTIMIZATION_NOTES.md`
