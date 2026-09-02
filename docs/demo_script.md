# Demo Script — Transaction Integrity Agent (90 seconds)

> Stack: `frontend/index.html` (plain HTML/JS) → `POST http://localhost:8000/transact` → `src/api.py` (LiveRazorpayClient with Stub fallback) → LangGraph (`buyer_agent → integrity_investigator → recovery_agent → generate_checkout`). The graph runs synchronously and returns the complete `audit_trail` at once; the frontend stages the reveal client-side at ~300ms/entry. **Do not use `scenarios.json` for this demo** — that file does not control `buyer_agent`'s behavior (see Phase 3 findings). The live toggle is `force_stockout_first` on `TransactionState` (src/state.py:105).

## Setup (do before the audience watches)

1. Backend: `uvicorn src.api:app --reload --port 8000`  (requires `.env` with `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` for a real test-mode link; if missing, the API falls back to `StubRazorpayClient` and logs `FALLBACK` in the trail — the demo does not crash).
2. Frontend: open `frontend/index.html` in a browser (or `python -m http.server 5173` inside `frontend/` and visit `http://localhost:5173`). Keep DevTools Network tab visible to prove only **ONE** `/transact` request is made.
3. Input is empty except for the default `one book under 3000`. Checkbox **Force first candidate out of stock** is unchecked by default.

## 90-Second Walkthrough — Recovery Path (reliable demo, not left to chance)

This script uses the `force_stockout_first` checkbox to deterministically trigger the `InventoryValidator → Recovery Agent` path.

| Time | Action | Say verbatim |
|------|--------|--------------|
| 0–10s | Type (or keep) `one book under 3000` in the text input. Hover the checkbox. | “This is a plain single-page frontend — no framework. One text input for the user’s request, one checkbox that maps to `force_stockout_first` on TransactionState, an audit trail panel, and a final status area. The UI is deliberately plain — the audit trail is the product.” |
| 10–20s | Check **Force first candidate out of stock**. | “This toggle is how we reliably demo recovery live — it forces the first candidate’s inventory to zero. Not `scenarios.json`, which buyer_agent never reads. `src/state.py` and `src/buyer_agent.py` honor this flag; Phase 3 showed the scenarios file doesn’t drive the live graph.” |
| 20–25s | Click **Submit → Run Agent**. Point to Network tab — one POST. | “One request. The graph runs synchronously — buyer, validator, recovery, checkout — and returns the full `audit_trail` at once. The front-end just reveals it staged, ~300ms per entry. No LangGraph streaming, no `astream` — that was cut as unnecessary risk.” |
| 25–35s | Trail entry 1 appears: `Buyer Agent: picked 'Fiction Novel 13' …` | “Buyer Agent picked a book — cheapest books candidate under ₹3000. Deterministic catalog search: `src/catalog.py`, not an LLM.” |
| 35–45s | Entry 2 appears: `VIOLATION: InventoryValidator: Insufficient stock… available 0`  Entry 3: `LOOP: attempt 1/3` | “Integrity Investigator blocked it — InventoryValidator failed, stock is zero because we forced it. Loop counter ticks. Only deterministic validators can decide — CORE DESIGN LAW in `src/state.py` — and every blocker is logged.” |
| 45–60s | Entry 4: `Recovery Agent: found alternative 'Fiction Novel 43' … attempt #1/3` Entry 5–6: `generate_checkout: creating payment link…` | “Recovery Agent found a *different* book — same category and budget, excluding the tried ID list so it never loops. Next validator pass succeeds, then we re-enter validation and go to checkout.” |
| 60–80s | Entry 6–7: `Razorpay link created — id=… short_url=https://…`  `DECISION: PASS — all validators passed, checkout link generated`  Status area flips to **PASS** with a Razorpay link. | “Checkout uses real Razorpay test-mode via `LiveRazorpayClient` — amount is `round(final_amount*100)` from `checkout_record.final_amount` only — and the real id/short_url is logged. Click — it’s a real test link. If keys are missing or the network hiccups, `src/api.py` falls back to `StubRazorpayClient` for that request and the trail says `FALLBACK: stub link used` — a stub never masks as live, and the demo never crashes.” |
| 80–90s | Leave the link visible. Uncheck the box and submit again if time allows. | “Uncheck the box and the same request passes on the first try — no recovery — showing the bounded loop is gated and auditable either way. Every money action is explainable, bounded and gated — and you just watched it.” |

