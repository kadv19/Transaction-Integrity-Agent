"""Graph — wires buyer_agent, integrity_investigator, recovery_agent, and
generate_checkout into a LangGraph StateGraph structure.

Note: The StateGraph is defined here for structure/registration, but state
management is handled manually in run_demo.py due to Pydantic/v2 compatibility
with langgraph's automatic serialization/deserialization."""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from src.state import TransactionState
from src.buyer_agent import buyer_agent
from src.integrity_investigator import integrity_investigator
from src.recovery_agent import recovery_agent
from src.razorpay_client import RazorpayClient, StubRazorpayClient
from src.razorpay_checkout import generate_checkout


def build_graph(razorpay_client: RazorpayClient | None = None) -> StateGraph:
    """Build and return the LangGraph StateGraph (structure only).

    Args:
        razorpay_client: Injected Razorpay client. Defaults to StubRazorpayClient
                         for safety (no real network calls during tests/benchmarks).
                         Pass LiveRazorpayClient() for real test-mode API calls.
    """
    if razorpay_client is None:
        razorpay_client = StubRazorpayClient()

    graph = StateGraph(TransactionState)

    # Closure captures the injected client so the node uses dependency injection
    def _checkout_node(state: TransactionState) -> TransactionState:
        return generate_checkout(state, razorpay_client)

    graph.add_node("buyer_agent", buyer_agent)
    graph.add_node("integrity_investigator", integrity_investigator)
    graph.add_node("recovery_agent", recovery_agent)
    graph.add_node("generate_checkout", _checkout_node)

    graph.set_entry_point("buyer_agent")

    graph.add_conditional_edges(
        "buyer_agent",
        lambda state: "integrity_investigator",
    )

    graph.add_conditional_edges(
        "integrity_investigator",
        lambda state: "generate_checkout"
        if _all_validators_pass(state)
        else "recovery_agent",
    )

    graph.add_conditional_edges(
        "recovery_agent",
        lambda state: END if state.final_decision != "PENDING" else "integrity_investigator",
    )

    graph.add_edge("generate_checkout", END)

    return graph


def _all_validators_pass(state: TransactionState) -> bool:
    """Check if all five validators passed."""
    if state.validation_results is None:
        return False
    return all(
        [
            state.validation_results.price_validator,
            state.validation_results.inventory_validator,
            state.validation_results.policy_validator,
            state.validation_results.budget_validator,
            state.validation_results.intent_alignment_validator,
        ]
    )


def _loop_exhausted(state: TransactionState) -> bool:
    """Check if loop count has reached MAX_LOOPS."""
    return state.final_decision == "FAIL" and state.loop_count >= state.MAX_LOOPS