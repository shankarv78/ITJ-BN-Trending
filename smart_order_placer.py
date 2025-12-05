"""
Smart order placement with retry logic for options trading
Implements: LIMIT orders with 1% buffer → Monitor → Adjust price → Fallback to MARKET
"""
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class SmartOrderPlacer:
    """
    Smart order placement strategy:
    1. Place LIMIT order at LTP ± 1%
    2. Monitor every 3 seconds (5 retries = 15 seconds)
    3. If not filled, modify to mid-price (bid+ask)/2
    4. After 15 seconds, fallback to MARKET order
    """
    
    def __init__(self, client, max_retries: int = 5, retry_interval: float = 3.0):
        """
        Initialize smart order placer
        
        Args:
            client: OpenAlgoClient instance
            max_retries: Maximum retry attempts (default 5 = 15 seconds)
            retry_interval: Seconds between retries (default 3)
        """
        self.client = client
        self.max_retries = max_retries
        self.retry_interval = retry_interval
    
    def place_with_retry(self, symbol: str, action: str, quantity: int,
                        product: str = "NRML") -> Dict:
        """
        Place order with smart retry logic
        
        Strategy:
        - Start with LIMIT order at LTP ± 1%
        - For BUY: LTP * 1.01 (1% above)
        - For SELL: LTP * 0.99 (1% below)
        - Monitor every 3 seconds
        - If not filled, adjust to mid-price: (bid + ask) / 2
        - After 15 seconds (5 retries), place MARKET order
        
        Args:
            symbol: Option symbol
            action: BUY or SELL
            quantity: Number of units
            product: Product type
            
        Returns:
            Result dict with status, order_id, fill_price, etc.
        """
        result = {
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'product': product,
            'status': 'pending',
            'attempts': []
        }
        
        # STEP 1: Get initial quote for limit price
        quote = self.client.get_quote(symbol)
        ltp = quote.get('ltp', 0)
        
        if ltp <= 0:
            logger.error(f"Invalid LTP for {symbol}: {ltp}")
            return {'status': 'failed', 'error': 'Invalid LTP', 'quote': quote}
        
        # Calculate initial limit price (LTP ± 1%)
        if action == "BUY":
            limit_price = round(ltp * 1.01, 2)  # 1% above LTP
            logger.info(f"BUY {symbol}: LTP={ltp}, Limit={limit_price} (+1%)")
        else:  # SELL
            limit_price = round(ltp * 0.99, 2)  # 1% below LTP
            logger.info(f"SELL {symbol}: LTP={ltp}, Limit={limit_price} (-1%)")
        
        result['initial_ltp'] = ltp
        result['initial_limit_price'] = limit_price
        
        # STEP 2: Place initial LIMIT order
        logger.info(f"[Attempt 1/{self.max_retries}] Placing LIMIT order: {action} {quantity} {symbol} @ {limit_price}")
        
        order_response = self.client.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type="LIMIT",
            product=product,
            price=limit_price
        )
        
        if order_response.get('status') != 'success':
            logger.error(f"Order placement failed: {order_response}")
            return {
                'status': 'failed',
                'error': 'Order placement failed',
                'response': order_response
            }
        
        order_id = order_response.get('orderid')
        result['order_id'] = order_id
        result['attempts'].append({
            'attempt': 1,
            'type': 'LIMIT',
            'price': limit_price,
            'timestamp': time.time()
        })
        
        logger.info(f"Order placed: {order_id}")
        
        # STEP 3: Monitor and retry with price adjustments
        for attempt in range(1, self.max_retries + 1):
            time.sleep(self.retry_interval)
            
            # Check order status
            order_status = self.client.get_order_status(order_id)
            
            if not order_status:
                logger.warning(f"[Attempt {attempt}/{self.max_retries}] Could not fetch order status")
                continue
            
            status = order_status.get('status', '').upper()
            logger.info(f"[Attempt {attempt}/{self.max_retries}] Order status: {status}")
            
            # Check if filled
            if status in ['COMPLETE', 'FILLED', 'TRADED']:
                fill_price = float(order_status.get('price', 0))
                logger.info(f"✓ Order FILLED at ₹{fill_price} (attempt {attempt})")
                result['status'] = 'success'
                result['fill_price'] = fill_price
                result['filled_at_attempt'] = attempt
                result['order_status'] = order_status
                return result
            
            # If rejected/cancelled, fail immediately
            if status in ['REJECTED', 'CANCELLED']:
                logger.error(f"Order {status}: {order_status}")
                result['status'] = 'failed'
                result['error'] = f'Order {status}'
                result['order_status'] = order_status
                return result
            
            # If still pending and not last attempt, adjust price
            if attempt < self.max_retries:
                # Get fresh quote
                quote = self.client.get_quote(symbol)
                bid = quote.get('bid', 0)
                ask = quote.get('ask', 0)
                
                if bid > 0 and ask > 0:
                    # Calculate mid-price
                    mid_price = round((bid + ask) / 2, 2)
                    logger.info(f"[Attempt {attempt + 1}/{self.max_retries}] Adjusting price to mid: Bid={bid}, Ask={ask}, Mid={mid_price}")
                    
                    # Modify order to mid-price
                    modify_result = self.client.modify_order(order_id, mid_price)
                    
                    if modify_result.get('status') == 'success':
                        logger.info(f"Order {order_id} modified to ₹{mid_price}")
                        result['attempts'].append({
                            'attempt': attempt + 1,
                            'type': 'LIMIT_MODIFIED',
                            'price': mid_price,
                            'bid': bid,
                            'ask': ask,
                            'timestamp': time.time()
                        })
                    else:
                        logger.warning(f"Order modification failed: {modify_result}")
                else:
                    logger.warning(f"Invalid bid/ask: {bid}/{ask}, skipping price adjustment")
        
        # STEP 4: After max retries, fallback to MARKET order
        logger.warning(f"⚠️ LIMIT order did not fill after {self.max_retries} attempts, placing MARKET order")
        
        # Cancel pending LIMIT order
        cancel_result = self.client.cancel_order(order_id)
        logger.info(f"Cancelled LIMIT order {order_id}: {cancel_result.get('status')}")
        
        # Place MARKET order
        logger.info(f"Placing MARKET order: {action} {quantity} {symbol}")
        market_order = self.client.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type="MARKET",
            product=product
        )
        
        if market_order.get('status') != 'success':
            logger.critical(f"❌ MARKET order FAILED: {market_order}")
            result['status'] = 'failed'
            result['error'] = 'MARKET order failed after LIMIT timeout'
            result['market_order_response'] = market_order
            return result
        
        market_order_id = market_order.get('orderid')
        result['market_order_id'] = market_order_id
        result['attempts'].append({
            'attempt': self.max_retries + 1,
            'type': 'MARKET',
            'timestamp': time.time()
        })
        
        # Wait briefly and check MARKET order status
        time.sleep(1)
        market_status = self.client.get_order_status(market_order_id)
        
        if market_status and market_status.get('status', '').upper() in ['COMPLETE', 'FILLED', 'TRADED']:
            fill_price = float(market_status.get('price', 0))
            logger.info(f"✓ MARKET order FILLED at ₹{fill_price}")
            result['status'] = 'success'
            result['fill_price'] = fill_price
            result['filled_at_attempt'] = self.max_retries + 1
            result['filled_via'] = 'MARKET'
            result['order_status'] = market_status
        else:
            logger.warning(f"MARKET order status unknown: {market_status}")
            result['status'] = 'market_pending'
            result['warning'] = 'MARKET order placed but status unknown'
            result['order_status'] = market_status
        
        return result


