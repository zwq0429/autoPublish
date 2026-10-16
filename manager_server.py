"""
寒山 小说项目管理服务端
运行后自动打开浏览器，通过 Web 界面管理所有小说项目。
"""
import re
import os
import time
import configparser
import json
import glob
import logging
import traceback
import subprocess
import threading
import shutil
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import io
import base64

try:
    import pystray
    from PIL import Image as PILImage
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    from icon import tray_icon_png
except ImportError:
    tray_icon_png = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manager_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

PORT = 18765
DEFAULT_ROOT_DIR = Path(r"E:\AutoWriter")
ROOT_DIR = DEFAULT_ROOT_DIR if DEFAULT_ROOT_DIR.is_dir() else Path.cwd()
DEFAULT_BROWSER_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USER_DATA_FILE = ROOT_DIR / "user_data.json"
NOVEL_INFO_FILE = ROOT_DIR / "novel_info.json"
HTML_FILE = ROOT_DIR / "manager_web.html"

# 日志缓冲区（供前端轮询）
log_buffer = []
log_lock = threading.Lock()

# 任务进度追踪
progress_lock = threading.Lock()
total_tasks = 0
completed_tasks = 0


def _collect_top_windows():
    """收集当前所有可见顶层窗口句柄（Windows）。"""
    handles = set()
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
        user32.IsWindowVisible.argtypes = [wt.HWND]

        @WNDENUMPROC
        def cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                handles.add(hwnd)
            return True

        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    return handles


