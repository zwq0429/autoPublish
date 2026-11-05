"""飞卢小说平台发布流程（提取自 app.py，逻辑保持一致）。"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, daily_publish_num: int) -> bool:
    """发布单个章节，处理新打开的页面，并在完成后关闭。"""
    print('飞卢暂不支持定时发布')
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
        return False
    publish_page = page
    try:
        # 使用更稳定的方式查找小说并点击更新
        print("先分卷")
        publish_page.locator("#nodeForm > div.nodeFormRegion > div:nth-child(1) > div > select").select_option("2")
        # publish_page.locator("#nodeForm > div.nodeFormRegion > div:nth-child(1) > div > select > option:nth-child(2)").click()
        print("填写章节标题...")
        publish_page.get_by_placeholder("请填写标题").fill(f"第{chapter_num}章 {chapter_title.strip()}")
        print("粘贴章节正文...")
        publish_page.get_by_placeholder("注：章节内容里请不要含章节标题").fill(chapter_content)
        print("添加小说章节...")
        publish_page.get_by_role("button", name="添加小说章节").click()
        publish_page.wait_for_timeout(3000)
        print(f"--- 第{chapter_num}章发布成功！---")
        publish_page.get_by_text("继续添新").click(timeout=3000)
        publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成

    except Exception as e:
        print(f"发布第{chapter_num}章时发生错误: {e}")
        traceback.print_exc()
        return False
    else:
        # if publish_page:
        #     print("关闭章节发布页面...")
        #     publish_page.close()
        return True


def run_publish(state) -> bool:
    (custom_browser_path, site_url,
     novel_title, novels_folder,
     publish_mode, start_chapter,
     end_chapter, keep_browser_open,
     novel_files, init_daily_publish_count, init_daily_publish_num,
     daily_publish_count, daily_publish_num,
     _interval_days, _interval_tag) = state.cfg.as_tuple()

    with sync_playwright() as p:
        browser, context = open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE, on_browser_not_found=None)
        page = context.new_page()

        try:
            print("导航到作者后台...")
            page.goto(site_url, timeout=60000, wait_until='networkidle')
            write_button = None
            # 直接查找小说标题(因为一般七猫也应该是单开，先查找工作台首页所需发布的书籍)
            # page.wait_for_selector('', timeout=60000)
            try:
                page.query_selector('body > div.zheZhao.zheZhao2.show > div > div.zz_listen_close').click(timeout=1500)
            except Exception as e:
                pass
            actual_title = page.query_selector('body > div:nth-child(7) > div.mo_opus').inner_text()
            print(f"当前页面小说标题: '{actual_title}'")
            if novel_title in actual_title:
                print(f"已找到小说: '{novel_title}'")
                # write_button = page.get_by_text('章节管理')
                write_button = page.locator('body > div:nth-child(7) > div.mo_opus > div.mo_o_layer2 > div.btnList.clearfix > a:nth-child(3)')
            else:
                pass
            write_button.click(timeout=1500) # 点击新建章节按钮
            publish_page = None
            with context.expect_page() as new_page_info:
                publish_page = new_page_info.value
                publish_page.wait_for_load_state('networkidle')
                print("已切换到新的发布页面。")

            list_count = len(novel_files)
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, publish_page, chapter_details, daily_publish_num):
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
                    # 回到首页
                list_count -= 1
                if list_count > 0:
                    print(f"本次任务剩余{list_count}章")
                    print("准备发布下一章...")

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
