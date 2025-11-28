#!/bin/bash

# ============================================================================
# Create Public Hostname for Named Tunnel
# ============================================================================
# This creates a public hostname (trycloudflare.com subdomain) for your
# named tunnel so you can get a permanent URL.
# ============================================================================

set -e

TUNNEL_NAME="portfolio-manager"

echo "============================================================================"
echo "Creating Public Hostname for Tunnel"
echo "============================================================================"
echo ""

# Check if tunnel exists
if ! cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "❌ Tunnel '$TUNNEL_NAME' does not exist."
    echo "   Run: ./setup_named_tunnel.sh first"
    exit 1
fi

echo "Creating public hostname..."
echo ""

# Try to create a public hostname
# Note: This might require the tunnel to be running
OUTPUT=$(cloudflared tunnel public-hostname create "$TUNNEL_NAME" 2>&1 || true)

if echo "$OUTPUT" | grep -q "trycloudflare.com"; then
    echo "✅ Public hostname created!"
    echo ""
    echo "$OUTPUT" | grep "trycloudflare.com"
    echo ""
elif echo "$OUTPUT" | grep -q "already exists"; then
    echo "✅ Public hostname already exists!"
    echo ""
    echo "Listing existing hostnames:"
    cloudflared tunnel public-hostname list "$TUNNEL_NAME" 2>&1 || echo "Could not list hostnames"
    echo ""
else
    echo "⚠️  Could not create public hostname automatically."
    echo ""
    echo "The output was:"
    echo "$OUTPUT"
    echo ""
    echo "Alternative: Use a quick tunnel instead:"
    echo "  ./setup_tunnel_no_domain.sh"
    echo ""
    echo "Or set up with a free domain:"
    echo "  ./setup_tunnel_with_free_domain.sh"
    echo ""
fi

