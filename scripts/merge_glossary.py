#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Merge per-chunk terminology files into the shared glossary.

Usage:
    python merge_glossary.py <chunks_dir> <skill_dir> [--out glossary.json]

Why this exists:
    Parallel chunk translators used to append to the shared glossary.json
    simultaneously, which races (read-modify-write is not atomic) and loses
    entries. Instead, each chunk agent now writes only its own
    chunk_XXX_terms.json; this script merges them into the shared glossary
    afterwards, deterministically and without conflicts.

Merge rules:
    - The base glossary (skill_dir/glossary.json) always wins for existing keys.
    - Chunk terms files are processed in chunk order (chunk_001, chunk_002, ...);
      the first agent that registered a term defines its translation.
    - Conflicting translations for the same English term are reported as
      warnings but the first occurrence is kept.

Term file format (written by chunk agents):
    {
      "institutions": {"Supreme Court of the United States": "联邦最高法院"},
      "laws": {}, "cases": {}, "doctrine": {}, "general": {}
    }
"""

import argparse
import io
import json
import os
import re
import sys

CATEGORIES = ["institutions", "laws", "cases", "doctrine", "general"]

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _load_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _skeleton():
    return {cat: {} for cat in CATEGORIES}


def _normalize(data):
    """Accept either the 5-category glossary shape or a flat {en: zh} map."""
    if isinstance(data, dict) and any(k in data for k in CATEGORIES):
        out = _skeleton()
        for cat in CATEGORIES:
            val = data.get(cat)
            if isinstance(val, dict):
                out[cat].update(val)
        return out
    if isinstance(data, dict):
        return {"general": dict(data)}
    return _skeleton()


def _terms_files(chunks_dir):
    pat = re.compile(r"^chunk_(\d+)_terms\.json$")
    found = []
    if os.path.isdir(chunks_dir):
        for name in os.listdir(chunks_dir):
            m = pat.match(name)
            if m:
                found.append((int(m.group(1)), name))
    found.sort()
    return [(name, idx) for idx, name in found]


def main():
    parser = argparse.ArgumentParser(description="Merge chunk term files into the shared glossary.")
    parser.add_argument("chunks_dir", help="directory with chunk_XXX_terms.json files")
    parser.add_argument("skill_dir", help="skill directory containing glossary.json")
    parser.add_argument("--out", default=None, help="output path (default: <skill_dir>/glossary.json)")
    args = parser.parse_args()

    base_path = os.path.join(args.skill_dir, "glossary.json")
    if os.path.isfile(base_path):
        merged = _normalize(_load_json(base_path))
    else:
        merged = _skeleton()

    term_files = _terms_files(args.chunks_dir)
    if not term_files:
        print("WARNING: no chunk_XXX_terms.json files found in %s" % args.chunks_dir)

    conflicts = []
    added = 0
    for name, idx in term_files:
        path = os.path.join(args.chunks_dir, name)
        try:
            data = _normalize(_load_json(path))
        except Exception as exc:
            print("ERROR: cannot read %s: %s" % (path, exc))
            return 1
        for cat in CATEGORIES:
            for en, zh in data.get(cat, {}).items():
                en = en.strip()
                zh = (zh or "").strip()
                if not en or not zh:
                    continue
                if en in merged[cat]:
                    if merged[cat][en] != zh:
                        conflicts.append(
                            "[%s] %s = %s (chunk_%03d) vs %s (already registered)"
                            % (cat, en, zh, idx, merged[cat][en]))
                    continue
                merged[cat][en] = zh
                added += 1

    out_path = args.out or base_path
    with io.open(out_path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("Merged %d new terms from %d chunk files -> %s" % (added, len(term_files), out_path))
    if conflicts:
        print("WARNING: %d conflicting translations (first registration kept):" % len(conflicts))
        for c in conflicts:
            print("  " + c)
    print("Total glossary terms: %d" % sum(len(v) for v in merged.values()))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
