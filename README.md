English · [简体中文](./README.zh-CN.md)

[![CI](https://github.com/1438388098-glitch/pdf-legal-zh-translator/actions/workflows/ci.yml/badge.svg)](https://github.com/1438388098-glitch/pdf-legal-zh-translator/actions/workflows/ci.yml)

# pdf-legal-zh-translator

A professional English → Chinese AI **Skill** for **long political & legal PDFs**.

It translates English PDFs of hundreds of pages (articles, treaties, statutes, court opinions, government reports, policy documents, academic legal literature) into formal, professional, terminology-consistent Chinese and produces a Chinese PDF. Built for very long documents: chunked parallel translation + a shared glossary + multi-agent review ensure terminology consistency, citation integrity, and full-document coverage.

> 📸 **Quick look at the output** (end-to-end translation of public-domain texts): [Page 1](examples/screenshot_page1.png) · [Page 2](examples/screenshot_page2.png) · [Page 3](examples/screenshot_page3.png)

---

## Features

- **PDFs of any length**: text is extracted page by page and split at section boundaries, so documents of hundreds of pages are translated in full
- **Parallel translation**: one sub-agent per chunk, substantially shortening translation time for long documents
- **Terminology consistency**: a shared `glossary.json` (single source of truth); new terms are written by each chunk agent to its own terms file and then merged centrally, eliminating parallel-write races
- **Statute/citation fidelity**: `§ 1983`, `5 U.S.C. § 552`, *Miranda v. Arizona* are preserved verbatim
- **First-occurrence English annotations** for institution/law/case names: `联邦最高法院 (Supreme Court of the United States)`
- **Automatic header/footer/page-number removal**: repeated headers/footers and bare page numbers are stripped automatically
- **Table support**: tables are detected automatically, converted to Markdown tables, their cells translated, and rendered as native tables in the PDF
- **Cross-chunk context**: each chunk carries the tail of the previous chunk as context, avoiding broken sentences at chunk boundaries
- **Automated completeness verification**: a script checks per-chunk page-marker coverage and translation length ratio; any missing page fails the run
- **Multi-agent quality review**: four parallel reviews (terminology / citations / completeness / language) + deterministic glossary back-fill
- **Chinese PDF output**: automatically selects a system Chinese font (Microsoft YaHei / SimHei / SimSun); supports headings, lists, tables, and page numbers

## Workflow

```
PDF ──① extract──> text (page-by-page) ──② pre-build glossary──> glossary.json
   ──③ split into chunks──> chunk_001.txt … (with context) + manifest.json
   ──④ parallel translation──> chunk_XXX_zh.md + chunk_XXX_terms.json
   ──④b merge glossary──> merge_glossary.py
   ──⑤ completeness check──> check_completeness.py (hard page-coverage verification)
   ──⑥ merge──> <name>_zh.md
   ──⑦ multi-agent review + apply_glossary.py back-fill
   ──⑧ render PDF──> <name>_zh.pdf
```

## Installation

The scripts use Python 3 and require the following packages:

```bash
pip install PyMuPDF reportlab
```

- `PyMuPDF` (fitz): PDF text/table extraction. `find_tables` requires ≥ 1.23.8; older versions automatically fall back to the built-in grid heuristic.
- `reportlab`: Chinese PDF generation. Requires a system Chinese font (Windows bundles Microsoft YaHei / SimHei / SimSun).

## Usage

Load this skill in an AI-Skill-capable environment (e.g. opencode), then:

```
Translate this PDF to Chinese
把这份政治/法律 PDF 翻译成中文
Create a Chinese version of <law/policy/treaty>
翻译这份判决书/条约/政策文件
```

Or run the script pipeline manually (see `SKILL.md` for step-by-step instructions):

```bash
# 1. Extract (auto-strips headers/footers/page numbers + table detection)
python scripts/extract_pdf.py input.pdf extracted.txt

# 2. Split into chunks (~20 pages each, adjustable; with cross-chunk context)
python scripts/split_chunks.py extracted.txt chunks --pages 20

# 3. Parallel translation (one sub-agent per chunk, see SKILL.md Step 4)

# 4. Merge per-chunk new terms into the shared glossary
python scripts/merge_glossary.py chunks <skill_dir>

# 5. Automated completeness check (missing pages / truncation raise errors)
python scripts/check_completeness.py extracted.txt chunks

# 6. Merge translations
python scripts/merge_chunks.py chunks <name>_zh.md

# 7. Deterministic glossary back-fill for consistency
python scripts/apply_glossary.py <skill_dir>/glossary.json <name>_zh.md

# 8. Generate the Chinese PDF (auto TOC + new page per section)
python scripts/build_pdf.py <name>_zh.md <name>_zh.pdf
```

## Scripts

| Script | Purpose |
|---|---|
| `extract_pdf.py` | PDF → page-by-page text; auto-strips repeated headers/footers and bare page numbers; detects scanned/encrypted PDFs; table detection (`find_tables` or word-coordinate heuristics) |
| `split_chunks.py` | Balanced chunking at section boundaries; each chunk header carries ~300 characters from the end of the previous chunk as context; produces `manifest.json` |
| `merge_glossary.py` | Merges the base glossary + per-chunk `chunk_XXX_terms.json`; first registration wins, conflicts are warned |
| `apply_glossary.py` | Uses the final glossary to deterministically back-fill residual English terms in the translation into the canonical `中文 (English)` form |
| `check_completeness.py` | Verifies per-chunk translation page-marker coverage (hard error), translation/source length ratio, and missing headings |
| `merge_chunks.py` | Concatenates chunk translations in manifest order, stripping page markers and context blocks; errors on missing chunks |
| `build_pdf.py` | Markdown → Chinese PDF; auto font selection, TOC generation, new-page-per-section pagination, renders headings/lists/quotes/Markdown tables (adaptive column widths + header shading + zebra striping), footer page numbers |

## Glossary format

`glossary.json` is the single source of truth for document-wide terminology consistency, with five groups:

```json
{
  "institutions": { "Supreme Court of the United States": "联邦最高法院" },
  "laws":        {},
  "cases":       { "Miranda v. Arizona": "米兰达诉亚利桑那州案" },
  "doctrine":    { "due process": "正当程序" },
  "general":     {}
}
```

Parallel agents must **not** modify the shared `glossary.json` directly (parallel writes would race and lose entries); new terms go into each agent's own `chunk_XXX_terms.json` and are merged centrally by `merge_glossary.py`.

## Output files

- `<name>_zh.md` — complete Chinese Markdown translation (same directory as the input)
- `<name>_zh.pdf` — rendered Chinese PDF (headings/lists/tables/page numbers)
- `<chunks_dir>/chunk_XXX_zh.md` — per-chunk translations (intermediate artifacts)
- `<chunks_dir>/chunk_XXX_terms.json` — per-chunk new terms (intermediate artifacts)
- `glossary.json` — final glossary (kept in the skill directory)

## Limitations

- **Scanned (image) PDFs** are out of scope — OCR would be required; the script warns explicitly.
- **Encrypted PDFs** must be decrypted first.
- Translation quality depends on the underlying model; statutory citations are re-checked by the review agents and terminology consistency is enforced by scripts as a safety net, but a human final review is still recommended for professional use.
- With older PyMuPDF (< 1.23.8), table detection is heuristic; complex layouts (cells merged across pages, nested tables) may not be fully reconstructed.

## Validation & examples

- **[examples/](examples/)**: an end-to-end example on public-domain texts (U.S. Constitution amendments, 42 U.S.C. § 1983) — source PDF generation, chunking, translations, glossary merge, completeness check, final Chinese PDF and page screenshots, with a real quality-data table (including an explanation of one length-ratio warning triggered by design)
- **Tests**: `python -m unittest discover -s tests` (6 cases) covering glossary merge rules (base table takes priority / first registration wins / conflict warnings), the page-coverage hard check (missing page → exit 1), the length-ratio warning path, merge order and page-marker stripping, and missing-translation errors

## Related

The design document is at [`docs/2026-08-12-pdf-poli-law-translator-design.md`](docs/2026-08-12-pdf-poli-law-translator-design.md); full workflow instructions are in [`SKILL.md`](SKILL.md).

## License

[MIT](LICENSE)
