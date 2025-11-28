#!/bin/bash

# ============================================================================
# Setup Cloudflare Tunnel WITHOUT Domain (Simplest Option)
# ============================================================================
# This script sets up a tunnel that provides a stable URL without needing
# a domain. The URL stays the same as long as you keep the tunnel running.
#
# Usage:
#   ./setup_tunnel_no_domain.sh
# ============================================================================

set -e

PORT=5002

echo "============================================================================"
echo "Cloudflare Tunnel Setup (No Domain Required)"
echo "============================================================================"
echo ""
echo "This setup provides a stable URL that:"
echo "  ✅ Works without any domain"
echo "  ✅ Stays the same as long as tunnel is running"
echo "  ✅ Perfect for TradingView webhooks"
echo ""
echo "⚠️  Note: If you restart the tunnel, you'll get a new URL."
echo "   Solution: Keep the tunnel running (use screen/tmux for background)"
echo ""
echo "============================================================================"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo ""
    echo "Installing cloudflared for macOS..."
    
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is not installed."
        echo "Please install Homebrew first:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    
    brew install cloudflared
    
    if ! command -v cloudflared &> /dev/null; then
        echo "❌ Installation failed."
        exit 1
    fi
    
    echo "✅ cloudflared installed successfully!"
    echo ""
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
echo "Starting Tunnel..."
echo "============================================================================"
echo ""
echo "📡 Tunnel will expose: http://localhost:${PORT}/webhook"
echo ""
echo "⚠️  IMPORTANT:"
echo "   1. Copy the URL shown below (e.g., https://abc123.trycloudflare.com)"
echo "   2. Use it in TradingView: https://YOUR-URL/webhook"
echo "   3. Keep this terminal open - URL stays same as long as tunnel runs"
echo ""
echo "   To run in background, use:"
echo "     screen -S tunnel"
echo "     ./start_tunnel_simple.sh"
echo "     (Press Ctrl+A, then D to detach)"
echo ""
echo "============================================================================"
echo ""

# Start the tunnel
cloudflared tunnel --url http://localhost:${PORT}

