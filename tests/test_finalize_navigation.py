import fitz

from finalize_navigation import _translated_link_rect


def test_translated_link_uses_nearby_matching_citation_token():
    words = [
        (120.0, 100.0, 155.0, 112.0, "2005;", 0, 0, 0),
        (510.0, 96.0, 560.0, 112.0, "等人,2005;", 0, 0, 0),
        (700.0, 300.0, 750.0, 316.0, "2005", 0, 0, 0),
    ]

    assert _translated_link_rect(words, {"2005"}, 106.0, 400.0) == fitz.Rect(
        510.0, 96.0, 560.0, 112.0
    )


def test_translated_link_does_not_guess_when_only_distant_match_exists():
    words = [(700.0, 300.0, 750.0, 316.0, "2005", 0, 0, 0)]

    assert _translated_link_rect(words, {"2005"}, 106.0, 400.0) is None
