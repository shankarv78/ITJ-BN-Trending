#!/usr/bin/env python3
"""
Bank Nifty Trend Following v6 - Monte Carlo Simulation & Kelly Criterion Analysis
Analyzes backtest results to determine worst-case drawdowns and optimal position sizing
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

def load_trade_data(file_path: str) -> pd.DataFrame:
    """Load and clean trade data from CSV"""
    df = pd.read_csv(file_path, encoding='utf-8-sig')
    # Filter for exit trades only (which contain the P&L)
    exit_trades = df[df['Type'] == 'Exit long'].copy()
    return exit_trades

def calculate_trade_returns(trades_df: pd.DataFrame, initial_capital: float = 5000000) -> Dict:
    """Calculate individual trade returns and statistics"""
    # Extract net P&L for each trade
    trade_pnl = trades_df['Net P&L INR'].values

    # Calculate returns
    wins = trade_pnl[trade_pnl > 0]
    losses = trade_pnl[trade_pnl < 0]

    win_rate = len(wins) / len(trade_pnl) if len(trade_pnl) > 0 else 0
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0

    # Calculate profit factor
    total_wins = np.sum(wins) if len(wins) > 0 else 0
    total_losses = abs(np.sum(losses)) if len(losses) > 0 else 1
    profit_factor = total_wins / total_losses if total_losses > 0 else 0

    return {
        'trade_pnl': trade_pnl,
        'num_trades': len(trade_pnl),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'total_pnl': np.sum(trade_pnl),
        'wins': len(wins),
        'losses': len(losses)
    }

def calculate_max_drawdown(equity_curve: np.ndarray) -> Tuple[float, int]:
    """Calculate maximum drawdown from equity curve"""
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - running_max) / running_max
    max_dd = np.min(drawdown)
    max_dd_idx = np.argmin(drawdown)
    return abs(max_dd), max_dd_idx  # Return absolute value for consistency

def monte_carlo_simulation(trade_pnl: np.ndarray, initial_capital: float, num_simulations: int = 10000) -> Dict:
    """
    Perform Monte Carlo simulation by randomly reordering trades
    """
    print(f"Running {num_simulations:,} Monte Carlo simulations...")

    max_drawdowns = []
    final_returns = []

    for i in range(num_simulations):
        if i % 1000 == 0:
            print(f"  Simulation {i:,}/{num_simulations:,} completed...")

        # Randomly shuffle the order of trades
        shuffled_trades = np.random.permutation(trade_pnl)

        # Build equity curve
        equity_curve = initial_capital + np.cumsum(shuffled_trades)
        equity_curve = np.insert(equity_curve, 0, initial_capital)

        # Calculate max drawdown for this simulation
        max_dd, _ = calculate_max_drawdown(equity_curve)
        max_drawdowns.append(max_dd * 100)  # Convert to percentage

        # Calculate final return
        final_equity = equity_curve[-1]
        total_return = ((final_equity - initial_capital) / initial_capital) * 100
        final_returns.append(total_return)

    # Calculate statistics
    dd_stats = {
        'mean': np.mean(max_drawdowns),
        'median': np.median(max_drawdowns),
        'std': np.std(max_drawdowns),
        'min': np.min(max_drawdowns),  # Best case (smallest drawdown)
        'max': np.max(max_drawdowns),  # Worst case (largest drawdown)
        'percentile_75': np.percentile(max_drawdowns, 75),
        'percentile_90': np.percentile(max_drawdowns, 90),
        'percentile_95': np.percentile(max_drawdowns, 95),
        'percentile_99': np.percentile(max_drawdowns, 99),
        'all_drawdowns': np.array(max_drawdowns)
    }

    return_stats = {
        'mean': np.mean(final_returns),
        'median': np.median(final_returns),
        'std': np.std(final_returns),
        'min': np.min(final_returns),
        'max': np.max(final_returns)
    }

    return {'drawdown_stats': dd_stats, 'return_stats': return_stats}

def calculate_kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> Dict:
    """
    Calculate Kelly Criterion for optimal position sizing
    Kelly % = (p * b - q) / b
    where:
    p = probability of win (win rate)
    q = probability of loss (1 - win rate)
    b = ratio of win to loss (avg_win / abs(avg_loss))
    """
    if avg_loss == 0:
        return {'full_kelly': 0, 'half_kelly': 0, 'quarter_kelly': 0}

    p = win_rate
    q = 1 - win_rate
    b = abs(avg_win / avg_loss)  # Win/loss ratio

    # Full Kelly
    kelly_pct = (p * b - q) / b if b > 0 else 0

    # Conservative Kelly variations
    half_kelly = kelly_pct * 0.5
    quarter_kelly = kelly_pct * 0.25

    return {
        'full_kelly': kelly_pct * 100,  # Convert to percentage
        'half_kelly': half_kelly * 100,
        'quarter_kelly': quarter_kelly * 100,
        'win_loss_ratio': b,
        'edge': p * b - q  # Expected value per unit risked
    }

def calculate_drawdown_probabilities(max_drawdowns: List[float], thresholds: List[float]) -> Dict:
    """Calculate probability of exceeding specific drawdown thresholds"""
    probabilities = {}
    for threshold in thresholds:
        prob = np.mean([1 if dd > threshold else 0 for dd in max_drawdowns]) * 100
        probabilities[f'>{threshold}%'] = prob
    return probabilities

def main():
    """Main analysis function"""
    print("=" * 80)
    print("BANK NIFTY TREND FOLLOWING v6 - MONTE CARLO & KELLY ANALYSIS")
    print("=" * 80)

    # Configuration
    file_path = "/Users/shankarvasudevan/claude-code/ITJ-BN-Trending/ITJ_BN_TrendFollowing v6.csv"
    initial_capital = 5000000  # 50 Lakhs
    num_simulations = 10000

    # Load trade data
    print("\n1. Loading trade data...")
    trades_df = load_trade_data(file_path)
    print(f"   Total exit trades loaded: {len(trades_df)}")

    # Calculate trade statistics
    print("\n2. Calculating trade statistics...")
    trade_stats = calculate_trade_returns(trades_df, initial_capital)

    print(f"   Total trades: {trade_stats['num_trades']}")
    print(f"   Winners: {trade_stats['wins']} ({trade_stats['win_rate']*100:.2f}%)")
    print(f"   Losers: {trade_stats['losses']} ({(1-trade_stats['win_rate'])*100:.2f}%)")
    print(f"   Average win: ₹{trade_stats['avg_win']:,.2f}")
    print(f"   Average loss: ₹{trade_stats['avg_loss']:,.2f}")
    print(f"   Profit factor: {trade_stats['profit_factor']:.2f}")
    print(f"   Total P&L: ₹{trade_stats['total_pnl']:,.2f}")

    # Calculate actual backtest performance
    actual_equity_curve = initial_capital + np.cumsum(trade_stats['trade_pnl'])
    actual_equity_curve = np.insert(actual_equity_curve, 0, initial_capital)
    actual_max_dd, _ = calculate_max_drawdown(actual_equity_curve)
    actual_final_return = ((actual_equity_curve[-1] - initial_capital) / initial_capital) * 100

    print(f"\n   Actual backtest max drawdown: -{actual_max_dd*100:.2f}%")
    print(f"   Actual final return: {actual_final_return:.2f}%")

    # Run Monte Carlo simulation
    print(f"\n3. Running Monte Carlo Simulation ({num_simulations:,} iterations)...")
    mc_results = monte_carlo_simulation(trade_stats['trade_pnl'], initial_capital, num_simulations)

    # Display Monte Carlo results
    print("\n" + "=" * 80)
    print("MONTE CARLO SIMULATION RESULTS - MAXIMUM DRAWDOWN DISTRIBUTION")
    print("=" * 80)

    dd_stats = mc_results['drawdown_stats']
    print(f"\nDrawdown Statistics (from {num_simulations:,} simulations):")
    print(f"  Mean drawdown:        -{dd_stats['mean']:.2f}%")
    print(f"  Median drawdown:      -{dd_stats['median']:.2f}%")
    print(f"  Std deviation:        {dd_stats['std']:.2f}%")
    print(f"  Best case (min):      -{dd_stats['min']:.2f}%")
    print(f"  Worst case (max):     -{dd_stats['max']:.2f}%")

    print(f"\nDrawdown Percentiles:")
    print(f"  75th percentile:      -{dd_stats['percentile_75']:.2f}% (Conservative estimate)")
    print(f"  90th percentile:      -{dd_stats['percentile_90']:.2f}%")
    print(f"  95th percentile:      -{dd_stats['percentile_95']:.2f}% (Worst-case with 95% confidence)")
    print(f"  99th percentile:      -{dd_stats['percentile_99']:.2f}% (Extreme worst-case)")

    print(f"\nComparison with Actual Backtest:")
    print(f"  Actual max drawdown:  -{actual_max_dd*100:.2f}%")
    # Find percentile rank of actual DD
    percentile_rank = (np.sum(dd_stats['all_drawdowns'] <= actual_max_dd*100) / len(dd_stats['all_drawdowns'])) * 100
    print(f"  Percentile rank:      {percentile_rank:.1f}th percentile")

    # Calculate drawdown probabilities
    print("\n" + "=" * 80)
    print("DRAWDOWN PROBABILITY ANALYSIS")
    print("=" * 80)

    dd_thresholds = [30, 35, 40, 45, 50]
    dd_probabilities = calculate_drawdown_probabilities(dd_stats['all_drawdowns'], dd_thresholds)

    print("\nProbability of experiencing drawdowns greater than:")
    for threshold, prob in dd_probabilities.items():
        print(f"  {threshold}: {prob:.2f}%")

    # Kelly Criterion calculation
    print("\n" + "=" * 80)
    print("KELLY CRITERION ANALYSIS")
    print("=" * 80)

    kelly = calculate_kelly_criterion(
        trade_stats['win_rate'],
        trade_stats['avg_win'],
        trade_stats['avg_loss']
    )

    print(f"\nKelly Criterion Calculation:")
    print(f"  Win rate (p):         {trade_stats['win_rate']*100:.2f}%")
    print(f"  Loss rate (q):        {(1-trade_stats['win_rate'])*100:.2f}%")
    print(f"  Win/Loss ratio (b):   {kelly['win_loss_ratio']:.2f}")
    print(f"  Edge:                 {kelly['edge']:.3f}")

    print(f"\nOptimal Position Sizing:")
    print(f"  Full Kelly:           {kelly['full_kelly']:.2f}% of capital (Theoretical optimal)")
    print(f"  Half Kelly:           {kelly['half_kelly']:.2f}% of capital (Conservative)")
    print(f"  Quarter Kelly:        {kelly['quarter_kelly']:.2f}% of capital (Very conservative)")

    # Final recommendations
    print("\n" + "=" * 80)
    print("RISK ASSESSMENT & RECOMMENDATIONS")
    print("=" * 80)

    print("\n1. WORST-CASE DRAWDOWN ASSESSMENT:")
    print(f"   - With 95% confidence, max drawdown will not exceed: -{dd_stats['percentile_95']:.2f}%")
    print(f"   - Conservative planning should assume: -{dd_stats['percentile_75']:.2f}% drawdown")
    print(f"   - Extreme tail risk (99th percentile): -{dd_stats['percentile_99']:.2f}%")

    print("\n2. POSITION SIZING RECOMMENDATIONS:")
    print(f"   - Aggressive (Full Kelly): {kelly['full_kelly']:.1f}% allocation")
    print(f"   - Recommended (Half Kelly): {kelly['half_kelly']:.1f}% allocation")
    print(f"   - Conservative (Quarter Kelly): {kelly['quarter_kelly']:.1f}% allocation")

    # Calculate safe capital allocation based on worst-case DD
    target_max_portfolio_dd = 20  # Target max portfolio DD of 20%
    worst_case_strategy_dd = dd_stats['percentile_95']
    safe_allocation = (target_max_portfolio_dd / worst_case_strategy_dd) * 100

    print(f"\n3. SAFE CAPITAL ALLOCATION:")
    print(f"   - To limit portfolio drawdown to {target_max_portfolio_dd}%:")
    print(f"     Allocate maximum {safe_allocation:.1f}% to this strategy")
    print(f"   - Based on 95th percentile worst-case DD of {worst_case_strategy_dd:.1f}%")

    print("\n4. RISK WARNINGS:")
    if dd_stats['percentile_99'] > 50:
        print("   ⚠️  EXTREME RISK: 1% chance of >50% drawdown")
    if dd_stats['percentile_95'] > 40:
        print("   ⚠️  HIGH RISK: 5% chance of >40% drawdown")
    if kelly['full_kelly'] > 100:
        print("   ⚠️  Kelly suggests >100% allocation - strategy edge may be overestimated")
    if kelly['full_kelly'] < 10:
        print("   ⚠️  Low Kelly percentage suggests modest edge - use conservative sizing")

    print("\n5. KEY INSIGHTS:")
    if actual_max_dd * 100 < dd_stats['median']:
        print("   ✓ Actual backtest DD better than median - potentially lucky sequence")
    else:
        print("   ✓ Actual backtest DD worse than median - conservative historical path")

    risk_reward_ratio = abs(actual_final_return / (actual_max_dd * 100))
    print(f"   ✓ Risk-Reward Ratio: {risk_reward_ratio:.2f} (Return/DD ratio)")

    print("\n" + "=" * 80)
    print("EXECUTIVE SUMMARY")
    print("=" * 80)

    print(f"""
Based on {num_simulations:,} Monte Carlo simulations of {trade_stats['num_trades']} trades:

WORST-CASE SCENARIOS:
• Expected worst-case DD (95% confidence): -{dd_stats['percentile_95']:.1f}%
• Extreme worst-case DD (99% confidence): -{dd_stats['percentile_99']:.1f}%
• Actual backtest DD of -{actual_max_dd*100:.1f}% ranks at {percentile_rank:.0f}th percentile

OPTIMAL POSITION SIZING:
• Kelly Criterion suggests: {kelly['half_kelly']:.1f}% allocation (Half Kelly)
• For max 20% portfolio DD: Allocate ≤{safe_allocation:.0f}% of capital
• Win rate: {trade_stats['win_rate']*100:.1f}%, Win/Loss ratio: {kelly['win_loss_ratio']:.2f}

FINAL RECOMMENDATION:
Allocate {min(kelly['half_kelly'], safe_allocation):.0f}% of portfolio capital to this strategy
for optimal risk-adjusted returns with acceptable drawdown risk.
    """)

if __name__ == "__main__":
    main()