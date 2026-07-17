"""Guards apparel_classification.py's liberal substring vocab against
accidental unification with garments.py's strict exact-family vocab.

These two lists are intentionally divergent: apparel_classification.py's
WESTERN_ITEMS is a substring scan over raw prose and includes "shirt";
garments.py's _EASTERN_FAMILIES/_WESTERN_FAMILIES require exact membership
on the canonical product_family token and exclude "shirt", since it's a
genuine near-50/50 eastern/western split in this catalog (see
tradition_from_family's docstring). product_semantics.py:111
(`if family != "shirt"`) exists specifically to reconcile that divergence
— merging the two lists would reintroduce the "shirt" guess it guards
against.
"""

from resham.nlp.apparel_classification import WESTERN_ITEMS
from resham.nlp.garments import _EASTERN_FAMILIES, _WESTERN_FAMILIES


def test_shirt_is_intentionally_excluded_from_the_strict_family_lists():
    assert "shirt" in WESTERN_ITEMS
    assert "shirt" not in _EASTERN_FAMILIES
    assert "shirt" not in _WESTERN_FAMILIES
