"""Integrity Investigator — runs the five deterministic validators once each
and records failures via mark_violation. No LLM is involved in this step."""

from __future__ import annotations

from src.state import TransactionState, ValidationResults
from src.validators import (
    price_validator,
    inventory_validator,
    policy_validator,
    budget_validator,
    intent_alignment_validator,
)


def integrity_investigator(state: TransactionState) -> TransactionState:
    """Run all five validators against the proposed transaction.

    Calls validators.py's functions directly — no reimplementation.
    Updates state.validation_results in place.
    Records any failures via mark_violation.
    """
    # Initialize validation_results if not already set
    if state.validation_results is None:
        from src.state import ValidationResults
        state.validation_results = ValidationResults()
    state.is_violation_detected = False

    # --- PriceValidator ---
    passed, reason = price_validator(state.catalog_record, state.checkout_record)
    state.validation_results.price_validator = passed
    if not passed:
        state.mark_violation(f"PriceValidator: {reason}")

    # --- InventoryValidator ---
    passed, reason = inventory_validator(state.inventory_record, state.checkout_record)
    state.validation_results.inventory_validator = passed
    if not passed:
        state.mark_violation(f"InventoryValidator: {reason}")

    # --- PolicyValidator ---
    passed, reason = policy_validator(state.policy_record, state.checkout_record, state.catalog_record)
    state.validation_results.policy_validator = passed
    if not passed:
        state.mark_violation(f"PolicyValidator: {reason}")

    # --- BudgetValidator ---
    passed, reason = budget_validator(state.max_budget, state.checkout_record)
    state.validation_results.budget_validator = passed
    if not passed:
        state.mark_violation(f"BudgetValidator: {reason}")

    # --- IntentAlignmentValidator ---
    passed, reason = intent_alignment_validator(state.user_intent, state.checkout_record, state.max_budget)
    state.validation_results.intent_alignment_validator = passed
    if not passed:
        state.mark_violation(f"IntentAlignmentValidator: {reason}")

    return state