def _topmost_new_window(before_handles, timeout=4.0):
    """将 before_handles 之后新出现的可见顶层窗口置顶到当前网页之上。

    先 HWND_TOPMOST 浮到最前（确保覆盖浏览器），短暂保持后取消置顶，
    使窗口停留在前台而不永久锁定在最前。
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        import time
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        HWND_TOPMOST = ctypes.c_void_p(-1)
        HWND_NOTOPMOST = ctypes.c_void_p(-2)
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040

        user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
        user32.IsWindowVisible.argtypes = [wt.HWND]
        user32.GetWindowTextLengthW.argtypes = [wt.HWND]
        user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.SetForegroundWindow.argtypes = [wt.HWND]
        found = []

        @WNDENUMPROC
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            if hwnd in before_handles:
                return True
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True
            found.append(hwnd)
            return True

        deadline = time.time() + timeout
        while time.time() < deadline:
            found = []
            user32.EnumWindows(cb, 0)
            if found:
                hwnd = found[0]
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
                try:
                    user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.8)  # 短暂保持置顶，确保已覆盖在网页之上
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE)
                return True
            time.sleep(0.2)
    except Exception:
        pass
    return False


def append_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    with log_lock:
        log_buffer.append(line)
        if len(log_buffer) > 500:
            log_buffer.pop(0)
    logging.info(msg)


class InfoCollector:
    def __init__(self, root_dir=None):
        self.root_dir = Path(root_dir) if root_dir else ROOT_DIR
        self.collector_info_history_path = self.root_dir / "novel_info.json"
        if self.collector_info_history_path.exists():
            with open(self.collector_info_history_path, 'r', encoding='utf-8') as f:
                self.all_novel_info = json.load(f)
        else:
            self.all_novel_info = []

    def get_fenshen_folders(self):
        try:
            return [d for d in self.root_dir.iterdir() if d.is_dir()]
        except Exception as e:
            logging.error(f"Error reading root directory: {e}")
            return []

    def read_config_info(self, project_path: Path):
        config_path = project_path / "config.ini"
        if not config_path.exists():
            return None
        config = configparser.ConfigParser(interpolation=None)
        try:
            config.read(config_path, encoding='utf-8')
            novel_path_str = config.get('Novel', 'novels_folder', fallback='')
            novel_path_resolved = ''
            if novel_path_str:
                novel_path_resolved = str((project_path / novel_path_str).resolve())
            daily_plan_config = config.get('Settings', 'daily_publish_num', fallback=0)
            daily_plan = daily_plan_config + '章/' if daily_plan_config != '-1' else config.get('Settings', 'daily_publish_count', fallback='0') + '字/'
            plan_status = config.get('History', 'daily_publish_num_remain', fallback='0') == '0' if daily_plan_config != '-1' else config.get('History', 'daily_publish_count_remain', fallback='0') == '0'
            daily_plan += config.get('Settings', 'interval_publish_mode', fallback='1/0')
            return {
                'project_name': project_path.name,
                'plan_status': plan_status,
                'title': config.get('Novel', 'novel_title', fallback='未知'),
                'platform': config.get('Settings', 'publish_plate', fallback='未知'),
                'last_publish_date': config.get('History', 'last_published_chapter_date', fallback='从未发布'),
                'published_chapters': config.getint('History', 'last_published_chapter', fallback=0),
                'daily_plan': daily_plan,
                'novel_writer': config.get('Novel', 'novel_writer', fallback='佚名'),
                'novel_path': novel_path_resolved,
                'novel_status': config.get('Novel', 'novel_status', fallback='未设置'),
            }
        except Exception as e:
            logging.error(f"Failed to read config file {config_path}: {e}")
            return None

    def collect_all_info(self):
        # logging.info("Starting to collect information...")
        fenshen_folders = self.get_fenshen_folders()
        all_info = [info.get('title') for info in self.all_novel_info]
        new_info = []
        for folder_path in fenshen_folders:
            info = self.read_config_info(folder_path)
            if info:
                novel_path = info.get('novel_path')
                if novel_path and Path(novel_path).is_dir():
                    if info.get('title') in all_info:
                        index = all_info.index(info.get('title'))
                        if info.get('published_chapters') == self.all_novel_info[index]['published_chapters']:
                            info['total_words'] = self.all_novel_info[index]['total_words']
                        else:
                            info['total_words'] = self.estimate_word_count(novel_path, int(info['published_chapters']))
                    else:
                        info['total_words'] = self.estimate_word_count(novel_path, int(info['published_chapters']))
                    info['total_chapters'] = self.count_chapters(novel_path)
                else:
                    info['total_chapters'] = 0
                    info['total_words'] = 0
                new_info.append(info)
        self.all_novel_info = new_info
        return self.all_novel_info

    def count_chapters(self, novel_folder_path: str) -> int:
        novel_path = Path(novel_folder_path)
        if not novel_path.is_dir():
            return 0
        return len(list(novel_path.glob("Chapter*.md")))

    def estimate_word_count(self, novel_folder_path: str, sample_size: int = 5) -> int:
        novel_path = Path(novel_folder_path)
        if not novel_path.is_dir():
            return 0
        chapter_files = sorted(list(novel_path.glob("Chapter*.md")),
                                key=lambda f: int(re.search(r'Chapter_(\d+)', f.name).group(1)))
        if not chapter_files:
            return 0

        def process_chapter(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content[content.find('\n'):]
                text = content.replace('\n', '').replace(' ', '')
                chars = 0
                for ch in text:
                    cp = ord(ch)
                    if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF  # CJK
                            or cp < 128 or cp in (0x3001, 0x3002, 0xFF0C, 0xFF0E,
                            0x300A, 0x300B, 0x2018, 0x2019, 0x201C, 0x201D,
                            0xFF08, 0xFF09, 0x3010, 0x3011,
                            0x2026, 0x2014, 0xFF05, 0xFE30)):
                        chars += 1
                return (True, chars)
            except Exception as e:
                logging.error(f"Could not read file {file_path}: {e}")
                return (False, 0)

        total_chars_sample = 0
        with ThreadPoolExecutor() as executor:
            results = executor.map(process_chapter, chapter_files[:sample_size])
        for success, char_count in results:
            if success:
                total_chars_sample += char_count
        return total_chars_sample

    def save_to_json(self, output_file="novel_info.json"):
        if not self.all_novel_info:
            return False
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.all_novel_info, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logging.error(f"Failed to save: {e}")
            return False


collector = InfoCollector()
task_queue = Queue()
batch_pool_running = False
batch_pool_lock = threading.Lock()
MAX_CONCURRENT = 5  # 非单线模式最大并发数，可通过 /api/config 修改


def load_user_marks():
    default = {
        "normal_config": {"weak_mode": False, "headless": False, "single_thread": False, "max_concurrent": 5},
        "account_tags": [],
        "novel_statuses": ["待书测", "待封测", "封测中", "全勤中", "已完结", "待创建", "待签约", "已签约", "划水期"],
        "novels": {}
    }
    if USER_DATA_FILE.exists():
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'account_tags' in data:
                return data
        except Exception:
            pass
    return default


def save_user_marks(data):
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to save user marks: {e}")


MANAGER_CONFIG_FILE = Path(os.path.expanduser("~\\Documents")) / "_manager_config.json"


def load_manager_config():
    """加载管理器配置（工作目录等）"""
    default = {"root_dir": str(ROOT_DIR), "browser_path": DEFAULT_BROWSER_PATH}
    if MANAGER_CONFIG_FILE.exists():
        try:
            with open(MANAGER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'root_dir' in data:
                return data
        except Exception:
            pass
    return default


def save_manager_config(config):
    """保存管理器配置"""
    try:
        with open(MANAGER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save manager config: {e}")


def get_novel_info(title):
    """根据书名查找小说信息"""
    for n in collector.all_novel_info:
        if n.get('title') == title:
            return n
    return None


def get_app_path(project_name):
    """获取项目的 app.exe 路径"""
    project_path = ROOT_DIR / project_name
    app_path = project_path / "app.exe"
    if app_path.exists():
        return str(project_path), str(app_path)
    return None, None


def update_root_dir(new_dir):
    """更新工作目录"""
    global ROOT_DIR, USER_DATA_FILE, NOVEL_INFO_FILE, HTML_FILE, collector
    new_path = Path(new_dir)
    if not new_path.is_dir():
        return False, f"目录不存在: {new_dir}"
    ROOT_DIR = new_path
    USER_DATA_FILE = ROOT_DIR / "user_data.json"
    NOVEL_INFO_FILE = ROOT_DIR / "novel_info.json"
    HTML_FILE = ROOT_DIR / "manager_web.html"
    collector = InfoCollector(root_dir=ROOT_DIR)
    collector.collect_all_info()
    collector.save_to_json()
    config = load_manager_config()
    config['root_dir'] = str(ROOT_DIR)
    save_manager_config(config)
    append_log(f"工作目录已切换: {ROOT_DIR}")
    return True, str(ROOT_DIR)


def update_all_browser_paths(browser_path=DEFAULT_BROWSER_PATH):
    """批量修改所有项目 config.ini 中的浏览器路径"""
    browser = Path(browser_path)
    if not browser.is_file():
        return {"success": False, "message": f"浏览器不存在: {browser_path}", "fails": []}

    success = 0
    fails = []
    for config_path in ROOT_DIR.glob("*/config.ini"):
        try:
            config = configparser.ConfigParser(interpolation=None)
            config.read(str(config_path), encoding='utf-8')
            if 'Settings' not in config:
                config.add_section('Settings')
            config['Settings']['custom_browser_path'] = str(browser)
            with open(str(config_path), 'w', encoding='utf-8') as f:
                config.write(f)
            success += 1
        except Exception as e:
            fails.append(f"{config_path.parent.name}: {e}")
            logging.error(f"批量修改浏览器路径失败 {config_path}: {e}")

    msg = f"浏览器路径已更新 {success} 个项目"
    if fails:
        msg += f", 失败 {len(fails)} 个: {'; '.join(fails[:3])}{'...' if len(fails) > 3 else ''}"
    append_log(msg)
    return {"success": success > 0, "message": msg, "fails": fails, "success_count": success}


def check_outline_file(project_path):
    """校验项目目录下是否存在以'大纲.txt'结尾的文件，且文件中包含'开书信息'键值。

    Args:
        project_path: 项目文件夹路径

    Returns:
        (bool, str): (是否通过校验, 提示信息)
    """
    # 查找以"大纲.txt"结尾的文件
    outline_files = glob.glob(os.path.join(project_path, "*大纲.txt"))
    if not outline_files:
        return False, "未找到以'大纲.txt'结尾的文件"

    # 检查文件中是否包含"开书信息"键值
    for fpath in outline_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            if '&&&开书信息&&&' in content:
                return True, f"大纲文件校验通过: {os.path.basename(fpath)}"
        except Exception as e:
            logging.error(f"读取大纲文件失败 {fpath}: {e}")

    return False, "大纲文件中未找到'&&&开书信息&&&'键值"


TASK_TIMEOUT = 1800  # 单任务超时 30 分钟（秒）


def run_app(project_folder_path, app_path, func_name, headless=False):
    """执行 app.exe，超时 30 分钟自动终止"""
    global completed_tasks
    exec_command = f'"{app_path}" -fast {func_name}'
    if headless:
        exec_command += " --headless "
    append_log(f"{func_name} 开始执行: {project_folder_path}")
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.lpTitle = f"[{func_name}]{project_folder_path}"
    process = None
    timed_out = [False]
    try:
        process = subprocess.Popen(
            exec_command, cwd=project_folder_path,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True,
            startupinfo=startupinfo
        )

        # 超时守护线程：30 分钟后强制终止
        def _timeout_killer():
            time.sleep(TASK_TIMEOUT)
            if process.poll() is None:
                timed_out[0] = True
                append_log(f"{func_name} 超时({TASK_TIMEOUT}s)，强制终止: {project_folder_path}")
                try:
                    process.kill()
                except Exception:
                    pass

        threading.Thread(target=_timeout_killer, daemon=True).start()

        for line in iter(process.stdout.readline, ''):
            if line:
                append_log(line.strip())
        process.stdout.close()
        process.wait()
        if timed_out[0]:
            append_log(f"{func_name} 已因超时终止: {project_folder_path}")
        else:
            append_log(f"{func_name} 执行完成")
    except Exception as e:
        append_log(f"{func_name} 执行失败: {e}")
    finally:
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
        with progress_lock:
            completed_tasks += 1


def open_browser_for_project(title):
    """用 Playwright 打开浏览器"""
    info = get_novel_info(title)
    if not info:
        return "找不到项目信息"

    project_name = info.get('project_name')
    project_path, _ = get_app_path(project_name)
    if not project_path:
        return "找不到项目路径"

    config_path = os.path.join(project_path, 'config.ini')
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    cookies_file = os.path.join(project_path, 'auth.json')
    publish_plate = config.get('Settings', 'publish_plate', fallback='番茄')
    custom_browser_path = config.get('Settings', 'custom_browser_path', fallback='')

    site_urls = {
        '番茄': "https://fanqienovel.com/main/writer/?enter_from=author_zone",
        '起点': "https://write.qq.com/portal/dashboard",
        'Q阅': "https://write.qq.com/portal/dashboard",
        '七猫': "https://zuozhe.qimao.com/front/index",
        '纵横': "https://zuozhe.qimao.com/front/index",
        '飞卢': "https://author.faloo.com/index2020.aspx",
        '微信': "https://mp.weixin.qq.com/cgi-bin/home",
        '书旗': "https://yc.aliwx.com.cn/author",
        '晋江': "https://my.jjwxc.net/backend/oneauthor_login.php",
        '息壤': "https://www.xrzww.com/authorhome/workmanagement",
    }
    site_url = site_urls.get(publish_plate, '')
    # 启动前收集现有窗口，浏览器打开后将其置顶到当前网页之上
    before = _collect_top_windows()

    def _run():
        try:
            # #region debug-point A:playwright-init
            try:
                _debug_payload = json.dumps({"sessionId": "browser-context-manager", "runId": "pre-fix", "hypothesisId": "A", "location": "manager_server.py:538", "msg": "[DEBUG] entering sync_playwright context", "data": {"thread": threading.current_thread().name}}).encode()
                urllib_request = __import__("urllib.request", fromlist=["Request"])
                urllib_request.urlopen(urllib_request.Request("http://127.0.0.1:7777/event", data=_debug_payload, headers={"Content-Type": "application/json"}), timeout=2).read()
            except Exception:
                pass
            # #endregion
            with sync_playwright() as p:
                # #region debug-point A:playwright-ready
                try:
                    _debug_payload = json.dumps({"sessionId": "browser-context-manager", "runId": "pre-fix", "hypothesisId": "A", "location": "manager_server.py:550", "msg": "[DEBUG] sync_playwright context ready", "data": {"playwright_type": type(p).__name__, "chromium_type": type(p.chromium).__name__}}).encode()
                    urllib_request.urlopen(urllib_request.Request("http://127.0.0.1:7777/event", data=_debug_payload, headers={"Content-Type": "application/json"}), timeout=2).read()
                except Exception:
                    pass
                # #endregion
                launch_args = {
                    "headless": False,
                    "args": [
                        "--disable-popup-blocking",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-blink-features=AutomationControlled"
                    ],
                    "ignore_default_args": ["--enable-automation"]
                }
                if custom_browser_path:
                    launch_args["executable_path"] = custom_browser_path
                browser = p.chromium.launch(**launch_args)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=cookies_file if os.path.exists(cookies_file) else None
                )
                page = context.new_page()
                # 将新打开的浏览器窗口置顶到当前网页之上
                threading.Thread(target=_topmost_new_window, args=(before,), daemon=True).start()
                # page.set_viewport_size({"width": 1920, "height": 1080})
                if site_url:
                    page.goto(site_url, timeout=60000)
                    append_log(f"已打开浏览器: {publish_plate} - {title}")
                while True:
                    if page.is_closed():
                        break
                    time.sleep(1)
        except Exception as e:
            append_log(f"浏览器出错: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return "浏览器已启动"


def batch_pool_worker(max_workers):
    """线程池并发执行队列中的任务，最多 max_workers 个同时运行"""
    global batch_pool_running
    semaphore = threading.Semaphore(max_workers)
    threads = []

    def run_with_semaphore(task):
        semaphore.acquire()
        try:
            app_path, project_folder_path, func_name, headless = task
            run_app(project_folder_path, app_path, func_name, headless)
        finally:
            semaphore.release()

    while not task_queue.empty():
        task = task_queue.get()
        t = threading.Thread(target=run_with_semaphore, args=(task,), daemon=True)
        t.start()
        threads.append(t)
        task_queue.task_done()

    for t in threads:
        t.join()

    with batch_pool_lock:
        batch_pool_running = False


def start_batch_worker(single_thread):
    """启动批量任务 worker（调用前确保所有任务已入队）"""
    global batch_pool_running
    workers = 1 if single_thread else MAX_CONCURRENT
    with batch_pool_lock:
        if not batch_pool_running:
            batch_pool_running = True
            threading.Thread(target=batch_pool_worker, args=(workers,), daemon=True).start()


def execute_action(title, action, headless=False, single_thread=False):
    """执行单个项目的操作（仅入队，不启动 worker）"""
    info = get_novel_info(title)
    if not info:
        return {"success": False, "message": f"找不到项目: {title}"}

    # 待创建/未设置/已完结 不允许执行发布相关操作
    user_marks = load_user_marks()
    marks = user_marks.get('novels', {}).get(title, {})
    st = marks.get('status', info.get('novel_status', ''))
    if st in ['待创建', '未创建', '未设置', '已完结']:
        return {"success": False, "message": f"状态为「{st}」，不允许执行操作"}

    project_name = info.get('project_name')
    project_path, app_path = get_app_path(project_name)

    if not app_path:
        return {"success": False, "message": f"找不到 app.exe: {project_name}"}

    action_map = {
        "publish": "本地定时发布",
        "sign": "自动签约",
        "verify": "自动验证",
        "book_test": "书测",
        "cover_test": "封测",
        "check_plan": "发布进度自检",
        "check_attendance": "全勤检查",
        "cancel_schedule": "取消定时",
        "create_book": "快速创书",
    }

    if action == "open_browser":
        msg = open_browser_for_project(title)
        return {"success": True, "message": msg}

    func_name = action_map.get(action)
    if not func_name:
        return {"success": False, "message": f"未知操作: {action}"}

    # 特殊检查
    if action == "book_test":
        test_dir = os.path.join(project_path, "书测")
        if not os.path.exists(test_dir):
            return {"success": False, "message": f"未找到书测文件夹: {title}"}
    if action == "cover_test":
        test_dir = os.path.join(project_path, "封测")
        if not os.path.exists(test_dir):
            return {"success": False, "message": f"未找到封测文件夹: {title}"}
    if action == "sign":
        sign_file = os.path.join(project_path, "签约信息.txt")
        if not os.path.exists(sign_file) and os.path.exists("签约信息.txt"):
            os.link("签约信息.txt", sign_file)
    if action == "create_book":
        ok, msg = check_outline_file(project_path)
        if not ok:
            return {"success": False, "message": f"{title}: {msg}"}

    task_queue.put((app_path, project_path, func_name, headless))
    return {"success": True, "message": f"已加入队列: {title} - {func_name}"}


def execute_action_single(title, action, headless=False):
    """直接启线程执行单个项目（不入队列）"""
    info = get_novel_info(title)
    if not info:
        return {"success": False, "message": f"找不到项目: {title}"}

    user_marks = load_user_marks()
    marks = user_marks.get('novels', {}).get(title, {})
    st = marks.get('status', info.get('novel_status', ''))
    if st in ['待创建', '未创建', '未设置', '已完结'] and action != "create_book":
        return {"success": False, "message": f"状态为「{st}」，不允许执行操作"}

    project_name = info.get('project_name')
    project_path, app_path = get_app_path(project_name)

    if not app_path:
        return {"success": False, "message": f"找不到 app.exe: {project_name}"}

    action_map = {
        "publish": "本地定时发布",
        "sign": "自动签约",
        "verify": "自动验证",
        "book_test": "书测",
        "cover_test": "封测",
        "check_plan": "发布进度自检",
        "check_attendance": "全勤检查",
        "cancel_schedule": "取消定时",
        "create_book": "快速创书",
    }

    if action == "open_browser":
        msg = open_browser_for_project(title)
        return {"success": True, "message": msg}

    func_name = action_map.get(action)
    if not func_name:
        return {"success": False, "message": f"未知操作: {action}"}

    if action == "book_test":
        test_dir = os.path.join(project_path, "书测")
        if not os.path.exists(test_dir):
            return {"success": False, "message": f"未找到书测文件夹: {title}"}
    if action == "cover_test":
        test_dir = os.path.join(project_path, "封测")
        if not os.path.exists(test_dir):
            return {"success": False, "message": f"未找到封测文件夹: {title}"}
    if action == "sign":
        sign_file = os.path.join(project_path, "签约信息.txt")
        if not os.path.exists(sign_file) and os.path.exists("签约信息.txt"):
            os.link("签约信息.txt", sign_file)
    if action == "create_book":
        ok, msg = check_outline_file(project_path)
        if not ok:
            return {"success": False, "message": f"{title}: {msg}"}

    global total_tasks
    with progress_lock:
        total_tasks += 1
    threading.Thread(target=run_app, args=(project_path, app_path, func_name, headless), daemon=True).start()
    return {"success": True, "message": f"已启动: {title} - {func_name}"}


def batch_action(action, account_tag, status, headless, single_thread):
    """批量执行操作"""
    global total_tasks, completed_tasks
    with progress_lock:
        total_tasks = 0
        completed_tasks = 0
    user_marks = load_user_marks()
    results = []
    for novel in collector.all_novel_info:
        title = novel.get('title', '')
        marks = user_marks.get('novels', {}).get(title, {})
        tag = marks.get('account_tag', novel.get('novel_writer', '佚名'))
        st = marks.get('status', novel.get('novel_status', '未知状态'))
        if account_tag and tag != account_tag:
            continue
        if status and st != status:
            continue
        if st in ['待创建', '未设置', '已完结']:
            continue
        # 对于发布操作，额外检查
        if action == "publish":
            last_date = novel.get('last_publish_date', '')
            daily_plan = novel.get('daily_plan', '')
            plan_status = novel.get('plan_status', True)
            if last_date and last_date != '从未发布':
                try:
                    pub_date = datetime.strptime(last_date, '%Y-%m-%d')
                    today = datetime.now()
                    diff_days = (pub_date - today).days
                    interval_status = False
                    if daily_plan and '/' in daily_plan:
                        parts = daily_plan.split('/')
                        if len(parts) >= 3:
                            interval = int(parts[1]) or 1
                            remainder = int(parts[2]) or 0
                            if (today.toordinal() % interval) == remainder:
                                interval_status = True
                    if diff_days > -2 or not interval_status:
                        continue
                except Exception:
                    pass
        result = execute_action(title, action, headless, single_thread)
        if result.get('success'):
            with progress_lock:
                total_tasks += 1
        results.append(result)
    start_batch_worker(single_thread)
    return results


def create_fenshen(template_title, new_name):
    """创建新分身"""
    template_info = get_novel_info(template_title)
    if not template_info:
        return {"success": False, "message": f"找不到模板项目: {template_title}"}

    template_project_name = template_info.get('project_name')
    template_path = ROOT_DIR / template_project_name
    new_project_path = ROOT_DIR / new_name

    if new_project_path.exists():
        return {"success": False, "message": f"项目文件夹已存在: {new_name}"}

    try:
        os.makedirs(new_project_path)
        for filename in ["app.exe", "auth.json", "签约信息.txt"]:
            src = template_path / filename
            dst = new_project_path / filename
            if src.exists():
                try:
                    os.link(str(src), str(dst))
                except OSError as e:
                    logging.warning(f"创建分身: {filename} 硬链接失败，改为复制: {e}")
                    shutil.copy2(str(src), str(dst))

        old_config = configparser.ConfigParser()
        old_config.read(str(template_path / "config.ini"), encoding='utf-8')
        config = configparser.ConfigParser()
        config['Settings'] = old_config['Settings']
        config['Novel'] = {
            'novel_title': new_name,
            'novel_writer': template_info.get('novel_writer', ''),
            'novels_folder': '小说正文',
            'novel_status': '待创建'
        }
        config['History'] = {}
        with open(str(new_project_path / "config.ini"), 'w', encoding='utf-8') as f:
            config.write(f)

        collector.collect_all_info()
        collector.save_to_json()
        return {"success": True, "message": f"新分身创建成功: {new_name}"}
    except Exception as e:
        if new_project_path.exists():
            shutil.rmtree(str(new_project_path))
        return {"success": False, "message": f"创建失败: {e}"}


def delete_project(title):
    """删除项目"""
    info = get_novel_info(title)
    if not info:
        return {"success": False, "message": f"找不到项目: {title}"}

    errors = []
    novel_path = info.get('novel_path')
    project_name = info.get('project_name')
    project_path = ROOT_DIR / project_name if project_name else None

    if novel_path and os.path.exists(novel_path):
        try:
            shutil.rmtree(novel_path)
        except Exception as e:
            errors.append(f"删除小说文件夹失败: {e}")

    if project_path and project_path.exists():
        try:
            shutil.rmtree(str(project_path))
        except Exception as e:
            errors.append(f"删除项目文件夹失败: {e}")

    # 清理 user_marks
    user_marks = load_user_marks()
    if title in user_marks.get('novels', {}):
        del user_marks['novels'][title]
        save_user_marks(user_marks)

    collector.collect_all_info()
    collector.save_to_json()

    if errors:
        return {"success": False, "message": "; ".join(errors)}
    return {"success": True, "message": f"已删除: {title}"}


def update_all_apps(file_name, file_data):
    """用上传的 app.exe 更新所有项目"""
    import base64
    if not file_data:
        return {"success": False, "message": "未收到文件数据"}
    if not file_name.lower().endswith('.exe'):
        return {"success": False, "message": "只接受 .exe 文件"}

    # 写入临时文件到 ROOT_DIR（与目标同盘，硬链接不能跨盘）
    tmp_path = ROOT_DIR / f"_tmp_{int(time.time())}_{file_name}"
    try:
        with open(tmp_path, 'wb') as tmp:
            tmp.write(base64.b64decode(file_data))
        source_app_path = str(tmp_path)
        logging.info(f"更新APP: 收到文件 {file_name}, 大小 {tmp_path.stat().st_size} 字节, 写入 {source_app_path}")
    except Exception as e:
        logging.error(f"更新APP: 文件写入失败: {e}")
        return {"success": False, "message": f"文件写入失败: {e}"}

    success = 0
    fails = []
    for novel in collector.all_novel_info:
        project_name = novel.get('project_name')
        if not project_name:
            continue
        target = ROOT_DIR / project_name / "app.exe"
        try:
            if target.exists():
                os.remove(str(target))
            os.link(source_app_path, str(target))
            success += 1
        except Exception as e:
            logging.error(f"更新APP: {project_name} 硬链接失败: {e}")
            # 硬链接失败时尝试复制
            try:
                shutil.copy2(source_app_path, str(target))
                success += 1
                logging.info(f"更新APP: {project_name} 改为复制成功")
            except Exception as e2:
                fails.append(f"{project_name}: {e2}")
                logging.error(f"更新APP: {project_name} 复制也失败: {e2}")

    # 清理临时文件
    try:
        os.unlink(source_app_path)
    except Exception:
        pass

    msg = f"更新成功 {success} 个"
    if fails:
        msg += f", 失败 {len(fails)} 个: {fails[:3]}{'...' if len(fails) > 3 else ''}"
    logging.info(f"更新APP: {msg}")
    return {"success": True, "message": msg, "fails": fails}


def migrate_projects(account_tags, target_dir):
    """批量移植指定作者账号的项目到目标文件夹

    account_tags: 单个账号名(str) 或 账号名列表(list)
    - app.exe: 目标目录中只保留一个实体文件，其余硬链接（全账号共享）
    - auth.json: 同账号的项目之间硬链接（按账号分别处理）
    - 其他文件/文件夹: 直接复制
    """
    if isinstance(account_tags, str):
        account_tags = [account_tags]
    account_tags = [t for t in account_tags if t]
    if not account_tags:
        return {"success": False, "message": "未选择任何账号"}

    target_path = Path(target_dir)
    if not target_path.is_dir():
        try:
            target_path.mkdir(parents=True)
        except Exception as e:
            return {"success": False, "message": f"目标目录创建失败: {e}"}

    # 找出这些账号的所有项目，并记录每个项目所属账号
    user_marks = load_user_marks()
    projects_to_migrate = []
    for novel in collector.all_novel_info:
        title = novel.get('title', '')
        marks = user_marks.get('novels', {}).get(title, {})
        tag = marks.get('account_tag', novel.get('novel_writer', '佚名'))
        if tag in account_tags:
            projects_to_migrate.append((novel, tag))

    if not projects_to_migrate:
        return {"success": False, "message": f"未找到账号 {account_tags} 的项目"}

    # 扫描目标目录，复用已有的 app.exe（全局共享）和各账号的 auth.json
    app_source = None
    auth_sources = {}  # {account_tag: auth_path}
    for d in target_path.iterdir():
        if not d.is_dir():
            continue
        app_file = d / 'app.exe'
        if app_file.exists() and app_source is None:
            app_source = app_file
        auth_file = d / 'auth.json'
        config_file = d / 'config.ini'
        if auth_file.exists() and config_file.exists():
            try:
                cfg = configparser.ConfigParser(interpolation=None)
                cfg.read(str(config_file), encoding='utf-8')
                writer = cfg.get('Novel', 'novel_writer', fallback='')
                if writer in account_tags and writer not in auth_sources:
                    auth_sources[writer] = auth_file
            except Exception:
                pass

    success = 0
    fails = []
    tags_display = '、'.join(account_tags) if len(account_tags) > 1 else account_tags[0]
    append_log(f"开始移植账号「{tags_display}」的 {len(projects_to_migrate)} 个项目到 {target_path}")

    for novel, this_tag in projects_to_migrate:
        project_name = novel.get('project_name', '')
        src_project_path = ROOT_DIR / project_name
        dst_project_path = target_path / project_name

        if not src_project_path.exists():
            fails.append(f"{project_name}: 源项目不存在")
            continue

        try:
            # 如果目标已存在，先清理
            if dst_project_path.exists():
                shutil.rmtree(str(dst_project_path))
            dst_project_path.mkdir(parents=True)

            for item in src_project_path.iterdir():
                src_file = src_project_path / item.name
                dst_file = dst_project_path / item.name

                if item.is_file():
                    if item.name == 'app.exe':
                        # app.exe: 全局只保留一个实体，其余硬链接
                        if app_source is None:
                            shutil.copy2(str(src_file), str(dst_file))
                            app_source = dst_file
                        else:
                            try:
                                os.link(str(app_source), str(dst_file))
                            except Exception:
                                shutil.copy2(str(src_file), str(dst_file))
                    elif item.name == 'auth.json':
                        # auth.json: 按账号硬链接
                        if this_tag not in auth_sources:
                            shutil.copy2(str(src_file), str(dst_file))
                            auth_sources[this_tag] = dst_file
                        else:
                            try:
                                os.link(str(auth_sources[this_tag]), str(dst_file))
                            except Exception:
                                shutil.copy2(str(src_file), str(dst_file))
                    else:
                        shutil.copy2(str(src_file), str(dst_file))
                elif item.is_dir():
                    shutil.copytree(str(src_file), str(dst_file))

            success += 1
            append_log(f"已移植: {project_name}")
        except Exception as e:
            fails.append(f"{project_name}: {e}")
            append_log(f"移植失败: {project_name}: {e}")

    msg = f"移植成功 {success} 个"
    if fails:
        msg += f", 失败 {len(fails)} 个: {'; '.join(fails[:3])}{'...' if len(fails) > 3 else ''}"
    append_log(msg)
    return {"success": success > 0, "message": msg, "fails": fails, "success_count": success}


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 抑制默认日志

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length > 0:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/' or path == '/index.html':
            # 返回 HTML 页面
            if HTML_FILE.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(HTML_FILE, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self._send_json({"error": "HTML file not found"}, 404)
            return

        if path == '/api/novels':
            collector.collect_all_info()
            collector.save_to_json()
            self._send_json(collector.all_novel_info)
            return

        if path == '/api/marks':
            self._send_json(load_user_marks())
            return

        if path == '/api/logs':
            with log_lock:
                logs = list(log_buffer)
            self._send_json(logs)
            return

        if path == '/api/progress':
            with progress_lock:
                t, c = total_tasks, completed_tasks
            self._send_json({"total": t, "completed": c, "queue": task_queue.qsize()})
            return

        if path == '/api/config':
            config_file = os.path.join(os.path.expanduser("~\\Documents"), '_login_config.ini')
            account = ''
            if os.path.exists(config_file):
                c = configparser.ConfigParser()
                c.read(config_file, encoding='utf-8')
                account = c.get('Settings', 'Account', fallback='')
            self._send_json({"account": account, "max_concurrent": MAX_CONCURRENT})
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        if path == '/api/action':
            title = body.get('title', '')
            action = body.get('action', '')
            headless = body.get('headless', False)
            if not title or not action:
                self._send_json({"success": False, "message": "缺少参数"}, 400)
                return
            result = execute_action_single(title, action, headless)
            self._send_json(result)
            return

        if path == '/api/batch':
            action = body.get('action', '')
            account_tag = body.get('account_tag', '')
            status = body.get('status', '')
            headless = body.get('headless', False)
            single_thread = body.get('single_thread', False)
            if not action:
                self._send_json({"success": False, "message": "缺少 action 参数"}, 400)
                return
            results = batch_action(action, account_tag, status, headless, single_thread)
            self._send_json({"success": True, "results": results})
            return

        if path == '/api/marks':
            save_user_marks(body)
            self._send_json({"success": True})
            return

        if path == '/api/config':
            global MAX_CONCURRENT
            mc = body.get('max_concurrent')
            if mc is not None and isinstance(mc, int) and 1 <= mc <= 20:
                MAX_CONCURRENT = mc
                self._send_json({"success": True, "max_concurrent": MAX_CONCURRENT})
            else:
                self._send_json({"success": False, "message": "max_concurrent 需为 1-20 的整数"})
            return

        if path == '/api/create_fenshen':
            template_title = body.get('template_title', '')
            new_name = body.get('new_name', '')
            result = create_fenshen(template_title, new_name)
            self._send_json(result)
            return

        if path == '/api/delete':
            title = body.get('title', '')
            result = delete_project(title)
            self._send_json(result)
            return

        if path == '/api/update_apps':
            file_name = body.get('file_name', '')
            file_data = body.get('file_data', '')
            result = update_all_apps(file_name, file_data)
            self._send_json(result)
            return

        if path == '/api/update_browser_path':
            browser_path = body.get('browser_path', DEFAULT_BROWSER_PATH)
            result = update_all_browser_paths(browser_path)
            self._send_json(result)
            return

        if path == '/api/migrate':
            # 兼容 account_tag(单个) 和 account_tags(列表)
            account_tags = body.get('account_tags', '')
            if not account_tags:
                single = body.get('account_tag', '')
                account_tags = [single] if single else []
            if isinstance(account_tags, str):
                account_tags = [account_tags]
            target_dir = body.get('target_dir', '')
            if not account_tags or not target_dir:
                self._send_json({"success": False, "message": "缺少 account_tags 或 target_dir 参数"}, 400)
                return
            threading.Thread(target=lambda: migrate_projects(account_tags, target_dir), daemon=True).start()
            self._send_json({"success": True, "message": f"已开始移植 {len(account_tags)} 个账号的项目，请查看日志了解进度"})
            return

        if path == '/api/refresh':
            collector.collect_all_info()
            collector.save_to_json()
            self._send_json({"success": True, "novels": collector.all_novel_info})
            return

        if path == '/api/shutdown':
            self._send_json({"success": True, "message": "服务端正在退出..."})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if path == '/api/open_folder':
            title = body.get('title', '')
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            project_path = ROOT_DIR / info.get('project_name', '')
            if project_path.exists():
                before = _collect_top_windows()
                subprocess.Popen(['explorer', str(project_path)])
                # 后台将新打开的文件夹窗口置顶到当前网页之上
                threading.Thread(target=_topmost_new_window, args=(before,), daemon=True).start()
                self._send_json({"success": True, "message": f"已打开文件夹: {project_path}"})
            else:
                self._send_json({"success": False, "message": "项目文件夹不存在"})
            return

        if path == '/api/open_app':
            title = body.get('title', '')
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            project_path, app_path = get_app_path(info.get('project_name', ''))
            if app_path:
                before = _collect_top_windows()
                subprocess.Popen(str(app_path), cwd=str(project_path))
                # 后台将新打开发布工具的窗口置顶到当前网页之上
                threading.Thread(target=_topmost_new_window, args=(before,), daemon=True).start()
                self._send_json({"success": True, "message": f"已打开发布工具: {title}"})
            else:
                self._send_json({"success": False, "message": "未找到 app.exe"})
            return

        if path == '/api/update_auth':
            title = body.get('title', '')
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            template_project = ROOT_DIR / info.get('project_name', '')
            template_auth = template_project / 'auth.json'
            if not template_auth.exists():
                self._send_json({"success": False, "message": "模板项目没有 auth.json"})
                return
            writer = info.get('novel_writer', '')
            success, fail = 0, []
            for novel in collector.all_novel_info:
                if novel.get('novel_writer') != writer or novel.get('title') == title:
                    continue
                pn = novel.get('project_name', '')
                if not pn:
                    continue
                target = ROOT_DIR / pn / 'auth.json'
                try:
                    if target.exists():
                        os.remove(str(target))
                    try:
                        os.link(str(template_auth), str(target))
                    except OSError as e:
                        logging.warning(f"关联登录状态: {pn} auth.json 硬链接失败，改为复制: {e}")
                        shutil.copy2(str(template_auth), str(target))
                    success += 1
                except Exception as e:
                    fail.append(f"{pn}: {e}")
            self._send_json({"success": True, "message": f"已关联 {success} 个项目, 失败 {len(fail)}"})
            return

        if path == '/api/publish_next_day':
            def _wait_and_publish():
                now = datetime.now()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                wait_seconds = (tomorrow - now).total_seconds()
                append_log(f"发布次日已启动，预计 {tomorrow.strftime('%H:%M')} 自动发布，等待 {wait_seconds/3600:.1f} 小时")
                time.sleep(wait_seconds)
                append_log("发布次日：跨天检测触发，开始自动发布")
                collector.collect_all_info()
                user_marks = load_user_marks()
                for novel in collector.all_novel_info:
                    title = novel.get('title', '')
                    marks = user_marks.get('novels', {}).get(title, {})
                    st = marks.get('status', novel.get('novel_status', ''))
                    if st in ['待创建', '未设置', '已完结']:
                        continue
                    last_date = novel.get('last_publish_date', '')
                    daily_plan = novel.get('daily_plan', '')
                    plan_status = novel.get('plan_status', True)
                    if last_date and last_date != '从未发布':
                        try:
                            pub_date = datetime.strptime(last_date, '%Y-%m-%d')
                            diff_days = (pub_date - datetime.now()).days
                            interval_status = False
                            if daily_plan and '/' in daily_plan:
                                parts = daily_plan.split('/')
                                if len(parts) >= 3:
                                    interval = int(parts[1]) or 1
                                    remainder = int(parts[2]) or 0
                                    if (datetime.now().toordinal() % interval) == remainder:
                                        interval_status = True
                            if diff_days <= -1 and interval_status:
                                execute_action(title, 'publish')
                                time.sleep(30)
                        except Exception:
                            pass
                append_log("发布次日：自动发布完成")
            threading.Thread(target=_wait_and_publish, daemon=True).start()
            self._send_json({"success": True, "message": "发布次日已启动，将在跨天后自动执行批量发布"})
            return

        if path == '/api/logs/clear':
            with log_lock:
                log_buffer.clear()
            self._send_json({"success": True})
            return

        if path == '/api/chapters':
            title = body.get('title', '')
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            novel_path = info.get('novel_path', '')
            if not novel_path or not Path(novel_path).is_dir():
                self._send_json({"success": False, "message": "小说文件夹不存在"})
                return
            chapter_files = sorted(Path(novel_path).glob("Chapter*.md"),
                                    key=lambda f: int(re.search(r'Chapter_(\d+)', f.name).group(1)))

            def _read_one(idx_path):
                idx, f = idx_path
                try:
                    with open(f, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    first_line = content.split('\n')[0].strip('# ').strip() or f.stem
                    chars = 0
                    text = content[content.find('\n'):].replace('\n', '').replace(' ', '')
                    for ch in text:
                        cp = ord(ch)
                        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF  # CJK
                                or cp < 128 or cp in (0x3001, 0x3002, 0xFF0C, 0xFF0E,
                                0x300A, 0x300B, 0x2018, 0x2019, 0x201C, 0x201D,
                                0xFF08, 0xFF09, 0x3010, 0x3011, 0x3001, 0x3002,
                                0x2026, 0x2014, 0xFF05, 0xFE30, 0xFF0E)):
                            chars += 1
                    return (idx, {"name": f.name, "title": first_line, "words": chars})
                except Exception as e:
                    return (idx, {"name": f.name, "title": f.stem, "words": 0, "error": str(e)})

            indexed = list(enumerate(chapter_files))
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = pool.map(_read_one, indexed)
            chapters = [r[1] for r in sorted(results, key=lambda x: x[0])]
            self._send_json({"success": True, "chapters": chapters, "path": novel_path})
            return

        if path == '/api/open_chapter':
            novel_path = body.get('path', '')
            filename = body.get('name', '')
            chapter_path = Path(novel_path) / filename
            if not chapter_path.exists():
                self._send_json({"success": False, "message": "章节文件不存在"})
                return
            try:
                with open(chapter_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._send_json({"success": True, "content": content, "path": str(chapter_path)})
            except Exception as e:
                self._send_json({"success": False, "message": f"读取失败: {e}"})
            return

        if path == '/api/save_chapter':
            novel_path = body.get('path', '')
            filename = body.get('name', '')
            content = body.get('content', '')
            chapter_path = Path(novel_path) / filename
            if not chapter_path.exists():
                self._send_json({"success": False, "message": "章节文件不存在"})
                return
            try:
                with open(chapter_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self._send_json({"success": True, "message": f"已保存: {filename}"})
            except Exception as e:
                self._send_json({"success": False, "message": f"保存失败: {e}"})
            return

        if path == '/api/parse_chapters':
            content = body.get('content', '')
            if not content:
                self._send_json({"success": False, "message": "内容为空"})
                return
            chapter_pattern = re.compile(
                r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[:：\s]+.*$)',
                re.MULTILINE
            )
            parts = chapter_pattern.split(content)
            if len(parts) <= 1:
                self._send_json({"success": False, "message": "未找到任何章节"})
                return
            chapters = []
            for i in range(1, len(parts), 2):
                title = parts[i].strip()
                c_content = parts[i + 1].strip() if i + 1 < len(parts) else ''
                chars = 0
                text = c_content.replace('\n', '').replace(' ', '')
                for ch in text:
                    cp = ord(ch)
                    if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
                            or cp < 128 or cp in (0x3001, 0x3002, 0xFF0C, 0xFF0E,
                            0x300A, 0x300B, 0x2018, 0x2019, 0x201C, 0x201D,
                            0xFF08, 0xFF09, 0x3010, 0x3011,
                            0x2026, 0x2014, 0xFF05, 0xFE30)):
                        chars += 1
                chapters.append({"title": title, "content": c_content, "words": chars})
            self._send_json({"success": True, "chapters": chapters, "count": len(chapters)})
            return

        if path == '/api/import_chapters':
            title = body.get('title', '')
            import_text = body.get('content', '')
            selected = body.get('selected', None)  # None=导入全部, list of 0-based indices
            if not title or not import_text:
                self._send_json({"success": False, "message": "缺少参数"})
                return
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            novel_path = info.get('novel_path', '')
            if not novel_path or not Path(novel_path).is_dir():
                self._send_json({"success": False, "message": "小说文件夹不存在"})
                return
            chapter_pattern = re.compile(
                r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[:：\s]+.*$)',
                re.MULTILINE
            )
            parts = chapter_pattern.split(import_text)
            if len(parts) <= 1:
                self._send_json({"success": False, "message": "未找到任何章节"})
                return
            all_chapters = []
            for i in range(1, len(parts), 2):
                ttl = parts[i].strip()
                cnt = parts[i + 1].strip() if i + 1 < len(parts) else ''
                all_chapters.append({"title": ttl, "content": cnt})

            if isinstance(selected, list) and len(selected) > 0:
                to_import = [all_chapters[i] for i in selected if 0 <= i < len(all_chapters)]
            else:
                to_import = all_chapters

            # 找到最大章节号
            max_num = 0
            for f in sorted(Path(novel_path).glob("Chapter*.md")):
                m = re.search(r'Chapter_?(\d+)', f.name)
                if m:
                    max_num = max(max_num, int(m.group(1)))

            for i, ch in enumerate(to_import):
                chapter_num = max_num + i + 1
                title_line = ch['title']
                if '：' not in title_line:
                    c_idx = title_line.find('章') + 1
                    if c_idx < len(title_line) and (title_line[c_idx] in (':', ' ')):
                        title_line = title_line[:c_idx] + '：' + title_line[c_idx + 1:]
                title_line = title_line.replace(' ', '')
                filename = f"Chapter_{chapter_num:03d}.md"
                filepath = Path(novel_path) / filename
                with open(filepath, 'w', encoding='utf-8') as fh:
                    fh.write(f"# {title_line}\n\n")
                    fh.write(ch['content'])

            collector.collect_all_info()
            collector.save_to_json()
            self._send_json({"success": True, "message": f"成功导入 {len(to_import)} 个章节"})
            return

        if path == '/api/export_chapters':
            title = body.get('title', '')
            start = body.get('from', 1)
            end = body.get('to', 0)
            if not title:
                self._send_json({"success": False, "message": "缺少参数"})
                return
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            novel_path = info.get('novel_path', '')
            if not novel_path or not Path(novel_path).is_dir():
                self._send_json({"success": False, "message": "小说文件夹不存在"})
                return
            chapter_files = []
            for f in Path(novel_path).glob("Chapter*.md"):
                m = re.search(r'Chapter_?(\d+)', f.name)
                if m:
                    chapter_files.append((int(m.group(1)), f))

            if not chapter_files:
                self._send_json({"success": False, "message": "未找到章节文件"})
                return

            chapter_files.sort(key=lambda x: x[0])
            if end == 0 or end > chapter_files[-1][0]:
                end = chapter_files[-1][0]

            output_parts = []
            count = 0
            for num, fp in chapter_files:
                if start <= num <= end:
                    try:
                        with open(fp, 'r', encoding='utf-8') as fh:
                            c = fh.read()
                        c = c.replace('# ', '').replace('**', '')
                        output_parts.append(c)
                        output_parts.append('\n\n')
                        count += 1
                    except Exception:
                        pass

            self._send_json({
                "success": True,
                "content": ''.join(output_parts),
                "count": count,
                "filename": f"{title}_导出_第{start}-{end}章.txt"
            })
            return

        if path == '/api/read_config':
            title = body.get('title', '')
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            project_path = ROOT_DIR / info.get('project_name', '')
            config_file = project_path / 'config.ini'
            if not config_file.exists():
                self._send_json({"success": False, "message": "config.ini 不存在"})
                return
            cfg = configparser.ConfigParser()
            cfg.read(str(config_file), encoding='utf-8')
            data = {s: dict(cfg.items(s)) for s in cfg.sections()}
            self._send_json({"success": True, "config": data})
            return

        if path == '/api/update_config':
            title = body.get('title', '')
            updates = body.get('updates', {})
            if not title or not updates:
                self._send_json({"success": False, "message": "缺少参数"})
                return
            info = get_novel_info(title)
            if not info:
                self._send_json({"success": False, "message": "找不到项目"})
                return
            project_path = ROOT_DIR / info.get('project_name', '')
            config_file = project_path / 'config.ini'
            if not config_file.exists():
                self._send_json({"success": False, "message": "config.ini 不存在"})
                return
            try:
                cfg = configparser.ConfigParser()
                cfg.read(str(config_file), encoding='utf-8')
                for section, items in updates.items():
                    if section not in cfg:
                        cfg.add_section(section)
                    for key, value in items.items():
                        cfg[section][key] = str(value)
                with open(str(config_file), 'w', encoding='utf-8') as f:
                    cfg.write(f)
                collector.collect_all_info()
                collector.save_to_json()
                self._send_json({"success": True, "message": f"发布计划已更新: {title}"})
            except Exception as e:
                self._send_json({"success": False, "message": f"保存失败: {e}"})
            return

        self._send_json({"error": "Not found"}, 404)


# 莫兰迪色系（与 web 端一致）
MORANDI = {
    'bg':       '#e8e4e1',
    'panel':    '#f5f2ee',
    'panel2':   '#efebe6',
    'border':   '#bcafa5',
    'text':     '#5c534c',
    'text_dim': '#9b8e84',
    'text_hi':  '#3d3630',
    'accent':   '#9b9eb0',
    'accent2':  '#b0a3a0',
    'blue':     '#8a9ba8',
    'green':    '#9aab9a',
    'rose':     '#b89a9a',
    'gold':     '#c4b49a',
    'red':      '#c49a9a',
}


class ManagerGUI:
    """Tkinter 管理界面 - 莫兰迪色系"""

    def __init__(self, root):
        self.root = root
        self.tray_icon = None
        self.root.title("寒山 小说项目管理")
        self.root.geometry("480x360")
        self.root.minsize(360, 260)
        self.root.configure(bg=MORANDI['bg'])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log_shown = 0
        self._setup_style()
        self._setup_ui()
        self._update_loop()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Frame / Labelframe
        style.configure('TLabelframe', background=MORANDI['panel'], bordercolor=MORANDI['border'], borderwidth=1)
        style.configure('TLabelframe.Label', background=MORANDI['panel'], foreground=MORANDI['text_hi'], font=('Microsoft YaHei UI', 9))
        style.configure('TFrame', background=MORANDI['panel'])

        # Label
        style.configure('TLabel', background=MORANDI['panel'], foreground=MORANDI['text'], font=('Microsoft YaHei UI', 9))

        # Button
        style.configure('TButton', background=MORANDI['accent'], foreground='white',
                        borderwidth=0, focusthickness=0, font=('Microsoft YaHei UI', 9), padding=(8, 3))
        style.map('TButton',
                  background=[('active', MORANDI['blue']), ('pressed', MORANDI['text_hi'])],
                  foreground=[('active', 'white')])

        # Entry
        style.configure('TEntry', fieldbackground=MORANDI['panel2'], foreground=MORANDI['text_hi'],
                        bordercolor=MORANDI['border'], borderwidth=1, padding=3)

        # Progressbar
        style.configure('Morandi.Horizontal.TProgressbar',
                        background=MORANDI['accent'], troughcolor=MORANDI['panel2'],
                        bordercolor=MORANDI['border'], borderwidth=0, thickness=10)
        style.map('Morandi.Horizontal.TProgressbar', background=[('active', MORANDI['blue'])])

        # Scrollbar
        style.configure('TScrollbar', background=MORANDI['panel2'], troughcolor=MORANDI['panel'],
                        bordercolor=MORANDI['border'], arrowcolor=MORANDI['text_dim'])

    def _setup_ui(self):
        pad = 6

        # ---- 工作目录 ----
        dir_frame = ttk.LabelFrame(self.root, text="工作目录", padding=5)
        dir_frame.pack(fill=tk.X, padx=pad, pady=(pad, 3))
        self.dir_var = tk.StringVar(value=str(ROOT_DIR))
        ttk.Entry(dir_frame, textvariable=self.dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="浏览", width=5, command=self._browse_dir).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(dir_frame, text="应用", width=5, command=self._apply_dir).pack(side=tk.LEFT, padx=4)

        # ---- 任务进度 ----
        prog_frame = ttk.LabelFrame(self.root, text="任务进度", padding=5)
        prog_frame.pack(fill=tk.X, padx=pad, pady=3)
        self.prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(prog_frame, variable=self.prog_var, maximum=100,
                        style='Morandi.Horizontal.TProgressbar').pack(fill=tk.X)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(prog_frame, textvariable=self.status_var, font=('Microsoft YaHei UI', 8)).pack(anchor=tk.W, pady=(3, 0))

        # ---- 按钮 ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=pad, pady=3)
        ttk.Button(btn_frame, text="刷新数据", command=self._refresh).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="一键发布", command=self._publish_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="批量移动", command=self._migrate).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="打开管理页面", command=self._open_web).pack(side=tk.LEFT, padx=4)

        # ---- 日志 ----
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(3, pad))
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED,
                                font=('Consolas', 8), bg=MORANDI['panel2'], fg=MORANDI['text'],
                                borderwidth=0, highlightthickness=0, padx=4, pady=3)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ---- 按钮回调 ----

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _apply_dir(self):
        new_dir = self.dir_var.get()
        self.status_var.set("正在切换工作目录...")
        threading.Thread(target=self._do_apply_dir, args=(new_dir,), daemon=True).start()

    def _do_apply_dir(self, new_dir):
        ok, msg = update_root_dir(new_dir)
        if ok:
            self.root.after(0, lambda: messagebox.showinfo("成功", f"工作目录已切换:\n{msg}"))
        else:
            self.root.after(0, lambda: messagebox.showerror("错误", msg))

    def _refresh(self):
        self.status_var.set("正在刷新数据...")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        collector.collect_all_info()
        collector.save_to_json()
        append_log("数据已刷新")

    def _publish_all(self):
        threading.Thread(target=lambda: batch_action("publish", "", "", False, False), daemon=True).start()
        append_log("一键发布已启动")

    def _open_web(self):
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    def _update_browser_path(self):
        if not messagebox.askyesno("确认", f"确定将所有项目浏览器路径修改为:\n{DEFAULT_BROWSER_PATH}？"):
            return
        threading.Thread(target=self._do_update_browser_path, daemon=True).start()

    def _do_update_browser_path(self):
        self.status_var.set("正在修改浏览器路径...")
        result = update_all_browser_paths()
        msg = result.get('message', '')
        if result.get('success'):
            self.root.after(0, lambda: messagebox.showinfo("完成", msg))
        else:
            self.root.after(0, lambda: messagebox.showerror("失败", msg))
        self.status_var.set("就绪")

    def _migrate(self):
        """打开批量移植对话框：多选账号 + 目标文件夹"""
        win = tk.Toplevel(self.root)
        win.title("批量移植")
        win.geometry("460x360")
        win.resizable(False, False)
        win.configure(bg=MORANDI['panel'])
        win.transient(self.root)
        win.grab_set()

        # 账号选择（多选）
        acct_frame = ttk.LabelFrame(win, text="作者账号（可多选）", padding=8)
        acct_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))
        user_marks = load_user_marks()
        tags = user_marks.get('account_tags', [])

        # 顶部：全选按钮 + 计数
        top_row = ttk.Frame(acct_frame)
        top_row.pack(fill=tk.X, pady=(0, 4))
        count_var = tk.StringVar(value=f"已选 0 / {len(tags)}")

        listbox = tk.Listbox(acct_frame, selectmode=tk.EXTENDED,
                             bg=MORANDI['panel2'], fg=MORANDI['text'],
                             selectbackground=MORANDI['accent'], selectforeground='white',
                             borderwidth=0, highlightthickness=1,
                             highlightbackground=MORANDI['border'],
                             font=('Microsoft YaHei UI', 9), height=8,
                             exportselection=False)
        for t in tags:
            listbox.insert(tk.END, t)
        listbox.pack(fill=tk.BOTH, expand=True)

        def _update_count():
            count_var.set(f"已选 {len(listbox.curselection())} / {len(tags)}")
        listbox.bind('<<ListboxSelect>>', lambda e: _update_count())

        def _toggle_all():
            if len(listbox.curselection()) == len(tags):
                listbox.selection_clear(0, tk.END)
            else:
                listbox.selection_set(0, tk.END)
            _update_count()

        ttk.Button(top_row, text="全选/全不选", command=_toggle_all).pack(side=tk.LEFT)
        ttk.Label(top_row, textvariable=count_var).pack(side=tk.LEFT, padx=(8, 0))

        # 目标目录
        dir_frame = ttk.LabelFrame(win, text="目标文件夹", padding=8)
        dir_frame.pack(fill=tk.X, padx=10, pady=4)
        target_var = tk.StringVar()
        ttk.Entry(dir_frame, textvariable=target_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _browse():
            d = filedialog.askdirectory(initialdir=str(ROOT_DIR))
            if d:
                target_var.set(d)
        ttk.Button(dir_frame, text="浏览", width=5, command=_browse).pack(side=tk.LEFT, padx=(4, 0))

        # 操作按钮
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=(4, 10))

        def _do_migrate():
            sel = listbox.curselection()
            selected_tags = [tags[i] for i in sel]
            target_dir = target_var.get().strip()
            if not selected_tags:
                messagebox.showwarning("提示", "请至少选择一个作者账号", parent=win)
                return
            if not target_dir:
                messagebox.showwarning("提示", "请选择目标文件夹", parent=win)
                return
            disp = '、'.join(selected_tags) if len(selected_tags) <= 3 else f"{len(selected_tags)} 个账号"
            if not messagebox.askyesno("确认", f"确定将账号「{disp}」的项目移植到\n{target_dir}？", parent=win):
                return
            win.destroy()
            threading.Thread(target=self._do_migrate_run, args=(selected_tags, target_dir), daemon=True).start()

        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="开始移植", command=_do_migrate).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="更新浏览器路径", command=self._update_browser_path).pack(side=tk.LEFT)

    def _do_migrate_run(self, account_tags, target_dir):
        """后台执行移植，完成后弹窗提示"""
        disp = '、'.join(account_tags) if len(account_tags) <= 3 else f"{len(account_tags)} 个账号"
        self.status_var.set(f"正在移植账号「{disp}」的项目...")
        result = migrate_projects(account_tags, target_dir)
        msg = result.get('message', '')
        if result.get('success'):
            self.root.after(0, lambda: messagebox.showinfo("移植完成", msg))
        else:
            self.root.after(0, lambda: messagebox.showerror("移植失败", msg))
        self.status_var.set("就绪")

    # ---- 更新循环 ----

    def _update_loop(self):
        with progress_lock:
            t, c = total_tasks, completed_tasks
        pending = task_queue.qsize()
        if t > 0:
            pct = min(c / t * 100, 100)
            self.prog_var.set(pct)
            self.status_var.set(f"总计 {t} | 已完成 {c} | 队列中 {pending} | 进度 {pct:.0f}%")
        else:
            self.prog_var.set(0)
            self.status_var.set(f"就绪 | 项目总数 {len(collector.all_novel_info)} | 队列中 {pending}")

        with log_lock:
            new_logs = log_buffer[self.log_shown:]
            self.log_shown = len(log_buffer)
        if new_logs:
            self.log_text.configure(state=tk.NORMAL)
            for line in new_logs:
                self.log_text.insert(tk.END, line + '\n')
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(500, self._update_loop)

    # ---- 窗口/退出 ----

    def on_close(self):
        if self.tray_icon:
            self.root.withdraw()
        else:
            self.quit_app()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()


def create_tray_icon(gui):
    """创建系统托盘图标"""
    if not HAS_TRAY:
        return None

    image = None
    if tray_icon_png:
        try:
            img_data = base64.b64decode(tray_icon_png)
            image = PILImage.open(io.BytesIO(img_data))
        except Exception as e:
            logging.error(f"Failed to load tray icon: {e}")
    if image is None:
        image = PILImage.new('RGB', (64, 64), 'red')

    def on_publish(icon, item):
        def _do():
            batch_action("publish", "", "", False, False)
            append_log("托盘一键发布已完成")
        threading.Thread(target=_do, daemon=True).start()
        append_log("托盘一键发布已启动")

    def on_open_web(icon, item):
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    def on_show(icon, item):
        gui.root.after(0, gui.show_window)

    def on_quit(icon, item):
        icon.stop()
        gui.root.after(0, gui.quit_app)

    menu = pystray.Menu(
        pystray.MenuItem("显示主窗口", on_show, default=True),
        pystray.MenuItem("一键发布", on_publish),
        pystray.MenuItem("打开网页", on_open_web),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )
    return pystray.Icon("AutoWriter", image, "寒山小说管理", menu)


def main():
    # 加载保存的工作目录
    config = load_manager_config()
    saved_dir = config.get('root_dir', '')
    if saved_dir and Path(saved_dir).is_dir() and Path(saved_dir) != ROOT_DIR:
        update_root_dir(saved_dir)

    print(f"========================================")
    print(f"  寒山 小说项目管理服务端 v3.0")
    print(f"  工作目录: {ROOT_DIR}")
    print(f"========================================")

    # 初始收集数据
    collector.collect_all_info()
    collector.save_to_json()

    # 启动HTTP服务（后台线程）
    server = HTTPServer(('127.0.0.1', PORT), RequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"服务已启动: http://127.0.0.1:{PORT}")
    append_log(f"服务已启动: http://127.0.0.1:{PORT}")

    # 创建Tkinter GUI
    root = tk.Tk()
    gui = ManagerGUI(root)

    # 创建托盘图标（后台线程）
    tray_icon = create_tray_icon(gui)
    gui.tray_icon = tray_icon
    if tray_icon:
        threading.Thread(target=tray_icon.run, daemon=True).start()

    # 自动打开浏览器
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()

    # Tkinter主循环
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if tray_icon:
            tray_icon.stop()
        server.shutdown()
        print("\n服务已停止")


if __name__ == "__main__":
    main()
