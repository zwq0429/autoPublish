"""定时任务注册表与调度"""

import threading
from typing import Callable, Dict, Optional


# 任务注册表：任务名 -> (执行函数, 是否在子线程中运行)
_TASKS: Dict[str, tuple] = {}


def register_task(name: str, threaded: bool = True):
    """装饰器：注册定时任务。

    Args:
        name: 任务名称（与界面下拉框对应）
        threaded: True 表示在子线程中执行，False 表示在主线程直接调用
    """
    def decorator(func: Callable):
        _TASKS[name] = (func, threaded)
        return func
    return decorator


def get_task(name: str) -> Optional[tuple]:
    """获取任务 (执行函数, 是否子线程)。"""
    return _TASKS.get(name)


def list_task_names() -> list:
    """返回所有已注册的任务名。"""
    return list(_TASKS.keys())


def execute_task(name: str, app) -> bool:
    """执行指定任务。

    Returns:
        True 如果任务存在并已启动，False 如果任务不存在
    """
    task = get_task(name)
    if task is None:
        return False
    func, threaded = task
    if threaded:
        threading.Thread(target=func, args=(app,), daemon=True).start()
    else:
        func(app)
    return True


# 导入适配器模块以触发任务注册
from . import adapters  # noqa: E402, F401
