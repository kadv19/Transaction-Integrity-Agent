"""
Synthetic Data Generator for Transaction Integrity Agent.

Produces ~180-200 scenarios across 6 categories with ground-truth labels.
Each scenario includes all records needed for validators + expected failures.
Output: data/scenarios.json (reusable across phases, no regeneration needed).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Literal
from pathlib import Path

from state import (
    CatalogRecord,
    InventoryRecord,
    CheckoutRecord,
    PolicyRecord,
    ValidationResults,
)


# ---------------------------------------------------------------------------
# Scenario Definition
# ---------------------------------------------------------------------------
ValidatorName = Literal[
    "price_validator",
    "inventory_validator",
    "policy_validator",
    "budget_validator",
    "authorization_validator",
]


@dataclass
class Scenario:
    """Complete scenario with all records and ground-truth expected failures."""
    scenario_id: str
    category: str
    user_intent: str
    max_budget: float
    catalog_record: dict
    inventory_record: dict
    checkout_record: dict
    policy_record: dict
    expected_failures: list[ValidatorName]  # which validators SHOULD fail
    description: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
CATEGORIES = [
    "electronics", "clothing", "books", "home", "sports", "beauty",
    "toys", "automotive", "grocery", "health"
]

PRODUCT_TEMPLATES = {
    "electronics": ["Smartphone", "Laptop", "Headphones", "Tablet", "Smartwatch", "Camera"],
    "clothing": ["T-Shirt", "Jeans", "Jacket", "Dress", "Sneakers", "Hoodie"],
    "books": ["Fiction Novel", "Technical Book", "Biography", "Textbook", "Comic", "Magazine"],
    "home": ["Lamp", "Curtains", "Bedding Set", "Kitchenware", "Decor", "Furniture"],
    "sports": ["Yoga Mat", "Dumbbells", "Running Shoes", "Tennis Racket", "Football", "Cycle"],
    "beauty": ["Skincare Set", "Perfume", "Makeup Kit", "Hair Care", "Nail Kit", "Grooming Kit"],
    "toys": ["Board Game", "Action Figure", "Puzzle", "LEGO Set", "Drone", "RC Car"],
    "automotive": ["Car Charger", "Phone Mount", "Seat Cover", "Dash Cam", "Tire Inflator", "Cleaner"],
    "grocery": ["Snacks Pack", "Beverages", "Breakfast Cereal", "Pasta", "Spices", "Canned Goods"],
    "health": ["Vitamins", "Protein Powder", "First Aid", "Thermometer", "BP Monitor", "Supplements"],
}

PRICE_RANGES = {
    "electronics": (5000, 150000),
    "clothing": (500, 10000),
    "books": (200, 3000),
    "home": (300, 25000),
    "sports": (500, 50000),
    "beauty": (300, 15000),
    "toys": (200, 20000),
    "automotive": (200, 10000),
    "grocery": (100, 5000),
    "health": (200, 10000),
}

FINE_PRINT_EXCLUSIONS = [
    "electronics", "clothing", "books", "home", "sports", "beauty",
    "toys", "automotive", "grocery", "health", "sale", "clearance",
    "final sale", "personalized", "perishable", "digital", "gift card",
    "jewelry", "luxury"
]


def random_price(category: str) -> float:
    """Generate realistic price for category."""
    low, high = PRICE_RANGES[category]
    return round(random.uniform(low, high), 2)


def random_quantity() -> int:
    return random.randint(1, 5)


def make_catalog_record(product_id: str, category: str, price: float | None = None) -> CatalogRecord:
    name = f"{random.choice(PRODUCT_TEMPLATES[category])} {random.randint(100, 999)}"
    return CatalogRecord(
        product_id=product_id,
        name=name,
        price=price if price is not None else random_price(category),
        currency="INR",
        description=f"Premium {name.lower()}",
        category=category,
    )


def make_inventory_record(product_id: str, available: int | None = None) -> InventoryRecord:
    if available is None:
        available = random.randint(0, 100)
    # Ensure at least 1 unit is available for purchase (reserved < available)
    max_reserved = max(0, min(10, available - 1))
    reserved = random.randint(0, max_reserved)
    return InventoryRecord(
        product_id=product_id,
        available_quantity=available,
        reserved_quantity=reserved,
        warehouse_id=f"WH-{random.randint(1, 10):02d}",
    )


def make_checkout_record(
    product_id: str,
    catalog_price: float,
    quantity: int,
    price_override: float | None = None,
    tax_rate: float = 0.18,
    shipping: float = 0.0,
    discount: float = 0.0,
) -> CheckoutRecord:
    unit_price = price_override if price_override is not None else catalog_price
    subtotal = round(unit_price * quantity, 2)
    tax = round(subtotal * tax_rate, 2)
    final_amount = round(subtotal + tax + shipping - discount, 2)
    return CheckoutRecord(
        product_id=product_id,
        unit_price=unit_price,
        quantity=quantity,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        discount=discount,
        final_amount=final_amount,
    )


def make_policy_record(
    product_id: str,
    category: str,
    max_qty: int | None = None,
    fine_print: list[str] | None = None,
    exclusions: list[str] | None = None,
) -> PolicyRecord:
    return PolicyRecord(
        product_id=product_id,
        returnable=random.choice([True, False]),
        cancellable=random.choice([True, False]),
        max_quantity_per_order=max_qty,
        excluded_payment_methods=[],
        excluded_regions=[],
        fine_print_exclusions=exclusions or [],
        fine_print=fine_print[0] if fine_print else None,
    )


def make_valid_scenario(scenario_id: str) -> Scenario:
    """Category 1: Fully valid — all validators should PASS."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = 1  # Intent says "Buy one"
    inventory = make_inventory_record(product_id, available=quantity + random.randint(5, 20))
    checkout = make_checkout_record(product_id, catalog.price, quantity)
    policy = make_policy_record(product_id, category, max_qty=10)
    budget = checkout.final_amount + random.uniform(100, 5000)
    intent = f"Buy one {catalog.name.lower()} for personal use"

    return Scenario(
        scenario_id=scenario_id,
        category="valid",
        user_intent=intent,
        max_budget=round(budget, 2),
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=[],
        description="All validators should pass — fully valid transaction",
    )


