"""
database.py

Mock data layer for the Razorpay AI Buildathon 2026 (Track 01) Boardroom Swarm.

Exposes two module-level structures consumed by the agent swarm:

    PRODUCT_CATALOG         -> dict of products keyed by product id
    RAZORPAY_GATEWAY_OFFERS -> list of active checkout discount offers

All data is static, in-memory mock data intended for debate/evaluation by the
six-agent swarm. No network calls, no external dependencies.
"""

from __future__ import annotations

import copy
from typing import Dict, List


# ---------------------------------------------------------------------------
# PRODUCT CATALOG
# ---------------------------------------------------------------------------
# Keys per item (all required by the swarm):
#   id          : str  unique product identifier
#   name        : str  human readable name
#   price       : float selling price in INR
#   margin_pct  : float gross margin percentage (0-100)
#   stock_level : int  units currently in warehouse
#   category    : str  logical grouping used by stylist / margin agents
#
# Margin logic:
#   - Basics (tees, socks, caps) carry the highest margins (~60-72%).
#   - Lifestyle tech accessories carry mid margins (~28-40%).
#   - Premium footwear / outerwear carry the lowest margins (~18-26%).
#
# Liquidation hint: items with very high stock_level (>= 400) are prime
# candidates for the Margin Maximizer to push for inventory liquidation.
# ---------------------------------------------------------------------------

PRODUCT_CATALOG: Dict[str, dict] = {
    "prod_001": {
        "id": "prod_001",
        "name": "Heavyweight Boxy Oversized Tee - Bone",
        "price": 1290.0,
        "margin_pct": 68.0,
        "stock_level": 540,
        "category": "apparel_basics",
    },
    "prod_002": {
        "id": "prod_002",
        "name": "Ribbed Crew Socks 3-Pack - Midnight",
        "price": 590.0,
        "margin_pct": 72.0,
        "stock_level": 880,
        "category": "apparel_basics",
    },
    "prod_003": {
        "id": "prod_003",
        "name": "Embroidered Dad Cap - Sand",
        "price": 750.0,
        "margin_pct": 65.0,
        "stock_level": 410,
        "category": "apparel_basics",
    },
    "prod_004": {
        "id": "prod_004",
        "name": "Garment-Dyed Hoodie - Slate",
        "price": 2490.0,
        "margin_pct": 55.0,
        "stock_level": 230,
        "category": "apparel_outerwear",
    },
    "prod_005": {
        "id": "prod_005",
        "name": "Tech Shell Rain Jacket - Black",
        "price": 3990.0,
        "margin_pct": 24.0,
        "stock_level": 95,
        "category": "apparel_outerwear",
    },
    "prod_006": {
        "id": "prod_006",
        "name": "Pleated Wide-Leg Trousers - Olive",
        "price": 2190.0,
        "margin_pct": 52.0,
        "stock_level": 160,
        "category": "apparel_bottomwear",
    },
    "prod_007": {
        "id": "prod_007",
        "name": "Relaxed Cargo Pant - Stonewash",
        "price": 1890.0,
        "margin_pct": 50.0,
        "stock_level": 210,
        "category": "apparel_bottomwear",
    },
    "prod_008": {
        "id": "prod_008",
        "name": "Limited Run High-Top Sneaker - Cream",
        "price": 5490.0,
        "margin_pct": 19.0,
        "stock_level": 60,
        "category": "footwear",
    },
    "prod_009": {
        "id": "prod_009",
        "name": "Cushioned Runner Low - Fog",
        "price": 4290.0,
        "margin_pct": 22.0,
        "stock_level": 140,
        "category": "footwear",
    },
    "prod_010": {
        "id": "prod_010",
        "name": "Suede Chelsea Boot - Tan",
        "price": 6290.0,
        "margin_pct": 18.0,
        "stock_level": 45,
        "category": "footwear",
    },
    "prod_011": {
        "id": "prod_011",
        "name": "Active Noise-Cancelling Earbuds - Graphite",
        "price": 4990.0,
        "margin_pct": 31.0,
        "stock_level": 320,
        "category": "tech_accessories",
    },
    "prod_012": {
        "id": "prod_012",
        "name": "MagSafe Power Bank 10K - Matte White",
        "price": 2190.0,
        "margin_pct": 38.0,
        "stock_level": 460,
        "category": "tech_accessories",
    },
    "prod_013": {
        "id": "prod_013",
        "name": "Smart LED Desk Lamp - Warm",
        "price": 1690.0,
        "margin_pct": 40.0,
        "stock_level": 280,
        "category": "tech_accessories",
    },
    "prod_014": {
        "id": "prod_014",
        "name": "Braided USB-C Cable 2m - Charcoal",
        "price": 490.0,
        "margin_pct": 66.0,
        "stock_level": 1200,
        "category": "tech_accessories",
    },
    "prod_015": {
        "id": "prod_015",
        "name": "Woven Crossbody Sling - Espresso",
        "price": 1790.0,
        "margin_pct": 58.0,
        "stock_level": 190,
        "category": "lifestyle_bags",
    },
    "prod_016": {
        "id": "prod_016",
        "name": "Canvas Tote - Natural",
        "price": 890.0,
        "margin_pct": 70.0,
        "stock_level": 610,
        "category": "lifestyle_bags",
    },
    "prod_017": {
        "id": "prod_017",
        "name": "Stainless Steel Insulated Bottle - Steel",
        "price": 1290.0,
        "margin_pct": 54.0,
        "stock_level": 350,
        "category": "lifestyle_bags",
    },
    "prod_018": {
        "id": "prod_018",
        "name": "Oversized Zip-Up Windbreaker - Cobalt",
        "price": 2890.0,
        "margin_pct": 47.0,
        "stock_level": 130,
        "category": "apparel_outerwear",
    },
}


