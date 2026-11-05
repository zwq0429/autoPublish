---
name: auto-publish-cli
description: 使用 autoPublish CLI 工具（v2.3.x 拆分版）发布/检查/下载/创建网文小说章节。当用户要求发布小说章节到番茄/起点/七猫/飞卢/微信/书旗/晋江/息壤/咪咕等平台、检查章节问题、下载小说、根据大纲创建新书，或询问 autoPublish / novel_publisher / cli 的用法时使用。
---

# autoPublish CLI 使用指南（AI 技能）

把原 Tk 图形程序（app.py，v2.2.x 旧版单文件）的发布能力拆分为 CLI 工具，便于模块化调用与 AI 自动化。
**本技能适用于 v2.3.x 及以上版本**；v2.2.x 为旧版单文件版，无 CLI 能力。

## 1. 环境与目录

- 项目根目录：`autoPublish/`，所有命令**在此目录下执行**（CLI 会自动 chdir 到此处，相对路径均以项目根为准）
- 运行环境：需 Python 3.10+，`pip install -r requirements.txt`（playwright / requests / parsel / pystray / Pillow / pywin32）
- 浏览器：自动化用**系统浏览器**（Edge/Chrome），不使用 playwright 自带内核；路径由 config.ini 指定

关键文件：

| 文件 | 作用 | 是否敏感 |
|---|---|---|
| `config.ini` | 全部配置与发布进度 | 含用户数据，勿上传/外发 |
| `auth.json` | 平台登录态（playwright storage_state） | **敏感**，勿读取内容/勿上传 |
| `小说文件夹/` | 章节 md 文件（`Chapter_序号_标题.md`） | - |

## 2. 登录（必须的人工环节）

CLI 依赖 `auth.json` 登录态，**AI 无法代替用户扫码**。检测到登录态缺失时，按以下话术请求用户：

> 需要先登录《XX平台》作者后台：请运行 `python app_cli.py`（或 `python app.py`），确认发布平台选择正确后点击【登录】按钮，在弹出的浏览器中完成扫码登录。登录成功后项目根目录会生成 `auth.json`，之后即可关闭程序，我来完成后续发布。

要点：
- 登录态按**平台**区分，URL 由发布平台名决定；切换平台后需重新登录该平台
- 若用户用"自行登录模式"（config.ini 的 `custom_browser_path` 填**纯数字端口号**，即 CDP 接管模式），则无需 auth.json，但要求用户先手动启动带 `--remote-debugging-port=<端口>` 的已登录浏览器
- `auth.json` 缺失时 publish 命令会报错退出（见第 6 节错误对照）

## 3. 配置数据（config.ini）

配置分三个 section。**命令行参数优先级高于 config.ini**——临时任务直接用 CLI 参数覆盖，长期配置才改文件。

### [Settings]（发布设置）

| 键 | 说明 | 取值 |
|---|---|---|
| `custom_browser_path` | 浏览器 exe 路径（`/` 分隔）；纯数字=CDP 端口 | 必填 |
| `publish_plate` | 发布平台 | 番茄/起点/Q阅/七猫/纵横/飞卢/微信/书旗/晋江/息壤/咪咕 |
| `publish_mode` | 发布模式 | 立刻发布 / 定时发布 / 保存为草稿 / 修改章节 |
| `publish_time` | 每日定时时间 | `HH:MM` |
| `interval_publish_mode` | 间隔发布 | `周期天/余数`，如 `3/1`；`1/0`=每天 |
| `daily_publish_num` | 日更章节数 | 整数；`-1` 切换为字数模式 |
| `daily_publish_count` | 日更字数（字数模式用） | 整数，如 4000 |
| `close_browser_open` | 是否保留浏览器窗口 | true/false |
| `neat_index` | 章节序号整理 | true/false |
| `danger_pre_check` | 危险前置检查 | true/false |

### [Novel]（小说信息）

| 键 | 说明 |
|---|---|
| `novel_title` | 小说名（须与平台后台完全一致） |
| `novel_writer` | 笔名（选填，部分平台建书用） |
| `novels_folder` | 章节文件夹路径（相对/绝对均可） |
| `novel_status` | 小说状态（发布流程自动维护，如 已签约/待验证/推荐中） |

### [History]（发布进度，**程序自动维护，AI 一般只读**）

