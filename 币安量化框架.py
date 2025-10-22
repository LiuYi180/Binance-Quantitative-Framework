import requests
import pandas as pd
from collections import deque
import time
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import importlib.util
import math
import threading
from binance.client import Client
from binance.enums import *
import logging

from admin_tools.db_manager import init_db, get_allowed_pairs
from admin_tools.ui_components import AdminPanel

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, root):
        self.root = root
        self.root.title("Athena Trading Engine - An Integrated Tool for Backtesting & Paper Trading & Live Trading")
        self.root.geometry("1400x900")

        init_db()
        self.current_user_role = "admin"  # 实际项目中应结合登录信息设置
        self.master_api_key = os.environ.get("BINANCE_MASTER_API_KEY", "你的主账户API")
        self.master_api_secret = os.environ.get("BINANCE_MASTER_API_SECRET", "你的主账户Secret")

        self.admin_panel_window = None
        self.admin_panel = None

        # 引擎模式：0-回测，1-实测，2-实盘
        self.engine_mode = 0

        # 公共数据
        self.default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
        self.symbols = get_allowed_pairs() or self.default_symbols
        self.intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
        self.data_queue = deque(maxlen=10000)
        self.df = pd.DataFrame()
        self.strategy = None
        self.strategy_name = ""
        self.order_list = []
        self.trade_orders = []
        self.order_sequence = 1
        
        # 创建界面
        self.create_main_ui()
        
    def create_main_ui(self):
        # 顶部引擎切换按钮
        engine_frame = ttk.Frame(self.root)
        engine_frame.pack(fill="x", padx=10, pady=5)
        
        self.backtest_btn = ttk.Button(engine_frame, text="回测引擎", command=lambda: self.switch_engine(0))
        self.backtest_btn.pack(side="left", padx=5)
        
        self.simulation_btn = ttk.Button(engine_frame, text="实测引擎", command=lambda: self.switch_engine(1))
        self.simulation_btn.pack(side="left", padx=5)
        
        self.live_btn = ttk.Button(engine_frame, text="实盘引擎", command=lambda: self.switch_engine(2))
        self.live_btn.pack(side="left", padx=5)

        if self.current_user_role == "admin":
            self.admin_btn = ttk.Button(engine_frame, text="管理后台", command=self.open_admin_panel)
            self.admin_btn.pack(side="left", padx=5)

        # 创建公共组件
        self.create_common_widgets()
        
        # 创建各引擎专用组件
        self.create_backtest_widgets()
        self.create_simulation_widgets()
        self.create_live_widgets()
        
        # 初始显示回测引擎
        self.switch_engine(0)
        
    def create_common_widgets(self):
        # 公共数据设置区域
        self.data_frame = ttk.LabelFrame(self.root, text="数据设置")
        self.data_frame.pack(fill="x", padx=10, pady=5)
        
        row1_frame = ttk.Frame(self.data_frame)
        row1_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(row1_frame, text="交易对:").pack(side="left", padx=5)
        initial_symbol = self.symbols[0] if self.symbols else ""
        self.symbol_var = tk.StringVar(value=initial_symbol)
        self.symbol_combo = ttk.Combobox(row1_frame, textvariable=self.symbol_var, values=self.symbols, width=15)
        self.symbol_combo.pack(side="left", padx=5)
        ttk.Button(row1_frame, text="刷新交易对", command=lambda: self.refresh_allowed_pairs(show_message=True)).pack(side="left", padx=5)
        
        ttk.Label(row1_frame, text="时间范围:").pack(side="left", padx=5)
        self.start_date_var = tk.StringVar(value=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"))
        self.end_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        start_date_entry = ttk.Entry(row1_frame, textvariable=self.start_date_var, width=20)
        start_date_entry.pack(side="left", padx=5)
        
        ttk.Label(row1_frame, text="至").pack(side="left", padx=5)
        end_date_entry = ttk.Entry(row1_frame, textvariable=self.end_date_var, width=20)
        end_date_entry.pack(side="left", padx=5)
        
        ttk.Label(row1_frame, text="时间周期:").pack(side="left", padx=5)
        self.interval_var = tk.StringVar(value="1h")
        interval_combo = ttk.Combobox(row1_frame, textvariable=self.interval_var, values=self.intervals, width=10)
        interval_combo.pack(side="left", padx=5)
        
        self.fetch_button = ttk.Button(row1_frame, text="获取数据", command=self.fetch_data)
        self.fetch_button.pack(side="left", padx=10)
        
        # 状态和进度条
        self.status_frame = ttk.Frame(self.data_frame)
        self.status_frame.pack(fill="x", padx=10, pady=5)
        self.status_label = ttk.Label(self.status_frame, text="", foreground="green")
        self.status_label.pack(side="left", padx=5)
        self.progress_bar = ttk.Progressbar(self.status_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side="left", padx=5)
        
        # 策略导入区域
        self.strategy_frame = ttk.LabelFrame(self.root, text="策略导入")
        self.strategy_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(self.strategy_frame, text="策略文件:").pack(side="left", padx=5)
        self.strategy_file_entry = ttk.Entry(self.strategy_frame, width=50)
        self.strategy_file_entry.pack(side="left", padx=5)
        
        ttk.Button(self.strategy_frame, text="选择策略文件", command=self.select_strategy_file).pack(side="left", padx=5)
        ttk.Button(self.strategy_frame, text="导入策略", command=self.load_strategy).pack(side="left", padx=5)
        
        self.strategy_status = tk.StringVar()
        self.strategy_status.set("未导入策略")
        ttk.Label(self.strategy_frame, textvariable=self.strategy_status).pack(side="left", padx=5)
        
        # 账户设置区域
        self.account_frame = ttk.LabelFrame(self.root, text="账户设置")
        self.account_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(self.account_frame, text="初始保证金金额:").pack(side="left", padx=5)
        self.initial_margin = tk.DoubleVar(value=1000)
        ttk.Entry(self.account_frame, textvariable=self.initial_margin, width=10).pack(side="left", padx=5)
        
        ttk.Label(self.account_frame, text="当前保证金余额:").pack(side="left", padx=5)
        self.current_margin = tk.DoubleVar(value=1000)
        ttk.Label(self.account_frame, textvariable=self.current_margin).pack(side="left", padx=5)
        
        ttk.Label(self.account_frame, text="未实现盈亏:").pack(side="left", padx=5)
        self.unrealized_profit = tk.DoubleVar(value=0)
        ttk.Label(self.account_frame, textvariable=self.unrealized_profit).pack(side="left", padx=5)
        
        # 交易规则设置
        self.trade_rule_frame = ttk.LabelFrame(self.root, text="交易规则设置")
        self.trade_rule_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(self.trade_rule_frame, text="手续费率(%):").pack(side="left", padx=5)
        self.fee_rate = tk.DoubleVar(value=0.05)
        ttk.Entry(self.trade_rule_frame, textvariable=self.fee_rate, width=10).pack(side="left", padx=5)
        
        ttk.Label(self.trade_rule_frame, text="下单模式:").pack(side="left", padx=5)
        self.order_mode = tk.StringVar(value="固定保证金模式")
        order_mode_combo = ttk.Combobox(self.trade_rule_frame, textvariable=self.order_mode, 
                                       values=["固定保证金模式", "百分比保证金模式（滚仓）"], width=20)
        order_mode_combo.pack(side="left", padx=5)
        
        self.fixed_margin_frame = ttk.Frame(self.trade_rule_frame)
        self.fixed_margin_frame.pack(side="left", padx=5)
        ttk.Label(self.fixed_margin_frame, text="下单保证金金额:").pack(side="left", padx=5)
        self.fixed_margin = tk.DoubleVar(value=100)
        ttk.Entry(self.fixed_margin_frame, textvariable=self.fixed_margin, width=10).pack(side="left", padx=5)
        
        self.percentage_margin_frame = ttk.Frame(self.trade_rule_frame)
        self.percentage_margin_frame.pack(side="left", padx=5)
        ttk.Label(self.percentage_margin_frame, text="下单保证金百分比(%):").pack(side="left", padx=5)
        self.percentage_margin = tk.DoubleVar(value=10)
        ttk.Entry(self.percentage_margin_frame, textvariable=self.percentage_margin, width=10).pack(side="left", padx=5)
        self.percentage_margin_frame.pack_forget()
        
        ttk.Label(self.trade_rule_frame, text="杠杆倍数:").pack(side="left", padx=5)
        self.leverage = tk.DoubleVar(value=10)
        ttk.Entry(self.trade_rule_frame, textvariable=self.leverage, width=10).pack(side="left", padx=5)
        
        ttk.Label(self.trade_rule_frame, text="预计手续费:").pack(side="left", padx=5)
        self.expected_fee = tk.DoubleVar(value=0)
        ttk.Label(self.trade_rule_frame, textvariable=self.expected_fee).pack(side="left", padx=5)
        
        ttk.Label(self.trade_rule_frame, text="预计控制资金:").pack(side="left", padx=5)
        self.expected_control_funds = tk.DoubleVar(value=0)
        ttk.Label(self.trade_rule_frame, textvariable=self.expected_control_funds).pack(side="left", padx=5)
        
        # 绑定事件
        self.order_mode.trace("w", self.update_order_mode)
        self.fixed_margin.trace("w", self.calculate_order_params)
        self.percentage_margin.trace("w", self.calculate_order_params)
        self.leverage.trace("w", self.calculate_order_params)
        self.initial_margin.trace("w", self.calculate_order_params)
        
        # 预热传参模型
        self.param_frame = ttk.LabelFrame(self.root, text="参数设置")
        self.param_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(self.param_frame, text="传参模型:").pack(side="left", padx=5)
        self.param_model = tk.StringVar(value="开高低收")
        param_model_combo = ttk.Combobox(self.param_frame, textvariable=self.param_model,
                                        values=["开高低收", "开低高收", "仅收盘价"], width=10)  # 增加"仅收盘价"选项
        param_model_combo.pack(side="left", padx=5)
        
        # 输出区域
        self.output_frame = ttk.LabelFrame(self.root, text="输出日志")
        self.output_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.output_text = tk.Text(self.output_frame, height=10)
        self.output_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(self.output_frame, command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)
        
        # 订单列表
        self.order_list_frame = ttk.LabelFrame(self.root, text="交易订单列表")
        self.order_list_frame.pack(fill="x", padx=10, pady=5)

    def open_admin_panel(self):
        if self.admin_panel_window and self.admin_panel_window.winfo_exists():
            self.admin_panel_window.lift()
            return

        self.admin_panel_window = tk.Toplevel(self.root)
        self.admin_panel_window.title("管理后台")
        self.admin_panel = AdminPanel(
            self.admin_panel_window,
            self.master_api_key,
            self.master_api_secret,
            on_pairs_changed=self.refresh_allowed_pairs,
        )
        self.admin_panel_window.protocol("WM_DELETE_WINDOW", self.close_admin_panel)

    def close_admin_panel(self):
        if self.admin_panel_window and self.admin_panel_window.winfo_exists():
            self.admin_panel_window.destroy()
        self.admin_panel_window = None
        self.admin_panel = None

    def refresh_allowed_pairs(self, show_message: bool = False):
        pairs = get_allowed_pairs()
        if not pairs:
            pairs = self.default_symbols

        self.symbols = pairs
        if hasattr(self, "symbol_combo"):
            current_symbol = self.symbol_var.get()
            self.symbol_combo["values"] = self.symbols
            if current_symbol not in self.symbols and self.symbols:
                self.symbol_var.set(self.symbols[0])
        if show_message:
            messagebox.showinfo("提示", "交易对列表已刷新")

    def create_backtest_widgets(self):
        # 回测专用控制按钮
        self.backtest_control_frame = ttk.LabelFrame(self.root, text="回测控制")
        self.backtest_control_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(self.backtest_control_frame, text="开始回测", command=self.start_backtest).pack(side="left", padx=5)
        ttk.Button(self.backtest_control_frame, text="停止回测", command=self.stop_backtest).pack(side="left", padx=5)
        
        # 强平设置
        self.liquidation_frame = ttk.Frame(self.backtest_control_frame)
        self.liquidation_frame.pack(side="left", padx=20)
        self.enable_liquidation = tk.IntVar(value=1)
        ttk.Checkbutton(self.liquidation_frame, text="启用强平机制", variable=self.enable_liquidation).pack(side="left")
        
        # 回测结果
        self.backtest_result_frame = ttk.LabelFrame(self.root, text="回测结果")
        self.backtest_result_frame.pack(fill="x", padx=10, pady=5)
        
        self.backtest_result = {
            "初始金额": 0, "结算金额": 0, "收益率": 0,
            "最大回撤": 0, "夏普比率": 0, "标准差": 0,
            "交易次数": 0, "胜率": 0, "最大盈利": 0, "最大亏损": 0
        }
        
        self.backtest_result_labels = {}
        result_frame = ttk.Frame(self.backtest_result_frame)
        result_frame.pack(fill="x", padx=10, pady=5)
        
        for i, key in enumerate(self.backtest_result.keys()):
            ttk.Label(result_frame, text=f"{key}:").grid(row=i//4, column=i%4*2, padx=5, pady=2, sticky="w")
            label = ttk.Label(result_frame, text="0")
            label.grid(row=i//4, column=i%4*2+1, padx=5, pady=2, sticky="w")
            self.backtest_result_labels[key] = label
        
        # 回测订单表格
        columns = ("序列", "时间", "操作", "币种", "盈亏", "保证金", "控制资金", "开仓价", "平仓价", "手续费")
        self.backtest_order_tree = ttk.Treeview(self.order_list_frame, columns=columns, show="headings")
        for col in columns:
            self.backtest_order_tree.heading(col, text=col)
            width = 150 if col == "时间" else 100
            self.backtest_order_tree.column(col, width=width)
    
    def create_simulation_widgets(self):
        # 实测专用控制按钮
        self.simulation_control_frame = ttk.LabelFrame(self.root, text="实测控制")
        self.simulation_control_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(self.simulation_control_frame, text="开始盘前预热", command=self.preheat).pack(side="left", padx=5)
        self.start_monitor_btn = ttk.Button(self.simulation_control_frame, text="开始监控价格", command=self.start_price_monitor)
        self.start_monitor_btn.pack(side="left", padx=5)
        self.stop_monitor_btn = ttk.Button(self.simulation_control_frame, text="停止监控价格", command=self.stop_price_monitor, state=tk.DISABLED)
        self.stop_monitor_btn.pack(side="left", padx=5)
        
        # 实测结果
        self.simulation_result_frame = ttk.LabelFrame(self.root, text="实测结果")
        self.simulation_result_frame.pack(fill="x", padx=10, pady=5)
        
        self.simulation_result = {
            "已运行时长": 0, "已获取数据条数": 0, "初始金额": 0,
            "当前保证金余额": 0, "未实现盈亏": 0, "总权益": 0,
            "收益率": 0, "最大回撤": 0, "夏普比率": 0, "标准差": 0
        }
        
        self.simulation_result_labels = {}
        result_frame = ttk.Frame(self.simulation_result_frame)
        result_frame.pack(fill="x", padx=10, pady=5)
        
        for i, key in enumerate(self.simulation_result.keys()):
            ttk.Label(result_frame, text=f"{key}:").grid(row=i//4, column=i%4*2, padx=5, pady=2, sticky="w")
            label = ttk.Label(result_frame, text="0")
            label.grid(row=i//4, column=i%4*2+1, padx=5, pady=2, sticky="w")
            self.simulation_result_labels[key] = label
        
        # 实测订单表格
        columns = ("序列", "时间", "操作", "币种", "平仓盈亏", "保证金", "控制资金", "开仓价", "当前价", "平仓价", "手续费", "未实现盈亏")
        self.simulation_order_tree = ttk.Treeview(self.order_list_frame, columns=columns, show="headings")
        for col in columns:
            self.simulation_order_tree.heading(col, text=col)
            width = 150 if col == "时间" else 100
            self.simulation_order_tree.column(col, width=width)
    
    def create_live_widgets(self):
        # 实盘API设置
        self.api_frame = ttk.LabelFrame(self.root, text="币安API设置")
        self.api_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(self.api_frame, text="API Key:").pack(side="left", padx=5)
        self.api_key = tk.StringVar()
        ttk.Entry(self.api_frame, textvariable=self.api_key, width=40).pack(side="left", padx=5)
        
        ttk.Label(self.api_frame, text="API Secret:").pack(side="left", padx=5)
        self.api_secret = tk.StringVar()
        ttk.Entry(self.api_frame, textvariable=self.api_secret, width=40, show="*").pack(side="left", padx=5)
        
        ttk.Button(self.api_frame, text="绑定API", command=self.bind_api).pack(side="left", padx=5)
        ttk.Button(self.api_frame, text="刷新账户", command=self.update_account_info).pack(side="left", padx=5)
        
        # 实盘控制按钮
        self.live_control_frame = ttk.LabelFrame(self.root, text="实盘控制")
        self.live_control_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(self.live_control_frame, text="开始实盘交易", command=self.start_live_trading).pack(side="left", padx=5)
        self.stop_live_btn = ttk.Button(self.live_control_frame, text="停止实盘交易", command=self.stop_live_trading, state=tk.DISABLED)
        self.stop_live_btn.pack(side="left", padx=5)
        
        # 双向持仓设置
        self.dspc = tk.Checkbutton(self.live_control_frame, text="启用双向持仓模式", variable=tk.BooleanVar(value=False), command=self.toggle_dual_position)
        self.dspc.pack(side="left", padx=20)
        
        # 实盘结果
        self.live_result_frame = ttk.LabelFrame(self.root, text="实盘结果")
        self.live_result_frame.pack(fill="x", padx=10, pady=5)
        
        self.live_result = {
            "已运行时长": 0, "交易次数": 0, "初始金额": 0,
            "当前保证金余额": 0, "未实现盈亏": 0, "总权益": 0,
            "收益率": 0, "最大回撤": 0
        }
        
        self.live_result_labels = {}
        result_frame = ttk.Frame(self.live_result_frame)
        result_frame.pack(fill="x", padx=10, pady=5)
        
        for i, key in enumerate(self.live_result.keys()):
            ttk.Label(result_frame, text=f"{key}:").grid(row=i//4, column=i%4*2, padx=5, pady=2, sticky="w")
            label = ttk.Label(result_frame, text="0")
            label.grid(row=i//4, column=i%4*2+1, padx=5, pady=2, sticky="w")
            self.live_result_labels[key] = label
        
        # 实盘订单表格
        columns = ("序列", "时间", "操作", "币种", "盈亏", "保证金", "控制资金", "开仓价", "平仓价", "手续费", "订单状态")
        self.live_order_tree = ttk.Treeview(self.order_list_frame, columns=columns, show="headings")
        for col in columns:
            self.live_order_tree.heading(col, text=col)
            width = 150 if col == "时间" else 100
            self.live_order_tree.column(col, width=width)
        
        # 实盘相关变量
        self.binance_client = None
        self.live_trading_running = False
        self.live_thread = None
    
    def switch_engine(self, mode):
        """切换引擎模式"""
        self.engine_mode = mode
        
        # 更新按钮状态
        self.backtest_btn.config(state=tk.NORMAL if mode != 0 else tk.DISABLED)
        self.simulation_btn.config(state=tk.NORMAL if mode != 1 else tk.DISABLED)
        self.live_btn.config(state=tk.NORMAL if mode != 2 else tk.DISABLED)
        
        # 隐藏所有专用框架
        self.backtest_control_frame.pack_forget()
        self.backtest_result_frame.pack_forget()
        self.simulation_control_frame.pack_forget()
        self.simulation_result_frame.pack_forget()
        self.api_frame.pack_forget()
        self.live_control_frame.pack_forget()
        self.live_result_frame.pack_forget()
        
        # 清空订单表格
        for widget in self.order_list_frame.winfo_children():
            widget.pack_forget()
        
        # 根据模式显示相应的框架
        if mode == 0:  # 回测
            self.backtest_control_frame.pack(fill="x", padx=10, pady=5)
            self.backtest_result_frame.pack(fill="x", padx=10, pady=5)
            self.backtest_order_tree.pack(fill="both", expand=True)
        elif mode == 1:  # 实测
            self.simulation_control_frame.pack(fill="x", padx=10, pady=5)
            self.simulation_result_frame.pack(fill="x", padx=10, pady=5)
            self.simulation_order_tree.pack(fill="both", expand=True)
        elif mode == 2:  # 实盘
            self.api_frame.pack(fill="x", padx=10, pady=5)
            self.live_control_frame.pack(fill="x", padx=10, pady=5)
            self.live_result_frame.pack(fill="x", padx=10, pady=5)
            self.live_order_tree.pack(fill="both", expand=True)
    
    def update_order_mode(self, *args):
        """更新订单模式显示"""
        if self.order_mode.get() == "固定保证金模式":
            self.fixed_margin_frame.pack(side="left", padx=5)
            self.percentage_margin_frame.pack_forget()
        else:
            self.fixed_margin_frame.pack_forget()
            self.percentage_margin_frame.pack(side="left", padx=5)
        self.calculate_order_params()
    
    def calculate_order_params(self, *args):
        """计算订单参数"""
        try:
            if self.order_mode.get() == "固定保证金模式":
                order_margin = self.fixed_margin.get()
            else:
                order_margin = self.initial_margin.get() * (self.percentage_margin.get() / 100)
            
            leverage = self.leverage.get()
            fee_rate = self.fee_rate.get() / 100
            
            actual_control_funds = order_margin * leverage
            fee = actual_control_funds * fee_rate
            
            self.expected_fee.set(round(fee, 4))
            self.expected_control_funds.set(round(actual_control_funds, 2))
        except:
            pass
    
    def select_strategy_file(self):
        """选择策略文件"""
        file_path = filedialog.askopenfilename(filetypes=[("Python Files", "*.py")])
        if file_path:
            self.strategy_file_entry.delete(0, tk.END)
            self.strategy_file_entry.insert(0, file_path)
    
    def load_strategy(self):
        """加载策略文件"""
        file_path = self.strategy_file_entry.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "请选择有效的策略文件")
            return
        
        try:
            code = None
            encodings = ['utf-8', 'gbk', 'latin-1', 'utf-16']
            used_encoding = None
            
            # 尝试多种编码格式打开文件
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        code = f.read()
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    messagebox.showerror("错误", f"读取文件时出错: {str(e)}")
                    return
            
            # 检查是否成功读取文件
            if code is None:
                messagebox.showerror("错误", "无法使用任何支持的编码格式读取文件，请将文件保存为UTF-8格式后重试")
                return
            elif code == '':
                messagebox.showerror("错误", "文件内容为空")
                return
            else:
                self.output_text.insert(tk.END, f"成功使用 {used_encoding} 编码读取文件\n")
            
            namespace = {}
            exec(code, namespace)
            
            if 'trade_signal' in namespace:
                self.strategy = namespace['trade_signal']
                self.strategy_name = os.path.basename(file_path)
                self.strategy_status.set(f"已导入: {self.strategy_name}")
                self.output_text.insert(tk.END, f"成功导入策略: {self.strategy_name}\n")
            else:
                messagebox.showerror("错误", "策略文件中未找到 trade_signal 函数")
                self.strategy_status.set("导入失败: 缺少trade_signal函数")
                
        except Exception as e:
            messagebox.showerror("错误", f"导入策略时出错: {str(e)}")
            self.strategy_status.set(f"导入失败: {str(e)}")
    
    def fetch_data(self):
        """从币安获取K线数据"""
        if not self.symbol_var.get() or not self.interval_var.get():
            messagebox.showerror("错误", "请选择交易对和时间周期")
            return
        
        self.status_label.config(text="正在获取数据...")
        self.progress_bar["value"] = 10
        self.root.update_idletasks()
        
        try:
            symbol = self.symbol_var.get()
            interval = self.interval_var.get()
            
            # 转换为Binance API所需的时间格式
            try:
                start_time = datetime.strptime(self.start_date_var.get(), "%Y-%m-%d %H:%M:%S")
                end_time = datetime.strptime(self.end_date_var.get(), "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                self.status_label.config(text=f"时间格式错误: {str(e)}", foreground="red")
                self.progress_bar["value"] = 0
                return
            
            # 确保开始时间早于结束时间
            if start_time >= end_time:
                self.status_label.config(text="开始时间必须早于结束时间", foreground="red")
                self.progress_bar["value"] = 0
                return
            
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            # 映射到Binance的时间间隔常量
            interval_mapping = {
                "1m": Client.KLINE_INTERVAL_1MINUTE,
                "3m": Client.KLINE_INTERVAL_3MINUTE,
                "5m": Client.KLINE_INTERVAL_5MINUTE,
                "15m": Client.KLINE_INTERVAL_15MINUTE,
                "30m": Client.KLINE_INTERVAL_30MINUTE,
                "1h": Client.KLINE_INTERVAL_1HOUR,
                "4h": Client.KLINE_INTERVAL_4HOUR,
                "1d": Client.KLINE_INTERVAL_1DAY,
                "1w": Client.KLINE_INTERVAL_1WEEK
            }
            
            binance_interval = interval_mapping.get(interval, Client.KLINE_INTERVAL_1HOUR)
            
            # 调用币安API获取数据（处理分页）
            url = "https://fapi.binance.com/fapi/v1/klines"
            limit = 1500  # 最大限制
            all_data = []
            current_start = start_timestamp
            total_points = 0
            
            # 计算时间间隔的毫秒数
            interval_ms = {
                "1m": 60 * 1000,
                "3m": 3 * 60 * 1000,
                "5m": 5 * 60 * 1000,
                "15m": 15 * 60 * 1000,
                "30m": 30 * 60 * 1000,
                "1h": 60 * 60 * 1000,
                "4h": 4 * 60 * 60 * 1000,
                "1d": 24 * 60 * 60 * 1000,
                "1w": 7 * 24 * 60 * 60 * 1000
            }.get(interval, 60 * 60 * 1000)
            
            # 计算总点数以更新进度
            total_expected = (end_timestamp - start_timestamp) // interval_ms
            if total_expected <= 0:
                self.status_label.config(text="时间范围过小，无法获取数据", foreground="red")
                self.progress_bar["value"] = 0
                return
            
            while current_start < end_timestamp:
                # 计算本次请求的结束时间
                current_end = min(current_start + limit * interval_ms, end_timestamp)
                
                params = {
                    "symbol": symbol,
                    "interval": binance_interval,
                    "startTime": current_start,
                    "endTime": current_end,
                    "limit": limit
                }
                
                try:
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()  # 抛出HTTP错误状态码
                    data = response.json()
                    
                    if not data:
                        break
                        
                    all_data.extend(data)
                    total_points += len(data)
                    
                    # 更新进度
                    progress = min(90 * total_points / total_expected + 10, 95)
                    self.progress_bar["value"] = progress
                    self.root.update_idletasks()
                    
                    # 准备下一次请求
                    current_start = data[-1][6] + 1  # 使用最后一个数据点的close_time
                    
                    # 避免请求过于频繁
                    time.sleep(0.1)
                    
                except requests.exceptions.RequestException as e:
                    self.status_label.config(text=f"网络请求错误: {str(e)}", foreground="red")
                    self.progress_bar["value"] = 0
                    return
                except Exception as e:
                    self.status_label.config(text=f"处理数据时出错: {str(e)}", foreground="red")
                    self.progress_bar["value"] = 0
                    return
            
            if not all_data:
                self.status_label.config(text="未获取到数据", foreground="red")
                self.progress_bar["value"] = 0
                return
            
            # 处理数据
            df = pd.DataFrame(all_data, columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
            ])
            
            # 转换数据类型
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("timestamp")
            numeric_columns = ["open", "high", "low", "close", "volume"]
            df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
            
            # 移除无效数据行
            df = df.dropna(subset=numeric_columns)
            
            # 去重
            df = df[~df.index.duplicated(keep='last')]
            
            self.df = df
            self.data_queue.clear()
            
            # 更新状态
            self.status_label.config(text=f"成功获取 {len(df)} 条数据", foreground="green")
            self.progress_bar["value"] = 100
            self.output_text.insert(tk.END, f"成功获取 {symbol} {interval} 数据，共 {len(df)} 条\n")
            
        except Exception as e:
            self.status_label.config(text=f"获取数据失败: {str(e)}", foreground="red")
            self.progress_bar["value"] = 0
            self.output_text.insert(tk.END, f"获取数据失败: {str(e)}\n")
    
    def start_backtest(self):
        """开始回测"""
        if self.strategy is None:
            messagebox.showerror("错误", "请先导入策略")
            return
        
        if self.df.empty:
            self.fetch_data()
            if self.df.empty:
                return
        
        # 初始化回测参数
        self.initial_margin_val = self.initial_margin.get()
        self.current_margin.set(self.initial_margin_val)
        self.order_list = []
        self.trade_orders = []
        self.order_sequence = 1
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, f"{self.strategy_name} 回测开始...\n")
        
        # 清空订单表格
        for item in self.backtest_order_tree.get_children():
            self.backtest_order_tree.delete(item)
        

        processed_data = []
        for index, row in self.df.iterrows():
            time_str = index.strftime("%Y-%m-%d %H:%M:%S")
            if self.param_model.get() == "开高低收":
                processed_data.extend([
                    (f"{time_str} open", row['open']),
                    (f"{time_str} high", row['high']),
                    (f"{time_str} low", row['low']),
                    (f"{time_str} close", row['close'])
                ])
            elif self.param_model.get() == "开低高收":  # 修改为elif结构
                processed_data.extend([
                    (f"{time_str} open", row['open']),
                    (f"{time_str} low", row['low']),
                    (f"{time_str} high", row['high']),
                    (f"{time_str} close", row['close'])
                ])
            else:  # 仅收盘价模型
                processed_data.extend([
                    (f"{time_str} close", row['close'])  # 只添加收盘价数据
                ])

        
        # 执行回测
        margin_max = self.initial_margin_val
        margin_min = self.initial_margin_val
        backtest_running = True
        
        for time, price in processed_data:
            if not backtest_running:
                break
                
            try:
                signal = self.strategy(time, price)
                self.output_text.insert(tk.END, f"{time}，价格: {price}，信号: {signal}\n")
                
                if signal in ["做多", "做空"]:
                    # 计算订单保证金
                    if self.order_mode.get() == "固定保证金模式":
                        order_margin = self.fixed_margin.get()
                    else:
                        percent = self.percentage_margin.get() / 100
                        order_margin = self.current_margin.get() * percent
                    
                    # 检查保证金是否充足
                    if self.current_margin.get() < order_margin:
                        self.output_text.insert(tk.END, "保证金不足，无法开仓\n")
                        continue
                    
                    # 计算手续费和控制资金
                    leverage = self.leverage.get()
                    fee_rate = self.fee_rate.get() / 100
                    fee = order_margin * leverage * fee_rate
                    actual_control_funds = order_margin * leverage
                    
                    # 计算强平价格
                    liquidation_price = self.calculate_liquidation_price(
                        signal, price, self.current_margin.get(), leverage)
                    
                    # 更新保证金
                    new_margin = self.current_margin.get() - order_margin - fee
                    self.current_margin.set(round(new_margin, 4))
                    
                    # 更新最大最小保证金
                    margin_max = max(margin_max, new_margin)
                    margin_min = min(margin_min, new_margin)
                    
                    # 记录订单
                    self.order_list.append({
                        "sequence": self.order_sequence,
                        "time": time,
                        "action": signal,
                        "symbol": self.symbol_var.get(),
                        "margin": order_margin,
                        "leverage": leverage,
                        "fee": fee,
                        "actual_control_funds": actual_control_funds,
                        "open_price": price,
                        "liquidation_price": liquidation_price
                    })
                    
                    # 输出日志
                    mode_text = "固定保证金" if self.order_mode.get() == "固定保证金模式" else f"百分比保证金({self.percentage_margin.get()}%)"
                    self.output_text.insert(tk.END, 
                        f"订单 {self.order_sequence}: {signal}，价格 {price}，保证金 {order_margin}，杠杆 {leverage}，手续费 {fee}，控制资金 {actual_control_funds}，强平价 {liquidation_price}\n")
                    
                    self.order_sequence += 1
                
                elif signal in ["平多", "平空"]:
                    # 平仓处理
                    for order in self.order_list.copy():
                        if (signal == "平多" and order["action"] == "做多") or (signal == "平空" and order["action"] == "做空"):
                            # 计算盈亏和手续费
                            fee = order["actual_control_funds"] * fee_rate
                            profit = self.calculate_profit(
                                order["action"], order["open_price"], price, order["actual_control_funds"])
                            
                            # 更新保证金
                            new_margin = self.current_margin.get() + order["margin"] + profit - fee
                            self.current_margin.set(round(new_margin, 4))
                            
                            # 更新最大最小保证金
                            margin_max = max(margin_max, new_margin)
                            margin_min = min(margin_min, new_margin)
                            
                            # 记录平仓订单
                            self.trade_orders.append({
                                "sequence": order["sequence"],
                                "time": time,
                                "action": signal,
                                "symbol": self.symbol_var.get(),
                                "profit": profit,
                                "margin": order["margin"],
                                "actual_control_funds": order["actual_control_funds"],
                                "open_price": order["open_price"],
                                "close_price": price,
                                "total_fee": order["fee"] + fee
                            })
                            
                            # 添加到表格
                            self.backtest_order_tree.insert('', 'end', values=(
                                order["sequence"], time, signal, self.symbol_var.get(),
                                round(profit, 4), round(order["margin"], 4),
                                round(order["actual_control_funds"], 4),
                                round(order["open_price"], 4), round(price, 4),
                                round(order["fee"] + fee, 4)
                            ))
                            
                            # 输出日志
                            self.output_text.insert(tk.END, 
                                f"订单 {order['sequence']}: {signal}，平仓价 {price}，盈亏 {profit}，手续费 {order['fee'] + fee}，余额 {self.current_margin.get()}\n")
                            
                            self.order_list.remove(order)
                            break
                
                # 检查强平
                if self.enable_liquidation.get() == 1:
                    for order in self.order_list.copy():
                        if (order["action"] == "做多" and price <= order["liquidation_price"]) or \
                           (order["action"] == "做空" and price >= order["liquidation_price"]):
                            
                            # 计算强平盈亏和手续费
                            fee = order["actual_control_funds"] * fee_rate
                            profit = self.calculate_profit(
                                order["action"], order["open_price"], price, order["actual_control_funds"])
                            
                            # 更新保证金
                            new_margin = self.current_margin.get() + order["margin"] + profit - fee
                            self.current_margin.set(round(new_margin, 4))
                            
                            # 更新最大最小保证金
                            margin_max = max(margin_max, new_margin)
                            margin_min = min(margin_min, new_margin)
                            
                            # 记录强平订单
                            self.trade_orders.append({
                                "sequence": order["sequence"],
                                "time": time,
                                "action": f"强平{order['action'][:-1]}",
                                "symbol": self.symbol_var.get(),
                                "profit": profit,
                                "margin": order["margin"],
                                "actual_control_funds": order["actual_control_funds"],
                                "open_price": order["open_price"],
                                "close_price": price,
                                "total_fee": order["fee"] + fee
                            })
                            
                            # 添加到表格
                            self.backtest_order_tree.insert('', 'end', values=(
                                order["sequence"], time, f"强平{order['action'][:-1]}", self.symbol_var.get(),
                                round(profit, 4), round(order["margin"], 4),
                                round(order["actual_control_funds"], 4),
                                round(order["open_price"], 4), round(price, 4),
                                round(order["fee"] + fee, 4)
                            ))
                            
                            # 输出日志
                            self.output_text.insert(tk.END, 
                                f"订单 {order['sequence']}: 强平{order['action'][:-1]}，价格 {price}，盈亏 {profit}，余额 {self.current_margin.get()}\n")
                            
                            self.order_list.remove(order)
                            
                            # 检查是否爆仓
                            if self.current_margin.get() <= 0:
                                self.output_text.insert(tk.END, "账户爆仓，回测结束\n")
                                backtest_running = False
                                break
                
                # 检查是否爆仓
                if self.current_margin.get() <= 0:
                    self.output_text.insert(tk.END, "账户爆仓，回测结束\n")
                    backtest_running = False
                    break
                
                # 刷新界面
                self.root.update_idletasks()
                
            except Exception as e:
                self.output_text.insert(tk.END, f"回测过程出错: {str(e)}\n")
                break
        
        # 计算回测结果
        self.calculate_backtest_result(margin_max, margin_min)
        self.output_text.insert(tk.END, "回测完成\n")
    
    def stop_backtest(self):
        """停止回测"""
        # 在实际实现中，需要设置一个标志位来终止回测循环
        self.output_text.insert(tk.END, "回测已停止\n")
    
    def calculate_liquidation_price(self, action, entry_price, margin, leverage):
        """计算强平价格"""
        try:
            if action == "做多":
                return entry_price * (1 - (margin * leverage) / (margin * leverage + margin))
            else:  # 做空
                return entry_price * (1 + (margin * leverage) / (margin * leverage + margin))
        except:
            return 0
    
    def calculate_profit(self, action, open_price, close_price, control_funds):
        """计算盈亏"""
        if action == "做多":
            return control_funds * (close_price - open_price) / open_price
        else:  # 做空
            return control_funds * (open_price - close_price) / open_price
    
    def calculate_backtest_result(self, margin_max, margin_min):
        """计算回测结果"""
        final_margin = self.current_margin.get()
        initial = self.initial_margin_val
        
        # 计算基本结果
        self.backtest_result["初始金额"] = round(initial, 2)
        self.backtest_result["结算金额"] = round(final_margin, 2)
        self.backtest_result["收益率"] = round((final_margin - initial) / initial * 100, 2) if initial != 0 else 0
        self.backtest_result["最大回撤"] = round((initial - margin_min) / initial * 100, 2) if initial != 0 else 0
        self.backtest_result["交易次数"] = len(self.trade_orders)
        
        # 计算胜率
        winning_trades = [t for t in self.trade_orders if t["profit"] > 0]
        self.backtest_result["胜率"] = round(len(winning_trades) / len(self.trade_orders) * 100, 2) if self.trade_orders else 0
        
        # 计算最大盈利和亏损
        if self.trade_orders:
            self.backtest_result["最大盈利"] = round(max(t["profit"] for t in self.trade_orders), 2)
            self.backtest_result["最大亏损"] = round(min(t["profit"] for t in self.trade_orders), 2)
        
        # 计算夏普比率和标准差（简化版）
        if len(self.trade_orders) >= 2:
            profits = [t["profit"] for t in self.trade_orders]
            mean_profit = sum(profits) / len(profits)
            std_dev = math.sqrt(sum((p - mean_profit) **2 for p in profits) / len(profits))
            self.backtest_result["标准差"] = round(std_dev, 4)
            self.backtest_result["夏普比率"] = round(mean_profit / std_dev * math.sqrt(252), 2) if std_dev != 0 else 0
        
        # 更新界面
        for key, value in self.backtest_result.items():
            self.backtest_result_labels[key].config(text=f"{value}{'%' if key in ['收益率', '最大回撤', '胜率'] else ''}")
    
    def preheat(self):
        """盘前预热"""
        if self.strategy is None:
            messagebox.showerror("错误", "请先导入策略")
            return
        
        if self.df.empty:
            self.fetch_data()
            if self.df.empty:
                return
        
        self.output_text.insert(tk.END, "开始盘前预热...\n")
        
        # 处理数据并预热策略
        processed_data = []
        for index, row in self.df.iterrows():
            time_str = index.strftime("%Y-%m-%d %H:%M:%S")
            if self.param_model.get() == "开高低收":
                processed_data.extend([
                    (f"{time_str} open", row['open']),
                    (f"{time_str} high", row['high']),
                    (f"{time_str} low", row['low']),
                    (f"{time_str} close", row['close'])
                ])
            else:
                processed_data.extend([
                    (f"{time_str} open", row['open']),
                    (f"{time_str} low", row['low']),
                    (f"{time_str} high", row['high']),
                    (f"{time_str} close", row['close'])
                ])
        
        # 执行预热
        for time, price in processed_data:
            try:
                signal = self.strategy(time, price)
            except Exception as e:
                self.output_text.insert(tk.END, f"预热过程出错: {str(e)}\n")
                return
        
        self.output_text.insert(tk.END, "盘前预热完成\n")
    
    def start_price_monitor(self):
        """开始价格监控（实测）"""
        if self.strategy is None:
            messagebox.showerror("错误", "请先导入策略")
            return
        
        self.price_monitor_running = True
        self.start_monitor_btn.config(state=tk.DISABLED)
        self.stop_monitor_btn.config(state=tk.NORMAL)
        
        # 初始化参数
        self.current_margin.set(self.initial_margin.get())
        self.order_list = []
        self.trade_orders = []
        self.order_sequence = 1
        self.start_time = datetime.now()
        self.data_count = 0
        
        # 清空订单表格
        for item in self.simulation_order_tree.get_children():
            self.simulation_order_tree.delete(item)
        
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "开始价格监控和模拟交易...\n")
        
        # 启动监控线程
        threading.Thread(target=self.price_monitor_thread, daemon=True).start()
        # 启动结果更新线程
        threading.Thread(target=self.update_simulation_results_thread, daemon=True).start()
    
    def stop_price_monitor(self):
        """停止价格监控"""
        self.price_monitor_running = False
        self.start_monitor_btn.config(state=tk.NORMAL)
        self.stop_monitor_btn.config(state=tk.DISABLED)
        self.output_text.insert(tk.END, "已停止价格监控\n")
    
    def price_monitor_thread(self):
        """价格监控线程"""
        symbol = self.symbol_var.get()
        interval = self.interval_var.get()
        
        interval_seconds = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800
        }.get(interval, 3600)
        
        while self.price_monitor_running:
            try:
                # 获取最新价格数据
                url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
                response = requests.get(url)
                data = response.json()
                
                if "price" in data:
                    price = float(data["price"])
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.data_count += 1
                    
                    # 处理交易信号
                    signal = self.strategy(current_time, price)
                    self.output_text.insert(tk.END, f"{current_time}，价格: {price}，信号: {signal}\n")
                    self.output_text.see(tk.END)
                    
                    # 处理交易信号
                    if signal in ["做多", "做空"]:
                        # 计算订单保证金
                        if self.order_mode.get() == "固定保证金模式":
                            order_margin = self.fixed_margin.get()
                        else:
                            percent = self.percentage_margin.get() / 100
                            order_margin = self.current_margin.get() * percent
                        
                        # 检查保证金是否充足
                        if self.current_margin.get() < order_margin:
                            self.output_text.insert(tk.END, "保证金不足，无法开仓\n")
                            self.output_text.see(tk.END)
                            time.sleep(interval_seconds)
                            continue
                        
                        # 计算手续费和控制资金
                        leverage = self.leverage.get()
                        fee_rate = self.fee_rate.get() / 100
                        fee = order_margin * leverage * fee_rate
                        actual_control_funds = order_margin * leverage
                        
                        # 计算强平价格
                        liquidation_price = self.calculate_liquidation_price(
                            signal, price, self.current_margin.get(), leverage)
                        
                        # 更新保证金
                        new_margin = self.current_margin.get() - order_margin - fee
                        self.current_margin.set(round(new_margin, 4))
                        
                        # 记录订单
                        self.order_list.append({
                            "sequence": self.order_sequence,
                            "time": current_time,
                            "action": signal,
                            "symbol": symbol,
                            "margin": order_margin,
                            "leverage": leverage,
                            "fee": fee,
                            "actual_control_funds": actual_control_funds,
                            "open_price": price,
                            "liquidation_price": liquidation_price
                        })
                        
                        # 输出日志
                        self.output_text.insert(tk.END, 
                            f"订单 {self.order_sequence}: {signal}，价格 {price}，保证金 {order_margin}，杠杆 {leverage}\n")
                        self.output_text.see(tk.END)
                        
                        self.order_sequence += 1
                    
                    elif signal in ["平多", "平空"]:
                        # 平仓处理
                        for order in self.order_list.copy():
                            if (signal == "平多" and order["action"] == "做多") or (signal == "平空" and order["action"] == "做空"):
                                # 计算盈亏和手续费
                                fee = order["actual_control_funds"] * fee_rate
                                profit = self.calculate_profit(
                                    order["action"], order["open_price"], price, order["actual_control_funds"])
                                
                                # 更新保证金
                                new_margin = self.current_margin.get() + order["margin"] + profit - fee
                                self.current_margin.set(round(new_margin, 4))
                                
                                # 记录平仓订单
                                self.trade_orders.append({
                                    "sequence": order["sequence"],
                                    "time": current_time,
                                    "action": signal,
                                    "symbol": symbol,
                                    "profit": profit,
                                    "margin": order["margin"],
                                    "actual_control_funds": order["actual_control_funds"],
                                    "open_price": order["open_price"],
                                    "close_price": price,
                                    "total_fee": order["fee"] + fee
                                })
                                
                                # 添加到表格
                                self.root.after(0, lambda o=order, t=current_time, p=price, pr=profit, f=order["fee"] + fee: 
                                    self.simulation_order_tree.insert('', 'end', values=(
                                        o["sequence"], t, signal, symbol,
                                        round(pr, 4), round(o["margin"], 4),
                                        round(o["actual_control_funds"], 4),
                                        round(o["open_price"], 4), p, p,
                                        round(f, 4), 0
                                    ))
                                )
                                
                                # 输出日志
                                self.output_text.insert(tk.END, 
                                    f"订单 {order['sequence']}: {signal}，平仓价 {price}，盈亏 {profit}，余额 {self.current_margin.get()}\n")
                                self.output_text.see(tk.END)
                                
                                self.order_list.remove(order)
                                break
                
                # 检查强平
                for order in self.order_list.copy():
                    if (order["action"] == "做多" and price <= order["liquidation_price"]) or \
                       (order["action"] == "做空" and price >= order["liquidation_price"]):
                        
                        # 计算强平盈亏和手续费
                        fee = order["actual_control_funds"] * fee_rate
                        profit = self.calculate_profit(
                            order["action"], order["open_price"], price, order["actual_control_funds"])
                        
                        # 更新保证金
                        new_margin = self.current_margin.get() + order["margin"] + profit - fee
                        self.current_margin.set(round(new_margin, 4))
                        
                        # 记录强平订单
                        self.trade_orders.append({
                            "sequence": order["sequence"],
                            "time": current_time,
                            "action": f"强平{order['action'][:-1]}",
                            "symbol": symbol,
                            "profit": profit,
                            "margin": order["margin"],
                            "actual_control_funds": order["actual_control_funds"],
                            "open_price": order["open_price"],
                            "close_price": price,
                            "total_fee": order["fee"] + fee
                        })
                        
                        # 添加到表格
                        self.root.after(0, lambda o=order, t=current_time, p=price, pr=profit, f=order["fee"] + fee: 
                            self.simulation_order_tree.insert('', 'end', values=(
                                o["sequence"], t, f"强平{o['action'][:-1]}", symbol,
                                round(pr, 4), round(o["margin"], 4),
                                round(o["actual_control_funds"], 4),
                                round(o["open_price"], 4), p, p,
                                round(f, 4), 0
                            ))
                        )
                        
                        # 输出日志
                        self.output_text.insert(tk.END, 
                            f"订单 {order['sequence']}: 强平{order['action'][:-1]}，价格 {price}，盈亏 {profit}，余额 {self.current_margin.get()}\n")
                        self.output_text.see(tk.END)
                        
                        self.order_list.remove(order)
                        
                        # 检查是否爆仓
                        if self.current_margin.get() <= 0:
                            self.output_text.insert(tk.END, "账户爆仓，停止监控\n")
                            self.output_text.see(tk.END)
                            self.price_monitor_running = False
                            break
                
                # 休眠到下一个周期
                time.sleep(interval_seconds)
                
            except Exception as e:
                self.output_text.insert(tk.END, f"监控过程出错: {str(e)}\n")
                self.output_text.see(tk.END)
                time.sleep(5)
    
    def update_simulation_results_thread(self):
        """更新实测结果线程"""
        initial_margin = self.initial_margin.get()
        margin_max = initial_margin
        margin_min = initial_margin
        
        while self.price_monitor_running:
            try:
                current_time = datetime.now()
                run_time = current_time - self.start_time
                hours = run_time.total_seconds() / 3600
                
                current_margin_val = self.current_margin.get()
                margin_max = max(margin_max, current_margin_val)
                margin_min = min(margin_min, current_margin_val)
                
                # 计算未实现盈亏
                unrealized = 0
                for order in self.order_list:
                    if order["action"] == "做多":
                        unrealized += self.calculate_profit(
                            "做多", order["open_price"], float(self.get_current_price()), order["actual_control_funds"])
                    else:
                        unrealized += self.calculate_profit(
                            "做空", order["open_price"], float(self.get_current_price()), order["actual_control_funds"])
                
                self.unrealized_profit.set(round(unrealized, 4))
                total_equity = current_margin_val + unrealized
                
                # 计算收益率
                return_rate = (current_margin_val - initial_margin) / initial_margin * 100 if initial_margin != 0 else 0
                
                # 计算最大回撤
                max_drawdown = (initial_margin - margin_min) / initial_margin * 100 if initial_margin != 0 else 0
                
                # 更新结果
                self.simulation_result["已运行时长"] = f"{int(run_time.total_seconds() // 3600)}h{int((run_time.total_seconds() % 3600) // 60)}m"
                self.simulation_result["已获取数据条数"] = self.data_count
                self.simulation_result["初始金额"] = round(initial_margin, 2)
                self.simulation_result["当前保证金余额"] = round(current_margin_val, 2)
                self.simulation_result["未实现盈亏"] = round(unrealized, 2)
                self.simulation_result["总权益"] = round(total_equity, 2)
                self.simulation_result["收益率"] = round(return_rate, 2)
                self.simulation_result["最大回撤"] = round(max_drawdown, 2)
                
                # 更新界面
                for key, value in self.simulation_result.items():
                    self.root.after(0, lambda k=key, v=value: 
                        self.simulation_result_labels[k].config(text=f"{v}{'%' if k in ['收益率', '最大回撤'] else ''}")
                    )
                
                # 更新未平仓订单的当前价格和未实现盈亏
                current_price = float(self.get_current_price())
                for item in self.simulation_order_tree.get_children():
                    values = self.simulation_order_tree.item(item, "values")
                    if values[2] in ["做多", "做空"] and values[9] == "":  # 未平仓
                        seq = int(values[0])
                        for order in self.order_list:
                            if order["sequence"] == seq:
                                profit = self.calculate_profit(
                                    order["action"], order["open_price"], current_price, order["actual_control_funds"])
                                self.root.after(0, lambda i=item, cp=current_price, p=profit: 
                                    self.simulation_order_tree.item(i, values=(*values[:8], cp, values[9], values[10], round(p, 4)))
                                )
                                break
                
                time.sleep(10)  # 每10秒更新一次结果
                
            except Exception as e:
                self.output_text.insert(tk.END, f"更新结果出错: {str(e)}\n")
                self.output_text.see(tk.END)
                time.sleep(10)
    
    def get_current_price(self):
        """获取当前价格"""
        try:
            symbol = self.symbol_var.get()
            url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
            response = requests.get(url)
            data = response.json()
            return data.get("price", 0)
        except:
            return 0
    
    def bind_api(self):
        """绑定Binance API"""
        api_key = self.api_key.get()
        api_secret = self.api_secret.get()
        
        if not api_key or not api_secret:
            messagebox.showerror("错误", "请输入API Key和Secret")
            return
        
        try:
            self.binance_client = Client(api_key, api_secret)
            # 测试API连接
            self.binance_client.futures_account()
            messagebox.showinfo("成功", "API绑定成功")
            self.output_text.insert(tk.END, "API绑定成功\n")
            self.update_account_info()
        except Exception as e:
            messagebox.showerror("错误", f"API绑定失败: {str(e)}")
            self.output_text.insert(tk.END, f"API绑定失败: {str(e)}\n")
            self.binance_client = None
    
    def update_account_info(self):
        """更新实盘账户信息（修正版）"""
        if not self.binance_client:
            messagebox.showerror("错误", "请先绑定API")
            return
        
        try:
            # 1. 获取合约账户余额（币安合约API）
            account_balances = self.binance_client.futures_account_balance()
            if not account_balances:
                raise ValueError("未获取到账户余额数据")
            
            # 2. 筛选USDT资产（根据实际交易对调整，如使用其他稳定币需修改）
            usdt_balance = next(
                (item for item in account_balances if item.get('asset') == 'USDT'),
                None
            )
            if not usdt_balance:
                raise ValueError("未找到USDT资产信息")
            
            # 3. 检查并获取balance字段（关键修正：确保字段存在）
            if 'balance' not in usdt_balance:
                raise KeyError("API返回数据中缺少'balance'字段")
            
            # 4. 更新当前保证金余额
            current_balance = float(usdt_balance['balance'])
            self.current_margin.set(round(current_balance, 2))
            
            # 5. 初始化初始金额（首次更新时）
            if self.live_result["初始金额"] == 0:
                self.live_result["初始金额"] = round(current_balance, 2)
                self.live_result_labels["初始金额"]["text"] = f"{current_balance:.2f}"
            
            # 6. 输出成功日志
            self.output_text.insert(tk.END, f"账户信息更新成功：当前保证金 {current_balance:.2f} USDT\n")
            self.output_text.see(tk.END)
            
        except KeyError as e:
            # 明确提示缺少的字段，便于调试
            self.output_text.insert(tk.END, f"更新账户信息失败：API返回数据中缺少字段 {str(e)}\n")
        except StopIteration:
            self.output_text.insert(tk.END, "更新账户信息失败：未找到指定资产（如USDT）\n")
        except Exception as e:
            self.output_text.insert(tk.END, f"更新账户信息失败：{str(e)}\n")
        finally:
            self.output_text.see(tk.END)
    
    def toggle_dual_position(self):
        """切换双向持仓模式"""
        if not self.binance_client:
            messagebox.showerror("错误", "请先绑定API")
            return
        
        try:
            current_state = self.dspc.variable.get()
            self.binance_client.futures_change_position_mode(dualSidePosition=current_state)
            status = "启用" if current_state else "禁用"
            self.output_text.insert(tk.END, f"{status}双向持仓模式成功\n")
        except Exception as e:
            self.output_text.insert(tk.END, f"切换双向持仓模式失败: {str(e)}\n")
    
    def start_live_trading(self):
        """开始实盘交易"""
        if not self.binance_client:
            messagebox.showerror("错误", "请先绑定API")
            return
        
        if self.strategy is None:
            messagebox.showerror("错误", "请先导入策略")
            return
        
        self.live_trading_running = True
        self.stop_live_btn.config(state=tk.NORMAL)
        
        # 初始化参数
        self.update_account_info()
        self.order_list = []
        self.trade_orders = []
        self.order_sequence = 1
        self.start_time = datetime.now()
        self.trade_count = 0
        
        # 清空订单表格
        for item in self.live_order_tree.get_children():
            self.live_order_tree.delete(item)
        
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "开始实盘交易...\n")
        
        # 设置杠杆
        try:
            symbol = self.symbol_var.get()
            leverage = int(self.leverage.get())
            self.binance_client.futures_change_leverage(symbol=symbol, leverage=leverage)
            self.output_text.insert(tk.END, f"设置杠杆为 {leverage} 倍成功\n")
        except Exception as e:
            self.output_text.insert(tk.END, f"设置杠杆失败: {str(e)}\n")
        
        # 启动实盘交易线程
        self.live_thread = threading.Thread(target=self.live_trading_thread, daemon=True)
        self.live_thread.start()
        # 启动结果更新线程
        threading.Thread(target=self.update_live_results_thread, daemon=True).start()
    
    def stop_live_trading(self):
        """停止实盘交易"""
        self.live_trading_running = False
        self.stop_live_btn.config(state=tk.DISABLED)
        self.output_text.insert(tk.END, "已停止实盘交易\n")
    
    def live_trading_thread(self):
        """实盘交易线程"""
        symbol = self.symbol_var.get()
        interval = self.interval_var.get()
        
        interval_seconds = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800
        }.get(interval, 3600)
        
        while self.live_trading_running:
            try:
                # 获取最新价格
                ticker = self.binance_client.futures_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 获取账户余额
                self.update_account_info()
                
                # 处理交易信号
                signal = self.strategy(current_time, price)
                self.output_text.insert(tk.END, f"{current_time}，价格: {price}，信号: {signal}\n")
                self.output_text.see(tk.END)
                
                if signal in ["做多", "做空"]:
                    # 计算订单保证金
                    if self.order_mode.get() == "固定保证金模式":
                        order_margin = self.fixed_margin.get()
                    else:
                        percent = self.percentage_margin.get() / 100
                        order_margin = self.current_margin.get() * percent
                    
                    # 检查保证金是否充足
                    if self.current_margin.get() < order_margin:
                        self.output_text.insert(tk.END, "保证金不足，无法开仓\n")
                        self.output_text.see(tk.END)
                        time.sleep(interval_seconds)
                        continue
                    
                    # 计算下单数量
                    leverage = self.leverage.get()
                    quantity = order_margin * leverage / price
                    # 调整数量精度
                    quantity = self.adjust_quantity(symbol, quantity)
                    
                    if quantity <= 0:
                        self.output_text.insert(tk.END, "计算下单数量错误，无法下单\n")
                        self.output_text.see(tk.END)
                        time.sleep(interval_seconds)
                        continue
                    
                    # 下单
                    side = Client.SIDE_BUY if signal == "做多" else Client.SIDE_SELL
                    position_side = "LONG" if signal == "做多" else "SHORT"
                    
                    try:
                        order = self.binance_client.futures_create_order(
                            symbol=symbol,
                            side=side,
                            type=Client.ORDER_TYPE_MARKET,
                            quantity=quantity,
                            positionSide=position_side
                        )
                        
                        self.output_text.insert(tk.END, f"下单成功: {order}\n")
                        self.trade_count += 1
                        
                        # 记录订单
                        fee = order_margin * leverage * (self.fee_rate.get() / 100)
                        self.order_list.append({
                            "sequence": self.order_sequence,
                            "time": current_time,
                            "action": signal,
                            "symbol": symbol,
                            "margin": order_margin,
                            "leverage": leverage,
                            "fee": fee,
                            "quantity": quantity,
                            "open_price": price,
                            "order_id": order['orderId']
                        })
                        
                        # 添加到表格
                        self.root.after(0, lambda seq=self.order_sequence, t=current_time, a=signal, p=price: 
                            self.live_order_tree.insert('', 'end', values=(
                                seq, t, a, symbol, 0, order_margin, 
                                order_margin * leverage, p, "", fee, "已成交"
                            ))
                        )
                        
                        self.order_sequence += 1
                        
                    except Exception as e:
                        self.output_text.insert(tk.END, f"下单失败: {str(e)}\n")
                        self.output_text.see(tk.END)
                
                elif signal in ["平多", "平空"]:
                    # 平仓处理
                    position_side = "LONG" if signal == "平多" else "SHORT"
                    side = Client.SIDE_SELL if signal == "平多" else Client.SIDE_BUY
                    
                    # 获取持仓信息
                    positions = self.binance_client.futures_position_information(symbol=symbol)
                    position = next((p for p in positions if p['positionSide'] == position_side and float(p['positionAmt']) != 0), None)
                    
                    if position:
                        quantity = abs(float(position['positionAmt']))
                        open_price = float(position['entryPrice'])
                        order_id = position['orderId'] if 'orderId' in position else ""
                        
                        try:
                            # 平仓
                            order = self.binance_client.futures_create_order(
                                symbol=symbol,
                                side=side,
                                type=Client.ORDER_TYPE_MARKET,
                                quantity=quantity,
                                positionSide=position_side
                            )
                            
                            self.output_text.insert(tk.END, f"平仓成功: {order}\n")
                            self.trade_count += 1
                            
                            # 计算盈亏
                            profit = float(position['unRealizedProfit'])
                            fee = float(position['commission'])
                            
                            # 查找对应的开仓订单
                            for open_order in self.order_list.copy():
                                if (signal == "平多" and open_order["action"] == "做多") or \
                                   (signal == "平空" and open_order["action"] == "做空"):
                                    
                                    # 记录平仓订单
                                    self.trade_orders.append({
                                        "sequence": open_order["sequence"],
                                        "time": current_time,
                                        "action": signal,
                                        "symbol": symbol,
                                        "profit": profit,
                                        "margin": open_order["margin"],
                                        "actual_control_funds": open_order["margin"] * open_order["leverage"],
                                        "open_price": open_order["open_price"],
                                        "close_price": price,
                                        "total_fee": open_order["fee"] + fee
                                    })
                                    
                                    # 更新表格
                                    for item in self.live_order_tree.get_children():
                                        values = self.live_order_tree.item(item, "values")
                                        if int(values[0]) == open_order["sequence"]:
                                            self.root.after(0, lambda i=item, p=price, pr=profit, f=open_order["fee"] + fee: 
                                                self.live_order_tree.item(i, values=(
                                                    values[0], values[1], signal, values[3],
                                                    round(pr, 4), values[5], values[6],
                                                    values[7], p, round(f, 4), "已平仓"
                                                ))
                                            )
                                            break
                                    
                                    self.order_list.remove(open_order)
                                    break
                            
                        except Exception as e:
                            self.output_text.insert(tk.END, f"平仓失败: {str(e)}\n")
                            self.output_text.see(tk.END)
                    else:
                        self.output_text.insert(tk.END, f"没有{signal}的持仓，无法平仓\n")
                        self.output_text.see(tk.END)
                
                # 休眠到下一个周期
                time.sleep(interval_seconds)
                
            except Exception as e:
                self.output_text.insert(tk.END, f"实盘交易出错: {str(e)}\n")
                self.output_text.see(tk.END)
                time.sleep(5)
    
    def update_live_results_thread(self):
        """更新实盘结果线程"""
        # 初始化关键变量，避免未定义错误
        if not hasattr(self, 'start_time'):
            self.start_time = datetime.now()
        if not hasattr(self, 'trade_count'):
            self.trade_count = 0
            
        initial_margin = self.initial_margin.get()
        margin_max = initial_margin
        margin_min = initial_margin
        self.output_text.insert(tk.END, "实盘结果更新线程已启动\n")
        self.output_text.see(tk.END)
        
        while self.live_trading_running:
            try:
                # 检查Binance客户端是否有效
                if not self.binance_client:
                    self.output_text.insert(tk.END, "等待API绑定...\n")
                    self.output_text.see(tk.END)
                    time.sleep(10)
                    continue
                    
                current_time = datetime.now()
                run_time = current_time - self.start_time
                
                # 获取当前保证金（从账户信息更新，而非本地变量）
                current_margin_val = self.current_margin.get()
                if current_margin_val <= 0:
                    current_margin_val = 0.01  # 避免除以零错误
                
                # 更新最大/最小保证金记录
                margin_max = max(margin_max, current_margin_val)
                margin_min = min(margin_min, current_margin_val)
                
                # 获取未实现盈亏（增加异常捕获）
                unrealized_profit = 0.0
                try:
                    positions = self.binance_client.futures_position_information(symbol=self.symbol_var.get())
                    # 过滤有效持仓数据
                    valid_positions = [p for p in positions if float(p['positionAmt']) != 0]
                    unrealized_profit = sum(float(p['unRealizedProfit']) for p in valid_positions)
                    self.unrealized_profit.set(round(unrealized_profit, 4))
                except Exception as pos_err:
                    self.output_text.insert(tk.END, f"获取持仓信息失败: {str(pos_err)}\n")
                    self.output_text.see(tk.END)
                
                # 计算总权益
                total_equity = current_margin_val + unrealized_profit
                
                # 计算收益率（增加零值保护）
                return_rate = 0.0
                if initial_margin > 0:
                    return_rate = (current_margin_val - initial_margin) / initial_margin * 100
                
                # 计算最大回撤（增加零值保护）
                max_drawdown = 0.0
                if initial_margin > 0 and (initial_margin - margin_min) > 0:
                    max_drawdown = (initial_margin - margin_min) / initial_margin * 100
                
                # 更新实盘结果字典
                self.live_result.update({
                    "已运行时长": f"{int(run_time.total_seconds() // 3600)}h{int((run_time.total_seconds() % 3600) // 60)}m",
                    "交易次数": self.trade_count,
                    "初始金额": round(initial_margin, 2),
                    "当前保证金余额": round(current_margin_val, 2),
                    "未实现盈亏": round(unrealized_profit, 2),
                    "总权益": round(total_equity, 2),
                    "收益率": round(return_rate, 2),
                    "最大回撤": round(max_drawdown, 2)
                })
                
                # 线程安全更新UI（使用after确保在主线程执行）
                def update_ui():
                    for key, value in self.live_result.items():
                        suffix = "%" if key in ["收益率", "最大回撤"] else ""
                        self.live_result_labels[key]["text"] = f"{value}{suffix}"
                
                self.root.after(0, update_ui)
                self.output_text.insert(tk.END, "实盘结果已更新\n")
                self.output_text.see(tk.END)
                
                # 每30秒更新一次
                time.sleep(30)
                
            except Exception as e:
                # 详细错误日志
                error_msg = f"更新实盘结果出错 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]: {str(e)}\n"
                self.root.after(0, lambda: self.output_text.insert(tk.END, error_msg))
                self.root.after(0, lambda: self.output_text.see(tk.END))
                time.sleep(30)  # 出错后延长等待时间
        
        self.output_text.insert(tk.END, "实盘结果更新线程已停止\n")
        self.output_text.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingEngine(root)
    root.mainloop()