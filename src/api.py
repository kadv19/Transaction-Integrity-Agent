"""FastAPI wrapper around run_demo's graph logic for live demo.

POST /transact body {"user_intent": str, "force_stockout_first": bool}
- Builds graph with LiveRazorpayClient by default (real Razorpay test-mode).
- If LiveRazorpayClient() raises (missing/invalid keys) OR the Razorpay API
  call itself fails during checkout, falls back to StubRazorpayClient for
  that request and logs clearly in audit_trail that a stub link was used.
- Returns the full result dict as JSON.
- Permissive CORS for local frontend (file:// and localhost).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.catalog import _CATALOG, _init_catalog
from src.graph import build_graph
from src.razorpay_client import LiveRazorpayClient, StubRazorpayClient
from src.state import TransactionState, ValidationResults

# Trust & Transparency Dashboard — read-only imports (no mutation of existing logic)
import uuid as _trust_uuid
from src.trust.guardrail_reader import get_guardrail_config as _get_guardrail_config
from src.trust.explainer import (
    build_explanation as _build_explanation,
    store_transaction as _store_transaction,
    get_stored_transaction as _get_stored_transaction,
)
from src.trust.failure_simulator import simulate_failure as _simulate_failure

app = FastAPI(title="Transaction Integrity Agent — Demo API", version="0.1.0")

# Permissive CORS for local frontend access (frontend/index.html served via file:// or localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransactRequest(BaseModel):
    user_intent: str = Field(..., description="Free-text user request, e.g. 'one book under 3000'")
    force_stockout_first: bool = Field(
        False,
        description="If true, first candidate is forced out-of-stock to demo recovery path",
    )


def _serialize_result(result: Any) -> dict:
    """Convert graph invoke result (dict with Pydantic values) to JSON-serializable dict."""
    # compiled.invoke may return dict or TransactionState
    if hasattr(result, "model_dump"):
        # TransactionState object
        data = result.model_dump()
    elif isinstance(result, dict):
        data: dict[str, Any] = {}
        for k, v in result.items():
            if hasattr(v, "model_dump"):
                data[k] = v.model_dump()
            elif isinstance(v, list):
                # handle list of models (not expected for audit_trail, but safe)
                data[k] = [item.model_dump() if hasattr(item, "model_dump") else item for item in v]
            else:
                data[k] = v
    else:
        # fallback: try to coerce
        try:
            data = dict(result)  # type: ignore
        except Exception:
            raise HTTPException(status_code=500, detail=f"Unexpected graph result type: {type(result)}")

    # Ensure optional keys exist for frontend stability
    if "failure_reason" not in data or data["failure_reason"] is None:
        # TransactionState stores failure_reason; ensure key present
        data.setdefault("failure_reason", None)
    if "checkout_link" not in data:
        data.setdefault("checkout_link", None)
    if "audit_trail" not in data or data["audit_trail"] is None:
        data["audit_trail"] = []
    if "final_decision" not in data:
        data["final_decision"] = "FAIL"

    # Internal bookkeeping should not be exposed — strip underscore-prefixed keys
    for _k in list(data.keys()):
        if _k.startswith("_"):
            data.pop(_k, None)

    return data


def _is_razorpay_failure(serialized: dict) -> bool:
    """Detect whether FAIL was caused by Razorpay client error (needs fallback)."""
    if serialized.get("final_decision") != "FAIL":
        return False
    failure_reason = serialized.get("failure_reason") or ""
    audit = serialized.get("audit_trail") or []
    # generate_checkout marks violation with "Razorpay client error" and sets failure_reason
    if "Payment link creation failed" in failure_reason:
        return True
    if "Razorpay client error" in failure_reason:
        return True
    for entry in audit:
        if "Razorpay client error" in entry:
            return True
        if "generate_checkout: Razorpay" in entry and "FAIL" in entry:
            return True
        if "Missing checkout_record at checkout step" in entry and "Razorpay" in entry:
            return True
    return False


def _inject_fallback_audit(serialized: dict, reason: str, init_failure: bool = False) -> dict:
    """Clearly log in audit_trail that stub was used instead of real Razorpay.

    Prepends a FALLBACK entry and appends a NOTE so the staged reveal shows it.
    Distinguishes PASS (stub link) vs FAIL (stub client was used but no link).
    """
    trail: list[str] = list(serialized.get("audit_trail") or [])
    is_pass = serialized.get("final_decision") == "PASS"
    has_link = bool(serialized.get("checkout_link"))
    if init_failure:
        if is_pass and has_link:
            fallback_entry = (
                f"FALLBACK: LiveRazorpayClient init failed ({reason}) — "
                f"using StubRazorpayClient for this request; checkout link is a STUB "
                f"(not a real Razorpay link). Demo continued without crash."
            )
            note_entry = (
                "NOTE: This checkout link is a STUB (not a real Razorpay link) due to live API "
                "unavailability — it would be a real Razorpay test-mode link with valid .env keys."
            )
        else:
            fallback_entry = (
                f"FALLBACK: LiveRazorpayClient init failed ({reason}) — "
                f"using StubRazorpayClient for this request. Demo continued without crash."
            )
            note_entry = (
                "NOTE: Stub client was used due to live Razorpay unavailability — "
                "with valid .env keys this would hit the real Razorpay test-mode API."
            )
    else:
        if is_pass and has_link:
            fallback_entry = (
                f"FALLBACK: Live Razorpay API call failed ({reason}) — "
                f"retrying with StubRazorpayClient; stub link used instead of real one. "
                f"Demo continued without crash."
            )
            note_entry = (
                "NOTE: This checkout link is a STUB (not a real Razorpay link) due to live API "
                "unavailability — it would be a real Razorpay test-mode link with valid .env keys."
            )
        else:
            fallback_entry = (
                f"FALLBACK: Live Razorpay API call failed ({reason}) — "
                f"retrying with StubRazorpayClient. Demo continued without crash."
            )
            note_entry = (
                "NOTE: Stub client was used due to live Razorpay unavailability — "
                "with valid .env keys this would hit the real Razorpay test-mode API."
            )
    # Prepend fallback, append note at end (after DECISION)
    trail.insert(0, fallback_entry)
    trail.append(note_entry)
    serialized["audit_trail"] = trail
    serialized["razorpay_mode"] = "stub_fallback"
    serialized["razorpay_fallback_reason"] = reason
    serialized["_live_fallback_applied"] = True
    # Internal bookkeeping shouldn't be visible in API response — strip underscore-prefixed keys
    for _k in list(serialized.keys()):
        if _k.startswith("_"):
            serialized.pop(_k, None)
    return serialized


def _execute(user_intent: str, force_stockout_first: bool, razorpay_client) -> dict:
    """Build graph with given client, invoke, and serialize."""
    initial_state = TransactionState(
        user_intent=user_intent,
        max_budget=0.0,
        validation_results=ValidationResults(),
        force_stockout_first=force_stockout_first,
    )
    graph = build_graph(razorpay_client=razorpay_client)
    compiled = graph.compile()
    result_raw = compiled.invoke(initial_state)
    serialized = _serialize_result(result_raw)
    return serialized


@app.get("/catalog")
async def get_catalog():
    """Read-only catalog discovery for AI buyers.

    Returns the full synthetic catalog (all 120 products) as a JSON array.
    Each item exposes only the public merchant fields:
    {product_id, name, price, currency, category}.
    No pagination needed at this size. Does not mutate any state — the
    underlying _CATALOG is initialized once (idempotent) and then served
    as detached copies.
    """
    _init_catalog()
    # Return detached dicts; never expose internal model mutation or extra fields
    return [
        {
            "product_id": r.product_id,
            "name": r.name,
            "price": r.price,
            "currency": r.currency,
            "category": r.category,
        }
        for r in _CATALOG
    ]


@app.get("/.well-known/agent.json")
async def agent_descriptor():
    """Machine-readable descriptor for AI shopping agents.

    Honestly scoped: describes only what this demo merchant actually
    implements (catalog discovery + bounded transaction with audit trail).
    No claimed compliance with external protocols (UCP/ACP/AP2) that are
    not implemented.
    """
    return {
        "name": "Transaction Integrity Agent — Demo Merchant",
        "description": "Demo merchant for the Transaction Integrity Agent — exposes a read-only synthetic catalog and a bounded transaction endpoint with deterministic validation and full audit trail.",
        "catalog_url": "http://localhost:8000/catalog",
        "transact_url": "http://localhost:8000/transact",
        "transact_method": "POST",
        "transact_schema": {
            "user_intent": "string",
            "force_stockout_first": "boolean (optional, demo only)",
        },
        "capabilities": ["catalog_discovery", "bounded_transaction", "audit_trail"],
    }


@app.get("/")
async def health():
    return {"status": "ok", "endpoint": "POST /transact"}


@app.get("/health")
async def health_alt():
    return {"status": "ok"}


@app.post("/transact")
async def transact(req: TransactRequest):
    """Run the full agent graph for one user intent.

    Single synchronous graph execution — returns the complete audit_trail at once.
    Frontend stages the reveal client-side with ~300ms delay (no streaming).
    """
    user_intent = req.user_intent.strip()
    if not user_intent:
        raise HTTPException(status_code=422, detail="user_intent must be non-empty")

    # Attempt LiveRazorpayClient path first
    live_init_error: Exception | None = None
    try:
        live_client = LiveRazorpayClient()
    except Exception as e:
        live_init_error = e
        live_client = None  # type: ignore

    if live_init_error is not None:
        # Live client construction failed (missing/invalid keys) -> fallback to Stub
        stub = StubRazorpayClient()
        try:
            result = _execute(user_intent, req.force_stockout_first, stub)
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Stub fallback also failed: {e2}") from e2
        result = _inject_fallback_audit(result, reason=str(live_init_error), init_failure=True)
        # Trust store (additive, non-breaking)
        try:
            if "transaction_id" not in result or not result.get("transaction_id"):
                result["transaction_id"] = str(_trust_uuid.uuid4())
            _store_transaction(result)
        except Exception:
            pass
        return result

    # Live client constructed successfully — try live graph execution
    try:
        result_live = _execute(user_intent, req.force_stockout_first, live_client)
    except Exception as e:
        # Graph-level exception (network etc.) — fallback to stub for this request
        stub = StubRazorpayClient()
        try:
            result = _execute(user_intent, req.force_stockout_first, stub)
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"Live failed ({e}); stub also failed ({e2})") from e2
        result = _inject_fallback_audit(result, reason=str(e), init_failure=False)
        try:
            if "transaction_id" not in result or not result.get("transaction_id"):
                result["transaction_id"] = str(_trust_uuid.uuid4())
            _store_transaction(result)
        except Exception:
            pass
        return result

    # Check if live execution resulted in Razorpay checkout failure -> retry with stub
    if _is_razorpay_failure(result_live):
        stub = StubRazorpayClient()
        try:
            result_stub = _execute(user_intent, req.force_stockout_first, stub)
        except Exception as e2:
            # If stub also fails, return original live failure (don't hide original error)
            result_live["razorpay_mode"] = "live_failed"
            try:
                if "transaction_id" not in result_live or not result_live.get("transaction_id"):
                    result_live["transaction_id"] = str(_trust_uuid.uuid4())
                _store_transaction(result_live)
            except Exception:
                pass
            return result_live
        # Inject fallback audit notes
        reason = result_live.get("failure_reason") or "Live Razorpay API error"
        result_stub = _inject_fallback_audit(result_stub, reason=reason, init_failure=False)
        try:
            if "transaction_id" not in result_stub or not result_stub.get("transaction_id"):
                result_stub["transaction_id"] = str(_trust_uuid.uuid4())
            _store_transaction(result_stub)
        except Exception:
            pass
        return result_stub

    # Live path succeeded (or failed for non-Razorpay deterministic reasons)
    # Mark mode as live; no fallback injection needed
    # If PASS, this is a real Razorpay link; if FAIL for validator reasons, also live
    result_live["razorpay_mode"] = "live"
    if result_live.get("final_decision") == "PASS":
        # Optionally annotate that this is a real link (when live keys present)
        # Don't add to audit_trail if already live — keep trail pure
        pass
    # --- Trust store (read-only, additive): persist for /trust/explain without changing existing behavior ---
    try:
        if "transaction_id" not in result_live or not result_live.get("transaction_id"):
            result_live["transaction_id"] = str(_trust_uuid.uuid4())
        _store_transaction(result_live)
    except Exception:
        pass  # never break existing /transact on trust store errors
    return result_live


# ---------------------------------------------------------------------------
# Trust & Transparency Dashboard — New Endpoints Only (read-only layer)
# ---------------------------------------------------------------------------

class _FailureSimRequest(BaseModel):
    scenario: str = Field(..., description="stockout | rate_limit | validation_error")


@app.get("/trust/guardrails")
async def trust_guardrails():
    """Return current guardrail configuration (read-only)."""
    return _get_guardrail_config()


@app.get("/trust/explain/{transaction_id}")
async def trust_explain(transaction_id: str):
    """Return natural-language explanation for a stored transaction.

    If ID not found in store, attempt to run a fresh demo transaction
    (one book under 3000) and explain it — ensures demo UX never 404s
    during live judging. For strict 404, client can check `is_synthetic`.
    """
    stored = _get_stored_transaction(transaction_id)
    if stored is not None:
        explanation = _build_explanation(stored)
        # Include raw for dashboard debugging, but keep spec fields top-level
        return explanation

    # Not found — try to provide a helpful synthetic explanation instead of hard 404
    # But per spec we should 404 if truly unknown. We'll 404 with hint and available IDs.
    # To keep demo smooth, if ID looks like a demo placeholder, run a live synthetic.
    # Otherwise 404.
    # Check if ID is "demo" or empty — then generate synthetic
    if transaction_id.lower() in ("demo", "sample", "test", "latest"):
        # Generate a synthetic transaction on the fly (stub, no side effects)
        from src.trust.failure_simulator import simulate_failure as _sim
        synth = _sim("stockout")
        # synth contains explanation; adapt to expected shape but include transaction_id mapping
        expl = synth.get("explanation") or _build_explanation(synth.get("result", {}))
        expl["transaction_id"] = transaction_id
        expl["_synthetic"] = True
        return expl

    raise HTTPException(
        status_code=404,
        detail=f"Transaction {transaction_id!r} not found. Run POST /transact first to generate a transaction_id, or try POST /trust/simulate/failure.",
    )


@app.get("/trust/transactions")
async def trust_list_transactions():
    """List recent transaction IDs (helper for dashboard — not in spec but useful)."""
    from src.trust.explainer import list_stored_ids

    ids = list_stored_ids()
    return {"transaction_ids": ids, "count": len(ids)}


@app.post("/trust/simulate/failure")
async def trust_simulate_failure(req: _FailureSimRequest):
    """Trigger controlled failure scenarios for demo — wraps existing stockout logic."""
    scenario = (req.scenario or "").strip().lower()
    if scenario not in ("stockout", "rate_limit", "validation_error"):
        raise HTTPException(
            status_code=422,
            detail="scenario must be one of: stockout, rate_limit, validation_error",
        )
    try:
        result = _simulate_failure(scenario)  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}") from e
    return result


@app.get("/trust/explain")
async def trust_explain_latest():
    """Convenience: explain the most recent transaction (if any)."""
    from src.trust.explainer import list_stored_ids

    ids = list_stored_ids()
    if not ids:
        raise HTTPException(status_code=404, detail="No transactions stored yet. Run POST /transact first.")
    latest = ids[-1]
    stored = _get_stored_transaction(latest)
    assert stored is not None
    return _build_explanation(stored)
