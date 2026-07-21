"""One-call image-to-text intent extraction for visual catalog search."""

import json
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VISUAL_SEARCH_INSTRUCTION = """Describe this fashion reference image for a
Pakistani clothing catalog search. Return JSON with query (a compact factual
product description), category (one lowercase garment type or null), and color
(one dominant common color or null). Only state visibly evident details. Never
infer a brand, person, gender, age, price, occasion, fabric, or availability.
Use null rather than guessing."""


class VisualSearchIntent(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    category: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=60)


async def describe_search_image(
    image_bytes: bytes, *, mime_type: str, api_key: str, model: str
) -> VisualSearchIntent | None:
    """Best-effort single Gemini call; the image is neither stored nor indexed."""
    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Describe this image for product search.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=VISUAL_SEARCH_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=VisualSearchIntent,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VisualSearchIntent):
            return parsed
        return VisualSearchIntent.model_validate(json.loads(response.text))
    except Exception:
        logger.warning("Visual search image description failed", exc_info=True)
        return None
