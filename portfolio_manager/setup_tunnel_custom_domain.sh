#!/bin/bash

# ============================================================================
# Setup Cloudflare Tunnel with Custom Domain
# ============================================================================
# This sets up a permanent URL using your custom domain.
#
# Usage:
#   ./setup_tunnel_custom_domain.sh
# ============================================================================

set -e

TUNNEL_NAME="portfolio-manager"
DOMAIN="shankarvasudevan.com"
SUBDOMAIN="webhook"  # Will create: webhook.shankarvasudevan.com
FULL_HOSTNAME="${SUBDOMAIN}.${DOMAIN}"
PORT=5002
CONFIG_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"

echo "============================================================================"
echo "Cloudflare Tunnel Setup with Custom Domain"
echo "============================================================================"
echo ""
echo "Domain: $DOMAIN"
echo "Subdomain: $SUBDOMAIN"
echo "Full URL: https://$FULL_HOSTNAME/webhook"
echo ""
echo "============================================================================"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo "   Run: brew install cloudflared"
    exit 1
fi

# Step 1: Check if domain is in Cloudflare
echo "Step 1: Checking if domain is in Cloudflare..."
echo ""

# Try to list zones to see if domain exists
if cloudflared tunnel login 2>&1 | grep -q "already logged in" || [ -f "$CONFIG_DIR/cert.pem" ]; then
    echo "✅ Already authenticated with Cloudflare"
else
    echo "Authenticating with Cloudflare..."
    echo "This will open your browser."
    echo ""
    read -p "Press Enter to continue..."
    cloudflared tunnel login
    echo ""
fi

# Step 2: Check if tunnel exists, create if not
echo "Step 2: Setting up tunnel '$TUNNEL_NAME'..."
echo ""

if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "✅ Tunnel '$TUNNEL_NAME' already exists"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    echo "   Tunnel ID: $TUNNEL_ID"
else
    echo "Creating tunnel '$TUNNEL_NAME'..."
    TUNNEL_OUTPUT=$(cloudflared tunnel create "$TUNNEL_NAME" 2>&1)
    echo "$TUNNEL_OUTPUT"
    
    TUNNEL_ID=$(echo "$TUNNEL_OUTPUT" | grep -oP 'Created tunnel \K[^ ]+' || cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    
    if [ -z "$TUNNEL_ID" ]; then
        echo "❌ Failed to create tunnel"
        exit 1
    fi
    
    echo "✅ Tunnel created: $TUNNEL_ID"
fi

echo ""

# Step 3: Find credentials file
echo "Step 3: Locating credentials..."
echo ""

CREDENTIALS_FILE=$(find "$CONFIG_DIR" -name "*.json" -path "*/$TUNNEL_ID/*" 2>/dev/null | head -n 1)

if [ -z "$CREDENTIALS_FILE" ]; then
    # Try alternative location
    CREDENTIALS_FILE="$CONFIG_DIR/$TUNNEL_ID.json"
fi

if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "⚠️  Warning: Could not find credentials file automatically."
    echo "   Expected location: $CREDENTIALS_FILE"
    echo "   Please check: ls -la $CONFIG_DIR/"
    read -p "Press Enter to continue anyway..."
fi

echo "✅ Credentials file: $CREDENTIALS_FILE"
echo ""

# Step 4: Create/update config file
echo "Step 4: Creating configuration..."
echo ""

mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

ingress:
  - hostname: $FULL_HOSTNAME
    service: http://localhost:$PORT
  - service: http_status:404
EOF

echo "✅ Configuration saved to: $CONFIG_FILE"
echo ""

# Step 5: Route DNS
echo "Step 5: Configuring DNS route..."
echo ""
echo "This will create a CNAME record: $SUBDOMAIN -> $TUNNEL_ID.cfargotunnel.com"
echo ""

read -p "Press Enter to configure DNS (or Ctrl+C to cancel)..."
echo ""

DNS_OUTPUT=$(cloudflared tunnel route dns "$TUNNEL_NAME" "$FULL_HOSTNAME" 2>&1)

if echo "$DNS_OUTPUT" | grep -q "success\|created\|already exists"; then
    echo "✅ DNS route configured successfully!"
    echo ""
else
    echo "⚠️  DNS configuration output:"
    echo "$DNS_OUTPUT"
    echo ""
    echo "If you see an error, you may need to:"
    echo "  1. Ensure $DOMAIN is added to Cloudflare"
    echo "  2. Check that you have permission to modify DNS"
    echo "  3. Manually create CNAME: $SUBDOMAIN -> $TUNNEL_ID.cfargotunnel.com"
    echo ""
fi

# Step 6: Summary
echo "============================================================================"
echo "✅ Setup Complete!"
echo "============================================================================"
echo ""
echo "Your PERMANENT webhook URL:"
echo "  https://$FULL_HOSTNAME/webhook"
echo ""
echo "To start the tunnel:"
echo "  cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "Or use:"
echo "  ./start_named_tunnel.sh"
echo ""
echo "============================================================================"
echo ""
echo "⚠️  Important:"
echo "  1. Make sure $DOMAIN is added to your Cloudflare account"
echo "  2. DNS propagation may take a few minutes"
echo "  3. Test the URL after starting the tunnel"
echo ""

