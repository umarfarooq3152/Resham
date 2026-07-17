"""Regression coverage for classify_apparel_text against a documented
historical misclassification.

The "collar" case is a forward-looking correctness assertion on today's
code, not a literal before/after repro: the old free-text classifier that
had this bug (a bare "collar" substring incidentally matching inside
"Johnny Collar Polo" and bumping it to a higher formality tier) predates
this repo's git history and isn't recoverable — see
src/resham/nlp/garments.py's tradition_from_family docstring for the
historical account. Verified against current code before writing this
case: classify_apparel_text("Johnny Collar Polo") returns SEMI_FORMAL,
not FORMAL.
"""

import pytest

from resham.nlp.apparel_classification import SEMI_FORMAL, classify_apparel_text
from tests.regression.cases import ClassificationRegressionCase

CLASSIFICATION_REGRESSION_CASES = [
    ClassificationRegressionCase(
        name="collar_substring_does_not_bump_formality",
        source=(
            "garments.py tradition_from_family docstring — historical account "
            "of the old free-text classifier; not recoverable from git history"
        ),
        text="Johnny Collar Polo",
        expected_formality=SEMI_FORMAL,
        expected_tradition="western",
    ),
]


@pytest.mark.parametrize(
    "case", CLASSIFICATION_REGRESSION_CASES, ids=lambda c: c.name
)
def test_apparel_classification_regression(case: ClassificationRegressionCase):
    result = classify_apparel_text(case.text)

    assert result.formality == case.expected_formality, case.source
    if case.expected_tradition is not None:
        assert result.tradition == case.expected_tradition, case.source
