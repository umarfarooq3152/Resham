"""Add image-derived classification columns to products.

Revision ID: 0002_add_vision_classification
Revises: 0001_initial_schema
Create Date: 2026-07-16 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_vision_classification"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("vision_category", sa.String(length=255), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "vision_colors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "products", sa.Column("vision_classified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_products_vision_classified_at"), "products", ["vision_classified_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_products_vision_classified_at"), table_name="products")
    op.drop_column("products", "vision_classified_at")
    op.drop_column("products", "vision_colors")
    op.drop_column("products", "vision_category")
