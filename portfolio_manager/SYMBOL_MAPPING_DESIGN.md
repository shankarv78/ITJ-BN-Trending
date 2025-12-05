# Symbol Mapping Design Document
## End-to-End Signal → Order Flow

**Version:** 1.0
**Date:** December 3, 2025
**Status:** Draft
**TaskMaster Reference:** Task #33 - Implement OpenAlgo Symbol Format Translation

---

## Quick Reference

### End-to-End Signal/Order Flow Architecture

```
╔═══════════════════════════════════════════════════════════════════════════════════════════╗
║                        END-TO-END SIGNAL → ORDER FLOW                                      ║
╠═══════════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                            ║
║  ┌─────────────────┐   ┌───────────────────────────────┐   ┌─────────────┐   ┌──────────┐║
║  │   TRADINGVIEW   │   │      PORTFOLIO MANAGER        │   │  OPENALGO   │   │  BROKER  │║
║  │                 │   │                               │   │             │   │          │║
║  │  Pine Script    │──▶│  1. Webhook Handler           │──▶│  Unified    │──▶│  Dhan    │║
║  │  Alert/Webhook  │   │  2. Signal Parser             │   │  REST API   │   │  Zerodha │║
║  │                 │   │  3. Symbol Mapper  ◀──────────│   │  Broker     │   │  Angel   │║
║  │                 │   │  4. Position Sizer            │   │  Adapter    │   │  etc.    │║
║  │                 │   │  5. Order Executor            │   │             │   │          │║
║  └─────────────────┘   └───────────────────────────────┘   └─────────────┘   └──────────┘║
║                                                                                            ║
║         │                         │                              │                │        ║
║         │                         │                              │                │        ║
║         ▼                         ▼                              ▼                ▼        ║
║  ┌─────────────────┐   ┌───────────────────────────────┐   ┌─────────────┐   ┌──────────┐║
║  │  SYMBOL FORMAT  │   │        SYMBOL FORMAT          │   │   SYMBOL    │   │  SYMBOL  │║
║  │                 │   │                               │   │   FORMAT    │   │  FORMAT  │║
║  │  "GOLD_MINI"    │   │  Gold: "GOLDM05JAN26FUT"      │   │   OpenAlgo  │   │  Broker  │║
║  │  "BANK_NIFTY"   │   │  BN:   "BANKNIFTY26DEC50000PE"│   │   Standard  │   │  Specific│║
║  │                 │   │        "BANKNIFTY26DEC50000CE"│   │   (same)    │   │  (auto)  │║
║  └─────────────────┘   └───────────────────────────────┘   └─────────────┘   └──────────┘║
║                                                                                            ║
║  LAYER:  TradingView      Portfolio Manager Internal       OpenAlgo API    Broker API     ║
║                                                                                            ║
╚═══════════════════════════════════════════════════════════════════════════════════════════╝
```

### Symbol Format by Layer (Complete Reference)

| Layer | Gold Mini | Bank Nifty (Synthetic) | Notes |
|-------|-----------|------------------------|-------|
| **TradingView** | `GOLDMINI` / `MCX:GOLDM` | `BANKNIFTY` / `NSE:BANKNIFTY` | Pine Script chart symbols |
| **Webhook Payload** | `GOLD_MINI` | `BANK_NIFTY` | Internal generic names |
| **Portfolio Manager** | `GOLD_MINI` | `BANK_NIFTY` | Same as webhook |
| **Symbol Mapper Output** | `GOLDM05JAN26FUT` | `BANKNIFTY26DEC2450000PE` + `BANKNIFTY26DEC2450000CE` | OpenAlgo standard format |
| **OpenAlgo API** | Same as above | Same as above | Unified format across brokers |
| **Dhan** | `security_id` (numeric) | `security_id` (numeric) | Auto-translated by OpenAlgo |
| **Zerodha** | `GOLDM25JANFUT` | `BANKNIFTY2412650000PE` | Auto-translated by OpenAlgo |

### Key Architecture Decision

> **OpenAlgo handles broker-specific translation automatically via its broker adapter layer.**
>
> We only need to translate from generic names (`GOLD_MINI`, `BANK_NIFTY`) to **OpenAlgo Standard Format**.
> OpenAlgo's broker adapter handles the final translation to broker-specific format (Dhan, Zerodha, etc.)

### Instrument Complexity

