"""Property-based crash-safety and structural-contract tests for
classify_apparel_text — chained regex/SequenceMatcher logic over raw
scraped Shopify text, where a crash would 500 the search endpoint.

Deliberately does NOT assert "formality is monotonic under heavy-work
markers" — that's currently false on real input (a bridal item with
heavy embellishment can demote from BRIDAL to PARTY, see
apparel_classification.py's hard `tier = PARTY` assignment for the
crop-top+heavy-work case), so encoding it as an invariant would just be
asserting a known-wrong behavior.
"""

from hypothesis import given, settings, strategies as st

from resham.nlp.apparel_classification import BRIDAL, CASUAL, classify_apparel_text


@given(st.text())
@settings(deadline=None)
def test_formality_tier_is_always_within_the_defined_range(text: str):
    result = classify_apparel_text(text)
    assert CASUAL <= result.formality <= BRIDAL


@given(st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x1FFFF)))
@settings(deadline=None)
def test_never_raises_on_arbitrary_unicode_or_garbage(text: str):
    classify_apparel_text(text)
