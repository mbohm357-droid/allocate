import os
from datetime import datetime, timedelta, timezone

from coinbase.rest import RESTClient
from dotenv import load_dotenv

load_dotenv()


def _build_client() -> RESTClient:
    api_key_name = os.getenv("COINBASE_API_KEY_NAME", "")
    private_key = os.getenv("COINBASE_PRIVATE_KEY", "")
    return RESTClient(api_key=api_key_name, api_secret=private_key)


def fetch_balances() -> dict[str, float]:
    """Return {currency: balance} for all non-zero active accounts."""
    client = _build_client()
    balances: dict[str, float] = {}
    cursor = None

    while True:
        kwargs: dict = {"limit": 250}
        if cursor:
            kwargs["cursor"] = cursor

        resp = client.get_accounts(**kwargs)

        for account in resp.accounts or []:
            if not getattr(account, "active", True):
                continue
            try:
                ab = account.available_balance
                raw = ab["value"] if isinstance(ab, dict) else ab.value
                value = float(raw)
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            if value > 0:
                currency = account.currency
                balances[currency] = balances.get(currency, 0.0) + value

        if not getattr(resp, "has_next", False):
            break
        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return balances


def fetch_transactions(days: int = 30) -> list[dict]:
    """Return filled orders from the last `days` days."""
    client = _build_client()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    resp = client.list_orders(
        start_date=start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_date=end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        order_status=["FILLED"],
        limit=250,
    )

    transactions = []
    for order in resp.orders or []:
        side = getattr(order, "side", "")
        product = getattr(order, "product_id", "UNKNOWN")

        try:
            usd_value = abs(float(getattr(order, "total_value_after_fees", None) or "0"))
        except (TypeError, ValueError):
            usd_value = 0.0

        try:
            fees = float(getattr(order, "total_fees", None) or "0")
        except (TypeError, ValueError):
            fees = 0.0

        transactions.append({
            "merchant": f"Coinbase — {side} {product}",
            "amount": usd_value,
            "type": side,
            "product": product,
            "fees": fees,
            "created_at": getattr(order, "created_time", ""),
        })

    return transactions


def get_coinbase_data(days: int = 30) -> dict:
    """
    Return balances and recent transactions for use with run_weekly_analysis().

    Example:
        data = get_coinbase_data()
        run_weekly_analysis(
            balances={"crypto": data["crypto_total"], **data["balances"]},
            transactions=data["transactions"],
            ...
        )
    """
    balances = fetch_balances()
    transactions = fetch_transactions(days=days)

    usd_cash = balances.pop("USD", 0.0) + balances.pop("USDC", 0.0)

    return {
        "balances": balances,       # {BTC: 0.01271441, ETH: 0.14847687, ...}
        "usd_cash": usd_cash,       # USD + USDC combined
        "transactions": transactions,
    }


if __name__ == "__main__":
    print("Account Balances")
    print("-" * 44)
    balances = fetch_balances()
    for currency, amount in sorted(balances.items()):
        print(f"  {currency:<10}  {amount:>16.8f}")

    print()
    print("Transactions — last 30 days")
    print("-" * 44)
    txns = fetch_transactions(days=30)
    if txns:
        for t in txns:
            arrow = "↑" if t["type"] == "BUY" else "↓"
            date = t["created_at"][:10] if t["created_at"] else "unknown"
            print(f"  {arrow} {t['product']:<14}  ${t['amount']:>10.2f}  {date}")
        print()
        print(f"  Orders : {len(txns)}")
        print(f"  Bought : ${sum(t['amount'] for t in txns if t['type'] == 'BUY'):,.2f}")
        print(f"  Sold   : ${sum(t['amount'] for t in txns if t['type'] == 'SELL'):,.2f}")
    else:
        print("  No filled orders in the last 30 days.")
