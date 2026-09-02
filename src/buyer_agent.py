"""Buyer Agent — extracts user intent, searches synthetic catalog, writes proposal."""

from __future__ import annotations

import re
import random

from src.state import (
    TransactionState,
    CatalogRecord,
    InventoryRecord,
    CheckoutRecord,
    PolicyRecord,
    ValidationResults,
)
from src.catalog import (
    _init_catalog,
    _extract_category,
    _extract_max_budget,
    _find_candidate,
)
from synthetic_data import (
    make_inventory_record,
    make_checkout_record,
    make_policy_record,
    PRICE_RANGES,
)


def buyer_agent(state: TransactionState) -> TransactionState:
    """Select a product candidate and write the proposal into state."""
    user_intent = state.user_intent
    max_budget = _extract_max_budget(user_intent, state.max_budget)
    state.max_budget = max_budget
    category = _extract_category(user_intent)

    # Search for a candidate, excluding products already tried in this run
    tried = set(state.tried_product_ids) if state.tried_product_ids else set()

    candidate = _find_candidate(max_budget, category, tried)

    if candidate is None:
        # No new candidate found — mark failure
        state.mark_violation("Buyer Agent: No matching product found in catalog")
        return state

    # Mark this product as tried
    state.tried_product_ids.append(candidate.product_id)

    # Generate matching records
    # Force stockout for the first candidate if flag is set (debug-only)
    if state.force_stockout_first:
        inventory = make_inventory_record(candidate.product_id, available=0)
    else:
        inventory = make_inventory_record(candidate.product_id)
    checkout = make_checkout_record(
        candidate.product_id, candidate.price, quantity=1
    )
    policy = make_policy_record(candidate.product_id, candidate.category)

    # Write proposal into state
    state.catalog_record = candidate
    state.inventory_record = inventory
    state.checkout_record = checkout
    state.policy_record = policy

    # Append audit trail entry
    audit_entry = (
        f"Buyer Agent: picked '{candidate.name}' "
        f"(category={candidate.category}, price=₹{candidate.price:.2f}, "
        f"budget=₹{max_budget:.2f}) for intent: '{user_intent}'"
    )
    state.append_audit(audit_entry)

    return state