# -*- coding: utf-8 -*-
"""单文件 exe 入口：默认启动服务；--worker / --login / --fetch-author 走子命令。"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd == "--worker":
        import worker
        worker.main(argv[1:])
    elif cmd == "--login":
        import douyin_login
        sys.argv = ["douyin_login.py"] + argv[1:]
        douyin_login.main()
    elif cmd == "--fetch-author":
        import fetch_author_cli
        sys.argv = ["fetch_author_cli.py"] + argv[1:]
        fetch_author_cli.main()
    else:
        import launcher
        launcher.main()


if __name__ == "__main__":
    main()
