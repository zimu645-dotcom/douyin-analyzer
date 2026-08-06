# -*- coding: utf-8 -*-
"""抓主页视频清单 CLI（独立 profile，headless）→ app_output/videos.json
用法: python fetch_author_cli.py <主页URL> <数量>
"""
import sys, os, json, time, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE, "chrome_profile")
OUT = os.path.join(BASE, "app_output", "videos.json")


def clean_title(raw):
    if not raw:
        return "(无标题)"
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    keep = []
    for l in lines:
        if l == "置顶":
            continue
        if re.fullmatch(r"[\d.,]+[万kK]?", l):
            continue
        if l not in keep:
            keep.append(l)
    with_hashtag = [l for l in keep if "#" in l]
    if with_hashtag:
        return with_hashtag[0]
    return keep[0] if keep else "(无标题)"


def main():
    url = sys.argv[1]
    max_count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    from playwright.sync_api import sync_playwright

    videos = {}
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR, headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        pg = browser.pages[0] if browser.pages else browser.new_page()
        pg.route("**/*", lambda route: route.abort()
                 if route.request.resource_type in ("image", "media", "font", "stylesheet") else route.continue_())
        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(8)
        # 尝试切换到「作品」标签，避免抓到推荐/喜欢流里的他人视频
        try:
            pg.click("text=作品", timeout=3000)
            time.sleep(2)
        except Exception:
            pass

        last_count, stable = 0, 0
        for i in range(80):
            pg.mouse.wheel(0, 1500)
            time.sleep(1.2)
            links = pg.eval_on_selector_all(
                "a[href*='/video/']",
                "els => els.map(e => ({href: e.href, title: (e.getAttribute('title') || e.innerText || '').trim()}))")
            for l in links:
                m = re.search(r"/video/(\d+)", l["href"])
                if m and m.group(1) not in videos:
                    videos[m.group(1)] = {"video_id": m.group(1),
                                          "title": clean_title(l["title"]),
                                          "url": f"https://www.douyin.com/video/{m.group(1)}"}
            if len(videos) == last_count:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last_count = len(videos)
            if len(videos) >= max_count:
                break
        browser.close()

    result = list(videos.values())[:max_count]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"OK {len(result)} videos")


if __name__ == "__main__":
    main()
