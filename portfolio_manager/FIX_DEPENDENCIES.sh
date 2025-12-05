#!/bin/bash
# Fix missing dependencies in virtual environment

echo "Installing missing dependencies in virtual environment..."
echo ""

# Install all requirements
python -m pip install --upgrade pip
python -m pip install python-dateutil psycopg2-binary redis Flask requests pandas numpy pytest pytest-cov

echo ""
echo "Verifying installation..."
python -c "
import dateutil
import psycopg2
import redis
import flask
print('✅ All dependencies installed successfully!')
"

echo ""
echo "Testing application import..."
python -c "from core.models import Signal; print('✅ Application modules load successfully!')"

