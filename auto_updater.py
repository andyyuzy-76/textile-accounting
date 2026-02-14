"""
自动更新模块
从GitHub仓库检查并下载最新版本
"""

import os
import json
import urllib.request
import urllib.error
import tempfile
import shutil
import subprocess
import sys
from datetime import datetime

# GitHub仓库信息
GITHUB_REPO = "andyyuzy-76/textile-accounting"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/version.json"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"

# 本地版本文件路径
LOCAL_VERSION_FILE = "version.json"

def get_current_version():
    """获取当前版本号"""
    try:
        if os.path.exists(LOCAL_VERSION_FILE):
            with open(LOCAL_VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', '1.0.0')
    except:
        pass
    return '1.0.0'

def get_remote_version():
    """获取远程最新版本号"""
    try:
        url = f"{GITHUB_RAW_URL}/version.json?t={datetime.now().timestamp()}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TextileAccounting/1.0',
            'Cache-Control': 'no-cache'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('version', '1.0.0'), data.get('message', '')
    except Exception as e:
        print(f"检查更新失败: {e}")
        return None, None

def compare_versions(v1, v2):
    """比较版本号，返回True表示v2更新"""
    try:
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        
        # 补齐版本号长度
        while len(parts1) < 3:
            parts1.append(0)
        while len(parts2) < 3:
            parts2.append(0)
        
        for i in range(3):
            if parts2[i] > parts1[i]:
                return True
            elif parts2[i] < parts1[i]:
                return False
        return False
    except:
        return False

def download_file(filename, dest_path):
    """从GitHub下载文件"""
    url = f"{GITHUB_RAW_URL}/{filename}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TextileAccounting/1.0',
            'Cache-Control': 'no-cache'
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(dest_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"下载 {filename} 失败: {e}")
        return False

def perform_update(callback=None):
    """执行更新操作"""
    backup_dir = None
    temp_dir = None
    
    try:
        if callback:
            callback("正在下载更新...")
        
        # 需要更新的文件列表
        files_to_update = [
            'accounting_gui.py',
            'auto_updater.py',
            'version.json',
            '记账系统-GUI.bat'
        ]
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        backup_dir = tempfile.mkdtemp()
        
        # 下载所有文件
        for filename in files_to_update:
            if callback:
                callback(f"下载 {filename}...")
            dest_path = os.path.join(temp_dir, filename)
            if not download_file(filename, dest_path):
                if filename != 'auto_updater.py':  # auto_updater.py 可能不存在旧版本
                    return False, f"下载 {filename} 失败"
        
        if callback:
            callback("正在应用更新...")
        
        # 备份当前文件
        for filename in files_to_update:
            if os.path.exists(filename):
                shutil.copy2(filename, os.path.join(backup_dir, filename))
        
        # 替换文件
        for filename in files_to_update:
            src = os.path.join(temp_dir, filename)
            if os.path.exists(src):
                shutil.copy2(src, filename)
        
        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if backup_dir and os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        
        return True, "更新成功！"
            
    except Exception as e:
        # 恢复备份
        if backup_dir and os.path.exists(backup_dir):
            for filename in ['accounting_gui.py', 'version.json', '记账系统-GUI.bat']:
                backup_file = os.path.join(backup_dir, filename)
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, filename)
        # 清理
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if backup_dir and os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        return False, f"更新出错: {e}"

def check_for_updates(silent=True):
    """检查是否有更新"""
    current = get_current_version()
    remote, message = get_remote_version()
    
    if remote is None:
        if not silent:
            return False, "无法连接到服务器", current, ""
        return False, None, current, ""
    
    has_update = compare_versions(current, remote)
    
    return has_update, remote, current, message or ""

if __name__ == "__main__":
    # 测试更新检查
    has_update, remote, current, message = check_for_updates(silent=False)
    print(f"当前版本: {current}")
    print(f"最新版本: {remote}")
    print(f"有更新: {has_update}")
    if message:
        print(f"更新说明: {message}")
