from tasdeeq.extract import extract_invoice, extract_line_items
from tasdeeq.schema import OCRResult

CLEAN_INVOICE = """\
انوائس نمبر: INV-2025-0042
تاریخ: 15-06-2025
تفصیل تعداد شرح رقم
چینی 2 150 300
آٹا 50 120 6000
مجموعی رقم: 6,300
سیلز ٹیکس: 945
کل رقم: 7,245
"""


def ocr(text: str, engine: str = "test") -> OCRResult:
    return OCRResult.from_text(engine, text)


def test_extract_full_invoice():
    inv, raw = extract_invoice(ocr(CLEAN_INVOICE))
    assert inv.invoice_number == "INV-2025-0042"
    assert inv.date == "2025-06-15"
    assert len(inv.line_items) == 2
    assert inv.line_items[0].quantity == 2
    assert inv.line_items[0].unit_price == 150
    assert inv.line_items[0].line_total == 300
    assert inv.line_items[1].line_total == 6000
    assert inv.subtotal == 6300
    assert inv.tax == 945
    assert inv.total == 7245
    assert raw["invoice_number"] == "INV-2025-0042"
    assert raw["date"] == "2025-06-15"


def test_extract_urdu_digits():
    text = """\
انوائس نمبر: بل-۰۰۷
تاریخ: ۱۵-۰۶-۲۰۲۵
چینی ۲ ۱۵۰ ۳۰۰
کل رقم: ۳۰۰
"""
    inv, _ = extract_invoice(ocr(text))
    assert inv.line_items[0].quantity == 2
    assert inv.line_items[0].line_total == 300
    assert inv.total == 300
    assert inv.date == "2025-06-15"


def test_extract_english_labels():
    text = """\
Invoice #: A-99
Date: 2025-01-03
Widget 3 10.5 31.5
Subtotal: 31.5
Tax: 0
Total: 31.5
"""
    inv, _ = extract_invoice(ocr(text))
    assert inv.invoice_number == "A-99"
    assert inv.date == "2025-01-03"
    assert inv.total == 31.5
    assert inv.tax == 0
    assert len(inv.line_items) == 1


def test_missing_fields_are_none_not_guessed():
    inv, raw = extract_invoice(ocr("چینی 2 150 300\n"))
    assert inv.invoice_number is None
    assert inv.date is None
    assert inv.subtotal is None
    assert inv.tax is None
    assert inv.total is None
    assert "total" not in raw


def test_impossible_date_kept_raw_for_verifier_to_flag():
    # extract keeps the raw string; verify.py turns it into a red verdict
    inv, _ = extract_invoice(ocr("تاریخ: 31-02-2025\nکل رقم: 100\n"))
    assert inv.date == "31-02-2025"
    assert inv.total == 100


def test_line_items_skip_total_and_header_rows():
    lines = [
        "تفصیل تعداد شرح رقم",
        "چینی 2 150 300",
        "کل رقم: 300",
        "آٹا 10 50 500",
    ]
    items = extract_line_items(lines)
    assert len(items) == 2
    assert items[0].description == "چینی"
    assert items[1].description == "آٹا"


def test_row_with_two_numbers_is_not_an_item():
    # conservative: needs qty, rate AND amount
    assert extract_line_items(["چینی 300"]) == []


def test_total_label_matches_specifically():
    # "کل رقم" must win over tax line even when both present
    text = "سیلز ٹیکس: 10\nکل رقم: 110\n"
    inv, _ = extract_invoice(ocr(text))
    assert inv.tax == 10
    assert inv.total == 110


def test_reversed_row_amount_first_desc_last():
    # engines reading RTL emit [amount rate qty desc] token order
    items = extract_line_items(["300  150  2  چینی"])
    assert len(items) == 1
    it = items[0]
    assert it.description == "چینی"
    assert it.quantity == 2
    assert it.unit_price == 150
    assert it.line_total == 300


def test_reversed_row_with_ocr_broken_product_uses_position():
    items = extract_line_items(["594  22  5  چائے"])
    assert len(items) == 1
    it = items[0]
    assert it.description == "چائے"
    assert it.quantity == 5
    assert it.unit_price == 22
    assert it.line_total == 594


def test_yeh_variants_match_labels():
    # OCR often prints Arabic Yeh U+064A inside تاریخ
    text = (
        "بل نمبر: INV-2025-0042\n"
        "\u062a\u0627\u0631\u064a\u062e: 15-06-2025\n"  # تاريخ with Arabic Yeh
        "کل رقم: 100\n"
    )
    inv, _ = extract_invoice(ocr(text))
    assert inv.invoice_number == "INV-2025-0042"
    assert inv.date == "2025-06-15"


