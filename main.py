"""
Allocate — AI-powered personal finance assistant.

Usage:
    python main.py          # weekly analysis (loads goals.json)
    python test_cases.py    # run hardcoded test cases
"""

import json
from datetime import date, datetime
from pathlib import Path

from coinbase_client import get_coinbase_data
from engine import calculate_after_tax, run_weekly_analysis
from plaid_client import get_plaid_data

GOALS_FILE = Path(__file__).parent / "goals.json"


# ---------------------------------------------------------------------------
# Deadline / goal helpers
# ---------------------------------------------------------------------------

def _parse_deadline(s: str) -> date:
    """Parse 'YYYY-MM-DD', 'Dec 14', or 'Mar 1' into a date."""
    # ISO full date
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        pass
    # Month-day without year — pick next upcoming occurrence
    today = date.today()
    for fmt in ("%b %d", "%B %d"):
        try:
            d = datetime.strptime(f"{s} {today.year}", f"{fmt} %Y").date()
            return d if d >= today else datetime.strptime(
                f"{s} {today.year + 1}", f"{fmt} %Y"
            ).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse deadline '{s}'. Use 'YYYY-MM-DD' or 'Dec 14'.")


def _weeks_until(d: date) -> float:
    return max(1.0, (d - date.today()).days / 7)


def _build_goals(raw: list[dict]) -> list[dict]:
    """Attach computed min_weekly and weeks-remaining label to each goal."""
    goals = []
    for g in raw:
        deadline_date = _parse_deadline(g["deadline"])
        weeks_left = _weeks_until(deadline_date)
        remaining = max(0.0, g["target"] - g.get("current", 0.0))
        min_weekly = round(remaining / weeks_left, 2)
        goals.append({
            "name": g["name"],
            "target": g["target"],
            "deadline": f"{g['deadline']} ({int(weeks_left)} weeks away)",
            "min_weekly": min_weekly,
            "current": g.get("current", 0.0),
        })
    return goals


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text())
    return _prompt_and_save_config()


def _prompt_and_save_config() -> dict:
    print("No goals.json found. Let's set up your profile.\n")

    def ask(prompt, default=None):
        hint = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{hint}: ").strip()
        return raw if raw else str(default)

    hourly_rate = float(ask("Hourly rate ($)"))
    tax_rate = float(ask("Tax rate (e.g. 0.25)", default=0.25))
    spending_budget = float(ask("Weekly spending budget ($)", default=300))
    investing_allocation = float(ask("Weekly investing allocation ($)", default=120))

    goals = []
    print("\nEnter savings goals (blank name to finish):")
    while True:
        name = input("  Goal name: ").strip()
        if not name:
            break
        target = float(input("  Target amount ($): ").strip())
        deadline = input("  Deadline (e.g. 'Dec 14'): ").strip()
        current = float(input("  Amount saved so far ($) [0]: ").strip() or "0")
        goals.append({"name": name, "target": target, "deadline": deadline, "current": current})

    config = {
        "hourly_rate": hourly_rate,
        "tax_rate": tax_rate,
        "spending_budget": spending_budget,
        "investing_allocation": investing_allocation,
        "goals": goals,
    }
    GOALS_FILE.write_text(json.dumps(config, indent=2))
    print(f"\nSaved to {GOALS_FILE.name}\n")
    return config


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Allocate — Weekly Analysis")
    print("=" * 60)

    config = _load_config()
    hourly_rate = config["hourly_rate"]
    tax_rate = config.get("tax_rate", 0.25)
    spending_budget = config.get("spending_budget", 300.0)
    investing_allocation = config.get("investing_allocation", 120.0)

    # Hours worked → gross → take-home
    hours = float(input(f"\nHours worked this week: ").strip())
    gross = hourly_rate * hours
    take_home = calculate_after_tax(gross, tax_rate)
    print(f"  Gross ${gross:.2f}  →  after-tax take-home ${take_home:.2f}")

    # Fetch Plaid
    print("\nFetching bank data (Plaid)...", end="", flush=True)
    plaid_data = get_plaid_data()
    print(" done")

    # Fetch Coinbase
    print("Fetching crypto data (Coinbase)...", end="", flush=True)
    coinbase_data = get_coinbase_data()
    print(" done")

    # Balances — checking/brokerage from Plaid; USD-stable crypto from Coinbase
    balances = {
        "checking": plaid_data["balances"]["checking"],
        "brokerage": plaid_data["balances"]["brokerage"],
        "crypto": coinbase_data["usd_cash"],
    }

    # Build a notes line so Claude sees the native crypto holdings
    crypto_holdings = coinbase_data["balances"]
    if crypto_holdings:
        holdings_str = "  " + "\n  ".join(
            f"{cur}: {amt:.8g}" for cur, amt in sorted(crypto_holdings.items())
        )
        notes = f"Coinbase crypto holdings (native units, not included in USD balances):\n{holdings_str}"
    else:
        notes = ""

    # Combine transactions from both sources
    all_transactions = plaid_data["transactions"] + coinbase_data["transactions"]

    # Goals with computed min_weekly
    goals = _build_goals(config.get("goals", []))

    # Run analysis
    print("\n" + "=" * 60)
    result = run_weekly_analysis(
        take_home=take_home,
        transactions=all_transactions,
        goals=goals,
        balances=balances,
        spending_budget=spending_budget,
        investing_allocation=investing_allocation,
        notes=notes,
    )
    print(result)


if __name__ == "__main__":
    main()
