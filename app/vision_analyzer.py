# -*- coding: utf-8 -*-
"""视频画面分析（mimo-v2.5 视觉）：下载视频流 → ffmpeg 每5秒抽帧 → 视觉模型分析
输出: [{time, image_path, analysis}]
"""
import os, sys, json, base64, subprocess, io, time, urllib.request

from _paths import BASE, OUTPUT_DIR
import accounts
COOKIES = accounts.cookies_path()

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


def _call_vision(conf, payload, timeout=90):
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
    with opener.open(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    if not d.get("choices"):
        err = d.get("error") or {}
        raise RuntimeError(err.get("message") or "接口返回无 choices")
    return _extract_content(d["choices"][0]["message"])


def _call_vision_stream(conf, payload, on_token=None, timeout=300):
    """流式调用视觉 API（SSE），边收边回调；返回完整文本。
    服务端不支持流式时自动回退普通调用。"""
    key = _resolve_key(conf)
    p = dict(payload)
    p["stream"] = True
    body = json.dumps(p).encode()
    req = urllib.request.Request(
        conf["base_url"], data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}",
                 "Accept": "text/event-stream"})
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    parts = []
    try:
        with opener.open(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                if obj.get("error"):
                    raise RuntimeError((obj["error"] or {}).get("message") or "流式返回错误")
                ch = (obj.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                tok = delta.get("content")
                if tok:
                    parts.append(tok)
                    if on_token:
                        on_token(tok)
        text = "".join(parts).strip()
        if not text:
            # 流式无内容 → 回退普通调用（推理模型偶发只给 reasoning）
            return _call_vision(conf, payload, timeout=timeout)
        return text
    except Exception:
        if parts:
            return "".join(parts).strip()
        return _call_vision(conf, payload, timeout=timeout)


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


VIDEO_PROMPT = """你是短视频拆解专家。下面是一条完整的抖音视频（画面 + 声音）。
请从以下四个角度分析，直接输出结果，不要任何前缀，不要使用 **、#、- 这类 Markdown 符号：

一、整体结构
开头钩子、中段推进、结尾收束，标注大致时间点。

二、画面语言
镜头运动、景别、转场、字幕/花字的使用。

三、视觉风格
色调、光线、场景、人物或产品呈现方式。

四、可复用要点
这条视频最值得借鉴的 3 个具体做法，每条一行。"""

# 整段视频直传 MiMo：URL 上限 300MB；base64 兜底（官方限制 base64 字符串 ≤50MB，原始约 30MB）
VIDEO_URL_MAX = 300 * 1024 * 1024
VIDEO_MAX_BYTES = 30 * 1024 * 1024


def _fetch_video_bytes(video_id):
    """通过登录浏览器（无头）抓取视频 mp4 流，返回 bytes；失败返回 None"""
    try:
        import services
        return services._capture_media_bytes(video_id, kind="video")
    except Exception as e:
        print(f"[WARN] 视频抓取失败: {str(e)[:120]}", flush=True)
        return None


def _ffmpeg_bin():
    for d in (getattr(sys, "_MEIPASS", ""), BASE, os.path.join(BASE, "app")):
        p = os.path.join(d, "ffmpeg.exe") if d else ""
        if p and os.path.exists(p):
            return p
    return "ffmpeg"


def _upload_video_url_feishu(data, filename):
    """把视频上传到飞书云空间，返回临时直链（MiMo 可直接拉取）。
    走已配置的飞书应用，不依赖第三方图床。失败返回 None。"""
    try:
        import app_config
        import urllib.parse
        from feishu_client import FeishuClient
        cfg = app_config.load_config().get("feishu", {})
        app_id = (cfg.get("app_id") or "").strip()
        secret = (cfg.get("app_secret") or "").strip()
        app_token = (cfg.get("app_token") or "").strip()
        if not (app_id and secret and app_token):
            print("[WARN] 未配置飞书凭证，无法托管视频", flush=True)
            return None
        c = FeishuClient(app_id, secret)
        token = c.get_tenant_token()
        import uuid
        boundary = uuid.uuid4().hex
        body = []
        for k, v in [("file_name", filename), ("parent_type", "bitable_file"),
                     ("parent_node", app_token), ("size", str(len(data))), ("extra", "")]:
            body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                    f'filename="{filename}"\r\nContent-Type: video/mp4\r\n\r\n'.encode())
        body.append(data)
        body.append(f'\r\n--{boundary}--\r\n'.encode())
        r = c._request_raw("POST", f"{c.BASE_URL}/drive/v1/medias/upload_all", b"".join(body),
                           {"Authorization": "Bearer " + token,
                            "Content-Type": f"multipart/form-data; boundary={boundary}"})
        if r.get("code") != 0:
            print(f"[WARN] 飞书上传失败: {r.get('msg')}", flush=True)
            return None
        ft = (r.get("data") or {}).get("file_token")
        if not ft:
            print("[WARN] 飞书上传未返回 file_token", flush=True)
            return None
        g = c._request("GET",
                       f"{c.BASE_URL}/drive/v1/medias/batch_get_tmp_download_url?file_tokens={urllib.parse.quote(ft)}",
                       headers={"Authorization": "Bearer " + token})
        urls = (g.get("data") or {}).get("tmp_download_urls") or []
        if not urls:
            print(f"[WARN] 获取飞书临时直链失败: {g.get('msg')}", flush=True)
            return None
        u = urls[0].get("tmp_download_url")
        if u and u.startswith("http"):
            print(f"[vision] 视频已托管到飞书: {u[:80]}...", flush=True)
            return u
    except Exception as e:
        print(f"[WARN] 飞书托管视频异常: {str(e)[:120]}", flush=True)
    return None


def _upload_video_url(data, filename):
    """把视频上传到临时公网托管（litterbox，1 小时有效），返回直链；失败返回 None。
    MiMo 官方推荐 URL 传入（最大 300MB）；用 curl 上传，比 urllib 稳定。"""
    tmpdir = os.path.join(OUTPUT_DIR, "video_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    tmp = os.path.join(tmpdir, filename)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        for attempt in range(3):
            r = subprocess.run([
                "curl", "-sS", "--max-time", "900",
                "-F", "reqtype=fileupload", "-F", "time=1h",
                "-F", f"fileToUpload=@{tmp}",
                "https://litterbox.catbox.moe/resources/internals/api.php",
            ], capture_output=True, text=True, timeout=920)
            url = (r.stdout or "").strip()
            if r.returncode == 0 and url.startswith("http"):
                print(f"[vision] 视频已上传: {url}", flush=True)
                return url
            print(f"[WARN] 视频上传失败({attempt + 1}/3): {url[:100] or (r.stderr or '')[:100]}", flush=True)
            time.sleep(3)
    except Exception as e:
        print(f"[WARN] 视频上传异常: {str(e)[:120]}", flush=True)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return None


def _upload_video_url_alt(data, filename):
    """备用图床 0x0.st，返回直链；失败返回 None"""
    tmpdir = os.path.join(OUTPUT_DIR, "video_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    tmp = os.path.join(tmpdir, "alt_" + filename)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        r = subprocess.run(["curl", "-sS", "--max-time", "600", "-F", f"file=@{tmp}", "https://0x0.st"],
                           capture_output=True, text=True, timeout=620)
        url = (r.stdout or "").strip()
        if r.returncode == 0 and url.startswith("http"):
            print(f"[vision] 视频已上传(备用): {url}", flush=True)
            return url
        print(f"[WARN] 备用图床失败: {url[:100] or (r.stderr or '')[:100]}", flush=True)
    except Exception as e:
        print(f"[WARN] 备用图床异常: {str(e)[:100]}", flush=True)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return None


def _compress_video(data, video_id):
    """超过 base64 上限时转码压缩（480p / CRF30 / 64k 音频），返回压缩后 bytes"""
    tmpdir = os.path.join(OUTPUT_DIR, "video_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    src = os.path.join(tmpdir, f"{video_id}_src.mp4")
    dst = os.path.join(tmpdir, f"{video_id}_mimo.mp4")
    with open(src, "wb") as f:
        f.write(data)
    try:
        subprocess.run([
            _ffmpeg_bin(), "-y", "-v", "error", "-i", src,
            "-vf", "scale='min(480,iw)':-2", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "32",
            "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", dst,
        ], timeout=600, check=True)
        with open(dst, "rb") as f:
            out = f.read()
        print(f"[vision] 视频压缩: {len(data) // 1024 // 1024}MB → {len(out) // 1024 // 1024}MB", flush=True)
        return out
    except Exception as e:
        print(f"[WARN] 视频压缩失败: {str(e)[:100]}", flush=True)
        return None
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def _resolve_video_url(video_id):
    """无头打开视频页，捕获 media-video 流地址（带签名，MiMo 可直接拉取）。失败返回 None。"""
    try:
        import services
        return services._capture_media_url(video_id, kind="video")
    except Exception as e:
        print(f"[WARN] 视频地址获取失败: {str(e)[:120]}", flush=True)
        return None


def _ffprobe_bin():
    for d in (getattr(sys, "_MEIPASS", ""), BASE, os.path.join(BASE, "app")):
        p = os.path.join(d, "ffprobe.exe") if d else ""
        if p and os.path.exists(p):
            return p
    return "ffprobe"


def _video_duration(src):
    try:
        r = subprocess.run([_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", src],
                           capture_output=True, text=True, timeout=60)
        val = (r.stdout or "").strip()
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def _split_video(data, video_id, chunk_sec=120):
    """按真实时长把视频切成 chunk_sec 秒片段（URL 单次处理长视频易超时）。
    返回 [bytes]；只有 1 段时直接返回 [data]。"""
    tmpdir = os.path.join(OUTPUT_DIR, "video_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    src = os.path.join(tmpdir, f"{video_id}_full.mp4")
    with open(src, "wb") as f:
        f.write(data)
    chunks = []
    try:
        dur = _video_duration(src)
        if dur <= chunk_sec + 1:
            return [data]
        count = (int(dur) + chunk_sec - 1) // chunk_sec
        for idx in range(count):
            dst = os.path.join(tmpdir, f"{video_id}_part{idx}.mp4")
            start = idx * chunk_sec
            r = subprocess.run([
                _ffmpeg_bin(), "-y", "-v", "error", "-ss", str(start), "-t", str(chunk_sec),
                "-i", src, "-c", "copy", "-reset_timestamps", "1", dst,
            ], timeout=300, capture_output=True)
            if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 5000:
                with open(dst, "rb") as f:
                    chunks.append(f.read())
            try:
                os.remove(dst)
            except OSError:
                pass
    except Exception as e:
        print(f"[WARN] 视频分段失败: {str(e)[:100]}", flush=True)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    return chunks if len(chunks) > 1 else [data]


def analyze_video(video_id, duration):
    """整条视频按段上传为公网 URL，发给 MiMo 逐段理解后合并（不抽帧）
    返回 [{time, image, analysis}]，与旧接口结构一致，image 为空
    """
    conf = _get_vision_conf()
    if not conf:
        return [{"time": 0, "image": "", "analysis": "(未配置视觉模型)"}]
    if not _resolve_key(conf):
        return [{"time": 0, "image": "", "analysis": "(未配置视觉模型 API Key)"}]

    # MiMo 无法拉取抖音签名 CDN 地址（返回 failed to download media），改为本地下载后 base64 直传
    data = _fetch_video_bytes(video_id)
    if not data:
        return [{"time": 0, "image": "", "analysis": "(视频下载失败，无法画面分析)"}]
    # 压缩到 480p 再上传：URL 上限 300MB，但小文件 MiMo 拉取/解析更快、更稳
    if len(data) > 30 * 1024 * 1024:
        data = _compress_video(data, video_id)
        if not data:
            return [{"time": 0, "image": "", "analysis": "(视频压缩失败，无法画面分析)"}]

    # 抽帧率：默认每秒 2 帧，可在设置面板调整（0.1～10）
    try:
        fps = float(conf.get("fps") or 2)
    except (TypeError, ValueError):
        fps = 2.0
    fps = max(0.1, min(10.0, fps))

    chunks = _split_video(data, video_id, chunk_sec=120)
    results = []
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        start = i * 120
        label = f"{start // 60:02d}:{start % 60:02d}"
        # 段开始就通知前端（避免长时间无输出）
        _write_event({"type": "vision_segment_start", "video_id": video_id,
                      "index": i + 1, "total": total, "time": start, "label": label})
        # 只走 URL 方式（MiMo v2.6-flash 不支持本地/base64 视频上传）
        # 首选飞书云空间托管（稳定，已在配置里），失败再试公共图床
        video_url = _upload_video_url_feishu(chunk, f"{video_id}_p{i}.mp4")
        if not video_url:
            video_url = _upload_video_url(chunk, f"{video_id}_p{i}.mp4")
        if not video_url:
            video_url = _upload_video_url_alt(chunk, f"{video_id}_p{i}.mp4")
        if not video_url:
            msg = f"第 {i + 1}/{total} 段上传失败，本段跳过（仅支持 URL 方式）"
            results.append({"time": start, "image": "", "analysis": msg})
            _write_event({"type": "vision_frame", "video_id": video_id,
                          "frame": {"time": start, "image": "", "analysis": msg}})
            continue
        content_part = {"type": "video_url", "video_url": {"url": video_url},
                        "fps": fps, "media_resolution": "default"}
        prompt = VIDEO_PROMPT if total == 1 else (
            f"这是同一条完整视频的第 {i + 1}/{total} 段，起始时间约 {label}。"
            f"请只分析本段，并按整条视频的绝对时间标注。\n" + VIDEO_PROMPT)
        payload = {
            "model": conf["model"],
            "messages": [{"role": "user", "content": [
                content_part,
                {"type": "text", "text": prompt},
            ]}],
            # 推理模型会先消耗 reasoning token，预算过小会返回空 content
            "max_completion_tokens": 2048,
        }

        # 真流式：边收 token 边推送前端
        _buf = []
        def _on_tok(tok, _i=i):
            _buf.append(tok)
            _write_event({"type": "vision_token", "video_id": video_id,
                          "index": _i + 1, "total": total, "time": start, "tok": tok})

        content = ""
        last_err = ""
        for attempt in range(2):
            _buf.clear()
            try:
                content = _call_vision_stream(conf, payload, on_token=_on_tok, timeout=300)
            except Exception as e:
                content = ""
                last_err = f"(本段分析失败: {str(e)[:80]})"
            if content:
                break
            if attempt == 0:
                payload["max_completion_tokens"] = 4096
                time.sleep(2)
        if not content:
            content = last_err or "(本段内容无法识别)"
        item = {"time": start, "image": "", "analysis": content}
        results.append(item)
        # 每段完成即推送（前端用最终文本替换流式片段）
        _write_event({"type": "vision_frame", "video_id": video_id, "frame": item})
    return results


def analyze_video_frames_legacy(video_id, duration):
    """旧版：下载视频 + 每 N 秒抽帧 + 逐帧分析（保留备用，默认不调用）
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
    # 优先用项目内自带 ffmpeg（项目根 或 app 目录），否则系统 PATH
    _ffmpeg = ""
    for _d in (BASE, os.path.join(BASE, "app")):
        _p = os.path.join(_d, "ffmpeg.exe")
        if os.path.exists(_p):
            _ffmpeg = _p
            break
    if not _ffmpeg:
        _ffmpeg = "ffmpeg"
    for i, t in enumerate(times):
        img = os.path.join(frames_dir, f"frame_{i:02d}_{t:03d}s.jpg")
        fr = subprocess.run(
            [_ffmpeg, "-y", "-v", "error", "-ss", str(t), "-i", vid_path,
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
