"""番茄小说平台发布流程（提取自 app.py，逻辑保持一致）。"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE
from novel_publisher.navigation import navigate_to_fanqie_novel_list


def recommend_status(state, word_count_text: str, status_text: str, msg: str):
    try:
        if status_text.endswith('已签约'):
            word_count = float(word_count_text.replace('万字', ''))
            print(status_text)
            print(f"当前字数: {word_count}万字")
            if word_count < 8:
                state.novel_status = '已签约'
            else:
                if '作品已达成推荐字数条件' in msg:
                    state.novel_status = '待验证'
                elif '开始推荐后7天内为推荐验证期' in msg:
                    state.novel_status = '验证中'
                elif '作品正在番茄持续推荐中' in msg:
                    if state.novel_status == '全勤中':
                        return
                    if word_count < 20:
                        state.novel_status = '推荐中'
                    elif 20 <= word_count < 50 or 100 <= word_count < 150:
                        if state.novel_status != '书测中':
                            state.novel_status = '待书测'
                    else:
                        if state.novel_status == '书测中':
                            state.novel_status = '待封测'
                        else:
                            if state.novel_status == '封测中':
                                state.novel_status = '划水期'
                else:
                    if status_text.startswith('已完结'):
                        state.novel_status = '已完结'
                    else:
                        state.novel_status = '划水期'
        else:
            if status_text.startswith('连载中'):
                if '签约审核已通过，请尽快完成合同签约' in msg:
                    state.novel_status = '待填写合同'
                elif '你的作品即将签约成功，请点击【立即签约】' in msg:
                    state.novel_status = '待签约'
                else:
                    word_count = float(word_count_text.replace('万字', ''))
                    if word_count >= 2:
                        state.novel_status = '请申请审核'
    except Exception:
        pass


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str, retry_times: int = 3) -> bool:
    """发布单个章节，处理新打开的页面，并在完成后关闭。"""
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    chapter_content = chapter_content.replace("\n\n", "\n").replace("\n\n", "\n") # 替换多个换行符为单换行符
    writer_said_content = chapter_details[3]
    if writer_said_content is not None and writer_said_content.strip() != '':
        print(f"章节 {chapter_num} 包含作者说!")
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if len(chapter_content.strip()) < 3:
        print("章节名字数不足3个字符，终止发布，请检查章节文件，可使用快捷键Ctrl+M打开当前章节")
        return False
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
        return False

    publish_page = None
    try:
        if publish_mode == '修改章节':
            try:
                try:
                    page.get_by_role("button", name="我知道了").click(timeout=1000, force=True)
                except:
                    pass
                try:
                    page.get_by_text("搜索章节").first.click(timeout=3000, force=True)
                except:
                    state.debug()
                page.get_by_placeholder("输入章节名称或章节号").fill(chapter_num, timeout=3000)
                page.wait_for_timeout(3000)
                page.wait_for_load_state('domcontentloaded')
                match_chapter_count = page.get_by_text(f"第{chapter_num}章").count()
                print(f"搜索到的章节数: {int(match_chapter_count)}")
                if match_chapter_count == 0:
                    page.click('div.arco-modal-wrapper.arco-modal-wrapper-align-center > div > span')
                    return False
                else:
                    try:
                        page.click("div.arco-modal-wrapper.arco-modal-wrapper-align-center > div > div.arco-modal-content > div.chapter-search-result > div > div > div > div > div > div > div.arco-table-body > table > tbody > tr > td:nth-child(5) > div > span > span > a > span", timeout=3000, force=True)
                        page.wait_for_timeout(2000)
                        page.wait_for_load_state('domcontentloaded')
                    except:
                        state.debug()
                    try:
                        page.get_by_text("我知道了", exact=True).click(timeout=1500, force=True)
                    except:
                        pass
                    page.get_by_placeholder("请输入标题").fill(chapter_title.strip()[:24], timeout=3000)
                    page.locator('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror').fill(chapter_content, timeout=3000)
                    while not page.get_by_role("button", name="确认发布").is_visible(timeout=3000):
                        page.get_by_role("button", name="下一步").click(timeout=3000, force=True)
                        try:
                            page.get_by_role("button", name="仅基础检测").click(timeout=1500)
                            print("基础风险预检")
                            page.wait_for_timeout(1000)
                        except Exception:
                            pass
                        try:
                            page.get_by_role("button", name="提交").click(timeout=1500)
                        except Exception:
                            pass
                        try:
                            page.get_by_role("button", name="提交").click(timeout=1500)
                        except Exception:
                            pass
                        page.wait_for_timeout(3000)
                    # 聚焦到"button", name="确认发布"
                    page.get_by_role("button", name="确认发布").click(timeout=3000, force=True)
                    try:
                        page.click('div.card-content-line-control > div > label:nth-child(2)', timeout=3000)
                    except Exception:
                        state.debug()
                    page.get_by_role("button", name="确认发布").click(timeout=3000, force=True)
                    print(f"--- 第{chapter_num}章修改成功！---")
                    page.wait_for_timeout(1500)  # 等待一下，确保操作完成
                    page.reload(timeout=3000)
                    page.wait_for_load_state('domcontentloaded')
                    return True
            except:
                traceback.print_exc()
                print(f"--- 第{chapter_num}章修改失败！---")
                return False
        else:
            try:
                page.get_by_role("button", name="我知道了").click(timeout=1000, force=True)
            except:
                pass
            max_attempts = 5
            attempt_count = 0
            while not page.get_by_role("button", name="新建章节").is_visible(timeout=5000):
                attempt_count += 1
                if attempt_count >= max_attempts:
                    print("新建章节按钮未出现，最大尝试次数已超过。")
                    return False
                page.reload(timeout=3000)
                page.wait_for_timeout(3000)
                page.wait_for_load_state('load')
        publish_page = None
        while publish_page is None:
            try:
                page.get_by_role("button", name="新建章节").click(timeout=5000)
                with context.expect_page(timeout=5000) as new_page_info:
                    publish_page = new_page_info.value
                    MAX_REPEAT = 3
                    while MAX_REPEAT > 0:
                        MAX_REPEAT -= 1
                        try:
                            publish_page.wait_for_load_state('domcontentloaded', timeout=10000)
                        except:
                            print(f"发布页面加载超时重试，剩余{MAX_REPEAT}次")
                            publish_page.reload(timeout=3000)
                    publish_page.wait_for_load_state('domcontentloaded', timeout=10000)
                    print("已切换到新的发布页面。")
            except:
                print("打开发布页面失败。")
                page.reload(timeout=3000)
                page.wait_for_load_state('domcontentloaded', timeout=10000)
                publish_page = None

        # --- 在新页面上执行操作 ---
        # 预先点击去除新手引导
        publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=3000, force=True)
        # publish_page.click('body')
        print(f"填写章节序号: {chapter_num}")
        publish_page.wait_for_selector('span.left-input > input', timeout=5000)
        publish_page.fill('span.left-input > input', chapter_num.strip(), timeout=3000)

        print(f"填写章节标题: {chapter_title[:24]}")
        publish_page.get_by_placeholder("请输入标题").fill(chapter_title.strip()[:24], timeout=3000)

        print("粘贴章节正文...")
        edit_path = '#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > ' \
                    'div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror'

        publish_page.wait_for_selector(edit_path, timeout=10000)
        publish_page.fill(edit_path, chapter_content)
        publish_page.wait_for_timeout(5000)

        if writer_said_content is not None and writer_said_content.strip() != '':
            if state.count_chinese_characters(writer_said_content.strip()) > 300:
                print(f"[错误] 章节 {chapter_num} 作者说内容超过300个中文字符，无法发布！")
                return False
            print("填写作者说...")
            publish_page.locator('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.author-speak-empty > div > div.author-speak-empty-btn > div.author-speak-empty-btn-content').hover(timeout=3000)
            publish_page.get_by_text("添加图文", exact=True).click(timeout=3000)
            publish_page.wait_for_selector('#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > div > div > div.author-speak > div.author-speak-input > div.syl-editor > div').fill(writer_said_content.strip(), timeout=3000)
            publish_page.get_by_role("button", name="保存", exact=True).click(timeout=3000)

        if publish_mode == '保存为草稿':
            print("保存为草稿...")
            publish_page.get_by_role("button", name="存草稿").click(timeout=3000)
        else:
            print("点击'下一步'进行发布...")
            publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=3000)

            # 处理发布确认弹窗
            print("处理发布确认弹窗...")
            try_times = 5
            while not (publish_page.get_by_role("button", name="确认发布").is_visible(timeout=3000) or publish_page.get_by_role("button", name="确认提交").is_visible(timeout=3000)) and try_times > 0:
                try:
                    publish_page.get_by_role("button", name="提交").click(timeout=1500)
                except Exception:
                    pass
                try:
                    publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1000)
                except Exception:
                    pass
                try:
                    if not False:  # 原: self.danger_pre_check_var.get()，CLI 无 UI，默认 False（基础风险预检）
                        publish_page.get_by_role("button", name="仅基础检测").click(timeout=1500)
                        print("基础风险预检")
                        publish_page.wait_for_timeout(1000)
                    else:
                        publish_page.get_by_role("button", name="全面检测").click(timeout=1500)
                        print("全面风险预检")
                        publish_page.wait_for_timeout(3000)
                        top_message = publish_page.wait_for_selector("span.arco-message-content", timeout=10000)
                        msg = top_message.inner_text()
                        print(msg)
                        if "暂无风险" in msg:
                            pass
                        else:
                            if not state.cfg.keep_browser_open:  # 原: self.keep_browser_open_var.get()
                                print("当前章节可能存在风险内容，请手动修改，修改完成后按Ctrl+K继续发布后续")
                                state.wait_event.wait()
                            else:
                                print("当前章节可能存在风险内容，结束发布")
                                return False
                        try:
                            publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=1500)
                        except Exception:
                            pass
                    try:
                        publish_page.get_by_role("button", name="提交").click(timeout=1500)
                    except Exception:
                        pass
                    try:
                        publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1000)
                    except Exception:
                        pass
                except Exception:
                    try:
                        # publish_page.wait_for_timeout(5000)
                        # state.debug()
                        try_times -= 1
                        print(f"重新填写章节序号: {chapter_num}")
                        publish_page.wait_for_selector('span.left-input > input', timeout=5000)
                        publish_page.fill('span.left-input > input', chapter_num.strip())

                        print(f"重新填写章节标题: {chapter_title}")
                        publish_page.get_by_placeholder("请输入标题").fill(chapter_title.strip())

                        print("重新粘贴章节正文...")
                        edit_path = '#app > div > div > div > div.publish-body > div.editor > div.serial-editor-container.notranslate > ' \
                                    'div > div > div.syl-editor-container.font-size-16.indent-2 > div > div.ProseMirror'

                        publish_page.wait_for_selector(edit_path, timeout=10000)
                        publish_page.fill(edit_path, chapter_content)
                        publish_page.fill('span.left-input > input', chapter_num.strip())
                        # 点击“确认发布”按钮
                        publish_page.locator('#app > div > div > div > div.publish-header > div.publish-header-right > button.arco-btn.arco-btn-secondary.arco-btn-size-default.arco-btn-shape-square.publish-button.auto-editor-next.btn-primary-variant').click(timeout=1500)
                    except Exception:
                        # 所有操作失败时，短暂等待后继续循环
                        publish_page.wait_for_timeout(500)
                        continue

            print("发布设置...AI-默认否")
            # 选择“否”单选框
            publish_page.wait_for_selector('div.card-content-line-control > div > label:nth-child(2)', timeout=5000).click()
            # publish_page.get_by_role("radiogroup").get_by_role("radio", name="否").check()

            if publish_mode == '定时发布':
                # 勾选定时发布
                publish_page.click('div > div.card-content-line-control > div > button', timeout=3000)
                # publish_page.get_by_role("button", name="定时发布").click()

                print("定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M'))
                try:
                    publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1500)
                except Exception:
                    pass
                # 使用 get_by_placeholder 来定位输入框，并确保先清空再填写
                date_input = publish_page.get_by_placeholder("请选择日期")
                date_input_value = state.publish_time.strftime('%Y-%m-%d')
                while date_input.input_value() != date_input_value:
                    date_input.clear(timeout=3000)
                    date_input.fill(date_input_value, timeout=3000)
                    date_input.press("Enter", timeout=3000)
                    try:
                        publish_page.get_by_text("今天").last.click(timeout=1500)
                    except Exception:
                        pass
                    publish_page.wait_for_timeout(1000)

                time_input = publish_page.get_by_placeholder("请选择时间")
                time_input_value = state.publish_time.strftime('%H:%M')
                while time_input.input_value() != time_input_value:
                    time_input.clear(timeout=3000)
                    time_input.fill(time_input_value, timeout=3000)
                    time_input.press("Enter", timeout=3000)
                    try:
                        publish_page.get_by_text("此刻").last.click(timeout=1500)
                    except Exception:
                        pass
                    publish_page.wait_for_timeout(1000)

            # 点击确认发布按钮
            chapter_details_new = list(chapter_details)
            try_times = 0
            while True:
                try:
                    if state.stop_publish_sign:
                        print("已检测到手动终止发布！！")
                        state.stop_publish_sign = False
                        return False
                    try:
                        publish_page.get_by_role("button", name="继续编辑本地").click(timeout=1500)
                    except Exception:
                        pass
                    publish_button = publish_page.get_by_role("button", name="确认发布") if publish_page.get_by_role("button", name="确认发布").is_visible(timeout=3000) else publish_page.get_by_role("button", name="确认提交")
                    publish_button.click(timeout=3000)
                except Exception:
                    pass
                try:
                    top_message = publish_page.wait_for_selector("span.arco-message-content", timeout=3000)
                    if top_message.is_visible():
                        msg = top_message.inner_text()
                        print(msg)
                    if '重复标题' in msg:
                        print("重复标题，添加章节序号")
                        chapter_details_new[1] = f"{chapter_title}/{chapter_num}"
                    if '大段落重复' in msg:
                        chapter_details_new[2] = state.check_repeat_content(chapter_content)
                    if '更新作品数超出每日上限' in msg:
                        print("更新作品数超出每日上限，直接退出")
                        return False
                except Exception:
                    print("未检测到网站消息")

                if "chapter-manage" in publish_page.url:
                    print("发布成功")
                    page.reload(timeout=3000)
                    break

                try_times += 1
                # state.debug()
                if try_times >= 2:
                    publish_page.close()
                    retry_times -= 1
                    if retry_times <= 0:
                        return False
                    else:
                        print(f"重试发布第{chapter_num}章，剩余重试次数: {retry_times}")
                        return publish_single_chapter(state, publish_mode, context, page, chapter_details_new, novel_title, retry_times)

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
     daily_publish_count, daily_publish_num,
     interval_days, interval_tag) = state.cfg.as_tuple()

    if publish_mode == '定时发布':
        while not state.check_interval_publish(state.publish_time):
            print(f"{state.publish_time.strftime('%Y-%m-%d')}非间隔发布日，跳过至")
            state.publish_time += datetime.timedelta(days=1)
        print(f"从 {state.publish_time.strftime('%Y-%m-%d')} 开始发布")
        state.last_published_chapter_date = state.publish_time.strftime('%Y-%m-%d')
    else:
        if not state.check_interval_publish():
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            print(f"今日({today_str})非发布日，跳过发布")
            return True

    with sync_playwright() as p:
        browser, context = open_browser(p, custom_browser_path, keep_browser_open, AUTH_FILE, on_browser_not_found=None)
        page = context.new_page()
        try:
            navigate_to_fanqie_novel_list(page, site_url)

            print(f"正在查找小说: '{novel_title}'")

            while True:
                page.wait_for_selector('[id^="long-article-table-item-"]')
                page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                novel_items = page.query_selector_all('[id^="long-article-table-item-"]')
                update_button = None
                for item in novel_items:
                    # state.debug()
                    title_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div'
                        ) or item.query_selector(
                        'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-title.font-1')
                    #print(title_element.inner_text())
                    if title_element and title_element.inner_text() == novel_title:
                        print(f"找到小说《{novel_title}》")
                        # 定位到“更新章节”按钮
                        item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见
                        page.wait_for_timeout(1000)
                        page.wait_for_load_state('domcontentloaded')
                        status_element = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.property') or item.query_selector(
                            'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-detail.font-4 > span:nth-child(1)')
                        wordcount_element = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.detail-wordcount.font-4 > span') or item.query_selector(
                            'div > div.completion-book-item-main > div.completion-book-item-content > div.completion-book-item-detail.font-4 > span:nth-child(3)')
                        msg_element = item.query_selector(
                            'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                        _retries = 0
                        while not msg_element and _retries < 3:
                            print("未找到状态提示，等待1秒后重试")
                            page.wait_for_timeout(1000)
                            msg_element = item.query_selector(
                                'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                            _retries += 1

                        if msg_element:
                            print(f"找到状态提示: {msg_element.inner_text()}")
                            recommend_status(state, wordcount_element.inner_text(), status_element.inner_text(), msg_element.inner_text())
                        else:
                            print("未找到状态提示")

                        update_button = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-right > div > a:nth-child(3) > button') or item.query_selector(
                            'div > div.completion-book-item-main > div.completion-book-item-actions > a:nth-child(3) > button')
                        update_button_unsign = item.query_selector(
                            'div > div.book-item-info > div.info-content > div.info-right > div > a:nth-child(4) > button') or item.query_selector(
                            'div > div.completion-book-item-main > div.completion-book-item-actions > a:nth-child(4) > button')
                        if update_button:
                            break
                        elif update_button_unsign:
                            print("小说未签约")
                            update_button = update_button_unsign
                            break
                        else:
                            print("未找到'创建章节'按钮")

                if not update_button:
                    next_page_button_limit = page.query_selector(
                        'div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next.arco-pagination-item-disabled')
                    next_page_button = page.query_selector(
                        "div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination > ul > li.arco-pagination-item.arco-pagination-item-next")
                    if next_page_button and not next_page_button_limit:
                        next_page_button.click()
                        page.wait_for_load_state('networkidle')
                    else:
                        print(f"错误：在列表中未找到小说 '{novel_title}'")
                        # state.debug()
                        return
                else:
                    break
            # state.debug()
            row = page.get_by_text(novel_title).locator("..").locator("..").locator("..")
            row.hover()
            row.get_by_role("button", name="章节管理").click(timeout=3000, force=True)

            # if not self.fast_publish_mode:
            # 开启间隔发布
            # if not self.check_interval_publish():

            list_count = len(novel_files)
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, page, chapter_details, novel_title):
                    print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                    break
                if publish_mode == '定时发布' or ('本地定时发布' in state.scheduled_task):
                    if init_daily_publish_num == -1:
                        daily_publish_count -= state.count_chinese_characters(chapter_details[2])
                        print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                        if daily_publish_count <= 0:
                            daily_publish_count = init_daily_publish_count
                            state.publish_time += datetime.timedelta(days=interval_days)
                    else:
                        daily_publish_num -= 1
                        print(f"本日还差发布{daily_publish_num}章")
                        if daily_publish_num <= 0:
                            daily_publish_num = init_daily_publish_num
                            state.publish_time += datetime.timedelta(days=interval_days)
                list_count -= 1
                if list_count > 0:
                    print(f"本次任务剩余{list_count}章")
                    print("准备发布下一章...")
                page.wait_for_timeout(3000)
            browser.close()

            state.save_history(list_count, daily_publish_num, daily_publish_count, max(start_chapter, end_chapter), publish_mode)
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
