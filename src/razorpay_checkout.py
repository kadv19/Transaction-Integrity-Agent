"""Deterministic checkout generation — no LLM, validated state only."""

from __future__ import annotations

from src.state import TransactionState
from src.razorpay_client import RazorpayClient


def generate_checkout(
    state: TransactionState, razorpay_client: RazorpayClient
) -> TransactionState:
    """Deterministically compute checkout amount and create Razorpay payment link.

    Rules (strict):
    - Amount is derived ONLY from state.checkout_record.final_amount.
      Never from catalog price, intermediate candidate, or any earlier pipeline value.
    - Conversion: amount_paise = round(final_amount * 100). Get this right — wrong-by-100x
      is an embarrassing live-demo failure.
    - Description is built from the product name (state.catalog_record.name if available).
    - The REAL id/short_url returned by the client is logged into audit_trail.
      Never fabricate or hardcode a link string here.
    - On PASS state only; if checkout_record is missing we FAIL loudly.

    Args:
        state: TransactionState that has already passed all validators (final_decision pending,
               but caller should only invoke after PASS validation).
        razorpay_client: Injected RazorpayClient (Live or Stub). Caller chooses.

    Returns:
        Mutated state with final_decision=PASS and checkout_link=short_url, or FAIL if error.
    """
    # Guard: must have checkout_record with final_amount
    if state.checkout_record is None:
        # Ensure validator state allows FAIL (CORE DESIGN LAW: FAIL requires at least one validator False)
        if state.validation_results is None:
            from src.state import ValidationResults

            state.validation_results = ValidationResults()
        # Force a validator to False to permit FAIL
        state.validation_results.budget_validator = False
        state.mark_violation("generate_checkout: missing checkout_record — cannot create payment link")
        state.set_final_fail("Missing checkout_record at checkout step")
        return state

    final_amount = state.checkout_record.final_amount
    if final_amount is None:
        if state.validation_results is None:
            from src.state import ValidationResults

            state.validation_results = ValidationResults()
        state.validation_results.budget_validator = False
        state.mark_violation("generate_checkout: checkout_record.final_amount is None")
        state.set_final_fail("Missing final_amount at checkout step")
        return state

    # Deterministic conversion: INR -> paise
    amount_paise = round(final_amount * 100)

    if amount_paise <= 0:
        if state.validation_results is None:
            from src.state import ValidationResults

            state.validation_results = ValidationResults()
        state.validation_results.budget_validator = False
        state.mark_violation(f"generate_checkout: computed amount_paise={amount_paise} is not positive (final_amount={final_amount})")
        state.set_final_fail(f"Invalid checkout amount: {final_amount}")
        return state

    # Description from product name (fallback to generic)
    if state.catalog_record is not None and state.catalog_record.name:
        description = f"Payment for {state.catalog_record.name}"
    else:
        description = f"Payment for order {state.checkout_record.product_id}"

    # Log intent before calling
    state.append_audit(
        f"generate_checkout: creating payment link for ₹{final_amount:.2f} "
        f"({amount_paise} paise) — {description}"
    )

    # Call injected client — real or stub, no branching here
    try:
        result = razorpay_client.create_payment_link(
            amount_paise=amount_paise, description=description
        )
    except Exception as e:
        if state.validation_results is None:
            from src.state import ValidationResults

            state.validation_results = ValidationResults()
        state.validation_results.budget_validator = False
        state.mark_violation(f"generate_checkout: Razorpay client error — {e}")
        state.set_final_fail(f"Payment link creation failed: {e}")
        return state

    # Validate returned shape
    link_id = result.get("id")
    short_url = result.get("short_url")

    if not link_id or not short_url:
        if state.validation_results is None:
            from src.state import ValidationResults

            state.validation_results = ValidationResults()
        state.validation_results.budget_validator = False
        state.mark_violation(
            f"generate_checkout: Razorpay client returned incomplete result {result}"
        )
        state.set_final_fail("Payment link creation returned incomplete data")
        return state

    # Log REAL values returned by client
    state.append_audit(
        f"generate_checkout: Razorpay link created — id={link_id} short_url={short_url}"
    )

    # Set final PASS with REAL short_url
    state.set_final_pass(short_url)

    return state
