"""快速发布计划（最速开书）CLI 子命令。

从 app.py 提取的"最速开书/快速发布"能力（无 UI 版本），来源:
  - parse_fast_publish_mode   app.py L5100-5162（解析计划串，逐行提取）
  - execute_publish_plan      app.py L5164-5208（逐阶段执行，参照改写）
  - show_fast_publish_dialog  app.py L5629-5657（UI 弹窗选计划串 → --plan 参数）
  - new_novel_publish_once    app.py L5659-5679（UI 入口调用链，仅了解，未整体提取）

计划串格式（如 "15*1+15*2+2*7"）:
  步骤1: 立刻发布第1-15章
  步骤2: 定时发布第16-45章（每日15章，持续2天）
  步骤3: 定时发布第46-59章（每日2章，持续7天，2*7=14章）

与原 UI 实现的对应关系:
  原版每阶段前修改 UI 变量（publish_mode_var / start_chapter_var /
  end_chapter_var / daily_publish_num_var / daily_publish_num_remain_var /
  last_published_chapter_date_var）再调 self.automation_flow()
  （内部 _normal_load_config 直接读变量，结束 _normal_save_config 写回变量和
  config.ini）。CLI 等效做法:
    - publish_mode / start_chapter / end_chapter / daily_publish_num(init 值)
      → load_publish_config(overrides={...}) 直接覆盖;
    - daily_publish_num_remain=0、第二阶段的 last_published_chapter_date=今天
      → load_publish_config 无对应 override 键（这两项从 config.ini [History]
      读取），故先把值写回 config.ini 再加载，效果一致;
    - 阶段间进度递推: 每阶段 run_publish 结束时 state.save_history 把
      last_published_chapter / last_published_chapter_date / 剩余数写回
      config.ini，下一阶段重新 load 即可拿到最新进度（各阶段章节范围仍由
      计划串解析结果显式给定，与原版一致，不依赖 History.last_published_chapter）。

用法（项目根目录）:
    python -m cli plan --plan "15*1+15*2+2*7" --dry-run   # 只解析并打印计划
    python -m cli plan --plan "15*1+15*2+2*7"             # 实际执行发布

退出码: 0 成功；1 某阶段执行失败；2 计划解析失败/平台不支持。
"""

import configparser
import datetime
import json
import os
import traceback


def parse_fast_publish_mode(plan_str):
    """解析快速发布模式字符串，生成发布计划。

    提取自 app.py L5100-5162 NovelPublisherApp.parse_fast_publish_mode
    （原方法从 UI 读取输入，此处改为参数传入；解析规则与打印完全保留）。
    例如: "15*1+15*2+2*7" 表示:
    - 第一步: 发布1-15章
    - 第二步: 预发布16-45章，每日15章，持续2天
    - 第三步: 预发布46-59章，每日2章，持续7天

    Returns:
        list[dict] 阶段列表；解析失败返回 None（与原版一致）。
    """
    try:
        # 分割字符串获取各个阶段
        stages = plan_str.split('+')
        plan = []

        current_chapter = 1

        for i, stage in enumerate(stages):
            if '*' in stage:
                # 解析格式如 "15*3" (每日章节数*持续天数)
                daily_count, days = stage.split('*')
                daily_count = int(daily_count)
                days = int(days)

                if i == 0:
                    # 第一步总是立即发布模式
                    end_chapter = current_chapter + daily_count - 1
                    plan.append({
                        'mode': '立刻发布',
                        'start_chapter': current_chapter,
                        'end_chapter': end_chapter,
                        'description': f"发布第{current_chapter}-{end_chapter}章"
                    })
                    current_chapter = end_chapter + 1
                else:
                    # 后续步骤是预发布模式
                    end_chapter = current_chapter + daily_count * days - 1
                    plan.append({
                        'mode': '定时发布',
                        'start_chapter': current_chapter,
                        'end_chapter': end_chapter,
                        'daily_count': daily_count,
                        'days': days,
                        'description': f"预发布第{current_chapter}-{end_chapter}章 (每日{daily_count}章)"
                    })
                    current_chapter = end_chapter + 1
            else:
                # 处理简单数字，如 "15"
                count = int(stage)
                end_chapter = current_chapter + count - 1

                if i == 0:
                    # 第一步总是立即发布模式
                    plan.append({
                        'mode': '立刻发布',
                        'start_chapter': current_chapter,
                        'end_chapter': end_chapter,
                        'description': f"发布第{current_chapter}-{end_chapter}章"
                    })
                current_chapter = end_chapter + 1

        return plan
    except Exception as e:
        print(f"解析发布模式失败: {e}")
        return None


