#!/bin/bash

# ============================================================================
# Restart Cloudflare Tunnel
# ============================================================================
# Quick script to restart the tunnel if it stopped.
# ============================================================================

set -e

TUNNEL_NAME="portfolio-manager"

echo "Restarting Cloudflare Tunnel..."
echo ""

# Stop any existing tunnel processes
if pgrep -f "cloudflared tunnel" > /dev/null; then
    echo "Stopping existing tunnel processes..."
    pkill -f "cloudflared tunnel"
    sleep 2
fi

# Check if portfolio manager is running
PORT=5002
if ! lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  WARNING: Portfolio manager is not running on port ${PORT}"
    echo "   Please start it first:"
    echo "   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    echo ""
    exit 1
fi

# Check config
CONFIG_FILE="$HOME/.cloudflared/config.yml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config file not found: $CONFIG_FILE"
    echo "   Run: ./setup_tunnel_custom_domain.sh first"
    exit 1
fi

# Show the URL from config
HOSTNAME=$(grep -E "^\s+hostname:" "$CONFIG_FILE" | head -n 1 | awk '{print $2}' | tr -d '"' | tr -d "'")
if [ -n "$HOSTNAME" ]; then
    echo "📡 Your webhook URL:"
    echo "   https://$HOSTNAME/webhook"
    echo ""
fi

echo "Starting tunnel..."
echo "⚠️  Keep this terminal open while trading!"
echo ""

# Start the tunnel
cloudflared tunnel run "$TUNNEL_NAME"

