"""Property-based structural-contract tests for
search_service._query_keywords — the entrypoint that tokenizes every
free-text shopper query before scoring.
"""

from hypothesis import given, settings, strategies as st

from resham.services.search_service import _query_keywords

_garbage_text = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x1FFFF))


@given(_garbage_text)
@settings(deadline=None)
def test_never_raises_on_arbitrary_unicode_or_garbage(text: str):
    _query_keywords(text)


@given(_garbage_text)
@settings(deadline=None)
def test_result_has_no_duplicates_and_no_blank_entries(text: str):
    result = _query_keywords(text)
    assert len(result) == len(set(result))
    assert all(keyword.strip() for keyword in result)