def make_price_mismatch_scenario(scenario_id: str) -> Scenario:
    """Category 2: Price inconsistency — catalog vs checkout mismatch."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = random_quantity()
    inventory = make_inventory_record(product_id, available=quantity + 10)
    # Introduce price mismatch: checkout price differs from catalog
    mismatch_factor = random.choice([0.8, 0.9, 1.1, 1.2, 1.5])
    checkout_price = round(catalog.price * mismatch_factor, 2)
    checkout = make_checkout_record(product_id, catalog.price, quantity, price_override=checkout_price)
    policy = make_policy_record(product_id, category)
    budget = checkout.final_amount + random.uniform(100, 5000)
    intent = f"Buy {catalog.name.lower()} at listed price"

    return Scenario(
        scenario_id=scenario_id,
        category="price_mismatch",
        user_intent=intent,
        max_budget=round(budget, 2),
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=["price_validator"],
        description=f"Catalog ₹{catalog.price:.2f} vs checkout ₹{checkout_price:.2f} — price validator should fail",
    )


def make_inventory_mismatch_scenario(scenario_id: str) -> Scenario:
    """Category 3: Inventory inconsistency — stock says available but actually 0 or below requested."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = random.randint(3, 10)  # Request more than available
    # Inventory shows 0 or less than requested
    available = random.randint(0, quantity - 1)
    inventory = make_inventory_record(product_id, available=available)
    checkout = make_checkout_record(product_id, catalog.price, quantity)
    policy = make_policy_record(product_id, category)
    budget = checkout.final_amount + random.uniform(100, 5000)
    intent = f"Purchase {quantity} units of {catalog.name.lower()}"

    return Scenario(
        scenario_id=scenario_id,
        category="inventory_mismatch",
        user_intent=intent,
        max_budget=round(budget, 2),
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=["inventory_validator"],
        description=f"Requested {quantity} but only {available} available — inventory validator should fail",
    )


def make_policy_contradiction_scenario(scenario_id: str) -> Scenario:
    """Category 4: Policy contradiction — headline vs fine-print exclusion."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = random_quantity()
    inventory = make_inventory_record(product_id, available=quantity + 10)
    checkout = make_checkout_record(product_id, catalog.price, quantity)
    # Fine print exclusion matches product category
    exclusion = category if category in FINE_PRINT_EXCLUSIONS else random.choice(FINE_PRINT_EXCLUSIONS)
    policy = make_policy_record(
        product_id,
        category,
        fine_print=[f"Exclusions apply to {exclusion} category"],
        exclusions=[exclusion],
    )
    budget = checkout.final_amount + random.uniform(100, 5000)
    intent = f"Buy {catalog.name.lower()} with standard return policy"

    return Scenario(
        scenario_id=scenario_id,
        category="policy_contradiction",
        user_intent=intent,
        max_budget=round(budget, 2),
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=["policy_validator"],
        description=f"Fine-print excludes '{exclusion}' category — policy validator should fail",
    )


def make_budget_violation_scenario(scenario_id: str) -> Scenario:
    """Category 5: Budget violation — final amount exceeds user's stated max."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = random_quantity()
    inventory = make_inventory_record(product_id, available=quantity + 10)
    checkout = make_checkout_record(product_id, catalog.price, quantity)
    policy = make_policy_record(product_id, category)
    # Budget is LESS than final amount
    budget = round(checkout.final_amount * random.uniform(0.5, 0.9), 2)
    intent = f"Buy {catalog.name.lower()} under ₹{budget:,.0f}"

    return Scenario(
        scenario_id=scenario_id,
        category="budget_violation",
        user_intent=intent,
        max_budget=budget,
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=["budget_validator", "authorization_validator"],
        description=f"Budget ₹{budget:.2f} < final ₹{checkout.final_amount:.2f} — budget & authorization validators should fail",
    )


