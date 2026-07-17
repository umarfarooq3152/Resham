"""Regression fixtures seeded from documented real production misses.

Each case cites its source (a commit, a docstring, or a test file) so a
future reader can trace why the assertion exists without re-deriving it.
This module intentionally has no pytest import — it's plain data, reusable
outside pytest if a future eval tool wants the same fixtures.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationRegressionCase:
    name: str
    source: str
    text: str
    expected_formality: int
    expected_tradition: str | None = None
