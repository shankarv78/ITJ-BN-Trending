"""
Signal Loader - Parses TradingView CSV exports

Reads and parses CSV files from TradingView Strategy Tester exports,
extracting signals with enhanced metadata from comment fields.
"""
import logging
import pandas as pd
import re
from datetime import datetime
from typing import List, Dict
from core.models import Signal, SignalType

logger = logging.getLogger(__name__)

class SignalLoader:
    """Loads and parses TradingView strategy export CSVs"""
    
    def __init__(self):
        """Initialize signal loader"""
        pass
    
    def parse_enhanced_comment(self, comment: str) -> Dict:
        """
        Parse enhanced comment with metadata
        
        Format: "ENTRY-5L|ATR:350|ER:0.82|STOP:51650|ST:51650|POS:Long_1"
        
        Args:
            comment: Comment string from CSV
            
        Returns:
            Dict with parsed metadata
        """
        metadata = {}
        
        # Extract lots from base comment
        lots_match = re.search(r'(\d+)L', comment)
        if lots_match:
            metadata['suggested_lots'] = int(lots_match.group(1))
        
        # Extract metadata fields
        patterns = {
            'atr': r'ATR:([\d.]+)',
            'er': r'ER:([\d.]+)',
            'stop': r'STOP:([\d.]+)',
            'supertrend': r'ST:([\d.]+)',
            'position': r'POS:(Long_\d+)',
            'highest': r'HI:([\d.]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, comment)
            if match:
                value = match.group(1)
                if key in ['atr', 'er', 'stop', 'supertrend', 'highest']:
                    metadata[key] = float(value)
                else:
                    metadata[key] = value
        
        return metadata
    
    def load_signals_from_csv(
        self,
        csv_path: str,
        instrument: str
    ) -> List[Signal]:
        """
        Load signals from TradingView CSV export
        
        Args:
            csv_path: Path to CSV file
            instrument: Instrument name (GOLD_MINI or BANK_NIFTY)
            
        Returns:
            List of Signal objects
        """
        logger.info(f"Loading signals from {csv_path} for {instrument}")
        
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')  # Handle BOM
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            return []
        
        signals = []
        
        for _, row in df.iterrows():
            try:
                # Parse timestamp
                timestamp = pd.to_datetime(row['Date/Time'])
                
                # Determine signal type
                row_type = row['Type']
                comment = row['Signal']
                
                if 'Entry' in row_type:
                    if 'PYR' in comment:
                        signal_type = SignalType.PYRAMID
                    else:
                        signal_type = SignalType.BASE_ENTRY
                elif 'Exit' in row_type:
                    signal_type = SignalType.EXIT
                else:
                    continue  # Skip unknown types
                
                # Parse metadata from comment
                metadata = self.parse_enhanced_comment(comment)
                
                # Create signal
                signal = Signal(
                    timestamp=timestamp,
                    instrument=instrument,
                    signal_type=signal_type,
                    position=metadata.get('position', 'Long_1'),
                    price=float(row['Price INR']),
                    stop=metadata.get('stop', 0.0),
                    suggested_lots=metadata.get('suggested_lots', int(row['Position size (qty)'])),
                    atr=metadata.get('atr', 0.0),
                    er=metadata.get('er', 1.0),
                    supertrend=metadata.get('supertrend', metadata.get('stop', 0.0))
                )
                
                signals.append(signal)
                
            except Exception as e:
                logger.error(f"Failed to parse row: {e}")
                continue
        
        logger.info(f"Loaded {len(signals)} signals from {csv_path}")
        return signals
    
    def merge_signals_chronologically(
        self,
        gold_signals: List[Signal],
        bn_signals: List[Signal]
    ) -> List[Signal]:
        """
        Merge signals from multiple instruments chronologically
        
        Args:
            gold_signals: List of Gold signals
            bn_signals: List of Bank Nifty signals
            
        Returns:
            Chronologically sorted list of all signals
        """
        all_signals = gold_signals + bn_signals
        all_signals.sort(key=lambda s: s.timestamp)
        
        logger.info(f"Merged {len(gold_signals)} Gold + {len(bn_signals)} BN signals "
                   f"= {len(all_signals)} total")
        
        return all_signals

