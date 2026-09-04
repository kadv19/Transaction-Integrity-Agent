"""Trust & Transparency Dashboard — read-only visualization layer.

This package exposes internal safety mechanisms without mutating existing state.
All modules are pure readers/wrappers around existing graph logic.
"""

from src.trust.explainer import build_explanation
from src.trust.guardrail_reader import get_guardrail_config
from src.trust.failure_simulator import simulate_failure

__all__ = ["build_explanation", "get_guardrail_config", "simulate_failure"]
