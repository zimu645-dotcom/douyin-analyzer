# -*- coding: utf-8 -*-
"""抖音视频拆解报告 - FastAPI 后端
启动: venv/Scripts/python app/server.py  (默认 http://127.0.0.1:8321)
"""
import os, sys, json, time, threading, re, shutil, subprocess
from pathlib import Path

from _paths import BASE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CUDA 库路径（faster-whisper GPU 需要）
_cublas = os.path.join(BASE, "venv", "Lib", "site-packages", "nvidia", "cublas", "bin")
if os.path.isdir(_cublas) and _cublas not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _cublas + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import services
from services import OUTPUT_DIR
import exporters

app = FastAPI(title="抖音视频拆解报告", version="1.0")

# ---------------- 任务状态（子进程调度，服务永不阻塞） ----------------
JOB = {
    "state": "idle",
    "message": "",
    "mode": "",
    "videos": {},
    "queue": 0,
    "started": None,
}
JOB_LOCK = threading.Lock()
STATUS_FILE = os.path.join(OUTPUT_DIR, "worker_status.json")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")
VENV_PY = os.path.join(BASE, "venv", "Scripts", "python.exe")


def _load_worker_status():
    try:
        if os.path.exists(STATUS_FILE):
            return json.load(open(STATUS_FILE, encoding="utf-8"))
    except Exception:
        pass
    return {}


def _merge_status():
    """把 worker 的状态文件合并进 JOB"""
    ws = _load_worker_status()
    if not ws:
        return
    with JOB_LOCK:
        if ws.get("state"):
            JOB["state"] = ws["state"]
        if ws.get("message"):
            JOB["message"] = ws["message"]
        for vid, v in (ws.get("videos") or {}).items():
            JOB["videos"][vid] = v


