# -*- coding: utf-8 -*-
"""视频画面分析（mimo-v2.5 视觉）：下载视频流 → ffmpeg 每5秒抽帧 → 视觉模型分析
输出: [{time, image_path, analysis}]
"""
import os, sys, json, base64, subprocess, io, time, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE, "app_output")
COOKIES = os.path.join(BASE, "cookies.txt")

VISION_PROMPT = """你是短视频画面分析专家。这是一段抖音视频的某一帧画面。
请从以下角度分析（60字以内，简洁）：
1. 画面内容：主体是什么（人物/产品/场景）
2. 场景氛围：光线、色调、环境
3. 画面中的文字/字幕（如有）
直接输出分析结果，不要任何前缀。"""

EVENT_FILE = os.path.join(OUTPUT_DIR, "stream_events.jsonl")


def _write_event(ev):
    """写 SSE 事件（JSON Lines，server 读最新推送）"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ev["ts"] = time.time()
        with open(EVENT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_mimo_key():
    with open(os.path.join(BASE, ".mimo_key"), encoding="utf-8") as f:
        return f.read().strip()


def _resolve_key(conf):
    """读取 API key：只认配置面板输入的 key 字段，绝不回退读 key 文件"""
    return (conf.get("key") or "").strip()


def _get_vision_conf():
    """从配置读取视觉模型（app_output/config.json）"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import app_config
        cfg = app_config.load_config()
        v = cfg.get("vision", {})
        if v.get("enabled", True) and v.get("base_url") and v.get("model"):
            return v
    except Exception:
        pass
    return None


def _extract_content(msg):
    """兼容 content 为字符串或 OpenAI 新版数组格式"""
    c = msg.get("content")
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c if isinstance(x, dict)).strip()
    return (c or "").strip()


def _call_vision(conf, payload):
    """调用视觉 API 一次，返回 content（可能为空）"""
    key = _resolve_key(conf)
    req = urllib.request.Request(
        conf["base_url"],
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    # 直连：清空代理环境变量 + ProxyHandler({})，避免系统代理拦截 HTTPS 导致 SSL EOF
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    return _extract_content(d["choices"][0]["message"])


def analyze_frame(image_path):
    """单帧视觉分析 → 文字描述（视觉模型可配置）"""
    try:
        conf = _get_vision_conf()
        if not conf:
            return "(未配置视觉模型)"
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        if not _resolve_key(conf):
            return "(未配置 API Key)"
        payload = {
            "model": conf["model"],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            "max_tokens": 150,
        }
        content = _call_vision(conf, payload)
        # 空内容重试 2 次（模型偶发返回空/限流），间隔递增
        for attempt in range(2):
            if content:
                break
            time.sleep(1.5 * (attempt + 1))
            content = _call_vision(conf, payload)
        if not content:
            return "(画面内容无法识别)"
        return content
    except Exception as e:
        return f"(画面分析失败: {str(e)[:60]})"


def analyze_video(video_id, duration):
    """下载视频流 + 每5秒抽帧 + 逐帧分析
    返回 [{time, image, analysis}]（最多 N 帧）
    """
    frames_dir = os.path.join(OUTPUT_DIR, "frames", video_id)
    os.makedirs(frames_dir, exist_ok=True)

    # 1. 下载完整视频（yt-dlp -f b，不转音频）
    vid_path = os.path.join(OUTPUT_DIR, "video_tmp", f"{video_id}.mp4")
    os.makedirs(os.path.dirname(vid_path), exist_ok=True)
    # 定位 yt-dlp：优先 venv Scripts（不依赖 PATH），否则系统 PATH
    import shutil as _shutil
    _yt = os.path.join(BASE, "venv", "Scripts", "yt-dlp.exe")
    if not os.path.exists(_yt):
        _yt = _shutil.which("yt-dlp") or "yt-dlp"
    r = subprocess.run(
        [_yt, "--cookies", COOKIES, "--no-playlist", "-f", "b",
         "-o", vid_path, "--no-warnings", "--quiet",
         f"https://www.douyin.com/video/{video_id}"],
        capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.exists(vid_path) or os.path.getsize(vid_path) < 10000:
        return [{"time": 0, "image": "", "analysis": "(视频下载失败，无法画面分析)"}]

    # 2. 按配置抽帧（读取 config.json 的 vision.frame_interval / max_frames）
    vconf = _get_vision_conf() or {}
    try:
        frame_interval = int(vconf.get("frame_interval") or 5)
    except (TypeError, ValueError):
        frame_interval = 5
    try:
        max_frames = int(vconf.get("max_frames") or 12)
    except (TypeError, ValueError):
        max_frames = 12
    times = []
    t = 0
    while t < (duration or 60) and len(times) < max_frames:
        times.append(t)
        t += frame_interval

    results = []
    for i, t in enumerate(times):
        img = os.path.join(frames_dir, f"frame_{i:02d}_{t:03d}s.jpg")
        fr = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", vid_path,
             "-frames:v", "1", "-q:v", "3", img],
            capture_output=True, timeout=60)
        if fr.returncode == 0 and os.path.exists(img) and os.path.getsize(img) > 500:
            analysis = analyze_frame(img)
            # image 存相对 URL（前端可访问）
            img_url = f"/api/frame/{video_id}/{os.path.basename(img)}"
            results.append({"time": t, "image": img_url, "analysis": analysis})
            # 实时写事件（SSE 用）
            _write_event({
                "type": "vision_frame", "video_id": video_id,
                "frame": {"time": t, "image": img_url, "analysis": analysis},
            })
        # 帧间小延迟，避免限流
        time.sleep(0.5)

    # 清理视频临时文件
    try:
        os.remove(vid_path)
    except OSError:
        pass
    return results


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    vid = sys.argv[1]
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 30
    print(f"分析视频 {vid} (时长 {dur}s)...")
    rs = analyze_video(vid, dur)
    for r in rs:
        print(f"  [{r['time']}s] {r['analysis'][:60]}")
