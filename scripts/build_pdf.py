#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a Chinese PDF from a translated Markdown file.

Usage:
    python build_pdf.py <translated.md> [output.pdf]

Features:
    - Auto-detects a system Chinese font (Microsoft YaHei / SimHei / SimSun)
    - Supports headings (#, ##, ###), paragraphs, bullet/numbered lists,
      horizontal rules, and basic inline markup (**bold**, *italic*, `code`)
    - Adds page numbers in the footer
    - Left margin is used for the page-number footer

Requires reportlab. Errors are reported with a non-zero exit code.
"""

import io
import os
import re
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable,
        ListFlowable,
        Paragraph,
        SimpleDocTemplate,
        Table as RLTable,
        TableStyle,
    )
except ImportError:
    print("ERROR: reportlab is not installed. Run: pip install reportlab")
    sys.exit(1)

FONT_CANDIDATES = [
    ("Microsoft YaHei", os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts\msyh.ttc"),
    ("Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttc"),
    ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
    ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
    ("Noto Sans CJK SC", r"C:\Windows\Fonts\msyh.ttc"),
]

PAGE_W, PAGE_H = A4


def pick_font():
    for name, path in FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                pdfmetrics.registerFontFamily(name, normal=name, bold=name,
                                              italic=name, boldItalic=name)
                return name
            except Exception:
                continue
    return None


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(md_text):
    text = esc(md_text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    return text


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HORIZ_RULE_RE = re.compile(r"^\s*(---+|\*\*\*+)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
NUMBER_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
TABLE_MARKER_RE = re.compile(r"^【表格[^】]*】\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|:-]*\|?\s*$")


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_pdf.py <translated.md> [output.pdf]")
        return 1

    md_path = sys.argv[1]
    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
    else:
        out_path = os.path.splitext(md_path)[0] + ".pdf"

    if not os.path.isfile(md_path):
        print("ERROR: file not found: %s" % md_path)
        return 1

    font_name = pick_font()
    if font_name is None:
        print("ERROR: no Chinese font found. Install one of: 微软雅黑/黑体/宋体")
        return 1
    print("Using font: %s" % font_name)

    styles = {
        "h1": ParagraphStyle("h1", fontName=font_name, fontSize=18, leading=26,
                             spaceAfter=10, spaceBefore=6),
        "h2": ParagraphStyle("h2", fontName=font_name, fontSize=15, leading=22,
                             spaceAfter=8, spaceBefore=4),
        "h3": ParagraphStyle("h3", fontName=font_name, fontSize=13, leading=19,
                             spaceAfter=6, spaceBefore=2),
        "body": ParagraphStyle("body", fontName=font_name, fontSize=11, leading=17,
                               firstLineIndent=22, spaceAfter=6, alignment=TA_LEFT),
        "list": ParagraphStyle("list", fontName=font_name, fontSize=11, leading=17,
                               spaceAfter=3, alignment=TA_LEFT),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=9, leading=13,
                               backColor=colors.lightgrey, leftIndent=12,
                               rightIndent=12, spaceAfter=6, spaceBefore=2),
        "cell": ParagraphStyle("cell", fontName=font_name, fontSize=9, leading=13,
                               alignment=TA_LEFT),
        "caption": ParagraphStyle("caption", fontName=font_name, fontSize=9,
                                  leading=12, spaceBefore=6, spaceAfter=2,
                                  textColor=colors.grey),
    }

    def render_table(rows):
        """rows: list of list-of-cell-text; first row is the header."""
        ncols = max(len(r) for r in rows)
        data = [r + [""] * (ncols - len(r)) for r in rows]
        cells = [[Paragraph(esc(c), styles["cell"]) for c in row] for row in data]
        tbl = RLTable(cells, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return tbl

    with io.open(md_path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    lines = raw.splitlines()
    flowables = []
    i = 0
    n = len(lines)
    in_code = False
    code_buf = []

    while i < n:
        line = lines[i]

        if line.strip().startswith("```"):
            if in_code:
                flowables.append(Paragraph("<br/>".join(esc(l) for l in code_buf),
                                           styles["code"]))
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        m = HEADING_RE.match(line)
        if m:
            level = min(len(m.group(1)), 3)
            flowables.append(Paragraph(inline(m.group(2).strip()),
                                       styles["h%d" % level]))
            i += 1
            continue

        if HORIZ_RULE_RE.match(line):
            flowables.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.grey, spaceAfter=8))
            i += 1
            continue

        # Markdown table block: optional 【表格 / Table】 caption + | rows
        if TABLE_MARKER_RE.match(line.strip()) or TABLE_ROW_RE.match(line):
            caption = None
            if TABLE_MARKER_RE.match(line.strip()):
                caption = line.strip()
                i += 1
            rows = []
            while i < n and TABLE_ROW_RE.match(lines[i]):
                rows.append(lines[i].strip())
                i += 1
            if len(rows) >= 2:
                body = []
                for r in rows:
                    cells = [c.strip() for c in r.strip().strip("|").split("|")]
                    if cells and all(re.match(r"^\s*:?-{2,}:?\s*$", c) or c == "" for c in cells):
                        continue  # header separator row
                    body.append(cells)
                if len(body) >= 2:
                    if caption:
                        flowables.append(Paragraph(inline(caption), styles["caption"]))
                    flowables.append(render_table(body))
                    continue
            if caption:
                flowables.append(Paragraph(inline(caption), styles["body"]))
                continue

        b = BULLET_RE.match(line)
        num = NUMBER_RE.match(line)
        if b or num:
            items = []
            start = 1
            while i < n and (BULLET_RE.match(lines[i]) or NUMBER_RE.match(lines[i])):
                bm = BULLET_RE.match(lines[i])
                nm = NUMBER_RE.match(lines[i])
                if nm:
                    start = int(nm.group(1))
                items.append(Paragraph(inline((bm or nm).group(1).strip()),
                                       styles["list"]))
                i += 1
            flowables.append(ListFlowable(
                items, bulletType="bullet" if b else "1",
                start=start, leftIndent=18, spaceAfter=6))
            continue

        para = []
        while i < n and lines[i].strip() and not HEADING_RE.match(lines[i]) \
                and not HORIZ_RULE_RE.match(lines[i]) \
                and not BULLET_RE.match(lines[i]) and not NUMBER_RE.match(lines[i]) \
                and not lines[i].strip().startswith("```") \
                and not TABLE_ROW_RE.match(lines[i]) \
                and not TABLE_MARKER_RE.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if para:
            flowables.append(Paragraph(inline(" ".join(para)), styles["body"]))

    out_path_real = sys.argv[2] if len(sys.argv) > 2 else out_path
    doc = SimpleDocTemplate(
        out_path_real,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
    )

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(font_name, 9)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(PAGE_W / 2.0, 12 * mm,
                                 "第 %d 页" % doc_obj.page)
        canvas.restoreState()

    doc.build(flowables, onFirstPage=footer, onLaterPages=footer)
    print("OK -> %s" % out_path_real)
    return 0


if __name__ == "__main__":
    sys.exit(main())
