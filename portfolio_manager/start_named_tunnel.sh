#!/bin/bash

# ============================================================================
# Start Named Cloudflare Tunnel (Permanent URL)
# ============================================================================
# This script starts the named tunnel that provides a permanent URL.
#
# Usage:
#   ./start_named_tunnel.sh
# ============================================================================

set -e

TUNNEL_NAME="portfolio-manager"
PORT=5002

echo "Starting named tunnel: $TUNNEL_NAME"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo "   Run: brew install cloudflared"
    exit 1
fi

# Check if tunnel exists
if ! cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "❌ Tunnel '$TUNNEL_NAME' does not exist."
    echo ""
    echo "Please run setup first:"
    echo "  ./setup_named_tunnel.sh"
    exit 1
fi

# Check if portfolio manager is running
if ! lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  WARNING: Portfolio manager is not running on port ${PORT}"
    echo "   Please start it first:"
    echo "   python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ Portfolio manager is running on port ${PORT}"
    echo ""
fi

echo "============================================================================"
echo "Starting Named Tunnel: $TUNNEL_NAME"
echo "============================================================================"
echo ""

# Check config file for hostname
CONFIG_FILE="$HOME/.cloudflared/config.yml"
if [ -f "$CONFIG_FILE" ]; then
    HOSTNAME=$(grep -E "^\s+hostname:" "$CONFIG_FILE" | head -n 1 | awk '{print $2}' | tr -d '"' | tr -d "'")
    if [ -n "$HOSTNAME" ]; then
        echo "📡 Your PERMANENT webhook URL:"
        echo "   https://$HOSTNAME/webhook"
        echo ""
    fi
fi

echo "📡 This tunnel provides a PERMANENT URL that:"
echo "   ✅ Stays the same after restarts"
echo "   ✅ No need to update TradingView alerts"
echo ""
echo "⚠️  IMPORTANT: Keep this terminal window open while trading!"
echo "   Press Ctrl+C to stop the tunnel."
echo ""
echo "============================================================================"
echo ""

# Start the tunnel
cloudflared tunnel run "$TUNNEL_NAME"

