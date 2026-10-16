"""章节文件读写与解析工具函数"""

import os
import re
import unicodedata
from typing import List, Tuple

from tkinter import messagebox


# 章节正则：匹配 "第...章：标题" 格式
CHAPTER_PATTERN = re.compile(
    r'(^\s*#*\s*第\s*[一二三四五六七八九十百千万零\dIVXLCDM]+\s*章[：:\s]+.*$)',
    re.MULTILINE
)


def split_chapters(content: str) -> list:
    """将全文按章节标记拆分为 [{title, content}, ...] 列表。"""
    parts = CHAPTER_PATTERN.split(content)
    if len(parts) <= 1:
        return []
    chapters = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        if i + 1 < len(parts):
            chapter_content = parts[i + 1].strip()
            chapters.append({"title": title, "content": chapter_content})
    return chapters


def normalize_chapter_title(title: str) -> str:
    """规范化章节标题中的冒号和空格。"""
    _title = str(title)
    if _title.find('：') == -1:
        c_index = _title.find('章') + 1
        if c_index < len(_title) and _title[c_index] in [':', ' ']:
            _title = _title[:c_index] + '：' + _title[c_index + 1:]
    _title = _title.replace(' ', '')
    return _title


def create_chapter_files_in_files(novel_file_path: str) -> bool:
    """从文件中分解生成章节文件"""
    if not novel_file_path.endswith('.txt'):
        print(f"错误: 文件 {novel_file_path} 不是文本文件，暂时不支持读取")
        return False

    output_dir = os.path.splitext(novel_file_path)[0]
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(novel_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"错误: 文件 {novel_file_path} 未找到。")
        return False

    chapters = split_chapters(content)
    if not chapters:
        print("未找到任何章节。")
        return False

    for i, chapter in enumerate(chapters):
        chapter_number = i + 1
        _title = normalize_chapter_title(chapter['title'])
        file_name = f"Chapter_{chapter_number:03d}.md"
        file_path = os.path.join(output_dir, file_name)

        with open(file_path, 'w', encoding='utf-8') as chapter_file:
            chapter_file.write(f"# {_title}\n\n")
            chapter_file.write(chapter['content'])

    print(f"成功分解 {len(chapters)} 个章节到目录: {output_dir}")
    return True


def create_chapter_files_in_files_custom(novel_file_path: str, custom_output_dir: str) -> bool:
    """从文件中分解生成章节文件到指定目录"""
    if not novel_file_path.endswith('.txt'):
        print(f"错误: 文件 {novel_file_path} 不是文本文件，暂时不支持读取")
        return False

    os.makedirs(custom_output_dir, exist_ok=True)

    try:
        with open(novel_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"错误: 文件 {novel_file_path} 未找到。")
        return False

    chapters = split_chapters(content)
    if not chapters:
        print("未找到任何章节。")
        return False

    for i, chapter in enumerate(chapters):
        try:
            chapter_number = i + 1
            _title = normalize_chapter_title(chapter['title'])
            file_name = f"Chapter_{chapter_number:03d}.md"
            file_path = os.path.join(custom_output_dir, file_name)

            with open(file_path, 'w', encoding='utf-8') as chapter_file:
                chapter_file.write(f"# {_title}\n\n")
                chapter_file.write(chapter['content'])
        except Exception as e:
            messagebox.showerror("错误", f"创建章节 {chapter_number} 失败: {str(e)}")
            return False

    print(f"成功分解 {len(chapters)} 个章节到目录: {custom_output_dir}")
    return True


def get_chapter_files_in_range(novels_folder: str, start_chapter: int, end_chapter: int) -> List[str]:
    """获取指定范围的章节文件路径列表（按章节号排序）。"""
    if not os.path.isdir(novels_folder):
        return []

    all_files = [os.path.join(novels_folder, f) for f in os.listdir(novels_folder) if f.endswith('.md')]
    if start_chapter > end_chapter:
        if not messagebox.askyesno("确认", f"起始章节号小于结束章节号，是否反向发布（适合存放草稿箱）？"):
            print("用户取消操作")
            return []

    chapter_files = []
    min_chapter, max_chapter = min(start_chapter, end_chapter), max(start_chapter, end_chapter)
    for filepath in all_files:
        basename = os.path.basename(filepath)
        filename, _ = os.path.splitext(basename)
        match = re.search(r'_(\d+)', filename)
        if match:
            chapter_num = int(match.group(1))
            if min_chapter <= chapter_num <= max_chapter:
                chapter_files.append((chapter_num, filepath))

    chapter_files.sort(key=lambda x: x[0])
    if start_chapter > end_chapter:
        chapter_files.reverse()

    if not chapter_files:
        print(f"在文件夹 {novels_folder} 中没有找到从第 {start_chapter} 章到第 {end_chapter} 章的小说文件。")

    return chapter_files


def get_chapter_details(filepath: str, neat_index: bool = True, verbose: bool = True) -> Tuple[str, str, str, str]:
    """从 .md 文件中提取章节序号、标题、正文和作者说。

    Args:
        filepath: 章节文件路径
        neat_index: 为 True 时返回补零序号 (如 "001")，为 False 时返回纯数字 (如 "1")
    """
    basename = os.path.basename(filepath)
    filename, _ = os.path.splitext(basename)

    match = re.search(r'_(\d+)', filename)
    if match:
        chapter_num = match.group(1)
    else:
        raise ValueError(f"文件名 {filename} 格式错误，未找到章节序号。")

    with open(filepath, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
        if first_line.find('：') == -1:
            c_index = first_line.find('章') + 1
            chapter_title = first_line[c_index + 1:]
        else:
            if first_line.startswith('#'):
                chapter_title = first_line.lstrip('# ').split('：', 1)[-1]
            else:
                chapter_title = first_line.split('：', 1)[-1] if '：' in first_line else first_line

        content = f.read()
        if '@作者说：' in content:
            content, writer_said_content = content.split('@作者说：')
        else:
            writer_said_content = ''

    if verbose:
        print(f"读取章节: 第{chapter_num}章 - {chapter_title}")
    if not neat_index:
        chapter_num = str(int(chapter_num))
    return chapter_num, chapter_title, content, writer_said_content


def count_chinese_characters(text: str) -> int:
    """统计文本中的中文字符数量，只计算中文字符和标准标点符号。
    忽略 Markdown 符号、换行符等特殊符号。
    """
    if not text:
        return 0
    chinese_chars = []
    text = text.replace('\n', '').replace(' ', '')
    for char in text:
        try:
            if 'CJK' in unicodedata.name(char):
                chinese_chars.append(char)
            elif char.isascii():
                chinese_chars.append(char)
            elif char in '，。！？；：""''…（）【】《》、-%.':
                chinese_chars.append(char)
            else:
                pass
        except:
            pass
    return len(chinese_chars)


def check_repeat_content(content: str) -> str:
    """检查内容是否包含重复的中文字符，返回去重后的内容。"""
    min_length = 30
    while len(content) >= min_length * 2:
        if content[:min_length] in content[min_length:]:
            if content[:min_length + 1] not in content[min_length + 1:]:
                print(f"发现重复内容:\n {content[:min_length]}")
                return content[min_length:]
        min_length += 1
    print("未发现简单重复内容，请手动查验")
    return content
