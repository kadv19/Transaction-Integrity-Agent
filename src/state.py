"""TransactionState: the single source of truth for a transaction's lifecycle.

This model enforces the CORE DESIGN LAW: only deterministic validators may
decide PASS/FAIL. The state captures everything needed for an auditable,
replayable decision — no hidden context, no LLM-influenced flags.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self


class CatalogRecord(BaseModel):
    """Merchant's source-of-truth product catalog entry."""
    product_id: str
    name: str
    price: float  # in INR, authoritative catalog price
    currency: str = "INR"
    description: str | None = None
    category: str | None = None


class InventoryRecord(BaseModel):
    """Verified stock level from inventory system."""
    product_id: str
    available_quantity: int
    reserved_quantity: int = 0
    warehouse_id: str | None = None


class CheckoutRecord(BaseModel):
    """Price and totals presented at checkout (what user sees)."""
    product_id: str
    unit_price: float  # price shown at checkout
    quantity: int
    subtotal: float
    tax: float = 0.0
    shipping: float = 0.0
    discount: float = 0.0
    final_amount: float


class PolicyRecord(BaseModel):
    """Merchant policy including fine-print exclusions."""
    product_id: str
    returnable: bool = True
    cancellable: bool = True
    max_quantity_per_order: int | None = None
    excluded_payment_methods: list[str] = Field(default_factory=list)
    excluded_regions: list[str] = Field(default_factory=list)
    fine_print_exclusions: list[str] = Field(default_factory=list)
    # Fine print: human-readable conditions that may contradict headline policy
    fine_print: str | None = None


class ValidationResults(BaseModel):
    """Results from the five deterministic validators."""
    price_validator: bool = False
    inventory_validator: bool = False
    policy_validator: bool = False
    budget_validator: bool = False
    intent_alignment_validator: bool = False


class TransactionState(BaseModel):
    """
    Immutable-ish state object for a single transaction attempt.

    Extra fields forbidden to prevent silent data corruption.
    validate_assignment=True catches mutations that violate invariants.
    """
    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
        "frozen": False,  # allow audit_trail append via reducer pattern
    }

    # --- Input / Context ---
    user_intent: str
    max_budget: float  # user's stated maximum spend (INR)
    min_budget: float = 0.0  # user's stated minimum spend (INR), 0 = no minimum
    proposed_product: CatalogRecord | None = None

    # --- Fetched Records (deterministic lookups) ---
    catalog_record: CatalogRecord | None = None
    inventory_record: InventoryRecord | None = None
    checkout_record: CheckoutRecord | None = None
    policy_record: PolicyRecord | None = None

    # --- Validation Outcomes ---
    validation_results: ValidationResults | None = None
    audit_trail: list[str] = Field(default_factory=list)
    is_violation_detected: bool = False

    # --- Loop Control (Recovery Agent) ---
    loop_count: int = 0
    MAX_LOOPS: int = 3

    # --- Track products already tried in this run ---
    tried_product_ids: list[str] = Field(default_factory=list)

    # --- Debug flags (test-only) ---
    force_stockout_first: bool = False

    # --- Final Decision ---
    final_decision: Literal["PASS", "FAIL", "PENDING"] = "PENDING"
    checkout_link: str | None = None
    failure_reason: str | None = None

    # --- Field Validators (enforce CORE DESIGN LAW) ---

    @field_validator("validation_results")
    @classmethod
    def _coerce_validation_results(cls, v):
        """Accept dict or ValidationResults, normalize to model."""
        if isinstance(v, dict):
            return ValidationResults(**v)
        return v

    @model_validator(mode="after")
    def _enforce_core_design_law(self) -> Self:
        """
        CORE DESIGN LAW enforcement:
        - If any validator fails, is_violation_detected MUST be True.
        - If all validators pass, is_violation_detected MUST be False.
        - final_decision PASS only if all validators pass AND no violation.
        Only enforced when final_decision is set (not PENDING).
        """
        # Only enforce consistency when a final decision has been made
        if self.final_decision == "PENDING":
            return self

        if self.validation_results is None:
            raise ValueError("validation_results must be set before final decision")

        vr = self.validation_results
        all_pass = all(
            [
                vr.price_validator,
                vr.inventory_validator,
                vr.policy_validator,
                vr.budget_validator,
                vr.intent_alignment_validator,
            ]
        )

        # Consistency check: violation flag must match validator results
        if all_pass and self.is_violation_detected:
            raise ValueError(
                "is_violation_detected=True but all validators passed — "
                "CORE DESIGN LAW violated: violation flag must be False when all pass"
            )
        if not all_pass and not self.is_violation_detected:
            raise ValueError(
                "is_violation_detected=False but at least one validator failed — "
                "CORE DESIGN LAW violated: violation flag must be True when any fail"
            )

        # final_decision consistency
        if self.final_decision == "PASS" and not all_pass:
            raise ValueError(
                "final_decision=PASS but not all validators passed — "
                "only deterministic code may set PASS"
            )
        if self.final_decision == "FAIL" and all_pass:
            raise ValueError(
                "final_decision=FAIL but all validators passed — "
                "contradicts deterministic outcome"
            )

        return self

    def append_audit(self, entry: str) -> None:
        """Append a human-readable reason to the audit trail (append-only)."""
        self.audit_trail.append(entry)

    def mark_violation(self, reason: str) -> None:
        """Mark violation detected and record reason."""
        self.is_violation_detected = True
        self.append_audit(f"VIOLATION: {reason}")

    def set_final_pass(self, checkout_link: str) -> None:
        """Deterministic PASS — only called after all validators return True."""
        self.final_decision = "PASS"
        self.checkout_link = checkout_link
        self.append_audit("DECISION: PASS — all validators passed, checkout link generated")

    def set_final_fail(self, reason: str) -> None:
        """Deterministic FAIL — called when validators fail or loops exhausted."""
        self.final_decision = "FAIL"
        self.failure_reason = reason
        self.append_audit(f"DECISION: FAIL — {reason}")

    def increment_loop(self) -> bool:
        """Increment loop counter; return True if loops remain."""
        self.loop_count += 1
        self.append_audit(f"LOOP: attempt {self.loop_count}/{self.MAX_LOOPS}")
        return self.loop_count < self.MAX_LOOPS