# Google Sheets Trade Log Template

**Purpose:** Track all trades, slippage, divergence, and P&L for Bank Nifty v6 strategy

**Access:** https://sheets.google.com → Create new spreadsheet → "BN v6 Trade Log"

---

## Sheet 1: Trade Log (Main)

### Column Headers (Row 1)

```
A: Date
B: Time
C: Signal Type
D: Signal Price
E: Actual Fill
F: Slippage
G: Lots
H: Actual P&L
I: Theoretical P&L
J: Divergence
K: Notes
L: Cumulative P&L
M: Position Size (₹)
N: Commission
O: Net P&L
```

### Column Formulas

**Column F (Slippage) - Cell F2:**
```
=IF(E2="","",E2-D2)
```

**Column J (Divergence) - Cell J2:**
```
=IF(AND(I2<>"",H2<>""),I2-H2,"")
```

**Column L (Cumulative P&L) - Cell L2:**
```
=IF(O2="","",SUM($O$2:O2))
```

**Column M (Position Size ₹) - Cell M2:**
```
=IF(G2="","",G2*15*D2)
```
*Assumes lot size = 15 (current Bank Nifty lot size)*

**Column N (Commission) - Cell N2:**
```
=IF(M2="","",M2*0.001)
```
*Assumes 0.1% commission (adjust as needed)*

**Column O (Net P&L) - Cell O2:**
```
=IF(H2="","",H2-N2)
```

### Example Data (Rows 2-4)

| Date | Time | Signal Type | Signal Price | Actual Fill | Slippage | Lots | Actual P&L | Theoretical P&L | Divergence | Notes | Cumulative P&L | Position Size | Commission | Net P&L |
|------|------|-------------|--------------|-------------|----------|------|------------|-----------------|------------|-------|----------------|---------------|------------|---------|
| 2025-11-18 | 10:29 | BASE_ENTRY | 50000 | 50150 | 150 | 12 | | | | First base entry | | 9,027,000 | 9,027 | |
| 2025-11-19 | 11:44 | PYRAMID_1 | 50750 | 50850 | 100 | 6 | | | | | | 4,576,500 | 4,577 | |
| 2025-11-20 | 14:29 | EXIT | 49600 | 49550 | -50 | 12 | -72,000 | -48,000 | -24,000 | Stop loss hit | -72,000 | 8,919,000 | 8,919 | -80,919 |

---

## Sheet 2: Dashboard (Summary Metrics)

Create a second sheet named "Dashboard" for real-time metrics.

### Section 1: Performance Metrics

**Layout:**

```
A1: PERFORMANCE METRICS
A2: [Blank]
A3: Total Trades
A4: Winning Trades
A5: Losing Trades
A6: Win Rate
A7: Total P&L (₹)
A8: Total P&L (%)
A9: Average Win
A10: Average Loss
A11: Profit Factor
A12: Largest Win
A13: Largest Loss
A14: Max Drawdown
```

**Column B (Formulas):**

```
B3: =COUNTA('Trade Log'!C:C)-1
B4: =COUNTIF('Trade Log'!O:O,">0")
B5: =COUNTIF('Trade Log'!O:O,"<0")
B6: =IF(B3=0,"",B4/B3)
B7: =SUM('Trade Log'!O:O)
B8: =IF(B7="","",B7/5000000)
B9: =AVERAGEIF('Trade Log'!O:O,">0")
B10: =AVERAGEIF('Trade Log'!O:O,"<0")
B11: =IF(B10=0,"",ABS(B9/B10))
B12: =MAX('Trade Log'!O:O)
B13: =MIN('Trade Log'!O:O)
B14: =MIN('Trade Log'!L:L)
```

