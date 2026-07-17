"""Add text-derived color fallback column to products.

Revision ID: 0003_add_text_derived_color
Revises: 0002_add_vision_classification
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_text_derived_color"
down_revision: Union[str, None] = "0002_add_vision_classification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("text_derived_color", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "text_derived_color")
