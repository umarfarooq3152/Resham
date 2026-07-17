"""Property-based crash-safety tests for garments.py's extraction
functions — regex/SequenceMatcher-based, run over free-text shopper
queries and raw merchant title/category/tag text at both request time
and ingestion time. A crash in any of these would 500 the search
endpoint or abort a catalog ingestion run.
"""

from hypothesis import given, settings, strategies as st

from resham.nlp.garments import (
    extract_garment_descriptors,
    extract_primary_garment,
    matches_garment_text,
)

_garbage_text = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x1FFFF))


@given(_garbage_text)
@settings(deadline=None)
def test_extract_garment_descriptors_never_raises(text: str):
    result = extract_garment_descriptors(text)
    assert isinstance(result, list)


@given(_garbage_text)
@settings(deadline=None)
def test_extract_primary_garment_never_raises_and_returns_str_or_none(text: str):
    result = extract_primary_garment(text)
    assert result is None or isinstance(result, str)


@given(_garbage_text, _garbage_text)
@settings(deadline=None)
def test_matches_garment_text_never_raises(value: str, garment: str):
    result = matches_garment_text(value, garment or None)
    assert isinstance(result, bool)
