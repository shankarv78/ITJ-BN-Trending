# How to Find Your Webhook URL

## Your Tunnel Status

✅ **Tunnel is running**: `portfolio-manager` (named tunnel)  
✅ **Portfolio manager is running**: Port 5002

## Where to Find the URL

### Method 1: Check the Terminal Where You Started the Tunnel

The webhook URL is displayed in the terminal where you ran:
```bash
./start_named_tunnel.sh
# or
cloudflared tunnel run portfolio-manager
```

**Look for a line like:**
```
https://portfolio-manager-xxxxx.trycloudflare.com
```

**Your webhook URL will be:**
```
https://portfolio-manager-xxxxx.trycloudflare.com/webhook
```

### Method 2: Check Screen/Tmux Session

If you started the tunnel in a background session:

**For screen:**
```bash
screen -r tunnel
# or
screen -ls  # to see all sessions
```

**For tmux:**
```bash
tmux attach -t tunnel
# or
tmux ls  # to see all sessions
```

### Method 3: Check Log Files

If you redirected output to a log file:
```bash
cat tunnel.log | grep trycloudflare.com
# or
tail -f tunnel.log
```

### Method 4: Restart Tunnel to See URL

If you can't find the terminal, you can restart the tunnel to see the URL:

```bash
# Stop current tunnel
pkill -f "cloudflared tunnel"

# Start it again (URL will be shown)
./start_named_tunnel.sh
```

## Quick Test

Once you have the URL, test it:

```bash
curl -X POST https://YOUR-URL.trycloudflare.com/webhook \
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
    "timestamp": "2025-11-27T10:30:00Z"
  }'
```

Expected response:
```json
{
  "status": "processed",
  "request_id": "...",
  "result": {...}
}
```

## Helper Script

Run this to check your setup:
```bash
./find_webhook_url.sh
```

## Common Locations

- **Terminal window** where you started the tunnel
- **Screen session**: `screen -r tunnel`
- **Tmux session**: `tmux attach -t tunnel`
- **Log file**: `tunnel.log` (if you created one)

---

**Tip:** The URL is assigned when the tunnel first starts. If you can't find it, the easiest way is to check the terminal where you started it, or restart the tunnel to see it again.

