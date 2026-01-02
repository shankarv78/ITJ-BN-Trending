"""Add excluded_margin columns to daily_session

Revision ID: 002_excluded_margin
Revises: 001_auto_hedge
Create Date: 2026-01-02

Adds columns to track margin that should be excluded from intraday calculations:
- excluded_margin: Total margin from PM trend-following + long-term positions
- excluded_margin_breakdown: JSON with breakdown by instrument
- excluded_margin_updated_at: When the excluded margin was last calculated
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_excluded_margin'
down_revision: Union[str, None] = '001_auto_hedge'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add excluded_margin columns to daily_session table."""

    # Add excluded_margin column
    op.add_column(
        'daily_session',
        sa.Column('excluded_margin', sa.Numeric(14, 2), nullable=True, default=0),
        schema='auto_hedge'
    )

    # Add excluded_margin_breakdown column (JSON as TEXT)
    op.add_column(
        'daily_session',
        sa.Column('excluded_margin_breakdown', sa.Text(), nullable=True),
        schema='auto_hedge'
    )

    # Add excluded_margin_updated_at column
    op.add_column(
        'daily_session',
        sa.Column('excluded_margin_updated_at', sa.DateTime(timezone=True), nullable=True),
        schema='auto_hedge'
    )


def downgrade() -> None:
    """Remove excluded_margin columns from daily_session table."""

    op.drop_column('daily_session', 'excluded_margin_updated_at', schema='auto_hedge')
    op.drop_column('daily_session', 'excluded_margin_breakdown', schema='auto_hedge')
    op.drop_column('daily_session', 'excluded_margin', schema='auto_hedge')
