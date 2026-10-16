"""平台策略基类与注册表"""

from abc import ABC, abstractmethod
from typing import Dict, Type


class BasePlatform(ABC):
    """发布平台抽象基类。

    子类需实现 run() 方法，完成从加载配置到发布章节的完整流程。
    """

    #: 平台名称（与界面下拉框对应）
    name: str = ''

    @abstractmethod
    def run(self, app) -> bool:
        """执行发布流程。

        Args:
            app: NovelPublisherApp 实例，提供配置、浏览器、日志等能力

        Returns:
            True 表示成功，False 表示失败
        """
        ...


# 平台注册表：平台名 -> 平台类
# 初始为空，各平台模块在导入时自行注册
PLATFORMS: Dict[str, BasePlatform] = {}


def register_platform(cls):
    """装饰器：将平台类注册到 PLATFORMS。"""
    PLATFORMS[cls.name] = cls()
    return cls


def get_platform(name: str):
    """根据平台名获取平台实例。"""
    return PLATFORMS.get(name)


# 导入适配器模块以触发平台注册
from . import adapters  # noqa: E402, F401
