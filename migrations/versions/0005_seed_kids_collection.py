"""Seed the "Kids Corner" curated collection.

5,761 in-stock kids/toddler products exist in the catalog (2,210 from
Outfitters alone) and the chat/session search already surfaces them
correctly when a shopper explicitly asks ("kids clothes", "for my son") —
but there was no discoverable entry point in the UI at all: onboarding only
offers Menswear/Womenswear, and none of the 5 existing curated collections
touch wants_kids. services/collections.py's build_collection_filters
already reads filter_definition["wants_kids"] straight into
EligibilityFilters — this needed no code change, only the missing row.

Revision ID: 0005_seed_kids_collection
Revises: 0004_add_tradition_and_formality
Create Date: 2026-07-20 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0005_seed_kids_collection"
down_revision: Union[str, None] = "0004_add_tradition_and_formality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TITLE = "Kids Corner"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            """
            INSERT INTO collections
                (id, title, subtitle, description, filter_definition, is_active, sort_order, created_at)
            VALUES
                (gen_random_uuid(), :title, :subtitle, :description, CAST(:filter_definition AS json), true, :sort_order, now())
            """
        ),
        {
            "title": _TITLE,
            "subtitle": "For your little ones",
            "description": "Everyday and festive styles for kids and toddlers, from newborn to pre-teen",
            "filter_definition": '{"wants_kids": true}',
            "sort_order": 6,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(text("DELETE FROM collections WHERE title = :title"), {"title": _TITLE})
