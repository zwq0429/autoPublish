"""起点：单章发布与完整发布流程（提取自 app.py）。

原方法对应关系：
  - publish_single_chapter <- NovelPublisherApp.publish_single_chapter_on_qidiannovel
  - run_publish            <- NovelPublisherApp.automation_flow_by_qidiannovel
"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, write_button, chapter_details: tuple) -> bool:
    """发布单个章节"""
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
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
                print("定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M'))
                # 先选择时间，不然不允许点击日期
                time_input_value = state.publish_time.strftime('%H:%M')
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
                while month_text != state.publish_time.strftime('%Y-%m'):
                    publish_page.click('div > div.ui-date-head > a.ui-date-next') # 目前只能选择下个月
                    publish_page.wait_for_timeout(500)
                    month_text = publish_page.query_selector('div.ui-date-head > a.ui-date-switch').inner_text()

                date_input_value = state.publish_time.strftime('%Y-%m-%d')
                day_number = state.publish_time.day
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


def run_publish(state) -> bool:
    (custom_browser_path, site_url,
     novel_title, novels_folder,
     publish_mode, start_chapter,
     end_chapter, keep_browser_open,
     novel_files, init_daily_publish_count, init_daily_publish_num,
     daily_publish_count, daily_publish_num) = state.cfg.as_tuple()

    with sync_playwright() as p:
        browser, context = open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE, on_browser_not_found=None)
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
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, write_button, chapter_details):
                    print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                    break
                if publish_mode == '定时发布':
                    if init_daily_publish_num == -1:
                        # 起点特殊的计数方式
                        chapter_word_count = state.count_chinese_characters(chapter_details[2]) // 1000 * 1000
                        daily_publish_count -= chapter_word_count
                        print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                        if daily_publish_count <= 0:
                            daily_publish_count = init_daily_publish_count
                            state.publish_time += datetime.timedelta(days=1)
                    else:
                        daily_publish_num -= 1
                        print(f"本日还差发布{daily_publish_num}章")
                        if daily_publish_num <=  0:
                            daily_publish_num = init_daily_publish_num
                            state.publish_time += datetime.timedelta(days=1)

                list_count -= 1
                if list_count > 0:
                    print(f"本次任务剩余{list_count}章")
                    print("准备发布下一章...")
                page.wait_for_timeout(3000)
            browser.close()

            state.save_history(list_count, daily_publish_num, daily_publish_count, end_chapter, publish_mode)
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
