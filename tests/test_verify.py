from tasdeeq.schema import Invoice, LineItem
from tasdeeq.verify import verify

GREEN, AMBER, RED = "green", "amber", "red"


def make_invoice(**overrides) -> Invoice:
    base = dict(
        invoice_number="INV-2025-0042",
        date="2025-06-15",
        line_items=[
            LineItem("چینی", 2.0, 150.0, 300.0),
            LineItem("آٹا", 50.0, 120.0, 6000.0),
        ],
        subtotal=6300.0,
        tax=945.0,
        total=7245.0,
    )
    base.update(overrides)
    return Invoice(**base)


def vmap(result):
    return {v.field: v for v in result.verdicts}


def test_two_agreeing_engines_all_green():
    res = verify(make_invoice(), make_invoice())
    vm = vmap(res)
    for field in ("invoice_number", "date", "subtotal", "tax", "total", "line_items"):
        assert vm[field].status == GREEN, f"{field}: {vm[field]}"
        assert vm[field].confidence == 0.9
        assert vm[field].reasons
    assert vm["line_items"].value == 2


def test_arithmetic_violation_with_localized_hint():
    # engines agree but line 1 arithmetic is wrong; 6001 -> 6000 is the unique fix
    inv = make_invoice()
    inv.line_items[1].line_total = 6001.0
    vm = vmap(verify(inv, inv))
    lt = vm["line_items[1].line_total"]
    assert lt.status == RED
    assert any("single-digit correction" in r for r in lt.reasons)
    assert lt.hints and "6001" in lt.hints[0]
    assert lt.value == 6001.0  # hint never auto-corrects the value
    assert vm["line_items[1].quantity"].status == AMBER
    assert vm["line_items[1].quantity"].reasons


def test_engine_disagreement_on_total_is_amber():
    a, b = make_invoice(), make_invoice()
    b.total = 7265.0
    vm = vmap(verify(a, b))
    assert vm["total"].status == AMBER
    assert any("engines disagree" in r for r in vm["total"].reasons)
    assert vm["total"].value == 7245.0  # keeps engine A value for review


def test_field_found_by_one_engine_only_is_amber():
    a, b = make_invoice(), make_invoice()
    b.total = None
    vm = vmap(verify(a, b))
    assert vm["total"].status == AMBER
    assert any("engine A only" in r for r in vm["total"].reasons)


def test_required_field_missing_in_both_is_red():
    a, b = make_invoice(invoice_number=None), make_invoice(invoice_number=None)
    vm = vmap(verify(a, b))
    assert vm["invoice_number"].status == RED
    assert vm["invoice_number"].confidence <= 0.1


def test_unparseable_date_is_red():
    a, b = make_invoice(date="31-02-2025"), make_invoice(date="31-02-2025")
    vm = vmap(verify(a, b))
    assert vm["date"].status == RED
    assert any("does not parse" in r for r in vm["date"].reasons)


def test_negative_amount_is_red():
    a, b = make_invoice(total=-500.0), make_invoice(total=-500.0)
    a.subtotal = b.subtotal = None
    vm = vmap(verify(a, b))
    assert vm["total"].status == RED
    assert any("negative" in r for r in vm["total"].reasons)


def test_row_count_mismatch_is_red_on_group():
    a = make_invoice()
    b = make_invoice()
    b.line_items = [LineItem("چینی", 2.0, 150.0, 300.0)]
    b.subtotal = b.tax = b.total = None
    vm = vmap(verify(a, b))
    assert vm["line_items"].status == RED
    assert any("row count" in r for r in vm["line_items"].reasons)
    assert vm["line_items[1].quantity"].status == AMBER
    assert any("engine B" in r for r in vm["line_items[1].quantity"].reasons)


def test_single_engine_mode_skips_agreement_keeps_arithmetic():
    inv = make_invoice()
    inv.line_items[1].line_total = 6001.0
    vm = vmap(verify(inv))  # b=None
    assert vm["total"].status == GREEN
    assert any("single engine" in r for r in vm["total"].reasons)
    assert vm["line_items[1].line_total"].status == RED


def test_text_disagreement_is_amber():
    a, b = make_invoice(), make_invoice()
    b.invoice_number = "INV-2025-0043"
    vm = vmap(verify(a, b))
    assert vm["invoice_number"].status == AMBER
    assert any("similarity" in r for r in vm["invoice_number"].reasons)


def test_missing_subtotal_with_uneven_total_is_flagged():
    a, b = make_invoice(subtotal=None), make_invoice(subtotal=None)
    a.total = b.total = 7300.0
    vm = vmap(verify(a, b))
    assert vm["subtotal"].status == AMBER
    assert vm["total"].status == AMBER


def test_no_tax_invoice_is_green_when_arithmetic_closes():
    a, b = make_invoice(tax=None), make_invoice(tax=None)
    a.total = b.total = 6300.0
    vm = vmap(verify(a, b))
    assert vm["tax"].status == GREEN
    assert vm["total"].status == GREEN
    assert vm["subtotal"].status == GREEN


def test_tax_absent_and_unverifiable_is_amber_not_green():
    # neither engine found tax and arithmetic cannot confirm absence (no subtotal)
    a, b = make_invoice(tax=None, subtotal=None), make_invoice(tax=None, subtotal=None)
    vm = vmap(verify(a, b))
    assert vm["tax"].status == AMBER
    assert vm["subtotal"].status == AMBER


def test_tax_absent_but_arithmetic_breaks_is_amber():
    # subtotal + 0 != total -> the missing tax is exactly what does not close
    a, b = make_invoice(tax=None), make_invoice(tax=None)  # 6300 + 0 != 7245
    vm = vmap(verify(a, b))
    assert vm["tax"].status == AMBER
    assert vm["subtotal"].status == AMBER
    assert vm["total"].status == AMBER


def test_empty_line_items_group_is_amber():
    a, b = make_invoice(line_items=[]), make_invoice(line_items=[])
    vm = vmap(verify(a, b))
    assert vm["line_items"].status == AMBER