def make_combined_failure_scenario(scenario_id: str) -> Scenario:
    """Category 6: Combined failures — 2+ validators fail on same scenario."""
    category = random.choice(CATEGORIES)
    product_id = f"PROD-{scenario_id}"
    catalog = make_catalog_record(product_id, category)
    quantity = random.randint(3, 8)

    # Combine 2-3 failure types
    failure_types = random.sample(
        ["price", "inventory", "policy", "budget", "authorization"],
        k=random.randint(2, 3)
    )

    # Inventory mismatch
    available = random.randint(0, quantity - 1) if "inventory" in failure_types else quantity + 10
    inventory = make_inventory_record(product_id, available=available)

    # Price mismatch
    mismatch_factor = random.choice([0.7, 0.85, 1.15, 1.3]) if "price" in failure_types else 1.0
    checkout_price = round(catalog.price * mismatch_factor, 2)
    checkout = make_checkout_record(product_id, catalog.price, quantity, price_override=checkout_price)

    # Policy contradiction
    exclusion = category if category in FINE_PRINT_EXCLUSIONS else random.choice(FINE_PRINT_EXCLUSIONS)
    policy = make_policy_record(
        product_id,
        category,
        max_qty=2 if "policy" in failure_types else 10,
        fine_print=[f"Exclusions apply to {exclusion}"] if "policy" in failure_types else [],
        exclusions=[exclusion] if "policy" in failure_types else [],
    )

    # Budget violation
    budget = round(checkout.final_amount * random.uniform(0.5, 0.8), 2) if "budget" in failure_types else checkout.final_amount + 5000

    # Authorization violation (intent implies single but quantity > 1)
    if "authorization" in failure_types:
        intent = f"Buy one {catalog.name.lower()} for personal use"
    else:
        intent = f"Buy {quantity} units of {catalog.name.lower()} under ₹{budget:,.0f}"

    expected = []
    if "price" in failure_types:
        expected.append("price_validator")
    if "inventory" in failure_types:
        expected.append("inventory_validator")
    if "policy" in failure_types:
        expected.append("policy_validator")
    if "budget" in failure_types:
        expected.append("budget_validator")
        # Budget mention in intent also triggers authorization validator
        expected.append("authorization_validator")
    if "authorization" in failure_types:
        expected.append("authorization_validator")

    return Scenario(
        scenario_id=scenario_id,
        category="combined_failure",
        user_intent=intent,
        max_budget=budget,
        catalog_record=catalog.model_dump(),
        inventory_record=inventory.model_dump(),
        checkout_record=checkout.model_dump(),
        policy_record=policy.model_dump(),
        expected_failures=expected,
        description=f"Combined failures: {', '.join(expected)}",
    )


# ---------------------------------------------------------------------------
# Main Generator
# ---------------------------------------------------------------------------
def generate_scenarios(
    n_valid: int = 60,
    n_price: int = 30,
    n_inventory: int = 25,
    n_policy: int = 25,
    n_budget: int = 20,
    n_combined: int = 20,
    seed: int = 42,
) -> list[Scenario]:
    """Generate all scenarios with deterministic seed for reproducibility."""
    random.seed(seed)

    scenarios = []
    counter = 1

    def next_id() -> str:
        nonlocal counter
        sid = f"{counter:04d}"
        counter += 1
        return sid

    # Category 1: Valid
    for _ in range(n_valid):
        scenarios.append(make_valid_scenario(next_id()))

    # Category 2: Price mismatch
    for _ in range(n_price):
        scenarios.append(make_price_mismatch_scenario(next_id()))

    # Category 3: Inventory mismatch
    for _ in range(n_inventory):
        scenarios.append(make_inventory_mismatch_scenario(next_id()))

    # Category 4: Policy contradiction
    for _ in range(n_policy):
        scenarios.append(make_policy_contradiction_scenario(next_id()))

    # Category 5: Budget violation
    for _ in range(n_budget):
        scenarios.append(make_budget_violation_scenario(next_id()))

    # Category 6: Combined failures
    for _ in range(n_combined):
        scenarios.append(make_combined_failure_scenario(next_id()))

    # Shuffle for realistic ordering
    random.shuffle(scenarios)

    # Re-assign sequential IDs after shuffle
    for i, s in enumerate(scenarios):
        s.scenario_id = f"{i+1:04d}"

    return scenarios


def save_scenarios(scenarios: list[Scenario], output_path: Path) -> None:
    """Save scenarios to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [s.__dict__ for s in scenarios]
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(scenarios)} scenarios to {output_path}")


def load_scenarios(input_path: Path) -> list[Scenario]:
    """Load scenarios from JSON file."""
    with open(input_path) as f:
        data = json.load(f)
    return [Scenario(**d) for d in data]


if __name__ == "__main__":
    scenarios = generate_scenarios()
    save_scenarios(scenarios, Path("data/scenarios.json"))
    print(f"Generated {len(scenarios)} scenarios")
    print("Categories:", {s.category for s in scenarios})