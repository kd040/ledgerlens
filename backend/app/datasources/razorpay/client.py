"""Minimal server-side Razorpay REST adapter.

Deliberately built on urllib.request (stdlib) rather than adding httpx/
requests -- this is one documented external API, called synchronously,
at Test Mode volumes. Credentials never leave this module: the
Authorization header and RAZORPAY_KEY_SECRET are never logged or
included in a raised exception's message.
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = "https://api.razorpay.com/v1"
DEFAULT_TIMEOUT_SECONDS = 15.0


class RazorpayConfigError(RuntimeError):
    """Raised when RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not configured."""


class RazorpayApiError(RuntimeError):
    """Raised for a non-2xx response or a network failure. Never carries
    the request's credentials -- only the HTTP status and Razorpay's own
    (non-secret) error description."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Razorpay API error ({status}): {message}")
        self.status = status


class RazorpayClient:
    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET")

        if not self.key_id or not self.key_secret:
            raise RazorpayConfigError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be configured"
            )

        self.timeout = timeout

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.key_id}:{self.key_secret}".encode()
        ).decode()
        return f"Basic {token}"

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        url = f"{BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"

        request = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            logger.warning("Razorpay API error %s for %s", error.code, path)
            try:
                detail = json.loads(body).get("error", {}).get("description", body)
            except json.JSONDecodeError:
                detail = body
            raise RazorpayApiError(error.code, detail) from None
        except urllib.error.URLError as error:
            logger.warning("Razorpay API unreachable for %s: %s", path, error.reason)
            raise RazorpayApiError(0, f"Could not reach Razorpay API: {error.reason}") from None
        except TimeoutError:
            logger.warning("Razorpay API timed out for %s", path)
            raise RazorpayApiError(0, "Razorpay API request timed out") from None

    def list_payments(
        self, *, from_ts: int, to_ts: int, count: int = 100, skip: int = 0
    ) -> dict[str, Any]:
        """GET /payments -- count is capped at 100 per Razorpay's documented
        pagination convention."""
        return self._get(
            "/payments",
            {"from": from_ts, "to": to_ts, "count": min(count, 100), "skip": skip},
        )

    def list_settlement_recon(
        self, *, year: int, month: int, day: int | None = None,
        count: int = 1000, skip: int = 0,
    ) -> dict[str, Any]:
        """GET /settlements/recon/combined -- day-granular, not a from/to
        range (Razorpay's own API shape for this endpoint); count max 1000
        per Razorpay's documented range for this specific endpoint."""
        params: dict[str, Any] = {
            "year": year,
            "month": f"{month:02d}",
            "count": min(count, 1000),
            "skip": skip,
        }
        if day is not None:
            params["day"] = f"{day:02d}"
        return self._get("/settlements/recon/combined", params)
