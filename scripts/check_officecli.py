#!/usr/bin/env python3
"""检测并自动安装 OfficeCLI（如果未安装）。

Usage:
    python check_officecli.py [--install]
    
默认只检测，不安装。传入 --install 时如果未安装则自动下载安装。
"""
import os
import shutil
import subprocess
import sys
import argparse

OFFICECLI_VERSION = "v1.0.144"
DOWNLOAD_URLS = [
    f"https://github.com/iOfficeAI/OfficeCLI/releases/download/{OFFICECLI_VERSION}/officecli-win-x64.exe",
    f"https://d.officecli.ai/{OFFICECLI_VERSION}/officecli-win-x64.exe",
]


def find_officecli():
    """查找系统中已安装的 officecli。返回路径或 None。"""
    candidates = [
        os.environ.get("OFFICECLI"),
        shutil.which("officecli"),
        os.path.expanduser("~/.office-form-filler/bin/officecli.exe"),
        os.path.expanduser("~/.workbuddy/binaries/officecli.exe"),
        os.path.expanduser("~/.officecli/bin/officecli.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(os.path.expanduser(c)):
            return os.path.expanduser(c)
    return None


def get_skill_dir():
    """获取技能目录路径。"""
    # 从脚本位置推导技能目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)  # scripts/ 的父目录就是技能根目录


def install_officecli(offline_mode=False):
    """下载并安装 officecli 到技能目录的 assets/ 下。"""
    skill_dir = get_skill_dir()
    assets_dir = os.path.join(skill_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    dest = os.path.join(assets_dir, "officecli.exe")
    
    # 已存在则跳过
    if os.path.isfile(dest):
        print(f"[INFO] OfficeCLI 已存在于技能目录: {dest}")
        return dest
    
    print(f"[INFO] 正在下载 OfficeCLI {OFFICECLI_VERSION}...")
    
    if offline_mode:
        print("[ERROR] 离线模式无法下载，请手动安装 OfficeCLI")
        print(f"       下载地址: {DOWNLOAD_URLS[0]}")
        print(f"       并将文件保存到: {dest}")
        sys.exit(1)
    
    # 尝试下载
    import urllib.request
    import ssl
    
    # 创建 SSL 上下文（某些环境需要）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for url in DOWNLOAD_URLS:
        try:
            print(f"[TRY] {url}")
            urllib.request.urlretrieve(url, dest)
            print(f"[OK] 已下载到: {dest}")
            return dest
        except Exception as e:
            print(f"[FAIL] {url}: {e}")
            continue
    
    print("[ERROR] 所有下载源均失败")
    print(f"       请手动下载: {DOWNLOAD_URLS[0]}")
    print(f"       并保存到: {dest}")
    sys.exit(1)


def check_and_install():
    """检测并可选安装。返回 officecli 路径。"""
    parser = argparse.ArgumentParser(description="检测并安装 OfficeCLI")
    parser.add_argument("--install", action="store_true", help="如果未安装则自动安装")
    parser.add_argument("--offline", action="store_true", help="离线模式，不尝试下载")
    args = parser.parse_args()
    
    # 1. 先检查技能目录内（自包含）
    skill_dir = get_skill_dir()
    local_bin = os.path.join(skill_dir, "assets", "officecli.exe")
    if os.path.isfile(local_bin):
        print(f"[OK] 使用技能内置 OfficeCLI: {local_bin}")
        return local_bin
    
    # 2. 检查系统安装
    system_cli = find_officecli()
    if system_cli:
        print(f"[OK] 使用系统安装的 OfficeCLI: {system_cli}")
        return system_cli
    
    # 3. 未找到
    print("[WARN] 未找到 OfficeCLI")
    
    if args.install:
        print("[INFO] 正在自动安装...")
        return install_officecli(offline_mode=args.offline)
    else:
        print("[INFO] 传入 --install 可自动下载安装")
        print("       或手动安装后重试")
        sys.exit(1)


if __name__ == "__main__":
    check_and_install()
