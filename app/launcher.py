# -*- coding: utf-8 -*-
"""启动抖音视频拆解报告服务"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONPATH"] = ""

import server  # noqa: E402

if __name__ == "__main__":
    print("启动服务: http://127.0.0.1:8321")
    server.run(watchdog=True)