def spawn_worker(args):
    """启动 worker 子进程（Popen，不阻塞）"""
    global _WORKER_PROC
    with JOB_LOCK:
        JOB["state"] = "running"
        JOB["message"] = "启动中..."
        JOB["videos"] = {}
        JOB["started"] = time.time()
    # 清旧状态文件 + 事件流 + 实时数据
    for f in [STATUS_FILE, os.path.join(OUTPUT_DIR, "stream_events.jsonl"),
              os.path.join(OUTPUT_DIR, "live_data.json")]:
        try:
            os.remove(f)
        except OSError:
            pass
    # 启动子进程（保存引用，供「停止拆解」终止）
    if getattr(sys, "frozen", False):
        # 打包模式：启动同目录下的 worker.exe
        _exe_dir = os.path.dirname(sys.executable)
        cmd = [os.path.join(_exe_dir, "worker.exe")] + args
        _cwd = _exe_dir
    else:
        cmd = [VENV_PY, WORKER] + args
        _cwd = os.path.dirname(WORKER)
    proc = subprocess.Popen(cmd, cwd=_cwd,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
    _WORKER_PROC = proc
    return True


_WORKER_PROC = None


def _kill_worker():
    """终止当前 worker 进程（含子进程树），关闭所有 API 调用与任务流程"""
    global _WORKER_PROC
    proc = _WORKER_PROC
    _WORKER_PROC = None
    if proc and proc.poll() is None:
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


@app.post("/api/stop")
def api_stop():
    """停止当前拆解任务：终止 worker（关闭所有 API 调用），清空任务状态"""
    _kill_worker()
    for f in [STATUS_FILE, os.path.join(OUTPUT_DIR, "stream_events.jsonl"),
              os.path.join(OUTPUT_DIR, "live_data.json")]:
        try:
            os.remove(f)
        except OSError:
            pass
    with JOB_LOCK:
        JOB["state"] = "idle"
        JOB["message"] = "任务已停止"
        JOB["videos"] = {}
        JOB["queue"] = 0
        JOB["started"] = None
    return {"ok": True, "message": "已停止拆解"}


# ---------------- 请求模型 ----------------
class AuthorJob(BaseModel):
    url: str
    count: int = 5
    modules: dict = {}   # 生成模块勾选 {analysis, rewrite, versions, vision}


class SingleJob(BaseModel):
    url: str
    modules: dict = {}   # 生成模块勾选 {analysis, rewrite, versions, vision}


# ---------------- API 路由 ----------------
@app.get("/", response_class=HTMLResponse)
def index():
    if getattr(sys, "frozen", False):
        _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        _base = os.path.dirname(os.path.abspath(__file__))
    html = Path(os.path.join(_base, "static", "index.html")).read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/api/author")
def api_author(job: AuthorJob):
    with JOB_LOCK:
        if JOB["state"] == "running":
            return {"ok": False, "error": "已有任务在运行，请稍候"}
    spawn_worker(["author", job.url, str(job.count), json.dumps(job.modules, ensure_ascii=False)])
    return {"ok": True}


@app.post("/api/single")
def api_single(job: SingleJob):
    with JOB_LOCK:
        if JOB["state"] == "running":
            return {"ok": False, "error": "已有任务在运行，请稍候"}
    spawn_worker(["single", job.url, json.dumps(job.modules, ensure_ascii=False)])
    return {"ok": True}


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    with JOB_LOCK:
        if JOB["state"] == "running":
            return {"ok": False, "error": "已有任务在运行，请稍候"}
    os.makedirs(os.path.join(OUTPUT_DIR, "uploads"), exist_ok=True)
    fname = f"up_{int(time.time())}_{file.filename}"
    fpath = os.path.join(OUTPUT_DIR, "uploads", fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    title = os.path.splitext(file.filename or "本地音频")[0]
    spawn_worker(["local", fpath, title])
    return {"ok": True, "file": fname}


# ---------------- 心跳（网页关闭自动停止服务） ----------------
_LAST_HB = 0.0
_PENDING_STOP = None   # 页面明确关闭后的停止时间
_HB_LOCK = threading.Lock()


@app.get("/api/heartbeat")
def api_heartbeat():
    """网页心跳：收到即表示网页还开着，取消待定停止"""
    global _LAST_HB, _PENDING_STOP
    with _HB_LOCK:
        _LAST_HB = time.time()
        _PENDING_STOP = None
    return {"ok": True}


@app.post("/api/page-closing")
def api_page_closing():
    """页面关闭信号：3 秒后停止服务（刷新时新页面会立即发心跳取消）"""
    global _PENDING_STOP
    with _HB_LOCK:
        _PENDING_STOP = time.time() + 3
    return {"ok": True}


def _hb_watchdog():
    """守护线程：
    - 收到「页面关闭」信号 → 3 秒后停止（刷新时新页面心跳会取消）
    - 未收到信号但 20 秒无心跳 → 兜底停止（异常关闭）"""
    global _LAST_HB, _PENDING_STOP
    got_first = False
    while True:
        time.sleep(1)
        with _HB_LOCK:
            hb = _LAST_HB
            pend = _PENDING_STOP
        now = time.time()
        if hb > 0:
            got_first = True
        # 页面明确关闭：3 秒停止窗口
        if pend and now >= pend:
            print("网页已关闭，停止服务", flush=True)
            os._exit(0)
        # 心跳超时兜底（异常关闭，如浏览器崩溃/强杀）
        if got_first and now - hb > 20:
            print("网页心跳超时，自动停止服务", flush=True)
            os._exit(0)


@app.get("/api/status")
def api_status():
    _merge_status()
    with JOB_LOCK:
        return json.loads(json.dumps(JOB, ensure_ascii=False))


@app.get("/api/live")
def api_live():
    """返回当前任务的实时累积数据（前端刷新恢复用）"""
    live_file = os.path.join(OUTPUT_DIR, "live_data.json")
    if os.path.exists(live_file):
        try:
            return json.load(open(live_file, encoding="utf-8"))
        except Exception:
            pass
    return {"video_id": None, "step": "idle"}


@app.get("/api/frame/{video_id}/{filename}")
def api_frame(video_id: str, filename: str):
    """返回视频分析帧图片"""
    # 防路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "非法文件名")
    fdir = os.path.join(OUTPUT_DIR, "frames", video_id)
    fpath = os.path.join(fdir, filename)
    if not os.path.exists(fpath):
        raise HTTPException(404, "帧不存在")
    return FileResponse(fpath, media_type="image/jpeg")


@app.get("/api/stream")
async def api_stream(request: Request):
    """SSE 实时事件流（流式优化版 v9 - to_thread 方案）
    架构要点（v9.3，解决两次卡死）：
    - 文件轮询封装在 asyncio.to_thread() 中，每次短暂占用线程池（毫秒级），
      既不阻塞 asyncio 事件循环，也不长期占用线程池线程 → 多连接/刷新/重连都不会卡死
    - 自适应轮询：有数据 50ms / 空闲 300ms
    - 事件序号 seq 保证顺序渲染 + 断线恢复去重（last-event-id）
    - 任务结束自动断开，心跳保持连接"""
    import asyncio
    from fastapi.responses import StreamingResponse

    EVENT_FILE = os.path.join(OUTPUT_DIR, "stream_events.jsonl")
    try:
        last_event_id = int(request.headers.get("last-event-id") or 0)
    except ValueError:
        last_event_id = 0

    def _format_sse(line):
        """格式化 SSE 消息，按 seq 去重"""
        try:
            ev = json.loads(line)
        except Exception:
            ev = {}
        seq = ev.get("seq") or 0
        if seq and seq <= last_event_id:
            return None
        if seq:
            return f"id: {seq}\ndata: {line}\n\n"
        return "data: " + line + "\n\n"

    # ===== 文件轮询（同步阻塞操作，放入 to_thread 执行，不阻塞事件循环） =====
    def _poll_events(state):
        """读取新增事件行，返回待推送的 SSE 消息列表。state 为可变的轮询状态 dict"""
        msgs = []
        try:
            if os.path.exists(EVENT_FILE):
                stat = os.stat(EVENT_FILE)
                cur_inode = stat.st_ino if hasattr(stat, 'st_ino') else None
                size = stat.st_size
                # 检测文件重建（inode 变化 或 大小变小）
                if (state["last_inode"] and cur_inode and cur_inode != state["last_inode"]) or size < state["last_pos"]:
                    state["last_pos"] = 0
                    state["last_inode"] = cur_inode
                if size > state["last_pos"]:
                    with open(EVENT_FILE, "r", encoding="utf-8") as f:
                        f.seek(state["last_pos"])
                        new_data = f.read()
                    state["last_pos"] = size
                    state["last_inode"] = cur_inode
                    for line in new_data.splitlines():
                        if line.strip():
                            msg = _format_sse(line.strip())
                            if msg:
                                msgs.append(msg)
                    state["idle_count"] = 0
                else:
                    state["idle_count"] += 1
            else:
                state["last_pos"] = 0
                state["idle_count"] += 1
        except Exception:
            state["idle_count"] += 1
        return msgs

    async def gen():
        # ===== 阶段 1：重放历史事件（页面刷新/晚打开恢复进度） =====
        await asyncio.to_thread(_merge_status)
        with JOB_LOCK:
            should_replay = JOB.get("state") == "running"
        if should_replay:
            def _replay():
                out = []
                try:
                    if os.path.exists(EVENT_FILE):
                        with open(EVENT_FILE, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    msg = _format_sse(line.strip())
                                    if msg:
                                        out.append(msg)
                        return out, f.tell()
                except Exception:
                    pass
                return out, 0
            msgs, last_pos = await asyncio.to_thread(_replay)
            for m in msgs:
                yield m
        else:
            last_pos = 0

        # 连接成功事件
        yield "data: " + json.dumps({"type": "connected", "seq": 0}, ensure_ascii=False) + "\n\n"

        # 任务已完成/失败（如页面刷新后重连）：推送状态事件并结束连接，
        # 前端据此设置 _taskCompleted，避免 done/error 状态下的重连风暴
        await asyncio.to_thread(_merge_status)
        with JOB_LOCK:
            _init_st = JOB.get("state")
        if _init_st in ("done", "error"):
            yield "data: " + json.dumps({"type": "job_state", "state": _init_st, "seq": 0}, ensure_ascii=False) + "\n\n"
            return

        # ===== 阶段 2：实时增量推送（to_thread 轮询） =====
        state = {"last_pos": last_pos, "last_inode": None, "idle_count": 0}
        FAST_POLL = 0.05   # 有数据：50ms
        SLOW_POLL = 1.0    # 空闲：1秒（降低线程池占用，防连接堆积）
        poll_interval = FAST_POLL
        last_activity = time.time()   # 最后一次有新事件的时间（keep-alive 不重置）

        try:
            while True:
                msgs = await asyncio.to_thread(_poll_events, state)
                if msgs:
                    last_activity = time.time()
                for m in msgs:
                    yield m
                if msgs:
                    poll_interval = FAST_POLL
                elif state["idle_count"] > 3:
                    poll_interval = SLOW_POLL

                # 任务结束立即断开：先推完当前批次（含 video_done），无新事件时关闭连接
                # 避免 done 状态下连接长期挂着、前端反复重连导致生成器堆积
                if not msgs:
                    await asyncio.to_thread(_merge_status)
                    with JOB_LOCK:
                        _st = JOB.get("state")
                    if _st in ("done", "error"):
                        break

                # 心跳 + 任务结束检测
                if state["idle_count"] > 30:
                    yield ": keep-alive\n\n"
                    state["idle_count"] = 0
                    await asyncio.to_thread(_merge_status)
                    with JOB_LOCK:
                        st = JOB.get("state")
                        if st in ("done", "error"):
                            await asyncio.sleep(0.5)
                            with JOB_LOCK:
                                if JOB.get("state") != "running":
                                    break

                # 空闲自动断开：非任务状态且 120 秒无新事件 → 关闭连接（前端自动重连）
                await asyncio.to_thread(_merge_status)
                with JOB_LOCK:
                    st2 = JOB.get("state")
                if st2 != "running" and time.time() - last_activity > 120:
                    yield "data: " + json.dumps({"type": "idle_close", "seq": 0}, ensure_ascii=False) + "\n\n"
                    break
                await asyncio.sleep(poll_interval)
        finally:
            pass  # 连接结束（已移除计数限制，依赖 idle 120s 自动断开防堆积）

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/config")
def api_get_config():
    """读取配置（key 脱敏）"""
    import app_config
    return app_config.get_config_public()


@app.post("/api/config")
def api_save_config(req: dict):
    """保存配置"""
    import app_config
    # 只接受白名单字段，防止覆盖 key 文件
    cfg = app_config.load_config()
    if "rewrite" in req:
        for eng in ("primary", "fallback"):
            if eng in req["rewrite"]:
                e = req["rewrite"][eng]
                for field in ("provider", "base_url", "model", "key_file", "key"):
                    if field in e and e[field]:
                        cfg["rewrite"][eng][field] = e[field]
    if "vision" in req:
        v = req["vision"]
        for field in ("provider", "base_url", "model", "key_file", "key", "frame_interval", "max_frames", "enabled"):
            if field in v and v[field] is not None:
                cfg["vision"][field] = v[field]
    if "whisper" in req:
        w = req["whisper"]
        if "use_title_prompt" in w and w["use_title_prompt"] is not None:
            cfg.setdefault("whisper", {})["use_title_prompt"] = bool(w["use_title_prompt"])
        if "hotwords" in w and isinstance(w["hotwords"], list):
            cfg.setdefault("whisper", {})["hotwords"] = [str(x).strip() for x in w["hotwords"] if str(x).strip()]
    # 长期保存标记：勾选才持久保存 key；不勾选任务完成后自动清除 key
    if "remember_key" in req:
        cfg["remember_key"] = bool(req["remember_key"])
    app_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/config/clear")
def api_clear_config():
    """清除配置：只删除各引擎的 API Key，保留默认模型名和服务器链接"""
    import app_config
    cfg = app_config.load_config()

    def _wipe(eng):
        """清除单个引擎的 key 来源（key + 旧版 key_file）"""
        if isinstance(eng, dict):
            eng["key"] = ""
            if "key_file" in eng:
                eng["key_file"] = ""

    # rewrite 是子引擎字典（primary/fallback），vision 是单引擎
    for eng in (cfg.get("rewrite", {}) or {}).values():
        _wipe(eng)
    _wipe(cfg.get("vision", {}))
    app_config.save_config(cfg)
    return {"ok": True, "message": "已清除 API Key，模型名与服务器链接已保留"}


@app.get("/api/history")
def api_history():
    """分析记录列表（含历史备份，最新在前）"""
    hfile = os.path.join(OUTPUT_DIR, "history.json")
    if os.path.exists(hfile):
        try:
            return json.load(open(hfile, encoding="utf-8"))
        except Exception:
            pass
    # 兼容：从 reports 目录扫描生成历史（之前采集的数据）
    hist = []
    rdir = os.path.join(OUTPUT_DIR, "reports")
    if os.path.isdir(rdir):
        for f in sorted(Path(rdir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.load(open(f, encoding="utf-8"))
                st = d.get("stats") or {}
                hist.append({
                    "video_id": d.get("video_id", ""), "title": d.get("title", ""),
                    "url": d.get("url", ""),
                    "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
                    "duration": round(d.get("duration", 0)),
                    "like": st.get("like", "-"), "comment": st.get("comment", "-"),
                    "collect": st.get("collect", "-"), "share": st.get("share", "-"),
                    "author": st.get("nickname") or st.get("channel_name", ""),
                    "fans": st.get("fans", "-"),
                    "segments": len(d.get("original_segments", [])),
                })
            except Exception:
                pass
    return hist


@app.delete("/api/history/{video_id}")
def api_delete_history(video_id: str):
    """删除指定视频的分析记录和相关文件"""
    deleted = []
    # 1. 从 history.json 中移除
    hfile = os.path.join(OUTPUT_DIR, "history.json")
    if os.path.exists(hfile):
        try:
            hist = json.load(open(hfile, encoding="utf-8"))
            hist = [h for h in hist if h.get("video_id") != video_id]
            with open(hfile, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=1)
            deleted.append("history.json")
        except Exception:
            pass
    # 2. 删除报告文件
    for subdir in ["reports", "transcripts", "rewritten", "audio"]:
        fpath = os.path.join(OUTPUT_DIR, subdir, f"{video_id}.json")
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                deleted.append(f"{subdir}/{video_id}.json")
            except Exception:
                pass
    # 删除音频文件（可能各种格式）
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    if os.path.isdir(audio_dir):
        for f in os.listdir(audio_dir):
            if f.startswith(video_id):
                try:
                    os.remove(os.path.join(audio_dir, f))
                    deleted.append(f"audio/{f}")
                except Exception:
                    pass
    # 3. 删除帧图片目录
    frames_dir = os.path.join(OUTPUT_DIR, "frames", video_id)
    if os.path.isdir(frames_dir):
        import shutil
        try:
            shutil.rmtree(frames_dir)
            deleted.append(f"frames/{video_id}/")
        except Exception:
            pass
    # 4. 删除导出文件
    export_dir = os.path.join(OUTPUT_DIR, "exports")
    if os.path.isdir(export_dir):
        for f in os.listdir(export_dir):
            if f.startswith(video_id):
                try:
                    os.remove(os.path.join(export_dir, f))
                    deleted.append(f"exports/{f}")
                except Exception:
                    pass
    return {"ok": True, "deleted": deleted}


@app.get("/api/reports")
def api_reports():
    rdir = os.path.join(OUTPUT_DIR, "reports")
    files = sorted(Path(rdir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if os.path.exists(rdir) else []
    out = []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
            out.append({"video_id": d["video_id"], "title": d["title"],
                        "url": d["url"], "duration": d.get("duration", 0)})
        except Exception:
            pass
    return out


@app.get("/api/report/{video_id}")
def api_report(video_id: str):
    rfile = os.path.join(OUTPUT_DIR, "reports", f"{video_id}.json")
    if not os.path.exists(rfile):
        raise HTTPException(404, "报告不存在")
    return json.load(open(rfile, encoding="utf-8"))


@app.get("/api/export/{video_id}/{fmt}")
def api_export(video_id: str, fmt: str):
    if fmt not in ("md", "xlsx"):
        raise HTTPException(400, "仅支持 md / xlsx")
    try:
        path = exporters.export(video_id, fmt)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    media = {"md": "text/markdown",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    return FileResponse(path, media_type=media.get(fmt, "application/octet-stream"),
                        filename=os.path.basename(path))


@app.post("/api/export/batch")
def api_export_batch(req: dict):
    """批量导出：{video_ids: [...], fmt: 'md'|'xlsx'}"""
    video_ids = req.get("video_ids") or []
    fmt = req.get("fmt", "xlsx")
    if not video_ids:
        raise HTTPException(400, "请选择要导出的视频")
    if fmt not in ("md", "xlsx"):
        raise HTTPException(400, "批量导出仅支持 md / xlsx")
    try:
        path = exporters.export_batch(video_ids, fmt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    media = {"md": "text/markdown",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    return FileResponse(path, media_type=media.get(fmt, "application/octet-stream"),
                        filename=os.path.basename(path))


# ---------------- 飞书多维表格导出 ----------------
@app.post("/api/export/feishu")
def api_export_feishu(req: dict):
    """导出到飞书多维表格：{video_ids: [...]}"""
    video_ids = req.get("video_ids") or []
    if not video_ids:
        raise HTTPException(400, "请选择要导出的视频")
    try:
        import feishu_export
        if len(video_ids) == 1:
            result = feishu_export.export_single(video_ids[0])
        else:
            result = feishu_export.export_batch(video_ids)
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导出失败: {str(e)}")


@app.get("/api/feishu/test")
def api_feishu_test():
    """测试飞书连接"""
    try:
        import feishu_export
        return feishu_export.test_connection()
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.get("/api/config/feishu")
def api_get_feishu_config():
    """获取飞书配置（脱敏）"""
    import app_config
    cfg = app_config.load_config().get("feishu", {})
    return {
        "app_id": cfg.get("app_id", ""),
        "app_token": cfg.get("app_token", ""),
        "table_id": cfg.get("table_id", ""),
        "auto_export": cfg.get("auto_export", False),
        # app_secret 不返回
    }


@app.post("/api/config/feishu")
def api_save_feishu_config(req: dict):
    """保存飞书配置"""
    import app_config
    cfg = app_config.load_config()
    feishu = cfg.setdefault("feishu", {})

    # 更新配置（允许清空字段）
    for field in ("app_id", "app_token", "table_id"):
        if field in req:
            feishu[field] = req[field] or ""
    # app_secret 特殊处理：只有传入非空值才更新，避免误清空
    if "app_secret" in req and req["app_secret"]:
        feishu["app_secret"] = req["app_secret"]
    if "auto_export" in req:
        feishu["auto_export"] = bool(req["auto_export"])

    app_config.save_config(cfg)
    return {"ok": True}


# ---------------- 启动 ----------------
def run(watchdog=False):
    import uvicorn
    import time as _t
    print("启动抖音视频拆解报告服务: http://127.0.0.1:8321")
    # 心跳看门狗：网页打开时持续心跳，网页关闭 20 秒后自动停止服务
    threading.Thread(target=_hb_watchdog, daemon=True).start()
    while True:
        try:
            # workers=1 单进程，但用线程模式避免同步阻塞互相影响
            uvicorn.run(app, host="127.0.0.1", port=8321, log_level="warning",
                        timeout_keep_alive=30)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            pass
        except Exception as e:
            print(f"服务异常退出: {e}", flush=True)
        if not watchdog:
            break
        # 看门狗：3 秒后自动重启，保证服务常驻
        print("服务崩溃，3 秒后自动重启...", flush=True)
        _t.sleep(3)


if __name__ == "__main__":
    run(watchdog=True)
