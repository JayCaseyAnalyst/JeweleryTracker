import asyncio
from unittest.mock import patch

import ring_tracker as rt


# ---------------------------------------------------------------------------
# compute_decision
# ---------------------------------------------------------------------------

def test_decision_new_sku_no_history():
    d = rt.compute_decision([], 990.0, "V-282350507")
    assert d.kind == "new"
    assert d.previous_price is None
    assert d.current_price == 990.0


def test_decision_first_record_creates_new():
    d = rt.compute_decision([{"sku": "OTHER", "price": 100.0}], 990.0, "V-282350507")
    assert d.kind == "new"


def test_decision_record_low():
    history = [
        {"sku": "A", "timestamp": "t", "price": 200.0},
        {"sku": "A", "timestamp": "t", "price": 150.0},
        {"sku": "A", "timestamp": "t", "price": 120.0},
    ]
    d = rt.compute_decision(history, 100.0, "A")
    assert d.kind == "record_low"
    assert d.lowest_price == 120.0
    assert d.previous_price == 120.0


def test_decision_drop_not_record():
    history = [
        {"sku": "A", "timestamp": "t", "price": 200.0},
        {"sku": "A", "timestamp": "t", "price": 90.0},
        {"sku": "A", "timestamp": "t", "price": 150.0},
    ]
    # previous 150, lowest 90, current 120 -> a drop but above the record low
    d = rt.compute_decision(history, 120.0, "A")
    assert d.kind == "drop"
    assert d.lowest_price == 90.0
    assert d.previous_price == 150.0


def test_decision_increase():
    history = [{"sku": "A", "timestamp": "t", "price": 100.0}]
    d = rt.compute_decision(history, 140.0, "A")
    assert d.kind == "increase"
    assert d.previous_price == 100.0


def test_decision_stable():
    history = [{"sku": "A", "timestamp": "t", "price": 100.0}]
    d = rt.compute_decision(history, 100.0, "A")
    assert d.kind == "stable"


def test_decision_ignores_null_and_bad_prices():
    history = [
        {"sku": "A", "timestamp": "t", "price": None},
        {"sku": "A", "timestamp": "t", "price": "not-a-number"},
    ]
    # all entries unparseable -> prior/lowest unknown -> treated as first record
    d = rt.compute_decision(history, 95.0, "A")
    assert d.kind == "new"
    assert d.previous_price is None


def test_decision_bad_prices_excluded_from_lowest():
    history = [
        {"sku": "A", "timestamp": "t", "price": None},
        {"sku": "A", "timestamp": "t", "price": "not-a-number"},
        {"sku": "A", "timestamp": "t", "price": 200.0},
        {"sku": "A", "timestamp": "t", "price": None},
        {"sku": "A", "timestamp": "t", "price": 150.0},
    ]
    # clean prices are [200,150]; previous=150, lowest=150, current 120 -> record low
    d = rt.compute_decision(history, 120.0, "A")
    assert d.kind == "record_low"
    assert d.previous_price == 150.0
    assert d.lowest_price == 150.0


def test_decision_skips_other_skus_in_record_low():
    history = [
        {"sku": "A", "timestamp": "t", "price": 10.0},
        {"sku": "B", "timestamp": "t", "price": 1.0},  # must not lower A's floor
    ]
    d = rt.compute_decision(history, 5.0, "A")
    assert d.kind == "record_low"
    assert d.lowest_price == 10.0


def test_decision_numbers_as_strings_coerced():
    history = [
        {"sku": "A", "timestamp": "t", "price": "200.00"},
        {"sku": "A", "timestamp": "t", "price": "104.99"},
    ]
    d = rt.compute_decision(history, 99.99, "A")
    assert d.kind == "record_low"
    assert d.previous_price == 104.99
    assert d.lowest_price == 104.99


# ---------------------------------------------------------------------------
# build_alert_message
# ---------------------------------------------------------------------------

def test_alert_record_low_gold():
    d = rt.PriceDecision("record_low", 120.0, 120.0, 100.0)
    title, desc, color = rt.build_alert_message(d, "https://www.jared.com/p/V-A")
    assert title == "🔥 All-Time Record Price Drop!"
    assert color == rt.COLOR_ALL_TIME_LOW
    assert "$100.00" in desc and "$20.00" in desc


def test_alert_drop_green():
    d = rt.PriceDecision("drop", 150.0, 100.0, 140.0)
    title, desc, color = rt.build_alert_message(d, "https://x/j")
    assert title == "📉 Ring Price Dropped!"
    assert color == rt.COLOR_PRICE_DROP
    assert "$10.00" in desc


def test_alert_increase_red():
    d = rt.PriceDecision("increase", 100.0, 100.0, 140.0)
    title, desc, color = rt.build_alert_message(d, "https://x/j")
    assert title == "😱 Ring Price Increase!"
    assert color == rt.COLOR_PRICE_UP


def test_alert_stable_grey():
    d = rt.PriceDecision("stable", 100.0, 100.0, 100.0)
    title, desc, color = rt.build_alert_message(d, "https://x/j")
    assert title == "😶 Ring Price Stable."
    assert color == rt.COLOR_NO_CHANGE


# ---------------------------------------------------------------------------
# extract_price
# ---------------------------------------------------------------------------

