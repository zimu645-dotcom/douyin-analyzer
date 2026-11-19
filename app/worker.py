# -*- coding: utf-8 -*-
"""独立任务 Worker（子进程运行，不阻塞服务主进程）
用法: python worker.py <mode> <args...>
  mode=single  url
  mode=author  url count
  mode=local   filepath title
状态写入 app_output/worker_status.json（服务从这里读取）
"""
import os, sys, json, time, re, io

from _paths import BASE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 强制 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import services
from services import OUTPUT_DIR

STATUS_FILE = os.path.join(OUTPUT_DIR, "worker_status.json")
EVENT_FILE = os.path.join(OUTPUT_DIR, "stream_events.jsonl")
LIVE_FILE = os.path.join(OUTPUT_DIR, "live_data.json")

# 当前任务的累积数据（每步更新，写入 LIVE_FILE 供前端刷新恢复）
_live = {"video_id": None, "title": "", "url": "", "duration": 0,
         "segments": [], "full_text": "", "rewritten_segments": [],
         "versions": {}, "analysis": {}, "prompt": "", "stats": {},
         "vision": [], "step": "init", "updated": 0}


# ===== 全局事件序号（前端按 seq 排序渲染 + 断线恢复去重） =====
import threading as _threading
_event_seq = [0]  # 列表包装便于闭包修改
_event_lock = _threading.Lock()


