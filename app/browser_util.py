# -*- coding: utf-8 -*-
"""Playwright 浏览器启动辅助：
- 优先系统 Chrome（抖音无头抓取更稳），再 Edge，最后 Playwright Chromium
- 提供线程内复用的常驻上下文，避免每个任务/每段视频重复启动浏览器（每次 10~15 秒）"""
import os
import threading

from _paths import BASE

# 线程本地：Playwright 同步 API 只能在创建它的线程里使用
_local = threading.local()


def _set_browsers_path():
    bundled = os.path.join(BASE, "browsers")
    if os.path.isdir(bundled):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled
    elif os.environ.get("PLAYWRIGHT_BROWSERS_PATH") == bundled:
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)


def launch_persistent(p, profile, headless=True, **kwargs):
    """启动持久化上下文：优先系统 Chrome（抖音无头抓取更稳），再 Edge，最后 Playwright Chromium。"""
    _set_browsers_path()
    os.makedirs(profile, exist_ok=True)
    last = None
    for channel in ("chrome", "msedge"):
        try:
            return p.chromium.launch_persistent_context(
                user_data_dir=profile, headless=headless, channel=channel, **kwargs)
        except Exception as e:
            last = e
    try:
        return p.chromium.launch_persistent_context(user_data_dir=profile, headless=headless, **kwargs)
    except Exception as e:
        last = e
    raise last


class SharedBrowser:
    """线程内复用的浏览器会话。
    用法：
        with browser_util.shared() as sb:
            page = sb.new_page()
            ...
    同一线程内的多次调用复用同一个浏览器进程，只开新页面，省掉反复启动的开销。"""

    def __init__(self):
        self._pw = None
        self._ctx = None
        self._profile = None

    def ensure(self, profile, headless=True, **kwargs):
        if self._ctx is not None and self._profile == profile:
            try:
                _ = self._ctx.pages  # 探活：浏览器被关掉会抛异常
                return self._ctx
            except Exception:
                self._ctx = None
        from playwright.sync_api import sync_playwright
        if self._pw is None:
            self._pw = sync_playwright().start()
        self._ctx = launch_persistent(self._pw, profile, headless=headless, **kwargs)
        self._profile = profile
        return self._ctx

    def new_page(self, profile, headless=True, **kwargs):
        ctx = self.ensure(profile, headless=headless, **kwargs)
        page = ctx.new_page()
        return ctx, page

    def close_page(self, page):
        try:
            page.close()
        except Exception:
            pass

    def shutdown(self):
        try:
            if self._ctx:
                self._ctx.close()
        except Exception:
            pass
        self._ctx = None
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._profile = None


def shared():
    """获取当前线程的共享浏览器实例"""
    sb = getattr(_local, "sb", None)
    if sb is None:
        sb = SharedBrowser()
        _local.sb = sb
    return sb

