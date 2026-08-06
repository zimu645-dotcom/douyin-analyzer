# -*- coding: utf-8 -*-
"""飞书多维表格导出模块
功能：将分析报告转换为飞书记录格式并批量写入
"""
import os
import json
import time

import app_config
from feishu_client import FeishuClient
from services import OUTPUT_DIR


def _get_client():
    """获取飞书客户端（从配置读取凭证）"""
    cfg = app_config.load_config().get("feishu", {})
    app_id = (cfg.get("app_id") or "").strip()
    app_secret = (cfg.get("app_secret") or "").strip()

    if not app_id or not app_secret:
        raise RuntimeError("未配置飞书应用凭证，请在设置中配置 App ID 和 App Secret")

    return FeishuClient(app_id, app_secret)


def _get_table_info():
    """获取多维表格配置"""
    cfg = app_config.load_config().get("feishu", {})
    app_token = (cfg.get("app_token") or "").strip()
    table_id = (cfg.get("table_id") or "").strip()

    if not app_token or not table_id:
        raise RuntimeError("未配置多维表格信息，请在设置中配置 app_token 和 table_id")

    return app_token, table_id


def _safe_number(value, default=0):
    """安全转换为数字"""
    if value is None or value == "" or value == "-":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def report_to_record(report):
    """将单个分析报告转换为飞书记录格式

    Args:
        report: 分析报告 dict（来自 reports/*.json）

    Returns:
        飞书记录格式 dict: {"fields": {...}}
    """
    stats = report.get("stats") or {}
    analysis = report.get("analysis") or {}
    versions = report.get("versions") or {}
    vision = report.get("vision") or []

    # 汇总画面分析
    vision_lines = []
    for v in vision:
        time_point = v.get("time", 0)
        text = v.get("analysis", "")
        vision_lines.append(f"[{time_point}秒] {text}")
    vision_summary = "\n".join(vision_lines) if vision_lines else ""

    # 汇总亮点分析
    highlights = analysis.get("highlights") or []
    highlights_lines = []
    for h in highlights:
        point = h.get("point", "")
        how = h.get("how", "")
        use = h.get("use", "")
        highlights_lines.append(f"• {point}: {how} → {use}")
    highlights_text = "\n".join(highlights_lines)

    # 汇总改进建议
    improvements = analysis.get("improvements") or []
    improvements_lines = []
    for i in improvements:
        point = i.get("point", "")
        problem = i.get("problem", "")
        fix = i.get("fix", "")
        improvements_lines.append(f"• {point}: {problem} → {fix}")
    improvements_text = "\n".join(improvements_lines)

    # 处理开头钩子（可能是列表）
    hooks = versions.get("开头钩子备选") or []
    if isinstance(hooks, list):
        hooks_text = "\n".join(hooks)
    else:
        hooks_text = str(hooks)

    # 处理链接字段（飞书URL格式）
    url = report.get("url") or ""
    title = report.get("title") or ""

    # 分析时间转为字符串（「分析时间」字段是文本类型，避免日期/时间戳格式问题）
    analysis_time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime())

    def _txt(v):
        """安全转文本：None/列表/字典统一转字符串"""
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    return {
        "fields": {
            "视频ID": _txt(report.get("video_id")),
            "标题": _txt(title),
            "链接": url,                      # 文本类型，直接传 url 字符串
            "时长(秒)": _safe_number(report.get("duration"), 0),
            "点赞": _safe_number(stats.get("like"), 0),
            "评论": _safe_number(stats.get("comment"), 0),
            "收藏": _safe_number(stats.get("collect"), 0),
            "转发": _safe_number(stats.get("share"), 0),
            "主播": _txt(stats.get("nickname") or stats.get("channel_name")),
            "粉丝": _safe_number(stats.get("fans"), 0),   # 数字字段
            "一句话总结": _txt(analysis.get("summary")),
            "适合场景": _txt(analysis.get("scenes")),
            "核心结构": _txt(analysis.get("structure")),
            "口播版": _txt(versions.get("口播版")),
            "变体版": _txt(versions.get("变体版")),
            "原结构复刻版": _txt(versions.get("原结构复刻版")),
            "开头钩子": _txt(hooks_text),
            "复刻提示词": _txt(report.get("prompt")),
            "画面分析": _txt(vision_summary),
            "值得学习": _txt(highlights_text),
            "改进建议": _txt(improvements_text),
            "分析时间": analysis_time_str,   # 文本字段，字符串
        }
    }


