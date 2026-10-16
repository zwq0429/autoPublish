"""小说下载器：支持番茄、飞卢、起点等平台"""

import os
import re
import time
import traceback

import requests
import parsel
from playwright.sync_api import sync_playwright
from tkinter import messagebox

from font_map import FONT_MAP


class NovelDownloader:
    def __init__(self, novel_plate: str, book_id: str, cookies={}):
        self.novel_plate = novel_plate
        self.book_id = book_id
        self.cookies = cookies

    @staticmethod
    def decrypt_text(content):
        """解密章节文本"""
        decrypted_chars = []
        for char in content:
            try:
                unicode_code = str(ord(char))
                real_char = FONT_MAP.get(unicode_code, char)
            except Exception:
                real_char = char
            decrypted_chars.append(real_char)
        return ''.join(decrypted_chars)

    def get_html(self, url, retries=3, timeout=10, verbose=True):
        """通用 HTML 请求函数，支持自动重试。"""
        for attempt in range(1, retries + 1):
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/114.0.0.0 Safari/537.36"
                    )
                }
                response = requests.get(url, headers=headers, timeout=timeout, cookies=self.cookies)
                if response.status_code == 200:
                    return response.text
                else:
                    if verbose:
                        print(f"[!] 第 {attempt} 次请求返回状态码: {response.status_code}")
            except requests.RequestException as e:
                if verbose:
                    print(f"[!] 第 {attempt} 次请求异常：{e}")
            time.sleep(1)
        if verbose:
            print(f"[x] 请求失败：共重试 {retries} 次，未成功获取 {url}")
        return None

    def parse_main_page(self):
        """解析小说主页，提取基本信息和章节目录"""
        if self.novel_plate == '番茄':
            url = f"https://fanqienovel.com/page/{self.book_id}"
        elif self.novel_plate == '飞卢':
            url = f"https://b.faloo.com/{self.book_id}.html"
        elif self.novel_plate == '起点':
            url = f"https://www.qidian.com/book/{self.book_id}/"
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    executable_path=r'C:\Program Files (x86)\Microsoft\Edge Dev\Application\msedge.exe',
                    args=[
                        "--disable-popup-blocking",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-blink-features=AutomationControlled"
                    ],
                    ignore_default_args=["--enable-automation"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state={}
                )
                page = context.new_page()
                page.goto(url)
                page.wait_for_load_state("networkidle")
                book_title = page.locator("#bookName").inner_text()
                author_name = page.locator("a.writer-name").inner_text()
                abstract_content = page.locator("#book-intro-detail").inner_text().splitlines()

                chapter_titles = []
                chapter_hrefs = []

                for i in range(1, page.locator("//*[@id='allCatalog']/div").count() + 1):
                    for j in range(1, page.locator(f"//*[@id='allCatalog']/div[{i}]/ul/li").count() + 1):
                        title = page.locator(f"//*[@id='allCatalog']/div[{i}]/ul/li[{j}]/a").get_attribute("alt")
                        href = page.locator(f"//*[@id='allCatalog']/div[{i}]/ul/li[{j}]/a").get_attribute('href')
                        chapter_titles.append(title.strip(book_title).strip('在线阅读').strip())
                        chapter_hrefs.append(href)
                print(f"📘 小说：《{book_title}》 by {author_name}")
                print(f"📖 共 {len(chapter_titles)} 章")
                return book_title, chapter_titles, chapter_hrefs, abstract_content
        else:
            messagebox.showerror("错误", f"不支持的平台: {self.novel_plate}")
            return None, [], []
        html = self.get_html(url)
        if not html:
            print("[x] 主页面请求失败")
            return None, [], []
        selector = parsel.Selector(html)
        if self.novel_plate == '番茄':
            try:
                book_title = selector.css('.info-name h1::text').get(default='未知标题').strip()
                author_name = selector.css('.author-name-text::text').get(default='未知作者').strip()
                chapter_count = selector.css('.page-directory-header h3::text').get(default='0').strip()
                tags = selector.css('.info-label span::text').getall()
                abstract_content = selector.css('.page-abstract-content p::text').getall()
                chapter_titles = selector.css('.chapter-item-title::text').getall()
                chapter_hrefs = selector.css('.chapter-item-title::attr(href)').getall()
                last_update_title = selector.css('.info-last-title::text').getall()[1]
                last_update_time = selector.css('.info-last-time::text').get(default='').strip()
                print(f"📘 小说：《{book_title}》 by {author_name}")
                print(f"📖 共 {chapter_count} 章；标签：{'、'.join(tags)}")
                print(f"🕘 最近更新：{last_update_title} · {last_update_time}")

                return book_title, chapter_titles, chapter_hrefs[1:], abstract_content
            except Exception as e:
                print(f"解析主页面时出错: {e}")
                traceback.print_exc()
                return None, [], []
        elif self.novel_plate == '飞卢':
            try:
                book_title = selector.css('#novelName').css('h1::text').get(default='未知标题').strip()
                author_name = selector.css('.zi1 a::attr(title)').get(default='未知作者').strip()

                abstract_content = selector.css('.T-L-T-C-Box1 p::text').getall()
                chapter_titles = [title.strip().replace(book_title + ":", '') for title in selector.css('.DivTd3 a::attr(title)').getall()] + [title.strip().replace(book_title, '') for title in selector.css('.DivTd a::attr(title)').getall()]
                chapter_hrefs = selector.css('.DivTd3 a::attr(href)').getall() + selector.css('.DivTd a::attr(href)').getall()
                chapter_count = len(chapter_titles)
                print(f"📘 小说：《{book_title}》 by {author_name}")
                print(f"📖 共 {chapter_count} 章")
                return book_title, chapter_titles, chapter_hrefs, abstract_content
            except Exception as e:
                print(f"解析主页面时出错: {e}")
                traceback.print_exc()
                return None, [], []
        else:
            messagebox.showerror("错误", f"不支持的平台: {self.novel_plate}")
            return None, [], []

    def download_chapters(self, book_title, abstract_content, titles, urls, output_dir="output"):
        """下载并解密章节"""
        if self.novel_plate != '番茄':
            print("当前只支持番茄平台的正文下载")
            return
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{book_title}.txt")
        print(f"🎁 开始下载小说《{book_title}》")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"书名：《{book_title}》\n\n简介：\n")
            f.write("\n".join(abstract_content))
            f.write("\n\n")
            for title, link in zip(titles, urls):
                full_url = 'https://fanqienovel.com' + link
                html = self.get_html(full_url)
                if not html:
                    print(f"[x] 章节《{title}》请求失败，已跳过")
                    continue
                selector = parsel.Selector(html)
                content_list = selector.css('.muye-reader-content-16 p::text').getall()
                raw_text = '\n'.join(content_list)
                decrypted_text = self.decrypt_text(raw_text)
                f.write(f"\n\n{title}\n\n")
                f.write(decrypted_text)
                print(title)
        print(f"🎉 已保存至：{file_path}")
        os.startfile(file_path)

    def debug(self):
        import inspect
        outer_locals = inspect.currentframe().f_back.f_locals
        outer_globals = inspect.currentframe().f_back.f_globals
        exec_namespace = {**outer_globals, **outer_locals, **self.__dict__}
        while True:
            code = input("请输入代码：")
            try:
                exec(code, exec_namespace, exec_namespace)
            except Exception:
                traceback.print_exc()