| Instrument | Type | Orders per Signal | Exchange | Expiry Rule |
|------------|------|-------------------|----------|-------------|
| **Gold Mini** | Simple Futures | 1 | MCX | 5th of each month |
| **Bank Nifty** | Synthetic Futures | 2 (PE + CE) | NFO | Last Thursday of month |

---

## 1. Problem Statement

The Portfolio Manager receives signals with generic instrument names but needs to place orders using broker-specific symbol formats. Different components use different naming conventions:

| Component | Gold Mini | Bank Nifty |
|-----------|-----------|------------|
| TradingView Pine Script | `GOLDMINI` | `BANKNIFTY` |
| Webhook Payload | `GOLD_MINI` | `BANK_NIFTY` |
| OpenAlgo Standard | `GOLDM05JAN26FUT` | `BANKNIFTY26DEC2450000PE/CE` |
| Dhan Broker | `security_id` (numeric) | `security_id` (numeric) |
| Zerodha Broker | `GOLDM25JANFUT` | `BANKNIFTY2412650000PE` |

**Key Challenge:** Bank Nifty uses **synthetic futures** (2 orders: ATM PE Sell + ATM CE Buy), not a simple futures contract.

---

## 2. Architecture: Signal → Order Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                              SIGNAL → ORDER FLOW                                            │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                             │
│  ┌─────────────┐    ┌──────────────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│  │ TradingView │    │   Portfolio Manager  │    │   OpenAlgo   │    │     Broker      │   │
│  │             │    │                      │    │              │    │   (Dhan/Zerodha)│   │
│  │ Pine Script │───▶│  Webhook Handler     │───▶│  REST API    │───▶│   Order API     │   │
│  │ Alert       │    │  Symbol Mapper       │    │  Broker      │    │                 │   │
│  └─────────────┘    │  Order Executor      │    │  Adapter     │    └─────────────────┘   │
│                     └──────────────────────┘    └──────────────┘                          │
│                                                                                             │
│  Webhook Payload:    OpenAlgo Standard:        Broker Specific:                            │
│  ─────────────────   ─────────────────────     ─────────────────                           │
│  {                   POST /placeorder          Auto-translated                             │
│    "instrument":     {                         by OpenAlgo's                               │
│    "GOLD_MINI"       "symbol": "GOLDM05JAN26   broker adapter                              │
│    ...               FUT",                                                                  │
│  }                   "exchange": "MCX"                                                      │
│                      ...                                                                    │
│                     }                                                                       │
│                                                                                             │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. OpenAlgo Symbol Format Specification

