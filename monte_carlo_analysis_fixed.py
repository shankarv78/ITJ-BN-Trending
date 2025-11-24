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

def calculate_trade_statistics(trades_df: pd.DataFrame) -> Dict:
    """Calculate trade statistics from raw data"""
    # Extract P&L percentages and convert to decimal
    trade_returns = trades_df['Net P&L %'].values / 100.0

    # Calculate win/loss statistics
    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns < 0]

    win_rate = len(wins) / len(trade_returns) if len(trade_returns) > 0 else 0
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0

    # Calculate profit factor using actual P&L values
    trade_pnl = trades_df['Net P&L INR'].values
    total_wins = np.sum(trade_pnl[trade_pnl > 0])
    total_losses = abs(np.sum(trade_pnl[trade_pnl < 0]))
    profit_factor = total_wins / total_losses if total_losses > 0 else 0

    return {
        'trade_returns': trade_returns,
        'trade_pnl': trade_pnl,
        'num_trades': len(trade_returns),
        'win_rate': win_rate,
        'avg_win_pct': avg_win * 100,
        'avg_loss_pct': avg_loss * 100,
        'avg_win_inr': np.mean(trade_pnl[trade_pnl > 0]) if len(trade_pnl[trade_pnl > 0]) > 0 else 0,
        'avg_loss_inr': np.mean(trade_pnl[trade_pnl < 0]) if len(trade_pnl[trade_pnl < 0]) > 0 else 0,
        'profit_factor': profit_factor,
        'total_pnl': np.sum(trade_pnl),
        'wins': len(wins),
        'losses': len(losses)
    }

def calculate_max_drawdown(equity_curve: np.ndarray) -> Tuple[float, int, float]:
    """Calculate maximum drawdown from equity curve"""
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - running_max) / running_max
    max_dd = np.min(drawdown)
    max_dd_idx = np.argmin(drawdown)

    # Calculate drawdown duration
    dd_start = np.where(running_max[:max_dd_idx] == running_max[max_dd_idx])[0]
    dd_start = dd_start[-1] if len(dd_start) > 0 else 0

    # Find recovery point
    recovery_idx = np.where(equity_curve[max_dd_idx:] >= running_max[max_dd_idx])[0]
    recovery_idx = max_dd_idx + recovery_idx[0] if len(recovery_idx) > 0 else len(equity_curve) - 1

    dd_duration = recovery_idx - dd_start

    return abs(max_dd) * 100, max_dd_idx, dd_duration

