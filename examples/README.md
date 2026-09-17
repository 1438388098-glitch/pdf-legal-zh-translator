# examples · 公有领域文本端到端示例

本目录用**公有领域**的美国联邦法律文本（宪法第一修正案、第十四修正案第一节、42 U.S.C. § 1983——美国联邦政府作品，不享版权）演示完整翻译流水线。**不包含任何受版权保护的材料**。

## 产物一览

| 文件 | 说明 |
|------|------|
| `constitution_excerpt.pdf` | 英文源 PDF（2 页，由 `make_source_pdf.py` 生成，可再现） |
| `run_extracted.txt` | `extract_pdf.py` 提取的按页文本 |
| `run_chunks/` | `split_chunks.py` 分块输出：2 个 chunk + manifest + **每块译文 + 术语文件** |
| `glossary_merged.json` | `merge_glossary.py` 合并后的术语表（16 条，0 冲突） |
| `constitution_excerpt_zh.md` / `.pdf` | 合并译文与最终中文 PDF（3 页：目录 + 正文 2 页） |
| `screenshot_page*.png` | 最终 PDF 的页面截图（PyMuPDF 渲染） |

说明：分块后的「翻译」步骤在本示例中由 AI 模型直接完成（正式使用时由各块 subagent 并行完成），其余全部步骤均为确定性脚本行为，可一键复现。

## 复现步骤

```bash
python examples/make_source_pdf.py                              # 1) 生成公有领域源 PDF
python scripts/extract_pdf.py examples/constitution_excerpt.pdf examples/run_extracted.txt
python scripts/split_chunks.py examples/run_extracted.txt examples/run_chunks --pages 1
# 2) 翻译：对每个 chunk_XXX.txt 产出 chunk_XXX_zh.md（保留页标记行）+ chunk_XXX_terms.json
#    （本示例的译文已就位，可直接从第 3 步继续）
python scripts/merge_glossary.py examples/run_chunks . --out examples/glossary_merged.json
python scripts/check_completeness.py examples/run_extracted.txt examples/run_chunks
python scripts/merge_chunks.py examples/run_chunks examples/constitution_excerpt_zh.md
python scripts/build_pdf.py examples/constitution_excerpt_zh.md examples/constitution_excerpt_zh.pdf
```

## 本次运行的质量数据（真实，非虚构）

| 指标 | 结果 |
|------|------|
| 页覆盖 | 2/2 页，`check_completeness` 通过（硬校验） |
| 长度比校验 | chunk_001 通过；chunk_002 触发 1 条 WARNING（比率 0.12 < 0.25）——**符合预期**：第 2 页源文仅 1.5 行（跨页段落尾部），该启发式按整页篇幅设计 |
| 术语表 | 2 个块的术语文件合并 16 条，冲突 0（首个登记者生效规则） |
| 引用保真 | `42 U.S.C. § 1983`、`Amendment I/XIV` 原样保留；「§ 1983」未遭翻译或改写 |
| 跨块衔接 | 第 1 块末句在页边界截断，第 2 块译文承接上文完成句子（上下文块未泄入译文） |
| 样本规模 | **N=1 篇 / 2 页**——仅证明流水线可用，不代表长文档批次统计 |

## 已知局限

- 长度比启发式对「末页只有少量内容」的文档会产生假阳性告警（如上），人工核验后放行是设计内动作
- 示例文档无表格、无页眉页脚，相关特性（表格转 Markdown、页眉剔除）未在此演示中覆盖
