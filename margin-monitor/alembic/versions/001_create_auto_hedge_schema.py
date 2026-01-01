"""Create auto_hedge schema and tables

Revision ID: 001_auto_hedge
Revises:
Create Date: 2026-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_auto_hedge'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create auto_hedge schema and all tables."""

    # Create schema
    op.execute("CREATE SCHEMA IF NOT EXISTS auto_hedge")

    # ================================================================
    # Table: strategy_schedule
    # ================================================================
    op.create_table(
        'strategy_schedule',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('day_of_week', sa.String(10), nullable=False),
        sa.Column('index_name', sa.String(10), nullable=False),
        sa.Column('expiry_type', sa.String(10), nullable=False),
        sa.Column('portfolio_name', sa.String(50), nullable=False),
        sa.Column('entry_time', sa.Time(), nullable=False),
        sa.Column('exit_time', sa.Time(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        schema='auto_hedge'
    )
    op.create_index('idx_strategy_schedule_day', 'strategy_schedule', ['day_of_week'], schema='auto_hedge')
    op.create_index('idx_strategy_schedule_active', 'strategy_schedule', ['is_active'], schema='auto_hedge')

    # ================================================================
    # Table: daily_session
    # ================================================================
    op.create_table(
        'daily_session',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_date', sa.Date(), nullable=False, unique=True),
        sa.Column('day_of_week', sa.String(10), nullable=False),
        sa.Column('index_name', sa.String(10), nullable=False),
        sa.Column('expiry_type', sa.String(10), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('num_baskets', sa.Integer(), nullable=False),
        sa.Column('budget_per_basket', sa.Numeric(12, 2), default=1000000.00),
        sa.Column('total_budget', sa.Numeric(14, 2), nullable=False),
        sa.Column('baseline_margin', sa.Numeric(14, 2), nullable=True),
        sa.Column('baseline_captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_hedge_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        schema='auto_hedge'
    )
    op.create_index('idx_daily_session_date', 'daily_session', ['session_date'], schema='auto_hedge')

    # ================================================================
    # Table: hedge_transactions
    # ================================================================
    op.create_table(
        'hedge_transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('auto_hedge.daily_session.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('trigger_reason', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False),
        sa.Column('strike', sa.Integer(), nullable=False),
        sa.Column('option_type', sa.String(2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('lots', sa.Integer(), nullable=False),
        sa.Column('order_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('executed_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('total_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('utilization_before', sa.Numeric(5, 2), nullable=False),
        sa.Column('utilization_after', sa.Numeric(5, 2), nullable=True),
        sa.Column('margin_impact', sa.Numeric(14, 2), nullable=True),
        sa.Column('order_id', sa.String(50), nullable=True),
        sa.Column('order_status', sa.String(20), nullable=False, default='PENDING'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('telegram_sent', sa.Boolean(), default=False),
        sa.Column('telegram_message_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        schema='auto_hedge'
    )
    op.create_index('idx_hedge_transactions_session', 'hedge_transactions', ['session_id'], schema='auto_hedge')
    op.create_index('idx_hedge_transactions_timestamp', 'hedge_transactions', ['timestamp'], schema='auto_hedge')
    op.create_index('idx_hedge_transactions_status', 'hedge_transactions', ['order_status'], schema='auto_hedge')

    # ================================================================
    # Table: strategy_executions
    # ================================================================
    op.create_table(
        'strategy_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('auto_hedge.daily_session.id'), nullable=False),
        sa.Column('portfolio_name', sa.String(50), nullable=False),
        sa.Column('scheduled_entry_time', sa.Time(), nullable=False),
        sa.Column('utilization_before', sa.Numeric(5, 2), nullable=True),
        sa.Column('projected_utilization', sa.Numeric(5, 2), nullable=True),
        sa.Column('hedge_required', sa.Boolean(), default=False),
        sa.Column('hedge_transaction_id', sa.Integer(), sa.ForeignKey('auto_hedge.hedge_transactions.id'), nullable=True),
        sa.Column('actual_entry_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('utilization_after', sa.Numeric(5, 2), nullable=True),
        sa.Column('entry_successful', sa.Boolean(), nullable=True),
        sa.Column('scheduled_exit_time', sa.Time(), nullable=True),
        sa.Column('actual_exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_reason', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        schema='auto_hedge'
    )
    op.create_index('idx_strategy_executions_session', 'strategy_executions', ['session_id'], schema='auto_hedge')
    op.create_index('idx_strategy_executions_portfolio', 'strategy_executions', ['portfolio_name'], schema='auto_hedge')

    # ================================================================
    # Table: active_hedges
    # ================================================================
    op.create_table(
        'active_hedges',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('auto_hedge.daily_session.id'), nullable=False),
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('auto_hedge.hedge_transactions.id'), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('exchange', sa.String(10), nullable=False),
        sa.Column('strike', sa.Integer(), nullable=False),
        sa.Column('option_type', sa.String(2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('entry_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('current_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('exit_transaction_id', sa.Integer(), sa.ForeignKey('auto_hedge.hedge_transactions.id'), nullable=True),
        sa.Column('otm_distance', sa.Integer(), nullable=True),
        sa.Column('margin_benefit', sa.Numeric(14, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        schema='auto_hedge'
    )
    op.create_index('idx_active_hedges_session', 'active_hedges', ['session_id', 'is_active'], schema='auto_hedge')
    op.create_index('idx_active_hedges_symbol', 'active_hedges', ['symbol'], schema='auto_hedge')
    # Composite index for efficient ORDER BY otm_distance queries
    op.create_index(
        'idx_active_hedges_session_active_otm',
        'active_hedges',
        ['session_id', 'is_active', sa.desc('otm_distance')],
        schema='auto_hedge'
    )


def downgrade() -> None:
    """Drop all auto_hedge tables and schema."""
    op.drop_table('active_hedges', schema='auto_hedge')
    op.drop_table('strategy_executions', schema='auto_hedge')
    op.drop_table('hedge_transactions', schema='auto_hedge')
    op.drop_table('daily_session', schema='auto_hedge')
    op.drop_table('strategy_schedule', schema='auto_hedge')
    op.execute("DROP SCHEMA IF EXISTS auto_hedge CASCADE")
