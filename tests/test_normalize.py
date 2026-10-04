from datetime import date

from tasdeeq.normalize import (
    edit_distance,
    iso_date,
    normalize_digits,
    normalize_text,
    normalized_similarity,
    parse_amount,
    parse_date,
)


def test_urdu_digits_to_ascii():
    assert normalize_digits("۱۲۳۴۵") == "12345"
    assert normalize_digits("٦٧٨٩٠") == "67890"


def test_strip_tatweel_and_zero_width():
    assert normalize_text("انـوائ\u200cس") == "انوائس"
    assert normalize_text("\ufeffبِل\u200d") == "بِل"


def test_punctuation_unified():
    assert normalize_text("۱۲،۳۴") == "12,34"
    assert normalize_text("۴۵۔") == "45."
    assert normalize_text("۵۰٫۵") == "50.5"   # Arabic decimal separator
    assert normalize_text("۱٬۰۰۰") == "1000"  # Arabic thousands separator


def test_whitespace_collapsed():
    assert normalize_text("بل  2024 \t- 001") == "بل 2024 - 001"


def test_parse_amount():
    assert parse_amount("1,250.50") == 1250.50
    assert parse_amount("۲۵۰") == 250.0
    assert parse_amount("Rs. 3,400") == 3400.0
    assert parse_amount("روپے ۷۵۰") == 750.0
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount("N/A") is None


def test_parse_date_formats():
    assert parse_date("15-06-2025") == date(2025, 6, 15)
    assert parse_date("2025/06/15") == date(2025, 6, 15)
    assert parse_date("۱۵-۰۶-۲۰۲۵") == date(2025, 6, 15)
    assert parse_date("31-02-2025") is None  # impossible date
    assert parse_date("not a date") is None
    assert iso_date("15-06-2025") == "2025-06-15"


def test_edit_distance():
    assert edit_distance("", "abc") == 3
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("same", "same") == 0


def test_normalized_similarity():
    assert normalized_similarity("۱۲۳", "123") == 1.0
    assert normalized_similarity("", "") == 1.0
    assert normalized_similarity("abc", "") == 0.0
    assert 0.0 < normalized_similarity("abcd", "abce") < 1.0


def test_edit_distance_limit():
    assert edit_distance("kitten", "sitting", limit=3) == 3
    assert edit_distance("abc", "xyz", limit=1) == 2  # > limit -> limit+1
    assert edit_distance("same", "same", limit=0) == 0
    assert edit_distance("a", "abcdefgh", limit=2) == 3  # length gate
    assert edit_distance("ab", "ab", limit=1) == 0
