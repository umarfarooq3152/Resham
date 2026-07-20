"""Tests for the deterministic fast-path refinement classifier."""

import pytest

from resham.nlp.kids_age import extract_child_age_months
from resham.nlp.fast_path_classifier import (
    classify,
    extract_budget_min,
    extract_budget_range,
    extract_department,
    is_kids_request,
)
from resham.schemas.product import Product
from resham.schemas.session import SessionState


def _product(id_, price, **kwargs) -> Product:
    defaults = dict(
        name="Test Product",
        description="A test product",
        image="https://example.com/1.jpg",
        product_url="https://example.com/products/1",
    )
    defaults.update(kwargs)
    return Product(id=id_, price=price, **defaults)


@pytest.fixture
def last_results() -> list[Product]:
    return [
        _product("limelight:1", 5000),
        _product("limelight:2", 3000),
        _product("alkaram:1", 15000),
    ]


def test_no_match_falls_through_to_none():
    assert classify("something totally unrelated to any pattern", SessionState(), []) is None


@pytest.mark.parametrize("text", ["hey", "hey how are you", "Assalam-o-Alaikum!", "what's up?"])
def test_greeting_gets_a_friendly_local_reply(text):
    result = classify(text, SessionState(), [])

    assert result is not None
    assert result.diff.clarify is True
    assert "thanks for asking" in result.diff.assistant_reply


def test_is_kids_request_by_age():
    # Real bug: the LLM didn't reliably recognize "shopping for a child" on
    # its own, extracting a nonsensical size="kids" and surfacing adult
    # womenswear as if it matched a toddler's outfit. Detection now happens
    # deterministically, independent of whichever path (fast-path or LLM)
    # extracts the rest of the message (occasion/color/style).
    text = "I want to dress up my 2 year old daughter in something pink and traditional"
    assert is_kids_request(text) is True
    assert extract_child_age_months(text) == 24


def test_extracts_child_age_in_months():
    assert extract_child_age_months("an outfit for my 18 month old son") == 18


def test_does_not_extract_unrelated_duration_as_child_age():
    assert extract_child_age_months("I've been shopping here for 2 years") is None


def test_is_kids_request_by_keyword():
    for text in ["need a toddler outfit for eid", "looking for kids clothes", "something for my newborn"]:
        assert is_kids_request(text) is True, f"expected a kids-request match for {text!r}"


def test_is_kids_request_survives_dropped_o_in_old():
    # Real bug: this exact phrasing (a typo, or a voice-transcription
    # artifact — this app now also does real voice search via Whisper)
    # slipped through undetected because the strict "...years old" regex
    # required the literal substring "old", which "ld" doesn't contain.
    text = "I want to dress up my 2 year ld daughter in something pink and traditional"
    assert is_kids_request(text) is True


def test_age_alone_without_relation_word_does_not_trigger_kids_request():
    # "2 years" alone (no "old", no daughter/son/kid/etc.) is too weak a
    # signal on its own — e.g. "shopping here for 2 years" shouldn't be
    # treated as a kids request.
    assert is_kids_request("I've been shopping here for 2 years") is False


def test_adult_age_does_not_trigger_kids_request():
    assert is_kids_request("something for my 25 year old sister's wedding") is False


def test_kids_request_does_not_short_circuit_classify():
    # is_kids_request is layered on top in session_service, not inside
    # classify() — a kids message with no OTHER fast-path pattern in it
    # should fall through to LLM extraction like any other message, so
    # occasion/color/style still get extracted normally.
    text = "I want to dress up my 2 year old daughter in something pink and traditional"
    assert classify(text, SessionState(), []) is None


def test_cheaper_computes_budget_from_min_price(last_results):
    match = classify("can you show cheaper ones?", SessionState(), last_results)
    assert match is not None
    assert match.diff.budget_max == 2000  # floor(3000*0.9/1000)*1000 = 2000
    assert not match.show_more


def test_cheaper_with_no_prior_results_falls_through():
    assert classify("cheaper please", SessionState(), []) is None


