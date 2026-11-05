"""七猫：单章发布与完整发布流程（提取自 app.py）。

原方法对应关系：
  - publish_single_chapter <- NovelPublisherApp.publish_single_chapter_on_qimaonovel
  - run_publish            <- NovelPublisherApp.automation_flow_by_qimaonovel
"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, add_var: int) -> bool:
    """发布单个章节，处理新打开的页面，并在完成后关闭。"""
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
        return False

    publish_page = page # 七猫发布页面不会弹窗
    try:
        # 使用更稳定的方式查找小说并点击更新
        print(f"填写章节序号: {chapter_num} - 七猫有默认序号")

        print(f"填写章节标题: {chapter_title}")
        publish_page.get_by_placeholder("请输入章节名称，最多20个字").fill(chapter_title.strip())

        print("粘贴章节正文...")
        edit_path = 'div.chapter-editor > div > div > div.q-contenteditable.book.font-size-16.edit-mask'
        # 'div.chapter-editor > div > div'

        publish_page.wait_for_selector(edit_path, timeout=10000)
        publish_page.fill(edit_path, chapter_content)

        if publish_mode == '保存为草稿':
            print("保存为草稿...")
            publish_page.get_by_role("button", name="存为草稿").click()
        else:
            pulish_button = None
            # add_var = int(self.daily_publish_num_var.get()) - daily_publish_num - 1
            # 七猫不允许同时定时发布，要求一定要晚一点
            while not pulish_button:
                try:
                    if publish_mode == '定时发布':
                        # 勾选定时发布
                        # publish_page.click('div > div.card-content-line-control > div > button', timeout=3000)
                        publish_page.get_by_text("定时发布").click()
                        publish_page.wait_for_timeout(1500)
                        print("获取确认发布按钮...")
                        # 使用更可靠的选择器，避免绝对路径
                        pulish_button = publish_page.query_selector('div.el-dialog__wrapper.qm-pop div.qm-pop-tf.show-mask > a, div.el-dialog__wrapper.qm-pop div.qm-pop-tf > a, .qm-pop-tf.show-mask > a, .qm-pop-tf > a')
                        if not pulish_button:
                            print(f"尝试其他方法1")
                            pulish_button = publish_page.get_by_text("确认发布", timeout=2000)

                        # 如果还找不到，尝试更通用的选择器
                        if not pulish_button:
                            print(f"尝试其他方法2")
                            pulish_button = publish_page.query_selector('div[class*="qm-pop"] a, div[class*="el-dialog__body"] a')
                        # pulish_button = publish_page.get_by_text('确认发布', timeout=1500)
                        print(f"成功获取发布按钮")
                        date_input = publish_page.get_by_placeholder("选择日期")
                        date_input_value = state.publish_time.strftime('%Y-%m-%d')
                        print(f"发布日期: {date_input_value}")
                        while date_input.input_value() != date_input_value:
                            date_input.clear()
                            date_input.fill(date_input_value)
                            date_input.press("Enter")
                            publish_page.wait_for_timeout(1000)

                        # 七猫也有常用时间设计
                        # 七猫不允许同时定时发布，要求一定要晚一点
                        if add_var > 0:
                            new_publish_time = state.publish_time + datetime.timedelta(minutes=add_var)
                        else:
                            new_publish_time = state.publish_time
                        time_input_value = new_publish_time.strftime('%H:%M')
                        print(f"发布时间: {time_input_value}")
                        print(f"Ps.七猫不允许同时定时发布，要求一定要晚于上一章发布时间")
                        # time_button = publish_page.query_selector(f'a.ui-time-item[data-time="{time_input_value}"][role="button"]')
                        time_button = publish_page.get_by_text(time_input_value).first
                        if time_button:
                            time_button.click()
                            print(f"成功选择常用时间: {time_input_value}")
                        else:
                            print(f"未找到常用时间元素: {time_input_value}")
                            return False
                            # 测试困难 -- 正确性未知
                            # 选择小时
                            hour_value = time_input_value.split(":")[0]
                            publish_page.get_by_placeholder("小时").click()
                            hour_element = publish_page.query_selector(f'//li[contains(@class, "el-select-dropdown__item") and .//span[text()="{hour_value}"]]')
                            if hour_element and hour_element.is_visible():
                                hour_element.click()
                                publish_page.wait_for_timeout(300)
                            else:
                                print(f"未找到小时元素: {hour_value}")
                                return False

                            # 选择分钟
                            minute_value = time_input_value.split(":")[1]
                            publish_page.query_selector('分钟').click()
                            minute_element = publish_page.query_selector(f'//li[contains(@class, "el-select-dropdown__item") and .//span[text()="{minute_value}"]]')
                            if minute_element and minute_element.is_visible():
                                minute_element.click()
                                publish_page.wait_for_timeout(300)
                            else:
                                print(f"未找到分钟元素: {minute_value}")
                                return False
                    else:
                        publish_page.get_by_text("立即发布").click()
                        publish_page.wait_for_timeout(1500)
                        print("获取确认发布按钮...")
                        # 使用更可靠的选择器，避免绝对路径
                        pulish_button = publish_page.query_selector('body > div.el-dialog__wrapper.qm-pop.w-480.timing-upload-dialog > div > div.el-dialog__body > div.qm-pop-tf > a')
                        if not pulish_button:
                            print(f"尝试其他方法1")
                            pulish_button = publish_page.get_by_text("确认发布", timeout=2000)

                        # 如果还找不到，尝试更通用的选择器
                        if not pulish_button:
                            print(f"尝试其他方法2")
                            pulish_button = publish_page.query_selector('div[class*="qm-pop"] a, div[class*="el-dialog__body"] a')
                        # pulish_button = publish_page.get_by_text('确认发布', timeout=1500)
                        print(f"成功获取发布按钮")
                except:
                    if pulish_button is None:
                        # try:
                        #     _button = input("输入发布按钮元素")
                        #     pulish_button = publish_page.query_selector(_button, timeout=1500)
                        # except:
                        #     publish_page.wait_for_timeout(500)
                        publish_page.get_by_placeholder("请输入章节名称，最多20个字").fill(chapter_title.strip())
                        print("重新粘贴章节正文...")
                        edit_path = 'div.chapter-editor > div > div > div.q-contenteditable.book.font-size-16.edit-mask'
                        # 'div.chapter-editor > div > div'
                        publish_page.wait_for_selector(edit_path, timeout=10000)
                        publish_page.fill(edit_path, chapter_content)
                        publish_page.wait_for_timeout(3000)
                        print("重新尝试发布")

            # 点击确认发布按钮
            pulish_button.click()
            publish_page.wait_for_timeout(5000)
            if add_var == 0:
                try:
                    # 需要点击已阅读并同意协议
                    has_read_button = publish_page.query_selector('div.el-dialog__wrapper.qm-pop.first-upload-dialog div.qm-pop-tf > a, div.first-upload-dialog div.qm-pop-tf > a, .first-upload-dialog .qm-pop-tf > a')
                    if has_read_button:
                        has_read_button.click(timeout=3000)
                    else:
                        # 尝试通过文本内容查找
                        has_read_button = publish_page.get_by_text("已阅读并同意协议").first
                    if has_read_button:
                        has_read_button.click(timeout=3000)
                except:
                    pass

        print(f"--- 第{chapter_num}章发布成功！---")
        publish_page.wait_for_timeout(3000)  # 等待一下，确保操作完成
        try:
            publish_page.get_by_text("我知道了").click(timeout=1500)
        except:
            pass
            # state.debug()

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
     daily_publish_count, daily_publish_num) = state.cfg.as_tuple()

    with sync_playwright() as p:
        browser, context = open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE, on_browser_not_found=None)
        page = context.new_page()
        try:
            print("导航到作者后台...")
            page.goto(site_url, timeout=60000, wait_until='networkidle')
            write_button = None
            # 直接查找小说标题(因为一般七猫也应该是单开，先查找工作台首页所需发布的书籍)
            # page.wait_for_selector('', timeout=60000)
            actual_title = page.query_selector('#app > div.layout > div.qm-main > div.wrapper > div > div.right-col > div.right-col-content.bg-index > div > div.author-book > div.index-module > div.index-module-body > div > ul > li > div > div.book-item-pic > div.txt > div > div.p-top > a').inner_text()
            if actual_title == novel_title:
                print(f"已找到小说: '{novel_title}'")
                write_button = page.get_by_text('新建章节')

            else:
                print(f"未找到小说: '{novel_title}'，继续查找...")
                pass

            list_count = len(novel_files)
            add_var = 0
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                write_button.click() # 点击新建章节按钮
                if not publish_single_chapter(state, publish_mode, context, page, chapter_details, add_var):
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
                while True:
                    try:
                        back_index = page.get_by_text("专区首页").first
                        back_index.click(timeout=1500)
                        page.wait_for_timeout(3000)
                        break
                    except Exception as e:
                        print(f"等待超时错误: {e}")
                        continue
                add_var += 1

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
