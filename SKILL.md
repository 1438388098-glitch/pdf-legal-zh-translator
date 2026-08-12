---
name: pdf-legal-zh-translator
description: "Professional English-to-Chinese translator for long political and legal PDF documents (articles, treaties, statutes, court opinions, judgments, government reports, policy papers), optimized for very long documents (hundreds of pages). Extracts text page-by-page (auto-removing running headers/footers/page numbers), splits into chunks at section boundaries, translates chunks IN PARALLEL using multiple sub-agents with a shared glossary for terminology consistency, merges, runs a multi-agent quality review, and outputs a Chinese PDF. Use when the user asks to translate a long English political/legal PDF to Chinese, create a Chinese version of a law/policy document, translate a treaty or judgment, or convert a long English legal/political document into a Chinese PDF. Preserves legal citations (e.g. 5 U.S.C. § 552) and keeps institution/law/case names consistent."
---

# English-to-Chinese PDF Translator for Political & Legal Documents

Translates long English political/legal PDF documents into natural Chinese and
produces a Chinese PDF output. Designed for: articles, treaties, statutes,
court opinions, judgments, government reports, policy papers, academic legal
writing. Optimized for very long PDFs (hundreds of pages).

## Overview

- **Input**: one or more English PDF files (`.pdf`), any length
- **Output**: Chinese PDF (`.pdf`) + merged Markdown draft (`.md`) + glossary (`glossary.json`)
- **Core principle**: accuracy, terminology consistency, and complete coverage —
  especially for long documents where context must be managed deliberately.

## Pipeline Overview

1. **Extract** — page-by-page text with headers/footers auto-removed, tables
   emitted as Markdown tables (`【表格 / Table】`)
2. **Build base glossary** — read the opening pages, detect key terms up front
3. **Split into chunks** — balanced chunks broken at section boundaries, each
   chunk carries the previous chunk's tail as context
4. **Parallel translation** — one sub-agent per chunk; agents read the shared
   glossary but write new terms only to their own `chunk_XXX_terms.json`
4b. **Merge glossary** — merge_glossary.py consolidates base + per-chunk terms
5. **Check completeness** — check_completeness.py verifies page coverage and
   length sanity (automated gate)
6. **Merge** — concatenate chunk translations in order
7. **Multi-agent review + apply glossary** — parallel quality audits
   (terminology, citations, language), then apply_glossary.py deterministically
   back-fills any stray English terms to the registered translations
8. **Regenerate PDF** — render the merged Markdown to a Chinese PDF
   (headings, lists, tables)

The scripts live in the `scripts/` directory next to this SKILL.md. Resolve
paths relative to the current skill base directory.

> **Glossary path (single source of truth):** `GLOSSARY = <skill_dir>/glossary.json`
> (absolute path to the skill directory). Every step and every sub-agent uses
> this exact path. Do NOT write glossary entries directly to the shared file
> from parallel agents — write per-chunk term files and merge them (Step 4b).

---

## Step 1 — Extract text

For each PDF, run:

```
python <skill_dir>/scripts/extract_pdf.py <input.pdf> <output.txt>
```

- Writes text page-by-page with `【第 N 页 / Page N】` markers.
- **Auto-removes** repeated running headers/footers and bare page numbers
  (use `--keep-header-footer` if a document needs them).
- **Tables** are detected and emitted as Markdown tables under a
  `【表格 / Table】` marker, so table content survives translation (native
  `find_tables` when available, grid heuristic otherwise).
- If the script warns about little/no text, the PDF is a scanned image —
  tell the user OCR is out of scope and stop.
- If the PDF is password-protected, tell the user to decrypt it first.

## Step 2 — Build the base glossary (before any translation)

Reading order matters. Do this **before** translating anything:

1. Read the extracted text's first few pages (or the document's table of
   contents if present) to identify the domain, structure, and recurring terms.
2. Read `GLOSSARY` (i.e. `<skill_dir>/glossary.json`). If missing, create the
   skeleton:
   ```json
   {
     "institutions": {}, "laws": {}, "cases": {},
     "doctrine": {}, "general": {}
   }
   ```
3. Pre-register the key institutions, laws, cases, and doctrine terms you can
   already identify (e.g. `Supreme Court of the United States` → `联邦最高法院`,
   `due process` → `正当程序`). These become the shared vocabulary for all
   translation agents.

