"""番茄平台特有任务（从 app.py 提取的纯函数版本）。

来源：
- run_sstory_batch   <- scheduled_publish_story_batch (app.py 716-760)
- run_sign           <- scheduled_sign (762-963)
- run_verify         <- scheduled_verify (1086-1193)
- run_book_test      <- schedule_command_by_name (1195-1304)
- run_cover_test     <- schedule_command_by_cover (1306-1433)
- run_attendance     <- schedule_check_attendance (1435-1587)

ctx 约定（types.SimpleNamespace）：
- ctx.browser_path      浏览器路径（原 self.custom_browser_path_var.get()）
- ctx.site_url          平台 URL（原 self._get_site_url()）
- ctx.novel_title       小说名（原 self.novel_title_var.get()）
- ctx.writer            笔名（原 self.novel_writer_var.get()，sstory/签约用）
- ctx.keep_browser_open 原 self.keep_browser_open_var.get()，作为 headless 参数
- ctx.auth_file         登录态文件路径（原 AUTH_FILE）
- ctx.config            configparser 实例
- ctx.config_file       配置文件路径
- ctx.story_folder      短故事文件夹路径（仅 run_sstory_batch 用，
                        原为 os.path.join(os.getcwd(), '短篇直出')）
- ctx.publish_plate     平台名（用于函数开头"仅支持番茄"校验）
- ctx.novel_status      动态属性：函数运行中按原逻辑写入
                        （'未申请签约'/'签约审核中'/'待签约'/'推荐评估中'/
                        '书测中'/'封测中'/'有全勤实力'/'全勤中'/'有缺勤'），
                        由 _save_status 持久化到 [Novel] novel_status。
                        调用前可不设置该属性；run_sign 读取时以
                        getattr(ctx, 'novel_status', '') 兜底。

注意：run_sign / run_verify 含超长等待（评估中每小时巡查、
run_verify 最长 wait_for_timeout(60*60*1000*12) 等 12 小时），属长任务。

返回值：True 表示流程正常完成；False 表示失败/异常（含平台校验不通过）。
run_sstory_batch 原方法无 try/except，异常会向上传播（与原逻辑一致）。
"""
from types import SimpleNamespace
import datetime
import os
import traceback
from playwright.sync_api import sync_playwright

from novel_publisher.browser import open_browser
from novel_publisher.sstory import FanqieSStoryAutoPublisher


def _save_status(ctx):
    """把 ctx.novel_status（若存在）写入 ctx.config 的 [Novel] novel_status
    并写文件到 ctx.config_file。

    对应原 app.py 的 self.save_config(True)（仅保存状态分支，去掉 UI 依赖）。
    """
    if hasattr(ctx, 'novel_status'):
        if not ctx.config.has_section('Novel'):
            ctx.config['Novel'] = {}
        ctx.config['Novel']['novel_status'] = ctx.novel_status
        print(f"状态已保存: {ctx.novel_status}")
    with open(ctx.config_file, 'w', encoding='utf-8') as configfile:
        ctx.config.write(configfile)


