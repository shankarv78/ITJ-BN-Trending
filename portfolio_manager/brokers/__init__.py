"""
Broker integration module for Portfolio Manager

Provides abstraction layer for different broker implementations:
- OpenAlgo: Production broker integration
- MockBrokerSimulator: Testing and development
"""

from brokers.factory import create_broker_client

__all__ = ['create_broker_client']
