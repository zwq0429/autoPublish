"""手动浏览器会话 CLI。

来源: app.py 行 2821-2870（open_manual_browser 方法）
  - 打开带登录态的浏览器，保持等待用户手动操作，直到用户关闭浏览器窗口；
  - 原 run_manual_browser 在后台线程执行（避免阻塞 Tk 主界面），CLI 无界面需守护，
    改为在主线程同步执行（等待行为本身不变）；
  - 关闭逻辑按源码保留：while True 循环轮询 page.is_closed()（源码即持续轮询，
    非 input() 等待）；
  - messagebox.showerror("错误", f"打开手动浏览器失败: {e}") 改为 print，退出码 1；
  - event 参数（Tk 事件，控制是否设置 1920x1080 视口）在 CLI 中恒为 None，
    按源码结构保留 if event: 分支。
"""

import configparser
import os
import time

from playwright.sync_api import sync_playwright

from novel_publisher.browser import open_browser
from novel_publisher.navigation import get_site_url

# 项目根目录（cli/ 的上一级），与 cli/main.py 的 APP_DIR 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 app.py 的 AUTH_FILE = r'auth.json' 对应，CLI 默认放到项目根下
DEFAULT_AUTH_FILE = os.path.join(APP_DIR, 'auth.json')


def register(subparsers):
    """向 argparse 子命令注册参数。"""
    subparsers.add_argument('-p', '--platform', default='',
                            help='平台名（默认读 config.ini [Settings] publish_plate）')
    subparsers.add_argument('--browser-path', dest='browser_path', default='',
                            help='浏览器路径（默认读 config.ini [Settings] custom_browser_path）')
    subparsers.add_argument('--config', default='config.ini',
                            help='配置文件路径（默认 config.ini）')


def main(args) -> int:
    """执行 manual-browser 命令，返回退出码（0 正常关闭，1 失败）。"""
    config = configparser.ConfigParser()
    if os.path.exists(args.config):
        config.read(args.config, encoding='utf-8')

    platform_name = args.platform or config.get('Settings', 'publish_plate', fallback='番茄')
    custom_browser_path = args.browser_path or config.get('Settings', 'custom_browser_path', fallback='')
    auth_file = DEFAULT_AUTH_FILE

    try:
        site_url = get_site_url(platform_name)
    except ValueError as e:
        print(f"错误: {e}")
        return 1

    # 原 open_manual_browser(self, event=None)：Tk 事件参数，CLI 中恒为 None
    event = None

    print("正在打开手动浏览器...")
    print("浏览器将保持打开状态，您可以进行手动操作")
    print("需要关闭时，请直接关闭浏览器窗口")
    try:
        # 原在后台线程 run_manual_browser 中执行，CLI 改为主线程同步执行
        try:
            with sync_playwright() as p:
                # 原 self._normal_open_browser(p, custom_browser_path, False)；
                # 其 on_browser_not_found 原为 self.open_browser_lnk（打开快捷方式），CLI 传 None
                browser, context = open_browser(p, custom_browser_path, False, auth_file,
                                                on_browser_not_found=None)
                if custom_browser_path.isdigit():
                    page = context.pages[0]
                else:
                    page = context.new_page()
                    if event:
                        page.set_viewport_size({"width": 1920, "height": 1080})

                    # 导航到网站
                    if site_url:
                        page.goto(site_url, timeout=60000)
                        print(f"已导航到: {site_url}")

                print("手动浏览器已启动，您可以自由操作")
                print("关闭浏览器窗口即可结束会话")

                # 保持浏览器打开，直到用户关闭
                try:
                    while True:
                        if page.is_closed():
                            break
                        time.sleep(1)
                except Exception:
                    pass

                print("手动浏览器已关闭")

        except Exception as e:
            print(f"手动浏览器出错: {e}")
            return 1
        return 0
    except Exception as e:
        # 原 messagebox.showerror("错误", f"打开手动浏览器失败: {e}") 改为 print
        print(f"打开手动浏览器失败: {e}")
        return 1
