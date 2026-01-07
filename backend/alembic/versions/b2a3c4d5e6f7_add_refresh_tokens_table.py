"""add_refresh_tokens_table

Revision ID: b2a3c4d5e6f7
Revises: fa1496962933
Create Date: 2026-01-01 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2a3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'fa1496962933'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema:
    1. Create refresh_tokens table
    2. Drop refresh_tokens JSON column from users table
    """
    # Create the new refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('device_info', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for performance
    op.create_index('ix_refresh_tokens_id', 'refresh_tokens', ['id'], unique=False)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=True)
    
    # Drop the old JSON column from users table
    op.drop_column('users', 'refresh_tokens')


def downgrade() -> None:
    """
    Downgrade schema:
    1. Re-add refresh_tokens JSON column to users table
    2. Drop refresh_tokens table
    """
    # Re-add the JSON column
    op.add_column('users', sa.Column('refresh_tokens', sa.JSON(), nullable=True))
    
    # Drop indexes
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_id', table_name='refresh_tokens')
    
    # Drop the table
    op.drop_table('refresh_tokens')
