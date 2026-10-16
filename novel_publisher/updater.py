# -*- coding: utf-8 -*-
"""静态更新模块

通过 GitHub Release 检查新版本并拉取更新：
- 优先直连 GitHub API / 下载地址，失败时自动切换到镜像加速站
- exe 打包运行（PyInstaller frozen）时下载新版 exe 并通过批处理脚本替换重启
- 源码运行时下载源码压缩包，覆盖本地代码文件后提示重启
"""

import os
import re
import sys
import zipfile
import subprocess
import tempfile
import threading

import requests

# 仓库信息（检查更新 / 拉取更新的来源）
GITHUB_OWNER = 'zwq0429'
GITHUB_REPO = 'autoPublish'
GITHUB_REPO_FULL = f'{GITHUB_OWNER}/{GITHUB_REPO}'

# 镜像加速前缀（按顺序尝试，空字符串表示直连）
DEFAULT_MIRRORS = [
    '',
    'https://gh-proxy.com/',
    'https://ghproxy.net/',
    'https://mirror.ghproxy.com/',
]

# 源码模式下允许覆盖的文件/目录（避免破坏用户配置和数据）
UPDATE_WHITELIST_FILES = ('app.py', 'browser_detector.py', 'font_map.py', 'icon.py')
UPDATE_WHITELIST_DIRS = ('novel_publisher',)
UPDATE_WHITELIST_EXTS = ('.py', '.ico', '.md')


def _parse_version(version_str):
    """把 'v2.2.9' 解析成 (2, 2, 9)，便于比较"""
    nums = re.findall(r'\d+', str(version_str))
    return tuple(int(n) for n in nums[:3]) if nums else (0, 0, 0)


def is_newer(remote_version, local_version):
    """判断远端版本是否比本地新"""
    return _parse_version(remote_version) > _parse_version(local_version)


def _request_with_mirrors(path, stream=False, timeout=10, mirrors=None, **kwargs):
    """依次尝试 直连 + 各镜像 拉取 GitHub 资源，返回第一个成功的 response"""
    urls = [f'{m}https://github.com/{path.lstrip("/")}' for m in (mirrors or DEFAULT_MIRRORS)]
    last_err = None
    for url in urls:
        try:
            resp = requests.get(url, stream=stream, timeout=timeout, allow_redirects=True, **kwargs)
            if resp.status_code == 200:
                print(f'<< 更新 >> 连接成功: {url.split("https://", 1)[-1][:80]}')
                return resp
            last_err = f'HTTP {resp.status_code}: {url}'
        except Exception as e:
            last_err = f'{type(e).__name__}: {url}'
    raise RuntimeError(f'所有更新源均连接失败，最后错误: {last_err}')


def fetch_latest_version(mirrors=None):
    """查询远端最新版本号，成功返回 tag 字符串（如 'v2.3.0'），失败抛异常"""
    # 1) 优先尝试 GitHub API 直连
    try:
        resp = requests.get(
            f'https://api.github.com/repos/{GITHUB_REPO_FULL}/releases/latest',
            timeout=8, headers={'Accept': 'application/vnd.github+json'})
        if resp.status_code == 200:
            tag = resp.json().get('tag_name', '')
            if tag:
                return tag
    except Exception:
        pass
    # 2) API 失败时通过镜像请求 releases/latest，跟随重定向从最终地址解析 tag
    resp = _request_with_mirrors(f'{GITHUB_REPO_FULL}/releases/latest', timeout=10, mirrors=mirrors)
    m = re.search(r'/releases/tag/(v[\d.]+)', resp.url)
    if m:
        return m.group(1)
    raise RuntimeError(f'无法从更新源解析最新版本号: {resp.url}')