**Formatting:**
- B6: Percentage (0.00%)
- B7, B9, B10, B12, B13, B14: Currency (₹#,##0)
- B8: Percentage (0.00%)
- B11: Number (0.00)

### Section 2: Slippage Analysis

```
A16: SLIPPAGE ANALYSIS
A18: Average Slippage
A19: Max Slippage (Positive)
A20: Max Slippage (Negative)
A21: Slippage StdDev
A22: Trades with >100 pts slip
A23: % Trades with High Slip
```

**Column B (Formulas):**

```
B18: =AVERAGE('Trade Log'!F:F)
B19: =MAX('Trade Log'!F:F)
B20: =MIN('Trade Log'!F:F)
B21: =STDEV('Trade Log'!F:F)
B22: =COUNTIF('Trade Log'!F:F,">100")+COUNTIF('Trade Log'!F:F,"<-100")
B23: =IF(B3=0,"",B22/B3)
```

**Formatting:**
- B18, B19, B20, B21: Number (0)
- B23: Percentage (0.00%)

### Section 3: Divergence Tracking

```
A25: DIVERGENCE TRACKING
A27: Average Divergence
A28: Max Positive Divergence
A29: Max Negative Divergence
A30: Divergence StdDev
A31: Trades with >₹10K divergence
```

**Column B (Formulas):**

```
B27: =AVERAGE('Trade Log'!J:J)
B28: =MAX('Trade Log'!J:J)
B29: =MIN('Trade Log'!J:J)
B30: =STDEV('Trade Log'!J:J)
B31: =COUNTIF('Trade Log'!J:J,">10000")+COUNTIF('Trade Log'!J:J,"<-10000")
```

**Formatting:**
- B27, B28, B29, B30: Currency (₹#,##0)

### Section 4: Signal Type Breakdown

```
A33: SIGNAL TYPE BREAKDOWN
A35: Base Entries
A36: Pyramids
A37: Exits
A38: Missed Signals
A39: Skipped Signals
```

**Column B (Count):**

```
B35: =COUNTIF('Trade Log'!C:C,"BASE_ENTRY")
B36: =COUNTIF('Trade Log'!C:C,"PYRAMID*")
B37: =COUNTIF('Trade Log'!C:C,"EXIT")
B38: =COUNTIF('Trade Log'!C:C,"MISSED*")
B39: =COUNTIF('Trade Log'!C:C,"SKIPPED*")
```

---

## Sheet 3: Weekly Summary

Create a third sheet named "Weekly Summary" to track weekly performance.

### Column Headers

```
A: Week Starting
B: Trades
C: Base Entries
D: Pyramids
E: Exits
F: Weekly P&L
G: Cumulative P&L
H: Win Rate
I: Avg Slippage
J: Notes
```

### Manual Entry

Fill this sheet manually at end of each week (Fridays after market close).

### Example Data

| Week Starting | Trades | Base Entries | Pyramids | Exits | Weekly P&L | Cumulative P&L | Win Rate | Avg Slippage | Notes |
|---------------|--------|--------------|----------|-------|------------|----------------|----------|--------------|-------|
| 2025-11-17 | 3 | 1 | 1 | 1 | -72,000 | -72,000 | 0% | 67 | First week live |
| 2025-11-24 | 5 | 1 | 2 | 2 | 120,000 | 48,000 | 50% | 85 | Better execution |

---

## Sheet 4: Position Tracking (Real-time)

Create a fourth sheet named "Open Positions" to track current open positions.

### Column Headers

```
A: Position
B: Entry Date
C: Entry Price (Signal)
D: Entry Price (Actual)
E: Lots
F: Current Stop
G: Highest Close
H: Current Price
I: Unrealized P&L
J: Status
```

### Manual Update

Update this sheet:
- When opening new position
- Daily EOD (update current price, stop, P&L)
- When closing position (move to Trade Log, clear row)

### Example (Open Position)

| Position | Entry Date | Entry Price (Signal) | Entry Price (Actual) | Lots | Current Stop | Highest Close | Current Price | Unrealized P&L | Status |
|----------|------------|----------------------|----------------------|------|--------------|---------------|---------------|----------------|--------|
| Long_1 | 2025-11-18 | 50000 | 50150 | 12 | 49650 | 50150 | 50400 | 45,000 | OPEN |
| Long_2 | 2025-11-19 | 50750 | 50850 | 6 | 50200 | 50850 | 50400 | -40,500 | OPEN |

### Formula for Unrealized P&L (Cell I2)

```
=IF(J2="OPEN",(H2-D2)*E2*15,"")
```

---

## Conditional Formatting (Optional)

### Trade Log Sheet

**Highlight Positive P&L (green):**
- Select column O (Net P&L)
- Format → Conditional formatting
- Format cells if: Greater than 0
- Green background

**Highlight Negative P&L (red):**
- Select column O
- Format → Conditional formatting
- Format cells if: Less than 0
- Red background

**Highlight High Slippage (orange):**
- Select column F (Slippage)
- Format → Conditional formatting
- Format cells if: Greater than 100 OR Less than -100
- Orange background

**Highlight High Divergence (yellow):**
- Select column J (Divergence)
- Format → Conditional formatting
- Format cells if: Greater than 10000 OR Less than -10000
- Yellow background

---

## Data Validation (Optional)

### Signal Type Dropdown

**For column C (Signal Type):**
1. Select column C (from C2 onwards)
2. Data → Data validation
3. Criteria: List from range
4. Add items:
   ```
   BASE_ENTRY
   PYRAMID_1
   PYRAMID_2
   PYRAMID_3
   PYRAMID_4
   PYRAMID_5
   EXIT
   MISSED
   SKIPPED
   ```
5. On invalid data: Reject input

---

## Charts (Optional)

### Chart 1: Cumulative P&L Over Time

1. Select columns A and L (Date and Cumulative P&L)
2. Insert → Chart → Line chart
3. Title: "Cumulative P&L - Bank Nifty v6"
4. X-axis: Date
5. Y-axis: P&L (₹)

### Chart 2: Slippage Distribution

1. Select column F (Slippage)
2. Insert → Chart → Histogram
3. Title: "Slippage Distribution"
4. Bucket size: 50 points

### Chart 3: Win Rate by Signal Type

1. Go to Dashboard sheet
2. Create manual table:
   ```
   | Signal Type | Wins | Total | Win Rate |
   | BASE_ENTRY  | ... | ... | ... |
   | PYRAMID     | ... | ... | ... |
   ```
3. Insert → Chart → Column chart

---

## Mobile Access

**Google Sheets App:**
1. Install on iOS/Android
2. Open "BN v6 Trade Log"
3. Can view real-time during market hours
4. Quick update from mobile when executing trades

---

## Backup & Export

### Weekly Backup

1. File → Download → Microsoft Excel (.xlsx)
2. Save to cloud storage (Google Drive, Dropbox)
3. Filename: `BN_v6_TradeLog_YYYY-MM-DD.xlsx`

### Share with Others

1. File → Share
2. Add email addresses
3. Set permissions: "Viewer" (read-only)

---

## Automation (Phase 2)

Once you set up Python webhook (Phase 2), you can auto-populate this sheet:

**Using Google Sheets API:**

```python
# In your webhook_server.py
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Append row to Google Sheets after trade execution
def log_to_sheets(trade_data):
    creds = service_account.Credentials.from_service_account_file(
        'credentials.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )

    service = build('sheets', 'v4', credentials=creds)
    sheet_id = 'YOUR_SHEET_ID'

    values = [[
        trade_data['date'],
        trade_data['time'],
        trade_data['signal_type'],
        trade_data['signal_price'],
        trade_data['actual_fill'],
        # ... etc
    ]]

    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range='Trade Log!A:O',
        valueInputOption='USER_ENTERED',
        body=body
    ).execute()
```

---

## Troubleshooting

**Formula not calculating:**
- Check if columns are formatted as "Number" not "Plain text"
- Ensure no extra spaces in cells
- Try Ctrl+Shift+Enter to force recalculation

**Cumulative P&L showing wrong value:**
- Verify SUM formula includes $ for absolute reference: `SUM($O$2:O2)`
- Not: `SUM(O$2:O2)` or `SUM(O2:O2)`

**Mobile app not syncing:**
- Ensure internet connection
- Force refresh (pull down on sheet)
- Sign out and sign back in to Google account

---

## Usage Tips

1. **Update immediately after execution** - Don't wait till EOD
2. **Use Notes column liberally** - Context helps later analysis
3. **Review weekly** - Look for slippage patterns, time-of-day effects
4. **Compare theoretical vs actual** - This reveals execution quality
5. **Share with mentor/friend** - Accountability helps discipline

---

**Your Google Sheets trade log is now ready! Start logging trades and build your performance history.**