# ---------------------------------------------------------------------------
# RAZORPAY GATEWAY OFFERS
# ---------------------------------------------------------------------------
# Each offer represents an active checkout-time discount the Gateway Hawk can
# surface. Constraints honoured by design:
#   - payment_method is one of the five allowed enum values.
#   - bank_name is meaningful per payment_method (UPI mandates a handle/bank
#     aggregator, cards/netbanking carry an issuing bank, wallets carry a
#     wallet provider).
#   - min_order_value gates eligibility so the Margin Maximizer and Gateway
#     Hawk must coordinate on basket size.
# ---------------------------------------------------------------------------

RAZORPAY_GATEWAY_OFFERS: List[dict] = [
    {
        "offer_id": "off_upi_01",
        "payment_method": "UPI",
        "discount_pct": 5.0,
        "min_order_value": 999.0,
        "bank_name": "BHIM UPI",
    },
    {
        "offer_id": "off_upi_02",
        "payment_method": "UPI",
        "discount_pct": 8.0,
        "min_order_value": 2999.0,
        "bank_name": "Google Pay",
    },
    {
        "offer_id": "off_hdfc_01",
        "payment_method": "CREDIT_CARD",
        "discount_pct": 10.0,
        "min_order_value": 1999.0,
        "bank_name": "HDFC Bank",
    },
    {
        "offer_id": "off_icici_01",
        "payment_method": "CREDIT_CARD",
        "discount_pct": 7.5,
        "min_order_value": 1499.0,
        "bank_name": "ICICI Bank",
    },
    {
        "offer_id": "off_sbi_01",
        "payment_method": "DEBIT_CARD",
        "discount_pct": 5.0,
        "min_order_value": 999.0,
        "bank_name": "SBI",
    },
    {
        "offer_id": "off_axis_01",
        "payment_method": "DEBIT_CARD",
        "discount_pct": 6.0,
        "min_order_value": 1999.0,
        "bank_name": "Axis Bank",
    },
    {
        "offer_id": "off_kotak_01",
        "payment_method": "NETBANKING",
        "discount_pct": 4.0,
        "min_order_value": 1499.0,
        "bank_name": "Kotak Mahindra",
    },
    {
        "offer_id": "off_pnb_01",
        "payment_method": "NETBANKING",
        "discount_pct": 3.5,
        "min_order_value": 999.0,
        "bank_name": "Punjab National Bank",
    },
    {
        "offer_id": "off_phonepe_01",
        "payment_method": "WALLET",
        "discount_pct": 6.0,
        "min_order_value": 799.0,
        "bank_name": "PhonePe",
    },
    {
        "offer_id": "off_paytm_01",
        "payment_method": "WALLET",
        "discount_pct": 5.0,
        "min_order_value": 799.0,
        "bank_name": "Paytm",
    },
    {
        "offer_id": "off_amazonpay_01",
        "payment_method": "WALLET",
        "discount_pct": 4.5,
        "min_order_value": 1299.0,
        "bank_name": "Amazon Pay",
    },
]


# ---------------------------------------------------------------------------
# Convenience accessors (pure, no side effects)
# ---------------------------------------------------------------------------

def get_product(product_id: str) -> dict | None:
    """Return a deep copy of a product, or None if not present."""
    product = PRODUCT_CATALOG.get(product_id)
    return copy.deepcopy(product) if product else None


def get_offers_for_method(payment_method: str) -> List[dict]:
    """Return all offers applicable to a given payment method."""
    method = payment_method.upper().strip()
    return [
        copy.deepcopy(offer)
        for offer in RAZORPAY_GATEWAY_OFFERS
        if offer["payment_method"] == method
    ]


def list_categories() -> List[str]:
    """Return the distinct product categories present in the catalog."""
    seen: List[str] = []
    for product in PRODUCT_CATALOG.values():
        if product["category"] not in seen:
            seen.append(product["category"])
    return seen


if __name__ == "__main__":
    print(f"Loaded {len(PRODUCT_CATALOG)} products across {len(list_categories())} categories.")
    print(f"Loaded {len(RAZORPAY_GATEWAY_OFFERS)} Razorpay gateway offers.")
