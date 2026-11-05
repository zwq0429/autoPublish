"""扫码登录 CLI。

来源: app.py 行 2017-2219
  - run_login_thread (2017-2022)：原为 UI 线程调度，CLI 直接同步执行 login
  - _get_site_url (2024-2026)：改为 novel_publisher.navigation.get_site_url(platform)
  - _get_app_base_dir (2028-2046)：逐行保留（__file__ 位于 cli/ 下，上两级同为项目根）
  - _get_login_profile_dir (2048-2063)：逐行保留（站点参数化）
  - _terminate_browser_using_profile (2065-2086)：原样保留
  - _get_login_browser_candidates (2087-2100)：self.custom_browser_path_var.get() 改为参数传入
  - _launch_login_context (2101-2151)：UI 变量读写改为返回实际使用的浏览器路径
  - login (2152-2219)：主体逻辑逐行保留

去 UI 化说明:
  - CLI 版不弹 Tk 窗口，用 print + input() 与用户交互：
    原 threading.Event(login_event) 的"等待用户点登录按钮"改为
    input("请在打开的浏览器中完成扫码登录，完成后回到此处按回车继续...")；
  - messagebox.showerror（登录失败弹窗）改为 print，并以退出码 1 表示失败、0 表示成功；
  - 保存 storage_state 到登录态文件的行为原样保留。
"""

import configparser
import os
import re
import sys
import time
import traceback

from playwright.sync_api import sync_playwright

from browser_detector import BrowserDetector
from novel_publisher.navigation import get_site_url

# 项目根目录（cli/ 的上一级），与 cli/main.py 的 APP_DIR 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 app.py 的 AUTH_FILE = r'auth.json' 对应，CLI 默认放到项目根下
DEFAULT_AUTH_FILE = os.path.join(APP_DIR, 'auth.json')


def get_app_base_dir():
    """获取应用数据目录。（原 _get_app_base_dir，app.py 2028-2046，逐行保留）

    打包后的 exe 可能放在桌面、下载目录或受企业策略管控的位置，
    Chromium 的 user-data-dir 放在那里容易被 Edge/系统安全策略拒绝。
    因此运行时数据统一放到当前用户 LOCALAPPDATA 下。
    """
    local_appdata = os.environ.get('LOCALAPPDATA')
    if local_appdata:
        base_dir = os.path.join(local_appdata, 'AutoPublish')
    elif getattr(sys, 'frozen', False):
        base_dir = os.path.join(os.path.dirname(sys.executable), 'AutoPublishData')
    else:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'AutoPublishData')
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        pass
    return base_dir


def get_login_profile_dir(site_url):
    """获取登录专用浏览器配置目录（每个站点独立）。（原 _get_login_profile_dir，app.py 2048-2063，逐行保留）

    Chromium 系浏览器（Chrome/Edge）对同一 user-data-dir 强制单实例：
    若该目录已被某个正在运行的浏览器占用，新启动会被"交接"给已有实例并立即退出，
    导致 Playwright 报 TargetClosedError（对应日志中的"正在现有浏览器会话中打开"）。
    使用每个站点独立的配置目录即可避免冲突，这也是官方维护者的建议。
    """
    site = site_url or 'default'
    site_name = re.sub(r'[^0-9a-zA-Z\u4e00-\u9fff_-]+', '_', site.split('?')[0].rstrip('/'))[:50]
    profile_dir = os.path.join(get_app_base_dir(), 'browser_profiles', site_name)
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception:
        pass
    return profile_dir


def terminate_browser_using_profile(profile_dir):
    """结束仍占用指定配置目录的残留浏览器进程（上次异常退出遗留），避免启动交接冲突
    （原 _terminate_browser_using_profile，app.py 2065-2086，原样保留）"""
    import subprocess
    if not profile_dir:
        return
    try:
        ps = (
            "$p = '%s'.ToLower(); "
            "Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -in @('msedge.exe','chrome.exe','chromium.exe') -and "
            "$_.CommandLine -and $_.CommandLine.ToLower().Contains($p) "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        ) % profile_dir.replace("'", "''")
        subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        time.sleep(0.5)
    except Exception:
        pass


def get_login_browser_candidates(current_browser_path):
    """获取登录可用浏览器候选列表，当前选择优先，失败后自动换其它浏览器
    （原 _get_login_browser_candidates，app.py 2087-2100；self.custom_browser_path_var.get() 改为参数传入）"""
    candidates = []
    current = (current_browser_path or '').strip()
    if current and os.path.isfile(current):
        candidates.append(current)
    try:
        for path in BrowserDetector.detect_all_browsers().values():
            if path and os.path.isfile(path) and path not in candidates:
                candidates.append(path)
    except Exception:
        pass
    return candidates


