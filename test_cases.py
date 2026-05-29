from engine import run_weekly_analysis


SHARED_GOALS_NORMAL = [
    {
        "name": "Winter Break Trip",
        "target": 800.00,
        "deadline": "Dec 14",
        "min_weekly": 80.00,
        "current": 240.00,
    },
    {
        "name": "Spring Break Trip",
        "target": 600.00,
        "deadline": "Mar 1",
        "min_weekly": 50.00,
        "current": 150.00,
    },
]

SHARED_BALANCES = {"checking": 1200.00, "brokerage": 3400.00, "crypto": 500.00}


def run_test(label: str, **kwargs) -> None:
    print("\n" + "=" * 60)
    print(f"TEST CASE — {label}")
    print("=" * 60)
    result = run_weekly_analysis(**kwargs)
    print(result)


def test_case_1():
    """Normal week, on track — spending well under $300 budget."""
    run_test(
        "Normal week, on track",
        take_home=620.00,
        spending_budget=300.00,
        investing_allocation=120.00,
        transactions=[
            {"merchant": "Chipotle", "amount": 14.00},
            {"merchant": "Uber", "amount": 22.00},
            {"merchant": "Trader Joe's", "amount": 55.00},
            {"merchant": "Netflix", "amount": 16.00},
            {"merchant": "Target", "amount": 40.00},
            {"merchant": "Wingstop", "amount": 18.00},
        ],
        goals=SHARED_GOALS_NORMAL,
        balances=SHARED_BALANCES,
    )


def test_case_2():
    """Overspend on dining — $346 total vs $300 budget, Nobu is the culprit."""
    run_test(
        "Overspend on dining, needs reallocation",
        take_home=620.00,
        spending_budget=300.00,
        investing_allocation=120.00,
        transactions=[
            {"merchant": "Chipotle", "amount": 14.00},
            {"merchant": "Nobu", "amount": 180.00},
            {"merchant": "Uber", "amount": 35.00},
            {"merchant": "Trader Joe's", "amount": 55.00},
            {"merchant": "Starbucks", "amount": 22.00},
            {"merchant": "Target", "amount": 40.00},
        ],
        goals=SHARED_GOALS_NORMAL,
        balances=SHARED_BALANCES,
    )


def test_case_3():
    """Heavy overspend — $478 total, Winter Break now needs $120/week (6 weeks away)."""
    run_test(
        "Heavy overspend, goals at risk",
        take_home=620.00,
        spending_budget=300.00,
        investing_allocation=120.00,
        transactions=[
            {"merchant": "Concert tickets", "amount": 200.00},
            {"merchant": "Airbnb", "amount": 150.00},
            {"merchant": "Uber", "amount": 45.00},
            {"merchant": "Chipotle", "amount": 28.00},
            {"merchant": "Trader Joe's", "amount": 55.00},
        ],
        goals=[
            {
                "name": "Winter Break Trip",
                "target": 800.00,
                "deadline": "Dec 14 (6 weeks away)",
                "min_weekly": 120.00,
                "current": 80.00,
            },
            {
                "name": "Spring Break Trip",
                "target": 600.00,
                "deadline": "Mar 1",
                "min_weekly": 50.00,
                "current": 150.00,
            },
        ],
        balances=SHARED_BALANCES,
    )


if __name__ == "__main__":
    test_case_1()
    test_case_2()
    test_case_3()
