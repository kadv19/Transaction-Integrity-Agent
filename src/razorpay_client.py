"""RazorpayClient interface with Live and Stub implementations.

Generate checkout must accept a client as dependency rather than constructing one
internally, so callers choose which implementation to use.
"""

from __future__ import annotations

import os
import abc
import uuid


class RazorpayClient(abc.ABC):
    """Abstract interface for creating Razorpay payment links."""

    @abc.abstractmethod
    def create_payment_link(self, amount_paise: int, description: str) -> dict:
        """Create a payment link.

        Args:
            amount_paise: Amount in paise (smallest currency unit, e.g. 50000 = Rs 500).
            description: Human-readable description (typically product name).

        Returns:
            Dict with at minimum {"id": ..., "short_url": ...}.
        """
        ...


class LiveRazorpayClient(RazorpayClient):
    """Calls the real Razorpay test-mode API via the razorpay Python SDK.

    Loads RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET from environment variables
    (via python-dotenv reading .env). Fails loudly if either is missing or empty.
    """

    def __init__(self) -> None:
        # Load .env if present — python-dotenv is optional but required per spec
        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv()
        except ImportError:
            pass  # dotenv not installed — still try env vars directly

        key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")

        if not key_id or not key_id.strip():
            raise ValueError(
                "RAZORPAY_KEY_ID is missing or empty. "
                "Set it in your .env file or environment variables. "
                "Get test keys from https://dashboard.razorpay.com/app/keys"
            )
        if not key_secret or not key_secret.strip():
            raise ValueError(
                "RAZORPAY_KEY_SECRET is missing or empty. "
                "Set it in your .env file or environment variables. "
                "Get test keys from https://dashboard.razorpay.com/app/keys"
            )

        self.key_id = key_id.strip()
        self.key_secret = key_secret.strip()

        # Lazily import razorpay SDK
        try:
            import razorpay  # type: ignore
        except ImportError as e:
            raise ImportError(
                "razorpay package is required for LiveRazorpayClient. "
                "Install with: pip install razorpay"
            ) from e

        self._client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def create_payment_link(self, amount_paise: int, description: str) -> dict:
        """Create a real Razorpay payment link via API."""
        if amount_paise <= 0:
            raise ValueError(f"amount_paise must be > 0, got {amount_paise}")

        # Razorpay payment_link payload
        # See: https://razorpay.com/docs/api/payment-links/
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "customer": {
                "name": "Test Customer",
                "email": "test@example.com",
                "contact": "+919999999999",
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"description": description},
            "callback_url": "https://example.com/callback",
            "callback_method": "get",
        }

        result = self._client.payment_link.create(payload)

        # Razorpay returns dict with 'id' and 'short_url' among others
        # Normalize to guarantee those keys exist
        if "id" not in result or "short_url" not in result:
            raise RuntimeError(
                f"Unexpected Razorpay response missing id/short_url: {result}"
            )

        return {"id": result["id"], "short_url": result["short_url"], "_raw": result}


class StubRazorpayClient(RazorpayClient):
    """In-memory stub — records calls, returns fake but realistic dict, no network."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create_payment_link(self, amount_paise: int, description: str) -> dict:
        """Record the call and return a fake payment link."""
        call_record = {"amount_paise": amount_paise, "description": description}
        self.calls.append(call_record)

        fake_id = f"stub_plink_{uuid.uuid4().hex[:12]}"
        fake_url = f"https://stub.example.com/plink/{uuid.uuid4().hex[:8]}"

        return {"id": fake_id, "short_url": fake_url}

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()