def run_sstory_batch(ctx) -> bool:
    """短故事批量发布（原 app.py scheduled_publish_story_batch 716-760）。

    读取 ctx.story_folder 下的短故事 txt，逐篇解析并发布，
    发布成功后移动到 os.getcwd() 下按日期命名的"已发布xx-xx"文件夹。
    """
    if ctx.publish_plate != "番茄":
        print("短故事批量发布仅支持番茄平台")
        return False
    # 读取工作目录下的短篇直出文件夹
    story_folder = ctx.story_folder
    if not os.path.exists(story_folder):
        print(f"{story_folder}文件夹不存在")
        print(f"请将统一格式的短故事txt文档放置到{story_folder}文件夹中")
        print("由于番茄发布限制，数量建议不多于10篇，否则只会发布前10篇")
    else:
        story_files = os.listdir(story_folder)
        print(f"发现{len(story_files)}篇短故事")
        if len(story_files) > 10:
            print("由于番茄发布限制，数量建议不多于10篇，否则只会发布前10篇")
        browser_path = ctx.browser_path
        site_url = ctx.site_url
        writer = ctx.writer
        fssp = FanqieSStoryAutoPublisher(browser_path, site_url, writer, ctx.auth_file)
        release_folder = os.path.join(os.getcwd(), f"已发布{datetime.datetime.now().strftime('%m-%d')}")
        os.makedirs(release_folder, exist_ok=True)
        for file in story_files[:10]:
            if file.endswith(".txt"):
                with open(os.path.join(story_folder, file), 'r', encoding='utf-8') as f:
                    input_text = f.read()
                parsed_info = fssp.parse_story_info(input_text)
                if fssp.publish(parsed_info):
                    if parsed_info['短故事名称'] == '未知':
                        print(f'未解析到短故事名称，使用文件名作为名称')
                        parsed_info['短故事名称'] = os.path.splitext(file)[0]
                    print(f"短故事名称 {parsed_info['短故事名称']} 发布成功")
                    os.rename(os.path.join(story_folder, file), os.path.join(release_folder, file))
                else:
                    print(f"短故事名称 {parsed_info['短故事名称']} 发布失败")
    return True


