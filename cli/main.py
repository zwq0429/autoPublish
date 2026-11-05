"""autoPublish CLI 工具集。

把原 Tk 主程序中的发布/检查/下载/建书能力拆分为独立 CLI 命令，
便于模块化调用与 AI 自动化。

用法（在项目根目录）:
    python -m cli publish --platform 番茄
    python -m cli publish -p 起点 --start 10 --end 12 --mode 立刻发布
    python -m cli check
    python -m cli download --book-id 7143038691944959011
    python -m cli create-book --info-file novel_info.txt --outline-dir ./outline
    python -m cli platforms

也可以按平台直接调用:
    python -m cli.fanqie publish
    python -m cli.qidian publish --start 1 --end 2

退出码: 0 成功，非 0 失败。
"""

import argparse
import importlib
import json
import os
import sys

# 项目根目录（cli/ 的上一级），保证相对路径 config.ini / auth.json 可用
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 平台名 -> 平台模块名（与 novel_publisher/platforms/adapters.py 的注册名一致）
PLATFORM_MODULES = {
    '番茄': 'fanqie',
    '起点': 'qidian',
    'Q阅': 'qidian',
    '七猫': 'qimao',
    '纵横': 'qimao',
    '飞卢': 'feilu',
    '微信': 'wechat',
    '书旗': 'shuqi',
    '晋江': 'jinjiang',
    '息壤': 'xirang',
    '咪咕': 'migu',
}


def get_platform_module(platform_name: str):
    """根据平台名返回平台模块（含 run_publish / publish_single_chapter）。"""
    module_name = PLATFORM_MODULES.get(platform_name)
    if not module_name:
        return None
    return importlib.import_module(f'novel_publisher.platforms.{module_name}')


def cmd_platforms(args) -> int:
    print("支持的平台：")
    for name in PLATFORM_MODULES:
        print(f"  {name}")
    print("\n用法示例： python -m cli publish --platform 番茄")
    return 0


def cmd_publish(args) -> int:
    from novel_publisher.flow import load_publish_config, ConfigLoadError

    overrides = {}
    if args.platform:
        overrides['platform'] = args.platform
    if args.mode:
        overrides['publish_mode'] = args.mode
    if args.title:
        overrides['novel_title'] = args.title
    if args.folder:
        overrides['novels_folder'] = args.folder
    if args.start is not None:
        overrides['start_chapter'] = args.start
    if args.end is not None:
        overrides['end_chapter'] = args.end
    if args.daily_num is not None:
        overrides['daily_publish_num'] = args.daily_num
    if args.daily_count is not None:
        overrides['daily_publish_count'] = args.daily_count
    if args.interval:
        overrides['interval_mode'] = args.interval
    if args.time:
        overrides['publish_time'] = args.time

    platform_name = overrides.get(
        'platform',
        _read_config_platform(args.config),
    )
    module = get_platform_module(platform_name)
    if module is None:
        print(f"错误：不支持的平台 '{platform_name}'。可用平台: {'、'.join(PLATFORM_MODULES)}")
        return 2

    try:
        state = load_publish_config(args.config, os.path.join(APP_DIR, 'auth.json'),
                                    overrides=overrides)
    except ConfigLoadError as e:
        print(str(e))
        return 2

    print(f"平台: {state.platform}  小说: {state.cfg.novel_title}  "
          f"章节: {state.cfg.start_chapter}-{state.cfg.end_chapter}  模式: {state.cfg.publish_mode}")
    ok = module.run_publish(state)

    if args.json:
        print(json.dumps({
            'ok': bool(ok),
            'platform': state.platform,
            'novel_title': state.cfg.novel_title,
            'published_to_chapter': state.cfg.end_chapter,
        }, ensure_ascii=False))
    return 0 if ok else 1


def _read_config_platform(config_file: str) -> str:
    import configparser
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
    return config.get('Settings', 'publish_plate', fallback='番茄')


def build_publish_parser(parser: argparse.ArgumentParser):
    """为 publish 命令添加参数（平台包装脚本复用）。"""
    parser.add_argument('-p', '--platform', help='发布平台（默认取 config.ini 的 publish_plate）')
    parser.add_argument('--mode', help='发布模式: 立刻发布 / 定时发布 / 保存为草稿 / 修改章节')
    parser.add_argument('--title', help='小说标题（默认取 config.ini）')
    parser.add_argument('--folder', help='小说章节文件夹（默认取 config.ini）')
    parser.add_argument('--start', type=int, help='开始章节号（默认为上次发布+1）')
    parser.add_argument('--end', type=int, help='结束章节号（默认按日更计划）')
    parser.add_argument('--daily-num', type=int, help='日更章节数（-1 表示按字数模式）')
    parser.add_argument('--daily-count', type=int, help='日更字数')
    parser.add_argument('--interval', help='间隔发布模式，如 3/1（3天周期余1发布）')
    parser.add_argument('--time', help='定时发布时间 HH:MM')
    parser.add_argument('--config', default='config.ini', help='配置文件路径（默认 config.ini）')
    parser.add_argument('--json', action='store_true', help='结束时输出 JSON 结果（便于 AI 解析）')
    parser.set_defaults(func=cmd_publish)


def main(argv=None):
    # 切换到项目根目录，保证 config.ini / auth.json / 章节文件夹相对路径一致
    os.chdir(APP_DIR)

    from cli import check as cli_check
    from cli import download as cli_download
    from cli import create_book as cli_create_book

    parser = argparse.ArgumentParser(
        prog='cli',
        description='autoPublish CLI 工具集（发布/检查/下载/建书）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest='command', required=True)

    build_publish_parser(sub.add_parser('publish', help='发布章节到指定平台'))

    p = sub.add_parser('platforms', help='列出支持的平台')
    p.set_defaults(func=cmd_platforms)

    p = sub.add_parser('check', help='章节查重与字数检查')
    cli_check.register(p)
    p.set_defaults(func=cli_check.main)

    p = sub.add_parser('download', help='下载小说')
    cli_download.register(p)
    p.set_defaults(func=cli_download.main)

    p = sub.add_parser('create-book', help='根据简介/大纲创建新书')
    cli_create_book.register(p)
    p.set_defaults(func=cli_create_book.main)

    args = parser.parse_args(argv)
    return args.func(args)


def platform_main(platform_name: str, argv=None) -> int:
    """平台包装脚本入口：python -m cli.<platform> publish ..."""
    os.chdir(APP_DIR)
    prog = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    parser = argparse.ArgumentParser(
        prog=f'cli.{prog}',
        description=f'{platform_name} 平台 CLI（发布等）',
    )
    sub = parser.add_subparsers(dest='command', required=True)
    build_publish_parser(sub.add_parser('publish', help='发布章节'))
    # 平台名固定，忽略用户传入的 --platform
    args = parser.parse_args(argv)
    args.platform = platform_name
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main() or 0)
