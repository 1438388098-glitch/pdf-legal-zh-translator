#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a Chinese PDF from a translated Markdown file.

Usage:
    python build_pdf.py <translated.md> [output.pdf] [--new-page REGEX] [--no-toc]

Features:
    - Auto-detects a system Chinese font (Microsoft YaHei / SimHei / SimSun)
    - Supports headings (#, ##, ###, ####), paragraphs, block quotes,
      bullet/numbered lists, horizontal rules, Markdown tables, and basic
      inline markup (**bold**, *italic*, `code`)
    - Generates a table of contents (multi-pass) from h1/h2 headings
    - Starts a new page before headings that match --new-page
      (defaults to common chapter/part/front/back-matter markers)
    - Tables render with fitted column widths, a shaded header row, and
      alternating row shading
    - Page numbers in the footer

Requires reportlab. Errors are reported with a non-zero exit code.
"""

import argparse
import io
import os
import re
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable,
        ListFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table as RLTable,
        TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
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
LEFT_M = RIGHT_M = 25 * mm
TOP_M = 25 * mm
BOTTOM_M = 25 * mm
FRAME_W = PAGE_W - LEFT_M - RIGHT_M

# Headings that should start on a new page (chapter / part / front / back matter).
DEFAULT_NEW_PAGE = (
    r"^(第[一二三四五六七八九十百千\d]+[章节部篇]"
    r"|附录|Appendices|绪论|Introduction|目录|Contents"
    r"|序言|前言|Preface|索引|Index|Glossary|词汇表"
    r"|结语|Conclusion|后记|Afterword"
    r"|Part\s+[IVX\d]+|Chapter\s+\d+)"
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HORIZ_RULE_RE = re.compile(r"^\s*(---+|\*\*\*+)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
NUMBER_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
TABLE_MARKER_RE = re.compile(r"^【表格[^】]*】\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|:-]*\|?\s*$")


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


def make_styles(font_name):
    body_font = font_name
    return {
        "h1": ParagraphStyle("h1", fontName=body_font, fontSize=20, leading=28,
                             textColor=colors.HexColor("#1a1a2e"),
                             spaceBefore=4, spaceAfter=12, keepWithNext=1),
        "h2": ParagraphStyle("h2", fontName=body_font, fontSize=16, leading=24,
                             textColor=colors.HexColor("#1a1a2e"),
                             spaceBefore=14, spaceAfter=8, keepWithNext=1),
        "h3": ParagraphStyle("h3", fontName=body_font, fontSize=13.5, leading=20,
                             spaceBefore=10, spaceAfter=6, keepWithNext=1),
        "h4": ParagraphStyle("h4", fontName=body_font, fontSize=12, leading=18,
                             spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "body": ParagraphStyle("body", fontName=body_font, fontSize=11, leading=19,
                               firstLineIndent=22, spaceAfter=8, alignment=TA_JUSTIFY),
        "quote": ParagraphStyle("quote", fontName=body_font, fontSize=10.5, leading=17,
                                leftIndent=20, rightIndent=16,
                                textColor=colors.HexColor("#333333"),
                                spaceBefore=6, spaceAfter=8, alignment=TA_LEFT),
        "list": ParagraphStyle("list", fontName=body_font, fontSize=11, leading=18,
                               leftIndent=18, spaceAfter=3, alignment=TA_LEFT),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=9, leading=13,
                               backColor=colors.HexColor("#f3f3f3"), leftIndent=12,
                               rightIndent=12, spaceAfter=8, spaceBefore=4),
        "cell": ParagraphStyle("cell", fontName=body_font, fontSize=9, leading=13,
                               alignment=TA_LEFT),
        "caption": ParagraphStyle("caption", fontName=body_font, fontSize=9,
                                  leading=12, spaceBefore=6, spaceAfter=3,
                                  textColor=colors.grey),
        "toc0": ParagraphStyle("toc0", fontName=body_font, fontSize=12, leading=22,
                               leftIndent=0, spaceBefore=4, spaceAfter=2),
        "toc1": ParagraphStyle("toc1", fontName=body_font, fontSize=10.5, leading=18,
                               leftIndent=18, spaceAfter=1),
    }


def render_table(rows, styles):
    ncols = max(len(r) for r in rows)
    data = [r + [""] * (ncols - len(r)) for r in rows]
    cells = [[Paragraph(esc(c), styles["cell"]) for c in row] for row in data]
    col_w = FRAME_W / float(ncols)
    tbl = RLTable(cells, colWidths=[col_w] * ncols, hAlign="LEFT", repeatRows=1)
    table_style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#666666")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    # alternating row shading
    for r in range(2, len(data)):
        if r % 2 == 0:
            table_style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f7f9fc")))
    tbl.setStyle(TableStyle(table_style))
    return tbl


class TocDocTemplate(SimpleDocTemplate):
    """Records heading page numbers for the table of contents."""

    def __init__(self, *args, **kwargs):
        SimpleDocTemplate.__init__(self, *args, **kwargs)
        self._headings = []
        self._toc_enabled = True

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name.startswith("h"):
            name = flowable.style.name  # h1..h4
            try:
                level = int(name[1]) - 1  # TOC levels are 0-based
            except ValueError:
                return
            text = flowable.getPlainText()
            self._headings.append((level, text, self.page))
            if self._toc_enabled:
                self.notify("TOCEntry", (level, text, self.page))


def parse_md(md_path, styles, new_page_re):
    flowables = []
    with io.open(md_path, "r", encoding="utf-8-sig") as fh:
        raw = fh.read()
    lines = raw.splitlines()
    n = len(lines)
    i = 0
    in_code = False
    code_buf = []
    pending_new_page = False

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
            if new_page_re and re.match(new_page_re, m.group(2).strip()):
                if flowables:
                    flowables.append(PageBreak())
            level = min(len(m.group(1)), 4)
            flowables.append(Paragraph(inline(m.group(2).strip()),
                                       styles["h%d" % level]))
            i += 1
            continue

        if HORIZ_RULE_RE.match(line):
            flowables.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.grey, spaceAfter=10))
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
                    flowables.append(render_table(body, styles))
                    continue
            if caption:
                flowables.append(Paragraph(inline(caption), styles["body"]))
                continue

        q = QUOTE_RE.match(line)
        if q and (q.group(1).strip() or (i + 1 < n and QUOTE_RE.match(lines[i + 1]))):
            quote_lines = []
            while i < n and QUOTE_RE.match(lines[i]):
                quote_lines.append(QUOTE_RE.match(lines[i]).group(1).strip())
                i += 1
            flowables.append(Paragraph(inline(" ".join(quote_lines)), styles["quote"]))
            continue

        b = BULLET_RE.match(line)
        num = NUMBER_RE.match(line)
        if b or num:
            is_numbered = bool(num)
            items = []
            start = 1
            while i < n and (BULLET_RE.match(lines[i]) or NUMBER_RE.match(lines[i])):
                bm = BULLET_RE.match(lines[i])
                nm = NUMBER_RE.match(lines[i])
                if nm:
                    start = int(nm.group(1))
                if nm:
                    item_text = nm.group(2).strip()
                    items.append(Paragraph(inline("%d. %s" % (start, item_text)),
                                           styles["list"]))
                    start += 1
                else:
                    item_text = (bm.group(1) if bm else "").strip()
                    items.append(Paragraph(inline(item_text), styles["list"]))
                i += 1
            if is_numbered:
                for it in items:
                    flowables.append(it)
            else:
                flowables.append(ListFlowable(
                    items, bulletType="bullet", leftIndent=18, spaceAfter=8))
            continue

        para = []
        while i < n and lines[i].strip() \
                and not HEADING_RE.match(lines[i]) \
                and not HORIZ_RULE_RE.match(lines[i]) \
                and not BULLET_RE.match(lines[i]) \
                and not NUMBER_RE.match(lines[i]) \
                and not QUOTE_RE.match(lines[i]) \
                and not lines[i].strip().startswith("```") \
                and not TABLE_ROW_RE.match(lines[i]) \
                and not TABLE_MARKER_RE.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if para:
            flowables.append(Paragraph(inline(" ".join(para)), styles["body"]))

    return flowables


def build_toc(styles, font_name, max_level=1):
    toc = TableOfContents()
    toc.dotsMinLevel = 0
    levels = []
    for lv in range(max_level + 1):
        base = "toc%d" % lv if lv <= 1 else "toc1"
        levels.append(ParagraphStyle("toc%dl" % lv, parent=styles[base],
                                     leftIndent=18 * lv))
    toc.levelStyles = levels
    return toc


def main():
    parser = argparse.ArgumentParser(description="Build a Chinese PDF from Markdown.")
    parser.add_argument("md_path", help="path to the translated Markdown")
    parser.add_argument("out_path", nargs="?", help="output PDF path")
    parser.add_argument("--new-page", default=DEFAULT_NEW_PAGE,
                        help="regex: headings matching start a new page (default: chapter/part markers)")
    parser.add_argument("--no-toc", action="store_true",
                        help="do not generate a table of contents")
    parser.add_argument("--toc-max-level", type=int, default=1,
                        help="deepest heading level to include in the TOC (0=h1..3=h4, default 1)")
    parser.add_argument("--toc-title", default="目录",
                        help="title of the table of contents page (default: 目录)")
    args = parser.parse_args()

    md_path = args.md_path
    out_path = args.out_path or (os.path.splitext(md_path)[0] + ".pdf")
    new_page_re = args.new_page
    if new_page_re == "0":
        new_page_re = None

    if not os.path.isfile(md_path):
        print("ERROR: file not found: %s" % md_path)
        return 1

    font_name = pick_font()
    if font_name is None:
        print("ERROR: no Chinese font found. Install one of: 微软雅黑/黑体/宋体")
        return 1
    print("Using font: %s" % font_name)

    styles = make_styles(font_name)
    story = parse_md(md_path, styles, new_page_re)

    if not args.no_toc:
        toc = build_toc(styles, font_name, max_level=args.toc_max_level)
        intro = [
            Paragraph(inline(args.toc_title), styles["h1"]),
            HRFlowable(width="100%", thickness=1, color=colors.grey, spaceAfter=10),
            toc,
            PageBreak(),
        ]
        story = intro + story

    doc = TocDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=LEFT_M,
        rightMargin=RIGHT_M,
        topMargin=TOP_M,
        bottomMargin=BOTTOM_M,
        title=os.path.splitext(os.path.basename(md_path))[0],
    )
    doc._toc_enabled = not args.no_toc

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.setLineWidth(0.5)
        canvas.line(LEFT_M, 15 * mm, PAGE_W - RIGHT_M, 15 * mm)
        canvas.setFont(font_name, 9)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(PAGE_W / 2.0, 11 * mm,
                                 "第 %d 页" % doc_obj.page)
        canvas.restoreState()

    doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)
    print("TOC entries: %d" % len(doc._headings))
    print("OK -> %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
