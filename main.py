"""
Allocate — AI-powered personal finance assistant.

Run test cases:
    python test_cases.py

Interactive mode:
    python main.py
"""

from engine import calculate_after_tax, run_weekly_analysis


def prompt_float(label: str, default: float | None = None) -> float:
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{label}{hint}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def collect_transactions() -> list[dict]:
    print("\nEnter transactions (blank merchant name to finish):")
    transactions = []
    while True:
        merchant = input("  Merchant: ").strip()
        if not merchant:
            break
        amount = prompt_float(f"  Amount for {merchant}")
        transactions.append({"merchant": merchant, "amount": amount})
    return transactions


def collect_goals() -> list[dict]:
    print("\nEnter savings goals (blank name to finish):")
    goals = []
    while True:
        name = input("  Goal name: ").strip()
        if not name:
            break
        target = prompt_float("  Target amount")
        deadline = input("  Deadline (e.g. Dec 14): ").strip()
        min_weekly = prompt_float("  Minimum weekly contribution needed")
        current = prompt_float("  Amount saved so far", default=0.0)
        goals.append(
            {
                "name": name,
                "target": target,
                "deadline": deadline,
                "min_weekly": min_weekly,
                "current": current,
            }
        )
    return goals


def main():
    print("=" * 60)
    print("  Allocate — Personal Finance Assistant")
    print("=" * 60)

    use_gross = input("\nEnter gross pay and calculate after-tax? (y/N): ").strip().lower()
    if use_gross == "y":
        gross = prompt_float("Weekly gross pay")
        tax_rate = prompt_float("Tax rate (e.g. 0.25 for 25%)", default=0.25)
        take_home = calculate_after_tax(gross, tax_rate)
        print(f"  After-tax take-home: ${take_home:.2f}")
    else:
        take_home = prompt_float("After-tax weekly take-home")

    spending_budget = prompt_float("Weekly spending budget", default=300.0)
    investing_allocation = prompt_float("Default weekly investing amount", default=120.0)

    balances = {
        "checking": prompt_float("Checking balance", default=0.0),
        "brokerage": prompt_float("Brokerage balance", default=0.0),
        "crypto": prompt_float("Crypto balance", default=0.0),
    }

    transactions = collect_transactions()
    if not transactions:
        print("No transactions entered — exiting.")
        return

    goals = collect_goals()

    print("\nAnalyzing your week...\n")
    result = run_weekly_analysis(
        take_home=take_home,
        transactions=transactions,
        goals=goals,
        balances=balances,
        spending_budget=spending_budget,
        investing_allocation=investing_allocation,
    )
    print(result)


if __name__ == "__main__":
    main()
