"""发布流程运行时状态与配置加载。

把原 NovelPublisherApp 上与发布流程相关的运行时属性/方法
(stop_publish_sign、publish_time、check_interval_publish、
get_chapter_details、_normal_save_config 等) 抽象为 FlowState，
使 novel_publisher/platforms/*.py 中的流程函数不再依赖 Tk UI 实例，
可被 CLI 工具直接调用。
"""

import configparser
import datetime
import os
import threading

from .chapter_files import (
    get_chapter_files_in_range,
    get_chapter_details as _cf_get_details,
    count_chinese_characters as _cf_count_chinese,
    check_repeat_content as _cf_check_repeat,
)
from .config import PublishConfig
from .navigation import get_site_url

CONFIG_FILE = r'config.ini'
AUTH_FILE = r'auth.json'


class FlowState:
    """发布流程运行时状态容器（替代原 app 实例上的相关属性）。

    平台流程函数通过 state 访问：
      state.cfg                    PublishConfig 发布配置
      state.config                 configparser 实例（读写 config.ini）
      state.config_file            配置文件路径
      state.publish_time           当前计划发布时间 (datetime)
      state.novel_status           小说状态（推荐状态机结果，会持久化）
      state.scheduled_task         当前任务名（如 '本地定时发布'，可为 ''）
      state.stop_publish_sign      停止标志（可读写，线程安全）
      state.wait_event             等待事件
      state.neat_index             章节序号整理开关
    """

    def __init__(self, cfg: PublishConfig, config: configparser.ConfigParser = None,
                 config_file: str = CONFIG_FILE, scheduled_task: str = '',
                 neat_index: bool = True, stop_event: threading.Event = None,
                 platform: str = ''):
        self.cfg = cfg
        self.platform = platform
        self.config = config if config is not None else configparser.ConfigParser()
        self.config_file = config_file
        self.scheduled_task = scheduled_task or ''
        self.wait_event = threading.Event()
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.neat_index = neat_index
        self.publish_time = datetime.datetime.now()
        self.novel_status = ''
        if self.config.has_option('Novel', 'novel_status'):
            self.novel_status = self.config.get('Novel', 'novel_status', fallback='未设置')

    # ---- 停止标志（原 self.stop_publish_sign） ----
    @property
    def stop_publish_sign(self) -> bool:
        return self.stop_event.is_set()

    @stop_publish_sign.setter
    def stop_publish_sign(self, value: bool):
        if value:
            self.stop_event.set()
        else:
            self.stop_event.clear()

    # ---- 上次发布日期（原 self.last_published_chapter_date_var） ----
    @property
    def last_published_chapter_date(self) -> str:
        return self.config.get('History', 'last_published_chapter_date',
                               fallback=self.publish_time.strftime('%Y-%m-%d'))

    @last_published_chapter_date.setter
    def last_published_chapter_date(self, value: str):
        if not self.config.has_section('History'):
            self.config['History'] = {}
        self.config['History']['last_published_chapter_date'] = value

    # ---- 间隔发布判断（原 self.check_interval_publish） ----
    def check_interval_publish(self, check_date: datetime.datetime = None) -> bool:
        cfg = self.cfg
        try:
            cycle = int(cfg.interval_days)
            remainder = int(cfg.interval_tag)
            if cycle == 1 and remainder == 0:
                return True
            if check_date is None:
                check_date = datetime.datetime.now()
            return (check_date.toordinal() % cycle) == remainder
        except Exception:
            pass
        return True

    # ---- 章节工具（原 self.get_chapter_details / count_chinese_characters / check_repeat_content） ----
    def get_chapter_details(self, filepath: str):
        return _cf_get_details(filepath, self.neat_index)

    get_chapter_files_in_range = staticmethod(get_chapter_files_in_range)

    @staticmethod
    def count_chinese_characters(text: str) -> int:
        return _cf_count_chinese(text)

    @staticmethod
    def check_repeat_content(content: str) -> str:
        return _cf_check_repeat(content)

    def debug(self):
        """原调试函数的空实现（CLI 场景无意义）。"""
        pass

    # ---- 进度保存（原 self._normal_save_config，去掉 UI 更新） ----
    def save_history(self, list_count, daily_publish_num, daily_publish_count,
                     end_chapter, publish_mode):
        """发布完成后把进度写回配置文件。"""
        end_chapter -= list_count
        if publish_mode == '修改章节':
            print(f"已修改成功章节至：{end_chapter}")
            print("修改章节不保存和更改配置")
            return

        if self.cfg.init_daily_publish_num != -1:
            if daily_publish_num == self.cfg.init_daily_publish_num:
                daily_publish_num = 0
                self.publish_time -= datetime.timedelta(days=1)
        else:
            if daily_publish_count == self.cfg.init_daily_publish_count:
                daily_publish_count = 0
                self.publish_time -= datetime.timedelta(days=1)

        if not self.config.has_section('History'):
            self.config['History'] = {}

        if publish_mode == '定时发布' or ('本地定时发布' in self.scheduled_task):
            self.config['History']['daily_publish_num_remain'] = str(daily_publish_num)
            self.config['History']['daily_publish_count_remain'] = str(daily_publish_count)
        else:
            self.publish_time = datetime.datetime.now()
            self.config['History']['daily_publish_num_remain'] = str(list_count)
            self.config['History']['daily_publish_count_remain'] = '0'

        self.config['History']['last_published_chapter'] = str(end_chapter)
        self.config['History']['last_published_chapter_date'] = self.publish_time.strftime('%Y-%m-%d')
        if not self.config.has_section('Novel'):
            self.config['Novel'] = {}
        self.config['Novel']['novel_status'] = self.novel_status
        self._write_config()
        print(f"进度已保存: 已发布至第 {end_chapter} 章")

    def _write_config(self):
        for section in ('Settings', 'Novel', 'History'):
            if not self.config.has_section(section):
                self.config[section] = {}
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

    # ---- 错误提示（原 self._normal_error_print，去掉 refresh_ui） ----
    def error_hint(self):
        print("主自动化流程中发生错误:")
        print("常见流程问题有(如果日志中未提交错误原因，可能是以下问题)：")
        print("1)登陆失效\n2)时间格式错误\n3)上次剩余章节/字数为空\n4)定时时间离当前时间间隔不足30分钟")
        print("常见章节问题有(一般会显示在日志中)：")
        print("1)章节号和序号对应不上\n2)章节标题太长\n3)章节内容不够 1000字\n4)章节标题重复\n5)章节内容有重复内容")


