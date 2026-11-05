"""书旗：单章发布与完整发布流程（提取自 app.py）。

原方法对应关系：
  - publish_single_chapter <- NovelPublisherApp.publish_single_chapter_on_shuqinovel
  - run_publish            <- NovelPublisherApp.automation_flow_by_shuqinovel
"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str) -> bool:
    """发布单个章节，处理新打开的页面，并在完成后关闭。"""
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    writer_said_content = chapter_details[3]
    if writer_said_content is not None and writer_said_content.strip() != '':
        print(f"章节 {chapter_num} 包含作者说!")
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
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
            if state.count_chinese_characters(writer_said_content.strip()) > 300:
                print(f"错误：章节 {chapter_num} 作者说内容超过300个中文字符，无法发布！")
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
                date_input.fill(state.publish_time.strftime('%Y-%m-%d'), timeout=3000)
                date_input.press('Enter')
                time_button = page.get_by_placeholder('请选择时间').first
                time_button.click(timeout=3000)
                time_input = page.get_by_placeholder('请选择时间').last
                time_input.fill(state.publish_time.strftime('%H:%M'), timeout=3000)
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
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, page, chapter_details, novel_title):
                    print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                    break
                if publish_mode == '定时发布':
                    if init_daily_publish_num == -1:
                        daily_publish_count -= state.count_chinese_characters(chapter_details[2])
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
            state.error_hint()
            return False
