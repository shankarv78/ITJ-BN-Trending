"""
Position Sizing Calculator with Triple-Constraint Logic
"""
import logging
from typing import Dict
from openalgo_client import OpenAlgoClient

logger = logging.getLogger(__name__)

class PositionSizer:
    """Calculates position size based on risk and margin constraints"""
    
    def __init__(self, openalgo_client: OpenAlgoClient, config: Dict):
        """
        Initialize position sizer
        
        Args:
            openalgo_client: OpenAlgo API client
            config: Configuration dict
        """
        self.client = openalgo_client
        self.config = config
        self.risk_percent = config.get('risk_percent', 1.5)
        self.margin_per_lot = config.get('margin_per_lot', 270000)
        self.lot_size = config.get('bank_nifty_lot_size', 35)
    
    def calculate_base_entry_size(self, signal: Dict, current_equity: float = None) -> int:
        """
        Calculate position size for BASE_ENTRY using risk-based method
        
        Logic:
        1. Risk amount = Equity × Risk%
        2. Risk per lot = (Entry - Stop) × Lot_Size
        3. Risk-based lots = Risk_Amount / Risk_Per_Lot
        4. Margin-based lots = Available_Margin / Margin_Per_Lot
        5. Final lots = min(risk_based, margin_based)
        
        Args:
            signal: Signal dict with price, stop
            current_equity: Current account equity (queries if not provided)
            
        Returns:
            Number of lots to trade (0 if insufficient capital)
        """
        price = signal.get('price')
        stop = signal.get('stop')
        
        if not price or not stop:
            logger.error("Missing price or stop in signal")
            return 0
        
        # Get current equity
        if current_equity is None:
            funds = self.client.get_funds()
            current_equity = funds.get('availablecash', 0)
        
        if current_equity <= 0:
            logger.error(f"Invalid equity: ₹{current_equity}")
            return 0
        
        logger.info(f"Calculating position size: Equity=₹{current_equity:,.2f}, Price={price}, Stop={stop}")
        
        # Calculate risk amount
        risk_amount = current_equity * (self.risk_percent / 100)
        logger.debug(f"Risk amount ({self.risk_percent}%): ₹{risk_amount:,.2f}")
        
        # Calculate risk per lot
        risk_per_point = price - stop
        if risk_per_point <= 0:
            logger.error(f"Invalid risk per point: {risk_per_point} (price={price}, stop={stop})")
            return 0
        
        risk_per_lot = risk_per_point * self.lot_size
        logger.debug(f"Risk per lot: {risk_per_point:.2f} pts × {self.lot_size} = ₹{risk_per_lot:,.2f}")
        
        # CONSTRAINT 1: Risk-based lots
        risk_based_lots = int(risk_amount / risk_per_lot)
        logger.debug(f"Risk-based lots: {risk_based_lots}")
        
        # CONSTRAINT 2: Margin-based lots
        margin_based_lots = int(current_equity / self.margin_per_lot)
        logger.debug(f"Margin-based lots: {margin_based_lots} (₹{current_equity:,.2f} / ₹{self.margin_per_lot:,.2f})")
        
        # Take minimum
        final_lots = min(risk_based_lots, margin_based_lots)
        final_lots = max(0, final_lots)  # Ensure non-negative
        
        limiting_factor = "risk" if final_lots == risk_based_lots else "margin"
        logger.info(f"Position size: {final_lots} lots (limited by {limiting_factor})")
        
        return final_lots
    
    def calculate_pyramid_size(self, signal: Dict, base_position_size: int, 
                               current_equity: float = None) -> int:
        """
        Calculate pyramid position size using suggested lots from TradingView
        (TradingView already calculated with triple-constraint logic)
        
        But verify margin availability as safety check
        
        Args:
            signal: Signal dict with suggested_lots
            base_position_size: Size of initial entry (lots)
            current_equity: Current account equity
            
        Returns:
            Number of lots for pyramid (0 if insufficient capital)
        """
        suggested_lots = signal.get('suggested_lots', 0)
        
        if suggested_lots <= 0:
            logger.warning("No suggested lots in pyramid signal")
            return 0
        
        # Get available margin
        if current_equity is None:
            funds = self.client.get_funds()
            current_equity = funds.get('availablecash', 0)
        
        if current_equity <= 0:
            logger.error(f"Invalid equity: ₹{current_equity}")
            return 0
        
        # Safety check: Verify margin availability
        margin_based_lots = int(current_equity / self.margin_per_lot)
        
        # Take minimum of suggested and available
        final_lots = min(suggested_lots, margin_based_lots)
        final_lots = max(0, final_lots)
        
        if final_lots < suggested_lots:
            logger.warning(f"Pyramid reduced: Suggested={suggested_lots}, Available margin={margin_based_lots}, Final={final_lots}")
        else:
            logger.info(f"Pyramid size: {final_lots} lots (as suggested by TradingView)")
        
        return final_lots
    
    def verify_margin_for_lots(self, lots: int, current_equity: float = None) -> bool:
        """
        Verify sufficient margin for given lot size
        
        Args:
            lots: Number of lots to check
            current_equity: Current account equity
            
        Returns:
            True if sufficient margin, False otherwise
        """
        if current_equity is None:
            funds = self.client.get_funds()
            current_equity = funds.get('availablecash', 0)
        
        required_margin = lots * self.margin_per_lot
        available = current_equity >= required_margin
        
        logger.debug(f"Margin check: {lots} lots need ₹{required_margin:,.2f}, available ₹{current_equity:,.2f} - {'✓' if available else '✗'}")
        
        return available
    
    def get_margin_status(self) -> Dict:
        """
        Get current margin status
        
        Returns:
            Dict with available margin, used margin, etc.
        """
        funds = self.client.get_funds()
        available = funds.get('availablecash', 0)
        
        max_lots = int(available / self.margin_per_lot) if self.margin_per_lot > 0 else 0
        
        return {
            'available_cash': available,
            'margin_per_lot': self.margin_per_lot,
            'max_lots': max_lots,
            'available_margin_lakhs': available / 100000
        }


