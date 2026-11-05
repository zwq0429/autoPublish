"""下载小说 CLI。

来源: app.py 行 2355-2480（download_book 方法）。

去 UI 化说明:
  - 原下载对话框（tk.Toplevel）中的输入框/复选框改为命令行参数：
      book_id_var        -> --book-id（必需）
      output_var('output')-> --save-dir（默认 'output'，与原 UI 默认一致）
      start_var(1)/end_var(3) -> --start / --end
      export_all_var      -> --all
      just_download_content_var -> --toc-only
      publish_plate_var   -> --platform（缺省读 config.ini 的 [Settings] publish_plate）
  - messagebox.showerror 改为 print；
  - 原 download_chapters 在后台线程中执行，CLI 改为同步调用；
  - 复用 novel_publisher.downloader.NovelDownloader，下载逻辑不变；
  - AUTH_FILE 与 app.py 一致，使用 'auth.json' 登录态。
"""

import configparser
import json
import os

from novel_publisher.downloader import NovelDownloader

# 项目根目录（cli/ 的上一级），与 app.py 的 CONFIG_FILE/AUTH_FILE 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')
AUTH_FILE = 'auth.json'


def _read_config_value(section, key, fallback=''):
    """从项目根目录 config.ini 读取配置项。"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
    return config.get(section, key, fallback=fallback)


def register(subparsers):
    """向 argparse 子命令注册参数。subparsers 是 download 命令的 parser。"""
    subparsers.add_argument(
        '--book-id', required=True, help='书籍ID或链接（必需）')
    subparsers.add_argument(
        '--platform', default=None,
        help='平台名，如 番茄/飞卢/起点（默认取 config.ini 的 [Settings] publish_plate）')
    subparsers.add_argument(
        '--save-dir', default='output',
        help="保存目录（默认 'output'，与原 UI 输出文件夹默认值一致）")
    subparsers.add_argument(
        '--start', type=int, default=1,
        help='下载范围：从第几章（默认 1）')
    subparsers.add_argument(
        '--end', type=int, default=3,
        help='下载范围：到第几章（默认 3，包含该章）')
    subparsers.add_argument(
        '--all', action='store_true',
        help='下载全部章节（忽略 --start/--end）')
    subparsers.add_argument(
        '--toc-only', action='store_true',
        help='只下载目录（保存 <书名>_目录.txt）')


def main(args) -> int:
    """执行 download 命令，返回退出码（0 成功，非 0 失败）。"""
    novel_platform = args.platform or _read_config_value('Settings', 'publish_plate', fallback='番茄')
    book_id = args.book_id.strip()
    save_dir = args.save_dir
    print(f"平台: {novel_platform}  书籍ID: {book_id}  保存目录: {save_dir}")
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            storage_state = json.load(f)

        # 提取cookies并转换为requests格式
        cookies = {}
        for cookie in storage_state['cookies']:
            cookies[cookie['name']] = cookie['value']

        fqd = NovelDownloader(novel_platform, book_id, cookies)
        result = fqd.parse_main_page()
        # 判断小说页面是否解析成功
        if not result:
            print("[x] 小说页面解析失败，程序终止。")
            return 1

        book_title, chapter_titles, chapter_urls, abstract_content = result
        selected_titles = []
        selected_urls = []
        if args.toc_only:
            os.makedirs(save_dir, exist_ok=True)  # 确保输出目录存在
            file_path = os.path.join(save_dir, f"{book_title}_目录.txt")
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
            if args.all:
                selected_titles = chapter_titles
                selected_urls = chapter_urls
            else:
                start_idx = args.start - 1  # 转换为列表下标
                end_idx = args.end  # 包含该章节

                if 0 <= start_idx < end_idx <= len(chapter_urls):
                    selected_titles = chapter_titles[start_idx:end_idx]
                    selected_urls = chapter_urls[start_idx:end_idx]
            # 原 UI 在后台线程中执行下载，CLI 改为同步调用
            print(f"下载 {len(selected_titles)}/{len(chapter_titles)} 个章节\n文件保存为: {save_dir}/{book_title}.txt")
            fqd.download_chapters(book_title, abstract_content, selected_titles, selected_urls, save_dir)
        return 0

    except ValueError:
        print("错误: 请输入有效的章节范围")
        return 1
    except Exception as e:
        print(f"错误: 下载失败: {e}")
        return 1