def _ensure_fields(client, app_token, table_id):
    """确保表格有所有需要的字段，没有则创建"""
    # 需要的字段：(名称, 类型)
    # 类型: 1=文本, 2=数字, 5=日期
    required_fields = [
        ("视频ID", 1),
        ("标题", 1),
        ("链接", 1),  # 改为文本类型，避免格式问题
        ("时长(秒)", 2),
        ("点赞", 2),
        ("评论", 2),
        ("收藏", 2),
        ("转发", 2),
        ("主播", 1),
        ("粉丝", 2),  # 改为数字类型
        ("一句话总结", 1),
        ("适合场景", 1),
        ("核心结构", 1),
        ("口播版", 1),
        ("变体版", 1),
        ("原结构复刻版", 1),
        ("开头钩子", 1),
        ("复刻提示词", 1),
        ("画面分析", 1),
        ("值得学习", 1),
        ("改进建议", 1),
        ("分析时间", 1),  # 改为文本类型，避免日期格式问题
        ("画面图片", 17),  # 17=附件，存储画面分析帧图
    ]

    # 获取现有字段
    existing = client.list_fields(app_token, table_id)
    existing_names = {f.get("field_name") for f in existing}

    # 创建缺失的字段
    created = 0
    failed = []
    for field_name, field_type in required_fields:
        if field_name not in existing_names:
            try:
                client.create_field(app_token, table_id, field_name, field_type)
                created += 1
            except Exception as e:
                failed.append(field_name)

    if failed:
        raise RuntimeError(
            f"创建字段失败({len(failed)}个): {', '.join(failed[:6])}{'...' if len(failed) > 6 else ''}。"
            f"请在飞书开放平台开通『更新数据表/字段』权限(base:table:update)并发布新版本")

    return created


def _upload_vision_images(client, app_token, video_id):
    """上传视频画面帧图到飞书，返回附件字段值列表 [{file_token, name}]"""
    frames_dir = os.path.join(OUTPUT_DIR, "frames", video_id)
    tokens = []
    if not os.path.isdir(frames_dir):
        return tokens
    for f in sorted(os.listdir(frames_dir)):
        if f.lower().endswith((".jpg", ".jpeg", ".png")):
            path = os.path.join(frames_dir, f)
            try:
                ft = client.upload_file(path, app_token)
                if ft:
                    tokens.append({"file_token": ft, "name": f})
            except Exception as e:
                print(f"  [WARN] 上传帧图失败 {f}: {e}")
    return tokens


def export_single(video_id):
    """导出单个视频报告到飞书

    Args:
        video_id: 视频ID

    Returns:
        导出结果 dict
    """
    # 读取报告
    report_file = os.path.join(OUTPUT_DIR, "reports", f"{video_id}.json")
    if not os.path.exists(report_file):
        raise FileNotFoundError(f"报告不存在: {video_id}")

    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    # 转换格式
    record = report_to_record(report)

    # 写入飞书
    client = _get_client()
    app_token, table_id = _get_table_info()

    # 确保字段存在
    _ensure_fields(client, app_token, table_id)

    # 上传画面帧图到飞书（附件字段）
    try:
        record["fields"]["画面图片"] = _upload_vision_images(client, app_token, video_id)
    except Exception as e:
        print(f"  [WARN] 上传画面图片失败: {e}")
        record["fields"]["画面图片"] = []

    # 写入记录
    result = client.batch_create_records(app_token, table_id, [record])

    return {
        "ok": True,
        "video_id": video_id,
        "title": report.get("title", ""),
        "message": f"成功导出到飞书多维表格",
    }


def export_batch(video_ids):
    """批量导出多个视频报告到飞书

    Args:
        video_ids: 视频ID列表

    Returns:
        导出结果 dict
    """
    records = []
    skipped = []

    for vid in video_ids:
        report_file = os.path.join(OUTPUT_DIR, "reports", f"{vid}.json")
        if not os.path.exists(report_file):
            skipped.append(vid)
            continue

        with open(report_file, "r", encoding="utf-8") as f:
            report = json.load(f)

        records.append((vid, report_to_record(report)))

    if not records:
        raise RuntimeError("没有可导出的报告")

    # 批量写入飞书
    client = _get_client()
    app_token, table_id = _get_table_info()
    _ensure_fields(client, app_token, table_id)

    # 逐个上传画面帧图
    for vid, record in records:
        try:
            record["fields"]["画面图片"] = _upload_vision_images(client, app_token, vid)
        except Exception:
            record["fields"]["画面图片"] = []

    result = client.batch_create_records(app_token, table_id, [r for _, r in records])

    return {
        "ok": True,
        "exported": len(records),
        "skipped": skipped,
        "message": f"成功导出 {len(records)} 条记录到飞书",
    }


def test_connection():
    """测试飞书连接（含表格权限验证，能直接暴露 403 权限问题）"""
    try:
        client = _get_client()
        base = client.test_connection()
        if not base.get("ok"):
            return base
        try:
            app_token, table_id = _get_table_info()
            client.list_fields(app_token, table_id)
            return {"ok": True, "message": "连接成功（凭证 + 表格权限均正常）"}
        except RuntimeError as e:
            return {"ok": False, "message": f"表格信息未配置: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"表格权限验证失败: {str(e)}（请检查应用权限及发布）"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
