#!/bin/bash

# OpenAlgo Integration Setup Script
# This script integrates OpenAlgo client with Portfolio Manager

set -e  # Exit on error

echo "========================================"
echo "OpenAlgo Integration Setup"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PM_DIR="$SCRIPT_DIR/portfolio_manager"

echo "Script directory: $SCRIPT_DIR"
echo "Portfolio Manager directory: $PM_DIR"
echo ""

# Step 1: Create brokers directory
echo -e "${YELLOW}Step 1: Creating brokers directory...${NC}"
mkdir -p "$PM_DIR/brokers"
echo -e "${GREEN}✓ Created $PM_DIR/brokers${NC}"
echo ""

# Step 2: Copy OpenAlgo client
echo -e "${YELLOW}Step 2: Copying OpenAlgo client...${NC}"
if [ -f "$SCRIPT_DIR/openalgo_client.py" ]; then
    cp "$SCRIPT_DIR/openalgo_client.py" "$PM_DIR/brokers/"
    echo -e "${GREEN}✓ Copied openalgo_client.py${NC}"
else
    echo -e "${RED}✗ Error: openalgo_client.py not found in $SCRIPT_DIR${NC}"
    exit 1
fi
echo ""

# Step 3: Create __init__.py
echo -e "${YELLOW}Step 3: Creating brokers/__init__.py...${NC}"
cat > "$PM_DIR/brokers/__init__.py" << 'EOF'
"""
Broker integration module for Portfolio Manager

Provides abstraction layer for different broker implementations:
- OpenAlgo: Production broker integration
- MockBrokerSimulator: Testing and development
"""

from brokers.factory import create_broker_client

__all__ = ['create_broker_client']
EOF
echo -e "${GREEN}✓ Created brokers/__init__.py${NC}"
echo ""

# Step 4: Create broker factory
echo -e "${YELLOW}Step 4: Creating broker factory...${NC}"
cat > "$PM_DIR/brokers/factory.py" << 'EOF'
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
        
        base_url = config.get('openalgo_url', 'http://localhost:5000')
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
EOF
echo -e "${GREEN}✓ Created brokers/factory.py${NC}"
echo ""

# Step 5: Create example config
echo -e "${YELLOW}Step 5: Creating example configuration...${NC}"
cat > "$PM_DIR/openalgo_config.json.example" << 'EOF'
{
  "openalgo_url": "http://localhost:5000",
  "openalgo_api_key": "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD",
  "broker": "zerodha",
  "execution_mode": "analyzer",
  "risk_percent": 1.5,
  "margin_per_lot_banknifty": 270000,
  "margin_per_lot_goldmini": 105000,
  "max_pyramids": 5,
  "bank_nifty_lot_size": 30,
  "gold_mini_lot_size": 100,
  "market_start_hour": 9,
  "market_start_minute": 15,
  "market_end_hour": 15,
  "market_end_minute": 30,
  "enable_signal_validation": true,
  "enable_eod_execution": true
}
EOF
echo -e "${GREEN}✓ Created openalgo_config.json.example${NC}"
echo ""

# Step 6: Update .gitignore
echo -e "${YELLOW}Step 6: Updating .gitignore...${NC}"
if ! grep -q "openalgo_config.json" "$PM_DIR/.gitignore" 2>/dev/null; then
    echo "" >> "$PM_DIR/.gitignore"
    echo "# OpenAlgo configuration (contains API keys)" >> "$PM_DIR/.gitignore"
    echo "openalgo_config.json" >> "$PM_DIR/.gitignore"
    echo -e "${GREEN}✓ Updated .gitignore${NC}"
else
    echo -e "${YELLOW}ℹ .gitignore already contains openalgo_config.json${NC}"
fi
echo ""

# Step 7: Create integration test
echo -e "${YELLOW}Step 7: Creating integration test...${NC}"
cat > "$PM_DIR/tests/integration/test_openalgo_integration.py" << 'EOF'
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
        'openalgo_url': 'http://localhost:5000',
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
    config = {'openalgo_url': 'http://localhost:5000'}
    with pytest.raises(ValueError, match="API key is required"):
        create_broker_client('openalgo', config)
EOF
echo -e "${GREEN}✓ Created tests/integration/test_openalgo_integration.py${NC}"
echo ""

# Step 8: Create quick start script
echo -e "${YELLOW}Step 8: Creating quick start script...${NC}"
cat > "$PM_DIR/start_portfolio_manager.sh" << 'EOF'
#!/bin/bash

# Quick start script for Portfolio Manager with OpenAlgo

# Check if OpenAlgo config exists
if [ ! -f "openalgo_config.json" ]; then
    echo "Error: openalgo_config.json not found"
    echo "Please copy openalgo_config.json.example and configure it"
    exit 1
fi

# Extract API key from config
API_KEY=$(python3 -c "import json; print(json.load(open('openalgo_config.json'))['openalgo_api_key'])")

if [ "$API_KEY" == "YOUR_API_KEY_FROM_OPENALGO_DASHBOARD" ]; then
    echo "Error: Please configure your OpenAlgo API key in openalgo_config.json"
    exit 1
fi

# Start Portfolio Manager
python portfolio_manager.py live \
  --broker openalgo \
  --api-key "$API_KEY" \
  --capital 5000000 \
  --mode analyzer \
  "$@"
EOF
chmod +x "$PM_DIR/start_portfolio_manager.sh"
echo -e "${GREEN}✓ Created start_portfolio_manager.sh${NC}"
echo ""

# Summary
echo "========================================"
echo -e "${GREEN}✓ Integration Setup Complete!${NC}"
echo "========================================"
echo ""
echo "Files created:"
echo "  ✓ portfolio_manager/brokers/__init__.py"
echo "  ✓ portfolio_manager/brokers/openalgo_client.py"
echo "  ✓ portfolio_manager/brokers/factory.py"
echo "  ✓ portfolio_manager/openalgo_config.json.example"
echo "  ✓ portfolio_manager/tests/integration/test_openalgo_integration.py"
echo "  ✓ portfolio_manager/start_portfolio_manager.sh"
echo ""
echo "Next steps:"
echo "  1. Install OpenAlgo server (see OPENALGO_SETUP_GUIDE.md)"
echo "  2. Configure openalgo_config.json with your API key"
echo "  3. Run tests: cd portfolio_manager && pytest tests/integration/test_openalgo_integration.py"
echo "  4. Start Portfolio Manager: cd portfolio_manager && ./start_portfolio_manager.sh"
echo ""
echo "For detailed instructions, see: OPENALGO_SETUP_GUIDE.md"
echo ""


