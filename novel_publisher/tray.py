"""系统托盘图标管理"""

import base64
import threading

import pystray
from PIL import Image
from io import BytesIO

from icon import tomato_png


def create_tray_icon(title: str, on_show, on_exit) -> pystray.Icon:
    """创建托盘图标实例（不启动）。

    Args:
        title: 鼠标悬停提示文字
        on_show: 点击"显示窗口"时的回调 (icon, item) -> None
        on_exit: 点击"退出"时的回调 (icon, item) -> None

    Returns:
        pystray.Icon 实例
    """
    byte_data = base64.b64decode(tomato_png)
    image = Image.open(BytesIO(byte_data))
    menu = (
        pystray.MenuItem('显示窗口', on_show, default=True),
        pystray.MenuItem('退出', on_exit)
    )
    return pystray.Icon("自动发布Tool", image, title, menu)


def run_tray_in_thread(icon: pystray.Icon) -> threading.Thread:
    """在守护线程中启动托盘图标。"""
    t = threading.Thread(target=icon.run, daemon=True)
    t.start()
    return t
