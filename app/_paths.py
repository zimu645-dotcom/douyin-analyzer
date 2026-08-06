# -*- coding: utf-8 -*-
"""统一路径：源码模式 BASE=项目根；打包(exe)模式 BASE=exe所在目录"""
import os, sys


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE = _base_dir()
OUTPUT_DIR = os.path.join(BASE, "app_output")