def run_sign(ctx) -> bool:
    """自动签约（原 app.py scheduled_sign 762-963）。长任务：评估中每小时巡查一次。

    从项目根目录"签约信息.txt"读取签约资料，在番茄作者后台查找小说：
    未签约则申请签约；评估通过后自动填写合同信息（电子签仍需手动收验证码）。
    状态变化通过 ctx.novel_status（'未申请签约'/'签约审核中'/'待签约'）记录并持久化。
    """
    if ctx.publish_plate != "番茄":
        print("自动签约仅支持番茄平台")
        return False
    print("=====================================")
    print("自动签约线程已启动")
    print("注意，仅等待评估完成后，自动填写内容，电子签还是需要手动操作接收验证码")
    try:
        if os.path.exists('签约信息.txt'):
            with open('签约信息.txt', 'r', encoding='utf-8') as f:
                auth_data = f.readlines()
            print(f"签约信息加载成功!")
            # 提取签约信息
            i=0
            for _ in range(len(auth_data)//8):
                author_name = auth_data[i].strip().split("：")[1]
                if author_name != ctx.writer:
                    # print(f"签约信息中作者姓名为{author_name}，与配置文件中作者姓名{ctx.writer}不匹配")
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
                    custom_browser_path = ctx.browser_path
                    site_url = ctx.site_url
                    try:
                        with sync_playwright() as p:
                            browser = p.chromium.launch(
                                headless=ctx.keep_browser_open,
                                executable_path=custom_browser_path if custom_browser_path else None,
                                args=[
                                    "--disable-popup-blocking",  # 禁用弹窗拦截
                                    "--disable-web-security",  # 禁用网页安全策略
                                    "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                                    "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                                ],
                                ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
                            )
                            if not os.path.exists(ctx.auth_file):
                                raise FileNotFoundError(f"未找到认证文件 {ctx.auth_file}")
                            context = browser.new_context(
                                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                storage_state=ctx.auth_file)
                            page = context.new_page()
                            novel_title = ctx.novel_title

                            # 刷新网页
                            while True:
                                page.goto(site_url, timeout=60000, wait_until='domcontentloaded')

                                print("点击进入小说列表页面...")
                                novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
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
                                novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                                try:
                                    page.wait_for_selector(novel_list_selector, timeout=60000)  # 等待元素出现
                                    page.click(novel_list_selector, timeout=60000)  # 延长点击超时
                                    page.wait_for_load_state('domcontentloaded')
                                except Exception as e:
                                    print(f"点击小说列表导航元素时发生错误: {e}")
                                    raise ValueError(f"点击小说列表导航元素时发生错误: {e}")  # 重新抛出异常以便上层捕获

                                print(f"正在查找小说: '{novel_title}'")

                                page.wait_for_selector('[id^="long-article-table-item-"]')
                                page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                                novel_items = page.query_selector_all('[id^="long-article-table-item-"]')

                                for item in novel_items:
                                    title_element = item.query_selector(
                                        'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div')
                                    # print(title_element.inner_text())
                                    if title_element and title_element.inner_text() == novel_title:
                                        print(f"找到小说 '{novel_title}'。")
                                        item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见
                                        break
                                row = page.get_by_text(novel_title).locator("..").locator("..").locator("..").locator("..")
                                row.hover()
                                page.wait_for_timeout(1500)
                                if row.get_by_text("【申请签约】").count() == 0:
                                    if row.get_by_text("就可申请签约，请努力码字").count() != 0:
                                        print("未达到签约字数")
                                        ctx.novel_status = '未申请签约'
                                        _save_status(ctx)
                                        page.wait_for_timeout(60000*5)
                                        continue
                                    if row.get_by_text("查看电子版合同并完成签约").count() != 0:
                                        print("已完成签约合同，请手动完成确认")
                                        break
                                    print("已申请签约")
                                    if row.get_by_text("签约审核已通过，请尽快完成合同签约").count() != 0 or row.get_by_text("评估通过，请尽快填写合同信息").count() != 0:
                                        print("评估通过")
                                        row.get_by_text("签约管理").click(timeout=1500)
                                        page.wait_for_timeout(1500)
                                        page.get_by_role("button", name="填写合同").click(timeout=1500)
                                        page.get_by_placeholder("请输入可联系的手机号，该手机号将用于获取签约验证码").fill(phone, timeout=1500)
                                        page.get_by_placeholder("请输入邮箱地址以接收电子合同").fill(email, timeout=1500)
                                        page.get_by_placeholder("请输入QQ号").fill(qq, timeout=1500)
                                        location_input = page.get_by_placeholder("请选择省市区")
                                        location_input.fill(location.split("-")[0], timeout=1500)
                                        page.wait_for_timeout(1500)
                                        try:
                                            if location.split("-")[1] == location.split("-")[0]:
                                                location_input.press("Enter", delay=1000)
                                            else:
                                                page.get_by_text(location.split("-")[1]).click(timeout=1500)
                                        except:
                                            pass
                                        page.wait_for_timeout(1500)
                                        page.get_by_placeholder("请输入详细地址").fill(address, timeout=1500)
                                        page.get_by_placeholder("请填写稿费收款银行卡号").fill(bank_account, timeout=1500)
                                        bank_branch_input = page.get_by_placeholder("请输入关键字搜索支行名称，例如：工行-北京-中关村")
                                        bank_branch_input.fill(bank_branch, timeout=1500)
                                        page.wait_for_timeout(1500)
                                        bank_branch_input.press("Enter", delay=1000)
                                        page.wait_for_timeout(1500)
                                        page.get_by_role("button", name="确认无误，提交").click(timeout=1500)
                                        # page.wait_for_timeout(1500)
                                        # page.get_by_role("button", name="生成合同").click(timeout=1500)
                                        # page.get_by_role("button", name="立即签约").click(timeout=120000)

                                        print("自动签约完成！")
                                        page.wait_for_timeout(timeout=10000)
                                        browser.close()
                                        break
                                    else:
                                        print("正在评估中...")
                                        page.wait_for_timeout(timeout=1000*60*60)
                                        # 等待评估完成 一小时一巡查
                                else:
                                    print("未申请签约")
                                    row.get_by_role("button", name="签约管理").click(timeout=1500)
                                    row.get_by_role("button", name="申请签约").click(timeout=1500)
                                    page.wait_for_timeout(timeout=5000)
                                    row.get_by_text("申请签约").last.click(timeout=1500)
                                    ctx.novel_status = '签约审核中'
                                    _save_status(ctx)
                            ctx.novel_status = '待签约'
                            _save_status(ctx)
                            break
                    except Exception as e:
                        print(f"自动签约过程中出现错误: {e}")
                        traceback.print_exc()
                if getattr(ctx, 'novel_status', '') != '待签约':
                    print(f"未找到笔名{ctx.writer}的签约信息！")
        else:
            print("缺少签约信息文件")
            print("请在项目根目录下创建’签约信息.txt‘文件")
            print("格式为——\n笔名：XXXX\n- 电话：13800000000\n- 邮箱：123@xx.com\n- QQ账号：123456789\n- 联系地址：辽宁-沈阳 or 上海-上海 \n- 详细地址：XXXXXX\n- 银行卡号：XXXXXXXXXXXXXXXX\n- 所属支行：XXXX")
            print("笔名作为二次验证，需要和界面填写一致")
    except Exception as e:
        print(f"自动签约过程中出现错误: {e}")
        traceback.print_exc()
        return False
    return True


def run_verify(ctx) -> bool:
    """自动验证（原 app.py scheduled_verify 1086-1193）。长任务：最长等待 12 小时。

    在番茄作者后台检查作品推荐状态：未开始推荐则点击推荐并等待
    wait_for_timeout(1000*61*60)（约 1 小时）评估；未申请签约时
    wait_for_timeout(60*60*1000*12) 等待 12 小时后重新检查。
    状态变化通过 ctx.novel_status（'推荐评估中'）记录并持久化。
    """
    if ctx.publish_plate != "番茄":
        print("自动验证仅支持番茄平台")
        return False
    print("=====================================")
    print("自动验证线程已启动")
    print("注意，需要预先上传非模版封面并在作品推荐中进行确认")
    custom_browser_path = ctx.browser_path
    site_url = ctx.site_url
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=ctx.keep_browser_open,
                executable_path=custom_browser_path if custom_browser_path else None,
                args=[
                    "--disable-popup-blocking",  # 禁用弹窗拦截
                    "--disable-web-security",  # 禁用网页安全策略
                    "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                    "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                ],
                ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
            )
            if not os.path.exists(ctx.auth_file):
                print(f"错误：未找到认证文件 {ctx.auth_file} 请先执行登录操作")
                raise RuntimeError(f"未找到认证文件 {ctx.auth_file} 请先执行登录操作")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                storage_state=ctx.auth_file)
            page = context.new_page()
            novel_title = ctx.novel_title

            # 刷新网页
            while True:
                if site_url:
                    page.goto(site_url, timeout=60000)
                    print(f"已导航到: {site_url}")
                    page.wait_for_load_state("networkidle")
                # 尝试关闭初始引导浮窗
                try:
                    page.click('div.user-guide-btn > button', timeout=1000)
                    print("已关闭初始引导浮窗。")
                except Exception:
                    print("未找到初始引导浮窗，继续执行...")

                print("点击进入小说列表页面...")
                novel_list_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
                try:
                    page.wait_for_selector(novel_list_selector, timeout=60000)  # 等待元素出现
                    page.click(novel_list_selector, timeout=60000)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    raise RuntimeError(f"点击小说列表导航元素时发生错误: {e}")

                print(f"正在查找小说: '{novel_title}'")

                page.wait_for_selector('[id^="long-article-table-item-"]')
                page.wait_for_timeout(3000)  # 等待一下，确保加载完成
                novel_items = page.query_selector_all('[id^="long-article-table-item-"]')

                for item in novel_items:
                    title_element = item.query_selector(
                        'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div')
                    # print(title_element.inner_text())
                    if title_element and title_element.inner_text() == novel_title:
                        print(f"找到小说 '{novel_title}'。")
                        # 定位到“更新章节”按钮
                        item.hover(timeout=3000)  # 鼠标悬停到该小说条目，确保按钮可见
                        break

                if page.get_by_role("button", name="作品推荐").count() == 0:
                    if page.get_by_role("button", name="申请签约").count() != 0:
                        print("未申请签约")
                        page.wait_for_timeout(timeout=60*60*1000*12)
                        continue
                    else:
                        if page.get_by_text("签约审核已通过，请尽快完成合同签约").count() != 0:
                            page.wait_for_timeout(timeout=60*60*1000)
                            continue
                        break
                else:
                    print("未开始推荐")
                    page.get_by_role("button", name="作品推荐").click(timeout=1500)
                    page.wait_for_load_state('load')
                    try:
                        page.locator("div.recommend-area.prepare-recommend > div.recommend-action > button").click(timeout=1500)
                        page.wait_for_timeout(1000*61*60)
                        ctx.novel_status = '推荐评估中'
                        _save_status(ctx)
                    except:
                        traceback.print_exc()
                        print("自动验证失败！")
                        break
    except Exception as e:
        print(f"自动签约过程中出现错误: {e}")
        traceback.print_exc()
        return False
    return True


