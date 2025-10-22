"""Helper around the Binance client for administrative tasks."""
from __future__ import annotations

from binance.client import Client
from binance.exceptions import BinanceAPIException


class BinanceAdmin:
    """Wrapper that exposes the subset of admin operations we require."""

    def __init__(self, api_key: str, api_secret: str):
        self.client = Client(api_key, api_secret)

    def get_sub_accounts(self):
        """Return the configured sub-accounts for the master account."""
        try:
            if hasattr(self.client, "get_sub_accounts"):
                data = self.client.get_sub_accounts()
            else:
                data = self.client.get_sub_account_list()
            if isinstance(data, dict) and "subAccounts" in data:
                return data["subAccounts"]
            return data
        except BinanceAPIException as exc:  # pragma: no cover - network dependant
            print(f"获取子账户失败: {exc}")
            return []

    def transfer_to_sub(self, sub_email: str, amount: float):
        """Transfer USDT funds from the master account to a sub-account."""
        try:
            return self.client.sub_account_transfer(
                asset="USDT",
                amount=amount,
                email=sub_email,
                type=Client.SUB_ACCOUNT_TRANSFER_IN,
            )
        except BinanceAPIException as exc:  # pragma: no cover - network dependant
            print(f"划转失败: {exc}")
            return None

    def get_sub_balance(self, sub_email: str) -> float:
        """Fetch the combined free and locked USDT balance for a sub-account."""
        try:
            balances = self.client.get_sub_account_balance(email=sub_email)
            if isinstance(balances, dict) and "balances" in balances:
                balances = balances["balances"]
        except BinanceAPIException as exc:  # pragma: no cover - network dependant
            print(f"获取子账户余额失败: {exc}")
            return 0.0

        for balance in balances:
            if balance.get("asset") == "USDT":
                free_amt = float(balance.get("free", 0))
                locked_amt = float(balance.get("locked", 0))
                return round(free_amt + locked_amt, 8)
        return 0.0