| 键 | 说明 |
|---|---|
| `last_published_chapter` | 已发布到的最后一章序号（下次从 +1 开始） |
| `last_published_chapter_date` | 上次发布日期（定时发布的起算日） |
| `daily_publish_num_remain` / `daily_publish_count_remain` | 当日计划剩余章数/字数 |

章节文件规范：文件夹内 `Chapter_序号_标题.md`，正文不少于 1000 中文字，标题不重复、不过长，"作者说"不超过 300 字。

## 4. 命令参考

### 发布章节

```bash
python -m cli publish [参数]
python -m cli.fanqie publish [参数]        # 也可按平台直调：cli.fanqie / cli.qidian / cli.qimao /
                                           # cli.feilu / cli.wechat / cli.shuqi / cli.jinjiang /
                                           # cli.xirang / cli.migu
```

| 参数 | 说明 |
|---|---|
| `-p / --platform` | 平台名（默认取 config.ini） |
| `--mode` | 立刻发布 / 定时发布 / 保存为草稿 / 修改章节 |
| `--title` / `--folder` | 覆盖小说名 / 章节文件夹 |
| `--start` / `--end` | 章节范围（默认：上次发布+1 起，按日更计划截止） |
| `--daily-num` / `--daily-count` | 覆盖日更章数 / 字数 |
| `--interval` | 覆盖间隔模式，如 `3/1` |
| `--time` | 覆盖定时时间 `HH:MM` |
| `--config` | 配置文件路径（默认 config.ini） |
| `--json` | 结束时输出 JSON 结果（`ok`/`platform`/`novel_title`/`published_to_chapter`） |

行为说明：
- **定时发布模式下，CLI 单次运行会按计划连续发布多日内容**（等待到点后逐日发布），AI 调用时注意这是长任务
- 发布完成后进度自动写回 config.ini 的 [History]，并保存小说状态机结果到 [Novel] novel_status

### 检查（章节查重 + 字数检查，会直接修改问题文件）

```bash
python -m cli check [--folder X] [--no-neat-index]
```

- `--folder` 缺省读 config.ini `[Novel] novels_folder`
- `--no-neat-index` 不整理序号
- 功能：修复重复章节标题、截断超长标题；多线程检查正文 <1000 或 >4000 字并打印问题清单

### 下载小说

```bash
python -m cli download --book-id <ID或链接> [--platform X] [--save-dir output]
                        [--all | --toc-only | --start 1 --end 3]
```

- 下载全文需要平台 svip 账号，否则只能下载前 10 章

### 创建新书

```bash
python -m cli create-book [--info-file X | --outline-dir .] [--platform X]
                          [--browser-path X] [--writer X] [--keep-browser-open]
```

- `--info-file`：开书信息文本（格式与 `parse_novel_info` 输入一致）；缺省时从 `--outline-dir` 中以"大纲.txt"结尾的文件读取 `&&&开书信息&&&` 键值
- 建书成功后新书面信息写回 config.ini

### 其他

```bash
python -m cli platforms        # 列出支持的平台
python -m cli --help           # 总帮助
```

### 环境/配置/素材类命令（AI 自动化全套工作流用）

| 命令 | 说明 |
|---|---|
| `python -m cli detect-browser [--no-save]` | 自动检测本机浏览器路径并写回 config.ini（首次配置第一步） |
| `python -m cli login [-p X] [--output X]` | 打开浏览器扫码登录，保存 auth.json（人工扫码环节，AI 引导用户执行） |
| `python -m cli manual-browser [-p X]` | 打开保持登录态的手动浏览器会话（人工干预/补操作用） |
| `python -m cli config get [Section.key ...] [--json]` | 读配置（`config get` 全量；缺文件报错 exit 2） |
| `python -m cli config set Section.key value [...]` | 写配置（自动建 section；**这是 AI 修改配置的首选方式**，勿手改 [History] 进度区） |
| `python -m cli export [--folder X] [-o X] [--all\|--start A --end B]` | 把章节文件夹导出为单个 txt |
| `python -m cli import --file X [--output-dir X] [--mode all\|append] [--chapters 1,3,5-7] [--reverse]` | 导入 txt 拆分为 Chapter_NNN.md 章节文件（成功后写回 novels_folder） |
| `python -m cli plan --plan "15*1+15*2+2*7" [--dry-run]` | 快速发布计划（最速开书）：逐阶段发布；`--dry-run` 只解析打印 |
| `python -m cli progress-check` | 发布进度自检：核对本地记录与平台最新进度，确认后更新本地 History |

