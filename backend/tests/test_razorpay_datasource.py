"""Tests for the Razorpay data source: normalization, pagination, date
filtering, source dispatch, and error handling. All mocked/pure -- no
real Razorpay credentials or network access required.

Run directly: python backend/tests/test_razorpay_datasource.py
"""

import os
import sys
import urllib.error
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasources import SOURCES
from app.datasources.razorpay.client import (
    RazorpayApiError,
    RazorpayClient,
    RazorpayConfigError,
)
from app.datasources.razorpay.normalize import (
    normalize_payment,
    normalize_settlement_recon_line,
)
from app.datasources.razorpay.source import _ist_days_in_range, _paginate


# --------------------------------------------------
# Normalization
# --------------------------------------------------

RAW_PAYMENT = {
    "id": "pay_DEXrnipqTmWVGE",
    "entity": "payment",
    "amount": 100000,
    "currency": "INR",
    "status": "captured",
    "method": "card",
    "created_at": 1567692556,
}

RAW_RECON_PAYMENT_LINE = {
    "entity_id": "pay_DEXrnipqTmWVGE",
    "type": "payment",
    "debit": 0,
    "credit": 97100,
    "amount": 100000,
    "currency": "INR",
    "fee": 2900,
    "tax": 0,
    "settled": True,
    "created_at": 1567692556,
    "settled_at": 1568176960,
    "settlement_id": "setl_DGlQ1Rj8os78Ec",
    "payment_id": None,
    "settlement_utr": "1568176960vxp0rj",
}

RAW_RECON_REFUND_LINE = {
    "entity_id": "rfnd_DGRcGzZSLyEdg1",
    "type": "refund",
    "debit": 242500,
    "credit": 0,
    "settlement_id": "setl_DGlQ1Rj8os78Ec",
    "payment_id": "pay_DEXq1pACSqFxtS",
}


def test_normalize_payment_converts_paise_to_rupees():
    result = normalize_payment(RAW_PAYMENT)
    assert result["external_payment_id"] == "pay_DEXrnipqTmWVGE"
    assert result["amount"] == Decimal("1000.00")
    assert result["status"] == "captured"
    assert result["method"] == "card"


def test_normalize_settlement_recon_line_uses_entity_id_not_payment_id():
    """Regression guard for the exact bug this checkpoint was built to
    avoid: payment_id is null on payment-type recon lines, the payment's
    own id is entity_id."""
    result = normalize_settlement_recon_line(RAW_RECON_PAYMENT_LINE)
    assert result is not None
    assert result["payment_reference"] == "pay_DEXrnipqTmWVGE"
    assert result["external_settlement_id"] == "setl_DGlQ1Rj8os78Ec:pay_DEXrnipqTmWVGE"
    assert result["settlement_amount"] == Decimal("971.00")
    assert result["fee_amount"] == Decimal("29.00")
    assert result["tax_amount"] == Decimal("0")
    assert result["status"] == "SETTLED"
    assert result["utr"] == "1568176960vxp0rj"


def test_normalize_settlement_recon_line_skips_non_payment_types():
    assert normalize_settlement_recon_line(RAW_RECON_REFUND_LINE) is None


def test_normalize_settlement_credit_equals_amount_minus_fee_minus_tax():
    """Verifies the documented semantics: credit is net of fee/tax, not
    the gross amount."""
    result = normalize_settlement_recon_line(RAW_RECON_PAYMENT_LINE)
    gross = Decimal(RAW_RECON_PAYMENT_LINE["amount"]) / 100
    fee = Decimal(RAW_RECON_PAYMENT_LINE["fee"]) / 100
    tax = Decimal(RAW_RECON_PAYMENT_LINE["tax"]) / 100
    assert result["settlement_amount"] == gross - fee - tax


# --------------------------------------------------
# Pagination
# --------------------------------------------------

def test_paginate_stops_on_short_page():
    pages = [
        {"items": [{"n": 1}, {"n": 2}]},
        {"items": [{"n": 3}, {"n": 4}]},
        {"items": [{"n": 5}]},  # short page -- fewer than page_size, stop here
    ]
    calls = []

    def fetch_page(count, skip):
        calls.append(skip)
        return pages[len(calls) - 1]

    result = _paginate(fetch_page, page_size=2)
    assert [item["n"] for item in result] == [1, 2, 3, 4, 5]
    assert calls == [0, 2, 4]


