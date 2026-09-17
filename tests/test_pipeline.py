#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""流水线脚本 CLI 端到端测试（stdlib unittest，无第三方依赖）。

覆盖：merge_glossary（合并规则）、check_completeness（页覆盖硬校验与长度告警）、
merge_chunks（顺序拼接、标记剥离、缺块报错）。

运行：python -m unittest discover -s tests -v
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")


def run_py(script, *args):
    out = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return out.returncode, out.stdout.decode("utf-8", "replace")


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content)


def make_chunks_dir(root, pages, missing=None, ratio_trim=None):
    """构造一个最小 chunks 目录：每页一个 chunk，页标记 + 一行内容。"""
    d = os.path.join(root, "chunks")
    chunks = []
    for p in pages:
        base = "chunk_%03d" % p
        write(os.path.join(d, base + ".txt"),
              u"【第 %d 页 / Page %d】\nSource line for page %d. " % (p, p, p) * 20)
        body = u"【第 %d 页 / Page %d】\n\n第 %d 页的译文内容，用于测试。\n" % (p, p, p)
        if ratio_trim and p in ratio_trim:
            body = u"【第 %d 页 / Page %d】\n短\n" % (p, p)
        if not (missing and p in missing):
            write(os.path.join(d, base + "_zh.md"), body)
        chunks.append({"index": p, "file": base + ".txt",
                       "pages": [p, p], "headings": []})
    write(os.path.join(d, "manifest.json"),
          json.dumps({"source": "x.txt", "total_pages": len(pages),
                      "target_pages_per_chunk": 1, "chunks": chunks},
                     ensure_ascii=False))
    return d


class MergeGlossaryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # skill_dir：基础术语表（唯一真源）
        write(os.path.join(self.dir, "glossary.json"), json.dumps({
            "institutions": {"Congress": "国会（既有译法优先）"},
            "laws": {}, "cases": {}, "doctrine": {}, "general": {}}, ensure_ascii=False))
        # chunk 1：既有键 + 新键（文件名须符合 chunk_XXX_terms.json 约定）
        write(os.path.join(self.dir, "chunk_001_terms.json"), json.dumps({
            "institutions": {"Congress": "国会", "Senate": "参议院"},
            "laws": {}, "cases": {}, "doctrine": {"due process": "正当程序"},
            "general": {}}, ensure_ascii=False))
        # chunk 2：与 chunk 1 冲突的新键（首个登记者应胜出）
        write(os.path.join(self.dir, "chunk_002_terms.json"), json.dumps({
            "institutions": {}, "laws": {}, "cases": {},
            "doctrine": {"due process": "正当法律程序"}, "general": {}},
            ensure_ascii=False))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_merge_rules(self):
        out_glossary = os.path.join(self.dir, "merged.json")
        code, out = run_py("merge_glossary.py", self.dir, self.dir, "--out", out_glossary)
        self.assertEqual(code, 0, out)
        with io.open(out_glossary, encoding="utf-8") as f:
            g = json.load(f)
        # 基础术语表对既有键永远获胜
        self.assertEqual(g["institutions"]["Congress"], u"国会（既有译法优先）")
        # 新键由首个登记的 chunk 定义
        self.assertEqual(g["institutions"]["Senate"], u"参议院")
        self.assertEqual(g["doctrine"]["due process"], u"正当程序")
        # 冲突有告警但不致命
        self.assertIn("WARN", out)


class CheckCompletenessTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _extracted(self, pages):
        write(os.path.join(self.dir, "src.txt"),
              "".join(u"【第 %d 页 / Page %d】\n%s\n" % (p, p, "word " * 200)
                      for p in pages))

    def test_full_coverage_passes(self):
        self._extracted([1, 2])
        d = make_chunks_dir(self.dir, [1, 2])
        code, out = run_py("check_completeness.py", os.path.join(self.dir, "src.txt"), d)
        self.assertEqual(code, 0, out)
        self.assertIn("OK", out)

    def test_missing_page_fails(self):
        self._extracted([1, 2])
        d = make_chunks_dir(self.dir, [1, 2], missing={2})
        code, out = run_py("check_completeness.py", os.path.join(self.dir, "src.txt"), d)
        self.assertEqual(code, 1)
        self.assertIn("chunk_002", out)

    def test_short_translation_warns_but_page_ok(self):
        self._extracted([1])
        d = make_chunks_dir(self.dir, [1], ratio_trim={1})
        code, out = run_py("check_completeness.py", os.path.join(self.dir, "src.txt"), d)
        self.assertEqual(code, 0)  # 页覆盖完整 → 硬校验通过
        self.assertIn("WARNING", out)  # 长度比异常 → 告警


class MergeChunksTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_order_and_marker_stripping(self):
        d = make_chunks_dir(self.dir, [1, 2])
        out_md = os.path.join(self.dir, "merged.md")
        code, out = run_py("merge_chunks.py", d, out_md)
        self.assertEqual(code, 0, out)
        with io.open(out_md, encoding="utf-8") as f:
            merged = f.read()
        self.assertNotIn(u"【第 1 页", merged)      # 页标记被剥离
        self.assertNotIn(u"【第 2 页", merged)
        self.assertLess(merged.index(u"第 1 页的译文"), merged.index(u"第 2 页的译文"))  # 顺序正确

    def test_missing_translation_reported(self):
        d = make_chunks_dir(self.dir, [1, 2])
        os.remove(os.path.join(d, "chunk_002_zh.md"))
        code, out = run_py("merge_chunks.py", d, os.path.join(self.dir, "m.md"))
        self.assertNotEqual(code, 0)
        self.assertIn("chunk_002_zh.md", out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    unittest.main()
