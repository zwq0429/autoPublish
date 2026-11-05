"""晋江文学城发布逻辑。

提取自 app.py：
- publish_single_chapter <- NovelPublisherApp.publish_single_chapter_on_jinjiangnovel
- run_publish            <- NovelPublisherApp.automation_flow_by_jinjiangnovel
"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, update_button) -> bool:
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
    update_button.click(timeout=3000)
    try:
        with context.expect_page() as new_page_info:
            publish_page = new_page_info.value
            publish_page.wait_for_load_state('networkidle')
            print("已切换到新的发布页面。")
        # print(publish_page.url)
        # print("调试模式已开启，输入q退出")
        # while True:
        #     try:
        #         command = input("@")
        #         if command == 'q':
        #             break
        #         eval(command)
        #     except Exception as e:
        #         print(f"error: {e}")
        # --- 在新页面上执行操作 ---
        # 预先点击去除新手引导
        try:
            publish_page.get_by_text("我知道了").click(timeout=3000)
        except:
            pass
        # publish_page.click('body')
        print(f"校对章节序号: {chapter_num}")
        if publish_page.get_by_placeholder(f"第{int(chapter_num)}章").count() == 0:
            print(f"错误：章节 {chapter_num} 序号有误！")
            return False

        print(f"填写章节标题: {chapter_title}")
        publish_page.get_by_placeholder(f"第{int(chapter_num)}章").fill(chapter_title.strip(), timeout=3000)

        print("粘贴章节正文...")
        publish_page.wait_for_selector('#chapterbody', timeout=10000)
        publish_page.fill('#chapterbody', chapter_content)
        publish_page.wait_for_timeout(3000)

        if writer_said_content is not None and writer_said_content.strip() != '':
            print("填写作者说...")
            publish_page.fill('#note', writer_said_content.strip())

        if publish_mode == '立刻发布':
            publish_page.get_by_role("button", name="直接发表").click(timeout=3000)
        else:
            publish_page.get_by_role("button", name="放入存稿箱").click(timeout=3000)
            if publish_mode == '定时发布':
                print("定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M:%S'))
                publish_page.get_by_placeholder("设置发表时间").fill(state.publish_time.strftime('%Y-%m-%d %H:%M:%S'), timeout=3000)
                publish_page.get_by_role("button", name="批量提交").click(timeout=3000)
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
     daily_publish_count, daily_publish_num, interval_days, interval_tag) = state.cfg.as_tuple()

    with sync_playwright() as p:
        browser, context = open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE, on_browser_not_found=None)
        page = context.new_page()
        try:
            # 特殊部分
            print("导航到作者后台...")
            page.goto(site_url, timeout=60000, wait_until='networkidle')
            if page.locator(f"tr:has(a:text-is('{novel_title}'))").count() == 0:
                print(f"错误：在列表中未找到小说 '{novel_title}'")
                return False
            else:
                print(f"找到小说 《{novel_title}》")
                print('准备更新素材...')
            update_button = page.locator(f"tr:has(a:text-is('{novel_title}'))").get_by_text('点我更新')

            list_count = len(novel_files)
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, page, chapter_details, update_button):
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
                        if daily_publish_num <= 0:
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