### 番茄特有任务

以下命令**仅支持番茄平台**，共用参数：`-p/--platform`、`--title`、`--browser-path`、`--keep-browser-open`、`--config`、`--json`（JSON 含 `novel_status` 最新状态）。

| 命令 | 对应 UI 任务 | 说明 |
|---|---|---|
| `python -m cli sstory [--folder X]` | 短故事批量发布 | 发布 `短篇直出/` 下的 txt（默认单次≤10篇），成功的文件移入 `已发布MM-DD/` |
| `python -m cli sign` | 自动签约 | 自动签约流程；**长任务**，评估期间每小时巡查，勿设超时 |
| `python -m cli verify` | 自动验证 | 作品推荐确认；**长任务**，最长等待 12 小时；需预先上传非模版封面 |
| `python -m cli book-test` | 书测 | 上传 `项目根/书测/` 下 jpg/png 封面图配置实验（文件名去掉"-封面"作为书名），完成后目录改名"已完成" |
| `python -m cli cover-test` | 封测 | 多封面推荐，上传 `项目根/封测/` 封面图，完成后目录改名"已完成" |
| `python -m cli attendance` | 全勤检查 | 核查当月听读收益与每日发布字数（≥4000/6000 字达标），结果写入 `novel_status`（全勤中/有缺勤/有全勤实力） |

- 这些任务会把最新小说状态写回 config.ini `[Novel] novel_status`，AI 执行后读该字段（或 `--json`）反馈给用户
- `sign` / `verify` 是**小时级长任务**：AI 调用时应告知用户预计耗时，或建议用户在后台终端自行运行

## 5. 结果反馈（AI 如何获取执行结果）

1. **退出码**：`0` 成功；非 0 失败（publish 中配置/登录问题为 2，运行失败为 1）
2. **stdout 日志**：全程中文日志，含每章发布结果、总耗时、进度保存信息
3. **`--json`**（publish）：末行输出结构化结果，适合程序解析
4. **config.ini**：执行后重读 [History] / [Novel] 核对实际进度（这是最可靠的"发布到哪了"来源）

## 6. 常见错误对照

| 日志/退出码 | 原因 | 处理 |
|---|---|---|
| `找不到登录状态文件 auth.json` | 未登录该平台 | 走第 2 节登录流程 |
| `错误：小说文件夹 X 不存在` | 路径错 | 检查/修正 `--folder` 或 config.ini |
| `没有找到要发布的小说文件（第 a-b 章）` | 章节已发完或文件命名不符 | 先跑 `check`；确认 `Chapter_*.md` 存在 |
| `发布时间格式错误` | `--time` 或 config.ini 时间格式不对 | 用 `HH:MM` |
| `错误：指定浏览器未开启` | CDP 模式浏览器未启动 | 让用户启动带调试端口的浏览器 |
| `不支持的平台 'X'` | 平台名不在列表 | 先跑 `python -m cli platforms` |

## 7. 典型工作流

**首次配置（AI 引导用户）**
1. 确认环境：`pip install -r requirements.txt`
2. `python -m cli detect-browser` 检测浏览器并写回配置
3. `python -m cli config set Settings.publish_plate 番茄 Novel.novel_title 书名 Novel.novels_folder 章节目录` 配置基础项
4. `python -m cli login` 请求用户扫码登录（第 2 节话术）
5. `python -m cli check` 验证章节文件没问题
6. `python -m cli publish --json` 试发布；`python -m cli config get History --json` 核对进度

**每日发布（AI / 定时任务）**
1. 读 config.ini 确认今日是否为间隔发布日、剩余计划
2. `python -m cli publish`（长任务，定时模式下会自动等待到点）
3. 结束后读 [History] 回报用户进度

**注意事项**
- **不要并行运行两个 publish**（浏览器与进度文件会冲突）；需要换平台串行执行
- 改 config.ini 前先备份；[History] 只能让程序写
- 用户想保持旧版（v2.2.x 单文件版）时：程序内更新是**自愿确认制**，拒绝弹窗即可保留旧版
