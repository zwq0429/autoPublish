# 小说自动发布工具

> 声明：本工具仅用于学习和研究，不涉及任何商业用途！

基于 Playwright 的番茄小说自动发布工具，支持自动发布章节、定时发布、快速创书、短故事发布、章节导入导出、发布进度自检等功能。

## 功能特性

- 自动发布：自动登录、创建书籍、按范围发布章节
- 定时任务：本地定时发布、全勤检查、发布进度自检
- 快速创书 / 最速开书 / 短故事发布
- 章节导出 / 导入、标题查重、草稿清理
- 内置更新：一键检查 GitHub 最新版本并自动升级（支持镜像加速）
- 系统托盘、日志重定向、多账号浏览器管理

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

运行主程序：

```bash
python app.py
```

## 打包 exe

```bash
pip install pyinstaller
pyinstaller app.spec --noconfirm
```

## 版本发布

版本号维护在根目录 `VERSION` 文件中。推送到 `main` 分支后，GitHub Actions 会自动：

1. 读取 `VERSION`，若对应 tag 的 Release 不存在则构建 exe
2. 使用 PyInstaller 打包 `app.exe`
3. 创建 Release 并上传 exe 资产

## 程序内更新

程序内置静态更新功能：

- 启动时自动静默检查更新（仅日志提示，不打扰）
- 主界面【其他功能】→【检查更新】可手动检查并升级
- 检查源为 GitHub Release（`api.github.com` 优先，失败自动切换 gh-proxy 等镜像）
- 下载同样支持镜像加速；exe 模式下载后自动替换重启，源码模式按白名单覆盖代码文件
- 可在 `config.ini` 的 `[Update] mirror_list` 中自定义镜像（逗号分隔，留空用默认）

## 目录结构

```
├── app.py                  # 主程序入口（GUI）
├── browser_detector.py     # 浏览器路径检测（注册表）
├── font_map.py             # 字体映射
├── icon.py                 # 托盘图标资源（base64）
├── tomato.ico              # 应用图标
├── app.spec                # PyInstaller 打包配置
├── VERSION                 # 当前版本号（发版依据）
├── manager_server.py       # Web 管理器服务端
├── manager_web.html        # Web 管理器页面
├── manager_server.spec     # Web 管理器 PyInstaller 打包配置
├── favicon.ico             # Web 管理器图标
└── novel_publisher/        # 核心功能包
    ├── browser.py          # 浏览器连接管理
    ├── navigation.py       # 页面导航与站点定位
    ├── chapter_files.py    # 章节文件读写
    ├── create_book.py      # 创建书籍
    ├── downloader.py       # 小说下载
    ├── platforms/          # 平台适配
    ├── tasks/              # 发布任务
    ├── sstory.py           # 短故事发布
    ├── tray.py             # 系统托盘
    └── updater.py          # 检查更新与自动升级
```

## 配置说明

首次运行生成 `config.ini`，常用配置项在界面中直接设置即可；`[Update]` 分组用于更新设置。

## Web 管理器

`manager_server.py` 是多项目批量管理服务端：运行后自动打开浏览器，通过 Web 页面（[manager_web.html](manager_web.html)）集中管理所有小说项目，支持批量调用主程序执行发布任务（单任务超时 30 分钟自动终止）、任务队列与日志查看，并带系统托盘。

```bash
# 启动（默认端口 18765）
python manager_server.py

# 打包为 exe
pip install pyinstaller
pyinstaller manager_server.spec --noconfirm
```

默认根目录为 `E:\AutoWriter`（不存在时回退到当前目录），项目组织与批量任务的字段约定见页面内提示。

## 联系与反馈

如有使用 bug 反馈或者交流 AI 写作经验：

- 微信：zwq123_789 / abrtga
- QQ 群：1073022161

## License

[MIT](LICENSE)
