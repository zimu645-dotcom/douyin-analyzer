# -*- coding: utf-8 -*-
"""启动抖音视频拆解报告服务"""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONPATH"] = ""

# 控制台编码兜底：非中文代码页(如 cp437/cp1252)下 print 中文不再崩溃
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import server  # noqa: E402


def main():
    print("启动服务: http://127.0.0.1:8321")
    server.run(watchdog=True)


if __name__ == "__main__":
    main()
