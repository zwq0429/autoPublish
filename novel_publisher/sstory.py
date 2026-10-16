"""番茄短故事自动发布器"""

import os
import re
import threading
import traceback
import inspect

from playwright.sync_api import sync_playwright, Page
import tkinter as tk
from tkinter import scrolledtext, messagebox

from novel_publisher.browser import BROWSER_ARGS, BROWSER_IGNORE_ARGS, DEFAULT_USER_AGENT
from novel_publisher.navigation import handle_fanqie_floats, FANQIE_STORY_LIST_SELECTOR


class FanqieSStoryAutoPublisher:
    def __init__(self, browser_path, site_url, writer, auth_file):
        self.browser_path = browser_path
        self.site_url = site_url
        self.writer = writer
        self.auth_file = auth_file

    def publish(self, parsed_info):
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=False, 
                    executable_path=self.browser_path if self.browser_path else None,
                    args=[
                        "--disable-popup-blocking",  # 禁用弹窗拦截
                        "--disable-web-security",  # 禁用网页安全策略
                        "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                        "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                    ],
                    ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                )
                if not os.path.exists(self.auth_file):
                    messagebox.showerror("错误", f"未找到认证文件 {self.auth_file} 请先执行登录操作")
                    return
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=self.auth_file)
                page = context.new_page()
                print("导航到作者后台...")
                page.goto(self.site_url, timeout=60000, wait_until='domcontentloaded')
                print("点击进入短故事列表页面...")
                novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(2)'
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
                page.wait_for_load_state('load')
                if page.get_by_text(parsed_info['短故事名称']).count() > 0:
                    print(f"短故事名称 {parsed_info['短故事名称']} 已存在")
                    #self.auto_sign(page)
                    return False

                page.get_by_role('button', name='新建短故事').click(timeout=1500)
                with context.expect_page() as new_page_info:
                    publish_page = new_page_info.value
                    publish_page.wait_for_load_state('networkidle')
                print("已切换到新的发布页面。")
                
                input_element = publish_page.locator('#app > div > div > div > div.publish-short-body > div.editor.publish-short-editor > div.serial-editor-container.notranslate > div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror.payNode-helper-content')
                while True:
                    try:
                        input_element.click(force=True, timeout=1500)
                        publish_page.wait_for_timeout(1500)
                        input_element.fill(parsed_info['正文'], timeout=5500)
                        break
                    except Exception:
                        print("正文输入框失败，重试...")
                        continue

                publish_page.get_by_placeholder('请输入短故事名称').fill(parsed_info['短故事名称'], timeout=1500)
                publish_page.locator('div.publish-short-block-item.publish_short_config_use_ai > div > div.publish-short-block-item-content > div > label:nth-child(2) > span.arco-radio-text').click(timeout=1500)

                publish_page.locator('div.publish-short-block-item.publish-short-config-pay > div > div.publish-short-block-item-content > button').click(timeout=1500)
                publish_page.locator(f"div.payNode-helper-wrap > div > div:nth-child({parsed_info['付费点']}) > div").click(timeout=5000)

                publish_page.locator('div.publish-short-block-item.publish-short-config-signLicense > div > div.publish-short-block-item-content > div:nth-child(1) > label > span > div').click(timeout=5000)
                publish_page.get_by_role('button', name='我已阅读并同意').click(timeout=5000)

                publish_page.locator('div.publish-short-block-item.publish-short-config-cover > div > div.publish-short-block-item-content > div.publish-short-config-cover-container > div > div').click(timeout=1500)
                publish_page.wait_for_load_state('load')
                if parsed_info['封面路径'] is not None:
                    publish_page.locator('#arco-tabs-1-tab-1 > span').get_by_text('本地上传').click(timeout=1500)
                    file_input = publish_page.locator('#arco-tabs-1-panel-1 input[type="file"]')
                    file_input.set_input_files(parsed_info['封面路径'])
                    publish_page.locator('#arco-tabs-1-panel-1').get_by_text('确认上传', exact=True).click(timeout=1500)
                    publish_page.wait_for_timeout(3000)
                    publish_page.wait_for_load_state('networkidle')
                    publish_page.locator('#arco-tabs-1-panel-1').get_by_text('确定', exact=True).click(timeout=1500)
                else:
                    try:
                        publish_page.wait_for_timeout(3000)
                        publish_page.locator('div.make-cover-deal > div.make-cover-deal-wrap > div.make-cover-deal-wrap-template > div > ul > li.story-template-list-item.story-template-list-item-active > img').click(timeout=1500)
                        publish_page.wait_for_timeout(3000)
                        publish_page.wait_for_load_state('load')
                        publish_page.get_by_text('完成制作', exact=True).click(timeout=4500)
                        publish_page.wait_for_timeout(3000)
                        publish_page.wait_for_load_state('load')
                    except Exception as e:
                        raise e

                publish_page.wait_for_selector('div.publish-short-block-item.publish-short-config-category > div > div.publish-short-block-item-content > div.publish-short-category-select', timeout=5000)
                publish_page.locator('div.publish-short-block-item.publish-short-config-category > div > div.publish-short-block-item-content > div.publish-short-category-select').click(timeout=1500)
                publish_page.wait_for_load_state('domcontentloaded')
                for key, value in parsed_info['标签'].items():
                    try:
                        publish_page.locator('div.publish-short-block-item.publish-short-config-category').get_by_text(key, exact=True).click(timeout=1500)
                        publish_page.wait_for_load_state('domcontentloaded')
                        publish_page.locator('div.publish-short-block-item.publish-short-config-category').get_by_text(value, exact=True).click(timeout=1500)
                    except Exception as e:
                        print(f"未找到标签 {key} 或 {value}，跳过...")
                        continue
                publish_page.get_by_role('button', name='下一步').click(timeout=3500)
                publish_page.get_by_text('继续发布', exact=True).click(timeout=3500)
                publish_page.wait_for_load_state('load')
                publish_page.locator("div.arco-modal-wrapper.arco-modal-wrapper-align-center").get_by_role('button', name='确定').click(timeout=1500)
                publish_page.wait_for_timeout(5000)
                publish_page.wait_for_load_state('load')
                if publish_page.get_by_text('发布成功').is_visible():
                    print("发布成功")
                    return True
                else:
                    print("发布失败, 请手动检查发布结果")
                    return False

            except Exception:
                traceback.print_exc()
                self.debug()
                return False

    def auto_sign(self, page: Page):
        page.get_by_role('button', name='签约管理').click(timeout=1500)
        if os.path.exists('签约信息.txt'):
            with open('签约信息.txt', 'r', encoding='utf-8') as f:
                auth_data = f.readlines()
            print(f"签约信息加载成功!")
            # 提取签约信息
            i=0
            for _ in range(len(auth_data)//8):
                author_name = auth_data[i].strip().split("：")[1]
                if author_name != self.writer:
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

                    while page.get_by_text('可申请签约').count()+page.get_by_text('未签约').count() > 0:
                        self.debug()
                        page.wait_for_timeout(60000)
                    break
        else:
            print("缺少签约信息文件")
            print("请在项目根目录下创建’签约信息.txt‘文件")
            print("格式为——\n笔名：XXXX\n- 电话：13800000000\n- 邮箱：123@xx.com\n- QQ账号：123456789\n- 联系地址：辽宁-沈阳 or 上海-上海 \n- 详细地址：XXXXXX\n- 银行卡号：XXXXXXXXXXXXXXXX\n- 所属支行：XXXX")
            print("笔名作为二次验证，需要和界面填写一致")

    def parse_story_info(self, story_text, cover_path=None):
        """解析短故事文本，提取作品名称和内容"""
        story_info = {
            '短故事名称': '',
            '标签': {},
            '正文': '',
            '付费点': 250,
            '封面路径': cover_path
        }
        story_text = story_text.replace('*', '').replace('#', '').replace('-', '').replace('>', '').replace(' ', '')
        # 中文化
        story_text = story_text.replace(':', '：').replace(',', '，').replace('\'', '‘').replace('\"', '“').replace('(', '（').replace(')', '）')
        title_match = re.search(r'短故事名称：《\s*(.+?)\s*》', story_text, re.DOTALL)
        content_match = re.search(r'正文内容：\s*(.+?)\s*标签信息：', story_text, re.DOTALL)
        tag_match = re.search(r'标签信息：\s*(.+?)\s*$', story_text, re.DOTALL)

        if title_match:
            story_info['短故事名称'] = title_match.group(1).strip()
        else:
            story_info['短故事名称'] = '未知'
        if content_match:
            story_info['正文'] = content_match.group(1).strip().replace('\n\n', '\n')
        else:
            print(f'未找到正文内容，使用全部内容作为正文')
            story_info['正文'] = story_text.replace('\n\n', '\n')
        
        if '===付费点===' in story_info['正文']:
            story_info['付费点'] = len(story_info['正文'].split('===付费点===')[0].split('\n'))
            story_info['正文'] = story_info['正文'].replace('===付费点===', '')
        else:
            print(f'未找到付费点信息，使用默认值60%为付费卡点')
            story_info['付费点'] = int(len(story_info['正文'].split('\n'))*0.6)
        
        if tag_match:
            main_category_match = re.search(r'主分类：\s*(.+?)\s*$', story_text, re.MULTILINE)
            if main_category_match:
                story_info['标签']['主分类'] = main_category_match.group(1).strip()
            sub_category_1_match = re.search(r'情节：\s*(.+?)\s*$', story_text, re.MULTILINE)
            if sub_category_1_match:
                story_info['标签']['情节'] = sub_category_1_match.group(1).strip()
            sub_category_2_match = re.search(r'角色：\s*(.+?)\s*$', story_text, re.MULTILINE)
            if sub_category_2_match:
                story_info['标签']['角色'] = sub_category_2_match.group(1).strip()
            sub_category_3_match = re.search(r'情绪：\s*(.+?)\s*$', story_text, re.MULTILINE)
            if sub_category_3_match:
                story_info['标签']['情绪'] = sub_category_3_match.group(1).strip()
            sub_category_4_match = re.search(r'背景：\s*(.+?)\s*$', story_text, re.MULTILINE)
            if sub_category_4_match:
                story_info['标签']['背景'] = sub_category_4_match.group(1).strip()
        else:
            print(f'未找到标签信息，使用默认值其他')
            story_info['标签']['主分类'] = '其他'
        
        print(f'解析结果: \n标题：{story_info["短故事名称"]} \n封面路径：{story_info["封面路径"]} \n \n正文：{story_info["正文"][:50]}...... \n标签：{story_info["标签"]}')
        return story_info

    def debug(self):
        import inspect
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
                exec(code, exec_namespace, exec_namespace)
            except Exception:
                traceback.print_exc()
