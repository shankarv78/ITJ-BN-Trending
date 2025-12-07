#!/bin/bash
# ============================================
# Uninstall Pipeline Monitor LaunchAgent
# ============================================

PLIST_NAME="com.itj.pipeline-monitor.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🔧 Pipeline Monitor Service Uninstaller"
echo "========================================"
echo ""

# Stop the service if running
if launchctl list | grep -q "com.itj.pipeline-monitor"; then
    echo "⏹️  Stopping service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Remove plist
if [ -f "$PLIST_DEST" ]; then
    echo "🗑️  Removing plist..."
    rm -f "$PLIST_DEST"
fi

echo ""
echo "✅ Pipeline Monitor service uninstalled."
echo "   The monitor will no longer auto-start on login."
echo ""
echo "To run manually: python3 monitor_pipeline.py --daemon"

