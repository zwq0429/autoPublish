"""发布进度自检 CLI。

来源: app.py 行 434-550（process_check 方法）+ 4068-4111（recommend_status 方法）
  - process_check (434-550)：登录后台后打开番茄作品列表，找到小说并进入"章节管理"，
    读取最新发布章节/时间/当日已发布章数字数，与本地日更计划比对后可回写 config.ini；
  - recommend_status (4068-4111)：根据作品状态/字数/提示文案推进小说状态机，
    原 self.novel_status 改为参数传入、返回新值（纯逻辑，逐行保留）。

去 UI 化说明:
  - 原 self._normal_load_config(True)（event=True 跳过确认弹窗）改为
    novel_publisher.flow.load_publish_config（self.xxx_var.get() 均从 config.ini 读取）；
  - messagebox.askyesno("再次确认", msg_str+"\\n是否更新本地记录？") 改为
    先 print(msg_str) 再 input("是否更新本地记录？(Y/n): ")；
    （原 fast_mode 为 app.py 的 -fast 命令行全局变量，CLI 无此参数，固定走确认分支）
  - self.last_published_chapter_date_var / start_chapter_var / end_chapter_var /
    daily_publish_num_remain_var / daily_publish_count_remain_var 的 set() 改为局部变量，
    经 _save_check_result（原 self.save_config(False) 的等价）写回 config.ini；
  - 原 self.scheduled_task.remove('发布进度自检') 与窗口标题切换（540-548 行）
    为 Tk 窗口/定时任务管理，CLI 无对应物，略。

退出码: 0 全部正常 / 1 有问题（配置缺失、未找到小说、最新章节字数非数字等） / 2 异常。
"""

import datetime
import os
import traceback

from playwright.sync_api import sync_playwright

from novel_publisher.browser import open_browser
from novel_publisher.flow import load_publish_config, ConfigLoadError
from novel_publisher.navigation import (
    navigate_to_fanqie_novel_list,
    find_novel_in_fanqie_list,
)

# 项目根目录（cli/ 的上一级），与 cli/main.py 的 APP_DIR 一致
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 app.py 的 AUTH_FILE = r'auth.json' 对应，CLI 默认放到项目根下
DEFAULT_AUTH_FILE = os.path.join(APP_DIR, 'auth.json')


def _recommend_status(novel_status, word_count_text, status_text, msg):
    """原 NovelPublisherApp.recommend_status（app.py 4068-4111，逐行保留）。
    self.novel_status 改为参数传入并返回新值。"""
    try:
        if status_text.endswith('已签约'):
            word_count = float(word_count_text.replace('万字', ''))
            print(status_text)
            print(f"当前字数: {word_count}万字")
            if word_count < 8:
                novel_status = '已签约'
            else:
                if '作品已达成推荐字数条件' in msg:
                    novel_status = '待验证'
                elif '开始推荐后7天内为推荐验证期' in msg:
                    novel_status = '验证中'
                elif '作品正在番茄持续推荐中' in msg:
                    if novel_status == '全勤中':
                        return novel_status
                    if word_count < 20:
                        novel_status = '推荐中'
                    elif 20 <= word_count < 50 or 100 <= word_count < 150:
                        if novel_status != '书测中':
                            novel_status = '待书测'
                    else:
                        if novel_status == '书测中':
                            novel_status = '待封测'
                        else:
                            if novel_status == '封测中':
                                novel_status = '划水期'
                else:
                    if status_text.startswith('已完结'):
                        novel_status = '已完结'
                    else:
                        novel_status = '划水期'
        else:
            if status_text.startswith('连载中'):
                if '签约审核已通过，请尽快完成合同签约' in msg:
                    novel_status = '待填写合同'
                elif '你的作品即将签约成功，请点击【立即签约】' in msg:
                    novel_status = '待签约'
                else:
                    word_count = float(word_count_text.replace('万字', ''))
                    if word_count >= 2:
                        novel_status = '请申请审核'
    except Exception:
        pass
    return novel_status


