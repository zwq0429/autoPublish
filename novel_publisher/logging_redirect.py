"""stdout/stderr 重定向到 tkinter ScrolledText 的代理类"""

import sys
import tkinter as tk


class TextRedirector:
    """将 stdout/stderr 重定向到 Tkinter Text 控件。

    用法::

        redirector = TextRedirector(log_text)
        redirector.install()   # 开始重定向
        ...
        redirector.restore()   # 恢复原始 stdout/stderr
    """

    def __init__(self, text_widget: tk.Text):
        self.text_widget = text_widget
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    # ---- 安装 / 恢复 ----

    def install(self):
        sys.stdout = self
        sys.stderr = self

    def restore(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    # ---- file-like 接口 ----

    def log(self, message):
        try:
            if not self.text_widget.winfo_exists():
                return
            self.text_widget.config(state='normal')
            self.text_widget.insert(tk.END, message + '\n')
            self.text_widget.config(state='disabled')
            self.text_widget.see(tk.END)
        except Exception:
            pass

    def write(self, text):
        try:
            if self.text_widget.winfo_exists():
                # 通过 after 在主线程安全调用
                self.text_widget.after(0, self.log, text.strip())
        except Exception:
            pass
        try:
            original = getattr(self, 'original_stdout', None)
            if original is not None:
                original.write(text)
                original.flush()
        except Exception:
            pass

    def flush(self):
        try:
            original = getattr(self, 'original_stdout', None)
            if original is not None:
                original.flush()
        except Exception:
            pass
        try:
            original = getattr(self, 'original_stderr', None)
            if original is not None:
                original.flush()
        except Exception:
            pass