def launch_login_context(playwright, profile_dir, current_browser_path):
    """启动登录浏览器；若当前 Edge 被企业策略/版本限制关闭，自动切换其它浏览器
    （原 _launch_login_context，app.py 2101-2151；UI 变量读写改为传入/返回实际使用的浏览器路径）"""
    args = [
        "--disable-popup-blocking",  # 禁用弹窗拦截
        "--disable-web-security",  # 禁用网页安全策略
        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
    ]
    common_kwargs = dict(
        headless=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        args=args,
        ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
    )
    last_error = None
    candidates = get_login_browser_candidates(current_browser_path)
    for index, browser_path in enumerate(candidates):
        browser_name = os.path.splitext(os.path.basename(browser_path))[0]
        candidate_profile_dir = profile_dir if index == 0 else f"{profile_dir}_{browser_name}_{index}"
        try:
            os.makedirs(candidate_profile_dir, exist_ok=True)
        except Exception:
            pass
        terminate_browser_using_profile(candidate_profile_dir)
        print(f"尝试启动浏览器: {browser_path}")
        print(f"浏览器配置目录: {candidate_profile_dir}")
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=candidate_profile_dir,
                executable_path=browser_path,
                **common_kwargs
            )
            if browser_path != current_browser_path:
                current_browser_path = browser_path
            return context, current_browser_path
        except Exception as e:
            last_error = e
            print(f"启动失败，尝试下一个浏览器: {e}")
    try:
        print("本机浏览器启动失败，尝试使用 Playwright 内置 Chromium...")
        builtin_profile_dir = f"{profile_dir}_playwright_chromium"
        os.makedirs(builtin_profile_dir, exist_ok=True)
        terminate_browser_using_profile(builtin_profile_dir)
        return (playwright.chromium.launch_persistent_context(
            user_data_dir=builtin_profile_dir,
            **common_kwargs
        ), current_browser_path)
    except Exception as e:
        last_error = e
    raise last_error


def login(site_url, platform_name, config, novel_writer, custom_browser_path, auth_file):
    """执行扫码登录。（原 login，app.py 2152-2219，主体逻辑逐行保留）

    原 threading.Event(login_event) 的"等待用户在 UI 点击登录按钮"改为 input() 等待；
    登录失败弹窗（messagebox.showerror）改为 print，返回退出码 1；成功返回 0。
    """
    print("正在启动浏览器...")
    try:
        with sync_playwright() as p:
            # # 使用每个站点独立的浏览器配置目录，避免与已打开的浏览器实例冲突
            # profile_dir = get_login_profile_dir(site_url)
            # # 清理上次异常退出后残留、仍占用该配置目录的浏览器进程
            # terminate_browser_using_profile(profile_dir)
            # # 添加必要的浏览器参数以允许弹窗和滑块验证，并在当前浏览器启动失败时自动切换其它浏览器
            # context, custom_browser_path = launch_login_context(p, profile_dir, custom_browser_path)
            # # 持久化上下文自带初始页面，直接使用
            # page = context.pages[0] if context.pages else context.new_page()
            browser = p.chromium.launch(
                headless=False,
                executable_path=custom_browser_path,
                args=[
                    "--disable-popup-blocking",  # 禁用弹窗拦截
                    "--disable-web-security",  # 禁用网页安全策略
                    "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                    "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                ],
                ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
            )
            # 设置用户代理，避免被网站识别为自动化工具
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print(f"请在打开的浏览器窗口中手动登录网站: {site_url}，完成后再次点击登录按钮完成登录。")
            page.goto(site_url, timeout=60000)
            # self.page.wait_for_timeout(600000)
            # 非阻塞等待登录完成信号（原 while not self.login_event.is_set(): time.sleep(1)）
            input("请在打开的浏览器中完成扫码登录，完成后回到此处按回车继续...")
            try:
                if (platform_name != config.get('Settings', 'publish_plate', fallback='')
                        or novel_writer != config.get('Novel', 'novel_writer', fallback='')):
                    if os.path.exists(auth_file):
                        os.remove(auth_file)
                        print("检测到账号变更")
                        print("已删除旧的登录状态文件")
                context.storage_state(path=auth_file)
                print(f"登录状态已保存到 {auth_file}")
            except Exception as e:
                print(f"保存登录状态失败: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                print("浏览器已关闭。")
                page = None
        return 0
    except Exception as e:
        traceback.print_exc()
        print(f"登录失败: {e}")
        # 原 messagebox.showerror("登录失败", ...) 改为 print
        try:
            print(
                "启动浏览器失败:\n"
                f"{e}\n\n"
                "程序已自动尝试切换 Chrome/Edge/内置 Chromium。\n"
                "若仍失败，通常是企业版系统安全策略、浏览器策略或杀毒软件拦截了自动化浏览器启动。"
            )
        except Exception:
            pass
        return 1


def register(subparsers):
    """向 argparse 子命令注册参数。"""
    subparsers.add_argument('-p', '--platform', default='',
                            help='平台名（默认读 config.ini [Settings] publish_plate）')
    subparsers.add_argument('--config', default='config.ini',
                            help='配置文件路径（默认 config.ini）')
    subparsers.add_argument('--output', default='',
                            help=f'登录态保存路径（默认 项目根/auth.json）')


def main(args) -> int:
    """执行 login 命令，返回退出码（0 成功，1 失败）。"""
    config = configparser.ConfigParser()
    if os.path.exists(args.config):
        config.read(args.config, encoding='utf-8')

    platform_name = args.platform or config.get('Settings', 'publish_plate', fallback='番茄')
    try:
        site_url = get_site_url(platform_name)
    except ValueError as e:
        print(f"错误: {e}")
        return 1

    auth_file = args.output or DEFAULT_AUTH_FILE
    novel_writer = config.get('Novel', 'novel_writer', fallback='')
    custom_browser_path = config.get('Settings', 'custom_browser_path', fallback='')

    print(f"平台: {platform_name}  登录地址: {site_url}")
    return login(site_url, platform_name, config, novel_writer, custom_browser_path, auth_file)