def test_cheaper_never_goes_below_price_rounding_floor():
    cheap_results = [_product("limelight:1", 500)]
    match = classify("cheaper", SessionState(), cheap_results)
    assert match.diff.budget_max == 1000  # floor(500*0.9/1000)*1000 = 0, clamped to 1000


def test_more_formal_appends_style_descriptor():
    match = classify("show me something more formal", SessionState(), [])
    assert match is not None
    assert match.diff.style_descriptors == ["formal"]


def test_more_casual_appends_style_descriptor():
    match = classify("something more casual please", SessionState(), [])
    assert match.diff.style_descriptors == ["casual"]


def test_short_color_message_overwrites_color():
    match = classify("show me blue instead", SessionState(color_preference="red"), [])
    assert match is not None
    assert match.diff.color_preference == "blue"


def test_color_fast_path_preserves_requested_shade():
    match = classify("navy blue instead", SessionState(color_preference="blue"), [])
    assert match is not None
    assert match.diff.color_preference == "dark blue"


def test_simple_color_and_category_query_avoids_llm_path():
    match = classify("blue shirt", SessionState(department="women"), [])

    assert match is not None
    assert match.diff.category == "shirt"
    assert match.diff.color_preference == "blue"
    assert match.diff.department is None


def test_simple_color_material_category_query_avoids_llm_path():
    match = classify("black leather jackets", SessionState(department="men"), [])

    assert match is not None
    assert match.diff.category == "jacket"
    assert match.diff.color_preference == "black"
    assert match.diff.style_descriptors == ["leather"]


def test_descriptive_color_category_query_still_uses_full_extraction():
    assert classify("earthy blue silk shirt", SessionState(), []) is None


def test_long_message_with_color_word_does_not_fast_path():
    # A longer, more complex request should go to full LLM extraction instead
    # of being misclassified as a simple color-swap.
    text = "something like the red one but for a wedding happening in three days"
    assert classify(text, SessionState(), []) is None


def test_unknown_seasonal_word_keeps_full_extraction_but_known_style_is_fast():
    assert classify("winter jacket black", SessionState(), []) is None
    match = classify("brown knitted polos", SessionState(), [])
    assert match is not None
    assert match.diff.category == "polo"
    assert match.diff.style_descriptors == ["knitted"]


@pytest.mark.parametrize(
    ("query", "category", "department", "color", "style", "budget", "size"),
    [
        ("men hoodies", "hoodie", "men", None, [], None, None),
        ("women blue linen tops", "top", "women", "blue", ["linen"], None, None),
        ("black baggy jeans under 8k", "jeans", None, "black", ["baggy"], 8000, None),
        ("embroidered kurta size medium", "kurta", None, None, ["embroidered"], None, "M"),
        ("oversized sweatshirts in XXL", "sweatshirt", None, None, ["oversized"], None, "XXL"),
        ("women co-ord sets below 12000", "co-ord", "women", None, [], 12000, None),
        ("pink stripes shirt", "shirt", None, "pink", ["striped"], None, None),
    ],
)
def test_structured_product_searches_use_general_fast_path(
    query, category, department, color, style, budget, size
):
    match = classify(query, SessionState(), [])

    assert match is not None
    assert match.diff.category == category
    assert match.diff.department == department
    assert match.diff.color_preference == color
    assert match.diff.style_descriptors == style
    assert match.diff.budget_max == budget
    assert match.diff.size == size


def test_different_brand_excludes_dominant_brand(last_results):
    match = classify("show me a different brand", SessionState(), last_results)
    assert match is not None
    # limelight appears twice (dominant) vs alkaram once
    assert match.diff.excluded == ["limelight"]


def test_different_brand_with_no_results_excludes_nothing():
    match = classify("different brand please", SessionState(), [])
    assert match.diff.excluded == []


