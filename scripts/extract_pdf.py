#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract text from a PDF file, page by page, with page markers.

Usage:
    python extract_pdf.py <input.pdf> [output.txt] [--keep-header-footer]

Features:
    - Outputs UTF-8 text with per-page markers: 【第 N 页 / Page N】
    - Auto-removes repeated running headers/footers and bare page numbers
      (use --keep-header-footer to disable).
    - Detects tables and emits them as Markdown tables marked with
      【表格 / Table】, so table content is not lost during translation.
      Uses PyMuPDF's native table detection when available (>=1.23.8) and
      falls back to a grid-layout heuristic on older versions.
    - Detects image-only (scanned) PDFs and warns when little text is found.
    - Extracts text in block reading order (top-to-bottom, left-to-right).

Requires PyMuPDF (fitz). Errors are reported with a non-zero exit code.
"""

import argparse
import io
import os
import re
import sys

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    fitz = None
    HAS_FITZ = False

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TABLE_MARKER = "【表格 / Table】"


def _norm(line):
    """Normalize a line for header/footer matching (strip digits/space/punct)."""
    return re.sub(r"[\d\s\u2010-\u2015\u00a0\u3000]+", "", line).strip().lower()


def _is_page_number(text):
    """Recognize bare page numbers and common 'Page N' footer forms."""
    stripped = re.sub(r"[\s\u2010-\u2015\u00a0\u3000.\-()·]+", "", text)
    if stripped.isdigit():
        return True
    if stripped.lower() in ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"):
        return True
    m = re.match(r"^(?:p(?:age)?|pp?\.?|第)?\s*[-\u2010-\u2015.]?\s*(\d+)\s*[-\u2010-\u2015.]?$", text.strip(), re.IGNORECASE)
    return bool(m)


# ---------------------------------------------------------------------------
# Table detection
# ---------------------------------------------------------------------------

def _cell_to_str(cell):
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell)).strip()


def _table_to_markdown(data):
    """Convert a 2D list of cell values to a Markdown table string (or None)."""
    if not data:
        return None
    rows = []
    ncols = 0
    for r in data:
        cells = [_cell_to_str(c) for c in r]
        ncols = max(ncols, len(cells))
        rows.append(cells)
    if ncols < 2 or len(rows) < 2:
        return None
    header = rows[0] + [""] * (ncols - len(rows[0]))
    lines = [TABLE_MARKER]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * ncols)
    for r in rows[1:]:
        cells = r + [""] * (ncols - len(r))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _tables_from_find(page):
    """Table detection via PyMuPDF's native find_tables (>= 1.23.8)."""
    tables = []
    try:
        found = page.find_tables()
    except Exception:
        return tables
    try:
        items = found.tables
    except Exception:
        return tables
    for t in items:
        try:
            data = t.extract()
            md = _table_to_markdown(data)
        except Exception:
            md = None
        if md:
            try:
                bbox = fitz.Rect(t.bbox)
            except Exception:
                bbox = None
            if bbox is not None:
                tables.append((bbox, md))
    return tables


def _tables_heuristic(page, blocks, page_h):
    """Fallback table detection for PyMuPDF < 1.23.8.

    Uses word coordinates: groups words into text lines, splits each line into
    cells by horizontal gaps, then groups consecutive lines into tables when
    their column boundaries align. This survives PyMuPDF merging a table row
    into a single text block (cells separated by newlines).
    """
    words = page.get_text("words")
    if not words:
        return []

    # 1) cluster words into visual lines by strong y-overlap
    lines = []  # each: [y0, y1, [word tuples]]
    for w in words:
        x0, y0, x1, y1, txt = w[0], w[1], w[2], w[3], w[4]
        if not txt.strip():
            continue
        placed = False
        for ln in lines:
            if min(ln[1], y1) - max(ln[0], y0) >= 0.5 * min(ln[1] - ln[0], y1 - y0):
                ln[0] = min(ln[0], y0)
                ln[1] = max(ln[1], y1)
                ln[2].append(w)
                placed = True
                break
        if not placed:
            lines.append([y0, y1, [w]])

    # 2) split each line into cells by horizontal gaps (>=5pt)
    table_rows = []  # list of (y0, [cell (x0, x1, text)])
    GAP = 5.0
    for y0, y1, ws in lines:
        if y0 >= 0.9 * page_h or y1 <= 0.1 * page_h:
            continue
        ws.sort(key=lambda w: w[0])
        cells = []
        cur = None
        for w in ws:
            x0, x1, txt = w[0], w[2], w[4]
            if cur is None:
                cur = [x0, x1, txt]
            elif x0 - cur[1] >= GAP:
                cells.append(tuple(cur))
                cur = [x0, x1, txt]
            else:
                cur[1] = x1
                cur[2] += " " + txt
        if cur:
            cells.append(tuple(cur))
        if len(cells) >= 2:
            table_rows.append((y0, cells))

    # 3) group consecutive rows into tables when column x0s align (<=3pt)
    tables = []
    current = []

    def close():
        if len(current) >= 2:
            tables.append(current)

    for y0, cells in table_rows:
        if not current:
            current = [(y0, cells)]
            continue
        ref_cols = [c[0] for c in current[0][1]]
        cols = [c[0] for c in cells]
        if len(cols) == len(ref_cols) and len(cols) >= 2 and \
                max(abs(a - b) for a, b in zip(cols, ref_cols)) <= 3:
            current.append((y0, cells))
        else:
            close()
            current = [(y0, cells)]
    close()

    out = []
    for trows in tables:
        data = [[c[2] for c in row[1]] for row in trows]
        md = _table_to_markdown(data)
        if not md:
            continue
        xs0 = min(c[0] for row in trows for c in row[1])
        ys0 = min(r[0] for r in trows)
        xs1 = max(c[1] for row in trows for c in row[1])
        ys1 = max(r[0] + 10 for r in trows)  # approximate row bottom
        out.append((fitz.Rect(xs0, ys0, xs1, ys1), md))
    return out


