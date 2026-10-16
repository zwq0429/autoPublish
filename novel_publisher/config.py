"""发布配置数据结构"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class PublishConfig:
    """发布配置，替代原来的 15 元素元组。

    通过 __getitem__ / __len__ 支持切片操作，
    兼容现有 normal_config[:13] / normal_config[:15] 调用方式。
    """
    custom_browser_path: str = ''
    site_url: str = ''
    novel_title: str = ''
    novels_folder: str = ''
    publish_mode: str = ''
    start_chapter: int = 0
    end_chapter: int = 0
    keep_browser_open: bool = False
    novel_files: list = field(default_factory=list)
    init_daily_publish_count: int = 0
    init_daily_publish_num: int = 0
    daily_publish_count: int = 0
    daily_publish_num: int = 0
    interval_days: int = 1
    interval_tag: int = 0

    def as_tuple(self):
        """返回与原元组完全一致的顺序。"""
        return (
            self.custom_browser_path,
            self.site_url,
            self.novel_title,
            self.novels_folder,
            self.publish_mode,
            self.start_chapter,
            self.end_chapter,
            self.keep_browser_open,
            self.novel_files,
            self.init_daily_publish_count,
            self.init_daily_publish_num,
            self.daily_publish_count,
            self.daily_publish_num,
            self.interval_days,
            self.interval_tag,
        )

    def __getitem__(self, index):
        return self.as_tuple()[index]

    def __len__(self):
        return len(self.as_tuple())

    def __iter__(self):
        return iter(self.as_tuple())
