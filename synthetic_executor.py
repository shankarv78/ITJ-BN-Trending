"""
Synthetic Futures Execution with Smart Order Placement
Uses LIMIT orders with retry logic for better fill prices
"""
import time
import logging
from typing import Dict
from openalgo_client import OpenAlgoClient
from smart_order_placer import SmartOrderPlacer
from bridge_utils import get_atm_strike, get_expiry_date, format_symbol

logger = logging.getLogger(__name__)

class SyntheticFuturesExecutor:
    """Handles synthetic futures execution (SELL PE + BUY CE) with smart order placement"""

    def __init__(self, openalgo_client: OpenAlgoClient, config: Dict):
        """
        Initialize executor

        Args:
            openalgo_client: OpenAlgo API client
            config: Configuration dict
        """
        self.client = openalgo_client
        self.config = config
        self.lot_size = config.get('bank_nifty_lot_size', 35)
        self.strike_interval = config.get('strike_interval', 100)
        self.use_monthly_expiry = config.get('use_monthly_expiry', True)
        self.broker = config.get('broker', 'zerodha')
        self.enable_partial_fill_protection = config.get('enable_partial_fill_protection', True)

        # Initialize smart order placer
        max_retries = config.get('order_retry_attempts', 5)
        retry_interval = config.get('order_retry_interval', 3.0)
        self.smart_placer = SmartOrderPlacer(
            client=openalgo_client,
            max_retries=max_retries,
            retry_interval=retry_interval
        )
        logger.info(f"Smart order placer initialized: {max_retries} retries @ {retry_interval}s intervals")
    
    def execute_synthetic_long(self, signal: Dict, lots: int) -> Dict:
        """
        Execute synthetic long future (SELL PE + BUY CE)
        
        Args:
            signal: Signal dict with price, position, etc.
            lots: Number of lots to trade
            
        Returns:
            Execution result dict with status, order IDs, fill prices, etc.
        """
        price = signal.get('price')
        position_id = signal.get('position')
        
        logger.info(f"Executing synthetic long: {position_id}, Price={price}, Lots={lots}")
        
        # Calculate strike and expiry with auto-rollover (7 days before expiry)
        strike = get_atm_strike(price, self.strike_interval)
        expiry = get_expiry_date(self.use_monthly_expiry, rollover_days=7)
        
        # Format symbols
        pe_symbol = format_symbol('BANKNIFTY', expiry, strike, 'PE', self.broker)
        ce_symbol = format_symbol('BANKNIFTY', expiry, strike, 'CE', self.broker)
        
        quantity = lots * self.lot_size
        
        result = {
            'position_id': position_id,
            'strike': strike,
            'expiry': expiry,
            'quantity_lots': lots,
            'quantity_units': quantity,
            'pe_symbol': pe_symbol,
            'ce_symbol': ce_symbol,
            'status': 'pending',
            'execution_timestamp': time.time()
        }
        
        # STEP 1: Place PE order (SELL) with smart retry logic
        logger.info(f"[1/2] Placing PE SELL order with smart retry: {pe_symbol} qty={quantity}")
        pe_result = self.smart_placer.place_with_retry(pe_symbol, "SELL", quantity)

        if pe_result.get('status') != 'success':
            logger.error(f"PE order failed: {pe_result}")
            result['status'] = 'failed'
            result['error'] = 'PE order failed after retries'
            result['pe_result'] = pe_result
            return result

        # PE filled successfully
        result['pe_order_id'] = pe_result.get('order_id')
        result['pe_fill_price'] = pe_result.get('fill_price', 0)
        result['pe_attempts'] = pe_result.get('attempts', [])
        logger.info(f"✓ PE filled at ₹{result['pe_fill_price']} ({len(result['pe_attempts'])} attempts)")

        # STEP 2: Place CE order (BUY) with smart retry logic
        logger.info(f"[2/2] Placing CE BUY order with smart retry: {ce_symbol} qty={quantity}")
        ce_result = self.smart_placer.place_with_retry(ce_symbol, "BUY", quantity)

        if ce_result.get('status') != 'success':
            logger.error(f"CE order failed: {ce_result}")
            logger.critical(f"⚠️ ALERT: PE filled but CE failed! PE={pe_symbol} qty={quantity}")

            # EMERGENCY: Try to cover PE with MARKET order
            if self.enable_partial_fill_protection:
                logger.info("🚨 Attempting emergency PE cover with MARKET order...")
                cover_order = self.client.place_order(
                    pe_symbol, "BUY", quantity,
                    order_type="MARKET"
                )

                if cover_order.get('status') == 'success':
                    logger.info(f"✓ Emergency PE cover successful: {cover_order.get('orderid')}")
                    result['status'] = 'failed_ce_covered'
                    result['error'] = 'CE failed after retries, PE emergency covered'
                    result['cover_order_id'] = cover_order.get('orderid')
                else:
                    logger.critical(f"❌ EMERGENCY COVER FAILED! Manual intervention required!")
                    result['status'] = 'failed_ce_cover_failed'
                    result['error'] = 'CE failed, PE cover also failed - MANUAL ACTION REQUIRED'

                result['cover_order'] = cover_order
            else:
                result['status'] = 'failed_ce'
                result['error'] = 'CE order failed after retries'

            result['ce_result'] = ce_result
            return result

        # Both legs filled successfully
        result['ce_order_id'] = ce_result.get('order_id')
        result['ce_fill_price'] = ce_result.get('fill_price', 0)
        result['ce_attempts'] = ce_result.get('attempts', [])
        result['status'] = 'success'
        logger.info(f"✓ CE filled at ₹{result['ce_fill_price']} ({len(result['ce_attempts'])} attempts)")
        
        # Calculate effective entry price (if both fills available)
        if 'pe_fill_price' in result and 'ce_fill_price' in result:
            # Synthetic long entry = Spot - (PE premium received - CE premium paid)
            net_premium = result['pe_fill_price'] - result['ce_fill_price']
            result['effective_entry'] = price - net_premium
            slippage = result['effective_entry'] - price
            result['slippage'] = slippage
            logger.info(f"Effective entry: ₹{result['effective_entry']:.2f}, Slippage: {slippage:+.2f}")
        
        return result
    
    def close_synthetic_long(self, position: Dict) -> Dict:
        """
        Close synthetic long (BUY PE + SELL CE)
        
        Args:
            position: Position dict with pe_symbol, ce_symbol, quantity_units
            
        Returns:
            Exit result dict with status, P&L, etc.
        """
        position_id = position.get('position_id')
        pe_symbol = position.get('pe_symbol')
        ce_symbol = position.get('ce_symbol')
        quantity = position.get('quantity_units')
        
        logger.info(f"Closing synthetic long: {position_id}")
        logger.info(f"PE: {pe_symbol}, CE: {ce_symbol}, Qty: {quantity}")
        
        result = {
            'position_id': position_id,
            'status': 'pending',
            'exit_timestamp': time.time()
        }
        
        # STEP 1: BUY PE (cover short)
        logger.info(f"[1/2] Buying back PE: {pe_symbol} qty={quantity}")
        pe_order = self.client.place_order(pe_symbol, "BUY", quantity)
        
        if pe_order.get('status') != 'success':
            logger.error(f"PE cover failed: {pe_order}")
            result['status'] = 'failed_pe_cover'
            result['error'] = 'PE cover order failed'
            result['pe_exit_order'] = pe_order
            return result
        
        result['pe_exit_order_id'] = pe_order.get('orderid')
        logger.info(f"PE cover order placed: {result['pe_exit_order_id']}")
        
        # STEP 2: SELL CE (close long)
        logger.info(f"[2/2] Selling CE: {ce_symbol} qty={quantity}")
        ce_order = self.client.place_order(ce_symbol, "SELL", quantity)
        
        if ce_order.get('status') != 'success':
            logger.error(f"CE exit failed: {ce_order}")
            logger.warning(f"⚠️ PE covered but CE exit failed for {position_id}")
            result['status'] = 'partial_pe_covered'
            result['error'] = 'CE exit order failed'
            result['ce_exit_order'] = ce_order
            return result
        
        result['ce_exit_order_id'] = ce_order.get('orderid')
        logger.info(f"CE exit order placed: {result['ce_exit_order_id']}")
        result['status'] = 'success'
        
        # Calculate P&L if fill prices available
        time.sleep(2)
        pe_exit_status = self.client.get_order_status(result['pe_exit_order_id'])
        ce_exit_status = self.client.get_order_status(result['ce_exit_order_id'])
        
        if pe_exit_status and ce_exit_status:
            pe_exit_price = float(pe_exit_status.get('price', 0))
            ce_exit_price = float(ce_exit_status.get('price', 0))
            
            result['pe_exit_price'] = pe_exit_price
            result['ce_exit_price'] = ce_exit_price
            
            # Calculate P&L
            pe_entry_price = position.get('pe_fill_price', 0)
            ce_entry_price = position.get('ce_fill_price', 0)
            
            if pe_entry_price > 0 and ce_entry_price > 0:
                # PE P&L: Sold at entry, bought at exit
                pe_pnl = (pe_entry_price - pe_exit_price) * quantity
                # CE P&L: Bought at entry, sold at exit
                ce_pnl = (ce_exit_price - ce_entry_price) * quantity
                
                total_pnl = pe_pnl + ce_pnl
                result['pnl'] = total_pnl
                result['pe_pnl'] = pe_pnl
                result['ce_pnl'] = ce_pnl
                
                logger.info(f"Position closed - P&L: ₹{total_pnl:,.2f} (PE: ₹{pe_pnl:,.2f}, CE: ₹{ce_pnl:,.2f})")
            else:
                logger.warning("Could not calculate P&L: missing entry prices")
        else:
            logger.warning("Could not fetch exit prices for P&L calculation")
        
        return result


