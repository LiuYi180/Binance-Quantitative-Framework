import subprocess
import sys


def install_libraries():
    """检查并安装运行框架所需的第三方依赖。"""
    libraries = [
        "requests",
        "pandas",
        "tkinter",  # 通常Python自带，但有些环境可能需要单独安装
        "python-binance",
        "cryptography",  # 新增：用于加密存储API密钥
        "matplotlib",  # 新增：管理后台可视化能力
    ]

    standard_libraries = [
        "collections",
        "time",
        "datetime",
        "os",
        "importlib",
        "math",
        "threading",
        "logging",
    ]

    print("开始检查并安装所需库...\n")

    for lib in libraries:
        try:
            __import__(lib)
            print(f"库 '{lib}' 已安装，跳过...")
        except ImportError:
            print(f"库 '{lib}' 未安装，正在安装...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
            print(f"库 '{lib}' 安装完成\n")

    print("\n以下库是Python标准库，无需单独安装：")
    for std_lib in standard_libraries:
        print(f"- {std_lib}")

    print("\n所有必要的库检查和安装已完成！")


if __name__ == "__main__":
    install_libraries()
    input("按回车键退出...")
