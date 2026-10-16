DECLARATION = """
声明：本工具仅用于学习和研究，不涉及任何商业用途！
如有使用bug反馈或者交流ai写作经验
可联系wx: zwq123_789 或 abrtga
或者加入QQ群: 1073022161
不定时更新，请关注星月写作【强盛集团】，关注 寒山
欢迎注册加入星月写作大家庭
https://xingyuexiezuo.com/?inviter=839096#/login
会在收获墙中发布新的网盘地址和更新说明
"""
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import configparser
import threading

from playwright.sync_api import sync_playwright, Page, BrowserContext
import traceback
import os
import re
import sys
from typing import Tuple, List
import datetime
import json
import argparse
import inspect
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入浏览器检测模块
from browser_detector import BrowserDetector

# 导入重构后的模块
from novel_publisher.chapter_files import (
    create_chapter_files_in_files as _cf_create_in_files,
    create_chapter_files_in_files_custom as _cf_create_custom,
    get_chapter_files_in_range as _cf_get_range,
    get_chapter_details as _cf_get_details,
    count_chinese_characters as _cf_count_chinese,
    check_repeat_content as _cf_check_repeat,
)
from novel_publisher.downloader import NovelDownloader
from novel_publisher.logging_redirect import TextRedirector
from novel_publisher.tray import create_tray_icon as _create_tray_icon, run_tray_in_thread
from novel_publisher.create_book import parse_novel_info as _parse_novel_info
from novel_publisher.create_book import load_outline_from_dir as _load_outline
from novel_publisher.config import PublishConfig
from novel_publisher.browser import open_browser as _open_browser
from novel_publisher.navigation import (
    get_site_url as _get_site_url_impl,
    navigate_to_fanqie_novel_list,
    click_novel_list_fanqie,
    handle_fanqie_floats,
    find_novel_in_fanqie_list,
)
from novel_publisher.platforms import get_platform
from novel_publisher.tasks import execute_task
from novel_publisher.sstory import FanqieSStoryAutoPublisher
from novel_publisher.updater import check_update_async, apply_update

CONFIG_FILE = r'config.ini'
AUTH_FILE = r'auth.json'

VERSION = 'v2.2.9'

class NovelPublisherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"❄【寒山】小说自动发布工具{VERSION}")
        self.geometry("640x900")  
        self.minsize(450, 520)
        # self.maxsize(640, 900)

        self.is_max_width = True  # 标记当前是否为最大宽度
        self.min_width = 450  # 最小宽度
        self.min_height = 520  # 最小高度
        self.max_width = 640  # 最大宽度
        self.max_height = 900  # 最大高度

        self.bind("<Control-l>", self.toggle_window_width)
        self.bind("<Control-d>", self.open_manual_browser)
        self.bind("<Control-s>", self.save_config)
        self.bind("<Control-f>", self.create_book_fast)
        self.bind("<Control-i>", self.import_chapters)
        self.bind("<Control-w>", lambda event: self.execute_scheduled_task('本地定时发布'))
        self.bind("<Control-p>", self.stop_publish)
        self.bind("<Control-k>", self.not_wait)
        self.bind("<Control-n>", self.open_dir)
        self.bind("<Control-m>", self.open_file)
        self.bind("<Control-e>", lambda event: self.execute_scheduled_task('发布进度自检'))
        self.bind("<Control-y>", lambda event: self.execute_scheduled_task('短故事发布'))
        self.bind("<Control-g>", lambda event: self.execute_scheduled_task('全勤检查'))
        
        # Create and configure the main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.config = configparser.ConfigParser()
        self.load_config()
        self.novel_status = self.config.get('Novel', 'novel_status', fallback='未设置')
        self.fast_publish_mode = False
        self.stop_publish_sign = False
        self.wait_event = threading.Event()
        self.scheduled_task = []
        self.tray_icon = None

        # Init More Var
        self.publish_time = datetime.datetime.now()
        self.fast_publish_mode_var = tk.StringVar(value="10*1+10*3+5*7")

        # --- 发布配置 (Settings) ---
        settings_frame = ttk.LabelFrame(main_frame, text="发布配置", padding="10")
        settings_frame.pack(fill=tk.X, pady=5)

        # Configure grid columns
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)

        # Browser Path
        row_idx = 0
        ttk.Label(settings_frame, text="浏览器地址/端口:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.custom_browser_path_var = tk.StringVar(
            value=self.config.get('Settings', 'custom_browser_path', fallback='(必填)允许多个账号使用同一个浏览器'))
        ttk.Entry(settings_frame, textvariable=self.custom_browser_path_var).grid(row=row_idx, column=1, sticky=tk.EW, padx=5, pady=3, columnspan=1)
        
        # Auto Detect Browser Path
        self.auto_detect_btn = ttk.Button(settings_frame, text="自动检测", command=self.auto_detect_browser)
        self.auto_detect_btn.grid(row=row_idx, column=2, sticky=tk.W, padx=5, pady=3)

        # Login Button
        self.login_page = None
        ttk.Button(settings_frame, text="登录(完成)", command=self.run_login_thread).grid(row=row_idx, column=3, sticky=tk.W, padx=5, pady=3)
        ttk.Label(settings_frame, text="浏览器分身:").grid(row=row_idx, column=4, sticky=tk.W, padx=5, pady=3)
        ttk.Button(settings_frame, text="创建分身", command=self.create_shortcut).grid(row=row_idx+1, column=4, sticky=tk.W, padx=5, pady=3)
        ttk.Button(settings_frame, text="打开分身", command=self.open_browser_lnk).grid(row=row_idx+2, column=4, sticky=tk.W, padx=5, pady=3)
        ttk.Button(settings_frame, text="劫持分身", command=self.relative_browser_lnk).grid(row=row_idx+3, column=4, sticky=tk.W, padx=5, pady=3)
        # Publish Plate and Mode
        row_idx += 1
        ttk.Label(settings_frame, text="发布平台:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.publish_plate_var = tk.StringVar(value=self.config.get('Settings', 'publish_plate', fallback='番茄'))
        ttk.Combobox(settings_frame, textvariable=self.publish_plate_var,
            values=['番茄', '起点', '七猫', '飞卢', 'Q阅', '纵横', '微信', '书旗', '晋江', '息壤', '*知乎', '*老福特', ]).grid(
            row=row_idx, column=1, sticky=tk.W, padx=5, pady=3)

        ttk.Label(settings_frame, text="发布模式:").grid(row=row_idx, column=2, sticky=tk.W, padx=5, pady=3)
        self.publish_mode_var = tk.StringVar(value=self.config.get('Settings', 'publish_mode', fallback='立刻发布'))
        ttk.Combobox(settings_frame, textvariable=self.publish_mode_var, values=['立刻发布', '保存为草稿', '定时发布', '修改章节']).grid(
            row=row_idx, column=3, sticky=tk.W, padx=5, pady=3)

        # Publish Time and Fast Publish Mode
        row_idx += 1
        ttk.Label(settings_frame, text="每日定时发布时间:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.publish_time_var = tk.StringVar(value=self.config.get('Settings', 'publish_time', fallback='00:00'))
        # 创建时间选项列表 (HH:MM格式，每15分钟一个选项)
        time_options = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in [0, 15, 30, 45]]
        # 添加一些常用的特定时间点
        common_times = ["06:00", "08:00", "12:00", "18:00", "20:00", "22:00"]
        # 合并并去重时间选项
        time_options = list(dict.fromkeys(common_times + time_options))
        # 按时间顺序排序
        time_options.sort()
        ttk.Spinbox(settings_frame, textvariable=self.publish_time_var, values=time_options, width=15).grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=3)

        ttk.Label(settings_frame, text="间隔发布:").grid(row=row_idx, column=2, sticky=tk.W, padx=5, pady=3)
        self.interval_publish_mode_var = tk.StringVar(value=self.config.get('Settings', 'interval_publish_mode', fallback='1/0'))
        ttk.Combobox(settings_frame, textvariable=self.interval_publish_mode_var,
                     values=["1/0", "3/1", "5/3", "7/2", "2/1"], width=15).grid(row=row_idx, column=3, sticky=tk.W, padx=5, pady=3)

        # Daily Publish Num and Remain
        row_idx += 1
        ttk.Label(settings_frame, text="每日更新章节数:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.daily_publish_num_var = tk.IntVar(value=int(self.config.get('Settings', 'daily_publish_num', fallback='2')))
        ttk.Spinbox(settings_frame, textvariable=self.daily_publish_num_var, width=15, from_=-1, to=100).grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=3)

        # Daily Publish Count
        ttk.Label(settings_frame, text="每日更新字数:").grid(row=row_idx, column=2, sticky=tk.W, padx=5, pady=3)
        self.daily_publish_count_var = tk.IntVar(value=int(self.config.get('Settings', 'daily_publish_count', fallback='4000')))
        ttk.Spinbox(settings_frame, textvariable=self.daily_publish_count_var, width=15, from_=0, to=100000, increment=1000).grid(row=row_idx, column=3, sticky=tk.W, padx=5, pady=3)

        # --- 小说配置 (Novel) ---
        novel_frame = ttk.LabelFrame(main_frame, text="小说配置", padding="10")
        novel_frame.pack(fill=tk.X, pady=5)

        # Configure grid columns
        novel_frame.columnconfigure(1, weight=1)

        # Novel Title
        row_idx = 0
        ttk.Label(novel_frame, text="小说标题:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.novel_title_var = tk.StringVar(value=self.config.get('Novel', 'novel_title', fallback='你的小说名(完整无误的)'))
        ttk.Entry(novel_frame, textvariable=self.novel_title_var).grid(row=row_idx, column=1, sticky=tk.EW, padx=5, pady=3, columnspan=3)
        # Novels Folder
        row_idx += 1
        ttk.Label(novel_frame, text="小说作者:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.novel_writer_var = tk.StringVar(value=self.config.get('Novel', 'novel_writer', fallback='你的笔名(选填)'))
        ttk.Entry(novel_frame, textvariable=self.novel_writer_var).grid(row=row_idx, column=1, sticky=tk.EW, padx=5, pady=3, columnspan=3)
        # Novels Folder
        row_idx += 1
        ttk.Label(novel_frame, text="小说文件夹:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.novels_folder_var = tk.StringVar(value=self.config.get('Novel', 'novels_folder', fallback='小说文件夹(允许相对路径/如果没有则输入路径然后点击导入)'))
        ttk.Entry(novel_frame, textvariable=self.novels_folder_var).grid(row=row_idx, column=1, sticky=tk.EW, padx=5, pady=3, columnspan=3)

        # Chapter Count and Save Button
        row_idx += 1
        ttk.Label(novel_frame, text="章节总数:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.chapter_count_var = tk.StringVar(value="0")
        self.chapter_count_label = ttk.Label(novel_frame, textvariable=self.chapter_count_var)
        self.chapter_count_label.grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=3)

        # Save Config Button
        ttk.Button(novel_frame, text="保存配置", command=self.save_config).grid(row=row_idx, column=3, sticky=tk.E, padx=5, pady=3)

        # --- Action Section ---
        action_frame = ttk.LabelFrame(main_frame, text="操作", padding="10")
        action_frame.pack(fill=tk.X, pady=5)
        
        # Configure grid for action frame
        action_frame.columnconfigure(2, weight=1)  # Empty column for spacing
        action_frame.columnconfigure(5, weight=1)  # Empty column for spacing

        # Last Published Chapter Date
        row_idx = 0
        ttk.Label(action_frame, text="上次更新日期:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.last_published_chapter_date_var = tk.StringVar(
            value=self.config.get('History', 'last_published_chapter_date', fallback=(datetime.datetime.now()-datetime.timedelta(days=1)).strftime('%Y-%m-%d')))
        self.last_published_chapter_date_entry = ttk.Entry(action_frame,
                                                           textvariable=self.last_published_chapter_date_var, width=18)
        self.last_published_chapter_date_entry.grid(row=row_idx, column=1, columnspan=2, padx=5, pady=3)

        # Last Remaining Chapter and Word Count
        ttk.Label(action_frame, text="上次剩余章节:").grid(row=row_idx, column=3, sticky=tk.W, padx=5, pady=3)
        self.daily_publish_num_remain_var = tk.IntVar(value=int(self.config.get('History', 'daily_publish_num_remain', fallback='0')))
        ttk.Spinbox(action_frame, textvariable=self.daily_publish_num_remain_var, width=10, from_=-1, to=100).grid(row=row_idx, column=4, sticky=tk.W, padx=5, pady=3)

        ttk.Label(action_frame, text="上次剩余字数:").grid(row=row_idx+1, column=3, sticky=tk.W, padx=5, pady=3)
        self.daily_publish_count_remain_var = tk.IntVar(value=int(self.config.get('History', 'daily_publish_count_remain', fallback='0')))
        ttk.Spinbox(action_frame, textvariable=self.daily_publish_count_remain_var, width=10, from_=0, to=100000, increment=1000).grid(row=row_idx+1, column=4, sticky=tk.W, padx=5, pady=3)

        # Checkboxes
        row_idx += 1
        self.keep_browser_open_var = tk.BooleanVar()
        ttk.Checkbutton(action_frame, text="后台执行", variable=self.keep_browser_open_var).grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        self.keep_browser_open_var.set(self.config.getboolean('Settings', 'close_browser_open', fallback=False))

        self.neat_index_var = tk.BooleanVar()
        ttk.Checkbutton(action_frame, text="格式索引", variable=self.neat_index_var).grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=3)
        self.neat_index_var.set(self.config.getboolean('Settings', 'neat_index', fallback=True))

        self.danger_pre_check_var = tk.BooleanVar()
        ttk.Checkbutton(action_frame, text="风险预检", variable=self.danger_pre_check_var).grid(row=row_idx, column=2, sticky=tk.W, padx=5, pady=3)
        self.danger_pre_check_var.set(self.config.getboolean('Settings', 'danger_pre_check', fallback=False))

        # Chapter Range
        row_idx += 1
        ttk.Label(action_frame, text="发布章节范围:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=3)
        last_published_chapter = self.config.get('History', 'last_published_chapter', fallback='0')
        daily_publish_num = int(self.daily_publish_num_var.get())
        self.start_chapter_var = tk.IntVar(value=(int(last_published_chapter) + 1))
        self.start_chapter_entry = ttk.Spinbox(action_frame, textvariable=self.start_chapter_var, width=5, from_=1, to=100000, increment=1)
        self.start_chapter_entry.grid(row=row_idx, column=1, padx=1, pady=3)
        ttk.Label(action_frame, text="到").grid(row=row_idx, column=2, padx=3, pady=3)
        self.end_chapter_var = tk.IntVar(value=(int(last_published_chapter) + (daily_publish_num if daily_publish_num != -1 else 1)))
        self.end_chapter_entry = ttk.Spinbox(action_frame, textvariable=self.end_chapter_var, width=5, from_=1, to=100000, increment=1)
        self.end_chapter_entry.grid(row=row_idx, column=3, padx=1, pady=3)

        # Run Button
        self.run_button = ttk.Button(action_frame, text="开始发布", command=self.run_automation_thread)
        self.run_button.grid(row=row_idx, column=4, sticky=tk.W, padx=5, pady=3)

        # Scheduled Release Button
        self.scheduled_button = ttk.Button(action_frame, text="扩展功能", command=self.scheduled_thread)
        self.scheduled_button.grid(row=row_idx, column=5, sticky=tk.E, padx=18, pady=3)

        self.submit_button = ttk.Button(action_frame, text="快速创书", command=self.create_book_fast)
        self.submit_button.grid(row=row_idx-1, column=5, sticky=tk.E, padx=18, pady=3)

        self.fast_once_button = ttk.Button(action_frame, text="最速开书", command=self.show_fast_publish_dialog)
        self.fast_once_button.grid(row=row_idx-2, column=5, sticky=tk.E, padx=18, pady=3)


        # --- Extended functionality ---
        others_frame = ttk.LabelFrame(main_frame, text="其他功能", padding="10")
        others_frame.pack(fill=tk.X, pady=5)

        # Function Buttons
        button_frame = ttk.Frame(others_frame)
        button_frame.pack(fill=tk.X, padx=5)
        
        # Export Button
        ttk.Button(button_frame, text="导出章节", command=self.export_chapters).pack(side=tk.LEFT, padx=5, pady=3)
        # Import Button
        ttk.Button(button_frame, text="导入章节", command=self.import_chapters).pack(side=tk.LEFT, padx=5, pady=3)
        # Manual Browser Button
        ttk.Button(button_frame, text="手动操作", command=self.open_manual_browser).pack(side=tk.LEFT, padx=5, pady=3)
        # Check Duplicate Titles Button
        self.check_title_button = ttk.Button(button_frame, text="检查标题", command=self.start_check_duplicate_titles)
        self.check_title_button.pack(side=tk.LEFT, padx=5, pady=3)
        # Download Book Button
        ttk.Button(button_frame, text="下载小说", command=self.download_book).pack(side=tk.LEFT, padx=5, pady=3)
        # Submit Button
        ttk.Button(button_frame, text="清空草稿", command=self.submit_thread).pack(side=tk.LEFT, padx=5, pady=3)
        # Check Update Button
        ttk.Button(button_frame, text="检查更新", command=lambda: self.check_update(manual=True)).pack(side=tk.LEFT, padx=5, pady=3)

        # --- Log Section ---
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', font=('Arial', 9))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', font=('微软雅黑', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        # 初始化章节计数
        self.update_chapter_count()
        # Redirect stdout to the log widget
        self.redirect_logging()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        if not fast_mode:
            print(DECLARATION)
            # 启动时静默检查更新（不弹窗，仅日志提示）
            self.check_update(manual=False)

    def check_update(self, manual=False):
        """检查 GitHub Release 是否有新版本（后台线程），manual=True 时弹窗提示结果"""
        print('<< 更新 >> 正在检查更新...')
        def _on_result(has_update, remote_tag):
            def _ui():
                if has_update:
                    print(f'<< 更新 >> 发现新版本 {remote_tag}（当前 {VERSION}），可在日志查看详情')
                    if manual or messagebox.askyesno(
                            '发现新版本',
                            f'发现新版本 {remote_tag}（当前 {VERSION}）\n是否立即下载并更新？'):
                        self.apply_update_thread(remote_tag)
                else:
                    print(f'<< 更新 >> 已是最新版本 {VERSION}')
                    if manual:
                        messagebox.showinfo('检查更新', f'当前已是最新版本 {VERSION}')
            self.after(0, _ui)

        def _on_error(err_msg):
            def _ui():
                print(f'<< 更新 >> 检查更新失败: {err_msg}')
                if manual:
                    messagebox.showwarning('检查更新', f'检查更新失败：\n{err_msg}\n\n请检查网络或稍后重试')
            self.after(0, _ui)

        check_update_async(VERSION, self.config, _on_result, _on_error)

    def apply_update_thread(self, remote_tag):
        """后台线程下载并应用更新"""
        print(f'<< 更新 >> 开始下载新版本 {remote_tag} ...')
        def _worker():
            try:
                apply_update(remote_tag, mirrors=None)
            except Exception as e:
                self.after(0, lambda: print(f'<< 更新 >> 更新失败: {e}'))
        threading.Thread(target=_worker, daemon=True).start()

    def on_closing(self):
        self.restore_stdout()
        self.destroy()

    def create_shortcut(self):
        import win32com.client

        def create_lnk(shortcut_path, target_path, arguments=None, icon_path=None):
            shell = win32com.client.Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            
            shortcut.TargetPath = target_path
            if arguments:
                shortcut.Arguments = arguments
            if icon_path:
                shortcut.IconLocation = icon_path
            
            shortcut.Save()

        # Example usage: Create Chrome shortcut with remote debugging
        create_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Shortcuts")
        contrast_file = os.path.join(create_dir, 'contrast.json')
        if os.path.exists(contrast_file):
            with open(contrast_file, 'r') as f:
                contrast_dict = json.load(f)
        else:
            contrast_dict = {}
        
        u_port = contrast_dict.get(self.novel_writer_var.get(), None)
        user_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{u_port}")
        if u_port is None:
            for i in range(1000):
                if not os.path.exists(user_data_dir):
                    os.makedirs(user_data_dir, exist_ok=True)
                    break
                u_port = 42900 + i
                user_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{u_port}")
            contrast_dict[self.novel_writer_var.get()] = u_port
            with open(contrast_file, 'w') as f:
                json.dump(contrast_dict, f, indent=4) 
            os.makedirs(create_dir, exist_ok=True)
            create_lnk(
                os.path.join(create_dir, fr"{self.novel_writer_var.get()}.lnk"),
                self.custom_browser_path_var.get(),
                f"--remote-debugging-port={self.novel_writer_var.get()} --user-data-dir=\"{user_data_dir}\" --new-window {self._get_site_url()}",
                f"{self.custom_browser_path_var.get()},0"
            ) 
        self.custom_browser_path_var.set(str(u_port))
        print(f"已创建快捷方式: {self.novel_writer_var.get()}")
        os.startfile(create_dir)
    
    def open_browser_lnk(self):
        create_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Shortcuts")
        os.startfile(os.path.join(create_dir, fr"{self.novel_writer_var.get()}.lnk"))

    def relative_browser_lnk(self):
        create_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Shortcuts")
        contrast_file = os.path.join(create_dir, 'contrast.json')
        if os.path.exists(contrast_file):
            with open(contrast_file, 'r') as f:
                contrast_dict = json.load(f)
        else:
            messagebox.showerror("错误", "未找到分身配置文件")
            return False
        
        u_port = contrast_dict.get(self.novel_writer_var.get(), None)
        if u_port is None:
            messagebox.showerror("错误", "未找到该账号的分身")
            return False
        self.custom_browser_path_var.set(str(u_port))

    def open_file(self, event=None):
        os.startfile(os.path.join(os.path.abspath(self.novels_folder_var.get()), f'Chapter_{self.start_chapter_var.get():03d}.md'))

    def open_dir(self, event=None):
        os.startfile(os.path.abspath(self.novels_folder_var.get()))

    def process_check(self):
        """发布进度自检"""
        normal_config = self._normal_load_config(True) 
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                navigate_to_fanqie_novel_list(page, site_url)

                def _on_novel_found(item):
                    status_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.property')
                    wordcount_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.detail-wordcount.font-4 > span')
                    msg_element = item.query_selector(
                        'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    while not msg_element:
                        page.wait_for_timeout(1000)
                        msg_element = item.query_selector(
                            'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    self.recommend_status(wordcount_element.inner_text(), status_element.inner_text(), msg_element.inner_text())

                if not find_novel_in_fanqie_list(page, novel_title, on_found=_on_novel_found):
                    return
                if self.novel_status == "已完结":
                    print(f"小说 '{novel_title}' 已完结，无需更新。")
                else:
                    row = page.get_by_text(novel_title).locator("..").locator("..")
                    row.hover()
                    row.get_by_role("button", name="章节管理").click(timeout=3000, force=True)
                    page.wait_for_load_state('networkidle')
                    latest_publish_time = datetime.datetime.now()
                    try:
                        page.get_by_role("button", name="我知道了").click(timeout=3000, force=True)
                    except:
                        pass
                    latest_chapter_row = page.locator('div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child(1)')
                    latest_chapter_title = latest_chapter_row.locator('td:nth-child(1) > div').inner_text()
                    latest_chapter_count = latest_chapter_row.locator('td:nth-child(2) > div').inner_text()
                    if not latest_chapter_count.isdigit():
                        print(f"错误：最新章节字数 '{latest_chapter_count}' 不是数字，可能是正在审核中，请稍后进行同步")
                        raise ValueError(f"最新章节字数 '{latest_chapter_count}' 不是数字，可能是正在审核中，请稍后进行同步")
                    latest_chapter_publish_time = latest_chapter_row.locator('td:nth-child(5) > div').inner_text()

                    latest_publish_time = datetime.datetime.strptime(latest_chapter_publish_time, '%Y-%m-%d %H:%M')
                    latest_chapter_index = int(latest_chapter_title.split("第")[1].split("章")[0])
                    latest_publish_count = int(latest_chapter_count) if latest_chapter_count.isdigit() else 2000
                    latest_publish_num = 1

                    while True:
                        next_chapter_row = page.locator(f'div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child({latest_publish_num+1})')
                        if latest_publish_time.date()==datetime.datetime.strptime(next_chapter_row.locator('td:nth-child(5) > div').inner_text(), '%Y-%m-%d %H:%M').date():       
                            latest_publish_num += 1
                            latest_publish_count += int(next_chapter_row.locator('td:nth-child(2) > div').inner_text())
                        else:
                            break
                    
                    msg_str = f"小说名：{novel_title}\n"
                    msg_str += f"最新发布章节：{latest_chapter_index}\n"
                    msg_str += f"最新发布时间：{latest_publish_time.strftime('%Y-%m-%d %H:%M')}\n"
                    msg_str += f"当日已发布：{latest_publish_num}章，{latest_publish_count}字\n"
                    is_update = False
                    if not fast_mode:
                        if messagebox.askyesno("再次确认", msg_str+"\n是否更新本地记录？"):
                            is_update = True
                    else:
                        print(msg_str)
                        is_update = True

                    if is_update:
                        self.last_published_chapter_date_var.set(latest_publish_time.strftime('%Y-%m-%d'))
                        # self.publish_time_var.set(latest_publish_time.strftime('%H:%M'))
                        self.start_chapter_var.set(latest_chapter_index+1)
                        if init_daily_publish_num != -1:
                            daily_publish_num = daily_publish_num if daily_publish_num !=0 else init_daily_publish_num
                            if daily_publish_num > latest_publish_num:
                                self.end_chapter_var.set(latest_chapter_index+daily_publish_num-latest_publish_num)
                                self.daily_publish_num_remain_var.set(daily_publish_num-latest_publish_num)
                            else:
                                self.end_chapter_var.set(latest_chapter_index+daily_publish_num)
                                self.daily_publish_num_remain_var.set(0)
                        else:
                            self.end_chapter_var.set(latest_chapter_index+1)
                            daily_publish_count = daily_publish_count if daily_publish_count !=0 else init_daily_publish_count
                            print(f"最新发布字数：{latest_publish_count}, 每日发布字数：{daily_publish_count}")
                            if daily_publish_count > latest_publish_count:             
                                self.daily_publish_count_remain_var.set(daily_publish_count-latest_publish_count)
                            else:
                                self.daily_publish_count_remain_var.set(0)
                    self.save_config(False)
            except Exception as e:
                traceback.print_exc()
                print(f"点击章节管理按钮时发生错误: {e}")
            finally:
                page.close()
                browser.close()
        self.scheduled_task.remove('发布进度自检')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def not_wait(self, event=None):
        """不等待风险预检"""
        if not self.wait_event.is_set():
            self.wait_event.set()
        self.wait_event.clear()
        print("继续发布后续")

    def stop_publish(self, event=None):
        """终止发布"""
        self.stop_publish_sign = True
        print("===========手动终止发布===========")
        # self.run_button.config(text="开始发布")
        # self.scheduled_button.config(text="定时任务")
    
    def scheduled_thread(self, event=None):
        """定时发布线程"""
        scheduled_dialog = tk.Toplevel(self)
        scheduled_dialog.title("扩展功能")
        scheduled_dialog.geometry("500x50")
        scheduled_dialog.transient(self)
        # scheduled_dialog.grab_set()
        # scheduled_dialog
        
        tk.Label(scheduled_dialog, text="任务名称:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.task_name_var = tk.StringVar(value="本地定时发布")
        ttk.Combobox(scheduled_dialog, textvariable=self.task_name_var, values=["本地定时发布", "自动签约", "自动验证", "短故事发布", "短故事批量发布", "书测", "封测", "全勤检查", "发布进度自检", "取消定时"], width=50).grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        def _execute_scheduled_task():
            nonlocal scheduled_dialog
            self.execute_scheduled_task(self.task_name_var.get())
            scheduled_dialog.destroy()
        tk.Button(scheduled_dialog, text="确定", command=_execute_scheduled_task).grid(row=0, column=2, sticky=tk.E, padx=5, pady=5)
    
    def execute_scheduled_task(self, task_name="本地定时发布"):
        """执行定时任务"""
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        if self.tray_icon is None:
            self.create_tray_icon()
            # 启动托盘图标线程
            threading.Thread(target=self.run_tray, daemon=True).start()
        self.scheduled_task.append(task_name)
        print(f"已添加任务: {self.scheduled_task}")
        self.title(f"定时任务执行中...{self.scheduled_task}")
        if not execute_task(task_name, self):
            self.scheduled_task.remove(task_name)
            print("未知任务类型")
            messagebox.showerror("错误", "未知任务类型")
            return

    def cancel_scheduled_task(self):
        """取消定时任务"""
        normal_config = self._normal_load_config(True) 
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                navigate_to_fanqie_novel_list(page, site_url)

                def _on_novel_found(item):
                    status_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.property')
                    wordcount_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.detail-wordcount.font-4 > span')
                    msg_element = item.query_selector(
                        'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    while not msg_element:
                        page.wait_for_timeout(1000)
                        msg_element = item.query_selector(
                            'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    self.recommend_status(wordcount_element.inner_text(), status_element.inner_text(), msg_element.inner_text())

                if not find_novel_in_fanqie_list(page, novel_title, on_found=_on_novel_found):
                    return
                if self.novel_status == "已完结":
                    print(f"小说 '{novel_title}' 已完结，无需更新。")
                else:
                    row = page.get_by_text(novel_title).locator("..").locator("..")
                    row.hover()
                    row.get_by_role("button", name="章节管理").click(timeout=3000, force=True)
                    page.wait_for_load_state('networkidle')
                    latest_publish_time = datetime.datetime.now()
                    try:
                        page.get_by_role("button", name="我知道了").click(timeout=3000, force=True)
                    except:
                        pass
                    # self.debug()
                    row_index = 0
                    latest_chapter_index = 0
                    while True:
                        latest_chapter_row = page.locator(f'div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child({row_index+1})')
                        latest_chapter_title = latest_chapter_row.locator('td:nth-child(1) > div').inner_text(timeout=3000)
                        # print(latest_chapter_title)
                        latest_chapter_publish_time = latest_chapter_row.locator('td:nth-child(5) > div').inner_text(timeout=3000)
                        latest_publish_time = datetime.datetime.strptime(latest_chapter_publish_time, '%Y-%m-%d %H:%M')
                        if latest_chapter_index == int(latest_chapter_title.split("第")[1].split("章")[0]):
                            #print(latest_chapter_index, int(latest_chapter_title.split("第")[1].split("章")[0]))
                            page.wait_for_timeout(1500)
                            continue
                        else:
                            latest_chapter_index = int(latest_chapter_title.split("第")[1].split("章")[0])
                        
                        if latest_publish_time.date() >= datetime.datetime.now().date():
                            modify_num = row_index
                            c_publish_date = datetime.datetime.now().date()
                            while True:
                                try:
                                    if modify_num == 15:
                                        break
                                    next_chapter_row = page.locator(f'div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child({modify_num+1})')
                                    if c_publish_date < datetime.datetime.strptime(next_chapter_row.locator('td:nth-child(5) > div').inner_text(), '%Y-%m-%d %H:%M').date():       
                                        next_chapter_row.locator('td:nth-child(5) > div > span > div > i').click(timeout=3000, force=True)
                                        page.wait_for_timeout(1000)
                                        page.click('div.card-content-line > div.card-content-line-control > div > button > div', timeout=3000, force=True) 
                                        page.get_by_text("确认修改").click(timeout=3000, force=True)
                                        page.wait_for_timeout(1000)
                                        modify_num += 1
                                    else:
                                        modify_num += 1
                                        continue
                                except:
                                    pass
                            if modify_num == 15:
                                current_page = page.locator('ul > li.arco-pagination-item.arco-pagination-item-active').inner_text(timeout=3000)
                                page.click('div.arco-table-pagination.arco-table-pagination-center > div > ul > li.arco-pagination-item.arco-pagination-item-next', timeout=3000, force=True)
                                page.wait_for_load_state('networkidle')
                                next_page = page.locator('ul > li.arco-pagination-item.arco-pagination-item-active').inner_text(timeout=3000)
                                while current_page == next_page:
                                    page.click('div.arco-table-pagination.arco-table-pagination-center > div > ul > li.arco-pagination-item.arco-pagination-item-next', timeout=3000, force=True)
                                    page.wait_for_load_state('networkidle')
                                    next_page = page.locator('ul > li.arco-pagination-item.arco-pagination-item-active').inner_text(timeout=3000)
                                continue
                            else:
                                print("所有章节修改完毕")
                                break
                        else:
                            row_index += 1
                            if row_index == 15:
                                print("没有可更新章节")
                                break
                            else:
                                continue
            except Exception as e:
                traceback.print_exc()
                print(f"点击章节管理按钮时发生错误: {e}")
            finally:
                page.close()
                browser.close()
        self.scheduled_task.remove('取消定时')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def scheduled_publish_story_batch(self):
        """短故事批量发布"""
        if self.publish_plate_var.get() != "番茄":
            print("短故事批量发布仅支持番茄平台")
            return
        # 读取工作目录下的短篇直出文件夹
        story_folder = os.path.join(os.getcwd(), "短篇直出")
        if not os.path.exists(story_folder):
            print(f"{story_folder}文件夹不存在")
            print(f"请将统一格式的短故事txt文档放置到{story_folder}文件夹中")
            print("由于番茄发布限制，数量建议不多于10篇，否则只会发布前10篇")
        else: 
            story_files = os.listdir(story_folder)
            print(f"发现{len(story_files)}篇短故事")
            if len(story_files) > 10:
                print("由于番茄发布限制，数量建议不多于10篇，否则只会发布前10篇")
            browser_path = self.custom_browser_path_var.get()
            site_url = self._get_site_url()
            writer = self.novel_writer_var.get()
            fssp = FanqieSStoryAutoPublisher(browser_path, site_url, writer, AUTH_FILE)
            release_folder = os.path.join(os.getcwd(), f"已发布{datetime.datetime.now().strftime('%m-%d')}")
            os.makedirs(release_folder, exist_ok=True)
            for file in story_files[:10]:
                if file.endswith(".txt"):
                    with open(os.path.join(story_folder, file), 'r', encoding='utf-8') as f:
                        input_text = f.read()
                    parsed_info = fssp.parse_story_info(input_text)
                    if fssp.publish(parsed_info):
                        if parsed_info['短故事名称'] == '未知':
                            print(f'未解析到短故事名称，使用文件名作为名称')
                            parsed_info['短故事名称'] = os.path.splitext(file)[0]
                        print(f"短故事名称 {parsed_info['短故事名称']} 发布成功")
                        os.rename(os.path.join(story_folder, file), os.path.join(release_folder, file))
                    else:
                        print(f"短故事名称 {parsed_info['短故事名称']} 发布失败")

        self.scheduled_task.remove('短故事批量发布')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def scheduled_sign(self):
        """自动签约"""
        if self.publish_plate_var.get() != "番茄":
            print("自动签约仅支持番茄平台")
            return
        print("=====================================")
        print("自动签约线程已启动")
        print("注意，仅等待评估完成后，自动填写内容，电子签还是需要手动操作接收验证码")
        try:
            if os.path.exists('签约信息.txt'):
                with open('签约信息.txt', 'r', encoding='utf-8') as f:
                    auth_data = f.readlines()
                print(f"签约信息加载成功!")
                # 提取签约信息
                i=0
                for _ in range(len(auth_data)//8):
                    author_name = auth_data[i].strip().split("：")[1]
                    if author_name != self.novel_writer_var.get():
                        # print(f"签约信息中作者姓名为{author_name}，与配置文件中作者姓名{self.novel_writer_var.get()}不匹配")
                        i += 8
                        continue
                    else: 
                        phone = auth_data[i+1].strip().split("：")[1]
                        email = auth_data[i+2].strip().split("：")[1]
                        qq = auth_data[i+3].strip().split("：")[1]
                        location = auth_data[i+4].strip().split("：")[1]
                        address = auth_data[i+5].strip().split("：")[1]
                        bank_account = auth_data[i+6].strip().split("：")[1]
                        bank_branch = auth_data[i+7].strip().split("：")[1]
                        print(f"{author_name}的签约信息提取成功!")
                        print("===============================")
                        print(f"电话：{phone}")
                        print(f"邮箱：{email}")
                        print(f"QQ账号：{qq}")
                        print(f"联系地址：{location}")
                        print(f"详细地址：{address}")
                        print(f"银行卡号：{bank_account}")
                        print(f"所属支行：{bank_branch}")
                        custom_browser_path = self.custom_browser_path_var.get()
                        site_url = self._get_site_url()
                        try:
                            with sync_playwright() as p:
                                browser = p.chromium.launch(
                                    headless=self.keep_browser_open_var.get(), 
                                    executable_path=custom_browser_path if custom_browser_path else None,
                                    args=[
                                        "--disable-popup-blocking",  # 禁用弹窗拦截
                                        "--disable-web-security",  # 禁用网页安全策略
                                        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                                        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                                    ],
                                    ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                                )
                                if not os.path.exists(AUTH_FILE):
                                    raise FileNotFoundError(f"未找到认证文件 {AUTH_FILE}")
                                context = browser.new_context(
                                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                    storage_state=AUTH_FILE)
                                page = context.new_page()
                                novel_title = self.novel_title_var.get()
                        
                                # 刷新网页
                                while True:
                                    page.goto(site_url, timeout=60000, wait_until='domcontentloaded')

                                    print("点击进入小说列表页面...")
                                    novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                                    try:
                                        page.wait_for_selector(novel_list_selector, timeout=3000)  # 等待元素出现
                                        page.click(novel_list_selector, timeout=1500)  # 延长点击超时
                                        page.wait_for_load_state('domcontentloaded')
                                    except Exception as e:
                                        print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
                                        try:
                                            page.click('div.user-guide-btn > button', timeout=1000)
                                            print("已关闭初始引导浮窗。")
                                        except Exception:
                                            print("未找到初始引导浮窗，继续执行...")
                                        try:
                                            page.get_by_text("立即收下").click(timeout=1000)
                                            print("收下补签卡")
                                        except Exception:
                                            pass
                                        try:
                                            print("重新点击进入小说列表页面...")
                                            page.wait_for_selector(novel_list_selector, timeout=3000)  # 等待元素出现
                                            page.click(novel_list_selector, timeout=1500)  # 延长点击超时
                                            page.wait_for_load_state('domcontentloaded')
                                        except Exception as e:
                                            print(f"点击小说列表导航元素时发生错误: {e}")
                                            raise  # 重新抛出异常以便上层捕获
                                    novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                                    try:
                                        page.wait_for_selector(novel_list_selector, timeout=60000)  # 等待元素出现
                                        page.click(novel_list_selector, timeout=60000)  # 延长点击超时
                                        page.wait_for_load_state('domcontentloaded')
                                    except Exception as e:
                                        print(f"点击小说列表导航元素时发生错误: {e}")
                                        raise ValueError(f"点击小说列表导航元素时发生错误: {e}")  # 重新抛出异常以便上层捕获

                                    print(f"正在查找小说: '{novel_title}'")

                                    page.wait_for_selector('[id^="long-article-table-item-"]')
                                    page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                                    novel_items = page.query_selector_all('[id^="long-article-table-item-"]')
            
                                    for item in novel_items:
                                        title_element = item.query_selector(
                                            'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div')
                                        # print(title_element.inner_text())
                                        if title_element and title_element.inner_text() == novel_title:
                                            print(f"找到小说 '{novel_title}'。")
                                            item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见 
                                            break 
                                    row = page.get_by_text(novel_title).locator("..").locator("..").locator("..").locator("..")
                                    row.hover()
                                    page.wait_for_timeout(1500)
                                    if row.get_by_text("【申请签约】").count() == 0:
                                        if row.get_by_text("就可申请签约，请努力码字").count() != 0:
                                            print("未达到签约字数")
                                            self.novel_status = '未申请签约'
                                            self.save_config(True)
                                            page.wait_for_timeout(60000*5)
                                            continue
                                        if row.get_by_text("查看电子版合同并完成签约").count() != 0:
                                            print("已完成签约合同，请手动完成确认")
                                            break
                                        print("已申请签约")
                                        if row.get_by_text("签约审核已通过，请尽快完成合同签约").count() != 0:
                                            print("评估通过")
                                            row.get_by_text("签约管理").click(timeout=1500)
                                            page.wait_for_timeout(1500) 
                                            page.get_by_role("button", name="填写合同").click(timeout=1500)
                                            page.get_by_placeholder("请输入可联系的手机号，该手机号将用于获取签约验证码").fill(phone, timeout=1500)
                                            page.get_by_placeholder("请输入邮箱地址以接收电子合同").fill(email, timeout=1500)
                                            page.get_by_placeholder("请输入QQ号").fill(qq, timeout=1500)
                                            location_input = page.get_by_placeholder("请选择省市区")
                                            location_input.fill(location.split("-")[0], timeout=1500)
                                            page.wait_for_timeout(1500) 
                                            try:
                                                if location.split("-")[1] == location.split("-")[0]:
                                                    location_input.press("Enter", delay=1000)
                                                else:
                                                    page.get_by_text(location.split("-")[1]).click(timeout=1500)
                                            except:
                                                pass
                                            page.wait_for_timeout(1500) 
                                            page.get_by_placeholder("请输入详细地址").fill(address, timeout=1500)
                                            page.get_by_placeholder("请填写稿费收款银行卡号").fill(bank_account, timeout=1500)
                                            bank_branch_input = page.get_by_placeholder("请输入关键字搜索支行名称，例如：工行-北京-中关村")
                                            bank_branch_input.fill(bank_branch, timeout=1500)
                                            page.wait_for_timeout(1500) 
                                            bank_branch_input.press("Enter", delay=1000)
                                            page.wait_for_timeout(1500)
                                            page.get_by_role("button", name="确认无误，提交").click(timeout=1500)
                                            page.wait_for_timeout(1500)
                                            page.get_by_role("button", name="生成合同").click(timeout=1500)
                                            page.get_by_role("button", name="立即签约").click(timeout=120000)

                                            print("自动签约完成！")
                                            page.wait_for_timeout(timeout=10000)
                                            browser.close()
                                            break
                                        else:
                                            print("正在评估中...")
                                            page.wait_for_timeout(timeout=1000*60*60)
                                            # 等待评估完成 一小时一巡查
                                    else:
                                        print("未申请签约")
                                        row.get_by_role("button", name="签约管理").click(timeout=1500)
                                        row.get_by_role("button", name="申请签约").click(timeout=1500)
                                        page.wait_for_timeout(timeout=5000)
                                        row.get_by_text("申请签约").last.click(timeout=1500)
                                        self.novel_status = '签约审核中'
                                        self.save_config(True)
                            self.novel_status = '待签约'
                            self.save_config(True)
                            break
                        except Exception as e:
                            print(f"自动签约过程中出现错误: {e}")
                            traceback.print_exc()
                    if self.novel_status != '待签约':
                        print(f"未找到笔名{self.novel_writer_var.get()}的签约信息！")
            else:
                print("缺少签约信息文件")
                print("请在项目根目录下创建’签约信息.txt‘文件")
                print("格式为——\n笔名：XXXX\n- 电话：13800000000\n- 邮箱：123@xx.com\n- QQ账号：123456789\n- 联系地址：辽宁-沈阳 or 上海-上海 \n- 详细地址：XXXXXX\n- 银行卡号：XXXXXXXXXXXXXXXX\n- 所属支行：XXXX")
                print("笔名作为二次验证，需要和界面填写一致")
        except Exception as e:
            print(f"自动签约过程中出现错误: {e}")
            traceback.print_exc()
        self.scheduled_task.remove('自动签约')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def scheduled_publish(self):
        """定时发布逻辑"""
        print("=====================================")
        print("定时发布线程已启动")
        print("定时发布任务执行中...")
        try:
            self.fast_publish_mode = True
            last_publish_mode_var = self.publish_mode_var.get()
            self.publish_mode_var.set('立刻发布')
            self.save_config()
            # self.scheduled_config = copy.deepcopy(self.config)
            if self.daily_publish_num_var.get() == -1:
                print("日更字数数：{}".format(self.daily_publish_count_var.get()))
            else:
                print("日更章节数：{}".format(self.daily_publish_num_var.get()))
            # scheduled_start_chapter = self.start_chapter_var.get()
            scheduled_end_chapter = self.end_chapter_var.get()

            while scheduled_end_chapter >= self.end_chapter_var.get():
                if self.stop_publish_sign:
                    self.stop_publish_sign = False
                    break
                current_time = datetime.datetime.now()
                last_publish_time = datetime.datetime.strptime(self.config['History']['last_published_chapter_date'], "%Y-%m-%d")
                # if self.daily_publish_num_var.get() == -1 and self.daily_publish_count_remain_var.get() == 0:
                #     last_publish_time += datetime.timedelta(days=1)
                # if self.daily_publish_num_var.get() != -1 and self.daily_publish_num_remain_var.get() == 0:
                #     last_publish_time += datetime.timedelta(days=1)
                publish_time = datetime.datetime.strptime(self.publish_time_var.get(), "%H:%M")
                publish_time = publish_time.replace(
                    year=last_publish_time.year, 
                    month=last_publish_time.month, 
                    day=last_publish_time.day
                    )
                print(publish_time.strftime("%Y-%m-%d %H:%M"))
                print(current_time.strftime("%Y-%m-%d %H:%M"))
                if publish_time.date() <= current_time.date():
                    # publish_time = publish_time.replace(hour=current_time.hour, minute=current_time.minute)
                    if publish_time <= current_time:
                        current_start_chapter = self.start_chapter_var.get()
                        print("执行发布...")
                        if self.daily_publish_num_var.get() == -1:
                            print("启动字数计算模式")
                            if self.daily_publish_count_remain_var.get() == 0:
                                if publish_time.date() == current_time.date():
                                    print("当日计划已完成")
                                    break
                                daily_publish_count = self.daily_publish_count_var.get()
                            else:
                                print(f"检测到当日计划未完成，剩余发布字数为{self.daily_publish_count_remain_var.get()}")
                                daily_publish_count = self.daily_publish_count_remain_var.get()
                            print(f"本次需要发布字数为{daily_publish_count}")
                            init_daily_publish_count = daily_publish_count
                            novel_files = self.get_chapter_files_in_range(self.novels_folder_var.get(), current_start_chapter, current_start_chapter+daily_publish_count//1000)
                            for _, novel_file in novel_files:
                                chapter_details = self.get_chapter_details(novel_file)
                                daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                                if daily_publish_count < 0:
                                    print(f"发布字数为{init_daily_publish_count-daily_publish_count}")
                                    daily_publish_count = 0
                                    # self.daily_publish_count_remain_var.set(0)
                                    break
                                current_start_chapter += 1
                            self.end_chapter_var.set(current_start_chapter)
                        else:
                            if self.daily_publish_num_remain_var.get() == 0:
                                if publish_time.date() == current_time.date():
                                    print("当日计划已完成")
                                    break
                                daily_publish_num = self.daily_publish_num_var.get()
                            else:
                                print(f"检测到当日计划未完成，剩余发布章节数为{self.daily_publish_num_remain_var.get()}")
                                daily_publish_num = self.daily_publish_num_remain_var.get()
                            self.end_chapter_var.set(current_start_chapter + (daily_publish_num - 1))
                        is_out_of_range = self.end_chapter_var.get() > scheduled_end_chapter
                        print("发布章节范围:{} 到 {}".format(self.start_chapter_var.get(), self.end_chapter_var.get()))
                        
                        if not self.automation_flow():
                            print("发布失败")
                            break
                        if is_out_of_range:
                            # print("章节数超出计划范围")
                            self.publish_time = current_time
                            self.last_published_chapter_date_var.set(self.publish_time.strftime("%Y-%m-%d"))
                            if self.daily_publish_num_var.get() == -1:
                                if daily_publish_count != 0:
                                    self.daily_publish_count_remain_var.set(daily_publish_count)
                                else:
                                    self.last_published_chapter_date_var.set(current_time.strftime("%Y-%m-%d"))
                                    publish_time += datetime.timedelta(days=1)
                            else:
                                self.daily_publish_num_remain_var.set(self.end_chapter_var.get() - scheduled_end_chapter + 1)
                            self.save_config()
                            break
                        else:
                            self.last_published_chapter_date_var.set(current_time.strftime("%Y-%m-%d"))
                            publish_time += datetime.timedelta(days=1)
                            self.save_config()
                    else:
                        print("当前时间:{}".format(current_time.strftime("%H:%M")), "计划发布时间:{}".format(publish_time.strftime("%H:%M")))
                        time.sleep(60)
                else:
                    print("当前日期:{}".format(current_time.strftime("%Y-%m-%d")), "计划发布时间:{}".format(publish_time.strftime("%Y-%m-%d %H:%M")))
                    time.sleep(300)
            print("定时发布完成！")
            self.title("定时发布完成！")
            self.publish_mode_var.set(last_publish_mode_var)
            self.save_config()
        except Exception as e:
            print(f"定时发布过程中出现错误: {e}")
            traceback.print_exc()
        
        self.scheduled_task.remove('本地定时发布')
        self.fast_publish_mode = False
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def scheduled_verify(self):
        """自动验证"""
        if self.publish_plate_var.get() != "番茄":
            print("自动验证仅支持番茄平台")
            return
        print("=====================================")
        print("自动验证线程已启动")
        print("注意，需要预先上传非模版封面并在作品推荐中进行确认")
        custom_browser_path = self.custom_browser_path_var.get()
        site_url = self._get_site_url()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.keep_browser_open_var.get(), 
                    executable_path=custom_browser_path if custom_browser_path else None,
                    args=[
                        "--disable-popup-blocking",  # 禁用弹窗拦截
                        "--disable-web-security",  # 禁用网页安全策略
                        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                    ],
                    ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                )
                if not os.path.exists(AUTH_FILE):
                    messagebox.showerror("错误", f"未找到认证文件 {AUTH_FILE} 请先执行登录操作")
                    raise RuntimeError(f"未找到认证文件 {AUTH_FILE} 请先执行登录操作")
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=AUTH_FILE)
                page = context.new_page()
                novel_title = self.novel_title_var.get()
            
                # 刷新网页
                while True:
                    if site_url:
                        page.goto(site_url, timeout=60000)
                        print(f"已导航到: {site_url}")
                        page.wait_for_load_state("networkidle")
                    # 尝试关闭初始引导浮窗
                    try:
                        page.click('div.user-guide-btn > button', timeout=1000)
                        print("已关闭初始引导浮窗。")
                    except Exception:
                        print("未找到初始引导浮窗，继续执行...")

                    print("点击进入小说列表页面...")
                    novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                    try:
                        page.wait_for_selector(novel_list_selector, timeout=60000)  # 等待元素出现
                        page.click(novel_list_selector, timeout=60000)  # 延长点击超时
                        page.wait_for_load_state('domcontentloaded')
                    except Exception as e:
                        raise RuntimeError(f"点击小说列表导航元素时发生错误: {e}")
                        
                    print(f"正在查找小说: '{novel_title}'")

                    page.wait_for_selector('[id^="long-article-table-item-"]')
                    page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                    novel_items = page.query_selector_all('[id^="long-article-table-item-"]')

                    for item in novel_items:
                        title_element = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div')
                        # print(title_element.inner_text())
                        if title_element and title_element.inner_text() == novel_title:
                            print(f"找到小说 '{novel_title}'。")
                            # 定位到“更新章节”按钮
                            item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见 
                            break 
    
                    if page.get_by_role("button", name="作品推荐").count() == 0:
                        if page.get_by_role("button", name="申请签约").count() != 0:
                            print("未申请签约")
                            page.wait_for_timeout(timeout=60*60*1000*12)
                            continue
                        else:
                            if page.get_by_text("签约审核已通过，请尽快完成合同签约").count() != 0:
                                page.wait_for_timeout(timeout=60*60*1000)
                                continue
                        self.title("自动验证完毕！")
                        break
                    else:
                        print("未开始推荐")
                        page.get_by_role("button", name="作品推荐").click(timeout=1500)
                        page.wait_for_load_state('load')
                        try:
                            page.locator("div.recommend-area.prepare-recommend > div.recommend-action > button").click(timeout=1500)
                            page.wait_for_timeout(1000*61*60)
                            self.novel_status = '推荐评估中'
                            self.save_config(True)
                        except:
                            traceback.print_exc()
                            print("自动验证失败！")
                            self.title("自动验证失败！")
                            break
        except Exception as e:
            print(f"自动签约过程中出现错误: {e}")
            traceback.print_exc()
        
        self.scheduled_task.remove('自动验证')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")
        
    def schedule_command_by_name(self):
        if self.publish_plate_var.get() != "番茄":
            print("书测仅支持番茄平台")
            return
        print("=====================================")
        custom_browser_path = self.custom_browser_path_var.get()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.keep_browser_open_var.get(), 
                    executable_path=custom_browser_path if custom_browser_path else None,
                    args=[
                        "--disable-popup-blocking",  # 禁用弹窗拦截
                        "--disable-web-security",  # 禁用网页安全策略
                        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                    ],
                    ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                )
                if not os.path.exists(AUTH_FILE):
                    raise FileNotFoundError(f"未找到认证文件 {AUTH_FILE}")
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=AUTH_FILE)
                page = context.new_page()
                novel_title = self.novel_title_var.get()
                site_url = self._get_site_url()

                page.goto(site_url, timeout=60000, wait_until='domcontentloaded')

                print("点击进入小说推荐页面...")
                novel_command_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(7) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                try:
                    page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
                    try:
                        page.click('div.user-guide-btn > button', timeout=1000)
                        print("已关闭初始引导浮窗。")
                    except Exception:
                        print("未找到初始引导浮窗，继续执行...")
                    try:
                        page.get_by_text("立即收下").click(timeout=1000)
                        print("收下补签卡")
                    except Exception:
                        pass
                    try:
                        print("重新点击进入小说列表页面...")
                        page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                        page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                        page.wait_for_load_state('domcontentloaded')
                    except Exception as e:
                        raise RuntimeError(f"点击小说列表导航元素时发生错误: {e}")
                print(f"正在查找小说: '{novel_title}'")
                page.get_by_text('切换作品').last.click(timeout=3000)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
                try:
                    page.get_by_text(novel_title).last.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                    page.get_by_text('确定').last.click(timeout=3000)
                    page.get_by_text('配置实验').last.click(timeout=3000)
                except Exception:
                    raise RuntimeError(f"未找到小说 '{novel_title}'")
                cover_dir_path = os.path.join(os.path.dirname(CONFIG_FILE), '书测')
                #cover_dir_path = os.path.join(os.getcwd(), '书测')
                if os.path.exists(cover_dir_path):
                    for filename in os.listdir(cover_dir_path):
                        if filename.endswith('.jpg') or filename.endswith('.png'):
                            new_title = os.path.splitext(filename)[0].strip('-封面').strip()
                            page.get_by_placeholder('请输入书名').last.fill(new_title, timeout=3000)
                            page.locator(' div.ne-config-item-body > div.ne-config-item-body-cover').last.click(timeout=3000)
                            page.get_by_text('本地上传', exact=True).last.click(timeout=1500)
                            page.locator('div.cover-upload input[type="file"]').set_input_files(os.path.join(cover_dir_path, filename))
                            page.wait_for_timeout(1000)
                            page.wait_for_load_state('networkidle')
                            page.get_by_text('确认上传', exact=True).last.click(timeout=1500)
                            page.wait_for_timeout(1500)
                            page.wait_for_load_state('load')
                            page.get_by_text('确定', exact=True).last.click(timeout=1500)
                            try:
                                page.get_by_text('添加实验组').last.click(timeout=3000)
                            except Exception:
                                break
                else:
                    raise RuntimeError("未找到书测封面目录")
                page.get_by_text('提交', exact=True).click(timeout=1500)
                page.get_by_text('确认', exact=True).click(timeout=1500)
                page.wait_for_timeout(1500)
                os.rename(cover_dir_path, cover_dir_path+f'已完成{datetime.datetime.now().strftime("%Y%m%d%H%M")}')
                page.wait_for_load_state('networkidle')
                page.wait_for_load_state('load')
            self.novel_status = '书测中'
            self.save_config(True)
        except Exception as e:
            print(f"书测过程中出现错误: {e}")
            traceback.print_exc()
        self.scheduled_task.remove('书测')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def schedule_command_by_cover(self):
        if self.publish_plate_var.get() != "番茄":
            print("封测仅支持番茄平台")
            return
        print("=====================================")
        custom_browser_path = self.custom_browser_path_var.get()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.keep_browser_open_var.get(), 
                    executable_path=custom_browser_path if custom_browser_path else None,
                    args=[
                        "--disable-popup-blocking",  # 禁用弹窗拦截
                        "--disable-web-security",  # 禁用网页安全策略
                        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                    ],
                    ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                )
                if not os.path.exists(AUTH_FILE):
                    raise FileNotFoundError(f"未找到认证文件 {AUTH_FILE}")
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=AUTH_FILE)
                page = context.new_page()
                novel_title = self.novel_title_var.get()
                site_url = self._get_site_url()
        
                page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
                print("点击进入小说推荐页面...")
                novel_command_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(7) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                try:
                    page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
                    try:
                        page.click('div.user-guide-btn > button', timeout=1000)
                        print("已关闭初始引导浮窗。")
                    except Exception:
                        print("未找到初始引导浮窗，继续执行...")
                    try:
                        page.get_by_text("立即收下").click(timeout=1000)
                        print("收下补签卡")
                    except Exception:
                        pass
                    try:
                        print("重新点击进入小说列表页面...")
                        page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                        page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                        page.wait_for_load_state('domcontentloaded')
                    except Exception as e:
                        print(f"点击小说列表导航元素时发生错误: {e}")
                        raise  # 重新抛出异常以便上层捕获
                print(f"正在查找小说: '{novel_title}'")
                page.get_by_text('多封面推荐').last.click(timeout=1500)
                try:
                    page.get_by_text('我知道了').last.click(timeout=1500)
                except Exception:
                    pass
                cover_selector = '#app > div > div.content.new-content > div.serial-card.serial-card-large.content-card-wrap.path-prefix-multi-cover > div > div.book-select.multi-cover-select-book-card > div.book-select-info > div.book-select-info-title'
                page.wait_for_load_state('load')
                while page.locator(cover_selector).inner_text() != novel_title:
                    page.get_by_text('切换作品').last.click(timeout=3000)
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state('load')
                    page.get_by_text(novel_title).last.click(timeout=3000, force=True)
                    # page.get_by_text(novel_title).last.click(timeout=3000, force=True)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.get_by_text('确定').last.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                cover_dir_path = os.path.join(os.getcwd(), '封测')
                new_title = ''
                if os.path.exists(cover_dir_path):
                    for filename in os.listdir(cover_dir_path):
                        if filename.endswith('.jpg') or filename.endswith('.png'):
                            new_title = os.path.splitext(filename)[0].split('_')[0]
                            break
                else:
                    print("未找到封测封面目录")
                if new_title == novel_title:
                    # 封说标题匹配，点击立即配置
                    print("原书名封测")
                    page.get_by_text('立即配置').first.click(timeout=3000)
                else:
                    print("书测名封测")
                    page.get_by_text('立即配置').last.click(timeout=3000)  

                for filename in os.listdir(cover_dir_path):
                    if filename.endswith('.jpg') or filename.endswith('.png'):
                        new_title = os.path.splitext(filename)[0].split('_')[0]
                        page.get_by_text('本地上传', exact=True).last.click(timeout=1500)
                        page.locator('div.cover-upload input[type="file"]').set_input_files(os.path.join(cover_dir_path, filename))
                        page.wait_for_timeout(1000)
                        page.wait_for_load_state('networkidle')
                        page.get_by_text('确认上传', exact=True).last.click(timeout=1500)
                        page.wait_for_timeout(1500)
                        page.wait_for_load_state('load')
                        page.get_by_text('确定', exact=True).last.click(timeout=1500)
                        try:
                            page.get_by_text('配置封面').first.click(timeout=3000)
                        except Exception:
                            break

                page.get_by_text('提交审核').last.click(timeout=3000)      
                page.get_by_text('确认').last.click(timeout=3000) 
                page.wait_for_timeout(1500)
                os.rename(cover_dir_path, cover_dir_path+f'已完成{datetime.datetime.now().strftime("%Y%m%d%H%M")}')
                page.wait_for_load_state('networkidle')
                page.wait_for_load_state('load')
            self.novel_status = '封测中'
            self.save_config(True)
        except Exception as e:
            print(f"封测过程中出现错误: {e}")
            traceback.print_exc()
        self.scheduled_task.remove('封测')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def schedule_check_attendance(self):
        if self.publish_plate_var.get() != "番茄":
            print("全勤检查 暂时仅支持番茄平台")
            return
        print("=====================================")
        custom_browser_path = self.custom_browser_path_var.get()
        try:
            with sync_playwright() as p:
                browser, context = self._normal_open_browser(p, custom_browser_path, self.keep_browser_open_var.get())
                page = context.new_page()
                novel_title = self.novel_title_var.get()
                site_url = self._get_site_url()
        
                page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
                print("进入小说收益页面...")
                novel_income_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(4) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                try:
                    page.wait_for_selector(novel_income_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_income_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
                    try:
                        page.click('div.user-guide-btn > button', timeout=1000)
                        print("已关闭初始引导浮窗。")
                    except Exception:
                        print("未找到初始引导浮窗，继续执行...")
                    try:
                        page.get_by_text("立即收下").click(timeout=1000)
                        print("收下补签卡")
                    except Exception:
                        pass
                    try:
                        print("重新点击进入小说列表页面...")
                        page.wait_for_selector(novel_income_selector, timeout=3000)  # 等待元素出现
                        page.click(novel_income_selector, timeout=1500)  # 延长点击超时
                        page.wait_for_load_state('domcontentloaded')
                    except Exception as e:
                        print(f"点击小说列表导航元素时发生错误: {e}")
                        raise  # 重新抛出异常以便上层捕获
                print("========1、检查收益情况========")
                check_res1 = False
                name_selector = 'div > div > div.book-select > div.book-select-info > div.book-select-info-title'
                if page.locator(name_selector).inner_text() != novel_title:
                    page.get_by_text('切换作品').last.click(timeout=3000)
                    page.wait_for_load_state('domcontentloaded')
                    page.get_by_text(novel_title).last.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                    page.get_by_text('确定').last.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                page.get_by_text('自定义').last.click(timeout=3000)
                current_date = datetime.datetime.now()
                # 采取当月1号作为开始日期,昨天为结束日期
                start_date = current_date.replace(day=1)
                end_date = (current_date - datetime.timedelta(days=1))
                page.get_by_placeholder('开始日期').fill(start_date.strftime('%Y-%m-%d'), timeout=3000)
                page.get_by_placeholder('结束日期').fill(end_date.strftime('%Y-%m-%d'), timeout=3000)
                page.get_by_placeholder('结束日期').press('Enter', timeout=3000)
                page.wait_for_timeout(3000)
                page.wait_for_load_state('load')
                table_count = page.locator('td:nth-child(1)').count()
                print(f"当前查询时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
                print(f"当前查询到 {table_count} 条数据")
                all_income = 0
                for i in range(table_count):
                    income_by_read = page.locator('td:nth-child(3)').nth(i).inner_text().replace('元', '')
                    income_by_read = income_by_read.replace(',', '')
                    income_by_listen = page.locator('td:nth-child(4)').nth(i).inner_text().replace('元', '')
                    income_by_listen = income_by_listen.replace(',', '')
                    all_income = all_income + float(income_by_read) + float(income_by_listen)
                print(f"当前听读总收益: {all_income:.2f}元, 日均收益: {all_income/table_count:.2f}元")
                month_days = ((start_date+datetime.timedelta(days=31)).replace(day=1) - start_date).days
                print(f"估计本月收益: {(all_income/table_count) * month_days:.2f}元")
                if all_income >= 500:
                    check_res1 = True
                    print("当前听读收益已超过500元，具备全勤实力！")
                # 平均值乘以当月的天数大于500元，具备全勤实力（当月不一定30天）
                elif (all_income/table_count) * month_days >= 500:
                    check_res1 = False
                    print("估计本月听读收益已超过500元，具备一定的全勤实力")
                    self.novel_status = '有全勤实力'
                else:
                    check_res1 = False
                    print("估计本月听读收益不足500元，无全勤")
                print("========2、检查发布情况========")
                check_res2 = True
                plate_init = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(1) > div > span.new-nav-item-content'
                page.wait_for_selector(plate_init, timeout=3000)  # 等待元素出现
                page.click(plate_init, timeout=1500)  # 延长点击超时
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')

                book_trigger = 'div.clock-in-calendar-filters > div.filter-book-trigger'
                while page.locator(book_trigger).inner_text() != novel_title:
                    page.click(book_trigger, timeout=1500)  # 延长点击超时
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                    page.get_by_text(novel_title).last.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(1500)
                # self.debug()
                n = 0
                m = 0
                for i in range(page.locator('div > div.content-value').count()):
                    publish_words_count_element = page.locator('div > div.content-value').nth(i)
                    if publish_words_count_element.inner_text().isdigit():
                        publish_words_count = int(publish_words_count_element.inner_text())
                        publish_date = publish_words_count_element.locator('..').locator('div.content-date').inner_text()
                        if publish_words_count >= 6000:
                            n += 1
                            m += 1   
                        elif publish_words_count >= 4000:
                            m += 1
                            print(f"{publish_date}号发布字数{publish_words_count}，不足6000字")
                        else:
                            print(f"{publish_date}号发布字数{publish_words_count}，不足4000字")
                            check_res2 = False
                #print(f"当前查询到 {page.locator('div > div.content-value').count()} 条数据")
                if m != month_days:
                    check_res2 = False

                if check_res1 and check_res2:
                    print("全勤检查通过")
                    if n == month_days:
                        print("并且为进阶版全勤")
                    else:
                        print(f"日更6000+仅有{n}天")
                    self.novel_status = '全勤中'
                else:
                    if not check_res2:
                        print("本月有缺勤，请查看发布记录")
                        self.novel_status = '有缺勤'
                    print("全勤检查未通过")
                self.save_config(True)
        except Exception as e:
            print(f"全勤检查过程中出现错误: {e}")
            traceback.print_exc()
        
        self.scheduled_task.remove('全勤检查')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    def toggle_window_width(self, event=None):
        """切换窗口宽度在最大值和最小值之间"""
        width, height = self.winfo_width(), self.winfo_height()
        if self.is_max_width:
            # 切换到最小宽度
            self.geometry(f"{self.min_width}x{self.min_height}")
        else:
            # 切换到最大宽度
            self.geometry(f"{self.max_width}x{self.max_height}")
        self.is_max_width = not self.is_max_width

    def log(self, message):
        if hasattr(self, '_log_redirector'):
            self._log_redirector.log(message)

    def redirect_logging(self):
        self._log_redirector = TextRedirector(self.log_text)
        self._log_redirector.install()

    def restore_stdout(self):
        if hasattr(self, '_log_redirector'):
            self._log_redirector.restore()

    def write(self, text):
        if hasattr(self, '_log_redirector'):
            self._log_redirector.write(text)

    def flush(self):
        if hasattr(self, '_log_redirector'):
            self._log_redirector.flush()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE, encoding='utf-8')
            # 兼容
            if self.config.get('Settings', 'publish_mode', fallback='') in ['publish', '立刻发布']:
                self.config['Settings']['publish_mode'] = '立刻发布'
            elif self.config.get('Settings', 'publish_mode', fallback='') in ['pre-publish', '定时发布']:
                self.config['Settings']['publish_mode'] = '定时发布'
            else:
                self.config['Settings']['publish_mode'] = '保存为草稿'

        else:
            self.config['Settings'] = {}
            self.config['Novel'] = {}
            self.config['History'] = {}

    def refresh_ui(self):
        """重新从配置文件加载并刷新界面，忽略并覆盖所有未保存的修改，回到初始加载状态"""
        try:
            # 重新创建一个全新的 ConfigParser，确保丢弃内存中所有未保存的修改
            self.config = configparser.ConfigParser()
            self.load_config()

            # --- 发布配置 ---
            self.custom_browser_path_var.set(
                self.config.get('Settings', 'custom_browser_path',
                                fallback='(必填)允许多个账号使用同一个浏览器'))
            self.publish_plate_var.set(
                self.config.get('Settings', 'publish_plate', fallback='番茄'))
            self.publish_mode_var.set(
                self.config.get('Settings', 'publish_mode', fallback='立刻发布'))
            self.publish_time_var.set(
                self.config.get('Settings', 'publish_time', fallback='00:00'))
            self.interval_publish_mode_var.set(
                self.config.get('Settings', 'interval_publish_mode', fallback='1/0'))
            self.daily_publish_num_var.set(
                int(self.config.get('Settings', 'daily_publish_num', fallback='2')))
            self.daily_publish_count_var.set(
                int(self.config.get('Settings', 'daily_publish_count', fallback='4000')))
            self.keep_browser_open_var.set(
                self.config.getboolean('Settings', 'close_browser_open', fallback=False))
            self.neat_index_var.set(
                self.config.getboolean('Settings', 'neat_index', fallback=True))
            self.danger_pre_check_var.set(
                self.config.getboolean('Settings', 'danger_pre_check', fallback=False))

            # --- 小说配置 ---
            self.novel_title_var.set(
                self.config.get('Novel', 'novel_title', fallback='你的小说名(完整无误的)'))
            self.novel_writer_var.set(
                self.config.get('Novel', 'novel_writer', fallback='你的笔名(选填)'))
            self.novels_folder_var.set(
                self.config.get('Novel', 'novels_folder',
                                fallback='小说文件夹(允许相对路径/如果没有则输入路径然后点击导入)'))
            self.novel_status = self.config.get('Novel', 'novel_status', fallback='未设置')

            # --- 历史与章节范围 ---
            last_published_chapter = int(self.config.get('History', 'last_published_chapter', fallback='0'))
            self.last_published_chapter_date_var.set(
                self.config.get('History', 'last_published_chapter_date',
                                fallback=(datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')))
            self.daily_publish_num_remain_var.set(
                int(self.config.get('History', 'daily_publish_num_remain', fallback='0')))
            self.daily_publish_count_remain_var.set(
                int(self.config.get('History', 'daily_publish_count_remain', fallback='0')))

            self.start_chapter_var.set(last_published_chapter + 1)
            daily_publish_num = int(self.daily_publish_num_var.get())
            self.end_chapter_var.set(
                last_published_chapter + (daily_publish_num if daily_publish_num != -1 else 1))

            # --- 运行时状态重置 ---
            self.fast_publish_mode = False
            self.stop_publish_sign = False
            self.publish_time = datetime.datetime.now()
            self.wait_event.clear()

            # --- 刷新章节计数 ---
            self.update_chapter_count()

            print('界面已刷新，所有未保存的修改已丢弃')
        except Exception as e:
            print(f'刷新界面失败: {e}')
            traceback.print_exc()

    def save_config(self, event=None):
        try:
            if event is True:
                print('仅保存状态')
                print('保存成功')
                self.config['Novel']['novel_status'] = self.novel_status            
                with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                    self.config.write(configfile)
                return

            self.config['Settings']['custom_browser_path'] = self.custom_browser_path_var.get().replace('\\', '/')
            self.config['Settings']['publish_plate'] = self.publish_plate_var.get()
            self.config['Settings']['publish_mode'] = self.publish_mode_var.get()
            self.config['Settings']['close_browser_open'] = str(self.keep_browser_open_var.get())
            self.config['Settings']['publish_time'] = self.publish_time_var.get()
            self.config['Settings']['daily_publish_num'] = str(self.daily_publish_num_var.get())
            self.config['Settings']['daily_publish_count'] = str(self.daily_publish_count_var.get())
            self.config['Settings']['neat_index'] = str(self.neat_index_var.get())
            self.config['Settings']['danger_pre_check'] = str(self.danger_pre_check_var.get())
            self.config['Settings']['interval_publish_mode'] = self.interval_publish_mode_var.get()
            # ---
            self.config['History']['last_published_chapter'] = str(int(self.start_chapter_var.get()) - 1)
            self.config['History']['last_published_chapter_date'] = self.last_published_chapter_date_var.get()
            self.config['History']['daily_publish_num_remain'] = str(self.daily_publish_num_remain_var.get())
            self.config['History']['daily_publish_count_remain'] = str(self.daily_publish_count_remain_var.get())
            # ---
            self.config['Novel']['novel_title'] = self.novel_title_var.get()
            self.config['Novel']['novel_writer'] = self.novel_writer_var.get()
            self.config['Novel']['novel_status'] = self.novel_status

            if os.path.isdir(self.novels_folder_var.get()):
                self.config['Novel']['novels_folder'] = self.novels_folder_var.get()
            else:
                messagebox.showerror("错误", "请输入正确的小说文件夹路径！拆分导入章节已独立")
                return
            # if self.novels_folder_var.get().endswith('.txt'):
            #     self.create_chapter_files_in_files(self.novels_folder_var.get())
            # self.config['Novel']['novels_folder'] = self.novels_folder_var.get().replace('.txt', '')
            self.novels_folder_var.set(self.config['Novel']['novels_folder'])
            
            # 更新章节计数
            self.update_chapter_count()
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            if self.fast_publish_mode:
                print('配置自动保存成功')
            else:
                print('配置保存成功')
                if event is None:   
                    messagebox.showinfo(f"《{self.novel_title_var.get()}》已发布成功", "祝 本本爆款！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def update_chapter_count(self):
        """更新章节总数显示"""
        try:
            novels_folder = self.novels_folder_var.get()
            if novels_folder and os.path.isdir(novels_folder):
                chapter_files = [f for f in os.listdir(novels_folder) if f.endswith('.md') and f.startswith('Chapter_')]
                count = len(chapter_files)
                self.chapter_count_var.set(str(count))
                print(f"检测到 {count} 个章节文件")
            else:
                self.chapter_count_var.set("0")
        except Exception as e:
            print(f"更新章节计数失败: {e}")
            self.chapter_count_var.set("0")
    
    def start_check_duplicate_titles(self):
        """后台执行标题和章节字数检查，避免阻塞界面。"""
        novels_folder = self.novels_folder_var.get()
        neat_index = self.neat_index_var.get()
        self.check_title_button.config(state='disabled', text="检查中...")
        threading.Thread(target=self.check_duplicate_titles, args=(novels_folder, neat_index), daemon=True).start()

    def check_duplicate_titles(self, novels_folder=None, neat_index=True):
        """检查并修复重复的章节标题，同时检查标题字数和章节字数"""
        try:
            if novels_folder is None:
                novels_folder = self.novels_folder_var.get()
            if not novels_folder or not os.path.isdir(novels_folder):
                self.after(0, lambda: self._finish_check_duplicate_titles(error_message="请先设置正确的小说文件夹路径"))
                return
            
            # 获取章节文件，按章节号排序
            chapter_files = []
            for f in os.listdir(novels_folder):
                if f.endswith('.md') and f.startswith('Chapter_'):
                    match = re.search(r'_(\d+)', f)
                    if match:
                        chapter_num = int(match.group(1))
                        chapter_files.append((chapter_num, os.path.join(novels_folder, f)))
            
            if not chapter_files:
                self.after(0, lambda: self._finish_check_duplicate_titles(error_message="未找到章节文件"))
                return
            
            # 按章节号排序
            chapter_files.sort(key=lambda x: x[0])
            word_count_issues = self.check_chapter_word_counts(chapter_files, neat_index)
            
            # 用于记录已处理的标题及其出现次数
            title_counts = {}
            modified_count = 0
            modified_info = []
            
            # 遍历所有章节文件
            for chapter_num, filepath in chapter_files:
                try:
                    # 读取文件内容
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if not lines:
                        continue
                    
                    # 获取标题行（通常是第一行，以#开头）
                    first_line = lines[0].strip()
                    if not first_line.startswith('#'):
                        continue
                    
                    # 提取标题内容（去掉#和空格）
                    original_title = first_line.lstrip('#').strip()
                    current_title = original_title
                    
                    # 检查标题长度，超过20字则截断
                    # 分离章节前缀（如"第X章"、"第X节"等）和实际标题内容
                    # X可以是任意长度的字符
                    chapter_prefix_pattern = r'^(第.*?[章节话])'
                    match = re.match(chapter_prefix_pattern, current_title)
                    if match:
                        # 有章节前缀的情况
                        prefix = match.group(1)
                        actual_title = current_title[len(prefix):]
                        
                        # 去掉实际标题开头的分隔符（如冒号、空格等）
                        actual_title = actual_title.lstrip(':： 	')
                        rematch = re.match(chapter_prefix_pattern, actual_title)
                        if rematch:
                            actual_title = actual_title[len(rematch.group(1)):].lstrip(':： 	')
                        
                        # 只对实际标题部分进行字数检查和截断
                        if len(actual_title) > 30:
                            actual_title = actual_title[:30]
                            print(f"截断标题: 章节 {chapter_num} 的标题 '{original_title}' 已截断为 '{current_title}'")
                        current_title = f"第{chapter_num}章：{actual_title}"
                            
                    else:
                        # 没有章节前缀的情况，直接检查整个标题
                        if len(current_title) > 30:
                            actual_title = current_title
                            current_title = current_title[:30]
                    
                    # 检查标题是否重复
                    if actual_title in title_counts:
                        # 增加计数并修改标题
                        title_counts[actual_title] += 1
                        new_title = f"{current_title}({title_counts[actual_title]})"
                    else:
                        # 首次出现的标题
                        title_counts[actual_title] = 1
                        new_title = current_title
                    
                    # 如果标题有变化（截断或去重），则更新文件
                    if new_title != original_title:
                        new_first_line = f"# {new_title}\n"
                        
                        # 更新文件内容
                        lines[0] = new_first_line
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        
                        modified_count += 1
                        modified_info.append(f"章节 {chapter_num}: '{original_title}' -> '{new_title}'")
                        # print(f"修改标题: 章节 {chapter_num} 的标题 '{original_title}' 已修改为 '{new_title}'")
                        
                except Exception as e:
                    print(f"处理文件 {filepath} 时出错: {e}")
            
            self.after(0, lambda: self._finish_check_duplicate_titles(modified_count, modified_info, word_count_issues))
                
        except Exception as e:
            self.after(0, lambda err=str(e): self._finish_check_duplicate_titles(error_message=f"检查标题时发生错误: {err}"))

    def _finish_check_duplicate_titles(self, modified_count=0, modified_info=None, word_count_issues=None, error_message=None):
        self.check_title_button.config(state='normal', text="检查标题")
        if error_message:
            messagebox.showerror("错误", error_message)
            return

        modified_info = modified_info or []
        word_count_issues = word_count_issues or []
        result_message = f"检查完成！共修改了 {modified_count} 个标题。"
        if modified_count > 0:
            result_message += "\n\n标题修改详情:\n" + "\n".join(modified_info[:10])
            if len(modified_info) > 10:
                result_message += f"\n... 等 {len(modified_info) - 10} 个更多修改"
        if word_count_issues:
            result_message += f"\n\n发现 {len(word_count_issues)} 个章节字数异常，已打开问题列表。"
            self.show_chapter_word_count_issues(word_count_issues)
        else:
            result_message += "\n\n未发现章节字数异常。"
        messagebox.showinfo("完成", result_message)

    def check_chapter_word_counts(self, chapter_files, neat_index=True):
        """多线程检查章节正文低于1000字或大于4000字的问题。"""
        def check_one(chapter_num, filepath):
            chapter_details = _cf_get_details(filepath, neat_index, verbose=False)
            word_count = self.count_chinese_characters(chapter_details[2])
            if word_count < 1000 or word_count > 4000:
                return {
                    'chapter_num': chapter_num,
                    'title': chapter_details[1],
                    'word_count': word_count,
                    'filepath': filepath,
                }
            return None

        issues = []
        max_workers = min(32, max(1, len(chapter_files)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(check_one, chapter_num, filepath): filepath for chapter_num, filepath in chapter_files}
            for future in as_completed(future_map):
                try:
                    issue = future.result()
                    if issue:
                        issues.append(issue)
                except Exception as e:
                    print(f"检查章节字数失败 {future_map[future]}: {e}")
        issues.sort(key=lambda item: item['chapter_num'])
        return issues

    def show_chapter_word_count_issues(self, issues):
        """显示章节字数异常列表，双击或点击按钮可打开章节文件。"""
        dialog = tk.Toplevel(self)
        dialog.title("章节字数异常")
        dialog.geometry("680x420")
        dialog.transient(self)

        columns = ('chapter_num', 'title', 'word_count')
        tree = ttk.Treeview(dialog, columns=columns, show='headings', selectmode='browse')
        tree.heading('chapter_num', text='章节序号')
        tree.heading('title', text='章节名')
        tree.heading('word_count', text='字数')
        tree.column('chapter_num', width=90, anchor=tk.CENTER)
        tree.column('title', width=440)
        tree.column('word_count', width=90, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        filepath_map = {}
        for issue in issues:
            item_id = tree.insert('', tk.END, values=(issue['chapter_num'], issue['title'], issue['word_count']))
            filepath_map[item_id] = issue['filepath']

        def open_selected(event=None):
            selected = tree.selection()
            if not selected:
                return
            filepath = filepath_map.get(selected[0])
            if filepath and os.path.exists(filepath):
                os.startfile(filepath)

        tree.bind('<Double-1>', open_selected)
        ttk.Button(dialog, text="打开选中章节", command=open_selected).pack(pady=(0, 10))

    def auto_detect_browser(self):
        """自动检测浏览器路径"""
        try:
            print("开始自动检测浏览器...")
            self.auto_detect_btn.config(state='disabled', text="检测中...")
            
            # 在新线程中执行检测，避免阻塞界面
            def detect_worker():
                try:
                    # 获取推荐的浏览器路径
                    recommended_path = BrowserDetector.get_recommended_browser()
                    
                    if recommended_path:
                        self.after(0, lambda: self._update_browser_path(recommended_path))
                        print(f"自动检测到浏览器: {recommended_path}")
                    else:
                        self.after(0, self._show_no_browser_found)
                        print("未检测到可用的浏览器")
                        
                except Exception as e:
                    self.after(0, lambda: self._show_detection_error(str(e)))
                    print(f"浏览器检测失败: {e}")
                finally:
                    self.after(0, lambda: self.auto_detect_btn.config(state='normal', text="自动检测"))
            
            # 启动检测线程
            detect_thread = threading.Thread(target=detect_worker, daemon=True)
            detect_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"启动浏览器检测失败: {e}")
            self.auto_detect_btn.config(state='normal', text="自动检测")

    def _update_browser_path(self, path: str):
        """更新浏览器路径显示"""
        self.custom_browser_path_var.set(path)
        messagebox.showinfo("成功", f"已自动检测到浏览器路径:\n{path}")

    def _show_no_browser_found(self):
        """显示未找到浏览器的提示"""
        messagebox.showwarning("提示", "未检测到可用的浏览器\n请手动设置浏览器路径")

    def _show_detection_error(self, error_msg: str):
        """显示检测错误"""
        messagebox.showerror("检测失败", f"浏览器检测失败:\n{error_msg}\n\n请手动设置浏览器路径")

    def run_login_thread(self):
        self.login_event = threading.Event()
        if self.login_page:
            self.login_event.set()
        else:
            threading.Thread(target=self.login, daemon=True).start()

    def _get_site_url(self):
        """根据发布平台获取登录URL"""
        return _get_site_url_impl(self.publish_plate_var.get())

    def _get_app_base_dir(self):
        """获取应用数据目录。

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

    def _get_login_profile_dir(self):
        """获取登录专用浏览器配置目录（每个站点独立）

        Chromium 系浏览器（Chrome/Edge）对同一 user-data-dir 强制单实例：
        若该目录已被某个正在运行的浏览器占用，新启动会被"交接"给已有实例并立即退出，
        导致 Playwright 报 TargetClosedError（对应日志中的"正在现有浏览器会话中打开"）。
        使用每个站点独立的配置目录即可避免冲突，这也是官方维护者的建议。
        """
        site = self._get_site_url() or 'default'
        site_name = re.sub(r'[^0-9a-zA-Z\u4e00-\u9fff_-]+', '_', site.split('?')[0].rstrip('/'))[:50]
        profile_dir = os.path.join(self._get_app_base_dir(), 'browser_profiles', site_name)
        try:
            os.makedirs(profile_dir, exist_ok=True)
        except Exception:
            pass
        return profile_dir

    def _terminate_browser_using_profile(self, profile_dir):
        """结束仍占用指定配置目录的残留浏览器进程（上次异常退出遗留），避免启动交接冲突"""
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

    def _get_login_browser_candidates(self):
        """获取登录可用浏览器候选列表，当前选择优先，失败后自动换其它浏览器"""
        candidates = []
        current = (self.custom_browser_path_var.get() or '').strip()
        if current and os.path.isfile(current):
            candidates.append(current)
        try:
            for path in BrowserDetector.detect_all_browsers().values():
                if path and os.path.isfile(path) and path not in candidates:
                    candidates.append(path)
        except Exception:
            pass
        return candidates

    def _launch_login_context(self, playwright, profile_dir):
        """启动登录浏览器；若当前 Edge 被企业策略/版本限制关闭，自动切换其它浏览器"""
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
        candidates = self._get_login_browser_candidates()
        for index, browser_path in enumerate(candidates):
            browser_name = os.path.splitext(os.path.basename(browser_path))[0]
            candidate_profile_dir = profile_dir if index == 0 else f"{profile_dir}_{browser_name}_{index}"
            try:
                os.makedirs(candidate_profile_dir, exist_ok=True)
            except Exception:
                pass
            self._terminate_browser_using_profile(candidate_profile_dir)
            print(f"尝试启动浏览器: {browser_path}")
            print(f"浏览器配置目录: {candidate_profile_dir}")
            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=candidate_profile_dir,
                    executable_path=browser_path,
                    **common_kwargs
                )
                if browser_path != self.custom_browser_path_var.get():
                    self.custom_browser_path_var.set(browser_path)
                return context
            except Exception as e:
                last_error = e
                print(f"启动失败，尝试下一个浏览器: {e}")
        try:
            print("本机浏览器启动失败，尝试使用 Playwright 内置 Chromium...")
            builtin_profile_dir = f"{profile_dir}_playwright_chromium"
            os.makedirs(builtin_profile_dir, exist_ok=True)
            self._terminate_browser_using_profile(builtin_profile_dir)
            return playwright.chromium.launch_persistent_context(
                user_data_dir=builtin_profile_dir,
                **common_kwargs
            )
        except Exception as e:
            last_error = e
        raise last_error

    def login(self):
        site_url = self._get_site_url()
        print("正在启动浏览器...")
        try:
            with sync_playwright() as p:
                # # 使用每个站点独立的浏览器配置目录，避免与已打开的浏览器实例冲突
                # profile_dir = self._get_login_profile_dir()
                # # 清理上次异常退出后残留、仍占用该配置目录的浏览器进程
                # self._terminate_browser_using_profile(profile_dir)
                # # 添加必要的浏览器参数以允许弹窗和滑块验证，并在当前浏览器启动失败时自动切换其它浏览器
                # context = self._launch_login_context(p, profile_dir)
                # # 持久化上下文自带初始页面，直接使用
                # self.login_page = context.pages[0] if context.pages else context.new_page()
                browser = p.chromium.launch(
                    headless=False, 
                    executable_path=self.custom_browser_path_var.get(),
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
                self.login_page = context.new_page()

                print(f"请在打开的浏览器窗口中手动登录网站: {site_url}，完成后再次点击登录按钮完成登录。")
                self.login_page.goto(site_url, timeout=60000)
                # self.login_page.wait_for_timeout(600000)
                # 非阻塞等待登录完成信号
                while not self.login_event.is_set():
                    time.sleep(1)
                try:
                    if (self.publish_plate_var.get() != self.config.get('Settings', 'publish_plate', fallback='') 
                        or self.novel_writer_var.get() != self.config.get('Novel', 'novel_writer', fallback='')):
                        if os.path.exists(AUTH_FILE):
                            os.remove(AUTH_FILE)
                            print("检测到账号变更")
                            print("已删除旧的登录状态文件")
                    context.storage_state(path=AUTH_FILE)
                    print(f"登录状态已保存到 {AUTH_FILE}")
                except Exception as e:
                    print(f"保存登录状态失败: {e}")
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass
                    print("浏览器已关闭。")
                    self.login_page = None
        except Exception as e:
            traceback.print_exc()
            print(f"登录失败: {e}")
            try:
                self.after(0, lambda err=e: messagebox.showerror(
                    "登录失败",
                    f"启动浏览器失败:\n{err}\n\n"
                    f"程序已自动尝试切换 Chrome/Edge/内置 Chromium。\n"
                    f"若仍失败，通常是企业版系统安全策略、浏览器策略或杀毒软件拦截了自动化浏览器启动。"
                ))
            except Exception:
                pass

    def run_automation_thread(self, fast_once=False):
        # if self.end_chapter_var.get() < self.start_chapter_var.get():
        #     messagebox.showerror("错误", "结束章节必须大于等于开始章节")
        #     return
        if self.end_chapter_var.get() - self.start_chapter_var.get() > 20 and self.publish_mode_var.get() == '立刻发布':
            if not messagebox.askyesno("确认", "当天发布章节超过20章，是否继续？"):
                return
        self.run_button.config(state='disabled')
        threading.Thread(target=self.run_automation, args=(fast_once,), daemon=True).start()

    def run_automation(self, fast_once=False):
        try:
            if fast_once:
                self.new_novel_publish_once()
            else:
                self.automation_flow()
        except ValueError:
            traceback.print_exc()
            messagebox.showerror("错误", "章节范围必须是有效的整数。")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("运行时错误", f"执行自动化流程时发生错误: {e}")
        finally:
            self.after(0, lambda: self.run_button.config(state='normal'))        

    def export_chapters(self):
        """导出章节功能"""
        try:
            novels_folder = self.novels_folder_var.get()
            if not novels_folder or not os.path.isdir(novels_folder):
                messagebox.showerror("错误", "请先设置正确的小说文件夹路径")
                return

            # 获取章节文件
            chapter_files = []
            for f in os.listdir(novels_folder):
                if f.endswith('.md') and f.startswith('Chapter_'):
                    match = re.search(r'_(\d+)', f)
                    if match:
                        chapter_num = int(match.group(1))
                        chapter_files.append((chapter_num, os.path.join(novels_folder, f)))
            
            if not chapter_files:
                messagebox.showerror("错误", "未找到章节文件")
                return

            chapter_files.sort(key=lambda x: x[0])
            
            # 创建导出对话框
            export_dialog = tk.Toplevel(self)
            export_dialog.title("导出章节")
            export_dialog.geometry("400x300")
            export_dialog.transient(self)
            export_dialog.grab_set()

            # 导出范围选择
            ttk.Label(export_dialog, text="选择导出范围:").pack(pady=10)
            
            # 范围输入框
            range_frame = ttk.Frame(export_dialog)
            range_frame.pack(pady=5)
            
            ttk.Label(range_frame, text="从第").pack(side=tk.LEFT)
            start_var = tk.StringVar(value="1")
            start_entry = ttk.Entry(range_frame, textvariable=start_var, width=5)
            start_entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(range_frame, text="章到第").pack(side=tk.LEFT)
            end_var = tk.StringVar(value=str(chapter_files[-1][0]))
            end_entry = ttk.Entry(range_frame, textvariable=end_var, width=5)
            end_entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(range_frame, text="章").pack(side=tk.LEFT)

            # 导出选项
            export_all_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(export_dialog, text="导出全部章节", 
                            variable=export_all_var,
                            command=lambda: self.toggle_export_range(start_entry, end_entry, export_all_var)).pack(pady=5)

            # 输出文件名
            ttk.Label(export_dialog, text="输出文件名:").pack(pady=5)
            output_var = tk.StringVar(value=f"{self.novel_title_var.get()}_导出.txt")
            ttk.Entry(export_dialog, textvariable=output_var, width=40).pack(pady=5)

            def perform_export():
                try:
                    if export_all_var.get():
                        start_chapter = 1
                        end_chapter = chapter_files[-1][0]
                    else:
                        start_chapter = int(start_var.get())
                        end_chapter = int(end_var.get())
                    
                    # 过滤要导出的章节
                    export_files = []
                    for chapter_num, filepath in chapter_files:
                        if start_chapter <= chapter_num <= end_chapter:
                            export_files.append((chapter_num, filepath))
                    
                    if not export_files:
                        messagebox.showerror("错误", "没有选择要导出的章节")
                        return

                    # 导出内容
                    output_content = []
                    for chapter_num, filepath in export_files:
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                content = f.read()
                                # 移除Markdown格式，转换为纯文本
                                content = content.replace('# ', '').replace('**', '')
                                output_content.append(content)
                                output_content.append('\n\n')  # 章节之间添加空行
                        except Exception as e:
                            print(f"读取章节 {chapter_num} 失败: {e}")
                    
                    # 保存文件
                    output_path = os.path.join(novels_folder, output_var.get())
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(''.join(output_content))
                    
                    messagebox.showinfo("成功", f"导出完成！共导出 {len(export_files)} 个章节\n文件保存为: {output_path}")
                    export_dialog.destroy()
                    
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的章节范围")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")

            # 导出按钮
            ttk.Button(export_dialog, text="开始导出", command=perform_export).pack(pady=20)

        except Exception as e:
            messagebox.showerror("错误", f"导出功能出错: {e}")

    def download_book(self):
        """下载小说功能"""
        try:
            novel_platform = self.publish_plate_var.get()
            # if novel_platform != "番茄":
            #     messagebox.showerror("错误", "目前仅支持番茄小说平台")
            #     return
            
            # 创建导出对话框
            export_dialog = tk.Toplevel(self)
            export_dialog.title("小说下载")
            export_dialog.geometry("400x360")
            export_dialog.transient(self)
            export_dialog.grab_set()

            ttk.Label(export_dialog, text="小说id:").pack(pady=10)
            # 范围输入框
            book_id_var = tk.StringVar()
            book_id_entry = ttk.Entry(export_dialog, textvariable=book_id_var, width=40)
            book_id_entry.pack(pady=5)

            # 导出范围选择
            ttk.Label(export_dialog, text="选择下载范围:").pack(pady=10)
            
            # 范围输入框
            range_frame = ttk.Frame(export_dialog)
            range_frame.pack(pady=5)
            
            ttk.Label(range_frame, text="从第").pack(side=tk.LEFT)
            start_var = tk.IntVar(value=1)
            start_entry = ttk.Entry(range_frame, textvariable=start_var, width=5)
            start_entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(range_frame, text="章到第").pack(side=tk.LEFT)
            end_var = tk.IntVar(value=3)
            end_entry = ttk.Entry(range_frame, textvariable=end_var, width=5)
            end_entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(range_frame, text="章").pack(side=tk.LEFT)

            # 导出选项
            export_all_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(export_dialog, text="下载全部章节", 
                            variable=export_all_var).pack(pady=5)
            just_download_content_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(export_dialog, text="只下载目录", 
                            variable=just_download_content_var).pack(pady=5)
            # open_after_download_var = tk.BooleanVar(value=False)
            # ttk.Checkbutton(export_dialog, text="完成时打开", 
            #                 variable=open_after_download_var).pack(pady=5)
            # 输出文件名
            ttk.Label(export_dialog, text="输出文件夹:").pack(pady=5)
            output_var = tk.StringVar(value="output")
            ttk.Entry(export_dialog, textvariable=output_var, width=40).pack(pady=5)

            def perform_export():
                try:
                    with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                        storage_state = json.load(f)

                    # 提取cookies并转换为requests格式
                    cookies = {}
                    for cookie in storage_state['cookies']:
                        cookies[cookie['name']] = cookie['value']
                    book_id= book_id_var.get().strip()
                    fqd = NovelDownloader(novel_platform, book_id, cookies)
                    result = fqd.parse_main_page()
                    output_dir = output_var.get()
                    # 判断小说页面是否解析成功
                    if not result:
                        print("[x] 小说页面解析失败，程序终止。")
                        messagebox.showerror("错误", "小说页面解析失败，程序终止。")
                        export_dialog.destroy()
                        return
                    else:
                        book_title, chapter_titles, chapter_urls, abstract_content = result
                        selected_titles = []
                        selected_urls = []
                        # for i, (title, url) in enumerate(zip(chapter_titles, chapter_urls), start=1):
                        #     print(f"{i}. {title} - {url}")
                        if just_download_content_var.get():
                            os.makedirs(output_dir, exist_ok=True)  # 确保输出目录存在
                            file_path = os.path.join(output_dir, f"{book_title}_目录.txt")
                            print(f"🎁 获取小说《{book_title}》目录")
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(f"《{book_title}》")
                                f.write("\n\n")
                                f.write("简介：")
                                f.write("\n".join(abstract_content))
                                f.write("\n\n")
                                f.write("\n".join(chapter_titles))
                            print(f"目录已保存到: {file_path}")
                            os.startfile(file_path)

                        else:
                            if export_all_var.get():
                                selected_titles = chapter_titles
                                selected_urls = chapter_urls
                                threading.Thread(target=fqd.download_chapters, args=(book_title, abstract_content, selected_titles, selected_urls, output_dir), daemon=True).start()
                            else:
                                start_str, end_str = start_var.get(), end_var.get()
                                start_idx = int(start_str) - 1  # 转换为列表下标
                                end_idx = int(end_str)  # 包含该章节

                                if 0 <= start_idx < end_idx <= len(chapter_urls):
                                    selected_titles = chapter_titles[start_idx:end_idx]
                                    selected_urls = chapter_urls[start_idx:end_idx]
                                    threading.Thread(target=fqd.download_chapters, args=(book_title, abstract_content, selected_titles, selected_urls, output_dir), daemon=True).start()
                            print(f"下载 {len(selected_titles)}/{len(chapter_titles)} 个章节\n文件保存为: {output_var.get()}/{book_title}.txt")

                    export_dialog.destroy()
                    
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的章节范围")
                except Exception as e:
                    messagebox.showerror("错误", f"下载失败: {e}")

            # 导出按钮
            ttk.Button(export_dialog, text="开始下载", command=perform_export).pack(pady=20)

            ttk.Label(export_dialog, text="ps.下载全文需要svip账号，否则只能下载前10章").pack(pady=5)

        except Exception as e:
            messagebox.showerror("错误", f"下载功能出错: {e}")

    def toggle_export_range(self, start_entry, end_entry, export_all_var):
        """切换导出范围输入框的状态"""
        if export_all_var.get():
            start_entry.config(state='disabled')
            end_entry.config(state='disabled')
        else:
            start_entry.config(state='normal')
            end_entry.config(state='normal')

    def import_chapters(self, event=None):
        """导入章节功能"""
        try:
            # 创建导入对话框
            import_dialog = tk.Toplevel(self)
            import_dialog.title("导入章节")
            import_dialog.geometry("600x500")
            import_dialog.transient(self)
            import_dialog.grab_set()
            
            # 文件选择区域
            file_frame = ttk.LabelFrame(import_dialog, text="选择TXT文件", padding="10")
            file_frame.pack(fill=tk.X, padx=10, pady=10)
            
            # 文件路径输入
            ttk.Label(file_frame, text="文件路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
            txt_file_var = tk.StringVar()
            txt_file_entry = ttk.Entry(file_frame, textvariable=txt_file_var, width=50)
            txt_file_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
            
            # 文件浏览按钮
            def browse_txt_file():
                from tkinter import filedialog
                file_path = filedialog.askopenfilename(
                    title="选择TXT文件",
                    filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
                )
                if file_path:
                    txt_file_var.set(file_path)
            
            ttk.Button(file_frame, text="浏览", command=browse_txt_file).grid(row=0, column=2, padx=5, pady=5)
            file_frame.columnconfigure(1, weight=1)
            
            # 章节列表区域
            list_frame = ttk.LabelFrame(import_dialog, text="章节列表", padding="10")
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # 章节列表
            chapter_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=10)
            chapter_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # 滚动条
            scrollbar = ttk.Scrollbar(chapter_listbox, orient=tk.VERTICAL, command=chapter_listbox.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            chapter_listbox.config(yscrollcommand=scrollbar.set)
            
            # 分解章节按钮
            def parse_chapters():
                file_path = txt_file_var.get()
                if not file_path or not os.path.exists(file_path):
                    messagebox.showerror("错误", "请选择有效的TXT文件")
                    return
                
                if not file_path.endswith('.txt'):
                    messagebox.showerror("错误", "请选择TXT文件")
                    return
                
                try:
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 使用正则表达式分解章节
                    chapter_pattern = re.compile(r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[:：\s]+.*$)', re.MULTILINE)
                    parts = chapter_pattern.split(content)
                    
                    if len(parts) <= 1:
                        messagebox.showerror("错误", "未找到任何章节")
                        return
                    
                    # 清空列表
                    chapter_listbox.delete(0, tk.END)
                    
                    # 解析章节
                    chapters = []
                    for i in range(1, len(parts), 2):
                        title = parts[i].strip()
                        if i + 1 < len(parts):
                            chapter_content = parts[i + 1].strip()
                            chapters.append({"title": title, "content": chapter_content})
                    
                    # 倒序添加到列表
                    for i in range(len(chapters)-1, -1, -1):
                        chapter_num = i + 1
                        title = chapters[i]["title"]
                        chapter_listbox.insert(tk.END, f"{chapter_num}_{title}")
                    
                    messagebox.showinfo("成功", f"成功解析出 {len(chapters)} 个章节")
                    
                except Exception as e:
                    messagebox.showerror("错误", f"解析文件失败: {str(e)}")
            
            # 追加十章按钮功能
            def select_next_ten():
                # 获取当前所有项目
                total_items = chapter_listbox.size()
                if total_items == 0:
                    messagebox.showinfo("提示", "请先分解章节")
                    return
                
                # 获取当前选中的项目
                currently_selected = set(chapter_listbox.curselection())
                
                # 从上到下查找10个未被选中的章节
                selected_count = 0
                for i in range(total_items):
                    if i not in currently_selected:
                        chapter_listbox.selection_set(i)
                        selected_count += 1
                        if selected_count >= 10:
                            break
                
                if selected_count == 0:
                    messagebox.showinfo("提示", "所有章节都已被选中")
                else:
                    pass
                    # messagebox.showinfo("成功", f"已选择 {selected_count} 个章节")
            
            # 清除所有选择按钮功能
            def clear_all_selections():
                chapter_listbox.selection_clear(0, tk.END)
                messagebox.showinfo("成功", "已清除所有选择")
            
            # 倒序按钮功能 - 重新编号章节序号
            def reverse_order():
                # 获取当前所有项目
                total_items = chapter_listbox.size()
                if total_items == 0:
                    messagebox.showinfo("提示", "请先分解章节")
                    return
                
                # 获取当前选中的项目
                currently_selected = set(chapter_listbox.curselection())
                
                # 获取所有项目内容（提取原始标题，去掉序号）
                items = []
                for i in range(total_items):
                    item_text = chapter_listbox.get(i)
                    # 分离序号和标题（格式为：序号_标题）
                    if "_" in item_text:
                        original_title = item_text.split("_", 1)[1]  # 获取标题部分
                    else:
                        original_title = item_text
                    items.append(original_title)
                
                # 清空列表并重新添加（倒序编号）
                chapter_listbox.delete(0, tk.END)
                for i, title in enumerate(reversed(items)):
                    new_chapter_num = total_items - i  # 倒序编号
                    chapter_listbox.insert(tk.END, f"{new_chapter_num}_{title}")
                
                # 恢复选中的项目（需要转换索引）
                if currently_selected:
                    new_selected = set()
                    for old_index in currently_selected:
                        # 倒序转换索引
                        new_index = total_items - 1 - old_index
                        new_selected.add(new_index)
                    
                    # 清除所有选择并重新选择
                    chapter_listbox.selection_clear(0, tk.END)
                    for new_index in new_selected:
                        chapter_listbox.selection_set(new_index)
                
                messagebox.showinfo("成功", "章节序号已倒序重排")
            
            # 按钮容器
            button_container = ttk.Frame(list_frame)
            button_container.pack(fill=tk.X, pady=5)
            
            ttk.Button(button_container, text="分解章节", command=parse_chapters).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_container, text="追加十章", command=select_next_ten).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_container, text="倒序", command=reverse_order).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_container, text="清除所有", command=clear_all_selections).pack(side=tk.RIGHT, padx=5)
            
            # 保存路径区域
            save_frame = ttk.LabelFrame(import_dialog, text="章节保存路径", padding="10")
            save_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Label(save_frame, text="保存路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
            save_path_var = tk.StringVar(value=self.novels_folder_var.get())
            save_path_entry = ttk.Entry(save_frame, textvariable=save_path_var, width=50)
            save_path_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
            
            # 文件夹浏览按钮
            def browse_save_folder():
                from tkinter import filedialog
                folder_path = filedialog.askdirectory(title="选择章节保存文件夹")
                if folder_path:
                    save_path_var.set(folder_path)
            
            ttk.Button(save_frame, text="浏览", command=browse_save_folder).grid(row=0, column=2, padx=5, pady=5)
            save_frame.columnconfigure(1, weight=1)
            
            # 按钮区域
            button_frame = ttk.Frame(import_dialog)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            # 导入全部按钮
            def import_all():
                file_path = txt_file_var.get()
                if not file_path or not os.path.exists(file_path):
                    messagebox.showerror("错误", "请选择有效的TXT文件")
                    return
                
                save_path = save_path_var.get()
                if not save_path:
                    messagebox.showerror("错误", "请选择保存路径")
                    return
                
                try:
                    # 确保目录存在
                    os.makedirs(save_path, exist_ok=True)
                    
                    # 使用现有的create_chapter_files_in_files方法，但修改输出路径
                    if not self.create_chapter_files_in_files_custom(file_path, save_path):
                        messagebox.showerror("错误", "导入章节失败")
                        return
                    
                    # 更新主界面的小说文件夹路径
                    self.novels_folder_var.set(save_path)
                    self.update_chapter_count()
                    
                    messagebox.showinfo("成功", f"成功导入全部章节到: {save_path}")
                    import_dialog.destroy()
                    
                except Exception as e:
                    messagebox.showerror("错误", f"导入失败: {str(e)}")
            
            # 追加导入按钮
            def import_selected():
                file_path = txt_file_var.get()
                if not file_path or not os.path.exists(file_path):
                    messagebox.showerror("错误", "请选择有效的TXT文件")
                    return
                
                save_path = save_path_var.get()
                if not save_path:
                    messagebox.showerror("错误", "请选择保存路径")
                    return
                
                selected_indices = chapter_listbox.curselection()
                if not selected_indices:
                    messagebox.showerror("错误", "请选择要导入的章节")
                    return
                
                try:
                    # 确保目录存在
                    os.makedirs(save_path, exist_ok=True)
                    
                    # 获取当前文件夹中最大的章节号
                    max_chapter_num = 0
                    if os.path.exists(save_path):
                        for f in os.listdir(save_path):
                            if f.startswith('Chapter_') and f.endswith('.md'):
                                match = re.search(r'Chapter_(\d+)\.md', f)
                                if match:
                                    num = int(match.group(1))
                                    if num > max_chapter_num:
                                        max_chapter_num = num
                    
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 使用正则表达式分解章节
                    chapter_pattern = re.compile(r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[:：\s]+.*$)', re.MULTILINE)
                    parts = chapter_pattern.split(content)
                    
                    if len(parts) <= 1:
                        messagebox.showerror("错误", "未找到任何章节")
                        return
                    
                    # 解析章节
                    chapters = []
                    for i in range(1, len(parts), 2):
                        title = parts[i].strip()
                        if i + 1 < len(parts):
                            chapter_content = parts[i + 1].strip()
                            chapters.append({"title": title, "content": chapter_content})
                    
                    # 获取选中的章节（倒序索引转换）
                    selected_chapters = []
                    total_chapters = len(chapters)
                    for idx in sorted(selected_indices, reverse=True):
                        # 列表是倒序的，需要转换索引
                        actual_idx = total_chapters - 1 - idx
                        if 0 <= actual_idx < total_chapters:
                            selected_chapters.append(chapters[actual_idx])
                    
                    # 创建选中的章节文件
                    for i, chapter in enumerate(selected_chapters):
                        try:
                            chapter_number = max_chapter_num + i + 1
                            title = str(chapter['title'])
                            if title.find('：') == -1:      
                                c_index = title.find('章') + 1
                                if c_index < len(title) and title[c_index] in [':', ' ']:
                                    title = title[:c_index] + '：' + title[c_index + 1:]
                            title = title.replace(' ', '')
                            file_name = f"Chapter_{chapter_number:03d}.md"
                            file_path = os.path.join(save_path, file_name)
                            
                            with open(file_path, 'w', encoding='utf-8') as chapter_file:
                                chapter_file.write(f"# {title}\n\n")
                                chapter_file.write(chapter['content'])
                        except Exception as e:
                            messagebox.showerror("错误", f"创建章节 {chapter_number} 失败: {str(e)}")
                            return False
                    
                    # 更新主界面的小说文件夹路径
                    self.novels_folder_var.set(save_path)
                    self.update_chapter_count()
                    
                    messagebox.showinfo("成功", f"成功导入 {len(selected_chapters)} 个章节到: {save_path}")
                    import_dialog.destroy()
                    
                except Exception as e:
                    messagebox.showerror("错误", f"导入失败: {str(e)}")
            
            
            ttk.Button(button_frame, text="导入全部", command=import_all).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="追加导入", command=import_selected).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消", command=import_dialog.destroy).pack(side=tk.RIGHT, padx=5)
            
        except Exception as e:
            messagebox.showerror("错误", f"打开导入对话框失败: {str(e)}")

    def create_chapter_files_in_files_custom(self, novel_file_path: str, custom_output_dir: str):
        """从文件中分解生成章节文件到指定目录"""
        return _cf_create_custom(novel_file_path, custom_output_dir)

    def open_manual_browser(self, event=None):
        """打开手动浏览器，持续等待用户操作"""
        try:
            custom_browser_path = self.custom_browser_path_var.get()
            site_url = self._get_site_url()
            print("正在打开手动浏览器...")
            print("浏览器将保持打开状态，您可以进行手动操作")
            print("需要关闭时，请直接关闭浏览器窗口")
            # 在新线程中运行浏览器，避免阻塞主界面
            def run_manual_browser():
                try:
                    with sync_playwright() as p:
                        browser, context = self._normal_open_browser(p, custom_browser_path, False)
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
            
            # 启动浏览器线程
            browser_thread = threading.Thread(target=run_manual_browser, daemon=True)
            browser_thread.start()
        except Exception as e:
            messagebox.showerror("错误", f"打开手动浏览器失败: {e}")

    @staticmethod
    def create_chapter_files_in_files(novel_file_path: str):
        """从文件中分解生成章节文件"""
        return _cf_create_in_files(novel_file_path)

    @staticmethod
    def get_chapter_files_in_range(novels_folder: str, start_chapter: int, end_chapter: int) -> List[str]:
        """获取指定范围的章节文件路径列表"""
        return _cf_get_range(novels_folder, start_chapter, end_chapter)

    def get_chapter_details(self, filepath: str) -> Tuple[str, str, str, str]:
        """从.md文件中提取章节序号、标题和内容。"""
        return _cf_get_details(filepath, self.neat_index_var.get())

    def publish_single_chapter_on_fanqienovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str, retry_times: int = 3):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        chapter_content = chapter_content.replace("\n\n", "\n").replace("\n\n", "\n") # 替换多个换行符为单换行符
        writer_said_content = chapter_details[3]
        if writer_said_content is not None and writer_said_content.strip() != '':
            print(f"章节 {chapter_num} 包含作者说!")
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if len(chapter_content.strip()) < 3:
            print("章节名字数不足3个字符，终止发布，请检查章节文件，可使用快捷键Ctrl+M打开当前章节")
            return False
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False

        publish_page = None
        try:
            if publish_mode == '修改章节':
                try:
                    try:
                        page.get_by_role("button", name="我知道了").click(timeout=1000, force=True)
                    except:
                        pass
                    try:
                        page.get_by_text("搜索章节").first.click(timeout=3000, force=True)
                    except:
                        self.debug()
                    page.get_by_placeholder("输入章节名称或章节号").fill(chapter_num, timeout=3000)
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state('domcontentloaded')
                    match_chapter_count = page.get_by_text(f"第{chapter_num}章").count()
                    print(f"搜索到的章节数: {int(match_chapter_count)}")
                    if match_chapter_count == 0:
                        page.click('div.arco-modal-wrapper.arco-modal-wrapper-align-center > div > span')
                        return False
                    else:
                        try:
                            page.click("div.arco-modal-wrapper.arco-modal-wrapper-align-center > div > div.arco-modal-content > div.chapter-search-result > div > div > div > div > div > div > div.arco-table-body > table > tbody > tr > td:nth-child(5) > div > span > span > a > span", timeout=3000, force=True)
                            page.wait_for_timeout(2000)
                            page.wait_for_load_state('domcontentloaded')
                        except:
                            self.debug()
                        try:
                            page.get_by_text("我知道了", exact=True).click(timeout=1500, force=True)
                        except:
                            pass
                        page.get_by_placeholder("请输入标题").fill(chapter_title.strip()[:24], timeout=3000)
                        page.locator('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror').fill(chapter_content, timeout=3000)
                        while not page.get_by_role("button", name="确认发布").is_visible(timeout=3000):
                            page.get_by_role("button", name="下一步").click(timeout=3000, force=True)
                            try:
                                page.get_by_role("button", name="仅基础检测").click(timeout=1500)
                                print("基础风险预检")
                                page.wait_for_timeout(1000)
                            except Exception:
                                pass
                            try:
                                page.get_by_role("button", name="提交").click(timeout=1500)
                            except Exception:
                                pass
                            try:
                                page.get_by_role("button", name="提交").click(timeout=1500)
                            except Exception:
                                pass
                            page.wait_for_timeout(3000)
                        # 聚焦到"button", name="确认发布"
                        page.get_by_role("button", name="确认发布").click(timeout=3000, force=True)
                        try:
                            page.click('div.card-content-line-control > div > label:nth-child(2)', timeout=3000)
                        except Exception:
                            self.debug()
                        page.get_by_role("button", name="确认发布").click(timeout=3000, force=True)
                        print(f"--- 第{chapter_num}章修改成功！---")
                        page.wait_for_timeout(1500)  # 等待一下，确保操作完成
                        page.reload(timeout=3000)
                        page.wait_for_load_state('domcontentloaded')
                        return True
                except:
                    traceback.print_exc()
                    print(f"--- 第{chapter_num}章修改失败！---")
                    return False
            else:
                try:
                    page.get_by_role("button", name="我知道了").click(timeout=1000, force=True)
                except:
                    pass
                max_attempts = 5
                attempt_count = 0
                while not page.get_by_role("button", name="新建章节").is_visible(timeout=5000):
                    attempt_count += 1
                    if attempt_count >= max_attempts:
                        print("新建章节按钮未出现，最大尝试次数已超过。")
                        return False
                    page.reload(timeout=3000)
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state('load')
            publish_page = None
            while publish_page is None:
                try:
                    page.get_by_role("button", name="新建章节").click(timeout=5000)
                    with context.expect_page(timeout=5000) as new_page_info:
                        publish_page = new_page_info.value
                        MAX_REPEAT = 3
                        while MAX_REPEAT > 0:
                            MAX_REPEAT -= 1
                            try:
                                publish_page.wait_for_load_state('networkidle', timeout=10000)
                            except:
                                print(f"发布页面加载超时重试，剩余{MAX_REPEAT}次")
                                publish_page.reload(timeout=3000)
                        publish_page.wait_for_load_state('domcontentloaded', timeout=10000)
                        print("已切换到新的发布页面。")
                except:
                    print("打开发布页面失败。")
                    page.reload(timeout=3000)
                    page.wait_for_load_state('domcontentloaded', timeout=10000)
                    publish_page = None
                    
            # --- 在新页面上执行操作 ---
            # 预先点击去除新手引导
            publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=3000, force=True)  
            # publish_page.click('body')
            print(f"填写章节序号: {chapter_num}")
            publish_page.wait_for_selector('span.left-input > input', timeout=5000)
            publish_page.fill('span.left-input > input', chapter_num.strip(), timeout=3000)

            print(f"填写章节标题: {chapter_title[:24]}")
            publish_page.get_by_placeholder("请输入标题").fill(chapter_title.strip()[:24], timeout=3000)

            print("粘贴章节正文...")
            edit_path = '#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > ' \
                        'div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror'

            publish_page.wait_for_selector(edit_path, timeout=10000)
            publish_page.fill(edit_path, chapter_content)
            publish_page.wait_for_timeout(5000)

            if writer_said_content is not None and writer_said_content.strip() != '':
                if self.count_chinese_characters(writer_said_content.strip()) > 300:
                    messagebox.showerror("错误", f"章节 {chapter_num} 作者说内容超过300个中文字符，无法发布！")
                    return False
                print("填写作者说...")
                publish_page.locator('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.author-speak-empty > div > div.author-speak-empty-btn > div.author-speak-empty-btn-content').hover(timeout=3000)
                publish_page.get_by_text("添加图文", exact=True).click(timeout=3000)
                publish_page.wait_for_selector('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.author-speak > div.author-speak-input > div.syl-editor > div').fill(writer_said_content.strip(), timeout=3000)
                publish_page.get_by_role("button", name="保存", exact=True).click(timeout=3000)

            if publish_mode == '保存为草稿':
                print("保存为草稿...")
                publish_page.get_by_role("button", name="存草稿").click(timeout=3000)
            else:
                print("点击'下一步'进行发布...")
                publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=3000)

                # 处理发布确认弹窗
                print("处理发布确认弹窗...")
                try_times = 5
                while not (publish_page.get_by_role("button", name="确认发布").is_visible(timeout=3000) or publish_page.get_by_role("button", name="确认提交").is_visible(timeout=3000)) and try_times > 0:
                    try:
                        publish_page.get_by_role("button", name="提交").click(timeout=1500)
                    except Exception:
                        pass
                    try:
                        publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1000)
                    except Exception:
                        pass
                    try:
                        if not self.danger_pre_check_var.get():
                            publish_page.get_by_role("button", name="仅基础检测").click(timeout=1500)
                            print("基础风险预检")
                            publish_page.wait_for_timeout(1000)
                        else:
                            publish_page.get_by_role("button", name="全面检测").click(timeout=1500)
                            print("全面风险预检")
                            publish_page.wait_for_timeout(3000)
                            top_message = publish_page.wait_for_selector("span.arco-message-content", timeout=10000)
                            msg = top_message.inner_text()
                            print(msg)
                            if "暂无风险" in msg:
                                pass
                            else:
                                if not self.keep_browser_open_var.get():
                                    print("当前章节可能存在风险内容，请手动修改，修改完成后按Ctrl+K继续发布后续")
                                    self.wait_event.wait()
                                else:
                                    print("当前章节可能存在风险内容，结束发布")
                                    return False
                            try:
                                publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=1500)
                            except Exception:
                                pass
                        try:
                            publish_page.get_by_role("button", name="提交").click(timeout=1500)
                        except Exception:
                            pass
                        try:
                            publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1000)
                        except Exception:
                            pass
                    except Exception:
                        try:
                            # publish_page.wait_for_timeout(5000)
                            # self.debug()
                            try_times -= 1
                            print(f"重新填写章节序号: {chapter_num}")
                            publish_page.wait_for_selector('span.left-input > input', timeout=5000)
                            publish_page.fill('span.left-input > input', chapter_num.strip())

                            print(f"重新填写章节标题: {chapter_title}")
                            publish_page.get_by_placeholder("请输入标题").fill(chapter_title.strip())

                            print("重新粘贴章节正文...")
                            edit_path = '#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > ' \
                                        'div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror'

                            publish_page.wait_for_selector(edit_path, timeout=10000)
                            publish_page.fill(edit_path, chapter_content)
                            publish_page.fill('span.left-input > input', chapter_num.strip())
                            # 点击“确认发布”按钮
                            publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=1500)
                        except Exception:
                            # 所有操作失败时，短暂等待后继续循环
                            publish_page.wait_for_timeout(500)   
                            continue
                            
                print("发布设置...AI-默认否")
                # 选择“否”单选框
                publish_page.wait_for_selector('div.card-content-line-control > div > label:nth-child(2)', timeout=5000).click()
                # publish_page.get_by_role("radiogroup").get_by_role("radio", name="否").check()

                if publish_mode == '定时发布':
                    # 勾选定时发布
                    publish_page.click('div > div.card-content-line-control > div > button', timeout=3000)
                    # publish_page.get_by_role("button", name="定时发布").click()

                    print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M'))
                    try:
                        publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1500)
                    except Exception:
                        pass
                    # 使用 get_by_placeholder 来定位输入框，并确保先清空再填写
                    date_input = publish_page.get_by_placeholder("请选择日期")
                    date_input_value = self.publish_time.strftime('%Y-%m-%d')
                    while date_input.input_value() != date_input_value:
                        date_input.clear(timeout=3000)
                        date_input.fill(date_input_value, timeout=3000)
                        date_input.press("Enter", timeout=3000)
                        try:
                            publish_page.get_by_text("今天").last.click(timeout=1500)
                        except Exception:
                            pass
                        publish_page.wait_for_timeout(1000)

                    time_input = publish_page.get_by_placeholder("请选择时间")
                    time_input_value = self.publish_time.strftime('%H:%M')
                    while time_input.input_value() != time_input_value:
                        time_input.clear(timeout=3000)
                        time_input.fill(time_input_value, timeout=3000)
                        time_input.press("Enter", timeout=3000)
                        try:
                            publish_page.get_by_text("此刻").last.click(timeout=1500)
                        except Exception:
                            pass
                        publish_page.wait_for_timeout(1000)

                # 点击确认发布按钮
                chapter_details_new = list(chapter_details)
                try_times = 0
                while True:
                    try:
                        if self.stop_publish_sign:
                            print("已检测到手动终止发布！！")
                            self.stop_publish_sign = False
                            return False
                        try:
                            publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1500)
                        except Exception:
                            pass  
                        publish_button = publish_page.get_by_role("button", name="确认发布") if publish_page.get_by_role("button", name="确认发布").is_visible(timeout=3000) else publish_page.get_by_role("button", name="确认提交")
                        publish_button.click(timeout=3000)
                    except Exception:
                        pass
                    try:
                        top_message = publish_page.wait_for_selector("span.arco-message-content", timeout=3000)
                        if top_message.is_visible():
                            msg = top_message.inner_text()
                            print(msg)
                        if '重复标题' in msg:
                            print("重复标题，添加章节序号")
                            chapter_details_new[1] = f"{chapter_title}/{chapter_num}"           
                        if '大段落重复' in msg:
                            chapter_details_new[2] = self.check_repeat_content(chapter_content)
                        if '更新作品数超出每日上限' in msg:
                            print("更新作品数超出每日上限，直接退出")
                            return False
                    except Exception:
                        print("未检测到网站消息")

                    if "chapter-manage" in publish_page.url:
                        print("发布成功") 
                        page.reload(timeout=3000)
                        break 
                    
                    try_times += 1
                    # self.debug()
                    if try_times >= 2:
                        publish_page.close()
                        retry_times -= 1
                        if retry_times <= 0:
                            return False
                        else:
                            print(f"重试发布第{chapter_num}章，剩余重试次数: {retry_times}")
                            return self.publish_single_chapter_on_fanqienovel(publish_mode, context, page, chapter_details_new, novel_title, retry_times)                        
            
            print(f"--- 第{chapter_num}章发布成功！---")
            publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def publish_single_chapter_on_qidiannovel(self, publish_mode: str, context: BrowserContext, write_button, chapter_details: tuple):
        """发布单个章节"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False
        try:
            # --- 在新页面上执行操作 ---
            write_button.click(timeout=3000)
            publish_page = None
            with context.expect_page() as new_page_info:
                publish_page = new_page_info.value
                publish_page.wait_for_load_state('networkidle')
                print("已切换到发布页面。")
            while not publish_page.is_visible('#chapter-body > div > div.chapter-content > div.chapter-content-placeholder', timeout=5000):
                try:
                    publish_page.click('#root > div.write-tabs.ne-sidebar.ne-sidebar-status > div.ne-sidebar-tool > a', timeout=1000)
                    print("创建章节成功")
                    publish_page.wait_for_timeout(500) 
                except:
                    publish_page.click('#root > div.write-tabs.ne-sidebar.ne-sidebar-status > div.side-coll-btn > span', timeout=1000)
                    publish_page.wait_for_timeout(500) 

            print(f"填写章节序号和标题——第{chapter_num}章：{chapter_title}")
            title_input = publish_page.get_by_placeholder("请输入章节号与章节名。示例：“第十章 天降奇缘”")
            title_input.fill(f"第{chapter_num}章：{chapter_title}")

            print("粘贴章节正文...")
            try:
                # 方法1：使用XPath定位并填充内容
                tinymce_body = publish_page.wait_for_selector('#chapter-body > div > div.chapter-content > div.chapter-content-placeholder', timeout=5000)
                
                if tinymce_body:
                    # 点击编辑器区域使其获得焦点
                    tinymce_body.click()
                    publish_page.wait_for_timeout(500)
                    
                    # 清空现有内容
                    publish_page.keyboard.press("Control+A")
                    publish_page.keyboard.press("Delete")
                    publish_page.wait_for_timeout(300)
                    
                    # 输入新内容
                    publish_page.keyboard.type(chapter_content)
                    publish_page.wait_for_timeout(500)
                    
                    print("成功填入章节内容")
                else:
                    print("未找到TinyMCE编辑器")
                    
            except Exception as e:
                print(f"填入章节内容时出错: {e}")
                return False

            if publish_mode == '保存为草稿':
                print("保存为草稿...")
                publish_page.get_by_role("button", name="保存").click()
            else:
                print("点击'发布'进行发布...")
                publish_page.get_by_role("button", name="发布").click()
                publish_page.wait_for_timeout(3000)
                print("发布设置...")
                if publish_mode == '定时发布':
                    # 勾选定时发布
                    publish_page.click('body > div.publish-form-dialog.nu_dialog_wrap._middle._open > div > div.ui-dialog-body > form > ul > li:nth-child(6) > div > div > label', timeout=3000)
                    # publish_page.get_by_role("button", name="定时发布").click()
                    print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M'))
                    # 先选择时间，不然不允许点击日期
                    time_input_value = self.publish_time.strftime('%H:%M')
                    # time_button = publish_page.query_selector(f'a.ui-time-item[data-time="{time_input_value}"][role="button"]')
                    time_button = publish_page.query_selector(f'//a[@class="publish-set-time" and @role="button" and text()="{time_input_value}"]')
                    if time_button:
                        time_button.click()
                        print(f"成功选择常用时间: {time_input_value}")
                    else:
                        # 测试困难 -- 正确性未知
                        # 如果时间按钮不可见，点击时间输入框展开选择器
                        while not publish_page.is_visible('span.ui-input.ui-time-input.active'):
                            try:
                                publish_page.click('span.ui-input.ui-time-input')
                                publish_page.wait_for_timeout(500)
                            except:
                                publish_page.wait_for_timeout(500)
                        
                        # 选择小时
                        hour_value = time_input_value.split(":")[0]
                        hour_element = publish_page.query_selector(f'div.ui-time-picker a.ui-time-item[data-type="hour"][role="button"]:has-text("{hour_value}")')
                        if hour_element and hour_element.is_visible():
                            hour_element.click()
                            publish_page.wait_for_timeout(300)
                        else:
                            print(f"未找到小时元素: {hour_value}")
                            return False
                            
                        # 选择分钟
                        minute_value = time_input_value.split(":")[1]
                        minute_element = publish_page.query_selector(f'div.ui-time-picker a.ui-time-item[data-type="minute"][role="button"]:has-text("{minute_value}")')
                        if minute_element and minute_element.is_visible():
                            minute_element.click()
                            publish_page.wait_for_timeout(300)
                        else:
                            print(f"未找到分钟元素: {minute_value}")
                            return False

                    while not publish_page.is_visible('span.ui-input.ui-date-input.active'):
                        try:
                            publish_page.click("span.ui-input.ui-date-input", timeout=2000)
                            publish_page.wait_for_timeout(500)
                        except:
                            publish_page.wait_for_timeout(500)
                    month_text = publish_page.query_selector('div.ui-date-head > a.ui-date-switch').inner_text()
                    while month_text != self.publish_time.strftime('%Y-%m'):
                        publish_page.click('div > div.ui-date-head > a.ui-date-next') # 目前只能选择下个月
                        publish_page.wait_for_timeout(500)
                        month_text = publish_page.query_selector('div.ui-date-head > a.ui-date-switch').inner_text()

                    date_input_value = self.publish_time.strftime('%Y-%m-%d')
                    day_number = self.publish_time.day
                    date_element = publish_page.query_selector(f'a.ui-date-item:has-text("{day_number}")')

                    if date_element:
                        try:
                            date_element.click(timeout=1000)
                        except:
                            print("无法点击")
                        print(f"成功选择日期: {date_input_value}")
                    else:
                        print(f"未找到日期元素: {date_input_value}")

                    publish_page.get_by_role("button", name="定时发布").click()

                # 点击确认发布按钮
                else:
                    publish_page.get_by_role("button", name="确认发布").click()

            print(f"--- 第{chapter_num}章发布成功！---")
            publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def publish_single_chapter_on_qimaonovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, add_var: int):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False
        
        publish_page = page # 七猫发布页面不会弹窗
        try:
            # 使用更稳定的方式查找小说并点击更新
            print(f"填写章节序号: {chapter_num} - 七猫有默认序号")

            print(f"填写章节标题: {chapter_title}")
            publish_page.get_by_placeholder("请输入章节名称，最多20个字").fill(chapter_title.strip())

            print("粘贴章节正文...")
            edit_path = 'div.chapter-editor > div > div > div.q-contenteditable.book.font-size-16.edit-mask'
            # 'div.chapter-editor > div > div'

            publish_page.wait_for_selector(edit_path, timeout=10000)
            publish_page.fill(edit_path, chapter_content)

            if publish_mode == '保存为草稿':
                print("保存为草稿...")
                publish_page.get_by_role("button", name="存为草稿").click()
            else:
                pulish_button = None
                # add_var = int(self.daily_publish_num_var.get()) - daily_publish_num - 1
                # 七猫不允许同时定时发布，要求一定要晚一点
                while not pulish_button:
                    try:
                        if publish_mode == '定时发布':
                            # 勾选定时发布
                            # publish_page.click('div > div.card-content-line-control > div > button', timeout=3000)
                            publish_page.get_by_text("定时发布").click()
                            publish_page.wait_for_timeout(1500)
                            print("获取确认发布按钮...")
                            # 使用更可靠的选择器，避免绝对路径
                            pulish_button = publish_page.query_selector('div.el-dialog__wrapper.qm-pop div.qm-pop-tf.show-mask > a, div.el-dialog__wrapper.qm-pop div.qm-pop-tf > a, .qm-pop-tf.show-mask > a, .qm-pop-tf > a')
                            if not pulish_button:
                                print(f"尝试其他方法1")
                                pulish_button = publish_page.get_by_text("确认发布", timeout=2000)
                            
                            # 如果还找不到，尝试更通用的选择器
                            if not pulish_button:
                                print(f"尝试其他方法2")
                                pulish_button = publish_page.query_selector('div[class*="qm-pop"] a, div[class*="el-dialog__body"] a')
                            # pulish_button = publish_page.get_by_text('确认发布', timeout=1500)
                            print(f"成功获取发布按钮")
                            date_input = publish_page.get_by_placeholder("选择日期")
                            date_input_value = self.publish_time.strftime('%Y-%m-%d')
                            print(f"发布日期: {date_input_value}")
                            while date_input.input_value() != date_input_value:
                                date_input.clear()
                                date_input.fill(date_input_value)
                                date_input.press("Enter")
                                publish_page.wait_for_timeout(1000)
                        
                            # 七猫也有常用时间设计
                            # 七猫不允许同时定时发布，要求一定要晚一点
                            if add_var > 0:
                                new_publish_time = self.publish_time + datetime.timedelta(minutes=add_var)
                            else:
                                new_publish_time = self.publish_time
                            time_input_value = new_publish_time.strftime('%H:%M')
                            print(f"发布时间: {time_input_value}")
                            print(f"Ps.七猫不允许同时定时发布，要求一定要晚于上一章发布时间")
                            # time_button = publish_page.query_selector(f'a.ui-time-item[data-time="{time_input_value}"][role="button"]')
                            time_button = publish_page.get_by_text(time_input_value).first
                            if time_button:
                                time_button.click()
                                print(f"成功选择常用时间: {time_input_value}")
                            else:
                                print(f"未找到常用时间元素: {time_input_value}")
                                return False
                                # 测试困难 -- 正确性未知
                                # 选择小时
                                hour_value = time_input_value.split(":")[0]
                                publish_page.get_by_placeholder("小时").click()
                                hour_element = publish_page.query_selector(f'//li[contains(@class, "el-select-dropdown__item") and .//span[text()="{hour_value}"]]')        
                                if hour_element and hour_element.is_visible():
                                    hour_element.click()
                                    publish_page.wait_for_timeout(300)
                                else:
                                    print(f"未找到小时元素: {hour_value}")
                                    return False
                                    
                                # 选择分钟
                                minute_value = time_input_value.split(":")[1]
                                publish_page.query_selector('分钟').click()
                                minute_element = publish_page.query_selector(f'//li[contains(@class, "el-select-dropdown__item") and .//span[text()="{minute_value}"]]')
                                if minute_element and minute_element.is_visible():
                                    minute_element.click()
                                    publish_page.wait_for_timeout(300)
                                else:
                                    print(f"未找到分钟元素: {minute_value}")
                                    return False
                        else:
                            publish_page.get_by_text("立即发布").click()
                            publish_page.wait_for_timeout(1500)
                            print("获取确认发布按钮...")
                            # 使用更可靠的选择器，避免绝对路径
                            pulish_button = publish_page.query_selector('body > div.el-dialog__wrapper.qm-pop.w-480.timing-upload-dialog > div > div.el-dialog__body > div.qm-pop-tf > a')
                            if not pulish_button:
                                print(f"尝试其他方法1")
                                pulish_button = publish_page.get_by_text("确认发布", timeout=2000)
                            
                            # 如果还找不到，尝试更通用的选择器
                            if not pulish_button:
                                print(f"尝试其他方法2")
                                pulish_button = publish_page.query_selector('div[class*="qm-pop"] a, div[class*="el-dialog__body"] a')
                            # pulish_button = publish_page.get_by_text('确认发布', timeout=1500)
                            print(f"成功获取发布按钮")
                    except:
                        if pulish_button is None:
                            # try:
                            #     _button = input("输入发布按钮元素")
                            #     pulish_button = publish_page.query_selector(_button, timeout=1500)
                            # except:
                            #     publish_page.wait_for_timeout(500)
                            publish_page.get_by_placeholder("请输入章节名称，最多20个字").fill(chapter_title.strip())
                            print("重新粘贴章节正文...")
                            edit_path = 'div.chapter-editor > div > div > div.q-contenteditable.book.font-size-16.edit-mask'
                            # 'div.chapter-editor > div > div'
                            publish_page.wait_for_selector(edit_path, timeout=10000)
                            publish_page.fill(edit_path, chapter_content)
                            publish_page.wait_for_timeout(3000)
                            print("重新尝试发布")
                
                # 点击确认发布按钮
                pulish_button.click()
                publish_page.wait_for_timeout(5000)
                if add_var == 0:
                    try:
                        # 需要点击已阅读并同意协议
                        has_read_button = publish_page.query_selector('div.el-dialog__wrapper.qm-pop.first-upload-dialog div.qm-pop-tf > a, div.first-upload-dialog div.qm-pop-tf > a, .first-upload-dialog .qm-pop-tf > a')
                        if has_read_button:
                            has_read_button.click(timeout=3000)
                        else:
                            # 尝试通过文本内容查找
                            has_read_button = publish_page.get_by_text("已阅读并同意协议").first
                        if has_read_button:
                            has_read_button.click(timeout=3000)
                    except:
                        pass

            print(f"--- 第{chapter_num}章发布成功！---")
            publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成
            try:
                publish_page.get_by_text("我知道了").click(timeout=1500)
            except:
                pass
                # self.debug()

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            # if publish_page:
            #     print("关闭章节发布页面...")
            #     publish_page.close()
            return True

    def publish_single_chapter_on_feilunovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, daily_publish_num: int):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        print('飞卢暂不支持定时发布')
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False
        publish_page = page
        try:
            # 使用更稳定的方式查找小说并点击更新
            print("先分卷")
            publish_page.locator("#nodeForm > div.nodeFormRegion > div:nth-child(1) > div > select").select_option("2")
            # publish_page.locator("#nodeForm > div.nodeFormRegion > div:nth-child(1) > div > select > option:nth-child(2)").click() 
            print("填写章节标题...")
            publish_page.get_by_placeholder("请填写标题").fill(f"第{chapter_num}章 {chapter_title.strip()}")
            print("粘贴章节正文...")
            publish_page.get_by_placeholder("注：章节内容里请不要含章节标题").fill(chapter_content)
            print("添加小说章节...")
            publish_page.get_by_role("button", name="添加小说章节").click()
            publish_page.wait_for_timeout(3000)
            print(f"--- 第{chapter_num}章发布成功！---")
            publish_page.get_by_text("继续添新").click(timeout=3000)
            publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            # if publish_page:
            #     print("关闭章节发布页面...")
            #     publish_page.close()
            return True

    def publish_single_chapter_on_wechatnovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False
        page.wait_for_selector('#app > div.main_bd_new > div:nth-child(3) > div.weui-desktop-panel__bd > div > div:nth-child(2)', timeout=3000).click(timeout=3000)
        publish_page = None
        with context.expect_page() as new_page_info:
            publish_page = new_page_info.value
            publish_page.wait_for_load_state('networkidle')
        novel_writer = self.config.get('Novel', 'novel_writer', fallback=None)
        is_reward = self.config.get('Settings', 'reward', fallback=False)
        print(f"填写章节标题...")
        publish_page.get_by_placeholder("请在这里输入标题").fill(f"第{chapter_num}章：{chapter_title.strip()}")
        if novel_writer:
            publish_page.get_by_placeholder("请输入作者").fill(novel_writer)
        print(f"填写正文...")
        publish_page.locator('#ueditor_0 > div > div > div > div').fill(chapter_content)
        print(f"使用默认封面...")
        publish_page.locator('#js_cover_area > div.select-cover__btn.js_cover_btn_area.select-cover__mask').hover()
        publish_page.get_by_text('从图片库选择').last.click(timeout=3000)
        publish_page.locator('#js_image_dialog_list_wrp > div > div:nth-child(1)').click(timeout=3000)
        # publish_page.get_by_text('下一步').last.click(timeout=3000)
        # publish_page.get_by_text('确认').last.click(timeout=3000)
        publish_page.get_by_role('button', name='下一步').last.click(timeout=3000)
        publish_page.get_by_role('button', name='确认').last.click(timeout=3000)
        publish_page.wait_for_timeout(3000)
        if novel_writer:
            try:
                publish_page.locator('#js_original > div:nth-child(1) > div.setting-group__switch.js_original_apply.js_edit_ori > div').click(timeout=3000)
                is_checked = publish_page.locator('#vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i').is_checked()
                if not is_checked:
                    publish_page.locator('#vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i').click(timeout=3000)
                publish_page.get_by_role('button', name='确定').last.click(timeout=3000)
            except:
                print("声明原创失败")
                publish_page.get_by_role('button', name='取消').last.click(timeout=3000)
        if is_reward:
            try:
                # 赞赏设置
                publish_page.locator('#js_reward_setting_area > div > div.setting-group__switch.js_reward_open > span').click(timeout=3000)
                publish_page.wait_for_timeout(1500)
                publish_page.get_by_role('button', name='确定').last.click(timeout=3000)
            except:
                print("赞赏设置失败")
                print('建议先手动设置一次赞赏，再运行脚本')
                publish_page.get_by_role('button', name='取消').last.click(timeout=3000)
        else:
            print("未开启赞赏-内测开启方式config.ini/Settings/reward=True, 需要预先设置一次赞赏")
        publish_page.wait_for_timeout(1500)
        publish_page.locator('#js_article_tags_area > label > div > span').click(timeout=3000)
        publish_page.wait_for_timeout(1500)
        publish_page.get_by_placeholder("请选择合集").click(timeout=3000)
        publish_page.wait_for_timeout(3000)
        publish_page.get_by_text(novel_title).last.click(timeout=3000)
        
        publish_page.locator('#vue_app').get_by_role('button', name='确认').last.click(timeout=3000)
        # publish_page.get_by_text(novel_title).last.click(timeout=3000)
        if publish_mode == '保存为草稿':
            print("保存为草稿...")
            publish_page.get_by_role("button", name="保存为草稿").click(timeout=3000)
        else:
            publish_page.locator('#js_send > button > span').click(timeout=3000)
            try:
                publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td > div.publish_container.mass_send__notify.weui-desktop-form__control-group > div > div.mass-send__timer-wrp > label > div', timeout=3000).click(timeout=3000)
            except:
                print("取消群发失败")
            if publish_mode == '定时发布':
                print('定时发布')
                print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M'))
                if self.publish_time - datetime.datetime.now() > datetime.timedelta(days=7):
                    print("公众号不能定时发布超过一周")
                    return False
                try:
                    publish_page.wait_for_timeout(3000)
                    publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td-setting > div > div > div.mass-send__timer-wrp > label > div').click(timeout=3000)
                except:
                    pass
                try:
                    # publish_page.get_by_text("今天").first.click(timeout=3000)
                    publish_page.wait_for_timeout(1500)
                    publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td-setting > div.mass-send__timer-container > div > div > dl > dt').click(timeout=3000)
                    publish_page.wait_for_timeout(1500)
                    #vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i
                    if self.publish_time - datetime.datetime.now() < datetime.timedelta(days=1):
                        publish_page.locator('#vue_app').get_by_text('明天').first.click(timeout=3000)
                    else:
                        if self.publish_time.year != datetime.datetime.now().year:
                            publish_page.locator('#vue_app').get_by_text(self.publish_time.strftime('%Y年%#m月%#d日')).first.click(timeout=3000)
                        else:
                            publish_page.locator('#vue_app').get_by_text(self.publish_time.strftime('%#m月%#d日')).first.click(timeout=3000)
                    try:
                        publish_page.locator('#vue_app').get_by_role('textbox', name="请选择时间").first.fill(self.publish_time.strftime('%H:%M'), timeout=3000)
                        publish_page.wait_for_timeout(1500)
                        publish_page.click('div.mass-send__timer-container > div > dl:nth-child(3) > dt > i', timeout=3000, force=True)
                    except:
                        print("设置发布时间失败")
                except:
                    print("调试模式已开启，输入q退出")
                    while True:
                        try:
                            command = input("@")
                            if command == 'q':
                                break
                            eval(command)
                        except Exception as e:
                            print(f"error: {e}")
            # 关闭群发
            # publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td > div.publish_container.mass_send__notify.weui-desktop-form__control-group > div > div.mass-send__timer-wrp > label > div').click(timeout=3000)
            publish_page.locator("#vue_app").get_by_role("button", name="发表").click(timeout=3000)
            publish_page.locator("#vue_app").get_by_role("button", name="继续发表").click(timeout=3000)
            publish_page.wait_for_timeout(5000)
            while '/home' not in publish_page.url:
                publish_page.wait_for_timeout(3000)
            publish_page.close()
            return True

    def publish_single_chapter_on_shuqinovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        writer_said_content = chapter_details[3]
        if writer_said_content is not None and writer_said_content.strip() != '':
            print(f"章节 {chapter_num} 包含作者说!")
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False

        publish_page = None
        try: 
            try:
                page.get_by_role('menuitem', name="长篇小说").click(timeout=3000)  # 延长点击超时
                page.wait_for_load_state('domcontentloaded')
            except Exception as e:
                print(f"点击小说列表导航元素时发生错误: {e}")
                # raise  # 重新抛出异常以便上层捕获
            print(f"正在查找小说: '{novel_title}'")
            update_button = None
            try:
                update_button = page.locator('.book-data-info').filter(has=page.locator('.book-name', has_text=novel_title)).get_by_text("创建章节")
            except Exception as e:
                print(f"查找创建章节按钮时发生错误: {e}")
                # raise  # 重新抛出异常以便上层捕获
            if update_button is not None:
                update_button.click(timeout=3000)
                page.wait_for_load_state('load')
            else:
                return False
            try:
                page.get_by_text("我知道了").click(timeout=3000)
            except Exception as e:
                pass

            # while True:
            #     try:
            #         command = input("@")
            #         if command == 'q':
            #             break
            #         eval(command)
            #     except Exception as e:
            #         print(f"error: {e}")
            # --- 在新页面上执行操作 ---
            print(f"填写章节序号: {chapter_num}")
            page.locator('#pcFormMidCol > form > div:nth-child(2) > div:nth-child(1) > div > div > span > div > div > input.ant-input.chapterInputNo').fill(chapter_num.strip(), timeout=3000)

            print(f"填写章节标题: {chapter_title.strip()[:14]}")
            page.get_by_placeholder("请输入标题").fill(chapter_title.strip()[:14], timeout=3000)
            # page.locator('#pcFormMidCol > form > div:nth-child(2) > div:nth-child(1) > div > div > span > div > div > input.ant-input.chapterInputText').fill(chapter_title.strip(), timeout=3000)  
            print("粘贴章节正文...")
            page.locator('#pcFormMidCol > form > div:nth-child(2) > div.ant-row.ant-form-item.itemContent > div > div > span > div > textarea').fill(chapter_content, timeout=3000)
            page.wait_for_timeout(3000)

            if writer_said_content is not None and writer_said_content.strip() != '':        
                if self.count_chinese_characters(writer_said_content.strip()) > 300:
                    messagebox.showerror("错误", f"章节 {chapter_num} 作者说内容超过300个中文字符，无法发布！")
                    return False
                print("填写作者说...")
                page.locator('#pcFormMidCol > form > div:nth-child(2) > div.authorSayBox > div.ant-row.ant-form-item.itemAuthorSay > div > div > span > div > textarea').fill(writer_said_content.strip(), timeout=3000)

            if publish_mode == '保存为草稿':
                print("保存为草稿...")
                page.get_by_text("存为草稿", exact=True).click(timeout=3000)
            else:
                page.get_by_text("发布", exact=True).click(timeout=3000)
                page.wait_for_timeout(3000)
                try:
                    page.get_by_text("提 交", exact=True).click(timeout=3000)
                except Exception as e:
                    pass
                    # while True:
                    #     try:
                    #         command = input("@")
                    #         if command == 'q':
                    #             break
                    #         eval(command)
                    #     except Exception as e:
                    #         print(f"error: {e}")
                page.wait_for_timeout(1500)
                if publish_mode == '定时发布':
                    page.get_by_text("定时发布", exact=True).click(timeout=3000)
                    date_button = page.get_by_placeholder('请选择日期').first
                    date_button.click(timeout=3000)
                    date_input = page.get_by_placeholder('请选择日期').last
                    date_input.fill(self.publish_time.strftime('%Y-%m-%d'), timeout=3000)
                    date_input.press('Enter')
                    time_button = page.get_by_placeholder('请选择时间').first
                    time_button.click(timeout=3000)
                    time_input = page.get_by_placeholder('请选择时间').last
                    time_input.fill(self.publish_time.strftime('%H:%M'), timeout=3000)
                    time_button.click(timeout=3000)
                else:
                    page.get_by_text("立即发布", exact=True).click(timeout=3000)
            try:
                page.get_by_text("确 认", exact=True).click(timeout=3000)
            except Exception as e:
                print(f"确认发布按钮点击时发生错误: {e}")
                while True:
                    try:
                        command = input("@")
                        if command == 'q':
                            break
                        eval(command)
                    except Exception as e:
                        print(f"error: {e}")

            print(f"--- 第{chapter_num}章发布成功！---")
            page.wait_for_timeout(3000)  # 等待一下，确保操作完成

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def publish_single_chapter_on_jinjiangnovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, update_button):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        writer_said_content = chapter_details[3]
        if writer_said_content is not None and writer_said_content.strip() != '':
            print(f"章节 {chapter_num} 包含作者说!")
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False

        publish_page = None
        update_button.click(timeout=3000)
        try:
            with context.expect_page() as new_page_info:
                publish_page = new_page_info.value
                publish_page.wait_for_load_state('networkidle')
                print("已切换到新的发布页面。")
            # print(publish_page.url)
            # print("调试模式已开启，输入q退出")
            # while True:
            #     try:
            #         command = input("@")
            #         if command == 'q':
            #             break
            #         eval(command)
            #     except Exception as e:
            #         print(f"error: {e}")
            # --- 在新页面上执行操作 ---
            # 预先点击去除新手引导
            try:
                publish_page.get_by_text("我知道了").click(timeout=3000)  
            except:
                pass
            # publish_page.click('body')
            print(f"校对章节序号: {chapter_num}")
            if publish_page.get_by_placeholder(f"第{int(chapter_num)}章").count() == 0:
                messagebox.showerror("错误", f"章节 {chapter_num} 序号有误！")
                return False
            
            print(f"填写章节标题: {chapter_title}")
            publish_page.get_by_placeholder(f"第{int(chapter_num)}章").fill(chapter_title.strip(), timeout=3000)

            print("粘贴章节正文...")
            publish_page.wait_for_selector('#chapterbody', timeout=10000)
            publish_page.fill('#chapterbody', chapter_content)
            publish_page.wait_for_timeout(3000)
            
            if writer_said_content is not None and writer_said_content.strip() != '':
                print("填写作者说...")
                publish_page.fill('#note', writer_said_content.strip())

            if publish_mode == '立刻发布':
                publish_page.get_by_role("button", name="直接发表").click(timeout=3000)
            else:
                publish_page.get_by_role("button", name="放入存稿箱").click(timeout=3000)
                if publish_mode == '定时发布':
                    print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M:%S'))
                    publish_page.get_by_placeholder("设置发表时间").fill(self.publish_time.strftime('%Y-%m-%d %H:%M:%S'), timeout=3000)
                    publish_page.get_by_role("button", name="批量提交").click(timeout=3000)
            print(f"--- 第{chapter_num}章发布成功！---")
            publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def publish_single_chapter_on_xirangnovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, update_button, add_var: int):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        writer_said_content = chapter_details[3]
        if writer_said_content is not None and writer_said_content.strip() != '':
            print(f"章节 {chapter_num} 包含作者说!")
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False

        publish_page = None
        # update_button.click(timeout=3000)
        try:
            # print(page.url)
            # print("调试模式已开启，输入q退出")
            # while True:
            #     try:
            #         command = input("@")
            #         if command == 'q':
            #             break
            #         eval(command)
            #     except Exception as e:
            #         print(f"error: {e}")
            # --- 在新页面上执行操作 ---
            # publish_page.click('body')
            print(f"当前章节序号: {chapter_num}")      
            print(f"填写章节标题: {chapter_title}")
            page.get_by_placeholder("这里请输入章节号与章节名。示例：第一章 天降奇缘").fill(f"第{chapter_num}章 {chapter_title.strip()}", timeout=3000)

            print("粘贴章节正文...")
            page.get_by_placeholder("这里请输入正文").fill(chapter_content, timeout=3000)
            page.wait_for_timeout(3000)
            
            # if writer_said_content is not None and writer_said_content.strip() != '':
            #     print("填写作者说...")
            #     publish_page.fill('#note', writer_said_content.strip())
            if publish_mode == '保存为草稿':
                page.get_by_text("存入草稿", exact=True).click(timeout=3000)
            else:
                page.get_by_text("发布", exact=True).click(timeout=3000)
                if publish_mode == '立刻发布':
                    page.get_by_role("radio", name="立即").click(timeout=3000, force=True)
                else:
                    page.get_by_role("radio", name="定时发布").click(timeout=3000, force=True)
                    page.wait_for_timeout(1500)
                    print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M:%S'))
                    date_input = page.get_by_placeholder("选择日期")
                    date_input_value = self.publish_time.strftime('%Y-%m-%d')
                    while date_input.input_value() != date_input_value:
                        date_input.fill(date_input_value, timeout=3000)
                        date_input.press('Enter')
                        page.wait_for_timeout(1500)

                    time_input = page.get_by_placeholder("选择时间")
                    if add_var > 0:
                        new_publish_time = self.publish_time + datetime.timedelta(minutes=add_var)
                    else:
                        new_publish_time = self.publish_time
                    time_input_value = new_publish_time.strftime('%H:%M:%S')
                    print(f"发布时间: {time_input_value}")
                    print(f"Ps.息壤不允许同时定时发布，要求一定要晚于上一章发布时间")
                    while time_input.input_value() != time_input_value:
                        time_input.fill(time_input_value, timeout=3000)
                        time_input.press('Enter')
                        page.wait_for_timeout(1500)
                    # print(page.url)
                    # print("调试模式已开启，输入q退出")
                    # while True:
                    #     try:
                    #         command = input("@")
                    #         if command == 'q':
                    #             break
                    #         eval(command)
                    #     except Exception as e:
                    #         print(f"error: {e}")

                page.click('#app > div > div.mainwarp > div > div.dialog_warp > div > div > div.el-dialog__body > div.d_footer > button', timeout=3000)

            print(f"--- 第{chapter_num}章发布成功！---")
            if publish_mode == '立刻发布':
                print("等待60秒，确保发布完成并避免显示发布频繁(息壤机制)...")
                page.wait_for_timeout(60000)
                page.reload()
            else:
                page.wait_for_timeout(3000)
            
        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def publish_single_chapter_on_migunovel(self, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, update_button):
        """发布单个章节，处理新打开的页面，并在完成后关闭。"""
        chapter_num, chapter_title, chapter_content = chapter_details[:3]
        writer_said_content = chapter_details[3]
        if writer_said_content is not None and writer_said_content.strip() != '':
            print(f"章节 {chapter_num} 包含作者说!")
        print(f"\n--- 开始发布: 第{chapter_num}章 ---")
        if self.stop_publish_sign:
            print("已检测到手动终止发布！！")
            self.stop_publish_sign = False
            return False

        publish_page = None
        # update_button.click(timeout=3000)
        try:
            # print(page.url)
            # print("调试模式已开启，输入q退出")
            # while True:
            #     try:
            #         command = input("@")
            #         if command == 'q':
            #             break
            #         eval(command)
            #     except Exception as e:
            #         print(f"error: {e}")
            # --- 在新页面上执行操作 ---
            # publish_page.click('body')
            print(f"当前章节序号: {chapter_num}")      
            print(f"填写章节标题: {chapter_title}")
            page.get_by_placeholder("这里请输入章节号与章节名。示例：第一章 天降奇缘").fill(f"第{chapter_num}章 {chapter_title.strip()}", timeout=3000)

            print("粘贴章节正文...")
            page.get_by_placeholder("这里请输入正文").fill(chapter_content, timeout=3000)
            page.wait_for_timeout(3000)
            
            # if writer_said_content is not None and writer_said_content.strip() != '':
            #     print("填写作者说...")
            #     publish_page.fill('#note', writer_said_content.strip())
            if publish_mode == '保存为草稿':
                page.get_by_text("存入草稿", exact=True).click(timeout=3000)
            else:
                page.get_by_text("发布", exact=True).click(timeout=3000)
                if publish_mode == '立刻发布':
                    page.get_by_role("radio", name="立即").click(timeout=3000, force=True)
                else:
                    page.get_by_role("radio", name="定时发布").click(timeout=3000, force=True)
                    page.wait_for_timeout(1500)
                    print("定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M:%S'))
                    date_input = page.get_by_placeholder("选择日期")
                    date_input.fill(self.publish_time.strftime('%Y-%m-%d'), timeout=3000)
                    date_input.press('Enter')
                    time_input = page.get_by_placeholder("选择时间")
                    time_input.fill(self.publish_time.strftime('%H:%M'), timeout=3000)
                    time_input.press('Enter')

                page.click('#app > div > div.mainwarp > div > div.dialog_warp > div > div > div.el-dialog__body > div.d_footer > button', timeout=3000)

            print(f"--- 第{chapter_num}章发布成功！---")
            print("等待60秒，确保发布完成并避免显示发布频繁(息壤机制)...")
            page.wait_for_timeout(60000)
            page.reload()
            

        except Exception as e:
            print(f"发布第{chapter_num}章时发生错误: {e}")
            traceback.print_exc()
            return False
        else:
            if publish_page:
                print("关闭章节发布页面...")
                publish_page.close()
            return True

    def automation_flow(self):
        """主自动化流程，负责初始化和循环调用章节发布。"""
        start_time = time.perf_counter()
        platform = get_platform(self.publish_plate_var.get())
        if platform:
            state = platform.run(self)
        else:
            print("暂时不支持的发布平台")
            return False
        end_time = time.perf_counter()
        spend_time = end_time - start_time
        if state:
            print(f"任务成功-总耗时: {spend_time//60:.0f}分{spend_time%60:.2f}秒")
            return True
        else:
            print(f"任务失败: {spend_time//60:.0f}分{spend_time%60:.2f}秒")
            return False

    def recommend_status(self, word_count_text: str, status_text: str, msg: str):
        try:
            if status_text.endswith('已签约'):
                word_count = float(word_count_text.replace('万字', ''))
                print(status_text)
                print(f"当前字数: {word_count}万字")
                if word_count < 8:
                    self.novel_status = '已签约'
                else:
                    if '作品已达成推荐字数条件' in msg:
                        self.novel_status = '待验证'
                    elif '开始推荐后7天内为推荐验证期' in msg:
                        self.novel_status = '验证中'
                    elif '作品正在番茄持续推荐中' in msg:
                        if self.novel_status == '全勤中':
                            return
                        if word_count < 20:
                            self.novel_status = '推荐中'
                        elif 20 <= word_count < 50 or 100 <= word_count < 150:
                            if self.novel_status != '书测中':
                                self.novel_status = '待书测'
                        else:
                            if self.novel_status == '书测中':
                                self.novel_status = '待封测'
                            else:
                                if self.novel_status == '封测中':
                                    self.novel_status = '划水期'
                    else:
                        if status_text.startswith('已完结'):
                            self.novel_status = '已完结'
                        else:
                            self.novel_status = '划水期'
            else:
                if status_text.startswith('连载中'):
                    if '签约审核已通过，请尽快完成合同签约' in msg:
                        self.novel_status = '待填写合同'
                    elif '你的作品即将签约成功，请点击【立即签约】' in msg:
                        self.novel_status = '待签约'
                    else:
                        word_count = float(word_count_text.replace('万字', ''))
                        if word_count >= 2:
                            self.novel_status = '请申请审核'
        except Exception:
            pass

    def automation_flow_by_fanqienovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num, 
            interval_days, interval_tag)  = normal_config[:15]

        if publish_mode == '定时发布':
            while not self.check_interval_publish(self.publish_time):
                print(f"{self.publish_time.strftime('%Y-%m-%d')}非间隔发布日，跳过至")
                self.publish_time += datetime.timedelta(days=1)
            print(f"从 {self.publish_time.strftime('%Y-%m-%d')} 开始发布")
            self.last_published_chapter_date_var.set(self.publish_time.strftime('%Y-%m-%d'))
        else:
            if not self.check_interval_publish(): 
                today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                print(f"今日({today_str})非发布日，跳过发布")
                return True

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                navigate_to_fanqie_novel_list(page, site_url)

                print(f"正在查找小说: '{novel_title}'")

                while True:
                    page.wait_for_selector('[id^="long-article-table-item-"]')
                    page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                    novel_items = page.query_selector_all('[id^="long-article-table-item-"]')
                    update_button = None
                    for item in novel_items:
                        #self.debug()
                        title_element = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div'
                            ) or item.query_selector(
                            'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-title.font-1')
                        #print(title_element.inner_text())
                        if title_element and title_element.inner_text() == novel_title:
                            print(f"找到小说《{novel_title}》")
                            # 定位到“更新章节”按钮
                            item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见  
                            page.wait_for_timeout(1000)
                            page.wait_for_load_state('domcontentloaded')
                            status_element = item.query_selector(
                                'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.property') or item.query_selector(
                                'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-detail.font-4 > span:nth-child(1)')
                            wordcount_element = item.query_selector(
                                'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.detail-wordcount.font-4 > span') or item.query_selector(
                                'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-detail.font-4 > span:nth-child(3)')
                            msg_element = item.query_selector(
                                'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                            _retries = 0
                            while not msg_element and _retries < 3:
                                print("未找到状态提示，等待1秒后重试")
                                page.wait_for_timeout(1000)
                                msg_element = item.query_selector(
                                    'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                                _retries += 1

                            if msg_element:
                                print(f"找到状态提示: {msg_element.inner_text()}")
                                self.recommend_status(wordcount_element.inner_text(), status_element.inner_text(), msg_element.inner_text())
                            else:
                                print("未找到状态提示")

                            update_button = item.query_selector(
                                'div > div.book-item-info > div.info-content > div.info-right > div > a:nth-child(3) > button') or item.query_selector(
                                'div > div.completion-book-item-main > div.completion-book-item-actions > a:nth-child(3) > button')
                            update_button_unsign = item.query_selector(
                                'div > div.book-item-info > div.info-content > div.info-right > div > a:nth-child(4) > button') or item.query_selector(
                                'div > div.completion-book-item-main > div.completion-book-item-actions > a:nth-child(4) > button')
                            if update_button:
                                break
                            elif update_button_unsign:
                                print("小说未签约")
                                update_button = update_button_unsign
                                break
                            else:
                                print("未找到'创建章节'按钮")

                    if not update_button:
                        next_page_button_limit = page.query_selector(
                            'div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next.arco-pagination-item-disabled')
                        next_page_button = page.query_selector(
                            "div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next")
                        if next_page_button and not next_page_button_limit:
                            next_page_button.click()
                            page.wait_for_load_state('networkidle')
                        else:
                            print(f"错误：在列表中未找到小说 '{novel_title}'")
                            # self.debug()
                            return
                    else:
                        break
                # self.debug()
                row = page.get_by_text(novel_title).locator("..").locator("..").locator("..")
                row.hover()
                row.get_by_role("button", name="章节管理").click(timeout=3000, force=True)

                # if not self.fast_publish_mode:
                # 开启间隔发布
                # if not self.check_interval_publish():

                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_fanqienovel(publish_mode, context, page, chapter_details, novel_title):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布' or ('本地定时发布' in self.scheduled_task):
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=interval_days)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=interval_days)
                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")
                    page.wait_for_timeout(3000)
                browser.close()
                
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, max(start_chapter, end_chapter), publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def automation_flow_by_wechatnovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]
        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_selector('#jumpUrl', timeout=3000).click(timeout=3000)
                page.wait_for_timeout(3000)

                if publish_mode == '定时发布':
                    if init_daily_publish_num != -1:
                        # 晚一分钟避免发布顺序错位
                        if init_daily_publish_num >= daily_publish_num:
                            self.publish_time += datetime.timedelta(minutes=init_daily_publish_num - daily_publish_num)
                        else:
                            self.publish_time += datetime.timedelta(hours=1)
                    else:           
                        if init_daily_publish_count >= daily_publish_count:
                            self.publish_time += datetime.timedelta(minutes=(init_daily_publish_count - daily_publish_count)//2000+1)
                        else:
                            self.publish_time += datetime.timedelta(hours=1)
                
                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_wechatnovel(publish_mode, context, page, chapter_details, novel_title):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if daily_publish_num == -1:
                            self.publish_time += datetime.timedelta(minutes=1) # 晚一分钟避免发布顺序错位
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = int(self.daily_publish_count_var.get())
                                self.publish_time += datetime.timedelta(days=1)
                                init_publish_time = datetime.datetime.strptime(self.publish_time_var.get(), '%H:%M')
                                self.publish_time = self.publish_time.replace(hour=init_publish_time.hour, minute=init_publish_time.minute)
                        else:
                            self.publish_time += datetime.timedelta(minutes=1) # 晚一分钟避免发布顺序错位
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <= 0:
                                daily_publish_num = int(self.daily_publish_num_var.get())
                                self.publish_time += datetime.timedelta(days=1)
                                init_publish_time = datetime.datetime.strptime(self.publish_time_var.get(), '%H:%M')
                                self.publish_time = self.publish_time.replace(hour=init_publish_time.hour, minute=init_publish_time.minute)
                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")
                    page.wait_for_timeout(3000)
                browser.close()

                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, 
                        max(end_chapter, start_chapter), publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                print("主自动化流程中发生错误:")
                print("常见问题有：登陆失效")
                return False

    def automation_flow_by_qidiannovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                write_button = None  
                # 直接查找小说标题(因为一般起点是单开，工作台首页即所需发布的书籍)
                page.wait_for_selector('#body > div.g-row.mt24 > div.g-col.g-col-10.g-body-main > div:nth-child(2) > div.g-prodution-item.fix.pb24 > div.g-prodution-item-lf.pr > div.g-prodution-item-title > a > h3', timeout=60000)
                actual_title = page.query_selector('#body > div.g-row.mt24 > div.g-col.g-col-10.g-body-main > div:nth-child(2) > div.g-prodution-item.fix.pb24 > div.g-prodution-item-lf.pr > div.g-prodution-item-title > a > h3').inner_text()
                if actual_title == novel_title:
                    print(f"已找到小说: '{novel_title}'")
                    write_button = page.get_by_role("button", name="去写作")
                else:
                    print(f"未找到小说: '{novel_title}'，继续查找...")
                    print("点击进入小说列表页面...")
                    page.query_selector("#body > div.g-row.mt24 > div.g-col.g-col-2.g-side > div > div > ul > li:nth-child(2) > a").click(timeout=1500)
                    novel_list_selector = '#book-body > div.g-nav-con > div > ul'
                    try:
                        page.wait_for_selector(novel_list_selector, timeout=60000)  # 等待元素出现
                        page.click(novel_list_selector, timeout=60000)  # 延长点击超时
                        page.wait_for_load_state('networkidle')
                    except Exception as e:
                        print(f"点击小说列表导航元素时发生错误: {e}")
                        raise  # 重新抛出异常以便上层捕获

                    print(f"正在查找小说: '{novel_title}'")

                    while True:
                        page.wait_for_selector('.g-prodution-item', timeout=10000)
                        page.wait_for_timeout(3000)
                        
                        # 获取所有小说项目
                        novel_items = page.query_selector_all('.g-prodution-item')
                        target_item = None
                        
                        for item in novel_items:
                            # 查找标题元素
                            title_element = item.query_selector('h3.open-book')
                            
                            if title_element and title_element.inner_text().strip() == novel_title:
                                print(f"找到小说 '{novel_title}'")
                                target_item = item
                                break
                        
                        if target_item:
                            # 找到后执行相关操作
                            write_button = target_item.query_selector('a.ui-button-primary')
                            if write_button:
                                # write_button.click()
                                break
                        else:
                            # 处理分页
                            next_button = page.query_selector('.pagination-next:not(.disabled)')
                            if next_button:
                                next_button.click()
                                page.wait_for_load_state('networkidle')
                                page.wait_for_timeout(2000)
                            else:
                                print(f"错误：在列表中未找到小说 '{novel_title}'")
                                return False

                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_qidiannovel(publish_mode, context, write_button, chapter_details):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            # 起点特殊的计数方式
                            chapter_word_count = self.count_chinese_characters(chapter_details[2]) // 1000 * 1000
                            daily_publish_count -= chapter_word_count
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)

                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")
                    page.wait_for_timeout(3000)
                browser.close()

                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                print("主自动化流程中发生错误:")
                print("常见问题有：登陆失效")
                return False

    def automation_flow_by_qimaonovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]
        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                write_button = None  
                # 直接查找小说标题(因为一般七猫也应该是单开，先查找工作台首页所需发布的书籍)
                # page.wait_for_selector('', timeout=60000)
                actual_title = page.query_selector('#app > div.layout > div.qm-main > div.wrapper > div > div.right-col > div.right-col-content.bg-index > div > div.author-book > div.index-module > div.index-module-body > div > ul > li > div > div.book-item-pic > div.txt > div > div.p-top > a').inner_text()
                if actual_title == novel_title:
                    print(f"已找到小说: '{novel_title}'")
                    write_button = page.get_by_text('新建章节')
                    
                else:
                    print(f"未找到小说: '{novel_title}'，继续查找...")
                    pass

                list_count = len(novel_files)
                add_var = 0
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    write_button.click() # 点击新建章节按钮
                    if not self.publish_single_chapter_on_qimaonovel(publish_mode, context, page, chapter_details, add_var):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)
                    while True:
                        try:
                            back_index = page.get_by_text("专区首页").first
                            back_index.click(timeout=1500)
                            page.wait_for_timeout(3000)
                            break
                        except Exception as e:
                            print(f"等待超时错误: {e}")
                            continue
                    add_var += 1

                    # 回到首页
                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")

                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def automation_flow_by_feilunovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()

            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                write_button = None  
                # 直接查找小说标题(因为一般七猫也应该是单开，先查找工作台首页所需发布的书籍)
                # page.wait_for_selector('', timeout=60000)
                try:
                    page.query_selector('body > div.zheZhao.zheZhao2.show > div > div.zz_listen_close').click(timeout=1500)
                except Exception as e:
                    pass
                actual_title = page.query_selector('body > div:nth-child(7) > div.mo_opus').inner_text()
                print(f"当前页面小说标题: '{actual_title}'")
                if novel_title in actual_title:
                    print(f"已找到小说: '{novel_title}'")
                    # write_button = page.get_by_text('章节管理')
                    write_button = page.locator('body > div:nth-child(7) > div.mo_opus > div.mo_o_layer2 > div.btnList.clearfix > a:nth-child(3)')
                else:
                    pass
                write_button.click(timeout=1500) # 点击新建章节按钮
                publish_page = None
                with context.expect_page() as new_page_info:
                    publish_page = new_page_info.value
                    publish_page.wait_for_load_state('networkidle')
                    print("已切换到新的发布页面。")

                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_feilunovel(publish_mode, context, publish_page, chapter_details, daily_publish_num):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)
                    # 回到首页
                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")

                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False
    
    def automation_flow_by_shuqinovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                print("点击进入小说列表页面...")
                try:
                    page.get_by_role('menuitem', name="长篇小说").click(timeout=3000)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"点击小说列表导航元素时发生错误: {e}")
                    # raise  # 重新抛出异常以便上层捕获
                page.wait_for_timeout(1500)
                #print(f"正在查找小说: '{novel_title}'")
                print(page.url)
                update_button = None
                try:
                    update_button = page.locator('.book-data-info').filter(has=page.locator('.book-name', has_text=novel_title)).get_by_text("创建章节")
                except Exception as e:
                    print(f"查找创建章节按钮时发生错误: {e}")

                    # raise  # 重新抛出异常以便上层捕获
                if update_button is None:
                    print(f"未找到小说: '{novel_title}'")
                    
                    return False
    
                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_shuqinovel(publish_mode, context, page, chapter_details, novel_title):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)

                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")
                    page.wait_for_timeout(3000)
                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def automation_flow_by_jinjiangnovel(self):
        # print("晋江目前仅支持单本更新...")
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                # 特殊部分
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                if page.locator(f"tr:has(a:text-is('{novel_title}'))").count() == 0:
                    print(f"错误：在列表中未找到小说 '{novel_title}'")
                    return False
                else:
                    print(f"找到小说 《{novel_title}》")
                    print('准备更新素材...')
                update_button = page.locator(f"tr:has(a:text-is('{novel_title}'))").get_by_text('点我更新')
                
                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_jinjiangnovel(publish_mode, context, page, chapter_details, update_button):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)

                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")
                    page.wait_for_timeout(3000)
                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def automation_flow_by_xirangnovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                print("点击进入小说列表页面...")
                try:
                    page.get_by_text("作品管理", exact=True).first.click(timeout=3000)  # 延长点击超时
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state('load')
                except Exception as e:
                    print(f"点击小说列表导航元素时发生错误: {e}")
                    # raise  # 重新抛出异常以便上层捕获
                if page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").count() == 0:
                    print(f"错误：在列表中未找到小说 '《{novel_title}》'")
                    return False
                else:
                    print(f"找到小说 《{novel_title}》")
                    print('准备更新素材...')
                    update_button = page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").get_by_text("去创作", exact=True)
                    update_button.click(timeout=1500)
                
                list_count = len(novel_files)
                add_var = 0
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_xirangnovel(publish_mode, context, page, chapter_details, update_button, add_var):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if init_daily_publish_num == -1:
                            daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                                add_var = 0
                        else:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                            if daily_publish_num <=  0:
                                daily_publish_num = init_daily_publish_num
                                self.publish_time += datetime.timedelta(days=1)
                                add_var = 0
                    add_var += 1

                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")

                    page.wait_for_timeout(3000)
                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def automation_flow_by_migunovel(self):
        normal_config = self._normal_load_config()
        if not normal_config:
            return False
        else:
            (custom_browser_path, site_url, 
            novel_title, novels_folder, 
            publish_mode, start_chapter, 
            end_chapter, keep_browser_open, 
            novel_files, init_daily_publish_count, init_daily_publish_num, 
            daily_publish_count, daily_publish_num) = normal_config[:13]

        with sync_playwright() as p:
            browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
            page = context.new_page()
            try:
                print("导航到作者后台...")
                page.goto(site_url, timeout=60000, wait_until='networkidle')
                print("点击进入小说列表页面...")
                try:
                    page.get_by_text("作品管理", exact=True).first.click(timeout=3000)  # 延长点击超时
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state('load')
                except Exception as e:
                    print(f"点击小说列表导航元素时发生错误: {e}")
                    # raise  # 重新抛出异常以便上层捕获
                if page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").count() == 0:
                    print(f"错误：在列表中未找到小说 '《{novel_title}》'")
                    return False
                else:
                    print(f"找到小说 《{novel_title}》")
                    print('准备更新素材...')
                    update_button = page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").get_by_text("去创作", exact=True)
                    update_button.click(timeout=1500)
                
                list_count = len(novel_files)
                for i, novel_file in novel_files:
                    chapter_details = self.get_chapter_details(novel_file)
                    if not self.publish_single_chapter_on_xirangnovel(publish_mode, context, page, chapter_details, update_button):
                        print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                        break
                    if publish_mode == '定时发布':
                        if daily_publish_num > 0:
                            daily_publish_num -= 1
                            print(f"本日还差发布{daily_publish_num}章")
                        elif daily_publish_num == 0:
                            daily_publish_num = init_daily_publish_num
                            self.publish_time += datetime.timedelta(days=1)
                        else:
                            if daily_publish_count <= 0:
                                daily_publish_count = init_daily_publish_count
                                self.publish_time += datetime.timedelta(days=1)
                            else:
                                daily_publish_count -= self.count_chinese_characters(chapter_details[2])
                                print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")

                    list_count -= 1
                    if list_count > 0:
                        print(f"本次任务剩余{list_count}章")
                        print("准备发布下一章...")

                    page.wait_for_timeout(3000)
                browser.close()
                self._normal_save_config(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
                if list_count == 0:
                    print("\n所有章节发布完毕！")
                    return True
                else:
                    print("\n有章节发布失败，已停止发布后续章节。")
                    return False
            except Exception as e:
                traceback.print_exc()
                self._normal_error_print()
                return False

    def _normal_load_config(self, event=None):
        """
        独立加载配置，避免过程中修改界面配置导致错乱
        """
        custom_browser_path = self.custom_browser_path_var.get()
        site_url = self._get_site_url()
        novel_title = self.novel_title_var.get()
        novels_folder = self.novels_folder_var.get()
        publish_mode = self.publish_mode_var.get()
        start_chapter = int(self.start_chapter_var.get())
        end_chapter = int(self.end_chapter_var.get())
        keep_browser_open = self.keep_browser_open_var.get()

        init_daily_publish_num = int(self.daily_publish_num_var.get())
        init_daily_publish_count = int(self.daily_publish_count_var.get())
        daily_publish_num = int(self.daily_publish_num_remain_var.get()) 
        daily_publish_count = int(self.daily_publish_count_remain_var.get())
        interval_mode = self.interval_publish_mode_var.get()
        interval_days, interval_tag = int(interval_mode.split('/')[0]), int(interval_mode.split('/')[1])

        if custom_browser_path.isdigit():
            print("自行登录模式")
        else:
            if not os.path.exists(AUTH_FILE):
                print(f"错误：找不到登录状态文件 {AUTH_FILE}。请先登录，允许扫码登录。")
                return False

        if not os.path.exists(novels_folder) and event is None:
            print(f"错误：小说文件夹 {novels_folder} 不存在。")
            return False
        else:
            if start_chapter is not None and end_chapter is not None:
                novel_files = self.get_chapter_files_in_range(novels_folder, start_chapter, end_chapter)
            else:
                novel_files = sorted(
                    [os.path.join(novels_folder, f) for f in os.listdir(novels_folder) if f.endswith('.md')])
            if not novel_files and event is None:
                print(f"在文件夹 {novels_folder} 中没有找到要发布的小说文件。")
                return False
        
        if publish_mode == '定时发布' or ('本地定时发布' in self.scheduled_task):
            time_str = self.last_published_chapter_date_var.get() + " " + self.publish_time_var.get().replace("：", ":")
            try:
                self.publish_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M')
            except Exception:
                print(f"错误：发布时间格式错误。请输入正确的时间格式（例如：2023-10-01 12:00）")
                return False
            self.publish_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M')
            
            if init_daily_publish_num != -1:
                print(f"计划：日更{init_daily_publish_num}章！") 
                if daily_publish_num == 0:
                    daily_publish_num = init_daily_publish_num
                    self.publish_time += datetime.timedelta(days=1)
                else:
                    if daily_publish_num != -1:
                        print(f"检查到上次计划剩余{daily_publish_num}章")       
            else:
                print(f"计划：日更{init_daily_publish_count}字！")
                if daily_publish_count == 0:
                    daily_publish_count = init_daily_publish_count
                    self.publish_time += datetime.timedelta(days=1)
                else:
                    if daily_publish_num == -1:
                        print(f"检查到上次计划剩余{daily_publish_count}字")
            print("预计定时发布时间: ", self.publish_time.strftime('%Y-%m-%d %H:%M'))
        
        if self.fast_publish_mode or event is not None:
            print('配置加载完毕')
        else:
            msg_str = f"小说名：{novel_title}\n发布模式：{publish_mode}\n"
            msg_str += f"开始章节：{start_chapter}\n"
            msg_str += f"结束章节：{end_chapter}\n"

            if interval_days != 1:
                msg_str += f"间隔发布：{interval_mode}（{self._describe_interval_mode(interval_mode)}）\n"
            if publish_mode == '定时发布':
                msg_str += f"   定时发布时间：{self.publish_time.strftime('%Y-%m-%d %H:%M')}\n"
                if init_daily_publish_num == -1:
                    msg_str += f"   字数计数模式：\n        计划：日更{init_daily_publish_count}字\n        上次计划剩余{daily_publish_count if daily_publish_count != init_daily_publish_count else 0}字\n"
                else:
                    msg_str += f"   章节计数模式：\n        计划：日更{init_daily_publish_num}章！\n        上次计划剩余{daily_publish_num if daily_publish_num != init_daily_publish_num else 0}章\n"
            if not messagebox.askyesno("再次确认", msg_str+"\n是否继续？"):
                return False

        return PublishConfig(
            custom_browser_path=custom_browser_path,
            site_url=site_url,
            novel_title=novel_title,
            novels_folder=novels_folder,
            publish_mode=publish_mode,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            keep_browser_open=keep_browser_open,
            novel_files=novel_files,
            init_daily_publish_count=init_daily_publish_count,
            init_daily_publish_num=init_daily_publish_num,
            daily_publish_count=daily_publish_count,
            daily_publish_num=daily_publish_num,
            interval_days=interval_days,
            interval_tag=interval_tag,
        )

    def _normal_open_browser(self, p, custom_browser_path, keep_browser_open):
        """打开浏览器，返回浏览器实例和上下文"""
        return _open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE,
                             on_browser_not_found=self.open_browser_lnk)

    def _normal_save_config(self, list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode):
        """
        保存配置到文件
        """
        end_chapter -= list_count
        if publish_mode == '修改章节':
            print(f"已修改成功章节至：{end_chapter}")
            print("修改章节不保存和更改配置")
            return
        
        if self.daily_publish_num_var.get() != -1:
            if daily_publish_num == self.daily_publish_num_var.get():
                daily_publish_num = 0
                self.publish_time -= datetime.timedelta(days=1)
        else:
            if daily_publish_count == self.daily_publish_count_var.get():
                daily_publish_count = 0
                self.publish_time -= datetime.timedelta(days=1)
        
        if publish_mode == '定时发布' or ('本地定时发布' in self.scheduled_task):
            self.config['History']['daily_publish_num_remain'] = str(daily_publish_num)
            self.config['History']['daily_publish_count_remain'] = str(daily_publish_count)
            self.daily_publish_num_remain_var.set(daily_publish_num)
            self.daily_publish_count_remain_var.set(daily_publish_count)
        else:
            self.publish_time = datetime.datetime.now()
            self.config['History']['daily_publish_num_remain'] = str(list_count)
            self.config['History']['daily_publish_count_remain'] = '0'
            self.daily_publish_num_remain_var.set(list_count)
            self.daily_publish_count_remain_var.set(0)

        self.config['History']['last_published_chapter'] = str(end_chapter)
        self.config['History']['last_published_chapter_date'] = self.publish_time.strftime('%Y-%m-%d')
        # 更新界面输入框的显示值
        self.start_chapter_var.set(end_chapter + 1)
        plan_daily_publish_num = int(self.daily_publish_num_var.get())
        self.end_chapter_var.set(end_chapter + ((plan_daily_publish_num - self.daily_publish_num_remain_var.get()) if plan_daily_publish_num != -1 else 1))
        self.last_published_chapter_date_var.set(self.publish_time.strftime('%Y-%m-%d'))
        self.save_config()

    def _normal_error_print(self):
        """
        打印错误信息
        """
        self.refresh_ui()
        print("主自动化流程中发生错误:")
        print("常见流程问题有(如果日志中未提交错误原因，可能是以下问题)：")
        print("1)登陆失效\n2)时间格式错误\n3)上次剩余章节/字数为空\n4)定时时间离当前时间间隔不足30分钟")
        print("常见章节问题有(一般会显示在日志中)：")
        print("1)章节号和序号对应不上\n2)章节标题太长\n3)章节内容不够 1000字\n4)章节标题重复\n5)章节内容有重复内容")

    def _describe_interval_mode(self, mode):
        try:
            if '/' in mode:
                cycle, remainder = mode.split('/')
                cycle = int(cycle)
                remainder = int(remainder)
                return f"{cycle}天周期，距起始日÷{cycle}余{remainder}时发布"
        except Exception:
            pass
        return mode

    def check_interval_publish(self, check_date=None):
        mode = self.interval_publish_mode_var.get()
        try:
            if '/' in mode:
                cycle, remainder = mode.split('/')
                cycle = int(cycle)
                remainder = int(remainder)
                if cycle == 1 and remainder == 0:
                    return True
                if check_date is None:
                    check_date = datetime.datetime.now()
                return (check_date.toordinal() % cycle) == remainder
        except Exception:
            pass
        return True

    def parse_fast_publish_mode(self, fast_publish_mode):
        """
        解析快速发布模式字符串，生成发布计划
        例如: "15*1+15*2+2*7" 表示:
        - 第一步: 发布1-15章
        - 第二步: 预发布16-45章，每日15章，持续2天
        - 第三步: 预发布46-60章，每日2章，持续7天
        """
        try:
            # 分割字符串获取各个阶段
            stages = fast_publish_mode.split('+')
            plan = []
            
            current_chapter = 1
            
            for i, stage in enumerate(stages):
                if '*' in stage:
                    # 解析格式如 "15*3" (每日章节数*持续天数)
                    daily_count, days = stage.split('*')
                    daily_count = int(daily_count)
                    days = int(days)
                    
                    if i == 0:
                        # 第一步总是立即发布模式
                        end_chapter = current_chapter + daily_count - 1
                        plan.append({
                            'mode': '立刻发布',
                            'start_chapter': current_chapter,
                            'end_chapter': end_chapter,
                            'description': f"发布第{current_chapter}-{end_chapter}章"
                        })
                        current_chapter = end_chapter + 1
                    else:
                        # 后续步骤是预发布模式
                        end_chapter = current_chapter + daily_count * days - 1
                        plan.append({
                            'mode': '定时发布',
                            'start_chapter': current_chapter,
                            'end_chapter': end_chapter,
                            'daily_count': daily_count,
                            'days': days,
                            'description': f"预发布第{current_chapter}-{end_chapter}章 (每日{daily_count}章)"
                        })
                        current_chapter = end_chapter + 1
                else:
                    # 处理简单数字，如 "15"
                    count = int(stage)
                    end_chapter = current_chapter + count - 1
                    
                    if i == 0:
                        # 第一步总是立即发布模式
                        plan.append({
                            'mode': '立刻发布',
                            'start_chapter': current_chapter,
                            'end_chapter': end_chapter,
                            'description': f"发布第{current_chapter}-{end_chapter}章"
                        })
                    current_chapter = end_chapter + 1
            
            return plan
        except Exception as e:
            print(f"解析发布模式失败: {e}")
            return None

    def execute_publish_plan(self, plan):
        """
        执行发布计划
        """
        try:
            if self.publish_plate_var.get() != '番茄':
                print("最速开书流程目前仅支持番茄小说")
                return False
            set_string = ""
            for step in plan:
                set_string += step['description'] + "\n"
            if not messagebox.askyesno("再次确认", set_string+"\n是否继续？"):
                return False
            self.fast_publish_mode = True
            for i, step in enumerate(plan, 1):
                print(f"\n--- 步骤{i}: {step['description']} ---")
                # 设置发布模式
                self.publish_mode_var.set(step['mode'])
                
                # 设置章节范围
                self.start_chapter_var.set(int(step['start_chapter']))
                self.end_chapter_var.set(int(step['end_chapter']))
                
                # 如果是预发布模式，设置每日发布章节数
                if step['mode'] == '定时发布':
                    self.daily_publish_num_var.set(int(step['daily_count']))
                    self.daily_publish_num_remain_var.set(0)
                    if i == 2:
                        today = datetime.datetime.now()
                        self.last_published_chapter_date_var.set(today.strftime('%Y-%m-%d'))
                
                # 执行自动化流程
                if not self.automation_flow():
                    raise Exception(f"执行步骤{i}失败: {step['description']}")
            
            print("\n最速开书流程完成！")
            self.fast_publish_mode = False
            # self.fast_once_create_book_var.set(False)
            return True
        except Exception as e:
            print(f"最速开书流程中发生错误: {e}")
            traceback.print_exc()
            self.fast_publish_mode = False
            # self.fast_once_create_book_var.set(False)
            return False

    def create_book_fast(self, event=None):
        """
        快速创书功能：弹出多行对话框，允许输入文字并解析，然后打开浏览器执行创书操作
        """
        try:
            # 创建一个新窗口作为对话框
            dialog = tk.Toplevel(self)
            dialog.title("快速创书")
            dialog.geometry("600x400")
            dialog.transient(self)  # 设置为主窗口的子窗口
            dialog.grab_set()  # 模态窗口
            
            # 添加标签
            ttk.Label(dialog, text="请输入小说信息（标题、简介等）：").pack(pady=10, padx=10, anchor=tk.W)

            # 签约模式选择（番茄平台新增：连载模式/完本模式）
            mode_frame = ttk.Frame(dialog)
            mode_frame.pack(fill=tk.X, padx=10, pady=0)
            ttk.Label(mode_frame, text="签约模式（仅番茄平台生效）：").pack(side=tk.LEFT)
            sign_mode_var = tk.StringVar(value="连载模式")
            ttk.Radiobutton(mode_frame, text="连载模式", variable=sign_mode_var, value="连载模式").pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(mode_frame, text="完本模式", variable=sign_mode_var, value="完本模式").pack(side=tk.LEFT, padx=5)

            # 添加多行文本框
            text_frame = ttk.Frame(dialog)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            text_widget = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, height=15, width=70)
            text_widget.pack(fill=tk.BOTH, expand=True)
            text_widget.focus_set()
            
            # 确认按钮的回调函数
            def on_confirm():
                input_text = text_widget.get("1.0", tk.END).strip()
                # if not input_text:
                #     messagebox.showwarning("警告", "请输入小说信息")
                #     return
                
                parsed_info = self.parse_novel_info(input_text, self.publish_plate_var.get())
                if self.publish_plate_var.get() == '番茄':
                    parsed_info['签约模式'] = sign_mode_var.get()
                dialog.destroy()
                
                # 打开浏览器执行创建书本操作
                threading.Thread(target=self._execute_create_book, args=(parsed_info,), daemon=True).start()
            
            # 添加按钮
            button_frame = ttk.Frame(dialog)
            button_frame.pack(fill=tk.X, pady=10, padx=10)
            
            ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
            ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.RIGHT, padx=5)
            
        except Exception as e:
            print(f"快速创书对话框创建失败: {e}")
            traceback.print_exc()
            messagebox.showerror("错误", f"创建对话框失败: {str(e)}")

    def create_book_from_outline(self):
        """从根目录的大纲.txt文件读取开书信息并执行快速创书。

        文件格式为 &&&键值&&& 分段，提取"开书信息"键值的内容作为用户输入。
        其他逻辑与 create_book_fast 一致。
        """
        try:
            outline_data = _load_outline(os.getcwd())
            if not outline_data:
                print("错误：未找到以'大纲.txt'结尾的文件")
                if not fast_mode:
                    messagebox.showerror("错误", "未找到以'大纲.txt'结尾的文件")
                return False

            input_text = outline_data.get('开书信息', '')
            if not input_text:
                print("错误：大纲文件中未找到'开书信息'键值")
                if not fast_mode:
                    messagebox.showerror("错误", "大纲文件中未找到'开书信息'键值")
                return False

            print(f"已从大纲文件读取开书信息")
            parsed_info = self.parse_novel_info(input_text, self.publish_plate_var.get())

            self._execute_create_book(parsed_info)

            self.scheduled_task.remove('快速创书')
            if len(self.scheduled_task) == 0:
                self.title(f"❄【寒山】小说自动发布工具{VERSION}")
                self.protocol("WM_DELETE_WINDOW", self.destroy)
                if fast_mode:
                    self.destroy()
            else:
                self.title(f"定时任务执行中...{self.scheduled_task}")
        except Exception as e:
            print(f"快速创书失败: {e}")
            traceback.print_exc()
            if not fast_mode:
                messagebox.showerror("错误", f"快速创书失败: {str(e)}")

    @staticmethod
    def parse_novel_info(input_text: str, publish_plate: str):
        """解析用户输入的小说信息"""
        return _parse_novel_info(input_text, publish_plate)

    def _execute_create_book(self, parsed_info):
        """
        打开浏览器执行创建书本操作
        """
        try:
            print(f"执行创建书本操作...")
            if self.publish_plate_var.get() == '番茄':
                old_novel_title = self.novel_title_var.get()
                if parsed_info.get('书本名称', '') == '':
                    self.novel_title_var.set(f'{self.novel_writer_var.get()}{datetime.datetime.now().strftime("%m%d")}')
                else:
                    self.novel_title_var.set(parsed_info['书本名称'])
                custom_browser_path = self.custom_browser_path_var.get()
                site_url = self._get_site_url()
                novel_title = self.novel_title_var.get()
                keep_browser_open = self.keep_browser_open_var.get()
                # 这里是占位实现，实际应该调用浏览器相关的函数来创建书本
                # 示例：使用现有的浏览器操作框架
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=keep_browser_open, executable_path=custom_browser_path)
                    context = browser.new_context(storage_state=AUTH_FILE)
                    page = context.new_page()
                    print("导航到作者后台...")
                    page.goto(site_url, timeout=600000, wait_until='networkidle')
                    print("点击进入小说列表页面...")
                    novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                    try:
                        page.wait_for_selector(novel_list_selector, timeout=3000)  # 等待元素出现
                        page.click(novel_list_selector, timeout=1500)  # 延长点击超时
                        page.wait_for_load_state('domcontentloaded')
                    except Exception as e:
                        print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
                        try:
                            page.click('div.user-guide-btn > button', timeout=1000)
                            print("已关闭初始引导浮窗。")
                        except Exception:
                            print("未找到初始引导浮窗，继续执行...")
                        try:
                            page.get_by_text("立即收下").click(timeout=1000)
                            print("收下补签卡")
                        except Exception:
                            pass
                        try:
                            print("重新点击进入小说列表页面...")
                            page.wait_for_selector(novel_list_selector, timeout=3000)  # 等待元素出现
                            page.click(novel_list_selector, timeout=1500)  # 延长点击超时
                            page.wait_for_load_state('domcontentloaded')
                        except Exception as e:
                            print(f"点击小说列表导航元素时发生错误: {e}")
                            raise  # 重新抛出异常以便上层捕获
                    page.wait_for_timeout(3000)
                    if parsed_info.get('书本名称', '') == '':
                        print(f"创建占位书本: {novel_title}")
                        page.hover('#app > div > div.content.new-content > div.serial-card.serial-card-large.content-card-wrap.path-prefix-book-manage > div > div > div.arco-tabs-header-nav.arco-tabs-header-nav-horizontal.arco-tabs-header-nav-top.arco-tabs-header-size-default.arco-tabs-header-nav-text > div > div.arco-tabs-header-extra > div > span > div', timeout=1500)
                        page.get_by_text('创建书本').last.click(timeout=1500)
                        page.wait_for_timeout(2000)
                        try:
                            page.get_by_text('知道了', exact=True).last.click(timeout=1500)
                        except Exception:
                            pass
                        page.get_by_placeholder('请输入作品名称').fill(novel_title)
                        page.wait_for_timeout(2000)
                        # 选择签约模式（连载模式/完本模式）
                        sign_mode = parsed_info.get('签约模式', '连载模式')
                        try:
                            if sign_mode == '连载模式':
                                page.locator('#signPattern > div > div > label:nth-child(1) > span.arco-radio-text').click(timeout=1500)
                            elif sign_mode == '完本模式':
                                page.locator('#signPattern > div > div > label:nth-child(2) > span.arco-radio-text').click(timeout=1500)
                            else:
                                pass
                            print(f"已选择签约模式: {sign_mode}")
                        except Exception:
                            print(f"未找到签约模式选项({sign_mode})，使用页面默认值")
                        page.wait_for_timeout(500)
                        page.get_by_text('立即创建', exact=True).last.click(timeout=1500)
                    else:
                        try:   
                            while True:
                                if page.get_by_text(old_novel_title).count() > 0:
                                    print("找到占位书")
                                    book_item = page.get_by_text(old_novel_title).nth(0)
                                    book_item.hover(timeout=1500)
                                    book_item.locator('..').locator('..').get_by_role('button', name='作品相关').click(timeout=1500)
                                    page.wait_for_timeout(1500)
                                    page.get_by_text('作品设置', exact=True).last.click(timeout=1500)
                                    page.wait_for_timeout(1500)
                                    page.wait_for_load_state('load')
                                    page.get_by_role('button', name='修改').last.click(timeout=1500)
                                    break
                                else:
                                    next_page_button_limit = page.query_selector('div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next.arco-pagination-item-disabled')
                                    next_page_button = page.query_selector("div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next")
                                    if next_page_button and not next_page_button_limit:
                                        next_page_button.click()
                                        page.wait_for_load_state('networkidle')
                                    else:
                                        page.hover('#app > div > div.content.new-content > div.serial-card.serial-card-large.content-card-wrap.path-prefix-book-manage > div > div > div.arco-tabs-header-nav.arco-tabs-header-nav-horizontal.arco-tabs-header-nav-top.arco-tabs-header-size-default.arco-tabs-header-nav-text > div > div.arco-tabs-header-extra > div > span > div', timeout=1500)
                                        page.get_by_text('创建书本').last.click(timeout=1500)
                                        break
                            try:
                                page.get_by_text('知道了', exact=True).last.click(timeout=1500)
                            except Exception:
                                pass
                            # self.debug()
                            page.get_by_placeholder('请输入作品名称').fill(novel_title)
                            # 选择签约模式（连载模式/完本模式）
                            sign_mode = parsed_info.get('签约模式', '连载模式')
                            try:
                                if sign_mode == '连载模式':
                                    page.locator('#signPattern > div > div > label:nth-child(1) > span.arco-radio-text').click(timeout=1500)
                                elif sign_mode == '完本模式':
                                    page.locator('#signPattern > div > div > label:nth-child(2) > span.arco-radio-text').click(timeout=1500)
                                else:
                                    pass
                                print(f"已选择签约模式: {sign_mode}")
                            except Exception:
                                print(f"未找到签约模式选项({sign_mode})，使用页面默认值")
                            page.wait_for_timeout(500)
                            if parsed_info.get('目标名称', '') == '男频':
                                page.click("#radio > div > div > label:nth-child(1) > span.arco-radio-text", timeout=1500)
                            else:
                                page.click("#radio > div > div > label:nth-child(2) > span.arco-radio-text", timeout=1500)

                            for file in os.listdir(os.getcwd()):
                                if file.endswith('.jpg') or file.endswith('.png'):
                                    parsed_info['封面路径'] = os.path.join(os.getcwd(), file)
                                    page.get_by_text('选择封面', exact=True).click(timeout=1500)
                                    page.locator('div.cover-upload input[type="file"]').set_input_files(parsed_info['封面路径'])
                                    page.wait_for_timeout(1000)
                                    page.wait_for_load_state('networkidle')
                                    page.get_by_text('确定', exact=True).click(timeout=10000)
                                    page.wait_for_timeout(1500)
                                    page.wait_for_load_state('load')
                                    break

                            # === 阅读标签（#selectRow）===
                            page.locator('#selectRow .select-view').click(timeout=1500)
                            page.wait_for_timeout(500)
                            for cat_name, tags in parsed_info['阅读标签'].items():
                                # 主分类是单个字符串，其余是列表
                                tag_list = [tags] if isinstance(tags, str) else tags
                                for tag in tag_list:
                                    page.locator(f'.category-choose-item:has(.category-choose-item-title:text-is("{tag}"))').click(timeout=1500)
                            page.get_by_text('确认').last.click(timeout=1500)
                            page.wait_for_timeout(1000)

                            # === 内容标签（#activitySelectRow）===
                            page.locator('#activitySelectRow .select-view').click(timeout=1500)
                            page.wait_for_timeout(500)
                            for cat_name, tags in parsed_info['内容标签'].items():
                                for tag in tags:
                                    page.locator(f'.category-choose-item:has(.category-choose-item-title:text-is("{tag}"))').click(timeout=1500)
                            page.get_by_text('确认').last.click(timeout=1500)
                            page.wait_for_timeout(1000)

                            # 主角名、简介、创建等（不变）
                            page.get_by_placeholder('请输入主角名1').fill(parsed_info['主角'][0])
                            if len(parsed_info['主角']) > 1:
                                page.get_by_placeholder('请输入主角名2').fill(parsed_info['主角'][1])
                            page.wait_for_timeout(1000)
                            if parsed_info.get('作品简介', ''):
                                page.locator("#descRow_input > div > div > textarea").fill(parsed_info['作品简介'])
                                # page.get_by_placeholder('请输入50-500字以内的作品简介...').fill(parsed_info['作品简介'])
                            page.wait_for_timeout(1500)
                            try:
                                page.locator('div.essay-activity-item-radio').last.click(timeout=1500)
                            except Exception:
                                pass
                            page.wait_for_timeout(2000)
                            try:
                                page.get_by_text('立即创建', exact=True).last.click(timeout=1500)
                            except Exception:
                                try:
                                    page.get_by_text('立即修改', exact=True).last.click(timeout=1500)
                                except Exception:
                                    pass
                            
                            # page.get_by_placeholder('请输入作品名称').fill(novel_title)
                            # page.get_by_text(parsed_info['目标名称']).click(timeout=1500)
                            # for file in os.listdir(os.getcwd()):
                            #     if file.endswith('.jpg') or file.endswith('.png'):
                            #         parsed_info['封面路径'] = os.path.join(os.getcwd(), file)
                            #         print(parsed_info['封面路径'])
                            #         page.get_by_text('选择封面', exact=True).click(timeout=1500)
                            #         page.locator('div.cover-upload input[type="file"]').set_input_files(parsed_info['封面路径'])
                            #         page.wait_for_timeout(1000)
                            #         page.wait_for_load_state('networkidle')
                            #         page.get_by_text('确定', exact=True).click(timeout=10000)
                            #         page.wait_for_timeout(1500)
                            #         page.wait_for_load_state('load')
                            #         break
                            # page.click('#selectRow > div > div > span > div', timeout=1500)
                            # # 选择主分类
                            # try:
                            #     page.click('#arco-tabs-1-tab-0 > span', timeout=1500)
                            # except:
                            #     pass
                            # page.locator(f'.category-choose-item-container:has(.category-choose-item-title:text-is("{parsed_info["标签"]["主分类"]}"))').click(timeout=1500)
                            # # page.click('#arco-tabs-1-tab-1 > span', timeout=1500)
                            # page.get_by_text('主题', exact=True).last.click(timeout=1500)
                            # for tag in parsed_info['标签']['主题']:
                            #     page.locator(f'.category-choose-item-container:has(.category-choose-item-title:text-is("{tag}"))').click(timeout=1500)
                            # # page.click('#arco-tabs-1-tab-2 > span', timeout=1500)
                            # page.get_by_text('角色', exact=True).last.click(timeout=1500)
                            # for tag in parsed_info['标签']['角色']:
                            #     page.locator(f'.category-choose-item-container:has(.category-choose-item-title:text-is("{tag}"))').click(timeout=1500)
                            # # page.click('#arco-tabs-1-tab-3 > span', timeout=1500)
                            # page.get_by_text('情节', exact=True).last.click(timeout=1500)
                            # for tag in parsed_info['标签']['情节']:
                            #     page.locator(f'.category-choose-item-container:has(.category-choose-item-title:text-is("{tag}"))').click(timeout=1500)
                            # page.wait_for_timeout(1000)
                            # page.get_by_text('确认').last.click(timeout=1500)
                            # page.wait_for_timeout(1000)
                            # page.get_by_placeholder('请输入主角名1').fill(parsed_info['主角'][0])
                            # if len(parsed_info['主角']) > 1:
                            #     page.get_by_placeholder('请输入主角名2').fill(parsed_info['主角'][1])
                            # page.wait_for_timeout(1000)
                            # if parsed_info.get('作品简介', ''):
                            #     page.get_by_placeholder('请输入50-500字以内的作品简介，不可出现低俗、暴力、血腥等不符合法律法规的内容').fill(parsed_info['作品简介'])
                            # page.wait_for_timeout(1500)
                            # try:
                            #     page.locator('div.essay-activity-item-radio').last.click(timeout=1500)
                            # except Exception:
                            #     pass
                            # page.wait_for_timeout(2000)
                            # try:
                            #     page.get_by_text('立即创建', exact=True).last.click(timeout=1500)
                            # except Exception:
                            #     try:
                            #         page.get_by_text('立即修改', exact=True).last.click(timeout=1500)
                            #     except Exception:
                            #         pass
                        except Exception as e:
                            print(f"创建失败: {e}")
                            traceback.print_exc()
                            messagebox.showerror("错误", f"创建书本失败: {str(e)}")
                            return False
                    page.wait_for_timeout(5000)
                messagebox.showinfo("提示", f"创建书本操作已完成\n标题: {novel_title}")
            elif self.publish_plate_var.get() == '七猫':
                self.novel_title_var.set(parsed_info['作品名称'])
                custom_browser_path = self.custom_browser_path_var.get()
                site_url = self._get_site_url()
                novel_title = self.novel_title_var.get()
                keep_browser_open = self.keep_browser_open_var.get()
                # 这里是占位实现，实际应该调用浏览器相关的函数来创建书本
                # 示例：使用现有的浏览器操作框架
                with sync_playwright() as p:
                    browser, context = self._normal_open_browser(p, custom_browser_path, keep_browser_open)
                    # browser = p.chromium.launch(headless=keep_browser_open, executable_path=custom_browser_path)
                    # context = browser.new_context(storage_state=AUTH_FILE)
                    page = context.new_page()

                    print("导航到作者后台...")
                    page.goto(site_url, timeout=600000, wait_until='networkidle')
                    try:
                        page.wait_for_timeout(1500)
                        page.get_by_text('新建小说').last.click(timeout=1500)
                        page.wait_for_timeout(1500)
                        page.get_by_text('七猫中文网').nth(1).click(timeout=1500)
                        page.get_by_text('确认').last.click(timeout=1500)
                        page.get_by_placeholder('请输入作品名称，最多18个字').fill(parsed_info['作品名称'])
                        page.get_by_text('男生').last.click(timeout=1500)
                        page.get_by_placeholder('请选择一级分类').click(timeout=1500)
                        page.get_by_text(parsed_info['作品分类']['一级分类']).last.click(timeout=1500)
                        page.get_by_placeholder('请选择二级分类').click(timeout=1500)
                        page.get_by_text(parsed_info['作品分类']['二级分类']).last.click(timeout=1500)
                        page.get_by_text('添加标签').last.click(timeout=1500)
                        # page.get_by_text('风格').nth(1).click(timeout=1500)
                        for tag in parsed_info['作品标签']['风格']:
                            try:
                                page.get_by_text(tag).last.click(timeout=1500)
                            except:
                                print(f"未找到标签: {tag}")
                        # page.get_by_text('角色').nth(1).click(timeout=1500)
                        for tag in parsed_info['作品标签']['角色']:
                            try:
                                page.get_by_text(tag).last.click(timeout=1500)
                            except:
                                print(f"未找到标签: {tag}")
                        # page.get_by_text('情节').nth(1).click(timeout=1500)
                        for tag in parsed_info['作品标签']['情节']:
                            try:
                                page.get_by_text(tag).last.click(timeout=1500)
                            except:
                                print(f"未找到标签: {tag}")
                        # page.get_by_text('背景').nth(1).click(timeout=1500)
                        for tag in parsed_info['作品标签']['背景']:
                            try:
                                page.get_by_text(tag).last.click(timeout=1500)
                            except:
                                print(f"未找到标签: {tag}")
                        page.click('body > div.el-dialog__wrapper.qm-dialog.qm-book-tag-picker-dialog.w-600px.center.h-p-0.bg-gray > div > div.el-dialog__body > div.qm-dialog-tb > div > div.content-wrap > div.tag-operation-wrap > div.operation-btn-wrap > a.qm-btn.important.small.spacing-24.radius', timeout=1500)
                        page.get_by_role("textbox").nth(3).fill(parsed_info['主角名'][0])
                        if len(parsed_info['主角名']) > 1:
                            page.get_by_role("textbox").nth(4).fill(parsed_info['主角名'][1])
                        page.get_by_placeholder("请简要介绍作品，最多500个字").fill(parsed_info['作品简介'])
                        page.wait_for_timeout(1500)
                        page.get_by_text('确认创建').last.click(timeout=1500)
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        print(f"创建失败: {e}")
                        traceback.print_exc()
                        messagebox.showerror("错误", f"创建书本失败: {str(e)}")
                        return False
                    page.wait_for_timeout(5000)
                messagebox.showinfo("提示", f"创建书本操作已完成\n标题: {parsed_info['作品名称']}")
            self.novel_status = '已创建'
            self.save_config(False)
            print(f"创书完成，已保存配置。小说状态: {self.novel_status}")
        except Exception as e:
            print(f"执行创建书本操作失败: {e}")
            traceback.print_exc()
            messagebox.showerror("错误", f"创建书本失败: {str(e)}")

    def show_fast_publish_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("最速开书配置")
        dialog.geometry("360x160")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        fast_var = tk.StringVar(value=self.fast_publish_mode_var.get())
        ttk.Label(frame, text="最速开书发布:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=10)
        fast_combo = ttk.Combobox(frame, textvariable=fast_var, width=25,
                                  values=["7*1+7*4+3*12", "15+15*2+2*7", "10*1+15*2+3*7", "10*1+10*3+5*7", "10*1+5*6+3*10"])
        fast_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=10)

        def on_ok():
            self.fast_publish_mode_var.set(fast_var.get())
            dialog.destroy()
            self.run_automation_thread(True)

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="确定", command=on_ok, width=10).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

    def new_novel_publish_once(self):
        print("执行最速开书！")
        novels_folder = self.novels_folder_var.get()
        all_files = sorted([os.path.join(novels_folder, f) for f in os.listdir(novels_folder) if
                            f.endswith('.md') and f.startswith('Chapter_')])
        fast_publish_mode = self.fast_publish_mode_var.get()
        need_num = eval(fast_publish_mode)
        print(f'当前发布计划需要发布的章节数: {need_num}章')
        if len(all_files) < need_num:
            print(f"错误：小说章节不足{need_num}章，无法执行最速开书-{fast_publish_mode}。\n"
                  f"当前章节数: {len(all_files)}")
            return
        
        # 解析发布模式并生成发布计划
        plan = self.parse_fast_publish_mode(fast_publish_mode)
        if not plan:
            print("解析发布模式失败")
            return
        # print(plan)
        # 执行发布计划
        self.execute_publish_plan(plan)

    @staticmethod
    def count_chinese_characters(text):
        """统计文本中的中文字符数量"""
        return _cf_count_chinese(text)

    def submit_thread(self):
        print("测试中，敬请期待")
        pass

    def create_tray_icon(self):
        self.tray_icon = _create_tray_icon(self.novel_title_var.get(), self.show_window, self.exit_app)

    def run_tray(self):
        run_tray_in_thread(self.tray_icon)

    def minimize_to_tray(self):
        self.withdraw()  # 隐藏主窗口

    def show_window(self, icon, item):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def exit_app(self, icon, item):
        self.tray_icon.stop()
        self.after(0, self.destroy)

    def publish_sstory(self):
        if self.publish_plate_var.get() != '番茄':
            print("当前只支持番茄短篇发布")
            return
        try:
            browser_path = self.custom_browser_path_var.get()
            site_url = self._get_site_url()
            writer = self.novel_writer_var.get()
            fssp = FanqieSStoryAutoPublisher(browser_path, site_url, writer, AUTH_FILE)
            # 创建一个新窗口作为对话框
            dialog = tk.Toplevel(self)
            dialog.title("快速发布短篇")
            dialog.geometry("600x400")
            dialog.transient(self)  # 设置为主窗口的子窗口
            dialog.grab_set()  # 模态窗口
            
            # 添加标签
            ttk.Label(dialog, text="请输入标准格式的短故事全文：").pack(pady=10, padx=10, anchor=tk.W)
            
            # 添加多行文本框
            text_frame = ttk.Frame(dialog)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            text_widget = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, height=15, width=70)
            text_widget.pack(fill=tk.BOTH, expand=True)
            text_widget.focus_set()
  
            # 添加按钮
            button_frame = ttk.Frame(dialog)
            button_frame.pack(fill=tk.X, pady=10, padx=10)
            def on_confirm():
                input_text = text_widget.get("1.0", tk.END).strip()
                if not input_text:
                    messagebox.showwarning("警告", "请输入短故事全文")
                    return
                dialog.destroy()
                # 打开浏览器执行创建书本操作
                threading.Thread(target=self.scheduled_sstory, args=(fssp, input_text,), daemon=True).start()
            
            def on_cancel():
                if '短故事发布' in self.scheduled_task:
                    self.scheduled_task.remove('短故事发布')
                    # 切换回正常关闭窗口
                    if len(self.scheduled_task) == 0:
                        self.title(f"❄【寒山】小说自动发布工具{VERSION}")
                        self.protocol("WM_DELETE_WINDOW", self.destroy)
                        if fast_mode:
                            self.destroy()
                    else:
                        self.title(f"定时任务执行中...{self.scheduled_task}")
                dialog.destroy()
            
            ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
            ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.RIGHT, padx=5)
            
        except Exception as e:
            print(f"快速发布短篇对话框创建失败: {e}")
            traceback.print_exc()
            messagebox.showerror("错误", f"创建对话框失败: {str(e)}")

    def scheduled_sstory(self, fssp, input_text: str):
        parsed_info = fssp.parse_story_info(input_text)
        fssp.publish(parsed_info)

        self.scheduled_task.remove('短故事发布')
        # 切换回正常关闭窗口
        if len(self.scheduled_task) == 0:
            self.title(f"❄【寒山】小说自动发布工具{VERSION}")
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            if fast_mode:
                self.destroy()
        else:
            self.title(f"定时任务执行中...{self.scheduled_task}")

    @staticmethod
    def check_repeat_content(content: str):
        """检查内容是否包含重复的中文字符，返回去重后的内容。"""
        return _cf_check_repeat(content)

    def debug(self):
        
        caller_frame = inspect.currentframe().f_back
        caller_info = inspect.getframeinfo(caller_frame)
        print(f"调试函数被调用位置: 文件 {caller_info.filename}，行号 {caller_info.lineno}，函数 {caller_info.function}")
        outer_locals = inspect.currentframe().f_back.f_locals
        outer_globals = inspect.currentframe().f_back.f_globals
    
        run_flag_signal = threading.Event()
        # 创建GUI窗口
        dialog = tk.Toplevel()
        dialog.title("调试代码编辑器")
        dialog.geometry("800x600")
        def run_code():
            run_flag_signal.set()
        def quit_code():
            dialog.destroy()
            run_flag_signal.set()
        dialog.protocol("WM_DELETE_WINDOW", quit_code)
        # 代码编辑区域
        code_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=("Consolas", 12))
        code_text.pack(expand=True, fill="both", padx=10, pady=10)
        
        # 运行按钮
        run_btn = tk.Button(dialog, text="运行代码", command=run_code, bg="#4CAF50", fg="white", font=("Arial", 12))
        run_btn.pack(pady=5)
        quit_btn = tk.Button(dialog, text="退出调试", command=quit_code, bg="#FF4D4F", fg="white", font=("Arial", 12))
        quit_btn.pack(pady=5)

        
        exec_namespace = {**outer_globals, **outer_locals, **self.__dict__}
        while True:
            run_flag_signal.wait()
            run_flag_signal.clear()
            if not dialog.winfo_exists():
                break
            code = code_text.get("1.0", tk.END).strip()
            try:
                # 在当前全局命名空间执行代码
                print("<< 执行代码 >>")
                exec(code, exec_namespace, exec_namespace)
                print("<< 代码执行完成 >>")
            except Exception:
                traceback.print_exc()
                print("<< 代码执行异常 >>")
                                
def parse_command_line_args():
    parser = argparse.ArgumentParser(description='Novel Publisher App')
    parser.add_argument('-key', type=str, help='Fast login key')
    parser.add_argument('-fast', type=str, help='Run in any fast mode (hide main interface)')
    parser.add_argument('--headless', action='store_true', help='Enable headless mode (no GUI)')
    
    args = parser.parse_args()
    return args.key, args.fast, args.headless

key, fast_mode, headless = parse_command_line_args()
# print(f"Fast: {fast_mode}, headless: {headless}")
# close_signal = threading.Event()
if __name__ == "__main__":
    app = NovelPublisherApp()
    if headless:
        # 不打开浏览器界面
        app.keep_browser_open_var.set(True)
    else:
        app.keep_browser_open_var.set(False)

    if fast_mode:
        # 快速模式下隐藏主界面，直接运行发布槽函数
        app.withdraw()
        # 这里需要调用发布槽函数
        #"快速模式：直接运行发布槽函数"
        app.execute_scheduled_task(fast_mode)
        app.mainloop()
    else:
        app.mainloop()

