"""CLI demo: take a user_intent string, run the full LangGraph agent,
and pretty-print the complete audit_trail plus the final decision."""

from __future__ import annotations

import sys
import os

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.graph import build_graph
from src.razorpay_client import LiveRazorpayClient
from src.state import TransactionState, ValidationResults


def pretty_print_state(result_dict: dict) -> None:
    print("\n" + "=" * 60)
    print("AUDIT TRAIL (chronological):")
    for i, entry in enumerate(result_dict["audit_trail"], 1):
        print(f"  {i:3d}. {entry}")
    print("=" * 60)
    print(f"FINAL DECISION: {result_dict['final_decision']}")
    if result_dict["final_decision"] == "PASS":
        print(f"CHECKOUT LINK: {result_dict['checkout_link']}")
    elif result_dict["final_decision"] == "FAIL":
        print(f"FAILURE REASON: {result_dict['failure_reason']}")
    print()


def run_demo(user_intent: str, force_stockout_first: bool = False) -> dict:
    """Run the full LangGraph agent and return the result dict."""

    # Initialize state
    initial_state = TransactionState(
        user_intent=user_intent,
        max_budget=0.0,
        validation_results=ValidationResults(),
        force_stockout_first=force_stockout_first,
    )

    # Build and compile the graph — live demo hits real Razorpay test-mode API
    razorpay_client = LiveRazorpayClient()
    graph = build_graph(razorpay_client=razorpay_client)
    compiled = graph.compile()

    # Invoke the compiled graph
    result_dict = compiled.invoke(initial_state)

    return result_dict


def main() -> None:
    """CLI entry point: take user_intent from args."""
    if len(sys.argv) < 2:
        print("Usage: python run_demo.py '<user_intent>' [--force-stockout-first]")
        print('Example: python run_demo.py "black mechanical keyboard under 8000"')
        print('Example: python run_demo.py "one book under 3000" --force-stockout-first')
        sys.exit(1)

    # Parse arguments
    force_stockout_first = False
    args = sys.argv[1:]
    if "--force-stockout-first" in args:
        force_stockout_first = True
        args.remove("--force-stockout-first")

    if len(args) < 1:
        print("Usage: python run_demo.py '<user_intent>' [--force-stockout-first]")
        sys.exit(1)

    user_intent = args[0]

    result_dict = run_demo(user_intent, force_stockout_first=force_stockout_first)

    pretty_print_state(result_dict)


if __name__ == "__main__":
    main()