def _set_history_field(config_file, key, value):
    """把 config.ini [History] 段的一个字段写回配置文件。

    等效原 execute_publish_plan（app.py L5188-5193）每阶段前对 UI 变量的 set:
      daily_publish_num_remain_var.set(0)        → [History] daily_publish_num_remain='0'
      last_published_chapter_date_var.set(today) → [History] last_published_chapter_date=今天
    原版 automation_flow 内部 _normal_load_config 直接读 UI 变量；CLI 版
    load_publish_config 从 config.ini [History] 读这两项（无 override 键），
    故先落盘再加载。
    """
    if not os.path.exists(config_file):
        # 配置文件不存在时不落盘，让后续 load_publish_config 报出明确错误
        return
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')
    if not config.has_section('History'):
        config['History'] = {}
    config['History'][key] = value
    with open(config_file, 'w', encoding='utf-8') as f:
        config.write(f)


def _print_plan(plan):
    """打印解析出的计划（--dry-run 展示，及执行前确认内容）。

    对应原 execute_publish_plan 开头拼接 set_string 弹窗确认的内容，
    messagebox → print。
    """
    for i, step in enumerate(plan, 1):
        line = f"步骤{i}: [{step['mode']}] {step['description']}"
        if step['mode'] == '定时发布':
            line += f"，每日{step['daily_count']}章 × {step['days']}天"
        print(line)
    total = int(plan[-1]['end_chapter'])
    print(f"合计: {len(plan)}个阶段，第1-{total}章，共{total}章")


def _stage_json(step, step_no, ok, error=None):
    """构造单阶段的 JSON 结果条目。"""
    data = {
        'step': step_no,
        'mode': step['mode'],
        'start_chapter': int(step['start_chapter']),
        'end_chapter': int(step['end_chapter']),
        'daily_count': step.get('daily_count'),
        'days': step.get('days'),
        'description': step['description'],
        'ok': bool(ok),
    }
    if error is not None:
        data['error'] = error
    return data


def _emit_json(plan_str, platform_name, stages, final_chapter, ok, dry_run=False):
    """输出 JSON 结果（--json）。"""
    print(json.dumps({
        'ok': bool(ok),
        'dry_run': bool(dry_run),
        'plan': plan_str,
        'platform': platform_name,
        'stages': stages,
        'final_chapter': final_chapter,
    }, ensure_ascii=False))


