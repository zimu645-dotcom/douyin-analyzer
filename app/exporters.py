# -*- coding: utf-8 -*-
"""导出模块：报告 → Excel / Markdown（美化版）
优化项：
- Excel：封面渐变、彩色徽章、对照表美化、版本色块、画面缩略图嵌入、A4横向打印
- Markdown：emoji 徽章、对照表、版本 blockquote、批量目录
"""
import os, json, time

from _paths import OUTPUT_DIR
EXPORT_DIR = os.path.join(OUTPUT_DIR, "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


def fmt_ts(sec):
    m, s = int(sec // 60), int(sec % 60)
    return f"{m:02d}:{s:02d}"


def _report_or_raise(video_id):
    rfile = os.path.join(OUTPUT_DIR, "reports", f"{video_id}.json")
    if not os.path.exists(rfile):
        raise FileNotFoundError(f"报告不存在: {video_id}")
    return json.load(open(rfile, encoding="utf-8"))


# ============================================================
#  Excel 导出（美化版）
# ============================================================

# 品牌色常量
_CLR_PRIMARY = "165DFF"
_CLR_PURPLE = "722ED1"
_CLR_GREEN = "00B42A"
_CLR_ORANGE = "FF7D00"
_CLR_RED = "F53F3F"
_CLR_BG_HEADER = "2B3A67"
_CLR_BG_COVER = "165DFF"
_CLR_BG_ROW_ALT = "F8F9FA"
_CLR_BG_SECTION = "EEF3FF"

# 版本色块映射
_VERSION_COLORS = {
    "口播版": ("165DFF", "EEF3FF"),
    "变体版": ("722ED1", "F3E8FF"),
    "原结构复刻版": ("00B42A", "E8FFF1"),
    "开头钩子备选": ("FF7D00", "FFF7E8"),
}


def _apply_font(cell, name="微软雅黑", size=10, bold=False, color="1F2329"):
    from openpyxl.styles import Font
    cell.font = Font(name=name, size=size, bold=bold, color=color)


def _apply_fill(cell, fg_color):
    from openpyxl.styles import PatternFill
    cell.fill = PatternFill("solid", fgColor=fg_color)


def _apply_border(cell, color="D9D9D9"):
    from openpyxl.styles import Border, Side
    thin = Side(style="thin", color=color)
    cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)


def _apply_align(cell, wrap=True, h="left", v="top"):
    from openpyxl.styles import Alignment
    cell.alignment = Alignment(wrap_text=wrap, horizontal=h, vertical=v)


def _style_header_row(ws, row, ncols, bg=_CLR_BG_HEADER):
    """深色表头样式"""
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        _apply_fill(cell, bg)
        _apply_font(cell, size=11, bold=True, color="FFFFFF")
        _apply_align(cell, h="center", v="center")
        _apply_border(cell, bg)


def _style_data_rows(ws, r1, r2, ncols, alt_bg=_CLR_BG_ROW_ALT):
    """数据行样式（隔行变色）"""
    for r in range(r1, r2 + 1):
        is_alt = (r - r1) % 2 == 1
        for c in range(1, ncols + 1):
            cell = ws.cell(row=r, column=c)
            _apply_font(cell, size=10)
            _apply_align(cell)
            _apply_border(cell)
            if is_alt:
                _apply_fill(cell, alt_bg)


def _set_col_widths(ws, widths):
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _auto_row_height(ws, r, ncols, base=18, chars_per_line=30):
    """根据内容自动调整行高"""
    max_lines = 1
    for c in range(1, ncols + 1):
        v = ws.cell(row=r, column=c).value or ""
        lines = len(str(v)) // chars_per_line + str(v).count("\n") + 1
        max_lines = max(max_lines, lines)
    ws.row_dimensions[r].height = max(base, base * max_lines)


def _add_cover(ws, report, st, an):
    """封面区：大标题 + 副标题 + 渐变色背景"""
    from openpyxl.styles import Alignment
    # 大标题
    ws.merge_cells("A1:G1")
    c = ws.cell(row=1, column=1, value=f"🎬 {report.get('title', '视频分析报告')}")
    _apply_font(c, size=18, bold=True, color="FFFFFF")
    _apply_fill(c, _CLR_BG_COVER)
    _apply_align(c, h="center", v="center")
    ws.row_dimensions[1].height = 48
    for col in range(1, 8):
        _apply_fill(ws.cell(row=1, column=col), _CLR_BG_COVER)

    # 副标题
    ws.merge_cells("A2:G2")
    url = report.get("url", "")
    dur = f"{report.get('duration', 0):.0f}秒"
    ts = time.strftime("%Y-%m-%d %H:%M")
    sub = f"链接: {url}  |  时长: {dur}  |  分析时间: {ts}"
    c = ws.cell(row=2, column=1, value=sub)
    _apply_font(c, size=10, color="FFFFFF")
    _apply_fill(c, "3B5FDB")
    _apply_align(c, h="center", v="center")
    ws.row_dimensions[2].height = 28
    for col in range(1, 8):
        _apply_fill(ws.cell(row=2, column=col), "3B5FDB")

    # 互动数据行（彩色徽章）
    row = 4
    badges = [
        ("❤️ 点赞", st.get("like", "-"), _CLR_RED),
        ("💬 评论", st.get("comment", "-"), _CLR_PRIMARY),
        ("⭐ 收藏", st.get("collect", "-"), _CLR_ORANGE),
        ("🔁 转发", st.get("share", "-"), _CLR_GREEN),
        ("▶️ 播放", st.get("play", "-"), _CLR_PURPLE),
    ]
    for i, (label, val, clr) in enumerate(badges):
        col = i + 1
        cell = ws.cell(row=row, column=col, value=f"{label} {val}")
        _apply_font(cell, size=11, bold=True, color="FFFFFF")
        _apply_fill(cell, clr)
        _apply_align(cell, h="center", v="center")
        _apply_border(cell, clr)
    ws.row_dimensions[row].height = 32

    # 主播信息
    row = 5
    author_parts = []
    if st.get("nickname"):
        author_parts.append(f"主播: {st['nickname']}")
    for k, label in [("fans", "粉丝"), ("total_likes", "获赞"), ("works", "作品"), ("following", "关注")]:
        if st.get(k) and st[k] != "-":
            author_parts.append(f"{label}: {st[k]}")
    if author_parts:
        ws.merge_cells("A5:G5")
        c = ws.cell(row=5, column=1, value="🎥 " + "  |  ".join(author_parts))
        _apply_font(c, size=10, color="4E5969")
        _apply_fill(c, "F8F9FA")
        _apply_align(c, h="left", v="center")
        ws.row_dimensions[5].height = 26

    # 分析总结
    row = 7
    for key, label, icon in [("summary", "💡 一句话总结", ""), ("scenes", "🎯 适合场景", ""), ("structure", "🏗 核心结构", "")]:
        val = an.get(key, "")
        if val:
            ws.cell(row=row, column=1, value=f"{icon} {label}")
            _apply_font(ws.cell(row=row, column=1), size=10, bold=True, color=_CLR_PRIMARY)
            _apply_fill(ws.cell(row=row, column=1), _CLR_BG_SECTION)
            _apply_border(ws.cell(row=row, column=1))
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
            c = ws.cell(row=row, column=2, value=val)
            _apply_font(c, size=10)
            _apply_align(c)
            for cc in range(2, 8):
                _apply_border(ws.cell(row=row, column=cc))
            ws.row_dimensions[row].height = max(24, 18 * (len(str(val)) // 50 + 1))
            row += 1
    return row


def to_excel(report, path):
    """美化版 Excel：封面 + 互动数据 + 分析 + 对照表 + 版本 + 画面 + 提示词"""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment

    wb = Workbook()
    st = report.get("stats") or {}
    an = report.get("analysis") or {}

    # ---- Sheet1: 视频总览（含封面） ----
    ws1 = wb.active
    ws1.title = "视频总览"
    row = _add_cover(ws1, report, st, an)

    # 值得学习表格
    if an.get("highlights"):
        row += 1
        ws1.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        _apply_font(ws1.cell(row=row, column=1), size=13, bold=True, color=_CLR_PURPLE)
        ws1.cell(row=row, column=1, value="⭐ 二、值得学习")
        row += 1
        hdrs = ["值得学的点", "原片怎么做的", "仿写时怎么用"]
        for c, h in enumerate(hdrs, 1):
            ws1.cell(row=row, column=c, value=h)
        _style_header_row(ws1, row, 3)
        row += 1
        hl_start = row
        for h in an["highlights"]:
            ws1.cell(row=row, column=1, value=h.get("point", ""))
            ws1.cell(row=row, column=2, value=h.get("how", ""))
            ws1.cell(row=row, column=3, value=h.get("use", ""))
            _auto_row_height(ws1, row, 3)
            row += 1
        _style_data_rows(ws1, hl_start, row - 1, 3)

    # 复用建议表格
    if an.get("improvements"):
        row += 1
        ws1.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        _apply_font(ws1.cell(row=row, column=1), size=13, bold=True, color=_CLR_ORANGE)
        ws1.cell(row=row, column=1, value="🔧 三、复用建议")
        row += 1
        hdrs = ["需要调整的点", "原片的问题", "仿写时怎么改"]
        for c, h in enumerate(hdrs, 1):
            ws1.cell(row=row, column=c, value=h)
        _style_header_row(ws1, row, 3, bg="8B5E00")
        row += 1
        imp_start = row
        for h in an["improvements"]:
            ws1.cell(row=row, column=1, value=h.get("point", ""))
            ws1.cell(row=row, column=2, value=h.get("problem", ""))
            ws1.cell(row=row, column=3, value=h.get("fix", ""))
            _auto_row_height(ws1, row, 3)
            row += 1
        _style_data_rows(ws1, imp_start, row - 1, 3)

    _set_col_widths(ws1, [20, 40, 40, 12, 12, 12, 12])
    ws1.freeze_panes = "A3"
    ws1.sheet_properties.pageSetUpPr = None
    from openpyxl.worksheet.page import PageMargins
    ws1.page_margins = PageMargins(left=0.5, right=0.5, top=0.75, bottom=0.75)
    ws1.page_setup.orientation = "landscape"
    ws1.page_setup.paperSize = ws1.PAPERSIZE_A4

    # ---- Sheet2: 原文对照润色（美化版） ----
    ws2 = wb.create_sheet("原文对照润色")
    ws2.merge_cells("A1:D1")
    c = ws2.cell(row=1, column=1, value="📄 原内容与润色改写对照")
    _apply_font(c, size=14, bold=True, color="FFFFFF")
    _apply_fill(c, _CLR_BG_COVER)
    _apply_align(c, h="center", v="center")
    ws2.row_dimensions[1].height = 40
    for col in range(1, 5):
        _apply_fill(ws2.cell(row=1, column=col), _CLR_BG_COVER)

    hdrs = ["⏱ 时间", "原内容", "✨ 润色改写", "状态"]
    for c_idx, h in enumerate(hdrs, 1):
        ws2.cell(row=2, column=c_idx, value=h)
    _style_header_row(ws2, 2, 4)

    orig = report.get("original_segments", [])
    rw = report.get("rewritten_segments") or []
    r = 3
    for i, s in enumerate(orig):
        ts = f"{fmt_ts(s['start'])} - {fmt_ts(s['end'])}"
        ws2.cell(row=r, column=1, value=ts)
        _apply_font(ws2.cell(row=r, column=1), size=10, bold=True, color=_CLR_PRIMARY)
        _apply_align(ws2.cell(row=r, column=1), h="center", v="center")

        ws2.cell(row=r, column=2, value=s["text"])
        if i < len(rw):
            ws2.cell(row=r, column=3, value=rw[i]["rewritten"])
            changed = rw[i]["rewritten"] != s["text"]
        else:
            changed = False

        status = "✅ 已润色" if changed else "— 原文"
        ws2.cell(row=r, column=4, value=status)
        _apply_font(ws2.cell(row=r, column=4), size=9, color=_CLR_GREEN if changed else "86909C")
        _apply_align(ws2.cell(row=r, column=4), h="center", v="center")

        _auto_row_height(ws2, r, 3)
        r += 1
    _style_data_rows(ws2, 3, r - 1, 4)
    _set_col_widths(ws2, [16, 50, 50, 12])
    ws2.freeze_panes = "A3"
    # 自动筛选（表头 A2:D2，数据 3..r-1）
    if r - 1 >= 3:
        ws2.auto_filter.ref = f"A2:D{r - 1}"

    # ---- Sheet3: 多版本仿写（色块区分） ----
    ws3 = wb.create_sheet("多版本仿写")
    ws3.merge_cells("A1:B1")
    c = ws3.cell(row=1, column=1, value="🎭 多版本仿写脚本")
    _apply_font(c, size=14, bold=True, color="FFFFFF")
    _apply_fill(c, _CLR_BG_COVER)
    _apply_align(c, h="center", v="center")
    ws3.row_dimensions[1].height = 40
    for col in range(1, 3):
        _apply_fill(ws3.cell(row=1, column=col), _CLR_BG_COVER)

    r = 3
    for name, text in (report.get("versions") or {}).items():
        # 版本标题行（色块）
        title_clr, bg_clr = _VERSION_COLORS.get(name, (_CLR_PURPLE, "F3E8FF"))
        ws3.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        c = ws3.cell(row=r, column=1, value=f"📝 {name}")
        _apply_font(c, size=12, bold=True, color="FFFFFF")
        _apply_fill(c, title_clr)
        _apply_align(c, h="left", v="center")
        _apply_border(c, title_clr)
        for col in range(1, 3):
            _apply_fill(ws3.cell(row=r, column=col), title_clr)
            _apply_border(ws3.cell(row=r, column=col), title_clr)
        ws3.row_dimensions[r].height = 32
        r += 1

        # 内容行
        content = "\n".join(text) if isinstance(text, list) else str(text)
        ws3.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        c = ws3.cell(row=r, column=1, value=content)
        _apply_font(c, size=10)
        _apply_fill(c, bg_clr)
        _apply_align(c)
        _apply_border(c)
        for col in range(1, 3):
            _apply_fill(ws3.cell(row=r, column=col), bg_clr)
            _apply_border(ws3.cell(row=r, column=col))
        ws3.row_dimensions[r].height = max(50, 16 * (len(content) // 50 + 1))
        r += 1

    _set_col_widths(ws3, [18, 90])

    # ---- Sheet4: 画面分析（含缩略图） ----
    vision = report.get("vision") or []
    if vision:
        ws4 = wb.create_sheet("画面分析")
        ws4.merge_cells("A1:C1")
        c = ws4.cell(row=1, column=1, value="🎬 画面分析（每5秒抽帧）")
        _apply_font(c, size=14, bold=True, color="FFFFFF")
        _apply_fill(c, _CLR_PURPLE)
        _apply_align(c, h="center", v="center")
        ws4.row_dimensions[1].height = 40
        for col in range(1, 4):
            _apply_fill(ws4.cell(row=1, column=col), _CLR_PURPLE)

        r = 3
        for fr in vision:
            # 时间标签
            ws4.cell(row=r, column=1, value=f"[{fr.get('time', 0)}s]")
            _apply_font(ws4.cell(row=r, column=1), size=11, bold=True, color=_CLR_PURPLE)
            _apply_align(ws4.cell(row=r, column=1), h="center", v="center")

            # 尝试嵌入缩略图
            img_url = fr.get("image", "")
            if img_url:
                # 从 /api/frame/xxx/frame_00_000s.jpg 提取本地路径
                parts = img_url.split("/")
                if len(parts) >= 4:
                    vid_from_url = parts[3] if len(parts) > 3 else ""
                    fname = parts[-1] if parts else ""
                    local_img = os.path.join(OUTPUT_DIR, "frames", vid_from_url, fname)
                    # 转为绝对路径（openpyxl Image 需要）
                    abs_img = os.path.abspath(local_img)
                    if os.path.exists(abs_img):
                        try:
                            from openpyxl.drawing.image import Image as XlImage
                            img = XlImage(abs_img)
                            img.width = 160
                            img.height = 90
                            ws4.add_image(img, f"B{r}")
                        except Exception as e:
                            pass

            # 描述
            ws4.cell(row=r, column=3, value=fr.get("analysis", ""))
            _apply_font(ws4.cell(row=r, column=3), size=10)
            _apply_align(ws4.cell(row=r, column=3))
            ws4.row_dimensions[r].height = max(80, 18 * (len(fr.get("analysis", "")) // 40 + 1))
            r += 1

        _set_col_widths(ws4, [12, 22, 60])

    # ---- Sheet5: 复刻提示词 ----
    if report.get("prompt"):
        ws5 = wb.create_sheet("复刻提示词")
        ws5.merge_cells("A1:A1")
        c = ws5.cell(row=1, column=1, value="🤖 复刻提示词（可直接用于 AI 视频工具）")
        _apply_font(c, size=14, bold=True, color="FFFFFF")
        _apply_fill(c, _CLR_BG_HEADER)
        _apply_align(c, h="center", v="center")
        ws5.row_dimensions[1].height = 40

        c = ws5.cell(row=3, column=1, value=report["prompt"])
        _apply_font(c, size=11)
        _apply_align(c)
        _apply_fill(c, "1F2329")
        from openpyxl.styles import Font
        c.font = Font(name="微软雅黑", size=11, color="E8E8E8")
        ws5.row_dimensions[3].height = max(80, 16 * (len(report["prompt"]) // 50 + 1))
        _set_col_widths(ws5, [100])

    wb.save(path)
    return path


# ============================================================
#  Markdown 导出（美化版）
# ============================================================

def to_markdown(report):
    lines = []
    st = report.get("stats") or {}
    an = report.get("analysis") or {}

    # 标题
    lines.append(f"# 🎬 {report.get('title', '视频分析报告')}")
    lines.append("")

    # 元信息表格
    lines.append("| 项目 | 信息 |")
    lines.append("|---|---|")
    lines.append(f"| 🔗 链接 | {report.get('url', '')} |")
    lines.append(f"| ⏱ 时长 | {report.get('duration', 0):.0f} 秒 |")
    lines.append(f"| 🌐 语言 | {report.get('language', 'zh')} |")
    lines.append("")

    # 互动数据（emoji 徽章行）
    if st:
        badges = []
        if st.get("like") and st["like"] != "-":
            badges.append(f"❤️ {st['like']}")
        if st.get("comment") and st["comment"] != "-":
            badges.append(f"💬 {st['comment']}")
        if st.get("collect") and st["collect"] != "-":
            badges.append(f"⭐ {st['collect']}")
        if st.get("share") and st["share"] != "-":
            badges.append(f"🔁 {st['share']}")
        if st.get("play") and st["play"] != "-":
            badges.append(f"▶️ {st['play']}")
        if badges:
            lines.append("### 📊 互动数据")
            lines.append("")
            lines.append("  ".join(badges))
            lines.append("")

        # 主播信息
        author_parts = []
        if st.get("nickname"):
            author_parts.append(f"**主播**: {st['nickname']}")
        for k, label in [("fans", "粉丝"), ("total_likes", "获赞"), ("works", "作品"), ("following", "关注")]:
            if st.get(k) and st[k] != "-":
                author_parts.append(f"**{label}**: {st[k]}")
        if author_parts:
            lines.append(f"🎥 {' | '.join(author_parts)}")
            lines.append("")

    # 一、视频总览
    if an.get("summary"):
        lines.append("## 一、视频总览")
        lines.append("")
        lines.append(f"> 💡 **一句话总结**: {an['summary']}")
        lines.append("")
        if an.get("scenes"):
            lines.append(f"🎯 **适合参考的场景**: {an['scenes']}")
            lines.append("")
        if an.get("structure"):
            lines.append(f"🏗 **核心结构**: {an['structure']}")
            lines.append("")

    # 二、值得学习
    if an.get("highlights"):
        lines.append("## 二、值得学习")
        lines.append("")
        lines.append("| ⭐ 值得学的点 | 原片怎么做的 | 仿写时怎么用 |")
        lines.append("|:---|:---|:---|")
        for h in an["highlights"]:
            lines.append(f"| {h.get('point', '')} | {h.get('how', '')} | {h.get('use', '')} |")
        lines.append("")

    # 三、复用建议
    if an.get("improvements"):
        lines.append("## 三、复用建议")
        lines.append("")
        lines.append("| 🔧 调整点 | 原片的问题 | 仿写时怎么改 |")
        lines.append("|:---|:---|:---|")
        for h in an["improvements"]:
            lines.append(f"| {h.get('point', '')} | {h.get('problem', '')} | {h.get('fix', '')} |")
        lines.append("")

    # 四、原内容（转写）
    lines.append("## 四、原内容（转写）")
    lines.append("")
    for s in report.get("original_segments", []):
        lines.append(f"- `[{fmt_ts(s['start'])}]` {s['text']}")
    lines.append("")

    # 五、润色改写（对照表）
    if report.get("rewritten_segments"):
        lines.append("## 五、润色改写")
        lines.append("")
        lines.append("| ⏱ 时间 | 原内容 | ✨ 润色改写 |")
        lines.append("|:---|:---|:---|")
        orig = report.get("original_segments", [])
        rw = report["rewritten_segments"]
        for i, s in enumerate(rw):
            ts = fmt_ts(s.get("start", 0))
            original = s.get("original", orig[i]["text"] if i < len(orig) else "")
            lines.append(f"| {ts} | {original} | {s.get('rewritten', '')} |")
        lines.append("")

    # 六、多版本仿写
    if report.get("versions"):
        lines.append("## 六、多版本仿写")
        lines.append("")
        for name, text in report["versions"].items():
            lines.append(f"### 📝 {name}")
            lines.append("")
            if isinstance(text, list):
                for h in text:
                    lines.append(f"- 🎯 {h}")
            else:
                lines.append(f"> {text}")
            lines.append("")

    # 七、复刻提示词
    if report.get("prompt"):
        lines.append("## 七、复刻提示词")
        lines.append("")
        lines.append("```")
        lines.append(report["prompt"])
        lines.append("```")
        lines.append("")

    # 八、画面分析
    if report.get("vision"):
        lines.append("## 八、画面分析")
        lines.append("")
        for fr in report["vision"]:
            t = fr.get("time", 0)
            analysis = fr.get("analysis", "")
            lines.append(f"- **[{t}s]** {analysis}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
#  导出入口
# ============================================================

def export(video_id, fmt):
    """导出单个视频为指定格式（md / xlsx）"""
    report = _report_or_raise(video_id)
    safe_title = "".join(c for c in report["title"] if c not in '\\/:*?"<>|')[:40] or video_id
    if fmt == "md":
        path = os.path.join(EXPORT_DIR, f"{video_id}_{safe_title}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(to_markdown(report))
    elif fmt == "xlsx":
        path = os.path.join(EXPORT_DIR, f"{video_id}_{safe_title}.xlsx")
        to_excel(report, path)
    else:
        raise ValueError(f"未知格式: {fmt}（仅支持 md/xlsx）")
    return path


def _batch_xlsx(reports, path):
    """批量导出 Excel：封面汇总表 + 每视频完整 sheet"""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # ===== Sheet1: 汇总对比表 =====
    ws = wb.active
    ws.title = "📊 视频汇总"

    # 封面行
    ws.merge_cells("A1:N1")
    c = ws.cell(row=1, column=1, value=f"📊 抖音视频批量分析报告（{len(reports)} 个视频）")
    _apply_font(c, size=16, bold=True, color="FFFFFF")
    _apply_fill(c, _CLR_BG_COVER)
    _apply_align(c, h="center", v="center")
    ws.row_dimensions[1].height = 45
    for col in range(1, 15):
        _apply_fill(ws.cell(row=1, column=col), _CLR_BG_COVER)

    # 生成时间
    ws.merge_cells("A2:N2")
    c = ws.cell(row=2, column=1, value=f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    _apply_font(c, size=10, color="FFFFFF")
    _apply_fill(c, "3B5FDB")
    _apply_align(c, h="center", v="center")
    for col in range(1, 15):
        _apply_fill(ws.cell(row=2, column=col), "3B5FDB")

    # 表头
    headers = ["序号", "标题", "链接", "时长(s)", "❤️赞", "💬评", "⭐藏", "🔁转",
               "▶️播", "主播", "粉丝", "获赞", "作品", "💡一句话总结"]
    for c_idx, h in enumerate(headers, 1):
        ws.cell(row=3, column=c_idx, value=h)
    _style_header_row(ws, 3, 14)

    # 数据行
    for i, r in enumerate(reports, 1):
        st = r.get("stats") or {}
        an = r.get("analysis") or {}
        row = [
            i, r.get("title", ""), r.get("url", ""), round(r.get("duration", 0)),
            st.get("like", "-"), st.get("comment", "-"), st.get("collect", "-"),
            st.get("share", "-"), st.get("play", "-"),
            st.get("nickname") or st.get("channel_name", ""),
            st.get("fans", "-"), st.get("total_likes", "-"), st.get("works", "-"),
            an.get("summary", ""),
        ]
        for c_idx, v in enumerate(row, 1):
            cell = ws.cell(row=i + 3, column=c_idx, value=v)
        _auto_row_height(ws, i + 3, 14, chars_per_line=25)
    _style_data_rows(ws, 4, len(reports) + 3, 14)

    widths = [6, 35, 28, 8, 8, 8, 8, 8, 8, 14, 10, 10, 8, 45]
    _set_col_widths(ws, widths)
    ws.freeze_panes = "A4"
    # 自动筛选（表头 A3:N3，数据 4..len+3）
    if len(reports) > 0:
        ws.auto_filter.ref = f"A3:N{len(reports) + 3}"

    # ===== 每视频一个完整 sheet =====
    for i, r in enumerate(reports, 1):
        sname = f"视频{i}"
        ws = wb.create_sheet(sname)
        st = r.get("stats") or {}
        an = r.get("analysis") or {}

        # 小封面
        ws.merge_cells("A1:D1")
        c = ws.cell(row=1, column=1, value=f"🎬 {r.get('title', f'视频{i}')}")
        _apply_font(c, size=14, bold=True, color="FFFFFF")
        _apply_fill(c, _CLR_BG_COVER)
        _apply_align(c, h="center", v="center")
        ws.row_dimensions[1].height = 38
        for col in range(1, 5):
            _apply_fill(ws.cell(row=1, column=col), _CLR_BG_COVER)

        # 信息区
        row = 3
        info = [
            ("🔗 链接", r.get("url", "")),
            ("⏱ 时长", f"{round(r.get('duration', 0))} 秒"),
            ("❤️ 点赞", st.get("like", "-")),
            ("💬 评论", st.get("comment", "-")),
            ("⭐ 收藏", st.get("collect", "-")),
            ("🔁 转发", st.get("share", "-")),
            ("🎥 主播", st.get("nickname") or st.get("channel_name", "-")),
            ("👥 粉丝", st.get("fans", "-")),
            ("💡 总结", an.get("summary", "")),
        ]
        for k, v in info:
            _apply_font(ws.cell(row=row, column=1), size=10, bold=True, color=_CLR_PRIMARY)
            _apply_fill(ws.cell(row=row, column=1), _CLR_BG_SECTION)
            _apply_border(ws.cell(row=row, column=1))
            ws.cell(row=row, column=1, value=k)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
            c = ws.cell(row=row, column=2, value=v)
            _apply_font(c, size=10)
            _apply_align(c)
            for cc in range(1, 5):
                _apply_border(ws.cell(row=row, column=cc))
            ws.row_dimensions[row].height = max(22, 18 * (len(str(v)) // 40 + 1))
            row += 1

        # 画面分析
        vision = r.get("vision") or []
        if vision:
            row += 1
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
            _apply_font(ws.cell(row=row, column=1), size=12, bold=True, color=_CLR_PURPLE)
            ws.cell(row=row, column=1, value="🎬 画面分析")
            row += 1
            for fr in vision:
                ws.cell(row=row, column=1, value=f"[{fr.get('time', 0)}s]")
                _apply_font(ws.cell(row=row, column=1), size=10, bold=True, color=_CLR_PURPLE)
                _apply_align(ws.cell(row=row, column=1), h="center", v="center")
                ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
                c = ws.cell(row=row, column=2, value=fr.get("analysis", ""))
                _apply_font(c, size=10)
                _apply_align(c)
                row += 1

        # 原版 + 改写对照
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        _apply_font(ws.cell(row=row, column=1), size=12, bold=True, color=_CLR_GREEN)
        ws.cell(row=row, column=1, value="📄 原版与润色改写对照")
        row += 1
        hdrs = ["⏱ 时间", "原版转写", "✨ 润色改写"]
        for c_idx, h in enumerate(hdrs, 1):
            ws.cell(row=row, column=c_idx, value=h)
        _style_header_row(ws, row, 3)
        row += 1
        orig = r.get("original_segments", [])
        rw = r.get("rewritten_segments") or []
        for j, s in enumerate(orig):
            ts = f"{fmt_ts(s['start'])} - {fmt_ts(s['end'])}"
            ws.cell(row=row, column=1, value=ts)
            _apply_font(ws.cell(row=row, column=1), size=9, bold=True, color=_CLR_PRIMARY)
            _apply_align(ws.cell(row=row, column=1), h="center", v="center")
            ws.cell(row=row, column=2, value=s["text"])
            if j < len(rw):
                ws.cell(row=row, column=3, value=rw[j]["rewritten"])
            _auto_row_height(ws, row, 3)
            row += 1

        # 多版本仿写（色块）
        versions = r.get("versions") or {}
        if versions:
            row += 1
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
            _apply_font(ws.cell(row=row, column=1), size=12, bold=True, color=_CLR_PURPLE)
            ws.cell(row=row, column=1, value="🎭 多版本仿写")
            row += 1
            for name, text in versions.items():
                title_clr, bg_clr = _VERSION_COLORS.get(name, (_CLR_PURPLE, "F3E8FF"))
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
                c = ws.cell(row=row, column=1, value=f"📝 {name}")
                _apply_font(c, size=11, bold=True, color="FFFFFF")
                _apply_fill(c, title_clr)
                for cc in range(1, 5):
                    _apply_fill(ws.cell(row=row, column=cc), title_clr)
                row += 1

                content = "\n".join(text) if isinstance(text, list) else str(text)
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
                c = ws.cell(row=row, column=1, value=content)
                _apply_font(c, size=10)
                _apply_fill(c, bg_clr)
                _apply_align(c)
                ws.row_dimensions[row].height = max(50, 15 * (len(content) // 50 + 1))
                for cc in range(1, 5):
                    _apply_fill(ws.cell(row=row, column=cc), bg_clr)
                row += 1

        # 复刻提示词
        if r.get("prompt"):
            row += 1
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
            _apply_font(ws.cell(row=row, column=1), size=12, bold=True, color=_CLR_BG_HEADER)
            ws.cell(row=row, column=1, value="🤖 复刻提示词")
            row += 1
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
            c = ws.cell(row=row, column=1, value=r["prompt"])
            _apply_font(c, size=10, color="E8E8E8")
            _apply_fill(c, "1F2329")
            _apply_align(c)
            ws.row_dimensions[row].height = max(80, 15 * (len(r["prompt"]) // 60 + 1))

        _set_col_widths(ws, [14, 45, 45, 14])

    wb.save(path)


def _batch_md(reports, path):
    """批量导出 Markdown：封面 + 目录 + 每视频一章"""
    parts = []

    # 封面页
    parts.append(f"# 📊 抖音视频批量分析报告")
    parts.append("")
    parts.append(f"> 共 **{len(reports)}** 个视频  |  生成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    parts.append("")

    # 目录
    parts.append("## 📋 目录")
    parts.append("")
    for i, r in enumerate(reports, 1):
        title = r.get("title", f"视频{i}")
        parts.append(f"{i}. [{title}](#{r.get('video_id', f'video-{i}')})")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 每视频一章
    for i, r in enumerate(reports, 1):
        parts.append(f"<a id=\"{r.get('video_id', f'video-{i}')}\"></a>")
        parts.append("")
        parts.append(f"# 第 {i} 章: {r.get('title', '视频')}")
        parts.append("")
        parts.append(to_markdown(r))
        parts.append("")
        parts.append("---")
        parts.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def export_batch(video_ids, fmt):
    """批量导出多个视频为一个文件"""
    reports = []
    for v in video_ids:
        try:
            reports.append(_report_or_raise(v))
        except FileNotFoundError:
            continue
    if not reports:
        raise ValueError("没有可导出的报告")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if fmt == "md":
        path = os.path.join(EXPORT_DIR, f"批量导出_{len(reports)}个视频_{stamp}.md")
        _batch_md(reports, path)
    elif fmt == "xlsx":
        path = os.path.join(EXPORT_DIR, f"批量导出_{len(reports)}个视频_{stamp}.xlsx")
        _batch_xlsx(reports, path)
    else:
        raise ValueError(f"批量导出仅支持 md/xlsx: {fmt}")
    return path
