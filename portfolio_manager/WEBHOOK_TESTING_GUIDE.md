# Webhook Testing Guide

## Quick Test

### Test with Script (Easiest)

```bash
# Test all signal types
./test_webhook.sh

# Test specific signal type
./test_webhook.sh base_entry
./test_webhook.sh pyramid
./test_webhook.sh exit
./test_webhook.sh gold
```

### Manual Test with curl

```bash
curl -X POST https://webhook.shankarvasudevan.com/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "BASE_ENTRY",
    "instrument": "BANK_NIFTY",
    "position": "Long_1",
    "price": 52000,
    "stop": 51650,
    "lots": 5,
    "atr": 350,
    "er": 0.82,
    "supertrend": 51650,
    "roc": 2.5,
    "timestamp": "2025-11-28T10:30:00Z"
  }'
```

## Sample JSON Payloads

### 1. BASE_ENTRY - Bank Nifty

```json
{
  "type": "BASE_ENTRY",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 52000,
  "stop": 51650,
  "lots": 5,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "roc": 2.5,
  "timestamp": "2025-11-28T10:30:00Z"
}
```

### 2. BASE_ENTRY - Gold Mini

```json
{
  "type": "BASE_ENTRY",
  "instrument": "GOLD_MINI",
  "position": "Long_1",
  "price": 72000,
  "stop": 71500,
  "lots": 3,
  "atr": 500,
  "er": 0.75,
  "supertrend": 71500,
  "roc": 1.8,
  "timestamp": "2025-11-28T10:30:00Z"
}
```

### 3. PYRAMID - Bank Nifty (Long_2)

```json
{
  "type": "PYRAMID",
  "instrument": "BANK_NIFTY",
  "position": "Long_2",
  "price": 52200,
  "stop": 51800,
  "lots": 3,
  "atr": 360,
  "er": 0.85,
  "supertrend": 51800,
  "roc": 2.8,
  "timestamp": "2025-11-28T10:35:00Z"
}
```

### 4. PYRAMID - Bank Nifty (Long_3)

```json
{
  "type": "PYRAMID",
  "instrument": "BANK_NIFTY",
  "position": "Long_3",
  "price": 52400,
  "stop": 52000,
  "lots": 2,
  "atr": 365,
  "er": 0.88,
  "supertrend": 52000,
  "roc": 3.2,
  "timestamp": "2025-11-28T10:40:00Z"
}
```

### 5. EXIT - Single Position (Stop Loss)

```json
{
  "type": "EXIT",
  "instrument": "BANK_NIFTY",
  "position": "Long_1",
  "price": 51600,
  "stop": 0,
  "lots": 0,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "reason": "Stop Loss Hit",
  "timestamp": "2025-11-28T11:00:00Z"
}
```

### 6. EXIT - All Positions

```json
{
  "type": "EXIT",
  "instrument": "BANK_NIFTY",
  "position": "ALL",
  "price": 52500,
  "stop": 0,
  "lots": 0,
  "atr": 350,
  "er": 0.82,
  "supertrend": 51650,
  "reason": "Manual Exit",
  "timestamp": "2025-11-28T11:10:00Z"
}
```

## How to Verify Processing

### 1. Check Processing Status

```bash
# Show all status (logs, stats, positions)
./check_processing.sh

# Show only logs
./check_processing.sh logs

# Show statistics
./check_processing.sh stats

# Monitor in real-time
./check_processing.sh realtime
```

### 2. Check Log Files

```bash
# Main portfolio manager log
tail -f portfolio_manager.log

# Webhook validation log
tail -f webhook_validation.log

# Webhook errors
tail -f webhook_errors.log

# All logs at once
tail -f portfolio_manager.log webhook_validation.log webhook_errors.log
```

### 3. Check Webhook Statistics

```bash
curl https://webhook.shankarvasudevan.com/webhook/stats | jq '.'
```

