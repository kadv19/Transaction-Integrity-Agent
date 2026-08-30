"""
Five Deterministic Validators — Pure Functions, No LLM, No Network.

Each validator:
- Takes only the state fields it needs (explicit, testable)
- Returns (passed: bool, reason: str | None)
- No side effects, no mutations, no hidden dependencies
- Reason string is human-readable and goes straight to audit_trail

CORE DESIGN LAW: Only these functions (and deterministic checkout) decide PASS/FAIL.
"""

from __future__ import annotations

from state import (
    CatalogRecord,
    CheckoutRecord,
    InventoryRecord,
    PolicyRecord,
    TransactionState,
)


# ---------------------------------------------------------------------------
# 1. PriceValidator
# ---------------------------------------------------------------------------
def price_validator(
    catalog_record: CatalogRecord | None,
    checkout_record: CheckoutRecord | None,
) -> tuple[bool, str | None]:
    """
    Verify catalog_price == checkout unit_price (within rounding tolerance).

    WHY: Prevents bait-and-switch where catalog shows one price but checkout
    charges another. This is the most common merchant integrity violation.
    """
    if not catalog_record or not checkout_record:
        return False, "Missing catalog or checkout record for price comparison"

    catalog_price = round(catalog_record.price, 2)
    checkout_price = round(checkout_record.unit_price, 2)

    if catalog_price != checkout_price:
        return (
            False,
            f"Price mismatch: catalog ₹{catalog_price:.2f} != checkout ₹{checkout_price:.2f}",
        )

    return True, None


# ---------------------------------------------------------------------------
# 2. InventoryValidator
# ---------------------------------------------------------------------------
def inventory_validator(
    inventory_record: InventoryRecord | None,
    checkout_record: CheckoutRecord | None,
) -> tuple[bool, str | None]:
    """
    Verify requested_quantity <= verified_stock (available - reserved).

    WHY: Prevents selling phantom stock. Inventory system is source of truth;
    checkout quantity must not exceed what's actually pickable.
    """
    if not inventory_record or not checkout_record:
        return False, "Missing inventory or checkout record for stock check"

    available = inventory_record.available_quantity - inventory_record.reserved_quantity
    requested = checkout_record.quantity

    if requested > available:
        return (
            False,
            f"Insufficient stock: requested {requested}, available {available} "
            f"(total {inventory_record.available_quantity} - reserved {inventory_record.reserved_quantity})",
        )

    return True, None


# ---------------------------------------------------------------------------
# 3. PolicyValidator
# ---------------------------------------------------------------------------
def policy_validator(
    policy_record: PolicyRecord | None,
    checkout_record: CheckoutRecord | None,
    catalog_record: CatalogRecord | None = None,
) -> tuple[bool, str | None]:
    """
    Verify requested_action satisfies merchant policy including fine print.

    WHY: Headline policies ("free returns") often have fine-print exclusions
    ("except electronics", "except sale items"). This validator checks both.
    """
    if not policy_record or not checkout_record:
        return False, "Missing policy or checkout record for policy check"

    # Max quantity per order
    if policy_record.max_quantity_per_order is not None:
        if checkout_record.quantity > policy_record.max_quantity_per_order:
            return (
                False,
                f"Quantity {checkout_record.quantity} exceeds policy limit "
                f"of {policy_record.max_quantity_per_order}",
            )

    # Fine-print exclusions (human-readable conditions that may override headline)
    if policy_record.fine_print_exclusions:
        product_category = catalog_record.category if catalog_record else "unknown"
        for exclusion in policy_record.fine_print_exclusions:
            # Simple keyword match for fine-print rules
            if exclusion.lower() in product_category.lower():
                return (
                    False,
                    f"Fine-print exclusion applies: '{exclusion}' matches product category '{product_category}'",
                )

    return True, None


