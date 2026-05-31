import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Allow importing from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from coinbase_client import fetch_prices, get_coinbase_data
from engine import calculate_after_tax, run_weekly_analysis
from main import _build_goals
from plaid_client import get_plaid_data

GOALS_FILE = Path(__file__).parent.parent / "goals.json"

# Plaid top-level categories that are never real spending
_EXCLUDED_PLAID_CATS = frozenset({
    "transfer", "payment", "bank charges", "tax", "interest",
    "payroll and wages", "deposit",
})

# (name fragments to match, human-readable reason label)
_EXCLUSION_RULES: list[tuple[list[str], str]] = [
    (["gusto", "adp ", "paychex", "rippling", "direct deposit", "payroll"],
     "Payroll / direct deposit — not spending"),
    (["intrst", "interest payment", "interest pymnt", "dividend"],
     "Interest / dividend income — not spending"),
    (["credit card"],
     "Credit card payment — not spending"),
    (["ach"],
     "ACH transfer — not spending"),
    (["wire transfer"],
     "Wire transfer — not spending"),
    (["automatic payment", "autopay", "online payment", "bill payment", "thank you"],
     "Automatic payment — not spending"),
    (["zelle", "venmo transfer", "paypal transfer", "cash app",
      "mobile deposit", "check deposit"],
     "Transfer — not spending"),
]


def _get_exclusion_reason(t: dict) -> str | None:
    """Return a reason string if this transaction is non-spending, else None."""
    amount = t.get("amount", 0.0)
    name = t.get("merchant", "").lower()
    plaid_cat = t.get("plaid_category", "").lower()

    if amount < 0:
        return "Incoming deposit — not spending"

    for fragments, reason in _EXCLUSION_RULES:
        if any(f in name for f in fragments):
            return reason

    if plaid_cat in _EXCLUDED_PLAID_CATS:
        if "payroll" in plaid_cat:
            return "Payroll / direct deposit — not spending"
        if "transfer" in plaid_cat:
            return "Transfer — not spending"
        if "payment" in plaid_cat:
            return "Payment — not spending"
        return "Non-spending transaction — excluded"

    if amount > 500 and not t.get("has_merchant_name"):
        return "Large unrecognized transaction — review recommended"

    return None