def monte_carlo_simulation_returns(trade_returns: np.ndarray, num_simulations: int = 10000) -> Dict:
    """
    Perform Monte Carlo simulation using percentage returns
    This method compounds returns properly to avoid unrealistic drawdowns
    """
    print(f"Running {num_simulations:,} Monte Carlo simulations...")

    max_drawdowns = []
    final_returns = []
    avg_drawdowns = []

    for i in range(num_simulations):
        if i % 1000 == 0:
            print(f"  Simulation {i:,}/{num_simulations:,} completed...")

        # Randomly shuffle the order of percentage returns
        shuffled_returns = np.random.permutation(trade_returns)

        # Build equity curve by compounding returns
        # Start with 1.0 (100% of initial capital)
        equity_multiplier = np.cumprod(1 + shuffled_returns)
        equity_curve = np.insert(equity_multiplier, 0, 1.0)

        # Calculate max drawdown for this simulation
        max_dd, _, _ = calculate_max_drawdown(equity_curve)
        max_drawdowns.append(max_dd)

        # Calculate final return
        final_return = (equity_curve[-1] - 1) * 100
        final_returns.append(final_return)

        # Calculate average drawdown
        running_max = np.maximum.accumulate(equity_curve)
        drawdowns = (equity_curve - running_max) / running_max
        avg_dd = np.mean(drawdowns[drawdowns < 0]) * 100 if len(drawdowns[drawdowns < 0]) > 0 else 0
        avg_drawdowns.append(abs(avg_dd))

    # Calculate statistics
    dd_stats = {
        'mean': np.mean(max_drawdowns),
        'median': np.median(max_drawdowns),
        'std': np.std(max_drawdowns),
        'min': np.min(max_drawdowns),
        'max': np.max(max_drawdowns),
        'percentile_25': np.percentile(max_drawdowns, 25),
        'percentile_50': np.percentile(max_drawdowns, 50),
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

    avg_dd_stats = {
        'mean': np.mean(avg_drawdowns),
        'median': np.median(avg_drawdowns)
    }

    return {'drawdown_stats': dd_stats, 'return_stats': return_stats, 'avg_dd_stats': avg_dd_stats}

def calculate_kelly_criterion(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> Dict:
    """
    Calculate Kelly Criterion for optimal position sizing
    Using percentage returns for more accurate calculation
    """
    if avg_loss_pct == 0:
        return {'full_kelly': 0, 'half_kelly': 0, 'quarter_kelly': 0, 'win_loss_ratio': 0, 'edge': 0}

    p = win_rate
    q = 1 - win_rate
    b = abs(avg_win_pct / avg_loss_pct)  # Win/loss ratio

    # Kelly formula: f* = (p * b - q) / b
    kelly_fraction = (p * b - q) / b if b > 0 else 0

    # Ensure Kelly is positive and reasonable
    kelly_fraction = max(0, min(kelly_fraction, 1))  # Cap at 100%

    return {
        'full_kelly': kelly_fraction * 100,
        'half_kelly': kelly_fraction * 50,
        'quarter_kelly': kelly_fraction * 25,
        'win_loss_ratio': b,
        'edge': p * b - q
    }

def calculate_drawdown_probabilities(max_drawdowns: np.ndarray, thresholds: List[float]) -> Dict:
    """Calculate probability of exceeding specific drawdown thresholds"""
    probabilities = {}
    for threshold in thresholds:
        prob = np.mean(max_drawdowns > threshold) * 100
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
    print(f"   Total trades loaded: {len(trades_df)}")

    # Calculate trade statistics
    print("\n2. Calculating trade statistics...")
    trade_stats = calculate_trade_statistics(trades_df)

    print(f"   Total trades: {trade_stats['num_trades']}")
    print(f"   Winners: {trade_stats['wins']} ({trade_stats['win_rate']*100:.2f}%)")
    print(f"   Losers: {trade_stats['losses']} ({(1-trade_stats['win_rate'])*100:.2f}%)")
    print(f"   Average win: {trade_stats['avg_win_pct']:.2f}% (₹{trade_stats['avg_win_inr']:,.0f})")
    print(f"   Average loss: {trade_stats['avg_loss_pct']:.2f}% (₹{trade_stats['avg_loss_inr']:,.0f})")
    print(f"   Profit factor: {trade_stats['profit_factor']:.2f}")
    print(f"   Total P&L: ₹{trade_stats['total_pnl']:,.0f}")

    # Calculate actual backtest performance using percentage returns
    actual_equity_multiplier = np.cumprod(1 + trade_stats['trade_returns'])
    actual_equity_curve = np.insert(actual_equity_multiplier, 0, 1.0)
    actual_max_dd, _, dd_duration = calculate_max_drawdown(actual_equity_curve)
    actual_final_return = (actual_equity_curve[-1] - 1) * 100
    actual_cagr = (actual_equity_curve[-1] ** (1/16.9) - 1) * 100  # 16.9 years

    print(f"\n   Actual backtest performance:")
    print(f"   - Max drawdown: -{actual_max_dd:.2f}%")
    print(f"   - Final return: {actual_final_return:.1f}%")
    print(f"   - CAGR: {actual_cagr:.2f}%")

    # Run Monte Carlo simulation
    print(f"\n3. Running Monte Carlo Simulation ({num_simulations:,} iterations)...")
    mc_results = monte_carlo_simulation_returns(trade_stats['trade_returns'], num_simulations)

    # Display Monte Carlo results
    print("\n" + "=" * 80)
    print("MONTE CARLO SIMULATION RESULTS - MAXIMUM DRAWDOWN DISTRIBUTION")
    print("=" * 80)

    dd_stats = mc_results['drawdown_stats']
    return_stats = mc_results['return_stats']
    avg_dd_stats = mc_results['avg_dd_stats']

    print(f"\nDrawdown Statistics (from {num_simulations:,} simulations):")
    print(f"  Mean max drawdown:    -{dd_stats['mean']:.2f}%")
    print(f"  Median max drawdown:  -{dd_stats['median']:.2f}%")
    print(f"  Std deviation:        {dd_stats['std']:.2f}%")
    print(f"  Best case (min DD):   -{dd_stats['min']:.2f}%")
    print(f"  Worst case (max DD):  -{dd_stats['max']:.2f}%")

    print(f"\nDrawdown Percentiles:")
    print(f"  25th percentile:      -{dd_stats['percentile_25']:.2f}% (Optimistic)")
    print(f"  50th percentile:      -{dd_stats['percentile_50']:.2f}% (Median expected)")
    print(f"  75th percentile:      -{dd_stats['percentile_75']:.2f}% (Conservative estimate)")
    print(f"  90th percentile:      -{dd_stats['percentile_90']:.2f}%")
    print(f"  95th percentile:      -{dd_stats['percentile_95']:.2f}% (Worst-case with 95% confidence)")
    print(f"  99th percentile:      -{dd_stats['percentile_99']:.2f}% (Extreme tail risk)")

    print(f"\nComparison with Actual Backtest:")
    print(f"  Actual max drawdown:  -{actual_max_dd:.2f}%")
    percentile_rank = (np.sum(dd_stats['all_drawdowns'] <= actual_max_dd) / len(dd_stats['all_drawdowns'])) * 100
    print(f"  Percentile rank:      {percentile_rank:.1f}th percentile")

    if percentile_rank < 50:
        print(f"  Interpretation:       Actual DD better than median - favorable historical sequence")
    else:
        print(f"  Interpretation:       Actual DD worse than median - unfavorable historical sequence")

    # Calculate drawdown probabilities
    print("\n" + "=" * 80)
    print("DRAWDOWN PROBABILITY ANALYSIS")
    print("=" * 80)

    dd_thresholds = [25, 30, 35, 40, 45, 50]
    dd_probabilities = calculate_drawdown_probabilities(dd_stats['all_drawdowns'], dd_thresholds)

    print("\nProbability of experiencing drawdowns greater than:")
    for threshold, prob in dd_probabilities.items():
        risk_level = "LOW" if prob < 10 else "MODERATE" if prob < 30 else "HIGH" if prob < 50 else "VERY HIGH"
        print(f"  {threshold}: {prob:.1f}% ({risk_level} RISK)")

    # Kelly Criterion calculation
    print("\n" + "=" * 80)
    print("KELLY CRITERION ANALYSIS")
    print("=" * 80)

    kelly = calculate_kelly_criterion(
        trade_stats['win_rate'],
        trade_stats['avg_win_pct'],
        abs(trade_stats['avg_loss_pct'])
    )

    print(f"\nKelly Criterion Inputs:")
    print(f"  Win rate (p):         {trade_stats['win_rate']*100:.2f}%")
    print(f"  Loss rate (q):        {(1-trade_stats['win_rate'])*100:.2f}%")
    print(f"  Avg win:              {trade_stats['avg_win_pct']:.2f}%")
    print(f"  Avg loss:             {trade_stats['avg_loss_pct']:.2f}%")
    print(f"  Win/Loss ratio (b):   {kelly['win_loss_ratio']:.2f}")
    print(f"  Edge:                 {kelly['edge']:.3f}")

    print(f"\nOptimal Position Sizing:")
    print(f"  Full Kelly:           {kelly['full_kelly']:.1f}% of capital (Theoretical optimal)")
    print(f"  Half Kelly:           {kelly['half_kelly']:.1f}% of capital (Conservative)")
    print(f"  Quarter Kelly:        {kelly['quarter_kelly']:.1f}% of capital (Very conservative)")

    # Risk-based position sizing
    print("\n" + "=" * 80)
    print("RISK-BASED POSITION SIZING")
    print("=" * 80)

    portfolio_dd_targets = [10, 15, 20, 25, 30]

    print("\nTo limit portfolio drawdown to specific levels, maximum allocation should be:")
    for target_dd in portfolio_dd_targets:
        # Use different percentiles for different risk tolerance
        if target_dd <= 15:
            strategy_dd = dd_stats['percentile_99']  # Very conservative
            percentile_used = "99th"
        elif target_dd <= 20:
            strategy_dd = dd_stats['percentile_95']  # Conservative
            percentile_used = "95th"
        elif target_dd <= 25:
            strategy_dd = dd_stats['percentile_90']  # Moderate
            percentile_used = "90th"
        else:
            strategy_dd = dd_stats['percentile_75']  # Aggressive
            percentile_used = "75th"

        safe_allocation = (target_dd / strategy_dd) * 100
        print(f"  {target_dd}% portfolio DD → Allocate ≤{safe_allocation:.1f}% (based on {percentile_used} percentile)")

    # Final recommendations
    print("\n" + "=" * 80)
    print("RISK ASSESSMENT & RECOMMENDATIONS")
    print("=" * 80)

    # Determine recommended allocation
    conservative_dd_target = 20
    conservative_strategy_dd = dd_stats['percentile_95']
    conservative_allocation = (conservative_dd_target / conservative_strategy_dd) * 100

    recommended_allocation = min(kelly['half_kelly'], conservative_allocation)

    print("\n1. STRATEGY RISK PROFILE:")
    print(f"   ✓ Expected drawdown range: -{dd_stats['percentile_25']:.1f}% to -{dd_stats['percentile_75']:.1f}%")
    print(f"   ✓ Worst-case (95% conf):   -{dd_stats['percentile_95']:.1f}%")
    print(f"   ✓ Risk-Reward Ratio:        {actual_cagr/actual_max_dd:.2f} (CAGR/MaxDD)")

    print("\n2. POSITION SIZING RECOMMENDATIONS:")
    print(f"   • Kelly-based optimal:      {kelly['half_kelly']:.1f}% (Half Kelly)")
    print(f"   • Risk-based maximum:       {conservative_allocation:.1f}% (for 20% portfolio DD)")
    print(f"   • RECOMMENDED ALLOCATION:   {recommended_allocation:.1f}%")

    print("\n3. RISK WARNINGS:")
    warnings = []
    if dd_stats['percentile_99'] > 50:
        warnings.append("⚠️  EXTREME TAIL RISK: 1% chance of >50% strategy drawdown")
    if dd_stats['percentile_95'] > 40:
        warnings.append("⚠️  HIGH VOLATILITY: 5% chance of >40% strategy drawdown")
    if dd_stats['percentile_90'] > 35:
        warnings.append("⚠️  SIGNIFICANT RISK: 10% chance of >35% strategy drawdown")
    if kelly['full_kelly'] < 10:
        warnings.append("⚠️  MODEST EDGE: Kelly suggests limited allocation")
    if trade_stats['num_trades'] / 16.9 < 30:
        warnings.append("⚠️  LOW TRADE FREQUENCY: <30 trades/year may indicate overfitting")

    if warnings:
        for warning in warnings:
            print(f"   {warning}")
    else:
        print("   ✓ No major risk warnings")

    print("\n4. KEY INSIGHTS:")
    insights = []

    if percentile_rank < 25:
        insights.append("✓ Historical backtest showed exceptionally good drawdown (bottom quartile)")
    elif percentile_rank < 50:
        insights.append("✓ Historical backtest showed better than median drawdown")
    else:
        insights.append("⚠️  Historical backtest showed worse than median drawdown")

    if trade_stats['profit_factor'] > 2:
        insights.append("✓ Strong profit factor (>2.0) indicates robust edge")
    elif trade_stats['profit_factor'] > 1.5:
        insights.append("✓ Good profit factor (>1.5) suggests consistent profitability")

    if actual_cagr > 20:
        insights.append(f"✓ Exceptional CAGR of {actual_cagr:.1f}% over 16.9 years")
    elif actual_cagr > 15:
        insights.append(f"✓ Strong CAGR of {actual_cagr:.1f}% over 16.9 years")

    for insight in insights:
        print(f"   {insight}")

    # Executive Summary
    print("\n" + "=" * 80)
    print("EXECUTIVE SUMMARY")
    print("=" * 80)

    print(f"""
Based on {num_simulations:,} Monte Carlo simulations of {trade_stats['num_trades']} trades over 16.9 years:

PERFORMANCE METRICS:
• Actual CAGR:                {actual_cagr:.1f}%
• Actual Max Drawdown:        -{actual_max_dd:.1f}% ({percentile_rank:.0f}th percentile)
• Win Rate:                   {trade_stats['win_rate']*100:.1f}%
• Profit Factor:              {trade_stats['profit_factor']:.2f}
• Risk-Reward Ratio:          {actual_cagr/actual_max_dd:.2f}

MONTE CARLO INSIGHTS:
• Median Expected DD:         -{dd_stats['percentile_50']:.1f}%
• Conservative DD (95%):      -{dd_stats['percentile_95']:.1f}%
• Extreme Tail Risk (99%):    -{dd_stats['percentile_99']:.1f}%

OPTIMAL ALLOCATION:
• Kelly Criterion:            {kelly['half_kelly']:.1f}% (Half Kelly)
• Risk-Based (20% DD limit):  {conservative_allocation:.1f}%
• FINAL RECOMMENDATION:       {recommended_allocation:.1f}% of portfolio

VERDICT:
""")

    if recommended_allocation >= 20:
        verdict = "HIGHLY ATTRACTIVE - Strong edge with manageable risk. Substantial allocation warranted."
    elif recommended_allocation >= 10:
        verdict = "ATTRACTIVE - Good risk-adjusted returns. Moderate allocation recommended."
    elif recommended_allocation >= 5:
        verdict = "ACCEPTABLE - Modest edge with notable risks. Conservative allocation advised."
    else:
        verdict = "MARGINAL - Limited edge or high risk. Minimal allocation if any."

    print(f"{verdict}")
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()