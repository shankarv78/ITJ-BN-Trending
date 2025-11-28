"""
Synthetic Futures Execution with Partial Fill Protection
"""
import time
import logging
from typing import Dict
from openalgo_client import OpenAlgoClient
from bridge_utils import get_atm_strike, get_expiry_date, format_symbol

logger = logging.getLogger(__name__)

class SyntheticFuturesExecutor:
    """Handles synthetic futures execution (SELL PE + BUY CE)"""
    
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
        
        # Calculate strike and expiry
        strike = get_atm_strike(price, self.strike_interval)
        expiry = get_expiry_date(self.use_monthly_expiry)
        
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
        
        # STEP 1: Place PE order (SELL)
        logger.info(f"[1/2] Placing PE SELL order: {pe_symbol} qty={quantity}")
        pe_order = self.client.place_order(pe_symbol, "SELL", quantity)
        
        if pe_order.get('status') != 'success':
            logger.error(f"PE order failed: {pe_order}")
            result['status'] = 'failed'
            result['error'] = 'PE order placement failed'
            result['pe_order_response'] = pe_order
            return result
        
        result['pe_order_id'] = pe_order.get('orderid')
        logger.info(f"PE order placed: {result['pe_order_id']}")
        
        # Wait and confirm PE fill
        if self.enable_partial_fill_protection:
            logger.info("Waiting for PE fill confirmation...")
            time.sleep(2)  # Give time for order to fill
            
            pe_status = self.client.get_order_status(result['pe_order_id'])
            
            if not pe_status:
                logger.error("Could not fetch PE order status")
                result['status'] = 'pe_status_unknown'
                result['warning'] = 'PE status check failed'
                # Continue with caution
            elif pe_status.get('status') not in ['COMPLETE', 'FILLED', 'TRADED']:
                logger.error(f"PE order not filled: {pe_status.get('status')}")
                result['status'] = 'pe_not_filled'
                result['error'] = f"PE order status: {pe_status.get('status')}"
                result['pe_order_status'] = pe_status
                return result
            else:
                result['pe_fill_price'] = float(pe_status.get('price', 0))
                logger.info(f"PE filled at ₹{result['pe_fill_price']}")
        
        # STEP 2: Place CE order (BUY)
        logger.info(f"[2/2] Placing CE BUY order: {ce_symbol} qty={quantity}")
        ce_order = self.client.place_order(ce_symbol, "BUY", quantity)
        
        if ce_order.get('status') != 'success':
            logger.error(f"CE order failed: {ce_order}")
            logger.critical(f"⚠️ ALERT: PE filled but CE failed! PE={pe_symbol} qty={quantity}")
            
            # EMERGENCY: Try to cover PE
            if self.enable_partial_fill_protection:
                logger.info("🚨 Attempting emergency PE cover...")
                cover_order = self.client.place_order(pe_symbol, "BUY", quantity)
                
                if cover_order.get('status') == 'success':
                    logger.info(f"✓ Emergency PE cover successful: {cover_order.get('orderid')}")
                    result['status'] = 'failed_ce_covered'
                    result['error'] = 'CE failed, PE emergency covered'
                    result['cover_order_id'] = cover_order.get('orderid')
                else:
                    logger.critical(f"❌ EMERGENCY COVER FAILED! Manual intervention required!")
                    result['status'] = 'failed_ce_cover_failed'
                    result['error'] = 'CE failed, PE cover also failed - MANUAL ACTION REQUIRED'
                
                result['cover_order'] = cover_order
            else:
                result['status'] = 'failed_ce'
                result['error'] = 'CE order placement failed'
            
            result['ce_order_response'] = ce_order
            return result
        
        result['ce_order_id'] = ce_order.get('orderid')
        logger.info(f"CE order placed: {result['ce_order_id']}")
        
        # Wait and confirm CE fill
        if self.enable_partial_fill_protection:
            logger.info("Waiting for CE fill confirmation...")
            time.sleep(2)
            
            ce_status = self.client.get_order_status(result['ce_order_id'])
            
            if not ce_status:
                logger.warning("Could not fetch CE order status")
                result['status'] = 'ce_status_unknown'
                result['warning'] = 'CE status check failed'
            elif ce_status.get('status') not in ['COMPLETE', 'FILLED', 'TRADED']:
                logger.warning(f"CE order not immediately filled: {ce_status.get('status')}")
                result['status'] = 'ce_pending'
                result['warning'] = f"CE order status: {ce_status.get('status')}"
                result['ce_order_status'] = ce_status
            else:
                result['ce_fill_price'] = float(ce_status.get('price', 0))
                logger.info(f"CE filled at ₹{result['ce_fill_price']}")
                result['status'] = 'success'
        else:
            result['status'] = 'success'
        
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