def run_book_test(ctx) -> bool:
    """书测（原 app.py schedule_command_by_name 1195-1304）。

    在番茄作者后台"小说推荐"页按 书测/ 目录下的封面图逐张配置实验，
    完成后重命名目录为 书测/已完成yyyymmddhhMM。
    封面目录取 os.path.dirname(ctx.config_file) 下的 '书测'。
    状态变化通过 ctx.novel_status（'书测中'）记录并持久化。
    """
    if ctx.publish_plate != "番茄":
        print("书测仅支持番茄平台")
        return False
    print("=====================================")
    custom_browser_path = ctx.browser_path
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=ctx.keep_browser_open,
                executable_path=custom_browser_path if custom_browser_path else None,
                args=[
                    "--disable-popup-blocking",  # 禁用弹窗拦截
                    "--disable-web-security",  # 禁用网页安全策略
                    "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                    "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                ],
                ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
            )
            if not os.path.exists(ctx.auth_file):
                raise FileNotFoundError(f"未找到认证文件 {ctx.auth_file}")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                storage_state=ctx.auth_file)
            page = context.new_page()
            novel_title = ctx.novel_title
            site_url = ctx.site_url

            page.goto(site_url, timeout=60000, wait_until='domcontentloaded')

            print("点击进入小说推荐页面...")
            novel_command_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(7) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
            try:
                page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                page.click(novel_command_selector, timeout=1500)  # 延长点击超时
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
                    page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    raise RuntimeError(f"点击小说列表导航元素时发生错误: {e}")
            print(f"正在查找小说: '{novel_title}'")
            page.get_by_text('切换作品').last.click(timeout=3000)
            page.wait_for_load_state('load')
            page.wait_for_timeout(1500)
            try:
                page.get_by_text(novel_title).last.click(timeout=3000)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
                page.get_by_text('确定').last.click(timeout=3000)
                page.get_by_text('配置实验').last.click(timeout=3000)
            except Exception:
                raise RuntimeError(f"未找到小说 '{novel_title}'")
            cover_dir_path = os.path.join(os.path.dirname(ctx.config_file), '书测')
            #cover_dir_path = os.path.join(os.getcwd(), '书测')
            if os.path.exists(cover_dir_path):
                for filename in os.listdir(cover_dir_path):
                    if filename.endswith('.jpg') or filename.endswith('.png'):
                        new_title = os.path.splitext(filename)[0].strip('-封面').strip()
                        page.get_by_placeholder('请输入书名').last.fill(new_title, timeout=3000)
                        page.locator(' div.ne-config-item-body > div.ne-config-item-body-cover').last.click(timeout=3000)
                        page.get_by_text('本地上传', exact=True).last.click(timeout=1500)
                        page.locator('div.cover-upload input[type="file"]').set_input_files(os.path.join(cover_dir_path, filename))
                        page.wait_for_timeout(1000)
                        page.wait_for_load_state('networkidle')
                        page.get_by_text('确认上传', exact=True).last.click(timeout=1500)
                        page.wait_for_timeout(1500)
                        page.wait_for_load_state('load')
                        page.get_by_text('确定', exact=True).last.click(timeout=1500)
                        try:
                            page.get_by_text('添加实验组').last.click(timeout=3000)
                        except Exception:
                            break
            else:
                raise RuntimeError("未找到书测封面目录")
            page.get_by_text('提交', exact=True).click(timeout=1500)
            page.get_by_text('确认', exact=True).click(timeout=1500)
            page.wait_for_timeout(1500)
            os.rename(cover_dir_path, cover_dir_path+f'已完成{datetime.datetime.now().strftime("%Y%m%d%H%M")}')
            page.wait_for_load_state('networkidle')
            page.wait_for_load_state('load')
        ctx.novel_status = '书测中'
        _save_status(ctx)
    except Exception as e:
        print(f"书测过程中出现错误: {e}")
        traceback.print_exc()
        return False
    return True


