"""章节导出 CLI：把章节文件夹中的 Chapter_*.md 合并导出为单个 txt（去除 Markdown 标记）。

来源: app.py 行 2244-2355 export_chapters 方法。

去 UI 化说明:
  - self.novels_folder_var.get() -> --folder 参数（缺省读项目根 config.ini [Novel] novels_folder）
  - 导出范围对话框（"导出全部"勾选框默认勾选 + 起/止章输入框，默认 1 到最后一章）
    -> --all / --start / --end 参数（两者都缺省时同为导出全部，与源码默认行为一致）
  - 输出文件名输入框（默认 f"{小说名}_导出.txt"）-> -o/--output 参数；
    缺省时小说名取 config.ini [Novel] novel_title，输出名与源码默认值一致
  - messagebox.showerror / showinfo -> print 输出同样信息
  - 输出文件仍拼接在章节文件夹内（os.path.join(novels_folder, 输出名)）；
    --output 传绝对路径时 os.path.join 会自动使用该绝对路径
  - 源码仅有一种输出格式（合并为单个 txt，content.replace('# ', '').replace('**', '')），
    无"格式"选项，故不设 --format 参数
"""

import configparser
import os
import re

# 项目根目录（cli/ 的上一级），与 app.py 的 CONFIG_FILE='config.ini' 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')


def _load_config():
    """读取项目根目录 config.ini（不存在时返回空配置）。"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
    return config


def _read_novels_folder_from_config():
    """缺省时从 config.ini 的 [Novel] novels_folder 读取章节文件夹。"""
    return _load_config().get('Novel', 'novels_folder', fallback='')


def _read_novel_title_from_config():
    """缺省输出文件名使用的小说名，取 config.ini 的 [Novel] novel_title。"""
    return _load_config().get('Novel', 'novel_title', fallback='')


def register(subparsers):
    """向 export 子命令的 argparse parser 注册参数。"""
    subparsers.add_argument(
        '--folder', default='',
        help='章节文件夹（缺省读项目根 config.ini [Novel] novels_folder）')
    subparsers.add_argument(
        '-o', '--output', default=None,
        help='输出文件名（默认 f"{小说名}_导出.txt"，保存在章节文件夹内；传绝对路径则按绝对路径保存）')
    subparsers.add_argument(
        '--all', action='store_true',
        help='导出全部章节（对应源码默认勾选的"导出全部"；不指定范围时同为全部）')
    subparsers.add_argument(
        '--start', type=int, default=None,
        help='起始章节号（源码默认 1；与 --end 搭配实现范围导出）')
    subparsers.add_argument(
        '--end', type=int, default=None,
        help='结束章节号（源码默认最后一章的章号）')


def _perform_export(chapter_files, novels_folder, output_name, start_chapter, end_chapter) -> bool:
    """对应源码 perform_export 闭包（app.py 2304-2347），messagebox 改为 print。

    返回 True 表示导出成功。
    """
    try:
        # 过滤要导出的章节（源码 2313-2321）
        export_files = []
        for chapter_num, filepath in chapter_files:
            if start_chapter <= chapter_num <= end_chapter:
                export_files.append((chapter_num, filepath))

        if not export_files:
            print("错误: 没有选择要导出的章节")
            return False

        # 导出内容（源码 2323-2334：移除 Markdown 格式，章节之间添加空行）
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

        # 保存文件（源码 2336-2341：输出保存在章节文件夹内）
        output_path = os.path.join(novels_folder, output_name)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(output_content))

        print(f"导出完成！共导出 {len(export_files)} 个章节")
        print(f"文件保存为: {output_path}")
        return True

    except ValueError:
        print("错误: 请输入有效的章节范围")
        return False
    except Exception as e:
        print(f"错误: 导出失败: {e}")
        return False


def main(args) -> int:
    """执行 export 命令，返回退出码（0 成功，1 失败）。"""
    try:
        novels_folder = args.folder or _read_novels_folder_from_config()
        if not novels_folder or not os.path.isdir(novels_folder):
            print("错误: 请先设置正确的小说文件夹路径")
            return 1
        print(f"章节文件夹: {novels_folder}")

        # 获取章节文件（源码 2252-2265）
        chapter_files = []
        for f in os.listdir(novels_folder):
            if f.endswith('.md') and f.startswith('Chapter_'):
                match = re.search(r'_(\d+)', f)
                if match:
                    chapter_num = int(match.group(1))
                    chapter_files.append((chapter_num, os.path.join(novels_folder, f)))

        if not chapter_files:
            print("错误: 未找到章节文件")
            return 1

        chapter_files.sort(key=lambda x: x[0])

        # 导出范围（源码对话框默认：勾选"导出全部"，start=1，end=最后一章）
        if args.all or (args.start is None and args.end is None):
            start_chapter = 1
            end_chapter = chapter_files[-1][0]
            print("导出全部章节")
        else:
            start_chapter = args.start if args.start is not None else 1
            end_chapter = args.end if args.end is not None else chapter_files[-1][0]
            print(f"导出范围: 第{start_chapter}章 到 第{end_chapter}章")

        # 输出文件名（源码默认 f"{novel_title}_导出.txt"）
        output_name = args.output
        if not output_name:
            output_name = f"{_read_novel_title_from_config()}_导出.txt"

        ok = _perform_export(chapter_files, novels_folder, output_name,
                             start_chapter, end_chapter)
        return 0 if ok else 1

    except Exception as e:
        print(f"错误: 导出功能出错: {e}")
        return 1
