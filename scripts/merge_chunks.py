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
