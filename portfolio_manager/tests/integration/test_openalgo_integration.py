"""
Integration tests for OpenAlgo broker
"""
import pytest
from brokers.factory import create_broker_client

def test_create_mock_broker():
    """Test creating mock broker"""
    config = {}
    broker = create_broker_client('mock', config)
    assert broker is not None
    assert hasattr(broker, 'place_order')
    assert hasattr(broker, 'get_order_status')
    assert hasattr(broker, 'get_funds')

def test_create_openalgo_broker():
    """Test creating OpenAlgo broker"""
    config = {
        'openalgo_url': 'http://127.0.0.1:5000',
        'openalgo_api_key': 'test_key'
    }
    broker = create_broker_client('openalgo', config)
    assert broker is not None
    assert hasattr(broker, 'place_order')
    assert hasattr(broker, 'get_order_status')

def test_invalid_broker_type():
    """Test invalid broker type raises error"""
    config = {}
    with pytest.raises(ValueError, match="Unknown broker type"):
        create_broker_client('invalid', config)

def test_openalgo_missing_api_key():
    """Test OpenAlgo without API key raises error"""
    config = {'openalgo_url': 'http://127.0.0.1:5000'}
    with pytest.raises(ValueError, match="API key is required"):
        create_broker_client('openalgo', config)
