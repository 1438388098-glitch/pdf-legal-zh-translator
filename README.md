# pdf-legal-zh-translator

面向**政治与法律文献长文本 PDF** 的英→中专业翻译 AI Skill。

将长达数百页的英文 PDF（文章、条约、法规、法院判决、政府报告、政策文件、学术法律文献）翻译为正式、专业、术语一致的中文，并生成中文 PDF。专为超长文档设计：分块并行翻译 + 共享术语表 + 多 agent 审查，保证术语一致性、引用完整性和全文覆盖。

> 简体中文 | [English](#english-overview)

---

## 特性

- **任意长度 PDF**：按页提取、按章节边界分块，数百页文档也能完整翻译
- **并行翻译**：每块派一个子 agent 并行翻译，显著缩短长文档翻译耗时
- **术语一致性**：共享 `glossary.json` 术语表（唯一真源），新术语由各块 agent 写入独立 terms 文件后统一合并，杜绝并行写竞态
- **法条引用保真**：`§ 1983`、`5 U.S.C. § 552`、`Miranda v. Arizona` 原样保留
- **机构/法律/案例名首现标注英文原名**：`联邦最高法院 (Supreme Court of the United States)`
- **自动去页眉/页脚/页码**：重复页眉页脚与裸页码自动剔除
- **表格支持**：表格自动识别并转为 Markdown 表格，翻译单元格后以原生表格渲染进 PDF
- **跨块上下文**：每块附带上一块结尾作上下文，避免切块处语句断裂
- **完整性自动校验**：脚本核对每块页标记覆盖、译文长度比，缺页即失败
- **多 agent 质量审查**：术语 / 引用 / 完整性 / 语言 四类并行审查 + 确定性术语回填
- **输出中文 PDF**：自动选用系统中文字体（微软雅黑/黑体/宋体），支持标题、列表、表格、页码

## 工作流程

```
PDF ──①提取──> 文本(按页) ──②预建术语表──> glossary.json
   ──③分块──> chunk_001.txt … (含上下文) + manifest.json
   ──④并行翻译──> chunk_XXX_zh.md + chunk_XXX_terms.json
   ──④b 合并术语表──> merge_glossary.py
   ──⑤ 完整性校验──> check_completeness.py (硬校验页覆盖)
   ──⑥ 合并──> <name>_zh.md
   ──⑦ 多agent审查 + apply_glossary.py 回填
   ──⑧ 生成PDF──> <name>_zh.pdf
```

## 安装

依赖脚本使用 Python 3，需要以下包：

```bash
pip install PyMuPDF reportlab
```

- `PyMuPDF`（fitz）：PDF 文本/表格提取。`find_tables` 需 ≥ 1.23.8；旧版本自动回退到内置网格启发式。
- `reportlab`：中文 PDF 生成。需要系统中文字体（Windows 自带微软雅黑/黑体/宋体）。

## 使用方法

在 opencode 等支持 AI Skill 的环境中加载本 skill，然后：

```
Translate this PDF to Chinese
把这份政治/法律 PDF 翻译成中文
Create a Chinese version of <law/policy/treaty>
翻译这份判决书/条约/政策文件
```

或手动执行脚本流水线（详见 `SKILL.md` 的分步说明）：

```bash
# 1. 提取（自动去页眉页脚页码 + 表格识别）
python scripts/extract_pdf.py input.pdf extracted.txt

# 2. 分块（每块约 20 页，可调；附带跨块上下文）
python scripts/split_chunks.py extracted.txt chunks --pages 20

# 3. 并行翻译（每块一个子 agent，见 SKILL.md Step 4）

# 4. 合并各块新术语到共享术语表
python scripts/merge_glossary.py chunks <skill_dir>

# 5. 完整性自动校验（缺页/截断会报错）
python scripts/check_completeness.py extracted.txt chunks

# 6. 合并译文
python scripts/merge_chunks.py chunks <name>_zh.md

# 7. 确定性回填术语一致性
python scripts/apply_glossary.py <skill_dir>/glossary.json <name>_zh.md

# 8. 生成中文 PDF（自动目录 + 章节新页）
python scripts/build_pdf.py <name>_zh.md <name>_zh.pdf
```

## 脚本一览

| 脚本 | 作用 |
|---|---|
| `extract_pdf.py` | PDF → 按页文本；自动剔除重复页眉/页脚/裸页码；检测扫描版/加密 PDF；表格识别（`find_tables` 或单词坐标启发式） |
| `split_chunks.py` | 按章节边界平衡分块；每块头部附上一块末尾约 300 字符作上下文；产出 `manifest.json` |
| `merge_glossary.py` | 合并 base glossary + 各 `chunk_XXX_terms.json`，首登记生效，冲突告警 |
| `apply_glossary.py` | 用最终术语表确定性回填正文中残留的英文术语为 `中文 (English)` 规范形式 |
| `check_completeness.py` | 自动校验每块译文的页标记覆盖（硬错误）、译文/源长度比、标题缺失 |
| `merge_chunks.py` | 按 manifest 顺序拼接各块译文，剥离页标记与上下文块；缺失块报错 |
| `build_pdf.py` | Markdown → 中文 PDF；自动选字体，生成目录（TOC）、章节新页分页，渲染标题/列表/引用/Markdown 表格（自适应列宽+表头底纹+隔行着色），页脚页码 |

## 术语表格式

`glossary.json` 是全文术语一致性的唯一真源，五类分组：

```json
{
  "institutions": { "Supreme Court of the United States": "联邦最高法院" },
  "laws":        {},
  "cases":       { "Miranda v. Arizona": "米兰达诉亚利桑那州案" },
  "doctrine":    { "due process": "正当程序" },
  "general":     {}
}
```

并行 agent **不得**直接修改共享 `glossary.json`（会写竞态丢条目），新术语写入各自的 `chunk_XXX_terms.json`，由 `merge_glossary.py` 统一合并。

## 输出文件

- `<name>_zh.md` — 完整中文 Markdown 译文（与输入同目录）
- `<name>_zh.pdf` — 渲染后的中文 PDF（标题/列表/表格/页码）
- `<chunks_dir>/chunk_XXX_zh.md` — 各块译文（中间产物）
- `<chunks_dir>/chunk_XXX_terms.json` — 各块新术语（中间产物）
- `glossary.json` — 最终术语表（保存在 skill 目录）

## 限制

- **扫描版（图片）PDF** 不在范围内——需要 OCR，脚本会明确警告。
- **加密 PDF** 需先解密。
- 翻译质量受基础模型能力影响；法条引用由审查 agent 复核，术语一致性由脚本兜底，但仍建议专业场景人工终审。
- 旧版 PyMuPDF（< 1.23.8）的表格识别为启发式，复杂版式（跨页合并单元格、嵌套表格）可能无法完整还原。

## 相关

设计文档见 [`docs/2026-08-12-pdf-poli-law-translator-design.md`](docs/2026-08-12-pdf-poli-law-translator-design.md)，完整工作流说明见 [`SKILL.md`](SKILL.md)。

---

## English overview

An AI **Skill** that translates long English political/legal PDFs (articles, treaties, statutes, court opinions, government reports, policy papers — hundreds of pages) into professional Chinese and produces a Chinese PDF.

Key design: extract page-by-page text (auto-stripping headers/footers/page numbers, detecting tables), split into chunks at section boundaries with cross-chunk context, translate chunks **in parallel** using sub-agents sharing a glossary for terminology consistency, merge per-chunk term files without write races, run an automated completeness gate, merge, multi-agent quality review with deterministic glossary back-fill, and finally render a Chinese PDF.

**Requirements:** Python 3 + `PyMuPDF` + `reportlab`; a system Chinese font (bundled on Windows).

**Scripts:** `extract_pdf.py`, `split_chunks.py`, `merge_glossary.py`, `apply_glossary.py`, `check_completeness.py`, `merge_chunks.py`, `build_pdf.py`.