## Step 3 — Split into chunks

Run:

```
python <skill_dir>/scripts/split_chunks.py <output.txt> <chunks_dir> --pages 20
```

- Defaults to ~20 pages per chunk (tune with `--pages`; for very long docs use
  `--max-chunks N` to cap the number of parallel workers).
- Prefers to break chunks at section headings so each agent works on coherent
  sections.
- **Each chunk after the first starts with a context block** (the previous
  chunk's last ~300 characters, marked `<!-- CONTEXT ... -->` and
  `【上下文 / Previous chunk tail】`) so agents keep sentences/paragraphs
  continuous across chunk seams.
- Produces `manifest.json` + `chunk_001.txt`, `chunk_002.txt`, ...
- Inspect `manifest.json` and record the total chunk count.

## Step 4 — Parallel translation (one sub-agent per chunk)

Dispatch **one sub-agent per chunk, all in parallel** (e.g. via the Task tool),
with identical instructions:

```
Translate <chunks_dir>/chunk_XXX.txt (pages A–B of <document>) into professional
formal Chinese following the pdf-legal-zh-translator skill. Write the result to
<chunks_dir>/chunk_XXX_zh.md.

CONSTRAINTS:
1. Read GLOSSARY = <skill_dir>/glossary.json FIRST. Reuse every existing term
   exactly. If you encounter a NEW key term, do NOT edit glossary.json. Instead
   append it to <chunks_dir>/chunk_XXX_terms.json (same 5-category structure),
   grouped by category, and reuse it consistently within your chunk.
2. On first occurrence of an institution/law/case name in your chunk, write
   Chinese + English in parentheses: 联邦最高法院 (Supreme Court of the United States).
3. Preserve all legal citations verbatim: § 1983, 5 U.S.C. § 552, Miranda v. Arizona.
4. Keep document headings (## / ###) matching the source structure.
5. Formal, professional, neutral Chinese. No opinion or slant.
6. Keep the per-page 【第 N 页】 markers in your chunk output — merge_chunks.py strips them.
7. Ignore any <!-- CONTEXT ... --> and 【上下文 ...】 block at the top of the
   file: it is context from the previous chunk for continuity only — never
   translate or copy it into your output.
8. Tables: keep the 【表格 / Table】 marker and the | ... | Markdown table rows;
   translate the cell contents, preserve the | column structure.
9. Do NOT truncate. Cover every paragraph in your chunk.
```

Each agent writes only its own `chunk_XXX_zh.md` and only its own
`chunk_XXX_terms.json`. Never let parallel agents write the same file or edit
`GLOSSARY` directly (that would race and lose entries).

## Step 4b — Merge the glossary (after all chunks translate)

Once **all** chunk agents finish, consolidate the per-chunk terms into the
shared glossary:

```
python <skill_dir>/scripts/merge_glossary.py <chunks_dir> <skill_dir>
```

- First registration wins; conflicting translations are reported as warnings.
- Writes the final merged `GLOSSARY` back to `<skill_dir>/glossary.json`.

## Step 5 — Check completeness (automated gate, before merging)

```
python <skill_dir>/scripts/check_completeness.py <output.txt> <chunks_dir>
```

- Verifies each `chunk_XXX_zh.md` covers exactly its source pages (via the page
  markers), flags suspiciously short/long chunks, and missing headings.
- Exit code 1 means hard errors — re-translate the flagged chunks, then re-run
  until it prints `Result: OK`.

## Step 6 — Merge

After completeness passes, run:

```
python <skill_dir>/scripts/merge_chunks.py <chunks_dir> <name>_zh.md
```

- Concatenates `chunk_XXX_zh.md` in manifest order and strips page markers and
  context blocks.
- If it reports missing translations, re-run those chunks before continuing.

## Step 7 — Multi-agent review (parallel)

Dispatch several review sub-agents **in parallel**, each with one focus area:

- **Terminology auditor**: read `GLOSSARY` + `<name>_zh.md`; flag any term
  used inconsistently or translated differently across chunks.
- **Citation auditor**: verify every legal citation (§, U.S.C., Statutes at
  Large, case names, treaties) is preserved exactly and correctly.
