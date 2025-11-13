# Code Quality Checklist - Always Verify Before Completion

## Compilation Errors - MUST CHECK

### 1. **Empty Code Blocks** ❌
```pinescript
// WRONG - Will cause compiler error
if condition
    // only comments, no code
else
    // only comments, no code  ← ERROR!
```

```pinescript
// CORRECT - Remove empty else or add statement
if condition
    // only comments
// No else block needed if empty
```

### 2. **All Variables Declared**
- [ ] All `var` declarations are at global scope
- [ ] All local variables are assigned before use
- [ ] No undefined variable references

### 3. **Function Return Values**
```pinescript
// WRONG
myFunc() =>
    result = 0  ← needs explicit return

// CORRECT
myFunc() =>
    result = 0
    result  ← explicit return
```

### 4. **String Concatenation**
- [ ] All numeric values converted with `str.tostring()`
- [ ] No direct concatenation of float + string
```pinescript
// WRONG
text = "Value: " + my_float

// CORRECT
text = "Value: " + str.tostring(my_float, "#.##")
```

### 5. **Plot Scope, Overlay & Parameters**
- [ ] All `plot()` calls are at global scope (not inside `if`)
- [ ] Use ternary operators for conditional plots
- [ ] Understand `overlay` and `force_overlay` behavior:
  - With `overlay=true`: All plots go on main chart (cannot split to panes)
  - With `overlay=false`: Script in separate pane, use `force_overlay=true` for specific plots on main chart
- [ ] `display.pane` parameter only used with `plot()`, NEVER with `hline()`
- [ ] `hline()` only accepts `display.none` or `display.all`

```pinescript
// WRONG - Can't split plots to different panes
strategy("MyStrat", overlay=true)
plot(ema)  // On chart
plot(rsi)  // Also on chart (wrong scale!)

// CORRECT - Use overlay=false + force_overlay=true
strategy("MyStrat", overlay=false)
plot(ema, force_overlay=true)  // Forces to main chart
plot(rsi)  // In separate pane (different scale)

// WRONG
if show_debug
    plot(value, "Name")

// CORRECT
plot(show_debug ? value : na, "Name")

// WRONG
hline(70, "Threshold", display=display.pane)  ❌ ERROR!

// CORRECT
hline(70, "Threshold")  ✅ Auto-appears in same pane as associated plot
```

### 6. **Table Operations**
- [ ] Table size matches number of rows/columns used
- [ ] All table.cell() calls use valid row/col indices
- [ ] Table created with `var` keyword

### 7. **Strategy Calls**
- [ ] `strategy.entry()` has valid qty parameter
- [ ] `strategy.close()` / `strategy.close_all()` properly called
- [ ] Exit logic doesn't conflict with entry logic

### 8. **Indentation & Structure**
- [ ] All `if` blocks properly closed
- [ ] All `for` loops properly closed
- [ ] Matching indentation levels

### 9. **Input Parameters**
- [ ] All inputs have valid min/max values
- [ ] Dropdown options match exact strings used in code
- [ ] Tooltips are helpful and accurate

### 10. **Logic Flow**
- [ ] No infinite loops
- [ ] No circular dependencies
- [ ] Exit conditions are reachable

---

## Testing Checklist

### Before Declaring Complete:

#### Compilation
- [ ] Copy code to Pine Editor
- [ ] Click "Save" - Does it compile without errors?
- [ ] Check error panel for any warnings

#### Syntax
- [ ] All brackets matched: `()`, `[]`, `{}`
- [ ] All string quotes closed
- [ ] No orphaned operators

#### Logic
- [ ] Entry conditions make sense
- [ ] Exit conditions are defined
- [ ] Variables are reset when needed
- [ ] Position sizing calculations are correct

#### Display
- [ ] Plots appear on chart
- [ ] Colors are visible
- [ ] Table displays correctly
- [ ] Labels are clear

---

## Common Errors & Fixes

### Error: "Cannot use 'plot' in local scope"
**Cause:** `plot()` inside `if` statement
**Fix:** Use ternary operator
```pinescript
plot(condition ? value : na, "Name")
```

### Error: "Cannot call 'operator +' with argument 'expr1'='% of Capital'"
**Cause:** Concatenating float directly with string
**Fix:** Convert to string first
```pinescript
str.tostring(risk_percent, "#.#") + "% of Capital"
```

### Error: "The structure is missing a local code block"
**Cause:** Empty `if`/`else` block with only comments
**Fix:** Remove empty block or add executable statement

### Error: "Undeclared identifier"
**Cause:** Using variable before declaration
**Fix:** Declare with `var` or assign value first

