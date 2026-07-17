"""Regression coverage for mapper.is_kids_apparel — specifically that it
also scans description_text, since this catalog's kids listings sometimes
name the audience only there ("toddler girls", "5 to 6 years") with no kids
word anywhere in title/category/tags."""

from resham.catalog.mapper import is_kids_apparel


def test_kids_signal_in_title_is_detected():
    assert is_kids_apparel("Boys Printed Tee", "T-Shirt", []) is True


def test_kids_signal_only_in_description_is_detected():
    assert (
        is_kids_apparel(
            "Crew Neck Graphic Tee",
            "T-Shirt",
            [],
            description_text="Stone-colored blended tee, designed for toddler girls",
        )
        is True
    )


def test_no_kids_signal_anywhere_is_not_flagged():
    assert (
        is_kids_apparel(
            "Crew Neck Graphic Tee",
            "T-Shirt",
            [],
            description_text="Stone-colored blended tee with a regular fit",
        )
        is False
    )
