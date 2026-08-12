#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Split an extracted-text file into balanced chunks for parallel translation.

Usage:
    python split_chunks.py <extracted.txt> [output_dir] [--pages N] [--max-chunks N]

Input format: the output of extract_pdf.py, containing page markers like
    【第 1 页 / Page 1】
    ============================================================

Strategy:
    - Detects likely section headings (ALL-CAPS lines, lines starting with
      "Article", "Section", "Chapter", "Part", "Title", "Annex", "Appendix",
      "§", "PART", numbered roman/arabic headings) to use as split points.
    - Groups pages into chunks of roughly N pages each (default 20), preferring
      to break at heading boundaries rather than in the middle of a section.
    - Writes chunk files `chunk_001.txt`, `chunk_002.txt`, ... into the output
      directory, plus a `manifest.json` describing page ranges and headings.

Output:
    <output_dir>/
        manifest.json
        chunk_001.txt
        chunk_002.txt
        ...
"""

import argparse
import io
import json
import os
import re
import sys

PAGE_RE = re.compile(r"^【第\s*(\d+)\s*页\s*/\s*Page\s*\d+】\s*$")
HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?:第[一二三四五六七八九十百千\d]+[章节篇部分条款项]?\s*[、．. ]?.{0,80})"
    r"|(?:[A-Z][A-Z0-9\s.,:;'()-]{8,})"
    r"|(?:Article\s+[IVXLC\d]+.*)"
    r"|(?:Section\s+\d+.*)"
    r"|(?:Chapter\s+\d+.*)"
    r"|(?:Part\s+[IVXLC\d]+.*)"
    r"|(?:Title\s+[IVXLC\d]+.*)"
    r"|(?:Annex\s+[IVXLC\d]+.*)"
    r"|(?:Appendix\s+[A-Z\d]+.*)"
    r"|(?:§\s*\d+.*)"
    r"|(?:[IVXLC]+\s*\..*)"
    r"|(?:\d+\.\d+\s+[A-Z].*)"
    r")\s*$"
)


def _read_pages(path):
    pages = []          # list of list-of-lines, one per page
    headings = {}       # page_index (0-based) -> [heading lines]
    current = None
    with io.open(path, "r", encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    for line in lines:
        m = PAGE_RE.match(line)
        if m:
            current = int(m.group(1)) - 1
            while len(pages) <= current:
                pages.append([])
            continue
        if current is None:
            continue
        if line.strip() == "=" * 60:
            continue
        if line.strip():
            pages[current].append(line)
            if HEADING_RE.match(line):
                headings.setdefault(current, []).append(line.strip())
    # trim trailing empty pages
    while pages and not pages[-1]:
        pages.pop()
    return pages, headings


def _tail(pages, p0, p1, max_chars=300):
    """Collect the last ~max_chars of non-empty body text in pages [p0, p1).

    Used to give the next chunk's translation agent continuity context.
    """
    lines = []
    for p in range(p0, p1):
        lines.extend(pages[p])
    tail = []
    total = 0
    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue
        tail.append(s)
        total += len(s)
        if total >= max_chars:
            break
    return list(reversed(tail))


def main():
    parser = argparse.ArgumentParser(description="Split extracted text into chunks.")
    parser.add_argument("extracted_txt", help="output of extract_pdf.py")
    parser.add_argument("output_dir", nargs="?", help="output directory (default: ./chunks)")
    parser.add_argument("--pages", type=int, default=20, help="target pages per chunk (default: 20)")
    parser.add_argument("--max-chunks", type=int, default=0, help="cap the number of chunks (0 = no cap)")
    args = parser.parse_args()

    if not os.path.isfile(args.extracted_txt):
        print("ERROR: file not found: %s" % args.extracted_txt)
        return 1

    pages, headings = _read_pages(args.extracted_txt)
    total_pages = len(pages)
    if total_pages == 0:
        print("ERROR: no text pages found in %s" % args.extracted_txt)
        return 1

    out_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.extracted_txt)), "chunks"
    )
    os.makedirs(out_dir, exist_ok=True)

    # Determine chunk boundaries.
    target = args.pages
    bounds = [0]
    while bounds[-1] < total_pages:
        nxt = min(bounds[-1] + target, total_pages)
        # Snap to the NEAREST heading-bearing page within the window.
        if nxt < total_pages:
            window = max(1, target // 3)
            best = None
            best_dist = None
            for p in range(max(0, nxt - window), min(nxt + window, total_pages)):
                if p in headings and p > bounds[-1]:
                    d = abs(p - nxt)
                    if best_dist is None or d < best_dist:
                        best, best_dist = p, d
            if best is not None:
                nxt = best
            if nxt == bounds[-1]:
                nxt = min(bounds[-1] + target, total_pages)
        bounds.append(nxt)

    if args.max_chunks and len(bounds) - 1 > args.max_chunks:
        step = (total_pages + args.max_chunks - 1) // args.max_chunks
        bounds = [min(i * step, total_pages) for i in range(args.max_chunks + 1)]
        bounds[-1] = total_pages
        bounds = sorted(set(bounds))

    chunks = []
    prev_tail = []  # tail lines of the previous chunk (context for the next)
    for ci in range(len(bounds) - 1):
        p0, p1 = bounds[ci], bounds[ci + 1]  # pages [p0, p1)
        chunk_lines = []
        chunk_headings = []
        if prev_tail:
            chunk_lines.append("<!-- CONTEXT: previous chunk tail (reference only, "
                               "DO NOT translate or output into the translation) -->")
            chunk_lines.append("【上下文 / Previous chunk tail】:")
            chunk_lines.extend(prev_tail)
            chunk_lines.append("<!-- END CONTEXT -->")
            chunk_lines.append("")
        for p in range(p0, p1):
            chunk_lines.append("【第 %d 页 / Page %d】" % (p + 1, p + 1))
            chunk_lines.append("=" * 60)
            chunk_lines.extend(pages[p])
            chunk_lines.append("")
            chunk_headings.extend(headings.get(p, []))
        prev_tail = _tail(pages, p0, p1)
        name = "chunk_%03d.txt" % (ci + 1)
        with io.open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(chunk_lines))
        chunks.append({
            "index": ci + 1,
            "file": name,
            "pages": [p0 + 1, p1],           # 1-based inclusive range start, exclusive end
            "headings": chunk_headings,
        })

    manifest = {
        "source": os.path.basename(args.extracted_txt),
        "total_pages": total_pages,
        "target_pages_per_chunk": target,
        "chunks": chunks,
    }
    with io.open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print("Total pages: %d" % total_pages)
    print("Chunks: %d" % len(chunks))
    for c in chunks:
        print("  chunk_%03d  pages %d-%d  headings: %d" % (
            c["index"], c["pages"][0], c["pages"][1], len(c["headings"])))
    print("Output dir: %s" % out_dir)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
