"""小说信息解析（创书用）"""

import re

def _match_field(input_text: str, field_name: str):
    return re.search(r'(?:^|\n)\s*(?:-\s*)?%s：\s*(.+?)\s*(?=\n|$)' % re.escape(field_name), input_text, re.DOTALL)


def _split_tags(text: str):
    return [x.strip() for x in text.strip().split('，') if x.strip()]


def parse_novel_info(input_text: str, publish_plate: str) -> dict:
    """解析用户输入的小说信息，返回结构化字典。

    支持 '番茄'、'七猫'、'书旗' 三种格式。
    """
    print("解析小说信息...")

    if publish_plate == '七猫':
        parsed_info = {}
        input_text = input_text.replace(':', '：').replace(',', '，')
        target_match = re.search(r'作品名称：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['作品名称'] = target_match.group(1).strip()
        else:
            parsed_info['作品名称'] = '未命名小说'
        target_match = re.search(r'目标名称：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['目标名称'] = target_match.group(1).strip()
        else:
            parsed_info['目标名称'] = '未知频道'
        if '作品分类：' in input_text:
            parsed_info['作品分类'] = {}
            target_match = re.search(r'一级分类：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品分类']['一级分类'] = target_match.group(1).strip()
            else:
                parsed_info['作品分类']['一级分类'] = '未知分类'
            target_match = re.search(r'二级分类：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品分类']['二级分类'] = target_match.group(1).strip()
            else:
                parsed_info['作品分类']['二级分类'] = '未知分类'
        if '作品标签：' in input_text:
            parsed_info['作品标签'] = {}
            target_match = re.search(r'风格：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品标签']['风格'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['作品标签']['风格'] = '未知风格'
            target_match = re.search(r'角色：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品标签']['角色'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['作品标签']['角色'] = '未知角色'
            target_match = re.search(r'情节：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品标签']['情节'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['作品标签']['情节'] = '未知情节'
            target_match = re.search(r'背景：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['作品标签']['背景'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['作品标签']['背景'] = '未知背景'

        target_match = re.search(r'主角名：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['主角名'] = target_match.group(1).strip().split('，')
        else:
            parsed_info['主角名'] = ['未知']

        target_match = re.search(r'作品简介：\s*(.+?)\s*$', input_text, re.DOTALL)
        if target_match:
            parsed_info['作品简介'] = target_match.group(1).strip()
        else:
            parsed_info['作品简介'] = ''
        return parsed_info

    elif publish_plate == '番茄':
        parsed_info = {}
        if input_text == '':
            print("输入为空，执行占位操作")
            return parsed_info
        input_text = input_text.replace(':', '：').replace(',', '，')
        target_match = _match_field(input_text, '书本名称')
        if target_match:
            parsed_info['书本名称'] = target_match.group(1).strip()
        else:
            parsed_info['书本名称'] = '未命名小说'
        target_match = _match_field(input_text, '目标名称')
        if target_match:
            parsed_info['目标名称'] = target_match.group(1).strip()
        else:
            target_match = _match_field(input_text, '目标读者')
            if target_match:
                parsed_info['目标名称'] = target_match.group(1).strip()
            else:
                raise ValueError("未找到目标名称或目标读者")
        if '阅读标签：' in input_text:
            parsed_info['阅读标签'] = {}
            read_block = input_text.split('阅读标签：', 1)[1]
            if '内容标签：' in read_block:
                read_block = read_block.split('内容标签：', 1)[0]
            for key in ('主分类', '主题', '角色', '情节'):
                target_match = _match_field(read_block, key)
                if target_match:
                    value = target_match.group(1).strip()
                    parsed_info['阅读标签'][key] = value if key == '主分类' else _split_tags(value)
                else:
                    parsed_info['阅读标签'][key] = '未知分类' if key == '主分类' else '未知%s' % key

        if '内容标签：' in input_text:
            parsed_info['内容标签'] = {}
            content_block = input_text.split('内容标签：', 1)[1]
            if '主角：' in content_block:
                content_block = content_block.split('主角：', 1)[0]
            for key in ('情节', '人设', '情感', '世界观'):
                target_match = _match_field(content_block, key)
                if target_match:
                    parsed_info['内容标签'][key] = _split_tags(target_match.group(1))
                else:
                    parsed_info['内容标签'][key] = []
        else:
            parsed_info['内容标签'] = {'情节': [], '人设': [], '情感': [], '世界观': []}

        target_match = _match_field(input_text, '主角')
        if target_match:
            parsed_info['主角'] = _split_tags(target_match.group(1))
        else:
            parsed_info['主角'] = ['未知']

        target_match = re.search(r'作品简介：\s*(.+?)\s*$', input_text, re.DOTALL)
        if target_match:
            parsed_info['作品简介'] = target_match.group(1).strip()
        else:
            parsed_info['作品简介'] = ''
        # print(parsed_info)
        return parsed_info

    elif publish_plate == '书旗':
        parsed_info = {}
        input_text = input_text.replace(':', '：').replace(',', '，')
        target_match = re.search(r'书本名称：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['书本名称'] = target_match.group(1).strip()
        else:
            parsed_info['书本名称'] = '未命名小说'
        target_match = re.search(r'目标名称：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['目标名称'] = target_match.group(1).strip()
        else:
            parsed_info['目标名称'] = '未知频道'
        if '标签：' in input_text:
            parsed_info['标签'] = {}
            target_match = re.search(r'主分类：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['标签']['主分类'] = target_match.group(1).strip()
            else:
                parsed_info['标签']['主分类'] = '未知分类'
            target_match = re.search(r'主题：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['标签']['主题'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['标签']['主题'] = '未知主题'
            target_match = re.search(r'角色：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['标签']['角色'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['标签']['角色'] = '未知角色'
            target_match = re.search(r'情节：\s*(.+?)\s*\n', input_text, re.DOTALL)
            if target_match:
                parsed_info['标签']['情节'] = target_match.group(1).strip().split('，')
            else:
                parsed_info['标签']['情节'] = '未知情节'

        target_match = re.search(r'主角：\s*(.+?)\s*\n', input_text, re.DOTALL)
        if target_match:
            parsed_info['主角'] = target_match.group(1).strip().split('，')
        else:
            parsed_info['主角'] = '未知'

        target_match = re.search(r'作品简介：\s*(.+?)\s*$', input_text, re.DOTALL)
        if target_match:
            parsed_info['作品简介'] = target_match.group(1).strip()
        else:
            parsed_info['作品简介'] = ''
        return parsed_info

    return {}


def parse_outline_file(content: str) -> dict:
    """解析 &&&键值&&& 格式的大纲文件。

    文件格式：
        &&&键值1&&&
        内容1
        &&&键值2&&&
        内容2
        ...

    Returns:
        dict: {键值1: 内容1, 键值2: 内容2, ...}
    """
    result = {}
    # 按 &&&...&&& 分割
    pattern = re.compile(r'&&&(.+?)&&&')
    parts = pattern.split(content)
    # split 结果: [前导文本, 键值1, 内容1, 键值2, 内容2, ...]
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            key = parts[i].strip()
            value = parts[i + 1].strip()
            result[key] = value
    return result


def load_outline_from_dir(directory: str = '.') -> dict:
    """从目录中读取以 '大纲.txt' 结尾的文件，返回解析后的字典。

    如果找到多个文件，合并所有键值对（后出现的覆盖先出现的）。
    Returns:
        dict: 解析后的键值字典，如果未找到文件则返回空字典
    """
    import os
    result = {}
    for f in os.listdir(directory):
        if f.endswith('大纲.txt'):
            filepath = os.path.join(directory, f)
            print(f"读取大纲文件: {filepath}")
            with open(filepath, 'r', encoding='utf-8') as fp:
                content = fp.read()
            parsed = parse_outline_file(content)
            result.update(parsed)
            print(f"从 {f} 解析到键值: {list(parsed.keys())}")
    return result
