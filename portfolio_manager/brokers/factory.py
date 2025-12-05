"""
Broker Factory

Creates appropriate broker client based on configuration
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def create_broker_client(broker_type: str, config: Dict[str, Any]):
    """
    Create broker client based on type
    
    Args:
        broker_type: Type of broker ('openalgo', 'mock')
        config: Broker configuration dictionary
        
    Returns:
        Broker client instance
        
    Raises:
        ValueError: If broker_type is unknown
    """
    if broker_type.lower() == 'openalgo':
        from brokers.openalgo_client import OpenAlgoClient
        
        base_url = config.get('openalgo_url', 'http://127.0.0.1:5000')
        api_key = config.get('openalgo_api_key')
        
        if not api_key:
            raise ValueError("OpenAlgo API key is required")
        
        logger.info(f"Creating OpenAlgo client: {base_url}")
        return OpenAlgoClient(base_url, api_key)
    
    elif broker_type.lower() == 'mock':
        from tests.mocks.mock_broker import MockBrokerSimulator
        
        logger.info("Creating MockBrokerSimulator")
        return MockBrokerSimulator()
    
    else:
        raise ValueError(f"Unknown broker type: {broker_type}")