def run_cover_test(ctx) -> bool:
    """封测（原 app.py schedule_command_by_cover 1306-1433）。

    在番茄作者后台"小说推荐-多封面推荐"页按 封测/（os.getcwd() 下）目录的
    封面图逐张配置封面并提交审核，完成后重命名目录为 封测/已完成yyyymmddhhMM。
    状态变化通过 ctx.novel_status（'封测中'）记录并持久化。
    """
    if ctx.publish_plate != "番茄":
        print("封测仅支持番茄平台")
        return False
    print("=====================================")
    custom_browser_path = ctx.browser_path
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=ctx.keep_browser_open,
                executable_path=custom_browser_path if custom_browser_path else None,
                args=[
                    "--disable-popup-blocking",  # 禁用弹窗拦截
                    "--disable-web-security",  # 禁用网页安全策略
                    "--disable-features=IsolateOrigins,site-per-process",  # 禁用同源策略隔离
                    "--disable-blink-features=AutomationControlled"  # 防止网站检测自动化工具
                ],
                ignore_default_args=["--enable-automation"]  # 忽略默认的自动化标志
            )
            if not os.path.exists(ctx.auth_file):
                raise FileNotFoundError(f"未找到认证文件 {ctx.auth_file}")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                storage_state=ctx.auth_file)
            page = context.new_page()
            novel_title = ctx.novel_title
            site_url = ctx.site_url

            page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
            print("点击进入小说推荐页面...")
            novel_command_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(7) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
            try:
                page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                page.click(novel_command_selector, timeout=1500)  # 延长点击超时
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
                    page.wait_for_selector(novel_command_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_command_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"点击小说列表导航元素时发生错误: {e}")
                    raise  # 重新抛出异常以便上层捕获
            print(f"正在查找小说: '{novel_title}'")
            page.get_by_text('多封面推荐').last.click(timeout=1500)
            try:
                page.get_by_text('我知道了').last.click(timeout=1500)
            except Exception:
                pass
            cover_selector = '#app > div > div.content.new-content > div.serial-card.serial-card-large.content-card-wrap.path-prefix-multi-cover > div > div.book-select.multi-cover-select-book-card > div.book-select-info > div.book-select-info-title'
            page.wait_for_load_state('load')
            while page.locator(cover_selector).inner_text() != novel_title:
                page.get_by_text('切换作品').last.click(timeout=3000)
                page.wait_for_timeout(3000)
                page.wait_for_load_state('load')
                page.get_by_text(novel_title).last.click(timeout=3000, force=True)
                # page.get_by_text(novel_title).last.click(timeout=3000, force=True)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.get_by_text('确定').last.click(timeout=3000)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
            cover_dir_path = os.path.join(os.getcwd(), '封测')
            new_title = ''
            if os.path.exists(cover_dir_path):
                for filename in os.listdir(cover_dir_path):
                    if filename.endswith('.jpg') or filename.endswith('.png'):
                        new_title = os.path.splitext(filename)[0].split('_')[0]
                        break
            else:
                print("未找到封测封面目录")
            if new_title == novel_title:
                # 封说标题匹配，点击立即配置
                print("原书名封测")
                page.get_by_text('立即配置').first.click(timeout=3000)
            else:
                print("书测名封测")
                page.get_by_text('立即配置').last.click(timeout=3000)

            for filename in os.listdir(cover_dir_path):
                if filename.endswith('.jpg') or filename.endswith('.png'):
                    new_title = os.path.splitext(filename)[0].split('_')[0]
                    page.get_by_text('本地上传', exact=True).last.click(timeout=1500)
                    page.locator('div.cover-upload input[type="file"]').set_input_files(os.path.join(cover_dir_path, filename))
                    page.wait_for_timeout(1000)
                    page.wait_for_load_state('networkidle')
                    page.get_by_text('确认上传', exact=True).last.click(timeout=1500)
                    page.wait_for_timeout(1500)
                    page.wait_for_load_state('load')
                    page.get_by_text('确定', exact=True).last.click(timeout=1500)
                    try:
                        page.get_by_text('配置封面').first.click(timeout=3000)
                    except Exception:
                        break

            page.get_by_text('提交审核').last.click(timeout=3000)
            page.get_by_text('确认').last.click(timeout=3000)
            page.wait_for_timeout(1500)
            os.rename(cover_dir_path, cover_dir_path+f'已完成{datetime.datetime.now().strftime("%Y%m%d%H%M")}')
            page.wait_for_load_state('networkidle')
            page.wait_for_load_state('load')
        ctx.novel_status = '封测中'
        _save_status(ctx)
    except Exception as e:
        print(f"封测过程中出现错误: {e}")
        traceback.print_exc()
        return False
    return True


