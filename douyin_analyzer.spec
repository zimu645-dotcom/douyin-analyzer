# -*- mode: python ; coding: utf-8 -*-
"""单文件 exe 打包：pyinstaller douyin_analyzer.spec --noconfirm"""
import shutil
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# Playwright 自带驱动 + Web 框架的隐式导入
for pkg in ("playwright", "uvicorn", "fastapi", "starlette", "multipart", "pydantic"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# urllib 会按域名动态查找 idna 等编码；单文件模式必须显式收集
hiddenimports += collect_submodules("encodings")

hiddenimports += [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "accounts", "browser_util", "worker", "launcher", "douyin_login",
    "fetch_author_cli", "fetch_stats", "vision_analyzer", "app_config", "exporters",
]

# 前端静态页与本地 ffmpeg
datas += [("app/static", "static")]
for _name in ("ffmpeg", "ffprobe"):
    _p = shutil.which(_name)
    if _p:
        binaries += [(_p, ".")]

a = Analysis(
    ["app/entry.py"],
    pathex=["app", "."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "numpy", "torch", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DouyinAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