def test_paginate_single_short_page_makes_one_call():
    def fetch_page(count, skip):
        return {"items": [{"n": 1}]}

    result = _paginate(fetch_page, page_size=100)
    assert len(result) == 1


# --------------------------------------------------
# Date/range handling
# --------------------------------------------------

def test_ist_days_in_range_single_day():
    start = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc)
    days = _ist_days_in_range(start, end)
    assert days == [date(2026, 8, 25)]


def test_ist_days_in_range_spans_multiple_days():
    start = datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)  # 25th 01:30 IST
    end = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)  # 27th 01:30 IST
    days = _ist_days_in_range(start, end)
    assert days == [date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)]


# --------------------------------------------------
# Authentication / configuration
# --------------------------------------------------

def test_client_raises_without_credentials():
    saved = {
        key: os.environ.pop(key, None)
        for key in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET")
    }
    try:
        try:
            RazorpayClient()
            raise AssertionError("expected RazorpayConfigError")
        except RazorpayConfigError:
            pass
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_client_accepts_explicit_credentials():
    client = RazorpayClient(key_id="rzp_test_x", key_secret="secret")
    assert client.key_id == "rzp_test_x"


def test_auth_header_is_basic_base64():
    client = RazorpayClient(key_id="abc", key_secret="def")
    header = client._auth_header()
    assert header.startswith("Basic ")
    import base64
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
    assert decoded == "abc:def"


# --------------------------------------------------
# API error handling
# --------------------------------------------------

def test_http_error_becomes_razorpay_api_error_without_leaking_secret():
    client = RazorpayClient(key_id="abc", key_secret="super-secret-value")

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("url", 401, "Unauthorized", {}, None)

        def read(self):
            return b'{"error": {"description": "Authentication failed"}}'

    with patch("urllib.request.urlopen", side_effect=FakeHTTPError()):
        try:
            client.list_payments(from_ts=0, to_ts=1)
            raise AssertionError("expected RazorpayApiError")
        except RazorpayApiError as error:
            assert error.status == 401
            assert "Authentication failed" in str(error)
            assert "super-secret-value" not in str(error)


def test_url_error_becomes_razorpay_api_error():
    client = RazorpayClient(key_id="abc", key_secret="def")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("timed out"),
    ):
        try:
            client.list_payments(from_ts=0, to_ts=1)
            raise AssertionError("expected RazorpayApiError")
        except RazorpayApiError as error:
            assert "timed out" in str(error)


# --------------------------------------------------
# Source abstraction
# --------------------------------------------------

def test_normalize_payment_retains_the_real_created_at_instant():
    """The transaction detail UI shows a Razorpay payment's actual
    date/time, so normalization must carry the provider's own
    created_at through as a real tz-aware instant -- never dropped, and
    never replaced with an ingestion time."""
    result = normalize_payment(RAW_PAYMENT)

    assert result["created_at"] == datetime(
        2019, 9, 5, 14, 9, 16, tzinfo=timezone.utc
    )
    assert result["created_at"] == datetime.fromtimestamp(
        RAW_PAYMENT["created_at"], tz=timezone.utc
    )
    assert result["created_at"].tzinfo is not None
    assert result["created_at"] != datetime.now(timezone.utc)


def test_normalize_payment_preserves_a_non_captured_status():
    """A payment the provider never captured must stay identifiable as
    such after normalization -- the reconciliation engine relies on this
    to avoid raising a false EX02 against it."""
    raw = {**RAW_PAYMENT, "status": "created"}
    assert normalize_payment(raw)["status"] == "created"


def test_razorpay_source_is_identifiable_in_the_registry():
    """The UI names a row's origin from the source key the run was made
    with, so that key has to be a stable, registered identifier."""
    assert "razorpay_test" in SOURCES
    assert callable(SOURCES["razorpay_test"])
    assert SOURCES["razorpay_test"] is not SOURCES["demo"]


def test_sources_registry_has_demo_and_razorpay_test():
    assert set(SOURCES) == {"demo", "razorpay_test"}


if __name__ == "__main__":
    tests = [
        obj for name, obj in list(globals().items()) if name.startswith("test_")
    ]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