def _download_stream(resp, dest_path, label=''):
    """把流式 response 写入文件，逐兆打印进度"""
    total = int(resp.headers.get('Content-Length', 0) or 0)
    done = 0
    next_report = 0
    with open(dest_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            done += len(chunk)
            if total and done >= next_report:
                print(f'<< 更新 >> {label}下载进度: {done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB')
                next_report += 2 * 1024 * 1024
    print(f'<< 更新 >> {label}下载完成: {dest_path}')


def _download_asset(tag, asset_name, dest_path, mirrors=None):
    """从 release 下载指定资产文件（自动尝试镜像）"""
    resp = _request_with_mirrors(
        f'{GITHUB_REPO_FULL}/releases/download/{tag}/{asset_name}',
        stream=True, timeout=30, mirrors=mirrors)
    _download_stream(resp, dest_path, label=asset_name)


def _download_source_zip(tag, dest_path, mirrors=None):
    """下载 release tag 对应的源码压缩包"""
    resp = _request_with_mirrors(
        f'{GITHUB_REPO_FULL}/archive/refs/tags/{tag}.zip',
        stream=True, timeout=30, mirrors=mirrors)
    _download_stream(resp, dest_path, label='源码包')


def _run_replace_and_restart(new_exe_path):
    """生成并执行替换脚本：等待当前进程退出 -> 覆盖 exe -> 重启新版本"""
    current_exe = sys.executable
    pid = os.getpid()
    bat_path = os.path.join(tempfile.gettempdir(), 'autoPublish_update.bat')
    bat_content = (
        '@echo off\r\n'
        'echo waiting for process to exit...\r\n'
        f':wait_loop\r\n'
        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\r\n'
        'if not errorlevel 1 (\r\n'
        '  timeout /t 1 /nobreak >NUL\r\n'
        '  goto wait_loop\r\n'
        ')\r\n'
        f'copy /y "{new_exe_path}" "{current_exe}"\r\n'
        f'del /f /q "{new_exe_path}"\r\n'
        f'start "" "{current_exe}"\r\n'
        'del /f /q "%~f0"\r\n'
    )
    with open(bat_path, 'w', encoding='gbk', errors='ignore') as f:
        f.write(bat_content)
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ['cmd', '/c', bat_path],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True)
    print(f'<< 更新 >> 替换脚本已启动，程序即将退出并自动升级到新版本...')
    os._exit(0)


def _apply_source_update(zip_path):
    """解压源码包并按白名单覆盖本地代码文件（不覆盖配置/数据）"""
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    extract_dir = os.path.join(tempfile.gettempdir(), 'autoPublish_update_src')
    overwritten = 0
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)
    # zip 内部有一层顶层目录 autoPublish-<tag>，定位它
    inner_root = extract_dir
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        inner_root = os.path.join(extract_dir, entries[0])
    # 覆盖白名单文件
    for name in UPDATE_WHITELIST_FILES:
        src = os.path.join(inner_root, name)
        if os.path.isfile(src):
            _copy_overwrite(src, os.path.join(base_dir, name))
            overwritten += 1
    # 覆盖白名单目录（novel_publisher 包）
    for dirname in UPDATE_WHITELIST_DIRS:
        src_root = os.path.join(inner_root, dirname)
        if not os.path.isdir(src_root):
            continue
        for root, _dirs, files in os.walk(src_root):
            rel = os.path.relpath(root, src_root)
            if '__pycache__' in rel.split(os.sep) or '.git' in rel.split(os.sep):
                continue
            dst_root = os.path.join(base_dir, dirname, rel) if rel != '.' else os.path.join(base_dir, dirname)
            os.makedirs(dst_root, exist_ok=True)
            for fname in files:
                if fname.endswith('.py'):
                    _copy_overwrite(os.path.join(root, fname), os.path.join(dst_root, fname))
                    overwritten += 1
    print(f'<< 更新 >> 源码更新完成，共覆盖 {overwritten} 个文件，请重启程序生效')


def _copy_overwrite(src, dst):
    with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
        fdst.write(fsrc.read())
    print(f'<< 更新 >> 已覆盖: {os.path.basename(dst)}')


def apply_update(tag, mirrors=None):
    """执行更新：exe 模式替换重启；源码模式覆盖代码文件"""
    if getattr(sys, 'frozen', False):
        exe_name = os.path.basename(sys.executable)
        new_exe = sys.executable + '.new'
        _download_asset(tag, exe_name, new_exe, mirrors=mirrors)
        if os.path.getsize(new_exe) < 1024 * 1024:
            os.remove(new_exe)
            raise RuntimeError('下载的更新文件过小，疑似无效，已取消替换')
        _run_replace_and_restart(new_exe)
    else:
        zip_path = os.path.join(tempfile.gettempdir(), f'autoPublish_{tag}_source.zip')
        _download_source_zip(tag, zip_path, mirrors=mirrors)
        _apply_source_update(zip_path)


def get_mirrors_from_config(config_parser):
    """从 config.ini [Update] 读取自定义镜像列表（逗号分隔），留空用默认"""
    try:
        raw = config_parser.get('Update', 'mirror_list', fallback='')
    except Exception:
        raw = ''
    mirrors = [m.strip() for m in raw.split(',') if m.strip()]
    return mirrors if mirrors else DEFAULT_MIRRORS


def check_update_async(current_version, config_parser, on_result, on_error=None):
    """后台线程检查更新

    on_result(has_update, remote_tag) / on_error(err_msg) 均在子线程回调
    """
    mirrors = get_mirrors_from_config(config_parser)

    def _worker():
        try:
            remote_tag = fetch_latest_version(mirrors)
            has_update = is_newer(remote_tag, current_version)
            on_result(has_update, remote_tag)
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_worker, daemon=True).start()
