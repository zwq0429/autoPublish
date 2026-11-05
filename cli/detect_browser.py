"""浏览器自动检测 CLI。

来源: app.py 行 1971-2015
  - auto_detect_browser (1971-2002)：原为后台线程执行避免阻塞界面，CLI 改为同步调用；
  - _update_browser_path (2004-2007)：原为 UI 变量赋值 + messagebox.showinfo，
    CLI 改为写回 config.ini [Settings] custom_browser_path 并 print
    （写回值与源 save_config 1715 行一致，做 replace('\\', '/')）；
  - _show_no_browser_found (2009-2011)：messagebox.showwarning 改为 print；
  - _show_detection_error (2013-2015)：messagebox.showerror 改为 print；
  - 浏览器枚举/推荐逻辑来自根目录 browser_detector.py 的 BrowserDetector
    （detect_all_browsers 内部即逐项打印检测列表，与源码输出一致）。

退出码: 0 找到浏览器 / 1 未找到 / 2 检测异常。
"""

import configparser
import os

from browser_detector import BrowserDetector


def _update_browser_path(path, config_file, save=True):
    """原 _update_browser_path（app.py 2004-2007）的去 UI 化版本：
    原 self.custom_browser_path_var.set(path) + messagebox.showinfo 改为
    写回 config.ini [Settings] custom_browser_path（--no-save 时跳过写回）并 print。"""
    if save:
        config = configparser.ConfigParser()
        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')
        if not config.has_section('Settings'):
            config['Settings'] = {}
        # 与源 save_config(1715) 的保存格式一致：统一正斜杠
        config['Settings']['custom_browser_path'] = path.replace('\\', '/')
        with open(config_file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        print(f"已写回配置文件 {config_file} [Settings] custom_browser_path")
    print(f"成功: 已自动检测到浏览器路径:\n{path}")


def _show_no_browser_found():
    """原 _show_no_browser_found（app.py 2009-2011）的去 UI 化版本：messagebox 改为 print。"""
    print("提示: 未检测到可用的浏览器\n请手动设置浏览器路径")


def _show_detection_error(error_msg):
    """原 _show_detection_error（app.py 2013-2015）的去 UI 化版本：messagebox 改为 print。"""
    print(f"检测失败: 浏览器检测失败:\n{error_msg}\n\n请手动设置浏览器路径")


def register(subparsers):
    """向 argparse 子命令注册参数。"""
    subparsers.add_argument('--config', default='config.ini',
                            help='配置文件路径（默认 config.ini）')
    subparsers.add_argument('--no-save', dest='no_save', action='store_true',
                            help='检测到后不写回 config.ini（默认写回 [Settings] custom_browser_path）')


def main(args) -> int:
    """执行 detect-browser 命令，返回退出码（0 找到 / 1 未找到 / 2 异常）。"""
    print("开始自动检测浏览器...")
    try:
        # 原在新线程 detect_worker 中执行，CLI 同步调用
        # 获取推荐的浏览器路径（内部 detect_all_browsers 会逐项打印检测列表）
        recommended_path = BrowserDetector.get_recommended_browser()

        if recommended_path:
            print(f"自动检测到浏览器: {recommended_path}")
            _update_browser_path(recommended_path, args.config, save=not args.no_save)
            return 0
        else:
            _show_no_browser_found()
            print("未检测到可用的浏览器")
            return 1

    except Exception as e:
        _show_detection_error(str(e))
        print(f"浏览器检测失败: {e}")
        return 2
