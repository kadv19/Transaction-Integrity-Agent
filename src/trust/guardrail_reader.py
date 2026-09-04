"""Guardrail reader — read-only view of active merchant controls.

No mutations. Values are canonical config that mirrors the deterministic
validators and checkout logic. This is the single source for the
/trust/guardrails endpoint.
"""

from __future__ import annotations

# Canonical guardrail values — kept in one place so dashboard and validators
# can never drift. Update here if merchant policy changes.
GUARDRAIL_CONFIG: dict = {
    "active_guardrails": {
        "max_discount_percentage": 30,
        "daily_transaction_limit": 100000,
        "max_budget_cap": 8000,
        "stockout_handling": "fallback",
    },
    "merchant_controls": ["max_discount", "budget_cap", "daily_limit"],
}

# Human-readable descriptions for UI tooltips / docs
GUARDRAIL_DESCRIPTIONS: dict[str, str] = {
    "max_discount_percentage": "Maximum discount allowed at checkout (veto if exceeded).",
    "daily_transaction_limit": "Maximum total INR per day across all transactions.",
    "max_budget_cap": "Upper budget clamp shown in Curator bundling demo (₹8000).",
    "stockout_handling": "Recovery strategy when first candidate is out of stock.",
}


def get_guardrail_config() -> dict:
    """Return a detached copy of the current guardrail configuration.

    Read-only: caller may mutate the returned dict without affecting canonical config.
    """
    import copy

    return copy.deepcopy(GUARDRAIL_CONFIG)


def get_guardrail_descriptions() -> dict[str, str]:
    """Return descriptions for each guardrail key."""
    import copy

    return copy.deepcopy(GUARDRAIL_DESCRIPTIONS)
