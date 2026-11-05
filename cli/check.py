"""章节查重与字数检查 CLI。

来源: app.py 行 1774-1970
  - start_check_duplicate_titles (1774-1781)：原为后台线程调用，CLI 改为同步执行
  - check_duplicate_titles (1781-1890)
  - _finish_check_duplicate_titles (1890-1910)：messagebox 弹窗改为 print
  - check_chapter_word_counts (1910-1938)：多线程字数检查逻辑保留
  - show_chapter_word_count_issues (1938-1970)：Treeview 弹窗改为逐行打印

去 UI 化说明:
  - self.xxx_var.get() 改为命令行参数 / config.ini 读取；
  - messagebox.showerror / showinfo 改为 print 输出同样信息；
  - self.get_chapter_details / self.count_chinese_characters 改用
    novel_publisher.chapter_files 中的同名函数；
  - 修改章节文件（标题截断/去重）的操作原样保留。
"""

import configparser
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from novel_publisher.chapter_files import (
    count_chinese_characters,
    get_chapter_details,
)

# 项目根目录（cli/ 的上一级），与 app.py 的 CONFIG_FILE='config.ini' 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')


def _read_novels_folder_from_config():
    """缺省时从项目根目录 config.ini 的 [Novel] novels_folder 读取小说文件夹。"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
    return config.get('Novel', 'novels_folder', fallback='')


def register(subparsers):
    """向 argparse 子命令注册参数。subparsers 是 check 命令的 parser。"""
    subparsers.add_argument(
        '--folder', default='',
        help='小说文件夹（缺省时从项目根目录 config.ini 的 [Novel] novels_folder 读取）')
    subparsers.add_argument(
        '--no-neat-index', action='store_false', dest='neat_index', default=True,
        help='不整理章节序号（默认整理序号，neat_index=True）')


def check_duplicate_titles(novels_folder=None, neat_index=True):
    """检查并修复重复的章节标题，同时检查标题字数和章节字数。

    返回 True 表示检查完成（无致命错误），False 表示出错。
    """
    try:
        if novels_folder is None:
            novels_folder = _read_novels_folder_from_config()
        if not novels_folder or not os.path.isdir(novels_folder):
            return _finish_check_duplicate_titles(error_message="请先设置正确的小说文件夹路径")

        # 获取章节文件，按章节号排序
        chapter_files = []
        for f in os.listdir(novels_folder):
            if f.endswith('.md') and f.startswith('Chapter_'):
                match = re.search(r'_(\d+)', f)
                if match:
                    chapter_num = int(match.group(1))
                    chapter_files.append((chapter_num, os.path.join(novels_folder, f)))

        if not chapter_files:
            return _finish_check_duplicate_titles(error_message="未找到章节文件")

        # 按章节号排序
        chapter_files.sort(key=lambda x: x[0])
        word_count_issues = check_chapter_word_counts(chapter_files, neat_index)

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
                    actual_title = actual_title.lstrip(':： \t')
                    rematch = re.match(chapter_prefix_pattern, actual_title)
                    if rematch:
                        actual_title = actual_title[len(rematch.group(1)):].lstrip(':： \t')

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

        return _finish_check_duplicate_titles(modified_count, modified_info, word_count_issues)

    except Exception as e:
        return _finish_check_duplicate_titles(error_message=f"检查标题时发生错误: {e}")


def _finish_check_duplicate_titles(modified_count=0, modified_info=None, word_count_issues=None, error_message=None):
    """原 UI 完成回调的去 UI 化版本：messagebox 内容改为 print 输出。

    返回 True 表示成功，False 表示出错（main 据此返回退出码）。
    """
    if error_message:
        print(f"错误: {error_message}")
        return False

    modified_info = modified_info or []
    word_count_issues = word_count_issues or []
    result_message = f"检查完成！共修改了 {modified_count} 个标题。"
    if modified_count > 0:
        result_message += "\n\n标题修改详情:\n" + "\n".join(modified_info[:10])
        if len(modified_info) > 10:
            result_message += f"\n... 等 {len(modified_info) - 10} 个更多修改"
    print(result_message)
    if word_count_issues:
        print(f"\n发现 {len(word_count_issues)} 个章节字数异常:")
        show_chapter_word_count_issues(word_count_issues)
    else:
        print("\n未发现章节字数异常。")
    return True


def check_chapter_word_counts(chapter_files, neat_index=True):
    """多线程检查章节正文低于1000字或大于4000字的问题。"""
    def check_one(chapter_num, filepath):
        chapter_details = get_chapter_details(filepath, neat_index, verbose=False)
        word_count = count_chinese_characters(chapter_details[2])
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


def show_chapter_word_count_issues(issues):
    """原 UI 弹窗列表（Treeview）的去 UI 化版本：逐行打印章节字数异常。"""
    print(f"{'章节序号':<10}{'字数':<10}章节名")
    for issue in issues:
        print(f"{issue['chapter_num']:<10}{issue['word_count']:<10}{issue['title']}  ({issue['filepath']})")


def main(args) -> int:
    """执行 check 命令，返回退出码（0 成功，1 失败）。"""
    if args.folder:
        novels_folder = args.folder
        print(f"小说文件夹: {novels_folder}")
    else:
        novels_folder = _read_novels_folder_from_config()
        print(f"未指定 --folder，使用 config.ini [Novel] novels_folder: {novels_folder}")

    # 原为后台线程执行（start_check_duplicate_titles），CLI 直接同步调用
    ok = check_duplicate_titles(novels_folder, neat_index=args.neat_index)
    return 0 if ok else 1