### Error: "Line is too long"
**Cause:** Line exceeds Pine Script's character limit
**Fix:** Break into multiple lines
```pinescript
// WRONG - too long
strategy.entry("Long", strategy.long, qty=final_lots, comment="BUY-" + str.tostring(final_lots) + "L-ENTRY-SIGNAL-TRIGGERED")

// CORRECT - split
comment_text = "BUY-" + str.tostring(final_lots) + "L"
strategy.entry("Long", strategy.long, qty=final_lots, comment=comment_text)
```

---

## Pre-Completion Workflow

### Step 1: Self-Review (2 min)
1. Read through entire code
2. Check for empty blocks
3. Verify all conditionals have code
4. Check string concatenations

### Step 2: Mental Compilation (2 min)
1. Trace through entry logic
2. Trace through exit logic
3. Verify pyramid logic
4. Check reset logic

### Step 3: Copy-Paste Test (1 min)
1. Copy entire code
2. Paste in Pine Editor
3. Click Save
4. Check for errors

### Step 4: Visual Verification (1 min)
1. Add to chart
2. Check if plots appear
3. Check if table appears
4. Verify no console errors

**Total Time: ~6 minutes** - Always worth it to avoid back-and-forth!

---

## Specific Issues to Watch For

### Pyramiding Logic
- [ ] `pyramid_count` properly reset on exit
- [ ] `last_pyramid_price` updated on each pyramid
- [ ] Entry names are unique (Long_1, Long_2, etc.)

### Equity Management
- [ ] `equity_high` only updates with realized profits
- [ ] `unrealized_pnl` correctly calculated
- [ ] Position sizing uses correct equity base

### Stop Loss Logic
- [ ] Both modes (SuperTrend & Van Tharp) have exit code
- [ ] Variables reset after exit in both modes
- [ ] No empty else blocks

### Table Display
- [ ] Row count matches table size declaration
- [ ] All cells filled (no gaps)
- [ ] Color logic doesn't cause errors
- [ ] String concatenations work

---

## Lessons Learned

### Issue #1: Empty Else Block (2025-11-10)
**Error:** "The structure is missing a local code block"
**Cause:** `else` clause with only comments, no executable code
**Fix:** Removed empty else block
**Prevention:** Always ensure if/else blocks have executable code or remove them

### Issue #2: Plot in Local Scope (2025-11-10)
**Error:** "Cannot use 'plot' in local scope"
**Cause:** `plot()` calls inside `if show_debug` block
**Fix:** Changed to `plot(show_debug ? value : na, ...)`
**Prevention:** Never put plot() inside conditionals

### Issue #3: String Concatenation (2025-11-10)
**Error:** "Cannot call 'operator +'"
**Cause:** Concatenating float `risk_percent` with string directly
**Fix:** Used `str.tostring(risk_percent, "#.#")` first
**Prevention:** Always convert numbers to strings before concatenating

### Issue #4: hline() Display Parameter (2025-11-10)
**Error:** "Invalid argument 'display' in 'hline' call. Possible values: [display.none, display.all]"
**Cause:** Used `display=display.pane` parameter in hline() calls
**Fix:** Removed display parameter from all hline() calls (hlines automatically appear in same pane as associated plot)
**Prevention:** Remember that `display.pane` only works with `plot()`, NOT with `hline()`. Valid hline display values are only `display.none` or `display.all`

### Issue #5: Overlay vs force_overlay (2025-11-10)
**Problem:** With `overlay=true`, all plots appear on main chart (RSI, ADX, ER, ATR overlay on price - wrong!)
**Cause:** Didn't understand Pine Script v5 overlay behavior - `overlay=true` means EVERYTHING overlays
**Fix:** Changed to `overlay=false` + added `force_overlay=true` to specific plots that should be on main chart
**Solution:**
- Set `strategy(..., overlay=false)` - strategy runs in separate pane
- Add `force_overlay=true` to: EMA, SuperTrend, Donchian, entry/exit arrows
- Leave RSI, ADX, ER, ATR without force_overlay - they auto-create separate panes
**Prevention:** Always use `overlay=false` + selective `force_overlay=true` when you need both overlay and separate pane plots in the same script

---

## Final Checklist Before Saying "Done"

- [ ] Code compiles without errors in Pine Editor
- [ ] All logic flows tested mentally
- [ ] No empty code blocks
- [ ] All strings properly formatted
- [ ] All plots at global scope
- [ ] All variables properly declared
- [ ] Table size matches usage
- [ ] Entry/exit logic complete
- [ ] Position sizing correct
- [ ] Documentation updated

**Only then can I say: "The code is complete and production-ready!" ✅**

---

**Purpose of this document:**
Ensure I ALWAYS verify compilation and basic logic before declaring work complete. No excuses!

**Last Updated:** 2025-11-10 (After overlay/force_overlay confusion - Issue #5)
**Important:** I MUST go through this checklist BEFORE saying "done" or "complete" - not after the user catches my errors!
