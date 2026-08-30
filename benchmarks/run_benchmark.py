"""
Benchmark Runner for Transaction Integrity Agent.

Runs all scenarios through the five deterministic validators,
compares against ground-truth labels, and outputs real metrics.
CRITICAL: "invalid transactions incorrectly marked PASS" must be 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from state import TransactionState, CatalogRecord, InventoryRecord, CheckoutRecord, PolicyRecord
from validators import run_all_validators
from synthetic_data import Scenario, load_scenarios


ValidatorName = Literal[
    "price_validator",
    "inventory_validator",
    "policy_validator",
    "budget_validator",
    "authorization_validator",
]


@dataclass
class BenchmarkResult:
    """Results for a single scenario."""
    scenario_id: str
    category: str
    expected_failures: list[ValidatorName]
    actual_failures: list[ValidatorName]
    all_passed: bool
    correctly_classified: bool


@dataclass
class BenchmarkReport:
    """Aggregate benchmark metrics."""
    total_scenarios: int
    valid_scenarios: int  # ground truth: should pass all
    invalid_scenarios: int  # ground truth: at least one failure

    # Per-validator metrics
    validator_metrics: dict[str, dict[str, float]]

    # Overall metrics
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float

    # CRITICAL: Invalid transactions incorrectly marked PASS
    invalid_marked_pass: int
    invalid_marked_pass_details: list[str]

    # Summary
    accuracy: float


def scenario_to_state(scenario: Scenario) -> TransactionState:
    """Convert a Scenario to TransactionState for validator execution."""
    return TransactionState(
        user_intent=scenario.user_intent,
        max_budget=scenario.max_budget,
        catalog_record=CatalogRecord(**scenario.catalog_record),
        inventory_record=InventoryRecord(**scenario.inventory_record),
        checkout_record=CheckoutRecord(**scenario.checkout_record),
        policy_record=PolicyRecord(**scenario.policy_record),
    )


def get_actual_failures(state: TransactionState) -> list[ValidatorName]:
    """Extract which validators failed from validation_results."""
    vr = state.validation_results
    failures = []
    if not vr.price_validator:
        failures.append("price_validator")
    if not vr.inventory_validator:
        failures.append("inventory_validator")
    if not vr.policy_validator:
        failures.append("policy_validator")
    if not vr.budget_validator:
        failures.append("budget_validator")
    if not vr.authorization_validator:
        failures.append("authorization_validator")
    return failures


def run_benchmark(scenarios: list[Scenario]) -> BenchmarkReport:
    """Run all scenarios through validators and compute metrics."""
    results: list[BenchmarkResult] = []
    invalid_marked_pass_details: list[str] = []

    for scenario in scenarios:
        state = scenario_to_state(scenario)
        state = run_all_validators(state)

        actual_failures = get_actual_failures(state)
        all_passed = len(actual_failures) == 0

        # Ground truth: valid scenarios have empty expected_failures
        is_valid_ground_truth = len(scenario.expected_failures) == 0
        is_invalid_ground_truth = len(scenario.expected_failures) > 0

        # Correctly classified: actual failures match expected (order-independent)
        expected_set = set(scenario.expected_failures)
        actual_set = set(actual_failures)
        correctly_classified = expected_set == actual_set

        # CRITICAL CHECK: Invalid transaction marked PASS
        if is_invalid_ground_truth and all_passed:
            invalid_marked_pass_details.append(
                f"{scenario.scenario_id}: expected {scenario.expected_failures} but got PASS"
            )

        results.append(BenchmarkResult(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            expected_failures=scenario.expected_failures,
            actual_failures=actual_failures,
            all_passed=all_passed,
            correctly_classified=correctly_classified,
        ))

    # Aggregate metrics
    total = len(results)
    valid_count = sum(1 for r in results if len(r.expected_failures) == 0)
    invalid_count = total - valid_count

    # Per-validator metrics
    validator_names: list[ValidatorName] = [
        "price_validator",
        "inventory_validator",
        "policy_validator",
        "budget_validator",
        "authorization_validator",
    ]

    validator_metrics = {}
    for vname in validator_names:
        tp = fp = tn = fn = 0
        for r in results:
            expected_fail = vname in r.expected_failures
            actual_fail = vname in r.actual_failures
            if expected_fail and actual_fail:
                tp += 1
            elif not expected_fail and actual_fail:
                fp += 1
            elif expected_fail and not actual_fail:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        validator_metrics[vname] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        }

    # Overall metrics (transaction-level: PASS vs FAIL)
    # PASS = all validators pass, FAIL = at least one fails
    tp_overall = sum(1 for r in results if not r.expected_failures and r.all_passed)  # valid -> PASS
    fp_overall = sum(1 for r in results if not r.expected_failures and not r.all_passed)  # valid -> FAIL
    fn_overall = sum(1 for r in results if r.expected_failures and r.all_passed)  # invalid -> PASS (CRITICAL)
    tn_overall = sum(1 for r in results if r.expected_failures and not r.all_passed)  # invalid -> FAIL

    precision_overall = tp_overall / (tp_overall + fp_overall) if (tp_overall + fp_overall) > 0 else 1.0
    recall_overall = tp_overall / (tp_overall + fn_overall) if (tp_overall + fn_overall) > 0 else 1.0
    fpr_overall = fp_overall / (fp_overall + tn_overall) if (fp_overall + tn_overall) > 0 else 0.0
    fnr_overall = fn_overall / (fn_overall + tp_overall) if (fn_overall + tp_overall) > 0 else 0.0
    accuracy = (tp_overall + tn_overall) / total if total > 0 else 1.0

    invalid_marked_pass = fn_overall

    return BenchmarkReport(
        total_scenarios=total,
        valid_scenarios=valid_count,
        invalid_scenarios=invalid_count,
        validator_metrics=validator_metrics,
        precision=round(precision_overall, 4),
        recall=round(recall_overall, 4),
        false_positive_rate=round(fpr_overall, 4),
        false_negative_rate=round(fnr_overall, 4),
        invalid_marked_pass=invalid_marked_pass,
        invalid_marked_pass_details=invalid_marked_pass_details,
        accuracy=round(accuracy, 4),
    )


def print_report(report: BenchmarkReport) -> None:
    """Print benchmark report to console."""
    print("\n" + "=" * 70)
    print("TRANSACTION INTEGRITY AGENT — BENCHMARK REPORT")
    print("=" * 70)
    print(f"Total Scenarios:     {report.total_scenarios}")
    print(f"Valid (should PASS): {report.valid_scenarios}")
    print(f"Invalid (should FAIL): {report.invalid_scenarios}")
    print("-" * 70)

    print("\nPER-VALIDATOR METRICS:")
    print("-" * 70)
    for vname, m in report.validator_metrics.items():
        print(f"\n  {vname}:")
        print(f"    Precision:           {m['precision']:.4f}")
        print(f"    Recall:              {m['recall']:.4f}")
        print(f"    False Positive Rate: {m['false_positive_rate']:.4f}")
        print(f"    False Negative Rate: {m['false_negative_rate']:.4f}")
        print(f"    TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")

    print("\n" + "-" * 70)
    print("OVERALL TRANSACTION-LEVEL METRICS:")
    print("-" * 70)
    print(f"  Precision:           {report.precision:.4f}")
    print(f"  Recall:              {report.recall:.4f}")
    print(f"  False Positive Rate: {report.false_positive_rate:.4f}")
    print(f"  False Negative Rate: {report.false_negative_rate:.4f}")
    print(f"  Accuracy:            {report.accuracy:.4f}")
    print("-" * 70)

    print("\nCRITICAL SAFETY CHECK:")
    print("-" * 70)
    print(f"  Invalid transactions incorrectly marked PASS: {report.invalid_marked_pass}")
    if report.invalid_marked_pass > 0:
        print("  ❌ FAILURE — CORE DESIGN LAW VIOLATED")
        for detail in report.invalid_marked_pass_details:
            print(f"    - {detail}")
    else:
        print("  ✅ PASS — Zero invalid transactions marked PASS")
    print("=" * 70)


def save_report(report: BenchmarkReport, output_path: Path) -> None:
    """Save benchmark report to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "total_scenarios": report.total_scenarios,
        "valid_scenarios": report.valid_scenarios,
        "invalid_scenarios": report.invalid_scenarios,
        "validator_metrics": report.validator_metrics,
        "precision": report.precision,
        "recall": report.recall,
        "false_positive_rate": report.false_positive_rate,
        "false_negative_rate": report.false_negative_rate,
        "invalid_marked_pass": report.invalid_marked_pass,
        "invalid_marked_pass_details": report.invalid_marked_pass_details,
        "accuracy": report.accuracy,
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nReport saved to {output_path}")


if __name__ == "__main__":
    scenarios_path = Path("data/scenarios.json")
    if not scenarios_path.exists():
        print("scenarios.json not found. Run synthetic_data.py first.")
        exit(1)

    scenarios = load_scenarios(scenarios_path)
    print(f"Loaded {len(scenarios)} scenarios from {scenarios_path}")

    report = run_benchmark(scenarios)
    print_report(report)
    save_report(report, Path("data/benchmark_report.json"))

    # Exit code for CI: fail if any invalid marked PASS
    if report.invalid_marked_pass > 0:
        exit(1)
    else:
        exit(0)