Expected response:
```json
{
  "webhook": {
    "duplicate_detector": {
      "total_checks": 10,
      "duplicates_found": 2,
      "current_history_size": 8,
      "window_seconds": 60
    },
    "total_received": 10,
    "duplicates_ignored": 2
  },
  "execution": {
    "entries_executed": 3,
    "pyramids_executed": 2,
    "exits_executed": 1,
    "entries_blocked": 0,
    "pyramids_blocked": 1
  }
}
```

## Expected Responses

### Successful Processing

```json
{
  "status": "processed",
  "request_id": "abc12345",
  "result": {
    "status": "executed",
    "signal_type": "BASE_ENTRY",
    "position_id": "Long_1",
    "lots": 5,
    "message": "Entry executed successfully"
  }
}
```

### Blocked Signal (Gate Failed)

```json
{
  "status": "processed",
  "request_id": "abc12345",
  "result": {
    "status": "blocked",
    "reason": "Portfolio risk limit exceeded",
    "signal_type": "PYRAMID"
  }
}
```

### Duplicate Signal

```json
{
  "status": "ignored",
  "error_type": "duplicate",
  "message": "Signal already processed within last 60 seconds",
  "request_id": "abc12345"
}
```

### Validation Error

```json
{
  "status": "error",
  "error_type": "validation_error",
  "message": "Missing required field: 'atr'",
  "request_id": "abc12345"
}
```

## What to Look For in Logs

### Successful Entry

Look for:
```
[INFO] Signal parsed: BASE_ENTRY Long_1 @ ₹52000
[INFO] Signal executed: BASE_ENTRY Long_1
[INFO] Entry executed successfully
```

### Blocked Signal

Look for:
```
[WARNING] Signal blocked: Portfolio risk limit exceeded
[INFO] Signal blocked: Portfolio gate BLOCKED: ...
```

### Validation Error

Look for:
```
[ERROR] Validation error during signal parsing: Missing required field: 'atr'
```

### Duplicate Detection

Look for:
```
[WARNING] Duplicate signal detected: BANK_NIFTY BASE_ENTRY Long_1
```

## Testing Workflow

1. **Send test signal:**
   ```bash
   ./test_webhook.sh base_entry
   ```

2. **Check response:**
   - Should see JSON response with `status: "processed"` or `status: "executed"`

3. **Check logs:**
   ```bash
   tail -20 portfolio_manager.log
   ```

4. **Verify processing:**
   - Look for log entries showing signal was parsed and processed
   - Check for any errors or warnings

5. **Check statistics:**
   ```bash
   ./check_processing.sh stats
   ```

## Common Issues

### Issue: "Duplicate signal detected"

**Cause:** Same signal sent within 60 seconds

**Solution:** Wait 60 seconds or change timestamp/position ID

### Issue: "Validation error"

**Cause:** Missing or invalid fields in JSON

**Solution:** Check JSON format matches sample payloads exactly

### Issue: "Signal blocked"

**Cause:** Portfolio gate conditions not met (risk, volatility, margin limits)

**Solution:** This is expected behavior - check the reason in the response

### Issue: No response or timeout

**Cause:** Portfolio manager not running or tunnel down

**Solution:** 
```bash
# Check if running
lsof -Pi :5002

# Restart if needed
python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY
```

## Live Market Testing

When testing with live market data from TradingView:

1. **Use real prices:** Replace sample prices with current market prices
2. **Use current timestamp:** Use `date -u +"%Y-%m-%dT%H:%M:%SZ"` for timestamp
3. **Check market hours:** Portfolio manager may ignore signals outside market hours
4. **Monitor logs:** Use `tail -f portfolio_manager.log` to watch in real-time

## Quick Reference

| Command | Purpose |
|---------|---------|
| `./test_webhook.sh` | Test all signal types |
| `./check_processing.sh` | Check processing status |
| `tail -f portfolio_manager.log` | Monitor logs in real-time |
| `curl .../webhook/stats` | Get webhook statistics |

---

**All sample payloads are in:** `sample_webhook_payloads.json`