def run_attendance(ctx) -> bool:
    """全勤检查（原 app.py schedule_check_attendance 1435-1587）。

    在番茄作者后台检查当月听读收益（>=500 元具备全勤实力）与发布记录
    （每天 >=4000 字、>=6000 字天数统计），结果通过 ctx.novel_status
    （'有全勤实力'/'全勤中'/'有缺勤'）记录并持久化。
    浏览器通过 novel_publisher.browser.open_browser 启动（支持 CDP 接管）。
    """
    if ctx.publish_plate != "番茄":
        print("全勤检查 暂时仅支持番茄平台")
        return False
    print("=====================================")
    custom_browser_path = ctx.browser_path
    try:
        with sync_playwright() as p:
            browser, context = open_browser(p, custom_browser_path, ctx.keep_browser_open, ctx.auth_file, on_browser_not_found=None)
            page = context.new_page()
            novel_title = ctx.novel_title
            site_url = ctx.site_url

            page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
            print("进入小说收益页面...")
            novel_income_selector = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(4) > div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
            try:
                page.wait_for_selector(novel_income_selector, timeout=3000)  # 等待元素出现
                page.click(novel_income_selector, timeout=1500)  # 延长点击超时
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
                    page.wait_for_selector(novel_income_selector, timeout=3000)  # 等待元素出现
                    page.click(novel_income_selector, timeout=1500)  # 延长点击超时
                    page.wait_for_load_state('domcontentloaded')
                except Exception as e:
                    print(f"点击小说列表导航元素时发生错误: {e}")
                    raise  # 重新抛出异常以便上层捕获
            print("========1、检查收益情况========")
            check_res1 = False
            name_selector = 'div > div > div.book-select > div.book-select-info > div.book-select-info-title'
            if page.locator(name_selector).inner_text() != novel_title:
                page.get_by_text('切换作品').last.click(timeout=3000)
                page.wait_for_load_state('domcontentloaded')
                page.get_by_text(novel_title).last.click(timeout=3000)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
                page.get_by_text('确定').last.click(timeout=3000)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
            page.get_by_text('自定义').last.click(timeout=3000)
            current_date = datetime.datetime.now()
            # 采取当月1号作为开始日期,昨天为结束日期
            start_date = current_date.replace(day=1)
            end_date = (current_date - datetime.timedelta(days=1))
            page.get_by_placeholder('开始日期').fill(start_date.strftime('%Y-%m-%d'), timeout=3000)
            page.get_by_placeholder('结束日期').fill(end_date.strftime('%Y-%m-%d'), timeout=3000)
            page.get_by_placeholder('结束日期').press('Enter', timeout=3000)
            page.wait_for_timeout(3000)
            page.wait_for_load_state('load')
            table_count = page.locator('td:nth-child(1)').count()
            print(f"当前查询时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            print(f"当前查询到 {table_count} 条数据")
            all_income = 0
            for i in range(table_count):
                income_by_read = page.locator('td:nth-child(3)').nth(i).inner_text().replace('元', '')
                income_by_read = income_by_read.replace(',', '')
                income_by_listen = page.locator('td:nth-child(4)').nth(i).inner_text().replace('元', '')
                income_by_listen = income_by_listen.replace(',', '')
                all_income = all_income + float(income_by_read) + float(income_by_listen)
            print(f"当前听读总收益: {all_income:.2f}元, 日均收益: {all_income/table_count:.2f}元")
            month_days = ((start_date+datetime.timedelta(days=31)).replace(day=1) - start_date).days
            print(f"估计本月收益: {(all_income/table_count) * month_days:.2f}元")
            if all_income >= 500:
                check_res1 = True
                print("当前听读收益已超过500元，具备全勤实力！")
            # 平均值乘以当月的天数大于500元，具备全勤实力（当月不一定30天）
            elif (all_income/table_count) * month_days >= 500:
                check_res1 = False
                print("估计本月听读收益已超过500元，具备一定的全勤实力")
                ctx.novel_status = '有全勤实力'
            else:
                check_res1 = False
                print("估计本月听读收益不足500元，无全勤")
            print("========2、检查发布情况========")
            check_res2 = True
            plate_init = '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(1) > div > span.new-nav-item-content'
            page.wait_for_selector(plate_init, timeout=3000)  # 等待元素出现
            page.click(plate_init, timeout=1500)  # 延长点击超时
            page.wait_for_timeout(1500)
            page.wait_for_load_state('load')

            book_trigger = 'div.clock-in-calendar-filters > div.filter-book-trigger'
            while page.locator(book_trigger).inner_text() != novel_title:
                page.click(book_trigger, timeout=1500)  # 延长点击超时
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
                page.get_by_text(novel_title).last.click(timeout=3000)
                page.wait_for_timeout(1500)
                page.wait_for_load_state('load')
                page.wait_for_timeout(1500)
            # self.debug()
            n = 0
            m = 0
            for i in range(page.locator('div > div.content-value').count()):
                publish_words_count_element = page.locator('div > div.content-value').nth(i)
                if publish_words_count_element.inner_text().isdigit():
                    publish_words_count = int(publish_words_count_element.inner_text())
                    publish_date = publish_words_count_element.locator('..').locator('div.content-date').inner_text()
                    if publish_words_count >= 6000:
                        n += 1
                        m += 1
                    elif publish_words_count >= 4000:
                        m += 1
                        print(f"{publish_date}号发布字数{publish_words_count}，不足6000字")
                    else:
                        print(f"{publish_date}号发布字数{publish_words_count}，不足4000字")
                        check_res2 = False
            #print(f"当前查询到 {page.locator('div > div.content-value').count()} 条数据")
            if m != month_days:
                check_res2 = False

            if check_res1 and check_res2:
                print("全勤检查通过")
                if n == month_days:
                    print("并且为进阶版全勤")
                else:
                    print(f"日更6000+仅有{n}天")
                ctx.novel_status = '全勤中'
            else:
                if not check_res2:
                    print("本月有缺勤，请查看发布记录")
                    ctx.novel_status = '有缺勤'
                print("全勤检查未通过")
            _save_status(ctx)
    except Exception as e:
        print(f"全勤检查过程中出现错误: {e}")
        traceback.print_exc()
        return False
    return True
