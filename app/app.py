import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Allow importing from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from coinbase_client import get_coinbase_data
from engine import calculate_after_tax, run_weekly_analysis
from main import _build_goals
from plaid_client import get_plaid_data

GOALS_FILE = Path(__file__).parent.parent / "goals.json"

INCOME_KEYWORDS = {
    "payroll", "direct deposit", "salary", "deposit", "transfer from",
    "zelle from", "venmo from", "paycheck", "cd interest", "interest",
    "dividend", "refund",
}

CATEGORY_KEYWORDS = {
    "Food & Dining": ["trader joe", "chipotle", "starbucks", "mcdonalds", "subway",
                      "pizza", "sushi", "restaurant", "doordash", "grubhub", "uber eats",
                      "whole foods", "safeway", "kroger", "aldi", "costco", "walmart"],
    "Transport": ["uber", "lyft", "mta", "metro", "transit", "parking", "gas",
                  "shell", "bp", "chevron", "exxon", "citibike"],
    "Utilities": ["con edison", "coned", "pge", "electric", "water", "internet",
                  "verizon", "at&t", "t-mobile", "spectrum", "comcast"],
    "Entertainment": ["netflix", "spotify", "hulu", "disney", "youtube", "steam",
                      "apple music", "hbo", "amazon prime", "cinema", "theater"],
    "Health": ["cvs", "walgreens", "rite aid", "pharmacy", "gym", "planet fitness",
               "doctor", "dental", "medical"],
    "Shopping": ["amazon", "target", "best buy", "apple", "zara", "h&m", "gap"],
}


def _categorize(transactions: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for t in transactions:
        merchant = t.get("merchant", "").lower()
        # Skip income / transfers
        if any(kw in merchant for kw in INCOME_KEYWORDS):
            continue
        amount = t.get("amount", 0.0)
        if amount <= 0:
            continue
        category = "Other"
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in merchant for kw in keywords):
                category = cat
                break
        totals[category] = totals.get(category, 0.0) + amount
    return dict(sorted(totals.items(), key=lambda x: x[1], reverse=True))


app = Flask(__name__)


@app.route("/")
def index():
    config = json.loads(GOALS_FILE.read_text())
    return render_template(
        "index.html",
        hourly_rate=config["hourly_rate"],
        tax_rate=config.get("tax_rate", 0.14),
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
    except Exception:
        holdings = {}
        usd_cash = None

    return jsonify({
        "checking": checking,
        "coinbase_holdings": holdings,
        "coinbase_usd": usd_cash,
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    body = request.get_json(force=True)
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
    except Exception:
        crypto_usd = 0.0
        holdings = {}

    balances = {
        "checking": checking,
        "brokerage": brokerage + lending_balance,
        "crypto": crypto_usd,
    }

    notes = ""
    if holdings:
        lines = "\n  ".join(f"{cur}: {amt:.8g}" for cur, amt in sorted(holdings.items()))
        notes = f"Coinbase crypto holdings (native units, not included in USD balances):\n  {lines}"
    if lending_balance > 0:
        notes += f"\nManually entered lending/yield balance: ${lending_balance:.2f}"

    spending_by_category = _categorize(raw_transactions)
    total_spent = sum(spending_by_category.values())

    goals = _build_goals(config.get("goals", []))

    # Filter to spending-only transactions for Claude
    spending_transactions = [
        t for t in raw_transactions
        if not any(kw in t.get("merchant", "").lower() for kw in INCOME_KEYWORDS)
        and t.get("amount", 0) > 0
    ]

    recommendation = run_weekly_analysis(
        take_home=take_home,
        transactions=spending_transactions,
        goals=goals,
        balances=balances,
        spending_budget=spending_budget,
        investing_allocation=investing_allocation,
        notes=notes,
    )

    return jsonify({
        "gross": round(gross, 2),
        "take_home": round(take_home, 2),
        "total_spent": round(total_spent, 2),
        "spending_budget": spending_budget,
        "spending_by_category": {k: round(v, 2) for k, v in spending_by_category.items()},
        "balances": {k: round(v, 2) for k, v in balances.items()},
        "coinbase_holdings": {k: round(v, 8) for k, v in holdings.items()},
        "goals": goals,
        "recommendation": recommendation,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