def test_space_separated_date_from_ocr():
    text = "تاریخ: 2024 10 23\nکل رقم: 40,807.25\n"
    inv, _ = extract_invoice(ocr(text))
    assert inv.date == "2024-10-23"


def test_date_line_is_not_parsed_as_a_row():
    items = extract_line_items(["تاریخ: 2024 10 23"])
    assert items == []


def test_invoice_number_shape_fallback_when_label_garbled():
    text = "INV-\u0628\u0644 \u0646\u0645\u067e : 6483-2024\nکل رقم: 100\n"
    inv, _ = extract_invoice(ocr(text))
    assert inv.invoice_number == "INV-2024-6483"


def test_invoice_number_shape_fallback_flipped_year_position():
    # RTL readers may emit the numeric pairs in reversed order
    text = "نمبر: INV-6483-2024\n"
    inv, _ = extract_invoice(ocr(text))
    assert inv.invoice_number == "INV-2024-6483"


# --- regressions from the real Qaari output on synth/out/0082 (captured 2026-10-02) ---

QAARI_0082 = """\
INV-2024-9288
15-08-2024
تفصيل تعداد شرح رقم
24 397.25 9,534
آيند
37 241 8,917
پتاس
33 8.25 272.25
آنا
31 312 9,672
مجمووع رقم: 28,395.25
28,395.25
كل رقم: 28,395.25
"""


def test_qaari_raw_0082_full_extraction():
    """Qaari output: Arabic Kaf in کل رقم, typo in مجموعی رقم, split rows."""
    inv, _ = extract_invoice(ocr(QAARI_0082, engine="qaari"))
    assert inv.invoice_number == "INV-2024-9288"
    assert inv.date == "2024-08-15"
    assert inv.subtotal == 28395.25
    assert inv.tax is None  # ground truth has no tax line either
    assert inv.total == 28395.25
    assert len(inv.line_items) == 4
    assert inv.line_items[0].quantity == 24
    assert inv.line_items[0].unit_price == 397.25
    assert inv.line_items[0].line_total == 9534


def test_arabic_kaf_matches_urdu_kaf_label():
    # Qaari reads Urdu ک (U+06A9) as Arabic ك (U+0643)
    inv, _ = extract_invoice(ocr("\u0643\u0644 \u0631\u0642\u0645: 100\n"))
    assert inv.total == 100


def test_fuzzy_label_typo_subtotal():
    # Qaari OCR typo: مجموعی رقم -> مجمووع رقم (edit distance 2)
    inv, _ = extract_invoice(ocr("مجمووع رقم: 500\nکل رقم: 550\n"))
    assert inv.subtotal == 500
    assert inv.total == 550


def test_split_row_numbers_line_then_desc_line():
    lines = [
        "تفصیل تعداد شرح رقم",
        "2 150 300",
        "چینی",
        "کل رقم: 300",
    ]
    items = extract_line_items(lines)
    assert len(items) == 1
    assert items[0].description == "چینی"
    assert items[0].quantity == 2
    assert items[0].unit_price == 150
    assert items[0].line_total == 300


def test_split_row_header_is_never_used_as_description():
    # only the header sits next to the numbers line: the row must be dropped,
    # not mislabelled with the header text
    items = extract_line_items(["تفصیل تعداد شرح رقم", "2 150 300"])
    assert items == []


def test_mega_line_split_at_labels_keeps_tail():
    # Qaari can emit the whole page as ONE line. The splitter must cut at
    # label anchors and keep the value AFTER the last anchor (regression:
    # the tail past the final cut was dropped -> total=None).
    mega = (
        "دم کی دکان INV-2024-1111 تاریخ: 2024-05-06 اشیاء پہلی 10 20 200 دوسرا 5 30 150"
        + " پرانی چیزیں بہت ہیں اور گاہک انتظار میں رہتے ہیں" * 2
        + " مجموعی رقم:350 وی اے ٹیکس:50 کل رقم:400"
    )
    assert len(mega) > 160  # otherwise the splitter is a no-op
    inv, _ = extract_invoice(ocr(mega))
    assert inv.invoice_number == "INV-2024-1111"
    assert inv.date == "2024-05-06"
    assert inv.subtotal == 350
    assert inv.tax == 50
    assert inv.total == 400
