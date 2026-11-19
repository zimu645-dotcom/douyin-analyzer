# -*- coding: utf-8 -*-
"""抓取抖音精确互动数据（官方 Web API，页面上下文 fetch，自带登录态+签名）
- 视频: /aweme/v1/web/aweme/detail/?aweme_id=xxx → 点赞/评论/收藏/转发/播放
- 主播: /aweme/v1/web/user/profile/other/?sec_user_id=xxx → 粉丝/关注/获赞/作品
- 可批量: 一次浏览器会话处理多个视频 + 1 个主播
"""
import json, os, sys, io

from _paths import BASE
import accounts
PROFILE = accounts.profile_dir()
# 指向项目内 browsers，不依赖系统环境变量
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(BASE, "browsers"))

API_SCRIPT = r"""
async (payload) => {
    const results = {videos: {}, author: null};
    const headers = {'Referer': 'https://www.douyin.com/'};
    // 视频详情
    for (const vid of payload.video_ids) {
        try {
            const url = '/aweme/v1/web/aweme/detail/?aweme_id=' + vid +
                '&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1';
            const r = await fetch(url, {headers});
            const d = await r.json();
            const a = d.aweme_detail;
            if (a) {
                const s = a.statistics || {};
                results.videos[vid] = {
                    like: s.digg_count ?? '-',
                    comment: s.comment_count ?? '-',
                    collect: s.collect_count ?? '-',
                    share: s.share_count ?? '-',
                    play: s.play_count ?? '-',
                    author_name: (a.author && a.author.nickname) || '',
                    author_id: (a.author && a.author.sec_uid) || '',
                    publish_time: a.create_time || 0,
                };
            } else {
                results.videos[vid] = {error: (d.status_msg || 'no data').slice(0, 50)};
            }
        } catch (e) {
            results.videos[vid] = {error: String(e).slice(0, 50)};
        }
    }
    // 主播主页
    if (payload.sec_user_id) {
        try {
            const url = '/aweme/v1/web/user/profile/other/?sec_user_id=' + payload.sec_user_id +
                '&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1';
            const r = await fetch(url, {headers});
            const d = await r.json();
            const u = d.user;
            if (u) {
                results.author = {
                    nickname: u.nickname || '',
                    fans: u.follower_count ?? '-',
                    following: u.following_count ?? '-',
                    total_likes: u.total_favorited ?? '-',
                    works: u.aweme_count ?? '-',
                };
            } else {
                results.author = {error: (d.status_msg || 'no user').slice(0, 50)};
            }
        } catch (e) {
            results.author = {error: String(e).slice(0, 50)};
        }
    }
    return results;
}
"""


def fetch_stats(video_ids, sec_user_id=None):
    """一次会话抓取多个视频 + 主播数据。返回 {videos: {...}, author: {...}}"""
    if not video_ids and not sec_user_id:
        return {"videos": {}, "author": None}
    from playwright.sync_api import sync_playwright
    import browser_util
    try:
        with sync_playwright() as p:
            ctx = browser_util.launch_persistent(
                p, PROFILE, headless=True,
                args=["--disable-blink-features=AutomationControlled"])
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            # 先建立会话（打开抖音首页拿 cookies/会话）
            pg.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(2500)
            payload = {"video_ids": video_ids, "sec_user_id": sec_user_id}
            results = pg.evaluate(API_SCRIPT, payload)
            ctx.close()
            return results
    except Exception as e:
        return {"videos": {}, "author": None, "error": str(e)[:100]}


def video_stats(video_id):
    """单个视频统计（兼容旧接口）"""
    r = fetch_stats([video_id])
    return r.get("videos", {}).get(video_id, {}) or {}


def author_stats(sec_user_id):
    """主播统计（兼容旧接口）"""
    r = fetch_stats([], sec_user_id)
    return r.get("author") or {}


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    vids = sys.argv[1:] or ["6993312408697572616"]
    print("测试视频:", vids)
    r = fetch_stats(vids)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r.get("videos", {}).get(vids[0], {}).get("author_id"):
        print("\n主播 sec_user_id:", r["videos"][vids[0]]["author_id"])
        a = author_stats(r["videos"][vids[0]]["author_id"])
        print("主播数据:", json.dumps(a, ensure_ascii=False))
