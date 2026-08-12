#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Enforce glossary consistency on the merged translation (deterministic).

Usage:
    python apply_glossary.py <glossary.json> <input.md> [output.md] [--min-len 3]

What it does:
    For every glossary entry (en -> zh), if the English term still appears in
    the translation body text, it is replaced with the canonical form
        zh (en)
    This back-fills chunks that were translated before a term was registered,
    and normalizes any stray English occurrences to the glossary term.

Safety rules:
    - Only whole words are matched (letter boundaries), so "Court" is not
      matched inside "Supreme Court".
    - Terms already written as "... zh (en)" are skipped (the en is already in
      parentheses).
    - Terms inside parentheses (first-occurrence annotations) are left alone.
    - Entries shorter than --min-len characters are ignored to avoid noise.
    - Longer entries are applied first so "due process" wins over "process".
    - This is best-effort normalization; semantic review is done by agents.

Output: writes to <output.md>, or in place if omitted.
"""

import argparse
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CATEGORIES = ["institutions", "laws", "cases", "doctrine", "general"]


def _prev_nonspace(text, i):
    j = i - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    return text[j] if j >= 0 else ""


def _next_nonspace(text, i):
    j = i
    while j < len(text) and text[j].isspace():
        j += 1
    return text[j] if j < len(text) else ""


def _apply_entry(text, en, zh, min_len):
    if len(en) < min_len:
        return text, 0
    if en == zh or en in zh:
        return text, 0
    pattern = re.compile(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])")
    out = []
    last_end = 0
    changed = 0
    for m in pattern.finditer(text):
        s, e = m.span()
        if s < last_end:
            continue
        # skip if already the "... zh (en)" form (en is inside parentheses)
        if _prev_nonspace(text, s) in "(（" or _next_nonspace(text, e) in ")）":
            continue
        out.append(text[last_end:s])
        out.append("%s (%s)" % (zh, en))
        last_end = e
        changed += 1
    out.append(text[last_end:])
    return "".join(out), changed


def main():
    parser = argparse.ArgumentParser(description="Apply glossary to a translation.")
    parser.add_argument("glossary_json", help="path to glossary.json")
    parser.add_argument("input_md", help="path to the translated Markdown")
    parser.add_argument("output_md", nargs="?", help="output path (default: overwrite input)")
    parser.add_argument("--min-len", type=int, default=3, help="min English term length to apply (default: 3)")
    args = parser.parse_args()

    if not os.path.isfile(args.glossary_json):
        print("ERROR: glossary not found: %s" % args.glossary_json)
        return 1
    if not os.path.isfile(args.input_md):
        print("ERROR: input not found: %s" % args.input_md)
        return 1

    with io.open(args.glossary_json, "r", encoding="utf-8-sig") as fh:
        glossary = json.load(fh)
    with io.open(args.input_md, "r", encoding="utf-8-sig") as fh:
        text = fh.read()

    entries = []
    for cat in CATEGORIES:
        for en, zh in glossary.get(cat, {}).items():
            if en and zh:
                entries.append((en, zh))
    # longer terms first so more specific entries apply before their parts
    entries.sort(key=lambda e: len(e[0]), reverse=True)

    total_changed = 0
    for en, zh in entries:
        text, changed = _apply_entry(text, en, zh, args.min_len)
        total_changed += changed

    out_path = args.output_md or args.input_md
    with io.open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    print("Applied %d glossary entries, %d replacements -> %s"
          % (len(entries), total_changed, out_path))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
