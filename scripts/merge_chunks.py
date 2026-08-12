#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Merge translated chunk files back into a single Markdown document.

Usage:
    python merge_chunks.py <chunks_dir> <output.md>

Input:
    <chunks_dir>/manifest.json  -- written by split_chunks.py
    <chunks_dir>/chunk_001_zh.md, chunk_002_zh.md, ...  -- agent-translated files
        (same basename as chunk_XXX.txt but with "_zh.md" suffix)

Behavior:
    - Concatenates translated chunks in manifest order.
    - Strips per-page markers (【第 N 页 / Page N】) and separator lines.
    - Strips split_chunks.py context blocks (<!-- ... --> and 【上下文 ...】).
    - Inserts a blank line between chunks.

Errors:
    - Reports any chunk whose _zh.md translation is missing.
"""

import argparse
import io
import json
import os
import re
import sys

PAGE_RE = re.compile(r"^【第\s*\d+\s*页\s*/\s*Page\s*\d+】\s*$")
RULE_RE = re.compile(r"^={10,}\s*$")

# Blank-page markers are legitimate and must survive the fragment filter.
BLANK_PAGE_MARKERS = {
    "本页有意留空", "本页有意留空。", "此页有意留空", "此页有意留空。",
    "本页有意留白", "本页有意留白。", "此页有意留白", "此页有意留白。",
    "本页有意留为空白（This page intentionally left blank）",
    "本页有意留为空白。", "本页留白。",
}


def _is_fragment_candidate(s):
    """Short-ish, non-numeric, non-structural line that might be a running-head
    piece (including italic-marked ones like '*美国总统：George Washington 至 ...*')."""
    if not s or len(s) < 2 or len(s) > 55:
        return False
    if s.startswith(("#", "|", ">", "=", "**", "【")):
        return False
    if re.search(r"\d", s):
        return False
    if s in BLANK_PAGE_MARKERS:
        return False
    if s.endswith(("。", "！", "？", "!", "?")):
        return False
    return True


def _is_junk_line(s, freq=0):
    """Running-head remnants that escaped extraction:
    bare page numbers, page-number-framed heads ("7 The Role of the Executive 7"),
    leading/trailing page numbers ("194 附录一", "立法制度  77"), and repeated
    short fragments (chapter running heads split across pages)."""
    if not s:
        return False
    if re.match(r"^\d{1,3}$", s):  # bare page number
        return True
    if re.match(r"^\d{1,4}\s+[^\d\s].{0,60}\s+\d{1,4}$", s):  # "7 ... 7"
        return True
    if re.match(r"^\d{1,4}\s+[A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\d]{2,40}$", s) \
            and not re.search(r"[,，。.!！?？:：;；]", s):  # "194 附录一"
        return True
    if re.match(r"^[^,，0-9].{2,40}\s{2,}\d{1,4}$", s):  # "立法制度  77"
        return True
    if _is_fragment_candidate(s) and freq >= 3:  # repeated running-head fragment
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Merge translated chunk files.")
    parser.add_argument("chunks_dir", help="directory containing manifest.json and chunk files")
    parser.add_argument("output_md", help="path of the merged Markdown output")
    args = parser.parse_args()

    manifest_path = os.path.join(args.chunks_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("ERROR: manifest.json not found in %s" % args.chunks_dir)
        return 1

    with io.open(manifest_path, "r", encoding="utf-8-sig") as fh:
        manifest = json.load(fh)

    # First pass: count short-fragment frequencies across all chunks so that
    # repeated running-head pieces can be identified reliably.
    freq = {}
    for chunk in manifest["chunks"]:
        idx = chunk["index"]
        base = os.path.splitext(chunk["file"])[0]
        tpath = os.path.join(args.chunks_dir, base + "_zh.md")
        if not os.path.isfile(tpath):
            continue
        with io.open(tpath, "r", encoding="utf-8-sig") as fh:
            for line in fh.read().splitlines():
                s = line.strip()
                if _is_fragment_candidate(s):
                    freq[s] = freq.get(s, 0) + 1

    merged = []
    missing = []
    for chunk in manifest["chunks"]:
        idx = chunk["index"]
        base = os.path.splitext(chunk["file"])[0]
        tpath = os.path.join(args.chunks_dir, base + "_zh.md")
        if not os.path.isfile(tpath):
            missing.append(base + "_zh.md")
            continue
        with io.open(tpath, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if PAGE_RE.match(line) or RULE_RE.match(line):
                continue
            if stripped.startswith("<!--") or stripped == "-->" or stripped.startswith("【上下文"):
                continue
            if _is_junk_line(stripped, freq.get(stripped, 0)):
                continue
            lines.append(line)
        block = "\n".join(lines).strip()
        if block:
            merged.append(block)

    if missing:
        print("ERROR: missing translated files: %s" % ", ".join(missing))
        return 1

    body = "\n\n".join(merged) + "\n"
    with io.open(args.output_md, "w", encoding="utf-8") as fh:
        fh.write(body)

    print("Merged %d chunks -> %s" % (len(merged), args.output_md))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
