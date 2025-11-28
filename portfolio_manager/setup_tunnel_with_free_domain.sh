#!/bin/bash

# ============================================================================
# Setup Cloudflare Tunnel WITH Free Domain (Permanent URL)
# ============================================================================
# This script guides you through getting a free domain and setting up
# a truly permanent URL that never changes.
#
# Usage:
#   ./setup_tunnel_with_free_domain.sh
# ============================================================================

set -e

echo "============================================================================"
echo "Cloudflare Tunnel Setup with Free Domain (Permanent URL)"
echo "============================================================================"
echo ""
echo "This will guide you through:"
echo "  1. Getting a FREE domain (5 minutes)"
echo "  2. Adding it to Cloudflare (2 minutes)"
echo "  3. Setting up permanent tunnel (3 minutes)"
echo ""
echo "Total time: ~10 minutes for a PERMANENT URL that never changes!"
echo ""
echo "============================================================================"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared is not installed."
    echo "   Run: brew install cloudflared"
    exit 1
fi

echo "Step 1: Get a Free Domain"
echo "=========================="
echo ""
echo "Option A: Freenom (Free .tk, .ml, .ga, .cf domains)"
echo "  1. Go to: https://www.freenom.com"
echo "  2. Search for a domain name (e.g., 'yourname')"
echo "  3. Select a free TLD (.tk, .ml, .ga, or .cf)"
echo "  4. Complete registration (free, no credit card needed)"
echo ""
echo "Option B: Use a subdomain of a domain you already own"
echo "  If you have any domain, you can use a subdomain like:"
echo "  webhook.yourdomain.com"
echo ""
read -p "Press Enter once you have a domain ready..."
echo ""

echo "Step 2: Add Domain to Cloudflare"
echo "=================================="
echo ""
echo "1. Go to: https://dash.cloudflare.com"
echo "2. Click 'Add a Site'"
echo "3. Enter your domain name"
echo "4. Select Free plan"
echo "5. Cloudflare will show you nameservers"
echo "6. Update your domain's nameservers at your registrar"
echo ""
echo "⚠️  This can take a few minutes to propagate."
echo ""
read -p "Press Enter once domain is added to Cloudflare..."
echo ""

echo "Step 3: Authenticate Cloudflare Tunnel"
echo "======================================="
echo ""
echo "This will open your browser to authorize the tunnel."
echo ""
read -p "Press Enter to continue..."
echo ""

CONFIG_DIR="$HOME/.cloudflared"
if [ ! -f "$CONFIG_DIR/cert.pem" ]; then
    cloudflared tunnel login
    echo ""
else
    echo "✅ Already authenticated"
    echo ""
fi

echo "Step 4: Create Named Tunnel"
echo "============================"
echo ""
read -p "Enter a name for your tunnel (e.g., 'portfolio-manager'): " TUNNEL_NAME
TUNNEL_NAME=${TUNNEL_NAME:-portfolio-manager}

echo ""
echo "Creating tunnel: $TUNNEL_NAME"
TUNNEL_OUTPUT=$(cloudflared tunnel create "$TUNNEL_NAME" 2>&1)
echo "$TUNNEL_OUTPUT"

TUNNEL_ID=$(echo "$TUNNEL_OUTPUT" | grep -oP 'Created tunnel \K[^ ]+' || cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')

if [ -z "$TUNNEL_ID" ]; then
    echo "❌ Failed to create tunnel"
    exit 1
fi

echo "✅ Tunnel created: $TUNNEL_ID"
echo ""

echo "Step 5: Configure DNS"
echo "====================="
echo ""
read -p "Enter your domain (e.g., webhook.yourname.tk): " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo "❌ Domain is required"
    exit 1
fi

echo ""
echo "Configuring DNS route..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN"

echo ""
echo "✅ DNS configured"
echo ""

echo "Step 6: Create Config File"
echo "=========================="
echo ""

CONFIG_FILE="$CONFIG_DIR/config.yml"
CREDENTIALS_FILE=$(find "$CONFIG_DIR" -name "*.json" -path "*/$TUNNEL_ID/*" 2>/dev/null | head -n 1)

if [ -z "$CREDENTIALS_FILE" ]; then
    CREDENTIALS_FILE="$CONFIG_DIR/$TUNNEL_ID.json"
fi

mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

ingress:
  - hostname: $DOMAIN
    service: http://localhost:5002
  - service: http_status:404
EOF

echo "✅ Configuration saved to: $CONFIG_FILE"
echo ""

echo "============================================================================"
echo "✅ Setup Complete!"
echo "============================================================================"
echo ""
echo "Your PERMANENT webhook URL:"
echo "  https://$DOMAIN/webhook"
echo ""
echo "To start the tunnel:"
echo "  cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "Or use:"
echo "  ./start_named_tunnel.sh"
echo ""
echo "============================================================================"

