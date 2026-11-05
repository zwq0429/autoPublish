"""微信公众号平台发布流程（提取自 app.py，逻辑保持一致）。"""

import datetime
import traceback

from playwright.sync_api import sync_playwright, Page, BrowserContext

from novel_publisher.browser import open_browser
from novel_publisher.flow import AUTH_FILE


def publish_single_chapter(state, publish_mode: str, context: BrowserContext, page: Page, chapter_details: tuple, novel_title: str) -> bool:
    """发布单个章节，处理新打开的页面，并在完成后关闭。"""
    chapter_num, chapter_title, chapter_content = chapter_details[:3]
    print(f"\n--- 开始发布: 第{chapter_num}章 ---")
    if state.stop_publish_sign:
        print("已检测到手动终止发布！！")
        state.stop_publish_sign = False
        return False
    page.wait_for_selector('#app > div.main_bd_new > div:nth-child(3) > div.weui-desktop-panel__bd > div > div:nth-child(2)', timeout=3000).click(timeout=3000)
    publish_page = None
    with context.expect_page() as new_page_info:
        publish_page = new_page_info.value
        publish_page.wait_for_load_state('networkidle')
    novel_writer = state.config.get('Novel', 'novel_writer', fallback=None)
    is_reward = state.config.get('Settings', 'reward', fallback=False)
    print(f"填写章节标题...")
    publish_page.get_by_placeholder("请在这里输入标题").fill(f"第{chapter_num}章：{chapter_title.strip()}")
    if novel_writer:
        publish_page.get_by_placeholder("请输入作者").fill(novel_writer)
    print(f"填写正文...")
    publish_page.locator('#ueditor_0 > div > div > div > div').fill(chapter_content)
    print(f"使用默认封面...")
    publish_page.locator('#js_cover_area > div.select-cover__btn.js_cover_btn_area.select-cover__mask').hover()
    publish_page.get_by_text('从图片库选择').last.click(timeout=3000)
    publish_page.locator('#js_image_dialog_list_wrp > div > div:nth-child(1)').click(timeout=3000)
    # publish_page.get_by_text('下一步').last.click(timeout=3000)
    # publish_page.get_by_text('确认').last.click(timeout=3000)
    publish_page.get_by_role('button', name='下一步').last.click(timeout=3000)
    publish_page.get_by_role('button', name='确认').last.click(timeout=3000)
    publish_page.wait_for_timeout(3000)
    if novel_writer:
        try:
            publish_page.locator('#js_original > div:nth-child(1) > div.setting-group__switch.js_original_apply.js_edit_ori > div').click(timeout=3000)
            is_checked = publish_page.locator('#vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i').is_checked()
            if not is_checked:
                publish_page.locator('#vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i').click(timeout=3000)
            publish_page.get_by_role('button', name='确定').last.click(timeout=3000)
        except:
            print("声明原创失败")
            publish_page.get_by_role('button', name='取消').last.click(timeout=3000)
    if is_reward:
        try:
            # 赞赏设置
            publish_page.locator('#js_reward_setting_area > div > div.setting-group__switch.js_reward_open > span').click(timeout=3000)
            publish_page.wait_for_timeout(1500)
            publish_page.get_by_role('button', name='确定').last.click(timeout=3000)
        except:
            print("赞赏设置失败")
            print('建议先手动设置一次赞赏，再运行脚本')
            publish_page.get_by_role('button', name='取消').last.click(timeout=3000)
    else:
        print("未开启赞赏-内测开启方式config.ini/Settings/reward=True, 需要预先设置一次赞赏")
    publish_page.wait_for_timeout(1500)
    publish_page.locator('#js_article_tags_area > label > div > span').click(timeout=3000)
    publish_page.wait_for_timeout(1500)
    publish_page.get_by_placeholder("请选择合集").click(timeout=3000)
    publish_page.wait_for_timeout(3000)
    publish_page.get_by_text(novel_title).last.click(timeout=3000)

    publish_page.locator('#vue_app').get_by_role('button', name='确认').last.click(timeout=3000)
    # publish_page.get_by_text(novel_title).last.click(timeout=3000)
    if publish_mode == '保存为草稿':
        print("保存为草稿...")
        publish_page.get_by_role("button", name="保存为草稿").click(timeout=3000)
    else:
        publish_page.locator('#js_send > button > span').click(timeout=3000)
        try:
            publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td > div.publish_container.mass_send__notify.weui-desktop-form__control-group > div > div.mass-send__timer-wrp > label > div', timeout=3000).click(timeout=3000)
        except:
            print("取消群发失败")
        if publish_mode == '定时发布':
            print('定时发布')
            print("定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M'))
            if state.publish_time - datetime.datetime.now() > datetime.timedelta(days=7):
                print("公众号不能定时发布超过一周")
                return False
            try:
                publish_page.wait_for_timeout(3000)
                publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td-setting > div > div > div.mass-send__timer-wrp > label > div').click(timeout=3000)
            except:
                pass
            try:
                # publish_page.get_by_text("今天").first.click(timeout=3000)
                publish_page.wait_for_timeout(1500)
                publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td-setting > div.mass-send__timer-container > div > div > dl > dt').click(timeout=3000)
                publish_page.wait_for_timeout(1500)
                #vue_app > mp-image-product-dialog > div > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__ft > div > div.original_agreement > label > i
                if state.publish_time - datetime.datetime.now() < datetime.timedelta(days=1):
                    publish_page.locator('#vue_app').get_by_text('明天').first.click(timeout=3000)
                else:
                    if state.publish_time.year != datetime.datetime.now().year:
                        publish_page.locator('#vue_app').get_by_text(state.publish_time.strftime('%Y年%#m月%#d日')).first.click(timeout=3000)
                    else:
                        publish_page.locator('#vue_app').get_by_text(state.publish_time.strftime('%#m月%#d日')).first.click(timeout=3000)
                try:
                    publish_page.locator('#vue_app').get_by_role('textbox', name="请选择时间").first.fill(state.publish_time.strftime('%H:%M'), timeout=3000)
                    publish_page.wait_for_timeout(1500)
                    publish_page.click('div.mass-send__timer-container > div > dl:nth-child(3) > dt > i', timeout=3000, force=True)
                except:
                    print("设置发布时间失败")
            except:
                print("调试模式已开启，输入q退出")
                while True:
                    try:
                        command = input("@")
                        if command == 'q':
                            break
                        eval(command)
                    except Exception as e:
                        print(f"error: {e}")
        # 关闭群发
        # publish_page.wait_for_selector('#vue_app > mp-image-product-dialog > div:nth-child(3) > div.new_mass_send_dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div > form > div.mass-send__td > div.publish_container.mass_send__notify.weui-desktop-form__control-group > div > div.mass-send__timer-wrp > label > div').click(timeout=3000)
        publish_page.locator("#vue_app").get_by_role("button", name="发表").click(timeout=3000)
        publish_page.locator("#vue_app").get_by_role("button", name="继续发表").click(timeout=3000)
        publish_page.wait_for_timeout(5000)
        while '/home' not in publish_page.url:
            publish_page.wait_for_timeout(3000)
        publish_page.close()
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
            page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('#jumpUrl', timeout=3000).click(timeout=3000)
            page.wait_for_timeout(3000)

            if publish_mode == '定时发布':
                if init_daily_publish_num != -1:
                    # 晚一分钟避免发布顺序错位
                    if init_daily_publish_num >= daily_publish_num:
                        state.publish_time += datetime.timedelta(minutes=init_daily_publish_num - daily_publish_num)
                    else:
                        state.publish_time += datetime.timedelta(hours=1)
                else:
                    if init_daily_publish_count >= daily_publish_count:
                        state.publish_time += datetime.timedelta(minutes=(init_daily_publish_count - daily_publish_count)//2000+1)
                    else:
                        state.publish_time += datetime.timedelta(hours=1)

            list_count = len(novel_files)
            for i, novel_file in novel_files:
                chapter_details = state.get_chapter_details(novel_file)
                if not publish_single_chapter(state, publish_mode, context, page, chapter_details, novel_title):
                    print(f"发布章节 {chapter_details[0]} {chapter_details[1]} 失败。")
                    break
                if publish_mode == '定时发布':
                    if daily_publish_num == -1:
                        state.publish_time += datetime.timedelta(minutes=1) # 晚一分钟避免发布顺序错位
                        daily_publish_count -= state.count_chinese_characters(chapter_details[2])
                        print(f"本日还差发布{daily_publish_count if daily_publish_count > 0 else 0}字")
                        if daily_publish_count <= 0:
                            daily_publish_count = init_daily_publish_count  # 原: int(self.daily_publish_count_var.get())
                            state.publish_time += datetime.timedelta(days=1)
                            init_publish_time = datetime.datetime.strptime(
                                state.config.get('Settings', 'publish_time', fallback='00:00').replace('：', ':'), '%H:%M')  # 原: self.publish_time_var.get()
                            state.publish_time = state.publish_time.replace(hour=init_publish_time.hour, minute=init_publish_time.minute)
                    else:
                        state.publish_time += datetime.timedelta(minutes=1) # 晚一分钟避免发布顺序错位
                        daily_publish_num -= 1
                        print(f"本日还差发布{daily_publish_num}章")
                        if daily_publish_num <= 0:
                            daily_publish_num = init_daily_publish_num  # 原: int(self.daily_publish_num_var.get())
                            state.publish_time += datetime.timedelta(days=1)
                            init_publish_time = datetime.datetime.strptime(
                                state.config.get('Settings', 'publish_time', fallback='00:00').replace('：', ':'), '%H:%M')  # 原: self.publish_time_var.get()
                            state.publish_time = state.publish_time.replace(hour=init_publish_time.hour, minute=init_publish_time.minute)
                list_count -= 1
                if list_count > 0:
                    print(f"本次任务剩余{list_count}章")
                    print("准备发布下一章...")
                page.wait_for_timeout(3000)
            browser.close()

            state.save_history(list_count, daily_publish_num, daily_publish_count,
                               max(end_chapter, start_chapter), publish_mode)
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
