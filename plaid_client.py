import os
from datetime import date, timedelta

import plaid
from dotenv import load_dotenv, set_key
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.transactions_get_request import TransactionsGetRequest

load_dotenv()

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

# Sandbox institution — First Platypus Bank (covers checking, savings, credit, investment)
_SANDBOX_INSTITUTION = "ins_109508"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _build_client() -> plaid_api.PlaidApi:
    env_name = os.getenv("PLAID_ENV", "sandbox").lower()
    cfg = Configuration(
        host=_ENV_MAP.get(env_name, plaid.Environment.Sandbox),
        api_key={
            "clientId": os.getenv("PLAID_CLIENT_ID", ""),
            "secret": os.getenv("PLAID_SECRET", ""),
        },
    )
    return plaid_api.PlaidApi(ApiClient(cfg))


# ---------------------------------------------------------------------------
# Access token management
# ---------------------------------------------------------------------------

def create_sandbox_token(institution_id: str = _SANDBOX_INSTITUTION) -> str:
    """
    Create a sandbox access token and save it to .env as PLAID_ACCESS_TOKEN.
    Only needed once — reuse the saved token after that.
    """
    client = _build_client()

    pt_resp = client.sandbox_public_token_create(
        SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products("transactions")],
        )
    )
    ex_resp = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=pt_resp.public_token)
    )
    token = ex_resp.access_token

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    set_key(env_path, "PLAID_ACCESS_TOKEN", token)
    print(f"Saved PLAID_ACCESS_TOKEN to .env")
    return token


def _get_access_token() -> str:
    token = os.getenv("PLAID_ACCESS_TOKEN", "")
    if not token:
        if os.getenv("PLAID_ENV", "sandbox").lower() == "sandbox":
            print("No PLAID_ACCESS_TOKEN found — creating sandbox token...")
            return create_sandbox_token()
        raise RuntimeError(
            "PLAID_ACCESS_TOKEN not set. Complete the Plaid Link flow and add it to .env."
        )
    return token


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def fetch_accounts(access_token: str | None = None) -> list[dict]:
    """Return all accounts with type, subtype, and balances."""
    client = _build_client()
    token = access_token or _get_access_token()
    resp = client.accounts_balance_get(AccountsBalanceGetRequest(access_token=token))

    accounts = []
    for acct in resp.accounts:
        bal = acct.balances
        accounts.append({
            "account_id": acct.account_id,
            "name": acct.name,
            "type": str(acct.type),
            "subtype": str(acct.subtype),
            "current": bal.current,
            "available": bal.available,
            "currency": bal.iso_currency_code or bal.unofficial_currency_code or "USD",
        })
    return accounts


def fetch_balances(access_token: str | None = None) -> dict[str, float]:
    """
    Return balances bucketed by type, ready for run_weekly_analysis():
        {"checking": float, "brokerage": float}
    Depository accounts (checking/savings/money market) → checking bucket.
    Investment accounts (IRA/401k/brokerage) → brokerage bucket.
    """
    accounts = fetch_accounts(access_token)
    checking = sum(
        (a["available"] if a["available"] is not None else a["current"] or 0.0)
        for a in accounts if a["type"] == "depository"
    )
    brokerage = sum(
        (a["current"] or 0.0)
        for a in accounts if a["type"] == "investment"
    )
    return {"checking": checking, "brokerage": brokerage}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def fetch_transactions(access_token: str | None = None, days: int = 30) -> list[dict]:
    """
    Return transactions from the last `days` days, formatted for run_weekly_analysis().
    Plaid amounts are positive for debits, negative for credits — we store absolute values.
    """
    client = _build_client()
    token = access_token or _get_access_token()

    end = date.today()
    start = end - timedelta(days=days)

    resp = client.transactions_get(
        TransactionsGetRequest(access_token=token, start_date=start, end_date=end)
    )

    transactions = []
    for txn in resp.transactions:
        if txn.pending:
            continue
        transactions.append({
            "merchant": txn.merchant_name or txn.name,
            "amount": abs(float(txn.amount)),
            "date": str(txn.date),
            "account_id": txn.account_id,
        })

    return transactions


# ---------------------------------------------------------------------------
# Combined — compatible with run_weekly_analysis()
# ---------------------------------------------------------------------------

def get_plaid_data(access_token: str | None = None, days: int = 30) -> dict:
    """
    Fetch balances and transactions from Plaid.

    Usage with run_weekly_analysis():
        data = get_plaid_data()
        run_weekly_analysis(
            balances=data["balances"],   # {"checking": ..., "brokerage": ...}
            transactions=data["transactions"],
            ...
        )
    """
    token = access_token or _get_access_token()
    return {
        "balances": fetch_balances(token),
        "transactions": fetch_transactions(token, days=days),
    }


# ---------------------------------------------------------------------------
# CLI summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    token = _get_access_token()

    print("Accounts")
    print("-" * 60)
    accounts = fetch_accounts(token)
    for a in accounts:
        avail = f"{a['available']:.2f}" if a["available"] is not None else "  n/a  "
        current = f"{a['current']:.2f}" if a["current"] is not None else "  n/a  "
        print(
            f"  {a['type']:<12} {a['subtype']:<18} "
            f"current={current:<12} avail={avail:<12} {a['name']}"
        )

    balances = fetch_balances(token)
    print(f"\n  → checking bucket : ${balances['checking']:,.2f}")
    print(f"  → brokerage bucket: ${balances['brokerage']:,.2f}")

    print()
    print("Transactions — last 30 days")
    print("-" * 60)
    txns = fetch_transactions(token, days=30)
    if txns:
        for t in txns:
            print(f"  {t['date']}  {t['merchant']:<32}  ${t['amount']:>9.2f}")
        print(f"\n  Total: {len(txns)} transactions, ${sum(t['amount'] for t in txns):,.2f}")
    else:
        print("  No transactions found.")