def test_show_more_sets_flag_without_state_mutation():
    match = classify("show more options", SessionState(occasion="eid"), [])
    assert match is not None
    assert match.show_more is True


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("remove occasion", "occasion"),
        ("any color", "color"),
        ("ignore the budget", "budget"),
        ("clear style", "style"),
        ("without a size", "size"),
    ],
)
def test_individual_filter_removal_is_a_fast_path(query, field):
    match = classify(query, SessionState(), [])

    assert match is not None
    assert match.diff.clear_fields == [field]


def test_any_age_inside_real_search_does_not_clear_filter():
    match = classify("kids shirts any age bro", SessionState(), [])

    assert match is None or match.diff.clear_fields == []


def test_specific_style_can_be_removed_without_clearing_other_styles():
    match = classify(
        "without stripes",
        SessionState(style_descriptors=["striped", "formal"]),
        [],
    )

    assert match is not None
    assert match.diff.remove_styles == ["striped"]


def test_formal_event_refinement_does_not_call_llm_or_invent_named_event():
    match = classify(
        "for a formal event",
        SessionState(category="shirt", color_preference="pink"),
        [],
    )

    assert match is not None
    assert match.diff.occasion is None
    assert match.diff.style_descriptors == ["formal"]
    assert match.diff.occasion is None
    assert match.diff.budget_max is None


def test_explicit_womenswear_refinement_is_deterministic():
    match = classify("I need women's clothing", SessionState(department="men"), [])
    assert match is not None
    assert match.diff.department == "women"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("a kurta for my son", "men"),
        ("for a toddler boy", "men"),
        ("a dress for my daughter", "women"),
        ("for a baby girl", "women"),
    ],
)
def test_child_gender_phrases_ground_the_requested_department(query, expected):
    assert extract_department(query) == expected
    assert is_kids_request(query) is True


def test_compound_gender_query_falls_through_for_full_extraction():
    assert classify("women's red wedding lehenga", SessionState(), []) is None


def test_unsure_category_gets_a_formality_path():
    match = classify("not sure", SessionState(occasion="wedding"), [])
    assert match is not None
    assert match.diff.clarify is True
    assert "understated" in match.diff.assistant_reply


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("more than 30000", 30000),
        ("more then 30000", 30000),  # common typo, must still match
        ("above 8k", 8000),
        ("starting from 1 lakh", 100000),
        ("at least 5000", 5000),
    ],
)
def test_extract_budget_min_variants(text, expected):
    assert extract_budget_min(text) == expected


def test_extract_budget_range_between_phrasing():
    assert extract_budget_range("between 20000 and 40000") == (20000, 40000)


def test_extract_budget_range_is_order_independent():
    # "Between 20k and 10k" still means (min=10000, max=20000) regardless of
    # which number the shopper stated first.
    assert extract_budget_range("between 20k and 10k") == (10000, 20000)


def test_extract_budget_range_returns_none_pair_without_between():
    assert extract_budget_range("under 5000") == (None, None)


def test_bare_budget_min_phrase_alone_is_a_fast_path():
    # Real bug: this branch used to require a category/style/occasion
    # alongside the budget phrase — a bare "above 30000" fell through to
    # the LLM even though it's an unambiguous structured search.
    match = classify("above 30000", SessionState(), [])
    assert match is not None
    assert match.diff.budget_min == 30000
    assert match.diff.budget_max is None
    assert "None" not in match.diff.assistant_reply


@pytest.mark.parametrize("text", ["western", "eastern"])
def test_bare_style_only_message_reply_never_prints_none(text):
    # Real bug: the old literal f-string reply printed the word "None" into
    # the user-facing reply whenever category was absent, e.g. a bare style
    # or budget-only refinement.
    match = classify(text, SessionState(), [])
    assert match is not None
    assert "None" not in match.diff.assistant_reply


def test_cheaper_diff_clears_budget_alongside_new_max(last_results):
    # _match_cheaper now sets clear_fields=["budget"] so a previously stated
    # budget_min (e.g. "above 30000") doesn't survive alongside the new,
    # lower ceiling and produce an impossible min > max range.
    match = classify("can you show cheaper ones?", SessionState(), last_results)
    assert match is not None
    assert match.diff.clear_fields == ["budget"]
    assert match.diff.budget_max == 2000
