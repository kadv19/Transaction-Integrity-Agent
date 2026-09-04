"""Shared catalog logic for buyer_agent and recovery_agent.

One canonical source of the 120-item synthetic catalog, seeded with
a deterministic Random instance so results are reproducible across
process invocations.  Exactly one of these two files should import
from it — no duplicate catalog definitions should live in
buyer_agent.py or recovery_agent.py."""
from __future__ import annotations

import random
import re
from src.state import CatalogRecord

# Price ranges per category (INR), matching synthetic_data.py exactly.
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

_random_seed = 42
_random = random.Random(_random_seed)

#: The 120-item synthetic catalog, populated once by _init_catalog().
_CATALOG: list[CatalogRecord] = []

# ---------------------------------------------------------------------------
# Merged category map — union of both maps.  buyer_agent has "keyboard":
# recovery_agent is missing it, so keep it.
# ---------------------------------------------------------------------------
_CATEGORY_MAP = {
    "smartphone": "electronics",
    "laptop": "electronics",
    "headphones": "electronics",
    "tablet": "electronics",
    "smartwatch": "electronics",
    "camera": "electronics",
    "keyboard": "electronics",
    "tv": "electronics",
    "television": "electronics",
    "led tv": "electronics",
    "smart tv": "electronics",
    "jacket": "clothing",
    "jeans": "clothing",
    "shirt": "clothing",
    "dress": "clothing",
    "sneakers": "clothing",
    "hoodie": "clothing",
    "fiction novel": "books",
    "technical book": "books",
    "biography": "books",
    "textbook": "books",
    "comic": "books",
    "magazine": "books",
    "lamp": "home",
    "curtains": "home",
    "bedding set": "home",
    "kitchenware": "home",
    "decor": "home",
    "furniture": "home",
    "yoga mat": "sports",
    "dumbbells": "sports",
    "running shoes": "sports",
    "tennis racket": "sports",
    "football": "sports",
    "cycle": "sports",
    "skincare set": "beauty",
    "perfume": "beauty",
    "makeup kit": "beauty",
    "hair care": "beauty",
    "nail kit": "beauty",
    "grooming kit": "beauty",
    "board game": "toys",
    "action figure": "toys",
    "puzzle": "toys",
    "lego set": "toys",
    "drone": "toys",
    "rc car": "toys",
    "car charger": "automotive",
    "phone mount": "automotive",
    "seat cover": "automotive",
    "dash cam": "automotive",
    "tire inflator": "automotive",
    "cleaner": "automotive",
    "snacks pack": "grocery",
    "beverages": "grocery",
    "breakfast cereal": "grocery",
    "pasta": "grocery",
    "spices": "grocery",
    "canned goods": "grocery",
    "vitamins": "health",
    "protein powder": "health",
    "first aid": "health",
    "thermometer": "health",
    "bp monitor": "health",
    "supplements": "health",
}


def _init_catalog() -> None:
    """Generate the fixed 120-item catalog once.

    Uses ONLY the local seeded _random instance for every random choice,
    including product names and category assignment.  No dependence on
    the unseeded global ``random`` module — this is what makes the catalog
    reproducible across process invocations.

    Names and categories are paired in a fixed order so that they stay
    coherent (e.g. no "Headphones" categorized as "books").  The pairing
    cycles through a single index, not two independent index expressions.
    """
    global _CATALOG
    if _CATALOG:
        return

    # Fixed product names, grouped by their coherent category.
    # This pairing restores the original grouping that existed before the
    # PRICE_RANGES NameError fix changed the indexing independently.
    paired = [
        ("Smartphone", "electronics"),
        ("Jacket", "clothing"),
        ("Fiction Novel", "books"),
        ("Lamp", "home"),
        ("Yoga Mat", "sports"),
        ("Skincare Set", "beauty"),
        ("Board Game", "toys"),
        ("Vitamins", "health"),
        ("Car Charger", "automotive"),
        ("Snacks Pack", "grocery"),
    ]

    # Cycle through the paired list with a single index.
    for i in range(1, 121):
        name_base, category = paired[(i - 1) % len(paired)]
        price = round(_uniform(*PRICE_RANGES[category]), 2)
        product_id = f"PROD-{i:04d}"

        record = CatalogRecord(
            product_id=product_id,
            name=f"{name_base} {i}",
            price=price,
            category=category,
        )
        _CATALOG.append(record)


