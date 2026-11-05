"""根据简介/大纲创建新书 CLI。

来源: app.py 行 5268-5629
  - create_book_from_outline (5268-5309)：读取大纲/信息文件中的"开书信息"
  - parse_novel_info (5308-5311)：已迁至 novel_publisher.create_book.parse_novel_info
  - _execute_create_book (5313-5629)：浏览器自动化建书核心流程

去 UI 化说明:
  - 开书信息来源: --info-file 指定的文本文件（内容格式与 parse_novel_info 的输入一致）；
    未指定时回退为原逻辑：从 --outline-dir 中读取以"大纲.txt"结尾的文件，
    提取"开书信息"键值（load_outline_from_dir）；
  - self.xxx_var 等 UI 变量改由命令行参数替代，缺省回退 config.ini：
      publish_plate_var        -> --platform（默认取 [Settings] publish_plate）
      novel_writer_var         -> --writer（默认取 [Novel] novel_writer，书本名称为空时拼占位书名）
      novel_title_var（旧书名） -> config.ini [Novel] novel_title（用于查找待修改的占位书）
      custom_browser_path_var  -> --browser-path（默认取 [Settings] custom_browser_path）
      keep_browser_open_var    -> --keep-browser-open（默认取 [Settings] close_browser_open）
  - messagebox 改为 print；
  - 原 self._get_site_url() 改用 novel_publisher.navigation.get_site_url；
  - 原 self._normal_open_browser(p, ...) 改用 novel_publisher.browser.open_browser
    （app 中该方法即委托于此，登录态同样使用 'auth.json'）；
  - 浏览器操作逻辑（选择器、等待时间、重试次数）逐行保留。
"""

import configparser
import datetime
import os
import traceback

from playwright.sync_api import sync_playwright

from novel_publisher.browser import open_browser as _open_browser
from novel_publisher.create_book import load_outline_from_dir, parse_novel_info
from novel_publisher.navigation import get_site_url

# 项目根目录（cli/ 的上一级），与 app.py 的 CONFIG_FILE/AUTH_FILE 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, 'config.ini')
AUTH_FILE = 'auth.json'


def _read_config(section, key, fallback=''):
    """从项目根目录 config.ini 读取配置项。"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
    return config.get(section, key, fallback=fallback)


def _read_config_bool(section, key, fallback=False):
    """从项目根目录 config.ini 读取布尔配置项。"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
    return config.getboolean(section, key, fallback=fallback)


def _save_created_status(novel_title=None):
    """原 self.novel_status = '已创建' + self.save_config(False) 的去 UI 化版本。

    将 novel_title / novel_status 写回项目根目录 config.ini（保留其他配置项）。
    """
    try:
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE, encoding='utf-8')
        if not config.has_section('Novel'):
            config['Novel'] = {}
        if novel_title:
            config['Novel']['novel_title'] = novel_title
        config['Novel']['novel_status'] = '已创建'
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
    except Exception as e:
        print(f"保存配置失败: {e}")
        return
    print("创书完成，已保存配置。小说状态: 已创建")


def register(subparsers):
    """向 argparse 子命令注册参数。subparsers 是 create-book 命令的 parser。"""
    subparsers.add_argument(
        '--info-file', default=None,
        help='小说信息文本文件路径（内容格式与 parse_novel_info 的输入一致）')
    subparsers.add_argument(
        '--outline-dir', default='.',
        help="大纲文件夹（默认 '.'；未指定 --info-file 时从中读取以'大纲.txt'结尾文件的'开书信息'键值）")
    subparsers.add_argument(
        '--platform', default=None,
        help='发布平台：番茄/七猫等（默认取 config.ini 的 [Settings] publish_plate）')
    subparsers.add_argument(
        '--browser-path', default=None,
        help='浏览器路径或CDP端口（默认取 config.ini 的 [Settings] custom_browser_path）')
    subparsers.add_argument(
        '--writer', default=None,
        help='作者笔名，书本名称为空时用于生成占位书名（默认取 config.ini 的 [Novel] novel_writer）')
    subparsers.add_argument(
        '--keep-browser-open', action='store_true',
        help='保持浏览器打开/无头开关（默认取 config.ini 的 [Settings] close_browser_open）')


