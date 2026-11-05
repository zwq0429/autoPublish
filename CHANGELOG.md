# 更新日志

## v2.3.1

- 架构拆分：各平台发布逻辑模块化为纯函数（novel_publisher/platforms/ 下番茄/起点/Q阅/七猫/纵横/飞卢/微信/书旗/晋江/息壤/咪咕 9 个平台模块 + flow.py 运行时状态），app.py 原样保留作为旧实现
- 新增 CLI 工具集（cli/ 目录）：
  - `python -m cli publish` 发布章节（支持 --platform/--start/--end/--mode/--json 等参数覆盖 config.ini）
  - `python -m cli check` 章节查重与字数检查
  - `python -m cli download` 下载小说（--book-id/--all/--toc-only/--start/--end）
  - `python -m cli create-book` 根据简介/大纲创建新书
  - `python -m cli platforms` 列出支持的平台；也可按平台直调（如 `python -m cli.fanqie publish`）
  - CLI 输出便于 AI 自动化调用，`--json` 输出结构化结果
- 新增新版主程序入口 app_cli.py：界面与原版完全一致，发布/检查/下载/建书槽函数改为调用 CLI 子进程（启动方式：`python app_cli.py`，快速模式参数与原版相同）
- 程序内更新白名单新增 app_cli.py 与 cli/ 目录，源码模式更新可完整覆盖
- 签约流程适配：兼容"评估通过，请尽快填写合同信息"提示；签约确认步骤调整
- 发布页面加载等待策略优化（networkidle → domcontentloaded 重试）
- 新增 AI 技能文档 skills/auto-publish-cli/SKILL.md：教 AI 如何调用 CLI（登录请求、配置数据、命令参考、结果反馈、错误处理）；Release 附件附带 skills.zip，程序内源码更新也会覆盖 skills/ 目录
- 修复：requirements.txt 补充缺失的 parsel 依赖（影响 CI 构建的 exe）

## v2.2.9

- 历史版本，详见 GitHub Releases
