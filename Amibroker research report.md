### Feasibility Analysis & Research Report

Based on deep research into Amibroker’s Custom Backtester (CBT) interface, here is the detailed evaluation for your Tom Basso-style multi-instrument portfolio.

#### 1. Feasibility Score: **YES (With High Complexity)**
Amibroker **can** handle every single requirement you listed, including the advanced ones like shared equity, 3-constraint position sizing, and independent position tracking with distinct stops. However, this is **not** out-of-the-box functionality; it requires writing a "Low-Level CBT" (Custom Backtester) script. You will essentially be writing your own portfolio manager logic inside Amibroker’s engine.

---

#### 2. Technical Findings by Requirement

| Requirement | Amibroker Capability | Implementation Details |
| :--- | :--- | :--- |
| **Shared Equity** | **Native** | The CBT is designed specifically for this. It maintains a single `bo.Equity` property that updates in real-time as trades across all symbols progress. |
| **3-Constraint Sizing** | **Feasible (CBT)** | You cannot do this in standard AFL `PositionSize` syntax effectively. You must calculate it inside the CBT loop (`PreProcess` phase) where you have access to `bo.Equity`, `bo.Cash`, and symbol-specific `ATR` values simultaneously. |
| **Independent Positions** | **Feasible (Advanced)** | Standard Amibroker merges same-symbol positions ("Scale In"). To keep them independent (e.g., Long_1, Long_2), you must use the **Trade Handle** property (`sig.Handle`) in Low-Level CBT to manage them as distinct entities. |
| **Independent Stops** | **Feasible (Manual)** | You must write a loop that iterates through every open trade handle, calculates its specific stop level (based on its own entry price), and calls `ExitTrade` for that specific handle if hit. |
| **Portfolio Constraints** | **Feasible** | Before converting signals to trades, you can sum the risk of all open positions + the new signal's risk. If `Total_Risk > 15%`, you simply discard the signal in the code. |
| **Cross-Instrument Priority** | **Feasible** | In the CBT loop, you get a list of all signals for the bar. You can sort this list using custom logic (e.g., "Risk Headroom") before processing them, effectively prioritizing one instrument over another. |
| **TradingView Import** | **Feasible** | You can import signals via CSV (`Buy = Import...`). However, you **must** also have the historical price data (OHLC) and ATR data loaded in Amibroker to calculate the "3-constraint" size dynamically. |

---

#### 3. Complexity & Development Estimate

**Complexity Score:** **8/10** (Requires advanced programming skills)
**Estimated Code Size:** **400 - 600 lines of AFL**
- **Standard Strategy Code:** ~50 lines (Signal import/generation)
- **Custom Backtester Code:** ~300-500 lines. You need to handle the `PreProcess` loop, iterate through signals, manage the "Trade List" manually, implement the "Handle" logic for stops, and calculate the sizing math.

**Development Time:**
- **Experienced Amibroker Developer:** 3-5 days.
- **New to Amibroker:** 2-4 weeks (The learning curve for Low-Level CBT is steep).

**Processing Speed:**
- **Extremely Fast.** Amibroker is C++ based. Even with this complex logic, backtesting 10 years of data on 2 symbols will take less than 1 second. It is significantly faster than Python iteration.

---

#### 4. Comparison Framework

| Feature | Score (1-10) | Notes |
| :--- | :---: | :--- |
| **Portfolio-level backtesting** | **10** | Native architecture is built for this. |
| **Multi-symbol position sizing** | **9** | Very powerful, but requires CBT code for complex math. |
| **Independent position tracking** | **7** | Possible using "Handles," but requires manual coding (default is merging). |
| **Stop management flexibility** | **8** | Flexible, but requires writing a custom loop to check each handle. |
| **TradingView integration** | **6** | Works (CSV import), but separates logic from data, which can be fragile. |
| **Custom reporting** | **10** | Best in class. You can add any custom metric (Risk%, Vol%) to the report easily. |
| **Code complexity** | **3** | (Lower is better) It is **high complexity**. Python might be more readable for this logic. |
| **Development time** | **5** | Slower than Python for *logic* implementation if you don't know CBT well. |
| **Maintenance/iteration** | **8** | Once built, changing parameters (e.g., Risk 15% -> 20%) is instant. |

