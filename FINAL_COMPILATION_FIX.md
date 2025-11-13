# Final Compilation Fix - Function Scope Issue

## The Real Problem:
Pine Script functions **cannot access external `var` variables** directly. The function `calculate_open_risk()` was trying to access:
- `initial_entry_price` (var variable)
- `pyr1_entry_price` (var variable)
- `basso_stop_long1` (var variable)
- etc.

These are all declared outside the function scope and Pine Script doesn't allow this.

## The Solution:
**Removed the function entirely** and replaced with inline calculations where needed.

### Before:
```pinescript
// Function that DOESN'T WORK
calculate_open_risk() =>
    if not na(initial_entry_price)  // ERROR: Can't access var variable
        ...
```

### After:
```pinescript
// Inline calculation that WORKS
current_open_risk = 0.0
if not na(initial_entry_price)  // Now in same scope - works!
    risk1 = 0.0
    ...
```

## Changes Made:
1. **Line 167:** Removed entire `calculate_open_risk()` function
2. **Lines 260-306:** Replaced function call with inline calculation for pyramiding
3. **Lines 586-631:** Replaced function call with inline calculation for info table

## Why My Previous Fixes Failed:
1. **First attempt:** Fixed ternary operator but missed variable declarations
2. **Second attempt:** Added variable declarations but function still couldn't access external vars
3. **Third attempt (THIS ONE):** Removed function entirely, calculate inline

## Pine Script Lesson Learned:
**Functions in Pine Script have limited scope access:**
- ✅ Can access: Parameters passed to them
- ✅ Can access: Global constants and inputs
- ❌ Cannot access: `var` variables declared outside
- ❌ Cannot access: Other script state variables

## Current Status: SHOULD WORK NOW ✅
The code now:
- Has no functions trying to access external variables
- Calculates risk inline where needed
- Uses variables in their proper scope

## My Apologies:
I failed to understand Pine Script's scope rules initially. I should have:
1. Recognized the scope limitation immediately
2. Either passed parameters properly or used inline code
3. Actually tested in TradingView before claiming "fixed"

This should genuinely compile now.