def test_extract_price_jsonld_dict_offers():
    html = """
    <html><body>
      <script type="application/ld+json">
        {"@type":"Product","offers":{"price":"1024.99","priceCurrency":"USD"}}
      </script>
    </body></html>
    """
    assert rt.extract_price(html) == 1024.99


def test_extract_price_jsonld_list_offers():
    html = """
    <script type="application/ld+json">
      {"@type":"Product","offers":[{"price":"89.50"},{"price":"99.99"}]}
    </script>
    """
    assert rt.extract_price(html) == 89.50


def test_extract_price_jsonld_multiple_scripts_first_match():
    html = """
    <script type="application/ld+json">{"other":"data"}</script>
    <script type="application/ld+json">{"offers":{"price":"77.25"}}</script>
    """
    assert rt.extract_price(html) == 77.25


def test_extract_price_css_fallback():
    html = '<div class="product-price"><span class="sale-price">$1,299.99</span></div>'
    assert rt.extract_price(html) == 1299.99


def test_extract_price_css_fallback_strips_commas():
    html = '<span class="price">$10,000.50</span>'
    assert rt.extract_price(html) == 10000.50


def test_extract_price_case_insensitive_class():
    html = '<span class="PRICE">$44.44</span>'
    assert rt.extract_price(html) == 44.44


def test_extract_price_none_when_absent():
    assert rt.extract_price("<html><body>no price</body></html>") is None


def test_extract_price_malformed_json_ignored():
    html = (
        '<script type="application/ld+json">{not valid json}</script>'
        '<span class="price">$9.99</span>'
    )
    assert rt.extract_price(html) == 9.99


# ---------------------------------------------------------------------------
# history I/O
# ---------------------------------------------------------------------------

def test_load_history_missing_returns_empty(tmp_path):
    assert rt.load_history(str(tmp_path / "nope.json")) == []


def test_load_history_corrupt_returns_empty(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    assert rt.load_history(str(f)) == []


def test_save_and_load_roundtrip(tmp_path):
    f = tmp_path / "data" / "history.json"  # nested dir to test makedirs
    rt.save_history(str(f), [{"sku": "A", "price": 10.0}])
    assert rt.load_history(str(f)) == [{"sku": "A", "price": 10.0}]


def test_save_history_preserves_unicode(tmp_path):
    f = tmp_path / "h.json"
    rt.save_history(str(f), [{"sku": "V-1", "note": "💍"}])
    raw = f.read_text(encoding="utf-8")
    assert "💍" in raw


# ---------------------------------------------------------------------------
# parse_skus
# ---------------------------------------------------------------------------

def test_parse_skus_csv():
    assert rt.parse_skus("A, B ,C", None) == ["A", "B", "C"]


def test_parse_skus_file(tmp_path):
    f = tmp_path / "skus.txt"
    f.write_text("V-1\n\nV-2\n", encoding="utf-8")
    assert rt.parse_skus(None, str(f)) == ["V-1", "V-2"]


def test_parse_skus_both_and_default_fallback():
    assert rt.parse_skus(None, None) == []
    assert rt.parse_skus("A", None) == ["A"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_build_parser_defaults():
    p = rt.build_parser().parse_args([])
    assert p.models is None
    assert p.no_notify is False
    assert p.delay == rt.DEFAULT_DELAY


def test_parse_args_flags():
    p = rt.build_parser().parse_args(
        ["--sku", "V-1", "--no-notify", "--delay", "5", "--data-file", "x.json"]
    )
    assert p.models == "V-1"
    assert p.no_notify is True
    assert p.delay == 5.0
    assert p.data_file == "x.json"


def test_cli_uses_no_notify_and_data_file(tmp_path):
    """Integration: with no-notify and a temp data file, main() runs without a
    browser by stubbing the fetch; verify the record is written."""
    data_file = str(tmp_path / "hist.json")
    html = """
    <script type="application/ld+json">
      {"offers":{"price":"999.00"}}
    </script>
    """

    async def _fetch(url):
        return html

    async def _run():
        with patch.object(rt, "fetch_page_html", side_effect=_fetch):
            return await rt.main(
                ["--sku", "V-999", "--no-notify", "--data-file", data_file]
            )

    code = asyncio.run(_run())
    assert code == 0
    hist = rt.load_history(data_file)
    assert hist[-1]["sku"] == "V-999"
    assert hist[-1]["price"] == 999.0


def test_cli_default_skus_without_browser_is_guarded(tmp_path):
    """Even when SKUs resolve to the defaults, a fetch that raises is handled
    per-SKU and main() still exits 0."""
    data_file = str(tmp_path / "h.json")

    async def _bad_fetch(url):
        raise RuntimeError("network down")

    async def _run():
        with patch.object(rt, "fetch_page_html", side_effect=_bad_fetch):
            return await rt.main(["--data-file", data_file, "--delay", "0"])

    assert asyncio.run(_run()) == 0
    assert rt.load_history(data_file) == []  # nothing scraped, nothing recorded


def test_send_discord_alert_no_webhook(capsys):
    rt.send_discord_alert("title", "https://x", "desc", 1)
    out = capsys.readouterr().out
    assert "DISCORD_WEBHOOK_URL" in out