"""公共页面导航 helper：goto / 点小说列表 / 关浮窗 / 翻页找书"""

# 番茄小说列表选择器
FANQIE_NOVEL_LIST_SELECTOR = (
    '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) '
    '> div.new-nav-children.new-nav-children-expanded > div:nth-child(1)'
)

# 番茄短故事列表选择器
FANQIE_STORY_LIST_SELECTOR = (
    '#app > div > div.content.new-content > div.serial-affix > div > div > div > div > div:nth-child(2) '
    '> div.new-nav-children.new-nav-children-expanded > div:nth-child(2)'
)

# 各平台作者后台 URL
SITE_URLS = {
    '番茄': "https://fanqienovel.com/main/writer/?enter_from=author_zone",
    '起点': "https://write.qq.com/portal/dashboard",
    'Q阅': "https://write.qq.com/portal/dashboard",
    '七猫': "https://zuozhe.qimao.com/front/index",
    '纵横': "https://zuozhe.qimao.com/front/index",
    '飞卢': "https://author.faloo.com/index2020.aspx",
    '微信': "https://mp.weixin.qq.com/cgi-bin/home",
    '书旗': "https://yc.aliwx.com.cn/author",
    '晋江': "https://my.jjwxc.net/backend/oneauthor_login.php",
    '息壤': "https://www.xrzww.com/authorhome/workmanagement",
}


def get_site_url(publish_plate: str) -> str:
    """根据发布平台返回作者后台 URL。"""
    if publish_plate not in SITE_URLS:
        raise ValueError(f"不支持发布平台: {publish_plate}")
    return SITE_URLS[publish_plate]


def handle_fanqie_floats(page):
    """关闭番茄作者后台常见的悬浮窗（引导浮窗、补签卡等）。"""
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


def click_novel_list_fanqie(page):
    """点击进入番茄小说列表页面，处理悬浮窗遮挡。"""
    print("点击进入小说列表页面...")
    try:
        page.wait_for_selector(FANQIE_NOVEL_LIST_SELECTOR, timeout=3000)
        page.click(FANQIE_NOVEL_LIST_SELECTOR, timeout=1500)
        page.wait_for_load_state('domcontentloaded')
    except Exception as e:
        print(f"可能有悬浮窗遮挡，尝试关闭初始引导浮窗")
        handle_fanqie_floats(page)
        try:
            print("重新点击进入小说列表页面...")
            page.wait_for_selector(FANQIE_NOVEL_LIST_SELECTOR, timeout=3000)
            page.click(FANQIE_NOVEL_LIST_SELECTOR, timeout=1500)
            page.wait_for_load_state('domcontentloaded')
        except Exception as e:
            print(f"点击小说列表导航元素时发生错误: {e}")
            raise


def find_novel_in_fanqie_list(page, novel_title: str, on_found=None) -> bool:
    """在番茄小说列表中翻页查找指定小说。

    Args:
        page: Playwright Page 实例
        novel_title: 要查找的小说标题
        on_found: 找到小说时的回调 (item) -> None，用于处理状态信息等

    Returns:
        True 如果找到小说，False 如果未找到
    """
    print(f"正在查找小说: '{novel_title}'")

    while True:
        page.wait_for_selector('[id^="long-article-table-item-"]')
        page.wait_for_timeout(3000)
        novel_items = page.query_selector_all('[id^="long-article-table-item-"]')
        update_button = None
        print(len(novel_items))
        for item in novel_items:
            title_element = item.query_selector(
                'div > div.book-item-info > div.info-content > div.info-content-title.font-1 > div')
            print(title_element.inner_text())
            if title_element and title_element.inner_text() == novel_title:
                print(f"找到小说 '{novel_title}'。")
                item.hover(timeout=3000)
                page.wait_for_timeout(1000)
                page.wait_for_load_state('domcontentloaded')
                if on_found:
                    on_found(item)
                update_button = True
        if not update_button:
            next_page_button_limit = page.query_selector(
                '#arco-tabs-3-panel-0 > div > div > div > '
                'div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination '
                '> ul > li.arco-pagination-item.arco-pagination-item-next.arco-pagination-item-disabled')
            next_page_button = page.query_selector(
                "#arco-tabs-1-panel-0 > div > div > div > "
                "div.arco-pagination.arco-pagination-size-default.serial-pagination.long-article-table-pagination "
                "> ul > li.arco-pagination-item.arco-pagination-item-next")
            if next_page_button and not next_page_button_limit:
                next_page_button.click()
                page.wait_for_load_state('networkidle')
            else:
                print(f"错误：在列表中未找到小说 '{novel_title}'")
                return False
        else:
            return True


def navigate_to_fanqie_novel_list(page, site_url: str):
    """番茄专用：导航到作者后台并进入小说列表页面。"""
    print("导航到作者后台...")
    page.goto(site_url, timeout=60000, wait_until='domcontentloaded')
    click_novel_list_fanqie(page)
