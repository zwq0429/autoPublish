"""
浏览器路径检测模块
通过读取Windows注册表自动检测可用的浏览器路径
"""

import winreg
import os
from typing import List, Optional, Dict


class BrowserDetector:
    """Windows浏览器路径检测器"""
    
    # 常见浏览器的注册表路径和显示名称
    BROWSER_REGISTRY_PATHS = {
        'Chrome': {
            'registry_paths': [
                r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
                r'SOFTWARE\Clients\StartMenuInternet\Google Chrome\shell\open\command'
            ],
            'default_paths': [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'
            ]
        },
        'Edge': {
            'registry_paths': [
                r'Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe',
                r'SOFTWARE\Clients\StartMenuInternet\Microsoft Edge\shell\open\command'
            ],
            'default_paths': [
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files (x86)\Microsoft\Edge Dev\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge Dev\Application\msedge.exe'
            ]
        },
        'Edge Dev': {
            'registry_paths': [
                r'Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe'
            ],
            'default_paths': [
                r'C:\Program Files (x86)\Microsoft\Edge Dev\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge Dev\Application\msedge.exe'
            ]
        },
        'Chromium': {
            'registry_paths': [
                r'Software\Microsoft\Windows\CurrentVersion\App Paths\chromium.exe'
            ],
            'default_paths': [
                r'C:\Program Files\Chromium\Application\chromium.exe',
                r'C:\Program Files (x86)\Chromium\Application\chromium.exe'
            ]
        }
    }
    
    @staticmethod
    def _expand_environment_variables(path: str) -> str:
        """展开环境变量"""
        return os.path.expandvars(path)
    
    @staticmethod
    def _read_registry_value(key_path: str, value_name: str = "") -> Optional[str]:
        """读取注册表值"""
        try:
            # 尝试当前用户注册表
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    # 去除可能的引号和参数
                    value = value.strip('"')
                    if ' -' in value:
                        value = value.split(' -')[0]
                    return value
        except (OSError, WindowsError):
            pass
        
        try:
            # 尝试本地机器注册表
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    # 去除可能的引号和参数
                    value = value.strip('"')
                    if ' -' in value:
                        value = value.split(' -')[0]
                    return value
        except (OSError, WindowsError):
            pass
        
        return None
    
    @staticmethod
    def _check_file_exists(file_path: str) -> bool:
        """检查文件是否存在且可执行"""
        if not file_path:
            return False
        
        file_path = BrowserDetector._expand_environment_variables(file_path)
        return os.path.isfile(file_path) and file_path.lower().endswith('.exe')
    
    @staticmethod
    def detect_browser_path(browser_name: str) -> Optional[str]:
        """检测指定浏览器的路径"""
        if browser_name not in BrowserDetector.BROWSER_REGISTRY_PATHS:
            return None
        
        browser_info = BrowserDetector.BROWSER_REGISTRY_PATHS[browser_name]
        
        # 1. 首先尝试从注册表读取
        for reg_path in browser_info['registry_paths']:
            path = BrowserDetector._read_registry_value(reg_path, "")
            if path and BrowserDetector._check_file_exists(path):
                print(f"从注册表找到 {browser_name}: {path}")
                return path
        
        # 2. 如果注册表没有找到，尝试默认路径
        for default_path in browser_info['default_paths']:
            if BrowserDetector._check_file_exists(default_path):
                print(f"从默认路径找到 {browser_name}: {default_path}")
                return default_path
        
        return None
    
    @staticmethod
    def detect_all_browsers() -> Dict[str, str]:
        """检测所有可用的浏览器"""
        available_browsers = {}
        
        print("开始检测可用的浏览器...")
        
        for browser_name in BrowserDetector.BROWSER_REGISTRY_PATHS.keys():
            path = BrowserDetector.detect_browser_path(browser_name)
            if path:
                available_browsers[browser_name] = path
                print(f"✓ 找到 {browser_name}: {path}")
            else:
                print(f"✗ 未找到 {browser_name}")
        
        return available_browsers
    
    @staticmethod
    def get_recommended_browser() -> Optional[str]:
        """获取推荐的浏览器路径（按优先级）"""
        # 优先级顺序：Edge Dev > Edge > Chrome > Chromium
        priority_order = ['Edge Dev', 'Edge', 'Chrome', 'Chromium']
        
        available_browsers = BrowserDetector.detect_all_browsers()
        
        for browser_name in priority_order:
            if browser_name in available_browsers:
                recommended_path = available_browsers[browser_name]
                print(f"推荐使用 {browser_name}: {recommended_path}")
                return recommended_path
        
        print("未找到任何可用的浏览器")
        return None
    
    @staticmethod
    def get_browser_info() -> str:
        """获取浏览器检测信息的字符串表示"""
        available_browsers = BrowserDetector.detect_all_browsers()
        
        if not available_browsers:
            return "未检测到任何可用的浏览器\n请手动配置浏览器路径"
        
        info = "检测到的浏览器:\n"
        for browser_name, path in available_browsers.items():
            info += f"  {browser_name}: {path}\n"
        
        recommended = BrowserDetector.get_recommended_browser()
        if recommended:
            info += f"\n推荐使用: {recommended}"
        
        return info


# 测试函数
def test_browser_detection():
    """测试浏览器检测功能"""
    print("=== 浏览器路径检测测试 ===")
    print(BrowserDetector.get_browser_info())
    print("=== 测试完成 ===")


if __name__ == "__main__":
    test_browser_detection()