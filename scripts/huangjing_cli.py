#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智鉴黄精 CLI 管理工具。

命令:
    start   - 启动服务
    stop    - 停止服务
    restart - 重启服务
    status  - 查看状态
    check   - 环境检查
    logs    - 查看日志
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
if sys.platform == "win32":
    VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"

PID_FILE = PROJECT_ROOT / ".huangjing.pid"
LOG_FILE = PROJECT_ROOT / "logs" / "app.log"


def start_service():
    """启动服务"""
    if PID_FILE.exists():
        print("服务可能已在运行，请先检查状态")
        return 1
    
    if not VENV_PYTHON.exists():
        print("错误: 虚拟环境不存在，请先运行 install 脚本")
        return 1
    
    app_py = PROJECT_ROOT / "app.py"
    if not app_py.exists():
        print("错误: app.py 不存在")
        return 1
    
    print("正在启动服务...")
    
    # 简化启动：直接运行streamlit
    cmd = [
        str(VENV_PYTHON),
        "-m", "streamlit",
        "run", str(app_py),
        "--server.address", "0.0.0.0",
        "--server.port", "8501"
    ]
    
    try:
        subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        print("\n服务已停止")
    
    return 0


def check_env():
    """环境检查"""
    print("=== 智鉴黄精 - 环境检查 ===\n")
    
    issues = 0
    
    # 检查Python
    print("[1/4] Python")
    if VENV_PYTHON.exists():
        print(f"  ✓ 虚拟环境: {VENV_PYTHON}")
    else:
        print("  ✗ 虚拟环境不存在")
        issues += 1
    
    # 检查依赖
    print("\n[2/4] 依赖包")
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        print("  ✓ requirements.txt 存在")
    else:
        print("  ✗ requirements.txt 不存在")
        issues += 1
    
    # 检查配置
    print("\n[3/4] 配置文件")
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        print("  ✓ .env 存在")
        # 检查API Key
        content = env_file.read_text()
        if "ARK_API_KEY=" in content and "your_api_key_here" not in content:
            print("  ✓ ARK_API_KEY 已配置")
        else:
            print("  ✗ ARK_API_KEY 未配置")
            issues += 1
    else:
        print("  ✗ .env 不存在")
        issues += 1
    
    # 检查Prompt
    print("\n[4/4] Prompt文件")
    prompt_file = PROJECT_ROOT / "prompts" / "system.txt"
    if prompt_file.exists():
        print("  ✓ prompts/system.txt 存在")
    else:
        print("  ! prompts/system.txt 不存在 (将使用内置备用)")
    
    print("\n" + "="*40)
    if issues == 0:
        print("✓ 检查完成: 全部通过")
        return 0
    else:
        print(f"✗ 检查完成: 发现 {issues} 个问题")
        return 1


def show_logs(tail=50):
    """查看日志"""
    if not LOG_FILE.exists():
        print("日志文件不存在")
        return 1
    
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        print(f"=== 最近 {tail} 行日志 ===\n")
        for line in lines[-tail:]:
            print(line)
    except Exception as e:
        print(f"读取日志失败: {e}")
        return 1
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="huangjing",
        description="智鉴黄精 CLI 管理工具"
    )
    parser.add_argument(
        "command",
        choices=["start", "check", "logs"],
        help="命令"
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=50,
        help="logs 命令显示的行数"
    )
    
    args = parser.parse_args()
    
    if args.command == "start":
        sys.exit(start_service())
    elif args.command == "check":
        sys.exit(check_env())
    elif args.command == "logs":
        sys.exit(show_logs(args.tail))


if __name__ == "__main__":
    main()