- **Completeness auditor**: compare `<name>_zh.md` against the extracted text;
  flag missing pages, paragraphs, or headings (check_completeness.py already
  covers page coverage — focus on content-level gaps).
- **Language reviewer**: flag unnatural, overly literal, or awkward Chinese and
  recommend fixes.

Collect all findings, apply the fixes yourself, then run the deterministic
consistency pass:

```
python <skill_dir>/scripts/apply_glossary.py <skill_dir>/glossary.json <name>_zh.md
```

- Replaces any stray English key term still in the body with its registered
  translation form `中文 (English)`, so late-registered terms are back-filled
  everywhere. Run it again after any further edits. Then confirm nothing else
  is missing and re-run a fix round if the auditors still find issues.

## Step 8 — Regenerate the PDF

```
python <skill_dir>/scripts/build_pdf.py <name>_zh.md <name>_zh.pdf
```

The script auto-selects a system Chinese font, adds page numbers, and renders
Markdown headings, lists, and tables.

## Step 9 — Save the glossary

Write the final `glossary.json` next to SKILL.md (or update it in place).

---

## Translation Guidelines

### Terminology consistency (REQUIRED)

- The glossary is the single source of truth shared by all parallel agents.
- **Parallel agents never write the shared glossary directly.** New terms go to
  that agent's `chunk_XXX_terms.json`; `merge_glossary.py` consolidates them.
- On first occurrence of any key term, choose a translation, **record it in the
  glossary (or your chunk terms file)**, and reuse that exact translation for
  the rest of the document.
- On first occurrence of an institution, law, or case name, include the English
  original in parentheses: `联邦最高法院 (Supreme Court of the United States)`.
- For repeat occurrences, use only the Chinese translation.
- Before generating the PDF, run `apply_glossary.py` to deterministically
  back-fill any stray English terms to their registered form.

### Legal and political precision

- **Preserve citations verbatim**: `§ 1983`, `5 U.S.C. § 552`, `Miranda v.
  Arizona`, `Rome Statute`, `UN Security Council Resolution 1325`.
- **Latin legal terms** keep standard Chinese conventions or original form with
  gloss: `habeas corpus (人身保护令)`, `stare decisis (遵循先例)`.
- **Neutral and objective** political language — translate accurately without
  adding opinion or ideological slant.
- Numbers, dates, and named entities (persons, place names) keep their
  canonical Chinese form; use the glossary for consistency.

### Style

- Natural, professional, formal written Chinese. Clarity and reversibility
  over ornamentation.
- Keep paragraph structure aligned with the source where possible.
- Combine broken sentences into complete lines; preserve paragraph breaks.
- Keep document headings (`#`, `##`, `###`) matching the source structure.
- **Tables** (between `【表格 / Table】` markers): translate the cell contents,
  keep the `| ... |` column structure and header row. Do not flatten or skip
  tables.
- **Context blocks** (`<!-- CONTEXT ... -->`, `【上下文 ...】`) at the top of a
  chunk are seam-continuity hints only — never translate or output them.

### Quality checklist (before generating the PDF)

- [ ] Every key term is in the glossary and used consistently across all chunks
- [ ] Legal citations are preserved exactly
- [ ] Institution/law/case names carry English originals on first use
- [ ] Paragraphs read naturally in formal Chinese
- [ ] Heading hierarchy mirrors the source document
- [ ] Table rows are translated and keep their `|` column structure
- [ ] All chunks translated — no gaps, no truncation (check_completeness.py passed)

---

## Output files

- `<name>_zh.md` — full Markdown translation, same directory as the input
- `<name>_zh.pdf` — rendered Chinese PDF, same directory
- `<chunks_dir>/chunk_XXX_zh.md` — per-chunk translations (intermediate)
- `<chunks_dir>/chunk_XXX_terms.json` — per-chunk new terms (intermediate, merged into the glossary)
- `glossary.json` — terminology table, saved in the skill directory

## Usage triggers

- "Translate this PDF to Chinese"
- "把这份政治/法律 PDF 翻译成中文"
- "Create a Chinese version of <law/policy/treaty>"
- "翻译这份判决书/条约/政策文件"
- "翻译这个几百页的 PDF"
