from app.config.cors import parse_allowed_origins


def test_parse_allowed_origins_empty_string():
    assert parse_allowed_origins("") == []


def test_parse_allowed_origins_single():
    assert parse_allowed_origins("https://planforge.example.com") == [
        "https://planforge.example.com"
    ]


def test_parse_allowed_origins_multiple_trims_whitespace():
    raw = "https://planforge.example.com, https://staging.planforge.example.com "
    assert parse_allowed_origins(raw) == [
        "https://planforge.example.com",
        "https://staging.planforge.example.com",
    ]


def test_parse_allowed_origins_ignores_empty_segments():
    assert parse_allowed_origins("https://a.com,,https://b.com,") == [
        "https://a.com",
        "https://b.com",
    ]
