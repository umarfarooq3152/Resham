"""Tests for orchestrator's crawl-start staggering — the fix for a real
incident where 25 brands crawled with no pacing finished in 39s and got
24/25 rate limited by Shopify/Cloudflare."""

from resham.crawler.orchestrator import _stagger_delays


def test_delays_are_strictly_increasing():
    delays = _stagger_delays(10, min_seconds=5.0, max_seconds=10.0)

    assert all(later > earlier for earlier, later in zip(delays, delays[1:]))


def test_delays_stay_within_the_cumulative_bounds():
    count = 20
    min_seconds, max_seconds = 20.0, 60.0
    delays = _stagger_delays(count, min_seconds, max_seconds)

    assert delays[0] >= min_seconds
    assert delays[-1] <= count * max_seconds
    assert delays[-1] >= count * min_seconds


def test_zero_brands_returns_empty_list():
    assert _stagger_delays(0, 20.0, 60.0) == []


def test_single_brand_still_gets_a_nonzero_delay():
    delays = _stagger_delays(1, 20.0, 60.0)

    assert len(delays) == 1
    assert 20.0 <= delays[0] <= 60.0
