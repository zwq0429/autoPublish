"""导入章节 CLI：把 txt 按"第X章"标记拆分为 Chapter_NNN.md 章节文件。

来源: app.py 行 2489-2817 import_chapters 方法
     （含行 2817-2819 create_chapter_files_in_files_custom 包装方法）。

去 UI 化说明:
  - filedialog.askopenfilename（选择TXT文件） -> --file 参数（必需）
  - filedialog.askdirectory（选择章节保存文件夹） -> --output-dir / --folder 参数
  - "分解章节"按钮 + 章节列表框预览 -> 省略（纯 UI 预览；解析逻辑保留在各导入分支内）
  - "追加十章"/"清除所有"按钮 -> 省略（纯列表框多选辅助，属 UI 专属交互）
  - "倒序"按钮 -> --reverse（业务效果：所选章节按文档倒序写入，仅 append 模式有效）
  - 列表框多选（列表倒序显示 + actual_idx = total-1-idx 索引转换）-> --chapters "1,3,5-7"
    （按文档顺序指定章节号；源码转换后的最终写入顺序即文档顺序，语义一致）
  - messagebox.showerror / showinfo -> print 输出同样信息
  - 导入全部: 源码 2704/2819 调用 novel_publisher.chapter_files.create_chapter_files_in_files_custom，
    因其内部 messagebox.showerror（chapter_files.py:109）在 CLI 无 root 窗口时会阻塞弹窗，
    故按去 UI 化规则在本模块内复刻该函数（拆分/命名/写盘逻辑逐行一致：
    split_chapters + normalize_chapter_title），仅把 messagebox 改为 print
  - 导入成功后 self.novels_folder_var.set(save_path) 的持久化行为
    （app.py 1735-1749: 写回 config.ini [Novel] novels_folder，utf-8 保存）保留:
    用 configparser 写回并 print 说明
  - update_chapter_count() -> 统计并 print 章节文件数
"""

import configparser
import os
import re

from novel_publisher.chapter_files import (
    normalize_chapter_title,
    split_chapters,
)

# 项目根目录（cli/ 的上一级），与 app.py 的 CONFIG_FILE='config.ini' 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')


def _load_config(config_file):
    """读取 config.ini（不存在时返回空配置）。"""
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
    return config


def _read_novels_folder_from_config(config_file):
    """缺省时从 config.ini 的 [Novel] novels_folder 读取章节保存文件夹。"""
    return _load_config(config_file).get('Novel', 'novels_folder', fallback='')


def _write_novels_folder_to_config(config_file, save_path):
    """导入成功后写回 config.ini [Novel] novels_folder。

    对应源码 self.novels_folder_var.set(save_path) 的持久化行为
    （app.py 1735-1749: 仅当目录存在时写入，config.write 以 utf-8 保存）。
    """
    config = _load_config(config_file)
    if not config.has_section('Novel'):
        config.add_section('Novel')
    config['Novel']['novels_folder'] = save_path
    with open(config_file, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
    print(f"已更新 {config_file} [Novel] novels_folder = {save_path}")


def _print_chapter_count(save_path):
    """对应源码 update_chapter_count()（app.py 1761-1764 的章节计数）：统计并打印。"""
    count = 0
    if os.path.isdir(save_path):
        count = len([f for f in os.listdir(save_path)
                     if f.endswith('.md') and f.startswith('Chapter_')])
    print(f"当前章节文件数: {count}")


def _parse_chapter_numbers(spec):
    """解析 '1,3,5-7' 形式的章节号列表（文档顺序），返回升序去重列表。"""
    numbers = set()
    for part in str(spec or '').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_s, end_s = part.split('-', 1)
            try:
                start_n, end_n = int(start_s), int(end_s)
            except ValueError:
                print(f"警告: 无法解析章节范围 '{part}'，已跳过")
                continue
            numbers.update(range(start_n, end_n + 1))
        else:
            try:
                numbers.add(int(part))
            except ValueError:
                print(f"警告: 无法解析章节号 '{part}'，已跳过")
                continue
    return sorted(numbers)


def _import_all(file_path, save_path) -> bool:
    """导入全部章节，对应源码 import_all 闭包（app.py 2688-2716）。

    源码委托给 create_chapter_files_in_files_custom（app.py 2817-2819 ->
    novel_publisher/chapter_files.py:78-113），此处逐行复刻该函数，
    仅将其中的 messagebox.showerror 改为 print（CLI 无 root 窗口会阻塞弹窗）。
    """
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        chapters = split_chapters(content)
        if not chapters:
            print("错误: 未找到任何章节")
            return False

        for i, chapter in enumerate(chapters):
            try:
                chapter_number = i + 1
                _title = normalize_chapter_title(chapter['title'])
                file_name = f"Chapter_{chapter_number:03d}.md"
                chapter_path = os.path.join(save_path, file_name)

                with open(chapter_path, 'w', encoding='utf-8') as chapter_file:
                    chapter_file.write(f"# {_title}\n\n")
                    chapter_file.write(chapter['content'])
            except Exception as e:
                print(f"错误: 创建章节 {chapter_number} 失败: {str(e)}")
                return False

        print(f"成功分解 {len(chapters)} 个章节到目录: {save_path}")
        return True
    except Exception as e:
        print(f"错误: 导入失败: {str(e)}")
        return False


def _import_selected(file_path, save_path, chapters_spec, reverse=False) -> bool:
    """追加导入所选章节，对应源码 import_selected 闭包（app.py 2719-2807）。

    源码通过列表框多选确定章节（列表倒序显示，actual_idx = total-1-idx，
    转换后最终按文档顺序写入）；CLI 用 --chapters（文档顺序章节号）直接指定。
    --reverse 对应源码"倒序"按钮：将章节按文档倒序编号写入。
    """
    try:
        selected_numbers = _parse_chapter_numbers(chapters_spec)
        if not selected_numbers:
            print("错误: 请选择要导入的章节（用 --chapters 指定，如 1,3,5-7）")
            return False

        # 获取当前文件夹中最大的章节号（源码 2739-2748）
        max_chapter_num = 0
        if os.path.exists(save_path):
            for f in os.listdir(save_path):
                if f.startswith('Chapter_') and f.endswith('.md'):
                    match = re.search(r'Chapter_(\d+)\.md', f)
                    if match:
                        num = int(match.group(1))
                        if num > max_chapter_num:
                            max_chapter_num = num

        # 读取文件内容（源码 2750-2752）
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用正则表达式分解章节（源码 2754-2756，与
        # novel_publisher.chapter_files.CHAPTER_PATTERN 一致）
        chapter_pattern = re.compile(
            r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[:：\s]+.*$)',
            re.MULTILINE)
        parts = chapter_pattern.split(content)

        if len(parts) <= 1:
            print("错误: 未找到任何章节")
            return False

        # 解析章节（源码 2762-2768）
        chapters = []
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            if i + 1 < len(parts):
                chapter_content = parts[i + 1].strip()
                chapters.append({"title": title, "content": chapter_content})

        # 获取选中的章节（源码 2770-2777 的倒序索引转换后即文档顺序：
        # actual_idx = total_chapters - 1 - 列表框索引；CLI 直接用章节号-1）
        total_chapters = len(chapters)
        selected_chapters = []
        for num in selected_numbers:
            actual_idx = num - 1
            if 0 <= actual_idx < total_chapters:
                selected_chapters.append(chapters[actual_idx])
            else:
                print(f"提示: 章节号 {num} 超出范围（共 {total_chapters} 章），已跳过")

        if not selected_chapters:
            print("错误: 请选择要导入的章节")
            return False

        # --reverse（对应源码"倒序"按钮）：按文档倒序编号写入
        if reverse:
            selected_chapters.reverse()

        # 创建选中的章节文件（源码 2779-2797，标题规范化逻辑逐行保留）
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
                chapter_path = os.path.join(save_path, file_name)

                with open(chapter_path, 'w', encoding='utf-8') as chapter_file:
                    chapter_file.write(f"# {title}\n\n")
                    chapter_file.write(chapter['content'])
            except Exception as e:
                print(f"错误: 创建章节 {chapter_number} 失败: {str(e)}")
                return False

        print(f"成功导入 {len(selected_chapters)} 个章节到: {save_path}")
        return True
    except Exception as e:
        print(f"错误: 导入失败: {str(e)}")
        return False


