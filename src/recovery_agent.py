"""Recovery Agent — on FAIL, increments loop counter and searches for an
alternative product, excluding every product already tried in this run."""

from __future__ import annotations

import re

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


def recovery_agent(state: TransactionState) -> TransactionState:
    """Handle a FAIL outcome from integrity_investigator.

    1. First check state.increment_loop() — if it returns False (loop_count
       has reached MAX_LOOPS), immediately call state.set_final_fail() with a
       clear reason and stop; do not search for another product.
    2. If increment_loop() returns True, search the catalog for an alternative
       product satisfying the original constraints, excluding every product
       already tried in this run, and write the new proposal into state the
       same way buyer_agent.py does.
    """
    # Step 1: check loop control INSIDE recovery_agent before searching
    # increment_loop() increments loop_count and returns True if loops remain
    loops_remaining = state.increment_loop()

    if not loops_remaining:
        # Loop count has reached MAX_LOOPS — stop immediately
        reason = (
            f"Maximum recovery loops ({state.MAX_LOOPS}) exhausted; "
            f"no valid product found after {state.loop_count} attempts. "
            f"User intent: '{state.user_intent}'"
        )
        state.set_final_fail(reason)
        return state

    # Step 2: search for an alternative product
    user_intent = state.user_intent
    max_budget = state.max_budget
    category = _extract_category(user_intent)

    # Exclude products already tried in this run, via state field
    tried_ids = set(state.tried_product_ids) if state.tried_product_ids else set()

    # Find a candidate excluding tried products
    candidate = _find_candidate(max_budget, category, tried_ids if tried_ids else None)

    if candidate is None:
        # No alternative product found — exhausted this category/budget combo
        reason = (
            f"No alternative product found in category '{category}' within "
            f"budget ₹{max_budget:.2f} after {state.loop_count} recovery attempts. "
            f"User intent: '{user_intent}'"
        )
        state.set_final_fail(reason)
        return state

    # Mark this product as tried
    state.tried_product_ids.append(candidate.product_id)

    # Generate matching records (same way buyer_agent does)
    inventory = make_inventory_record(candidate.product_id)
    checkout = make_checkout_record(
        candidate.product_id, candidate.price, quantity=1
    )
    policy = make_policy_record(candidate.product_id, candidate.category)

    # Write new proposal into state
    state.catalog_record = candidate
    state.inventory_record = inventory
    state.checkout_record = checkout
    state.policy_record = policy

    # Append audit trail entry describing what was picked and why
    state.append_audit(
        f"Recovery Agent: found alternative '{candidate.name}' "
        f"(category={candidate.category}, price=₹{candidate.price:.2f}, "
        f"attempt #{state.loop_count}/{state.MAX_LOOPS}) for intent: '{user_intent}'"
    )

    return state