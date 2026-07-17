"""Coverage for the product_tradition/product_formality query-side and
catalog-side helpers — both are soft ranking signals only, so the tests
focus on the "never guess, leave it None" boundary as much as the positive
matches (see search/ranking.py's STYLE_MATCH_BOOST docstring for why an
absent value must never be treated as a mismatch)."""

from resham.nlp.garments import (
    requested_formality,
    requested_tradition,
    tradition_from_family,
)


def test_tradition_from_family_recognizes_an_unambiguous_eastern_garment():
    assert tradition_from_family("kurta") == "eastern"
    assert tradition_from_family("lehenga") == "eastern"
    assert tradition_from_family("suit") == "eastern"  # verified: catalog's "suit" bucket is unstitched lawn/khaddar sets


def test_tradition_from_family_recognizes_an_unambiguous_western_garment():
    assert tradition_from_family("jeans") == "western"
    assert tradition_from_family("blazer") == "western"
    assert tradition_from_family("coat") == "western"


def test_tradition_from_family_leaves_a_genuinely_mixed_family_as_none():
    """"shirt" (18k+ live products) is a near-even split between eastern
    kameez tops and western casual shirts in this catalog — asserting
    either would wrongly exclude real matches on one side whenever
    tradition were ever used as a hard filter, so it must stay unknown."""
    assert tradition_from_family("shirt") is None
    assert tradition_from_family("top") is None
    assert tradition_from_family("tunic") is None


def test_tradition_from_family_returns_none_for_no_family():
    assert tradition_from_family(None) is None


def test_requested_tradition_reads_eastern_or_western_from_style_descriptors():
    assert requested_tradition(["embroidered", "eastern"]) == "eastern"
    assert requested_tradition(["western"]) == "western"


def test_requested_tradition_is_none_when_no_tradition_word_present():
    assert requested_tradition(["embroidered", "formal"]) is None
    assert requested_tradition([]) is None


def test_requested_formality_reads_an_explicit_formality_word():
    assert requested_formality(["formal", "eastern"]) == "formal"
    assert requested_formality(["semi-formal"]) == "semi-formal"


def test_requested_formality_is_none_when_no_formality_word_present():
    assert requested_formality(["eastern", "embroidered"]) is None
