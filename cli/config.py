"""config 读写子命令：AI 安全操作 config.ini。

用法:
    python -m cli config get Settings.publish_plate Novel.novel_title
    python -m cli config get                      # 输出全部配置
    python -m cli config set Settings.publish_plate 番茄 Novel.novel_writer 某某
"""

import configparser
import json
import os
import sys


def register(p):
    p.add_argument('action', choices=['get', 'set'], help='get=读取 / set=写入')
    p.add_argument('keys', nargs='*',
                   help='get: section.key [section.key ...]（缺省读全部）；'
                        'set: section.key value [section.key value ...]（成对）')
    p.add_argument('--config', default='config.ini', help='配置文件路径（默认 config.ini）')
    p.add_argument('--json', action='store_true', help='以 JSON 输出（仅 get）')


def main(args) -> int:
    config = configparser.ConfigParser()
    if os.path.exists(args.config):
        config.read(args.config, encoding='utf-8')
    elif args.action == 'get':
        print(f"错误：找不到配置文件 {os.path.abspath(args.config)}", file=sys.stderr)
        return 2

    if args.action == 'get':
        if not args.keys:
            data = {s: dict(config[s]) for s in config.sections()}
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for s, kv in data.items():
                    print(f'[{s}]')
                    for k, v in kv.items():
                        print(f'{s}.{k} = {v}')
            return 0
        result = {}
        missing = []
        for key in args.keys:
            section, _, name = key.partition('.')
            if not section or not name or not config.has_section(section) \
                    or name not in config[section]:
                missing.append(key)
                continue
            result[key] = config[section][name]
        for key in missing:
            print(f"错误：配置项不存在: {key}", file=sys.stderr)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for k, v in result.items():
                print(f'{k} = {v}')
        return 1 if missing else 0

    # set：成对的 section.key value
    if len(args.keys) == 0 or len(args.keys) % 2 != 0:
        print("错误：set 需要「section.key value」成对出现", file=sys.stderr)
        return 2
    for i in range(0, len(args.keys), 2):
        key, value = args.keys[i], args.keys[i + 1]
        section, _, name = key.partition('.')
        if not section or not name:
            print(f"错误：键格式应为 section.key: {key}", file=sys.stderr)
            return 2
        if not config.has_section(section):
            config[section] = {}
        config[section][name] = value
        print(f"已设置 {key} = {value}")
    with open(args.config, 'w', encoding='utf-8') as f:
        config.write(f)
    print("配置已保存")
    return 0