def _detect_tables(page, blocks):
    """Return list of (bbox, markdown) for tables on a page."""
    page_h = page.rect.height
    if hasattr(page, "find_tables"):
        try:
            found = _tables_from_find(page)
            if found:
                return found
        except Exception:
            pass
    try:
        return _tables_heuristic(page, blocks, page_h)
    except Exception:
        return []


def _overlaps_any(block, bboxes):
    """True if >50% of the block's area sits inside any table bbox."""
    if not bboxes:
        return False
    x0, y0, x1, y1, _ = block
    area = (x1 - x0) * (y1 - y0)
    if area <= 0:
        return False
    r = fitz.Rect(x0, y0, x1, y1)
    for tb in bboxes:
        inter = r & tb
        if not inter.is_empty and inter.get_area() >= 0.5 * area:
            return True
    return False


def extract(pdf_path, out_path, clean=True):
    if not HAS_FITZ:
        print("ERROR: PyMuPDF is not installed. Run: pip install PyMuPDF")
        return 1

    if not os.path.isfile(pdf_path):
        print("ERROR: file not found: %s" % pdf_path)
        return 1

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        print("ERROR: cannot open PDF: %s" % exc)
        return 1

    if doc.needs_pass:
        print("ERROR: PDF is password-protected. Decrypt it first, then retry.")
        doc.close()
        return 1

    page_count = doc.page_count

    per_page = []            # list of (page_idx, blocks)
    header_zone_blocks = []  # list of (page_idx, norm, text)
    footer_zone_blocks = []

    for pno in range(page_count):
        page = doc[pno]
        raw_blocks = page.get_text("blocks")
        blocks = [(b[0], b[1], b[2], b[3], b[4]) for b in raw_blocks if b[6] == 0]

        tables = _detect_tables(page, blocks)
        table_bboxes = [t[0] for t in tables]

        kept = [blk for blk in blocks if not _overlaps_any(blk, table_bboxes)]
        table_blks = [(tb[0].x0, tb[0].y0, tb[0].x1, tb[0].y1, tb[1]) for tb in tables]
        merged_blocks = kept + table_blks
        merged_blocks.sort(key=lambda b: (round(b[1] / 8.0), b[0]))

        per_page.append(merged_blocks)
        for x0, y0, x1, y1, text in merged_blocks:
            t = text.strip()
            if not t:
                continue
            if y1 <= 0.08 * page.rect.height:
                header_zone_blocks.append((pno, _norm(t), t))
            elif y0 >= 0.92 * page.rect.height:
                footer_zone_blocks.append((pno, _norm(t), t))

    # --- Decide which repeated header/footer texts to drop ---
    drop_norms = set()

    def classify(zones, min_occur=2):
        counts = {}
        for _, norm, _t in zones:
            counts[norm] = counts.get(norm, 0) + 1
        for norm, c in counts.items():
            if c >= min_occur and c >= 0.4 * page_count:
                drop_norms.add(norm)

    if clean and page_count >= 2:
        classify(header_zone_blocks)
        classify(footer_zone_blocks)

    # --- Write output ---
    total_chars = 0
    out_lines = []
    dropped = 0
    for pno, blocks in enumerate(per_page, start=1):
        page_h = doc[pno - 1].rect.height
        out_lines.append("【第 %d 页 / Page %d】" % (pno, pno))
        out_lines.append("=" * 60)
        for x0, y0, x1, y1, text in blocks:
            t = text.strip()
            if not t:
                continue
            norm = _norm(t)
            in_header_zone = y1 <= 0.08 * page_h
            in_footer_zone = y0 >= 0.92 * page_h
            if clean and (norm in drop_norms or (_is_page_number(t) and (in_header_zone or in_footer_zone))):
                dropped += 1
                continue
            out_lines.append(t)
            total_chars += len(t)
        out_lines.append("")

    with io.open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines))

    doc.close()

    print("Pages: %d" % page_count)
    print("Extracted chars: %d" % total_chars)
    print("Dropped header/footer blocks: %d" % dropped)
    print("Output: %s" % out_path)

    if page_count > 0 and total_chars < max(50 * page_count, 100):
        print("WARNING: very little text extracted. This PDF may be a scanned "
              "image-only document. OCR is out of scope for this skill.")
    else:
        print("OK")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Extract text from a PDF page by page.")
    parser.add_argument("input_pdf", help="path to the input PDF")
    parser.add_argument("output_txt", nargs="?", help="output text path (default: <input>_extracted.txt)")
    parser.add_argument("--keep-header-footer", action="store_true",
                        help="keep repeated page headers/footers and page numbers")
    args = parser.parse_args()

    out_path = args.output_txt or (
        os.path.splitext(args.input_pdf)[0] + "_extracted.txt"
    )
    return extract(args.input_pdf, out_path, clean=not args.keep_header_footer)


if __name__ == "__main__":
    sys.exit(main())