def main(args) -> int:
    """执行 create-book 命令，返回退出码（0 成功，非 0 失败）。"""
    publish_plate = args.platform or _read_config('Settings', 'publish_plate', fallback='番茄')
    try:
        if args.info_file:
            with open(args.info_file, 'r', encoding='utf-8') as f:
                input_text = f.read()
            print(f"已从信息文件读取开书信息: {args.info_file}")
        else:
            outline_data = load_outline_from_dir(args.outline_dir)
            if not outline_data:
                print("错误：未找到以'大纲.txt'结尾的文件")
                return 1

            input_text = outline_data.get('开书信息', '')
            if not input_text:
                print("错误：大纲文件中未找到'开书信息'键值")
                return 1

            print("已从大纲文件读取开书信息")

        parsed_info = parse_novel_info(input_text, publish_plate)

        # 原 self.xxx_var 读取，改为命令行参数 + config.ini 回退
        custom_browser_path = args.browser_path or _read_config(
            'Settings', 'custom_browser_path', fallback='(必填)允许多个账号使用同一个浏览器')
        novel_writer = args.writer if args.writer is not None else _read_config(
            'Novel', 'novel_writer', fallback='你的笔名(选填)')
        # 原 old_novel_title = self.novel_title_var.get()（修改占位书时查找用）
        old_novel_title = _read_config('Novel', 'novel_title', fallback='你的小说名(完整无误的)')
        keep_browser_open = bool(args.keep_browser_open) or _read_config_bool(
            'Settings', 'close_browser_open', fallback=False)

        ok = _execute_create_book(
            parsed_info, publish_plate, novel_writer, old_novel_title,
            custom_browser_path, keep_browser_open)
        return 0 if ok else 1
    except Exception as e:
        print(f"快速创书失败: {e}")
        traceback.print_exc()
        return 1


def _execute_create_book(parsed_info, publish_plate, novel_writer='', old_novel_title='',
                         custom_browser_path='', keep_browser_open=False):
    """
    打开浏览器执行创建书本操作（原 app.py _execute_create_book，去 UI 化）。

    返回 True 表示成功，False 表示失败。
    """
    novel_title = None
    try:
        print(f"执行创建书本操作...")
        if publish_plate == '番茄':
            # 原: old_novel_title = self.novel_title_var.get()（已由参数传入）
            if parsed_info.get('书本名称', '') == '':
                # 原: self.novel_title_var.set(f'{self.novel_writer_var.get()}...')
                novel_title = f'{novel_writer}{datetime.datetime.now().strftime("%m%d")}'
            else:
                novel_title = parsed_info['书本名称']
            site_url = get_site_url(publish_plate)
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
                    except Exception as e:
                        print(f"创建失败: {e}")
                        traceback.print_exc()
                        print(f"错误: 创建书本失败: {str(e)}")
                        return False
                page.wait_for_timeout(5000)
            print(f"提示: 创建书本操作已完成\n标题: {novel_title}")
        elif publish_plate == '七猫':
            novel_title = parsed_info['作品名称']
            site_url = get_site_url(publish_plate)
            # 这里是占位实现，实际应该调用浏览器相关的函数来创建书本
            # 示例：使用现有的浏览器操作框架
            with sync_playwright() as p:
                # 原: self._normal_open_browser(p, custom_browser_path, keep_browser_open)
                #     等价于 novel_publisher.browser.open_browser(..., AUTH_FILE)
                browser, context = _open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE)
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
                    print(f"错误: 创建书本失败: {str(e)}")
                    return False
                page.wait_for_timeout(5000)
            print(f"提示: 创建书本操作已完成\n标题: {parsed_info['作品名称']}")
        # 原: self.novel_status = '已创建'; self.save_config(False)
        _save_created_status(novel_title)
        return True
    except Exception as e:
        print(f"执行创建书本操作失败: {e}")
        traceback.print_exc()
        return False