def _classify_transactions(
    transactions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Split into (spending_transactions, excluded_with_reasons)."""
    spending, excluded = [], []
    for t in transactions:
        reason = _get_exclusion_reason(t)
        if reason:
            excluded.append({**t, "amount": abs(t["amount"]), "reason": reason})
        else:
            spending.append(t)
    return spending, excluded

CATEGORY_KEYWORDS = {
    "Food & Dining": [
        "trader joe", "chipotle", "starbucks", "mcdonalds", "mcdonald", "kfc",
        "subway", "pizza", "sushi", "restaurant", "doordash", "grubhub", "uber eats",
        "whole foods", "safeway", "kroger", "aldi", "costco", "walmart", "chick-fil",
        "taco bell", "wendy", "burger king", "five guys", "shake shack", "panera",
        "dunkin", "sweetgreen", "cafe", "diner", "grill", "bakery", "deli",
    ],
    "Transport": [
        "uber", "lyft", "mta", "metro", "transit", "parking", "gas station",
        "shell", "bp", "chevron", "exxon", "citibike", "citi bike",
        "united airlines", "delta", "american airlines", "jetblue", "southwest",
        "spirit airlines", "airlines", "airline", "amtrak", "train", "bus",
    ],
    "Utilities": [
        "con edison", "coned", "pge", "electric", "water", "internet",
        "verizon", "at&t", "t-mobile", "spectrum", "comcast",
    ],
    "Entertainment": [
        "netflix", "spotify", "hulu", "disney", "youtube", "steam",
        "apple music", "hbo", "amazon prime", "cinema", "theater", "theatre",
        "climbing", "bouldering", "bowling", "arcade", "concert", "ticketmaster",
        "fun ", "adventure", "escape room",
    ],
    "Health & Fitness": [
        "cvs", "walgreens", "rite aid", "pharmacy", "gym", "planet fitness",
        "equinox", "blink fitness", "crossfit", "yoga", "pilates",
        "doctor", "dental", "medical", "urgent care", "hospital",
    ],
    "Shopping": [
        "amazon", "target", "best buy", "apple store", "zara", "h&m", "gap",
        "nike", "adidas", "uniqlo", "macy", "nordstrom", "tj maxx",
        "bicycle", "bike shop", "REI", "outdoor", "hardware", "home depot", "ikea",
    ],
}


def _categorize(transactions: list[dict]) -> dict[str, float]:
    """Categorize spending transactions. Unrecognized merchants go to 'Uncategorized' (always last)."""
    totals: dict[str, float] = {}
    for t in transactions:
        merchant = t.get("merchant", "").lower()
        amount = t.get("amount", 0.0)
        if amount <= 0:
            continue
        category = "Uncategorized"
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in merchant for kw in keywords):
                category = cat
                break
        totals[category] = totals.get(category, 0.0) + amount
    # Sort known categories by amount desc; Uncategorized always last
    known = {k: v for k, v in totals.items() if k != "Uncategorized"}
    result = dict(sorted(known.items(), key=lambda x: -x[1]))
    if "Uncategorized" in totals:
        result["Uncategorized"] = totals["Uncategorized"]
    return result


app = Flask(__name__)


@app.route("/")
def index():
    config = json.loads(GOALS_FILE.read_text())
    goals = _build_goals(config.get("goals", []))
    return render_template(
        "index.html",
        hourly_rate=config["hourly_rate"],
        tax_rate=config.get("tax_rate", 0.14),
        goals=goals,
    )


@app.route("/api/accounts")
def api_accounts():
    try:
        plaid_data = get_plaid_data()
        checking = plaid_data["balances"].get("checking", 0.0)
    except Exception:
        checking = None

    try:
        cb_data = get_coinbase_data()
        holdings = cb_data["balances"]
        usd_cash = cb_data["usd_cash"]
        prices = fetch_prices(list(holdings.keys()))
        usd_values = {cur: round(amt * prices.get(cur, 0), 2) for cur, amt in holdings.items()}
        total_crypto_usd = round(sum(usd_values.values()), 2)
    except Exception:
        holdings = {}
        usd_cash = None
        usd_values = {}
        total_crypto_usd = None

    return jsonify({
        "checking": checking,
        "coinbase_holdings": holdings,
        "coinbase_usd": usd_cash,
        "coinbase_usd_values": usd_values,
        "coinbase_total_usd": total_crypto_usd,
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    print("[allocate] /api/analyze hit", flush=True)
    body = request.get_json(force=True)
    print(f"[allocate] body: {body}", flush=True)
    hours = float(body.get("hours", 0))
    lending_balance = float(body.get("lending_balance", 0.0))

    config = json.loads(GOALS_FILE.read_text())
    hourly_rate = config["hourly_rate"]
    tax_rate = config.get("tax_rate", 0.14)
    spending_budget = config.get("spending_budget", 300.0)
    investing_allocation = config.get("investing_allocation", 120.0)

    gross = hourly_rate * hours
    take_home = calculate_after_tax(gross, tax_rate)

    # Fetch live data (with fallbacks)
    try:
        plaid_data = get_plaid_data()
        checking = plaid_data["balances"].get("checking", 0.0)
        brokerage = plaid_data["balances"].get("brokerage", 0.0)
        raw_transactions = plaid_data["transactions"]
    except Exception:
        checking = 0.0
        brokerage = 0.0
        raw_transactions = []

    try:
        cb_data = get_coinbase_data()
        crypto_usd = cb_data["usd_cash"]
        holdings = cb_data["balances"]
        raw_transactions += cb_data["transactions"]
        prices = fetch_prices(list(holdings.keys()))
        usd_values = {cur: round(amt * prices.get(cur, 0), 2) for cur, amt in holdings.items()}
        total_crypto_usd = round(sum(usd_values.values()), 2)
    except Exception:
        crypto_usd = 0.0
        holdings = {}
        usd_values = {}
        total_crypto_usd = 0.0

    balances = {
        "checking": checking,
        "brokerage": brokerage + lending_balance,
        "crypto": crypto_usd,
    }

    # Classify: split into spending vs. excluded (transfers, payroll, etc.)
    spending_txns, excluded_txns = _classify_transactions(raw_transactions)

    notes = ""
    if holdings:
        lines = "\n  ".join(f"{cur}: {amt:.8g}" for cur, amt in sorted(holdings.items()))
        notes = f"Coinbase crypto holdings (native units, not included in USD balances):\n  {lines}"
    if lending_balance > 0:
        notes += f"\nManually entered lending/yield balance: ${lending_balance:.2f}"
    if excluded_txns:
        ex_lines = "\n".join(
            f"  - {e['merchant']}: ${e['amount']:.2f} ({e['reason']})"
            for e in excluded_txns
        )
        notes += f"\n\nExcluded from spending (shown to user separately — do NOT count these in spending totals):\n{ex_lines}"

    spending_by_category = _categorize(spending_txns)
    total_spent = sum(t["amount"] for t in spending_txns if t["amount"] > 0)

    goals = _build_goals(config.get("goals", []))

    recommendation = run_weekly_analysis(
        take_home=take_home,
        transactions=spending_txns,
        goals=goals,
        balances=balances,
        spending_budget=spending_budget,
        investing_allocation=investing_allocation,
        notes=notes,
    )

    print(f"[allocate] returning: gross={gross:.2f} take_home={take_home:.2f} "
          f"spending={total_spent:.2f} excluded={len(excluded_txns)}", flush=True)
    return jsonify({
        "gross": round(gross, 2),
        "take_home": round(take_home, 2),
        "total_spent": round(total_spent, 2),
        "spending_budget": spending_budget,
        "spending_by_category": {k: round(v, 2) for k, v in spending_by_category.items()},
        "excluded_transactions": [
            {
                "merchant": e["merchant"],
                "amount": round(e["amount"], 2),
                "reason": e["reason"],
                "date": e.get("date", ""),
            }
            for e in excluded_txns
        ],
        "balances": {k: round(v, 2) for k, v in balances.items()},
        "coinbase_holdings": {k: round(v, 8) for k, v in holdings.items()},
        "coinbase_usd_values": usd_values,
        "coinbase_total_usd": total_crypto_usd,
        "goals": goals,
        "recommendation": recommendation,
    })


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    app.run(debug=True, port=args.port)
