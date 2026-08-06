# -*- coding: utf-8 -*-
"""独立抖音登录（不依赖 OpenClaw）：启动自己的 Chrome，打开抖音登录页
老大扫码登录后，自动导出 cookies.txt（yt-dlp 用）+ 保存浏览器 profile（以后免登录）

用法: python douyin_login.py
依赖: playwright (pip install playwright && playwright install chromium)
"""
import os, sys, time, json

from _paths import BASE
PROFILE_DIR = os.path.join(BASE, "chrome_profile")
COOKIES = os.path.join(BASE, "cookies.txt")
# 打包/源码都指向项目内 browsers（不依赖系统环境变量，避免闪退）
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(BASE, "browsers"))

from playwright.sync_api import sync_playwright


def export_cookies(ctx):
    """导出抖音 cookies 为 Netscape 格式（yt-dlp 用，domain 带前导点）"""
    cookies = ctx.cookies("https://www.douyin.com")
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c["domain"] if c["domain"].startswith(".") else "." + c["domain"]
        secure = "TRUE" if c["secure"] else "FALSE"
        expires = str(int(c["expires"])) if c["expires"] else "0"
        lines.append(f"{domain}\tTRUE\t{c['path']}\t{secure}\t{expires}\t{c['name']}\t{c['value']}")
    with open(COOKIES, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    # 验证
    from http.cookiejar import MozillaCookieJar
    cj = MozillaCookieJar(COOKIES)
    cj.load(ignore_discard=True, ignore_expires=True)
    names = [c.name for c in cj]
    has_session = "sessionid" in names
    print(f"✅ cookies 已导出: {len(cj)} 个, sessionid={'有' if has_session else '无'}")
    return has_session


def main():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with sync_playwright() as p:
        # 启动独立 Chrome（自己的 profile，headed 可看）
        browser = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            viewport=None,
        )
        pg = browser.pages[0] if browser.pages else browser.new_page()
        print("打开抖音登录页... 请用抖音APP扫码登录", flush=True)
        pg.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        # 等用户扫码登录：轮询检测 sessionid cookie
        print("等待扫码登录（最长 3 分钟）...", flush=True)
        logged_in = False
        for i in range(90):
            time.sleep(2)
            cookies = browser.cookies("https://www.douyin.com")
            names = [c["name"] for c in cookies]
            if "sessionid" in names and "ttwid" in names:
                logged_in = True
                break
            if i % 15 == 0:
                print(f"  已等待 {(i+1)*2}s, 请扫码...", flush=True)

        if logged_in:
            print("🎉 登录成功！导出 cookies...", flush=True)
            ok = export_cookies(browser)
            if ok:
                print("✅ 全部完成：profile 已保存（以后免登录），cookies.txt 已导出", flush=True)
                print(f"  profile: {PROFILE_DIR}", flush=True)
                print(f"  cookies: {COOKIES}", flush=True)
            else:
                print("⚠️ cookies 导出缺少 sessionid，请重试", flush=True)
        else:
            print("❌ 超时未检测到登录，请重跑", flush=True)

        # 保持浏览器开着让老大确认（10秒后关闭）
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
