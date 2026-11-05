"""新版主程序入口：UI 与 app.py 完全一致，业务槽函数改为调用 cli/ 下的 CLI 工具。

- app.py 原样保留（旧实现，仍可独立运行），本文件不修改它。
- 本文件通过继承 NovelPublisherApp 复用全部界面与辅助逻辑，
  仅覆写 发布 / 检查 / 下载 / 建书 四个业务槽函数，改为 subprocess 调用 CLI：
      python -m cli publish        （发布）
      python -m cli check          （章节查重/字数检查）
      python -m cli download       （下载小说）
      python -m cli create-book    （创建新书）
- CLI 子进程的输出实时转发到界面日志区；CLI 完成后从 config.ini 刷新界面。

用法（源码模式，需在项目依赖环境中运行）:
    python app_cli.py
    python app_cli.py -fast 本地定时发布     # 与 app.py 相同的快速模式参数
"""

import os
import subprocess
import sys
import threading
import time
import traceback

# app.py 在模块级解析 sys.argv，导入前先屏蔽本程序的命令行参数
_argv = sys.argv[1:]
sys.argv = [sys.argv[0]]
try:
    from app import NovelPublisherApp  # noqa: E402  UI 完整复用
finally:
    sys.argv = [sys.argv[0]] + _argv

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class CliNovelPublisherApp(NovelPublisherApp):
    """UI 不变；发布/检查/下载/建书槽函数通过 CLI 子进程执行。"""

    def __init__(self):
        self._current_cli_proc = None
        super().__init__()

    # ---------------- CLI 调用基础设施 ----------------

    def _run_cli(self, cli_args, on_finish=None):
        """在子进程中运行 CLI，实时把输出转发到日志区，返回退出码。

        必须在非主线程中调用（内部会阻塞等待子进程结束）。
        """
        cmd = [sys.executable, '-m', 'cli'] + [str(a) for a in cli_args]
        print(f"[CLI] {' '.join(cmd)}")
        code = -1
        try:
            proc = subprocess.Popen(
                cmd, cwd=APP_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
            )
            self._current_cli_proc = proc
            for line in proc.stdout:
                print(line.rstrip('\n'))
            code = proc.wait()
        except Exception:
            traceback.print_exc()
            print("[CLI] 调用失败")
        finally:
            self._current_cli_proc = None
        if on_finish:
            try:
                on_finish(code)
            except Exception:
                traceback.print_exc()
        return code

    # ---------------- 发布（原槽: automation_flow） ----------------

    def automation_flow(self):
        """覆写：保存界面配置到 config.ini，然后调用 CLI publish。"""
        start_time = time.perf_counter()
        try:
            # fast_publish_mode=True 与原定时发布路径一致：保存配置且不弹确认框
            self.fast_publish_mode = True
            self.save_config()
        except Exception:
            traceback.print_exc()

        ok = self._run_cli(['publish']) == 0
        spend_time = time.perf_counter() - start_time
        if ok:
            print(f"任务成功-总耗时: {spend_time//60:.0f}分{spend_time%60:.2f}秒")
        else:
            print(f"任务失败: {spend_time//60:.0f}分{spend_time%60:.2f}秒")
        # CLI 已把发布进度写回 config.ini，在主线程刷新界面
        try:
            self.after(0, self.refresh_ui)
        except Exception:
            pass
        return ok

    def stop_publish(self, event=None):
        """覆写：保留原停止逻辑，并终止正在运行的 CLI 子进程。"""
        super().stop_publish(event)
        proc = self._current_cli_proc
        if proc is not None and proc.poll() is None:
            print("[CLI] 终止发布子进程...")
            try:
                proc.terminate()
            except Exception:
                traceback.print_exc()

    # ---------------- 检查（原槽: start_check_duplicate_titles） ----------------

    def start_check_duplicate_titles(self):
        """覆写：调用 CLI check（章节查重 + 字数检查）。"""
        novels_folder = self.novels_folder_var.get()
        neat_index = self.neat_index_var.get()
        self.check_title_button.config(state='disabled', text="检查中...")

        def worker():
            cli_args = ['check', '--folder', novels_folder]
            if not neat_index:
                cli_args.append('--no-neat-index')
            self._run_cli(cli_args)

            def restore():
                self.check_title_button.config(state='normal', text="检查标题")
            self.after(0, restore)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- 下载（原槽: download_book） ----------------

    def download_book(self):
        """覆写：保留原下载对话框 UI，“开始下载”改为调用 CLI download。"""
        import json as _json
        import tkinter as tk
        from tkinter import ttk

        try:
            novel_platform = self.publish_plate_var.get()

            export_dialog = tk.Toplevel(self)
            export_dialog.title("小说下载")
            export_dialog.geometry("400x360")
            export_dialog.transient(self)
            export_dialog.grab_set()

            ttk.Label(export_dialog, text="小说id:").pack(pady=10)
            book_id_var = tk.StringVar()
            ttk.Entry(export_dialog, textvariable=book_id_var, width=40).pack(pady=5)

            ttk.Label(export_dialog, text="选择下载范围:").pack(pady=10)
            range_frame = ttk.Frame(export_dialog)
            range_frame.pack(pady=5)
            ttk.Label(range_frame, text="从第").pack(side=tk.LEFT)
            start_var = tk.IntVar(value=1)
            start_entry = ttk.Entry(range_frame, textvariable=start_var, width=5)
            start_entry.pack(side=tk.LEFT, padx=5)
            ttk.Label(range_frame, text="章到第").pack(side=tk.LEFT)
            end_var = tk.IntVar(value=3)
            end_entry = ttk.Entry(range_frame, textvariable=end_var, width=5)
            end_entry.pack(side=tk.LEFT, padx=5)
            ttk.Label(range_frame, text="章").pack(side=tk.LEFT)

            export_all_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(export_dialog, text="下载全部章节",
                            variable=export_all_var).pack(pady=5)
            just_download_content_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(export_dialog, text="只下载目录",
                            variable=just_download_content_var).pack(pady=5)

            ttk.Label(export_dialog, text="输出文件夹:").pack(pady=5)
            output_var = tk.StringVar(value="output")
            ttk.Entry(export_dialog, textvariable=output_var, width=40).pack(pady=5)

            def perform_export():
                book_id = book_id_var.get().strip()
                if not book_id:
                    print("错误：请输入小说id")
                    return
                cli_args = ['download',
                            '--platform', novel_platform,
                            '--book-id', book_id,
                            '--save-dir', output_var.get()]
                if just_download_content_var.get():
                    cli_args.append('--toc-only')
                elif export_all_var.get():
                    cli_args.append('--all')
                else:
                    cli_args += ['--start', str(start_var.get()), '--end', str(end_var.get())]
                export_dialog.destroy()
                threading.Thread(target=self._run_cli, args=(cli_args,), daemon=True).start()

            ttk.Button(export_dialog, text="开始下载", command=perform_export).pack(pady=20)
            ttk.Label(export_dialog, text="ps.下载全文需要svip账号，否则只能下载前10章").pack(pady=5)

        except Exception as e:
            traceback.print_exc()
            print(f"下载功能出错: {e}")

    # ---------------- 建书（原槽: create_book_from_outline） ----------------

    def create_book_from_outline(self, fast_mode=False):
        """覆写：调用 CLI create-book（默认从项目根目录的大纲.txt 读取开书信息）。"""
        def worker():
            self._run_cli(['create-book'])

            def refresh():
                try:
                    self.refresh_ui()
                except Exception:
                    traceback.print_exc()
            self.after(0, refresh)

        threading.Thread(target=worker, daemon=True).start()


def main():
    import app as app_module

    # 快速模式参数与 app.py 一致（-fast 任务名 / -key / --headless）
    try:
        key, fast_mode, headless = app_module.parse_command_line_args()
    except SystemExit:
        key, fast_mode, headless = None, None, False
    # 与 app.py 直接运行时一致：同步模块级全局，供基类 __init__ 等读取
    app_module.key = key
    app_module.fast_mode = fast_mode

    app = CliNovelPublisherApp()

    if headless:
        app.keep_browser_open_var.set(True)
    else:
        app.keep_browser_open_var.set(False)

    if fast_mode:
        app.withdraw()
        app.execute_scheduled_task(fast_mode)
        app.mainloop()
    else:
        app.mainloop()


if __name__ == '__main__':
    main()
