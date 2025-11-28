#!/usr/bin/env python3
"""
Setup Verification Script

Validates that the portfolio manager is correctly installed and configured
"""
import sys
import importlib
from pathlib import Path

def check_module(module_name):
    """Check if module can be imported"""
    try:
        importlib.import_module(module_name)
        return True, "✓"
    except ImportError as e:
        return False, f"✗ {e}"

def main():
    print("=" * 60)
    print("Tom Basso Portfolio Manager - Setup Verification")
    print("=" * 60)
    print()
    
    # Check Python version
    print("[1] Python Version")
    print(f"    Version: {sys.version}")
    if sys.version_info < (3, 8):
        print("    ✗ Python 3.8+ required")
        return 1
    print("    ✓ Compatible")
    print()
    
    # Check core modules
    print("[2] Core Modules")
    modules = [
        'core.models',
        'core.config',
        'core.position_sizer',
        'core.portfolio_state',
        'core.pyramid_gate',
        'core.stop_manager'
    ]
    
    all_ok = True
    for module in modules:
        ok, msg = check_module(module)
        print(f"    {msg} {module}")
        if not ok:
            all_ok = False
    print()
    
    # Check dependencies
    print("[3] Dependencies")
    deps = ['pandas', 'numpy', 'pytest', 'flask', 'requests']
    for dep in deps:
        ok, msg = check_module(dep)
        print(f"    {msg} {dep}")
        if not ok:
            all_ok = False
    print()
    
    # Check test files
    print("[4] Test Files")
    test_files = [
        'tests/unit/test_position_sizer.py',
        'tests/unit/test_portfolio_state.py',
        'tests/unit/test_stop_manager.py',
        'tests/integration/test_backtest_engine.py',
        'tests/test_end_to_end.py'
    ]
    
    for test_file in test_files:
        if Path(test_file).exists():
            print(f"    ✓ {test_file}")
        else:
            print(f"    ✗ {test_file} (missing)")
            all_ok = False
    print()
    
    # Try to import main components
    print("[5] Component Validation")
    try:
        from core.position_sizer import TomBassoPositionSizer
        from core.portfolio_state import PortfolioStateManager
        from core.stop_manager import TomBassoStopManager
        from backtest.engine import PortfolioBacktestEngine
        
        print("    ✓ Position Sizer")
        print("    ✓ Portfolio State Manager")
        print("    ✓ Stop Manager")
        print("    ✓ Backtest Engine")
    except Exception as e:
        print(f"    ✗ Import error: {e}")
        all_ok = False
    print()
    
    # Summary
    print("=" * 60)
    if all_ok:
        print("✓ ALL CHECKS PASSED")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run tests: ./run_tests.sh")
        print("  2. View coverage: open htmlcov/index.html")
        print("  3. Run backtest: python portfolio_manager.py backtest --help")
        print()
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print("=" * 60)
        print()
        print("Fix issues above, then run this script again.")
        print()
        return 1

if __name__ == '__main__':
    sys.exit(main())

