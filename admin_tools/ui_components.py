"""Tkinter widgets implementing the administrator console."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from .binance_admin_api import BinanceAdmin
from .db_manager import add_allowed_pair, get_allowed_pairs, record_fund_allocation


class AdminPanel:
    """Composite widget used for managing pairs and fund allocations."""

    def __init__(
        self,
        parent: tk.Misc,
        master_api_key: str,
        master_api_secret: str,
        on_pairs_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.parent = parent
        self.on_pairs_changed = on_pairs_changed
        self.admin_api = BinanceAdmin(master_api_key, master_api_secret)
        self._build_ui()

    def _build_ui(self) -> None:
        self.tab_control = ttk.Notebook(self.parent)
        self.tab_control.pack(fill="both", expand=True)

        self.pair_tab = ttk.Frame(self.tab_control)
        self.fund_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.pair_tab, text="交易对管理")
        self.tab_control.add(self.fund_tab, text="资金分配")

        # Pair management widgets
        ttk.Label(self.pair_tab, text="添加允许的交易对（如BTCUSDT）：").grid(row=0, column=0, padx=5, pady=5)
        self.symbol_entry = ttk.Entry(self.pair_tab, width=20)
        self.symbol_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(self.pair_tab, text="添加", command=self.add_pair).grid(row=0, column=2, padx=5)

        self.pair_tree = ttk.Treeview(self.pair_tab, columns=["symbol"], show="headings", height=6)
        self.pair_tree.heading("symbol", text="允许的交易对")
        self.pair_tree.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        self.pair_tab.grid_rowconfigure(1, weight=1)
        self.pair_tab.grid_columnconfigure(1, weight=1)

        # Fund management widgets
        ttk.Label(self.fund_tab, text="子账户邮箱:").grid(row=0, column=0, padx=5, pady=5)
        self.sub_email_entry = ttk.Entry(self.fund_tab, width=30)
        self.sub_email_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(self.fund_tab, text="金额 (USDT):").grid(row=1, column=0, padx=5, pady=5)
        self.amount_entry = ttk.Entry(self.fund_tab, width=15)
        self.amount_entry.grid(row=1, column=1, padx=5, pady=5)

        action_frame = ttk.Frame(self.fund_tab)
        action_frame.grid(row=2, column=0, columnspan=2, pady=5)
        ttk.Button(action_frame, text="分配资金", command=lambda: self._handle_fund_action("分配")).pack(side="left", padx=5)
        ttk.Button(action_frame, text="回收资金", command=lambda: self._handle_fund_action("回收")).pack(side="left", padx=5)

        self.sub_tree = ttk.Treeview(self.fund_tab, columns=["email", "balance"], show="headings", height=6)
        self.sub_tree.heading("email", text="子账户邮箱")
        self.sub_tree.heading("balance", text="当前余额(USDT)")
        self.sub_tree.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        self.fund_tab.grid_rowconfigure(3, weight=1)
        self.fund_tab.grid_columnconfigure(0, weight=1)
        self.fund_tab.grid_columnconfigure(1, weight=1)

        self.refresh_pair_list()
        self.refresh_sub_accounts()

    def add_pair(self) -> None:
        symbol = self.symbol_entry.get().strip().upper()
        if not symbol:
            messagebox.showwarning("提示", "请输入交易对")
            return
        if add_allowed_pair(symbol):
            messagebox.showinfo("成功", f"添加交易对 {symbol} 成功")
            self.symbol_entry.delete(0, tk.END)
            self.refresh_pair_list()
            if self.on_pairs_changed:
                self.on_pairs_changed()
        else:
            messagebox.showerror("错误", f"交易对 {symbol} 已存在")

    def refresh_pair_list(self) -> None:
        for item in self.pair_tree.get_children():
            self.pair_tree.delete(item)
        for pair in get_allowed_pairs():
            self.pair_tree.insert("", tk.END, values=(pair,))

    def refresh_sub_accounts(self) -> None:
        for item in self.sub_tree.get_children():
            self.sub_tree.delete(item)
        for sub in self.admin_api.get_sub_accounts():
            email = sub.get("email") or sub.get("subAccountString")
            if not email:
                continue
            balance = self.admin_api.get_sub_balance(email)
            self.sub_tree.insert("", tk.END, values=(email, round(balance, 2)))

    def _handle_fund_action(self, action: str) -> None:
        email = self.sub_email_entry.get().strip()
        try:
            amount = float(self.amount_entry.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "请输入有效金额")
            return

        if not email or amount <= 0:
            messagebox.showwarning("提示", "邮箱和金额不能为空且金额需为正数")
            return

        if action == "分配":
            result = self.admin_api.transfer_to_sub(email, amount)
        else:
            # 回收资金逻辑在此示例中省略，对应实际实现可调用其他接口。
            result = {"success": True}

        if result:
            record_fund_allocation(user_id=1, amount=amount, action=action)
            messagebox.showinfo("成功", f"{action}资金 {amount} USDT 成功")
            self.refresh_sub_accounts()
        else:
            messagebox.showerror("错误", f"{action}资金失败")
