"""Regression coverage for mapper.extract_color_images — specifically the
filename fallback for stores that give zero structured variant<->image
linkage (no featured_image, no image_id match, empty variant_ids on every
image), which a live catalog audit found on ~75% of in-stock multi-color
products. Real product data patterns (from resham.myshopify handbag
listings) are used as fixtures rather than synthetic ones."""

from resham.catalog.mapper import extract_color_images


def _variant(option1: str) -> dict:
    return {"id": 1, "option1": option1, "featured_image": None, "image_id": None}


def test_structured_variant_image_id_still_wins_over_filename():
    product = {
        "options": [{"name": "Color", "values": ["Black"]}],
        "variants": [{"id": 1, "option1": "Black", "image_id": 55, "featured_image": None}],
        "images": [{"id": 55, "src": "https://cdn.shopify.com/files/generic.jpg"}],
    }
    assert extract_color_images(product) == {"black": "https://cdn.shopify.com/files/generic.jpg"}


def test_falls_back_to_filename_when_no_structured_linkage_exists():
    # Real shape observed on Cross-Body Bags - E933: every image has
    # variant_ids == [] and every variant has featured_image/image_id null,
    # but the color is spelled out in the filename itself.
    product = {
        "options": [{"name": "Color", "values": ["Black", "Fawn", "Pink"]}],
        "variants": [
            _variant("Black"),
            _variant("Fawn"),
            _variant("Pink"),
        ],
        "images": [
            {"id": 10, "src": "https://cdn.shopify.com/files/WBC25E933_BLACK_3.png", "variant_ids": []},
            {"id": 11, "src": "https://cdn.shopify.com/files/WBC25E933_FAWN_1.png", "variant_ids": []},
            {"id": 12, "src": "https://cdn.shopify.com/files/WBC25E933_PINK_2.png", "variant_ids": []},
        ],
    }
    assert extract_color_images(product) == {
        "black": "https://cdn.shopify.com/files/WBC25E933_BLACK_3.png",
        "fawn": "https://cdn.shopify.com/files/WBC25E933_FAWN_1.png",
        "pink": "https://cdn.shopify.com/files/WBC25E933_PINK_2.png",
    }


def test_colors_with_no_matching_filename_are_left_unmapped_not_guessed():
    # Real shape observed on Shoulder Bags - E830: only 3 of 4 declared
    # colors are ever spelled out in an image filename. The 4th ("Mustard")
    # must stay absent, not get force-matched to an unrelated image.
    product = {
        "options": [{"name": "Color", "values": ["Black", "Fawn", "Green", "Mustard"]}],
        "variants": [_variant("Black"), _variant("Fawn"), _variant("Green"), _variant("Mustard")],
        "images": [
            {"id": 1, "src": "https://cdn.shopify.com/files/WBS25E830_3.jpg", "variant_ids": []},
            {"id": 2, "src": "https://cdn.shopify.com/files/WBS25E830_-_Fawn_3.png", "variant_ids": []},
            {"id": 3, "src": "https://cdn.shopify.com/files/WBS25E830_green_3.jpg", "variant_ids": []},
            {"id": 4, "src": "https://cdn.shopify.com/files/WBS25E830_-_Black_1.png", "variant_ids": []},
        ],
    }
    result = extract_color_images(product)
    assert result == {
        "fawn": "https://cdn.shopify.com/files/WBS25E830_-_Fawn_3.png",
        "green": "https://cdn.shopify.com/files/WBS25E830_green_3.jpg",
        "black": "https://cdn.shopify.com/files/WBS25E830_-_Black_1.png",
    }
    assert "mustard" not in result


def test_short_color_label_is_not_matched_by_filename_fallback():
    # A short/ambiguous declared color (e.g. a single letter) must not
    # latch onto a coincidental substring in an unrelated filename.
    product = {
        "options": [{"name": "Color", "values": ["A", "Black"]}],
        "variants": [_variant("A"), _variant("Black")],
        "images": [
            {"id": 1, "src": "https://cdn.shopify.com/files/SKU-A123.jpg", "variant_ids": []},
            {"id": 2, "src": "https://cdn.shopify.com/files/SKU-BLACK.jpg", "variant_ids": []},
        ],
    }
    result = extract_color_images(product)
    assert "a" not in result
    assert result["black"] == "https://cdn.shopify.com/files/SKU-BLACK.jpg"


def test_no_color_option_still_returns_empty_without_touching_filenames():
    product = {
        "options": [{"name": "Size", "values": ["Small", "Medium"]}],
        "variants": [{"id": 1, "option1": "Small"}],
        "images": [{"id": 1, "src": "https://cdn.shopify.com/files/whatever_black.jpg"}],
    }
    assert extract_color_images(product) == {}
