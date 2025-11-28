# Bug Fix: Logging Configuration Error

## Issue

When starting `portfolio_manager.py`, two errors occurred:

1. **TypeError: RotatingFileHandler.__init__() got an unexpected keyword argument 'level'**
   - Line 33: `RotatingFileHandler(..., level=logging.ERROR)`
   - `RotatingFileHandler` doesn't accept `level` in constructor

2. **AttributeError: 'ArgumentParser' object has no attribute 'add_parsers'**
   - Line 586: `parser.add_parsers('mode', ...)`
   - Should be `add_subparsers(dest='mode', ...)`

## Fix Applied

### Fix 1: Logging Handler Level
**Before:**
```python
RotatingFileHandler('webhook_errors.log', ..., level=logging.ERROR)
```

**After:**
```python
error_handler = RotatingFileHandler('webhook_errors.log', ...)
error_handler.setLevel(logging.ERROR)  # Set level after creation
```

### Fix 2: Argument Parser
**Before:**
```python
subparsers = parser.add_parsers('mode', help='Operating mode')
```

**After:**
```python
subparsers = parser.add_subparsers(dest='mode', help='Operating mode')
```

## Why This Was Missed in Testing

### Root Cause Analysis

1. **Integration tests don't import the main module:**
   - Tests create Flask apps directly (`app = Flask(__name__)`)
   - They don't execute `portfolio_manager.py` as a script
   - The logging configuration at module level never runs

2. **Unit tests don't import the main module:**
   - Unit tests import individual modules (`from core.models import Signal`)
   - They don't trigger the `if __name__ == '__main__'` block
   - Logging setup code isn't executed

3. **No startup test:**
   - We tested endpoints, parsing, validation
   - We didn't test that the script can actually start
   - Missing: "Can the server start without errors?" test

### Test Coverage Gap

**What we tested:**
- ✅ Webhook endpoint functionality (via Flask test client)
- ✅ Signal parsing and validation
- ✅ Duplicate detection
- ✅ Error handling

**What we didn't test:**
- ❌ Actual script startup (`python portfolio_manager.py live ...`)
- ❌ Module-level code execution
- ❌ Logging configuration initialization

## Prevention Strategy

### Add Startup Test

Create `tests/integration/test_startup.py`:

```python
def test_server_can_start():
    """Test that server can start without errors"""
    import subprocess
    import sys
    
    result = subprocess.run(
        [sys.executable, 'portfolio_manager.py', 'live', 
         '--broker', 'zerodha', '--api-key', 'TEST', '--capital', '1000000'],
        capture_output=True,
        timeout=5,
        cwd='portfolio_manager'
    )
    
    # Should start (may fail later, but not on import/startup)
    assert result.returncode != 1 or 'TypeError' not in result.stderr.decode()
    assert 'RotatingFileHandler' not in result.stderr.decode()
```

### Add Import Test

```python
def test_module_can_be_imported():
    """Test that portfolio_manager module can be imported"""
    import sys
    import importlib
    
    # Should not raise TypeError or AttributeError
    try:
        importlib.import_module('portfolio_manager')
    except (TypeError, AttributeError) as e:
        pytest.fail(f"Module import failed: {e}")
```

## Status

✅ **Fixed**: Both errors resolved
✅ **Verified**: Server starts successfully
✅ **Tested**: `python portfolio_manager.py --help` works
✅ **Tested**: Server initializes without errors

## Files Modified

- `portfolio_manager/portfolio_manager.py`:
  - Line 27-36: Fixed logging handler level setting
  - Line 586: Fixed argument parser method name

