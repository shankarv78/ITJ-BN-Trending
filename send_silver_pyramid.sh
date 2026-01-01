#!/bin/bash
# ================================================================
# SILVER MINI PYRAMID SIGNAL - Dec 31, 2025 at 9:00 AM
# ================================================================
# Reason: EOD conditions met at close on Dec 30, conditions_met=true
#         but market had closed. PM couldn't act.
#
# Base Position: 2 lots @ ₹244,010 (entry Dec 30 @ 19:00)
# EOD Close: ₹252,918 | P&L: ₹90,005
# ================================================================

# IMPORTANT: Update price to actual market price at 9 AM before running!
# Check TradingView or broker for current Silver Mini price

# Current signal (use Dec 30 close price as baseline)
PRICE=252900    # <-- UPDATE THIS to actual 9 AM price
STOP=245000     # Stop loss (trailing from base entry)
ATR=2500        # Approximate ATR
SUPERTREND=245000  # Same as stop for pyramid
ROC=2.5         # Rate of change
LOTS=1          # 50% of base (2 lots → 1 lot pyramid)

# Generate timestamp in ISO format
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")

echo "=========================================="
echo "SILVER MINI PYRAMID SIGNAL"
echo "=========================================="
echo "Price:      ₹${PRICE}"
echo "Stop:       ₹${STOP}"
echo "Lots:       ${LOTS}"
echo "ATR:        ${ATR}"
echo "SuperTrend: ${SUPERTREND}"
echo "Timestamp:  ${TIMESTAMP}"
echo ""
echo "Sending to PM webhook..."
echo ""

curl -X POST http://localhost:5002/webhook \
  -H 'Content-Type: application/json' \
  -d "{\"type\":\"PYRAMID\",\"instrument\":\"SILVER_MINI\",\"position\":\"Long_2\",\"price\":${PRICE},\"stop\":${STOP},\"atr\":${ATR},\"er\":0.5,\"supertrend\":${SUPERTREND},\"roc\":${ROC},\"lots\":${LOTS},\"timestamp\":\"${TIMESTAMP}\"}"

echo ""
echo ""
echo "=========================================="
echo "Signal sent! Check PM logs for execution."
echo "=========================================="

