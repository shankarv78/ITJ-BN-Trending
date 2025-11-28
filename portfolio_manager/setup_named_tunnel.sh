#!/bin/bash

# ============================================================================
# Setup Named Cloudflare Tunnel (Permanent URL)
# ============================================================================
# This script sets up a named tunnel that provides a permanent URL that
# doesn't change even after restarts. Perfect for TradingView alerts!
#
# Usage:
#   ./setup_named_tunnel.sh
# ============================================================================

set -e

TUNNEL_NAME="portfolio-manager"
PORT=5002
CONFIG_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"

echo "============================================================================"
echo "Cloudflare Named Tunnel Setup (Permanent URL)"
echo "============================================================================"
echo ""
echo "This will create a tunnel with a PERMANENT URL that:"
echo "  ✅ Stays the same even after restarts"
echo "  ✅ No need to update TradingView alerts daily"
echo "  ✅ Works with your Cloudflare account (free)"
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

# Step 1: Login to Cloudflare
echo "Step 1: Authenticating with Cloudflare..."
echo ""
echo "This will open your browser to log in to Cloudflare."
echo "You need a free Cloudflare account (create one at cloudflare.com if needed)."
echo ""
read -p "Press Enter to continue..."
echo ""

if [ ! -f "$CONFIG_DIR/cert.pem" ]; then
    cloudflared tunnel login
    echo ""
else
    echo "✅ Already authenticated with Cloudflare"
    echo ""
fi

# Step 2: Create named tunnel
echo "Step 2: Creating named tunnel '$TUNNEL_NAME'..."
echo ""

# Check if tunnel already exists
if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "✅ Tunnel '$TUNNEL_NAME' already exists"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    echo "   Tunnel ID: $TUNNEL_ID"
else
    echo "Creating new tunnel..."
    TUNNEL_OUTPUT=$(cloudflared tunnel create "$TUNNEL_NAME" 2>&1)
    echo "$TUNNEL_OUTPUT"
    
    # Extract tunnel ID from output
    TUNNEL_ID=$(echo "$TUNNEL_OUTPUT" | grep -oP 'Created tunnel \K[^ ]+' || cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    
    if [ -z "$TUNNEL_ID" ]; then
        echo "❌ Failed to create tunnel. Please check the output above."
        exit 1
    fi
    
    echo "✅ Tunnel created: $TUNNEL_ID"
fi

echo ""

# Step 3: Create config file
echo "Step 3: Creating tunnel configuration..."
echo ""

mkdir -p "$CONFIG_DIR"

# Find credentials file
CREDENTIALS_FILE=$(find "$CONFIG_DIR" -name "*.json" -path "*/$TUNNEL_ID/*" 2>/dev/null | head -n 1)

if [ -z "$CREDENTIALS_FILE" ]; then
    # Try alternative location
    CREDENTIALS_FILE="$CONFIG_DIR/$TUNNEL_ID.json"
fi

if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "⚠️  Warning: Could not find credentials file automatically."
    echo "   You may need to specify the path manually in the config file."
    CREDENTIALS_FILE="$CONFIG_DIR/$TUNNEL_ID.json"
fi

# Create config file
# Note: We don't specify a hostname - Cloudflare will assign one automatically
# on first run, and that will become the permanent URL
cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

ingress:
  - service: http://localhost:$PORT
EOF

echo "✅ Configuration saved to: $CONFIG_FILE"
echo ""

# Step 4: Route DNS (optional - for trycloudflare.com subdomain, this is automatic)
echo "Step 4: Tunnel configuration complete!"
echo ""

# Step 5: Show how to run
echo "============================================================================"
echo "✅ Setup Complete!"
echo "============================================================================"
echo ""
echo "To start the tunnel with permanent URL:"
echo "  cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "Or use the helper script:"
echo "  ./start_named_tunnel.sh"
echo ""
echo "📝 IMPORTANT: When you first run the tunnel, Cloudflare will:"
echo "   1. Assign a random subdomain (e.g., portfolio-manager-abc123.trycloudflare.com)"
echo "   2. Display the URL in the terminal output"
echo "   3. This URL will be PERMANENT - it won't change after restarts"
echo ""
echo "   Copy that URL and use it in TradingView:"
echo "   https://YOUR-ASSIGNED-URL.trycloudflare.com/webhook"
echo ""
echo "   Once set in TradingView, you never need to change it again!"
echo ""
echo "============================================================================"

