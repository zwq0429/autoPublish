"""咪咕平台发布逻辑。

提取自 app.py：
- publish_single_chapter <- NovelPublisherApp.publish_single_chapter_on_migunovel
- run_publish            <- NovelPublisherApp.automation_flow_by_migunovel

注意：原 automation_flow_by_migunovel 中发布单章调用的是
publish_single_chapter_on_xirangnovel（未传 add_var 参数），此处忠实保留原调用方式。
"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE
from novel_publisher.platforms.xirang import publish_single_chapter as _xirang_publish_single_chapter


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
    # update_button.click(timeout=3000)
    try:
        # print(page.url)
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
        # publish_page.click('body')
        print(f"当前章节序号: {chapter_num}")
        print(f"填写章节标题: {chapter_title}")
        page.get_by_placeholder("这里请输入章节号与章节名。示例：第一章 天降奇缘").fill(f"第{chapter_num}章 {chapter_title.strip()}", timeout=3000)

        print("粘贴章节正文...")
        page.get_by_placeholder("这里请输入正文").fill(chapter_content, timeout=3000)
        page.wait_for_timeout(3000)

        # if writer_said_content is not None and writer_said_content.strip() != '':
        #     print("填写作者说...")
        #     publish_page.fill('#note', writer_said_content.strip())
        if publish_mode == '保存为草稿':
            page.get_by_text("存入草稿", exact=True).click(timeout=3000)
        else:
            page.get_by_text("发布", exact=True).click(timeout=3000)
            if publish_mode == '立刻发布':
                page.get_by_role("radio", name="立即").click(timeout=3000, force=True)
            else:
                page.get_by_role("radio", name="定时发布").click(timeout=3000, force=True)
                page.wait_for_timeout(1500)
                print("定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M:%S'))
                date_input = page.get_by_placeholder("选择日期")
                date_input.fill(state.publish_time.strftime('%Y-%m-%d'), timeout=3000)
                date_input.press('Enter')
                time_input = page.get_by_placeholder("选择时间")
                time_input.fill(state.publish_time.strftime('%H:%M'), timeout=3000)
                time_input.press('Enter')

            page.click('#app > div > div.mainwarp > div > div.dialog_warp > div > div > div.el-dialog__body > div.d_footer > button', timeout=3000)

        print(f"--- 第{chapter_num}章发布成功！---")
        print("等待60秒，确保发布完成并避免显示发布频繁(息壤机制)...")
        page.wait_for_timeout(60000)
        page.reload()


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
            print("导航到作者后台...")
            page.goto(site_url, timeout=60000, wait_until='networkidle')
            print("点击进入小说列表页面...")
            try:
                page.get_by_text("作品管理", exact=True).first.click(timeout=3000)  # 延长点击超时
                page.wait_for_timeout(3000)
                page.wait_for_load_state('load')
            except Exception as e:
                print(f"点击小说列表导航元素时发生错误: {e}")
                # raise  # 重新抛出异常以便上层捕获
            if page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").count() == 0:
                print(f"错误：在列表中未找到小说 '《{novel_title}》'")
                return False
            else:
                print(f"找到小说 《{novel_title}》")
                print('准备更新素材...')
                update_button = page.locator(f".list_view:has(.novel_name:text('{novel_title}'))").get_by_text("去创作", exact=True)
                update_button.click(timeout=1500)

            list_count = len(novel_files)
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                if not _xirang_publish_single_chapter(state, publish_mode, context, page, chapter_details, update_button):
                    print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                    break
                if publish_mode == '定时发布':
                    if daily_publish_num > 0:
                        daily_publish_num -= 1
                        print(f"本日还差发布{daily_publish_num}章")
                    elif daily_publish_num == 0:
                        daily_publish_num = init_daily_publish_num
                        state.publish_time += datetime.timedelta(days=1)
                    else:
                        if daily_publish_count <= 0:
                            daily_publish_count = init_daily_publish_count
                            state.publish_time += datetime.timedelta(days=1)
                        else:
                            daily_publish_count -= state.count_chinese_characters(chapter_details[2])
                            print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")

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
