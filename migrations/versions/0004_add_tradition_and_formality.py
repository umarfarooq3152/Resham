"""Add product_tradition and product_formality soft-ranking columns.

Revision ID: 0004_add_tradition_and_formality
Revises: 0003_add_text_derived_color
Create Date: 2026-07-17 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_add_tradition_and_formality"
down_revision: Union[str, None] = "0003_add_text_derived_color"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("product_tradition", sa.String(length=20), nullable=True))
    op.add_column("products", sa.Column("product_formality", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "product_formality")
    op.drop_column("products", "product_tradition")