Source: [OpenAlgo Symbol Format Documentation](https://docs.openalgo.in/symbol-format)

### 3.1 Futures Format

```
[BaseSymbol][DDMMMYY]FUT
```

**Examples:**
| Instrument | OpenAlgo Symbol |
|------------|-----------------|
| Bank Nifty Futures | `BANKNIFTY26DEC24FUT` |
| Gold Mini (MCX) | `GOLDM05JAN26FUT` |
| Crude Oil Mini | `CRUDEOILM20MAY24FUT` |

### 3.2 Options Format

```
[BaseSymbol][DDMMMYY][Strike][CE/PE]
```

**Examples:**
| Instrument | OpenAlgo Symbol |
|------------|-----------------|
| Nifty 20800 Call | `NIFTY28MAR2420800CE` |
| Bank Nifty 50000 Put | `BANKNIFTY26DEC2450000PE` |
| Bank Nifty 50000 Call | `BANKNIFTY26DEC2450000CE` |

### 3.3 Exchange Codes

| Exchange | Code | Instruments |
|----------|------|-------------|
| NSE Equity | `NSE` | Stocks |
| NSE F&O | `NFO` | Index/Stock Futures & Options |
| MCX | `MCX` | Commodities |
| BSE | `BSE` | Stocks |
| Currency | `CDS` | Currency Futures & Options |

---

## 4. Instrument-Specific Translation

### 4.1 Gold Mini (Simple Futures)

**Input:** `GOLD_MINI`
**Output:** Single symbol

```python
def translate_gold_mini(expiry_date: date) -> str:
    """
    Gold Mini expires on 5th of each month.
    Format: GOLDM[DDMMMYY]FUT
    """
    return f"GOLDM{expiry_date.strftime('%d%b%y').upper()}FUT"

# Example:
# expiry = date(2026, 1, 5)
# Result: "GOLDM05JAN26FUT"
```

**Expiry Rules:**
- Expiry: 5th of every month
- If 5th is holiday, previous trading day
- Current contract = nearest expiry date

### 4.2 Bank Nifty (Synthetic Futures - TWO Orders)

**Input:** `BANK_NIFTY`
**Output:** TWO symbols (PE + CE)

```python
def translate_bank_nifty(expiry_date: date, current_price: float) -> tuple[str, str]:
    """
    Bank Nifty uses synthetic futures = ATM PE Sell + ATM CE Buy
    Format: BANKNIFTY[DDMMMYY][Strike][CE/PE]

    Args:
        expiry_date: Monthly expiry date
        current_price: Current Bank Nifty index price for ATM calculation

    Returns:
        Tuple of (PE_symbol, CE_symbol)
    """
    # Calculate ATM strike (round to nearest 100)
    atm_strike = round(current_price / 100) * 100

    date_str = expiry_date.strftime('%d%b%y').upper()

    pe_symbol = f"BANKNIFTY{date_str}{atm_strike}PE"
    ce_symbol = f"BANKNIFTY{date_str}{atm_strike}CE"

    return (pe_symbol, ce_symbol)

# Example:
# expiry = date(2024, 12, 26)  # Monthly expiry
# price = 50347.50
# ATM strike = 50300 (rounded)
# Result: ("BANKNIFTY26DEC2450300PE", "BANKNIFTY26DEC2450300CE")
```

**Expiry Rules:**
- Bank Nifty Monthly: Last Thursday of month
- If Thursday is holiday, previous trading day
- We use MONTHLY options (not weekly) for lower premium decay

**Synthetic Futures Order Execution:**
| Action | Order 1 (PE) | Order 2 (CE) |
|--------|--------------|--------------|
| Entry (Long) | SELL PE | BUY CE |
| Exit (Close Long) | BUY PE | SELL CE |
| Entry (Short) | BUY PE | SELL CE |
| Exit (Close Short) | SELL PE | BUY CE |

---

## 5. Symbol Mapper Module Design

### 5.1 Class Structure

```python
# core/symbol_mapper.py

from dataclasses import dataclass
from datetime import date
from typing import Union, List, Optional
from enum import Enum

class InstrumentType(Enum):
    GOLD_MINI = "GOLD_MINI"
    BANK_NIFTY = "BANK_NIFTY"

class ExchangeCode(Enum):
    MCX = "MCX"
    NFO = "NFO"
    NSE = "NSE"

@dataclass
class TranslatedSymbol:
    """Result of symbol translation"""
    instrument: InstrumentType
    exchange: ExchangeCode
    symbols: List[str]  # Single for futures, TWO for synthetic
    expiry_date: date
    atm_strike: Optional[int] = None  # Only for options
    is_synthetic: bool = False

@dataclass
class OrderLeg:
    """Individual order leg"""
    symbol: str
    exchange: str
    action: str  # BUY or SELL
    leg_type: str  # "PE", "CE", or "FUT"

class SymbolMapper:
    """
    Translates generic instrument names to OpenAlgo standard format.

    OpenAlgo handles final broker-specific translation automatically.
    """

    def __init__(self, price_provider=None):
        """
        Args:
            price_provider: Callable to get current price for ATM calculation
                           Signature: (symbol: str) -> float
        """
        self.price_provider = price_provider

    def translate(self, instrument: str, action: str = "BUY") -> TranslatedSymbol:
        """
        Translate generic instrument to OpenAlgo symbols.

        Args:
            instrument: Generic name ("GOLD_MINI" or "BANK_NIFTY")
            action: Trade direction ("BUY" for long, "SELL" for short)

        Returns:
            TranslatedSymbol with OpenAlgo-formatted symbols
        """
        if instrument == "GOLD_MINI":
            return self._translate_gold_mini()
        elif instrument == "BANK_NIFTY":
            return self._translate_bank_nifty()
        else:
            raise ValueError(f"Unknown instrument: {instrument}")

    def get_order_legs(self, translated: TranslatedSymbol,
                       action: str, quantity: int) -> List[OrderLeg]:
        """
        Generate order legs for execution.

        For Gold Mini: Single order
        For Bank Nifty: TWO orders (PE + CE)
        """
        pass

    def _translate_gold_mini(self) -> TranslatedSymbol:
        expiry = self._get_gold_mini_expiry()
        symbol = f"GOLDM{expiry.strftime('%d%b%y').upper()}FUT"
        return TranslatedSymbol(
            instrument=InstrumentType.GOLD_MINI,
            exchange=ExchangeCode.MCX,
            symbols=[symbol],
            expiry_date=expiry,
            is_synthetic=False
        )

    def _translate_bank_nifty(self) -> TranslatedSymbol:
        expiry = self._get_bank_nifty_expiry()
        current_price = self._get_bank_nifty_price()
        atm_strike = round(current_price / 100) * 100

        date_str = expiry.strftime('%d%b%y').upper()
        pe_symbol = f"BANKNIFTY{date_str}{atm_strike}PE"
        ce_symbol = f"BANKNIFTY{date_str}{atm_strike}CE"

        return TranslatedSymbol(
            instrument=InstrumentType.BANK_NIFTY,
            exchange=ExchangeCode.NFO,
            symbols=[pe_symbol, ce_symbol],
            expiry_date=expiry,
            atm_strike=atm_strike,
            is_synthetic=True
        )

    def _get_gold_mini_expiry(self) -> date:
        """Get current/next Gold Mini expiry (5th of month)"""
        pass

    def _get_bank_nifty_expiry(self) -> date:
        """Get current/next Bank Nifty monthly expiry (last Thursday)"""
        pass

    def _get_bank_nifty_price(self) -> float:
        """Get current Bank Nifty index price for ATM calculation"""
        if self.price_provider:
            return self.price_provider("NSE:NIFTY BANK")
        raise ValueError("Price provider required for Bank Nifty ATM calculation")
```

### 5.2 Expiry Calendar Logic

```python
# core/expiry_calendar.py

from datetime import date, timedelta
import calendar

def get_gold_mini_expiry(reference_date: date = None) -> date:
    """
    Gold Mini expires on 5th of each month.
    If 5th is weekend, use previous trading day.
    """
    if reference_date is None:
        reference_date = date.today()

    year, month = reference_date.year, reference_date.month

    # If we're past the 5th, use next month
    if reference_date.day > 5:
        month += 1
        if month > 12:
            month = 1
            year += 1

    expiry = date(year, month, 5)

    # Adjust for weekends
    while expiry.weekday() >= 5:  # Saturday or Sunday
        expiry -= timedelta(days=1)

    return expiry

def get_bank_nifty_monthly_expiry(reference_date: date = None) -> date:
    """
    Bank Nifty monthly expiry is last Thursday of month.
    If Thursday is holiday, use previous trading day.
    """
    if reference_date is None:
        reference_date = date.today()

    year, month = reference_date.year, reference_date.month

    # Get last day of month
    last_day = calendar.monthrange(year, month)[1]

    # Find last Thursday
    last_date = date(year, month, last_day)
    while last_date.weekday() != 3:  # Thursday = 3
        last_date -= timedelta(days=1)

    # If we're past this month's expiry, get next month's
    if reference_date > last_date:
        month += 1
        if month > 12:
            month = 1
            year += 1
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        while last_date.weekday() != 3:
            last_date -= timedelta(days=1)

    return last_date
```

---

## 6. Order Executor Updates

### 6.1 Current Flow (Single Order)

```python
# Current: Only handles single symbol
def execute_order(instrument, action, quantity, price):
    symbol = instrument  # No translation!
    openalgo.place_order(symbol, action, quantity, price)
```

### 6.2 New Flow (Synthetic Futures Support)

```python
# New: Handles both simple and synthetic futures
def execute_order(instrument, action, quantity, price):
    mapper = SymbolMapper(price_provider=openalgo.get_quote)
    translated = mapper.translate(instrument, action)

    if translated.is_synthetic:
        # Bank Nifty: Place TWO orders
        results = execute_synthetic_order(translated, action, quantity, price)
    else:
        # Gold Mini: Place single order
        result = execute_simple_order(translated, action, quantity, price)

def execute_synthetic_order(translated, action, quantity, price):
    """
    Execute synthetic futures (PE Sell + CE Buy for long entry)

    Entry Long:  SELL PE, BUY CE
    Exit Long:   BUY PE, SELL CE
    """
    pe_symbol = translated.symbols[0]
    ce_symbol = translated.symbols[1]

    if action == "BUY":  # Long entry
        pe_result = openalgo.place_order(pe_symbol, "SELL", quantity, exchange="NFO")
        ce_result = openalgo.place_order(ce_symbol, "BUY", quantity, exchange="NFO")
    else:  # Close long
        pe_result = openalgo.place_order(pe_symbol, "BUY", quantity, exchange="NFO")
        ce_result = openalgo.place_order(ce_symbol, "SELL", quantity, exchange="NFO")

    return [pe_result, ce_result]
```

---

## 7. TradingView Webhook Integration

### 7.1 Current Webhook Payload

```json
{
  "timestamp": "2025-12-03T16:00:00Z",
  "instrument": "GOLD_MINI",
  "signal_type": "BASE_ENTRY",
  "position_id": "Long_1",
  "price": 76500.0,
  "atr": 450.0,
  "supertrend": 76000.0
}
```

### 7.2 No Changes Needed to Webhook

The webhook payload remains unchanged. Symbol translation happens inside Portfolio Manager:

```
TradingView Alert → Webhook (GOLD_MINI) → Symbol Mapper → OpenAlgo (GOLDM05JAN26FUT)
```

---

## 8. Implementation Tasks

### Phase 1: Core Symbol Mapper
1. Create `core/symbol_mapper.py` with TranslatedSymbol dataclass
2. Implement `_translate_gold_mini()`
3. Implement `_translate_bank_nifty()` with ATM calculation
4. Create `core/expiry_calendar.py` with expiry logic

### Phase 2: Order Executor Integration
5. Update `core/order_executor.py` to use SymbolMapper
6. Add `execute_synthetic_order()` for Bank Nifty
7. Handle partial fill scenarios (one leg fills, other fails)

### Phase 3: Price Provider
8. Add index price lookup to OpenAlgo client
9. Implement `get_bank_nifty_price()` for ATM calculation

### Phase 4: Testing
10. Unit tests for symbol translation
11. Unit tests for expiry calculation
12. Integration tests with OpenAlgo API
13. Paper trading validation

---

## 9. Risk Considerations

### 9.1 Synthetic Futures Leg Risk

If one leg of synthetic futures fails:
- **Scenario:** PE sells but CE buy fails
- **Risk:** Naked short put (unlimited downside risk!)
- **Mitigation:** Must implement rollback if second leg fails

```python
def execute_synthetic_order_with_rollback(translated, action, quantity):
    pe_result = place_order(pe_symbol, pe_action, quantity)

    if pe_result['status'] != 'success':
        return {'status': 'failed', 'reason': 'PE leg failed'}

    ce_result = place_order(ce_symbol, ce_action, quantity)

    if ce_result['status'] != 'success':
        # CRITICAL: Rollback PE leg!
        rollback_action = "BUY" if pe_action == "SELL" else "SELL"
        rollback_result = place_order(pe_symbol, rollback_action, quantity)
        return {'status': 'failed', 'reason': 'CE leg failed, PE rolled back'}

    return {'status': 'success', 'pe': pe_result, 'ce': ce_result}
```

### 9.2 ATM Strike Drift

If Bank Nifty moves significantly between ATM calculation and order execution:
- **Scenario:** Calculate ATM at 50300, by execution price moved to 50600
- **Risk:** Options are no longer truly ATM, affecting delta
- **Mitigation:** Recalculate ATM immediately before order placement

---

## 10. References

- [OpenAlgo Symbol Format](https://docs.openalgo.in/symbol-format)
- [OpenAlgo Symbol API](https://docs.openalgo.in/api-documentation/v1/data-api/symbol)
- [Dhan Instrument List API](https://dhanhq.co/docs/v2/instruments/)
- [Zerodha Trading Symbols](https://kite.trade/forum/discussion/13240/trading-symbols-of-options)

---

## Appendix A: Symbol Format Quick Reference

| Instrument | Internal | OpenAlgo Format | Example |
|------------|----------|-----------------|---------|
| Gold Mini | `GOLD_MINI` | `GOLDM[DDMMMYY]FUT` | `GOLDM05JAN26FUT` |
| Bank Nifty (PE) | `BANK_NIFTY` | `BANKNIFTY[DDMMMYY][Strike]PE` | `BANKNIFTY26DEC2450300PE` |
| Bank Nifty (CE) | `BANK_NIFTY` | `BANKNIFTY[DDMMMYY][Strike]CE` | `BANKNIFTY26DEC2450300CE` |

## Appendix B: Synthetic Futures Order Matrix

| Trade Action | PE Order | CE Order | Result |
|--------------|----------|----------|--------|
| Long Entry | SELL | BUY | Synthetic long futures |
| Close Long | BUY | SELL | Exit long position |
| Short Entry | BUY | SELL | Synthetic short futures |
| Close Short | SELL | BUY | Exit short position |
