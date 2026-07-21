"""Move "Kids Corner" to the front of the curated collections list.

0005 appended it at sort_order=6 (last) without actually thinking about
placement — the whole point of adding it was to fix a real discoverability
gap (5,761 real kids products with no UI entry point), so burying it last
undercut its own purpose. Sort_order=0 puts it first without needing to
renumber the other 5.

Revision ID: 0006_promote_kids_corner
Revises: 0005_seed_kids_collection
Create Date: 2026-07-20 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0006_promote_kids_corner"
down_revision: Union[str, None] = "0005_seed_kids_collection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TITLE = "Kids Corner"


def upgrade() -> None:
    op.get_bind().execute(
        text("UPDATE collections SET sort_order = 0 WHERE title = :title"), {"title": _TITLE}
    )


def downgrade() -> None:
    op.get_bind().execute(
        text("UPDATE collections SET sort_order = 6 WHERE title = :title"), {"title": _TITLE}
    )
