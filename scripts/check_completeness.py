#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Automated completeness check: source vs translated chunks.

Usage:
    python check_completeness.py <extracted.txt> <chunks_dir> [--min-ratio 0.25] [--max-ratio 1.6]

What it checks (deterministic, complements the human/agent review):
    1. Page coverage: the set of page markers found in each chunk_XXX_zh.md
       must equal the source pages that chunk was assigned (manifest.json).
    2. Length sanity: translated chunk length vs source chunk length. A
       translation shorter than --min-ratio (default 0.25) or longer than
       --max-ratio (default 1.6) of the source is flagged as suspicious
       (possible truncation or padding).
    3. Heading presence: if a source chunk has section headings but the
       translation contains no heading-like lines, it is flagged.

Exit code: 0 if no hard errors; 1 if any translated chunk is missing or any
page is not covered (missing/truncated translation).
"""

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split_chunks import PAGE_RE, HEADING_RE  # noqa: E402

# Loosened heading patterns for the *translated* (Chinese) text.
ZH_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"#{1,6}\s+.+"
    r"|第[一二三四五六七八九十百千\d]+[章节篇部分条款项目]?\s*[、．. ]?.{0,60}"
    r"|[一二三四五六七八九十]+[、.．]\s*.{0,60}"
    r"|[（(]?[A-Z]\)?\s*.{0,60}"
    r")\s*$"
)
RULE_RE = re.compile(r"^={10,}\s*$")

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _read_lines(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read().splitlines()


def _count_pages(lines):
    pages = set()
    for line in lines:
        m = PAGE_RE.match(line)
        if m:
            pages.add(int(m.group(1)))
    return pages


def _count_heading_lines(lines, pattern):
    n = 0
    for line in lines:
        if line.strip() and pattern.match(line):
            n += 1
    return n


def _source_chunk_text(path):
    lines = []
    for line in _read_lines(path):
        if PAGE_RE.match(line) or RULE_RE.match(line):
            continue
        if line.lstrip().startswith("<!--") or line.strip().startswith("【上下文"):
            continue
        lines.append(line)
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check translation completeness.")
    parser.add_argument("extracted_txt", help="output of extract_pdf.py")
    parser.add_argument("chunks_dir", help="directory with chunk files + manifest.json")
    parser.add_argument("--min-ratio", type=float, default=0.25, help="min zh/source length ratio (default: 0.25)")
    parser.add_argument("--max-ratio", type=float, default=1.6, help="max zh/source length ratio (default: 1.6)")
    args = parser.parse_args()

    if not os.path.isfile(args.extracted_txt):
        print("ERROR: extracted text not found: %s" % args.extracted_txt)
        return 1

    manifest_path = os.path.join(args.chunks_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("ERROR: manifest.json not found in %s" % args.chunks_dir)
        return 1

    with io.open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    src_pages = _count_pages(_read_lines(args.extracted_txt))
    if not src_pages:
        print("ERROR: no page markers found in %s" % args.extracted_txt)
        return 1

    errors = []
    warnings = []

    for chunk in manifest["chunks"]:
        idx = chunk["index"]
        base = os.path.splitext(chunk["file"])[0]
        zh_path = os.path.join(args.chunks_dir, base + "_zh.md")
        if not os.path.isfile(zh_path):
            errors.append("missing translation: %s_zh.md" % base)
            continue

        zh_lines = _read_lines(zh_path)
        zh_pages = _count_pages(zh_lines)

        p_start, p_end = chunk["pages"]  # [inclusive start, exclusive end]
        expect = set(range(p_start, p_end + 1))
        missing_pages = expect - zh_pages
        extra_pages = zh_pages - expect
        if missing_pages:
            errors.append("%s missing page markers for pages %s"
                          % (base, sorted(missing_pages)))
        if extra_pages:
            warnings.append("%s has unexpected page markers %s"
                            % (base, sorted(extra_pages)))

        src_text = _source_chunk_text(os.path.join(args.chunks_dir, chunk["file"]))
        zh_text = "".join(zh_lines)
        if src_text:
            ratio = len(zh_text) / float(len(src_text))
            if ratio < args.min_ratio:
                warnings.append("%s translation suspiciously short (ratio %.2f, min %.2f) "
                                "— possible truncation" % (base, ratio, args.min_ratio))
            elif ratio > args.max_ratio:
                warnings.append("%s translation longer than expected (ratio %.2f, max %.2f) "
                                "— possible padding" % (base, ratio, args.max_ratio))

        src_headings = len(chunk.get("headings", []))
        zh_headings = _count_heading_lines(zh_lines, ZH_HEADING_RE)
        if src_headings > 0 and zh_headings == 0:
            warnings.append("%s has %d source section headings but no heading-like lines "
                            "in the translation" % (base, src_headings))

    print("Source pages: %d (min %d – max %d)"
          % (len(src_pages), min(src_pages), max(src_pages)))
    print("Chunks checked: %d" % len(manifest["chunks"]))

    if warnings:
        print("Warnings (%d):" % len(warnings))
        for w in warnings:
            print("  WARNING: " + w)
    if errors:
        print("Errors (%d):" % len(errors))
        for e in errors:
            print("  ERROR: " + e)
        print("Result: FAIL — re-translate the flagged chunks, then re-run.")
        return 1

    print("Result: OK — all chunks cover their source pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