def write_event(ev):
    """写 SSE 事件（实时流输出用），自动加序号 seq 和时间戳，立即 flush"""
    _event_seq[0] += 1
    ev["seq"] = _event_seq[0]
    ev["ts"] = time.time()
    try:
        with _event_lock:
            with open(EVENT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()  # 立即刷盘，降低前端延迟
    except Exception:
        pass


def write_live():
    """把当前累积数据写入 LIVE_FILE（前端刷新恢复用）"""
    try:
        _live["updated"] = time.time()
        with open(LIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(_live, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def live_update(**kwargs):
    """更新 _live 并写盘"""
    _live.update(kwargs)
    write_live()

# ===== 各阶段进度百分比定义（前端分段进度条用） =====
PROGRESS_MAP = {
    "downloading": 5,
    "transcribing": 20,
    "rewriting": 50,
    "versions_gen": 65,
    "analysis_gen": 75,
    "vision_gen": 85,
    "video_done": 100,
}


def write_status(state=None, message=None, video_id=None, **fields):
    try:
        s = json.load(open(STATUS_FILE, encoding="utf-8")) if os.path.exists(STATUS_FILE) else {}
    except Exception:
        s = {}
    if state:
        s["state"] = state
    if message:
        s["message"] = message
    s["videos"] = s.get("videos", {})
    if video_id:
        s["videos"].setdefault(video_id, {})
        s["videos"][video_id].update(fields)
        # 若传了 stage 标识，写分段进度事件（前端分段进度条 + 主进度条）
        stage = fields.get("stage")
        if stage and stage in PROGRESS_MAP:
            write_event({"type": "progress", "video_id": video_id,
                         "percent": PROGRESS_MAP[stage], "stage": stage,
                         "ts": time.time()})
    s["updated"] = time.time()
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


# 替换 services 的进度回调
services.set_progress = lambda state=None, message=None, video_id=None, **f: write_status(state, message, video_id, **f)


def process_one(vid, title, url, modules=None):
    """下载→转写→改写→分析→报告（含互动数据抓取，改写阶段并发加速）
    modules: 生成模块勾选 {analysis, rewrite, versions, vision}，未勾选的跳过生成"""
    from concurrent.futures import ThreadPoolExecutor
    import fetch_stats
    modules = modules or {}
    use_analysis = modules.get("analysis", True)
    use_rewrite = modules.get("rewrite", True)
    use_versions = False   # 多版本仿写已移除
    use_vision_requested = modules.get("vision", False)
    _t_start = time.time()
    _done_times = {}  # 各并行阶段耗时（供 done 事件显示）
    # 初始化 live 数据
    live_update(video_id=vid, title=title, url=url, duration=0,
                segments=[], full_text="", rewritten_segments=[],
                versions={}, analysis={}, prompt="", stats={},
                vision=[], step="downloading")
    write_status(video_id=vid, status="downloading", title=title, progress="下载中", percent=5, stage="downloading")
    ok, api_title, dur = services.download_audio(vid, title)
    if not ok:
        write_status(video_id=vid, status="failed", progress="下载失败", percent=0)
        live_update(step="failed")
        return False

    # 抓互动数据（yt-dlp，与转写并行）
    write_status(video_id=vid, status="transcribing", title=api_title, progress="转写中", percent=20, stage="transcribing")
    write_event({"type": "video_start", "video_id": vid, "title": api_title,
                 "url": url, "source_url": url,
                 "canonical_url": f"https://www.douyin.com/video/{vid}"})

    def on_seg(seg):
        # 转写逐段实时推送
        _live["segments"].append(seg)
        write_live()  # 每段都写盘，刷新不丢
        write_event({"type": "transcribe_segment", "video_id": vid, "segment": seg})

    _t_trans_start = time.time()
    try:
        data = services.transcribe(vid, api_title, url, on_segment=on_seg)
    except Exception as e:
        # 转写失败不崩溃：标记失败，让批量继续下一个
        print(f"  ⚠️ 转写失败: {str(e)[:120]}", flush=True)
        write_status(video_id=vid, status="failed", title=api_title, progress="转写失败", percent=0)
        write_event({"type": "video_failed", "video_id": vid, "title": api_title,
                     "reason": f"转写失败: {str(e)[:80]}"})
        live_update(step="failed")
        return False
    _t_trans = round(time.time() - _t_trans_start, 1)
    live_update(title=api_title, duration=data["duration"],
                full_text=data["full_text"], segments=data["segments"], step="rewriting")
    write_event({"type": "transcribe_done", "video_id": vid, "title": api_title,
                 "segments": data["segments"], "full_text": data["full_text"],
                 "duration": data["duration"],
                 "transcribe_time": _t_trans,
                 "segment_count": len(data["segments"])})
    write_status(video_id=vid, status="rewriting", progress="AI 改写分析中", percent=50, duration=data["duration"], stage="rewriting")

    # 无语音（纯音乐/静音视频）：跳过 AI 分析，避免无效调用
    if not (data.get("full_text") or "").strip():
        write_status(video_id=vid, status="skipped", progress="无语音(跳过分析)", percent=100, duration=data["duration"])
        write_event({"type": "video_skipped", "video_id": vid, "reason": "no_audio", "title": api_title})
        base = {"video_id": vid, "title": api_title, "url": url, "duration": data.get("duration", 0),
                "language": data.get("language", ""), "skipped": True, "reason": "无语音",
                "original_segments": data.get("segments", [])}
        rdir = os.path.join(OUTPUT_DIR, "reports")
        os.makedirs(rdir, exist_ok=True)
        with open(os.path.join(rdir, f"{vid}.json"), "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)
        return True

    # 并行执行：润色 / 多版本 / 分析 / 提示词 / 互动数据 / 画面分析（6 路并发）
    def _polish():
        def on_batch(batch_out):
            # 追加到 live 累积数据
            for seg in batch_out:
                _live["rewritten_segments"].append(seg)
            write_live()
            write_event({"type": "rewrite_batch", "video_id": vid,
                         "segments": batch_out})
        return services.rewrite_segments(data["segments"], on_batch=on_batch)
    def _versions():
        # 流式：token 逐段推送（打字机效果）
        _v_t0 = time.time()
        _ver_buf = []
        def on_tok(tok):
            _ver_buf.append(tok)
            # 每 20 个 token 更新一次 live（减少磁盘写入频率）
            if len(_ver_buf) % 20 == 0:
                _live["versions"] = {"text": "".join(_ver_buf)}
                write_live()
            write_event({"type": "versions_token", "video_id": vid, "tok": tok})
        result = services.rewrite_versions(data["full_text"], stream=True, on_token=on_tok)
        _live["versions"] = result if isinstance(result, dict) else {"text": "".join(_ver_buf) or str(result)}
        _done_times["versions"] = round(time.time() - _v_t0, 1)
        write_live()
        return result
    def _analyze():
        _a_t0 = time.time()
        _ana_buf = []
        def on_tok(tok):
            _ana_buf.append(tok)
            if len(_ana_buf) % 20 == 0:
                _live["analysis"] = {"text": "".join(_ana_buf)}
                write_live()
            write_event({"type": "analysis_token", "video_id": vid, "tok": tok})
        result = services.analyze(data["full_text"], stream=True, on_token=on_tok)
        _live["analysis"] = result if isinstance(result, dict) else {"text": "".join(_ana_buf) or str(result)}
        _done_times["analysis"] = round(time.time() - _a_t0, 1)
        write_live()
        return result
    def _stats():
        # API 精确抓取：视频互动 + 主播主页（一次会话）
        _s_t0 = time.time()
        r = fetch_stats.fetch_stats([vid])
        v = r.get("videos", {}).get(vid, {}) or {}
        out = {
            "like": v.get("like", "-"), "comment": v.get("comment", "-"),
            "collect": v.get("collect", "-"), "share": v.get("share", "-"),
            "play": v.get("play", "-"),
            "channel_name": v.get("author_name", ""),
            "channel_id": v.get("author_id", ""),
        }
        if v.get("author_id"):
            a = fetch_stats.author_stats(v["author_id"]) or {}
            out.update({
                "fans": a.get("fans", "-"), "following": a.get("following", "-"),
                "total_likes": a.get("total_likes", "-"), "works": a.get("works", "-"),
                "nickname": a.get("nickname", ""),
            })
        _done_times["stats"] = round(time.time() - _s_t0, 1)
        return out

    def _stats_placeholder():
        return {"like": "-", "comment": "-", "collect": "-", "share": "-",
                "play": "-", "channel_name": "", "channel_id": "",
                "fans": "-", "following": "-", "total_likes": "-", "works": "-",
                "nickname": ""}
    def _vision():
        # 画面分析（mimo-v2.5 视觉，每5秒一帧）——失败不阻塞主流程
        try:
            import vision_analyzer
            return vision_analyzer.analyze_video(vid, data.get("duration", 30))
        except Exception as e:
            print(f"  ⚠️ 画面分析失败: {str(e)[:80]}", flush=True)
            return []

    def _vision_enabled():
        """勾选画面分析 + 配置启用视觉模型 → 才下载视频做画面分析"""
        if not use_vision_requested:
            return False
        try:
            import app_config
            v = app_config.load_config().get("vision", {})
            return bool(v.get("enabled", True) and v.get("base_url") and v.get("model") and v.get("key"))
        except Exception:
            return False

    use_vision = _vision_enabled()

    with ThreadPoolExecutor(max_workers=6) as ex:
        f_polish = ex.submit(_polish) if use_rewrite else None
        f_analyze = ex.submit(_analyze) if use_analysis else None
        f_vision = ex.submit(_vision) if use_vision else None
        rw = f_polish.result() if f_polish else []
        _done_times["polish"] = round(time.time() - _t_start, 1) if use_rewrite else 0
        versions = {}
        if use_analysis:
            write_status(video_id=vid, status="rewriting", progress="AI 分析中", percent=75, stage="analysis_gen")
        analysis = f_analyze.result() if f_analyze else {}
        prompt = ""  # 复刻提示词模块已移除
        # 互动数据不阻塞主流程：先占位，后台抓完再回写
        stats = _stats_placeholder()
        _live["stats"] = stats
        write_live()
        if f_vision:
            write_status(video_id=vid, status="rewriting", progress="画面分析中", percent=85, stage="vision_gen")
            vision = f_vision.result()
        else:
            vision = []
        _live["vision"] = vision
        live_update(step="finalizing")

    # 实时事件：分析 / 多版本 / 提示词 完成推送（带各阶段耗时）
    write_event({"type": "polish_done", "video_id": vid, "time": _done_times.get("polish", 0)})
    write_event({"type": "analysis_done", "video_id": vid, "analysis": analysis,
                 "time": _done_times.get("analysis", 0)})
    # 互动数据异步抓取：先发占位事件，后台抓完再发真实数据
    write_event({"type": "stats_done", "video_id": vid, "stats": stats,
                 "time": 0, "pending": True})

    # source_url = 用户粘贴的原始链接（原样保存，不改写）
    # canonical_url = 实际用于下载的规范链接
    source_url = url
    canonical_url = f"https://www.douyin.com/video/{vid}"
    rw_data = {"video_id": vid, "title": api_title, "url": source_url,
               "source_url": source_url, "canonical_url": canonical_url,
               "duration": data["duration"],
               "segments": rw, "versions": versions, "analysis": analysis, "prompt": prompt,
               "stats": stats, "vision": vision}
    with open(os.path.join(OUTPUT_DIR, "rewritten", f"{vid}.json"), "w", encoding="utf-8") as f:
        json.dump(rw_data, f, ensure_ascii=False, indent=2)
    report = {
        "video_id": vid, "title": api_title, "url": source_url,
        "source_url": source_url, "canonical_url": canonical_url,
        "duration": data["duration"],
        "language": data["language"], "original_segments": data["segments"],
        "full_text": data["full_text"], "rewritten_segments": rw,
        "versions": versions, "analysis": analysis, "prompt": prompt,
        "stats": stats, "vision": vision,
    }
    rdir = os.path.join(OUTPUT_DIR, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f"{vid}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    # 写入分析记录（history）
    _log_history(report)
    live_update(step="done")
    _t_total = round(time.time() - _t_start, 1)
    write_event({"type": "video_done", "video_id": vid, "title": report.get("title", ""),
                 "stats": stats, "url": report.get("url", ""),
                 "total_time": _t_total,
                 "timing": {
                     "transcribe": _t_trans,
                     "versions": _done_times.get("versions", 0),
                     "analysis": _done_times.get("analysis", 0),
                     "prompt": _done_times.get("prompt", 0),
                     "stats": _done_times.get("stats", 0),
                     "total": _t_total,
                 }})
    write_status(video_id=vid, status="done", progress="完成", percent=100, duration=data["duration"], stage="video_done")

    # 自动导出到飞书（如果配置了）
    try:
        import app_config
        cfg = app_config.load_config().get("feishu", {})
        if cfg.get("auto_export") and cfg.get("app_id") and cfg.get("app_secret"):
            print(f"  [FEISHU] Exporting: {vid}", flush=True)
            import feishu_export
            feishu_export.export_single(vid)
            print(f"  [FEISHU] Export success", flush=True)
    except Exception as e:
        print(f"  [FEISHU] Export failed: {str(e)[:80]}", flush=True)

    # 互动数据异步回填：不阻塞主流程，抓完后写回报告 + 刷新前端
    def _fill_stats_async():
        try:
            real_stats = _stats()
            # 更新 live
            _live["stats"] = real_stats
            write_live()
            write_event({"type": "stats_done", "video_id": vid, "stats": real_stats,
                         "time": _done_times.get("stats", 0), "pending": False})
            # 回写报告文件
            try:
                _rf = os.path.join(OUTPUT_DIR, "reports", f"{vid}.json")
                if os.path.exists(_rf):
                    _rep = json.load(open(_rf, encoding="utf-8"))
                    _rep["stats"] = real_stats
                    with open(_rf, "w", encoding="utf-8") as _f:
                        json.dump(_rep, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        except Exception as e:
            print(f"  ⚠️ 互动数据抓取失败: {str(e)[:80]}", flush=True)

    _threading.Thread(target=_fill_stats_async, daemon=True).start()

    return True


def _log_history(report):
    """记录分析历史（追加到 history.json，供前端随时查看）"""
    try:
        hfile = os.path.join(OUTPUT_DIR, "history.json")
        hist = []
        if os.path.exists(hfile):
            hist = json.load(open(hfile, encoding="utf-8"))
        st = report.get("stats") or {}
        entry = {
            "video_id": report["video_id"],
            "title": report.get("title", ""),
            "url": report.get("url", ""),
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "duration": round(report.get("duration", 0)),
            "like": st.get("like", "-"), "comment": st.get("comment", "-"),
            "collect": st.get("collect", "-"), "share": st.get("share", "-"),
            "author": st.get("nickname") or st.get("channel_name", ""),
            "fans": st.get("fans", "-"),
            "segments": len(report.get("original_segments", [])),
        }
        # 去重：同 video_id 覆盖旧记录（最新在前）
        hist = [h for h in hist if h.get("video_id") != report["video_id"]]
        hist.insert(0, entry)
        with open(hfile, "w", encoding="utf-8") as f:
            json.dump(hist[:200], f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _maybe_clear_key():
    """未勾选「长期保存」→ 任务完成后清除服务端所有 API Key，下次需重新填写"""
    try:
        import app_config
        cfg = app_config.load_config()
        if cfg.get("remember_key", False):
            return
        for eng in (cfg.get("rewrite", {}) or {}).values():
            if isinstance(eng, dict):
                eng["key"] = ""
        v = cfg.get("vision", {})
        if isinstance(v, dict):
            v["key"] = ""
        a = cfg.get("asr", {})
        if isinstance(a, dict):
            a["key"] = ""
        app_config.save_config(cfg)
        print("已清除 API Key（未勾选长期保存，下次需重新填写）", flush=True)
    except Exception as e:
        print(f"清除 key 失败: {e}", flush=True)


def run_single(url, modules=None):
    vid = extract_video_id(url)
    if not vid:
        write_status(state="error", message=f"链接中未找到视频ID: {url[:50]}")
        write_event({"type": "job_error", "video_id": "pending",
                     "message": f"链接中未找到视频ID，请检查链接格式: {url[:60]}"})
        return
    ok = process_one(vid, vid, url, modules=modules)
    write_status(state="done" if ok else "error",
                 message=f"视频处理{'完成' if ok else '失败'}")
    _maybe_clear_key()
    print("DONE", vid, ok, flush=True)


def extract_video_id(url):
    """从各种抖音链接格式提取视频 ID：
    1. /video/123456
    2. ?modal_id=123456 (主页弹窗)
    3. 纯数字串
    4. v.douyin.com 短链（尝试展开）
    """
    url = (url or "").strip()
    # 1. /video/ 路径
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    # 2. modal_id 参数
    m = re.search(r"modal_id=(\d+)", url)
    if m:
        return m.group(1)
    # 3. 纯数字
    if re.fullmatch(r"\d+", url):
        return url
    # 4. 短链（v.douyin.com）——尝试跟随重定向拿真实 URL
    if "v.douyin.com" in url:
        try:
            import urllib.request
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            final_url = resp.geturl()
            m = re.search(r"/video/(\d+)", final_url)
            if m:
                return m.group(1)
            m = re.search(r"modal_id=(\d+)", final_url)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None


def run_author(url, count, modules=None):
    from fetch_author_cli import main as fetch_main
    import subprocess, re as _re
    write_status(state="running", message="抓取主页视频清单...")
    # 抓清单：多抓 count*3 个候选，供作者过滤（主页可能混入推荐视频）
    if getattr(sys, "frozen", False):
        # 单文件 exe：自身即为分发入口，用 --fetch-author 子命令
        r = subprocess.run([sys.executable, "--fetch-author", url, str(count * 5)],
                           capture_output=True, timeout=180)
    else:
        _cli_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_author_cli.py")
        r = subprocess.run([sys.executable, _cli_py, url, str(count * 5)], capture_output=True, timeout=180)
    vfile = os.path.join(OUTPUT_DIR, "videos.json")
    if not os.path.exists(vfile):
        write_status(state="error", message="主页未抓取到视频")
        return
    videos = json.load(open(vfile, encoding="utf-8"))[:count * 3]

    # 提取目标博主 sec_uid（主页URL 形如 /user/{sec_uid}）
    m = _re.search(r"/user/([^/?]+)", url or "")
    target_sec_uid = m.group(1) if m else None

    # 批量验证作者：只保留该博主的作品，排除主页推荐的他人视频
    if target_sec_uid and videos:
        import fetch_stats
        stats = fetch_stats.fetch_stats([v["video_id"] for v in videos])
        got_author = any(stats.get("videos", {}).get(vv, {}).get("author_id")
                         for vv in [x["video_id"] for x in videos])
        if got_author:
            before = len(videos)
            videos = [v for v in videos
                      if stats.get("videos", {}).get(v["video_id"], {}).get("author_id") == target_sec_uid]
            if len(videos) < before:
                write_status(message=f"已排除 {before - len(videos)} 个非博主视频，确认 {len(videos)} 个博主作品")

    videos = videos[:count]
    if not videos:
        write_status(state="error", message="未验证到该博主的作品，请检查主页链接")
        return
    if len(videos) < count:
        write_status(message=f"该博主作品较少，仅确认 {len(videos)} 个，将全部分析")
    total = len(videos)
    write_status(state="running", message=f"确认 {total} 个博主作品，开始批量下载音频...")

    # ===== 阶段1：并行批量下载所有音频（下载快，互不阻塞） =====
    from concurrent.futures import ThreadPoolExecutor, as_completed
    for i, v in enumerate(videos):
        write_event({"type": "batch_progress", "video_id": v["video_id"], "index": i + 1,
                     "total": total, "title": v["title"], "phase": "download"})
    download_ok = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(services.download_audio, v["video_id"], v["title"]): v for v in videos}
        for fut in as_completed(futs):
            v = futs[fut]
            try:
                ok, _, _ = fut.result()
                download_ok[v["video_id"]] = ok
            except Exception:
                download_ok[v["video_id"]] = False

    # ===== 阶段2：按顺序逐个处理（第1→第2→第3，转写→润色→改写分析），不随机 =====
    write_status(state="running", message=f"音频下载完成，按顺序逐个分析 {total} 个视频...")
    for i, v in enumerate(videos):
        vid = v["video_id"]
        rfile = os.path.join(OUTPUT_DIR, "reports", f"{vid}.json")
        if os.path.exists(rfile):
            write_status(video_id=vid, status="done", title=v["title"], progress="已缓存(跳过)")
            write_event({"type": "batch_progress", "video_id": vid, "index": i + 1,
                         "total": total, "title": v["title"], "cached": True})
            continue
        if not download_ok.get(vid):
            write_status(video_id=vid, status="failed", title=v["title"], progress="下载失败(跳过)")
            write_event({"type": "batch_progress", "video_id": vid, "index": i + 1,
                         "total": total, "title": v["title"], "failed": True})
            continue
        write_event({"type": "batch_progress", "video_id": vid, "index": i + 1,
                     "total": total, "title": v["title"]})
        try:
            ok = process_one(vid, v["title"], v["url"], modules=modules)
        except Exception as e:
            # 双保险：任何单视频异常都不拖垮整个批量
            print(f"  ⚠️ 视频处理异常: {str(e)[:120]}", flush=True)
            write_status(video_id=vid, status="failed", title=v["title"], progress="处理异常", percent=0)
            write_event({"type": "batch_progress", "video_id": vid, "index": i + 1,
                         "total": total, "title": v["title"], "failed": True})
            ok = False
        write_status(message=f"[{i+1}/{total}] {v['title'][:20]}... {'完成' if ok else '失败'}")
    write_status(state="done", message=f"全部 {total} 个视频处理完成")
    _maybe_clear_key()
    print("DONE author", total, flush=True)


def run_local(file_path, title):
    write_status(state="running", message="处理本地音频...")
    vid = f"local_{int(time.time())}"
    write_status(video_id=vid, status="transcribing", title=title, progress="转写中", percent=30)
    wav = os.path.join(OUTPUT_DIR, "uploads", f"{vid}.wav")
    import subprocess
    _ff = "ffmpeg"
    for _d in (getattr(sys, "_MEIPASS", ""), BASE):
        _p = os.path.join(_d, "ffmpeg.exe") if _d else ""
        if _p and os.path.exists(_p):
            _ff = _p
            break
    subprocess.run([_ff, "-y", "-v", "error", "-i", file_path, "-ar", "16000", "-ac", "1", wav],
                   check=True, timeout=300)
    data = services.transcribe_local(wav, vid, title)
    write_status(video_id=vid, status="rewriting", progress="润色改写中", percent=55, duration=data["duration"])
    rw = services.rewrite_segments(data["segments"])
    versions = {}
    write_status(video_id=vid, status="rewriting", progress="AI 分析中", percent=85)
    analysis = services.analyze(data["full_text"])
    prompt = ""  # 复刻提示词模块已移除
    report = {
        "video_id": vid, "title": title, "url": "(本地文件)", "duration": data["duration"],
        "language": data["language"], "original_segments": data["segments"],
        "full_text": data["full_text"], "rewritten_segments": rw,
        "versions": versions, "analysis": analysis, "prompt": prompt,
    }
    rdir = os.path.join(OUTPUT_DIR, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f"{vid}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    write_status(video_id=vid, status="done", progress="完成", percent=100, duration=data["duration"])
    write_status(state="done", message="本地音频处理完成")
    print("DONE local", vid, flush=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0]

    def _mods(i):
        """解析生成模块勾选（JSON dict）"""
        try:
            return json.loads(argv[i]) if len(argv) > i else None
        except Exception:
            return None

    if mode == "single":
        run_single(argv[1], _mods(2))
    elif mode == "author":
        run_author(argv[1], int(argv[2]) if len(argv) > 2 else 5, _mods(3))
    elif mode == "local":
        run_local(argv[1], argv[2])


if __name__ == "__main__":
    main()
