"""Gemini-based product image classification — a supplementary,
non-authoritative signal for garment category/color, used only to fill
gaps the text pipeline (nlp/garments.py, nlp/colors.py) leaves behind on a
sparsely-described product. Never touches is_kids/age_ranges_months: a
photo cannot safely settle that hard, safety-relevant constraint (see
search/eligibility.py's "unknown age excluded, not guessed" rule), so
vision is deliberately scoped out of it entirely.
"""

import json
import logging

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VISION_INSTRUCTION = """You are a fashion product image classifier for a Pakistani
clothing catalog. Look only at the product photo and identify what is actually
shown — you do not have access to the listing's title or description.

Return:
- category: the single garment type shown (e.g. "kurta", "polo shirt", "abaya",
  "lehenga", "jeans", "sneakers"), lowercase, catalog-friendly English. Use null
  if you genuinely cannot tell.
- colors: the dominant color(s) actually visible on the garment, as a short list
  of common color words (e.g. ["red"], ["black", "white"]). Empty list if unclear.

Only describe what is visibly in the image. Never guess age, gender, or size from
the photo or any model wearing the item — that judgment belongs to a different,
merchant-data-driven part of the system, not to you. Use null/empty rather than a
low-confidence guess."""


class VisionClassification(BaseModel):
    category: str | None = None
    colors: list[str] = Field(default_factory=list)


async def classify_product_image(
    image_url: str,
    *,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> VisionClassification | None:
    """Best-effort image classification. Returns None on any failure
    (download error, timeout, rate limit, unparseable response) — the
    caller leaves the product's vision_classified_at unset so it's retried
    on a later worker cycle rather than recording a guess."""
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            image_response = await client.get(image_url)
            image_response.raise_for_status()
            image_bytes = image_response.content
            mime_type = image_response.headers.get("content-type", "image/jpeg").split(";")[0]

        genai_client = genai.Client(api_key=api_key)
        response = await genai_client.aio.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Classify this product photo.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=VISION_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=VisionClassification,
            ),
        )
    except Exception:
        logger.warning("Vision classification failed for %s", image_url, exc_info=True)
        return None

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, VisionClassification):
        return parsed

    try:
        return VisionClassification.model_validate(json.loads(response.text))
    except Exception:
        logger.warning("Vision classification returned an unparseable response for %s", image_url)
        return None
