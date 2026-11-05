"""支持 `python -m cli ...` 入口。"""

import sys

from .main import main

if __name__ == '__main__':
    sys.exit(main() or 0)
