#!/bin/bash

# ============================================================================
# Find Your Webhook URL
# ============================================================================
# This script helps you find the webhook URL from your running tunnel.
# ============================================================================

echo "============================================================================"
echo "Finding Your Webhook URL"
echo "============================================================================"
echo ""

# Check if cloudflared is running
CLOUDFLARED_PID=$(pgrep -f "cloudflared tunnel" | head -n 1)

if [ -z "$CLOUDFLARED_PID" ]; then
    echo "❌ Cloudflare tunnel is not running."
    echo ""
    echo "To start it:"
    echo "  ./setup_tunnel_no_domain.sh"
    echo ""
    exit 1
fi

echo "✅ Cloudflare tunnel is running (PID: $CLOUDFLARED_PID)"
echo ""

# Check for named tunnel config
CONFIG_FILE="$HOME/.cloudflared/config.yml"
if [ -f "$CONFIG_FILE" ]; then
    echo "📋 Named tunnel detected (permanent URL)"
    echo ""
    
    # Try to extract domain from config
    DOMAIN=$(grep -E "^\s+hostname:" "$CONFIG_FILE" | head -n 1 | awk '{print $2}' | tr -d '"')
    
    if [ -n "$DOMAIN" ]; then
        echo "Your webhook URL:"
        echo "  https://$DOMAIN/webhook"
        echo ""
    else
        echo "⚠️  Could not find domain in config file."
        echo "   Check the tunnel terminal output for the URL."
        echo ""
    fi
else
    echo "📋 Quick tunnel detected (temporary URL)"
    echo ""
    echo "The URL is shown in the terminal where you started the tunnel."
    echo ""
    echo "To find it:"
    echo "  1. Look at the terminal where you ran: ./setup_tunnel_no_domain.sh"
    echo "  2. Find the line that says:"
    echo "     'https://xxxxx.trycloudflare.com'"
    echo ""
    echo "Or check recent logs:"
    echo ""
    
    # Try to find URL in process output or logs
    if [ -f "tunnel.log" ]; then
        echo "Found tunnel.log - checking for URL:"
        URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' tunnel.log 2>/dev/null | tail -n 1)
        if [ -n "$URL" ]; then
            echo "  $URL"
            echo ""
            echo "Your webhook URL:"
            echo "  $URL/webhook"
            echo ""
        else
            echo "  (No URL found in log file)"
            echo ""
        fi
    fi
fi

# Check if portfolio manager is running
PORT=5002
if lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✅ Portfolio manager is running on port $PORT"
    echo ""
else
    echo "⚠️  Portfolio manager is NOT running on port $PORT"
    echo "   Start it with:"
    echo "   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    echo ""
fi

echo "============================================================================"
echo "Quick Check Commands"
echo "============================================================================"
echo ""
echo "To see tunnel process:"
echo "  ps aux | grep cloudflared"
echo ""
echo "To see tunnel output (if running in screen/tmux):"
echo "  screen -r tunnel    # if using screen"
echo "  tmux attach -t tunnel  # if using tmux"
echo ""
echo "To test your webhook URL:"
echo "  curl -X POST https://YOUR-URL/webhook \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"type\":\"BASE_ENTRY\",\"instrument\":\"BANK_NIFTY\",\"position\":\"Long_1\",\"price\":52000,\"stop\":51650,\"lots\":5,\"atr\":350,\"er\":0.82,\"supertrend\":51650,\"timestamp\":\"2025-11-27T10:30:00Z\"}'"
echo ""
echo "============================================================================"