# ---------------------------------------------------------------------------
# 4. BudgetValidator
# ---------------------------------------------------------------------------
def budget_validator(
    max_budget: float,
    checkout_record: CheckoutRecord | None,
) -> tuple[bool, str | None]:
    """
    Verify final_amount <= user_max_budget.

    WHY: User sets a hard ceiling. Even if product is valid, we must not
    authorize spend beyond what the user explicitly approved.
    """
    if not checkout_record:
        return False, "Missing checkout record for budget check"

    final_amount = round(checkout_record.final_amount, 2)
    budget = round(max_budget, 2)

    if final_amount > budget:
        return (
            False,
            f"Budget exceeded: final amount ₹{final_amount:.2f} > user max budget ₹{budget:.2f}",
        )

    return True, None


# ---------------------------------------------------------------------------
# 5. AuthorizationValidator
# ---------------------------------------------------------------------------
def authorization_validator(
    user_intent: str,
    checkout_record: CheckoutRecord | None,
    max_budget: float,
) -> tuple[bool, str | None]:
    """
    Verify transaction aligns with user's stated spending authorization.

    WHY: User intent ("buy one laptop under 50k") may not match what the
    buyer agent proposed ("gaming laptop at 80k"). This catches intent drift.
    """
    if not checkout_record:
        return False, "Missing checkout record for authorization check"

    final_amount = round(checkout_record.final_amount, 2)

    # Parse user intent for explicit limits (simplified deterministic parse)
    # In production this would be more sophisticated; for hackathon we check:
    # - If user mentions a specific max, enforce it (redundant with budget_validator but independent)
    # - If user intent implies single item, reject bulk quantities
    intent_lower = user_intent.lower()

    # Check for "one", "single", "a", "an" as quantity indicators (not in product names)
    # Match patterns like "buy one", "purchase a", "get single", "order an"
    import re
    single_qty_patterns = [
        r"\b(?:buy|purchase|get|order)\s+(?:one|single|a|an)\b",
        r"\b(?:one|single)\s+item\b",
        r"\bjust\s+(?:one|a|an)\b",
    ]
    implies_single = any(re.search(p, intent_lower) for p in single_qty_patterns)
    if implies_single and checkout_record.quantity > 1:
        return (
            False,
            f"User intent implies single item but checkout has quantity {checkout_record.quantity}",
        )

    # Check for explicit budget mentions in intent (e.g., "under 50000", "below 50k")
    budget_matches = re.findall(r"(?:under|below|max|maximum|upto|up to)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", intent_lower)
    for match in budget_matches:
        mentioned_budget = float(match.replace(",", ""))
        if final_amount > mentioned_budget:
            return (
                False,
                f"User intent mentions max ₹{mentioned_budget:.2f} but final amount is ₹{final_amount:.2f}",
            )

    return True, None


# ---------------------------------------------------------------------------
# Orchestrator: run all validators on a TransactionState
# ---------------------------------------------------------------------------
def run_all_validators(state: TransactionState) -> TransactionState:
    """
    Execute all five validators, update state.validation_results and audit_trail.

    Returns mutated state (validators are pure; orchestrator applies results).
    """
    # Initialize validation_results if not already set
    if state.validation_results is None:
        from state import ValidationResults
        state.validation_results = ValidationResults()

    # PriceValidator
    passed, reason = price_validator(state.catalog_record, state.checkout_record)
    state.validation_results.price_validator = passed
    if not passed:
        state.mark_violation(f"PriceValidator: {reason}")

    # InventoryValidator
    passed, reason = inventory_validator(state.inventory_record, state.checkout_record)
    state.validation_results.inventory_validator = passed
    if not passed:
        state.mark_violation(f"InventoryValidator: {reason}")

    # PolicyValidator
    passed, reason = policy_validator(state.policy_record, state.checkout_record, state.catalog_record)
    state.validation_results.policy_validator = passed
    if not passed:
        state.mark_violation(f"PolicyValidator: {reason}")

    # BudgetValidator
    passed, reason = budget_validator(state.max_budget, state.checkout_record)
    state.validation_results.budget_validator = passed
    if not passed:
        state.mark_violation(f"BudgetValidator: {reason}")

    # AuthorizationValidator
    passed, reason = authorization_validator(state.user_intent, state.checkout_record, state.max_budget)
    state.validation_results.authorization_validator = passed
    if not passed:
        state.mark_violation(f"AuthorizationValidator: {reason}")

    return state