"""Product schema — used throughout the API."""

from typing import Optional
from pydantic import BaseModel, Field


class ProductSemantics(BaseModel):
    """Versioned retrieval profile derived from trustworthy catalog fields."""

    version: str = "catalog-semantic-v1"
    product_family: Optional[str] = None
    text_derived_color: Optional[str] = None
    product_tradition: Optional[str] = None
    product_formality: Optional[str] = None
    audiences: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)
    search_text: str = Field(
        default="",
        exclude=True,
        description="Internal retrieval text; never included in product API payloads.",
    )


class ProductVariantOut(BaseModel):
    """One purchasable Shopify variant — the unit `cart/add.js` operates on.
    `variant_id` is Shopify's own numeric variant id (distinct from
    Product.id's composite catalog key), the only id a merchant's cart
    endpoint accepts."""

    variant_id: str
    color: Optional[str] = None
    size: Optional[str] = None
    price: float
    available: bool


class Product(BaseModel):
    """Product data model — matches frontend expectations."""

    id: str = Field(..., description="Composite id: {brand_slug}:{shopify_id}")
    name: str
    description: Optional[str] = None
    price: float
    colors: list[str] = Field(default_factory=list)
    color_images: dict[str, str] = Field(
        default_factory=dict,
        description="Lowercase color option to its variant-specific image URL.",
    )
    sizes: list[str] = Field(default_factory=list)
    occasion: Optional[str] = None
    category: Optional[str] = Field(None, description="Garment type, e.g. Shopify product_type")
    tags: list[str] = Field(default_factory=list)
    shopify_tags: list[str] = Field(
        default_factory=list,
        description=(
            "Raw merchant-set Shopify tags — often names the garment type or "
            "audience (e.g. 'Kurta', 'Kids', 'Girls') more reliably than the "
            "title/description alone; used for search scoring and ingestion "
            "filtering, not primarily for display."
        ),
    )
    is_kids: bool = Field(
        default=False,
        description=(
            "Detected as a kids/toddler item (category prefix, vendor, or "
            "tags) — excluded from search by default so it doesn't surface "
            "in an adult's search, but specifically filtered FOR when a "
            "shopper's message indicates they're buying for a child."
        ),
    )
    department: Optional[str] = Field(
        None,
        pattern="^(men|women|unisex)$",
        description="Product-level audience inferred from merchant metadata.",
    )
    age_ranges_months: list[tuple[int, int]] = Field(
        default_factory=list,
        description="Explicit child-size age ranges, stored as inclusive months.",
    )
    semantics: Optional[ProductSemantics] = Field(
        None,
        description="Versioned canonical profile used by hybrid retrieval.",
    )
    image: str
    secondaryImage: Optional[str] = None
    product_url: str
    variants: list[ProductVariantOut] = Field(
        default_factory=list,
        description=(
            "Purchasable Shopify variants for cart hand-off. Populated only "
            "by GET /products/{id} (the detail view) — search/collections/"
            "session/wishlist responses leave this empty by design, to keep "
            "list payloads lean."
        ),
    )
    brand_domain: Optional[str] = Field(
        None, description="Merchant storefront domain, for building a cart/add.js URL."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "limelight:8439992975448",
                "name": "Embroidered Lawn Suit",
                "description": "Beautiful embroidered suit with silk lining",
                "price": 8500.0,
                "colors": ["Blue", "Pink"],
                "sizes": ["S", "M", "L"],
                "occasion": "Eid",
                "tags": ["silk", "embroidery"],
                "image": "https://cdn.shopify.com/...",
                "secondaryImage": "https://cdn.shopify.com/...",
                "product_url": "https://limelight.pk/products/8439992975448",
            }
        }


class ProductSearchResponse(BaseModel):
    """Paginated product search response."""

    items: list[Product]
    total: int
    page: int
    page_size: int
    has_more: bool = Field(
        default=False,
        description="True if more results available on next page",
    )