class ConfigLoadError(Exception):
    """发布配置加载失败。"""


def load_publish_config(config_file: str = CONFIG_FILE, auth_file: str = AUTH_FILE,
                        overrides: dict = None, scheduled_task: str = '',
                        interactive_confirm: bool = False) -> FlowState:
    """从配置文件加载发布配置（原 self._normal_load_config 的无 UI 版本）。

    Args:
        overrides: 可选覆盖项，键与 PublishConfig 字段名对应：
            platform, publish_mode, novel_title, novels_folder,
            start_chapter, end_chapter, keep_browser_open,
            daily_publish_num, daily_publish_count, interval_mode, publish_time

    Returns:
        FlowState

    Raises:
        ConfigLoadError: 配置不合法（缺少登录文件、小说文件夹不存在等）
    """
    overrides = overrides or {}
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
        if config.get('Settings', 'publish_mode', fallback='') in ['publish', '立刻发布']:
            config['Settings']['publish_mode'] = '立刻发布'
        elif config.get('Settings', 'publish_mode', fallback='') in ['pre-publish', '定时发布']:
            config['Settings']['publish_mode'] = '定时发布'
        else:
            config['Settings']['publish_mode'] = '保存为草稿'
    else:
        raise ConfigLoadError(f"错误：找不到配置文件 {config_file}")

    def setting(key, fallback=''):
        return overrides.get(key, config.get('Settings', key, fallback=fallback))

    def novel(key, fallback=''):
        return overrides.get(key, config.get('Novel', key, fallback=fallback))

    custom_browser_path = setting('custom_browser_path')
    platform_name = setting('platform', config.get('Settings', 'publish_plate', fallback='番茄'))
    publish_mode = setting('publish_mode', '立刻发布')
    publish_time_str = setting('publish_time', '00:00').replace('：', ':')
    interval_mode = setting('interval_mode',
                            config.get('Settings', 'interval_publish_mode', fallback='1/0'))
    keep_browser_open = str(setting('keep_browser_open',
                                    config.get('Settings', 'close_browser_open', fallback='False')))\
        .lower() in ('1', 'true', 'yes')

    init_daily_publish_num = int(overrides.get('daily_publish_num',
                                               config.get('Settings', 'daily_publish_num', fallback='2')))
    init_daily_publish_count = int(overrides.get('daily_publish_count',
                                                 config.get('Settings', 'daily_publish_count', fallback='4000')))
    daily_publish_num = int(config.get('History', 'daily_publish_num_remain', fallback='0'))
    daily_publish_count = int(config.get('History', 'daily_publish_count_remain', fallback='0'))

    try:
        interval_days, interval_tag = int(interval_mode.split('/')[0]), int(interval_mode.split('/')[1])
    except Exception:
        raise ConfigLoadError(f"错误：间隔发布模式格式错误: {interval_mode}")

    novel_title = novel('novel_title', '你的小说名(完整无误的)')
    novels_folder = novel('novels_folder', '')
    neat_index = config.getboolean('Settings', 'neat_index', fallback=True)

    if custom_browser_path.isdigit():
        print("自行登录模式")
    elif not os.path.exists(auth_file):
        raise ConfigLoadError(f"错误：找不到登录状态文件 {auth_file}。请先登录，允许扫码登录。")

    if not os.path.isdir(novels_folder):
        raise ConfigLoadError(f"错误：小说文件夹 {novels_folder} 不存在。")

    if 'start_chapter' in overrides or 'end_chapter' in overrides:
        start_chapter = int(overrides.get('start_chapter', 1))
        end_chapter = int(overrides.get('end_chapter', start_chapter))
    else:
        last_published_chapter = int(config.get('History', 'last_published_chapter', fallback='0'))
        start_chapter = last_published_chapter + 1
        end_chapter = last_published_chapter + (init_daily_publish_num if init_daily_publish_num != -1 else 1)

    novel_files = get_chapter_files_in_range(novels_folder, start_chapter, end_chapter)
    if not novel_files:
        raise ConfigLoadError(f"在文件夹 {novels_folder} 中没有找到要发布的小说文件（第 {start_chapter}-{end_chapter} 章）。")

    state = FlowState(
        cfg=PublishConfig(
            custom_browser_path=custom_browser_path,
            site_url=get_site_url(platform_name),
            novel_title=novel_title,
            novels_folder=novels_folder,
            publish_mode=publish_mode,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            keep_browser_open=keep_browser_open,
            novel_files=novel_files,
            init_daily_publish_count=init_daily_publish_count,
            init_daily_publish_num=init_daily_publish_num,
            daily_publish_count=daily_publish_count,
            daily_publish_num=daily_publish_num,
            interval_days=interval_days,
            interval_tag=interval_tag,
        ),
        config=config,
        config_file=config_file,
        scheduled_task=scheduled_task,
        neat_index=neat_index,
        platform=platform_name,
    )

    if publish_mode == '定时发布' or ('本地定时发布' in scheduled_task):
        time_str = config.get('History', 'last_published_chapter_date',
                              fallback=datetime.datetime.now().strftime('%Y-%m-%d')) + " " + publish_time_str
        try:
            state.publish_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M')
        except Exception:
            raise ConfigLoadError("错误：发布时间格式错误。请输入正确的时间格式（例如：2023-10-01 12:00）")

        if init_daily_publish_num != -1:
            print(f"计划：日更{init_daily_publish_num}章！")
            if daily_publish_num == 0:
                daily_publish_num = init_daily_publish_num
                state.publish_time += datetime.timedelta(days=1)
            else:
                print(f"检查到上次计划剩余{daily_publish_num}章")
        else:
            print(f"计划：日更{init_daily_publish_count}字！")
            if daily_publish_count == 0:
                daily_publish_count = init_daily_publish_count
                state.publish_time += datetime.timedelta(days=1)
            else:
                if daily_publish_num == -1:
                    print(f"检查到上次计划剩余{daily_publish_count}字")
        print("预计定时发布时间: ", state.publish_time.strftime('%Y-%m-%d %H:%M'))

    print('配置加载完毕')
    return state