def register(subparsers):
    """向 import-chapters 子命令的 argparse parser 注册参数。"""
    subparsers.add_argument(
        '--file', required=True,
        help='要导入的 txt 文件路径（必需）')
    subparsers.add_argument(
        '--output-dir', '--folder', dest='output_dir', default='',
        help='章节输出文件夹（缺省读 config.ini [Novel] novels_folder；'
             '导入成功后写回 config.ini）')
    subparsers.add_argument(
        '--config', default=DEFAULT_CONFIG_FILE,
        help='配置文件路径（默认 config.ini）')
    subparsers.add_argument(
        '--mode', choices=['all', 'append'], default='all',
        help='导入模式: all=导入全部（源码"导入全部"，从第001章写起，默认）；'
             'append=追加导入（源码"追加导入"，接在文件夹现有最大章号之后）')
    subparsers.add_argument(
        '--chapters', default='',
        help='append 模式下要导入的章节号（按文档顺序，如 "1,3,5-7"，'
             '替代源码列表框多选）')
    subparsers.add_argument(
        '--reverse', action='store_true',
        help='将所选章节按文档倒序编号写入（对应源码"倒序"按钮，仅 append 模式有效）')


def main(args) -> int:
    """执行 import-chapters 命令，返回退出码（0 成功，1 失败）。"""
    file_path = args.file
    if not file_path or not os.path.exists(file_path):
        print("错误: 请选择有效的TXT文件")
        return 1

    if not file_path.endswith('.txt'):
        print("错误: 请选择TXT文件")
        return 1

    save_path = args.output_dir or _read_novels_folder_from_config(args.config)
    if not save_path:
        print("错误: 请选择保存路径（--output-dir 或 config.ini [Novel] novels_folder）")
        return 1

    print(f"导入文件: {file_path}")
    print(f"保存路径: {save_path}  模式: {'导入全部' if args.mode == 'all' else '追加导入'}")

    try:
        # 确保目录存在（源码 2700-2701 / 2736-2737）
        os.makedirs(save_path, exist_ok=True)

        if args.mode == 'all':
            ok = _import_all(file_path, save_path)
        else:
            ok = _import_selected(file_path, save_path, args.chapters, args.reverse)

        if not ok:
            return 1

        # 对应源码 self.novels_folder_var.set(save_path) 的持久化行为:
        # 写回 config.ini [Novel] novels_folder
        _write_novels_folder_to_config(args.config, save_path)

        # 对应源码 self.update_chapter_count()
        _print_chapter_count(save_path)

        if args.mode == 'all':
            print(f"成功导入全部章节到: {save_path}")
        return 0

    except Exception as e:
        print(f"错误: 导入失败: {str(e)}")
        return 1
