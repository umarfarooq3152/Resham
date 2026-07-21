"""Set a representative image for each curated collection.

All 6 collections had image_url = '' (the blank/gray placeholders the user
flagged). Each one now points to a real, currently in-stock product's own
CDN image, picked to match that collection's filter_definition (e.g. Eid
Collection -> a real occasion=eid product's image). These are the same
merchant CDN URLs already trusted and rendered everywhere else in the app
(referrerpolicy="no-referrer").

Known tradeoff, accepted for now, consistent with how title/subtitle/
description are already static hand-curated fields rather than computed
per-request: if the specific underlying product is later removed from the
catalog, its image URL likely still resolves (Shopify CDN retention), but
isn't guaranteed forever. A future improvement would be to pick this image
dynamically per-request from the collection's own live filter results
instead of a fixed URL.

Revision ID: 0007_seed_collection_images
Revises: 0006_promote_kids_corner
Create Date: 2026-07-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0007_seed_collection_images"
down_revision: Union[str, None] = "0006_promote_kids_corner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IMAGES = {
    "Kids Corner": "https://cdn.shopify.com/s/files/1/0488/9201/8848/files/BK12602BGWS8557_1.jpg?v=1772189753",
    "Eid Collection": "https://cdn.shopify.com/s/files/1/0488/9201/8848/files/BT12601UN004171_1_c4a3ba68-8217-45de-9b4d-06fe5c41d265.jpg?v=1772014021",
    "Mehndi & Sangeet": "https://cdn.shopify.com/s/files/1/0650/8249/1105/files/S26B4078_Teal_1.jpg?v=1774854491",
    "Everyday Essentials": "https://cdn.shopify.com/s/files/1/0872/1278/5848/files/MU2PBS26O1F1_1.jpg?v=1784209808",
    "Formal Affairs": "https://cdn.shopify.com/s/files/1/0268/9715/4090/files/5_bc250fea-c691-45e4-903f-02952d13fcec.webp?v=1759748809",
    "Summer Breeze": "https://cdn.shopify.com/s/files/1/0488/9201/8848/files/BT12602UN004512_1.jpg?v=1776943221",
}


def upgrade() -> None:
    bind = op.get_bind()
    for title, image_url in _IMAGES.items():
        bind.execute(
            text("UPDATE collections SET image_url = :image_url WHERE title = :title"),
            {"title": title, "image_url": image_url},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for title in _IMAGES:
        bind.execute(
            text("UPDATE collections SET image_url = '' WHERE title = :title"), {"title": title}
        )
