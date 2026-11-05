"""咪咕平台 CLI 包装：python -m cli.migu publish [参数]"""

import sys

from .main import platform_main

if __name__ == '__main__':
    sys.exit(platform_main('咪咕'))