def _save_check_result(state, start_chapter, last_published_chapter_date,
                       daily_publish_num_remain, daily_publish_count_remain, novel_status):
    """原 self.save_config(False)（app.py 1705-1757）的 CLI 等价。

    自检过程不修改 Settings 中的 UI 配置，仅写回自检更新的字段：
    History.last_published_chapter（= start_chapter - 1）、last_published_chapter_date、
    daily_publish_num_remain、daily_publish_count_remain 及 Novel.novel_status。
    """
    config = state.config
    if not config.has_section('History'):
        config['History'] = {}
    if not config.has_section('Novel'):
        config['Novel'] = {}
    config['History']['last_published_chapter'] = str(int(start_chapter) - 1)
    config['History']['last_published_chapter_date'] = last_published_chapter_date
    config['History']['daily_publish_num_remain'] = str(daily_publish_num_remain)
    config['History']['daily_publish_count_remain'] = str(daily_publish_count_remain)
    config['Novel']['novel_status'] = novel_status
    with open(state.config_file, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
    print('配置保存成功')


def register(subparsers):
    """向 argparse 子命令注册参数。"""
    subparsers.add_argument('--config', default='config.ini',
                            help='配置文件路径（默认 config.ini）')


def main(args) -> int:
    """执行 progress-check 命令，返回退出码（0 全部正常 / 1 有问题 / 2 异常）。"""
    auth_file = DEFAULT_AUTH_FILE

    # 原 normal_config = self._normal_load_config(True)（event=True 跳过确认弹窗）
    try:
        state = load_publish_config(args.config, auth_file)
    except ConfigLoadError as e:
        print(str(e))
        return 1

    cfg = state.cfg
    (custom_browser_path, site_url,
     novel_title, novels_folder,
     publish_mode, start_chapter,
     end_chapter, keep_browser_open,
     novel_files, init_daily_publish_count, init_daily_publish_num,
     daily_publish_count, daily_publish_num) = (
        cfg.custom_browser_path, cfg.site_url,
        cfg.novel_title, cfg.novels_folder,
        cfg.publish_mode, cfg.start_chapter,
        cfg.end_chapter, cfg.keep_browser_open,
        cfg.novel_files, cfg.init_daily_publish_count, cfg.init_daily_publish_num,
        cfg.daily_publish_count, cfg.daily_publish_num)

    # 原 self.novel_status（recommend_status 状态机的当前值，来自 config [Novel] novel_status）
    novel_status = state.novel_status
    # 原 self.last_published_chapter_date_var.get()（来自 config [History] last_published_chapter_date）
    last_published_chapter_date = state.last_published_chapter_date
    # 原 self.daily_publish_num_remain_var / self.daily_publish_count_remain_var
    daily_publish_num_remain = daily_publish_num
    daily_publish_count_remain = daily_publish_count

    try:
        with sync_playwright() as p:
            # 原 self._normal_open_browser(p, custom_browser_path, keep_browser_open)；
            # 其 on_browser_not_found 原为 self.open_browser_lnk（打开快捷方式），CLI 传 None
            browser, context = open_browser(p, custom_browser_path, keep_browser_open, auth_file,
                                            on_browser_not_found=None)
            page = context.new_page()
            try:
                navigate_to_fanqie_novel_list(page, site_url)

                def _on_novel_found(item):
                    nonlocal novel_status
                    status_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.property')
                    wordcount_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-left > div.detail.font-4 > div.detail-wordcount.font-4 > span')
                    msg_element = item.query_selector(
                        'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    while not msg_element:
                        page.wait_for_timeout(1000)
                        msg_element = item.query_selector(
                            'div > div.expand-container-expand > div > div > div.book-tip-step-title.font-3')
                    novel_status = _recommend_status(novel_status, wordcount_element.inner_text(),
                                                     status_element.inner_text(), msg_element.inner_text())

                if not find_novel_in_fanqie_list(page, novel_title, on_found=_on_novel_found):
                    return 1
                if novel_status == "已完结":
                    print(f"小说 '{novel_title}' 已完结，无需更新。")
                    return 0
                else:
                    row = page.get_by_text(novel_title).locator("..").locator("..")
                    row.hover()
                    row.get_by_role("button", name="章节管理").click(timeout=3000, force=True)
                    page.wait_for_load_state('networkidle')
                    latest_publish_time = datetime.datetime.now()
                    try:
                        page.get_by_role("button", name="我知道了").click(timeout=3000, force=True)
                    except:
                        pass
                    latest_chapter_row = page.locator('div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child(1)')
                    latest_chapter_title = latest_chapter_row.locator('td:nth-child(1) > div').inner_text()
                    latest_chapter_count = latest_chapter_row.locator('td:nth-child(2) > div').inner_text()
                    if not latest_chapter_count.isdigit():
                        print(f"错误：最新章节字数 '{latest_chapter_count}' 不是数字，可能是正在审核中，请稍后进行同步")
                        raise ValueError(f"最新章节字数 '{latest_chapter_count}' 不是数字，可能是正在审核中，请稍后进行同步")
                    latest_chapter_publish_time = latest_chapter_row.locator('td:nth-child(5) > div').inner_text()

                    latest_publish_time = datetime.datetime.strptime(latest_chapter_publish_time, '%Y-%m-%d %H:%M')
                    latest_chapter_index = int(latest_chapter_title.split("第")[1].split("章")[0])
                    latest_publish_count = int(latest_chapter_count) if latest_chapter_count.isdigit() else 2000
                    latest_publish_num = 1

                    while True:
                        next_chapter_row = page.locator(f'div.chapter-table.auto-editor-chapter > div > div > div > div.arco-table-container > div > div > table > tbody > tr:nth-child({latest_publish_num+1})')
                        if latest_publish_time.date() == datetime.datetime.strptime(next_chapter_row.locator('td:nth-child(5) > div').inner_text(), '%Y-%m-%d %H:%M').date():
                            latest_publish_num += 1
                            latest_publish_count += int(next_chapter_row.locator('td:nth-child(2) > div').inner_text())
                        else:
                            break

                    msg_str = f"小说名：{novel_title}\n"
                    msg_str += f"最新发布章节：{latest_chapter_index}\n"
                    msg_str += f"最新发布时间：{latest_publish_time.strftime('%Y-%m-%d %H:%M')}\n"
                    msg_str += f"当日已发布：{latest_publish_num}章，{latest_publish_count}字\n"
                    is_update = False
                    # 原 if not fast_mode: messagebox.askyesno(...) / else: print(msg_str); is_update=True
                    # CLI 无 fast_mode 参数，固定走确认分支；messagebox.askyesno 改为 input() 询问
                    print(msg_str)
                    is_update = input("是否更新本地记录？(Y/n): ").strip().lower() != 'n'

                    if is_update:
                        # 原 var.set(...) 改为局部变量，最终经 _save_check_result 写回 config.ini
                        last_published_chapter_date = latest_publish_time.strftime('%Y-%m-%d')
                        # self.publish_time_var.set(latest_publish_time.strftime('%H:%M'))
                        start_chapter = latest_chapter_index + 1
                        if init_daily_publish_num != -1:
                            daily_publish_num = daily_publish_num if daily_publish_num != 0 else init_daily_publish_num
                            if daily_publish_num > latest_publish_num:
                                end_chapter = latest_chapter_index + daily_publish_num - latest_publish_num
                                daily_publish_num_remain = daily_publish_num - latest_publish_num
                            else:
                                end_chapter = latest_chapter_index + daily_publish_num
                                daily_publish_num_remain = 0
                        else:
                            end_chapter = latest_chapter_index + 1
                            daily_publish_count = daily_publish_count if daily_publish_count != 0 else init_daily_publish_count
                            print(f"最新发布字数：{latest_publish_count}, 每日发布字数：{daily_publish_count}")
                            if daily_publish_count > latest_publish_count:
                                daily_publish_count_remain = daily_publish_count - latest_publish_count
                            else:
                                daily_publish_count_remain = 0
                        print(f"已更新本地记录: 开始章节 {start_chapter}，结束章节 {end_chapter}")
                    _save_check_result(state, start_chapter, last_published_chapter_date,
                                       daily_publish_num_remain, daily_publish_count_remain, novel_status)
            except ValueError as e:
                # 原 except Exception 分支；CLI 拆分：已知数据问题（字数非数字等 ValueError）→ 退出码 1
                traceback.print_exc()
                print(f"点击章节管理按钮时发生错误: {e}")
                return 1
            except Exception as e:
                traceback.print_exc()
                print(f"点击章节管理按钮时发生错误: {e}")
                return 2
            finally:
                page.close()
                browser.close()
        # 原 self.scheduled_task.remove('发布进度自检') 与窗口标题/退出切换（app.py 540-548）：
        # CLI 无定时任务集合与 Tk 窗口，略
        return 0
    except Exception as e:
        # 浏览器/上下文创建阶段的未捕获异常 → 异常退出码
        traceback.print_exc()
        print(f"发布进度自检失败: {e}")
        return 2
