"""add device_location table for location tracking

Revision ID: d6f0e1a2b3c4
Revises: c1a2b3c4d5e6
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6f0e1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('device_location',
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('altitude_m', sa.Float(), nullable=True),
    sa.Column('accuracy_m', sa.Float(), nullable=True),
    sa.Column('source', sa.String(), nullable=True),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_location_device_captured', 'device_location', ['device_id', 'captured_at'], unique=False)
    op.create_index(op.f('ix_device_location_device_id'), 'device_location', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_location_captured_at'), 'device_location', ['captured_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_device_location_captured_at'), table_name='device_location')
    op.drop_index(op.f('ix_device_location_device_id'), table_name='device_location')
    op.drop_index('ix_device_location_device_captured', table_name='device_location')
    op.drop_table('device_location')
