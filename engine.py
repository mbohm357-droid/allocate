import os
import anthropic
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT

load_dotenv()


def calculate_after_tax(gross_weekly: float, tax_rate: float = 0.25) -> float:
    """Calculate after-tax weekly take-home from gross weekly income."""
    return gross_weekly * (1 - tax_rate)


def run_weekly_analysis(
    take_home: float,
    transactions: list[dict],
    goals: list[dict],
    balances: dict,
    spending_budget: float = 300.0,
    investing_allocation: float = 120.0,
) -> str:
    """
    Run a weekly financial analysis using Claude.

    Args:
        take_home: After-tax weekly take-home pay
        transactions: List of {"merchant": str, "amount": float}
        goals: List of {"name": str, "target": float, "deadline": str,
                        "min_weekly": float, "current": float}
        balances: {"checking": float, "brokerage": float, "crypto": float}
        spending_budget: Weekly discretionary spending limit
        investing_allocation: Default weekly investing amount (e.g. Vanguard)

    Returns:
        Claude's analysis and recommendations as a string
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    transaction_lines = "\n".join(
        f"- {t['merchant']}: ${t['amount']:.2f}" for t in transactions
    )
    total_spending = sum(t["amount"] for t in transactions)

    goal_lines = "\n".join(
        f"- {g['name']}: ${g['target']:.2f} target by {g['deadline']}, "
        f"needs ${g['min_weekly']:.2f}/week minimum "
        f"(current saved: ${g.get('current', 0):.2f})"
        for g in goals
    )

    user_message = f"""Weekly financial update:

After-tax weekly take-home: ${take_home:.2f}
Weekly spending budget: ${spending_budget:.2f}
Default investing allocation: ${investing_allocation:.2f}/week (Vanguard)

Current account balances:
- Checking: ${balances.get('checking', 0):.2f}
- Brokerage: ${balances.get('brokerage', 0):.2f}
- Crypto: ${balances.get('crypto', 0):.2f}

Savings goals:
{goal_lines}

Transactions this week (total: ${total_spending:.2f}):
{transaction_lines}

Please analyze my spending, compare it to my budget, and recommend how to allocate this week's paycheck."""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text