def main(args) -> int:
    """执行 plan 子命令。

    参照 app.py L5164-5208 execute_publish_plan 与 L5659-5679
    new_novel_publish_once 改写（messagebox 确认/UI 变量 → print + 覆盖项）。
    """
    plan = parse_fast_publish_mode(args.plan)
    if not plan:
        return 2

    if args.dry_run:
        # 只解析并打印计划，不实际发布
        print(f"发布计划解析结果（共{len(plan)}个阶段，--dry-run 不实际发布）:")
        _print_plan(plan)
        if args.json:
            stages = [_stage_json(step, i, True) for i, step in enumerate(plan, 1)]
            _emit_json(args.plan, None, stages, int(plan[-1]['end_chapter']),
                       True, dry_run=True)
        return 0

    # 延迟导入 cli.main，避免与 cli/main.py 的子命令注册形成循环导入
    from cli.main import APP_DIR, get_platform_module, _read_config_platform
    from novel_publisher.flow import load_publish_config, ConfigLoadError

    # 原版 execute_publish_plan 开头校验: 仅支持番茄
    platform_name = args.platform or _read_config_platform(args.config)
    if platform_name != '番茄':
        print("最速开书流程目前仅支持番茄小说")
        return 2
    module = get_platform_module(platform_name)
    if module is None:
        print(f"错误：不支持的平台 '{platform_name}'。")
        return 2

    # 透传的公共覆盖项（同 cli/main.py 的 publish 命令）
    base_overrides = {}
    if args.platform:
        base_overrides['platform'] = args.platform
    if args.title:
        base_overrides['novel_title'] = args.title
    if args.folder:
        base_overrides['novels_folder'] = args.folder

    auth_file = os.path.join(APP_DIR, 'auth.json')
    stage_results = []
    final_chapter = None

    print("发布计划:")
    _print_plan(plan)

    for i, step in enumerate(plan, 1):
        print(f"\n--- 步骤{i}: {step['description']} ---")

        # 每阶段重新覆盖发布模式与章节范围
        # （原版: set publish_mode_var / start_chapter_var / end_chapter_var 后
        # 循环调 self.automation_flow()；章节范围取计划解析结果，
        # 与原版一样不依赖 History.last_published_chapter 递推）
        overrides = dict(base_overrides)
        overrides['start_chapter'] = int(step['start_chapter'])
        overrides['end_chapter'] = int(step['end_chapter'])
        overrides['publish_mode'] = step['mode']

        if step['mode'] == '定时发布':
            # 原版: daily_publish_num_var.set(int(step['daily_count'])) → 覆盖 init 值
            overrides['daily_publish_num'] = int(step['daily_count'])
            # 原版: daily_publish_num_remain_var.set(0) → 先落盘再加载
            _set_history_field(args.config, 'daily_publish_num_remain', '0')
            if i == 2:
                # 原版: 第二步设 last_published_chapter_date_var = 今天
                _set_history_field(args.config, 'last_published_chapter_date',
                                   datetime.datetime.now().strftime('%Y-%m-%d'))

        try:
            # 每阶段重新 load: 上一阶段 run_publish 内部 save_history 已把
            # 最新进度（last_published_chapter/date、剩余数）写回 config.ini
            state = load_publish_config(args.config, auth_file, overrides=overrides)
        except ConfigLoadError as e:
            print(str(e))
            print(f"最速开书流程中发生错误: 执行步骤{i}失败: {step['description']}")
            stage_results.append(_stage_json(step, i, False, error=str(e)))
            if args.json:
                _emit_json(args.plan, platform_name, stage_results, final_chapter, False)
            return 1

        try:
            ok = module.run_publish(state)
        except Exception as e:
            print(f"最速开书流程中发生错误: 执行步骤{i}失败: {step['description']}: {e}")
            traceback.print_exc()
            stage_results.append(_stage_json(step, i, False, error=str(e)))
            if args.json:
                _emit_json(args.plan, platform_name, stage_results, final_chapter, False)
            return 1

        if ok:
            stage_results.append(_stage_json(step, i, True))
            final_chapter = int(step['end_chapter'])
            print(f"步骤{i}完成，累计进度: 已发布至第{final_chapter}章")
        else:
            # 原版: raise Exception(f"执行步骤{i}失败: ...") → 打印错误后整体失败
            print(f"最速开书流程中发生错误: 执行步骤{i}失败: {step['description']}")
            stage_results.append(_stage_json(step, i, False))
            if args.json:
                _emit_json(args.plan, platform_name, stage_results, final_chapter, False)
            return 1

    print("\n最速开书流程完成！")
    if args.json:
        _emit_json(args.plan, platform_name, stage_results, final_chapter, True)
    return 0


def register(p):
    """注册 plan 子命令参数（p 为 cli/main.py 创建的该命令 parser）。"""
    p.description = ('按计划串逐阶段发布（原"最速开书"功能），如 "15*1+15*2+2*7": '
                     '第1步立刻发布1-15章；第2步每日15章定时发2天(16-45章)；'
                     '第3步每日2章定时发7天(46-59章)')
    p.add_argument('--plan', required=True,
                   help='计划字符串，如 "15*1+15*2+2*7"（格式: 章节数 或 每日章节数*天数，'
                        '用 + 连接多阶段；第一阶段总是立刻发布）')
    p.add_argument('-p', '--platform', help='发布平台（仅支持番茄，默认取 config.ini）')
    p.add_argument('--title', help='小说标题（默认取 config.ini）')
    p.add_argument('--folder', help='小说章节文件夹（默认取 config.ini）')
    p.add_argument('--config', default='config.ini', help='配置文件路径（默认 config.ini）')
    p.add_argument('--json', action='store_true',
                   help='结束时输出 JSON 结果（各阶段 ok/章节范围/最终章节）')
    p.add_argument('--dry-run', action='store_true',
                   help='只解析并打印计划（每阶段章节范围/天数/每日数量），不实际发布')
    p.set_defaults(func=main)
