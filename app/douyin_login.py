# -*- coding: utf-8 -*-
"""抖音扫码登录（多账号）
用法:
  python douyin_login.py                  # 登录/续期 default 账号（旧路径兼容）
  python douyin_login.py --account 小号A   # 登录指定账号，长期保存，自动切换为活跃账号

登录态保存在 accounts/<账号>/profile（Playwright 持久化 profile，长期免登录），
同时导出 accounts/<账号>/cookies.txt 供接口/下载使用；并复制一份到根 cookies.txt 兼容旧逻辑。
"""
import os, sys, time, json, shutil, io

# 控制台编码兜底：非中文代码页下 print 中文不再崩溃（登录闪退的根因）
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from _paths import BASE
import accounts

# 指向项目内 browsers（存在时），否则用 Playwright 全局缓存
_bundled = os.path.join(BASE, "browsers")
if os.path.isdir(_bundled):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _bundled

from playwright.sync_api import sync_playwright


def export_cookies(ctx, cookies_file):
    """导出抖音 cookies 为 Netscape 格式（yt-dlp 用，domain 带前导点）"""
    cookies = ctx.cookies("https://www.douyin.com")
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c["domain"] if c["domain"].startswith(".") else "." + c["domain"]
        secure = "TRUE" if c["secure"] else "FALSE"
        exp = int(c["expires"]) if c["expires"] else 0
        if exp <= 0:
            exp = 0
        lines.append(f"{domain}\tTRUE\t{c['path']}\t{secure}\t{exp}\t{c['name']}\t{c['value']}")
    os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
    with open(cookies_file, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    from http.cookiejar import MozillaCookieJar
    cj = MozillaCookieJar(cookies_file)
    cj.load(ignore_discard=True, ignore_expires=True)
    names = [c.name for c in cj]
    has_session = "sessionid" in names
    print(f"✅ cookies 已导出: {len(cj)} 个, sessionid={'有' if has_session else '无'}")
    return has_session


def _dispatch_context(pg):
    """把 Playwright 上下文转成 cookies 导出需要的接口（PersistentContext 本身有 cookies()）"""
    return pg


def main():
    account = ""
    force = "--force" in sys.argv[1:]
    args = sys.argv[1:]
    if "--account" in args:
        i = args.index("--account")
        if i + 1 < len(args):
            account = accounts.safe_name(args[i + 1])
    if account:
        accounts.ensure_account(account)
        profile = accounts.profile_dir(account)
        cookie_out = accounts.cookies_path(account)
        print(f"账号: {account}\nprofile: {profile}")
    else:
        profile = accounts.profile_dir()          # 无账号时回退旧 chrome_profile
        cookie_out = accounts.cookies_path()
        print(f"账号: default（兼容旧路径）")

    os.makedirs(profile, exist_ok=True)
    import browser_util
    with sync_playwright() as p:
        browser = browser_util.launch_persistent(
            p, profile, headless=False, args=["--start-maximized"], viewport=None)
        if force:
            # 重新登录：清掉旧 cookie，避免一启动就检测到旧 sessionid 直接关闭
            try:
                browser.clear_cookies()
                print("已清除旧登录态，等待重新扫码", flush=True)
            except Exception:
                pass
        pg = browser.pages[0] if browser.pages else browser.new_page()
        print("打开抖音登录页... 请用抖音APP扫码登录", flush=True)
        pg.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        print("等待扫码登录（实时检测，最长 1 分钟）...", flush=True)
        logged_in = False
        for i in range(60):
            time.sleep(1)
            cookies = browser.cookies("https://www.douyin.com")
            names = [c["name"] for c in cookies]
            if "sessionid" in names and "ttwid" in names:
                logged_in = True
                print(f"✅ 检测到登录成功（{i + 1}s）", flush=True)
                break
            if i % 10 == 0:
                print(f"  已等待 {i + 1}s, 请扫码...", flush=True)

        if logged_in:
            print("🎉 登录成功！导出 cookies...", flush=True)
            ok = export_cookies(browser, cookie_out)
            if ok:
                # 兼容旧的根 cookies.txt（fetch_stats/vision 等旧逻辑）
                try:
                    shutil.copyfile(cookie_out, accounts.LEGACY_COOKIES)
                except Exception:
                    pass
                if account:
                    accounts.set_active(account)
                    print(f"✅ 已切换活跃账号: {account}")
                print("✅ 全部完成：登录态长期保存，下次免扫码", flush=True)
                print(f"  profile: {profile}")
                print(f"  cookies: {cookie_out}")
            else:
                print("⚠️ cookies 导出缺少 sessionid，请重试", flush=True)
        else:
            print("❌ 超时未检测到登录，请重跑", flush=True)

        # 登录成功立即关闭；超时也直接关闭
        try:
            browser.close()
        except Exception:
            pass
        print("浏览器已关闭", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback, time
        traceback.print_exc()
        try:
            log = os.path.join(BASE, "app_output", "login.log")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write("\n===== " + time.strftime("%Y-%m-%d %H:%M:%S") + " =====\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        # 保留窗口 8 秒，避免闪退看不到错误
        time.sleep(8)
        raise
