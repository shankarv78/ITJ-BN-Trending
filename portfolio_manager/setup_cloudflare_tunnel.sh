#!/bin/bash

# ============================================================================
# Cloudflare Tunnel Setup Script for Portfolio Manager
# ============================================================================
# This script sets up Cloudflare Tunnel to expose your local portfolio
# manager webhook endpoint to the internet for TradingView alerts.
#
# Usage:
#   ./setup_cloudflare_tunnel.sh
# ============================================================================

set -e  # Exit on error

PORT=5002
WEBHOOK_PATH="/webhook"

echo "============================================================================"
echo "Cloudflare Tunnel Setup for Portfolio Manager"
echo "============================================================================"
echo ""
echo "This script will:"
echo "  1. Check if cloudflared is installed"
echo "  2. Install cloudflared if needed (macOS)"
echo "  3. Start a tunnel to expose localhost:${PORT}${WEBHOOK_PATH}"
echo "  4. Provide the public URL for TradingView webhooks"
echo ""
echo "============================================================================"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo ""
    echo "Installing cloudflared for macOS..."
    echo ""
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is not installed."
        echo ""
        echo "Please install Homebrew first:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo ""
        echo "Then run this script again."
        exit 1
    fi
    
    echo "Installing cloudflared via Homebrew..."
    brew install cloudflared
    
    if ! command -v cloudflared &> /dev/null; then
        echo "❌ Installation failed. Please install manually:"
        echo "   brew install cloudflared"
        echo ""
        echo "Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
        exit 1
    fi
    
    echo "✅ cloudflared installed successfully!"
    echo ""
else
    echo "✅ cloudflared is already installed"
    echo "   Version: $(cloudflared --version | head -n 1)"
    echo ""
fi

# Check if portfolio manager is running
echo "Checking if portfolio manager is running on port ${PORT}..."
if ! lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  WARNING: Portfolio manager is not running on port ${PORT}"
    echo ""
    echo "Please start the portfolio manager first:"
    echo "  cd portfolio_manager"
    echo "  python portfolio_manager.py live --broker zerodha --api-key YOUR_KEY"
    echo ""
    echo "Then run this script again in a separate terminal."
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

# Start the tunnel
echo "============================================================================"
echo "Starting Cloudflare Tunnel..."
echo "============================================================================"
echo ""
echo "📡 Tunnel will expose: http://localhost:${PORT}${WEBHOOK_PATH}"
echo ""
echo "⚠️  IMPORTANT: Keep this terminal window open while trading!"
echo "   Press Ctrl+C to stop the tunnel."
echo ""
echo "============================================================================"
echo ""

# Start cloudflared tunnel
# The --url flag creates a temporary tunnel
cloudflared tunnel --url http://localhost:${PORT}