---

#### 5. Code Concept (CBT Snippet)

Here is a conceptual skeleton of how the Low-Level CBT would look to handle your "3-Constraint Sizing" and "Portfolio Risk Check":

```c
SetCustomBacktestProc("");

if( Status("action") == actionPortfolio )
{
    bo = GetBacktesterObject();
    bo.PreProcess(); // Initialize

    // Iterate through every bar of history
    for( bar = 0; bar < BarCount; bar++ )
    {
        // 1. Calculate Current Portfolio Risk & Volatility
        CurrentPortRisk = 0;
        CurrentPortVol = 0;
        
        // Loop through open trades to sum up risk
        for( trade = bo.GetFirstOpenPos(); trade; trade = bo.GetNextOpenPos() )
        {
            // You would need to store 'StopDistance' in a custom variable when entering
            RiskPerShare = trade.GetEntryValue() - trade.GetStopLoss(); 
            CurrentPortRisk += (RiskPerShare * trade.GetShares());
        }

        // 2. Process New Signals
        for( sig = bo.GetFirstSignal(bar); sig; sig = bo.GetNextSignal(bar) )
        {
            // A. CHECK PORTFOLIO GATES
            if( CurrentPortRisk > (bo.Equity * 0.15) ) 
            {
                sig.PosSize = 0; // Reject signal
                continue; 
            }

            // B. CALCULATE 3-CONSTRAINT SIZING
            // You need to access Price and ATR from the signal object or Foreign() calls
            StopDist = ...; // Need logic to retrieve this
            
            Lot_R = (bo.Equity * 0.005) / StopDist;
            Lot_V = (bo.Equity * 0.002) / (ATR_Value * PointValue);
            Lot_M = bo.Cash / MarginPerLot; // Simplified
            
            Final_Lots = Min(Lot_R, Min(Lot_V, Lot_M));
            
            // Apply Size
            sig.PosSize = Final_Lots * OneLotValue;
        }

        bo.ProcessTradeSignals( bar ); // Execute trades
    }
    bo.PostProcess();
}
```

---

#### 6. Recommendation

**Choose Python IF:**
- You value **code readability** and "logic visibility" over execution speed.
- You are already comfortable with Python (Pandas/VectorBT/Backtrader).
- You want to inspect the "state" of the portfolio at every step easily (debugging CBT loops can be tricky).
- You want to plug this directly into a live execution engine (OpenAlgo) without bridging Amibroker -> Python.

**Choose Amibroker IF:**
- You need to run **optimizations** (e.g., finding the best Risk% or Pyramid Count). Amibroker will run 10,000 combinations in minutes; Python will take hours/days.
- You want professional-grade **equity curves, drawdowns, and Monte Carlo analysis** out of the box without building them yourself.
- You are willing to hire an Amibroker expert (or spend 2 weeks learning CBT) to build the core engine once.

**Final Verdict for Your Case:**
Since you mentioned integrating with **OpenAlgo (Python)** and your logic is highly specific (Tom Basso independent stops), **Python is likely the better fit** for the *development* and *execution* phase. Amibroker forces you to fight its default "merging" behavior to get independent stops, whereas in Python (custom class), tracking `[Trade1, Trade2]` list is trivial.

**Recommendation: Python** (unless backtest speed/optimization is critical).

### Interesting Findings
- **Trade Handles:** Amibroker *does* support independent trades on the same symbol, but it's a hidden feature in the CBT (`sig.Handle`) that few users utilize. It effectively turns Amibroker into a hedging-compatible engine.
- **Speed Difference:** Amibroker's speed advantage is massive. If you plan to backtest this on 50+ symbols or run genetic optimizations, Python will be a bottleneck. For just 2 symbols (Gold + BankNifty), Python is fast enough.

### Sources
- [Amibroker Custom Backtester Guide](https://www.amibroker.com/guide/a_custombacktest.html)
- [Amibroker Knowledge Base: Low Level CBT](https://www.amibroker.com/kb/category/analysis/backtest-analysis/custom-backtest/)
- [Amibroker Forum: Managing Multiple Positions](https://forum.amibroker.com/t/low-level-custom-backtester-backtestregularraw2multi/39474)