def _uniform(low: float, high: float) -> float:
    """Wrap :func:`random.Random.uniform` for deterministic use."""
    return _random.uniform(low, high)


def _extract_max_budget(user_intent: str, current_max: float | None = None) -> float:
    """Extract max_budget from user intent using deterministic regex patterns."""
    if current_max is not None and current_max > 0:
        return current_max

    intent_lower = user_intent.lower()
    # Patterns: explicit budget keywords including "for 500" (was missing, caused 100k default)
    # Covers: under/below/max/maximum/upto/up to/for/at/around/about/within/budget/price/cost
    # Use word boundaries to avoid matching "at" inside "mat" (e.g., "yoga mat 877")
    budget_matches = re.findall(
        r"(?:\b(?:under|below|max|maximum|upto|up to|for|at|around|about|within|budget|price|cost)\b|less than|not more than)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        intent_lower,
    )
    for match in budget_matches:
        budget = float(match.replace(",", ""))
        if budget > 0:
            # Guard: avoid treating product model numbers like "RC Car 866 for personal use" as budget
            # "for" must be followed by budget-like number <= 1e6 and intent should imply budget context
            # If keyword is "for" and next word after number is not NaN, still valid if number is plausible budget
            return budget

    # Fallback: look for "under ₹X" or "under X" anywhere
    m = re.search(r"under\s*₹?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", intent_lower)
    if m:
        return float(m.group(1).replace(",", ""))

    m = re.search(r"under\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", intent_lower)
    if m:
        return float(m.group(1).replace(",", ""))

    return 100000.0  # very large default


def _extract_min_budget(user_intent: str, current_min: float | None = None) -> float:
    """Extract min_budget for phrases like 'more than 50', 'greater than 500', 'at least 1000', 'above 2000', 'over 500'."""
    if current_min is not None and current_min > 0:
        return current_min

    intent_lower = user_intent.lower()
    # "more than X", "greater than X", "above X", "over X", "at least X", "minimum X", "starting at X", "from X"
    # Use word boundaries to avoid false matches
    min_patterns = [
        r"\bmore than\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bgreater than\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\babove\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bover\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bat least\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bminimum\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bstarting at\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"\bfrom\b\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    ]
    for pat in min_patterns:
        m = re.search(pat, intent_lower)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    return val
            except:
                continue
    return 0.0  # no minimum


def _extract_category(user_intent: str) -> str:
    """Extract product category from user intent via keyword matching."""
    intent_lower = user_intent.lower()
    # Direct category keyword matches
    for keyword, category in sorted(
        _CATEGORY_MAP.items(), key=lambda x: -len(x[0])
    ):
        if keyword in intent_lower:
            return category

    # Fallback: broad keyword hints
    if any(w in intent_lower for w in ["laptop", "phone", "electronics", "gadget"]):
        return "electronics"
    if any(w in intent_lower for w in ["shirt", "jeans", "clothes", "fashion"]):
        return "clothing"
    if any(w in intent_lower for w in ["book", "novel", "study"]):
        return "books"
    return "electronics"  # default fallback


def _find_candidate(
    max_budget: float,
    category: str,
    tried_product_ids: set[str] | None = None,
    min_budget: float = 0.0,
) -> CatalogRecord | None:
    """Search the synthetic catalog for a product matching category and budget,
    excluding every product ID already tried in this run."""
    _init_catalog()

    budget = round(max_budget, 2)
    min_b = round(min_budget, 2)
    candidates = []
    for record in _CATALOG:
        if record.category != category:
            continue
        if record.price > budget:
            continue
        if record.price < min_b:
            continue
        if tried_product_ids and record.product_id in tried_product_ids:
            continue
        candidates.append(record)

    if not candidates:
        return None

    # Pick the first affordable match (deterministic: sorted by price ascending then ID)
    candidates.sort(key=lambda r: (r.price, r.product_id))
    return candidates[0]