### If it FAILs instead (audience asks about failure)

“Any FAIL also ends with `failure_reason` in the status area after the trail finishes — the trail shows exactly which validator fired and why. No money moves on FAIL.”

### What NOT to do

- Do not claim `scenarios.json` drives the live agent — it doesn’t; use the checkbox.
- Do not claim streaming — the backend returns JSON; the front-end stages it.
- Do not hardcode a link — `src/razorpay_checkout.py:112–114` logs the *real* `id`/`short_url` returned by the client.

---

## One-Paragraph Pitch

We built a checkout copilot where every money action explainable, bounded and gated — five deterministic validators (price, inventory, policy, budget, intent) are the only code that can set PASS/FAIL, every decision is appended to an auditable `audit_trail`, and recovery is bounded to `MAX_LOOPS=3` on a tried-product exclusion list. Detection accuracy is proven by the Phase 1 validator-only benchmark on 180 scenarios (data/benchmark_report.json): 1.0 precision and 1.0 recall with 0 invalid transactions marked PASS across all validators. Routing safety is proven by Phase 3’s safety_invariant_check (benchmarks/full_benchmark_report.json): invalid_final_state_reached_checkout=0 and fail_but_checkout_bug=0, verified via the StubRazorpayClient call log — meaning no transaction with a failing validator ever reached checkout and no FAIL ever minted a link. Live, the same graph mints a real Razorpay test-mode link from `checkout_record.final_amount` and falls back to a clearly-labeled stub link on key/network failure so the demo never crashes.

---

## Appendix — Numbers to have ready (not in the pitch paragraph)

- **Validator-only baseline (Phase 1):** `data/benchmark_report.json` — `precision=1.0`, `recall=1.0`, `invalid_marked_pass=0`, `accuracy=1.0`. Proves *detection* is perfect when validators see the injected record.
- **Routing safety (Phase 3):** `benchmarks/full_benchmark_report.json → safety_invariant_check` — `invalid_final_state_reached_checkout=0`, `fail_but_checkout_bug=0`, `amount_conversion_correct=true`, `stub_total_calls=174`. Proves *routing* never lets a failing transaction reach `generate_checkout`. Framing is `does_prove` / `does_not_prove` as written in that report section.
- **Agent behavior gap — answer only if asked:** `benchmarks/full_benchmark_report.json → agent_behavior_gap` discusses buyer_agent’s independent catalog search (category substitution) vs. validator-only. If asked about “117/120”, say: *“That gap section does NOT measure safety — safety is the two zeros above. The substitution count shows buyer_agent resolved adversarial intents to a different valid product in the same category/budget and validators correctly passed the new proposal; it’s a design observation about search, not a validator miss. Detail is in `does_prove`/`does_not_prove` and the `sanity_check` in the same report.”* Do not add that figure to the one-paragraph pitch; it needs its caveat to be non-misleading.

## Run Commands

```bash
# backend (needs live keys in .env for a real link; otherwise stub fallback is automatic)
uvicorn src.api:app --reload --port 8000

# frontend — open directly or serve:
# option A: browser → file://.../frontend/index.html
# option B:
python -m http.server 5173 --directory frontend
# then http://localhost:5173
```

Expected PASS example (force_stockout ON): `audit_trail` 7 entries, `final_decision=PASS`, `checkout_link=https://...razorpay...` (or `https://stub.example.com/plink/...` with FALLBACK note if live unavailable), `razorpay_mode=live|stub_fallback`. Expected PASS example (force_stockout OFF): 4 entries, `PASS`, live link.

