from resham.nlp.brands import extract_requested_brands

BRANDS = [
    ("khaadi", "Khaadi"),
    ("sapphire", "Sapphire"),
    ("maria-b", "Maria B."),
]


def test_extracts_explicit_declared_brand_names_and_slugs():
    assert extract_requested_brands("show Khaadi or maria-b kurtas", BRANDS) == [
        "khaadi",
        "maria-b",
    ]


def test_requires_whole_declared_brand_name_not_a_partial_match():
    assert extract_requested_brands("a sapphire-blue outfit", BRANDS) == []


def test_does_not_invent_or_fuzzily_match_a_brand():
    assert extract_requested_brands("something from Khaadii", BRANDS) == []
